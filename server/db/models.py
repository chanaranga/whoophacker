from datetime import datetime
from sqlalchemy import Column, Integer, Float, Text, TIMESTAMP, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_type = Column(Text, nullable=False)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    end_time = Column(TIMESTAMP(timezone=True))
    duration_min = Column(Integer)
    avg_hr = Column(Integer)
    max_hr = Column(Integer)
    avg_hrv = Column(Float)
    effort_score = Column(Integer)
    recovery_cost = Column(Integer)
    analysis_text = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())


class HealthMetric(Base):
    __tablename__ = "health_metrics"

    time = Column(TIMESTAMP(timezone=True), primary_key=True, default=func.now())
    heart_rate = Column(Integer)
    hrv_rmssd = Column(Float)
    spo2 = Column(Float)
    skin_temp = Column(Float)
    resp_rate = Column(Float)


class SleepSession(Base):
    __tablename__ = "sleep_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    end_time = Column(TIMESTAMP(timezone=True))
    duration_min = Column(Integer)
    avg_hrv = Column(Float)
    avg_hr = Column(Integer)
    min_spo2 = Column(Float)
    sleep_score = Column(Integer)
    analysis_text = Column(Text)
    stage_breakdown = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
