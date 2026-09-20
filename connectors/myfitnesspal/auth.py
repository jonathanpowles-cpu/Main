"""Password-protected OAuth 2.1 authorization server for hosted deployments.

claude.ai custom connectors talk to a remote MCP server over HTTPS and
authenticate with OAuth (dynamic client registration + authorization code +
PKCE). This module is the smallest authorization server that satisfies that
flow for a single-user connector:

* ``/authorize`` redirects to a login page that asks for one password
  (``CONNECTOR_PASSWORD``).
* Client registrations, authorization codes, access tokens and refresh tokens
  are all HMAC-signed blobs, so nothing needs a database and a restart or
  redeploy does not log Claude out. Revoked tokens and used codes are kept in
  memory only, which is acceptable for a single-user service.

Never run the HTTP transport without this provider: the server holds your
MyFitnessPal session cookies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from typing import Any

from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

SCOPE = "mfp"
TXN_TTL = 10 * 60
CODE_TTL = 5 * 60
ACCESS_TTL = 60 * 60
REFRESH_TTL = 30 * 24 * 60 * 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordAuthProvider:
    """``OAuthAuthorizationServerProvider`` guarded by a single password."""

    def __init__(self, password: str, public_url: str, secret: str | None = None) -> None:
        if not password:
            raise ValueError("A non-empty password is required")
        self._password = password
        self.public_url = public_url.rstrip("/")
        self._key = hashlib.sha256(f"mfp-connector:{secret or password}".encode()).digest()
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._used_codes: set[str] = set()
        self._revoked: set[str] = set()

    # -- signed blobs ---------------------------------------------------------

    def _sign(self, payload: dict[str, Any]) -> str:
        body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        sig = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def _verify(self, token: str, kind: str) -> dict[str, Any] | None:
        try:
            body, sig = token.split(".", 1)
            expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(_unb64(body))
        except (ValueError, TypeError):
            return None
        if payload.get("k") != kind:
            return None
        if payload.get("exp") is not None and payload["exp"] < time.time():
            return None
        return payload

    # -- clients (dynamic registration) --------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if client_id in self._clients:
            return self._clients[client_id]
        payload = self._verify(client_id, "client")
        if payload is None:
            return None
        metadata = payload["m"]
        secret = self._client_secret(client_id) if metadata.get("token_endpoint_auth_method") != "none" else None
        client = OAuthClientInformationFull.model_validate(
            {**metadata, "client_id": client_id, "client_secret": secret, "client_secret_expires_at": 0}
        )
        self._clients[client_id] = client
        return client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        metadata = client_info.model_dump(
            mode="json",
            exclude={"client_id", "client_secret", "client_id_issued_at", "client_secret_expires_at"},
            exclude_none=True,
        )
        # Encode the registration in the client_id so it survives restarts.
        client_info.client_id = self._sign({"k": "client", "m": metadata, "n": secrets.token_hex(4)})
        if client_info.client_secret is not None:
            client_info.client_secret = self._client_secret(client_info.client_id)
        self._clients[client_info.client_id] = client_info

    def _client_secret(self, client_id: str) -> str:
        return hmac.new(self._key, f"secret:{client_id}".encode(), hashlib.sha256).hexdigest()

    # -- authorization --------------------------------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        txn = self._sign(
            {
                "k": "txn",
                "client_id": client.client_id,
                "client_name": client.client_name or "",
                "redirect_uri": str(params.redirect_uri),
                "explicit": params.redirect_uri_provided_explicitly,
                "cc": params.code_challenge,
                "scopes": params.scopes or [SCOPE],
                "state": params.state,
                "resource": params.resource,
                "exp": time.time() + TXN_TTL,
            }
        )
        return f"{self.public_url}/login?txn={txn}"

    async def login_page(self, request: Request) -> Response:
        txn = request.query_params.get("txn", "")
        if self._verify(txn, "txn") is None:
            return HTMLResponse(_page("This sign-in link is invalid or has expired. Start again from Claude."), 400)
        return HTMLResponse(_login_form(txn, self._verify(txn, "txn")["client_name"]))

    async def login_submit(self, request: Request) -> Response:
        form = await request.form()
        txn = str(form.get("txn", ""))
        payload = self._verify(txn, "txn")
        if payload is None:
            return HTMLResponse(_page("This sign-in link is invalid or has expired. Start again from Claude."), 400)
        password = str(form.get("password", ""))
        if not hmac.compare_digest(password.encode(), self._password.encode()):
            return HTMLResponse(_login_form(txn, payload["client_name"], error="Wrong password."), 401)
        code = self._sign(
            {
                "k": "code",
                "client_id": payload["client_id"],
                "redirect_uri": payload["redirect_uri"],
                "explicit": payload["explicit"],
                "cc": payload["cc"],
                "scopes": payload["scopes"],
                "resource": payload["resource"],
                "exp": time.time() + CODE_TTL,
                "n": secrets.token_hex(8),
            }
        )
        location = construct_redirect_uri(payload["redirect_uri"], code=code, state=payload["state"])
        return RedirectResponse(location, status_code=302, headers={"Cache-Control": "no-store"})

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        payload = self._verify(authorization_code, "code")
        if payload is None or payload["client_id"] != client.client_id or _hash(authorization_code) in self._used_codes:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=payload["scopes"],
            expires_at=payload["exp"],
            client_id=payload["client_id"],
            code_challenge=payload["cc"],
            redirect_uri=AnyUrl(payload["redirect_uri"]),
            redirect_uri_provided_explicitly=payload["explicit"],
            resource=payload["resource"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._used_codes.add(_hash(authorization_code.code))
        return self._issue_tokens(client.client_id, authorization_code.scopes, authorization_code.resource)

    # -- tokens -----------------------------------------------------------------

    def _issue_tokens(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = time.time()
        common = {"client_id": client_id, "scopes": scopes, "resource": resource}
        access = self._sign({"k": "access", "exp": now + ACCESS_TTL, "n": secrets.token_hex(8), **common})
        refresh = self._sign({"k": "refresh", "exp": now + REFRESH_TTL, "n": secrets.token_hex(8), **common})
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        payload = self._verify(token, "access")
        if payload is None or _hash(token) in self._revoked:
            return None
        return AccessToken(
            token=token,
            client_id=payload["client_id"],
            scopes=payload["scopes"],
            expires_at=int(payload["exp"]),
            resource=payload["resource"],
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        payload = self._verify(refresh_token, "refresh")
        if payload is None or payload["client_id"] != client.client_id or _hash(refresh_token) in self._revoked:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=payload["client_id"],
            scopes=payload["scopes"],
            expires_at=int(payload["exp"]),
            resource=payload["resource"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        if scopes and not set(scopes).issubset(refresh_token.scopes):
            raise TokenError("invalid_scope", "Requested scopes exceed the original grant")
        self._revoked.add(_hash(refresh_token.token))
        return self._issue_tokens(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._revoked.add(_hash(token.token))


# -- HTML ----------------------------------------------------------------------

_STYLE = """
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111;color:#eee;
font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
main{width:min(360px,90vw);padding:2rem;background:#1c1c1c;border:1px solid #333;border-radius:12px}
h1{font-size:1.2rem;margin:0 0 .5rem}p{margin:.5rem 0;color:#bbb}
input,button{width:100%;box-sizing:border-box;padding:.7rem;border-radius:8px;border:1px solid #444;font-size:1rem}
input{background:#111;color:#eee;margin:.75rem 0}button{background:#3b82f6;color:#fff;border:0;cursor:pointer}
.err{color:#f87171}
"""


def _page(body_html: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>" \
           f"<title>MyFitnessPal connector</title><style>{_STYLE}</style></head><body><main>{body_html}</main></body></html>"


def _login_form(txn: str, client_name: str, error: str | None = None) -> str:
    who = html.escape(client_name) if client_name else "An application"
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    return _page(
        f"<h1>MyFitnessPal connector</h1><p>{who} wants to create foods in your MyFitnessPal account.</p>"
        f"{err}<form method='post' action='/login'><input type='hidden' name='txn' value='{html.escape(txn)}'>"
        f"<input type='password' name='password' placeholder='Connector password' autofocus required>"
        f"<button type='submit'>Allow</button></form>"
    )
