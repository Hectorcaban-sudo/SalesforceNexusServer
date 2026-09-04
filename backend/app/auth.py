from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt

from .config import settings
from .database import users_table, Q
from .models import now_ts
from .audit import log_auth_event

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class AccountLockedError(Exception):
    """Raised by authenticate_user() when the account is currently locked
    out due to too many recent failed login attempts."""
    def __init__(self, unlock_at: float):
        self.unlock_at = unlock_at
        super().__init__(f"Account locked until {unlock_at}")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


def bootstrap_default_admin():
    """Create a default admin/admin123 account on first run if none exists."""
    if len(users_table) == 0:
        users_table.insert(
            {
                "username": "admin",
                "password_hash": hash_password("admin123"),
                "role": "admin",
                "auth_provider": "local",
                "created_at": now_ts(),
                "must_change_password": True,
                "failed_login_count": 0,
                "locked_until": None,
            }
        )


def find_or_create_sso_user(username: str, default_role: str = "viewer") -> dict:
    """Used by the SSO callback: look up a user provisioned via SSO by their
    IdP-supplied username/email, creating one on first login (no password -
    they always authenticate via the IdP)."""
    user = users_table.get(Q.username == username)
    if user:
        return user
    record = {
        "username": username,
        "password_hash": None,
        "role": default_role,
        "auth_provider": "sso",
        "created_at": now_ts(),
        "must_change_password": False,
        "failed_login_count": 0,
        "locked_until": None,
    }
    users_table.insert(record)
    return record


def unlock_user(username: str):
    """Admin action: clears a lockout and resets the failed-attempt counter,
    regardless of whether the lockout window has actually expired yet."""
    users_table.update({"failed_login_count": 0, "locked_until": None}, Q.username == username)
    log_auth_event(username, "account_unlocked")


def authenticate_user(username: str, password: str, ip: Optional[str] = None) -> Optional[dict]:
    """
    Returns the user dict on success, None on plain invalid credentials, or
    raises AccountLockedError if the account is currently locked out. Every
    outcome (success, failure, blocked-while-locked) is recorded to the
    auth_events log - this is the basis for the admin UI's Authentication
    Monitoring view and supports CMMC/NIST 800-171 AC.L2-3.1.8 ("limit
    unsuccessful logon attempts").
    """
    user = users_table.get(Q.username == username)
    if not user:
        # Deliberately identical failure path/logging as a wrong password,
        # so a login attempt can't be used to enumerate valid usernames.
        log_auth_event(username, "login_failure", ip=ip, detail="Unknown username")
        return None

    locked_until = user.get("locked_until")
    if locked_until and locked_until > now_ts():
        log_auth_event(username, "login_blocked_locked", ip=ip, detail=f"Locked until {locked_until}")
        raise AccountLockedError(locked_until)

    if user.get("auth_provider") == "sso" or not user.get("password_hash"):
        log_auth_event(username, "login_failure", ip=ip, detail="Account is SSO-managed; no local password")
        return None

    if not verify_password(password, user["password_hash"]):
        failed_count = user.get("failed_login_count", 0) + 1
        update = {"failed_login_count": failed_count}
        if failed_count >= settings.max_failed_login_attempts:
            update["locked_until"] = now_ts() + settings.lockout_duration_seconds
            users_table.update(update, Q.username == username)
            log_auth_event(
                username, "account_locked", ip=ip,
                detail=f"Locked for {settings.lockout_duration_seconds}s after {failed_count} failed attempts",
            )
        else:
            users_table.update(update, Q.username == username)
            log_auth_event(username, "login_failure", ip=ip, detail=f"Wrong password (attempt {failed_count})")
        return None

    # Success - clear any prior failure count/lockout.
    if user.get("failed_login_count") or user.get("locked_until"):
        users_table.update({"failed_login_count": 0, "locked_until": None}, Q.username == username)
    log_auth_event(username, "login_success", ip=ip)
    return user


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = users_table.get(Q.username == username)
    if user is None:
        raise credentials_exception
    return user


# ---------- RBAC ----------
# Role hierarchy: admin > operator > viewer. Every route that mutates state
# should depend on `require_role(...)` with the minimum role allowed to call
# it; read-only routes just depend on `get_current_user` (any authenticated
# role can view).
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: 403s unless the current user's role is one
    of `allowed_roles` (or ranks at or above the lowest of them)."""
    min_rank = min(ROLE_RANK.get(r, 99) for r in allowed_roles) if allowed_roles else 0

    async def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        user_rank = ROLE_RANK.get(current_user.get("role", "viewer"), -1)
        if user_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{allowed_roles[0]}' role or higher",
            )
        return current_user

    return _dependency
