"""自動收集股票相關內容：股價歷史 + 多個 RSS 新聞來源，去重後寫入 SQLite。

可單獨執行：
    python -m stockapp.collector            # 收集一次全部觀察清單
    python -m stockapp.collector 2330.TW    # 只收集指定股票
"""
import email.utils
import logging
import random
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from . import config, db, market, sentiment

log = logging.getLogger(__name__)


def _is_tw(symbol):
    return symbol.upper().endswith((".TW", ".TWO"))


def news_sources(symbol, name=None):
    """回傳 [(來源名稱, RSS URL)]。台股以中文名稱查詢，美股以代號 + 英文查詢。"""
    code = symbol.split(".")[0]
    if _is_tw(symbol):
        query = f"{name} {code} 股票" if name else f"{code} 股票"
        google = ("Google 新聞",
                  f"https://news.google.com/rss/search?q={quote_plus(query)}"
                  "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    else:
        query = f"{symbol} stock"
        google = ("Google News",
                  f"https://news.google.com/rss/search?q={quote_plus(query)}"
                  "&hl=en-US&gl=US&ceid=US:en")
    yahoo = ("Yahoo Finance",
             f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(symbol)}"
             "&region=US&lang=en-US")
    return [google, yahoo]


def parse_rss(xml_text, source, limit=None):
    """解析 RSS 2.0，回傳新聞 dict 列表（含情緒分數）。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        publisher = (item.findtext("source") or "").strip() or None
        # Google 新聞標題格式為「標題 - 媒體」
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].strip()
        summary = _strip_html(item.findtext("description") or "")
        if summary == title or summary.startswith(title):
            summary = ""
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "publisher": publisher,
            "published": _parse_date(item.findtext("pubDate")),
            "summary": summary[:500],
            "sentiment": sentiment.score(f"{title} {summary}"),
        })
        if limit and len(items) >= limit:
            break
    return items


def _strip_html(text):
    if "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def _parse_date(value):
    now = datetime.now(timezone.utc)
    if not value:
        return now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return now.strftime("%Y-%m-%d %H:%M:%S")


def fetch_news(symbol, name=None):
    """從各來源抓新聞；回傳 (items, errors)。單一來源失敗不影響其他來源。"""
    if config.DEMO_MODE:
        return demo_news(symbol, name), []

    items, errors = [], []
    for source, url in news_sources(symbol, name):
        try:
            resp = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            items.extend(parse_rss(resp.text, source, limit=config.NEWS_PER_SOURCE))
        except requests.RequestException as e:
            errors.append(f"{symbol} {source}: {e}")
    return items, errors


def collect_symbol(symbol, name=None):
    """收集單一股票；回傳 dict(prices_added, news_added, errors)。"""
    result = {"prices_added": 0, "news_added": 0, "errors": []}
    try:
        fetched_name, rows = market.fetch_history(symbol)
        result["prices_added"] = db.upsert_prices(symbol, rows)
        if fetched_name:
            db.set_name(symbol, fetched_name)
            name = name or fetched_name
    except market.MarketDataError as e:
        result["errors"].append(str(e))

    items, errors = fetch_news(symbol, name)
    result["news_added"] = db.insert_news(symbol, items)
    result["errors"].extend(errors)
    return result


def collect_all(symbols=None):
    """收集觀察清單（或指定代號）的股價與新聞，並記錄到 collection_runs。"""
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    watch = {w["symbol"]: w["name"] for w in db.get_watchlist()}
    targets = symbols or list(watch)

    totals = {"symbols": len(targets), "prices_added": 0, "news_added": 0, "errors": []}
    for sym in targets:
        r = collect_symbol(sym, watch.get(sym))
        totals["prices_added"] += r["prices_added"]
        totals["news_added"] += r["news_added"]
        totals["errors"].extend(r["errors"])
        log.info("collected %s: +%d prices, +%d news", sym, r["prices_added"], r["news_added"])

    finished = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    db.log_run(started, finished, totals["symbols"], totals["prices_added"],
               totals["news_added"], totals["errors"])
    totals["started_at"], totals["finished_at"] = started, finished
    return totals


# ---- 離線展示用的模擬新聞 ----

_DEMO_TEMPLATES = [
    "{n}營收創新高，法人看好後市",
    "{n}獲外資調升目標價，買盤湧入",
    "{n}新產品熱銷，訂單能見度提升",
    "{n}股價震盪整理，市場觀望氣氛濃",
    "{n}召開法說會，說明下半年營運展望",
    "{n}受關稅衝擊，獲利恐不如預期",
    "{n}遭外資減碼，股價跌破季線",
    "{n}傳出砍單消息，股價重挫",
]


def demo_news(symbol, name=None, count=8):
    n = name or symbol
    rng = random.Random(f"news-{symbol}")
    bias = rng.random()
    now = datetime.now(timezone.utc)
    items = []
    for i in range(count):
        # 讓每檔股票有不同的正負面偏向
        idx = int(rng.random() * len(_DEMO_TEMPLATES) * 0.6 + bias * len(_DEMO_TEMPLATES) * 0.4)
        title = _DEMO_TEMPLATES[min(idx, len(_DEMO_TEMPLATES) - 1)].format(n=n)
        published = now - timedelta(hours=i * 9 + rng.randint(0, 8))
        items.append({
            "title": title,
            "link": f"https://example.com/demo/{symbol}/{i}",
            "source": "模擬資料",
            "publisher": "Demo News",
            "published": published.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": "（離線展示用的模擬新聞）",
            "sentiment": sentiment.score(title),
        })
    return items


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_db()
    args = (argv if argv is not None else sys.argv[1:])
    totals = collect_all([a.upper() for a in args] or None)
    print(f"完成：{totals['symbols']} 檔，新增股價 {totals['prices_added']} 筆，"
          f"新增新聞 {totals['news_added']} 筆")
    for err in totals["errors"]:
        print("  錯誤:", err)


if __name__ == "__main__":
    main()
