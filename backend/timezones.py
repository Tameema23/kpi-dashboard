"""
timezones.py — every time zone rule in ApexTrack lives here.

How time works in this app
  • The business calendar runs in BUSINESS_TZ (America/Edmonton by default).
    Every stored time ("YYYY-MM-DDTHH:MM") is a wall-clock time in that zone.
    The planner grid, blocked hours and booking rules all read it as-is.
  • A client can be in another zone. That zone is saved on the appointment
    (booking_tz) and used only to show or text the client their local time.
  • No offset is ever written in code. Every conversion goes through the IANA
    time zone database, so DST starts, DST ends and permanent changes are
    handled by data, not by code. Fall 2026 is a good example: Alberta, B.C.
    and Manitoba stop changing clocks while Ontario, Quebec and the Atlantic
    provinces still fall back. Nothing in the code knows that. The data does.
  • The IANA data comes from the pinned `tzdata` Python package, never from
    the server's operating system. An out-of-date OS copy would put every
    converted time an hour off after a rule change. When a province changes
    its rules again, bump `tzdata` in requirements.txt and redeploy.
  • Elapsed time ("is it 60 minutes until the appointment?") is measured in
    UTC. Subtracting two aware datetimes in the same zone in Python compares
    wall clocks and ignores the offset, which is wrong across a clock change.

This module must be imported before any ZoneInfo object is created, which is
why main.py imports it first.
"""

import os
import logging
import zoneinfo
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

logger = logging.getLogger("kpi")


# ── Use the bundled IANA data, not the OS copy ───────────────────────────────

def _use_bundled_tzdata() -> str:
    try:
        import tzdata  # noqa: F401  (the package only needs to be present)
    except ImportError:
        logger.warning(
            "tzdata package not installed. Falling back to the server's own "
            "time zone files, which may be out of date. Add tzdata to "
            "requirements.txt."
        )
        return "system"
    # An empty search path makes zoneinfo read straight from the tzdata
    # package. Clear the cache in case anything built a zone first.
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()
    return getattr(tzdata, "IANA_VERSION", "unknown")


TZDATA_VERSION = _use_bundled_tzdata()

ZoneInfo = zoneinfo.ZoneInfo
UTC      = timezone.utc
STAMP    = "%Y-%m-%dT%H:%M"


# ── Zones the app offers ─────────────────────────────────────────────────────
# One row per zone: IANA id, dropdown label, short label used in texts and on
# screen. To offer another zone, add a row here. Nothing else needs to change:
# the server, the planner dropdown and the agent booking page all read this.
TIMEZONES = [
    ("America/Vancouver", "Pacific (British Columbia)",     "PT"),
    ("America/Edmonton",  "Mountain (Alberta)",             "MT"),
    ("America/Regina",    "Saskatchewan",                   "CST"),
    ("America/Winnipeg",  "Central (Manitoba)",             "CT"),
    ("America/Toronto",   "Eastern (Ontario / Quebec)",     "ET"),
    ("America/Halifax",   "Atlantic (NS / NB / PEI)",       "AT"),
    ("America/St_Johns",  "Newfoundland",                   "NT"),
]

_LABELS = {tz: label for tz, label, _ in TIMEZONES}
_ABBREV = {tz: abbr  for tz, _, abbr in TIMEZONES}
ALLOWED_TIMEZONES = set(_LABELS)


def _business_tz_name() -> str:
    """BUSINESS_TZ from the environment, if it is a zone the app offers.
    Changing it reinterprets every stored time, so it is a deliberate,
    one-time setting, not something to flip."""
    name = os.environ.get("BUSINESS_TZ", "America/Edmonton").strip()
    if name not in ALLOWED_TIMEZONES:
        logger.warning(f"BUSINESS_TZ={name!r} is not in TIMEZONES; using America/Edmonton.")
        name = "America/Edmonton"
    return name


BUSINESS_TZ_NAME = _business_tz_name()
BUSINESS_TZ      = ZoneInfo(BUSINESS_TZ_NAME)




# ── Lookups ──────────────────────────────────────────────────────────────────

def validate_tz(tz: Optional[str]) -> str:
    """The zone if the app offers it, otherwise the business zone."""
    return tz if tz in ALLOWED_TIMEZONES else BUSINESS_TZ_NAME


