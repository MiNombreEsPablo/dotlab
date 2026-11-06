// Engine seam, browser adapter: the engine in the browser, answered by Pyodide in a worker.
//   init(onProgress)  options() -> object  preview(spec) -> {pixels: Uint8Array(W*H gray), hints: string[]}
//   tspl(spec) -> Uint8Array   addImage(bytes, name) -> path   exportPng(spec, scale) -> {data, name}
//   statusProblems(byte) -> string[]
// `spec` is a plain object (the label's JSON); the worker gets it as text.

export function createEngine(baseUrl) {
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  const pending = new Map();
  let nextId = 1;
  let onProgress = () => {};

  worker.onmessage = ({ data }) => {
    if (data.progress !== undefined) return onProgress(data.progress);
    const call = pending.get(data.id);
    pending.delete(data.id);
    if (data.error !== undefined) call.reject(new Error(data.error));
    else call.resolve(data.result);
  };

  const call = (method, args, transfer = []) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, method, args }, transfer);
    });

  return {
    async init(progress) {
      onProgress = progress || onProgress;
      await call("init", { baseUrl });
    },
    async options() {
      return JSON.parse(await call("options"));
    },
    preview: (spec) => call("preview", { spec: JSON.stringify(spec) }),
    // bytes of a picture the user chose -> the path to put in the label (rejects with a sentence if it isn't usable)
    addImage: (bytes, name) => call("addImage", { data: bytes, name }, [bytes.buffer]),
    // a label from before layers (an old preset, a remembered label) as the same label made of layers
    migrate: async (spec) => JSON.parse(await call("migrate", { spec: JSON.stringify(spec) })),
    // a preset to keep: {name, spec}
    presetEntry: async (name, spec) => JSON.parse(await call("presetEntry", { name, spec: JSON.stringify(spec) })),
    // the label as a label file, a PNG with the design inside ({data: Uint8Array, name}), and back from its bytes (-> the label as an object)
    compositionDumps: (spec) => call("compositionDumps", { spec: JSON.stringify(spec) }),
    compositionLoads: async (bytes) => JSON.parse(await call("compositionLoads", { data: bytes }, [bytes.buffer])),
    // the label as a PNG: {data: Uint8Array, name: "Neon Nights.png"}, at one of options.export.scales
    exportPng: (spec, scale) => call("exportPng", { spec: JSON.stringify(spec), scale }),
    tspl: (spec) => call("tspl", { spec: JSON.stringify(spec) }),
    statusProblems: (status) => call("statusProblems", { status }),
  };
}
