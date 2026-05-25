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

import os, re, html, logging, shutil, hashlib, asyncio, urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
import httpx

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo
from jose import jwt, JWTError
from passlib.context import CryptContext
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Import from same backend/ folder ─────────────────────────────────────────
from backend.database import SessionLocal, create_db, User, DailyLog, Appointment, QualityEntry, AuditLog, ReferralProgram, ReferralEntry, BlockedDay, BlockedDate, BlockedHour, TimesheetEntry, TimesheetPunch, RcToken

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kpi")

# ── Build hash — computed once at startup from all JS/CSS file contents ────────
# This hash changes automatically every deploy whenever any frontend file changes.
# It is injected into every HTML response as the ?v= query string on static assets,
# so the browser is always forced to fetch the latest files after a deploy.
# Your client can log out and log back in to pick up new features — no Ctrl+R needed.

def _compute_build_hash() -> str:
    frontend_dir = "frontend"
    h = hashlib.md5()
    extensions = (".js", ".css")
    try:
        for root, _, files in os.walk(frontend_dir):
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
#   • 9:00 AM — morning reminder (day of appointment)
# Both jobs respect dry_run mode — no real texts sent until live mode is on.

async def _run_sms_job(job_type: str):
    """
    job_type: "evening" — sends to appointments TOMORROW
              "morning"  — sends to appointments TODAY
    """
    db = SessionLocal()
    try:
        mt = ZoneInfo("America/Edmonton")
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
            Appointment.phone_number != "",
            Appointment.phone_number != None,
            Appointment.appt_type != "callback",
            Appointment.sms_status != "rescheduled",
            Appointment.appt_status != "cancelled",
            Appointment.appt_status != "no_show",
        ).all()

        for appt in appts:
            # Skip if already sent this message
            already_sent = getattr(appt, sent_flag)
            if already_sent:
                continue

            # Format time and date in the booking timezone
            time_display, date_display = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or "America/Edmonton"
            )

            first_name = (appt.attendee_name or appt.lead_name or "").split()[0].capitalize() if (appt.attendee_name or appt.lead_name) else "there"
            message    = template.format(name=first_name, time=time_display, date=date_display)

            result = await send_sms(db, appt.owner_id, appt.phone_number, message)

            # Mark as sent (even in dry run — so we don't log it repeatedly)
            setattr(appt, sent_flag, True)
            db.commit()

            logger.info(
                f"[SMS {label.upper()}] Appt {appt.id} ({appt.lead_name}) "
                f"→ {appt.phone_number} | dry_run={result.get('dry_run')} | {result.get('detail')}"
            )

    except Exception as e:
        logger.error(f"SMS job ({job_type}) error: {e}")
    finally:
        db.close()


async def _run_reminder_job():
    """
    Fires every minute (called from scheduler).
    Finds appointments starting in exactly 60 minutes that are NOT confirmed
    and have a phone number, and sends them a quick reminder text.
    Tracks sent reminders via a new sms_sent_reminder flag.

    Special case: appointments at 10:00 AM (or any time where 60 min prior
    would be at or before 9:00 AM) get their reminder at 30 minutes before
    instead, so clients aren't hit with two texts back-to-back at 9am.
    """
    db = SessionLocal()
    try:
        mt     = ZoneInfo("America/Edmonton")
        now_mt = datetime.now(mt)

        # Standard window: appointments starting 59-61 minutes from now
        target_start_60 = now_mt + timedelta(minutes=59)
        target_end_60   = now_mt + timedelta(minutes=61)
        start_str_60 = target_start_60.strftime("%Y-%m-%dT%H:%M")
        end_str_60   = target_end_60.strftime("%Y-%m-%dT%H:%M")

        # Early-morning window: appointments starting 29-31 minutes from now
        # Only applies when now is between 9:00-9:01am (catches 10am appts)
        target_start_30 = now_mt + timedelta(minutes=29)
        target_end_30   = now_mt + timedelta(minutes=31)
        start_str_30 = target_start_30.strftime("%Y-%m-%dT%H:%M")
        end_str_30   = target_end_30.strftime("%Y-%m-%dT%H:%M")

        # Determine which window to use:
        # If the 60-min target falls at or before 9:00 AM, use the 30-min window instead
        use_30min_window = target_end_60.hour < 9 or (target_end_60.hour == 9 and target_end_60.minute == 0)

        if use_30min_window:
            start_str = start_str_30
            end_str   = end_str_30
        else:
            start_str = start_str_60
            end_str   = end_str_60

        appts = db.query(Appointment).filter(
            Appointment.scheduled_for >= start_str,
            Appointment.scheduled_for <= end_str,
            Appointment.phone_number != "",
            Appointment.phone_number != None,
            Appointment.appt_type != "callback",
            Appointment.sms_status != "confirmed",
            Appointment.sms_status != "rescheduled",
            Appointment.appt_status != "cancelled",
            Appointment.appt_status != "no_show",
            Appointment.sms_sent_reminder == False,
        ).all()

        for appt in appts:
            time_display, _ = _fmt_appt_time_for_tz(
                appt.scheduled_for,
                appt.booking_tz or "America/Edmonton"
            )
            first_name = (appt.attendee_name or appt.lead_name or "").split()[0].capitalize() if (appt.attendee_name or appt.lead_name) else "there"
            message    = SMS_REMINDER_TEMPLATE.format(name=first_name, time=time_display)

            result = await send_sms(db, appt.owner_id, appt.phone_number, message)
            appt.sms_sent_reminder = True
            db.commit()

            logger.info(
                f"[SMS REMINDER] Appt {appt.id} ({appt.lead_name}) "
                f"→ {appt.phone_number} | dry_run={result.get('dry_run')} | {result.get('detail')}"
            )

    except Exception as e:
        logger.error(f"Reminder job error: {e}")
    finally:
        db.close()

