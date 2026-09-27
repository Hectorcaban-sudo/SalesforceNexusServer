from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from ..auth import get_current_user, require_role
from ..models import EventConfigCreate, EventConfigUpdate, EventConfigOut, PublishEventRequest
from ..services import event_service

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[EventConfigOut])
def list_event_configs(org_id: Optional[str] = None, project_id: Optional[str] = None):
    return event_service.list_configs(org_id, project_id)


@router.post("", response_model=EventConfigOut, dependencies=[Depends(require_role("operator"))])
async def create_event_config(cfg: EventConfigCreate):
    return await event_service.create_config(cfg)


@router.put("/{config_id}", response_model=EventConfigOut, dependencies=[Depends(require_role("operator"))])
async def update_event_config(config_id: str, updates: EventConfigUpdate):
    return await event_service.update_config(config_id, updates)


@router.delete("/{config_id}", dependencies=[Depends(require_role("admin"))])
async def delete_event_config(config_id: str):
    return await event_service.delete_config(config_id)


@router.post("/publish", dependencies=[Depends(require_role("operator"))])
async def publish_event(req: PublishEventRequest):
    try:
        record = await event_service.publish_test(req.org_id, req.channel, req.payload)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {"detail": "published", "transaction_id": record["id"]}


@router.post("/schema/infer", dependencies=[Depends(require_role("operator"))])
def infer_schema_from_sample(body: dict):
    from ..worker import infer_json_schema
    sample = body.get("sample")
    if not isinstance(sample, dict):
        raise HTTPException(400, "sample must be a JSON object")
    return infer_json_schema(sample)
