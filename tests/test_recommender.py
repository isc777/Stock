from stockapp import recommender, sentiment


def _prices(closes):
    return [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c, "high": c, "low": c,
             "close": c, "volume": 1000} for i, c in enumerate(closes)]


def test_uptrend_scores_higher_than_downtrend():
    up = [100 * 1.004 ** i for i in range(120)]
    down = [100 * 0.996 ** i for i in range(120)]
    good = [{"sentiment": 0.8, "published": "2026-10-25 00:00:00"}]
    bad = [{"sentiment": -0.8, "published": "2026-10-25 00:00:00"}]
    r_up = recommender.analyze("UP", prices=_prices(up), news=good)
    r_down = recommender.analyze("DOWN", prices=_prices(down), news=bad)
    assert r_up["score"] > r_down["score"]
    assert r_up["rating_code"] in ("strong_buy", "buy")
    assert r_down["rating_code"] in ("sell", "reduce")
    assert 0 <= r_down["score"] <= r_up["score"] <= 100


def test_insufficient_history_returns_none():
    assert recommender.analyze("X", prices=_prices([1, 2, 3]), news=[]) is None


def test_rating_thresholds():
    assert recommender.rating_for(75)[1] == "strong_buy"
    assert recommender.rating_for(50)[1] == "hold"
    assert recommender.rating_for(5)[1] == "sell"


def test_sentiment_negation():
    assert sentiment.score("營收成長") > 0
    assert sentiment.score("營收沒有成長") < 0
    assert sentiment.score("") == 0
