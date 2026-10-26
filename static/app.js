const $ = (sel) => document.querySelector(sel);
const api = async (path, opts = {}) => {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  if (res.status === 401) { location.href = "/login"; throw new Error("請先登入"); }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));
const sentTag = (v) => v >= 0.2 ? '<span class="tag pos">正面</span>' : v <= -0.2 ? '<span class="tag neg">負面</span>' : '<span class="tag neu">中性</span>';
const localTime = (utc) => utc ? new Date(utc.replace(" ", "T") + "Z").toLocaleString("zh-TW", { hour12: false }) : "";

let selected = null;
let charts = {};

async function loadRecommendations() {
  const recs = await api("/api/recommendations");
  const watch = await api("/api/watchlist");
  const tbody = $("#rec-table tbody");
  const have = new Set(recs.map((r) => r.symbol));
  const pending = watch.filter((w) => !have.has(w.symbol));
  $("#empty").classList.toggle("hidden", recs.length + pending.length > 0);

  tbody.innerHTML = recs.map((r) => `
    <tr data-symbol="${esc(r.symbol)}" class="${r.symbol === selected ? "active" : ""}">
      <td class="c-name"><span class="sym">${esc(r.symbol)}</span><span class="name">${esc(r.name)}</span></td>
      <td class="c-close num">${fmt(r.close)}</td>
      <td class="c-chg num ${r.change_pct >= 0 ? "up" : "down"}">${r.change_pct >= 0 ? "+" : ""}${fmt(r.change_pct)}%</td>
      <td class="c-score num"><span class="m-label">評分 </span>${fmt(r.score, 1)}<span class="score-bar"><i style="width:${r.score}%"></i></span></td>
      <td class="c-rating"><span class="rating ${r.rating_code}">${r.rating}</span></td>
      <td class="c-sent num">${r.news_sentiment == null ? "—" : sentTag(r.news_sentiment) + fmt(r.news_sentiment)}</td>
      <td class="c-act"><button class="link remove" data-remove="${esc(r.symbol)}" aria-label="將 ${esc(r.symbol)} 移出觀察清單">✕</button></td>
    </tr>`).join("") + pending.map((w) => `
    <tr data-symbol="${esc(w.symbol)}">
      <td class="c-name"><span class="sym">${esc(w.symbol)}</span><span class="name">${esc(w.name)}</span></td>
      <td colspan="5" class="c-pending muted">資料收集中或不足…</td>
      <td class="c-act"><button class="link remove" data-remove="${esc(w.symbol)}" aria-label="將 ${esc(w.symbol)} 移出觀察清單">✕</button></td>
    </tr>`).join("");
}

async function loadDetail(symbol) {
  selected = symbol;
  document.querySelectorAll("#rec-table tbody tr").forEach((tr) => tr.classList.toggle("active", tr.dataset.symbol === symbol));
  let d;
  try { d = await api(`/api/stocks/${encodeURIComponent(symbol)}`); } catch (e) { return alert(e.message); }
  $("#detail").classList.remove("hidden");
  $("#d-title").textContent = `${d.symbol} ${d.name || ""}`;
  const r = d.recommendation;
  $("#d-rating").className = `rating ${r ? r.rating_code : "hold"}`;
  $("#d-rating").textContent = r ? `${r.rating} · ${r.score} 分` : "資料不足";

  const max = { trend: 30, momentum: 20, rsi: 15, macd: 15, sentiment: 20 };
  const labels = { trend: "趨勢", momentum: "動能", rsi: "RSI", macd: "MACD", sentiment: "新聞情緒" };
  $("#d-breakdown").innerHTML = r ? Object.keys(max).map((k) => [k, r.breakdown[k]]).map(([k, v]) => `
    <div class="bd-row"><span>${labels[k]}</span><span class="bar"><i style="width:${(v / max[k]) * 100}%"></i></span><span class="num">${v}/${max[k]}</span></div>`).join("") : "";
  $("#d-reasons").innerHTML = r ? r.reasons.map((x) => `<li>${esc(x)}</li>`).join("") : "";
  $("#d-ind").innerHTML = r ? `
    <dt>MA20</dt><dd>${fmt(r.indicators.ma20)}</dd><dt>MA60</dt><dd>${fmt(r.indicators.ma60)}</dd>
    <dt>RSI(14)</dt><dd>${fmt(r.indicators.rsi14, 1)}</dd><dt>MACD 柱</dt><dd>${fmt(r.indicators.macd_hist, 3)}</dd>
    <dt>年化波動</dt><dd>${r.indicators.volatility20 == null ? "—" : fmt(r.indicators.volatility20 * 100, 1) + "%"}</dd>` : "";

  renderNews($("#d-news"), d.news, false);
  drawCharts(d.series);
  $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function drawCharts(s) {
  Object.values(charts).forEach((c) => c.destroy());
  charts = {};
  if (typeof Chart === "undefined") return; // 圖表函式庫載入失敗時，其餘功能照常運作
  const css = getComputedStyle(document.documentElement);
  const color = (v) => css.getPropertyValue(v).trim();
  const grid = { color: color("--border") };
  const narrow = window.innerWidth < 640;
  const ticks = { color: color("--muted"), maxTicksLimit: narrow ? 4 : 8, maxRotation: 0 };
  const common = { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { color: color("--muted"), boxWidth: 12 } } }, elements: { point: { radius: 0 } } };
  charts.price = new Chart($("#price-chart"), {
    type: "line",
    data: { labels: s.date, datasets: [
      { label: "收盤", data: s.close, borderColor: color("--accent"), borderWidth: 2 },
      { label: "MA20", data: s.ma20, borderColor: color("--buy"), borderWidth: 1.2 },
      { label: "MA60", data: s.ma60, borderColor: color("--hold"), borderWidth: 1.2 },
    ] },
    options: { ...common, scales: { x: { grid, ticks }, y: { grid, ticks } } },
  });
  charts.rsi = new Chart($("#rsi-chart"), {
    type: "line",
    data: { labels: s.date, datasets: [{ label: "RSI(14)", data: s.rsi14, borderColor: color("--strong-buy"), borderWidth: 1.2 }] },
    options: { ...common, scales: { x: { display: false }, y: { min: 0, max: 100, grid, ticks: { ...ticks, stepSize: 30 } } } },
  });
}

