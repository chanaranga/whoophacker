import json
from datetime import datetime
from typing import Any

import httpx

from config import settings
from db.schemas import HealthSnapshot


SLEEP_SYSTEM_PROMPT = """You are a personal sleep analyst. Analyse the provided sleep window data and return ONLY a JSON object with these exact keys:

- sleep_score: integer 0-100
- deep_pct: integer (estimated % of sleep time in deep/N3 sleep)
- deep_min: integer (estimated minutes in deep sleep)
- rem_pct: integer (estimated % of sleep time in REM sleep)
- rem_min: integer (estimated minutes in REM sleep)
- light_pct: integer (estimated % of sleep time in light/N1+N2 sleep; deep_pct + rem_pct + light_pct should sum to ~100)
- light_min: integer (estimated minutes in light sleep)
- hrv_assessment: string (1-2 sentences on HRV quality and what it means for recovery)
- spo2_notes: string (1 sentence on oxygen saturation; omit field if no SpO2 data)
- recommendations: array of 2-3 short actionable strings
- summary: string (2-3 sentences, overall sleep quality in plain English)

Estimate sleep stages from heart rate and HRV patterns in the time series (format: [offset_minutes, avg_hr, avg_hrv_or_null]):
- Deep sleep (N3): HR sustained >=8% below the sleep-window mean, paired with higher or stable HRV; concentrated in the first third of the night
- REM: moderate HR with brief spikes or drops, HRV lower than during deep sleep; cycles every ~90 min
- Light sleep (N1/N2): HR between deep and waking baseline, moderate to low HRV; transitions between stages

Score based on: sleep duration vs 7-9h target (25%), deep% vs ideal 15-20% (30%), HRV quality (30%), SpO2 stability (15%).
Return only valid JSON, no markdown or extra text."""

SNAPSHOT_SYSTEM_PROMPT = """You are a personal health assistant. Given aggregated health metrics, write a brief 2-3 sentence narrative summary assessing the user's current health state.
Focus on what the numbers mean in plain English — mention any notable trends, concerns, or positives.
Keep it conversational, concise, and actionable. Do NOT repeat the raw numbers."""


def _format_sleep_payload(
    stats: dict, start: datetime, end: datetime, timeseries: list[dict] | None = None
) -> str:
    duration_min = int((end - start).total_seconds() / 60)
    payload: dict = {
        "sleep_duration_minutes": duration_min,
        "avg_heart_rate_bpm": stats.get("avg_hr"),
        "min_heart_rate_bpm": stats.get("min_hr"),
        "max_heart_rate_bpm": stats.get("max_hr"),
        "avg_hrv_rmssd_ms": stats.get("avg_hrv"),
        "min_spo2_percent": stats.get("min_spo2"),
        "data_samples": stats.get("sample_count", 0),
    }
    if timeseries:
        # Compact format: [offset_min, hr, hrv] — hrv may be null
        payload["timeseries_5min"] = [
            [p["min"], p["hr"], p["hrv"]] for p in timeseries
        ]
    return json.dumps(payload)


def _format_snapshot_payload(snap: HealthSnapshot) -> str:
    parts = []
    if snap.hr_now is not None:
        parts.append(f"Current HR: {snap.hr_now} bpm (24h avg: {snap.hr_24h_avg} bpm)")
    if snap.hrv_now is not None:
        trend = ""
        if snap.hrv_now and snap.hrv_7d_avg:
            trend = " ↑" if snap.hrv_now > snap.hrv_7d_avg else " ↓"
        parts.append(f"HRV (RMSSD): {snap.hrv_now:.1f} ms (7d avg: {snap.hrv_7d_avg} ms{trend})")
    if snap.spo2_now is not None:
        parts.append(f"SpO2: {snap.spo2_now:.1f}%")
    if snap.last_sleep_score is not None:
        h = snap.last_sleep_duration_min // 60 if snap.last_sleep_duration_min else "?"
        m = snap.last_sleep_duration_min % 60 if snap.last_sleep_duration_min else "?"
        parts.append(f"Last sleep score: {snap.last_sleep_score}/100 ({h}h {m}m)")
    return "\n".join(parts) if parts else "No metrics available yet."


