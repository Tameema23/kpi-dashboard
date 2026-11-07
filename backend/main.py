"""
main.py — ApexTrack API (backend/ folder)
Imported as: from backend.database import ...
Run from project root: uvicorn backend.main:app

Security:
  ✓ bcrypt password hashing
  ✓ SECRET_KEY from environment variable
  ✓ CORS locked to your domain
  ✓ Rate limiting on /login — 5 attempts/minute per IP
  ✓ _require_admin infinite-recursion bug FIXED
  ✓ Input validation + HTML sanitization on all string fields
  ✓ Date/datetime format validation
  ✓ Timezone whitelist
  ✓ Numeric bounds on log entries
  ✓ JWT token_version — password change invalidates old tokens
  ✓ Soft password reset — short passwords are NOT broken,
    user gets a prompt on login to update to 8+ chars
  ✓ Audit log on sensitive actions
  ✓ Timing-safe login (prevents username enumeration)
"""

import os, re, json, html, logging, shutil, hashlib, asyncio, urllib.parse, secrets, tempfile, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, List
import httpx

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from passlib.context import CryptContext
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Time zones — imported before anything builds a zone ──────────────────────
# backend/timezones.py points zoneinfo at the pinned tzdata package and holds
# every time zone rule. See the notes at the top of that file.
from backend.timezones import (
    BUSINESS_TZ, BUSINESS_TZ_NAME, UTC, TZDATA_VERSION, ALLOWED_TIMEZONES,
    validate_tz, business_now, business_now_str, minutes_between, add_real_time,
    to_business, from_business, fmt_for_tz, fmt_hhmm, client_time_summary,
    timezone_options, tz_abbrev, tz_label, utc_offset_minutes,
)

# ── Import from same backend/ folder ─────────────────────────────────────────
from backend.database import SessionLocal, create_db, AppSetting, SmsLog, User, DailyLog, Appointment, AppointmentRecipient, QualityEntry, AuditLog, ReferralProgram, ReferralEntry, BlockedDay, BlockedDate, BlockedHour, BlockedHourRecurring, TimesheetEntry, TimesheetPunch, RcToken, BookingConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kpi")
logger.info(f"Time zones: business={BUSINESS_TZ_NAME}, tzdata={TZDATA_VERSION}")

# ── Build hash — computed once at startup from all JS/CSS file contents ────────
# This hash changes automatically every deploy whenever any frontend file changes.
# It is injected into every HTML response as the ?v= query string on static assets,
# so the browser is always forced to fetch the latest files after a deploy.
# Your client can log out and log back in to pick up new features — no Ctrl+R needed.

def _compute_build_hash() -> str:
    frontend_dir = "frontend"
    h = hashlib.md5()
    extensions = (".js", ".css", ".png", ".woff2")
    try:
        for root, dirs, files in os.walk(frontend_dir):
            dirs.sort()
            for fname in sorted(files):
                if any(fname.endswith(ext) for ext in extensions):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "rb") as f:
                            h.update(f.read())
                    except OSError:
                        pass
    except OSError:
        pass
    return h.hexdigest()[:10]  # short 10-char hash, e.g. "a3f9c1d820"

BUILD_HASH = _compute_build_hash()
logger.info(f"Build hash: {BUILD_HASH}")

# ── Secret key — MUST be set as environment variable on Render ────────────────
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set.\n"
        "Generate one in VS Code terminal:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "Then add it to Render → Environment → SECRET_KEY"
    )

ALGORITHM         = "HS256"
TOKEN_EXPIRE_DAYS = 7
MIN_PASSWORD_LEN  = 8
PASSWORD_EXPIRY_DAYS = 183  # ~6 months

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ── Scheduler ──────────────────────────────────────────────────────────────────
# Runs two daily SMS jobs in Mountain Time:
#   • 8:00 PM — evening reminder (night before appointment)
#   • Morning reminder (day of appointment) — 1 hour before the owner's first
#     open hour that day, derived from blocked hours (see _morning_text_hour)
# Both jobs respect dry_run mode — no real texts sent until live mode is on.

def _first_name_of(full_name: str) -> str:
    """First name, capitalized; 'there' if empty."""
    s = (full_name or "").strip()
    if not s:
        return "there"
    return s.split()[0].capitalize()


def _greeting_name_of(attendee_name: str, lead_name: str) -> str:
    """
    The name used in the SMS greeting.

    If an attendee name is set it is used exactly as typed, so an attendee
    of "Michelle & David" produces "Hi Michelle & David!". That field is
    filled in specifically for messaging, so what is typed is what sends.

    With no attendee name we fall back to the lead's FIRST name only,
    because lead_name holds a full legal name and "Hi Jimmy Tandawadon!"
    is not how we greet anyone.
    """
    attendee = (attendee_name or "").strip()
    if attendee:
        return attendee
    return _first_name_of(lead_name)


def _appt_recipients(db: Session, appt: Appointment):
    """
    Returns the full list of SMS recipients for an appointment as
    [(greeting_name, phone_number), ...] - the primary attendee/lead first,
    then any extra recipients. Only entries with a phone number are included.

    The greeting name is already resolved here (see _greeting_name_of), so
    callers send it straight into a message template without trimming it.

    Appointments booked through the public agent link are excluded entirely
    and permanently. Those clients have not agreed to hear from us, so even
    if someone later adds a phone number in the planner no text is ever sent.
    Enforced here rather than in each job because this is the single point
    every SMS path funnels through.
    """
    if getattr(appt, "booked_by_agent", False):
        return []

    out = []
    seen = set()   # one text per phone number, even if it is entered twice

    def _add(name: str, phone: str):
        key = _phone_key(phone)
        if key and key not in seen:
            seen.add(key)
            out.append((name, phone))

    primary_phone = (appt.phone_number or "").strip()
    if primary_phone:
        _add(_greeting_name_of(appt.attendee_name, appt.lead_name), primary_phone)
    try:
        extras = db.query(AppointmentRecipient).filter(
            AppointmentRecipient.appointment_id == appt.id
        ).all()
    except Exception:
        extras = []
    for r in extras:
        ph = (r.phone_number or "").strip()
        if ph:
            # Extra recipients are typed for messaging too, so their name is
            # used exactly as entered.
            _add((r.name or "").strip() or "there", ph)
    return out


def _phone_key(phone: str) -> str:
    """Use the full number so different country codes never collide."""
    return normalize_phone(phone)


def _sms_kind(log_tag: str) -> str:
    """'SMS EVENING' -> 'evening', 'CONFIRMED NOTICE' -> 'confirmed_notice'."""
    tag = re.sub(r"^SMS\s+", "", log_tag.strip(), flags=re.I)
    tag = re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", tag)          # drop a trailing date
    tag = re.sub(r"\s+CATCHUP$", "", tag, flags=re.I)          # same text as the booking one
    return re.sub(r"[^a-z0-9]+", "_", tag.lower()).strip("_")[:40] or "sms"


def _still_textable(appt: Appointment) -> bool:
    return _sms_status_allows_texting(appt) and _appt_is_upcoming(appt)


async def _send_to_all_recipients(db: Session, appt: Appointment, build_message,
                                 log_tag: str, still_ok=_still_textable):
    """Claim each send before contacting RingCentral. A retry skips accepted sends."""
    kind = _sms_kind(log_tag)
    appt_id = appt.id
    scheduled = appt.scheduled_for
    recipients = _appt_recipients(db, appt)
    sent = failed = settled = 0
    for _, phone in recipients:
        try:
            db.refresh(appt)
        except InvalidRequestError:
            break
        if appt.scheduled_for != scheduled or not still_ok(appt):
            break
        current = {_phone_key(number): name for name, number in _appt_recipients(db, appt)}
        phone = _phone_key(phone)
        if phone not in current:
            continue

        key = f"out:{appt_id}:{kind}:{scheduled}:{phone}"
        row = db.query(SmsLog).filter(SmsLog.dedupe_key == key).first()
        if row and row.status in ("sent", "suppressed"):
            settled += 1
            continue
        if row and row.status in ("sending", "uncertain"):
            continue
        if row and row.status == "dry_run":
            token = _get_rc_token(db, appt.owner_id)
            if token and token.dry_run:
                continue
        if row is None:
            row = SmsLog(dedupe_key=key, direction="out", kind=kind,
                         appointment_id=appt_id, phone=phone)
            db.add(row)
        message = build_message(current[phone])
        row.status = "sending"
        row.created_at = _mt_now_str_seconds()
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue

        result = await send_sms(db, appt.owner_id, phone, message)
        if result.get("sent"):
            row.status = "sent"
            sent += 1
            settled += 1
        elif result.get("dry_run"):
            row.status = "dry_run"
        elif result.get("skipped"):
            row.status = "suppressed"
            settled += 1
        elif result.get("uncertain"):
            row.status = "uncertain"
            failed += 1
        else:
            row.status = "failed"
            failed += 1
        row.detail = str(result.get("detail") or "")[:300]
        db.commit()

    complete = bool(recipients) and settled == len(recipients)
    if complete:
        try:
            db.refresh(appt)
        except InvalidRequestError:
            complete = False
        else:
            complete = appt.scheduled_for == scheduled and still_ok(appt)
            complete = complete and {_phone_key(phone) for _, phone in recipients} == {
                _phone_key(phone) for _, phone in _appt_recipients(db, appt)}
    return {"sent": sent, "failed": failed, "total": len(recipients), "complete": complete}


def _mt_now_str_seconds() -> str:
    return business_now().strftime("%Y-%m-%dT%H:%M:%S")


# ── Shared SMS eligibility rules ──────────────────────────────────────────────
# Every automated and manual client text goes through these, so a status set on
# the planner or confirmations page stops ALL texts, not just some of them.

def _mt_now_str() -> str:
    return business_now_str()


def _sms_status_allows_texting(appt: Appointment) -> bool:
    """False for callbacks and for any appointment marked rescheduled,
    cancelled or no-show on either status field."""
    if (appt.appt_type or "") == "callback":
        return False
    if appt.sms_status in RELEASED_STATUSES:
        return False
    if (getattr(appt, "appt_status", "") or "") in ("cancelled", "no_show", "rescheduled"):
        return False
    return True


def _appt_is_upcoming(appt: Appointment, now_str: Optional[str] = None) -> bool:
    """True if the appointment start time is still in the future (MT)."""
    return (appt.scheduled_for or "") > (now_str or _mt_now_str())


def _booked_within_minutes(appt: Appointment, minutes: int) -> bool:
    """True if booked_at is within the last `minutes` minutes."""
    try:
        booked_dt = datetime.strptime(appt.booked_at, "%Y-%m-%dT%H:%M").replace(tzinfo=BUSINESS_TZ)
        # Measured in UTC so a clock change can't stretch or shrink the window.
        return minutes_between(booked_dt, business_now()) <= minutes
    except Exception:
        return False


# If the booking confirmation went out this recently, the evening/morning
# confirmation is a near-identical duplicate, so it is skipped.
RECENT_BOOKING_TEXT_MINUTES = 120

# ── Morning text time follows working hours ───────────────────────────────────
# The morning confirmation goes out 1 hour before the owner's first open hour
# that day, read from the same blocked-day / blocked-hour data the planner
# uses. Change the hours in the planner and the text time follows, with no
# code change. Examples: open at 10 → text at 9; open at 9 → text at 8.
MORNING_TEXT_LEAD_HOURS    = 1
EARLIEST_MORNING_TEXT_HOUR = 7   # never text clients before 7 AM MT
DEFAULT_MORNING_TEXT_HOUR  = 9   # fallback when no open hour can be found


def _first_open_hour(db: Session, owner: Optional[int], date_str: str) -> Optional[int]:
    """First bookable hour on date_str for this owner, or None if the whole
    day is blocked (or there is no owner to read hours from)."""
    if owner is None:
        return None
    for h in range(PLANNER_FIRST_HOUR, PLANNER_LAST_HOUR + 1):
        if not slot_unavailable_reason(db, owner, f"{date_str}T{h:02d}:00"):
            return h
    return None


def _morning_text_hour(db: Session, owner: Optional[int], date_str: str) -> int:
    """Hour (MT, 24h) the morning confirmation goes out for this owner/day."""
    first = _first_open_hour(db, owner, date_str)
    if first is None:
        return DEFAULT_MORNING_TEXT_HOUR
    return max(EARLIEST_MORNING_TEXT_HOUR, first - MORNING_TEXT_LEAD_HOURS)


_ALL_OWNERS = object()   # sentinel: run a job across every owner

# Daily summaries to Tameema go out within this many minutes of 8 AM / 9 PM.
# Kept short so a restart later in the hour doesn't send a second summary.
SUMMARY_WINDOW_MIN = 15


async def _run_sms_job(job_type: str, owner_id=_ALL_OWNERS):
    """
    job_type: "evening" — sends to appointments TOMORROW
              "morning"  — sends to appointments TODAY
    owner_id: limit to one owner's appointments (the morning job runs per
              owner, because each owner's first open hour can differ).
              None means appointments with no owner. Default: everyone.
    """
    db = SessionLocal()
    try:
        mt = BUSINESS_TZ
        now_mt    = datetime.now(mt)
        today_str = now_mt.strftime("%Y-%m-%d")

        if job_type == "evening":
            target_date = (now_mt + timedelta(days=1)).strftime("%Y-%m-%d")
            sent_flag   = "sms_sent_evening"
            template    = SMS_EVENING_TEMPLATE
            label       = "evening"
        else:
            target_date = today_str
            sent_flag   = "sms_sent_morning"
            template    = SMS_MORNING_TEMPLATE
            label       = "morning"

        # Get all appointments on the target date that haven't been texted yet
        appts = db.query(Appointment).filter(
            Appointment.scheduled_for.startswith(target_date),
        ).all()
        if owner_id is not _ALL_OWNERS:
            appts = [a for a in appts if a.owner_id == owner_id]
        # Cancelled, no-show, rescheduled and callbacks never get texts
        appts = [a for a in appts if _sms_status_allows_texting(a)]
        now_str = _mt_now_str()

        for appt in appts:
            # Skip if already sent this message
            already_sent = getattr(appt, sent_flag)
            if already_sent:
                continue

            # Never text a confirmation for a time that has already passed
            # (e.g. an 8:30 AM appointment when the 9 AM job runs).
            if not _appt_is_upcoming(appt, now_str):
                continue

            # Already covered: the booking text sent this same confirmation
            # very recently. Mark it done so the manual button doesn't
            # re-send it either.
            if (getattr(appt, "sms_sent_booking", False)
                    and _booked_within_minutes(appt, RECENT_BOOKING_TEXT_MINUTES)):
                setattr(appt, sent_flag, True)
                db.commit()
                continue

            # Format time and date in the booking timezone
            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )

            confirmed  = _is_confirmed(appt)

            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: _build_sms(fn, time_display, date_display, confirmed),
                f"SMS {label.upper()}"
            )

            # Leave this job retryable until all recipients are covered.
            if summary["complete"]:
                setattr(appt, sent_flag, True)
                db.commit()

    except Exception as e:
        logger.error(f"SMS job ({job_type}) error: {e}")
    finally:
        db.close()


async def _send_confirmation_texts_for_date(target_date: str) -> dict:
    """
    Send the appointment confirmation SMS to every eligible client whose
    appointment falls on target_date (YYYY-MM-DD) and who hasn't already
    been reached about it.

    This powers the manual "Send Confirmation Texts" button on the
    confirmations page, scoped to the selected day only.

    Eligibility mirrors the scheduled jobs:
      - has a phone number
      - not a callback
      - not rescheduled / cancelled / no_show

    On top of that, this is a catch-up mechanism only — it must NOT
    re-text anyone who has already been reached about this appointment:
      - already confirmed (sms_status or appt_status == "confirmed") → skip
      - already sent the evening OR morning automated text → skip
      - already sent by this button before (second click) → skip
      - appointment time has already passed → skip
    Everyone else (never texted yet for this appointment) gets sent.

    After a successful send, the evening/morning flag for the job that would
    cover this appointment next is set too, so the client doesn't get the
    same text again a few hours later from the scheduler.
    Returns a small summary dict for UI feedback.
    """
    db = SessionLocal()
    sent = 0
    skipped = 0
    failed = 0
    try:
        appts = db.query(Appointment).filter(
            Appointment.scheduled_for.startswith(target_date),
        ).all()
        appts = [a for a in appts if _sms_status_allows_texting(a)]

        mt       = BUSINESS_TZ
        now_mt   = datetime.now(mt)
        now_str  = now_mt.strftime("%Y-%m-%dT%H:%M")
        today    = now_mt.strftime("%Y-%m-%d")
        tomorrow = (now_mt + timedelta(days=1)).strftime("%Y-%m-%d")

        eligible = []
        for appt in appts:
            if _is_confirmed(appt):
                skipped += 1
                continue
            if (getattr(appt, "sms_sent_morning", False)
                    or getattr(appt, "sms_sent_evening", False)
                    or getattr(appt, "sms_sent_manual", False)):
                skipped += 1
                continue
            if not _appt_is_upcoming(appt, now_str):
                skipped += 1
                continue
            # They got this same confirmation from the booking text moments ago
            # (the scheduled jobs apply the same rule).
            if (getattr(appt, "sms_sent_booking", False)
                    and _booked_within_minutes(appt, RECENT_BOOKING_TEXT_MINUTES)):
                skipped += 1
                continue
            eligible.append(appt)

        for appt in eligible:
            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )
            # Every appt reaching this point is unconfirmed (filtered above),
            # so it always gets the 'reply YES' prompt.
            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: _build_sms(fn, time_display, date_display, False),
                f"SMS MANUAL-CONFIRM {target_date}",
                still_ok=lambda a: _still_textable(a) and not _is_confirmed(a),
            )
            sent   += summary["sent"]
            failed += summary["failed"]
            # Mark that a YES-prompt text went out via the manual button, so the
            # inbound webhook can match this appointment. Without this the client
            # replies YES and nothing happens.
            if summary["complete"]:
                appt.sms_sent_manual = True
                # Stop the scheduler repeating this same text: today's
                # appointments are covered by the 9 AM job, tomorrow's by
                # tonight's 8 PM job.
                if target_date == today:
                    appt.sms_sent_morning = True
                elif target_date == tomorrow:
                    appt.sms_sent_evening = True

        db.commit()
        return {"sent": sent, "failed": failed, "skipped": skipped, "total": len(appts)}
    except Exception as e:
        logger.error(f"Manual confirmation texts error ({target_date}): {e}")
        return {"sent": sent, "failed": failed, "skipped": skipped, "total": sent + failed, "error": str(e)}
    finally:
        db.close()


async def _run_reminder_job():
    """
    Fires every minute (called from scheduler).
    Sends a quick reminder to UNCONFIRMED appointments shortly before they start.

    Timing, decided per appointment, relative to that day's morning text
    (which is 1 hour before the first open hour, from blocked hours):
      - normally 60 minutes before the start time
      - if 60 minutes before would land at or before the morning text,
        send 30 minutes before instead so the two don't collide
      - if even 30 minutes before would collide, skip it: the morning text
        just went out and serves as the reminder

    Skipped when the client booked within the last hour: the booking
    confirmation they just received already covers it.
    Tracked via sms_sent_reminder.
    """
    db = SessionLocal()
    try:
        mt     = BUSINESS_TZ
        now_mt = datetime.now(mt)

        # Pull everything starting in the next ~61 minutes, then decide per
        # appointment which lead time applies.
        start_str = add_real_time(now_mt, timedelta(minutes=29)).strftime("%Y-%m-%dT%H:%M")
        end_str   = add_real_time(now_mt, timedelta(minutes=61)).strftime("%Y-%m-%dT%H:%M")

        appts = db.query(Appointment).filter(
            Appointment.scheduled_for >= start_str,
            Appointment.scheduled_for <= end_str,
            or_(Appointment.sms_sent_reminder == False,
                Appointment.sms_sent_reminder == None),
        ).all()
        appts = [a for a in appts
                 if _sms_status_allows_texting(a) and not _is_confirmed(a)]

        for appt in appts:
            try:
                start_dt = datetime.strptime(appt.scheduled_for, "%Y-%m-%dT%H:%M").replace(tzinfo=mt)
            except Exception:
                continue
            # Anchor to this owner's morning text time for that day, which
            # follows their working hours (see _morning_text_hour).
            morning_dt = start_dt.replace(
                hour=_morning_text_hour(db, appt.owner_id, appt.scheduled_for[:10]),
                minute=0)
            if (start_dt - timedelta(minutes=30)) <= morning_dt:
                # Starts within 30 min of the morning text; that text is the reminder.
                continue
            lead    = 60 if (start_dt - timedelta(minutes=60)) > morning_dt else 30
            mins_to_start = minutes_between(now_mt, start_dt)
            # Fire inside a 2-minute window around the chosen lead time
            if not (lead - 1 <= mins_to_start <= lead + 1):
                continue

            if _booked_within_minutes(appt, 60):
                appt.sms_sent_reminder = True
                db.commit()
                continue

            time_display, _ = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )
            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: SMS_REMINDER_TEMPLATE.format(name=fn, time=time_display),
                "SMS REMINDER",
                still_ok=lambda a: _still_textable(a) and not _is_confirmed(a),
            )
            # Only mark it done if a text actually went out, so a failed send
            # is retried on the next pass inside the window.
            if summary["complete"]:
                appt.sms_sent_reminder = True
                db.commit()

    except Exception as e:
        logger.error(f"Reminder job error: {e}")
    finally:
        db.close()


