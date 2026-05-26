from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.schemas import HealthSnapshot


async def get_latest_metric(db: AsyncSession, column: str) -> Optional[float]:
    row = await db.execute(
        text(f"SELECT {column} FROM health_metrics WHERE {column} IS NOT NULL ORDER BY time DESC LIMIT 1")
    )
    result = row.fetchone()
    return result[0] if result else None


async def get_24h_avg(db: AsyncSession, column: str) -> Optional[float]:
    row = await db.execute(
        text(
            f"SELECT AVG({column}) FROM health_metrics "
            f"WHERE {column} IS NOT NULL AND time > NOW() - INTERVAL '24 hours'"
        )
    )
    result = row.fetchone()
    return round(result[0], 1) if result and result[0] else None


async def get_7d_avg(db: AsyncSession, column: str) -> Optional[float]:
    row = await db.execute(
        text(
            f"SELECT AVG({column}) FROM health_metrics "
            f"WHERE {column} IS NOT NULL AND time > NOW() - INTERVAL '7 days'"
        )
    )
    result = row.fetchone()
    return round(result[0], 1) if result and result[0] else None


async def get_sleep_window_stats(
    db: AsyncSession, start: datetime, end: datetime
) -> dict:
    row = await db.execute(
        text(
            "SELECT AVG(heart_rate), AVG(hrv_rmssd), MIN(spo2), COUNT(*), "
            "MIN(heart_rate), MAX(heart_rate) "
            "FROM health_metrics WHERE time BETWEEN :start AND :end"
        ),
        {"start": start, "end": end},
    )
    result = row.fetchone()
    if not result or result[3] == 0:
        return {}
    return {
        "avg_hr": round(result[0], 0) if result[0] else None,
        "avg_hrv": round(result[1], 1) if result[1] else None,
        "min_spo2": round(result[2], 1) if result[2] else None,
        "sample_count": result[3],
        "min_hr": round(result[4], 0) if result[4] else None,
        "max_hr": round(result[5], 0) if result[5] else None,
    }


async def get_sleep_window_timeseries(
    db: AsyncSession, start: datetime, end: datetime, bucket_minutes: int = 5
) -> list[dict]:
    """Return HR + HRV averaged in N-minute buckets over the sleep window."""
    rows = await db.execute(
        text(
            """
            SELECT
                time_bucket(:bucket, time) AS bucket,
                ROUND(AVG(heart_rate)) AS hr,
                ROUND(AVG(hrv_rmssd)::numeric, 1) AS hrv
            FROM health_metrics
            WHERE time BETWEEN :start AND :end
              AND (heart_rate IS NOT NULL OR hrv_rmssd IS NOT NULL)
            GROUP BY bucket
            ORDER BY bucket
            """
        ),
        {"bucket": f"{bucket_minutes} minutes", "start": start, "end": end},
    )
    results = rows.fetchall()
    if not results:
        return []
    base = results[0][0]
    return [
        {
            "min": int((row[0] - base).total_seconds() / 60),
            "hr": int(row[1]) if row[1] is not None else None,
            "hrv": float(row[2]) if row[2] is not None else None,
        }
        for row in results
    ]


async def get_health_snapshot(db: AsyncSession) -> HealthSnapshot:
    hr_now = await get_latest_metric(db, "heart_rate")
    hr_24h = await get_24h_avg(db, "heart_rate")
    hrv_now = await get_latest_metric(db, "hrv_rmssd")
    hrv_7d = await get_7d_avg(db, "hrv_rmssd")
    spo2_now = await get_latest_metric(db, "spo2")

    last_sleep = await db.execute(
        text(
            "SELECT sleep_score, duration_min FROM sleep_sessions "
            "WHERE sleep_score IS NOT NULL ORDER BY start_time DESC LIMIT 1"
        )
    )
    last = last_sleep.fetchone()

    return HealthSnapshot(
        hr_now=int(hr_now) if hr_now else None,
        hr_24h_avg=hr_24h,
        hrv_now=hrv_now,
        hrv_7d_avg=hrv_7d,
        spo2_now=spo2_now,
        last_sleep_score=last[0] if last else None,
        last_sleep_duration_min=last[1] if last else None,
    )
