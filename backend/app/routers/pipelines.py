from typing import List

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, require_role
from ..database import event_configs_table, event_pipelines_table, Q
from ..logging_config import log_event
from ..models import EventPipelineCreate, EventPipelineOut, EventPipelineUpdate, new_id, now_ts

router = APIRouter(prefix="/api/events", tags=["pipelines"], dependencies=[Depends(get_current_user)])


def ensure_default_pipeline(event: dict) -> list:
    """If this subscribe event has no pipeline rows, promote flow_graph into Default."""
    eid = event["id"]
    rows = event_pipelines_table.search(Q.event_id == eid)
    if rows:
        return rows
    graph = event.get("flow_graph") or {"nodes": [], "edges": []}
    record = {
        "id": new_id(),
        "event_id": eid,
        "name": "Default",
        "description": "Migrated from event flow_graph",
        "enabled": True,
        "flow_graph": graph,
        "created_at": str(now_ts()),
        "updated_at": str(now_ts()),
    }
    event_pipelines_table.insert(record)
    return [record]


def list_enabled_pipelines(event: dict) -> list:
    rows = ensure_default_pipeline(event)
    return [r for r in rows if r.get("enabled", True)]


@router.get("/{event_id}/pipelines", response_model=List[EventPipelineOut])
def list_pipelines(event_id: str):
    ev = event_configs_table.get(Q.id == event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    return ensure_default_pipeline(ev)


@router.post("/{event_id}/pipelines", response_model=EventPipelineOut, dependencies=[Depends(require_role("operator"))])
def create_pipeline(event_id: str, body: EventPipelineCreate):
    ev = event_configs_table.get(Q.id == event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.get("direction") != "subscribe":
        raise HTTPException(400, "Pipelines are only for subscribe channels")
    record = {
        "id": new_id(),
        "event_id": event_id,
        "name": body.name,
        "description": body.description or "",
        "enabled": body.enabled,
        "flow_graph": body.flow_graph or {"nodes": [], "edges": []},
        "created_at": str(now_ts()),
        "updated_at": str(now_ts()),
    }
    event_pipelines_table.insert(record)
    log_event("info", f"Pipeline '{record['name']}' created", event_id=event_id)
    return record


@router.get("/{event_id}/pipelines/{pipeline_id}", response_model=EventPipelineOut)
def get_pipeline(event_id: str, pipeline_id: str):
    row = event_pipelines_table.get((Q.id == pipeline_id) & (Q.event_id == event_id))
    if not row:
        raise HTTPException(404, "Pipeline not found")
    return row


@router.put("/{event_id}/pipelines/{pipeline_id}", response_model=EventPipelineOut, dependencies=[Depends(require_role("operator"))])
def update_pipeline(event_id: str, pipeline_id: str, body: EventPipelineUpdate):
    existing = event_pipelines_table.get((Q.id == pipeline_id) & (Q.event_id == event_id))
    if not existing:
        raise HTTPException(404, "Pipeline not found")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_at"] = str(now_ts())
    event_pipelines_table.update(data, Q.id == pipeline_id)
    # Keep event.flow_graph in sync with first/default enabled graph for legacy export.
    if "flow_graph" in data:
        event_configs_table.update({"flow_graph": data["flow_graph"]}, Q.id == event_id)
    return event_pipelines_table.get(Q.id == pipeline_id)


@router.delete("/{event_id}/pipelines/{pipeline_id}", dependencies=[Depends(require_role("operator"))])
def delete_pipeline(event_id: str, pipeline_id: str):
    existing = event_pipelines_table.get((Q.id == pipeline_id) & (Q.event_id == event_id))
    if not existing:
        raise HTTPException(404, "Pipeline not found")
    remaining = [r for r in event_pipelines_table.search(Q.event_id == event_id) if r["id"] != pipeline_id]
    if not remaining:
        raise HTTPException(400, "Cannot delete the last pipeline on an event")
    event_pipelines_table.remove(Q.id == pipeline_id)
    return {"ok": True}