async def _scheduler_loop():
    mt = ZoneInfo("America/Edmonton")
    fired = {
        "evening":         None,
        "morning":         None,
        "summary_morning": None,   # 8am — today's appointments
        "summary_evening": None,   # 9pm — tomorrow's appointments
        "summary_retry":   None,   # retry flag for 9pm
    }
    summary_evening_sent = {}  # date → bool, tracks if 9pm actually succeeded

    while True:
        try:
            now    = datetime.now(mt)
            today  = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            h, min_ = now.hour, now.minute

            # 8:00 AM — send TODAY's appointment list
            if h == 8 and min_ == 0 and fired["summary_morning"] != today:
                fired["summary_morning"] = today
                logger.info("Scheduler: firing 8am daily summary (today's appointments)")
                await _send_daily_summary(today)

            # 9:00 AM — morning client texts
            if h == 9 and min_ == 0 and fired["morning"] != today:
                fired["morning"] = today
                logger.info("Scheduler: firing morning SMS job")
                await _run_sms_job("morning")

            # 8:00 PM — evening client texts (tomorrow's appointments)
            if h == 20 and min_ == 0 and fired["evening"] != today:
                fired["evening"] = today
                logger.info("Scheduler: firing evening SMS job")
                await _run_sms_job("evening")

            # 9:00 PM — send TOMORROW's appointment list
            if h == 21 and min_ == 0 and fired["summary_evening"] != today:
                fired["summary_evening"] = today
                logger.info("Scheduler: firing 9pm daily summary (tomorrow's appointments)")
                sent = await _send_daily_summary(tomorrow)
                summary_evening_sent[today] = sent

            # 9:01 PM — retry once if 9pm summary failed
            if h == 21 and min_ == 1 and fired["summary_retry"] != today:
                if not summary_evening_sent.get(today, True):
                    fired["summary_retry"] = today
                    logger.info("Scheduler: retrying 9pm summary (previous attempt failed)")
                    await _send_daily_summary(tomorrow)
                else:
                    fired["summary_retry"] = today  # already sent, flag and skip

            # Every minute — 1hr reminder for unconfirmed appointments
            await _run_reminder_job()

        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")

        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    """Start background scheduler on app startup."""
    task = asyncio.create_task(_scheduler_loop())
    logger.info("SMS scheduler started.")
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
        "https://data-log.onrender.com"
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

# ── Security headers — added to every response ─────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"]    = "nosniff"
        response.headers["X-Frame-Options"]           = "DENY"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
        # CSP — allows our CDN scripts, Google Fonts, own API
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://data-log.onrender.com; "
            "frame-ancestors 'none';"
        )
        # HTML pages must never be cached — ensures fresh content on every navigation
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"]        = "no-cache"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Cache-busting middleware — rewrites ?v=... in HTML responses ───────────────
# Replaces any ?v=<anything> on .js and .css references with ?v=BUILD_HASH.
# Works on every FileResponse HTML page automatically — no manual version bumping.
from fastapi.responses import Response as StarletteResponse

