import json
from datetime import datetime
from typing import Any

import httpx

from config import settings
from db.schemas import HealthSnapshot


SLEEP_SYSTEM_PROMPT = """You are a personal health analyst. Analyse the provided sleep data and return ONLY a JSON object with these exact keys:
- sleep_score: integer 0-100
- hrv_assessment: string (1-2 sentences on HRV quality and trend)
- spo2_notes: string (1 sentence on oxygen saturation)
- recommendations: array of 2-3 short actionable strings
- summary: string (2-3 sentences — overall sleep quality in plain English)

Base the score on: HRV quality (weight 40%), SpO2 stability (20%), sleep duration (25%), HR stability (15%).
Return only valid JSON, no markdown or extra text."""

SNAPSHOT_SYSTEM_PROMPT = """You are a personal health assistant. Given aggregated health metrics, write a brief 2-3 sentence narrative summary assessing the user's current health state.
Focus on what the numbers mean in plain English — mention any notable trends, concerns, or positives.
Keep it conversational, concise, and actionable. Do NOT repeat the raw numbers."""


def _format_sleep_payload(stats: dict, start: datetime, end: datetime) -> str:
    duration_min = int((end - start).total_seconds() / 60)
    return json.dumps(
        {
            "sleep_duration_minutes": duration_min,
            "avg_heart_rate_bpm": stats.get("avg_hr"),
            "avg_hrv_rmssd_ms": stats.get("avg_hrv"),
            "min_spo2_percent": stats.get("min_spo2"),
            "data_samples": stats.get("sample_count", 0),
        }
    )


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


async def analyze_sleep(stats: dict, start: datetime, end: datetime) -> dict[str, Any]:
    payload = _format_sleep_payload(stats, start, end)
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
