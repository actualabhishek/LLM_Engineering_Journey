from fastapi.testclient import TestClient

from app.main import STATIC_DIR, app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_boots_without_static_dir():
    # Local dev has no built frontend/out copied into app/static; the app
    # must still start and serve /health without mounting a static route.
    assert not STATIC_DIR.is_dir()
    response = client.get("/health")
    assert response.status_code == 200
