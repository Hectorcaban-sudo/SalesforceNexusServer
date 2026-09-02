"""
Outbound integration fan-out.

After a transaction is processed (and Salesforce publish is attempted), it
is optionally fanned out to any number of configured "integration sinks" -
a webhook, a Slack/Teams notification, a data-warehouse loader, or a
generic custom API call. Each sink is independent, best-effort (a failure
here never affects the Salesforce publish outcome or the transaction's
recorded status), and scoped by:

  - `org_id`   : None = applies to every org, or a specific org's events only
  - `trigger`  : "always" | "on_success" | "on_failure" (based on the
                 transaction's final status)
  - `enabled`  : toggle without deleting the configuration

Heavy warehouse client libraries (snowflake-connector-python,
google-cloud-bigquery) are optional dependencies - if they aren't installed,
the corresponding sink logs a clear message telling you how to enable it
instead of crashing the pipeline.
"""
import hashlib
import hmac
import json
import time
from typing import Optional

import requests
import urllib3

from .database import integrations_table, Q
from .logging_config import log_event
from .tracing import start_span

# Many internal/enterprise integration endpoints sit behind self-signed or
# internally-issued certificates. SSL verification is disabled for every
# outbound integration call by deliberate operator choice - suppress the
# resulting urllib3 warning spam that would otherwise flood the logs.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _record_result(integration_id: str, status: str, error: Optional[str] = None, result: Optional[dict] = None):
    integrations_table.update(
        {"last_status": status, "last_run_at": time.time(), "last_error": error, "last_result": result},
        Q.id == integration_id,
    )


def _response_summary(resp) -> dict:
    """Best-effort JSON-or-text summary of an HTTP response, capped in size
    so a huge response body doesn't bloat the stored log record."""
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:2000]
    return {"status_code": resp.status_code, "body": body}


