"""
Direct execution endpoints.

These let another system (or you, for testing) invoke the DSSClient or
Langflow processing logic directly with an arbitrary payload, without going
through CometD/the broker/Salesforce at all. Useful for testing a
configuration change, or for another internal system that wants to reuse
this server's configured AI processor without being a Salesforce event.

Unlike the normal event pipeline, failures here are NOT swallowed into a
local fallback result - the caller gets the real error back, since they
explicitly asked for this specific processor to run.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_role
from ..logging_config import log_event

router = APIRouter(prefix="/api/execute", tags=["execute"], dependencies=[Depends(require_role("operator"))])


class ExecuteRequest(BaseModel):
    payload: dict


@router.post("/dss-client")
def execute_dss_client(req: ExecuteRequest):
    from ..worker import run_dss_client  # local import avoids a circular import at module load time

    try:
        result = run_dss_client(req.payload)
        log_event("info", "Direct execute: DSSClient call succeeded", result=result)
        return {"detail": "ok", "result": result}
    except Exception as exc:  # noqa: BLE001
        log_event("error", f"Direct execute: DSSClient call failed: {exc}")
        raise HTTPException(400, str(exc))


@router.post("/langflow")
def execute_langflow(req: ExecuteRequest):
    from ..worker import run_langflow  # local import avoids a circular import at module load time

    try:
        result = run_langflow(req.payload)
        log_event("info", "Direct execute: Langflow call succeeded", result=result)
        return {"detail": "ok", "result": result}
    except Exception as exc:  # noqa: BLE001
        log_event("error", f"Direct execute: Langflow call failed: {exc}")
        raise HTTPException(400, str(exc))
