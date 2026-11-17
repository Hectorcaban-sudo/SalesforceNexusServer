from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_role
from .. import api_clients

router = APIRouter(prefix="/api/api-clients", tags=["api-clients"], dependencies=[Depends(require_role("admin"))])


class ClientIn(BaseModel):
    name: str
    project_id: Optional[str] = None


@router.get("")
def list_clients():
    return api_clients.list_clients()


@router.post("")
def create_client(body: ClientIn):
    created = api_clients.create_client(body.name, body.project_id)
    return {
        "id": created["id"],
        "name": created["name"],
        "consumer_key": created["consumer_key"],
        "consumer_secret": created["consumer_secret"],
        "project_id": created.get("project_id"),
        "note": "Copy the secret now. It is not shown again.",
    }


@router.post("/{client_id}/disable")
def disable_client(client_id: str):
    row = api_clients.set_enabled(client_id, False)
    if not row:
        raise HTTPException(404, "Client not found")
    return {"ok": True}


@router.post("/{client_id}/enable")
def enable_client(client_id: str):
    row = api_clients.set_enabled(client_id, True)
    if not row:
        raise HTTPException(404, "Client not found")
    return {"ok": True}


@router.delete("/{client_id}")
def delete_client(client_id: str):
    if not api_clients.delete_client(client_id):
        raise HTTPException(404, "Client not found")
    return {"ok": True}
