import asyncio
import json
import logging
from contextlib import asynccontextmanager

import websockets
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text as sa_text

from config import settings
from db.session import AsyncSessionLocal
from routers.metrics import router as metrics_router
from routers.signal_webhook import router as signal_router
from routers.sleep import router as sleep_router

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


async def _run_migrations():
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_text(
                "ALTER TABLE sleep_sessions "
                "ADD COLUMN IF NOT EXISTS stage_breakdown TEXT"
            )
        )
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _run_migrations()
    task = asyncio.create_task(_signal_listener())
    yield
    task.cancel()


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


@app.get("/health")
async def health():
    return {"status": "ok"}
