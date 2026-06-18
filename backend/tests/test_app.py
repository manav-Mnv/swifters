from io import BytesIO

import pytest

from app.server import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "attendance.db"))
    monkeypatch.setenv("FACES_DIR", str(tmp_path / "faces"))
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SESSION_SECRET", "testing")
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def login(client):
    return client.post("/api/login", json={"password": "secret"})


def create_event(client):
    login(client)
    response = client.post("/api/create-event", json={"name": "Meetup", "date": "2026-06-19", "club_name": "Swift"})
    assert response.status_code == 200


def test_geo_check_disabled_by_default(client):
    create_event(client)
    response = client.post("/api/check-location", json={"lat": 22.3, "lng": 73.1})
    assert response.status_code == 200
    assert response.get_json()["allowed"] is True


def test_import_rejects_wrong_file_type(client):
    create_event(client)
    response = client.post(
        "/api/import",
        data={"file": (BytesIO(b"oops"), "members.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_public_members_available(client):
    create_event(client)
    response = client.get("/api/public-members")
    assert response.status_code == 200
    assert response.get_json()["members"] == []
