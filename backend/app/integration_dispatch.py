"""Dispatch fan-out."""
from typing import Optional

from .database import integrations_table, Q
from .logging_config import log_event
from .tracing import start_span
from .integration_http import (
    _send_webhook, _send_custom_api, _send_slack, _send_teams, _record_result,
)
from .integration_other import (
    _send_email, _load_snowflake, _load_bigquery, _send_sharepoint_file, _send_sharepoint_list,
)

_SENDERS = {
    "webhook": _send_webhook,
    "custom_api": _send_custom_api,
    "slack": _send_slack,
    "teams": _send_teams,
    "email": _send_email,
    "snowflake": _load_snowflake,
    "bigquery": _load_bigquery,
    "sharepoint_file": _send_sharepoint_file,
    "sharepoint_list": _send_sharepoint_list,
}


def _matches_trigger(trigger: str, status: str) -> bool:
    if trigger == "always":
        return True
    if trigger == "on_success":
        return status == "published"
    if trigger == "on_failure":
        return status == "failed"
    return False


def dispatch_integrations(transaction: dict, only_ids: Optional[list] = None, trace_carrier: Optional[dict] = None):
    org_id = transaction.get("org_id")
    status = transaction.get("status")
    candidates = integrations_table.search(Q.enabled == True)  # noqa: E712
    candidates = [c for c in candidates if not c.get("alert_only")]
    if only_ids is not None:
        candidates = [c for c in candidates if c["id"] in only_ids]
    for cfg in candidates:
        if only_ids is None and cfg.get("org_id") not in (None, "", org_id):
            continue
        if not _matches_trigger(cfg.get("trigger", "always"), status):
            continue
        sender = _SENDERS.get(cfg.get("type"))
        if sender is None:
            continue
        from .circuit import is_open, record_success, record_failure
        from .metrics import inc
        sink_id = f"integration:{cfg['id']}"
        if is_open(sink_id):
            inc("circuit_open_total")
            log_event("warning", f"Integration '{cfg['name']}' circuit open — skipped", integration_id=cfg["id"])
            continue
        with start_span(f"integration.{cfg['type']}", carrier=trace_carrier, integration_id=cfg["id"], transaction_id=transaction.get("id")):
            try:
                result = sender(cfg, transaction)
                record_success(sink_id)
                inc("integration_ok_total")
                _record_result(cfg["id"], "ok", result=result)
                log_event("info", f"Integration '{cfg['name']}' ({cfg['type']}) dispatched", transaction_id=transaction.get("id"), integration_id=cfg["id"], result=result)
            except Exception as exc:  # noqa: BLE001
                record_failure(sink_id)
                inc("integration_error_total")
                _record_result(cfg["id"], "error", str(exc))
                log_event("error", f"Integration '{cfg['name']}' ({cfg['type']}) failed: {exc}", transaction_id=transaction.get("id"), integration_id=cfg["id"])
                from . import alerts as alerts_module
                alerts_module.fire_alert("integration_failed", {
                    "integration_id": cfg["id"], "integration_name": cfg["name"], "integration_type": cfg["type"],
                    "transaction_id": transaction.get("id"), "error": str(exc),
                }, org_id=cfg.get("org_id"))
