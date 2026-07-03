"""Shared pytest fixtures for the ITC test suite.

Every test gets a completely fresh SQLite database: the engine's connection
pool is disposed and `itc_database.db` is deleted before the app's
startup/seeding lifespan runs (and again after). This guarantees every test
starts from zero users and zero progress, so results are deterministic
regardless of test order or how many times the suite has run before.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import User

DB_PATH = Path(__file__).resolve().parent.parent / "itc_database.db"

DEFAULT_PASSWORD = "correcthorsebattery"


def _reset_database() -> None:
    """Close pooled connections and delete the SQLite file for a clean slate."""
    engine.dispose()
    if DB_PATH.exists():
        DB_PATH.unlink()


@pytest.fixture()
def client():
    """A TestClient backed by a freshly seeded, empty-progress database."""
    _reset_database()
    with TestClient(app) as test_client:
        yield test_client
    _reset_database()


def register_and_login(client: TestClient, username: str, password: str = DEFAULT_PASSWORD) -> str:
    """Register a new account and return a bearer access token for it."""
    register_response = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def promote_to_admin(username: str) -> None:
    """Flip `is_admin=True` directly via the DB.

    There is deliberately no API endpoint for self-service admin promotion --
    granting admin access is meant to be an out-of-band operational action,
    not something reachable through the HTTP surface.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def learner_token(client) -> str:
    """A freshly registered, non-admin account's bearer token."""
    return register_and_login(client, "learner_alice")


@pytest.fixture()
def admin_token(client) -> str:
    """A freshly registered account's bearer token, promoted to admin."""
    token = register_and_login(client, "root_admin")
    promote_to_admin("root_admin")
    return token
