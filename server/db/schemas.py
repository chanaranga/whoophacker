from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MetricsPayload(BaseModel):
    heart_rate: Optional[int] = Field(None, ge=20, le=300)
    hrv_rmssd: Optional[float] = Field(None, ge=0, le=300)
    spo2: Optional[float] = Field(None, ge=50, le=100)
    skin_temp: Optional[float] = None
    resp_rate: Optional[float] = None
    timestamp: Optional[datetime] = None   # client can supply its own timestamp


class SignalMessage(BaseModel):
    account: str
    sourceNumber: str
    sourceUuid: Optional[str] = None
    message: str
    timestamp: Optional[int] = None


class HealthSnapshot(BaseModel):
    hr_now: Optional[int] = None
    hr_24h_avg: Optional[float] = None
    hrv_now: Optional[float] = None
    hrv_7d_avg: Optional[float] = None
    spo2_now: Optional[float] = None
    last_sleep_score: Optional[int] = None
    last_sleep_duration_min: Optional[int] = None
