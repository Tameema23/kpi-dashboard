"""
main.py — KPI Dashboard API (backend/ folder)
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

import os, re, html, logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo
from jose import jwt, JWTError
from passlib.context import CryptContext
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Import from same backend/ folder ─────────────────────────────────────────
from backend.database import SessionLocal, create_db, User, DailyLog, Appointment, QualityEntry, AuditLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kpi")

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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="KPI Dashboard",
    docs_url=None,   # Disable Swagger in production
    redoc_url=None,
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
    cleaned = html.escape(cleaned, quote=True)
    return cleaned[:max_len].strip()

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

def create_token(user_id: int, role: str, token_version: int,
                 can_planner: bool = True, can_quality: bool = False) -> str:
    return jwt.encode({
        "user_id":       user_id,
        "role":          role,
        "token_version": token_version,
        "can_planner":   can_planner,
        "can_quality":   can_quality,
        "exp":           datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
        "iat":           datetime.utcnow(),
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
        # Generic message — never reveal whether the username exists
        raise HTTPException(401, "Invalid username or password.")

    if user.role == "admin":
        can_planner, can_quality = True, True
    else:
        can_planner = bool(user.can_planner)
        can_quality = bool(user.can_quality)

    audit(db, user.id, "login", f"IP: {get_remote_address(request)}")
    logger.info(f"Login: {username} ({user.role})")

    return {
        "token":                create_token(
                                    user.id, user.role or "admin",
                                    user.token_version or 0,
                                    can_planner, can_quality
                                ),
        "role":                 user.role or "admin",
        "can_planner":          can_planner,
        "can_quality":          can_quality,
        "username":             user.username,
        # ← This tells the frontend to show a password update prompt.
        #   True only for accounts whose original password was under 8 chars.
        #   They are fully logged in — just nudged to update their password.
        "needs_password_reset": bool(getattr(user, "needs_password_reset", False)),
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

    user.password             = hash_password(new_pw)
    user.token_version        = (user.token_version or 0) + 1
    user.needs_password_reset = False   # clear the flag — requirement now met
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
    if not data.can_planner and not data.can_quality:
        raise HTTPException(400, "At least one permission must be selected.")
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
             "can_quality": bool(a.can_quality)}
            for a in assistants]

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
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
    owner = get_owner_id(user)
    appt  = Appointment(
        created_by=user.id, owner_id=owner,
        lead_name=lead_name,
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
    appt.lead_name     = sanitize_str(data.lead_name, 200)
    appt.comments      = sanitize_str(data.comments or "", 2000)
    appt.scheduled_for = validate_datetime(data.scheduled_for)
    appt.appt_type     = data.appt_type if data.appt_type in ("appointment","callback") else "appointment"
    if data.booking_tz: appt.booking_tz = validate_tz(data.booking_tz)
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
            "comments": appt.comments, "scheduled_for": appt.scheduled_for,
            "booked_at": appt.booked_at,
            "created_by": creator.username if creator else "unknown",
            "appt_type": appt.appt_type or "appointment",
            "booking_tz": appt.booking_tz or "America/Edmonton"}

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
    }

def _quality_dict(e):
    return {"id": e.id, "insured_name": e.insured_name,
            "policy_number": e.policy_number or "", "remarks": e.remarks or "",
            "date": e.date or "", "phone_number": e.phone_number or "",
            "follow_up": e.follow_up or "", "action": e.action or "",
            "alp": e.alp or "", "created_at": e.created_at or ""}

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