async def _run_booking_job():
    """
    Fires every minute. Finds appointments booked 4–6 minutes ago that haven't
    received the booking confirmation text yet, and sends it.
    Also catches any appointments booked today that still haven't received it
    (catch-up for missed sends).
    """
    db = SessionLocal()
    try:
        mt     = BUSINESS_TZ
        now_mt = datetime.now(mt)
        today  = now_mt.strftime("%Y-%m-%d")

        # Find all appointments booked today that haven't received booking text
        appts = db.query(Appointment).filter(
            Appointment.booked_at.startswith(today),
        ).all()
        appts = [a for a in appts
                 if not getattr(a, "sms_sent_booking", False)
                 and _sms_status_allows_texting(a)]
        now_str = now_mt.strftime("%Y-%m-%dT%H:%M")

        for appt in appts:
            # Only fire if booked 4–6 minutes ago OR it's been more than 6 minutes
            # (catch-up: anything booked today that hasn't been sent yet)
            try:
                booked_dt = datetime.strptime(appt.booked_at, "%Y-%m-%dT%H:%M").replace(tzinfo=mt)
                mins_since = minutes_between(booked_dt, now_mt)
                if mins_since < 4:
                    continue  # Too soon — wait for the 5-minute window
            except Exception:
                continue

            # Appointments entered after the fact (time already passed) must
            # never get a "confirmation for your meeting" text.
            if not _appt_is_upcoming(appt, now_str):
                appt.sms_sent_booking = True
                db.commit()
                continue

            # The evening/morning/manual text already delivered this exact
            # confirmation (e.g. booked at 7:58 PM, evening job ran at 8:00 PM).
            if (getattr(appt, "sms_sent_evening", False)
                    or getattr(appt, "sms_sent_morning", False)
                    or getattr(appt, "sms_sent_manual", False)):
                appt.sms_sent_booking = True
                db.commit()
                continue

            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )
            confirmed  = _is_confirmed(appt)

            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: _build_sms(fn, time_display, date_display, confirmed),
                "SMS BOOKING"
            )
            # A failed send (e.g. RingCentral out of credits) stays retryable:
            # this job runs every minute. A later retry that does get through
            # can't double up, because the duplicate guard in send_sms skips
            # anyone who already has this exact text.
            if summary["complete"]:
                appt.sms_sent_booking = True
                db.commit()

    except Exception as e:
        logger.error(f"Booking job error: {e}")
    finally:
        db.close()


async def _run_booking_job_catchup():
    """
    One-time catch-up: sends booking confirmation to ALL future appointments
    that haven't received one yet, regardless of when they were originally booked.
    Used when appointments are rescheduled or when the feature is first deployed.
    """
    db = SessionLocal()
    try:
        mt    = BUSINESS_TZ
        today = datetime.now(mt).strftime("%Y-%m-%d")

        # All future appointments (scheduled_for >= today) without booking text
        appts = db.query(Appointment).filter(
            Appointment.scheduled_for >= today,
        ).all()
        now_str = _mt_now_str()
        appts = [a for a in appts
                 if not getattr(a, "sms_sent_booking", False)
                 and _sms_status_allows_texting(a)
                 and _appt_is_upcoming(a, now_str)]

        sent_count = 0
        for appt in appts:
            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )
            confirmed  = _is_confirmed(appt)

            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: _build_sms(fn, time_display, date_display, confirmed),
                "SMS BOOKING CATCHUP"
            )
            if summary["complete"]:
                appt.sms_sent_booking = True
                db.commit()
                sent_count += 1

        logger.info(f"[SMS BOOKING CATCHUP] Sent to {sent_count} appointment(s).")

    except Exception as e:
        logger.error(f"Booking catchup job error: {e}")
    finally:
        db.close()


async def _run_midpoint_job():
    """
    Fires once daily. Sends a reminder to appointments whose midpoint_send_date
    is today — i.e. halfway between booking and appointment date.
    Only applies to appointments booked 5+ days before the appointment.
    """
    db = SessionLocal()
    try:
        mt    = BUSINESS_TZ
        today = datetime.now(mt).strftime("%Y-%m-%d")

        appts = db.query(Appointment).filter(Appointment.midpoint_send_date == today).all()
        now_str = _mt_now_str()
        appts = [a for a in appts
                 if not getattr(a, "sms_sent_midpoint", False)
                 and _sms_status_allows_texting(a)
                 and _appt_is_upcoming(a, now_str)]

        for appt in appts:
            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or BUSINESS_TZ_NAME
            )
            confirmed  = _is_confirmed(appt)

            summary = await _send_to_all_recipients(
                db, appt,
                lambda fn: _build_sms(fn, time_display, date_display, confirmed),
                "SMS MIDPOINT"
            )
            if summary["complete"]:
                appt.sms_sent_midpoint = True
                db.commit()

    except Exception as e:
        logger.error(f"Midpoint job error: {e}")
    finally:
        db.close()


async def _scheduler_loop():
    mt = BUSINESS_TZ
    fired = {
        "evening":         None,
        "morning":         None,
        "summary_morning": None,   # 8am — today's appointments
        "summary_evening": None,   # 9pm — tomorrow's appointments
        "summary_retry":   None,   # retry flag for 9pm
        "midpoint":        None,   # 10am — midpoint reminders
    }
    summary_evening_sent = {}  # date → bool, tracks if 9pm actually succeeded
    morning_fired        = {}  # owner_id → date the morning job last ran

    while True:
        try:
            now    = datetime.now(mt)
            today  = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            h, min_ = now.hour, now.minute

            # Fixed-time jobs match a window, not the exact minute. Each loop
            # takes 60s plus however long that pass's work took, so the loop
            # slowly drifts and can step straight over minute 0. A job pinned
            # to `min_ == 0` (the 8 PM confirmations, for example) would then
            # be skipped for the whole day. The `fired` dates and the per-
            # appointment sms_sent_* flags stop anything running twice.
            # 8:00 AM — send TODAY's appointment list
            if h == 8 and min_ < SUMMARY_WINDOW_MIN and fired["summary_morning"] != today:
                fired["summary_morning"] = today
                logger.info("Scheduler: firing 8am daily summary (today's appointments)")
                await _send_daily_summary(today)

            # Morning client texts — 1 hour before each owner's first open
            # hour today (from blocked hours). Checked across the whole hour,
            # not just minute 0, so a slow loop or a restart can't skip it;
            # the sms_sent_morning flag prevents any double send.
            due_owners = []
            sdb = SessionLocal()
            try:
                # Every owner with an appointment today, whatever their role.
                # (Listing only admins skipped appointments owned by anyone
                # else, so those clients never got a morning text.)
                owner_keys = {row[0] for row in sdb.query(Appointment.owner_id)
                              .filter(Appointment.scheduled_for.startswith(today))
                              .distinct().all()}
                for oid in owner_keys:
                    if morning_fired.get(oid) == today:
                        continue
                    if h == _morning_text_hour(sdb, oid, today):
                        due_owners.append(oid)
            finally:
                sdb.close()
            for oid in due_owners:
                morning_fired[oid] = today
                logger.info(f"Scheduler: firing morning SMS job for owner {oid} at {h}:00")
                await _run_sms_job("morning", owner_id=oid)

            # 8:00 PM — evening client texts (tomorrow's appointments).
            # Whole hour: sms_sent_evening stops repeats after a restart.
            if h == 20 and fired["evening"] != today:
                fired["evening"] = today
                logger.info("Scheduler: firing evening SMS job")
                await _run_sms_job("evening")

            # 9:00 PM — send TOMORROW's appointment list
            if h == 21 and min_ < SUMMARY_WINDOW_MIN and fired["summary_evening"] != today:
                fired["summary_evening"] = today
                logger.info("Scheduler: firing 9pm daily summary (tomorrow's appointments)")
                sent = await _send_daily_summary(tomorrow)
                summary_evening_sent[today] = sent

            # Next pass after 9 PM — retry once if the 9pm summary failed
            elif (h == 21 and fired["summary_evening"] == today
                    and fired["summary_retry"] != today):
                fired["summary_retry"] = today
                if summary_evening_sent.get(today) is False:
                    logger.info("Scheduler: retrying 9pm summary (previous attempt failed)")
                    await _send_daily_summary(tomorrow)

            # Every minute — 1hr reminder for unconfirmed appointments
            await _run_reminder_job()

            # Every minute — booking confirmation (~5 min after booking)
            await _run_booking_job()

            # Once daily at 10:00 AM — midpoint reminders.
            # Whole hour: sms_sent_midpoint stops repeats after a restart.
            if h == 10 and fired.get("midpoint") != today:
                fired["midpoint"] = today
                logger.info("Scheduler: firing midpoint SMS job")
                await _run_midpoint_job()

        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")

        # Wake just after the next minute boundary instead of a flat 60s,
        # so the time spent sending texts doesn't push the loop later and later.
        await asyncio.sleep(60 - (time.time() % 60) + 1)

@asynccontextmanager
async def lifespan(app):
    """Start background scheduler on app startup."""
    task = asyncio.create_task(_scheduler_loop())
    logger.info("SMS scheduler started.")
    # Fire and forget: a RingCentral hiccup must never block startup.
    cleanup = asyncio.create_task(_cleanup_rc_webhooks_on_startup())  # noqa: F841 (keep a reference)
    yield
    task.cancel()
    logger.info("SMS scheduler stopped.")


# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ApexTrack",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — locked to your actual domain ───────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://apextrack.oneconnectors.com,https://data-log.onrender.com"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Security + caching headers — added to every response ──────────────────────
# Plain ASGI middleware rather than BaseHTTPMiddleware: it only edits headers
# as they pass through, so it adds no per-request overhead and never buffers
# a response body.
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options":    "nosniff",
    "X-Frame-Options":           "DENY",
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    "Permissions-Policy":        "geolocation=(), microphone=(), camera=()",
    # Everything (scripts, fonts, charts, Excel export) is served from this
    # origin, so no third-party host is allowed.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    ),
}


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        # Only the current build's hash proves the bytes match this deploy.
        # Anything else (an old hash, a hand-set ?v=1) gets a short cache.
        query = urllib.parse.parse_qs(scope.get("query_string", b"").decode("latin-1"))
        versioned = query.get("v") == [BUILD_HASH]

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in _SECURITY_HEADERS.items():
                    headers[k] = v
                ctype = headers.get("content-type", "")
                if "text/html" in ctype or path.startswith("/static/") and path.endswith(".html"):
                    # Pages must always be fresh so a deploy shows up at once.
                    headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                    headers["Pragma"] = "no-cache"
                elif path.startswith("/static/") and message.get("status", 200) in (200, 304):
                    # Every page links its assets with ?v=<build hash>, and the
                    # hash changes whenever any asset changes. A versioned URL
                    # therefore never changes content: cache it for a year.
                    headers["Cache-Control"] = ("public, max-age=31536000, immutable"
                                                if versioned else "public, max-age=3600")
                    if "accept-encoding" not in headers.get("vary", "").lower():
                        headers.add_vary_header("Accept-Encoding")
                    etag = headers.get("etag")
                    if etag and not etag.startswith("W/"):
                        headers["ETag"] = "W/" + etag
                elif path == "/appointments" and headers.get("etag"):
                    if "accept-encoding" not in headers.get("vary", "").lower():
                        headers.add_vary_header("Accept-Encoding")
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(SecurityHeadersMiddleware)

# ── Frontend pages ─────────────────────────────────────────────────────────────
# Each page is read once at startup with every ?v= asset reference stamped with
# BUILD_HASH, then served from memory. No disk read and no body rewriting per
# request, and every asset URL changes automatically on each deploy.
# Fonts keep their fixed ?v= so the <link rel="preload"> and the @font-face URL
# in style.css stay identical (otherwise the font downloads twice).
_ASSET_VERSION = re.compile(r'(\.(?:js|css|png|json))\?v=[^"\'&\s]+')
_PAGE_CACHE: dict = {}


def _page(name: str, extra_headers: Optional[dict] = None) -> Response:
    body = _PAGE_CACHE.get(name)
    if body is None:
        with open(os.path.join("frontend", name), encoding="utf-8") as f:
            html_text = f.read()
        body = _ASSET_VERSION.sub(lambda m: m.group(1) + "?v=" + BUILD_HASH,
                                  html_text).encode("utf-8")
        _PAGE_CACHE[name] = body
    return Response(content=body, media_type="text/html; charset=utf-8",
                    headers=extra_headers)


app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_home():     return _page("login.html")
@app.get("/index.html")
def dashboard():      return _page("index.html")
@app.get("/log.html")
def log_page():       return _page("log.html")
@app.get("/reports.html")
def reports_page():   return _page("reports.html")
@app.get("/history.html")
def history_page():   return _page("history.html")
@app.get("/settings.html")
def settings_page():  return _page("settings.html")
@app.get("/planner.html")
def planner_page():   return _page("planner.html")
@app.get("/quality.html")
def quality_page():   return _page("quality.html")
@app.get("/referrals.html")
def referrals_page(): return _page("referrals.html")
@app.get("/timesheet.html")
def timesheet_page(): return _page("timesheet.html")

@app.get("/manifest.json")
def manifest():      return FileResponse("frontend/manifest.json", media_type="application/manifest+json")

@app.get("/icon-192.png")
def icon192():       return FileResponse("frontend/images/icon-192.png", media_type="image/png")

@app.get("/icon-512.png")
def icon512():       return FileResponse("frontend/images/icon-512.png", media_type="image/png")

# ── DB ─────────────────────────────────────────────────────────────────────────
create_db()

def get_db():
    db = SessionLocal()
    try:    yield db
    finally: db.close()

# ── Sanitization helpers ───────────────────────────────────────────────────────

def sanitize_str(value: str, max_len: int = 500) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"<[^>]+>", "", value)
    return cleaned[:max_len].strip()

def title_case(s: str) -> str:
    """Normalize name capitalization: 'JIMMY TANDAWADON' → 'Jimmy Tandawadon'."""
    if not s:
        return s
    return " ".join(word.capitalize() for word in s.strip().split())

