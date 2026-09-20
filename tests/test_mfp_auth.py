"""End-to-end test of the hosted transport: OAuth flow + authenticated MCP call."""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from connectors.myfitnesspal.auth import PasswordAuthProvider
from connectors.myfitnesspal.server import create_server

PUBLIC_URL = "http://localhost"
PASSWORD = "hunter2"
REDIRECT = "https://claude.ai/api/mcp/auth_callback"


class RecordingClient:
    def create_food(self, spec):
        return {"id": "food-1", "description": spec.name, "brand": spec.brand, "item": {}}


def _app(secret="stable-secret"):
    from mcp.server.transport_security import TransportSecuritySettings

    auth = PasswordAuthProvider(PASSWORD, PUBLIC_URL, secret=secret)
    server = create_server(client_factory=RecordingClient, auth=auth)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=["localhost", "localhost:*"], allowed_origins=[PUBLIC_URL]
    )
    return server.streamable_http_app(host="0.0.0.0", transport_security=security)


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _register(client):
    r = client.post(
        "/register",
        json={
            "redirect_uris": [REDIRECT],
            "client_name": "Claude",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _authorize(client, reg, challenge, password=PASSWORD):
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "mfp",
            "resource": f"{PUBLIC_URL}/mcp",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    login_url = r.headers["location"]
    assert login_url.startswith(f"{PUBLIC_URL}/login?txn=")
    txn = parse_qs(urlparse(login_url).query)["txn"][0]

    page = client.get("/login", params={"txn": txn})
    assert page.status_code == 200
    assert "Claude" in page.text and "password" in page.text

    return client.post("/login", data={"txn": txn, "password": password}, follow_redirects=False)


def _token(client, reg, code, verifier):
    return client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
            "code_verifier": verifier,
            "redirect_uri": REDIRECT,
            "resource": f"{PUBLIC_URL}/mcp",
        },
    )


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def test_metadata_advertises_registration_and_login_flow():
    with TestClient(_app(), base_url=PUBLIC_URL) as client:
        meta = client.get("/.well-known/oauth-authorization-server").json()
        assert meta["issuer"].rstrip("/") == PUBLIC_URL
        assert meta["registration_endpoint"].endswith("/register")
        assert client.get("/health").json() == {"status": "ok"}


def test_full_oauth_flow_and_authenticated_mcp_call():
    with TestClient(_app(), base_url=PUBLIC_URL) as client:
        reg = _register(client)
        verifier, challenge = _pkce()

        # Wrong password is refused and no code is issued.
        denied = _authorize(client, reg, challenge, password="nope")
        assert denied.status_code == 401
        assert "Wrong password" in denied.text

        granted = _authorize(client, reg, challenge)
        assert granted.status_code == 302
        target = urlparse(granted.headers["location"])
        assert f"{target.scheme}://{target.netloc}{target.path}" == REDIRECT
        query = parse_qs(target.query)
        assert query["state"] == ["xyz"]
        code = query["code"][0]

        tokens = _token(client, reg, code, verifier)
        assert tokens.status_code == 200, tokens.text
        access = tokens.json()["access_token"]
        refresh = tokens.json()["refresh_token"]

        # Codes are single-use.
        assert _token(client, reg, code, verifier).status_code == 400

        # MCP endpoint requires the bearer token.
        assert client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS).status_code == 401
        ok = client.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": f"Bearer {access}"})
        assert ok.status_code == 200, ok.text
        assert "myfitnesspal-nutrients" in ok.text

        # Refresh rotates tokens and invalidates the old refresh token.
        refreshed = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": reg["client_id"],
                "client_secret": reg["client_secret"],
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["access_token"] != access
        again = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": reg["client_id"],
                "client_secret": reg["client_secret"],
            },
        )
        assert again.status_code == 400


def test_tokens_and_clients_survive_restart_with_same_secret():
    with TestClient(_app(), base_url=PUBLIC_URL) as client:
        reg = _register(client)
        verifier, challenge = _pkce()
        code = parse_qs(urlparse(_authorize(client, reg, challenge).headers["location"]).query)["code"][0]
        access = _token(client, reg, code, verifier).json()["access_token"]

    # A fresh process with the same secret still accepts the client and token...
    with TestClient(_app(), base_url=PUBLIC_URL) as client:
        ok = client.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": f"Bearer {access}"})
        assert ok.status_code == 200
        assert client.get(
            "/authorize",
            params={"response_type": "code", "client_id": reg["client_id"], "redirect_uri": REDIRECT,
                    "code_challenge": challenge, "code_challenge_method": "S256"},
            follow_redirects=False,
        ).status_code == 302

    # ...and one with a different secret does not.
    with TestClient(_app(secret="other"), base_url=PUBLIC_URL) as client:
        assert client.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": f"Bearer {access}"}).status_code == 401


def test_expired_or_forged_login_link_is_rejected():
    with TestClient(_app(), base_url=PUBLIC_URL) as client:
        assert client.get("/login", params={"txn": "forged.token"}).status_code == 400
        assert client.post("/login", data={"txn": "forged.token", "password": PASSWORD}).status_code == 400


def test_password_required():
    with pytest.raises(ValueError):
        PasswordAuthProvider("", PUBLIC_URL)
