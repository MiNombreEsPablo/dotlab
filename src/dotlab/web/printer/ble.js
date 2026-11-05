// Printer seam, browser adapter: print over Web Bluetooth (Chrome/Edge/Opera on Android and desktop; not Safari, iOS
// or Firefox). The UUIDs, chunk size and gap come from the engine's options (src/dotlab/bluetooth.py), so nothing about
// the printer is repeated here.
//   modes: string[]   print(spec) -> {problems: string[], error: string|null}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Web Bluetooth calls can hang forever (Chromium on Linux does when BlueZ stalls), which leaves the page on "Printing...".
// Every step gets a deadline and a name, so the error says where it stopped.
function step(name, ms, promise) {
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Bluetooth stopped at "${name}" (no answer after ${ms / 1000} s).`)), ms);
  });
  return Promise.race([promise, deadline]).finally(() => clearTimeout(timer));
}

// Why navigator.bluetooth is missing, from what the page can tell. Chrome and Edge are not enough on Linux: Web Bluetooth
// is behind a flag there; it also needs a secure context (https or localhost).
function webBluetoothHelp() {
  const ua = navigator.userAgent;
  if (!window.isSecureContext) return "Web Bluetooth needs a secure page (https).";
  if (/Firefox\//.test(ua) || (/Safari\//.test(ua) && !/Chrome\/|Chromium\//.test(ua))) {
    return "This browser has no Web Bluetooth. Use Chrome or Edge.";
  }
  return "Web Bluetooth is not available in this browser. Use a current Chrome or Edge.";
}

// Chromium on Linux reports a failed GATT connection (BlueZ) as "Unknown error when connecting to the device". It is
// seen when the system already holds the printer over classic Bluetooth, or has a stale pairing for it.
function explain(e) {
  const message = e.message || String(e);
  if (e.name === "NetworkError" && /connect/i.test(message) && /Linux/.test(navigator.userAgent)) {
    return `${message} Try disconnecting or removing the printer in the system's Bluetooth settings (or "bluetoothctl remove <address>"), switch the printer off and on, and print again so the browser can pair it itself.`;
  }
  return message;
}

export function createPrinter(engine, options) {
  const { ble, name_prefix: namePrefix, status_query: statusQuery } = options.bluetooth;
  let device = null;
  let writeChar = null;
  let onStatus = null; // set while we wait for the printer's reply to a status query
  let busy = Promise.resolve(); // one print at a time: overlapping GATT writes fail

  const isConnected = () => device && device.gatt.connected && writeChar;

  async function connect() {
    if (!navigator.bluetooth) {
      const apple = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
      throw new Error(apple
        ? "iPhone and iPad browsers can't use Bluetooth (an Apple rule). Save the label as an image instead, or open this page in the Bluefy browser."
        : webBluetoothHelp());
    }
    if (!device) {
      device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix }],
        optionalServices: [ble.service],
      });
    }
    try {
      const server = await step("connecting to the printer", 20000, device.gatt.connect());
      const service = await step("finding the print service", 10000, server.getPrimaryService(ble.service));
      writeChar = await step("finding the write channel", 10000, service.getCharacteristic(ble.write));
      try {
        const notify = await step("finding the status channel", 10000, service.getCharacteristic(ble.notify));
        notify.addEventListener("characteristicvaluechanged", (event) => {
          if (onStatus) onStatus(event.target.value.getUint8(0));
        });
        await step("listening for the status", 5000, notify.startNotifications());
      } catch (e) {
        console.warn("T003: no status channel, printing without it:", e); // the label still prints; we just can't read problems
      }
    } catch (e) {
      disconnect(); // start clean next time instead of reusing a half-open connection
      throw e;
    }
  }

  function disconnect() {
    writeChar = null;
    if (device && device.gatt.connected) device.gatt.disconnect();
  }

  async function write(bytes) {
    for (let i = 0; i < bytes.length; i += ble.chunk) {
      const part = bytes.slice(i, i + ble.chunk);
      if (writeChar.properties.writeWithoutResponse) await step("sending the label", 10000, writeChar.writeValueWithoutResponse(part));
      else await step("sending the label", 10000, writeChar.writeValueWithResponse(part));
      await sleep(ble.gap_ms);
    }
  }

  // The printer's status byte, or null when it doesn't answer (that is not an error).
  async function status() {
    const reply = new Promise((resolve) => {
      onStatus = resolve;
      setTimeout(() => resolve(null), 1500);
    });
    await write(Uint8Array.from(statusQuery));
    const byte = await reply;
    onStatus = null;
    return byte;
  }

  async function printNow(spec) {
    if (!isConnected()) await connect(); // first, while the click still counts as a user gesture (the chooser needs it)
    try {
      await write(await engine.tspl(spec));
    } catch (e) {
      disconnect();
      throw e;
    }
    await sleep(300);
    const byte = await status();
    return { problems: byte === null ? [] : await engine.statusProblems(byte), error: null };
  }

  return {
    modes: ["Bluetooth LE"],
    print(spec) {
      const run = busy.then(() => printNow(spec)).catch((e) => ({
        problems: [],
        error: e.name === "NotFoundError" ? "No printer chosen." : explain(e),
      }));
      busy = run;
      return run;
    },
  };
}
