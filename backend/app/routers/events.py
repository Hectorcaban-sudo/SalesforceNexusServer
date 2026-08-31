from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from ..auth import get_current_user, require_role
from ..database import event_configs_table, orgs_table, Q
from ..models import EventConfigCreate, EventConfigUpdate, EventConfigOut, PublishEventRequest, new_id
from ..logging_config import log_event
from ..cometd_client import cometd_manager
from ..worker import publish_manual_event

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[EventConfigOut])
def list_event_configs(org_id: Optional[str] = None):
    if org_id:
        return event_configs_table.search(Q.org_id == org_id)
    return event_configs_table.all()


@router.post("", response_model=EventConfigOut, dependencies=[Depends(require_role("operator"))])
async def create_event_config(cfg: EventConfigCreate):
    if not orgs_table.get(Q.id == cfg.org_id):
        raise HTTPException(404, "Org not found")
    record = cfg.model_dump()
    record["id"] = new_id()
    event_configs_table.insert(record)
    log_event("info", f"Event config created: {record['direction']} '{record['channel']}'", org_id=cfg.org_id)
    await cometd_manager.sync()
    return record


@router.put("/{config_id}", response_model=EventConfigOut, dependencies=[Depends(require_role("operator"))])
async def update_event_config(config_id: str, updates: EventConfigUpdate):
    existing = event_configs_table.get(Q.id == config_id)
    if not existing:
        raise HTTPException(404, "Event config not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    event_configs_table.update(data, Q.id == config_id)
    log_event("info", f"Event config '{config_id}' updated", fields=list(data.keys()))
    await cometd_manager.sync()
    return event_configs_table.get(Q.id == config_id)


@router.delete("/{config_id}", dependencies=[Depends(require_role("admin"))])
async def delete_event_config(config_id: str):
    existing = event_configs_table.get(Q.id == config_id)
    if not existing:
        raise HTTPException(404, "Event config not found")
    event_configs_table.remove(Q.id == config_id)
    log_event("warning", f"Event config '{config_id}' deleted")
    await cometd_manager.sync()
    return {"detail": "deleted"}


@router.post("/publish", dependencies=[Depends(require_role("operator"))])
async def publish_event(req: PublishEventRequest):
    try:
        record = await publish_manual_event(req.org_id, req.channel, req.payload)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"detail": "published", "transaction_id": record["id"]}
