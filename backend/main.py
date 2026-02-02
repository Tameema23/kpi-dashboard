from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import SessionLocal, create_db, User, DailyLog

SECRET_KEY = "supersecretkey"

app = FastAPI()

# ---------------- SERVE FRONTEND SAFELY ---------------- #

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_home():
    return FileResponse("frontend/login.html")

# ------------------------------------------------------ #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

create_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- AUTH ---------------- #

class UserPayload(BaseModel):
    username: str
    password: str

def create_token(user_id: int):
    return jwt.encode(
        {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY,
        algorithm="HS256"
    )

def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        if not user:
            raise HTTPException(401)
        return user
    except:
        raise HTTPException(401)

@app.post("/create-user")
def create_user(data: UserPayload, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "User exists")

    user = User(
        username=data.username,
        password=data.password
    )
    db.add(user)
    db.commit()
    return {"status": "created"}

@app.post("/login")
def login(data: UserPayload, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == data.username,
        User.password == data.password
    ).first()

    if not user:
        raise HTTPException(401)

    return {"token": create_token(user.id)}

# ---------------- LOGGING ---------------- #

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

@app.post("/log-day")
def log_day(
    data: LogPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = DailyLog(
        user_id=user.id,
        **data.dict()
    )

    db.add(entry)
    db.commit()
    return {"status": "saved"}

@app.get("/history")
def history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(DailyLog).filter(DailyLog.user_id == user.id).all()

    return [
        {
            "id": l.id,
            "date": l.date,
            "appointments_start": l.appointments_start,
            "appointments_finish": l.appointments_finish,
            "total_presentations": l.total_presentations,
            "total_sales": l.total_sales,
            "total_alp": l.total_alp,
            "total_ah": l.total_ah,
            "referrals_collected": l.referrals_collected,
            "referral_presentations": l.referral_presentations,
            "referral_sales": l.referral_sales
        }
        for l in logs
    ]

@app.get("/index.html")
def dashboard():
    return FileResponse("frontend/index.html")

@app.get("/log.html")
def log_page():
    return FileResponse("frontend/log.html")

@app.get("/reports.html")
def reports_page():
    return FileResponse("frontend/reports.html")

@app.get("/history.html")
def history_page():
    return FileResponse("frontend/history.html")

@app.delete("/delete-day/{date}")
def delete_day(
    date: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = db.query(DailyLog).filter(
        DailyLog.user_id == user.id,
        DailyLog.date == date
    ).first()

    if not entry:
        raise HTTPException(404, "Entry not found")

    db.delete(entry)
    db.commit()

    return {"status": "deleted"}