def tz_abbrev(tz: Optional[str]) -> str:
    return _ABBREV.get(validate_tz(tz), "")


def tz_label(tz: Optional[str]) -> str:
    return _LABELS.get(validate_tz(tz), "")


def timezone_options() -> list:
    """Dropdown data for the front end, west to east."""
    return [{"id": tz, "label": label, "abbrev": abbr, "default": tz == BUSINESS_TZ_NAME}
            for tz, label, abbr in TIMEZONES]


# ── Now ──────────────────────────────────────────────────────────────────────

def business_now() -> datetime:
    """Current time as an aware datetime in the business zone."""
    return datetime.now(BUSINESS_TZ)


def business_now_str(fmt: str = STAMP) -> str:
    return business_now().strftime(fmt)


def utc_offset_minutes(tz: Optional[str] = None, at: Optional[datetime] = None) -> int:
    """UTC offset of a zone at a moment (default: now), in minutes."""
    zone = ZoneInfo(validate_tz(tz or BUSINESS_TZ_NAME))
    moment = (at or datetime.now(UTC)).astimezone(zone)
    return int(moment.utcoffset().total_seconds() // 60)


# ── Parsing and conversion ───────────────────────────────────────────────────

def parse_business(stamp: str) -> datetime:
    """'YYYY-MM-DDTHH:MM' business wall clock → aware datetime."""
    return datetime.strptime(stamp[:16], STAMP).replace(tzinfo=BUSINESS_TZ)


def convert_wall(stamp: str, from_tz: Optional[str], to_tz: Optional[str]) -> str:
    """
    Re-express a wall-clock stamp from one zone in another, for that exact
    date. The offset is looked up for the date itself, so a week that crosses
    a clock change converts each day correctly.
    """
    src = ZoneInfo(validate_tz(from_tz))
    dst = ZoneInfo(validate_tz(to_tz))
    naive = datetime.strptime(stamp[:16], STAMP)
    return naive.replace(tzinfo=src).astimezone(dst).strftime(STAMP)


def to_business(stamp: str, from_tz: Optional[str]) -> str:
    """Client wall clock → business wall clock (what gets stored)."""
    return convert_wall(stamp, from_tz, BUSINESS_TZ_NAME)


def from_business(stamp: str, to_tz: Optional[str]) -> str:
    """Business wall clock (stored) → client wall clock."""
    return convert_wall(stamp, BUSINESS_TZ_NAME, to_tz)


# ── Elapsed time, always in UTC ──────────────────────────────────────────────

def minutes_between(start: datetime, end: datetime) -> float:
    """Real minutes from start to end, correct across any clock change."""
    return (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() / 60


def add_real_time(moment: datetime, delta: timedelta) -> datetime:
    """moment + delta of real elapsed time, returned in moment's zone."""
    return (moment.astimezone(UTC) + delta).astimezone(moment.tzinfo)


# ── Display ──────────────────────────────────────────────────────────────────

def _fmt_time(dt: datetime) -> str:
    h12 = dt.hour % 12 or 12
    return f"{h12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_hhmm(stamp: str) -> str:
    """'2026-11-02T14:30' → '2:30 PM'."""
    return _fmt_time(datetime.strptime(stamp[:16], STAMP))


def fmt_for_tz(business_stamp: str, tz: Optional[str]) -> Tuple[str, str]:
    """
    Stored business time → (time with zone, long date) in the client's zone.
    ('2:00 PM ET', 'November 2, 2026'). Used by every client text.
    """
    try:
        local = datetime.strptime(from_business(business_stamp, tz), STAMP)
        abbr  = tz_abbrev(tz)
        return (f"{_fmt_time(local)} {abbr}".strip(),
                f"{local.strftime('%B')} {local.day}, {local.year}")
    except Exception:
        return business_stamp, ""


def client_time_summary(business_stamp: str, tz: Optional[str]) -> str:
    """Short client-side summary for the planner: 'Mon, Nov 2, 2:00 PM ET'.
    Empty when the client is in the business zone (nothing to add)."""
    tz = validate_tz(tz)
    if tz == BUSINESS_TZ_NAME or not business_stamp:
        return ""
    try:
        local = datetime.strptime(from_business(business_stamp, tz), STAMP)
        return f"{local.strftime('%a, %b')} {local.day}, {_fmt_time(local)} {tz_abbrev(tz)}"
    except Exception:
        return ""
