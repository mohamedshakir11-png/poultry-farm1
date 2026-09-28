import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# قراءة رابط قاعدة البيانات من منصة Render أو استخدام SQLite كخيار احتياطي
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./poultry_farm.db")

# تعديل الرابط إذا كان يبدأ بـ postgres:// (يتطلبه SQLAlchemy)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_kwargs = {}
if "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class BroilerBatch(Base):
    __tablename__ = "broiler_batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    initial_count = Column(Integer, default=0)
    chick_price = Column(Float, default=0.0)
    start_date = Column(DateTime, default=datetime.now)

    daily_logs = relationship("DailyLog", back_populates="batch", cascade="all, delete-orphan")
    feed_logs = relationship("DailyFeedLog", back_populates="batch", cascade="all, delete-orphan")
    vaccine_logs = relationship("VaccineLog", back_populates="batch", cascade="all, delete-orphan")
    transactions = relationship("FarmTransaction", back_populates="batch", cascade="all, delete-orphan")

class DailyLog(Base):
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("broiler_batches.id"), nullable=False)
    dead_birds = Column(Integer, default=0)
    avg_weight = Column(Float, default=0.0)
    log_date = Column(DateTime, default=datetime.now)

    batch = relationship("BroilerBatch", back_populates="daily_logs")

class DailyFeedLog(Base):
    __tablename__ = "daily_feed_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("broiler_batches.id"), nullable=False)
    feed_type = Column(String, default="بادي")
    bags_consumed = Column(Float, default=0.0)
    bag_price = Column(Float, default=0.0)
    log_date = Column(DateTime, default=datetime.now)

    batch = relationship("BroilerBatch", back_populates="feed_logs")

class VaccineLog(Base):
    __tablename__ = "vaccine_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("broiler_batches.id"), nullable=False)
    vaccine_name = Column(String, nullable=False)
    cost = Column(Float, default=0.0)
    log_date = Column(DateTime, default=datetime.now)

    batch = relationship("BroilerBatch", back_populates="vaccine_logs")

class FarmTransaction(Base):
    __tablename__ = "farm_transactions"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("broiler_batches.id"), nullable=False)
    amount = Column(Float, default=0.0)
    description = Column(String, nullable=True)
    tx_date = Column(DateTime, default=datetime.now)

    batch = relationship("BroilerBatch", back_populates="transactions")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
