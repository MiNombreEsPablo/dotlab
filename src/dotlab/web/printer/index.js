// Printer seam, browser adapter: picks how this browser reaches the printer. Web Bluetooth (BLE, printer/ble.js) works on
// Android and on Windows and macOS; Web Serial over classic Bluetooth (printer/serial.js) works on desktop Chrome and Edge,
// and is the only way on Linux, where BlueZ cannot open this printer's BLE link.
//   modes: string[]   print(spec, {mode}) -> {problems: string[], error: string|null}
// With one way available the page shows no choice; with both, the choice is remembered and the default is chosen here.

import { createPrinter as createBle } from "./ble.js";
import { createSerialPrinter, serialAvailable } from "./serial.js";

export function createPrinter(engine, options) {
  const ble = createBle(engine, options);
  const printers = new Map();
  const linuxDesktop = /Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent);
  const hasBle = !!navigator.bluetooth;
  const hasSerial = serialAvailable();
  const serialFirst = hasSerial && (linuxDesktop || !hasBle);
  if (hasSerial) {
    const serial = createSerialPrinter(engine, options);
    printers.set(serial.modes[0], serial);
  }
  if (hasBle || !hasSerial) printers.set(ble.modes[0], ble); // with neither, BLE's own message explains what to use
  const modes = [...printers.keys()];
  if (!serialFirst && modes.length > 1) modes.reverse(); // serial was added first
  return {
    modes,
    print(spec, { mode } = {}) {
      return (printers.get(mode) || printers.get(modes[0])).print(spec);
    },
  };
}
