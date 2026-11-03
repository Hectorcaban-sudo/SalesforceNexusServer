"""Saved database connections. Postgres now; other engines later."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_role
from ..database import admin_settings_table, Q
from ..logging_config import log_event

router = APIRouter(prefix="/api/databases", tags=["databases"], dependencies=[Depends(require_role("admin"))])
CONNECTIONS_ID = "database_connections"


def _load():
    row = admin_settings_table.get(Q.id == CONNECTIONS_ID) or {}
    items = row.get("items")
    return items if isinstance(items, list) else []


def _save(items):
    existing = admin_settings_table.get(Q.id == CONNECTIONS_ID)
    record = {"id": CONNECTIONS_ID, "items": items}
    if existing:
        admin_settings_table.update(record, Q.id == CONNECTIONS_ID)
    else:
        admin_settings_table.insert(record)


def _mask(row):
    out = dict(row)
    if out.get("password"):
        out["password"] = "\u2022" * 8
    return out


class DatabaseIn(BaseModel):
    name: str
    engine: str = "postgres"
    host: str
    port: int = 5432
    database: str
    username: str = ""
    password: str = ""
    ssl: bool = False


@router.get("")
def list_connections():
    return [_mask(r) for r in _load()]


@router.post("")
def create_connection(body: DatabaseIn):
    if body.engine != "postgres":
        raise HTTPException(400, "Only postgres is supported for now")
    items = _load()
    row = body.model_dump()
    row["id"] = uuid.uuid4().hex[:12]
    items.append(row)
    _save(items)
    log_event("info", f"Database connection created: {row['name']}")
    return _mask(row)


@router.put("/{connection_id}")
def update_connection(connection_id: str, body: DatabaseIn):
    if body.engine != "postgres":
        raise HTTPException(400, "Only postgres is supported for now")
    items = _load()
    found = None
    for row in items:
        if row.get("id") == connection_id:
            incoming = body.model_dump()
            if not incoming.get("password") or set(str(incoming.get("password"))) <= {"\u2022"}:
                incoming["password"] = row.get("password") or ""
            row.update(incoming)
            row["id"] = connection_id
            found = row
    if not found:
        raise HTTPException(404, "connection not found")
    _save(items)
    return _mask(found)


@router.delete("/{connection_id}")
def delete_connection(connection_id: str):
    items = _load()
    kept = [r for r in items if r.get("id") != connection_id]
    if len(kept) == len(items):
        raise HTTPException(404, "connection not found")
    _save(kept)
    return {"ok": True}


@router.post("/{connection_id}/test")
def test_connection(connection_id: str):
    row = next((r for r in _load() if r.get("id") == connection_id), None)
    if not row:
        raise HTTPException(404, "connection not found")
    try:
        import psycopg
        conn = psycopg.connect(
            host=row.get("host"),
            port=int(row.get("port") or 5432),
            dbname=row.get("database"),
            user=row.get("username") or None,
            password=row.get("password") or None,
            sslmode="require" if row.get("ssl") else "prefer",
            connect_timeout=8,
        )
        with conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
        conn.close()
    except Exception as exc:
        raise HTTPException(400, f"Connection failed: {exc}")
    return {"ok": True}
