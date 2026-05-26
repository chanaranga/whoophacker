import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Dimensions,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { LineChart } from "react-native-chart-kit";
import { connectToWhoop, getCurrentRmssd, disconnectWhoop, HealthReading } from "./BleManager";
import { syncReadings, fetchSleepScores, fetchWorkouts, fetchRecovery, SleepScoreEntry, WorkoutEntry, RecoveryData } from "./ServerSync";
import { registerBackgroundSync, addReading } from "./BackgroundTask";
import { getHourlyPoints, getUnsynced, markSynced, HourlyPoint } from "./DataStore";

const SCREEN_W = Dimensions.get("window").width;
const CHART_W = SCREEN_W - 32;

const CHART_CONFIG = {
  backgroundGradientFrom: "#f5f5f5",
  backgroundGradientTo: "#f5f5f5",
  color: (opacity = 1) => `rgba(220, 38, 38, ${opacity})`,
  labelColor: () => "#666",
  strokeWidth: 2,
  propsForDots: { r: "3" },
};

const HRV_CHART_CONFIG = {
  ...CHART_CONFIG,
  color: (opacity = 1) => `rgba(37, 99, 235, ${opacity})`,
};

const NIGHTLY_HRV_CHART_CONFIG = {
  ...CHART_CONFIG,
  color: (opacity = 1) => `rgba(124, 58, 237, ${opacity})`,
};

