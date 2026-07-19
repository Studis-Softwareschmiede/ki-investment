from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_leitet_auf_depot_view_weiter() -> None:
    resp = TestClient(app).get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui/depot"
