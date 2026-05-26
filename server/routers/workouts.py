from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.queries import get_recent_workouts, get_recovery_inputs
from integrations.ollama_cloud import analyze_recovery
from routers.metrics import verify_secret

router = APIRouter(prefix="/api", tags=["workouts"])


@router.get("/workouts", dependencies=[Depends(verify_secret)])
async def list_workouts(
    days: int = Query(default=7, le=30),
    db: AsyncSession = Depends(get_db),
):
    return await get_recent_workouts(db, days)


@router.get("/recovery", dependencies=[Depends(verify_secret)])
async def get_recovery(db: AsyncSession = Depends(get_db)):
    inputs = await get_recovery_inputs(db)
    recovery = await analyze_recovery(inputs)
    return recovery
