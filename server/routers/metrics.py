from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, text

from config import settings
from db.session import get_db
from db.models import HealthMetric
from db.schemas import MetricsPayload

router = APIRouter(prefix="/api", tags=["metrics"])


def verify_secret(x_server_secret: Annotated[str | None, Header()] = None):
    if x_server_secret != settings.server_secret:
        raise HTTPException(status_code=401, detail="Invalid secret")


@router.post("/metrics", status_code=201, dependencies=[Depends(verify_secret)])
async def ingest_metrics(payload: MetricsPayload, db: AsyncSession = Depends(get_db)):
    row = {
        "time": payload.timestamp or datetime.now(timezone.utc),
        "heart_rate": payload.heart_rate,
        "hrv_rmssd": payload.hrv_rmssd,
        "spo2": payload.spo2,
        "skin_temp": payload.skin_temp,
        "resp_rate": payload.resp_rate,
    }
    await db.execute(insert(HealthMetric).values(**row))
    await db.commit()
    return {"status": "ok"}


@router.get("/metrics")
async def get_metrics(
    limit: int = Query(default=20, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT * FROM health_metrics ORDER BY time DESC LIMIT :limit"),
        {"limit": limit},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]
