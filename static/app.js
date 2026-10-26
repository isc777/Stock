const $ = (sel) => document.querySelector(sel);
// server：Flask API；static：GitHub Pages 上預先產生的 JSON 檔
const STATIC = (window.STOCK_CONFIG || {}).mode === "static";
const dataFile = (symbol) => symbol.replace(/[^A-Za-z0-9.\-]/g, "_");
const URLS = STATIC ? {
  recommendations: "data/recommendations.json",
  watchlist: "data/watchlist.json",
  stock: (s) => `data/stocks/${dataFile(s)}.json`,
  news: "data/news.json",
  status: "data/status.json",
} : {
  recommendations: "api/recommendations",
  watchlist: "api/watchlist",
  stock: (s) => `api/stocks/${encodeURIComponent(s)}`,
  news: "api/news?limit=30",
  status: "api/status",
};
const api = async (path, opts = {}) => {
  // no-cache：每次都向伺服器確認是否有新資料（沒變時只回 304，很省流量）
  const res = await fetch(path, { cache: "no-cache", headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 204) return null;
  if (res.status === 401) { location.href = "login"; throw new Error("請先登入"); }
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

const removeBtn = (symbol) =>
  `<button class="link remove" data-remove="${esc(symbol)}" aria-label="將 ${esc(symbol)} 移出觀察清單">✕</button>`;

// 靜態模式下，送出後到 GitHub 重新產生網站前，先在畫面上反映變更
const pendingAdds = new Map();
const pendingRemoves = new Set();

async function loadRecommendations() {
  let [recs, watch] = await Promise.all([api(URLS.recommendations), api(URLS.watchlist)]);
  recs = recs.filter((r) => !pendingRemoves.has(r.symbol));
  watch = watch.filter((w) => !pendingRemoves.has(w.symbol));
  for (const [symbol, name] of pendingAdds) {
    if (!watch.some((w) => w.symbol === symbol)) watch.push({ symbol, name });
  }
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
      <td class="c-act">${removeBtn(r.symbol)}</td>
    </tr>`).join("") + pending.map((w) => `
    <tr data-symbol="${esc(w.symbol)}">
      <td class="c-name"><span class="sym">${esc(w.symbol)}</span><span class="name">${esc(w.name)}</span></td>
      <td colspan="5" class="c-pending muted">資料收集中或不足…</td>
      <td class="c-act">${removeBtn(w.symbol)}</td>
    </tr>`).join("");
}

async function loadDetail(symbol, scroll = true) {
  selected = symbol;
  document.querySelectorAll("#rec-table tbody tr").forEach((tr) => tr.classList.toggle("active", tr.dataset.symbol === symbol));
  let d;
  try { d = await api(URLS.stock(symbol)); } catch (e) { return alert(e.message); }
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
  if (scroll) $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
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
  renderNews($("#all-news"), await api(URLS.news), true);
}

async function loadStatus() {
  const s = await api(URLS.status);
  const last = s.last_run;
  let text;
  if (STATIC) {
    text = s.generated_at ? `資料更新：${localTime(s.generated_at)} · 約每小時自動更新` : "尚未產生資料";
    if (s.demo) text += " · 模擬資料";
  } else {
    text = s.collecting ? "收集中…" : last ? `上次收集：${localTime(last.finished_at)}（+${last.news_added} 則新聞）` : "尚未收集";
    if (s.interval_min > 0) text += ` · 每 ${s.interval_min} 分鐘自動收集`;
  }
  if (last && last.errors) text += " · ⚠ 部分來源失敗";
  $("#status").textContent = text;
  $("#status").title = last?.errors || "";
}

async function refreshAll() {
  await Promise.all([loadRecommendations(), loadNews(), loadStatus()]);
}

// ---- 進度提示 ----
let busy = false;
let taskTimer = null;
function setTask(text, link, { done = false, error = false } = {}) {
  clearTimeout(taskTimer);
  $("#task").classList.remove("hidden");
  $("#task").classList.toggle("error", error);
  $("#task .spinner").classList.toggle("hidden", done);
  $("#task-text").textContent = text;
  $("#task-link").classList.toggle("hidden", !link);
  if (link) $("#task-link").href = link;
  if (done) taskTimer = setTimeout(() => $("#task").classList.add("hidden"), error ? 10000 : 4000);
}
const showTask = (text, link) => setTask(text, link);
const finishTask = (text, isError, link) => setTask(text, link, { done: true, error: !!isError });

// GitHub 執行完成後，等 GitHub Pages 換上新資料再重新整理畫面
async function waitForFreshData(previous) {
  for (let i = 0; i < 18; i++) {
    const s = await api(URLS.status).catch(() => null);
    if (s && s.generated_at !== previous) return;
    await new Promise((r) => setTimeout(r, 5000));
  }
}

async function runStatic(label, job, onDone) {
  if (busy) return;
  if (!GH.token()) return openGitHub(`要${label}，請先連結 GitHub。`);
  busy = true;
  setButtonsDisabled();
  const previous = (await api(URLS.status).catch(() => ({}))).generated_at;
  try {
    showTask(`${label}：準備中…`);
    const run = await job((text, link) => showTask(`${label}：${text}`, link));
    if (run === null) { onDone?.(); finishTask(`${label}：沒有需要變更的地方`); return; }
    showTask(`${label}：等待網站更新…`);
    await waitForFreshData(previous);
    onDone?.();
    await refreshAll();
    if (selected) loadDetail(selected, false);
    finishTask(`${label}：完成`);
  } catch (err) {
    onDone?.();
    await loadRecommendations().catch(() => {});
    if (err.status === 401) openGitHub(err.message);
    finishTask(err.message, true, err.url);
  } finally {
    busy = false;
    setButtonsDisabled();
  }
}

function setButtonsDisabled() {
  const off = busy || !navigator.onLine;
  document.querySelectorAll("#collect-btn, #add-form button").forEach((b) => { b.disabled = off; });
}

// ---- GitHub 設定（只在 GitHub Pages 模式）----
function openGitHub(reason) {
  const dlg = $("#gh-dialog");
  if (!dlg) return;
  $("#gh-reason").textContent = reason || "";
  $("#gh-reason").classList.toggle("hidden", !reason);
  $("#gh-error").classList.add("hidden");
  $("#gh-token").value = "";
  $("#gh-state").textContent = GH.token() ? "這台裝置已連結 GitHub。貼上新的 token 可以替換。" : "這台裝置尚未連結 GitHub。";
  $("#gh-clear").classList.toggle("hidden", !GH.token());
  dlg.showModal();
}

if (STATIC) {
  $("#gh-settings").addEventListener("click", () => openGitHub());
  $("#gh-save").addEventListener("click", async () => {
    const t = $("#gh-token").value.trim();
    const errEl = $("#gh-error");
    if (!t) { errEl.textContent = "請貼上 token"; errEl.classList.remove("hidden"); return; }
    $("#gh-save").disabled = true; $("#gh-save").textContent = "檢查中…";
    try {
      await GH.verify(t);
      GH.saveToken(t);
      if (!GH.token()) throw new Error("這個瀏覽器無法儲存 token（可能是無痕模式）");
      $("#gh-dialog").close();
      finishTask("已連結 GitHub");
    } catch (err) {
      errEl.textContent = err.message; errEl.classList.remove("hidden");
    } finally {
      $("#gh-save").disabled = false; $("#gh-save").textContent = "儲存";
    }
  });
  $("#gh-clear").addEventListener("click", () => {
    GH.saveToken("");
    $("#gh-dialog").close();
    finishTask("已移除這台裝置的 GitHub token");
  });
}

$("#rec-table").addEventListener("click", async (e) => {
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    e.stopPropagation();
    const symbol = rm.dataset.remove;
    if (!confirm(`將 ${symbol} 移出觀察清單？`)) return;
    if (selected === symbol) $("#detail").classList.add("hidden");
    if (STATIC) {
      if (!GH.token()) return openGitHub("要修改觀察清單，請先連結 GitHub。");
      pendingRemoves.add(symbol);
      loadRecommendations();
      return runStatic(`移除 ${symbol}`, (p) => GH.remove(symbol, p), () => pendingRemoves.delete(symbol));
    }
    await api(`api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" });
    return loadRecommendations();
  }
  const tr = e.target.closest("tr[data-symbol]");
  if (tr) loadDetail(tr.dataset.symbol);
});

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (STATIC) {
    const symbol = GH.normalizeSymbol($("#add-symbol").value);
    const name = $("#add-name").value.trim();
    if (!symbol) return alert("股票代號格式不正確");
    if (!GH.token()) return openGitHub("要修改觀察清單，請先連結 GitHub。");
    e.target.reset();
    pendingAdds.set(symbol, name || null);
    loadRecommendations();
    return runStatic(`加入 ${symbol}`, (p) => GH.add(symbol, name, p), () => pendingAdds.delete(symbol));
  }
  try {
    await api("api/watchlist", { method: "POST", body: JSON.stringify({ symbol: $("#add-symbol").value, name: $("#add-name").value }) });
    e.target.reset();
    await loadRecommendations();
    setTimeout(refreshAll, 4000);
  } catch (err) { alert(err.message); }
});

