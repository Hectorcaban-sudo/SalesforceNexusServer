"""Direct execution endpoints for DSS and Langflow."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_role
from ..logging_config import log_event

router = APIRouter(prefix="/api/execute", tags=["execute"], dependencies=[Depends(require_role("operator"))])


class ExecuteRequest(BaseModel):
    payload: dict


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
