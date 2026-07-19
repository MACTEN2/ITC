"""Test suite for the login activity log (GET /api/auth/login-activity)."""

from tests.conftest import DEFAULT_PASSWORD, auth_headers

LOGIN_ACTIVITY_URL = "/api/auth/login-activity"


def test_login_activity_requires_authentication(client):
    assert client.get(LOGIN_ACTIVITY_URL).status_code == 401


def test_registering_and_logging_in_records_one_event(client, learner_token):
    response = client.get(LOGIN_ACTIVITY_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    # TestClient's reported host can differ across httpx/Starlette versions --
    # assert presence, not a specific literal.
    assert entries[0]["ip_address"]
    assert "created_at" in entries[0]


def test_second_login_adds_a_newest_first_entry(client, learner_token):
    login = client.post("/api/auth/login", data={"username": "learner_alice", "password": DEFAULT_PASSWORD})
    assert login.status_code == 200
    new_token = login.json()["access_token"]

    response = client.get(LOGIN_ACTIVITY_URL, headers=auth_headers(new_token))
    entries = response.json()
    assert len(entries) == 2
    assert entries[0]["created_at"] >= entries[1]["created_at"]
