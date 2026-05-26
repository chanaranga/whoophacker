from datetime import datetime
from typing import Optional, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession


class HealthAgentState(TypedDict):
    user_phone: str
    user_message: str
    intent: str
    sleep_start: Optional[datetime]
    workout_type: Optional[str]
    db: AsyncSession
