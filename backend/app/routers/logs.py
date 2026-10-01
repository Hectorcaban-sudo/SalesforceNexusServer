from fastapi import APIRouter, Depends, Query
from typing import Optional, List
import json

from ..auth import get_current_user, require_role
from ..database import logs_table
from ..models import LogEntryOut

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(get_current_user)])


def _context(row):
    ctx = row.get("context") or {}
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = {}
    return ctx if isinstance(ctx, dict) else {}


@router.get("", response_model=List[LogEntryOut])
def list_logs(
    level: Optional[str] = None,
    search: Optional[str] = None,
    transaction_id: Optional[str] = None,
    limit: int = 500,
):
    rows = logs_table.all()
    if level:
        rows = [r for r in rows if r["level"] == level.upper()]
    if transaction_id:
        tid = str(transaction_id)
        def matches_tx(r):
            ctx = _context(r)
            if str(ctx.get("transaction_id") or "") == tid:
                return True
            return tid in (r.get("message") or "")
        rows = [r for r in rows if matches_tx(r)]
    if search:
        s = search.lower()
        rows = [r for r in rows if s in (r.get("message") or "").lower()]
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows[:limit]


@router.delete("", dependencies=[Depends(require_role("admin"))])
def clear_logs():
    logs_table.truncate()
    return {"detail": "logs cleared"}
