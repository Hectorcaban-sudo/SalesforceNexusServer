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
    pipeline_id: Optional[str] = None
    name: Optional[str] = None
    payload: dict = {}
    org_id: Optional[str] = None


def _resolve_pipeline(pipeline_id: Optional[str], name: Optional[str]):
    from ..database import event_pipelines_table, Q

    if pipeline_id:
        row = event_pipelines_table.get(Q.id == pipeline_id)
        if not row:
            raise HTTPException(404, f"Pipeline not found: {pipeline_id}")
        return row
    if name:
        matches = [r for r in event_pipelines_table.all() if (r.get("name") or "").strip() == name.strip()]
        if not matches:
            raise HTTPException(404, f"Pipeline not found: {name}")
        if len(matches) > 1:
            raise HTTPException(400, f"More than one pipeline named {name}. Pass pipeline_id.")
        return matches[0]
    raise HTTPException(400, "Pass pipeline_id or name")


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


@router.post("/pipeline")
async def execute_pipeline(req: ExecutePipelineRequest):
    """Run a saved pipeline with the given payload and return its result.

    The call is recorded as a transaction. The response includes that id so
    the caller can open the trace on the Transactions page.
    """
    from .. import transactions as tx
    from ..pipeline_mode import run_subflow

    row = _resolve_pipeline(req.pipeline_id, req.name)
    pipeline_id = row["id"]
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
        child = tx.get_transaction(parent["id"]) or {}
        # run_subflow stores the walk on its own child; the parent is the API call.
        tx.update_transaction(parent["id"], status="published", result=result or {})
        log_event("info", f"Direct execute: pipeline {row.get('name') or pipeline_id} finished", transaction_id=parent["id"])
        return {
            "detail": "ok",
            "pipeline_id": pipeline_id,
            "pipeline_name": row.get("name"),
            "transaction_id": parent["id"],
            "result": result or {},
            "trace": (child.get("result") or {}).get("flow_trace") or [],
        }
    except Exception as exc:
        tx.update_transaction(parent["id"], status="failed", error=str(exc))
        log_event("error", f"Direct execute: pipeline failed: {exc}", transaction_id=parent["id"])
        raise HTTPException(400, str(exc))
