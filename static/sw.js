// 離線支援：網頁外殼預先快取；資料（API 或 data/*.json）先走網路，失敗時用上次的資料。
// 路徑一律相對於 service worker 所在位置，才能同時用於伺服器（/）與 GitHub Pages（/Stock/）。
const VERSION = "stock-v2";
const BASE = new URL("./", self.location).pathname;
const SHELL = ["./", "static/icons/icon-192.png", "manifest.webmanifest"];

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

// 頁面上的 CSS/JS 帶有 ?v= 版本號，第一次載入時由 staleWhileRevalidate 存入快取

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
    if (request.mode === "navigate") return (await cache.match(BASE)) || Response.error();
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

// 頁面告知要離線保存的網址（含版本號的 CSS/JS 與各股資料），確保第一次開啟後就能離線使用
self.addEventListener("message", (event) => {
  const urls = (event.data && event.data.cache) || [];
  const own = urls.filter((u) => new URL(u, self.location).pathname.startsWith(BASE));
  // 逐一加入：單一檔案失敗（例如尚未收集的股票）不影響其他檔案
  event.waitUntil(caches.open(VERSION).then((c) => Promise.allSettled(own.map((u) => c.add(u)))));
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith(BASE)) return;
  const path = url.pathname.slice(BASE.length);
  if (path.startsWith("static/")) {
    event.respondWith(staleWhileRevalidate(request));
  } else if (path.startsWith("api/") || path.startsWith("data/") || request.mode === "navigate") {
    event.respondWith(networkFirst(request));
  }
});