export default function App() {
  const [status, setStatus] = useState("Idle");
  const [connected, setConnected] = useState(false);
  const [lastReading, setLastReading] = useState<HealthReading | null>(null);
  const [hourlyPoints, setHourlyPoints] = useState<HourlyPoint[]>([]);
  const [sleepScores, setSleepScores] = useState<SleepScoreEntry[]>([]);
  const [workouts, setWorkouts] = useState<WorkoutEntry[]>([]);
  const [recovery, setRecovery] = useState<RecoveryData | null>(null);

  const lastReadingRef = useRef<HealthReading | null>(null);
  const syncInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const avgInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const readingBuffer = useRef<HealthReading[]>([]);

  const refreshCharts = useCallback(async () => {
    const [pts, scores, wkts, rec] = await Promise.all([
      getHourlyPoints(24),
      fetchSleepScores(7),
      fetchWorkouts(7),
      fetchRecovery(),
    ]);
    setHourlyPoints(pts);
    setSleepScores(scores);
    setWorkouts(wkts);
    setRecovery(rec);
  }, []);

  useEffect(() => {
    registerBackgroundSync();
    refreshCharts();
  }, [refreshCharts]);

  async function handleConnect() {
    setStatus("Scanning for WHOOP...");
    try {
      await connectToWhoop((reading) => {
        setLastReading(reading);
        lastReadingRef.current = reading;
        readingBuffer.current.push(reading);
      });
      setConnected(true);
      setStatus("Connected");

      // Every 30 s: average the buffer and store one record
      avgInterval.current = setInterval(async () => {
        const buf = readingBuffer.current.splice(0);
        if (buf.length === 0) return;
        const avg = (vals: (number | null)[]) => {
          const nums = vals.filter((v): v is number => v != null);
          return nums.length ? nums.reduce((s, v) => s + v, 0) / nums.length : null;
        };
        await addReading(
          Math.round(avg(buf.map((r) => r.heartRate)) ?? 0),
          null,
          getCurrentRmssd(),
          new Date().toISOString()
        );
      }, 30_000);

      // Sync every 3 minutes
      syncInterval.current = setInterval(async () => {
        const unsynced = await getUnsynced();
        if (unsynced.length === 0) return;
        const ids = await syncReadings(unsynced);
        if (ids.length > 0) {
          await markSynced(ids);
          setStatus(`Synced ${new Date().toLocaleTimeString()}`);
        } else {
          setStatus("Sync failed");
        }
        refreshCharts();
      }, 3 * 60 * 1000);
    } catch (err: any) {
      setStatus(`Error: ${err.message}`);
    }
  }

  function handleDisconnect() {
    disconnectWhoop();
    if (avgInterval.current) { clearInterval(avgInterval.current); avgInterval.current = null; }
    if (syncInterval.current) { clearInterval(syncInterval.current); syncInterval.current = null; }
    readingBuffer.current = [];
    setConnected(false);
    setStatus("Disconnected");
    setLastReading(null);
    lastReadingRef.current = null;
  }

  // Build chart datasets — fill null gaps with 0 so the chart doesn't crash
  const hrData = hourlyPoints.map((p) => p.hr ?? 0);
  const hrvData = hourlyPoints.map((p) => p.hrv ?? 0);
  const labels = hourlyPoints
    .map((p, i) => (i % 4 === 0 ? p.label : ""))
    .filter((_, i) => i % 4 === 0);
  const labelledIndices = hourlyPoints
    .map((_, i) => (i % 4 === 0 ? i : -1))
    .filter((i) => i >= 0);
  const xLabels = hourlyPoints.map((p, i) => (labelledIndices.includes(i) ? p.label : ""));

  const hasHRData = hrData.some((v) => v > 0);
  const hasHRVData = hrvData.some((v) => v > 0);

  // Nightly HRV — reverse so chart runs oldest → newest
  const nightlyScores = [...sleepScores].reverse();
  const nightlyHrvData = nightlyScores.map((s) => s.avg_hrv ?? 0);
  const nightlyLabels = nightlyScores.map((s) =>
    new Date(s.start_time).toLocaleDateString(undefined, { weekday: "short" })
  );
  const hasNightlyHrv = nightlyHrvData.some((v) => v > 0);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>WHOOP Collector</Text>
      <Text style={styles.statusText}>{status}</Text>

      {/* Recovery widget */}
      {recovery?.recovery_score != null && (
        <View style={[styles.recoveryCard, { borderLeftColor: scoreColor(recovery.recovery_score) }]}>
          <View style={styles.recoveryRow}>
            <Text style={styles.recoveryLabel}>Recovery</Text>
            <Text style={[styles.recoveryScore, { color: scoreColor(recovery.recovery_score) }]}>
              {recovery.recovery_score}
            </Text>
            <Text style={styles.recoveryReadiness}>{recovery.readiness?.toUpperCase()}</Text>
          </View>
          {recovery.recommendation ? (
            <Text style={styles.recoveryRec}>{recovery.recommendation}</Text>
          ) : null}
        </View>
      )}

      {/* Current values */}
      {lastReading && (
        <View style={styles.card}>
          <View style={styles.row}>
            <Metric label="HR" value={`${lastReading.heartRate ?? "—"}`} unit="bpm" color="#dc2626" />
            <Metric label="HRV" value={getCurrentRmssd()?.toFixed(1) ?? "—"} unit="ms" color="#2563eb" />
          </View>
          <Text style={styles.ts}>{new Date(lastReading.timestamp).toLocaleTimeString()}</Text>
        </View>
      )}

      {/* Heart rate chart */}
      <Text style={styles.chartTitle}>Heart Rate — last 24 h (bpm)</Text>
      {hasHRData ? (
        <LineChart
          data={{ labels: xLabels, datasets: [{ data: hrData }] }}
          width={CHART_W}
          height={160}
          chartConfig={CHART_CONFIG}
          bezier
          withDots={false}
          withInnerLines={false}
          style={styles.chart}
        />
      ) : (
        <View style={[styles.chart, styles.placeholder]}>
          <Text style={styles.placeholderText}>No HR data yet</Text>
        </View>
      )}

      {/* HRV chart */}
      <Text style={styles.chartTitle}>HRV (RMSSD) — last 24 h (ms)</Text>
      {hasHRVData ? (
        <LineChart
          data={{ labels: xLabels, datasets: [{ data: hrvData }] }}
          width={CHART_W}
          height={160}
          chartConfig={HRV_CHART_CONFIG}
          bezier
          withDots={false}
          withInnerLines={false}
          style={styles.chart}
        />
      ) : (
        <View style={[styles.chart, styles.placeholder]}>
          <Text style={styles.placeholderText}>No HRV data yet</Text>
        </View>
      )}

      {/* Nightly HRV chart */}
      <Text style={styles.chartTitle}>Nightly HRV — last 7 nights (ms)</Text>
      {hasNightlyHrv ? (
        <LineChart
          data={{ labels: nightlyLabels, datasets: [{ data: nightlyHrvData }] }}
          width={CHART_W}
          height={160}
          chartConfig={NIGHTLY_HRV_CHART_CONFIG}
          bezier
          withDots={true}
          withInnerLines={false}
          style={styles.chart}
        />
      ) : (
        <View style={[styles.chart, styles.placeholder]}>
          <Text style={styles.placeholderText}>No nightly HRV data yet</Text>
        </View>
      )}

      {/* Recent workouts */}
      <Text style={styles.chartTitle}>Recent Workouts</Text>
      {workouts.length === 0 ? (
        <View style={[styles.chart, styles.placeholder]}>
          <Text style={styles.placeholderText}>No workouts yet — tell the agent when you start one</Text>
        </View>
      ) : (
        <View style={styles.sleepList}>
          {workouts.map((w) => <WorkoutRow key={w.id} entry={w} />)}
        </View>
      )}

      {/* Recent sleep scores */}
      <Text style={styles.chartTitle}>Recent Sleep</Text>
      {sleepScores.length === 0 ? (
        <View style={[styles.chart, styles.placeholder]}>
          <Text style={styles.placeholderText}>No sleep sessions yet</Text>
        </View>
      ) : (
        <View style={styles.sleepList}>
          {sleepScores.map((s) => (
            <SleepRow key={s.id} entry={s} />
          ))}
        </View>
      )}

      <View style={styles.buttonRow}>
        {!connected ? (
          <Button title="Connect to WHOOP" onPress={handleConnect} />
        ) : (
          <Button title="Disconnect" onPress={handleDisconnect} color="#cc0000" />
        )}
      </View>
    </ScrollView>
  );
}

