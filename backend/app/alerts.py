"""
Alerts.

An alert rule watches for a category of failure (a transaction failing, a
Salesforce org's CometD connection going down, an integration dispatch
failing, or the configured RabbitMQ broker failing to connect) and, when it
fires, delivers a notification through one of the already-configured
Integration sinks (webhook/Slack/Teams/custom API - the same sender
functions `integrations.py` uses for normal transaction fan-out).

Two ways an alert rule gets selected when something fails:
  1. Global rules: scope + org match (org_id=None applies to every org).
  2. Per-event rules: a specific subscribed event channel's `route_alert_ids`
     (set from the Routing dialog) restrict transaction_failed alerts to
     exactly the rules picked for that channel, same pattern as
     `route_integration_ids` for normal integration dispatch.

IMPORTANT: alert delivery calls sender functions directly rather than going
through `dispatch_integrations()`, so a failing alert-delivery sink can never
itself trigger another "integration_failed" alert and loop forever.
"""
from typing import Optional

from .database import alerts_table, integrations_table, Q
from .logging_config import log_event
from .models import now_ts


def _matches_scope_and_org(rule: dict, scope: str, org_id: Optional[str]) -> bool:
    if rule.get("scope") != scope:
        return False
    if rule.get("org_id") not in (None, "") and rule.get("org_id") != org_id:
        return False
    return True


def _deliver(rule: dict, context: dict) -> None:
    from .integrations import _SENDERS  # local import avoids a circular import at module load time

    integration = integrations_table.get(Q.id == rule["integration_id"])
    if not integration or not integration.get("enabled", True):
        log_event("warning", f"Alert '{rule['name']}' has no enabled integration sink configured; skipping delivery")
        return

    sender = _SENDERS.get(integration.get("type"))
    if sender is None:
        return

    # Shape the alert as a transaction-like dict, since every sender function
    # (webhook/slack/teams/custom_api) already knows how to format one of
    # these - this reuses that formatting rather than duplicating it.
    alert_transaction = {
        "id": f"alert-{rule['id']}",
        "org_id": context.get("org_id") or rule.get("org_id") or "",
        "org_name": context.get("org_name", ""),
        "direction": "alert",
        "channel": context.get("channel", rule["scope"]),
        "status": "failed",
        "payload": context,
        "result": None,
        "error": context.get("error") or f"Alert triggered: {rule['scope']}",
        "created_at": now_ts(),
    }

    try:
        sender(integration, alert_transaction)
        alerts_table.update({"last_status": "ok", "last_fired_at": now_ts(), "last_error": None}, Q.id == rule["id"])
        log_event("info", f"Alert '{rule['name']}' fired successfully", scope=rule["scope"], context=context)
    except Exception as exc:  # noqa: BLE001
        alerts_table.update({"last_status": "error", "last_fired_at": now_ts(), "last_error": str(exc)}, Q.id == rule["id"])
        log_event("error", f"Alert '{rule['name']}' failed to deliver: {exc}", scope=rule["scope"])


def fire_alert(scope: str, context: dict, org_id: Optional[str] = None, only_ids: Optional[list] = None):
    """
    Fire every enabled alert rule matching `scope` (+ org, unless `only_ids`
    is given). Best-effort and never raises - a broken alert rule should
    never affect the pipeline that triggered it.
    """
    try:
        rules = alerts_table.search(Q.enabled == True)  # noqa: E712
        if only_ids is not None:
            rules = [r for r in rules if r["id"] in only_ids and r.get("scope") == scope]
        else:
            rules = [r for r in rules if _matches_scope_and_org(r, scope, org_id)]

        for rule in rules:
            _deliver(rule, context)
    except Exception as exc:  # noqa: BLE001
        log_event("error", f"Alert dispatch itself failed unexpectedly: {exc}")


def fire_alert_for_transaction(transaction: dict, only_ids: Optional[list] = None):
    """Convenience wrapper used wherever a transaction ends in 'failed'."""
    if transaction.get("status") != "failed":
        return
    context = {
        "transaction_id": transaction.get("id"),
        "org_id": transaction.get("org_id"),
        "org_name": transaction.get("org_name"),
        "channel": transaction.get("channel"),
        "direction": transaction.get("direction"),
        "error": transaction.get("error"),
    }
    fire_alert("transaction_failed", context, org_id=transaction.get("org_id"), only_ids=only_ids)
