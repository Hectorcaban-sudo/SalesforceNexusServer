"""Direct execution endpoints for DSS, Langflow, and a saved pipeline."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_role
from ..logging_config import log_event

router = APIRouter(prefix="/api/execute", tags=["execute"], dependencies=[Depends(require_role("operator"))])


class ExecuteRequest(BaseModel):
    payload: dict


class ExecutePipelineRequest(BaseModel):
    payload: dict = {}
    org_id: Optional[str] = None


def _resolve_project(project: str):
    from ..database import projects_table, Q

    row = projects_table.get(Q.id == project)
    if row:
        return row
    matches = [p for p in projects_table.all() if (p.get("name") or "").strip().lower() == project.strip().lower()]
    if not matches:
        raise HTTPException(404, f"Project not found: {project}")
    if len(matches) > 1:
        raise HTTPException(400, f"More than one project named {project}. Pass the project id.")
    return matches[0]


def _resolve_pipeline(pipeline_id: str, project_id: str):
    from ..database import event_pipelines_table, event_configs_table, Q

    row = event_pipelines_table.get(Q.id == pipeline_id)
    if not row:
        raise HTTPException(404, f"Pipeline not found: {pipeline_id}")
    owner = row.get("project_id")
    if not owner and row.get("event_id"):
        ev = event_configs_table.get(Q.id == row.get("event_id")) or {}
        owner = ev.get("project_id")
    if owner and owner != project_id:
        raise HTTPException(404, "Pipeline is not in this project")
    return row


def _child_trace(parent_id: str) -> list:
    from ..database import transactions_table, Q

    children = transactions_table.search(Q.parent_transaction_id == parent_id) or []
    if not children:
        return []
    child = sorted(children, key=lambda r: r.get("created_at") or 0, reverse=True)[0]
    return (child.get("result") or {}).get("flow_trace") or child.get("flow_trace") or []


@router.post("/dss-client")
def execute_dss_client(req: ExecuteRequest):
    from ..dss_runner import run_dss_client

    try:
        result = run_dss_client(req.payload)
        log_event("info", "Direct execute: DSSClient call succeeded", result=result)
        return {"detail": "ok", "result": result}
    except Exception as exc:
        log_event("error", f"Direct execute: DSSClient call failed: {exc}")
        raise HTTPException(400, str(exc))


@router.post("/langflow")
async def execute_langflow(req: ExecuteRequest):
    from ..worker import run_langflow

    try:
        result = await run_langflow(req.payload)
        log_event("info", "Direct execute: Langflow call succeeded", result=result)
        return {"detail": "ok", "result": result}
    except Exception as exc:
        log_event("error", f"Direct execute: Langflow call failed: {exc}")
        raise HTTPException(400, str(exc))


@router.post("/{project}/pipeline/{pipeline_id}")
async def execute_pipeline(project: str, pipeline_id: str, req: ExecutePipelineRequest):
    """Run a saved pipeline in a project and return its result.

    project is a project id or name. pipeline_id is the pipeline id. The call
    is recorded as a transaction. The response includes that id.
    """
    from .. import transactions as tx
    from ..pipeline_mode import run_subflow

    proj = _resolve_project(project)
    row = _resolve_pipeline(pipeline_id, proj["id"])
    org_id = req.org_id or row.get("org_id") or ""
    parent = tx.record_transaction(
        org_id=org_id,
        org_name=None,
        direction="api",
        channel=row.get("name") or "execute/pipeline",
        status="processing",
        payload=req.payload or {},
        pipeline_id=pipeline_id,
        pipeline_name=row.get("name"),
    )
    try:
        result = await run_subflow(pipeline_id, req.payload or {}, org_id, parent["id"])
        tx.update_transaction(parent["id"], status="published", result=result or {})
        log_event("info", f"Direct execute: pipeline {row.get('name') or pipeline_id} finished", transaction_id=parent["id"], project_id=proj["id"])
        return {
            "detail": "ok",
            "project_id": proj["id"],
            "project_name": proj.get("name"),
            "pipeline_id": pipeline_id,
            "pipeline_name": row.get("name"),
            "transaction_id": parent["id"],
            "result": result or {},
            "trace": _child_trace(parent["id"]),
        }
    except Exception as exc:
        tx.update_transaction(parent["id"], status="failed", error=str(exc))
        log_event("error", f"Direct execute: pipeline failed: {exc}", transaction_id=parent["id"], project_id=proj["id"])
        raise HTTPException(400, str(exc))
