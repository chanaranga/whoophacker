import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "health_readings_v1";
const RETENTION_MS = 72 * 60 * 60 * 1000;

export interface StoredReading {
  id: string;
  timestamp: string;
  heartRate: number | null;
  hrv: number | null;
  synced: boolean;
}

export interface HourlyPoint {
  label: string; // "HH:00"
  hr: number | null;
  hrv: number | null;
}

async function load(): Promise<StoredReading[]> {
  const raw = await AsyncStorage.getItem(KEY);
  return raw ? JSON.parse(raw) : [];
}

async function persist(readings: StoredReading[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(readings));
}

export async function storeReading(r: Omit<StoredReading, "id" | "synced">): Promise<void> {
  const readings = await load();
  readings.push({ ...r, id: r.timestamp, synced: false });
  await persist(readings);
}


export async function getUnsynced(): Promise<StoredReading[]> {
  const readings = await load();
  return readings.filter((r) => !r.synced);
}

export async function markSynced(ids: string[]): Promise<void> {
  const set = new Set(ids);
  const readings = await load();
  readings.forEach((r) => { if (set.has(r.id)) r.synced = true; });
  // prune: only remove readings older than 72 hrs that are already synced
  const cutoff = Date.now() - RETENTION_MS;
  const kept = readings.filter((r) => {
    const age = new Date(r.timestamp).getTime();
    return age > cutoff || !r.synced;
  });
  await persist(kept);
}

export async function getHourlyPoints(hoursBack = 24): Promise<HourlyPoint[]> {
  const readings = await load();
  const now = Date.now();
  const cutoff = now - hoursBack * 3600_000;

  const buckets: Record<string, { hrs: number[]; hrvs: number[] }> = {};
  readings
    .filter((r) => new Date(r.timestamp).getTime() >= cutoff)
    .forEach((r) => {
      const d = new Date(r.timestamp);
      const key = `${d.getHours().toString().padStart(2, "0")}:00`;
      if (!buckets[key]) buckets[key] = { hrs: [], hrvs: [] };
      if (r.heartRate) buckets[key].hrs.push(r.heartRate);
      if (r.hrv) buckets[key].hrvs.push(r.hrv);
    });

  const points: HourlyPoint[] = [];
  for (let i = hoursBack - 1; i >= 0; i--) {
    const d = new Date(now - i * 3600_000);
    const label = `${d.getHours().toString().padStart(2, "0")}:00`;
    const b = buckets[label];
    const avg = (arr: number[]) =>
      arr.length ? Math.round((arr.reduce((s, v) => s + v, 0) / arr.length) * 10) / 10 : null;
    points.push({ label, hr: b ? avg(b.hrs) : null, hrv: b ? avg(b.hrvs) : null });
  }
  return points;
}
