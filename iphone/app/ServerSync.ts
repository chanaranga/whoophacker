import { StoredReading } from "./DataStore";

const SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL ?? "http://100.64.0.1:8080";
const SERVER_SECRET = process.env.EXPO_PUBLIC_SERVER_SECRET ?? "";

export interface SleepStages {
  deep_pct?: number | null;
  deep_min?: number | null;
  rem_pct?: number | null;
  rem_min?: number | null;
  light_pct?: number | null;
  light_min?: number | null;
}

export interface SleepScoreEntry {
  id: number;
  start_time: string;
  end_time: string | null;
  duration_min: number | null;
  sleep_score: number | null;
  avg_hrv: number | null;
  avg_hr: number | null;
  min_spo2: number | null;
  stages: SleepStages | null;
}

export interface WorkoutEntry {
  id: number;
  workout_type: string;
  start_time: string;
  end_time: string | null;
  duration_min: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_hrv: number | null;
  effort_score: number | null;
  recovery_cost: number | null;
}

export interface RecoveryData {
  recovery_score: number | null;
  readiness: "high" | "moderate" | "low" | null;
  factors: string[];
  recommendation: string;
}

export async function fetchWorkouts(days = 7): Promise<WorkoutEntry[]> {
  try {
    const res = await fetch(`${SERVER_URL}/api/workouts?days=${days}`, {
      headers: { "X-Server-Secret": SERVER_SECRET },
    });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function fetchRecovery(): Promise<RecoveryData | null> {
  try {
    const res = await fetch(`${SERVER_URL}/api/recovery`, {
      headers: { "X-Server-Secret": SERVER_SECRET },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchSleepScores(days = 7): Promise<SleepScoreEntry[]> {
  try {
    const res = await fetch(`${SERVER_URL}/api/sleep/scores?days=${days}`, {
      headers: { "X-Server-Secret": SERVER_SECRET },
    });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export interface MetricsPayload {
  heart_rate?: number;
  hrv_rmssd?: number;
  timestamp?: string;
}

export async function postMetrics(payload: MetricsPayload): Promise<boolean> {
  try {
    const res = await fetch(`${SERVER_URL}/api/metrics`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Server-Secret": SERVER_SECRET },
      body: JSON.stringify(payload),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// Post all unsynced readings to the server and return the IDs that succeeded.
export async function syncReadings(readings: StoredReading[]): Promise<string[]> {
  if (readings.length === 0) return [];
  const synced: string[] = [];
  // Post each reading; if the server returns ok, record as synced.
  // Uses Promise.allSettled so one failure doesn't block the rest.
  const results = await Promise.allSettled(
    readings.map(async (r) => {
      const ok = await postMetrics({
        heart_rate: r.heartRate ?? undefined,
        hrv_rmssd: r.hrv ?? undefined,
        timestamp: r.timestamp,
      });
      return ok ? r.id : null;
    })
  );
  results.forEach((result) => {
    if (result.status === "fulfilled" && result.value) synced.push(result.value);
  });
  return synced;
}
