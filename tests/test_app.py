def test_flow(client):
    assert client.get("/").status_code == 200
    assert client.post("/api/collect", json={"symbols": ["2330"]}).status_code == 200

    recs = client.get("/api/recommendations").get_json()
    assert [r["symbol"] for r in recs] == ["2330.TW"]

    detail = client.get("/api/stocks/2330.TW").get_json()
    assert detail["recommendation"]["score"] == recs[0]["score"]
    assert len(detail["series"]["close"]) == len(detail["series"]["date"])
    assert detail["news"]

    assert client.get("/api/news?symbol=2330.TW").get_json()
    assert client.get("/api/status").get_json()["last_run"]["symbols"] == 1


def test_watchlist_validation(client):
    assert client.post("/api/watchlist", json={"symbol": "bad symbol!"}).status_code == 400
    assert client.delete("/api/watchlist/NOPE").status_code == 404
    assert client.delete("/api/watchlist/AAPL").status_code == 204
    symbols = [w["symbol"] for w in client.get("/api/watchlist").get_json()]
    assert "AAPL" not in symbols


def test_unknown_stock(client):
    assert client.get("/api/stocks/ZZZZ").status_code == 404
