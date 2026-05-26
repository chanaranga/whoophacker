from datetime import datetime, timezone, timedelta
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


async def has_recent_sleep_session(db: AsyncSession) -> bool:
    """True if a completed or open sleep session already exists in the last 18 hours."""
    row = await db.execute(
        text(
            "SELECT id FROM sleep_sessions "
            "WHERE start_time > NOW() - INTERVAL '18 hours' "
            "ORDER BY start_time DESC LIMIT 1"
        )
    )
    return row.fetchone() is not None


async def get_overnight_data(
    db: AsyncSession, start: datetime, end: datetime, bucket_minutes: int = 5
) -> list[dict]:
    """5-minute bucketed HR + HRV with actual bucket timestamps for sleep inference."""
    rows = await db.execute(
        text(
            """
            SELECT
                time_bucket(:bucket, time) AS bucket,
                ROUND(AVG(heart_rate)) AS hr,
                ROUND(AVG(hrv_rmssd)::numeric, 1) AS hrv
            FROM health_metrics
            WHERE time BETWEEN :start AND :end
              AND heart_rate IS NOT NULL
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
            "time": row[0],
            "min": int((row[0] - base).total_seconds() / 60),
            "hr": int(row[1]) if row[1] is not None else None,
            "hrv": float(row[2]) if row[2] is not None else None,
        }
        for row in results
    ]


async def get_workout_window_stats(
    db: AsyncSession, start: datetime, end: datetime
) -> dict:
    row = await db.execute(
        text(
            "SELECT AVG(heart_rate), MAX(heart_rate), AVG(hrv_rmssd), COUNT(*) "
            "FROM health_metrics WHERE time BETWEEN :start AND :end"
        ),
        {"start": start, "end": end},
    )
    result = row.fetchone()
    if not result or result[3] == 0:
        return {}
    return {
        "avg_hr": round(result[0], 0) if result[0] else None,
        "max_hr": round(result[1], 0) if result[1] else None,
        "avg_hrv": round(result[2], 1) if result[2] else None,
        "sample_count": result[3],
    }


async def get_recovery_inputs(db: AsyncSession) -> dict:
    """Gather all inputs needed to compute a recovery score."""
    # Last sleep session
    sleep_row = await db.execute(
        text(
            "SELECT sleep_score, avg_hrv, duration_min FROM sleep_sessions "
            "WHERE end_time IS NOT NULL ORDER BY start_time DESC LIMIT 1"
        )
    )
    last_sleep = sleep_row.fetchone()

    # Current HRV and trend
    hrv_now = await get_latest_metric(db, "hrv_rmssd")
    hrv_7d = await get_7d_avg(db, "hrv_rmssd")
    hr_now = await get_latest_metric(db, "heart_rate")
    hr_7d = await get_7d_avg(db, "heart_rate")

    # Cumulative workout recovery cost from last 48h
    workout_row = await db.execute(
        text(
            "SELECT COALESCE(SUM(recovery_cost), 0), COUNT(*) "
            "FROM workout_sessions "
            "WHERE end_time IS NOT NULL AND start_time > NOW() - INTERVAL '48 hours'"
        )
    )
    workout_load = workout_row.fetchone()

    return {
        "last_sleep_score": last_sleep[0] if last_sleep else None,
        "last_sleep_hrv": last_sleep[1] if last_sleep else None,
        "last_sleep_duration_min": last_sleep[2] if last_sleep else None,
        "hrv_now": hrv_now,
        "hrv_7d_avg": hrv_7d,
        "hr_now": int(hr_now) if hr_now else None,
        "hr_7d_avg": hr_7d,
        "workout_load_48h": int(workout_load[0]) if workout_load else 0,
        "workouts_48h": int(workout_load[1]) if workout_load else 0,
    }


async def get_pattern_data(db: AsyncSession) -> dict:
    """Aggregated data for pattern analysis — no raw rows, only summaries."""
    # Last 14 days of workouts
    w_rows = await db.execute(
        text(
            """
            SELECT DATE(start_time), workout_type, effort_score, recovery_cost
            FROM workout_sessions
            WHERE end_time IS NOT NULL AND start_time > NOW() - INTERVAL '14 days'
            ORDER BY start_time
            """
        )
    )
    workouts = [
        {"date": str(r[0]), "type": r[1], "effort": r[2], "cost": r[3]}
        for r in w_rows.fetchall()
    ]

    # Last 7 days of sleep
    s_rows = await db.execute(
        text(
            """
            SELECT DATE(start_time), sleep_score, duration_min, avg_hrv
            FROM sleep_sessions
            WHERE end_time IS NOT NULL AND start_time > NOW() - INTERVAL '7 days'
            ORDER BY start_time
            """
        )
    )
    sleeps = [
        {
            "date": str(r[0]),
            "score": r[1],
            "duration_h": round(r[2] / 60, 1) if r[2] else None,
            "hrv": r[3],
        }
        for r in s_rows.fetchall()
    ]

    # Days since each workout type
    last_w = await db.execute(
        text(
            """
            SELECT workout_type, MAX(start_time)
            FROM workout_sessions WHERE end_time IS NOT NULL
            GROUP BY workout_type
            """
        )
    )
    now = datetime.now(timezone.utc)
    days_since = {
        r[0]: (now - r[1]).days for r in last_w.fetchall()
    }

    # Recent memories (last 8)
    mem_rows = await db.execute(
        text("SELECT content FROM agent_memories ORDER BY created_at DESC LIMIT 8")
    )
    memories = [r[0] for r in mem_rows.fetchall()]

    return {
        "workouts_last_14d": workouts,
        "sleep_last_7d": sleeps,
        "days_since_workout_type": days_since,
        "recent_memories": memories,
    }


async def save_memory(db: AsyncSession, content: str) -> None:
    await db.execute(
        text("INSERT INTO agent_memories (content) VALUES (:c)"),
        {"c": content},
    )
    # Keep only the last 50 memories
    await db.execute(
        text(
            "DELETE FROM agent_memories WHERE id NOT IN "
            "(SELECT id FROM agent_memories ORDER BY created_at DESC LIMIT 50)"
        )
    )
    await db.commit()


async def get_recent_workouts(db: AsyncSession, days: int = 7) -> list[dict]:
    rows = await db.execute(
        text(
            """
            SELECT id, workout_type, start_time, end_time, duration_min,
                   avg_hr, max_hr, avg_hrv, effort_score, recovery_cost
            FROM workout_sessions
            WHERE end_time IS NOT NULL
              AND start_time > NOW() - (:days * INTERVAL '1 day')
            ORDER BY start_time DESC
            LIMIT :days
            """
        ),
        {"days": days},
    )
    return [
        {
            "id": r[0],
            "workout_type": r[1],
            "start_time": r[2].isoformat() if r[2] else None,
            "end_time": r[3].isoformat() if r[3] else None,
            "duration_min": r[4],
            "avg_hr": r[5],
            "max_hr": r[6],
            "avg_hrv": r[7],
            "effort_score": r[8],
            "recovery_cost": r[9],
        }
        for r in rows.fetchall()
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
