from sqlalchemy import create_engine, Column, Integer, Float, String, Boolean, ForeignKey
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

    id       = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role     = Column(String, default="admin")
    # roles: "admin" | "assistant"
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Permission flags for assistants (ignored for admins)
    can_planner = Column(Boolean, default=True)
    can_quality = Column(Boolean, default=False)

    logs                 = relationship("DailyLog",   back_populates="user")
    appointments_created = relationship("Appointment", foreign_keys="Appointment.created_by",
                                        back_populates="created_by_user")


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    date                   = Column(String)
    appointments_start     = Column(Integer)
    appointments_finish    = Column(Integer)
    total_presentations    = Column(Integer)
    total_sales            = Column(Integer)
    total_alp              = Column(Float)
    total_ah               = Column(Float)
    referrals_collected    = Column(Integer)
    referral_presentations = Column(Integer)
    referral_sales         = Column(Integer)
    assigned_leads         = Column(Integer, default=0)
    bad_leads              = Column(Integer, default=0)

    user = relationship("User", back_populates="logs")


class Appointment(Base):
    __tablename__ = "appointments"

    id         = Column(Integer, primary_key=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    owner_id   = Column(Integer, ForeignKey("users.id"), nullable=True)

    lead_name     = Column(String, nullable=False)
    comments      = Column(String, default="")
    scheduled_for = Column(String, nullable=False)
    booked_at     = Column(String, nullable=False)
    appt_type     = Column(String, default="appointment")  # "appointment" | "callback"

    created_by_user = relationship("User", foreign_keys=[created_by],
                                   back_populates="appointments_created")


class QualityEntry(Base):
    __tablename__ = "quality_entries"

    id         = Column(Integer, primary_key=True)
    owner_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    insured_name  = Column(String, nullable=False)
    policy_number = Column(String, default="")
    remarks       = Column(String, default="")
    date          = Column(String, default="")
    phone_number  = Column(String, default="")
    follow_up     = Column(String, default="")
    action        = Column(String, default="")
    alp           = Column(String, default="")
    created_at    = Column(String, default="")


def create_db():
    Base.metadata.create_all(engine)