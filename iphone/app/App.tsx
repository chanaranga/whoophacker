import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  Button,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { connectToWhoop, getCurrentRmssd, disconnectWhoop, HealthReading } from "./BleManager";
import { postMetrics } from "./ServerSync";
import { registerBackgroundSync, addReading } from "./BackgroundTask";

export default function App() {
  const [status, setStatus] = useState("Idle");
  const [lastReading, setLastReading] = useState<HealthReading | null>(null);
  const [connected, setConnected] = useState(false);
  const syncInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    registerBackgroundSync();
  }, []);

  async function handleConnect() {
    setStatus("Scanning for WHOOP...");
    try {
      await connectToWhoop((reading) => {
        setLastReading(reading);
        if (reading.heartRate) addReading(reading.heartRate, reading.rrIntervalMs, reading.timestamp);
      });
      setConnected(true);
      setStatus("Connected");

      // Sync to server every 5 minutes while foregrounded
      syncInterval.current = setInterval(async () => {
        if (!lastReading?.heartRate) return;
        await postMetrics({
          heart_rate: lastReading.heartRate,
          hrv_rmssd: getCurrentRmssd() ?? undefined,
          timestamp: new Date().toISOString(),
        });
      }, 5 * 60 * 1000);
    } catch (err: any) {
      setStatus(`Error: ${err.message}`);
    }
  }

  function handleDisconnect() {
    disconnectWhoop();
    if (syncInterval.current) clearInterval(syncInterval.current);
    setConnected(false);
    setStatus("Disconnected");
    setLastReading(null);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>WHOOP Collector</Text>
      <Text style={styles.status}>{status}</Text>

      {lastReading && (
        <View style={styles.card}>
          <Text style={styles.metric}>HR: {lastReading.heartRate} bpm</Text>
          {getCurrentRmssd() !== null && (
            <Text style={styles.metric}>HRV (RMSSD): {getCurrentRmssd()?.toFixed(1)} ms</Text>
          )}
          <Text style={styles.ts}>{lastReading.timestamp}</Text>
        </View>
      )}

      {!connected ? (
        <Button title="Connect to WHOOP" onPress={handleConnect} />
      ) : (
        <Button title="Disconnect" onPress={handleDisconnect} color="#cc0000" />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  title: { fontSize: 22, fontWeight: "bold", marginBottom: 16 },
  status: { fontSize: 14, color: "#555", marginBottom: 24 },
  card: {
    backgroundColor: "#f5f5f5",
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
    width: "100%",
    alignItems: "center",
  },
  metric: { fontSize: 20, fontWeight: "600", marginBottom: 6 },
  ts: { fontSize: 11, color: "#999" },
});
