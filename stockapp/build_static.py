"""產生可放在 GitHub Pages（或任何靜態網站空間）的版本，不需要伺服器。

    python -m stockapp.build_static --out _site              # 收集最新資料並產生網站
    python -m stockapp.build_static --out _site --no-collect # 只用資料庫現有資料產生

輸出：index.html、static/、manifest、service worker，以及 data/ 底下的 JSON：
    recommendations.json、watchlist.json、news.json、status.json、stocks/<代號>.json
"""
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import collector, config, db, recommender, views, watchlist

log = logging.getLogger(__name__)

# 新聞只保留近期的，避免資料庫無限長大
NEWS_RETENTION_DAYS = 60


def data_file(symbol):
    """與前端 app.js 的 dataFile() 規則一致。"""
    return re.sub(r"[^A-Za-z0-9.\-]", "_", symbol)


def repo_info(repo_url=None, branch=None):
    """GitHub repo 網址與分支：優先用參數，其次 GitHub Actions 環境變數，最後讀 git 設定。"""
    if not repo_url and os.environ.get("GITHUB_REPOSITORY"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo_url = f"{server}/{os.environ['GITHUB_REPOSITORY']}"
    if not repo_url:
        repo_url = _git("remote", "get-url", "origin")
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", repo_url or "")
        repo_url = f"https://github.com/{m.group(1)}" if m else None
    branch = branch or os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD")
    return repo_url, branch or "main"


def _git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                              cwd=config.BASE_DIR).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build(out, collect=True, repo_url=None, branch=None):
    out = Path(out)
    db.init_db()
    entries = watchlist.load(config.WATCHLIST_FILE)
    if entries:
        db.replace_watchlist(entries)

    run = collector.collect_all() if collect else None
    db.prune_news(NEWS_RETENTION_DAYS)

    if out.exists():
        shutil.rmtree(out)
    data = out / "data"
    watch = db.get_watchlist()
    recs = recommender.recommend_all()

    _write_json(data / "recommendations.json", recs)
    _write_json(data / "watchlist.json", watch)
    _write_json(data / "news.json", views.news(limit=30))
    for w in watch:
        detail = views.stock_detail(w["symbol"], w["name"])
        if detail:
            _write_json(data / "stocks" / f"{data_file(w['symbol'])}.json", detail)
    _write_json(data / "status.json", {
        "mode": "static",
        "demo": config.DEMO_MODE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "last_run": db.last_run(),
    })

    static_dir = config.BASE_DIR / "static"
    shutil.copytree(static_dir, out / "static",
                    ignore=shutil.ignore_patterns("sw.js", "manifest.webmanifest"))
    shutil.copy(static_dir / "sw.js", out / "sw.js")
    shutil.copy(static_dir / "manifest.webmanifest", out / "manifest.webmanifest")
    (out / ".nojekyll").touch()  # 讓 GitHub Pages 原樣提供檔案

    repo_url, branch = repo_info(repo_url, branch)
    env = Environment(loader=FileSystemLoader(config.BASE_DIR / "templates"),
                      autoescape=select_autoescape(["html"]))
    html = env.get_template("index.html").render(
        demo=config.DEMO_MODE,
        auth=False,
        static_site=True,
        client_config={"mode": "static"},
        v=config.asset_version(),
        actions_url=f"{repo_url}/actions/workflows/update.yml" if repo_url else "#",
        edit_url=f"{repo_url}/edit/{branch}/watchlist.txt" if repo_url else "#",
    )
    (out / "index.html").write_text(html, encoding="utf-8")
    return run, recs


def write_summary(run, recs):
    """在 GitHub Actions 的執行頁面顯示本次結果。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["## 股票推薦", "", "| 股票 | 收盤 | 評分 | 建議 |", "|---|---:|---:|---|"]
    lines += [f"| {r['symbol']} {r['name'] or ''} | {r['close']} | {r['score']} | {r['rating']} |"
              for r in recs]
    if run:
        lines += ["", f"新增股價 {run['prices_added']} 筆、新聞 {run['news_added']} 則"]
        if run["errors"]:
            lines += ["", "<details><summary>錯誤</summary>", ""]
            lines += [f"- {e}" for e in run["errors"]]
            lines += ["", "</details>"]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="產生靜態網站版本")
    parser.add_argument("--out", default="_site", help="輸出資料夾（會先清空）")
    parser.add_argument("--no-collect", action="store_true", help="不收集新資料")
    parser.add_argument("--repo-url", help="GitHub repo 網址，用於「立即更新」「編輯觀察清單」連結")
    parser.add_argument("--branch", help="watchlist.txt 所在分支")
    args = parser.parse_args(argv)

    run, recs = build(args.out, collect=not args.no_collect,
                      repo_url=args.repo_url, branch=args.branch)
    print(f"已產生 {args.out}：{len(recs)} 檔推薦")
    if run:
        for err in run["errors"]:
            print("  錯誤:", err)
    write_summary(run, recs)


if __name__ == "__main__":
    main()
