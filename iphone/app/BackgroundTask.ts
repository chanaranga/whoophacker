import * as BackgroundFetch from "expo-background-fetch";
import * as TaskManager from "expo-task-manager";
import { connectToWhoop, getCurrentRmssd, disconnectWhoop } from "./BleManager";
import { postMetrics } from "./ServerSync";

const TASK_NAME = "whoop-background-sync";
const SYNC_INTERVAL_SECS = 300; // 5 minutes

// Buffer for readings collected during this background window
const pendingReadings: Array<{ hr: number; rr: number | null; ts: string }> = [];

TaskManager.defineTask(TASK_NAME, async () => {
  try {
    const readings = [...pendingReadings];
    pendingReadings.length = 0;

    if (readings.length === 0) {
      return BackgroundFetch.BackgroundFetchResult.NoData;
    }

    const avgHr = Math.round(readings.reduce((s, r) => s + (r.hr ?? 0), 0) / readings.length);
    const rmssd = getCurrentRmssd();

    await postMetrics({
      heart_rate: avgHr,
      hrv_rmssd: rmssd ?? undefined,
      timestamp: new Date().toISOString(),
    });

    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync(): Promise<void> {
  const status = await BackgroundFetch.getStatusAsync();
  if (
    status === BackgroundFetch.BackgroundFetchStatus.Restricted ||
    status === BackgroundFetch.BackgroundFetchStatus.Denied
  ) {
    console.warn("Background fetch is not available on this device");
    return;
  }
  await BackgroundFetch.registerTaskAsync(TASK_NAME, {
    minimumInterval: SYNC_INTERVAL_SECS,
    stopOnTerminate: false,
    startOnBoot: true,
  });
}

export function addReading(hr: number, rr: number | null, ts: string): void {
  pendingReadings.push({ hr, rr, ts });
}
