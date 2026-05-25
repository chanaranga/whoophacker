import { BleManager, Device, Characteristic, BleError } from "react-native-ble-plx";
import { Buffer } from "buffer";

// Standard GATT Heart Rate service / characteristic
const HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb";
const HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb";

// WHOOP proprietary service (from community reverse engineering)
// CMD_FROM_STRAP / DATA_FROM_STRAP — may vary by firmware version
const WHOOP_SERVICE = "61080001-8d6d-82b8-614a-1c8cb0f8dbbe";
const WHOOP_DATA_CHAR = "61080003-8d6d-82b8-614a-1c8cb0f8dbbe";

export interface HealthReading {
  heartRate: number | null;
  rrIntervalMs: number | null; // used to compute HRV RMSSD
  timestamp: string;
}

const manager = new BleManager();
let connectedDevice: Device | null = null;
const rrBuffer: number[] = []; // rolling window of R-R intervals

function parseHRCharacteristic(data: string): { hr: number; rr: number | null } {
  const bytes = Buffer.from(data, "base64");
  const flags = bytes[0];
  const hrFormat16bit = (flags & 0x01) !== 0;
  const hrValue = hrFormat16bit ? bytes.readUInt16LE(1) : bytes[1];

  // R-R interval (optional, 16-bit, in 1/1024 sec units)
  let rr: number | null = null;
  const rrPresent = (flags & 0x10) !== 0;
  if (rrPresent) {
    const rrOffset = hrFormat16bit ? 3 : 2;
    if (bytes.length >= rrOffset + 2) {
      const rrRaw = bytes.readUInt16LE(rrOffset);
      rr = Math.round((rrRaw / 1024) * 1000); // convert to ms
    }
  }

  return { hr: hrValue, rr };
}

function computeRmssd(intervals: number[]): number | null {
  if (intervals.length < 2) return null;
  let sumSqDiff = 0;
  for (let i = 1; i < intervals.length; i++) {
    const diff = intervals[i] - intervals[i - 1];
    sumSqDiff += diff * diff;
  }
  return Math.sqrt(sumSqDiff / (intervals.length - 1));
}

export async function connectToWhoop(
  onReading: (r: HealthReading) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    manager.startDeviceScan(null, { allowDuplicates: false }, (error, device) => {
      if (error) {
        reject(error);
        return;
      }
      if (device?.name?.toUpperCase().includes("WHOOP")) {
        manager.stopDeviceScan();
        device
          .connect()
          .then((d) => d.discoverAllServicesAndCharacteristics())
          .then((d) => {
            connectedDevice = d;
            d.monitorCharacteristicForService(
              HR_SERVICE,
              HR_CHAR,
              (err: BleError | null, char: Characteristic | null) => {
                if (err || !char?.value) return;
                const { hr, rr } = parseHRCharacteristic(char.value);
                if (rr !== null) rrBuffer.push(rr);
                if (rrBuffer.length > 30) rrBuffer.shift(); // keep last 30 intervals
                onReading({
                  heartRate: hr,
                  rrIntervalMs: rr,
                  timestamp: new Date().toISOString(),
                });
              }
            );
            resolve();
          })
          .catch(reject);
      }
    });
    // Time out scan after 15 seconds
    setTimeout(() => {
      manager.stopDeviceScan();
      reject(new Error("WHOOP device not found within 15 seconds"));
    }, 15000);
  });
}

export function getCurrentRmssd(): number | null {
  return computeRmssd(rrBuffer);
}

export function disconnectWhoop(): void {
  connectedDevice?.cancelConnection();
  connectedDevice = null;
}
