"""API 與靜態網站共用的資料組裝，確保兩種模式輸出相同的 JSON。"""
from . import db, indicators, recommender, sentiment


def _label(items):
    for n in items:
        n["sentiment_label"] = sentiment.label(n["sentiment"])
    return items


def news(symbol=None, limit=50):
    return _label(db.get_news(symbol, limit=limit))


def stock_detail(symbol, name=None):
    """個股詳情；尚無股價資料時回傳 None。"""
    prices = db.get_prices(symbol)
    if not prices:
        return None
    df = indicators.compute(prices).tail(180)
    series = {
        col: [None if v != v else round(float(v), 2) for v in df[col]]
        for col in ("close", "ma20", "ma60", "rsi14")
    }
    series["date"] = list(df["date"])
    return {
        "symbol": symbol,
        "name": name,
        "recommendation": recommender.analyze(symbol, name, prices=prices),
        "series": series,
        "news": news(symbol, limit=40),
    }
