import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Use a temporary file-based SQLite DB so tables persist within the test session
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

from main import app, Base, engine, get_db, ADMIN_PASSWORD  # noqa: E402

# Create all tables in the test database
Base.metadata.create_all(bind=engine)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
headers = {"x-admin-password": ADMIN_PASSWORD}


@pytest.fixture(autouse=True)
def clean_posts():
    """Drop and recreate the posts table before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_create_post_include_timestamps_true():
    response = client.post(
        "/posts",
        json={"title": "Test", "text": "Body", "include_timestamps": True},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["include_timestamps"] is True


def test_create_post_include_timestamps_false():
    response = client.post(
        "/posts",
        json={"title": "No Time", "text": "Body", "include_timestamps": False},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["include_timestamps"] is False


def test_create_post_default_include_timestamps():
    response = client.post(
        "/posts",
        json={"title": "Default", "text": "Body"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["include_timestamps"] is True


def test_get_posts_returns_include_timestamps():
    client.post(
        "/posts",
        json={"title": "For GET", "text": "Body", "include_timestamps": True},
        headers=headers,
    )
    response = client.get("/posts")
    assert response.status_code == 200
    posts = response.json()
    assert len(posts) > 0
    for post in posts:
        assert "include_timestamps" in post


def test_update_post_include_timestamps():
    create_resp = client.post(
        "/posts",
        json={"title": "Update Me", "text": "Original", "include_timestamps": True},
        headers=headers,
    )
    post_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/posts/{post_id}",
        json={"title": "Updated", "text": "New body", "include_timestamps": False},
        headers=headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["include_timestamps"] is False


def test_update_post_include_timestamps_none_preserves_value():
    create_resp = client.post(
        "/posts",
        json={"title": "Preserve", "text": "Body", "include_timestamps": True},
        headers=headers,
    )
    post_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/posts/{post_id}",
        json={"title": "Preserve", "text": "Body"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["include_timestamps"] is True
