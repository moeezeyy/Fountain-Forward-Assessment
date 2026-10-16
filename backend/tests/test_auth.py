from tests.conftest import login


def test_login_with_valid_credentials_succeeds(client):
    resp, headers = login(client, "admin1@northgate.test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin1@northgate.test"
    assert body["role"] == "admin"
    assert "session" in resp.cookies


def test_login_with_invalid_password_rejected(client):
    resp, _ = login(client, "admin1@northgate.test", password="wrong-password")
    assert resp.status_code == 401


def test_login_with_unknown_email_rejected(client):
    resp, _ = login(client, "nobody@northgate.test")
    assert resp.status_code == 401


def test_protected_route_without_cookie_rejected(client):
    resp = client.get("/api/vehicles")
    assert resp.status_code == 401


def test_protected_route_with_garbage_cookie_rejected(client):
    resp = client.get("/api/vehicles", headers={"Cookie": "session=not-a-real-token"})
    assert resp.status_code == 401


def test_logout_invalidates_prior_session(client):
    _, headers = login(client, "admin1@northgate.test")

    ok = client.get("/api/vehicles", headers=headers)
    assert ok.status_code == 200

    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # The old token is still cryptographically valid and unexpired, but its
    # embedded token_version no longer matches the user's current value.
    after_logout = client.get("/api/vehicles", headers=headers)
    assert after_logout.status_code == 401


def test_health_endpoint_exposes_no_secrets(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}
