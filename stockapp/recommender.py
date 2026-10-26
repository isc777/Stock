"""推薦引擎：技術面（趨勢、動能、RSI、MACD）+ 新聞情緒，合成 0~100 分。

各面向權重（滿分合計 100）：
    趨勢 30、動能 20、RSI 15、MACD 15、新聞情緒 20
"""
import math
from datetime import datetime, timedelta, timezone

from . import db, indicators

RATINGS = [
    (70, "強力買進", "strong_buy"),
    (58, "買進", "buy"),
    (42, "持有", "hold"),
    (30, "減碼", "reduce"),
    (0, "賣出", "sell"),
]

MIN_HISTORY = 30
SENTIMENT_DAYS = 7


def _f(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def score_trend(last, prev20_ma20):
    close, ma20, ma60 = last["close"], _f(last["ma20"]), _f(last["ma60"])
    pts, reasons = 0.0, []
    if ma20 is not None:
        if close > ma20:
            pts += 10
            reasons.append("股價站上 20 日均線")
        else:
            reasons.append("股價跌破 20 日均線")
    if ma20 is not None and ma60 is not None:
        if ma20 > ma60:
            pts += 10
            reasons.append("20 日均線在 60 日均線之上（多頭排列）")
        else:
            reasons.append("20 日均線在 60 日均線之下（空頭排列）")
    elif ma20 is not None:
        pts += 5  # 歷史不足，給中性分數
    if ma20 is not None and prev20_ma20 is not None:
        if ma20 > prev20_ma20:
            pts += 10
            reasons.append("20 日均線向上")
        else:
            reasons.append("20 日均線向下")
    return pts, reasons


def score_momentum(df):
    pts, reasons = 10.0, []
    if len(df) > 20:
        ret = float(df["close"].iloc[-1] / df["close"].iloc[-21] - 1)
        # 近 20 日報酬 -10% → 0 分、+10% → 20 分
        pts = max(0.0, min(20.0, 10 + ret * 100))
        reasons.append(f"近 20 日{'上漲' if ret >= 0 else '下跌'} {abs(ret) * 100:.1f}%")
    return pts, reasons


def score_rsi(value):
    if value is None:
        return 7.5, []
    if value >= 80:
        return 2, [f"RSI {value:.0f}，嚴重超買"]
    if value >= 70:
        return 6, [f"RSI {value:.0f}，偏超買"]
    if value >= 50:
        return 15, [f"RSI {value:.0f}，多方動能健康"]
    if value >= 30:
        return 8, [f"RSI {value:.0f}，動能偏弱"]
    return 10, [f"RSI {value:.0f}，超賣，留意反彈"]


def score_macd(df):
    hist = df["macd_hist"]
    if hist.isna().all() or len(df) < 2:
        return 7.5, []
    cur, prev = float(hist.iloc[-1]), float(hist.iloc[-2])
    pts, reasons = 0.0, []
    if cur > 0:
        pts += 9
        reasons.append("MACD 柱狀體為正")
        if prev <= 0:
            reasons.append("MACD 黃金交叉")
    else:
        reasons.append("MACD 柱狀體為負")
        if prev > 0:
            reasons.append("MACD 死亡交叉")
    if cur > prev:
        pts += 6
    return pts, reasons


def score_sentiment(news):
    if not news:
        return 10.0, None, ["近期無相關新聞"]
    # 越新的新聞權重越高
    now = datetime.now(timezone.utc)
    total = weight_sum = 0.0
    for n in news:
        try:
            pub = datetime.strptime(n["published"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - pub).total_seconds() / 86400)
        except (TypeError, ValueError):
            age_days = SENTIMENT_DAYS
        w = 1.0 / (1.0 + age_days)
        total += n["sentiment"] * w
        weight_sum += w
    avg = total / weight_sum if weight_sum else 0.0
    pts = 10 + avg * 10
    pos = sum(1 for n in news if n["sentiment"] >= 0.2)
    neg = sum(1 for n in news if n["sentiment"] <= -0.2)
    return pts, avg, [f"近 {SENTIMENT_DAYS} 日新聞 {len(news)} 則（正面 {pos}、負面 {neg}）"]


def rating_for(score):
    for threshold, label, code in RATINGS:
        if score >= threshold:
            return label, code
    return RATINGS[-1][1], RATINGS[-1][2]


def analyze(symbol, name=None, prices=None, news=None):
    """分析單一股票，回傳推薦結果 dict；資料不足時回傳 None。"""
    prices = prices if prices is not None else db.get_prices(symbol)
    if len(prices) < MIN_HISTORY:
        return None
    if news is None:
        since = (datetime.now(timezone.utc) - timedelta(days=SENTIMENT_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        news = db.get_news(symbol, limit=100, since=since)

    df = indicators.compute(prices)
    last = df.iloc[-1]
    prev20_ma20 = _f(df["ma20"].iloc[-21]) if len(df) > 20 else None

    parts = {}
    reasons = []
    parts["trend"], r = score_trend(last, prev20_ma20); reasons += r
    parts["momentum"], r = score_momentum(df); reasons += r
    parts["rsi"], r = score_rsi(_f(last["rsi14"])); reasons += r
    parts["macd"], r = score_macd(df); reasons += r
    parts["sentiment"], avg_sent, r = score_sentiment(news); reasons += r

    total = round(sum(parts.values()), 1)
    label, code = rating_for(total)
    prev_close = float(df["close"].iloc[-2])
    close = float(last["close"])
    return {
        "symbol": symbol,
        "name": name,
        "date": last["date"],
        "close": round(close, 2),
        "change_pct": round((close / prev_close - 1) * 100, 2),
        "score": total,
        "rating": label,
        "rating_code": code,
        "breakdown": {k: round(v, 1) for k, v in parts.items()},
        "indicators": {
            "ma20": _round(last["ma20"]),
            "ma60": _round(last["ma60"]),
            "rsi14": _round(last["rsi14"]),
            "macd_hist": _round(last["macd_hist"], 3),
            "volatility20": _round(last["volatility20"], 3),
        },
        "news_sentiment": None if avg_sent is None else round(avg_sent, 3),
        "news_count": len(news),
        "reasons": reasons,
    }


def _round(v, digits=2):
    v = _f(v)
    return None if v is None else round(v, digits)


def recommend_all():
    results = []
    for w in db.get_watchlist():
        r = analyze(w["symbol"], w["name"])
        if r:
            results.append(r)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
