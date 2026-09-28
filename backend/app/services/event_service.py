<<<<<<< Updated upstream
from fastapi import HTTPException
=======
"""Event catalog service. Routers stay thin; CometD sync is a side effect here."""
from fastapi import HTTPException

>>>>>>> Stashed changes
from ..database import event_configs_table, orgs_table, Q
from ..models import EventConfigCreate, EventConfigUpdate, new_id
from ..logging_config import log_event
from ..cometd_client import cometd_manager
from ..project_scope import filter_by_project


def list_configs(org_id=None, project_id=None):
    rows = event_configs_table.search(Q.org_id == org_id) if org_id else event_configs_table.all()
    return filter_by_project(rows, project_id, include_global=False)


async def create_config(cfg: EventConfigCreate):
    if not orgs_table.get(Q.id == cfg.org_id):
        raise HTTPException(404, "Org not found")
    record = cfg.model_dump()
    record["id"] = new_id()
    event_configs_table.insert(record)
    log_event("info", f"Event config created: {record['direction']} '{record['channel']}'", org_id=cfg.org_id)
    await cometd_manager.sync()
    return record


async def update_config(config_id: str, updates: EventConfigUpdate):
    existing = event_configs_table.get(Q.id == config_id)
    if not existing:
        raise HTTPException(404, "Event config not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    for field in ("processing_mode", "processor_id", "rule_id"):
        if field in data and data[field] == "":
            data[field] = None
    event_configs_table.update(data, Q.id == config_id)
    log_event("info", f"Event config '{config_id}' updated", fields=list(data.keys()))
    await cometd_manager.sync()
    return event_configs_table.get(Q.id == config_id)


async def delete_config(config_id: str):
    existing = event_configs_table.get(Q.id == config_id)
    if not existing:
        raise HTTPException(404, "Event config not found")
    event_configs_table.remove(Q.id == config_id)
    log_event("warning", f"Event config '{config_id}' deleted")
    await cometd_manager.sync()
    return {"detail": "deleted"}


async def publish_test(org_id: str, channel: str, payload: dict):
    from ..worker import publish_manual_event
    return await publish_manual_event(org_id, channel, payload)