class CacheBustMiddleware(BaseHTTPMiddleware):
    _pattern = re.compile(rb'(\.(js|css))\?v=[^"\'&\s]+')

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return response
        # Read and rewrite the body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        new_body = self._pattern.sub(
            lambda m: m.group(1) + b"?v=" + BUILD_HASH.encode(),
            body
        )
        # Drop Content-Length — StarletteResponse recomputes it from new_body.
        # Without this, uvicorn crashes with "Response content longer than Content-Length"
        # because the rewritten body is longer than the original header value.
        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.pop("Content-Length", None)
        return StarletteResponse(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type=content_type,
        )

app.add_middleware(CacheBustMiddleware)

# ── Frontend pages ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_home():    return FileResponse("frontend/login.html")
@app.get("/index.html")
def dashboard():     return FileResponse("frontend/index.html")
@app.get("/log.html")
def log_page():      return FileResponse("frontend/log.html")
@app.get("/reports.html")
def reports_page():  return FileResponse("frontend/reports.html")
@app.get("/history.html")
def history_page():  return FileResponse("frontend/history.html")
@app.get("/settings.html")
def settings_page(): return FileResponse("frontend/settings.html")
@app.get("/planner.html")
def planner_page():  return FileResponse("frontend/planner.html")
@app.get("/quality.html")
def quality_page():  return FileResponse("frontend/quality.html")
@app.get("/referrals.html")
def referrals_page(): return FileResponse("frontend/referrals.html")
@app.get("/timesheet.html")
def timesheet_page(): return FileResponse("frontend/timesheet.html")

@app.get("/manifest.json")
def manifest():      return FileResponse("frontend/manifest.json", media_type="application/manifest+json")

@app.get("/icon-192.png")
def icon192():       return FileResponse("frontend/icon-192.png", media_type="image/png")

@app.get("/icon-512.png")
def icon512():       return FileResponse("frontend/icon-512.png", media_type="image/png")

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
    return value

ALLOWED_TIMEZONES = {
    "America/Edmonton", "America/Vancouver", "America/Winnipeg",
    "America/Toronto",  "America/Halifax",  "America/St_Johns"
}

def validate_tz(tz: str) -> str:
    return tz if tz in ALLOWED_TIMEZONES else "America/Edmonton"

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
        now = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M:%S")
        db.add(AuditLog(user_id=user_id, action=action,
                        detail=detail[:500], timestamp=now))
        db.commit()
    except Exception as e:
        logger.error(f"Audit log failed: {e}")

# ── JWT ────────────────────────────────────────────────────────────────────────

def _midnight_utc() -> datetime:
    """Returns UTC datetime for midnight tonight in Mountain Time (America/Edmonton)."""
    now_mt = datetime.now(ZoneInfo("America/Edmonton"))
    midnight_mt = now_mt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return midnight_mt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

