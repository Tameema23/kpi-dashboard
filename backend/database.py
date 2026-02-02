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

    logs = relationship("DailyLog", back_populates="user")


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

    user = relationship("User", back_populates="logs")


def create_db():
    Base.metadata.create_all(engine)
