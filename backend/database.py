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


class ReferralProgram(Base):
    """A sponsorship/referral program record — one per client visit."""
    __tablename__ = "referral_programs"

    id           = Column(Integer, primary_key=True, index=True)
    owner_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Sponsor (the person giving the referrals)
    sponsor_first      = Column(String(100), default="")
    sponsor_last       = Column(String(100), default="")
    sponsor_org        = Column(String(200), default="")
    sponsor_phone      = Column(String(30),  default="")
    sponsor_email      = Column(String(200), default="")
    sponsor_city       = Column(String(100), default="")
    sponsor_province   = Column(String(100), default="")
    sponsor_occupation = Column(String(200), default="")
    sponsor_notes      = Column(Text,        default="")
    program_date       = Column(String(10),  default="")   # YYYY-MM-DD
    total_gifted       = Column(Float,       default=0.0)

    created_at   = Column(String(16),  default="")

    referrals = relationship(
        "ReferralEntry", back_populates="program", cascade="all, delete-orphan"
    )


class ReferralEntry(Base):
    """An individual referral within a ReferralProgram."""
    __tablename__ = "referral_entries"

    id           = Column(Integer, primary_key=True, index=True)
    program_id   = Column(Integer, ForeignKey("referral_programs.id"), nullable=False, index=True)

    ref_type        = Column(String(50),  default="")
    benefit         = Column(String(200), default="")
    notes           = Column(Text,        default="")
    first_name      = Column(String(100), default="")
    last_name       = Column(String(100), default="")
    city            = Column(String(100), default="")
    province        = Column(String(50),  default="")
    phone           = Column(String(30),  default="")
    rel_to_sponsor  = Column(String(100), default="")
    occupation      = Column(String(200), default="")
    sig_other       = Column(String(200), default="")
    status          = Column(String(20),  default="")  # "met" | "pending" | "skip" | ""

    program = relationship("ReferralProgram", back_populates="referrals")


class BlockedDay(Base):
    """
    A recurring day-of-week that an admin has marked as unavailable.
    day_of_week: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat.
    Persists until the admin removes it. Applies to every week.
    Assistants see these and cannot book on these days either.
    """
    __tablename__ = "blocked_days"

    id          = Column(Integer, primary_key=True, index=True)
    owner_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0–6


class BlockedDate(Base):
    """
    A one-time specific date that an admin has marked as unavailable.
    Unlike BlockedDay (recurring), this only blocks ONE specific date.
    Use case: vacation days, holidays, personal days off.
    """
    __tablename__ = "blocked_dates"

    id       = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date     = Column(String(10), nullable=False)  # YYYY-MM-DD


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