import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

import websockets
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text as sa_text

from config import settings
from db.session import AsyncSessionLocal
from routers.metrics import router as metrics_router
from routers.signal_webhook import router as signal_router
from routers.sleep import router as sleep_router
from routers.workouts import router as workouts_router

logger = logging.getLogger("signal_listener")


async def _signal_listener():
    uri = (
        settings.signal_api_url.replace("http://", "ws://").replace("https://", "wss://")
        + f"/v1/receive/{settings.signal_bot_number}"
    )
    while True:
        try:
            logger.info("Connecting to Signal WebSocket: %s", uri)
            async with websockets.connect(uri, ping_interval=30) as ws:
                logger.info("Signal WebSocket connected")
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        envelope = data.get("envelope", {})
                        source = envelope.get("sourceNumber") or envelope.get("source")
                        msg_data = envelope.get("dataMessage", {})
                        text = msg_data.get("message", "").strip()

                        if source and text and source == settings.signal_user_number:
                            from agent.graph import run_agent
                            async with AsyncSessionLocal() as db:
                                asyncio.create_task(run_agent(source, text, db))
                    except Exception:
                        logger.exception("Error processing Signal message")
        except Exception:
            logger.warning("Signal WebSocket disconnected, retrying in 5s...")
            await asyncio.sleep(5)


async def _daily_loop(utc_hour: int, task_name: str, coro_factory):
    """Generic daily loop: waits until utc_hour each day then runs coro_factory()."""
    while True:
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=utc_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_sec = (next_run - now).total_seconds()
        logger.info("%s scheduled in %.0f minutes.", task_name, wait_sec / 60)
        await asyncio.sleep(wait_sec)
        try:
            async with AsyncSessionLocal() as db:
                await coro_factory(db)
        except Exception:
            logger.exception("%s failed.", task_name)


async def _auto_sleep_loop():
    from agent.nodes import auto_sleep_analysis
    await _daily_loop(
        settings.auto_sleep_check_utc_hour,
        "Auto sleep check",
        lambda db: auto_sleep_analysis(db, settings.signal_user_number),
    )


async def _suggestion_loop():
    from agent.nodes import proactive_suggestion
    await _daily_loop(
        settings.auto_suggestion_utc_hour,
        "Workout suggestion",
        lambda db: proactive_suggestion(db, settings.signal_user_number),
    )


async def _run_migrations():
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_text("ALTER TABLE sleep_sessions ADD COLUMN IF NOT EXISTS stage_breakdown TEXT")
        )
        await db.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS agent_memories "
            "(id SERIAL PRIMARY KEY, content TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        ))
        await db.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS workout_sessions (
                id            SERIAL PRIMARY KEY,
                workout_type  TEXT NOT NULL,
                start_time    TIMESTAMPTZ NOT NULL,
                end_time      TIMESTAMPTZ,
                duration_min  INTEGER,
                avg_hr        INTEGER,
                max_hr        INTEGER,
                avg_hrv       FLOAT,
                effort_score  INTEGER,
                recovery_cost INTEGER,
                analysis_text TEXT,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _run_migrations()
    signal_task = asyncio.create_task(_signal_listener())
    sleep_task = asyncio.create_task(_auto_sleep_loop())
    suggestion_task = asyncio.create_task(_suggestion_loop())
    yield
    signal_task.cancel()
    sleep_task.cancel()
    suggestion_task.cancel()


app = FastAPI(title="WHOOP Health Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)
app.include_router(signal_router)
app.include_router(sleep_router)
app.include_router(workouts_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
