"""Test suite for self-service profile editing (PATCH /api/auth/me)."""

from tests.conftest import DEFAULT_PASSWORD, auth_headers

ME_URL = "/api/auth/me"


def test_update_email_succeeds_and_is_reflected_in_me(client, learner_token):
    response = client.patch(ME_URL, json={"email": "new-address@example.com"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    assert response.json()["email"] == "new-address@example.com"

    me = client.get(ME_URL, headers=auth_headers(learner_token))
    assert me.json()["email"] == "new-address@example.com"


def test_update_email_to_one_already_in_use_is_rejected(client, learner_token):
    client.post(
        "/api/auth/register",
        json={"username": "other_user", "email": "taken@example.com", "password": DEFAULT_PASSWORD},
    )

    response = client.patch(ME_URL, json={"email": "taken@example.com"}, headers=auth_headers(learner_token))
    assert response.status_code == 400


def test_password_change_requires_correct_current_password(client, learner_token):
    response = client.patch(
        ME_URL,
        json={"current_password": "totally-wrong-password", "new_password": "brand-new-password123"},
        headers=auth_headers(learner_token),
    )
    assert response.status_code == 400


def test_successful_password_change_allows_login_with_new_password_and_rejects_old(client, learner_token):
    response = client.patch(
        ME_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-password123"},
        headers=auth_headers(learner_token),
    )
    assert response.status_code == 200

    old_login = client.post("/api/auth/login", data={"username": "learner_alice", "password": DEFAULT_PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login", data={"username": "learner_alice", "password": "brand-new-password123"}
    )
    assert new_login.status_code == 200


def test_patch_with_no_fields_is_rejected(client, learner_token):
    response = client.patch(ME_URL, json={}, headers=auth_headers(learner_token))
    assert response.status_code == 400


def test_patch_without_token_requires_authentication(client):
    response = client.patch(ME_URL, json={"email": "someone@example.com"})
    assert response.status_code == 401
