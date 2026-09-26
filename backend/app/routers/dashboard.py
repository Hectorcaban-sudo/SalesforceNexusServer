import time
from fastapi import APIRouter, Depends
from typing import Optional

from ..auth import get_current_user
from ..database import orgs_table, transactions_table, event_configs_table, Q
from ..broker import broker
from ..cometd_client import cometd_manager
from ..config import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/summary")
def summary(project_id: Optional[str] = None):
    from ..project_scope import filter_by_project
    orgs = filter_by_project(orgs_table.all(), project_id, include_global=False) if project_id else orgs_table.all()
    org_ids = {o["id"] for o in orgs}
    connected = sum(1 for o in orgs if o.get("active") and cometd_manager.status_for(o["id"]) == "connected")
    rows = transactions_table.all()
    if project_id:
        rows = [r for r in rows if r.get("project_id") == project_id or r.get("org_id") in org_ids]

    now = time.time()
    last_hour = [r for r in rows if now - r["created_at"] <= 3600]

    # bucket last 24 hours into 24 hourly buckets for the trend chart
    buckets = [0] * 24
    for r in rows:
        age_h = (now - r["created_at"]) / 3600
        if 0 <= age_h < 24:
            idx = 23 - int(age_h)
            buckets[idx] += 1

    events = event_configs_table.all()
    if project_id:
        events = filter_by_project(events, project_id, include_global=False)
    subs = [e for e in events if e.get("direction") == "subscribe"]
    pipelines_on = 0
    attention = []
    try:
        from ..database import event_pipelines_table
        from ..routers.pipelines import list_enabled_pipelines
        for ev in subs:
            enabled = list_enabled_pipelines(ev)
            pipelines_on += len(enabled)
            if ev.get("enabled") and not enabled:
                attention.append({
                    "kind": "no_pipeline",
                    "title": f"Event {ev.get('channel')} has no enabled pipeline",
                    "href": f"/events/{ev['id']}/pipelines",
                })
    except Exception:
        pass
    skipped_hour = sum(1 for r in last_hour if r.get("status") == "skipped")
    failed_hour = [r for r in last_hour if r.get("status") == "failed"]
    for r in failed_hour[:8]:
        attention.append({
            "kind": "failed",
            "title": f"{r.get('channel') or 'transaction'} failed",
            "href": "/transactions",
            "detail": (r.get("error") or "")[:160],
        })
    for o in orgs:
        st = cometd_manager.status_for(o["id"]) if o.get("active") else "disconnected"
        if o.get("active") and st != "connected":
            attention.append({
                "kind": "org_down",
                "title": f"Org {o.get('name')} is {st}",
                "href": "/orgs",
            })

    return {
        "app_name": settings.app_name,
        "total_orgs": len(orgs),
        "connected_orgs": connected,
        "total_event_configs": len(events),
        "subscribe_channels": len(subs),
        "pipelines_enabled": pipelines_on,
        "skipped_last_hour": skipped_hour,
        "failed_last_hour": len(failed_hour),
        "attention": attention[:12],
        "total_transactions": len(rows),
        "transactions_last_hour": len(last_hour),
        "inbound_queue_depth": broker.queue_depth("inbound"),
        "outbound_queue_depth": broker.queue_depth("outbound"),
        "hourly_transaction_trend": buckets,
        "orgs": [
            {
                "id": o["id"],
                "name": o["name"],
                "active": o.get("active", False),
                "status": cometd_manager.status_for(o["id"]) if o.get("active") else "disconnected",
            }
            for o in orgs
        ],
    }


@router.get("/notifications")
def notifications(project_id: Optional[str] = None):
    """Unread-style inbox derived from summary attention (no extra store in v1)."""
    data = summary(project_id=project_id)
    items = []
    for i, a in enumerate(data.get("attention") or []):
        items.append({
            "id": f"att-{i}",
            "kind": a.get("kind"),
            "title": a.get("title"),
            "detail": a.get("detail"),
            "href": a.get("href"),
            "read": False,
        })
    return {"count": len(items), "items": items}


@router.get("/ui-settings")
def get_ui_settings():
    from ..database import admin_settings_table
    row = admin_settings_table.get(Q.id == "ui_settings") or {}
    return {
        "docs_url": row.get("docs_url") or "",
        "docs_label": row.get("docs_label") or "Documentation",
    }
