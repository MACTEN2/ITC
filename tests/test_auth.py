"""Test suite for registration, login, and JWT-protected access.

Covers the security-sensitive paths explicitly: duplicate accounts, wrong
credentials, missing/malformed tokens, and that password hashes are never
echoed back over the API.
"""

from app.routes.auth import hash_password
from tests.conftest import DEFAULT_PASSWORD, auth_headers

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_creates_user_with_zero_starting_stats(client):
    response = client.post(
        REGISTER_URL,
        json={"username": "newbie", "email": "newbie@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "newbie"
    assert body["email"] == "newbie@example.com"
    assert body["current_role"] == "Help Desk Tier 1"
    assert body["is_admin"] is False
    assert body["networking_xp"] == 0
    assert body["automation_xp"] == 0
    assert body["database_xp"] == 0
    assert body["infra_points"] == 0
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_duplicate_username(client):
    client.post(REGISTER_URL, json={"username": "dup", "email": "a@example.com", "password": DEFAULT_PASSWORD})
    response = client.post(
        REGISTER_URL, json={"username": "dup", "email": "different@example.com", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 400


def test_register_rejects_duplicate_email(client):
    client.post(REGISTER_URL, json={"username": "user_one", "email": "shared@example.com", "password": DEFAULT_PASSWORD})
    response = client.post(
        REGISTER_URL, json={"username": "user_two", "email": "shared@example.com", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 400


def test_register_rejects_invalid_email_format(client):
    response = client.post(
        REGISTER_URL, json={"username": "bademail", "email": "not-an-email", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post(
        REGISTER_URL, json={"username": "shortpw", "email": "shortpw@example.com", "password": "short"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_success_returns_bearer_token(client):
    client.post(REGISTER_URL, json={"username": "loginok", "email": "loginok@example.com", "password": DEFAULT_PASSWORD})

    response = client.post(LOGIN_URL, data={"username": "loginok", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 0


def test_login_wrong_password_rejected(client):
    client.post(REGISTER_URL, json={"username": "wrongpw", "email": "wrongpw@example.com", "password": DEFAULT_PASSWORD})

    response = client.post(LOGIN_URL, data={"username": "wrongpw", "password": "definitely-not-it"})
    assert response.status_code == 401


def test_login_unknown_username_rejected(client):
    response = client.post(LOGIN_URL, data={"username": "ghost_user", "password": DEFAULT_PASSWORD})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token-protected access
# ---------------------------------------------------------------------------


def test_protected_endpoint_rejects_missing_token(client):
    response = client.get("/api/tickets")
    assert response.status_code == 401


def test_protected_endpoint_rejects_malformed_token(client):
    response = client.get("/api/tickets", headers=auth_headers("not-a-real-jwt"))
    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_token(client, learner_token):
    response = client.get("/api/tickets", headers=auth_headers(learner_token))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------


def test_me_returns_own_profile(client):
    client.post(REGISTER_URL, json={"username": "profileuser", "email": "profileuser@example.com", "password": DEFAULT_PASSWORD})
    login_response = client.post(LOGIN_URL, data={"username": "profileuser", "password": DEFAULT_PASSWORD})
    token = login_response.json()["access_token"]

    response = client.get("/api/auth/me", headers=auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "profileuser"
    assert body["is_admin"] is False
    assert "password" not in body
    assert "hashed_password" not in body


def test_me_rejects_missing_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Password hashing (unit-level, exercised directly rather than over HTTP)
# ---------------------------------------------------------------------------


def test_password_hashing_is_salted_per_call():
    hash_one = hash_password(DEFAULT_PASSWORD)
    hash_two = hash_password(DEFAULT_PASSWORD)
    assert hash_one != hash_two, "bcrypt must salt independently on every hash call"
