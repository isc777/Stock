import pytest

from stockapp import config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "DEMO_MODE", True)
    yield


@pytest.fixture
def client():
    from app import create_app
    app = create_app(start_scheduler=False)
    return app.test_client()
