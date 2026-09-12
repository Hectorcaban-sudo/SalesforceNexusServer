"""Helpers for creating/updating transaction records (the audit trail the
admin dashboard displays for every event that flows through the system)."""
from typing import Optional
from .database import transactions_table, orgs_table, projects_table, Q
from .models import new_id, now_ts


def _resolve_project(org_id: Optional[str]) -> tuple:
    """Return (project_id, project_name) from the org, if available."""
    if not org_id:
        return None, None
    org = orgs_table.get(Q.id == org_id)
    if not org:
        return None, None
    pid = org.get("project_id")
    if not pid:
        return None, None
    proj = projects_table.get(Q.id == pid)
    return pid, (proj or {}).get("name")


def record_transaction(
    org_id: str,
    org_name: Optional[str],
    direction: str,
    channel: str,
    status: str,
    payload: dict,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    parent_transaction_id: Optional[str] = None,
) -> dict:
    project_id, project_name = _resolve_project(org_id)
    record = {
        "id": new_id(),
        "org_id": org_id,
        "org_name": org_name,
        "project_id": project_id,
        "project_name": project_name,
        "direction": direction,
        "channel": channel,
        "status": status,
        "payload": payload,
        "result": result,
        "error": error,
        "attempts": 0,
        "parent_transaction_id": parent_transaction_id,
        "created_at": now_ts(),
        "updated_at": now_ts(),
    }
    transactions_table.insert(record)
    return record


def update_transaction(transaction_id: str, **fields):
    fields["updated_at"] = now_ts()
    transactions_table.update(fields, Q.id == transaction_id)


def get_transaction(transaction_id: str) -> Optional[dict]:
    return transactions_table.get(Q.id == transaction_id)
