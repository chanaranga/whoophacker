from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import SleepSession
from db.queries import (
    get_health_snapshot,
    get_latest_metric,
    get_24h_avg,
    get_sleep_window_stats,
)
from integrations.ollama_cloud import analyze_sleep, analyze_snapshot
from integrations.signal_client import send_message
from agent.tools import (
    classify_intent_keywords,
    format_sleep_report,
    format_snapshot_message,
)
from agent.prompts import INTENT_SYSTEM_PROMPT

if TYPE_CHECKING:
    from agent.graph import HealthAgentState


async def parse_intent_node(state: "HealthAgentState") -> "HealthAgentState":
    msg = state["user_message"]

    # Fast keyword path
    intent = classify_intent_keywords(msg)
    if intent:
        return {**state, "intent": intent}

    # LLM fallback for ambiguous messages
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.ollama_cloud_base}/api/chat",
            headers={"Authorization": f"Bearer {settings.ollama_cloud_api_key}"},
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                ],
                "stream": False,
            },
        )
    intent = r.json()["message"]["content"].strip().lower()
    return {**state, "intent": intent}


async def record_sleep_start_node(state: "HealthAgentState") -> "HealthAgentState":
    now = datetime.now(timezone.utc)
    db: AsyncSession = state["db"]
    await db.execute(
        text("INSERT INTO sleep_sessions (start_time) VALUES (:t)"),
        {"t": now},
    )
    await db.commit()
    await send_message(state["user_phone"], "Sleep tracking started. Good night!")
    return {**state, "sleep_start": now}


async def run_sleep_analysis_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    end = datetime.now(timezone.utc)

    # Find the latest unclosed sleep session
    row = await db.execute(
        text(
            "SELECT id, start_time FROM sleep_sessions "
            "WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        )
    )
    session = row.fetchone()
    if not session:
        await send_message(state["user_phone"], "No active sleep session found. Did you forget to say 'going to sleep'?")
        return state

    session_id, start = session
    duration_min = int((end - start).total_seconds() / 60)

    stats = await get_sleep_window_stats(db, start, end)
    if not stats:
        await send_message(state["user_phone"], f"Woke up after {duration_min}m but no health data was recorded. Make sure the Expo app was running.")
        return state

    analysis = await analyze_sleep(stats, start, end)
    score = analysis.get("sleep_score")

    # Persist the completed session
    await db.execute(
        text(
            "UPDATE sleep_sessions SET end_time=:end, duration_min=:dur, "
            "avg_hrv=:hrv, avg_hr=:hr, min_spo2=:spo2, sleep_score=:score, "
            "analysis_text=:text WHERE id=:id"
        ),
        {
            "end": end,
            "dur": duration_min,
            "hrv": stats.get("avg_hrv"),
            "hr": stats.get("avg_hr"),
            "spo2": stats.get("min_spo2"),
            "score": score,
            "text": json.dumps(analysis),
            "id": session_id,
        },
    )
    await db.commit()

    report = format_sleep_report(analysis, stats, duration_min)
    await send_message(state["user_phone"], report)
    return state


async def query_metrics_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    intent = state["intent"]
    lines = []

    if intent == "query_hr":
        hr = await get_latest_metric(db, "heart_rate")
        avg = await get_24h_avg(db, "heart_rate")
        lines = [
            f"Heart Rate: {int(hr)} bpm" if hr else "Heart Rate: no data",
            f"24h average: {avg} bpm" if avg else "",
        ]
    elif intent == "query_hrv":
        hrv = await get_latest_metric(db, "hrv_rmssd")
        lines = [f"HRV (RMSSD): {hrv:.1f} ms" if hrv else "HRV: no data"]
    elif intent == "query_spo2":
        spo2 = await get_latest_metric(db, "spo2")
        lines = [f"SpO2: {spo2:.1f}%" if spo2 else "SpO2: no data"]

    await send_message(state["user_phone"], "\n".join(l for l in lines if l))
    return state


async def health_snapshot_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    snap = await get_health_snapshot(db)
    narrative = await analyze_snapshot(snap)
    msg = format_snapshot_message(snap, narrative)
    await send_message(state["user_phone"], msg)
    return state
