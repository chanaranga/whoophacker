# WHOOP Health Agent

Personal health pipeline: WHOOP band → iPhone (BLE) → Ubuntu server → LangGraph agent → DeepSeek (Ollama Cloud) → Signal bot.

## Architecture

```
WHOOP 4.0 → Expo iPhone App (BLE) → Ubuntu Server (Docker)
                                          ├── FastAPI :8080
                                          ├── PostgreSQL + TimescaleDB
                                          ├── Redis
                                          └── LangGraph Agent → Ollama Cloud (DeepSeek)
                                                                        ↓
                                                               Signal Bot → your phone
```

## Quick start

### 1. Ubuntu server — prerequisites

```bash
# Install Docker + Tailscale
apt install docker.io docker-compose-plugin
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
```

### 2. Clone and configure

```bash
git clone https://github.com/<you>/whoophack
cd whoophack
cp .env.example .env
# Edit .env — fill in OLLAMA_CLOUD_API_KEY, SIGNAL_BOT_NUMBER,
# SIGNAL_USER_NUMBER, SERVER_SECRET
```

### 3. Start services

```bash
docker compose up -d
```

### 4. Register Signal bot number (one-time)

```bash
# Replace +1BOT with your dedicated bot number
docker compose exec signal-rest signal-cli -u +1BOT register
# You'll receive an SMS with a code:
docker compose exec signal-rest signal-cli -u +1BOT verify THE_CODE

# Register the FastAPI webhook so Signal messages reach the agent:
curl -X POST http://localhost:8083/v1/configuration/webhook \
  -H "Content-Type: application/json" \
  -d '{"url": "http://api:8080/webhook/signal"}'
```

### 5. iPhone — build the Expo app

```bash
cd iphone/app
npm install
# Create iphone/app/.env with:
#   EXPO_PUBLIC_SERVER_URL=http://100.x.x.x:8080   (your Tailscale IP)
#   EXPO_PUBLIC_SERVER_SECRET=<same as SERVER_SECRET in .env>

# Build a development build (TestFlight or direct install via USB):
npx eas build --platform ios --profile development
# or for a local simulator test:
npx expo run:ios
```

### 6. Connect Tailscale on iPhone

Install the Tailscale app from the App Store and sign in with the same account used on the Ubuntu server. The server's Tailscale IP (e.g. `100.x.x.x`) will be reachable from your iPhone anywhere.

---

## Signal commands

| Message | Response |
|---------|----------|
| `give me my health stats` | Full health snapshot + DeepSeek narrative |
| `heart rate` | Current HR + 24h average |
| `HRV` | Latest HRV (RMSSD) + 7-day trend |
| `SpO2` | Latest oxygen saturation |
| `going to sleep` | Starts sleep tracking session |
| `I just woke up` | Ends session, sends sleep score + analysis |

---

## Verification

```bash
# Test data ingestion (from Mac or server):
curl -X POST http://localhost:8080/api/metrics \
  -H "Content-Type: application/json" \
  -H "X-Server-Secret: your_secret" \
  -d '{"heart_rate": 65, "hrv_rmssd": 40.5, "spo2": 97.2}'

# Check stored data:
curl http://localhost:8080/api/metrics?limit=5

# Send a test Signal message from your personal number to the bot number.
```

---

## Scriptable widget (optional)

Copy `iphone/scriptable/whoop_notify.js` into Scriptable on your iPhone.  
Set the widget parameter to: `{"url":"http://100.x.x.x:8080","secret":"your_secret"}`

---

## Notes

- **WHOOP BLE**: Heart rate + R-R intervals (for HRV RMSSD) come from standard GATT service `0x180D`. SpO2 via proprietary WHOOP characteristics may need firmware-specific UUIDs.
- **Background BLE on iOS**: Enable in Settings → WHOOP Collector → Background App Refresh. For overnight sleep monitoring, keep the app in the foreground (screen-off is fine).
- **Ollama Cloud models**: Cloud models require the `-cloud` suffix. Change `OLLAMA_MODEL` in `.env` — full list at https://ollama.com/search?c=cloud
