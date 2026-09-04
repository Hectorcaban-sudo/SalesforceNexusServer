from fastapi import APIRouter, Depends, Query
from typing import Optional, List

from ..auth import require_role
from ..database import audit_log_table, auth_events_table

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_role("admin"))])


@router.get("/actions")
def list_audit_actions(username: Optional[str] = None, limit: int = 300):
    """Every privileged (state-changing) admin-console API call - see
    audit.py / AuditMiddleware in main.py for what gets captured."""
    rows = audit_log_table.all()
    if username:
        rows = [r for r in rows if r["username"] == username]
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows[:limit]


@router.get("/auth-events")
def list_auth_events(username: Optional[str] = None, event_type: Optional[str] = None, limit: int = 300):
    """Every authentication-related event: login success/failure, lockouts,
    unlocks, password changes, SSO logins."""
    rows = auth_events_table.all()
    if username:
        rows = [r for r in rows if r["username"] == username]
    if event_type:
        rows = [r for r in rows if r["event_type"] == event_type]
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows[:limit]


@router.get("/summary")
def audit_summary():
    """Quick counts for the Authentication Monitoring dashboard: recent
    failed logins, currently-locked accounts, etc."""
    import time
    from ..database import users_table

    auth_rows = auth_events_table.all()
    now = time.time()
    last_24h = [r for r in auth_rows if now - r["timestamp"] <= 86400]

    locked_accounts = [
        {"username": u["username"], "locked_until": u.get("locked_until")}
        for u in users_table.all()
        if u.get("locked_until") and u["locked_until"] > now
    ]

    return {
        "total_auth_events": len(auth_rows),
        "auth_events_last_24h": len(last_24h),
        "failed_logins_last_24h": len([r for r in last_24h if r["event_type"] in ("login_failure", "login_blocked_locked")]),
        "successful_logins_last_24h": len([r for r in last_24h if r["event_type"] in ("login_success", "sso_login_success")]),
        "locked_accounts": locked_accounts,
        "total_audit_actions": len(audit_log_table.all()),
    }
