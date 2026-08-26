from fastapi import APIRouter, Depends, Query
from typing import Optional, List

from ..auth import get_current_user
from ..database import transactions_table, Q
from ..models import TransactionOut

router = APIRouter(prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    org_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    direction: Optional[str] = None,
    limit: int = 200,
):
    rows = transactions_table.all()
    if org_id:
        rows = [r for r in rows if r["org_id"] == org_id]
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    if direction:
        rows = [r for r in rows if r["direction"] == direction]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


@router.get("/stats")
def transaction_stats():
    rows = transactions_table.all()
    total = len(rows)
    by_status = {}
    by_org = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        key = r.get("org_name") or r["org_id"]
        by_org[key] = by_org.get(key, 0) + 1
    failed = by_status.get("failed", 0)
    published = by_status.get("published", 0)
    success_rate = round((published / total) * 100, 1) if total else 100.0
    return {
        "total": total,
        "by_status": by_status,
        "by_org": by_org,
        "failed": failed,
        "published": published,
        "success_rate": success_rate,
    }
