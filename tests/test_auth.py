"""Microsoft Entra ID 登录与 Session 鉴权测试。"""


class FakeMsalApp:
    def __init__(self, flow=None, result=None, error=None):
        self.flow = flow or {
            "auth_uri": "https://login.microsoftonline.com/test/oauth2/v2.0/authorize",
            "state": "test-state",
        }
        self.result = result or {}
        self.error = error
        self.received_flow = None
        self.received_response = None

    def initiate_auth_code_flow(self, scopes, redirect_uri):
        assert scopes == []
        assert redirect_uri == "https://example.com/api/auth/callback"
        return self.flow

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        self.received_flow = flow
        self.received_response = auth_response
        if self.error:
            raise self.error
        return self.result


def _set_aad_environment(monkeypatch):
    monkeypatch.setenv("AAD_CLIENT_ID", "client-id")
    monkeypatch.setenv("AAD_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AAD_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AAD_REDIRECT_URI", "https://example.com/api/auth/callback")


def test_auth_status_when_logged_out(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False, "user": None}


def test_auth_login_stores_flow_and_redirects(client, app_module, monkeypatch):
    _set_aad_environment(monkeypatch)
    fake_app = FakeMsalApp()
    monkeypatch.setattr(app_module.auth_module, "_build_msal_app", lambda settings: fake_app)

    response = client.get("/api/auth/login")

    assert response.status_code == 302
    assert response.location == fake_app.flow["auth_uri"]
    with client.session_transaction() as flask_session:
        assert flask_session["aad_auth_flow"]["state"] == "test-state"


def test_auth_callback_stores_minimal_user_and_redirects(client, app_module, monkeypatch):
    _set_aad_environment(monkeypatch)
    fake_app = FakeMsalApp(
        result={
            "access_token": "must-not-be-stored",
            "id_token_claims": {
                "oid": "user-object-id",
                "name": "Test User",
                "preferred_username": "test@example.com",
            },
        }
    )
    monkeypatch.setattr(app_module.auth_module, "_build_msal_app", lambda settings: fake_app)
    with client.session_transaction() as flask_session:
        flask_session["aad_auth_flow"] = {"state": "test-state", "nonce": "nonce"}

    response = client.get("/api/auth/callback?code=code&state=test-state")

    assert response.status_code == 302
    assert response.location.endswith("/")
    with client.session_transaction() as flask_session:
        assert flask_session["aad_user"] == {
            "id": "user-object-id",
            "name": "Test User",
            "username": "test@example.com",
        }
        assert "aad_auth_flow" not in flask_session
        assert "access_token" not in flask_session


def test_auth_callback_rejects_missing_flow(client):
    response = client.get("/api/auth/callback?code=code&state=wrong")
    assert response.status_code == 400


def test_auth_callback_rejects_invalid_state(client, app_module, monkeypatch):
    _set_aad_environment(monkeypatch)
    fake_app = FakeMsalApp(error=ValueError("state mismatch"))
    monkeypatch.setattr(app_module.auth_module, "_build_msal_app", lambda settings: fake_app)
    with client.session_transaction() as flask_session:
        flask_session["aad_auth_flow"] = {"state": "expected-state"}

    response = client.get("/api/auth/callback?code=code&state=wrong-state")
    assert response.status_code == 400


def test_auth_callback_rejects_msal_error(client, app_module, monkeypatch):
    _set_aad_environment(monkeypatch)
    fake_app = FakeMsalApp(result={"error": "access_denied", "error_description": "denied"})
    monkeypatch.setattr(app_module.auth_module, "_build_msal_app", lambda settings: fake_app)
    with client.session_transaction() as flask_session:
        flask_session["aad_auth_flow"] = {"state": "test-state"}

    response = client.get("/api/auth/callback?error=access_denied&state=test-state")
    assert response.status_code == 401


def test_auth_status_and_generate_with_aad_session(client):
    with client.session_transaction() as flask_session:
        flask_session["aad_user"] = {
            "id": "user-object-id",
            "name": "Test User",
            "username": "test@example.com",
        }

    status_response = client.get("/api/auth/status")
    assert status_response.get_json()["authenticated"] is True

    generate_response = client.post("/api/generate", json={"prompt": "a cat"})
    assert generate_response.status_code == 202


def test_auth_logout_clears_login_and_flow(client):
    with client.session_transaction() as flask_session:
        flask_session["aad_user"] = {"id": "user-object-id"}
        flask_session["aad_auth_flow"] = {"state": "test-state"}

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}
    with client.session_transaction() as flask_session:
        assert "aad_user" not in flask_session
        assert "aad_auth_flow" not in flask_session


def test_missing_aad_config_does_not_break_access_code(client, monkeypatch):
    for name in ("AAD_CLIENT_ID", "AAD_CLIENT_SECRET", "AAD_TENANT_ID", "AAD_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)

    login_response = client.get("/api/auth/login")
    assert login_response.status_code == 503
    assert "Microsoft 登录未配置" in login_response.get_json()["error"]

    generate_response = client.post(
        "/api/generate",
        json={"access_code": "test-code", "prompt": "a cat"},
    )
    assert generate_response.status_code == 202
