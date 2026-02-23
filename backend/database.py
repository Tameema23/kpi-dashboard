from sqlalchemy import create_engine, Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

SQLALCHEMY_DATABASE_URL = "sqlite:////data/kpi.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String, default="admin")  # "admin" or "assistant"

    logs = relationship("DailyLog", back_populates="user")
    appointments_created = relationship("Appointment", foreign_keys="Appointment.created_by", back_populates="created_by_user")


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    date = Column(String)
    appointments_start = Column(Integer)
    appointments_finish = Column(Integer)
    total_presentations = Column(Integer)
    total_sales = Column(Integer)
    total_alp = Column(Float)
    total_ah = Column(Float)
    referrals_collected = Column(Integer)
    referral_presentations = Column(Integer)
    referral_sales = Column(Integer)
    assigned_leads = Column(Integer, default=0)
    bad_leads = Column(Integer, default=0)

    user = relationship("User", back_populates="logs")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    created_by = Column(Integer, ForeignKey("users.id"))

    lead_name = Column(String, nullable=False)
    comments = Column(String, default="")

    # When the appointment is scheduled for (ISO string "2026-02-24T14:00")
    scheduled_for = Column(String, nullable=False)

    # When it was booked (set at creation time)
    booked_at = Column(String, nullable=False)

    created_by_user = relationship("User", back_populates="appointments_created")


def create_db():
    Base.metadata.create_all(engine)