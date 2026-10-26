// GitHub Pages 模式：用使用者自己的 GitHub token，直接從瀏覽器觸發更新、修改觀察清單（不需要伺服器）。
// token 只存在這台裝置的瀏覽器（localStorage），只會送到 api.github.com。
const GH = (() => {
  const cfg = window.STOCK_CONFIG || {};
  const KEY = "stock.githubToken";
  const API = "https://api.github.com";
  const RUNS = () => `/repos/${cfg.repo}/actions/workflows/${cfg.workflow}/runs?per_page=10&branch=${encodeURIComponent(cfg.branch)}`;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const token = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
  const saveToken = (t) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* 無痕模式等情況存不了 */ } };

  async function call(path, opts = {}, auth = token()) {
    const res = await fetch(API + path, {
      ...opts,
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${auth}`,
        "X-GitHub-Api-Version": "2022-11-28",
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(explain(res.status, data.message));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function explain(status, message) {
    if (status === 401) return "GitHub token 無效或已過期，請到「GitHub 設定」重新設定";
    if (status === 403 || status === 404) return "token 沒有這個 repo 的權限（Actions 與 Contents 都要設為 Read and write）";
    if (status === 409 || status === 422) return "觀察清單剛被其他地方修改，請再試一次";
    return `GitHub 回應錯誤 ${status}${message ? "：" + message : ""}`;
  }

  // 儲存前檢查 token 能讀取 workflow 與觀察清單（寫入權限要實際寫入才知道）
  async function verify(t) {
    await call(`/repos/${cfg.repo}/actions/workflows/${cfg.workflow}`, {}, t);
    await call(`/repos/${cfg.repo}/contents/watchlist.txt?ref=${encodeURIComponent(cfg.branch)}`, {}, t);
  }

  // ---- 觀察清單（與 stockapp/watchlist.py 的規則一致）----
  function normalizeSymbol(raw) {
    let s = (raw || "").trim().toUpperCase();
    if (/^\d+$/.test(s)) s += ".TW";
    return /^[A-Z0-9.\-^=]{1,15}$/.test(s) ? s : null;
  }
  const lineSymbol = (line) => normalizeSymbol(line.split("#")[0].trim().split(/\s+/)[0]);

  function addLine(text, symbol, name) {
    if (text.split("\n").some((l) => lineSymbol(l) === symbol)) return text;
    const clean = (name || "").replace(/[#\r\n]/g, " ").trim();
    return text.replace(/\s*$/, "\n") + `${symbol}${clean ? " " + clean : ""}\n`;
  }
  const removeLine = (text, symbol) => text.split("\n").filter((l) => lineSymbol(l) !== symbol).join("\n");

  const b64decode = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), (c) => c.charCodeAt(0)));
  function b64encode(text) {
    let bin = "";
    new TextEncoder().encode(text).forEach((b) => { bin += String.fromCharCode(b); });
    return btoa(bin);
  }

  async function editWatchlist(change, message) {
    const path = `/repos/${cfg.repo}/contents/watchlist.txt`;
    const file = await call(`${path}?ref=${encodeURIComponent(cfg.branch)}`);
    const before = b64decode(file.content);
    const after = change(before);
    if (after === before) return false;
    await call(path, {
      method: "PUT",
      body: JSON.stringify({ message, content: b64encode(after), sha: file.sha, branch: cfg.branch }),
    });
    return true;
  }

  // ---- 執行與等待 ----
  const latestRunId = async () => (await call(RUNS())).workflow_runs.reduce((m, r) => Math.max(m, r.id), 0);

  // 等待「之後才建立」的那次執行完成；run id 會遞增，所以用觸發前的最大 id 來辨識
  async function waitForRun(afterId, event, onProgress) {
    const deadline = Date.now() + 15 * 60000;
    while (Date.now() < deadline) {
      await sleep(5000);
      const runs = (await call(RUNS())).workflow_runs;
      const run = runs.filter((r) => r.id > afterId && r.event === event).sort((a, b) => a.id - b.id)[0];
      if (!run) { onProgress("等待 GitHub 開始執行…"); continue; }
      if (run.status === "completed") {
        if (run.conclusion !== "success") {
          const err = new Error("GitHub 更新失敗，可到執行頁面查看原因");
          err.url = run.html_url;
          throw err;
        }
        return run;
      }
      onProgress(run.status === "in_progress" ? "收集資料中…" : "排隊中…", run.html_url);
    }
    throw new Error("等候逾時，請稍後重新整理");
  }

  // 立即更新：觸發 workflow_dispatch 並等它完成
  async function update(onProgress) {
    const before = await latestRunId();
    await call(`/repos/${cfg.repo}/actions/workflows/${cfg.workflow}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: cfg.branch }),
    });
    onProgress("已送出，等待 GitHub 開始執行…");
    return waitForRun(before, "workflow_dispatch", onProgress);
  }

  // 修改觀察清單：commit 後 GitHub 會因 push 自動重新產生網站
  async function changeWatchlist(change, message, onProgress) {
    const before = await latestRunId();
    onProgress("更新觀察清單…");
    if (!(await editWatchlist(change, message))) return null;
    onProgress("已儲存，等待 GitHub 重新收集…");
    return waitForRun(before, "push", onProgress);
  }

  return {
    enabled: !!(cfg.repo && cfg.branch && cfg.workflow),
    token,
    saveToken,
    verify,
    normalizeSymbol,
    update,
    add: (symbol, name, onProgress) =>
      changeWatchlist((t) => addLine(t, symbol, name), `觀察清單：加入 ${symbol}`, onProgress),
    remove: (symbol, onProgress) =>
      changeWatchlist((t) => removeLine(t, symbol), `觀察清單：移除 ${symbol}`, onProgress),
  };
})();
