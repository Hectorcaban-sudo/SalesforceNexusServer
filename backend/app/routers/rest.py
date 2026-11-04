"""Admin and project REST processors. A pipeline calls one like Chroma."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_role
from ..database import admin_settings_table, Q
from ..logging_config import log_event

router = APIRouter(prefix="/api/rest", tags=["rest"], dependencies=[Depends(require_role("admin"))])
PROCESSORS_ID = "rest_processors"
_MASK = "\u2022" * 8


def _load():
    row = admin_settings_table.get(Q.id == PROCESSORS_ID) or {}
    items = row.get("items")
    return items if isinstance(items, list) else []


def _save(items):
    record = {"id": PROCESSORS_ID, "items": items}
    if admin_settings_table.get(Q.id == PROCESSORS_ID):
        admin_settings_table.update(record, Q.id == PROCESSORS_ID)
    else:
        admin_settings_table.insert(record)


def _new_id():
    return uuid.uuid4().hex[:12]


class HeaderIn(BaseModel):
    name: str = ""
    value: str = ""


class RestProcessorIn(BaseModel):
    name: str
    project_id: Optional[str] = None
    url: str
    method: str = "POST"
    timeout: int = 60
    verify_ssl: bool = True
    headers: list[HeaderIn] = Field(default_factory=list)
    body_template: str = "{{ payload | tojson }}"
    enabled: bool = True


class RestTestIn(BaseModel):
    payload: dict = Field(default_factory=dict)


def _mask(row):
    out = dict(row)
    out["headers"] = [
        {"name": h.get("name") or "", "value": _MASK if h.get("value") else ""}
        for h in (row.get("headers") or [])
    ]
    out["scope"] = "global" if not out.get("project_id") else "project"
    return out


def _resolve(processor_id: str):
    row = next((r for r in _load() if r.get("id") == processor_id), None)
    if not row:
        raise HTTPException(404, "processor not found")
    return row


def run_saved(processor_id: str, payload: dict, transaction_id: str = None):
    from ..rest_runner import run_rest
    return run_rest(_resolve(processor_id), payload, transaction_id=transaction_id)


def _keep_secrets(existing: dict, incoming: dict) -> dict:
    old = {(h.get("name") or ""): h.get("value") or "" for h in existing.get("headers") or []}
    kept = []
    for h in incoming.get("headers") or []:
        name = (h.get("name") or "").strip()
        value = h.get("value") or ""
        if name and (not value or set(value) <= {"\u2022"}):
            value = old.get(name, "")
        if name:
            kept.append({"name": name, "value": value})
    incoming["headers"] = kept
    return incoming


@router.get("/processors")
def list_processors(project_id: Optional[str] = None):
    rows = _load()
    if project_id:
        rows = [r for r in rows if r.get("project_id") in (None, "", project_id)]
    return [_mask(r) for r in rows]


@router.post("/processors")
def create_processor(body: RestProcessorIn):
    items = _load()
    row = body.model_dump()
    row["id"] = _new_id()
    row["headers"] = [h for h in row["headers"] if (h.get("name") or "").strip()]
    items.append(row)
    _save(items)
    log_event("info", f"REST processor created: {row['name']}")
    return _mask(row)


@router.put("/processors/{processor_id}")
def update_processor(processor_id: str, body: RestProcessorIn):
    items = _load()
    found = None
    for row in items:
        if row.get("id") == processor_id:
            incoming = _keep_secrets(row, body.model_dump())
            row.update(incoming)
            row["id"] = processor_id
            found = row
    if not found:
        raise HTTPException(404, "processor not found")
    _save(items)
    return _mask(found)


@router.delete("/processors/{processor_id}")
def delete_processor(processor_id: str):
    items = _load()
    kept = [r for r in items if r.get("id") != processor_id]
    if len(kept) == len(items):
        raise HTTPException(404, "processor not found")
    _save(kept)
    return {"ok": True}


@router.post("/processors/{processor_id}/test")
def test_processor(processor_id: str, body: RestTestIn):
    try:
        return run_saved(processor_id, body.payload or {})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc))
