"""Email, warehouse, and SharePoint integration sinks."""
import json

from .template_renderer import build_integration_body


def _send_email(cfg: dict, transaction: dict) -> dict:
    import smtplib
    from email.mime.text import MIMEText
    from .routers.admin_config import get_email_settings_raw

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
    custom = build_integration_body(cfg, transaction)
    if custom is not None:
        if isinstance(custom, dict):
            subject = custom.get("subject", subject)
            body_text = custom.get("body", json.dumps(custom, default=str))
        else:
            body_text = str(custom)
    else:
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
        body_text = "\n".join(body_lines)
    msg = MIMEText(body_text)
    msg["Subject"] = subject
    msg["From"] = settings["from_address"]
    msg["To"] = ", ".join(to_addresses)
    with smtplib.SMTP(settings["host"], settings.get("port", 587), timeout=30) as smtp:
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
        raise RuntimeError("Snowflake sink is configured but 'snowflake-connector-python' isn't installed.") from exc
    c = cfg["config"]
    conn = snowflake.connector.connect(
        account=c["account"], user=c["user"], password=c["password"],
        warehouse=c.get("warehouse"), database=c.get("database"), schema=c.get("schema"),
        insecure_mode=True,
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
        raise RuntimeError("BigQuery sink is configured but 'google-cloud-bigquery' isn't installed.") from exc
    c = cfg["config"]
    client = bigquery.Client(project=c.get("project"))
    table_ref = f"{c['project']}.{c['dataset']}.{c['table']}"
    row = {
        "transaction_id": transaction.get("id"), "org_id": transaction.get("org_id"),
        "org_name": transaction.get("org_name"), "direction": transaction.get("direction"),
        "channel": transaction.get("channel"), "status": transaction.get("status"),
        "payload": json.dumps(transaction.get("payload") or {}),
        "result": json.dumps(transaction.get("result") or {}),
        "error": transaction.get("error"), "created_at": transaction.get("created_at"),
    }
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
    return {"rows_inserted": 1, "table": table_ref}


def _send_sharepoint_file(cfg: dict, transaction: dict) -> dict:
    from .sharepoint import run_sharepoint_file
    action_id = (cfg.get("config") or {}).get("action_id") or cfg.get("action_id")
    if not action_id:
        raise RuntimeError("SharePoint file integration is missing config.action_id")
    return run_sharepoint_file(action_id, transaction.get("payload") or transaction, transaction.get("org_id"))


def _send_sharepoint_list(cfg: dict, transaction: dict) -> dict:
    from .sharepoint import run_sharepoint_list
    action_id = (cfg.get("config") or {}).get("action_id") or cfg.get("action_id")
    if not action_id:
        raise RuntimeError("SharePoint list integration is missing config.action_id")
    return run_sharepoint_list(action_id, transaction.get("payload") or transaction, transaction.get("org_id"))
