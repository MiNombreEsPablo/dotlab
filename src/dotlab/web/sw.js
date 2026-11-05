// Service worker: remembers what makes the first visit slow, so later visits start fast and work without a network.
//   - Pyodide (the Python runtime, from the jsDelivr CDN, one fixed version per site build), the bundled fonts and the
//     pinned qrcode wheel never change under the same URL: answered from the cache, fetched once.
//   - The page itself (html, css, js, the engine's Python files, the manifest) is network first, so an update arrives on
//     the next visit and is never mixed with old files; the cache is only the fallback when there is no network.
// It touches nothing else (other origins, non-GET requests) and keeps one cache.

const CACHE = "dotlab-runtime-v1";
const CDN = "https://cdn.jsdelivr.net";

const isCdnPyodide = (url) => url.origin === CDN && url.pathname.startsWith("/pyodide/");
const isImmutable = (url) =>
  isCdnPyodide(url) || (url.origin === location.origin && (url.pathname.includes("/fonts/") || url.pathname.includes("/engine/wheels/")));
const pyodideVersion = (url) => (url.pathname.match(/^\/pyodide\/(v[^/]+)\//) || [])[1];

// `copy` is a clone taken before the page gets the response: once the page reads the body, it can't be cloned any more.
async function keep(request, copy) {
  if (copy.status !== 200) return; // never keep a partial or failed answer
  const cache = await caches.open(CACHE);
  await cache.put(request, copy);
  const version = pyodideVersion(new URL(request.url));
  if (version) { // a newer Pyodide replaces the old one instead of piling up beside it
    for (const other of await cache.keys()) {
      const url = new URL(other.url);
      if (isCdnPyodide(url) && pyodideVersion(url) !== version) await cache.delete(other);
    }
  }
}

async function cacheFirst(request, event) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  event.waitUntil(keep(request, response.clone()).catch(() => {}));
  return response;
}

async function networkFirst(request, event) {
  try {
    const response = await fetch(request, { cache: "no-cache" }); // revalidate: a 304 costs nothing
    event.waitUntil(keep(request, response.clone()).catch(() => {}));
    return response;
  } catch (error) {
    const hit = await caches.match(request);
    if (hit) return hit;
    throw error;
  }
}

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) if (name !== CACHE) await caches.delete(name);
    await self.clients.claim(); // the page that registered us is served by us from now on
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin && !isCdnPyodide(url)) return;
  event.respondWith(isImmutable(url) ? cacheFirst(request, event) : networkFirst(request, event));
});
