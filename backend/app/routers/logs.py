from fastapi import APIRouter, Depends, Query
from typing import Optional, List

from ..auth import get_current_user
from ..database import logs_table
from ..models import LogEntryOut

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[LogEntryOut])
def list_logs(
    level: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 300,
):
    rows = logs_table.all()
    if level:
        rows = [r for r in rows if r["level"] == level.upper()]
    if search:
        s = search.lower()
        rows = [r for r in rows if s in r["message"].lower()]
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows[:limit]


@router.delete("")
def clear_logs():
    logs_table.truncate()
    return {"detail": "logs cleared"}
