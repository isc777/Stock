"""股價資料來源：Yahoo Finance chart API（台股代號加 .TW / .TWO，美股直接用代號）。"""
import math
import random
from datetime import date, datetime, timedelta, timezone

import requests

from . import config

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class MarketDataError(Exception):
    pass


def fetch_history(symbol, range_=None):
    """回傳 (name, rows)；rows 為依日期排序的 dict(date, open, high, low, close, volume)。"""
    if config.DEMO_MODE:
        return demo_history(symbol)

    try:
        resp = requests.get(
            CHART_URL.format(symbol=symbol),
            params={"range": range_ or config.PRICE_RANGE, "interval": "1d"},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise MarketDataError(f"{symbol}: 無法取得股價 ({e})") from e

    chart = payload.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise MarketDataError(f"{symbol}: 查無資料 ({chart.get('error')})")

    result = chart["result"][0]
    meta = result.get("meta", {})
    name = meta.get("longName") or meta.get("shortName")
    tz_offset = meta.get("gmtoffset", 0)
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]

    rows = []
    for i, ts in enumerate(result.get("timestamp") or []):
        close = _at(quote.get("close"), i)
        if close is None:
            continue
        day = datetime.fromtimestamp(ts + tz_offset, tz=timezone.utc).date().isoformat()
        rows.append({
            "date": day,
            "open": _at(quote.get("open"), i) or close,
            "high": _at(quote.get("high"), i) or close,
            "low": _at(quote.get("low"), i) or close,
            "close": close,
            "volume": _at(quote.get("volume"), i) or 0,
        })
    if not rows:
        raise MarketDataError(f"{symbol}: 回傳資料為空")
    return name, rows


def _at(values, i):
    if not values or i >= len(values):
        return None
    v = values[i]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def demo_history(symbol, days=260):
    """離線模擬資料：依代號產生固定的隨機漫步，方便沒有網路時展示。"""
    rng = random.Random(symbol)
    price = rng.uniform(50, 900)
    drift = rng.uniform(-0.0015, 0.0025)
    vol = rng.uniform(0.01, 0.025)
    rows = []
    day = date.today() - timedelta(days=int(days * 1.45))
    while len(rows) < days:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        open_ = price
        price = max(1.0, price * (1 + drift + rng.gauss(0, vol)))
        rows.append({
            "date": day.isoformat(),
            "open": round(open_, 2),
            "high": round(max(open_, price) * (1 + abs(rng.gauss(0, vol / 2))), 2),
            "low": round(min(open_, price) * (1 - abs(rng.gauss(0, vol / 2))), 2),
            "close": round(price, 2),
            "volume": float(rng.randint(5_000, 80_000) * 1000),
        })
    return None, rows
