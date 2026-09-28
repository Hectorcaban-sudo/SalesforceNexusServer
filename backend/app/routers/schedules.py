from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from ..auth import get_current_user, require_role
from ..database import scheduled_jobs_table, orgs_table, Q
from ..models import new_id, now_ts
from ..scheduler import reload_jobs, run_now

router = APIRouter(prefix="/api/schedules", tags=["schedules"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_jobs(project_id: Optional[str] = None):
    rows = scheduled_jobs_table.all()
    if project_id:
        rows = [r for r in rows if r.get("project_id") == project_id]
    return rows


@router.post("", dependencies=[Depends(require_role("operator"))])
async def create_job(body: dict):
    if not orgs_table.get(Q.id == body.get("org_id")):
        raise HTTPException(404, "Org not found")
    rec = {
        "id": new_id(),
        "name": body.get("name") or "Scheduled job",
        "description": body.get("description") or "",
        "project_id": body.get("project_id"),
        "org_id": body.get("org_id"),
        "soql": body.get("soql") or "",
        "cron": body.get("cron") or "0 2 * * *",
        "timezone": body.get("timezone") or "UTC",
        "mode": body.get("mode") or "per_record",
        "pipeline_ids": body.get("pipeline_ids") or [],
        "max_records": int(body.get("max_records") or 500),
        "enabled": body.get("enabled", True),
        "last_run_at": None,
        "last_count": None,
        "last_error": None,
        "created_at": now_ts(),
    }
    scheduled_jobs_table.insert(rec)
    await reload_jobs()
    return rec


@router.put("/{job_id}", dependencies=[Depends(require_role("operator"))])
async def update_job(job_id: str, body: dict):
    if not scheduled_jobs_table.get(Q.id == job_id):
        raise HTTPException(404, "Job not found")
    data = {k: v for k, v in body.items() if k in (
        "name", "description", "org_id", "soql", "cron", "timezone",
        "mode", "pipeline_ids", "max_records", "enabled", "project_id",
    )}
    scheduled_jobs_table.update(data, Q.id == job_id)
    await reload_jobs()
    return scheduled_jobs_table.get(Q.id == job_id)


@router.delete("/{job_id}", dependencies=[Depends(require_role("admin"))])
async def delete_job(job_id: str):
    scheduled_jobs_table.remove(Q.id == job_id)
    await reload_jobs()
    return {"detail": "deleted"}


@router.post("/{job_id}/run", dependencies=[Depends(require_role("operator"))])
async def run_job_now(job_id: str):
    if not scheduled_jobs_table.get(Q.id == job_id):
        raise HTTPException(404, "Job not found")
    await run_now(job_id)
    return scheduled_jobs_table.get(Q.id == job_id)
