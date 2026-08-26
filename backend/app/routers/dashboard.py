import time
from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..database import orgs_table, transactions_table, event_configs_table, Q
from ..broker import broker
from ..cometd_client import cometd_manager
from ..config import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/summary")
def summary():
    orgs = orgs_table.all()
    connected = sum(1 for o in orgs if o.get("active") and cometd_manager.status_for(o["id"]) == "connected")
    rows = transactions_table.all()

    now = time.time()
    last_hour = [r for r in rows if now - r["created_at"] <= 3600]

    # bucket last 24 hours into 24 hourly buckets for the trend chart
    buckets = [0] * 24
    for r in rows:
        age_h = (now - r["created_at"]) / 3600
        if 0 <= age_h < 24:
            idx = 23 - int(age_h)
            buckets[idx] += 1

    return {
        "app_name": settings.app_name,
        "total_orgs": len(orgs),
        "connected_orgs": connected,
        "total_event_configs": len(event_configs_table.all()),
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
