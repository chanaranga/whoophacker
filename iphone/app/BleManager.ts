import { BleManager, Device, Characteristic, BleError } from "react-native-ble-plx";
import { Buffer } from "buffer";

const HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb";
const HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb";

export interface HealthReading {
  heartRate: number | null;
  rrIntervalMs: number | null;
  timestamp: string;
}

const manager = new BleManager();
let connectedDevice: Device | null = null;
const rrBuffer: number[] = [];

function parseHRCharacteristic(data: string): { hr: number; rrs: number[] } {
  const bytes = Buffer.from(data, "base64");
  const flags = bytes[0];
  const hr16bit = (flags & 0x01) !== 0;
  const hr = hr16bit ? bytes.readUInt16LE(1) : bytes[1];

  const rrs: number[] = [];
  if ((flags & 0x10) !== 0) {
    // There may be multiple R-R values; each is 2 bytes (1/1024 s units → ms)
    let offset = hr16bit ? 3 : 2;
    while (offset + 2 <= bytes.length) {
      const rr = Math.round((bytes.readUInt16LE(offset) / 1024) * 1000);
      // Filter physiologically impossible values (< 300ms = 200bpm, > 2000ms = 30bpm)
      if (rr >= 300 && rr <= 2000) rrs.push(rr);
      offset += 2;
    }
  }
  return { hr, rrs };
}


function computeRmssd(intervals: number[]): number | null {
  if (intervals.length < 4) return null;
  // Use median (not mean) as reference so the threshold is unaffected by the
  // very outliers we're trying to remove.
  const sorted = [...intervals].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const clean = intervals.filter((v) => Math.abs(v - median) / median <= 0.25);
  if (clean.length < 2) return null;
  let sumSqDiff = 0;
  for (let i = 1; i < clean.length; i++) {
    const diff = clean[i] - clean[i - 1];
    sumSqDiff += diff * diff;
  }
  return Math.sqrt(sumSqDiff / (clean.length - 1));
}

export async function connectToWhoop(onReading: (r: HealthReading) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    manager.startDeviceScan(null, { allowDuplicates: false }, (error, device) => {
      if (error) { reject(error); return; }
      if (device?.name?.toUpperCase().includes("WHOOP")) {
        manager.stopDeviceScan();
        device
          .connect()
          .then((d) => d.discoverAllServicesAndCharacteristics())
          .then((d) => {
            connectedDevice = d;

            // Standard GATT heart rate + R-R
            d.monitorCharacteristicForService(
              HR_SERVICE,
              HR_CHAR,
              (err: BleError | null, char: Characteristic | null) => {
                if (err || !char?.value) return;
                const { hr, rrs } = parseHRCharacteristic(char.value);
                for (const rr of rrs) {
                  rrBuffer.push(rr);
                  if (rrBuffer.length > 60) rrBuffer.shift();
                }
                onReading({
                  heartRate: hr,
                  rrIntervalMs: rrs[rrs.length - 1] ?? null,
                  timestamp: new Date().toISOString(),
                });
              }
            );

            resolve();
          })
          .catch(reject);
      }
    });
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
  rrBuffer.length = 0;
}
