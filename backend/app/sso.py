"""
Generic OpenID Connect SSO.

This intentionally does not hard-code any particular identity provider -
any OIDC-compliant IdP (Okta, Azure AD / Entra ID, Auth0, Google Workspace,
Ping, Keycloak, ...) works as long as its issuer URL is reachable and
publishes the standard `/.well-known/openid-configuration` discovery
document. SSO is entirely optional: if `SSO_ISSUER`/`SSO_CLIENT_ID` aren't
set, every endpoint here reports itself as disabled and the app falls back
to local username/password auth only.

Flow (Authorization Code):
  1. Browser hits  GET /api/auth/sso/login
  2. We redirect to the IdP's authorization endpoint with a signed `state`
  3. User authenticates at the IdP, which redirects back to
     GET /api/auth/sso/callback?code=...&state=...
  4. We exchange the code for tokens, verify the ID token's signature
     against the IdP's published JWKS, extract the user's identity, and
     find-or-create a local user record for them (defaulting to the
     configured `sso_default_role`)
  5. We issue our own app JWT (same as local login) and redirect the
     browser back to the SPA with it
"""
import time
import secrets
from typing import Optional

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt

from .config import settings
from .auth import find_or_create_sso_user, create_access_token
from .logging_config import log_event

# short-lived in-memory state store for CSRF protection during the redirect
# round-trip (single-process app, so this is fine - like the broker, swap for
# a shared store e.g. Redis if you run multiple replicas behind a load balancer)
_PENDING_STATES: dict[str, float] = {}
_STATE_TTL_SECONDS = 600


def is_sso_enabled() -> bool:
    return bool(settings.sso_issuer and settings.sso_client_id)


def _discover() -> dict:
    resp = requests.get(f"{settings.sso_issuer.rstrip('/')}/.well-known/openid-configuration", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _cleanup_states():
    now = time.time()
    expired = [s for s, ts in _PENDING_STATES.items() if now - ts > _STATE_TTL_SECONDS]
    for s in expired:
        _PENDING_STATES.pop(s, None)


async def start_login():
    if not is_sso_enabled():
        raise HTTPException(status_code=404, detail="SSO is not configured")

    try:
        discovery = _discover()
    except requests.RequestException as exc:
        log_event("error", f"SSO: failed to fetch discovery document: {exc}")
        raise HTTPException(status_code=502, detail="Could not reach identity provider")

    _cleanup_states()
    state = secrets.token_urlsafe(24)
    _PENDING_STATES[state] = time.time()

    params = {
        "response_type": "code",
        "client_id": settings.sso_client_id,
        "redirect_uri": settings.sso_redirect_uri,
        "scope": settings.sso_scope,
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    auth_url = f"{discovery['authorization_endpoint']}?{query}"
    log_event("info", "SSO: redirecting to identity provider for login")
    return RedirectResponse(auth_url)


async def handle_callback(code: Optional[str], state: Optional[str], error: Optional[str]):
    if not is_sso_enabled():
        raise HTTPException(status_code=404, detail="SSO is not configured")

    if error:
        raise HTTPException(status_code=400, detail=f"Identity provider returned an error: {error}")
    if not code or not state or state not in _PENDING_STATES:
        raise HTTPException(status_code=400, detail="Invalid or expired SSO state")
    _PENDING_STATES.pop(state, None)

    try:
        discovery = _discover()

        token_resp = requests.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.sso_redirect_uri,
                "client_id": settings.sso_client_id,
                "client_secret": settings.sso_client_secret,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        id_token = token_resp.json().get("id_token")
        if not id_token:
            raise HTTPException(status_code=502, detail="Identity provider did not return an ID token")

        jwks = requests.get(discovery["jwks_uri"], timeout=10).json()
        header = jose_jwt.get_unverified_header(id_token)
        key = next((k for k in jwks["keys"] if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise HTTPException(status_code=502, detail="Could not find a matching signing key from the identity provider")

        claims = jose_jwt.decode(
            id_token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=settings.sso_client_id,
            issuer=discovery.get("issuer", settings.sso_issuer),
        )
    except requests.RequestException as exc:
        log_event("error", f"SSO: token exchange failed: {exc}")
        raise HTTPException(status_code=502, detail="Could not complete sign-in with the identity provider")

    username = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
    if not username:
        raise HTTPException(status_code=502, detail="Identity provider did not supply a usable identity claim")

    user = find_or_create_sso_user(username, default_role=settings.sso_default_role)
    log_event("info", f"SSO: user '{username}' authenticated via identity provider", role=user.get("role"))

    app_token = create_access_token({"sub": user["username"]})
    redirect_target = f"{settings.frontend_base_url.rstrip('/')}/sso-callback?token={app_token}"
    return RedirectResponse(redirect_target)
