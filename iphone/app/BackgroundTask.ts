import * as BackgroundFetch from "expo-background-fetch";
import * as TaskManager from "expo-task-manager";
import { storeReading, getUnsynced, markSynced } from "./DataStore";
import { syncReadings } from "./ServerSync";

const TASK_NAME = "whoop-background-sync";

TaskManager.defineTask(TASK_NAME, async () => {
  try {
    const unsynced = await getUnsynced();
    if (unsynced.length === 0) return BackgroundFetch.BackgroundFetchResult.NoData;
    const syncedIds = await syncReadings(unsynced);
    if (syncedIds.length > 0) await markSynced(syncedIds);
    return syncedIds.length > 0
      ? BackgroundFetch.BackgroundFetchResult.NewData
      : BackgroundFetch.BackgroundFetchResult.Failed;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync(): Promise<void> {
  const status = await BackgroundFetch.getStatusAsync();
  if (
    status === BackgroundFetch.BackgroundFetchStatus.Restricted ||
    status === BackgroundFetch.BackgroundFetchStatus.Denied
  ) return;
  await BackgroundFetch.registerTaskAsync(TASK_NAME, {
    minimumInterval: 300,
    stopOnTerminate: false,
    startOnBoot: true,
  });
}

export async function addReading(
  hr: number,
  rr: number | null,
  hrv: number | null,
  timestamp: string
): Promise<void> {
  await storeReading({ timestamp, heartRate: hr, hrv });
}
