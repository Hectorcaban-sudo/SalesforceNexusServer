from fastapi import APIRouter, Depends, HTTPException
from typing import List

from ..auth import require_role, get_current_user, hash_password
from ..database import users_table, Q
from ..models import UserOut, UserCreate, UserUpdate
from ..logging_config import log_event

router = APIRouter(prefix="/api/users", tags=["users"])


def _out(u: dict) -> UserOut:
    return UserOut(
        username=u["username"],
        role=u.get("role", "viewer"),
        auth_provider=u.get("auth_provider", "local"),
        created_at=u.get("created_at"),
    )


@router.get("", response_model=List[UserOut], dependencies=[Depends(require_role("admin"))])
def list_users():
    return [_out(u) for u in users_table.all()]


@router.post("", response_model=UserOut, dependencies=[Depends(require_role("admin"))])
def create_user(user: UserCreate):
    if users_table.get(Q.username == user.username):
        raise HTTPException(409, "A user with that username already exists")
    record = {
        "username": user.username,
        "password_hash": hash_password(user.password),
        "role": user.role.value,
        "auth_provider": "local",
        "created_at": __import__("time").time(),
        "must_change_password": True,
    }
    users_table.insert(record)
    log_event("info", f"User '{user.username}' created with role '{user.role.value}'")
    return _out(record)


@router.put("/{username}", response_model=UserOut, dependencies=[Depends(require_role("admin"))])
def update_user(username: str, updates: UserUpdate, current_user: dict = Depends(get_current_user)):
    existing = users_table.get(Q.username == username)
    if not existing:
        raise HTTPException(404, "User not found")
    if username == current_user["username"] and updates.role is not None and updates.role.value != "admin":
        raise HTTPException(400, "You can't demote your own account")

    data = {}
    if updates.role is not None:
        data["role"] = updates.role.value
    if updates.password:
        if existing.get("auth_provider") == "sso":
            raise HTTPException(400, "Cannot set a local password for an SSO-managed account")
        data["password_hash"] = hash_password(updates.password)

    if data:
        users_table.update(data, Q.username == username)
        log_event("info", f"User '{username}' updated", fields=list(data.keys()))

    return _out(users_table.get(Q.username == username))


@router.delete("/{username}", dependencies=[Depends(require_role("admin"))])
def delete_user(username: str, current_user: dict = Depends(get_current_user)):
    if username == current_user["username"]:
        raise HTTPException(400, "You can't delete your own account")
    existing = users_table.get(Q.username == username)
    if not existing:
        raise HTTPException(404, "User not found")
    users_table.remove(Q.username == username)
    log_event("warning", f"User '{username}' deleted")
    return {"detail": "deleted"}
