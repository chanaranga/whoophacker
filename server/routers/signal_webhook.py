from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.session import get_db
from db.schemas import SignalMessage

router = APIRouter(prefix="/webhook", tags=["signal"])


@router.post("/signal")
async def handle_signal_message(
    body: SignalMessage,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Only respond to the configured user number
    if body.sourceNumber != settings.signal_user_number:
        return {"status": "ignored"}

    # Import here to avoid circular imports at startup
    from agent.graph import run_agent

    background_tasks.add_task(run_agent, body.sourceNumber, body.message, db)
    return {"status": "queued"}
