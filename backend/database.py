"""
database.py — KPI Dashboard ORM models (backend/ folder)
Security additions:
  ✓ token_version — bumped on password change, invalidates old JWTs
  ✓ needs_password_reset — True for accounts with passwords under 8 chars
    These users are NOT locked out. They log in normally and see a prompt.
  ✓ AuditLog table — records logins, password changes, deletes
"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, Float,
    String, Boolean, ForeignKey, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/kpi.db")

# Railway/Render Postgres URLs start with postgres:// — fix for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine       = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


class User(Base):
    __tablename__ = "users"

    id                   = Column(Integer, primary_key=True, index=True)
    username             = Column(String(30),  unique=True, nullable=False, index=True)
    password             = Column(String(200), nullable=False)   # bcrypt hash
    role                 = Column(String(20),  default="admin")  # "admin" | "assistant"
    owner_id             = Column(Integer, ForeignKey("users.id"), nullable=True)
    can_planner          = Column(Boolean, default=True)
    can_quality          = Column(Boolean, default=False)

    # Bumped every time password changes.
    # Any JWT with an older token_version is immediately rejected.
    token_version        = Column(Integer, default=0, nullable=False)

    # True if the account's original password was under 8 characters.
    # User can still log in — they just see a prompt to update it.
    needs_password_reset = Column(Boolean, default=False, nullable=False)

    logs = relationship(
        "DailyLog", back_populates="user", cascade="all, delete-orphan"
    )
    appointments_created = relationship(
        "Appointment", foreign_keys="Appointment.created_by",
        back_populates="created_by_user"
    )


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id                     = Column(Integer, primary_key=True, index=True)
    user_id                = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date                   = Column(String(10),  nullable=False)  # YYYY-MM-DD
    appointments_start     = Column(Integer, default=0)
    appointments_finish    = Column(Integer, default=0)
    total_presentations    = Column(Integer, default=0)
    total_sales            = Column(Integer, default=0)
    total_alp              = Column(Float,   default=0.0)
    total_ah               = Column(Float,   default=0.0)
    referrals_collected    = Column(Integer, default=0)
    referral_presentations = Column(Integer, default=0)
    referral_sales         = Column(Integer, default=0)
    assigned_leads         = Column(Integer, default=0)
    bad_leads              = Column(Integer, default=0)

    user = relationship("User", back_populates="logs")


class Appointment(Base):
    __tablename__ = "appointments"

    id            = Column(Integer, primary_key=True, index=True)
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    lead_name     = Column(String(200), nullable=False)
    comments      = Column(Text,        default="")
    scheduled_for = Column(String(16),  nullable=False)  # YYYY-MM-DDTHH:MM
    booked_at     = Column(String(16),  nullable=False)
    appt_type     = Column(String(20),  default="appointment")
    booking_tz    = Column(String(50),  default="America/Edmonton")

    created_by_user = relationship(
        "User", foreign_keys=[created_by],
        back_populates="appointments_created"
    )


class QualityEntry(Base):
    __tablename__ = "quality_entries"

    id            = Column(Integer, primary_key=True, index=True)
    owner_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=False)
    insured_name  = Column(String(200), nullable=False)
    policy_number = Column(String(100), default="")
    remarks       = Column(Text,        default="")
    date          = Column(String(20),  default="")
    phone_number  = Column(String(30),  default="")
    follow_up     = Column(String(100), default="")
    action        = Column(String(200), default="")
    alp           = Column(String(50),  default="")
    created_at    = Column(String(16),  default="")


class AuditLog(Base):
    """Tracks sensitive actions: logins, password changes, deletes."""
    __tablename__ = "audit_logs"

    id        = Column(Integer, primary_key=True, index=True)
    user_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action    = Column(String(100), nullable=False)
    detail    = Column(String(500), default="")
    timestamp = Column(String(20),  nullable=False)  # YYYY-MM-DDTHH:MM:SS


def create_db():
    """
    Creates all missing tables on startup.
    Safe to call every time — never drops existing tables or data.

    If you add new columns to existing models after first deploy,
    run migrate_passwords.py which handles ALTER TABLE for SQLite.
    """
    Base.metadata.create_all(engine)