function scoreColor(score: number | null): string {
  if (score == null) return "#9ca3af";
  if (score >= 80) return "#16a34a";
  if (score >= 60) return "#d97706";
  return "#dc2626";
}

function WorkoutRow({ entry }: { entry: WorkoutEntry }) {
  const date = new Date(entry.start_time);
  const label = date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const h = entry.duration_min ? Math.floor(entry.duration_min / 60) : null;
  const m = entry.duration_min ? entry.duration_min % 60 : null;
  const dur = h != null ? (h > 0 ? `${h}h ${m}m` : `${m}m`) : "—";
  const effortColor = scoreColor(entry.effort_score);

  return (
    <View style={styles.sleepRow}>
      <View style={styles.sleepRowTop}>
        <Text style={styles.sleepDate}>{entry.workout_type.charAt(0).toUpperCase() + entry.workout_type.slice(1)}  {label}</Text>
        <View style={styles.sleepRight}>
          {entry.effort_score != null && (
            <Text style={[styles.sleepScore, { color: effortColor }]}>{entry.effort_score}</Text>
          )}
          <Text style={styles.sleepDur}>{dur}</Text>
        </View>
      </View>
      {(entry.avg_hr != null || entry.max_hr != null) && (
        <Text style={styles.sleepStages}>
          {entry.avg_hr != null ? `Avg HR ${entry.avg_hr} bpm` : ""}
          {entry.max_hr != null ? `  Peak ${entry.max_hr} bpm` : ""}
          {entry.recovery_cost != null ? `  Cost ${entry.recovery_cost}/100` : ""}
        </Text>
      )}
    </View>
  );
}

