"""Projects: multi-customer / solution boundary for orgs, events, integrations."""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from ..auth import get_current_user, require_role
from ..database import (
    projects_table, project_members_table, users_table,
    orgs_table, event_configs_table, integrations_table,
    processors_table, rules_table, alerts_table,
    sharepoint_connections_table, sharepoint_file_actions_table,
    sharepoint_list_actions_table, Q,
)
from ..models import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectMemberCreate, ProjectMemberOut, new_id, now_ts,
)
from ..logging_config import log_event

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(get_current_user)])

DEFAULT_PROJECT_NAME = "Default Project"


def ensure_default_project() -> dict:
    """Create a default project and attach unscoped resources once."""
    try:
        existing = projects_table.search(Q.name == DEFAULT_PROJECT_NAME)
    except Exception:
        existing = []
    if existing:
        default = existing[0]
    else:
        # Prefer first project if any exists under a different name
        all_projects = projects_table.all()
        if all_projects:
            default = all_projects[0]
        else:
            default = {
                "id": new_id(),
                "name": DEFAULT_PROJECT_NAME,
                "description": "Auto-created for existing configuration",
                "enabled": True,
                "created_at": str(now_ts()),
            }
            projects_table.insert(default)
            log_event("info", f"Created default project {default['id']}")

    pid = default["id"]

    def _attach(table):
        try:
            for row in table.all():
                rid = row.get("id")
                if rid and not row.get("project_id"):
                    try:
                        table.update({"project_id": pid}, Q.id == rid)
                    except Exception as exc:
                        log_event("warning", f"Could not attach project_id to {rid}: {exc}")
        except Exception as exc:
            log_event("warning", f"Project attach scan failed: {exc}")

    for tbl in (
        orgs_table,
        event_configs_table,
        integrations_table,
        processors_table,
        rules_table,
        alerts_table,
        sharepoint_connections_table,
        sharepoint_file_actions_table,
        sharepoint_list_actions_table,
    ):
        _attach(tbl)
    return default


@router.get("", response_model=List[ProjectOut])
def list_projects():
    ensure_default_project()
    rows = projects_table.all()
    # Normalize created_at for response model (str | None)
    out = []
    for r in rows:
        item = dict(r)
        if item.get("created_at") is not None:
            item["created_at"] = str(item["created_at"])
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, dependencies=[Depends(require_role("admin"))])
def create_project(body: ProjectCreate):
    record = body.model_dump()
    record["id"] = new_id()
    record["created_at"] = str(now_ts())
    projects_table.insert(record)
    log_event("info", f"Project created: {record['name']}", project_id=record["id"])
    return record


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str):
    ensure_default_project()
    p = projects_table.get(Q.id == project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    item = dict(p)
    if item.get("created_at") is not None:
        item["created_at"] = str(item["created_at"])
    return item


@router.put("/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_role("admin"))])
def update_project(project_id: str, body: ProjectUpdate):
    p = projects_table.get(Q.id == project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    projects_table.update(data, Q.id == project_id)
    item = dict(projects_table.get(Q.id == project_id))
    if item.get("created_at") is not None:
        item["created_at"] = str(item["created_at"])
    return item


@router.delete("/{project_id}", dependencies=[Depends(require_role("admin"))])
def delete_project(project_id: str):
    p = projects_table.get(Q.id == project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    if p.get("name") == DEFAULT_PROJECT_NAME:
        raise HTTPException(400, "Cannot delete the default project")
    for label, table in (
        ("orgs", orgs_table),
        ("events", event_configs_table),
        ("integrations", integrations_table),
    ):
        if table.search(Q.project_id == project_id):
            raise HTTPException(400, f"Project still has {label}; reassign or delete them first")
    project_members_table.remove(Q.project_id == project_id)
    projects_table.remove(Q.id == project_id)
    return {"detail": "deleted"}


@router.get("/{project_id}/members", response_model=List[ProjectMemberOut])
def list_members(project_id: str):
    if not projects_table.get(Q.id == project_id):
        raise HTTPException(404, "Project not found")
    out = []
    for m in project_members_table.search(Q.project_id == project_id):
        u = users_table.get(Q.id == m["user_id"])
        out.append({
            **m,
            "username": (u or {}).get("username"),
        })
    return out


@router.post("/{project_id}/members", response_model=ProjectMemberOut, dependencies=[Depends(require_role("admin"))])
def add_member(project_id: str, body: ProjectMemberCreate):
    if not projects_table.get(Q.id == project_id):
        raise HTTPException(404, "Project not found")
    user = users_table.get(Q.id == body.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    existing = project_members_table.search(
        (Q.project_id == project_id) & (Q.user_id == body.user_id)
    )
    if existing:
        raise HTTPException(400, "User is already a member of this project")
    record = {
        "id": new_id(),
        "project_id": project_id,
        "user_id": body.user_id,
        "role": body.role or "project_admin",
    }
    project_members_table.insert(record)
    return {**record, "username": user.get("username")}


@router.delete("/{project_id}/members/{member_id}", dependencies=[Depends(require_role("admin"))])
def remove_member(project_id: str, member_id: str):
    m = project_members_table.get(Q.id == member_id)
    if not m or m.get("project_id") != project_id:
        raise HTTPException(404, "Member not found")
    project_members_table.remove(Q.id == member_id)
    return {"detail": "deleted"}
