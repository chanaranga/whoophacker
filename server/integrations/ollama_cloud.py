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
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{settings.ollama_cloud_base}/api/chat",
            headers={"Authorization": f"Bearer {settings.ollama_cloud_api_key}"},
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SLEEP_SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
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
        return {"summary": raw, "sleep_score": None, "recommendations": []}


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
