from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm

from ..auth import authenticate_user, create_access_token, get_current_user, hash_password, verify_password, AccountLockedError
from ..database import users_table, Q
from ..models import Token, UserOut, ChangePasswordRequest
from ..audit import log_auth_event
from .. import sso as sso_module

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For if present (set by a reverse proxy/load balancer
    # in front of the app); otherwise fall back to the direct connection.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    ip = _client_ip(request)
    try:
        user = authenticate_user(form_data.username, form_data.password, ip=ip)
    except AccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account is locked due to too many failed login attempts. Try again later, or ask an admin to unlock it.",
        )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_access_token({"sub": user["username"]})
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return UserOut(
        username=current_user["username"],
        role=current_user.get("role", "admin"),
        auth_provider=current_user.get("auth_provider", "local"),
        created_at=current_user.get("created_at"),
    )


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    if current_user.get("auth_provider") == "sso":
        raise HTTPException(status_code=400, detail="SSO-managed accounts change their password with your identity provider")
    if not verify_password(req.current_password, current_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    users_table.update(
        {"password_hash": hash_password(req.new_password), "must_change_password": False},
        Q.username == current_user["username"],
    )
    log_auth_event(current_user["username"], "password_change")
    return {"detail": "Password updated"}


@router.get("/sso/status")
def sso_status():
    return {"enabled": sso_module.is_sso_enabled(), "login_url": "/api/auth/sso/login"}


@router.get("/sso/login")
async def sso_login():
    return await sso_module.start_login()


@router.get("/sso/callback")
async def sso_callback(request: Request, code: str = None, state: str = None, error: str = None):
    return await sso_module.handle_callback(code, state, error, ip=_client_ip(request))