$("#collect-btn").addEventListener("click", async () => {
  if (STATIC) return runStatic("立即更新", (p) => GH.update(p));
  const btn = $("#collect-btn");
  btn.disabled = true; btn.textContent = "收集中…";
  try { await api("api/collect", { method: "POST", body: "{}" }); }
  catch (err) { alert(err.message); }
  finally { btn.disabled = false; btn.textContent = "立即收集"; }
  await refreshAll();
  if (selected) loadDetail(selected, false);
});

// 把頁面資源與所有股票的資料交給 service worker 保存，離線時也能瀏覽每一檔
async function cacheForOffline() {
  const reg = await navigator.serviceWorker.ready;
  const assets = [...document.querySelectorAll("link[rel=stylesheet], script[src]")].map((el) => el.href || el.src);
  const watch = await api(URLS.watchlist).catch(() => []);
  const data = [URLS.recommendations, URLS.watchlist, URLS.news, URLS.status, ...watch.map((w) => URLS.stock(w.symbol))];
  reg.active?.postMessage({ cache: [...assets, ...data.map((u) => new URL(u, location.href).href)] });
}

function updateOnline() {
  $("#offline").classList.toggle("hidden", navigator.onLine);
  setButtonsDisabled();
}
window.addEventListener("online", () => { updateOnline(); refreshAll(); });
window.addEventListener("offline", updateOnline);
updateOnline();

// 從背景切回 App 時（手機常見）自動更新
document.addEventListener("visibilitychange", () => { if (!document.hidden && navigator.onLine) refreshAll(); });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((err) => console.warn("service worker:", err));
  cacheForOffline();
}

refreshAll();
setInterval(() => { if (navigator.onLine) loadStatus(); }, 30000);
setInterval(() => { if (navigator.onLine) refreshAll(); }, 5 * 60000);
