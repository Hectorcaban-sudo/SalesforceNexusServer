"""Outbound integration HTTP helpers."""
import hashlib
import hmac
import json
import time
from typing import Optional

import requests
import urllib3

from .database import integrations_table, Q
from .http_timeouts import requests_timeout
from .template_renderer import build_integration_body

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _record_result(integration_id: str, status: str, error: Optional[str] = None, result: Optional[dict] = None):
    integrations_table.update(
        {"last_status": status, "last_run_at": time.time(), "last_error": error, "last_result": result},
        Q.id == integration_id,
    )


def _response_summary(resp) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:2000]
    return {"status_code": resp.status_code, "body": body}


def _send_webhook(cfg: dict, transaction: dict) -> dict:
    url = cfg["config"]["url"]
    secret = cfg["config"].get("secret", "")
    custom = build_integration_body(cfg, transaction)
    body_obj = transaction if custom is None else custom
    body = json.dumps(body_obj, default=str) if not isinstance(body_obj, str) else body_obj
    headers = dict(cfg["config"].get("headers", {}))
    headers.setdefault("Content-Type", "application/json")
    if secret:
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Nexus-Signature"] = f"sha256={signature}"
    resp = requests.post(url, data=body, headers=headers, timeout=requests_timeout(), verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_custom_api(cfg: dict, transaction: dict) -> dict:
    c = cfg["config"]
    method = c.get("method", "POST").upper()
    headers = dict(c.get("headers", {}))
    if c.get("auth_header"):
        headers["Authorization"] = c["auth_header"]
    custom = build_integration_body(cfg, transaction)
    payload = transaction if custom is None else custom
    if isinstance(payload, str):
        headers.setdefault("Content-Type", "application/json")
        resp = requests.request(method, c["url"], data=payload, headers=headers, timeout=requests_timeout(), verify=False)
    else:
        resp = requests.request(method, c["url"], json=payload, headers=headers, timeout=requests_timeout(), verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_slack(cfg: dict, transaction: dict) -> dict:
    webhook_url = cfg["config"]["webhook_url"]
    custom = build_integration_body(cfg, transaction)
    if custom is not None:
        body = custom if isinstance(custom, dict) else {"text": str(custom)}
    else:
        status_emoji = {"published": "\u2705", "failed": "\u274c"}.get(transaction.get("status"), "\u2139\ufe0f")
        text = (
            f"{status_emoji} *Salesforce Nexus AI Server* \u2014 transaction `{transaction.get('id')}`\n"
            f"Org: *{transaction.get('org_name')}* \u00b7 Channel: `{transaction.get('channel')}` \u00b7 "
            f"Status: *{transaction.get('status')}*"
        )
        if transaction.get("error"):
            text += f"\nError: {transaction['error']}"
        body = {"text": text}
    resp = requests.post(webhook_url, json=body, timeout=requests_timeout(), verify=False)
    resp.raise_for_status()
    return _response_summary(resp)


def _send_teams(cfg: dict, transaction: dict) -> dict:
    webhook_url = cfg["config"]["webhook_url"]
    custom = build_integration_body(cfg, transaction)
    if custom is not None:
        card = custom if isinstance(custom, dict) else json.loads(custom)
    else:
        status = transaction.get("status")
        color = {"published": "33D685", "failed": "FF5470"}.get(status, "3D8BFD")
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"Nexus transaction {status}",
            "title": "Salesforce Nexus AI Server",
            "sections": [{"facts": [
                {"name": "Transaction", "value": transaction.get("id", "")},
                {"name": "Org", "value": transaction.get("org_name", "")},
                {"name": "Channel", "value": transaction.get("channel", "")},
                {"name": "Status", "value": status or ""},
                {"name": "Error", "value": transaction.get("error") or "\u2014"},
            ]}],
        }
    resp = requests.post(webhook_url, json=card, timeout=requests_timeout(), verify=False)
    resp.raise_for_status()
    return _response_summary(resp)
