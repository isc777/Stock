"""股票推薦 App 入口。

    python app.py                 # 使用真實資料（需可連到 Yahoo Finance / Google 新聞）
    STOCK_DEMO=1 python app.py    # 離線展示模式
"""
import hmac
import logging
import os
import re
import socket
import threading
from datetime import timedelta

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

from stockapp import config, db, indicators, recommender, sentiment
from stockapp.scheduler import CollectorScheduler

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")

# 不需登入即可存取的路徑（登入頁本身與 PWA 安裝所需檔案）
PUBLIC_PATHS = {"/login", "/manifest.webmanifest", "/sw.js"}


def create_app(start_scheduler=True):
    app = Flask(__name__)
    app.secret_key = config.secret_key()
    app.permanent_session_lifetime = timedelta(days=90)
    db.init_db()

    @app.before_request
    def require_login():
        if not config.APP_PASSWORD or session.get("auth"):
            return None
        if request.path in PUBLIC_PATHS or request.path.startswith("/static/"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "請先登入"}), 401
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not config.APP_PASSWORD:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            given = request.form.get("password", "")
            if hmac.compare_digest(given.encode(), config.APP_PASSWORD.encode()):
                session.permanent = True
                session["auth"] = True
                return redirect(url_for("index"))
            error = "密碼錯誤"
        return render_template("login.html", error=error), 401 if error else 200

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # Service worker 必須從根路徑提供，才能控制整個網站
    @app.get("/sw.js")
    def service_worker():
        resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest",
                                   mimetype="application/manifest+json")
    scheduler = CollectorScheduler()
    app.config["SCHEDULER"] = scheduler
    if start_scheduler:
        scheduler.start()

    @app.get("/")
    def index():
        return render_template("index.html", demo=config.DEMO_MODE,
                               auth=bool(config.APP_PASSWORD))

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


def lan_addresses():
    """猜測本機在區域網路中的 IP，方便手機 / 平板連線。"""
    addrs = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # 不會真的送出封包，只用來找出對外網卡
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()

    print(f"\n  電腦上開啟： http://localhost:{port}")
    if host == "0.0.0.0":
        for ip in lan_addresses():
            print(f"  手機 / 平板（同一個 Wi-Fi）： http://{ip}:{port}")
    if not config.APP_PASSWORD:
        print("  提示：若要開放到網際網路，請設定 APP_PASSWORD 環境變數啟用登入")
    print()

    try:
        from waitress import serve
    except ImportError:
        app.run(host=host, port=port, debug=False)
    else:
        serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
