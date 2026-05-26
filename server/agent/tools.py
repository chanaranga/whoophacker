import re

SLEEP_KEYWORDS = {"sleep", "sleeping", "bed", "goodnight", "good night", "nap"}
WAKE_KEYWORDS = {"woke", "awake", "morning", "wake", "up", "risen"}
HR_KEYWORDS = {"heart rate", "hr", "pulse", "bpm"}
HRV_KEYWORDS = {"hrv", "heart rate variability", "variability"}
SPO2_KEYWORDS = {"spo2", "oxygen", "o2", "saturation", "spO2"}
SNAPSHOT_KEYWORDS = {"health stats", "stats", "status", "summary", "health", "how am i", "snapshot"}


def classify_intent_keywords(message: str) -> str | None:
    msg = message.lower()
    if any(k in msg for k in WAKE_KEYWORDS):
        return "sleep_end"
    if any(k in msg for k in SLEEP_KEYWORDS):
        return "sleep_start"
    if any(k in msg for k in SNAPSHOT_KEYWORDS):
        return "health_snapshot"
    if any(k in msg for k in HRV_KEYWORDS):
        return "query_hrv"
    if any(k in msg for k in SPO2_KEYWORDS):
        return "query_spo2"
    if any(k in msg for k in HR_KEYWORDS):
        return "query_hr"
    return None


def _fmt_stage(pct: int | None, minutes: int | None) -> str:
    if pct is None:
        return "n/a"
    if minutes is None:
        return f"{pct}%"
    h, m = divmod(minutes, 60)
    t = f"{h}h {m}m" if h else f"{m}m"
    return f"{pct}%  ({t})"


def format_sleep_report(analysis: dict, stats: dict, duration_min: int) -> str:
    h, m = divmod(duration_min, 60)
    score = analysis.get("sleep_score")
    summary = analysis.get("summary", "")
    hrv = analysis.get("hrv_assessment", "")
    spo2 = analysis.get("spo2_notes", "")
    recs = analysis.get("recommendations", [])

    deep_pct = analysis.get("deep_pct")
    deep_min = analysis.get("deep_min")
    rem_pct = analysis.get("rem_pct")
    rem_min = analysis.get("rem_min")
    light_pct = analysis.get("light_pct")
    light_min = analysis.get("light_min")

    lines = [
        f"Sleep Report — {h}h {m}m",
        f"Score: {score}/100" if score else "Score: n/a",
    ]

    if any(v is not None for v in (deep_pct, rem_pct, light_pct)):
        lines += [
            "",
            f"Deep:   {_fmt_stage(deep_pct, deep_min)}",
            f"REM:    {_fmt_stage(rem_pct, rem_min)}",
            f"Light:  {_fmt_stage(light_pct, light_min)}",
            "(estimated from HR/HRV)",
        ]

    lines += ["", summary]

    if hrv:
        lines += ["", hrv]
    if spo2:
        lines.append(spo2)
    if recs:
        lines += ["", "Tips:"] + [f"  • {r}" for r in recs]

    return "\n".join(lines)


def format_snapshot_message(snap, narrative: str) -> str:
    lines = []
    if snap.hr_now is not None:
        lines.append(f"HR:    {snap.hr_now} bpm  (24h avg: {snap.hr_24h_avg})")
    if snap.hrv_now is not None:
        trend = ""
        if snap.hrv_now and snap.hrv_7d_avg:
            trend = " ↑" if snap.hrv_now > snap.hrv_7d_avg else " ↓"
        lines.append(f"HRV:   {snap.hrv_now:.1f} ms  (7d avg: {snap.hrv_7d_avg} ms{trend})")
    if snap.spo2_now is not None:
        lines.append(f"SpO2:  {snap.spo2_now:.1f}%")
    if snap.last_sleep_score is not None:
        h, m = divmod(snap.last_sleep_duration_min or 0, 60)
        lines.append(f"Sleep: {snap.last_sleep_score}/100  ({h}h {m}m last night)")
    if narrative:
        lines += ["", narrative]
    return "\n".join(lines) if lines else "No data collected yet. Make sure the WHOOP app is syncing."
