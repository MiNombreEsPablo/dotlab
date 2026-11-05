// Printer seam, browser adapter: print over classic Bluetooth serial (RFCOMM) with Web Serial. Chrome and Edge on desktop,
// including Linux, where Web Bluetooth (BLE) cannot reach this printer. The printer must be paired in the system's
// Bluetooth settings once; after that the browser lists it. Android Chrome has no Web Serial: it uses printer/ble.js.
// The service id, chunk size and gap come from the engine's options (src/dotlab/bluetooth.py).
//   modes: string[]   print(spec) -> {problems: string[], error: string|null}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function step(name, ms, promise) {
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Bluetooth stopped at "${name}" (no answer after ${ms / 1000} s).`)), ms);
  });
  return Promise.race([promise, deadline]).finally(() => clearTimeout(timer));
}

export const serialAvailable = () => !!(navigator.serial && window.isSecureContext);

export function createSerialPrinter(engine, options) {
  const { serial, status_query: statusQuery } = options.bluetooth;
  let port = null;
  let busy = Promise.resolve(); // one print at a time

  const isPrinter = (p) => (p.getInfo().bluetoothServiceClassId || "").toLowerCase() === serial.service;

  async function open() {
    if (port) return;
    // a printer this page was allowed to use before opens without asking again; otherwise ask (this needs the click)
    let chosen = (await navigator.serial.getPorts()).find(isPrinter);
    const remembered = !!chosen;
    if (!chosen) {
      try {
        chosen = await navigator.serial.requestPort({ filters: [{ bluetoothServiceClassId: serial.service }] });
      } catch (e) {
        if (e.name === "NotFoundError") {
          throw new Error("No printer chosen. If the list was empty, pair the printer in your system's Bluetooth settings first (it appears here only once paired), then print again.");
        }
        throw e;
      }
    }
    try {
      await step("connecting to the printer", 20000, chosen.open({ baudRate: 9600 }));
    } catch (e) {
      if (remembered && chosen.forget) await chosen.forget().catch(() => {}); // next print asks again, in case it is another printer
      throw new Error(`Couldn't connect to the printer (${e.message || e.name}). Switch it on, make sure no phone is connected to it, and print again. If it keeps failing, disconnect it in your system's Bluetooth settings (a link left over from a closed page can block it).`);
    }
    port = chosen;
  }

  async function close() {
    const p = port;
    port = null;
    if (p) await p.close().catch(() => {});
  }

  async function write(bytes) {
    const writer = port.writable.getWriter();
    try {
      for (let i = 0; i < bytes.length; i += serial.chunk) {
        await step("sending the label", 10000, writer.write(bytes.slice(i, i + serial.chunk)));
        await sleep(serial.gap_ms);
      }
    } finally {
      writer.releaseLock();
    }
  }

  // The printer's status byte, or null when it doesn't answer (that is not an error). It may send a stale byte first,
  // so the last one received is the answer.
  async function status() {
    await write(Uint8Array.from(statusQuery));
    const reader = port.readable.getReader();
    const stop = setTimeout(() => reader.cancel().catch(() => {}), 1500);
    let last = null;
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && value.length) {
          last = value[value.length - 1];
          clearTimeout(stop);
          setTimeout(() => reader.cancel().catch(() => {}), 150); // anything else that follows straight away
        }
      }
    } catch (_) { /* a read error just means no answer */ }
    clearTimeout(stop);
    reader.releaseLock();
    return last;
  }

  async function printNow(spec) {
    const bytes = await engine.tspl(spec);
    await open(); // first, while the click still counts as a user gesture (the chooser needs it)
    try {
      await write(bytes);
    } catch (e) { // the link went away since the last print: reconnect once
      await close();
      await open();
      await write(bytes);
    }
    await sleep(300);
    const byte = await status();
    return { problems: byte === null ? [] : await engine.statusProblems(byte), error: null };
  }

  return {
    modes: ["Bluetooth (serial)"],
    print(spec) {
      const run = busy.then(() => printNow(spec)).catch(async (e) => {
        await close();
        return { problems: [], error: e.message || String(e) };
      });
      busy = run;
      return run;
    },
  };
}
