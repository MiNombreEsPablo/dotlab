// Presets seam, browser adapter: named styles kept in the browser's own storage (it can be full or switched off: that
// is said in a sentence). A preset is a style, not a picture: the engine decides what is kept (api.preset_entry).
//   list() -> names, sorted   get(name) -> label | null   save(name, label) -> the name it was kept under   delete(name)

const KEY = "dotlab:presets";

export function createPresets(engine) {
  const read = () => {
    try {
      const kept = JSON.parse(localStorage.getItem(KEY));
      return kept && typeof kept === "object" && !Array.isArray(kept) ? kept : {};
    } catch (_) {
      return {};
    }
  };
  const write = (kept) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(kept));
    } catch (_) {
      throw new Error("The browser wouldn't keep the preset (its storage is full or switched off).");
    }
  };
  return {
    async list() {
      return Object.keys(read()).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    },
    async get(name) {
      return read()[name] || null;
    },
    async save(name, label) {
      const entry = await engine.presetEntry(name, label);
      write({ ...read(), [entry.name]: entry.spec });
      return entry.name;
    },
    async delete(name) {
      const kept = read();
      delete kept[name];
      write(kept);
    },
  };
}