def validate_date(value: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date value.")
    return value

def validate_datetime(value: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", value):
        raise HTTPException(400, "Invalid datetime format. Use YYYY-MM-DDTHH:MM.")
    # The pattern alone accepts values like 2026-02-30T14:00 or T25:00, which
    # later crash date parsing with a 500. Reject them here with a clean 400.
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise HTTPException(400, "Invalid date or time.")
    return value

# ALLOWED_TIMEZONES and validate_tz live in backend/timezones.py.

def validate_username(username: str) -> str:
    username = username.strip()
    if not re.match(r"^[a-zA-Z0-9_]{3,30}$", username):
        raise HTTPException(
            400,
            "Username must be 3–30 characters and contain only "
            "letters, numbers, and underscores."
        )
    return username

def validate_new_password(password: str) -> str:
    """Used when CREATING or CHANGING a password. Enforces 8-char minimum."""
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            400,
            f"Password must be at least {MIN_PASSWORD_LEN} characters."
        )
    return password

# ── Audit log ──────────────────────────────────────────────────────────────────

def audit(db: Session, user_id: int, action: str, detail: str = ""):
    try:
        now = business_now().strftime("%Y-%m-%dT%H:%M:%S")
        db.add(AuditLog(user_id=user_id, action=action,
                        detail=detail[:500], timestamp=now))
        db.commit()
    except Exception as e:
        logger.error(f"Audit log failed: {e}")

# ── JWT ────────────────────────────────────────────────────────────────────────

def _midnight_utc() -> datetime:
    """Returns naive UTC datetime for midnight tonight in the business zone."""
    now_mt = business_now()
    midnight_mt = now_mt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return midnight_mt.astimezone(UTC).replace(tzinfo=None)

def create_token(user_id: int, role: str, token_version: int,
                 can_planner: bool = True, can_quality: bool = False,
                 can_confirmations: bool = False,
                 password_expires_at: Optional[str] = None) -> str:
    return jwt.encode({
        "user_id":             user_id,
        "role":                role,
        "token_version":       token_version,
        "can_planner":         can_planner,
        "can_quality":         can_quality,
        "can_confirmations":   can_confirmations,
        # Token expires at midnight Mountain Time — forces daily re-login
        "exp":                 _midnight_utc(),
        "iat":                 datetime.utcnow(),
        # Password expiry date so the frontend can warn the user
        "password_expires_at": password_expires_at or "",
    }, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str = Header(...),
                     db: Session = Depends(get_db)) -> User:
    err = HTTPException(
        status_code=401,
        detail="Session expired or invalid. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token   = authorization.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid     = payload.get("user_id")
        tv      = payload.get("token_version", 0)
        if uid is None:
            raise err
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            raise err
        # Token version mismatch = password was changed, token is revoked
        if (user.token_version or 0) != tv:
            raise err
        return user
    except JWTError:
        raise err

# ── Permission guards ──────────────────────────────────────────────────────────

def _require_admin(user: User):
    # NOTE: Original code had infinite recursion here — this is the fixed version
    if user.role != "admin":
        raise HTTPException(403, "Admin access required.")

def _has_planner_access(user: User) -> bool:
    return user.role == "admin" or bool(user.can_planner)

def _check_planner_access(user: User):
    if _has_planner_access(user):
        return
    raise HTTPException(403, "No planner access.")

def _check_quality_access(user: User):
    if user.role == "admin" or bool(user.can_quality):
        return
    raise HTTPException(403, "No quality access.")

def _check_confirmations_access(user: User):
    """
    Confirmations page access. Allowed for:
      - any admin
      - any user with can_confirmations = True (e.g. Tameema23, Yousef)
    """
    if user.role == "admin" or bool(getattr(user, "can_confirmations", False)):
        return
    raise HTTPException(403, "No confirmations access.")

def get_owner_id(user: User) -> int:
    return user.owner_id if user.role == "assistant" else user.id


# ── Availability ──────────────────────────────────────────────────────────────
# Working hours and days off are NOT hardcoded. They are whatever the admin has
# configured via the blocked-day / blocked-date / blocked-hour tables, so a
# different client with different hours needs no code change. Every consumer —
# the planner, and later the public booking page — asks these helpers rather
# than carrying its own copy of the rules.

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday",
             "Thursday", "Friday", "Saturday"]


def normalize_phone(raw: str) -> str:
    """
    Coerce a typed phone number into E.164, which is what RingCentral requires.
    A number stored without its country code is accepted silently by the DB and
    then fails to send, so normalising at the edge prevents a class of invisible
    SMS failures.

      "(403) 555-0134"  → "+14035550134"
      "403-555-0134"    → "+14035550134"
      "14035550134"     → "+14035550134"
      "+14035550134"    → "+14035550134"   (unchanged)
      "+442071234567"   → "+442071234567"  (non-NANP left alone)
      ""                → ""
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    has_plus = raw.startswith("+")
    digits   = re.sub(r"[^\d]", "", raw)
    if not digits:
        return ""
    if has_plus:
        return ("+" + digits)[:20]          # already international
    if len(digits) == 10:                   # North American, no country code
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ("+" + digits)[:20]              # best effort for anything else


def js_dow(date_str: str) -> int:
    """Day-of-week for YYYY-MM-DD in JS convention: 0=Sunday … 6=Saturday."""
    return (datetime.strptime(date_str[:10], "%Y-%m-%d").weekday() + 1) % 7


def blocked_day_reason(db: Session, owner: int, date_str: str) -> Optional[str]:
    """Why this whole date is unavailable, or None if it is open."""
    dow = js_dow(date_str)
    if db.query(BlockedDay).filter(
        BlockedDay.owner_id == owner, BlockedDay.day_of_week == dow
    ).first():
        return (f"{DAY_NAMES[dow]} is marked as unavailable. "
                f"Appointments cannot be scheduled on this day.")
    if db.query(BlockedDate).filter(
        BlockedDate.owner_id == owner, BlockedDate.date == date_str[:10]
    ).first():
        return (f"{date_str[:10]} is marked as unavailable. "
                f"Appointments cannot be scheduled on this date.")
    return None


def blocked_hour_reason(db: Session, owner: int, scheduled_for: str) -> Optional[str]:
    """
    Why this specific hour is unavailable, or None if it is open.
    Covers one-off hour blocks and recurring blocks (daily or per-weekday).
    """
    date_str = scheduled_for[:10]
    try:
        hour = int(scheduled_for[11:13])
    except (ValueError, IndexError):
        return None

    one_off = db.query(BlockedHour).filter(
        BlockedHour.owner_id   == owner,
        BlockedHour.date       == date_str,
        BlockedHour.start_hour <= hour,
        BlockedHour.end_hour   >  hour,
    ).first()
    if one_off:
        return f"{one_off.label or 'This time'} is blocked on {date_str}."

    dow = js_dow(date_str)
    for r in db.query(BlockedHourRecurring).filter(
        BlockedHourRecurring.owner_id   == owner,
        BlockedHourRecurring.start_hour <= hour,
        BlockedHourRecurring.end_hour   >  hour,
    ).all():
        r_dow = getattr(r, "day_of_week", None)
        if r_dow is None or r_dow == dow:
            when = "every day" if r_dow is None else f"every {DAY_NAMES[dow]}"
            return f"{r.label or 'This time'} is blocked {when}."
    return None


def slot_unavailable_reason(db: Session, owner: int,
                            scheduled_for: str) -> Optional[str]:
    """Combined check. None means the slot is free to book."""
    return (blocked_day_reason(db, owner, scheduled_for)
            or blocked_hour_reason(db, owner, scheduled_for))


# ── Same-day notice ───────────────────────────────────────────────────────────
# Assistants on the planner and agents on the public booking link cannot book
# a slot that starts sooner than this many hours from now. Opening the calendar
# at 10:00 makes 14:00 the earliest slot; at 10:15 it is 15:00. Admins are
# exempt. Set SAME_DAY_LEAD_HOURS in the environment to change it (0 disables).
def _lead_hours_from_env() -> int:
    try:
        return max(0, min(24, int(os.environ.get("SAME_DAY_LEAD_HOURS", "4"))))
    except ValueError:
        return 4

SAME_DAY_LEAD_HOURS = _lead_hours_from_env()


def earliest_bookable(now: Optional[datetime] = None) -> str:
    """
    First moment a restricted booker may book, as YYYY-MM-DDTHH:MM Mountain.
    The offset is added in UTC so a DST change can never shorten the notice.
    """
    mt  = BUSINESS_TZ
    now = now or datetime.now(mt)
    out = now.astimezone(UTC) + timedelta(hours=SAME_DAY_LEAD_HOURS)
    return out.astimezone(mt).strftime("%Y-%m-%dT%H:%M")


def _fmt_cutoff(stamp: str) -> str:
    """'2026-09-28T14:15' -> '2:15 PM' (with the date if it is not today)."""
    dt   = datetime.strptime(stamp, "%Y-%m-%dT%H:%M")
    h12  = dt.hour % 12 or 12
    text = f"{h12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    today = business_now().strftime("%Y-%m-%d")
    if stamp[:10] != today:
        text = f"{dt.strftime('%b')} {dt.day}, {text}"
    return text


def lead_time_reason(scheduled_for: str) -> Optional[str]:
    """Why this start time is too soon, or None if it gives enough notice."""
    now = business_now().strftime("%Y-%m-%dT%H:%M")
    if scheduled_for[:16] < now:
        return "That time has already passed. Please pick another time."
    if SAME_DAY_LEAD_HOURS <= 0:
        return None
    cutoff = earliest_bookable()
    if scheduled_for[:16] < cutoff:
        return (f"Same-day appointments need at least {SAME_DAY_LEAD_HOURS} "
                f"hours' notice. Please pick a time at or after "
                f"{_fmt_cutoff(cutoff)} (Mountain Time).")
    return None

# ── One appointment per hour ─────────────────────────────────────────────────
# No two appointments may share a clock hour (1:00 and 1:30 clash). Callbacks
# never clash with anything, so a callback can sit beside an appointment.
# Cancelled appointments release their hour. A missing appt_type is treated as
# an appointment, matching _appt_dict. The planner, the agent link, and the
# availability grid all ask this one helper, so they cannot disagree.
# An appointment marked cancelled or rescheduled is not happening at that
# time any more, so it gives its hour back. (Rescheduled used to keep holding
# the old hour, so nobody else could be booked into a slot the client had
# already moved out of.) Restoring one re-checks the hour first.
RELEASED_STATUSES = ("cancelled", "rescheduled")


def releases_slot(appt_status: Optional[str], sms_status: Optional[str] = "") -> bool:
    return appt_status in RELEASED_STATUSES or sms_status in RELEASED_STATUSES


def appointment_conflict(db: Session, owner: int, scheduled_for: str,
                         exclude_id: Optional[int] = None):
    """The active appointment already holding this hour, or None."""
    q = db.query(Appointment).filter(
        Appointment.owner_id == owner,
        Appointment.scheduled_for >= scheduled_for[:13] + ":00",
        Appointment.scheduled_for <= scheduled_for[:13] + ":59",
        or_(Appointment.appt_status.is_(None),
            Appointment.appt_status.notin_(RELEASED_STATUSES)),
        or_(Appointment.sms_status.is_(None),
            Appointment.sms_status.notin_(RELEASED_STATUSES)),
        or_(Appointment.appt_type.is_(None),
            Appointment.appt_type != "callback"),
    )
    if exclude_id is not None:
        q = q.filter(Appointment.id != exclude_id)
    return q.first()


def conflict_message(scheduled_for: str) -> str:
    dt  = datetime.strptime(scheduled_for[:13], "%Y-%m-%dT%H")
    h12 = dt.hour % 12 or 12
    return (f"There is already an appointment booked at {h12}:00 "
            f"{'AM' if dt.hour < 12 else 'PM'} on {dt.strftime('%b')} {dt.day}. "
            f"Only one appointment can be booked per hour. "
            f"Pick another time, or book this as a callback.")


# ── Auth ───────────────────────────────────────────────────────────────────────

class UserPayload(BaseModel):
    username: str
    password: str

def _signup_code() -> str:
    return os.environ.get("SIGNUP_CODE", "").strip()


def _signup_open() -> bool:
    """
    Self-signup creates an ADMIN account, so it is closed unless the operator
    sets SIGNUP_CODE in Render's environment. Even then, a new account needs
    that code, so a visitor who finds the form still can't get in. Remove the
    variable once the account exists. Assistants are added by an admin from
    Settings, and a locked-out owner is reset from the Render shell with
    `python -m backend.reset_password <username>`.
    """
    return bool(_signup_code())


class SignupPayload(BaseModel):
    username: str
    password: str
    signup_code: Optional[str] = ""


@app.get("/signup-status")
def signup_status():
    return {"open": _signup_open()}


@app.post("/create-user", status_code=201)
@limiter.limit("5/minute")
def create_user(request: Request, data: SignupPayload, db: Session = Depends(get_db)):
    code = _signup_code()
    if not code or not secrets.compare_digest((data.signup_code or "").strip().encode(), code.encode()):
        raise HTTPException(403, "New accounts are created by your administrator.")
    username = validate_username(data.username)
    password = validate_new_password(data.password)  # enforce 8+ on new accounts
    if db.query(User).filter(User.username.ilike(username)).first():
        raise HTTPException(400, "Username already exists.")
    db.add(User(
        username=username,
        password=hash_password(password),
        role="admin",
        owner_id=None,
        token_version=0,
        needs_password_reset=False,
    ))
    db.commit()
    return {"status": "created"}

@app.post("/login")
@limiter.limit("5/minute")
def login(request: Request, data: UserPayload, db: Session = Depends(get_db)):
    username = data.username.strip()
    if not username or not data.password:
        raise HTTPException(400, "Username and password are required.")

    user = db.query(User).filter(User.username == username).first()

    # Always call verify_password even if user not found
    # This prevents timing-based username enumeration attacks
    _dummy = "$2b$12$KIXtT5P5vB5n5n5n5n5nAu"
    ok = verify_password(data.password, user.password if user else _dummy)

    if not user or not ok:
        logger.warning(f"Failed login: {username}")
        raise HTTPException(401, "Invalid username or password.")

    if getattr(user, "is_suspended", False):
        raise HTTPException(403, "Your account has been suspended. Please contact your manager.")

    if user.role == "admin":
        can_planner, can_quality = True, True
        can_confirmations = True
    else:
        can_planner = bool(user.can_planner)
        can_quality = bool(user.can_quality)
        can_confirmations = bool(getattr(user, "can_confirmations", False))

    # ── Password expiry check (6 months) ─────────────────────────────────────
    now_mt = business_now()
    pw_changed_at = getattr(user, "password_changed_at", None)
    password_expired = False
    password_expires_at = ""

    if pw_changed_at:
        try:
            changed_dt = datetime.strptime(pw_changed_at, "%Y-%m-%dT%H:%M:%S")
            expires_dt = changed_dt + timedelta(days=PASSWORD_EXPIRY_DAYS)
            password_expires_at = expires_dt.strftime("%Y-%m-%d")
            if now_mt.replace(tzinfo=None) >= expires_dt:
                password_expired = True
        except ValueError:
            pass
    else:
        # Account predates the expiry feature — treat as needing password set
        # so password_changed_at gets stamped on their next change.
        pass

    audit(db, user.id, "login", f"IP: {get_remote_address(request)}")
    logger.info(f"Login: {username} ({user.role})")

    return {
        "token":                create_token(
                                    user.id, user.role or "admin",
                                    user.token_version or 0,
                                    can_planner, can_quality,
                                    can_confirmations,
                                    password_expires_at
                                ),
        "role":                 user.role or "admin",
        "can_planner":          can_planner,
        "can_quality":          can_quality,
        "can_confirmations":    can_confirmations,
        "username":             user.username,
        # ← True only for accounts whose original password was under 8 chars.
        "needs_password_reset": bool(getattr(user, "needs_password_reset", False)),
        # ← True if the password hasn't been changed in 6+ months
        "password_expired":     password_expired,
        # ← ISO date string of when the password expires (YYYY-MM-DD)
        "password_expires_at":  password_expires_at,
    }

# ── Change password ────────────────────────────────────────────────────────────

class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password:     str

@app.post("/change-password")
def change_password(data: ChangePasswordPayload,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password):
        raise HTTPException(400, "Current password is incorrect.")

    new_pw = validate_new_password(data.new_password)

    if data.current_password == new_pw:
        raise HTTPException(400, "New password must be different from your current password.")

    # Prevent reuse of the immediately previous password
    prev_hash = getattr(user, "previous_password_hash", None)
    if prev_hash and verify_password(new_pw, prev_hash):
        raise HTTPException(400, "You cannot reuse your previous password. Please choose a different one.")

    # Save current hash as previous before overwriting
    user.previous_password_hash = user.password
    user.password                = hash_password(new_pw)
    user.token_version           = (user.token_version or 0) + 1
    user.needs_password_reset    = False   # clear short-password flag
    user.password_changed_at     = business_now().strftime("%Y-%m-%dT%H:%M:%S")
    db.commit()

    audit(db, user.id, "password_change", "Password updated")
    return {"status": "password updated"}

# ── Assistant management ───────────────────────────────────────────────────────

class AssistantPayload(BaseModel):
    username:    str
    password:    str
    can_planner: bool = True
    can_quality: bool = False
    can_confirmations: bool = False

class AssistantPermissionsPayload(BaseModel):
    can_planner: bool
    can_quality: bool
    can_confirmations: bool = False

@app.post("/create-assistant", status_code=201)
def create_assistant(data: AssistantPayload,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _require_admin(user)
    username = validate_username(data.username)
    password = validate_new_password(data.password)
    if not data.can_planner and not data.can_quality and not data.can_confirmations:
        raise HTTPException(400, "At least one permission must be selected.")
    if db.query(User).filter(User.username.ilike(username)).first():
        raise HTTPException(400, "Username already exists.")
    db.add(User(
        username=username,
        password=hash_password(password),
        role="assistant",
        owner_id=user.id,
        can_planner=data.can_planner,
        can_quality=data.can_quality,
        can_confirmations=data.can_confirmations,
        token_version=0,
        needs_password_reset=False,
    ))
    db.commit()
    audit(db, user.id, "create_assistant", f"Created: {username}")
    return {"status": "created"}

@app.put("/assistants/{assistant_id}/permissions")
def update_assistant_permissions(assistant_id: int,
                                  data: AssistantPermissionsPayload,
                                  user: User = Depends(get_current_user),
                                  db: Session = Depends(get_db)):
    _require_admin(user)
    assistant = db.query(User).filter(
        User.id == assistant_id,
        User.role == "assistant",
        User.owner_id == user.id
    ).first()
    if not assistant:
        raise HTTPException(404, "Assistant not found.")
    assistant.can_planner = data.can_planner
    assistant.can_quality = data.can_quality
    assistant.can_confirmations = data.can_confirmations
    db.commit()
    audit(db, user.id, "update_permissions",
          f"{assistant.username}: planner={data.can_planner}, quality={data.can_quality}, confirmations={data.can_confirmations}")
    return {"status": "updated",
            "can_planner": bool(assistant.can_planner),
            "can_quality": bool(assistant.can_quality),
            "can_confirmations": bool(assistant.can_confirmations)}

@app.get("/assistants")
def list_assistants(user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    _require_admin(user)
    assistants = db.query(User).filter(
        User.role == "assistant", User.owner_id == user.id
    ).all()
    return [{"id": a.id, "username": a.username, "role": a.role,
             "can_planner": bool(a.can_planner),
             "can_quality": bool(a.can_quality),
             "can_confirmations": bool(getattr(a, "can_confirmations", False)),
             "is_suspended": bool(getattr(a, "is_suspended", False))}
            for a in assistants]

@app.patch("/assistants/{assistant_id}/suspend")
def suspend_assistant(assistant_id: int,
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Toggle suspended state for an assistant. No permissions required."""
    _require_admin(user)
    assistant = db.query(User).filter(
        User.id == assistant_id,
        User.role == "assistant",
        User.owner_id == user.id
    ).first()
    if not assistant:
        raise HTTPException(404, "Assistant not found.")
    assistant.is_suspended = not bool(getattr(assistant, "is_suspended", False))
    # Bump token version so any active session is immediately invalidated
    assistant.token_version = (assistant.token_version or 0) + 1
    db.commit()
    action = "suspended" if assistant.is_suspended else "unsuspended"
    audit(db, user.id, f"assistant_{action}", assistant.username)
    return {"is_suspended": bool(assistant.is_suspended)}

@app.delete("/assistants/{assistant_id}")
def delete_assistant(assistant_id: int,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _require_admin(user)
    assistant = db.query(User).filter(
        User.id == assistant_id,
        User.role == "assistant",
        User.owner_id == user.id
    ).first()
    if not assistant:
        raise HTTPException(404, "Assistant not found.")
    name = assistant.username
    db.delete(assistant)
    db.commit()
    audit(db, user.id, "delete_assistant", f"Deleted: {name}")
    return {"status": "deleted"}

# ── Daily log ──────────────────────────────────────────────────────────────────

class LogPayload(BaseModel):
    date:                   str
    appointments_start:     int
    appointments_finish:    int
    total_presentations:    int
    total_sales:            int
    total_alp:              float
    total_ah:               float
    referrals_collected:    int
    referral_presentations: int
    referral_sales:         int
    assigned_leads:         int = 0
    bad_leads:              int = 0
    resolves_bad_number:    int = 0
    resolves_pres_refused:  int = 0
    resolves_duplicate:     int = 0

    @field_validator("date")
    @classmethod
    def check_date(cls, v):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Invalid date format.")
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @field_validator("appointments_start", "appointments_finish", "total_presentations",
                     "total_sales", "referrals_collected", "referral_presentations",
                     "referral_sales", "assigned_leads", "bad_leads",
                     "resolves_bad_number", "resolves_pres_refused",
                     "resolves_duplicate")
    @classmethod
    def non_negative_int(cls, v):
        if v < 0:    raise ValueError("Cannot be negative.")
        if v > 9999: raise ValueError("Exceeds maximum (9999).")
        return v

    @field_validator("total_alp", "total_ah")
    @classmethod
    def non_negative_float(cls, v):
        if v < 0:          raise ValueError("Cannot be negative.")
        if v > 9_999_999:  raise ValueError("Exceeds maximum.")
        return round(v, 2)

@app.post("/log-day")
def log_day(data: LogPayload,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _require_admin(user)
    existing = db.query(DailyLog).filter(
        DailyLog.user_id == user.id, DailyLog.date == data.date
    ).first()
    if existing:
        for k, v in data.dict().items():
            setattr(existing, k, v)
        db.commit()
        return {"status": "updated"}
    db.add(DailyLog(user_id=user.id, **data.dict()))
    db.commit()
    return {"status": "saved"}

@app.get("/history")
def history(user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _require_admin(user)
    logs = db.query(DailyLog).filter(
        DailyLog.user_id == user.id
    ).order_by(DailyLog.date.desc()).all()
    return [
        {"id": l.id, "date": l.date,
         "appointments_start": l.appointments_start,
         "appointments_finish": l.appointments_finish,
         "total_presentations": l.total_presentations,
         "total_sales": l.total_sales,
         "total_alp": l.total_alp, "total_ah": l.total_ah,
         "referrals_collected": l.referrals_collected,
         "referral_presentations": l.referral_presentations,
         "referral_sales": l.referral_sales,
         "assigned_leads": l.assigned_leads or 0,
         "bad_leads": l.bad_leads or 0,
         "resolves_bad_number": l.resolves_bad_number or 0,
         "resolves_pres_refused": l.resolves_pres_refused or 0,
         "resolves_duplicate": l.resolves_duplicate or 0}
        for l in logs
    ]

@app.delete("/delete-days")
def delete_days(ids: list[int],
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    _require_admin(user)
    if not ids:
        raise HTTPException(400, "No IDs provided.")
    if len(ids) > 500:
        raise HTTPException(400, "Too many IDs in one request.")
    deleted = db.query(DailyLog).filter(
        DailyLog.user_id == user.id, DailyLog.id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()
    audit(db, user.id, "delete_logs", f"Deleted {deleted} log entries")
    return {"status": "deleted", "count": deleted}

# ── Appointments ───────────────────────────────────────────────────────────────

class RecipientPayload(BaseModel):
    name:         Optional[str] = ""
    phone_number: Optional[str] = ""

class AppointmentPayload(BaseModel):
    lead_name:     str
    attendee_name: Optional[str] = ""
    phone_number:  Optional[str] = ""
    comments:      Optional[str] = ""
    scheduled_for: str
    appt_type:     Optional[str] = "appointment"
    booking_tz:    Optional[str] = BUSINESS_TZ_NAME
    recipients:    Optional[List[RecipientPayload]] = None  # extra SMS recipients
    # Admin-only escape hatch: book into an hour the admin has blocked.
    # Ignored for assistants and for the public booking page.
    override_block: Optional[bool] = False


def _sync_recipients(db: Session, appt: Appointment, recipients):
    """
    Replace an appointment's extra recipients with the provided list.
    Blank rows (no phone) are ignored. Phones are normalized like the primary.
    Passing None leaves existing recipients untouched (e.g. partial updates);
    passing [] clears them.
    """
    if recipients is None:
        return
    # Remove existing
    db.query(AppointmentRecipient).filter(
        AppointmentRecipient.appointment_id == appt.id
    ).delete(synchronize_session=False)
    # Add the new set (skip blanks)
    for r in recipients:
        phone = normalize_phone(r.phone_number)
        name  = title_case(sanitize_str(r.name or "", 200))
        if not phone:
            continue
        db.add(AppointmentRecipient(
            appointment_id=appt.id, name=name, phone_number=phone
        ))

@app.post("/appointments", status_code=201)
def create_appointment(data: AppointmentPayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _check_planner_access(user)
    lead_name = sanitize_str(data.lead_name, 200)
    if not lead_name:
        raise HTTPException(400, "Lead name is required.")
    # ── Availability enforcement ─────────────────────────────
    # Days off and blocked dates are absolute for everyone.
    owner = get_owner_id(user)
    sched = validate_datetime(data.scheduled_for)
    day_reason = blocked_day_reason(db, owner, sched)
    if day_reason:
        raise HTTPException(400, day_reason)
    # Blocked hours are absolute too, except an admin may knowingly override
    # their own block. 409 signals "blocked, but overridable" so the client can
    # offer a confirmation; assistants get a plain 400 with no way through.
    hour_reason = blocked_hour_reason(db, owner, sched)
    override_used = False
    if hour_reason:
        if user.role == "admin" and bool(getattr(data, "override_block", False)):
            override_used = True     # logged once the booking is actually saved
        elif user.role == "admin":
            raise HTTPException(409, hour_reason)
        else:
            raise HTTPException(400, hour_reason)
    # Same-day notice applies to assistants. Admins are exempt.
    if user.role != "admin":
        lead_reason = lead_time_reason(sched)
        if lead_reason:
            raise HTTPException(400, lead_reason)
    # Normalize to E.164 so RingCentral can actually dial it.
    raw_phone = normalize_phone(data.phone_number)
    now   = business_now().strftime("%Y-%m-%dT%H:%M")
    appt  = Appointment(
        created_by=user.id, owner_id=owner,
        lead_name=title_case(sanitize_str(data.lead_name, 200)),
        attendee_name=title_case(sanitize_str(data.attendee_name or "", 200)),
        phone_number=raw_phone[:20],
        comments=sanitize_str(data.comments or "", 2000),
        scheduled_for=validate_datetime(data.scheduled_for),
        booked_at=now,
        appt_type=data.appt_type if data.appt_type in ("appointment","callback") else "appointment",
        booking_tz=validate_tz(data.booking_tz),
    )
    # Calculate midpoint reminder date if appointment is 5+ days out
    try:
        mt          = BUSINESS_TZ
        now_date    = datetime.now(mt).date()
        sched_date  = datetime.strptime(validate_datetime(data.scheduled_for)[:10], "%Y-%m-%d").date()
        days_out    = (sched_date - now_date).days
        if days_out >= 5:
            midpoint_date = now_date + timedelta(days=days_out // 2)
            appt.midpoint_send_date = midpoint_date.strftime("%Y-%m-%d")
    except Exception:
        pass
    # One appointment per hour. Check and insert under the same lock the agent
    # link uses, so a planner save and an agent booking cannot both win.
    with _booking_lock:
        if appt.appt_type != "callback" and appointment_conflict(db, owner, appt.scheduled_for):
            raise HTTPException(400, conflict_message(appt.scheduled_for))
        db.add(appt); db.flush()
        # Extra SMS recipients go in the same transaction, so no job can ever
        # see the appointment without them.
        _sync_recipients(db, appt, data.recipients)
        db.commit(); db.refresh(appt)
    if override_used:
        audit(db, user.id, "override_blocked_hour", f"{sched} — {hour_reason}")
    return _appt_dict(appt, db)

def _json_with_etag(request: Request, payload) -> Response:
    """
    JSON response with an ETag. The planner re-polls every 30 seconds; when
    nothing changed the browser gets an empty 304 instead of the whole list.
    """
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    # Weak validator: the same data compressed or not is still "the same".
    etag = 'W/"' + hashlib.md5(body).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    sent = [t.strip() for t in request.headers.get("if-none-match", "").split(",")]
    if "*" in sent or etag in sent or etag[2:] in sent:
        headers["Vary"] = "Accept-Encoding"
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@app.get("/appointments")
def get_appointments(request: Request,
                     start: Optional[str] = None,
                     end: Optional[str] = None,
                     limit: Optional[int] = None,
                     active: bool = False,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """
    Appointments for the user's planner, oldest first.
    Optional filters, so a page that needs only part of the list doesn't
    download all of it: start / end (YYYY-MM-DD, inclusive) on the
    appointment date, and limit. With no filters it returns everything, as
    the planner and its search expect.
    """
    _check_planner_access(user)
    owner = get_owner_id(user)
    q = db.query(Appointment).filter(Appointment.owner_id == owner)
    if start:
        q = q.filter(Appointment.scheduled_for >= validate_date(start))
    if end:
        q = q.filter(Appointment.scheduled_for < validate_date(end) + "T99")
    if active:
        q = q.filter(
            Appointment.scheduled_for >= business_now_str(),
            or_(Appointment.appt_status.is_(None), Appointment.appt_status.notin_(RELEASED_STATUSES)),
            or_(Appointment.sms_status.is_(None), Appointment.sms_status.notin_(RELEASED_STATUSES)),
        )
    q = q.order_by(Appointment.scheduled_for, Appointment.id)
    if limit:
        q = q.limit(max(1, min(int(limit), 500)))
    return _json_with_etag(request, _appt_dicts(q.all(), db))


@app.get("/appointments/new-count")
def appointments_new_count(since_ms: int = 0,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """
    How many appointments were booked after `since_ms` (browser epoch ms of
    the user's last planner visit). Drives the red badge on the Planner link
    on every page, which used to download the whole appointment list just to
    count it.
    """
    if not _has_planner_access(user):
        return {"count": 0}
    owner = get_owner_id(user)
    upper = int((time.time() + 86400) * 1000)
    since = datetime.fromtimestamp(min(max(since_ms, 0), upper) / 1000, tz=UTC) \
        .astimezone(BUSINESS_TZ).strftime("%Y-%m-%dT%H:%M")
    count = db.query(Appointment).filter(
        Appointment.owner_id == owner,
        Appointment.booked_at > since,
    ).count()
    return {"count": count}

@app.put("/appointments/{appt_id}")
def update_appointment(appt_id: int, data: AppointmentPayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _check_planner_access(user)
    owner = get_owner_id(user)
    with _booking_lock:
        appt  = db.query(Appointment).filter(
            Appointment.id == appt_id, Appointment.owner_id == owner
        ).first()
        if not appt: raise HTTPException(404, "Appointment not found.")
        # ── Blocked-day enforcement ──────────────────────────────
        # Only when the DATE actually moves. Fixing a typo in the phone number of
        # an appointment on a day that was blocked afterwards must still work.
        sched = validate_datetime(data.scheduled_for)
        if sched[:10] != (appt.scheduled_for or "")[:10]:
            sched_date = datetime.strptime(sched[:10], "%Y-%m-%d")
            sched_dow  = (sched_date.weekday() + 1) % 7  # JS style: Sun=0 … Sat=6
            blocked = db.query(BlockedDay).filter(
                BlockedDay.owner_id == owner, BlockedDay.day_of_week == sched_dow
            ).first()
            if blocked:
                raise HTTPException(400, f"{DAY_NAMES[sched_dow]} is marked as unavailable. Appointments cannot be rescheduled to this day.")
            # ── One-time blocked date enforcement ─────────────────────
            blocked_date = db.query(BlockedDate).filter(
                BlockedDate.owner_id == owner, BlockedDate.date == sched[:10]
            ).first()
            if blocked_date:
                raise HTTPException(400, f"{sched[:10]} is marked as unavailable. Appointments cannot be rescheduled to this date.")
        # Captured before any field changes, for the one-per-hour check below.
        prev_sched = appt.scheduled_for or ""
        prev_type  = appt.appt_type or "appointment"
        prev_released = releases_slot(getattr(appt, "appt_status", ""), appt.sms_status)
        pending_audit = None
        # Normalised so legacy rows stored without +1 don't count as a change
        old_phone          = normalize_phone(appt.phone_number or "")
        appt.lead_name     = title_case(sanitize_str(data.lead_name, 200))
        appt.attendee_name = title_case(sanitize_str(data.attendee_name or "", 200))
        appt.phone_number  = normalize_phone(data.phone_number)
        appt.comments      = sanitize_str(data.comments or "", 2000)
        appt.appt_type     = data.appt_type if data.appt_type in ("appointment","callback") else "appointment"
        if data.booking_tz: appt.booking_tz = validate_tz(data.booking_tz)

        # ── Smart SMS reset on reschedule ───────────────────────────
        new_sched  = validate_datetime(data.scheduled_for)

        # Rescheduling into a blocked hour follows the same rules as booking one.
        # Only checked when the time actually moves, so editing a name or comment
        # on an appointment that already sits inside a block still works.
        if new_sched != (appt.scheduled_for or ""):
            hour_reason = blocked_hour_reason(db, owner, new_sched)
            if hour_reason:
                if user.role == "admin" and bool(getattr(data, "override_block", False)):
                    # Logged only after the edit is saved; audit() commits, which
                    # would otherwise save this half-applied edit early.
                    pending_audit = ("override_blocked_hour", f"{new_sched} — {hour_reason}")
                elif user.role == "admin":
                    raise HTTPException(409, hour_reason)
                else:
                    raise HTTPException(400, hour_reason)
            # Same-day notice, assistants only. Editing a name or phone on an
            # appointment that is already inside the window still works.
            if user.role != "admin":
                lead_reason = lead_time_reason(new_sched)
                if lead_reason:
                    raise HTTPException(400, lead_reason)

        old_date   = appt.scheduled_for[:10] if appt.scheduled_for else ""
        new_date   = new_sched[:10]
        old_time   = appt.scheduled_for[11:16] if appt.scheduled_for and len(appt.scheduled_for) > 10 else ""
        new_time   = new_sched[11:16] if len(new_sched) > 10 else ""

        if old_date != new_date:
            # Date changed — full reset so they get a fresh evening + morning text
            appt.sms_sent_evening  = False
            appt.sms_sent_morning  = False
            appt.sms_sent_reminder = False
            appt.sms_sent_booking  = False
            appt.sms_sent_midpoint = False
            appt.sms_sent_manual   = False
            appt.sms_status        = ""
            # A confirmation or outcome (rescheduled / no-show / cancelled)
            # belongs to the OLD date/time. Moving the appointment is the
            # reschedule, so it starts pending and must be re-confirmed. Leaving
            # "rescheduled" in place would block every text for the new time.
            appt.appt_status = ""
            appt.sms_sent_confirmed_notice = False
            # Recalculate midpoint for new date
            try:
                mt         = BUSINESS_TZ
                now_date   = datetime.now(mt).date()
                sched_date = datetime.strptime(new_sched[:10], "%Y-%m-%d").date()
                days_out   = (sched_date - now_date).days
                if days_out >= 5:
                    midpoint_date = now_date + timedelta(days=days_out // 2)
                    appt.midpoint_send_date = midpoint_date.strftime("%Y-%m-%d")
                else:
                    appt.midpoint_send_date = ""
            except Exception:
                pass
            # Update booked_at so booking job fires again for the rescheduled appt
            try:
                mt  = BUSINESS_TZ
                appt.booked_at = datetime.now(mt).strftime("%Y-%m-%dT%H:%M")
            except Exception:
                pass
        elif old_time != new_time:
            # Same date, time changed. Any text already sent quoted the OLD time,
            # so reset everything and re-send a booking confirmation with the new
            # time (~5 minutes from now via the booking job).
            appt.sms_sent_evening  = False
            appt.sms_sent_morning  = False
            appt.sms_sent_reminder = False
            appt.sms_sent_booking  = False
            appt.sms_sent_manual   = False
            appt.sms_status        = ""
            appt.appt_status       = ""
            appt.sms_sent_confirmed_notice = False
            try:
                appt.booked_at = business_now().strftime("%Y-%m-%dT%H:%M")
            except Exception:
                pass
        elif (appt.phone_number or "") != old_phone and (appt.phone_number or ""):
            # Phone number corrected on an unchanged time. Earlier texts went to
            # the old (possibly wrong) number, so the client may have received
            # nothing. Re-send the confirmation to the new number via the booking
            # job. Confirmation status is left as is.
            appt.sms_sent_evening  = False
            appt.sms_sent_morning  = False
            appt.sms_sent_booking  = False
            appt.sms_sent_manual   = False
            try:
                appt.booked_at = business_now().strftime("%Y-%m-%dT%H:%M")
            except Exception:
                pass
        # else: only non-time fields changed — leave SMS fields untouched

        appt.scheduled_for = new_sched
        # Update extra SMS recipients (None = leave as-is; [] = clear)
        _sync_recipients(db, appt, data.recipients)

        # One appointment per hour. Only checked when this edit could create a
        # clash (the hour moves, or a callback becomes an appointment), so fixing a
        # name on an older pair that already overlaps still saves.
        # Also checked when a cancelled or rescheduled appointment becomes active
        # again by being moved, even within the same hour (moving it clears the
        # old status), since it is taking an hour back.
        now_released = releases_slot(getattr(appt, "appt_status", ""), appt.sms_status)
        needs_check = (appt.appt_type != "callback"
                       and not now_released
                       and (new_sched[:13] != prev_sched[:13] or prev_type == "callback"
                            or prev_released))
        if needs_check and appointment_conflict(db, owner, new_sched, exclude_id=appt.id):
            db.rollback()
            raise HTTPException(400, conflict_message(new_sched))
        db.commit()
    if pending_audit:
        audit(db, user.id, *pending_audit)
    return _appt_dict(appt, db)

@app.delete("/appointments/{appt_id}")
def delete_appointment(appt_id: int,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _check_planner_access(user)
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt: raise HTTPException(404, "Appointment not found.")
    db.delete(appt); db.commit()
    return {"status": "deleted"}

def _appt_dicts(appts, db) -> list:
    """
    Serialize many appointments with two extra queries in total (creators and
    recipients), instead of two per appointment. The planner loads every
    appointment, so the per-row version got slower with each booking.
    """
    if not appts:
        return []
    creator_ids = {a.created_by for a in appts if a.created_by is not None}
    names = dict(db.query(User.id, User.username).filter(User.id.in_(creator_ids)).all()) \
        if creator_ids else {}
    recips_by_appt: dict = {}
    ids = [a.id for a in appts]
    # Chunked so a very large planner never exceeds SQLite's variable limit.
    for i in range(0, len(ids), 500):
        for r in db.query(AppointmentRecipient).filter(
                AppointmentRecipient.appointment_id.in_(ids[i:i + 500])
        ).order_by(AppointmentRecipient.id).all():
            recips_by_appt.setdefault(r.appointment_id, []).append(
                {"name": r.name or "", "phone_number": r.phone_number or ""})
    return [_appt_dict(a, db, names.get(a.created_by, "unknown"),
                       recips_by_appt.get(a.id, [])) for a in appts]


def _appt_dict(appt, db, creator_name: Optional[str] = None,
               recipients: Optional[list] = None):
    if creator_name is None:
        creator = db.query(User).filter(User.id == appt.created_by).first()
        creator_name = creator.username if creator else "unknown"
    if recipients is None:
        recipients = [{"name": r.name or "", "phone_number": r.phone_number or ""}
                      for r in db.query(AppointmentRecipient).filter(
                          AppointmentRecipient.appointment_id == appt.id
                      ).order_by(AppointmentRecipient.id).all()]
    return {"id": appt.id, "lead_name": appt.lead_name,
            "attendee_name": appt.attendee_name or "",
            "phone_number": appt.phone_number or "",
            "recipients": recipients,
            "comments": appt.comments, "scheduled_for": appt.scheduled_for,
            "booked_at": appt.booked_at,
            "created_by": creator_name,
            "appt_type": appt.appt_type or "appointment",
            "booking_tz": appt.booking_tz or BUSINESS_TZ_NAME,
            # The client's own local time, worked out here with the pinned
            # tzdata so the planner never depends on the browser's copy.
            "client_time": client_time_summary(appt.scheduled_for or "", appt.booking_tz),
            "sms_status": appt.sms_status or "",
            "appt_status": getattr(appt, "appt_status", "") or "",
            "sms_sent_evening": bool(appt.sms_sent_evening),
            "sms_sent_morning": bool(appt.sms_sent_morning),
            "sms_sent_reminder": bool(appt.sms_sent_reminder),
            "sms_sent_booking": bool(getattr(appt, "sms_sent_booking", False)),
            "sms_sent_midpoint": bool(getattr(appt, "sms_sent_midpoint", False)),
            "sms_sent_manual": bool(getattr(appt, "sms_sent_manual", False)),
            "booked_by_agent": bool(getattr(appt, "booked_by_agent", False)),
            "booked_by_name": getattr(appt, "booked_by_name", "") or "",
            "midpoint_send_date": getattr(appt, "midpoint_send_date", "") or ""}

@app.get("/scheduling-rules")
def get_scheduling_rules(user: User = Depends(get_current_user)):
    """Booking rules the planner mirrors client-side. The server stays the
    authority: every rule here is re-checked on create and update."""
    _check_planner_access(user)
    return {
        "timezone":            BUSINESS_TZ_NAME,
        "timezone_abbrev":     tz_abbrev(BUSINESS_TZ_NAME),
        # The planner works out "now" from this offset rather than from the
        # browser's own time zone data, which may be older than the server's.
        "utc_offset_minutes":  utc_offset_minutes(BUSINESS_TZ_NAME),
        "timezones":           timezone_options(),
        "same_day_lead_hours": SAME_DAY_LEAD_HOURS,
        "lead_applies":        user.role != "admin",
    }


@app.get("/time/convert")
def convert_client_time(stamp: str, from_tz: str,
                        user: User = Depends(get_current_user)):
    """
    A client's local time → the business time the planner stores.
    Done here, with the pinned tzdata, so the planner gives the same answer
    on every computer no matter how old its browser's time zone data is.
    """
    _check_planner_access(user)
    stamp = validate_datetime(stamp)
    if from_tz not in ALLOWED_TIMEZONES:
        raise HTTPException(400, "Unknown time zone.")
    business = to_business(stamp, from_tz)
    return {
        "business":        business,
        "business_display": f"{fmt_hhmm(business)} {tz_abbrev(BUSINESS_TZ_NAME)}",
        "business_tz":     BUSINESS_TZ_NAME,
    }


# ── Blocked Days (Unavailable Days) ────────────────────────────────────────────

class BlockedDayPayload(BaseModel):
    day_of_week: int  # 0=Sun … 6=Sat

@app.get("/blocked-days")
def get_blocked_days(user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Return the list of blocked day-of-week numbers for this admin/owner."""
    _check_planner_access(user)
    owner = get_owner_id(user)
    rows = db.query(BlockedDay).filter(BlockedDay.owner_id == owner).all()
    return [r.day_of_week for r in rows]

@app.post("/blocked-days", status_code=201)
def add_blocked_day(data: BlockedDayPayload,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Admin-only: mark a day-of-week as unavailable."""
    _require_admin(user)
    dow = data.day_of_week
    if dow < 0 or dow > 6:
        raise HTTPException(400, "day_of_week must be 0–6 (Sun–Sat).")
    owner = user.id
    existing = db.query(BlockedDay).filter(
        BlockedDay.owner_id == owner, BlockedDay.day_of_week == dow
    ).first()
    if existing:
        return {"status": "already blocked"}
    db.add(BlockedDay(owner_id=owner, day_of_week=dow))
    db.commit()
    audit(db, user.id, "block_day", f"Blocked {DAY_NAMES[dow]}")
    return {"status": "blocked"}

@app.delete("/blocked-days/{dow}")
def remove_blocked_day(dow: int,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Admin-only: unblock a day-of-week."""
    _require_admin(user)
    if dow < 0 or dow > 6:
        raise HTTPException(400, "day_of_week must be 0–6 (Sun–Sat).")
    owner = user.id
    row = db.query(BlockedDay).filter(
        BlockedDay.owner_id == owner, BlockedDay.day_of_week == dow
    ).first()
    if row:
        db.delete(row)
        db.commit()
        audit(db, user.id, "unblock_day", f"Unblocked {DAY_NAMES[dow]}")
    return {"status": "unblocked"}

# ── Blocked Dates (One-Time) ──────────────────────────────────────────────────

class BlockedDatePayload(BaseModel):
    date: str  # YYYY-MM-DD

@app.get("/blocked-dates")
def get_blocked_dates(user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Return list of one-time blocked dates for this admin/owner."""
    _check_planner_access(user)
    owner = get_owner_id(user)
    rows = db.query(BlockedDate).filter(BlockedDate.owner_id == owner).all()
    return [r.date for r in rows]

@app.post("/blocked-dates", status_code=201)
def add_blocked_date(data: BlockedDatePayload,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Admin-only: block a specific date (one-time)."""
    _require_admin(user)
    date_str = validate_date(data.date)
    owner = user.id
    existing = db.query(BlockedDate).filter(
        BlockedDate.owner_id == owner, BlockedDate.date == date_str
    ).first()
    if existing:
        return {"status": "already blocked"}
    db.add(BlockedDate(owner_id=owner, date=date_str))
    db.commit()
    audit(db, user.id, "block_date", f"Blocked {date_str}")
    return {"status": "blocked"}

@app.delete("/blocked-dates/{date_str}")
def remove_blocked_date(date_str: str,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Admin-only: unblock a specific date."""
    _require_admin(user)
    owner = user.id
    row = db.query(BlockedDate).filter(
        BlockedDate.owner_id == owner, BlockedDate.date == date_str
    ).first()
    if row:
        db.delete(row)
        db.commit()
        audit(db, user.id, "unblock_date", f"Unblocked {date_str}")
    return {"status": "unblocked"}


# ── Blocked Hours (one-time hour-range blocks) ────────────────────────────────

class BlockedHourPayload(BaseModel):
    date:       str        # YYYY-MM-DD
    start_hour: int        # 7–21
    end_hour:   int        # 7–21, must be > start_hour
    label:      Optional[str] = ""

@app.get("/blocked-hours")
def get_blocked_hours(user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Return all blocked hour ranges for this admin's owner."""
    owner = get_owner_id(user)
    rows = db.query(BlockedHour).filter(BlockedHour.owner_id == owner).all()
    return [{"id": r.id, "date": r.date, "start_hour": r.start_hour,
             "end_hour": r.end_hour, "label": r.label or ""} for r in rows]

@app.post("/blocked-hours", status_code=201)
def add_blocked_hour(data: BlockedHourPayload,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Admin-only: block a range of hours on a specific date."""
    _require_admin(user)
    if data.start_hour < 7 or data.end_hour > 22 or data.start_hour >= data.end_hour:
        raise HTTPException(400, "Invalid hour range. Start must be 7–21, end must be 8–22, and start < end.")
    date_str = validate_date(data.date)
    row = BlockedHour(
        owner_id   = user.id,
        date       = date_str,
        start_hour = data.start_hour,
        end_hour   = data.end_hour,
        label      = sanitize_str(data.label or "", 100)
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user.id, "block_hours", f"Blocked {date_str} {data.start_hour}:00–{data.end_hour}:00")
    return {"id": row.id, "date": row.date, "start_hour": row.start_hour,
            "end_hour": row.end_hour, "label": row.label or ""}

@app.delete("/blocked-hours/{block_id}")
def remove_blocked_hour(block_id: int,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Admin-only: remove a blocked hour range."""
    _require_admin(user)
    row = db.query(BlockedHour).filter(
        BlockedHour.id == block_id, BlockedHour.owner_id == user.id
    ).first()
    if not row:
        raise HTTPException(404, "Blocked hour not found.")
    db.delete(row)
    db.commit()
    audit(db, user.id, "unblock_hours", f"Removed hour block {block_id}")
    return {"status": "removed"}


# ── Blocked Hours Recurring (every day, specific hour range) ──────────────────

class BlockedHourRecurringPayload(BaseModel):
    start_hour:  int        # 7–21
    end_hour:    int        # 7–21, must be > start_hour
    label:       Optional[str] = ""
    day_of_week: Optional[int] = None   # None = every day; 0=Sun … 6=Sat

@app.get("/blocked-hours-recurring")
def get_blocked_hours_recurring(user: User = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
    """Return all recurring daily hour blocks for this admin's owner."""
    owner = get_owner_id(user)
    rows = db.query(BlockedHourRecurring).filter(BlockedHourRecurring.owner_id == owner).all()
    return [{"id": r.id, "start_hour": r.start_hour, "end_hour": r.end_hour,
             "label": r.label or "",
             "day_of_week": getattr(r, "day_of_week", None)} for r in rows]

@app.post("/blocked-hours-recurring", status_code=201)
def add_blocked_hour_recurring(data: BlockedHourRecurringPayload,
                                user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    """Admin-only: block a range of hours every single day (recurring)."""
    _require_admin(user)
    owner = get_owner_id(user)
    if data.start_hour < 7 or data.end_hour > 22 or data.start_hour >= data.end_hour:
        raise HTTPException(400, "Invalid hour range. Start must be 7–21, end must be 8–22, and start < end.")
    dow = data.day_of_week
    if dow is not None and dow not in range(7):
        raise HTTPException(400, "day_of_week must be 0–6 (0=Sunday) or omitted for every day.")
    # Prevent exact duplicates — same range on the same repeat pattern
    existing = db.query(BlockedHourRecurring).filter(
        BlockedHourRecurring.owner_id    == owner,
        BlockedHourRecurring.start_hour  == data.start_hour,
        BlockedHourRecurring.end_hour    == data.end_hour,
        BlockedHourRecurring.day_of_week.is_(None) if dow is None
            else BlockedHourRecurring.day_of_week == dow,
    ).first()
    if existing:
        return {"id": existing.id, "start_hour": existing.start_hour,
                "end_hour": existing.end_hour, "label": existing.label or "",
                "day_of_week": getattr(existing, "day_of_week", None)}
    row = BlockedHourRecurring(
        owner_id    = owner,
        start_hour  = data.start_hour,
        end_hour    = data.end_hour,
        label       = sanitize_str(data.label or "", 100),
        day_of_week = dow,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    when = "every day" if dow is None else f"every {DAY_NAMES[dow]}"
    audit(db, user.id, "block_hours_recurring",
          f"Recurring block {data.start_hour}:00–{data.end_hour}:00 {when}")
    return {"id": row.id, "start_hour": row.start_hour, "end_hour": row.end_hour,
            "label": row.label or "", "day_of_week": row.day_of_week}

@app.delete("/blocked-hours-recurring/{block_id}")
def remove_blocked_hour_recurring(block_id: int,
                                   user: User = Depends(get_current_user),
                                   db: Session = Depends(get_db)):
    """Admin-only: remove a recurring daily hour block."""
    _require_admin(user)
    row = db.query(BlockedHourRecurring).filter(
        BlockedHourRecurring.id == block_id,
        BlockedHourRecurring.owner_id == get_owner_id(user)
    ).first()
    if not row:
        raise HTTPException(404, "Recurring block not found.")
    db.delete(row)
    db.commit()
    audit(db, user.id, "unblock_hours_recurring", f"Removed recurring block {block_id}")
    return {"status": "removed"}

# ── Quality ────────────────────────────────────────────────────────────────────

class QualityPayload(BaseModel):
    insured_name:  str
    policy_number: Optional[str] = ""
    remarks:       Optional[str] = ""
    date:          Optional[str] = ""
    phone_number:  Optional[str] = ""
    follow_up:     Optional[str] = ""
    action:        Optional[str] = ""
    alp:           Optional[str] = ""
    due_date:      Optional[str] = ""   # YYYY-MM-DD

def _sanitize_quality(data: QualityPayload) -> dict:
    return {
        "insured_name":  sanitize_str(data.insured_name, 200),
        "policy_number": sanitize_str(data.policy_number or "", 100),
        "remarks":       sanitize_str(data.remarks or "", 1000),
        "date":          sanitize_str(data.date or "", 20),
        "phone_number":  re.sub(r"[^\d\s\+\-\(\)ext\.]", "", data.phone_number or "")[:30],
        "follow_up":     sanitize_str(data.follow_up or "", 100),
        "action":        sanitize_str(data.action or "", 5000),
        "alp":           sanitize_str(data.alp or "", 50),
        "due_date":      sanitize_str(data.due_date or "", 10),
    }

def _quality_dict(e):
    return {"id": e.id, "insured_name": e.insured_name,
            "policy_number": e.policy_number or "", "remarks": e.remarks or "",
            "date": e.date or "", "phone_number": e.phone_number or "",
            "follow_up": e.follow_up or "", "action": e.action or "",
            "alp": e.alp or "", "due_date": getattr(e, "due_date", "") or "",
            "created_at": e.created_at or ""}

@app.post("/quality", status_code=201)
def create_quality(data: QualityPayload,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _check_quality_access(user)
    fields = _sanitize_quality(data)
    if not fields["insured_name"]:
        raise HTTPException(400, "Insured name is required.")
    owner = get_owner_id(user)
    now     = business_now().strftime("%Y-%m-%dT%H:%M")
    now_date = now[:10]  # YYYY-MM-DD
    # If user left date blank, auto-fill with the actual insertion date
    if not fields.get("date"):
        fields["date"] = now_date
    due_date = fields.pop("due_date", "")
    entry = QualityEntry(owner_id=owner, created_by=user.id, created_at=now, **fields)
    entry.due_date = due_date
    db.add(entry); db.commit(); db.refresh(entry)
    return _quality_dict(entry)

@app.get("/quality")
def get_quality(user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    _check_quality_access(user)
    owner = get_owner_id(user)
    return [_quality_dict(e) for e in
            db.query(QualityEntry).filter(QualityEntry.owner_id == owner)
              .order_by(QualityEntry.id.desc()).all()]

@app.put("/quality/{entry_id}")
def update_quality(entry_id: int, data: QualityPayload,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _check_quality_access(user)
    owner = get_owner_id(user)
    entry = db.query(QualityEntry).filter(
        QualityEntry.id == entry_id, QualityEntry.owner_id == owner
    ).first()
    if not entry: raise HTTPException(404, "Entry not found.")
    fields = _sanitize_quality(data)
    due_date = fields.pop("due_date", "")
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.due_date = due_date
    db.commit()
    return _quality_dict(entry)

@app.delete("/quality/{entry_id}")
def delete_quality(entry_id: int,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _check_quality_access(user)
    owner = get_owner_id(user)
    entry = db.query(QualityEntry).filter(
        QualityEntry.id == entry_id, QualityEntry.owner_id == owner
    ).first()
    if not entry: raise HTTPException(404, "Entry not found.")
    db.delete(entry); db.commit()
    return {"status": "deleted"}

# ── Database backup ───────────────────────────────────────────────────────────

@app.post("/backup")
def backup_database(user: User = Depends(get_current_user)):
    """
    Creates a timestamped copy of the SQLite database file.
    Stored in /data/backups/ on Render's persistent disk.
    Admins can also trigger this manually from Settings.
    """
    _require_admin(user)

    db_path = os.environ.get("DATABASE_URL", "sqlite:////data/kpi.db")

    # Only works for SQLite
    if not db_path.startswith("sqlite:///"):
        raise HTTPException(400, "Backup is only supported for SQLite databases.")

    # Strip sqlite:/// prefix to get the actual file path
    src = db_path.replace("sqlite:///", "")

    if not os.path.exists(src):
        raise HTTPException(404, "Database file not found.")

    # Create backups directory next to the database
    backup_dir = os.path.join(os.path.dirname(src), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # Timestamped filename
    ts       = business_now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"kpi_backup_{ts}.db"
    dest     = os.path.join(backup_dir, filename)

    # SQLite's own backup API takes a consistent snapshot even if a booking or
    # an SMS job writes mid-copy. A plain file copy at that moment can produce
    # a backup that won't open.
    import sqlite3
    fd, temporary = tempfile.mkstemp(dir=backup_dir, prefix=".backup-", suffix=".tmp")
    os.close(fd)
    try:
        src_conn = sqlite3.connect(src)
        try:
            dest_conn = sqlite3.connect(temporary)
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()
        os.replace(temporary, dest)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logger.info(f"Backup created: {dest} by user {user.username}")

    # Keep only the 10 most recent backups to save disk space
    try:
        existing = sorted([
            f for f in os.listdir(backup_dir) if f.startswith("kpi_backup_") and f.endswith(".db")
        ])
        while len(existing) > 10:
            os.remove(os.path.join(backup_dir, existing.pop(0)))
    except Exception as e:
        logger.warning(f"Backup cleanup failed: {e}")

    return {"status": "ok", "filename": filename, "path": dest}


@app.get("/backups")
def list_backups(user: User = Depends(get_current_user)):
    """Lists available backup files with their sizes and timestamps."""
    _require_admin(user)

    db_path   = os.environ.get("DATABASE_URL", "sqlite:////data/kpi.db")
    if not db_path.startswith("sqlite:///"):
        return []

    src        = db_path.replace("sqlite:///", "")
    backup_dir = os.path.join(os.path.dirname(src), "backups")

    if not os.path.exists(backup_dir):
        return []

    files = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.startswith("kpi_backup_") and f.endswith(".db"):
            fp   = os.path.join(backup_dir, f)
            size = os.path.getsize(fp)
            files.append({
                "filename": f,
                "size_kb":  round(size / 1024, 1),
                "created":  f.replace("kpi_backup_", "").replace(".db", "").replace("_", " ")
            })
    return files


# ── Audit log ──────────────────────────────────────────────────────────────────

@app.get("/audit-log")
def get_audit_log(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _require_admin(user)
    entries = db.query(AuditLog).filter(
        AuditLog.user_id == user.id
    ).order_by(AuditLog.id.desc()).limit(200).all()
    return [{"id": e.id, "action": e.action,
             "detail": e.detail, "timestamp": e.timestamp}
            for e in entries]

# ── Referral Programs ─────────────────────────────────────────────────────────

class ReferralEntryPayload(BaseModel):
    ref_type:       Optional[str] = ""
    benefit:        Optional[str] = ""
    notes:          Optional[str] = ""
    first_name:     Optional[str] = ""
    last_name:      Optional[str] = ""
    city:           Optional[str] = ""
    province:       Optional[str] = ""
    phone:          Optional[str] = ""
    rel_to_sponsor: Optional[str] = ""
    occupation:     Optional[str] = ""
    sig_other:      Optional[str] = ""
    spouse_name:    Optional[str] = ""
    num_children:   Optional[int] = 0
    status:         Optional[str] = ""  # "met" | "pending" | "skip" | ""

class ReferralProgramPayload(BaseModel):
    sponsor_first:      Optional[str]   = ""
    sponsor_last:       Optional[str]   = ""
    sponsor_org:        Optional[str]   = ""
    sponsor_phone:      Optional[str]   = ""
    sponsor_email:      Optional[str]   = ""
    sponsor_city:       Optional[str]   = ""
    sponsor_province:   Optional[str]   = ""
    sponsor_occupation: Optional[str]   = ""
    sponsor_notes:      Optional[str]   = ""
    program_date:       Optional[str]   = ""
    total_gifted:       Optional[float] = 0.0
    referrals:      list[ReferralEntryPayload] = []

def _sanitize_referral_entry(d: ReferralEntryPayload) -> dict:
    return {
        "ref_type":      sanitize_str(d.ref_type or "", 50),
        "benefit":       sanitize_str(d.benefit or "", 200),
        "notes":         sanitize_str(d.notes or "", 1000),
        "first_name":    sanitize_str(d.first_name or "", 100),
        "last_name":     sanitize_str(d.last_name or "", 100),
        "city":          sanitize_str(d.city or "", 100),
        "province":      sanitize_str(d.province or "", 50),
        "phone":         re.sub(r"[^\d\s\+\-\(\)ext\.]", "", d.phone or "")[:30],
        "rel_to_sponsor":sanitize_str(d.rel_to_sponsor or "", 100),
        "occupation":    sanitize_str(d.occupation or "", 200),
        "status":        d.status if d.status in ("met", "pending", "skip") else "",
        "sig_other":     sanitize_str(d.sig_other or "", 200),
        "spouse_name":   sanitize_str(d.spouse_name or "", 200),
        "num_children":  max(0, int(d.num_children or 0)),
    }

def _program_dict(p: ReferralProgram) -> dict:
    return {
        "id":            p.id,
        "sponsor_first":      p.sponsor_first or "",
        "sponsor_last":       p.sponsor_last or "",
        "sponsor_org":        p.sponsor_org or "",
        "sponsor_phone":      p.sponsor_phone or "",
        "sponsor_email":      p.sponsor_email or "",
        "sponsor_city":       getattr(p, "sponsor_city", "") or "",
        "sponsor_province":   getattr(p, "sponsor_province", "") or "",
        "sponsor_occupation": getattr(p, "sponsor_occupation", "") or "",
        "sponsor_notes":      getattr(p, "sponsor_notes", "") or "",
        "program_date":       p.program_date or "",
        "total_gifted":       p.total_gifted or 0.0,
        "created_at":    p.created_at or "",
        "referrals": [
            {
                "id":            r.id,
                "ref_type":      r.ref_type or "",
                "benefit":       r.benefit or "",
                "notes":         r.notes or "",
                "first_name":    r.first_name or "",
                "last_name":     r.last_name or "",
                "city":          r.city or "",
                "province":      r.province or "",
                "phone":         r.phone or "",
                "rel_to_sponsor":r.rel_to_sponsor or "",
                "occupation":    r.occupation or "",
                "status":        getattr(r, "status", "") or "",
                "sig_other":     r.sig_other or "",
                "spouse_name":   getattr(r, "spouse_name", "") or "",
                "num_children":  getattr(r, "num_children", 0) or 0,
            }
            for r in p.referrals
        ]
    }

@app.post("/referral-programs", status_code=201)
def create_referral_program(data: ReferralProgramPayload,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    _require_admin(user)
    now = business_now().strftime("%Y-%m-%dT%H:%M")
    prog = ReferralProgram(
        owner_id=user.id,
        created_by=user.id,
        sponsor_first=sanitize_str(data.sponsor_first or "", 100),
        sponsor_last=sanitize_str(data.sponsor_last or "", 100),
        sponsor_org=sanitize_str(data.sponsor_org or "", 200),
        sponsor_phone=re.sub(r"[^\d\s\+\-\(\)ext\.]", "", data.sponsor_phone or "")[:30],
        sponsor_email=sanitize_str(data.sponsor_email or "", 200),
        sponsor_city=sanitize_str(data.sponsor_city or "", 100),
        sponsor_province=sanitize_str(data.sponsor_province or "", 100),
        sponsor_occupation=sanitize_str(data.sponsor_occupation or "", 200),
        sponsor_notes=sanitize_str(data.sponsor_notes or "", 1000),
        program_date=sanitize_str(data.program_date or "", 10),
        total_gifted=max(0.0, min(data.total_gifted or 0.0, 9_999_999)),
        created_at=now,
    )
    db.add(prog)
    db.flush()
    for ref in data.referrals:
        db.add(ReferralEntry(program_id=prog.id, **_sanitize_referral_entry(ref)))
    db.commit()
    db.refresh(prog)
    return _program_dict(prog)

@app.get("/referral-programs")
def get_referral_programs(user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    _require_admin(user)
    progs = db.query(ReferralProgram).filter(
        ReferralProgram.owner_id == user.id
    ).order_by(ReferralProgram.id.desc()).all()
    return [_program_dict(p) for p in progs]

@app.get("/referral-programs/{prog_id}")
def get_referral_program(prog_id: int,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    _require_admin(user)
    prog = db.query(ReferralProgram).filter(
        ReferralProgram.id == prog_id,
        ReferralProgram.owner_id == user.id
    ).first()
    if not prog:
        raise HTTPException(404, "Referral program not found.")
    return _program_dict(prog)

@app.put("/referral-programs/{prog_id}")
def update_referral_program(prog_id: int, data: ReferralProgramPayload,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    _require_admin(user)
    prog = db.query(ReferralProgram).filter(
        ReferralProgram.id == prog_id,
        ReferralProgram.owner_id == user.id
    ).first()
    if not prog:
        raise HTTPException(404, "Referral program not found.")

    prog.sponsor_first      = sanitize_str(data.sponsor_first or "", 100)
    prog.sponsor_last       = sanitize_str(data.sponsor_last or "", 100)
    prog.sponsor_org        = sanitize_str(data.sponsor_org or "", 200)
    prog.sponsor_phone      = re.sub(r"[^\d\s\+\-\(\)ext\.]", "", data.sponsor_phone or "")[:30]
    prog.sponsor_email      = sanitize_str(data.sponsor_email or "", 200)
    prog.sponsor_city       = sanitize_str(data.sponsor_city or "", 100)
    prog.sponsor_province   = sanitize_str(data.sponsor_province or "", 100)
    prog.sponsor_occupation = sanitize_str(data.sponsor_occupation or "", 200)
    prog.sponsor_notes      = sanitize_str(data.sponsor_notes or "", 1000)
    prog.program_date       = sanitize_str(data.program_date or "", 10)
    prog.total_gifted       = max(0.0, min(data.total_gifted or 0.0, 9_999_999))

    # Replace all referral entries
    db.query(ReferralEntry).filter(ReferralEntry.program_id == prog.id).delete()
    for ref in data.referrals:
        db.add(ReferralEntry(program_id=prog.id, **_sanitize_referral_entry(ref)))
    db.commit()
    db.refresh(prog)
    return _program_dict(prog)

@app.delete("/referral-programs/{prog_id}")
def delete_referral_program(prog_id: int,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    _require_admin(user)
    prog = db.query(ReferralProgram).filter(
        ReferralProgram.id == prog_id,
        ReferralProgram.owner_id == user.id
    ).first()
    if not prog:
        raise HTTPException(404, "Referral program not found.")
    db.delete(prog)
    db.commit()
    audit(db, user.id, "delete_referral_program", f"Deleted program ID {prog_id}")
    return {"status": "deleted"}


class ReferralEntryStatusPayload(BaseModel):
    status: str = ""  # "met" | "pending" | "skip" | ""

@app.patch("/referral-entries/{entry_id}/status")
def update_referral_entry_status(entry_id: int,
                                  data: ReferralEntryStatusPayload,
                                  user: User = Depends(get_current_user),
                                  db: Session = Depends(get_db)):
    """Update only the status of a single referral entry."""
    _require_admin(user)
    entry = db.query(ReferralEntry).join(
        ReferralProgram, ReferralEntry.program_id == ReferralProgram.id
    ).filter(
        ReferralEntry.id == entry_id,
        ReferralProgram.owner_id == user.id
    ).first()
    if not entry:
        raise HTTPException(404, "Referral entry not found.")
    if data.status not in ("met", "pending", "skip", ""):
        raise HTTPException(422, "Invalid status value.")
    entry.status = data.status
    db.commit()
    return {"id": entry_id, "status": entry.status}

# ── Timesheet ──────────────────────────────────────────────────────────────────

class TimesheetPayload(BaseModel):
    date:           str
    hours_worked:   float
    appts_booked:   int
    appts_resolved: int
    callbacks:      int
    notes:          str = ""

class TimesheetUpdatePayload(BaseModel):
    hours_worked:   float
    appts_booked:   int
    appts_resolved: int
    callbacks:      int
    notes:          str = ""

def _ts_row(entry: TimesheetEntry, username: str) -> dict:
    punches = []
    for p in (entry.punches or []):
        punches.append({
            "id":          p.id,
            "clock_in":    p.clock_in,
            "clock_out":   p.clock_out or "",
            "hours_delta": round(p.hours_delta or 0, 2),
        })
    return {
        "id":             entry.id,
        "username":       username,
        "date":           entry.date,
        "hours_worked":   entry.hours_worked,
        "appts_booked":   entry.appts_booked,
        "appts_resolved": entry.appts_resolved,
        "callbacks":      entry.callbacks,
        "notes":          entry.notes,
        "submitted_at":   entry.submitted_at,
        "punches":        punches,
    }

def _recalc_hours(entry: TimesheetEntry, db):
    """Recalculate total hours_worked from all punches on this entry."""
    total = 0.0
    for p in entry.punches:
        if p.clock_in and p.clock_out:
            try:
                h_in,  m_in  = map(int, p.clock_in.split(":"))
                h_out, m_out = map(int, p.clock_out.split(":"))
                mins = (h_out * 60 + m_out) - (h_in * 60 + m_in)
                delta = max(0.0, mins / 60.0)
                p.hours_delta = round(delta, 2)
                total += delta
            except Exception:
                pass
    entry.hours_worked = round(total, 2)
    db.commit()

class PunchPayload(BaseModel):
    clock_in:  str   # HH:MM
    clock_out: Optional[str] = ""

@app.post("/timesheet", status_code=201)
def create_timesheet_entry(data: TimesheetPayload,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Assistant or admin submits a daily timesheet entry. One per date per user."""
    date_str = validate_date(data.date)
    existing = db.query(TimesheetEntry).filter(
        TimesheetEntry.user_id == user.id,
        TimesheetEntry.date    == date_str
    ).first()
    if existing:
        raise HTTPException(409, "An entry for this date already exists. Edit the existing one.")
    owner = get_owner_id(user)
    now   = business_now().strftime("%Y-%m-%dT%H:%M")
    entry = TimesheetEntry(
        user_id        = user.id,
        owner_id       = owner,
        date           = date_str,
        hours_worked   = max(0.0, round(float(data.hours_worked), 2)),
        appts_booked   = max(0, int(data.appts_booked)),
        appts_resolved = max(0, int(data.appts_resolved)),
        callbacks      = max(0, int(data.callbacks)),
        notes          = sanitize_str(data.notes, 500),
        submitted_at   = now,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    audit(db, user.id, "timesheet_submit", f"Date {date_str}")
    return _ts_row(entry, user.username)

@app.get("/timesheet")
def get_timesheet(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """
    Assistant: returns only their own entries.
    Admin: returns all entries for all of their assistants.
    """
    if user.role == "admin":
        assistants = db.query(User).filter(
            User.owner_id == user.id,
            User.role     == "assistant"
        ).all()
        assistant_ids = [a.id for a in assistants]
        if not assistant_ids:
            return []
        rows = db.query(TimesheetEntry).filter(
            TimesheetEntry.user_id.in_(assistant_ids)
        ).order_by(TimesheetEntry.date.desc()).all()
        uid_to_name = {a.id: a.username for a in assistants}
        return [_ts_row(r, uid_to_name.get(r.user_id, "unknown")) for r in rows]
    else:
        rows = db.query(TimesheetEntry).filter(
            TimesheetEntry.user_id == user.id
        ).order_by(TimesheetEntry.date.desc()).all()
        return [_ts_row(r, user.username) for r in rows]

# ── Punch routes MUST come before /{entry_id} routes to avoid conflicts ────────

@app.put("/timesheet/punches/{punch_id}")
def update_punch(punch_id: int,
                 data: PunchPayload,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Edit a punch's clock_in / clock_out times."""
    punch = db.query(TimesheetPunch).filter(TimesheetPunch.id == punch_id).first()
    if not punch:
        raise HTTPException(404, "Punch not found.")
    entry = punch.entry
    if user.role == "assistant" and entry.user_id != user.id:
        raise HTTPException(403, "Not your entry.")
    if user.role == "admin" and entry.owner_id != user.id:
        raise HTTPException(403, "Entry not in your team.")
    if not re.match(r"^\d{2}:\d{2}$", data.clock_in):
        raise HTTPException(422, "clock_in must be HH:MM format.")
    clock_out = data.clock_out or ""
    if clock_out and not re.match(r"^\d{2}:\d{2}$", clock_out):
        raise HTTPException(422, "clock_out must be HH:MM format.")
    punch.clock_in  = data.clock_in
    punch.clock_out = clock_out or None
    db.commit()
    db.refresh(entry)
    _recalc_hours(entry, db)
    submitter = db.query(User).filter(User.id == entry.user_id).first()
    return _ts_row(entry, submitter.username if submitter else "unknown")

@app.delete("/timesheet/punches/{punch_id}")
def delete_punch(punch_id: int,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Delete a punch row."""
    punch = db.query(TimesheetPunch).filter(TimesheetPunch.id == punch_id).first()
    if not punch:
        raise HTTPException(404, "Punch not found.")
    entry = punch.entry
    if user.role == "assistant" and entry.user_id != user.id:
        raise HTTPException(403, "Not your entry.")
    if user.role == "admin" and entry.owner_id != user.id:
        raise HTTPException(403, "Entry not in your team.")
    db.delete(punch)
    db.commit()
    db.refresh(entry)
    _recalc_hours(entry, db)
    submitter = db.query(User).filter(User.id == entry.user_id).first()
    return _ts_row(entry, submitter.username if submitter else "unknown")

@app.post("/timesheet/{entry_id}/punches", status_code=201)
def add_punch(entry_id: int,
              data: PunchPayload,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Add a clock-in/out punch to an existing timesheet entry."""
    entry = db.query(TimesheetEntry).filter(TimesheetEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Entry not found.")
    if user.role == "assistant" and entry.user_id != user.id:
        raise HTTPException(403, "Not your entry.")
    if user.role == "admin" and entry.owner_id != user.id:
        raise HTTPException(403, "Entry not in your team.")
    if not re.match(r"^\d{2}:\d{2}$", data.clock_in):
        raise HTTPException(422, "clock_in must be HH:MM format.")
    clock_out = data.clock_out or ""
    if clock_out and not re.match(r"^\d{2}:\d{2}$", clock_out):
        raise HTTPException(422, "clock_out must be HH:MM format.")
    punch = TimesheetPunch(
        entry_id    = entry_id,
        clock_in    = data.clock_in,
        clock_out   = clock_out or None,
        hours_delta = 0.0,
    )
    db.add(punch)
    db.commit()
    db.refresh(entry)
    _recalc_hours(entry, db)
    submitter = db.query(User).filter(User.id == entry.user_id).first()
    return _ts_row(entry, submitter.username if submitter else "unknown")

@app.put("/timesheet/{entry_id}")
def update_timesheet_entry(entry_id: int,
                            data: TimesheetUpdatePayload,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Owner (assistant) or admin can edit an entry."""
    entry = db.query(TimesheetEntry).filter(TimesheetEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Entry not found.")
    if user.role == "assistant" and entry.user_id != user.id:
        raise HTTPException(403, "Cannot edit another assistant's entry.")
    if user.role == "admin" and entry.owner_id != user.id:
        raise HTTPException(403, "Entry does not belong to your team.")
    entry.hours_worked   = max(0.0, round(float(data.hours_worked), 2))
    entry.appts_booked   = max(0, int(data.appts_booked))
    entry.appts_resolved = max(0, int(data.appts_resolved))
    entry.callbacks      = max(0, int(data.callbacks))
    entry.notes          = sanitize_str(data.notes, 500)
    db.commit()
    db.refresh(entry)
    submitter = db.query(User).filter(User.id == entry.user_id).first()
    uname = submitter.username if submitter else "unknown"
    audit(db, user.id, "timesheet_edit", f"Entry {entry_id}")
    return _ts_row(entry, uname)

@app.delete("/timesheet/{entry_id}")
def delete_timesheet_entry(entry_id: int,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Admin only can delete timesheet entries."""
    _require_admin(user)
    entry = db.query(TimesheetEntry).filter(
        TimesheetEntry.id       == entry_id,
        TimesheetEntry.owner_id == user.id
    ).first()
    if not entry:
        raise HTTPException(404, "Entry not found.")
    db.delete(entry)
    db.commit()
    audit(db, user.id, "timesheet_delete", f"Entry {entry_id}")
    return {"status": "deleted"}
# ── RingCentral OAuth + SMS Automation ────────────────────────────────────────
# Environment variables required on Render:
#   RC_CLIENT_ID      — from developers.ringcentral.com
#   RC_CLIENT_SECRET  — from developers.ringcentral.com
#   RC_REDIRECT_URI   — https://data-log.onrender.com/rc/callback

RC_CLIENT_ID     = os.environ.get("RC_CLIENT_ID", "")
RC_CLIENT_SECRET = os.environ.get("RC_CLIENT_SECRET", "")
RC_REDIRECT_URI  = os.environ.get("RC_REDIRECT_URI", "https://data-log.onrender.com/rc/callback")
RC_AUTH_BASE = "https://platform.ringcentral.com"  # production

# Placeholder SMS scripts — replace with real scripts when ready
SMS_BASE_DETAILS = (
    "Here are the details:\n\n"
    "Date: {date}\n"
    "Time: {time}\n"
    "Manager: Hazem\n"
    "Number: 403-305-2652\n\n"
    "Go to www.zoom.com\n"
    "Click Meet then Join a meeting\n"
    "Meeting ID: 403-305-2652"
)

SMS_YES_SUFFIX   = "\n\nKindly confirm your attendance by replying YES.\n\nSee you soon!"
SMS_CONF_SUFFIX  = "\n\nSee you soon!"

def _build_sms(name: str, time_str: str, date_str: str, confirmed: bool) -> str:
    """Build the standard appointment SMS. Omits 'reply YES' if already confirmed."""
    suffix = SMS_CONF_SUFFIX if confirmed else SMS_YES_SUFFIX
    return (
        f"Hi {name}!\n\n"
        "This is a confirmation for your zoom call meeting with American Income Life.\n\n"
        + SMS_BASE_DETAILS.format(date=date_str, time=time_str)
        + suffix
    )

SMS_EVENING_TEMPLATE = (
    "Hi {name}!\n\n"
    "This is a confirmation for your zoom call meeting with American Income Life.\n\n"
    "Here are the details:\n\n"
    "Date: {date}\n"
    "Time: {time}\n"
    "Manager: Hazem\n"
    "Number: 403-305-2652\n\n"
    "Go to www.zoom.com\n"
    "Click Meet then Join a meeting\n"
    "Meeting ID: 403-305-2652\n\n"
    "Kindly confirm your attendance by replying YES.\n\n"
    "See you soon!"
)
SMS_MORNING_TEMPLATE = SMS_EVENING_TEMPLATE
SMS_REMINDER_TEMPLATE = "Hi {name}! Just a quick reminder about your appointment today at {time}."

def _build_confirmed_notice_sms(name: str, time_str: str = "", date_str: str = "") -> str:
    """The one-off 'your appointment is confirmed' notice.
    Sent once when an appointment transitions into confirmed status. It names
    the date and time, so a family with several bookings can tell which one."""
    display = name.strip() if name and name.strip() else "there"
    if date_str and time_str:
        return f"Hi {display}. Your appointment on {date_str} at {time_str} is confirmed."
    return f"Hi {display}. Your appointment is confirmed."

def _fmt_appt_time_for_tz(scheduled_for_mt: str, booking_tz: str) -> tuple[str, str]:
    """
    Stored business time → (time_display, date_display) in the client's zone,
    for SMS. e.g. ("12:00 PM PT", "May 22, 2026"). The conversion and labels
    live in backend/timezones.py so every caller agrees.
    """
    time_display, date_display = fmt_for_tz(scheduled_for_mt, booking_tz)
    if not date_display:
        logger.warning(f"Could not format {scheduled_for_mt!r} for {booking_tz!r}")
        return "your scheduled time", ""
    return time_display, date_display

# ── RC token helpers ──────────────────────────────────────────────────────────

def _get_rc_token(db: Session, owner_id: int) -> RcToken | None:
    return db.query(RcToken).filter(RcToken.owner_user_id == owner_id).first()

async def _refresh_rc_token_if_needed(db: Session, token_row: RcToken) -> bool:
    """Refresh the access token if it expires within 5 minutes. Returns True if OK."""
    try:
        expiry = datetime.fromisoformat(token_row.token_expiry)
        if datetime.utcnow() < expiry - timedelta(minutes=5):
            return True  # still valid
        # Refresh it
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{RC_AUTH_BASE}/restapi/oauth/token",
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": token_row.refresh_token,
                },
                auth=(RC_CLIENT_ID, RC_CLIENT_SECRET),
            )
        if resp.status_code != 200:
            logger.error(f"RC token refresh failed: {resp.text}")
            return False
        data = resp.json()
        token_row.access_token  = data["access_token"]
        token_row.refresh_token = data.get("refresh_token", token_row.refresh_token)
        token_row.token_expiry  = (
            datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat()
        db.commit()
        return True
    except Exception as e:
        logger.error(f"RC token refresh error: {e}")
        return False

# ── OAuth: start flow ─────────────────────────────────────────────────────────

# One-time OAuth "state" values. The state used to be the admin's user ID,
# which anyone could guess, so a crafted callback link could attach someone
# else's RingCentral account to this app. Now each connect attempt gets a
# random state that is tied to the admin who started it and expires.
_RC_OAUTH_STATES: dict = {}
_rc_oauth_lock = threading.Lock()
RC_OAUTH_STATE_SECONDS = 15 * 60


@app.post("/rc/connect-start")
def rc_connect_start(user: User = Depends(get_current_user)):
    """Settings calls this (signed in), then sends the browser to the URL.
    The admin's login token never appears in a URL or a server log."""
    _require_admin(user)
    now = time.monotonic()
    state = secrets.token_urlsafe(24)
    with _rc_oauth_lock:
        for key, (_, _, deadline) in list(_RC_OAUTH_STATES.items()):
            if deadline < now:
                del _RC_OAUTH_STATES[key]
        _RC_OAUTH_STATES[state] = (user.id, user.token_version or 0, now + RC_OAUTH_STATE_SECONDS)
    url = (f"{RC_AUTH_BASE}/restapi/oauth/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": RC_CLIENT_ID,
        "redirect_uri": RC_REDIRECT_URI, "state": state}))
    return {"url": url}

# ── OAuth: callback ───────────────────────────────────────────────────────────

@app.get("/rc/callback")
async def rc_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    RingCentral redirects here after the user logs in and approves.
    Exchanges the code for tokens and stores them in rc_tokens table.
    Then redirects back to settings page.
    """
    with _rc_oauth_lock:
        entry = _RC_OAUTH_STATES.pop(state, None)
    if not entry or entry[2] < time.monotonic():
        logger.warning("RC OAuth callback with an unknown or expired state; ignored")
        return RedirectResponse("/settings.html?rc=error")
    user_id, token_version, _ = entry
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin" or (user.token_version or 0) != token_version:
        return RedirectResponse("/settings.html?rc=error")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{RC_AUTH_BASE}/restapi/oauth/token",
            data={
                "grant_type":   "authorization_code",
                "code":         code,
                "redirect_uri": RC_REDIRECT_URI,
            },
            auth=(RC_CLIENT_ID, RC_CLIENT_SECRET),
        )

    if resp.status_code != 200:
        logger.error(f"RC OAuth token exchange failed: {resp.text}")
        return RedirectResponse("/settings.html?rc=error")

    data    = resp.json()
    expiry  = (datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))).isoformat()
    now_str = business_now().strftime("%Y-%m-%dT%H:%M:%S")

    # Fetch the account's phone number from RC
    rc_phone = ""
    try:
        async with httpx.AsyncClient() as client:
            ph_resp = await client.get(
                f"{RC_AUTH_BASE}/restapi/v1.0/account/~/extension/~/phone-number",
                headers={"Authorization": f"Bearer {data['access_token']}"},
            )
        if ph_resp.status_code == 200:
            numbers = ph_resp.json().get("records", [])
            for n in numbers:
                features = n.get("features", [])
                if "SmsSender" in features:
                    rc_phone = n.get("phoneNumber", "")
                    break
    except Exception as e:
        logger.warning(f"Could not fetch RC phone number: {e}")

    # Upsert token row
    token_row = db.query(RcToken).filter(RcToken.owner_user_id == user_id).first()
    if token_row:
        token_row.access_token  = data["access_token"]
        token_row.refresh_token = data.get("refresh_token", "")
        token_row.token_expiry  = expiry
        token_row.rc_phone_number = rc_phone
        token_row.connected_at  = now_str
    else:
        token_row = RcToken(
            owner_user_id   = user_id,
            access_token    = data["access_token"],
            refresh_token   = data.get("refresh_token", ""),
            token_expiry    = expiry,
            rc_phone_number = rc_phone,
            dry_run         = True,   # always start in dry-run/sandbox mode
            connected_at    = now_str,
        )
        db.add(token_row)
    db.commit()
    audit(db, user_id, "rc_connect", f"RingCentral connected, number: {rc_phone}")
    return RedirectResponse("/settings.html?rc=connected")

# ── RC: disconnect ────────────────────────────────────────────────────────────

@app.delete("/rc/disconnect")
def rc_disconnect(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _require_admin(user)
    token_row = _get_rc_token(db, user.id)
    if token_row:
        db.delete(token_row)
        db.commit()
        audit(db, user.id, "rc_disconnect", "RingCentral disconnected")
    return {"status": "disconnected"}

# ── RC: status ────────────────────────────────────────────────────────────────

@app.get("/rc/status")
def rc_status(user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Returns whether this admin has RC connected, and key info."""
    _require_admin(user)
    token_row = _get_rc_token(db, user.id)
    if not token_row:
        return {"connected": False}
    return {
        "connected":      True,
        "rc_phone_number": token_row.rc_phone_number or "Unknown",
        "dry_run":        bool(token_row.dry_run),
        "connected_at":   token_row.connected_at or "",
    }

# ── RC: toggle dry run ────────────────────────────────────────────────────────

class DryRunPayload(BaseModel):
    dry_run: bool

@app.patch("/rc/dry-run")
def rc_set_dry_run(data: DryRunPayload,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _require_admin(user)
    token_row = _get_rc_token(db, user.id)
    if not token_row:
        raise HTTPException(404, "RingCentral not connected.")
    token_row.dry_run = data.dry_run
    db.commit()
    mode = "dry run (sandbox)" if data.dry_run else "LIVE"
    audit(db, user.id, "rc_dry_run_toggle", f"SMS mode set to {mode}")
    return {"dry_run": token_row.dry_run}

# ── SMS sender ────────────────────────────────────────────────────────────────

# Last-resort guard against texting the same person the same words twice.
# Whatever path a duplicate comes from (a repeated webhook, a double click, two
# jobs overlapping), an identical text to the same number inside this window
# is skipped. Different wording (another appointment time, a new summary)
# always goes through. Kept in memory: the app runs as a single process.
SMS_DUPLICATE_WINDOW_SECONDS = 10 * 60
_recent_sms: dict = {}
_sms_in_flight: set = set()


async def send_sms(db: Session, owner_id: int, to_number: str, message: str) -> dict:
    """
    Send an SMS via RingCentral API.
    If dry_run is True, logs the message instead of sending.
    Returns {"sent": bool, "dry_run": bool, "detail": str}, plus
    "skipped": True when the duplicate guard held back a repeat text.
    """
    token_row = _get_rc_token(db, owner_id)
    if not token_row:
        return {"sent": False, "dry_run": False, "detail": "RC not connected"}

    if token_row.dry_run:
        logger.info(f"[DRY RUN] SMS to {to_number}: {message}")
        return {"sent": False, "dry_run": True, "detail": f"[DRY RUN] Would send to {to_number}: {message}"}

    key = (owner_id, _phone_key(to_number), message)
    now = time.monotonic()
    for old, at in list(_recent_sms.items()):
        if now - at >= SMS_DUPLICATE_WINDOW_SECONDS:
            del _recent_sms[old]
    if key in _recent_sms:
        return {"sent": False, "skipped": True, "detail": "Recently accepted by RingCentral"}
    if key in _sms_in_flight:
        return {"sent": False, "detail": "Matching send still in progress"}

    _sms_in_flight.add(key)
    try:
        result = await _post_sms(db, token_row, to_number, message)
        if result["sent"]:
            _recent_sms[key] = time.monotonic()
        return result
    finally:
        _sms_in_flight.discard(key)


async def _post_sms(db: Session, token_row, to_number: str, message: str) -> dict:
    """The RingCentral call itself. Use send_sms, which adds the guards."""
    ok = await _refresh_rc_token_if_needed(db, token_row)
    if not ok:
        return {"sent": False, "dry_run": False, "detail": "Token refresh failed"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{RC_AUTH_BASE}/restapi/v1.0/account/~/extension/~/sms",
                headers={
                    "Authorization": f"Bearer {token_row.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": {"phoneNumber": token_row.rc_phone_number},
                    "to":   [{"phoneNumber": to_number}],
                    "text": message,
                },
            )
        if resp.status_code in (200, 201):
            return {"sent": True, "dry_run": False, "detail": "Sent"}
        logger.error(f"RC SMS error {resp.status_code}: {resp.text}")
        return {"sent": False, "dry_run": False, "detail": resp.text}
    except Exception as e:
        logger.error("RC SMS transport error: %s", type(e).__name__)
        return {"sent": False, "uncertain": True, "detail": type(e).__name__}

# ── Inbound webhook — RingCentral posts here when a client replies ────────────

# ── Webhook verification ─────────────────────────────────────────────────────
# RingCentral puts the subscription's verification token in a
# "Verification-Token" header on every event. Set RC_WEBHOOK_TOKEN in Render,
# then press Register Webhook once: that recreates the subscription with the
# token and switches checking on. From then on a POST without the token (anyone
# who found the URL faking a client's "YES") is refused.

def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _rc_webhook_token() -> str:
    return os.environ.get("RC_WEBHOOK_TOKEN", "").strip()


def _webhook_request_trusted(db: Session, request: Request) -> bool:
    token = _get_setting(db, "rc_webhook_verified")
    if not token:
        return True
    got = request.headers.get("verification-token", "")
    return secrets.compare_digest(got.encode(), token.encode())


# ── Matching a "YES" to the right appointment ────────────────────────────────
# Kinds of outbound text that ask the client to reply YES.
_YES_PROMPT_KINDS = ("booking", "midpoint", "evening", "morning", "manual_confirm")


def _yes_candidates(db: Session, sender: str, destinations: list[str]) -> list:
    """
    Upcoming, unconfirmed, still-active appointments that this phone number
    was actually asked to confirm, for the appointment's CURRENT time.
    Uses the per-recipient send record; appointments texted before that
    record existed fall back to the appointment's sent flags.
    """
    sender_phone = _phone_key(sender)
    if not sender_phone:
        return []
    q = db.query(Appointment).filter(Appointment.scheduled_for > business_now_str())
    if destinations:
        owners = [t.owner_user_id for t in db.query(RcToken).all()
                  if _phone_key(t.rc_phone_number) in destinations]
        q = q.filter(Appointment.owner_id.in_(owners))
    appts = q.order_by(Appointment.scheduled_for).all()
    eligible = [a for a in appts if not a.booked_by_agent and not _is_confirmed(a)
                and _sms_status_allows_texting(a)]
    if not eligible:
        return []
    extra_ids = {
        r.appointment_id for r in db.query(AppointmentRecipient).join(Appointment)
        .filter(Appointment.scheduled_for > business_now_str()).all()
        if _phone_key(r.phone_number) == sender_phone
    }
    matches = [a for a in eligible if _phone_key(a.phone_number) == sender_phone or a.id in extra_ids]
    out = []
    for a in matches:
        logged = db.query(SmsLog).filter(SmsLog.direction == "out",
                                         SmsLog.appointment_id == a.id).all()
        if logged:
            prompted = any(r.status == "sent" and r.kind in _YES_PROMPT_KINDS
                           and _phone_key(r.phone) == sender_phone
                           and f":{a.scheduled_for}:" in r.dedupe_key
                           for r in logged)
        else:
            prompted = any(getattr(a, f, False) for f in (
                "sms_sent_morning", "sms_sent_evening", "sms_sent_booking",
                "sms_sent_manual", "sms_sent_midpoint"))
        if prompted:
            out.append(a)
    return out


async def _after_inbound_confirm(appt_id: int, appt_day: str) -> None:
    """Follow-up texts after a YES, run after RingCentral has its answer."""
    db = SessionLocal()
    try:
        appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
        if appt:
            await _maybe_send_confirmed_notice(db, appt)
        today = business_now().strftime("%Y-%m-%d")
        tomorrow = (business_now() + timedelta(days=1)).strftime("%Y-%m-%d")
        if appt_day in (today, tomorrow):
            await _send_daily_summary(appt_day)
    except Exception as e:
        logger.error(f"RC webhook follow-up failed for appt {appt_id}: {e}")
    finally:
        db.close()


async def _alert_ambiguous_yes(sender: str, appts: list) -> None:
    """Several bookings share this number: ask staff to confirm the right one."""
    if not TAMEEMA_PHONE:
        return
    db = SessionLocal()
    try:
        token_row = db.query(RcToken).first()
        if not token_row:
            return
        lines = [f"YES from {sender} matches {len(appts)} bookings. Please confirm the right one:"]
        for name, scheduled_for in appts[:5]:
            t, d = _fmt_appt_time_for_tz(scheduled_for, BUSINESS_TZ_NAME)
            lines.append(f"- {name}, {d} {t}")
        await send_sms(db, token_row.owner_user_id, TAMEEMA_PHONE, "\n".join(lines))
    except Exception as e:
        logger.error(f"RC webhook: ambiguous-YES alert failed: {e}")
    finally:
        db.close()


_background_tasks: set = set()

def _spawn(coro) -> None:
    """Run follow-up work after the response, keeping a reference so it
    isn't garbage-collected mid-flight."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.post("/rc/webhook")
async def rc_webhook(request: Request, db: Session = Depends(get_db)):
    """
    RingCentral sends inbound SMS events here. A reply containing YES (and no
    "no / can't / cancel / reschedule") confirms the appointment this number
    was asked about, but ONLY when exactly one appointment fits. If several
    bookings share the number, nothing is auto-confirmed and staff get a text
    listing them. Also answers RingCentral's validation challenge.
    """
    # RC sends a validation challenge header on first registration
    # Must echo it back in both the response header AND body
    challenge = request.headers.get("Validation-Token")
    if challenge:
        return Response(
            content=challenge,
            media_type="text/plain",
            headers={"Validation-Token": challenge}
        )

    if not _webhook_request_trusted(db, request):
        logger.warning("RC webhook: rejected an event without the verification token")
        return Response(status_code=403)

    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    # Navigate RC's event payload structure (body nested under "body" key)
    if not isinstance(body, dict):
        return {"status": "ignored"}
    body_data = body.get("body", {})
    if not isinstance(body_data, dict):
        return {"status": "ignored"}
    msg_type  = body_data.get("type", "")
    direction = body_data.get("direction", "")

    if msg_type != "SMS" or direction != "Inbound":
        # Fallback: try top-level structure
        msg_type  = body.get("type", "")
        direction = body.get("direction", "")
        if msg_type != "SMS" or direction != "Inbound":
            return {"status": "ignored"}
        body_data = body

    raw_text = body_data.get("subject") or body_data.get("text") or ""
    sender_info = body_data.get("from")
    sender = sender_info.get("phoneNumber") if isinstance(sender_info, dict) else None
    if not isinstance(raw_text, str) or not isinstance(sender, str) or not _phone_key(sender):
        return {"status": "ignored"}
    text = raw_text.strip().upper()
    recipients = body_data.get("to") or []
    if not isinstance(recipients, list):
        return {"status": "ignored"}
    destinations = [_phone_key(item["phoneNumber"]) for item in recipients
                    if isinstance(item, dict) and isinstance(item.get("phoneNumber"), str)]
    message_key = body_data.get("id") or f"{sender}|{text}|{body_data.get('creationTime', '')}"
    # RingCentral message IDs are scoped to the receiving line. Hash the full key.
    inbound_key = f"{','.join(sorted(destinations))}|{message_key}"
    key = "in:" + hashlib.sha256(inbound_key.encode()).hexdigest()

    # "Yes", "YES!", "yes thank you", "yes see you soon" all match. YES must be
    # a whole word, so "yesterday" or "eyes" never confirm anyone.
    if not re.search(r"\bYES\b", text):
        return {"status": "ignored"}
    # A reply that says yes but also no/can't/cancel/reschedule ("yes but I
    # can't make it", "no, not yes") is not a confirmation. Leave it for
    # staff to read instead of auto-confirming the wrong thing.
    if re.search(r"\b(NO|NOT|CAN'?T|CAN’T|CANNOT|UNABLE|CANCEL\w*|RESCHEDUL\w*)\b", text):
        logger.info(f"RC webhook: YES reply from {sender} also contains a negative; not auto-confirming: {text!r}")
        return {"status": "ignored"}

    with _booking_lock:
        db.add(SmsLog(dedupe_key=key, direction="in", kind="reply", phone=sender,
                      status="received", created_at=_mt_now_str_seconds()))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"status": "duplicate"}
        candidates = _yes_candidates(db, sender, destinations)
        matched = candidates[0] if len(candidates) == 1 else None
        if matched:
            matched.sms_status = "confirmed"
            matched.appt_status = "confirmed"
        db.commit()

    if matched:
        logger.info(f"Appointment {matched.id} ({matched.lead_name}) confirmed via YES from {sender}")
        # Texts go out after RingCentral gets its quick 200, so a slow send can
        # never make RingCentral think the event failed and deliver it again.
        _spawn(_after_inbound_confirm(matched.id, (matched.scheduled_for or "")[:10]))
        return {"status": "ok"}

    if candidates:
        logger.info(f"RC webhook: YES from {sender} matches {len(candidates)} bookings "
                    f"({', '.join(str(a.id) for a in candidates)}); left for staff")
        _spawn(_alert_ambiguous_yes(sender, [(a.lead_name, a.scheduled_for) for a in candidates]))
        return {"status": "needs_review"}

    logger.warning(f"RC webhook: no appointment matched sender {sender}")
    return {"status": "ok"}

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC AGENT BOOKING LINK
#
# A single unguessable URL that outside marketing agents open to see when Hazem
# is free and drop an appointment into the planner. Deliberately add-only:
# there is no public route that edits or deletes anything, so the capability
# does not exist rather than merely being switched off.
#
# Availability is never described by this module. It asks the same
# slot_unavailable_reason() helper the planner uses, so the agent view and the
# planner can never disagree about when Hazem is free, and changing his hours
# or days off is a data change with no code change anywhere.
# ══════════════════════════════════════════════════════════════════════════════

# The planner grid spans these hours. Anything permanently blocked inside the
# range simply never appears as bookable, so a client working 10-9 needs no
# code change — their 7/8/9am blocks do the work.
PLANNER_FIRST_HOUR = 7
PLANNER_LAST_HOUR  = 21          # last bookable start hour, inclusive

# horizon_days == 0 means the calendar runs forward indefinitely, which is the
# default. A non-zero value caps how far ahead agents may book. The sanity bound
# below is not a product limit: it exists so a malformed or hostile request
# cannot create an appointment centuries from now.
BOOKING_MAX_HORIZON_DAYS  = 3650
BOOKING_SANITY_LIMIT_DAYS = 3650

BOOKING_WINDOW_MIN_DAYS = 1
BOOKING_WINDOW_MAX_DAYS = 31

# WEB_CONCURRENCY is 1 on this service, so a process-level lock genuinely
# serialises the read-then-insert in the booking endpoint and two agents
# cannot claim the same slot. If the service is ever scaled to multiple
# workers this must become a database-level guard.
_booking_lock = threading.Lock()


def _mt_now() -> datetime:
    return business_now()


def _get_booking_config(db: Session, owner: int,
                        create: bool = False) -> Optional[BookingConfig]:
    cfg = db.query(BookingConfig).filter(BookingConfig.owner_id == owner).first()
    if cfg or not create:
        return cfg
    cfg = BookingConfig(
        owner_id     = owner,
        slug         = secrets.token_urlsafe(12),
        enabled      = False,
        horizon_days = 0,          # unlimited

        created_at   = _mt_now().strftime("%Y-%m-%dT%H:%M:%S"),
    )
    db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg


def _occupied_slots(db: Session, owner: int, start: str, end: str) -> set:
    """
    Set of "YYYY-MM-DDTHH" strings already taken by an appointment.
    Cancelled and rescheduled appointments release their slot and callbacks
    never hold one, the same rule appointment_conflict() applies.
    """
    rows = db.query(Appointment.scheduled_for, Appointment.appt_status,
                    Appointment.appt_type, Appointment.sms_status).filter(
        Appointment.owner_id == owner,
        Appointment.scheduled_for >= start,
        Appointment.scheduled_for <= end,
    ).all()
    return {r[0][:13] for r in rows
            if not releases_slot(r[1], r[3]) and (r[2] or "appointment") != "callback"}


def _client_slot_labels(date_str: str, hours: list, client_tz: str) -> list:
    """
    Each business hour on date_str as the client sees it, e.g.
    {"time": "12:00 PM", "shift": 0}. shift is -1 / +1 when the client's date
    differs from the business date. Looked up per date, so a week that spans
    a clock change in either zone is labelled correctly day by day.
    """
    out = []
    for hour in hours:
        local = from_business(f"{date_str}T{hour:02d}:00", client_tz)
        shift = (datetime.strptime(local[:10], "%Y-%m-%d").date()
                 - datetime.strptime(date_str, "%Y-%m-%d").date()).days
        out.append({"time": fmt_hhmm(local), "shift": shift})
    return out


def _availability(db: Session, owner: int, start_date, days: int,
                  last_bookable_date=None, client_tz: Optional[str] = None) -> dict:
    """
    Build the agent-facing grid for one window of days beginning at start_date.

    Windowed rather than precomputed so the calendar can run forward
    indefinitely: the page asks for the week it is showing and nothing more.

    Every blocked rule is loaded once and evaluated in memory. The previous
    version asked the database per day per hour, which cost roughly 1,800
    queries for a 60 day span and would not survive an unbounded range.
    Five queries here, regardless of window size.

    Returns only what an outsider may know: which hours exist and whether each
    is open. No names, no numbers, no distinction between booked and blocked.
    """
    last_date  = start_date + timedelta(days=days - 1)
    start_iso  = start_date.isoformat()
    last_iso   = last_date.isoformat()

    blocked_dows = {
        r.day_of_week for r in
        db.query(BlockedDay).filter(BlockedDay.owner_id == owner).all()
    }
    blocked_dates = {
        r.date for r in db.query(BlockedDate).filter(
            BlockedDate.owner_id == owner,
            BlockedDate.date >= start_iso,
            BlockedDate.date <= last_iso,
        ).all()
    }
    one_off_hours = {}
    for r in db.query(BlockedHour).filter(
        BlockedHour.owner_id == owner,
        BlockedHour.date >= start_iso,
        BlockedHour.date <= last_iso,
    ).all():
        one_off_hours.setdefault(r.date, []).append((r.start_hour, r.end_hour))

    recurring = [
        (getattr(r, "day_of_week", None), r.start_hour, r.end_hour)
        for r in db.query(BlockedHourRecurring).filter(
            BlockedHourRecurring.owner_id == owner
        ).all()
    ]
    occupied = _occupied_slots(db, owner, f"{start_iso}T00:00", f"{last_iso}T23:59")

    # Hours hidden from the grid are those blocked every single day, which is
    # how a client's working hours are expressed. Deriving the row set from the
    # daily rules alone keeps it identical from one week to the next, instead
    # of shifting as individual days fill up.
    hidden = set()
    for dow, s_h, e_h in recurring:
        if dow is None:
            hidden.update(range(s_h, e_h))
    visible_hours = [h for h in range(PLANNER_FIRST_HOUR, PLANNER_LAST_HOUR + 1)
                     if h not in hidden]

    # A slot is open only if it starts at or after the same-day notice cutoff.
    # This also hides every slot that has already passed.
    now_mt    = _mt_now()
    cutoff    = earliest_bookable(now_mt)
    out_days  = []
    client_tz = validate_tz(client_tz)
    convert   = client_tz != BUSINESS_TZ_NAME

    for offset in range(days):
        d        = start_date + timedelta(days=offset)
        date_str = d.isoformat()
        dow      = (d.weekday() + 1) % 7

        # Past the booking horizon the POST would refuse, so never offer it.
        beyond_horizon = last_bookable_date is not None and d > last_bookable_date
        if dow in blocked_dows or date_str in blocked_dates or beyond_horizon:
            out_days.append({"date": date_str, "closed": True,
                             "slots": [False] * len(visible_hours),
                             "local": None})
            continue

        # Copy, so the per-date list in one_off_hours is never mutated.
        day_ranges = list(one_off_hours.get(date_str, []))
        day_ranges += [(s_h, e_h) for wd, s_h, e_h in recurring if wd == dow]

        slots = []
        for hour in visible_hours:
            stamp = f"{date_str}T{hour:02d}"
            slots.append(
                f"{stamp}:00" >= cutoff
                and stamp not in occupied
                and not any(s_h <= hour < e_h for s_h, e_h in day_ranges)
            )
        out_days.append({
            "date":   date_str,
            "closed": False,
            "slots":  slots,
            # The client's local time for each hour, when they are elsewhere.
            "local":  _client_slot_labels(date_str, visible_hours, client_tz) if convert else None,
        })

    return {
        "timezone":   BUSINESS_TZ_NAME,
        "tz_abbrev":  tz_abbrev(BUSINESS_TZ_NAME),
        "client_tz":  {"id": client_tz, "label": tz_label(client_tz),
                       "abbrev": tz_abbrev(client_tz)},
        "timezones":  timezone_options(),
        "today":      now_mt.date().isoformat(),
        "start":      start_iso,
        "last_bookable_date": last_bookable_date.isoformat() if last_bookable_date else None,
        "hours":      visible_hours,
        "days":       out_days,
        "lead_hours": SAME_DAY_LEAD_HOURS,
    }


def _require_booking(db: Session, slug: str) -> BookingConfig:
    """Resolve a slug to an enabled config, or 404. Never reveals which of the
    two failed — an attacker probing slugs learns nothing either way."""
    cfg = db.query(BookingConfig).filter(BookingConfig.slug == slug).first()
    if not cfg or not cfg.enabled:
        raise HTTPException(404, "This booking link is not available.")
    return cfg


# ── Admin: manage the link ────────────────────────────────────────────────────

class BookingConfigPayload(BaseModel):
    enabled:      Optional[bool] = None
    horizon_days: Optional[int]  = None   # 0 = unlimited


def _booking_cfg_dict(cfg: BookingConfig) -> dict:
    return {
        "enabled":      bool(cfg.enabled),
        "slug":         cfg.slug,
        "path":         f"/book/{cfg.slug}",
        "horizon_days": cfg.horizon_days,
        "rotated_at":   cfg.rotated_at or "",
    }


@app.get("/booking-config")
def get_booking_config(user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _require_admin(user)
    return _booking_cfg_dict(_get_booking_config(db, get_owner_id(user), create=True))


@app.patch("/booking-config")
def update_booking_config(data: BookingConfigPayload,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    _require_admin(user)
    cfg = _get_booking_config(db, get_owner_id(user), create=True)
    if data.enabled is not None:
        cfg.enabled = bool(data.enabled)
        audit(db, user.id, "booking_link",
              "enabled" if cfg.enabled else "disabled")
    if data.horizon_days is not None:
        if not 0 <= data.horizon_days <= BOOKING_MAX_HORIZON_DAYS:
            raise HTTPException(400, f"Horizon must be 0–{BOOKING_MAX_HORIZON_DAYS} days.")
        cfg.horizon_days = data.horizon_days
    db.commit(); db.refresh(cfg)
    return _booking_cfg_dict(cfg)


@app.post("/booking-config/regenerate")
def regenerate_booking_slug(user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Issue a new slug. Every existing copy of the old link stops working."""
    _require_admin(user)
    cfg = _get_booking_config(db, get_owner_id(user), create=True)
    cfg.slug       = secrets.token_urlsafe(12)
    cfg.rotated_at = _mt_now().strftime("%Y-%m-%dT%H:%M:%S")
    db.commit(); db.refresh(cfg)
    audit(db, user.id, "booking_link", "regenerated link")
    return _booking_cfg_dict(cfg)


# ── Public: the agent-facing endpoints ────────────────────────────────────────

@app.get("/book/{slug}")
@limiter.limit("60/minute")
def booking_page(slug: str, request: Request, db: Session = Depends(get_db)):
    _require_booking(db, slug)
    return _page("book.html", {"X-Robots-Tag": "noindex, nofollow"})


@app.get("/api/book/{slug}/availability")
@limiter.limit("120/minute")
def booking_availability(slug: str, request: Request,
                         start: Optional[str] = None,
                         days: int = 7,
                         tz: Optional[str] = None,
                         db: Session = Depends(get_db)):
    """
    Availability for one window. The page requests the week it is displaying,
    so paging forward is unbounded and nothing is precomputed. Each call
    reflects the planner as it stands right now.

    tz: the client's time zone. Slots stay business hours (that is the
    calendar being booked); each one also carries the client's local time.
    """
    cfg   = _require_booking(db, slug)
    today = _mt_now().date()

    if start:
        try:
            start_date = datetime.strptime(start[:10], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid start date.")
        # Never serve the past, and never let a bad value walk backwards.
        if start_date < today:
            start_date = today
    else:
        start_date = today

    if not BOOKING_WINDOW_MIN_DAYS <= days <= BOOKING_WINDOW_MAX_DAYS:
        raise HTTPException(400, f"days must be {BOOKING_WINDOW_MIN_DAYS}-{BOOKING_WINDOW_MAX_DAYS}.")

    limit = cfg.horizon_days or BOOKING_SANITY_LIMIT_DAYS
    if (start_date - today).days > limit:
        raise HTTPException(400, "That date is too far ahead.")

    return _availability(db, cfg.owner_id, start_date, days,
                         last_bookable_date=today + timedelta(days=limit),
                         client_tz=tz)


class PublicBookingPayload(BaseModel):
    """
    No phone field, deliberately. Clients booked by an outside agent are never
    texted by us, so the number is not collected at all rather than collected
    and then ignored.
    """
    lead_name:     str                      # the only required field
    scheduled_for: str                      # YYYY-MM-DDTHH:MM
    comments:      Optional[str] = ""
    booked_by:     Optional[str] = ""       # the agent's own name, optional
    booking_tz:    Optional[str] = None     # the client's time zone


@app.post("/api/book/{slug}", status_code=201)
@limiter.limit("10/minute")
def create_public_booking(slug: str, data: PublicBookingPayload,
                                request: Request, db: Session = Depends(get_db)):
    """
    The only public write in the application. Creates one appointment and
    nothing else — no update path, no delete path, no way to read anyone
    else's data. Every field is re-validated and every availability rule is
    re-checked server-side; the front end is treated as untrusted.
    """
    cfg   = _require_booking(db, slug)
    owner = cfg.owner_id

    lead_name = title_case(sanitize_str(data.lead_name, 200))
    if not lead_name:
        raise HTTPException(400, "Name is required.")

    sched = validate_datetime(data.scheduled_for)
    if not sched.endswith(":00"):
        raise HTTPException(400, "Appointments are booked on the hour.")

    hour = int(sched[11:13])
    if not PLANNER_FIRST_HOUR <= hour <= PLANNER_LAST_HOUR:
        raise HTTPException(400, "That time is outside booking hours.")

    now = _mt_now()
    if sched[:13] <= now.strftime("%Y-%m-%dT%H"):
        raise HTTPException(409, "That time has already passed. Please pick another slot.")
    # Same rule the availability grid uses, so a page left open too long
    # cannot book a slot that has since fallen inside the notice window.
    lead_reason = lead_time_reason(sched)
    if lead_reason:
        raise HTTPException(409, lead_reason)
    limit = cfg.horizon_days or BOOKING_SANITY_LIMIT_DAYS
    if datetime.strptime(sched[:10], "%Y-%m-%d").date() > (now.date() + timedelta(days=limit)):
        raise HTTPException(400, "That date is too far ahead.")

    reason = slot_unavailable_reason(db, owner, sched)
    if reason:
        raise HTTPException(409, "That time is not available. Please pick another slot.")

    # Serialise the final check-then-insert so two agents submitting the same
    # slot at the same moment cannot both succeed.
    # Same one-per-hour rule as the planner: a planner appointment at 14:30
    # holds the 14:00 slot, a callback does not.
    with _booking_lock:
        if appointment_conflict(db, owner, sched):
            raise HTTPException(409, "That slot was just taken. Please pick another.")

        appt = Appointment(
            created_by      = owner,          # attributed to the account being booked
            owner_id        = owner,
            lead_name       = lead_name,
            attendee_name   = "",
            phone_number    = "",          # never collected for agent bookings
            comments        = sanitize_str(data.comments or "", 2000),
            scheduled_for   = sched,
            booked_at       = now.strftime("%Y-%m-%dT%H:%M"),
            appt_type       = "appointment",
            booking_tz      = validate_tz(data.booking_tz),
            booked_by_agent = True,
            booked_by_name  = sanitize_str(data.booked_by or "", 120),
        )
        try:
            days_out = (datetime.strptime(sched[:10], "%Y-%m-%d").date() - now.date()).days
            if days_out >= 5:
                appt.midpoint_send_date = (
                    now.date() + timedelta(days=days_out // 2)
                ).strftime("%Y-%m-%d")
        except Exception:
            pass

        db.add(appt); db.commit(); db.refresh(appt)

    logger.info(
        f"Agent booking: appt {appt.id} ({appt.lead_name}) at {sched}"
        f"{' by ' + appt.booked_by_name if appt.booked_by_name else ''}"
    )
    time_display, date_display = _fmt_appt_time_for_tz(sched, BUSINESS_TZ_NAME)
    out = {"status": "booked", "time": time_display, "date": date_display}
    if appt.booking_tz != BUSINESS_TZ_NAME:
        c_time, c_date = _fmt_appt_time_for_tz(sched, appt.booking_tz)
        out.update({"client_time": c_time, "client_date": c_date,
                    "client_tz_label": tz_label(appt.booking_tz)})
    return out


# ── Confirmations page API ────────────────────────────────────────────────────

# Legacy: the page was originally Tameema23-only. Access is now governed by the
# can_confirmations flag (admins + Tameema23 + Yousef). Kept for backward compat.
CONFIRMATIONS_USERNAME = "Tameema23"
TAMEEMA_PHONE = os.environ.get("TAMEEMA_SUMMARY_PHONE", "")   # daily summary destination


def _is_confirmed(appt: Appointment) -> bool:
    """
    Confirmed if EITHER status field says so, unless the appointment is off:
    cancelled, rescheduled or no-show always win over a confirmation. Without
    this, a cancelled booking that still carried an old "confirmed" could get
    a "your appointment is confirmed" text.
    """
    if not _sms_status_allows_texting(appt) or (getattr(appt, "appt_status", "") or "") == "no_show":
        return False
    return (appt.sms_status == "confirmed"
            or getattr(appt, "appt_status", "") == "confirmed")


async def _maybe_send_confirmed_notice(db: Session, appt: Appointment) -> bool:
    """
    Send the one-off 'your appointment is confirmed' SMS — exactly once.

    Idempotency: guarded by sms_sent_confirmed_notice. Even if the client
    replies YES repeatedly, or an admin re-saves 'confirmed' on the planner,
    this fires at most once per appointment.

    Only sends when:
      - the appointment is actually confirmed (either status field), AND
      - the notice has not already been sent, AND
      - it is not a callback, AND
      - there is a phone number on file.

    Caller is responsible for committing the surrounding transaction; this
    function commits the flag itself so the guard persists even if a later
    step in the caller fails.
    """
    if not _is_confirmed(appt):
        return False
    if getattr(appt, "sms_sent_confirmed_notice", False):
        return False
    if (appt.appt_type or "") == "callback":
        return False
    # Marking an appointment confirmed after its start time (e.g. tidying
    # records later) must not text the client "Your appointment is confirmed".
    if not _appt_is_upcoming(appt):
        return False
    # Must have at least one recipient with a phone number
    if not _appt_recipients(db, appt):
        return False

    # Send the confirmed notice to the primary + every extra recipient,
    # each personalized with their own first name.
    time_display, date_display = _fmt_appt_time_for_tz(
        appt.scheduled_for, appt.booking_tz or BUSINESS_TZ_NAME)
    summary = await _send_to_all_recipients(
        db, appt,
        lambda fn: _build_confirmed_notice_sms(fn, time_display, date_display),
        "CONFIRMED NOTICE",
        still_ok=lambda a: _is_confirmed(a) and _appt_is_upcoming(a),
    )

    # Keep failed recipients retryable without resending to the others.
    if summary["complete"]:
        appt.sms_sent_confirmed_notice = True
        db.commit()
        logger.info(f"Confirmed notice sent for appt {appt.id} ({appt.lead_name}) "
                    f"→ {summary['sent']}/{summary['total']} recipient(s)")
        return True

    logger.warning("Confirmed notice incomplete for appointment %s", appt.id)
    return False


# ── Daily summary job ─────────────────────────────────────────────────────────

async def _send_daily_summary(target_date: Optional[str] = None):
    """
    Sends Tameema a daily SMS listing appointments for target_date.
    If target_date is None, defaults to today (used for YES confirmations).
    """
    db = SessionLocal()
    try:
        mt        = BUSINESS_TZ
        now_mt    = datetime.now(mt)
        date_str  = target_date or now_mt.strftime("%Y-%m-%d")
        date_obj  = datetime.strptime(date_str, "%Y-%m-%d")
        date_label = date_obj.strftime("%B %-d, %Y")

        # Get all admin appointments for target_date
        admins = db.query(User).filter(User.role == "admin").all()
        rows   = []
        for admin in admins:
            appts = db.query(Appointment).filter(
                Appointment.owner_id == admin.id,
                Appointment.scheduled_for.startswith(date_str),
                ).order_by(Appointment.scheduled_for).all()
            rows.extend(a for a in appts if (a.appt_type or "") != "callback")

        rows.sort(key=lambda a: a.scheduled_for)

        if not rows:
            logger.info(f"Daily summary: no appointments on {date_str}, skipping.")
            return None  # nothing to send (distinct from a failed send)

        lines = [date_label, ""]
        for a in rows:
            try:
                time_part = a.scheduled_for.split("T")[1]
                h, m      = map(int, time_part.split(":"))
                ampm      = "am" if h < 12 else "pm"
                h12       = h % 12 or 12
                time_str  = f"{h12}{':{:02d}'.format(m) if m else ''}{ampm}"
            except Exception:
                time_str = "?"

            sms_st  = a.sms_status  or ""
            appt_st = getattr(a, "appt_status", "") or ""
            if _is_confirmed(a):
                suffix = " - ✅"
            elif appt_st == "no_show":
                suffix = " - NS"
            elif appt_st == "cancelled":
                suffix = " - CXL"
            elif appt_st == "rescheduled" or sms_st == "rescheduled":
                suffix = " - rs"
            else:
                suffix = ""

            lines.append(f"{a.lead_name.split()[0]} {time_str}{suffix}")

        message = "\n".join(lines)

        if not TAMEEMA_PHONE:
            logger.warning("Daily summary: TAMEEMA_SUMMARY_PHONE is not set, cannot send.")
            return False

        token_row = db.query(RcToken).first()
        if not token_row:
            logger.warning("Daily summary: no RC token found, cannot send.")
            return False

        result = await send_sms(db, token_row.owner_user_id, TAMEEMA_PHONE, message)
        logger.info(f"Daily summary sent → {TAMEEMA_PHONE} | {result.get('detail')}")
        # Report the real outcome so the 9:01 PM retry fires when a send fails.
        # A skipped duplicate means Tameema already has this exact summary.
        return bool(result.get("sent") or result.get("dry_run") or result.get("skipped"))

    except Exception as e:
        logger.error(f"Daily summary job error: {e}")
        return False
    finally:
        db.close()

@app.get("/confirmations")
def get_confirmations(date: Optional[str] = None,
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """
    Returns appointments for ALL admins (so confirmations users see Hazem's).
    Accessible by admins and users with can_confirmations.
    """
    _check_confirmations_access(user)

    # Validated: a raw value went into a LIKE prefix, so "%" listed every date.
    target_date = validate_date(date) if date else business_now().strftime("%Y-%m-%d")

    # Get all admin users
    admins = db.query(User).filter(User.role == "admin").all()
    result = []
    for admin in admins:
        appts = db.query(Appointment).filter(
            Appointment.owner_id == admin.id,
            Appointment.scheduled_for.startswith(target_date),
        ).order_by(Appointment.scheduled_for).all()
        for a in appts:
            result.append({
                "id":            a.id,
                "lead_name":     a.lead_name,
                "attendee_name": a.attendee_name or "",
                "phone_number":  a.phone_number or "",
                "scheduled_for": a.scheduled_for,
                "sms_status":    a.sms_status or "",
                "appt_status":   getattr(a, "appt_status", "") or "",
                "sms_sent_evening": bool(a.sms_sent_evening),
                "sms_sent_morning": bool(a.sms_sent_morning),
                "sms_sent_confirmed_notice": bool(getattr(a, "sms_sent_confirmed_notice", False)),
                "owner":         admin.username,
            })
    result.sort(key=lambda x: x["scheduled_for"])
    return result

def _apply_status(db: Session, appt: Appointment, status: str, *, from_confirmations=False):
    with _booking_lock:
        try:
            db.refresh(appt)
        except InvalidRequestError:
            raise HTTPException(404, "Appointment not found.") from None
        old_appt = appt.appt_status or ""
        old_sms = appt.sms_status or ""
        if from_confirmations:
            if status == "confirmed" and old_appt in (*RELEASED_STATUSES, "no_show"):
                label = old_appt.replace("_", "-")
                raise HTTPException(400, f"This appointment is marked {label} on the planner. "
                                         "Clear that status first if the client is attending.")
            new_appt = "" if status != "confirmed" and old_appt == "confirmed" else old_appt
            new_sms = status
        else:
            new_appt = status
            new_sms = old_sms
            if (status == "confirmed" and old_sms in RELEASED_STATUSES
                    or status != "confirmed" and old_sms == "confirmed"):
                new_sms = ""
        if (releases_slot(old_appt, old_sms) and not releases_slot(new_appt, new_sms)
                and (appt.appt_type or "appointment") != "callback"
                and appt.scheduled_for
                and appointment_conflict(db, appt.owner_id, appt.scheduled_for, exclude_id=appt.id)):
            raise HTTPException(400, "This appointment cannot be restored. "
                                     + conflict_message(appt.scheduled_for))
        appt.appt_status = new_appt
        appt.sms_status = new_sms
        db.commit()


@app.patch("/confirmations/{appt_id}/status")
async def set_confirmation_status(appt_id: int,
                             data: ReferralEntryStatusPayload,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """Confirmations-page users can set sms_status: confirmed | rescheduled | (empty)."""
    _check_confirmations_access(user)
    appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
    # Same scope as the list this page shows: appointments on an admin's calendar.
    owner_row = db.query(User).filter(User.id == appt.owner_id).first() if appt else None
    if not appt or not owner_row or owner_row.role != "admin":
        raise HTTPException(404, "Appointment not found.")
    if data.status not in ("confirmed", "rescheduled", ""):
        raise HTTPException(422, "Invalid status.")
    _apply_status(db, appt, data.status, from_confirmations=True)

    # If this transition makes the appointment confirmed, fire the one-off notice.
    if data.status == "confirmed":
        await _maybe_send_confirmed_notice(db, appt)

    # Keep Tameema's summary in sync if the appointment is today.
    today_str = business_now().strftime("%Y-%m-%d")
    if appt.scheduled_for and appt.scheduled_for.startswith(today_str):
        await _send_daily_summary(today_str)

    return {"id": appt_id, "sms_status": appt.sms_status}


class ApptStatusPayload(BaseModel):
    appt_status: str  # "" | "confirmed" | "rescheduled" | "no_show" | "cancelled"

@app.patch("/appointments/{appt_id}/appt-status")
async def set_appt_status(appt_id: int,
                    data: ApptStatusPayload,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """
    Admin sets the outcome status of an appointment.
    Valid values: "" | "confirmed" | "rescheduled" | "no_show" | "cancelled"
    If the appointment is scheduled for today, automatically re-sends the
    daily summary text to Tameema with the updated status reflected.
    """
    _check_planner_access(user)
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt:
        raise HTTPException(404, "Appointment not found.")
    valid = ("", "confirmed", "rescheduled", "no_show", "cancelled")
    if data.appt_status not in valid:
        raise HTTPException(422, "Invalid appt_status.")
    _apply_status(db, appt, data.appt_status)

    # If admin just confirmed on the planner, fire the one-off confirmed notice
    # (idempotent — won't double-send if the client also replied YES).
    if data.appt_status == "confirmed":
        await _maybe_send_confirmed_notice(db, appt)

    # If the appointment is today, resend the summary so Tameema sees the new status
    mt = BUSINESS_TZ
    today_str = datetime.now(mt).strftime("%Y-%m-%d")
    if appt.scheduled_for and appt.scheduled_for.startswith(today_str):
        await _send_daily_summary(today_str)

    return {"id": appt_id,
            "appt_status": appt.appt_status,
            "sms_status":  appt.sms_status or ""}

# ── RC: register inbound SMS webhook ─────────────────────────────────────────

@app.post("/rc/register-webhook")
async def rc_register_webhook(user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    """
    Registers a RingCentral webhook subscription so inbound SMS replies
    are posted to /rc/webhook. Call this once after connecting RC.
    Accessible by admins and users with can_confirmations.
    """
    _check_confirmations_access(user)
    token_row = _get_rc_token(db, user.id)
    if not token_row:
        # Try any connected token
        token_row = db.query(RcToken).first()
    if not token_row:
        raise HTTPException(404, "RingCentral not connected.")

    try:
        result = await _sync_rc_webhook(db, token_row, create_if_missing=True)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return result


def _rc_webhook_url() -> str:
    return f"{RC_REDIRECT_URI.replace('/rc/callback', '')}/rc/webhook"


# RingCentral's maximum lifetime for a webhook subscription (10 years). The
# old value asked for twice that.
RC_SUBSCRIPTION_SECONDS = 315360000
_rc_sync_lock = asyncio.Lock()


async def _sync_rc_webhook(db: Session, token_row, create_if_missing: bool) -> dict:
    """
    Make sure exactly ONE healthy RingCentral subscription posts to our webhook.

    Registering used to create a new subscription on every click and never
    remove the old ones. RingCentral delivers every inbound text once per
    subscription, so three registrations meant each YES hit /rc/webhook three
    times. This keeps the newest Active subscription for our URL that listens
    for SMS, deletes the rest, and only creates one when none is healthy.

    When RC_WEBHOOK_TOKEN is set and an explicit registration (not startup)
    runs, the subscription is recreated with that token and verification is
    switched on, because an existing subscription can't be given a token.
    """
    async with _rc_sync_lock:     # two clicks can't race each other
        return await _sync_rc_webhook_locked(db, token_row, create_if_missing)


async def _sync_rc_webhook_locked(db: Session, token_row, create_if_missing: bool) -> dict:
    if not await _refresh_rc_token_if_needed(db, token_row):
        raise RuntimeError("Token refresh failed.")

    webhook_url = _rc_webhook_url()
    sms_filter  = "/restapi/v1.0/account/~/extension/~/message-store/instant?type=SMS"
    verify_token = _rc_webhook_token()
    active_token = _get_setting(db, "rc_webhook_verified")
    verify_token = verify_token or active_token
    subscription_key = f"rc_verified_subscription:{token_row.owner_user_id}"
    verified_id = _get_setting(db, subscription_key)
    headers = {
        "Authorization": f"Bearer {token_row.access_token}",
        "Content-Type": "application/json",
    }
    base = f"{RC_AUTH_BASE}/restapi/v1.0/subscription"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(base, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"RC error listing subscriptions: {resp.text}")

        ours = [s for s in resp.json().get("records", [])
                if (s.get("deliveryMode") or {}).get("address") == webhook_url]
        healthy = sorted((s for s in ours
                          if s.get("status") == "Active"
                          # RingCentral may echo the filter with real account
                          # and extension IDs instead of "~".
                          and any("message-store/instant" in f and "SMS" in f
                                  for f in s.get("eventFilters", []))),
                         key=lambda s: s.get("creationTime") or "", reverse=True)
        if verify_token:
            healthy = [s for s in healthy if s.get("id") == verified_id and active_token == verify_token]
        keep = healthy[0] if healthy else None
        registered = False
        if keep is None:
            if not create_if_missing:
                return {"status": "none_healthy", "webhook_url": webhook_url, "removed_duplicates": 0}
            delivery = {"transportType": "WebHook", "address": webhook_url}
            if verify_token:
                delivery["verificationToken"] = verify_token
            resp = await client.post(base, headers=headers, json={
                "eventFilters": [sms_filter],
                "deliveryMode": delivery,
                "expiresIn": RC_SUBSCRIPTION_SECONDS,
            })
            if resp.status_code not in (200, 201):
                logger.error("RC webhook registration failed (%s)", resp.status_code)
                raise RuntimeError(f"RingCentral rejected the subscription ({resp.status_code}).")
            keep = resp.json()
            if not keep.get("id"):
                raise RuntimeError("RingCentral did not return a subscription ID.")
            if verify_token:
                _set_setting(db, "rc_webhook_verified", verify_token)
                _set_setting(db, subscription_key, keep["id"])
            registered = True

        removed = 0
        for subscription in ours:
            if subscription.get("id") == keep.get("id"):
                continue
            result = await client.delete(f"{base}/{subscription['id']}", headers=headers)
            if result.status_code in (200, 204):
                removed += 1
            else:
                logger.warning("RC webhook cleanup failed (%s)", result.status_code)

    return {"status": "registered" if registered else "already_registered",
            "webhook_url": webhook_url, "subscription_id": keep.get("id"),
            "expires_at": keep.get("expirationTime"), "verified": bool(verify_token),
            "removed_duplicates": removed}


async def _cleanup_rc_webhooks_on_startup():
    """On boot, remove duplicate webhook subscriptions. Never creates one."""
    db = SessionLocal()
    try:
        for token_row in db.query(RcToken).all():
            try:
                await _sync_rc_webhook(db, token_row, create_if_missing=False)
            except Exception as e:
                logger.error(f"RC webhook startup cleanup failed for owner "
                             f"{token_row.owner_user_id}: {e}")
    finally:
        db.close()

class SendConfirmationsPayload(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD; defaults to today (Mountain Time)

@app.post("/rc/send-confirmation-texts")
async def send_confirmation_texts(data: SendConfirmationsPayload = SendConfirmationsPayload(),
                                   user: User = Depends(get_current_user),
                                   db: Session = Depends(get_db)):
    """
    Send appointment confirmation texts to clients on a specific date only.
    Independent of the daily summary. Defaults to today in Mountain Time.
    Accessible by admins and users with can_confirmations.
    """
    _check_confirmations_access(user)
    mt = BUSINESS_TZ
    if data.date:
        target_date = validate_date(data.date)
    else:
        target_date = datetime.now(mt).strftime("%Y-%m-%d")

    summary = await _send_confirmation_texts_for_date(target_date)
    return {
        "status": "fired",
        "date": target_date,
        "detail": f"Confirmation texts for {target_date}: "
                  f"{summary.get('sent', 0)} sent, {summary.get('failed', 0)} failed "
                  f"of {summary.get('total', 0)} eligible.",
        **summary,
    }


@app.post("/rc/test-sms")
async def test_sms_trigger(user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """
    Legacy testing endpoint — fires evening + morning jobs and the summary.
    Kept for backward compatibility. Accessible by admins and can_confirmations users.
    """
    _check_confirmations_access(user)
    await _run_sms_job("evening")
    await _run_sms_job("morning")
    await _send_daily_summary()
    return {"status": "SMS jobs and daily summary fired."}

class SendSummaryPayload(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD, defaults to tomorrow if omitted

@app.post("/rc/send-summary")
async def manual_send_summary(data: SendSummaryPayload = SendSummaryPayload(),
                               user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    """
    Manually trigger the daily summary text to Tameema.
    date: YYYY-MM-DD to send appointments for (defaults to tomorrow).
    Accessible by admins and users with can_confirmations.
    """
    _check_confirmations_access(user)

    mt = BUSINESS_TZ
    if data.date:
        target_date = validate_date(data.date)
    else:
        # Default to tomorrow — mirrors what the 9pm scheduler sends
        target_date = (datetime.now(mt) + timedelta(days=1)).strftime("%Y-%m-%d")

    sent = await _send_daily_summary(target_date)
    if sent is None:
        return {"status": "no_appointments", "date": target_date,
                "detail": f"Summary for {target_date} skipped (no appointments)"}
    if not sent:
        return {"status": "failed", "date": target_date,
                "detail": f"Summary for {target_date} could not be sent. Check RingCentral."}
    return {"status": "sent", "date": target_date,
            "detail": f"Summary for {target_date} sent to {TAMEEMA_PHONE}"}


@app.post("/rc/send-booking-texts")
async def manual_send_booking_texts(user: User = Depends(get_current_user),
                                     db: Session = Depends(get_db)):
    """
    Manually trigger booking confirmation texts.
    Sends to ALL future appointments that haven't received a booking text yet,
    regardless of when they were booked. Use this for catch-up after reschedules.
    Accessible by admins and users with can_confirmations.
    """
    _check_confirmations_access(user)
    await _run_booking_job_catchup()
    return {"status": "fired", "detail": "Booking confirmation sent to all eligible future appointments."}

# ── Confirmations HTML page ───────────────────────────────────────────────────

@app.get("/confirmations.html")
def confirmations_page():
    return _page("confirmations.html")