def _send_webhook(cfg: dict, transaction: dict) -> dict:
    url = cfg["config"]["url"]
    secret = cfg["config"].get("secret", "")
    body = json.dumps(transaction, default=str)
    headers = dict(cfg["config"].get("headers", {}))
    headers["Content-Type"] = "application/json"
    if secret:
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Nexus-Signature"] = f"sha256={signature}"
    resp = requests.post(url, data=body, headers=headers, timeout=15, verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_custom_api(cfg: dict, transaction: dict) -> dict:
    c = cfg["config"]
    method = c.get("method", "POST").upper()
    headers = dict(c.get("headers", {}))
    if c.get("auth_header"):
        headers["Authorization"] = c["auth_header"]
    resp = requests.request(method, c["url"], json=transaction, headers=headers, timeout=15, verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_slack(cfg: dict, transaction: dict) -> dict:
    webhook_url = cfg["config"]["webhook_url"]
    status_emoji = {"published": "✅", "failed": "❌"}.get(transaction.get("status"), "ℹ️")
    text = (
        f"{status_emoji} *Salesforce Nexus AI Server* — transaction `{transaction.get('id')}`\n"
        f"Org: *{transaction.get('org_name')}* · Channel: `{transaction.get('channel')}` · "
        f"Status: *{transaction.get('status')}*"
    )
    if transaction.get("error"):
        text += f"\nError: {transaction['error']}"
    resp = requests.post(webhook_url, json={"text": text}, timeout=15, verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_teams(cfg: dict, transaction: dict) -> dict:
    webhook_url = cfg["config"]["webhook_url"]
    status = transaction.get("status")
    color = {"published": "33D685", "failed": "FF5470"}.get(status, "3D8BFD")
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"Nexus transaction {status}",
        "title": "Salesforce Nexus AI Server",
        "sections": [
            {
                "facts": [
                    {"name": "Transaction", "value": transaction.get("id", "")},
                    {"name": "Org", "value": transaction.get("org_name", "")},
                    {"name": "Channel", "value": transaction.get("channel", "")},
                    {"name": "Status", "value": status or ""},
                    {"name": "Error", "value": transaction.get("error") or "—"},
                ]
            }
        ],
    }
    resp = requests.post(webhook_url, json=card, timeout=15, verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_email(cfg: dict, transaction: dict) -> dict:
    import smtplib
    from email.mime.text import MIMEText
    from .routers.admin_config import get_email_settings_raw  # local import avoids a circular import at module load time

    settings = get_email_settings_raw()
    if not settings.get("host") or not settings.get("from_address"):
        raise RuntimeError("Email is not configured (set SMTP host and from-address in Admin Configuration -> Email)")

    to_addresses = cfg["config"].get("to") or []
    if isinstance(to_addresses, str):
        to_addresses = [a.strip() for a in to_addresses.split(",") if a.strip()]
    if not to_addresses:
        raise RuntimeError("This email integration has no recipient addresses configured")

    status = transaction.get("status")
    subject = cfg["config"].get("subject") or f"[Salesforce Nexus AI Server] {transaction.get('channel', 'event')} — {status}"

    body_lines = [
        f"Transaction: {transaction.get('id')}",
        f"Org: {transaction.get('org_name')}",
        f"Channel: {transaction.get('channel')}",
        f"Direction: {transaction.get('direction')}",
        f"Status: {status}",
    ]
    if transaction.get("error"):
        body_lines.append(f"Error: {transaction['error']}")
    body_lines.append("")
    body_lines.append(f"Payload: {json.dumps(transaction.get('payload'), default=str)}")

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = subject
    msg["From"] = settings["from_address"]
    msg["To"] = ", ".join(to_addresses)

    with smtplib.SMTP(settings["host"], settings.get("port", 587), timeout=15) as smtp:
        if settings.get("use_tls"):
            smtp.starttls()
        if settings.get("username"):
            smtp.login(settings["username"], settings.get("password", ""))
        smtp.sendmail(settings["from_address"], to_addresses, msg.as_string())

    return {"to": to_addresses, "subject": subject}


def _load_snowflake(cfg: dict, transaction: dict) -> dict:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError(
            "Snowflake sink is configured but 'snowflake-connector-python' isn't installed. "
            "Install it with: pip install snowflake-connector-python"
        ) from exc

    c = cfg["config"]
    conn = snowflake.connector.connect(
        account=c["account"], user=c["user"], password=c["password"],
        warehouse=c.get("warehouse"), database=c.get("database"), schema=c.get("schema"),
        insecure_mode=True,  # disable OCSP/cert verification, consistent with other integration sinks
    )
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {c['table']} (transaction_id, org_id, org_name, direction, channel, status, "
            "payload, result, error, created_at) "
            "SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, TO_TIMESTAMP(%s)",
            (
                transaction.get("id"), transaction.get("org_id"), transaction.get("org_name"),
                transaction.get("direction"), transaction.get("channel"), transaction.get("status"),
                json.dumps(transaction.get("payload") or {}), json.dumps(transaction.get("result") or {}),
                transaction.get("error"), transaction.get("created_at"),
            ),
        )
        conn.commit()
        return {"rows_inserted": cur.rowcount}
    finally:
        conn.close()


def _load_bigquery(cfg: dict, transaction: dict) -> dict:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "BigQuery sink is configured but 'google-cloud-bigquery' isn't installed. "
            "Install it with: pip install google-cloud-bigquery"
        ) from exc

    c = cfg["config"]
    client = bigquery.Client(project=c.get("project"))
    table_ref = f"{c['project']}.{c['dataset']}.{c['table']}"
    row = {
        "transaction_id": transaction.get("id"),
        "org_id": transaction.get("org_id"),
        "org_name": transaction.get("org_name"),
        "direction": transaction.get("direction"),
        "channel": transaction.get("channel"),
        "status": transaction.get("status"),
        "payload": json.dumps(transaction.get("payload") or {}),
        "result": json.dumps(transaction.get("result") or {}),
        "error": transaction.get("error"),
        "created_at": transaction.get("created_at"),
    }
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
    return {"rows_inserted": 1, "table": table_ref}


_SENDERS = {
    "webhook": _send_webhook,
    "custom_api": _send_custom_api,
    "slack": _send_slack,
    "teams": _send_teams,
    "email": _send_email,
    "snowflake": _load_snowflake,
    "bigquery": _load_bigquery,
}


def _matches_trigger(trigger: str, status: str) -> bool:
    if trigger == "always":
        return True
    if trigger == "on_success":
        return status == "published"
    if trigger == "on_failure":
        return status == "failed"
    return False


def dispatch_integrations(transaction: dict, only_ids: Optional[list] = None):
    """Fan a completed transaction out to every enabled, matching integration
    sink. Best-effort: exceptions are caught and logged per-sink so one
    broken integration never blocks another or affects the pipeline.

    If `only_ids` is provided (an explicit routing selection made on the
    source subscribe event config), dispatch is restricted to exactly those
    integration ids - each still respects its own `trigger` setting. When
    `only_ids` is None, falls back to the legacy behavior of matching every
    enabled integration by org scope + trigger.
    """
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

        with start_span(f"integration.{cfg['type']}", integration_id=cfg["id"], transaction_id=transaction.get("id")):
            try:
                result = sender(cfg, transaction)
                _record_result(cfg["id"], "ok", result=result)
                log_event(
                    "info", f"Integration '{cfg['name']}' ({cfg['type']}) dispatched",
                    transaction_id=transaction.get("id"), integration_id=cfg["id"], result=result,
                )
            except Exception as exc:  # noqa: BLE001
                _record_result(cfg["id"], "error", str(exc))
                log_event(
                    "error", f"Integration '{cfg['name']}' ({cfg['type']}) failed: {exc}",
                    transaction_id=transaction.get("id"), integration_id=cfg["id"],
                )
                from . import alerts as alerts_module  # local import avoids a circular import at module load time
                alerts_module.fire_alert("integration_failed", {
                    "integration_id": cfg["id"], "integration_name": cfg["name"], "integration_type": cfg["type"],
                    "transaction_id": transaction.get("id"), "error": str(exc),
                }, org_id=cfg.get("org_id"))
