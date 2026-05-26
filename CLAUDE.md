# WHOOP Health Agent — Project Guide

## What this is
A fully self-hosted personal health pipeline: WHOOP 4.0 band → iPhone (BLE collection) → Ubuntu home server → LangGraph agent → Ollama Cloud (DeepSeek V3) → Signal bot for interactive health queries, sleep analysis, and workout tracking.

## Architecture

```
WHOOP 4.0
  ↓ BLE (GATT HR service 0x180D / 0x2A37)
iPhone – Expo app (react-native-ble-plx)
  ↓ HTTPS POST every 30s, sync every 3min  [Tailscale VPN: 100.118.146.121:8080]
Ubuntu server – Docker Compose (~/whoophacker/)
  ├── FastAPI :8080          — data ingestion + API
  ├── PostgreSQL+TimescaleDB — health_metrics hypertable + sleep/workout/memory tables
  ├── Redis                  — LangGraph checkpointing
  ├── signal-cli-rest-api :8083  — Signal bot (number: +31621372816)
  └── LangGraph agent → Ollama Cloud (deepseek-v3.1:671b-cloud)
```

## Key files

### iPhone app (`iphone/app/`)
| File | Purpose |
|------|---------|
| `BleManager.ts` | BLE connection, GATT HR parsing, R-R intervals, RMSSD computation |
| `DataStore.ts` | SQLite local store (72h rolling, 30s averages) |
| `ServerSync.ts` | HTTP client for all server endpoints; sends `X-Timezone` header |
| `BackgroundTask.ts` | expo-background-fetch task registration |
| `App.tsx` | Main UI: HR/HRV charts, nightly HRV chart, recovery widget, workouts, sleep list |

### Server (`server/`)
| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, lifespan startup (migrations + 3 background tasks) |
| `config.py` | pydantic-settings env config |
| `routers/metrics.py` | `POST /api/metrics`, `GET /api/metrics` |
| `routers/sleep.py` | `GET /api/sleep/scores?days=N` |
| `routers/workouts.py` | `GET /api/workouts?days=N`, `GET /api/recovery` |
| `routers/signal_webhook.py` | Signal message ingestion |
| `agent/graph.py` | LangGraph state machine |
| `agent/nodes.py` | All agent nodes incl. `auto_sleep_analysis`, `proactive_suggestion` |
| `agent/tools.py` | Intent classification (keyword + LLM fallback), formatters |
| `agent/prompts.py` | All LLM system prompts |
| `integrations/ollama_cloud.py` | Ollama Cloud API client |
| `integrations/signal_client.py` | signal-cli-rest-api HTTP client |
| `db/queries.py` | All DB query helpers |
| `db/models.py` | SQLAlchemy ORM models |
| `db/schemas.py` | Pydantic request/response schemas |

## Agent intents
`sleep_start` → `sleep_end` → `workout_start` → `workout_end` → `query_recovery` → `workout_advice` → `query_hr` → `query_hrv` → `health_snapshot`

## Background tasks (auto-scheduled)
- **Auto sleep analysis**: runs at `AUTO_SLEEP_CHECK_LOCAL_HOUR` (default 10am) in user's timezone — infers sleep window from overnight HR data and sends Signal message if no manual session was recorded
- **Proactive workout suggestion**: runs at `AUTO_SUGGESTION_LOCAL_HOUR` (default 5pm) — analyses 14d patterns and sends a suggestion via Signal
- Timezone is auto-detected from `X-Timezone` header sent by the iPhone app

## Database tables
- `health_metrics` — TimescaleDB hypertable, raw HR/HRV readings
- `sleep_sessions` — scored sleep sessions with stage breakdown (LLM-estimated)
- `workout_sessions` — workouts with effort_score, recovery_cost, analysis
- `agent_memories` — pattern insights, max 50 rows, feeds back into analysis
- `user_settings` — key/value store, currently stores `timezone`

## Server access
- SSH: `chana@192.168.1.150` (key-based auth)
- Docker Compose dir: `~/whoophacker/`
- Rebuild API: `cd ~/whoophacker && git pull && docker compose up -d --build api`
- Logs: `docker logs whoophacker-api-1 -f`
- Signal container: `whoophacker-signal-rest-1` on host port 8083

**IMPORTANT — do NOT read `~/whoophacker/.env` via SSH.** It contains live credentials (API keys, DB password, server secret). Use `sed -i` to edit it non-interactively. The auto-mode classifier will block it.

## iPhone app build
- Build via Xcode only: **Cmd+R** (Release scheme)
- Never use `xcodebuild` from CLI — signing fails
- Clean build if seeing stale native code: Product → Clean Build Folder, then Cmd+R
- ATS fix already in Info.plist: `NSAllowsArbitraryLoads = true` (needed for Tailscale CGNAT range 100.x.x.x)

## HRV notes
- Measured via standard GATT R-R intervals from WHOOP's HR service
- `computeRmssd` in `BleManager.ts` uses a median-based ectopic filter (discard intervals >25% from buffer median)
- Typical daytime values: 50-80ms. WHOOP's app shows overnight values (lightest sleep stage) which are typically lower (35-45ms) — these are different measurements, not a bug
- SpO2 and skin temp via proprietary WHOOP BLE characteristics are NOT implemented (undocumented write command required; removed from stack entirely)

## Ollama Cloud
- Model: `deepseek-v3.1:671b-cloud` (requires `-cloud` suffix for remote inference)
- Base URL: `https://ollama.com` → `/api/chat`
- User has a paid subscription (~210 tokens/sec dedicated capacity)
- Only aggregated stats are sent to LLM (never raw timestamped rows)
