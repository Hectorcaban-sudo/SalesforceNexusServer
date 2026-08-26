from fastapi import APIRouter, Depends, HTTPException
from typing import List

from ..auth import get_current_user
from ..database import orgs_table, Q
from ..models import OrgCreate, OrgUpdate, OrgOut, new_id
from ..logging_config import log_event
from ..cometd_client import cometd_manager

router = APIRouter(prefix="/api/orgs", tags=["orgs"], dependencies=[Depends(get_current_user)])


def _mask(org: dict) -> dict:
    """Never return secrets to the browser in plaintext beyond a hint."""
    masked = dict(org)
    for field in ("client_secret", "password", "security_token"):
        if masked.get(field):
            masked[field] = "••••••••"
    return masked


@router.get("", response_model=List[OrgOut])
def list_orgs():
    orgs = orgs_table.all()
    for o in orgs:
        o["status"] = cometd_manager.status_for(o["id"]) if o.get("active") else "disconnected"
    return [_mask(o) for o in orgs]


@router.post("", response_model=OrgOut)
async def create_org(org: OrgCreate):
    record = org.model_dump()
    record.update({"id": new_id(), "status": "disconnected", "last_error": None, "last_connected_at": None})
    orgs_table.insert(record)
    log_event("info", f"Org '{record['name']}' created", org_id=record["id"])
    await cometd_manager.sync()
    return _mask(record)


@router.put("/{org_id}", response_model=OrgOut)
async def update_org(org_id: str, updates: OrgUpdate):
    existing = orgs_table.get(Q.id == org_id)
    if not existing:
        raise HTTPException(404, "Org not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    orgs_table.update(data, Q.id == org_id)
    log_event("info", f"Org '{existing['name']}' updated", org_id=org_id, fields=list(data.keys()))
    await cometd_manager.sync()
    return _mask(orgs_table.get(Q.id == org_id))


@router.delete("/{org_id}")
async def delete_org(org_id: str):
    existing = orgs_table.get(Q.id == org_id)
    if not existing:
        raise HTTPException(404, "Org not found")
    orgs_table.remove(Q.id == org_id)
    log_event("warning", f"Org '{existing['name']}' deleted", org_id=org_id)
    await cometd_manager.sync()
    return {"detail": "deleted"}


@router.post("/{org_id}/test-connection")
def test_connection(org_id: str):
    from ..salesforce_client import sf_client, SalesforceAuthError

    org = orgs_table.get(Q.id == org_id)
    if not org:
        raise HTTPException(404, "Org not found")
    try:
        session = sf_client.get_session(org, force_refresh=True)
        return {"detail": "Connection successful", "instance_url": session.instance_url}
    except SalesforceAuthError as exc:
        raise HTTPException(400, str(exc))


@router.post("/resync")
async def resync():
    """Force the CometD manager to re-read org/event configuration and
    reconnect all active orgs. Useful after bulk config changes."""
    await cometd_manager.sync()
    return {"detail": "Resync triggered"}
