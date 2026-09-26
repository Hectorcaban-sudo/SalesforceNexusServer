from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user, require_role
from ..database import flow_templates_table, Q
from ..logging_config import log_event
from ..models import FlowTemplateCreate, FlowTemplateOut, FlowTemplateUpdate, new_id, now_ts

router = APIRouter(prefix="/api/flow-templates", tags=["flow-templates"], dependencies=[Depends(get_current_user)])


PLACEHOLDER_TYPES = {"integration", "alert", "publish"}


def strip_live_ids(graph: dict) -> dict:
    nodes = []
    for n in (graph or {}).get("nodes") or []:
        node = dict(n)
        data = dict(node.get("data") or {})
        if node.get("type") in PLACEHOLDER_TYPES and data.get("refId"):
            data["boundRefId"] = data.get("refId")
            data["refId"] = ""
            data["placeholder"] = True
            data["subtitle"] = (data.get("subtitle") or "") + " (bind on apply)"
        node["data"] = data
        nodes.append(node)
    return {"nodes": nodes, "edges": list((graph or {}).get("edges") or [])}


@router.get("", response_model=List[FlowTemplateOut])
def list_templates(project_id: Optional[str] = None, include_global: bool = True):
    from ..project_scope import filter_by_project
    return filter_by_project(flow_templates_table.all(), project_id, include_global=include_global)


@router.post("", response_model=FlowTemplateOut, dependencies=[Depends(require_role("operator"))])
def create_template(body: FlowTemplateCreate):
    graph = body.graph or {}
    if body.placeholders:
        graph = strip_live_ids(graph)
    record = {
        "id": new_id(),
        "name": body.name,
        "description": body.description or "",
        "project_id": (body.project_id or "").strip() or None,
        "graph": graph,
        "placeholders": body.placeholders,
        "created_at": str(now_ts()),
    }
    flow_templates_table.insert(record)
    log_event("info", f"Flow template '{record['name']}' saved")
    return record


@router.put("/{template_id}", response_model=FlowTemplateOut, dependencies=[Depends(require_role("operator"))])
def update_template(template_id: str, body: FlowTemplateUpdate):
    existing = flow_templates_table.get(Q.id == template_id)
    if not existing:
        raise HTTPException(404, "Template not found")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    flow_templates_table.update(data, Q.id == template_id)
    return flow_templates_table.get(Q.id == template_id)


@router.delete("/{template_id}", dependencies=[Depends(require_role("operator"))])
def delete_template(template_id: str):
    existing = flow_templates_table.get(Q.id == template_id)
    if not existing:
        raise HTTPException(404, "Template not found")
    flow_templates_table.remove(Q.id == template_id)
    return {"ok": True}
