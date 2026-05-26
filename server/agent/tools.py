import re

SLEEP_KEYWORDS = {"sleep", "sleeping", "bed", "goodnight", "good night", "nap"}
WAKE_KEYWORDS = {"woke", "awake", "morning", "wake", "risen"}
HR_KEYWORDS = {"heart rate", "hr", "pulse", "bpm"}
HRV_KEYWORDS = {"hrv", "heart rate variability", "variability"}
SNAPSHOT_KEYWORDS = {"health stats", "stats", "status", "summary", "health", "how am i", "snapshot"}
WORKOUT_START_PHRASES = {"starting", "starting a", "beginning", "going for", "about to", "i'm going to", "starting my"}
WORKOUT_WORDS = {"workout", "run", "cardio", "weights", "lifting", "gym", "hiit", "yoga", "walk", "hike", "swim", "cycling", "bike", "training", "exercise"}
WORKOUT_END_PHRASES = {"done", "finished", "completed", "stopped", "ending", "done with workout", "workout done", "workout finished", "finished workout"}
RECOVERY_KEYWORDS = {"recovery", "recovered", "readiness", "ready to train", "how recovered"}
ADVICE_PHRASES = {"can i", "should i", "is it ok", "okay to", "alright to", "safe to"}

WORKOUT_TYPE_MAP = {
    "run": "running", "running": "running", "jog": "running",
    "cardio": "cardio", "cycling": "cycling", "bike": "cycling",
    "swim": "swimming", "swimming": "swimming",
    "weights": "weights", "lifting": "weights", "strength": "weights", "gym": "weights",
    "hiit": "hiit", "circuit": "hiit", "intervals": "hiit",
    "yoga": "yoga", "stretch": "yoga",
    "walk": "walking", "walking": "walking", "hike": "hiking",
}


def extract_workout_type(message: str) -> str:
    msg = message.lower()
    for keyword, wtype in WORKOUT_TYPE_MAP.items():
        if keyword in msg:
            return wtype
    return "workout"


def classify_intent_keywords(message: str) -> str | None:
    msg = message.lower()
    # Workout advice must come before workout_start ("can I do cardio?")
    if any(p in msg for p in ADVICE_PHRASES) and any(w in msg for w in WORKOUT_WORDS):
        return "workout_advice"
    # Workout end before wake (both might contain "done")
    if any(p in msg for p in WORKOUT_END_PHRASES) and any(w in msg for w in WORKOUT_WORDS | {"training", "session"}):
        return "workout_end"
    if any(p in msg for p in WORKOUT_START_PHRASES) and any(w in msg for w in WORKOUT_WORDS):
        return "workout_start"
    if any(k in msg for k in RECOVERY_KEYWORDS):
        return "query_recovery"
    if any(k in msg for k in WAKE_KEYWORDS):
        return "sleep_end"
    if any(k in msg for k in SLEEP_KEYWORDS):
        return "sleep_start"
    if any(k in msg for k in SNAPSHOT_KEYWORDS):
        return "health_snapshot"
    if any(k in msg for k in HRV_KEYWORDS):
        return "query_hrv"
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


def format_workout_report(analysis: dict, workout_type: str, duration_min: int) -> str:
    h, m = divmod(duration_min, 60)
    dur = f"{h}h {m}m" if h else f"{m}m"
    score = analysis.get("effort_score")
    cost = analysis.get("recovery_cost")
    summary = analysis.get("summary", "")
    recs = analysis.get("recommendations", [])

    easy = analysis.get("zone_easy_pct")
    mod = analysis.get("zone_moderate_pct")
    hard = analysis.get("zone_hard_pct")
    intense = analysis.get("zone_intense_pct")

    lines = [
        f"Workout Report — {workout_type.title()}  {dur}",
        f"Effort: {score}/100   Recovery cost: {cost}/100" if score else "",
        "",
    ]
    if any(v is not None for v in (easy, mod, hard, intense)):
        lines += [
            "HR Zones:",
            f"  Easy (<120):     {easy}%",
            f"  Moderate (120-140): {mod}%",
            f"  Hard (140-160):  {hard}%",
            f"  Intense (>160):  {intense}%",
            "",
        ]
    lines.append(summary)
    if analysis.get("hrv_response"):
        lines += ["", analysis["hrv_response"]]
    if recs:
        lines += ["", "Recovery tips:"] + [f"  • {r}" for r in recs]
    return "\n".join(l for l in lines if l is not None)


def format_recovery_message(recovery: dict) -> str:
    score = recovery.get("recovery_score")
    readiness = recovery.get("readiness", "").title()
    factors = recovery.get("factors", [])
    rec = recovery.get("recommendation", "")

    lines = [
        f"Recovery Score: {score}/100  ({readiness})" if score else "Recovery: no data",
        "",
    ]
    if factors:
        lines += [f"  • {f}" for f in factors]
    if rec:
        lines += ["", rec]
    return "\n".join(lines)


def format_advice_message(advice: dict, workout_type: str) -> str:
    rec = advice.get("recommendation", "").upper()
    rationale = advice.get("rationale", "")
    alt = advice.get("alternative", "")
    lines = [
        f"{rec} — {workout_type.title()}",
        "",
        rationale,
    ]
    if alt:
        lines += ["", alt]
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
