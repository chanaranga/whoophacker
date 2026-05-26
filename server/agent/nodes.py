import json
import logging
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.queries import (
    get_health_snapshot,
    get_latest_metric,
    get_24h_avg,
    get_sleep_window_stats,
    get_sleep_window_timeseries,
    get_overnight_data,
    has_recent_sleep_session,
    get_workout_window_stats,
    get_recovery_inputs,
)
from integrations.ollama_cloud import (
    analyze_sleep, analyze_snapshot, analyze_workout,
    analyze_recovery, advise_workout,
)
from integrations.signal_client import send_message
from agent.state import HealthAgentState
from agent.tools import (
    classify_intent_keywords,
    extract_workout_type,
    format_sleep_report,
    format_workout_report,
    format_recovery_message,
    format_advice_message,
    format_snapshot_message,
)
from agent.prompts import INTENT_SYSTEM_PROMPT


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

    timeseries = await get_sleep_window_timeseries(db, start, end)
    analysis = await analyze_sleep(stats, start, end, timeseries)
    score = analysis.get("sleep_score")

    stage_breakdown = {
        k: analysis.get(k)
        for k in ("deep_pct", "deep_min", "rem_pct", "rem_min", "light_pct", "light_min")
    }

    # Persist the completed session
    await db.execute(
        text(
            "UPDATE sleep_sessions SET end_time=:end, duration_min=:dur, "
            "avg_hrv=:hrv, avg_hr=:hr, min_spo2=:spo2, sleep_score=:score, "
            "analysis_text=:text, stage_breakdown=:stages WHERE id=:id"
        ),
        {
            "end": end,
            "dur": duration_min,
            "hrv": stats.get("avg_hrv"),
            "hr": stats.get("avg_hr"),
            "spo2": stats.get("min_spo2"),
            "score": score,
            "text": json.dumps(analysis),
            "stages": json.dumps(stage_breakdown),
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


async def workout_start_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    workout_type = state.get("workout_type") or extract_workout_type(state["user_message"])
    now = datetime.now(timezone.utc)
    await db.execute(
        text("INSERT INTO workout_sessions (workout_type, start_time) VALUES (:t, :s)"),
        {"t": workout_type, "s": now},
    )
    await db.commit()
    await send_message(state["user_phone"], f"{workout_type.title()} session started. Good luck!")
    return state


async def workout_end_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    end = datetime.now(timezone.utc)

    row = await db.execute(
        text(
            "SELECT id, workout_type, start_time FROM workout_sessions "
            "WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        )
    )
    session = row.fetchone()
    if not session:
        await send_message(state["user_phone"], "No active workout session found. Did you forget to say you were starting one?")
        return state

    session_id, workout_type, start = session
    duration_min = int((end - start).total_seconds() / 60)

    stats = await get_workout_window_stats(db, start, end)
    timeseries = await get_sleep_window_timeseries(db, start, end)

    analysis = await analyze_workout(stats, workout_type, start, end, timeseries)

    await db.execute(
        text(
            "UPDATE workout_sessions SET end_time=:end, duration_min=:dur, "
            "avg_hr=:hr, max_hr=:maxhr, avg_hrv=:hrv, effort_score=:effort, "
            "recovery_cost=:cost, analysis_text=:text WHERE id=:id"
        ),
        {
            "end": end, "dur": duration_min,
            "hr": stats.get("avg_hr"), "maxhr": stats.get("max_hr"),
            "hrv": stats.get("avg_hrv"),
            "effort": analysis.get("effort_score"),
            "cost": analysis.get("recovery_cost"),
            "text": json.dumps(analysis),
            "id": session_id,
        },
    )
    await db.commit()

    report = format_workout_report(analysis, workout_type, duration_min)
    await send_message(state["user_phone"], report)
    return state


async def recovery_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    inputs = await get_recovery_inputs(db)
    recovery = await analyze_recovery(inputs)
    msg = format_recovery_message(recovery)
    await send_message(state["user_phone"], msg)
    return state


async def workout_advice_node(state: "HealthAgentState") -> "HealthAgentState":
    db: AsyncSession = state["db"]
    workout_type = extract_workout_type(state["user_message"])
    inputs = await get_recovery_inputs(db)
    recovery = await analyze_recovery(inputs)
    advice = await advise_workout(recovery, workout_type)
    msg = format_advice_message(advice, workout_type)
    await send_message(state["user_phone"], msg)
    return state


def _infer_sleep_window(timeseries: list[dict]) -> tuple[datetime, datetime] | None:
    """
    Infer sleep start and end from HR pattern in overnight data.
    Uses the 20th-percentile HR as a baseline; anything within 20% above
    that is treated as 'sleep range'. Requires ≥3h of inferred sleep.
    """
    pts = [p for p in timeseries if p["hr"] is not None]
    if len(pts) < 12:  # need at least 1 hour of data
        return None

    hrs = sorted(p["hr"] for p in pts)
    p20 = hrs[max(0, len(hrs) // 5)]
    threshold = p20 * 1.20  # 20% above lowest-20th-pct = sleep range ceiling

    # Find first 3-consecutive-bucket window all below threshold → sleep start
    sleep_start = None
    for i in range(len(pts) - 2):
        window = [pts[j]["hr"] for j in range(i, i + 3)]
        if all(h <= threshold for h in window):
            sleep_start = pts[i]
            break

    if sleep_start is None:
        return None

    # Find last 3-consecutive-bucket window all below threshold → wake end
    sleep_end = sleep_start
    for i in range(len(pts) - 3, pts.index(sleep_start), -1):
        window = [pts[j]["hr"] for j in range(i, i + 3)]
        if all(h <= threshold for h in window):
            sleep_end = pts[i + 2]
            break

    duration_min = sleep_end["min"] - sleep_start["min"]
    if duration_min < 180:
        return None

    return sleep_start["time"], sleep_end["time"]


async def auto_sleep_analysis(db: AsyncSession, user_phone: str) -> None:
    """
    Called at the morning check time. If no sleep session was logged
    manually for last night, infer sleep window from HR data and run
    the full analysis automatically.
    """
    if await has_recent_sleep_session(db):
        logger.info("Auto sleep check: session already exists, skipping.")
        return

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=15)  # look back 15 h (covers any sleep time)

    timeseries = await get_overnight_data(db, window_start, now)
    if not timeseries:
        logger.info("Auto sleep check: no overnight data found.")
        return

    inferred = _infer_sleep_window(timeseries)
    if inferred is None:
        logger.info("Auto sleep check: could not infer sleep window from data.")
        return

    sleep_start, sleep_end = inferred
    duration_min = int((sleep_end - sleep_start).total_seconds() / 60)

    # Trim timeseries to the inferred window for the LLM
    sleep_ts = [p for p in timeseries if sleep_start <= p["time"] <= sleep_end]

    stats = await get_sleep_window_stats(db, sleep_start, sleep_end)
    if not stats:
        return

    analysis = await analyze_sleep(stats, sleep_start, sleep_end, sleep_ts)
    score = analysis.get("sleep_score")
    stage_breakdown = {
        k: analysis.get(k)
        for k in ("deep_pct", "deep_min", "rem_pct", "rem_min", "light_pct", "light_min")
    }

    await db.execute(
        text(
            "INSERT INTO sleep_sessions "
            "(start_time, end_time, duration_min, avg_hrv, avg_hr, min_spo2, "
            "sleep_score, analysis_text, stage_breakdown) "
            "VALUES (:start, :end, :dur, :hrv, :hr, :spo2, :score, :text, :stages)"
        ),
        {
            "start": sleep_start,
            "end": sleep_end,
            "dur": duration_min,
            "hrv": stats.get("avg_hrv"),
            "hr": stats.get("avg_hr"),
            "spo2": stats.get("min_spo2"),
            "score": score,
            "text": json.dumps(analysis),
            "stages": json.dumps(stage_breakdown),
        },
    )
    await db.commit()

    report = format_sleep_report(analysis, stats, duration_min)
    h, m = divmod(duration_min, 60)
    header = f"Good morning! (Auto-detected sleep: {h}h {m}m)\n\n"
    await send_message(user_phone, header + report)
