from fastapi.testclient import TestClient

import app.api.admin as admin_api
from app.main import app


def make_client() -> TestClient:
    # https:// base_url so the Secure session cookie (https_only=True) round-trips,
    # matching a real browser talking to the app over HTTPS.
    return TestClient(app, base_url="https://testserver")


def test_login_wrong_password(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "correct-horse")
    client = make_client()
    response = client.post("/api/admin/login", json={"password": "wrong"})
    assert response.status_code == 401


def test_login_empty_configured_password_always_fails(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "")
    client = make_client()
    response = client.post("/api/admin/login", json={"password": ""})
    assert response.status_code == 401


def test_login_correct_password_succeeds(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "correct-horse")
    client = make_client()
    response = client.post("/api/admin/login", json={"password": "correct-horse"})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_protected_endpoint_requires_login(seeded_db):
    client = make_client()
    response = client.get("/api/admin/bookings")
    assert response.status_code == 401


def test_bookings_checkins_conversations_after_login(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "correct-horse")
    client = make_client()
    login = client.post("/api/admin/login", json={"password": "correct-horse"})
    assert login.status_code == 200

    bookings = client.get("/api/admin/bookings")
    assert bookings.status_code == 200
    body = bookings.json()
    assert len(body) >= 1
    names = {row["guest_name"] for row in body}
    assert names & {"Asha Rao", "Rohan Verma"}
    assert all("room_type_name" in row and "total_price_paise" in row for row in body)

    checkins = client.get("/api/admin/checkins")
    assert checkins.status_code == 200
    assert checkins.json() == []

    conversations = client.get("/api/admin/conversations")
    assert conversations.status_code == 200
    assert conversations.json() == []


def test_conversation_detail_404(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "correct-horse")
    client = make_client()
    client.post("/api/admin/login", json={"password": "correct-horse"})
    response = client.get("/api/admin/conversations/999")
    assert response.status_code == 404


def test_logout_clears_session(seeded_db, monkeypatch):
    monkeypatch.setattr(admin_api.settings, "admin_password", "correct-horse")
    client = make_client()
    client.post("/api/admin/login", json={"password": "correct-horse"})
    assert client.get("/api/admin/bookings").status_code == 200

    logout = client.post("/api/admin/logout")
    assert logout.status_code == 200
    assert logout.json() == {"authenticated": False}

    assert client.get("/api/admin/bookings").status_code == 401
