"""股票推薦 App 入口。

    python app.py                 # 使用真實資料（需可連到 Yahoo Finance / Google 新聞）
    STOCK_DEMO=1 python app.py    # 離線展示模式
"""
import logging
import os
import re
import threading

from flask import Flask, jsonify, render_template, request

from stockapp import config, db, indicators, recommender, sentiment
from stockapp.scheduler import CollectorScheduler

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")


def create_app(start_scheduler=True):
    app = Flask(__name__)
    db.init_db()
    scheduler = CollectorScheduler()
    app.config["SCHEDULER"] = scheduler
    if start_scheduler:
        scheduler.start()

    @app.get("/")
    def index():
        return render_template("index.html", demo=config.DEMO_MODE)

    @app.get("/api/status")
    def status():
        return jsonify({
            "demo": config.DEMO_MODE,
            "interval_min": scheduler.interval_min,
            "collecting": scheduler.running,
            "next_run": scheduler.next_run.isoformat() if scheduler.next_run else None,
            "last_run": db.last_run(),
        })

    @app.get("/api/watchlist")
    def watchlist():
        return jsonify(db.get_watchlist())

    @app.post("/api/watchlist")
    def add_watch():
        data = request.get_json(silent=True) or {}
        symbol = normalize_symbol(data.get("symbol", ""))
        if not symbol:
            return jsonify({"error": "股票代號格式不正確"}), 400
        name = (data.get("name") or "").strip() or None
        db.add_to_watchlist(symbol, name)
        # 新加入的股票立即在背景收集，不讓使用者等待
        threading.Thread(target=scheduler.run_now, args=([symbol],), daemon=True).start()
        return jsonify({"symbol": symbol, "name": name}), 201

    @app.delete("/api/watchlist/<symbol>")
    def remove_watch(symbol):
        if not db.remove_from_watchlist(symbol.upper()):
            return jsonify({"error": "不在觀察清單中"}), 404
        return "", 204

    @app.get("/api/recommendations")
    def recommendations():
        return jsonify(recommender.recommend_all())

    @app.get("/api/stocks/<symbol>")
    def stock_detail(symbol):
        symbol = symbol.upper()
        names = {w["symbol"]: w["name"] for w in db.get_watchlist()}
        prices = db.get_prices(symbol)
        if not prices:
            return jsonify({"error": "尚無資料，請先收集"}), 404
        df = indicators.compute(prices).tail(180)
        series = {
            col: [None if v != v else round(float(v), 2) for v in df[col]]
            for col in ("close", "ma20", "ma60", "rsi14")
        }
        series["date"] = list(df["date"])
        news = db.get_news(symbol, limit=40)
        for n in news:
            n["sentiment_label"] = sentiment.label(n["sentiment"])
        return jsonify({
            "symbol": symbol,
            "name": names.get(symbol),
            "recommendation": recommender.analyze(symbol, names.get(symbol), prices=prices),
            "series": series,
            "news": news,
        })

    @app.get("/api/news")
    def news():
        symbol = request.args.get("symbol")
        limit = min(int(request.args.get("limit", 50)), 200)
        items = db.get_news(symbol.upper() if symbol else None, limit=limit)
        for n in items:
            n["sentiment_label"] = sentiment.label(n["sentiment"])
        return jsonify(items)

    @app.post("/api/collect")
    def collect():
        data = request.get_json(silent=True) or {}
        symbols = [normalize_symbol(s) for s in data.get("symbols", [])] or None
        if symbols and not all(symbols):
            return jsonify({"error": "股票代號格式不正確"}), 400
        result = scheduler.run_now(symbols)
        if result is None:
            return jsonify({"error": "收集進行中，請稍後再試"}), 409
        return jsonify(result)

    return app


def normalize_symbol(raw):
    symbol = (raw or "").strip().upper()
    # 純數字視為台股上市代號，例如 2330 → 2330.TW
    if symbol.isdigit():
        symbol += ".TW"
    return symbol if SYMBOL_RE.match(symbol) else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("PORT", "5000"))
    create_app().run(host="0.0.0.0", port=port, debug=False)