def create_token(user_id: int, role: str, token_version: int,
                 can_planner: bool = True, can_quality: bool = False,
                 password_expires_at: Optional[str] = None) -> str:
    return jwt.encode({
        "user_id":             user_id,
        "role":                role,
        "token_version":       token_version,
        "can_planner":         can_planner,
        "can_quality":         can_quality,
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

def _check_planner_access(user: User):
    if user.role == "admin" or bool(user.can_planner):
        return
    raise HTTPException(403, "No planner access.")

def _check_quality_access(user: User):
    if user.role == "admin" or bool(user.can_quality):
        return
    raise HTTPException(403, "No quality access.")

def get_owner_id(user: User) -> int:
    return user.owner_id if user.role == "assistant" else user.id

# ── Auth ───────────────────────────────────────────────────────────────────────

class UserPayload(BaseModel):
    username: str
    password: str

@app.post("/create-user", status_code=201)
def create_user(data: UserPayload, db: Session = Depends(get_db)):
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
    else:
        can_planner = bool(user.can_planner)
        can_quality = bool(user.can_quality)

    # ── Password expiry check (6 months) ─────────────────────────────────────
    now_mt = datetime.now(ZoneInfo("America/Edmonton"))
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
                                    password_expires_at
                                ),
        "role":                 user.role or "admin",
        "can_planner":          can_planner,
        "can_quality":          can_quality,
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
    user.password_changed_at     = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M:%S")
    db.commit()

    audit(db, user.id, "password_change", "Password updated")
    return {"status": "password updated"}

# ── Assistant management ───────────────────────────────────────────────────────

class AssistantPayload(BaseModel):
    username:    str
    password:    str
    can_planner: bool = True
    can_quality: bool = False

class AssistantPermissionsPayload(BaseModel):
    can_planner: bool
    can_quality: bool

@app.post("/create-assistant", status_code=201)
def create_assistant(data: AssistantPayload,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _require_admin(user)
    username = validate_username(data.username)
    password = validate_new_password(data.password)
    if not data.can_planner and not data.can_quality:
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
    db.commit()
    audit(db, user.id, "update_permissions",
          f"{assistant.username}: planner={data.can_planner}, quality={data.can_quality}")
    return {"status": "updated",
            "can_planner": bool(assistant.can_planner),
            "can_quality": bool(assistant.can_quality)}

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

    @field_validator("date")
    @classmethod
    def check_date(cls, v):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Invalid date format.")
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @field_validator("appointments_start", "appointments_finish", "total_presentations",
                     "total_sales", "referrals_collected", "referral_presentations",
                     "referral_sales", "assigned_leads", "bad_leads")
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
         "bad_leads": l.bad_leads or 0}
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

class AppointmentPayload(BaseModel):
    lead_name:     str
    attendee_name: Optional[str] = ""
    phone_number:  Optional[str] = ""
    comments:      Optional[str] = ""
    scheduled_for: str
    appt_type:     Optional[str] = "appointment"
    booking_tz:    Optional[str] = "America/Edmonton"

@app.post("/appointments", status_code=201)
def create_appointment(data: AppointmentPayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _check_planner_access(user)
    lead_name = sanitize_str(data.lead_name, 200)
    if not lead_name:
        raise HTTPException(400, "Lead name is required.")
    # ── Blocked-day enforcement ──────────────────────────────
    owner = get_owner_id(user)
    sched = validate_datetime(data.scheduled_for)
    sched_date = datetime.strptime(sched[:10], "%Y-%m-%d")
    sched_dow  = sched_date.weekday()            # Mon=0 … Sun=6
    sched_dow  = (sched_dow + 1) % 7             # convert to JS style: Sun=0 … Sat=6
    blocked = db.query(BlockedDay).filter(
        BlockedDay.owner_id == owner, BlockedDay.day_of_week == sched_dow
    ).first()
    if blocked:
        DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
        raise HTTPException(400, f"{DAY_NAMES[sched_dow]} is marked as unavailable. Appointments cannot be scheduled on this day.")
    # ── One-time blocked date enforcement ─────────────────────
    blocked_date = db.query(BlockedDate).filter(
        BlockedDate.owner_id == owner, BlockedDate.date == sched[:10]
    ).first()
    if blocked_date:
        raise HTTPException(400, f"{sched[:10]} is marked as unavailable. Appointments cannot be scheduled on this date.")
    # Normalize phone: strip everything except digits, keep leading +
    raw_phone = re.sub(r"[^\d+]", "", data.phone_number or "")
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
    appt  = Appointment(
        created_by=user.id, owner_id=owner,
        lead_name=title_case(sanitize_str(data.lead_name, 200)),
        attendee_name=title_case(sanitize_str(data.attendee_name or "", 200)),
        phone_number=raw_phone[:20],
        comments=sanitize_str(data.comments or "", 2000),
        scheduled_for=validate_datetime(data.scheduled_for),
        booked_at=now,
        appt_type=data.appt_type if data.appt_type in ("appointment","callback") else "appointment",
        booking_tz=validate_tz(data.booking_tz or "America/Edmonton"),
    )
    db.add(appt); db.commit(); db.refresh(appt)
    return _appt_dict(appt, db)

@app.get("/appointments")
def get_appointments(user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _check_planner_access(user)
    owner = get_owner_id(user)
    return [_appt_dict(a, db) for a in
            db.query(Appointment).filter(Appointment.owner_id == owner)
              .order_by(Appointment.scheduled_for).all()]

@app.put("/appointments/{appt_id}")
def update_appointment(appt_id: int, data: AppointmentPayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _check_planner_access(user)
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt: raise HTTPException(404, "Appointment not found.")
    # ── Blocked-day enforcement ──────────────────────────────
    sched = validate_datetime(data.scheduled_for)
    sched_date = datetime.strptime(sched[:10], "%Y-%m-%d")
    sched_dow  = (sched_date.weekday() + 1) % 7  # JS style: Sun=0 … Sat=6
    blocked = db.query(BlockedDay).filter(
        BlockedDay.owner_id == owner, BlockedDay.day_of_week == sched_dow
    ).first()
    if blocked:
        DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
        raise HTTPException(400, f"{DAY_NAMES[sched_dow]} is marked as unavailable. Appointments cannot be rescheduled to this day.")
    # ── One-time blocked date enforcement ─────────────────────
    blocked_date = db.query(BlockedDate).filter(
        BlockedDate.owner_id == owner, BlockedDate.date == sched[:10]
    ).first()
    if blocked_date:
        raise HTTPException(400, f"{sched[:10]} is marked as unavailable. Appointments cannot be rescheduled to this date.")
    appt.lead_name     = title_case(sanitize_str(data.lead_name, 200))
    appt.attendee_name = title_case(sanitize_str(data.attendee_name or "", 200))
    appt.phone_number  = re.sub(r"[^\d+]", "", data.phone_number or "")[:20]
    appt.comments      = sanitize_str(data.comments or "", 2000)
    appt.appt_type     = data.appt_type if data.appt_type in ("appointment","callback") else "appointment"
    if data.booking_tz: appt.booking_tz = validate_tz(data.booking_tz)

    # ── Smart SMS reset on reschedule ───────────────────────────
    new_sched  = validate_datetime(data.scheduled_for)
    old_date   = appt.scheduled_for[:10] if appt.scheduled_for else ""
    new_date   = new_sched[:10]
    old_time   = appt.scheduled_for[11:16] if appt.scheduled_for and len(appt.scheduled_for) > 10 else ""
    new_time   = new_sched[11:16] if len(new_sched) > 10 else ""

    if old_date != new_date:
        # Date changed — full reset so they get a fresh evening + morning text
        appt.sms_sent_evening  = False
        appt.sms_sent_morning  = False
        appt.sms_sent_reminder = False
        appt.sms_status        = ""
    elif old_time != new_time:
        # Same date, time changed — reset evening + status only
        # Morning already sent (client got it), no need to re-send
        appt.sms_sent_evening  = False
        appt.sms_sent_reminder = False
        appt.sms_status        = ""
    # else: only non-time fields changed — leave SMS fields untouched

    appt.scheduled_for = new_sched
    db.commit()
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

def _appt_dict(appt, db):
    creator = db.query(User).filter(User.id == appt.created_by).first()
    return {"id": appt.id, "lead_name": appt.lead_name,
            "attendee_name": appt.attendee_name or "",
            "phone_number": appt.phone_number or "",
            "comments": appt.comments, "scheduled_for": appt.scheduled_for,
            "booked_at": appt.booked_at,
            "created_by": creator.username if creator else "unknown",
            "appt_type": appt.appt_type or "appointment",
            "booking_tz": appt.booking_tz or "America/Edmonton",
            "sms_status": appt.sms_status or "",
            "appt_status": appt.appt_status or "",
            "sms_sent_evening": bool(appt.sms_sent_evening),
            "sms_sent_morning": bool(appt.sms_sent_morning),
            "sms_sent_reminder": bool(appt.sms_sent_reminder)}

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
    DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
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
        DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
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
    if data.start_hour < 7 or data.end_hour > 21 or data.start_hour >= data.end_hour:
        raise HTTPException(400, "Invalid hour range. Must be within 7–21 and start < end.")
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
        "action":        sanitize_str(data.action or "", 200),
        "alp":           sanitize_str(data.alp or "", 50),
        "due_date":      sanitize_str(data.due_date or "", 10),
    }

def _quality_dict(e):
    return {"id": e.id, "insured_name": e.insured_name,
            "policy_number": e.policy_number or "", "remarks": e.remarks or "",
            "date": e.date or "", "phone_number": e.phone_number or "",
            "follow_up": e.follow_up or "", "action": e.action or "",
            "alp": e.alp or "", "due_date": e.due_date or "",
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
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
    entry = QualityEntry(owner_id=owner, created_by=user.id, created_at=now, **fields)
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
    for k, v in _sanitize_quality(data).items():
        setattr(entry, k, v)
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
    ts       = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y%m%d_%H%M%S")
    filename = f"kpi_backup_{ts}.db"
    dest     = os.path.join(backup_dir, filename)

    shutil.copy2(src, dest)
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
            }
            for r in p.referrals
        ]
    }

@app.post("/referral-programs", status_code=201)
def create_referral_program(data: ReferralProgramPayload,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    _require_admin(user)
    now = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
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
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
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
    "Meeting ID: 403-305-2652"
)
SMS_MORNING_TEMPLATE = (
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
SMS_REMINDER_TEMPLATE = "Hi {name}! Just a quick reminder about your {time}."

# Timezone abbreviation map for display in SMS
TZ_ABBREV = {
    "America/Edmonton":    "MT",
    "America/Winnipeg":    "CT",
    "America/Toronto":     "ET",
    "America/Vancouver":   "PT",
    "America/Halifax":     "AT",
    "America/St_Johns":    "NT",
}

def _fmt_appt_time_for_tz(scheduled_for_mt: str, booking_tz: str) -> tuple[str, str]:
    """
    Convert an appointment's stored MT datetime back to the booking timezone
    for display in SMS messages.

    scheduled_for_mt: "YYYY-MM-DDTHH:MM" in Mountain Time
    booking_tz: IANA timezone string e.g. "America/Vancouver"

    Returns: (time_display, date_display)
    e.g. ("12:00 PM PT", "May 22, 2026")
    """
    try:
        mt      = ZoneInfo("America/Edmonton")
        btz     = ZoneInfo(booking_tz or "America/Edmonton")
        abbrev  = TZ_ABBREV.get(booking_tz or "America/Edmonton", "MT")

        # Parse MT time and localize it
        naive_mt  = datetime.strptime(scheduled_for_mt, "%Y-%m-%dT%H:%M")
        aware_mt  = naive_mt.replace(tzinfo=mt)

        # Convert to booking timezone
        aware_btz = aware_mt.astimezone(btz)

        h    = aware_btz.hour
        m    = aware_btz.minute
        ampm = "AM" if h < 12 else "PM"
        h12  = h % 12 or 12
        time_display = f"{h12}:{m:02d} {ampm} {abbrev}"
        date_display = aware_btz.strftime("%B %-d, %Y")
        return time_display, date_display
    except Exception:
        # Fallback: just use MT
        try:
            parts = scheduled_for_mt.split("T")[1].split(":")
            h, m  = int(parts[0]), int(parts[1])
            ampm  = "AM" if h < 12 else "PM"
            h12   = h % 12 or 12
            return f"{h12}:{m:02d} {ampm} MT", scheduled_for_mt[:10]
        except Exception:
            return "your scheduled time", ""

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

@app.get("/rc/connect")
def rc_connect(token: str, db: Session = Depends(get_db)):
    """Admin clicks 'Connect RingCentral' → redirects to RC login page."""
    # Validate token manually since we can't use Header() in a redirect
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid  = payload.get("user_id")
        user = db.query(User).filter(User.id == uid).first()
        if not user or user.role != "admin":
            raise HTTPException(403, "Admin only.")
    except Exception:
        raise HTTPException(401, "Invalid token.")
    return RedirectResponse(f"{RC_AUTH_BASE}/restapi/oauth/authorize?{urllib.parse.urlencode({'response_type': 'code', 'client_id': RC_CLIENT_ID, 'redirect_uri': RC_REDIRECT_URI, 'state': str(user.id)})}")

# ── OAuth: callback ───────────────────────────────────────────────────────────

@app.get("/rc/callback")
async def rc_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    RingCentral redirects here after the user logs in and approves.
    Exchanges the code for tokens and stores them in rc_tokens table.
    Then redirects back to settings page.
    """
    user_id = int(state)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
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
    now_str = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M:%S")

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

async def send_sms(db: Session, owner_id: int, to_number: str, message: str) -> dict:
    """
    Send an SMS via RingCentral API.
    If dry_run is True, logs the message instead of sending.
    Returns {"sent": bool, "dry_run": bool, "detail": str}
    """
    token_row = _get_rc_token(db, owner_id)
    if not token_row:
        return {"sent": False, "dry_run": False, "detail": "RC not connected"}

    if token_row.dry_run:
        logger.info(f"[DRY RUN] SMS to {to_number}: {message}")
        return {"sent": False, "dry_run": True, "detail": f"[DRY RUN] Would send to {to_number}: {message}"}

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
        logger.error(f"RC SMS exception: {e}")
        return {"sent": False, "dry_run": False, "detail": str(e)}

# ── Inbound webhook — RingCentral posts here when a client replies ────────────

@app.post("/rc/webhook")
async def rc_webhook(request: Request, db: Session = Depends(get_db)):
    """
    RingCentral sends inbound SMS events here.
    If the message body is exactly 'YES' (case-insensitive),
    find the appointment matching the sender's number and mark it confirmed.
    Also handles RC's validation challenge (first-time webhook registration).
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

    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    # Navigate RC's event payload structure (body nested under "body" key)
    body_data = body.get("body", {})
    msg_type  = body_data.get("type", "")
    direction = body_data.get("direction", "")

    if msg_type != "SMS" or direction != "Inbound":
        # Fallback: try top-level structure
        msg_type  = body.get("type", "")
        direction = body.get("direction", "")
        if msg_type != "SMS" or direction != "Inbound":
            return {"status": "ignored"}
        body_data = body

    text   = (body_data.get("subject", "") or body_data.get("text", "") or "").strip().upper()
    sender = body_data.get("from", {}).get("phoneNumber", "")

    if "YES" not in text or not sender:
        return {"status": "ignored"}

    # Normalize sender number for matching (last 10 digits)
    sender_digits = re.sub(r"[^\d]", "", sender)

    # Only confirm appointments that have received the morning text
    # (that's the only message that asks them to reply YES)
    appts = db.query(Appointment).filter(
        Appointment.sms_status != "confirmed",
        Appointment.sms_sent_morning == True,
    ).all()

    matched = None
    for a in appts:
        appt_digits = re.sub(r"[^\d]", "", a.phone_number or "")
        if appt_digits and appt_digits[-10:] == sender_digits[-10:]:
            matched = a
            break

    if matched:
        matched.sms_status = "confirmed"
        db.commit()
        logger.info(f"Appointment {matched.id} ({matched.lead_name}) confirmed via YES from {sender}")
        # Send Tameema the updated daily summary
        await _send_daily_summary()
    else:
        logger.warning(f"RC webhook: no appointment matched sender {sender}")

    return {"status": "ok"}

# ── Confirmations page API — Tameema23 only ───────────────────────────────────

CONFIRMATIONS_USERNAME = "Tameema23"
TAMEEMA_PHONE = os.environ.get("TAMEEMA_SUMMARY_PHONE", "")   # daily summary destination

# ── Daily summary job ─────────────────────────────────────────────────────────

async def _send_daily_summary(target_date: Optional[str] = None):
    """
    Sends Tameema a daily SMS listing appointments for target_date.
    If target_date is None, defaults to today (used for YES confirmations).
    """
    db = SessionLocal()
    try:
        mt        = ZoneInfo("America/Edmonton")
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
                Appointment.appt_type != "callback",
            ).order_by(Appointment.scheduled_for).all()
            rows.extend(appts)

        rows.sort(key=lambda a: a.scheduled_for)

        if not rows:
            logger.info(f"Daily summary: no appointments on {date_str}, skipping.")
            return False  # nothing to send

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

            status = a.sms_status or ""
            if status == "confirmed":
                suffix = " - ✅"
            elif status == "rescheduled":
                suffix = " - rs"
            else:
                suffix = ""

            lines.append(f"{a.lead_name.split()[0]} {time_str}{suffix}")

        message = "\n".join(lines)

        token_row = db.query(RcToken).first()
        if not token_row:
            logger.warning("Daily summary: no RC token found, cannot send.")
            return False

        result = await send_sms(db, token_row.owner_user_id, TAMEEMA_PHONE, message)
        logger.info(f"Daily summary sent → {TAMEEMA_PHONE} | {result.get('detail')}")
        return True  # sent successfully

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
    Returns today's appointments for ALL admins (so Tameema23 sees Hazem's).
    Only accessible by the Tameema23 account.
    """
    if user.username.lower() != CONFIRMATIONS_USERNAME.lower():
        raise HTTPException(403, "Access denied.")

    target_date = date or datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%d")

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
                "sms_sent_evening": bool(a.sms_sent_evening),
                "sms_sent_morning": bool(a.sms_sent_morning),
                "owner":         admin.username,
            })
    result.sort(key=lambda x: x["scheduled_for"])
    return result

@app.patch("/confirmations/{appt_id}/status")
def set_confirmation_status(appt_id: int,
                             data: ReferralEntryStatusPayload,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """Tameema23 can manually set sms_status: confirmed | rescheduled | (empty)."""
    if user.username.lower() != CONFIRMATIONS_USERNAME.lower():
        raise HTTPException(403, "Access denied.")
    appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not appt:
        raise HTTPException(404, "Appointment not found.")
    if data.status not in ("confirmed", "rescheduled", ""):
        raise HTTPException(422, "Invalid status.")
    appt.sms_status = data.status
    db.commit()
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
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt:
        raise HTTPException(404, "Appointment not found.")
    valid = ("", "confirmed", "rescheduled", "no_show", "cancelled")
    if data.appt_status not in valid:
        raise HTTPException(422, "Invalid appt_status.")
    appt.appt_status = data.appt_status
    db.commit()

    # If the appointment is today, resend the summary so Tameema sees the new status
    mt = ZoneInfo("America/Edmonton")
    today_str = datetime.now(mt).strftime("%Y-%m-%d")
    if appt.scheduled_for and appt.scheduled_for.startswith(today_str):
        await _send_daily_summary(today_str)

    return {"id": appt_id, "appt_status": appt.appt_status}

# ── RC: register inbound SMS webhook ─────────────────────────────────────────

@app.post("/rc/register-webhook")
async def rc_register_webhook(user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    """
    Registers a RingCentral webhook subscription so inbound SMS replies
    are posted to /rc/webhook. Call this once after connecting RC.
    Only Tameema23 or admins can call this.
    """
    _require_admin(user)
    token_row = _get_rc_token(db, user.id)
    if not token_row:
        # Try any connected token
        token_row = db.query(RcToken).first()
    if not token_row:
        raise HTTPException(404, "RingCentral not connected.")

    ok = await _refresh_rc_token_if_needed(db, token_row)
    if not ok:
        raise HTTPException(500, "Token refresh failed.")

    webhook_url = f"{RC_REDIRECT_URI.replace('/rc/callback', '')}/rc/webhook"

    payload = {
        "eventFilters": [
            "/restapi/v1.0/account/~/extension/~/message-store/instant?type=SMS"
        ],
        "deliveryMode": {
            "transportType": "WebHook",
            "address": webhook_url,
        },
        "expiresIn": 630720000,  # max ~20 years in seconds
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{RC_AUTH_BASE}/restapi/v1.0/subscription",
            headers={
                "Authorization": f"Bearer {token_row.access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code in (200, 201):
        data = resp.json()
        logger.info(f"RC webhook registered: {data.get('id')} → {webhook_url}")
        return {
            "status": "registered",
            "webhook_url": webhook_url,
            "subscription_id": data.get("id"),
            "expires_at": data.get("expirationTime"),
        }

    logger.error(f"RC webhook registration failed {resp.status_code}: {resp.text}")
    raise HTTPException(500, f"RC error: {resp.text}")

@app.post("/rc/test-sms")
async def test_sms_trigger(user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """
    Manually fire SMS jobs and daily summary — for testing only.
    Only Tameema23 can call this.
    """
    if user.username.lower() != CONFIRMATIONS_USERNAME.lower():
        raise HTTPException(403, "Access denied.")
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
    Only Tameema23 or admins can call this.
    """
    if user.username.lower() != CONFIRMATIONS_USERNAME.lower() and user.role != "admin":
        raise HTTPException(403, "Access denied.")

    mt = ZoneInfo("America/Edmonton")
    if data.date:
        target_date = validate_date(data.date)
    else:
        # Default to tomorrow — mirrors what the 9pm scheduler sends
        target_date = (datetime.now(mt) + timedelta(days=1)).strftime("%Y-%m-%d")

    sent = await _send_daily_summary(target_date)
    return {
        "status": "sent" if sent else "no_appointments",
        "date": target_date,
        "detail": f"Summary for {target_date} {'sent to ' + TAMEEMA_PHONE if sent else 'skipped (no appointments)'}",
    }

# ── Confirmations HTML page ───────────────────────────────────────────────────

@app.get("/confirmations.html")
def confirmations_page():
    return FileResponse("frontend/confirmations.html")