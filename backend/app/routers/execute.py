"""Direct execution endpoints for DSS, Langflow, and a saved pipeline."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from ..auth import get_current_user, require_role
from ..logging_config import log_event

router = APIRouter(prefix="/api/execute", tags=["execute"])
optional_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class ExecuteRequest(BaseModel):
    payload: dict


class ExecutePipelineRequest(BaseModel):
    payload: dict = {}
    org_id: Optional[str] = None


async def require_operator_or_client(
    request: Request,
    token: Optional[str] = Depends(optional_bearer),
) -> dict:
    """A login token with operator or higher, or a consumer key and secret."""
    key = (request.headers.get("x-consumer-key") or "").strip()
    secret = (request.headers.get("x-consumer-secret") or "").strip()
    if key or secret:
        from ..api_clients import verify_client
        client = verify_client(key, secret)
        if not client:
            raise HTTPException(401, "Invalid consumer key or secret")
        return {"kind": "client", "client": client}
    if not token:
        raise HTTPException(401, "Missing credentials")
    user = await get_current_user(token)
    rank = {"viewer": 0, "operator": 1, "admin": 2}.get(user.get("role", "viewer"), -1)
    if rank < 1:
        raise HTTPException(403, "This action requires the 'operator' role or higher")
    return {"kind": "user", "user": user}


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


@router.post("/dss-client", dependencies=[Depends(require_role("operator"))])
def execute_dss_client(req: ExecuteRequest):
    from ..dss_runner import run_dss_client

    try:
        result = run_dss_client(req.payload)
        log_event("info", "Direct execute: DSSClient call succeeded", result=result)
        return {"detail": "ok", "result": result}
    except Exception as exc:
        log_event("error", f"Direct execute: DSSClient call failed: {exc}")
        raise HTTPException(400, str(exc))


@router.post("/langflow", dependencies=[Depends(require_role("operator"))])
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
async def execute_pipeline(
    project: str,
    pipeline_id: str,
    req: ExecutePipelineRequest,
    auth: dict = Depends(require_operator_or_client),
):
    """Run a saved pipeline in a project and return its result.

    Auth is a login token, or the X-Consumer-Key and X-Consumer-Secret headers.
    project is a project id or name. The call is recorded as a transaction.
    """
    from .. import transactions as tx
    from ..pipeline_mode import run_subflow

    proj = _resolve_project(project)
    if auth.get("kind") == "client":
        scoped = (auth.get("client") or {}).get("project_id")
        if scoped and scoped != proj["id"]:
            raise HTTPException(403, "This client is not allowed to call this project")
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
        project_id=proj["id"],
        project_name=proj.get("name"),
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
