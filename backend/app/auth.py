from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt

from .config import settings
from .database import users_table, Q
from .models import now_ts

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


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
    }
    users_table.insert(record)
    return record


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = users_table.get(Q.username == username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
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
