import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from routers.metrics import verify_secret

router = APIRouter(prefix="/api", tags=["sleep"])


@router.get("/sleep/scores", dependencies=[Depends(verify_secret)])
async def get_sleep_scores(
    days: int = Query(default=7, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT id, start_time, end_time, duration_min, sleep_score,
                   avg_hrv, avg_hr, min_spo2, stage_breakdown
            FROM sleep_sessions
            WHERE end_time IS NOT NULL
              AND start_time > NOW() - (:days * INTERVAL '1 day')
            ORDER BY start_time DESC
            LIMIT :days
            """
        ),
        {"days": days},
    )
    rows = result.mappings().all()
    out = []
    for r in rows:
        stages = None
        if r["stage_breakdown"]:
            try:
                stages = json.loads(r["stage_breakdown"])
            except Exception:
                pass
        out.append(
            {
                "id": r["id"],
                "start_time": r["start_time"].isoformat() if r["start_time"] else None,
                "end_time": r["end_time"].isoformat() if r["end_time"] else None,
                "duration_min": r["duration_min"],
                "sleep_score": r["sleep_score"],
                "avg_hrv": r["avg_hrv"],
                "avg_hr": r["avg_hr"],
                "min_spo2": r["min_spo2"],
                "stages": stages,
            }
        )
    return out
