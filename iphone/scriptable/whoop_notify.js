// Scriptable widget — displays latest health stats from your home server
// Add your Tailscale IP and secret in the widget parameter field (JSON string):
// {"url":"http://100.x.x.x:8080","secret":"your_secret"}

const param = args.widgetParameter ? JSON.parse(args.widgetParameter) : {};
const SERVER_URL = param.url || "http://100.64.0.1:8080";
const SECRET = param.secret || "";

async function fetchMetrics() {
  const req = new Request(`${SERVER_URL}/api/metrics?limit=1`);
  req.headers = { "X-Server-Secret": SECRET };
  return req.loadJSON();
}

const data = await fetchMetrics().catch(() => null);
const latest = data?.[0];

const w = new ListWidget();
w.backgroundColor = new Color("#1a1a2e");

const title = w.addText("WHOOP");
title.textColor = Color.white();
title.font = Font.boldSystemFont(14);
w.addSpacer(6);

if (latest) {
  if (latest.heart_rate) {
    const hr = w.addText(`❤️ ${latest.heart_rate} bpm`);
    hr.textColor = new Color("#ff6b6b");
    hr.font = Font.systemFont(13);
  }
  if (latest.hrv_rmssd) {
    const hrv = w.addText(`📊 HRV ${latest.hrv_rmssd.toFixed(1)} ms`);
    hrv.textColor = new Color("#4ecdc4");
    hrv.font = Font.systemFont(13);
  }
  if (latest.spo2) {
    const spo2 = w.addText(`🫁 SpO2 ${latest.spo2.toFixed(1)}%`);
    spo2.textColor = new Color("#a8e6cf");
    spo2.font = Font.systemFont(13);
  }
} else {
  const err = w.addText("No data");
  err.textColor = Color.gray();
  err.font = Font.systemFont(12);
}

w.addSpacer();
const ts = w.addDate(new Date());
ts.textColor = Color.gray();
ts.font = Font.systemFont(9);
ts.applyTimeStyle();

Script.setWidget(w);
Script.complete();
