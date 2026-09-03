from fastapi import APIRouter, Depends, HTTPException
from typing import List

from ..auth import get_current_user, require_role
from ..database import alerts_table, integrations_table, Q
from ..models import AlertCreate, AlertUpdate, AlertOut, new_id, now_ts
from ..logging_config import log_event

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[AlertOut])
def list_alerts():
    return alerts_table.all()


@router.post("", response_model=AlertOut, dependencies=[Depends(require_role("admin"))])
def create_alert(alert: AlertCreate):
    if not integrations_table.get(Q.id == alert.integration_id):
        raise HTTPException(404, "Selected integration sink not found")
    record = alert.model_dump()
    record.update({"id": new_id(), "last_fired_at": None, "last_status": None, "last_error": None})
    alerts_table.insert(record)
    log_event("info", f"Alert '{record['name']}' created", scope=record["scope"])
    return record


@router.put("/{alert_id}", response_model=AlertOut, dependencies=[Depends(require_role("admin"))])
def update_alert(alert_id: str, updates: AlertUpdate):
    existing = alerts_table.get(Q.id == alert_id)
    if not existing:
        raise HTTPException(404, "Alert not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    alerts_table.update(data, Q.id == alert_id)
    log_event("info", f"Alert '{existing['name']}' updated", fields=list(data.keys()))
    return alerts_table.get(Q.id == alert_id)


@router.delete("/{alert_id}", dependencies=[Depends(require_role("admin"))])
def delete_alert(alert_id: str):
    existing = alerts_table.get(Q.id == alert_id)
    if not existing:
        raise HTTPException(404, "Alert not found")
    alerts_table.remove(Q.id == alert_id)
    log_event("warning", f"Alert '{existing['name']}' deleted")
    return {"detail": "deleted"}


@router.post("/{alert_id}/test", dependencies=[Depends(require_role("admin"))])
def test_alert(alert_id: str):
    rule = alerts_table.get(Q.id == alert_id)
    if not rule:
        raise HTTPException(404, "Alert not found")

    from ..alerts import _deliver  # noqa: PLC0415

    try:
        test_status = "failed" if rule.get("trigger", "on_failure") != "on_success" else "published"
        _deliver(rule, {
            "transaction_id": "test-" + new_id(),
            "org_id": rule.get("org_id"),
            "org_name": "Test Org",
            "channel": rule["scope"],
            "status": test_status,
            "error": "This is a test alert from Salesforce Nexus AI Server" if test_status == "failed" else None,
        })
        updated = alerts_table.get(Q.id == alert_id)
        if updated.get("last_status") == "error":
            raise HTTPException(400, f"Test failed: {updated.get('last_error')}")
        return {"detail": "Test alert sent successfully"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Test failed: {exc}")
