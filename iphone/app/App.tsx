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
import { syncReadings } from "./ServerSync";
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

export default function App() {
  const [status, setStatus] = useState("Idle");
  const [connected, setConnected] = useState(false);
  const [lastReading, setLastReading] = useState<HealthReading | null>(null);
  const [hourlyPoints, setHourlyPoints] = useState<HourlyPoint[]>([]);

  const lastReadingRef = useRef<HealthReading | null>(null);
  const syncInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const avgInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const readingBuffer = useRef<HealthReading[]>([]);

  const refreshCharts = useCallback(async () => {
    const pts = await getHourlyPoints(24);
    setHourlyPoints(pts);
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
          avg(buf.map((r) => r.spo2)),
          avg(buf.map((r) => r.skinTempC)),
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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>WHOOP Collector</Text>
      <Text style={styles.statusText}>{status}</Text>

      {/* Current values */}
      {lastReading && (
        <View style={styles.card}>
          <View style={styles.row}>
            <Metric label="HR" value={`${lastReading.heartRate ?? "—"}`} unit="bpm" color="#dc2626" />
            <Metric label="HRV" value={getCurrentRmssd()?.toFixed(1) ?? "—"} unit="ms" color="#2563eb" />
          </View>
          <View style={styles.row}>
            <Metric label="SpO₂" value={lastReading.spo2 != null ? `${lastReading.spo2.toFixed(1)}` : "—"} unit="%" color="#059669" />
            <Metric label="Skin" value={lastReading.skinTempC != null ? `${lastReading.skinTempC.toFixed(1)}` : "—"} unit="°C" color="#d97706" />
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
});
