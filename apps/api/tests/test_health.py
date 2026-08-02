from fastapi.testclient import TestClient

from crv_api.main import app

client = TestClient(app)


def test_healthz_returns_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