function renderNews(el, items, showSymbol) {
  el.innerHTML = items.length ? items.map((n) => `
    <li>${sentTag(n.sentiment)}${showSymbol ? `<b>${esc(n.symbol)}</b> ` : ""}<a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      <div class="meta">${esc(n.publisher || "")} · ${esc(n.source)} · ${localTime(n.published)}</div></li>`).join("")
    : '<li class="muted">尚無新聞</li>';
}

async function loadNews() {
  renderNews($("#all-news"), await api("/api/news?limit=30"), true);
}

async function loadStatus() {
  const s = await api("/api/status");
  const last = s.last_run;
  let text = s.collecting ? "收集中…" : last ? `上次收集：${localTime(last.finished_at)}（+${last.news_added} 則新聞）` : "尚未收集";
  if (s.interval_min > 0) text += ` · 每 ${s.interval_min} 分鐘自動收集`;
  if (last && last.errors) text += " · ⚠ 部分來源失敗";
  $("#status").textContent = text;
  $("#status").title = last?.errors || "";
}

async function refreshAll() {
  await Promise.all([loadRecommendations(), loadNews(), loadStatus()]);
}

$("#rec-table").addEventListener("click", async (e) => {
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    e.stopPropagation();
    if (!confirm(`將 ${rm.dataset.remove} 移出觀察清單？`)) return;
    await api(`/api/watchlist/${encodeURIComponent(rm.dataset.remove)}`, { method: "DELETE" });
    if (selected === rm.dataset.remove) $("#detail").classList.add("hidden");
    return loadRecommendations();
  }
  const tr = e.target.closest("tr[data-symbol]");
  if (tr) loadDetail(tr.dataset.symbol);
});

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/watchlist", { method: "POST", body: JSON.stringify({ symbol: $("#add-symbol").value, name: $("#add-name").value }) });
    e.target.reset();
    await loadRecommendations();
    setTimeout(refreshAll, 4000);
  } catch (err) { alert(err.message); }
});

$("#collect-btn").addEventListener("click", async () => {
  const btn = $("#collect-btn");
  btn.disabled = true; btn.textContent = "收集中…";
  try { await api("/api/collect", { method: "POST", body: "{}" }); }
  catch (err) { alert(err.message); }
  finally { btn.disabled = false; btn.textContent = "立即收集"; }
  await refreshAll();
  if (selected) loadDetail(selected);
});

function updateOnline() {
  $("#offline").classList.toggle("hidden", navigator.onLine);
  $("#collect-btn").disabled = !navigator.onLine;
}
window.addEventListener("online", () => { updateOnline(); refreshAll(); });
window.addEventListener("offline", updateOnline);
updateOnline();

// 從背景切回 App 時（手機常見）自動更新
document.addEventListener("visibilitychange", () => { if (!document.hidden && navigator.onLine) refreshAll(); });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch((err) => console.warn("service worker:", err));
}

refreshAll();
setInterval(() => { if (navigator.onLine) loadStatus(); }, 30000);
setInterval(() => { if (navigator.onLine) refreshAll(); }, 5 * 60000);
