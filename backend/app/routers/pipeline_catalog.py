from fastapi import APIRouter, Depends
from typing import Optional
from ..auth import get_current_user
from ..database import event_pipelines_table, event_configs_table, orgs_table, Q

router = APIRouter(prefix="/api/pipeline-catalog", tags=["pipelines"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_catalog(project_id: Optional[str] = None):
    rows = []
    for p in event_pipelines_table.all():
        ev = event_configs_table.get(Q.id == p.get("event_id")) or {}
<<<<<<< Updated upstream
        if project_id and ev.get("project_id") not in (None, "", project_id):
=======
        if project_id and ev.get("project_id") not in (None, "", project_id) and p.get("project_id") not in (None, "", project_id):
>>>>>>> Stashed changes
            if ev.get("project_id") != project_id:
                continue
        org = orgs_table.get(Q.id == ev.get("org_id")) or {}
        nodes = ((p.get("flow_graph") or {}).get("nodes") or [])
        rows.append({
            **p,
            "channel": ev.get("channel"),
            "org_id": ev.get("org_id"),
            "org_name": org.get("name"),
<<<<<<< Updated upstream
=======
            "event_project_id": ev.get("project_id"),
>>>>>>> Stashed changes
            "source": "event",
            "node_count": len(nodes),
        })
    return rows
