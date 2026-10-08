from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import Q
from ..flow_actions import flow_actions_table
from ..models import new_id, now_ts

router = APIRouter(prefix="/api/flow-actions", tags=["flow-actions"], dependencies=[Depends(get_current_user)])


class FlowActionIn(BaseModel):
    name: str
    type: str
    enabled: bool = True
    project_id: Optional[str] = None
    object_template: str = "ContentDocument"
    id_template: str = "{{ payload.ContentDocumentId }}"
    sharepoint_action_id: str = ""
    replace_existing: bool = False
    name_prefix: str = ""


@router.get("")
def list_actions():
    return flow_actions_table.all()


@router.post("")
def create_action(body: FlowActionIn):
    if body.type not in ("salesforce_get", "salesforce_delete", "sharepoint_file"):
        raise HTTPException(400, "type must be salesforce_get, salesforce_delete, or sharepoint_file")
    row = {"id": new_id(), **body.model_dump(), "created_at": str(now_ts())}
    flow_actions_table.insert(row)
    return row


@router.delete("/{action_id}")
def delete_action(action_id: str):
    removed = flow_actions_table.remove(Q.id == action_id)
    if not removed:
        raise HTTPException(404, "Flow action not found")
    return {"ok": True}
