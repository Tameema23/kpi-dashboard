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
    role = Column(String, default="admin")       # "admin" or "assistant"
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for admins, set for assistants

    logs = relationship("DailyLog", back_populates="user")
    appointments_created = relationship("Appointment", back_populates="created_by_user")
    # Assistants owned by this admin
    assistants = relationship("User", foreign_keys="User.owner_id", backref="owner")


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
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # The admin who owns this appointment pool

    lead_name = Column(String, nullable=False)
    comments = Column(String, default="")

    scheduled_for = Column(String, nullable=False)
    booked_at = Column(String, nullable=False)

    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="appointments_created")
    owner = relationship("User", foreign_keys=[owner_id])


def create_db():
    Base.metadata.create_all(engine)