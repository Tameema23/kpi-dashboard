from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from jose import jwt
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import SessionLocal, create_db, User, DailyLog, Appointment, QualityEntry

SECRET_KEY = "supersecretkey"
app = FastAPI()

# ── Serve frontend ────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")           
def serve_home():   return FileResponse("frontend/login.html")
@app.get("/index.html") 
def dashboard():    return FileResponse("frontend/index.html")
@app.get("/log.html")   
def log_page():     return FileResponse("frontend/log.html")
@app.get("/reports.html")
def reports_page(): return FileResponse("frontend/reports.html")
@app.get("/history.html")
def history_page(): return FileResponse("frontend/history.html")
@app.get("/settings.html")
def settings_page():return FileResponse("frontend/settings.html")
@app.get("/planner.html")
def planner_page(): return FileResponse("frontend/planner.html")
@app.get("/quality.html")
def quality_page(): return FileResponse("frontend/quality.html")

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

create_db()

# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:    yield db
    finally: db.close()

# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_owner_id(user: User) -> int:
    """Admin → own id. Assistant (any type) → owner_id (the admin who made them)."""
    if user.role in ("assistant", "quality_assistant"):
        return user.owner_id
    return user.id


def create_token(user_id: int, role: str):
    return jwt.encode(
        {"user_id": user_id, "role": role,
         "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)):
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        if not user: raise HTTPException(401)
        return user
    except:
        raise HTTPException(401)

# ── Auth endpoints ────────────────────────────────────────────────────────────

class UserPayload(BaseModel):
    username: str
    password: str

@app.post("/create-user")
def create_user(data: UserPayload, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "User exists")
    db.add(User(username=data.username, password=data.password, role="admin", owner_id=None))
    db.commit()
    return {"status": "created"}

@app.post("/login")
def login(data: UserPayload, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == data.username, User.password == data.password
    ).first()
    if not user: raise HTTPException(401)
    return {
        "token": create_token(user.id, user.role or "admin"),
        "role":  user.role or "admin",
        "username": user.username
    }

# ── Assistant management (admin only) ─────────────────────────────────────────

class AssistantPayload(BaseModel):
    username: str
    password: str
    assistant_type: str = "assistant"   # "assistant" | "quality_assistant"

@app.post("/create-assistant")
def create_assistant(data: AssistantPayload,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if (user.role or "admin") != "admin":
        raise HTTPException(403, "Admin only")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Username already exists")

    role = data.assistant_type if data.assistant_type in ("assistant", "quality_assistant") else "assistant"
    db.add(User(username=data.username, password=data.password,
                role=role, owner_id=user.id))
    db.commit()
    return {"status": "created"}

@app.get("/assistants")
def list_assistants(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (user.role or "admin") != "admin":
        raise HTTPException(403, "Admin only")
    assistants = db.query(User).filter(
        User.role.in_(["assistant", "quality_assistant"]),
        User.owner_id == user.id
    ).all()
    return [{"id": a.id, "username": a.username, "role": a.role} for a in assistants]

@app.delete("/assistants/{assistant_id}")
def delete_assistant(assistant_id: int,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if (user.role or "admin") != "admin":
        raise HTTPException(403, "Admin only")
    assistant = db.query(User).filter(
        User.id == assistant_id,
        User.role.in_(["assistant", "quality_assistant"]),
        User.owner_id == user.id
    ).first()
    if not assistant: raise HTTPException(404, "Assistant not found")
    db.delete(assistant)
    db.commit()
    return {"status": "deleted"}

# ── Daily logging ─────────────────────────────────────────────────────────────

class LogPayload(BaseModel):
    date: str
    appointments_start: int
    appointments_finish: int
    total_presentations: int
    total_sales: int
    total_alp: float
    total_ah: float
    referrals_collected: int
    referral_presentations: int
    referral_sales: int
    assigned_leads: int = 0
    bad_leads: int = 0

@app.post("/log-day")
def log_day(data: LogPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(DailyLog).filter(
        DailyLog.user_id == user.id, DailyLog.date == data.date
    ).first()
    if existing:
        for k, v in data.dict().items(): setattr(existing, k, v)
        db.commit()
        return {"status": "updated"}
    db.add(DailyLog(user_id=user.id, **data.dict()))
    db.commit()
    return {"status": "saved"}

@app.get("/history")
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(DailyLog).filter(DailyLog.user_id == user.id).all()
    return [
        {"id": l.id, "date": l.date,
         "appointments_start": l.appointments_start, "appointments_finish": l.appointments_finish,
         "total_presentations": l.total_presentations, "total_sales": l.total_sales,
         "total_alp": l.total_alp, "total_ah": l.total_ah,
         "referrals_collected": l.referrals_collected, "referral_presentations": l.referral_presentations,
         "referral_sales": l.referral_sales,
         "assigned_leads": l.assigned_leads or 0, "bad_leads": l.bad_leads or 0}
        for l in logs
    ]

# ── Change password ───────────────────────────────────────────────────────────

class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str

@app.post("/change-password")
def change_password(data: ChangePasswordPayload,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if user.password != data.current_password:
        raise HTTPException(400, "Current password is incorrect")
    if len(data.new_password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    user.password = data.new_password
    db.commit()
    return {"status": "password updated"}

# ── Bulk delete ───────────────────────────────────────────────────────────────

@app.delete("/delete-days")
def delete_days(ids: list[int], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(DailyLog).filter(
        DailyLog.user_id == user.id, DailyLog.id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "deleted"}

# ── Appointments (Planner) ────────────────────────────────────────────────────

class AppointmentPayload(BaseModel):
    lead_name: str
    comments: Optional[str] = ""
    scheduled_for: str

class AppointmentUpdatePayload(BaseModel):
    lead_name: str
    comments: Optional[str] = ""
    scheduled_for: str

@app.post("/appointments")
def create_appointment(data: AppointmentPayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
    owner = get_owner_id(user)
    appt  = Appointment(created_by=user.id, owner_id=owner,
                        lead_name=data.lead_name, comments=data.comments or "",
                        scheduled_for=data.scheduled_for, booked_at=now)
    db.add(appt); db.commit(); db.refresh(appt)
    return _appt_dict(appt, db)

@app.get("/appointments")
def get_appointments(week_start: Optional[str] = None,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    owner = get_owner_id(user)
    appts = db.query(Appointment).filter(Appointment.owner_id == owner).all()
    return [_appt_dict(a, db) for a in appts]

@app.put("/appointments/{appt_id}")
def update_appointment(appt_id: int, data: AppointmentUpdatePayload,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt: raise HTTPException(404, "Appointment not found")
    appt.lead_name = data.lead_name
    appt.comments  = data.comments or ""
    appt.scheduled_for = data.scheduled_for
    db.commit()
    return _appt_dict(appt, db)

@app.delete("/appointments/{appt_id}")
def delete_appointment(appt_id: int,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    owner = get_owner_id(user)
    appt  = db.query(Appointment).filter(
        Appointment.id == appt_id, Appointment.owner_id == owner
    ).first()
    if not appt: raise HTTPException(404, "Appointment not found")
    db.delete(appt); db.commit()
    return {"status": "deleted"}

def _appt_dict(appt, db):
    creator = db.query(User).filter(User.id == appt.created_by).first()
    return {"id": appt.id, "lead_name": appt.lead_name, "comments": appt.comments,
            "scheduled_for": appt.scheduled_for, "booked_at": appt.booked_at,
            "created_by": creator.username if creator else "unknown"}

# ── Quality Tracker ───────────────────────────────────────────────────────────

class QualityPayload(BaseModel):
    insured_name:  str
    policy_number: Optional[str] = ""
    remarks:       Optional[str] = ""
    date:          Optional[str] = ""
    phone_number:  Optional[str] = ""
    follow_up:     Optional[str] = ""
    action:        Optional[str] = ""
    alp:           Optional[str] = ""

def _quality_dict(e):
    return {"id": e.id, "insured_name": e.insured_name,
            "policy_number": e.policy_number or "", "remarks": e.remarks or "",
            "date": e.date or "", "phone_number": e.phone_number or "",
            "follow_up": e.follow_up or "", "action": e.action or "",
            "alp": e.alp or "", "created_at": e.created_at or ""}

@app.post("/quality")
def create_quality(data: QualityPayload,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role not in ("admin", "quality_assistant"):
        raise HTTPException(403, "Not authorized")
    owner = get_owner_id(user)
    now   = datetime.now(ZoneInfo("America/Edmonton")).strftime("%Y-%m-%dT%H:%M")
    entry = QualityEntry(owner_id=owner, created_by=user.id,
                         insured_name=data.insured_name,
                         policy_number=data.policy_number or "",
                         remarks=data.remarks or "",
                         date=data.date or "",
                         phone_number=data.phone_number or "",
                         follow_up=data.follow_up or "",
                         action=data.action or "",
                         alp=data.alp or "",
                         created_at=now)
    db.add(entry); db.commit(); db.refresh(entry)
    return _quality_dict(entry)

@app.get("/quality")
def get_quality(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("admin", "quality_assistant"):
        raise HTTPException(403, "Not authorized")
    owner   = get_owner_id(user)
    entries = db.query(QualityEntry).filter(
        QualityEntry.owner_id == owner
    ).order_by(QualityEntry.id.desc()).all()
    return [_quality_dict(e) for e in entries]

@app.put("/quality/{entry_id}")
def update_quality(entry_id: int, data: QualityPayload,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role not in ("admin", "quality_assistant"):
        raise HTTPException(403, "Not authorized")
    owner = get_owner_id(user)
    entry = db.query(QualityEntry).filter(
        QualityEntry.id == entry_id, QualityEntry.owner_id == owner
    ).first()
    if not entry: raise HTTPException(404, "Entry not found")
    entry.insured_name  = data.insured_name
    entry.policy_number = data.policy_number or ""
    entry.remarks       = data.remarks or ""
    entry.date          = data.date or ""
    entry.phone_number  = data.phone_number or ""
    entry.follow_up     = data.follow_up or ""
    entry.action        = data.action or ""
    entry.alp           = data.alp or ""
    db.commit()
    return _quality_dict(entry)

@app.delete("/quality/{entry_id}")
def delete_quality(entry_id: int,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role not in ("admin", "quality_assistant"):
        raise HTTPException(403, "Not authorized")
    owner = get_owner_id(user)
    entry = db.query(QualityEntry).filter(
        QualityEntry.id == entry_id, QualityEntry.owner_id == owner
    ).first()
    if not entry: raise HTTPException(404, "Entry not found")
    db.delete(entry); db.commit()
    return {"status": "deleted"}