async def analyze_sleep(
    stats: dict,
    start: datetime,
    end: datetime,
    timeseries: list[dict] | None = None,
) -> dict[str, Any]:
    payload = _format_sleep_payload(stats, start, end, timeseries)
    return await _call_llm(SLEEP_SYSTEM_PROMPT, payload)


WORKOUT_SYSTEM_PROMPT = """You are a personal fitness analyst. Analyse the provided workout data and return ONLY a JSON object with these exact keys:

- effort_score: integer 0-100
- recovery_cost: integer 0-100 (20=easy walk, 50=moderate cardio, 80=hard HIIT or heavy lifting)
- zone_easy_pct: integer (% HR < 120 bpm)
- zone_moderate_pct: integer (% HR 120-140 bpm)
- zone_hard_pct: integer (% HR 140-160 bpm)
- zone_intense_pct: integer (% HR > 160 bpm; all zone_* sum to ~100)
- hrv_response: string (1 sentence on HRV during workout)
- summary: string (2-3 sentences on workout quality)
- recommendations: array of 2 short recovery/follow-up strings

Return only valid JSON, no markdown."""

RECOVERY_SYSTEM_PROMPT = """You are a personal health coach. Given recovery indicators, return ONLY a JSON object:

- recovery_score: integer 0-100
- readiness: exactly one of "high", "moderate", "low"
- factors: array of 3-4 short strings explaining the score
- recommendation: string (1-2 sentences on appropriate activity today)

Weights: sleep quality 35%, HRV vs baseline 30%, recent workout load 25%, resting HR trend 10%.
>=75 = ready for hard training; 50-74 = moderate; <50 = rest or light only.
Return only valid JSON, no markdown."""

WORKOUT_ADVICE_SYSTEM_PROMPT = """You are a personal health coach. Given recovery data and a requested workout type, return ONLY a JSON object:

- recommendation: exactly one of "yes", "caution", "no"
- rationale: string (2-3 sentences referencing specific recovery metrics)
- alternative: string (if caution/no: suggest alternative; if yes: how to maximise the session)

Return only valid JSON, no markdown."""


async def _call_llm(system: str, user: str, model: str | None = None, timeout: int = 90) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{settings.ollama_cloud_base}/api/chat",
            headers={"Authorization": f"Bearer {settings.ollama_cloud_api_key}"},
            json={
                "model": model or settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
            },
        )
    r.raise_for_status()
    raw = r.json()["message"]["content"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


async def analyze_workout(
    stats: dict, workout_type: str, start: datetime, end: datetime,
    timeseries: list[dict] | None = None,
) -> dict[str, Any]:
    duration_min = int((end - start).total_seconds() / 60)
    payload: dict = {
        "workout_type": workout_type,
        "duration_minutes": duration_min,
        "avg_heart_rate_bpm": stats.get("avg_hr"),
        "max_heart_rate_bpm": stats.get("max_hr"),
        "avg_hrv_rmssd_ms": stats.get("avg_hrv"),
        "data_samples": stats.get("sample_count", 0),
    }
    if timeseries:
        payload["timeseries_5min"] = [[p["min"], p["hr"], p["hrv"]] for p in timeseries]
    return await _call_llm(WORKOUT_SYSTEM_PROMPT, json.dumps(payload))


async def analyze_recovery(inputs: dict) -> dict[str, Any]:
    return await _call_llm(RECOVERY_SYSTEM_PROMPT, json.dumps(inputs), timeout=60)


async def advise_workout(recovery: dict, workout_type: str) -> dict[str, Any]:
    payload = {**recovery, "requested_workout": workout_type}
    return await _call_llm(WORKOUT_ADVICE_SYSTEM_PROMPT, json.dumps(payload), timeout=60)


async def analyze_patterns(pattern_data: dict) -> dict[str, Any]:
    from agent.prompts import PATTERN_ANALYSIS_PROMPT
    return await _call_llm(PATTERN_ANALYSIS_PROMPT, json.dumps(pattern_data), timeout=90)


async def analyze_snapshot(snap: HealthSnapshot) -> str:
    payload = _format_snapshot_payload(snap)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.ollama_cloud_base}/api/chat",
            headers={"Authorization": f"Bearer {settings.ollama_cloud_api_key}"},
            json={
                "model": settings.ollama_snapshot_model,
                "messages": [
                    {"role": "system", "content": SNAPSHOT_SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
                ],
                "stream": False,
            },
        )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()