function SleepRow({ entry }: { entry: SleepScoreEntry }) {
  const date = new Date(entry.start_time);
  const label = date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const h = entry.duration_min ? Math.floor(entry.duration_min / 60) : null;
  const m = entry.duration_min ? entry.duration_min % 60 : null;
  const dur = h != null ? `${h}h ${m}m` : "—";
  const color = scoreColor(entry.sleep_score);
  const s = entry.stages;

  return (
    <View style={styles.sleepRow}>
      <View style={styles.sleepRowTop}>
        <Text style={styles.sleepDate}>{label}</Text>
        <View style={styles.sleepRight}>
          {entry.sleep_score != null && (
            <Text style={[styles.sleepScore, { color }]}>{entry.sleep_score}</Text>
          )}
          {entry.sleep_score == null && (
            <Text style={[styles.sleepScore, { color }]}>—</Text>
          )}
          <Text style={styles.sleepDur}>{dur}</Text>
          {entry.avg_hrv != null && (
            <Text style={styles.sleepHrv}>HRV {entry.avg_hrv.toFixed(0)}ms</Text>
          )}
        </View>
      </View>
      {s && (s.deep_pct != null || s.rem_pct != null) && (
        <Text style={styles.sleepStages}>
          {s.deep_pct != null ? `Deep ${s.deep_pct}%` : ""}
          {s.rem_pct != null ? `  REM ${s.rem_pct}%` : ""}
          {s.light_pct != null ? `  Light ${s.light_pct}%` : ""}
        </Text>
      )}
    </View>
  );
}

function Metric({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
      <Text style={styles.metricUnit}>{unit}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", paddingVertical: 48, paddingHorizontal: 16 },
  title: { fontSize: 22, fontWeight: "bold", marginBottom: 4 },
  statusText: { fontSize: 13, color: "#666", marginBottom: 20 },
  card: {
    backgroundColor: "#f5f5f5",
    borderRadius: 14,
    padding: 16,
    width: "100%",
    marginBottom: 24,
  },
  row: { flexDirection: "row", justifyContent: "space-around", marginBottom: 8 },
  metric: { alignItems: "center", flex: 1 },
  metricLabel: { fontSize: 12, color: "#888", marginBottom: 2 },
  metricValue: { fontSize: 26, fontWeight: "700" },
  metricUnit: { fontSize: 12, color: "#888" },
  ts: { textAlign: "center", fontSize: 11, color: "#bbb", marginTop: 4 },
  chartTitle: { alignSelf: "flex-start", fontSize: 13, fontWeight: "600", color: "#444", marginBottom: 4 },
  chart: { borderRadius: 10, marginBottom: 20 },
  placeholder: {
    width: CHART_W,
    height: 160,
    backgroundColor: "#f5f5f5",
    justifyContent: "center",
    alignItems: "center",
  },
  placeholderText: { color: "#bbb", fontSize: 13 },
  buttonRow: { marginTop: 8 },
  recoveryCard: {
    width: "100%",
    backgroundColor: "#f5f5f5",
    borderRadius: 12,
    borderLeftWidth: 4,
    padding: 12,
    marginBottom: 16,
  },
  recoveryRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  recoveryLabel: { fontSize: 13, color: "#666", flex: 1 },
  recoveryScore: { fontSize: 26, fontWeight: "700" },
  recoveryReadiness: { fontSize: 11, fontWeight: "600", color: "#888" },
  recoveryRec: { fontSize: 12, color: "#555", marginTop: 6 },
  sleepList: { width: "100%", marginBottom: 20 },
  sleepRow: {
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
  },
  sleepRowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sleepDate: { fontSize: 13, fontWeight: "600", color: "#333" },
  sleepRight: { flexDirection: "row", alignItems: "center", gap: 10 },
  sleepScore: { fontSize: 18, fontWeight: "700" },
  sleepDur: { fontSize: 12, color: "#666" },
  sleepHrv: { fontSize: 12, color: "#2563eb" },
  sleepStages: { fontSize: 11, color: "#888", marginTop: 4 },
});
