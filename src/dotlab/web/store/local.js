// Store seam, browser adapter: small remembered settings in localStorage. It can be unavailable (private windows,
// blocked site data), so every access is guarded and the page works without it.
//   get(key, fallback) -> value   set(key, value)

const PREFIX = "dotlab:";

export function createStore() {
  return {
    async get(key, fallback) {
      try {
        const raw = localStorage.getItem(PREFIX + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (_) {
        return fallback;
      }
    },
    async set(key, value) {
      try {
        localStorage.setItem(PREFIX + key, JSON.stringify(value));
      } catch (_) {
        /* not remembered; nothing else to do */
      }
    },
  };
}
