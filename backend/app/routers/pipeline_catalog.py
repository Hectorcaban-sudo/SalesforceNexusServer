from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from ..auth import get_current_user, require_role
from ..database import event_pipelines_table, event_configs_table, orgs_table, Q
from ..models import new_id, now_ts

router = APIRouter(prefix="/api/pipeline-catalog", tags=["pipelines"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_catalog(project_id: Optional[str] = None):
    rows = []
    for p in event_pipelines_table.all():
        ev = event_configs_table.get(Q.id == p.get("event_id")) or {}
        owner = p.get("project_id") or ev.get("project_id")
        if project_id and owner and owner != project_id:
            continue
        org = orgs_table.get(Q.id == ev.get("org_id")) or {}
        nodes = ((p.get("flow_graph") or {}).get("nodes") or [])
        rows.append({
            **p,
            "channel": ev.get("channel"),
            "org_id": ev.get("org_id"),
            "org_name": org.get("name"),
            "event_project_id": ev.get("project_id"),
            "source": "schedule" if not ev.get("id") else "event",
            "node_count": len(nodes),
        })
    return rows


@router.post("", dependencies=[Depends(require_role("operator"))])
def create_standalone(body: dict):
    rec = {
        "id": new_id(),
        "event_id": body.get("event_id") or "",
        "project_id": body.get("project_id"),
        "name": body.get("name") or "Scheduled pipeline",
        "description": body.get("description") or "Standalone — started by a scheduled job",
        "enabled": True,
        "source": "schedule",
        "flow_graph": body.get("flow_graph") or {"nodes": [], "edges": []},
        "created_at": str(now_ts()),
        "updated_at": str(now_ts()),
    }
    event_pipelines_table.insert(rec)
    return rec


@router.get("/{pipeline_id}")
def get_one(pipeline_id: str):
    row = event_pipelines_table.get(Q.id == pipeline_id)
    if not row:
        raise HTTPException(404, "Pipeline not found")
    return row


@router.put("/{pipeline_id}", dependencies=[Depends(require_role("operator"))])
def update_one(pipeline_id: str, body: dict):
    if not event_pipelines_table.get(Q.id == pipeline_id):
        raise HTTPException(404, "Pipeline not found")
    data = {k: v for k, v in body.items() if k in ("name", "description", "enabled", "flow_graph")}
    data["updated_at"] = str(now_ts())
    event_pipelines_table.update(data, Q.id == pipeline_id)
    return event_pipelines_table.get(Q.id == pipeline_id)
