import { BleManager, Device, Characteristic, BleError } from "react-native-ble-plx";
import { Buffer } from "buffer";

const HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb";
const HR_CHAR = "00002a37-0000-1000-8000-00805f9b34fb";

// WHOOP 4.0 proprietary service (community reverse engineering)
const WHOOP_SERVICE = "61080001-8d6d-82b8-614a-1c8cb0f8dbbe";
const WHOOP_DATA_CHAR = "61080003-8d6d-82b8-614a-1c8cb0f8dbbe";

export interface HealthReading {
  heartRate: number | null;
  rrIntervalMs: number | null;
  spo2: number | null;
  skinTempC: number | null;
  timestamp: string;
}

const manager = new BleManager();
let connectedDevice: Device | null = null;
const rrBuffer: number[] = [];

// Latest SpO2 / skin temp from proprietary packets (updated when WHOOP sends them)
let latestSpo2: number | null = null;
let latestSkinTemp: number | null = null;

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

// Best-effort parser for WHOOP proprietary packets.
// WHOOP sends periodic sensor packets; structure is partially reverse-engineered.
// Byte 0 = packet type. Known types used by community:
//   0x07: extended vitals — bytes 1-2: SpO2 (uint16, /100), bytes 3-4: skin temp (int16, /100 °C)
// All others are silently ignored.
function parseWhoopPacket(data: string): void {
  const bytes = Buffer.from(data, "base64");
  if (bytes.length < 1) return;
  const type = bytes[0];

  if (type === 0x07 && bytes.length >= 5) {
    const rawSpo2 = bytes.readUInt16LE(1);
    const rawTemp = bytes.readInt16LE(3);
    if (rawSpo2 >= 7000 && rawSpo2 <= 10000) latestSpo2 = rawSpo2 / 100;
    if (rawTemp > -1000 && rawTemp < 5000) latestSkinTemp = rawTemp / 100;
  }
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
                  spo2: latestSpo2,
                  skinTempC: latestSkinTemp,
                  timestamp: new Date().toISOString(),
                });
              }
            );

            // WHOOP proprietary — SpO2 + skin temp (best-effort)
            d.monitorCharacteristicForService(
              WHOOP_SERVICE,
              WHOOP_DATA_CHAR,
              (err: BleError | null, char: Characteristic | null) => {
                if (err || !char?.value) return;
                parseWhoopPacket(char.value);
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
  latestSpo2 = null;
  latestSkinTemp = null;
  rrBuffer.length = 0;
}
