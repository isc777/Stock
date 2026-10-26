// 離線支援：網頁外殼預先快取；API 先走網路，失敗時用上次的資料
const VERSION = "stock-v1";
const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/vendor/chart.umd.min.js",
  "/static/icons/icon-192.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 只快取正常回應；被導向登入頁的回應不能存成首頁
const cacheable = (res) => res && res.ok && !res.redirected && res.type === "basic";

async function networkFirst(request) {
  const cache = await caches.open(VERSION);
  try {
    const res = await fetch(request);
    if (cacheable(res)) cache.put(request, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: request.mode === "navigate" });
    if (cached) return cached;
    if (request.mode === "navigate") return (await cache.match("/")) || Response.error();
    return new Response(JSON.stringify({ error: "離線中，且沒有快取資料" }), {
      status: 503, headers: { "Content-Type": "application/json" },
    });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(request);
  const fresh = fetch(request).then((res) => {
    if (cacheable(res)) cache.put(request, res.clone());
    return res;
  }).catch(() => cached);
  return cached || fresh;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(staleWhileRevalidate(request));
  } else if (url.pathname.startsWith("/api/") || request.mode === "navigate") {
    event.respondWith(networkFirst(request));
  }
});
