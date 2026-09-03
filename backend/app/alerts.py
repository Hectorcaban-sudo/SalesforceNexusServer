"""
Alerts.

An alert rule watches for a category of outcome (a transaction reaching a
terminal state, a Salesforce org's CometD connection going down, an
integration dispatch failing, or the configured RabbitMQ broker failing to
connect) and, when it fires, delivers a notification through one of the
already-configured Integration sinks (webhook/Slack/Teams/email/custom API -
the same sender functions `integrations.py` uses for normal transaction
fan-out).

The "transaction" scope can fire on success, failure, or always - set via
its `trigger` field (mirrors Integration's trigger semantics exactly):
  - "always"      : any terminal transaction (published, processed, or failed)
  - "on_success"  : published or processed with no error
  - "on_failure"  : failed (the default, matching the original behavior)
The other three scopes are inherently single-outcome events with no natural
success counterpart, so `trigger` is ignored for those.

Two ways an alert rule gets selected when a transaction reaches a terminal
state:
  1. Global rules: scope + org match (org_id=None applies to every org).
  2. Per-event rules: a specific subscribed event channel's `route_alert_ids`
     (set from the Routing dialog) restrict alert dispatch to exactly the
     rules picked for that channel, same pattern as `route_integration_ids`
     for normal integration dispatch.

IMPORTANT: alert delivery calls sender functions directly rather than going
through `dispatch_integrations()`, so a failing alert-delivery sink can never
itself trigger another "integration_failed" alert and loop forever.
"""
from typing import Optional

from .database import alerts_table, integrations_table, Q
from .logging_config import log_event
from .models import now_ts

TERMINAL_TRANSACTION_STATUSES = ("published", "processed", "failed")


def _matches_scope_and_org(rule: dict, scope: str, org_id: Optional[str]) -> bool:
    if rule.get("scope") != scope:
        return False
    if rule.get("org_id") not in (None, "") and rule.get("org_id") != org_id:
        return False
    return True


def _matches_transaction_trigger(trigger: str, transaction: dict) -> bool:
    status = transaction.get("status")
    if status not in TERMINAL_TRANSACTION_STATUSES:
        return False
    if trigger == "always":
        return True
    if trigger == "on_success":
        return status in ("published", "processed") and not transaction.get("error")
    if trigger == "on_failure":
        return status == "failed"
    return False


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
    # (webhook/slack/teams/email/custom_api) already knows how to format one
    # of these - this reuses that formatting rather than duplicating it.
    alert_transaction = {
        "id": f"alert-{rule['id']}",
        "org_id": context.get("org_id") or rule.get("org_id") or "",
        "org_name": context.get("org_name", ""),
        "direction": "alert",
        "channel": context.get("channel", rule["scope"]),
        "status": context.get("status", "failed"),
        "payload": context,
        "result": None,
        "error": context.get("error") or (None if context.get("status") in ("published", "processed") else f"Alert triggered: {rule['scope']}"),
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
    is given). Used for the three single-outcome scopes (connection_failed,
    integration_failed, broker_degraded) - `fire_alert_for_transaction` below
    handles the "transaction" scope's trigger logic separately. Best-effort
    and never raises - a broken alert rule should never affect the pipeline
    that triggered it.
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
    """
    Call this wherever a transaction reaches a terminal state (published,
    processed, or failed) - each matching "transaction"-scoped alert rule's
    own `trigger` decides whether it actually fires for this particular
    outcome. Silently does nothing if the transaction isn't in a terminal
    state yet, and never raises.
    """
    try:
        if transaction.get("status") not in TERMINAL_TRANSACTION_STATUSES:
            return

        org_id = transaction.get("org_id")
        context = {
            "transaction_id": transaction.get("id"),
            "org_id": org_id,
            "org_name": transaction.get("org_name"),
            "channel": transaction.get("channel"),
            "direction": transaction.get("direction"),
            "status": transaction.get("status"),
            "error": transaction.get("error"),
        }

        rules = alerts_table.search(Q.enabled == True)  # noqa: E712
        if only_ids is not None:
            rules = [r for r in rules if r["id"] in only_ids and r.get("scope") == "transaction"]
        else:
            rules = [r for r in rules if _matches_scope_and_org(r, "transaction", org_id)]

        for rule in rules:
            if _matches_transaction_trigger(rule.get("trigger", "on_failure"), transaction):
                _deliver(rule, context)
    except Exception as exc:  # noqa: BLE001
        log_event("error", f"Alert dispatch itself failed unexpectedly: {exc}")
