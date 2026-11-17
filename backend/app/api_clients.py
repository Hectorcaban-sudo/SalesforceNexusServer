"""API clients: a consumer key and a hashed secret for the execute endpoint."""
import secrets
import uuid

import bcrypt

from .database import admin_settings_table, Q
from .models import now_ts

CLIENTS_ID = "api_clients"


def _load() -> list:
    row = admin_settings_table.get(Q.id == CLIENTS_ID) or {}
    items = row.get("items")
    return items if isinstance(items, list) else []


def _save(items: list):
    record = {"id": CLIENTS_ID, "items": items}
    if admin_settings_table.get(Q.id == CLIENTS_ID):
        admin_settings_table.update(record, Q.id == CLIENTS_ID)
    else:
        admin_settings_table.insert(record)


def _hash(secret: str) -> str:
    return bcrypt.hashpw(secret.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _check(secret: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


def create_client(name: str, project_id: str = None) -> dict:
    consumer_key = secrets.token_hex(16)
    consumer_secret = secrets.token_urlsafe(32)
    row = {
        "id": uuid.uuid4().hex[:12],
        "name": name or "API client",
        "consumer_key": consumer_key,
        "secret_hash": _hash(consumer_secret),
        "project_id": project_id or None,
        "enabled": True,
        "created_at": now_ts(),
    }
    items = _load()
    items.append(row)
    _save(items)
    return {**row, "consumer_secret": consumer_secret}


def list_clients() -> list:
    out = []
    for row in _load():
        out.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "consumer_key": row.get("consumer_key"),
            "project_id": row.get("project_id"),
            "enabled": row.get("enabled", True),
            "created_at": row.get("created_at"),
        })
    return out


def set_enabled(client_id: str, enabled: bool) -> dict:
    items = _load()
    found = None
    for row in items:
        if row.get("id") == client_id:
            row["enabled"] = enabled
            found = row
    if not found:
        return None
    _save(items)
    return found


def delete_client(client_id: str) -> bool:
    items = _load()
    kept = [r for r in items if r.get("id") != client_id]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


def verify_client(consumer_key: str, consumer_secret: str) -> dict:
    if not consumer_key or not consumer_secret:
        return None
    for row in _load():
        if row.get("consumer_key") == consumer_key and _check(consumer_secret, row.get("secret_hash") or ""):
            if not row.get("enabled", True):
                return None
            return row
    return None
