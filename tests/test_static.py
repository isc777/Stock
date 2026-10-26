import json

from stockapp import build_static, config, db, watchlist


def test_parse_watchlist():
    text = """
    # 註解
    2330 台積電
    2330.TW 重複的會略過
    aapl
    台積電 2330
    00878.TW 國泰永續高股息  # 行尾註解
    """
    assert watchlist.parse(text) == [
        ("2330.TW", "台積電"),
        ("AAPL", None),
        ("00878.TW", "國泰永續高股息"),
    ]


def test_build_static_site(tmp_path, monkeypatch):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("2330 台積電\nNVDA\n", encoding="utf-8")
    monkeypatch.setattr(config, "WATCHLIST_FILE", wl)
    out = tmp_path / "site"

    run, recs = build_static.build(out, repo_url="https://github.com/me/repo", branch="main")

    assert {r["symbol"] for r in recs} == {"2330.TW", "NVDA"}
    assert run["errors"] == []
    data = out / "data"
    saved = json.loads((data / "recommendations.json").read_text(encoding="utf-8"))
    assert saved == json.loads(json.dumps(recs))
    detail = json.loads((data / "stocks" / "2330.TW.json").read_text(encoding="utf-8"))
    assert detail["name"] == "台積電" and detail["news"]
    assert json.loads((data / "status.json").read_text())["mode"] == "static"
    for f in ("index.html", "sw.js", "manifest.webmanifest", ".nojekyll",
              "static/app.js", "static/vendor/chart.umd.min.js"):
        assert (out / f).exists(), f

    html = (out / "index.html").read_text(encoding="utf-8")
    assert '"mode": "static"' in html and '"repo": "me/repo"' in html and '"branch": "main"' in html
    assert "https://github.com/me/repo/edit/main/watchlist.txt" in html  # 沒有 token 時的備用連結
    assert 'id="gh-dialog"' in html and "static/github.js" in html
    assert "target_name=me" in html
    assert 'src="/' not in html and 'href="/' not in html  # 子路徑（/Stock/）下也要能用


def test_build_follows_watchlist_file(tmp_path, monkeypatch):
    wl = tmp_path / "watchlist.txt"
    wl.write_text("AAPL\nMSFT\n", encoding="utf-8")
    monkeypatch.setattr(config, "WATCHLIST_FILE", wl)
    build_static.build(tmp_path / "a")
    wl.write_text("MSFT\n", encoding="utf-8")
    _, recs = build_static.build(tmp_path / "b", collect=False)
    assert [r["symbol"] for r in recs] == ["MSFT"]
    assert [w["symbol"] for w in db.get_watchlist()] == ["MSFT"]


def test_data_file_matches_frontend():
    assert build_static.data_file("^TWII") == "_TWII"
    assert build_static.data_file("2330.TW") == "2330.TW"
