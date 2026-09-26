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
def list_event_configs(org_id: Optional[str] = None, project_id: Optional[str] = None):
    from ..project_scope import filter_by_project
    rows = event_configs_table.search(Q.org_id == org_id) if org_id else event_configs_table.all()
    return filter_by_project(rows, project_id, include_global=False)


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
    # An empty string for processing_mode/processor_id means "clear the
    # per-event override and fall back to the global default" - model_dump()
    # filtering above only drops actual None values, so "" would otherwise
    # get stored as a literal empty string instead of being cleared.
    for field in ("processing_mode", "processor_id", "rule_id"):
        if field in data and data[field] == "":
            data[field] = None
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


@router.post("/schema/infer", dependencies=[Depends(require_role("operator"))])
def infer_schema_from_sample(body: dict):
    """Body: { "sample": { ... } } → JSON Schema draft-07 style object."""
    from ..worker import infer_json_schema
    sample = body.get("sample")
    if not isinstance(sample, dict):
        raise HTTPException(400, "sample must be a JSON object")
    return {"schema": infer_json_schema(sample)}


@router.post("/schema/validate", dependencies=[Depends(require_role("operator"))])
def validate_payload_against_schema(body: dict):
    """Body: { "payload": {...}, "schema": {...} } or use event's stored schema via event_id."""
    from ..worker import validate_payload_schema
    payload = body.get("payload")
    schema = body.get("schema")
    event_id = body.get("event_id")
    if event_id and not schema:
        ev = event_configs_table.get(Q.id == event_id)
        if not ev:
            raise HTTPException(404, "Event config not found")
        schema = ev.get("payload_schema")
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload must be a JSON object")
    if not schema:
        return {"ok": True, "errors": [], "detail": "No schema provided"}
    ok, errors = validate_payload_schema(payload, schema)
    return {"ok": ok, "errors": errors}


@router.post("/{config_id}/dry-run", dependencies=[Depends(require_role("operator"))])
def dry_run_flow(config_id: str, body: dict):
    """Walk the (saved or posted) graph with a sample payload. No Salesforce / hooks."""
    from ..flow_walker import simulate_flow_graph
    from ..models import FlowDryRunRequest
    ev = event_configs_table.get(Q.id == config_id)
    if not ev:
        raise HTTPException(404, "Event config not found")
    req = FlowDryRunRequest(**(body or {}))
    graph = req.graph or ev.get("flow_graph") or {}
    return simulate_flow_graph(graph, req.payload or {}, ev)
