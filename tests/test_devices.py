import pytest

from stockapp import config


def test_pwa_files(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200
    assert m.get_json()["display"] == "standalone"
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "javascript" in sw.content_type
    for icon in m.get_json()["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/static/vendor/chart.umd.min.js").status_code == 200


def test_no_password_means_open(client):
    assert client.get("/api/watchlist").status_code == 200
    assert client.get("/login").status_code == 302


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD", "s3cret")
    from app import create_app
    return create_app(start_scheduler=False).test_client()


def test_password_protects_pages_and_api(locked):
    assert locked.get("/").status_code == 302
    assert locked.get("/api/watchlist").status_code == 401
    # PWA 安裝所需檔案不需登入
    assert locked.get("/manifest.webmanifest").status_code == 200
    assert locked.get("/sw.js").status_code == 200
    assert locked.get("/static/style.css").status_code == 200


def test_login_flow(locked):
    assert locked.post("/login", data={"password": "wrong"}).status_code == 401
    assert locked.post("/login", data={"password": "s3cret"}).status_code == 302
    assert locked.get("/api/watchlist").status_code == 200
    locked.post("/logout")
    assert locked.get("/api/watchlist").status_code == 401
