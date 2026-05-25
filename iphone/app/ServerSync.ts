// SERVER_URL: set to your Tailscale IP, e.g. http://100.x.x.x:8080
// SERVER_SECRET: must match SERVER_SECRET in your .env on the Ubuntu server
const SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL ?? "http://100.64.0.1:8080";
const SERVER_SECRET = process.env.EXPO_PUBLIC_SERVER_SECRET ?? "";

export interface MetricsPayload {
  heart_rate?: number;
  hrv_rmssd?: number;
  spo2?: number;
  skin_temp?: number;
  resp_rate?: number;
  timestamp?: string;
}

export async function postMetrics(payload: MetricsPayload): Promise<boolean> {
  try {
    const res = await fetch(`${SERVER_URL}/api/metrics`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Server-Secret": SERVER_SECRET,
      },
      body: JSON.stringify(payload),
    });
    return res.ok;
  } catch {
    return false;
  }
}
