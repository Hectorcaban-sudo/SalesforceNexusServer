"""
Audit logging and authentication monitoring.

Two separate trails, both distinct from the general System Logs (which are
about the event-processing pipeline's own health):

  - `audit_log`  : every privileged (state-changing) admin-console API call
                    - who did what, when, from where, and what the server
                    responded. Populated automatically by AuditMiddleware
                    below, so individual routers don't need to remember to
                    log anything themselves.
  - `auth_events` : every authentication-related event - login success,
                    login failure, account lockout/unlock, SSO logins,
                    password changes. This is what account lockout (see
                    auth.py:authenticate_user) is built on top of, and what
                    the admin UI's Authentication Monitoring view reads.

These two logs are the technical basis for several CMMC Level 2 / NIST
800-171 practices (see docs/SECURITY.md for specifics and honest caveats
about what this does and doesn't cover).
"""
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware

from .database import audit_log_table, auth_events_table
from .models import new_id, now_ts

# Paths that are noisy or already covered elsewhere and shouldn't clutter the
# audit trail with routine, non-privileged traffic.
AUDIT_EXCLUDED_PATH_PREFIXES = (
    "/api/auth/login",
    "/api/auth/sso/callback",
    "/api/auth/sso/login",
)


def log_audit(username: Optional[str], role: Optional[str], method: str, path: str, status_code: int, ip: Optional[str] = None):
    audit_log_table.insert({
        "id": new_id(),
        "timestamp": now_ts(),
        "username": username or "(unauthenticated)",
        "role": role,
        "method": method,
        "path": path,
        "status_code": status_code,
        "ip": ip,
    })


def log_auth_event(username: str, event_type: str, ip: Optional[str] = None, detail: Optional[str] = None):
    auth_events_table.insert({
        "id": new_id(),
        "timestamp": now_ts(),
        "username": username,
        "event_type": event_type,  # login_success | login_failure | login_blocked_locked |
                                    # account_locked | account_unlocked | logout |
                                    # password_change | sso_login_success
        "ip": ip,
        "detail": detail,
    })


def _client_ip(request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class AuditMiddleware(BaseHTTPMiddleware):
    """Automatically records every state-changing (POST/PUT/DELETE/PATCH)
    call to an admin-console API endpoint - who made it (decoded from their
    JWT, if any), from where, and what the server responded. This is
    deliberately separate from authentication logging (see log_auth_event
    above, used directly by the login/SSO/password-change endpoints) since
    login attempts aren't "actions taken by an already-authenticated user".

    Failure to record an audit entry (e.g. a malformed token) never blocks
    or alters the real response - this is purely observational.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        try:
            method = request.method
            path = request.url.path
            if (
                method in ("POST", "PUT", "DELETE", "PATCH")
                and path.startswith("/api/")
                and not any(path.startswith(p) for p in AUDIT_EXCLUDED_PATH_PREFIXES)
            ):
                username, role = self._identify(request)
                log_audit(username, role, method, path, response.status_code, _client_ip(request))
        except Exception:  # noqa: BLE001
            pass  # audit logging must never break a real request

        return response

    @staticmethod
    def _identify(request):
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None, None
        try:
            from jose import jwt, JWTError
            from .config import settings
            from .database import users_table, Q

            payload = jwt.decode(auth_header[7:], settings.secret_key, algorithms=[settings.algorithm])
            username = payload.get("sub")
            if not username:
                return None, None
            user = users_table.get(Q.username == username)
            return username, (user.get("role") if user else None)
        except Exception:  # noqa: BLE001
            return None, None
