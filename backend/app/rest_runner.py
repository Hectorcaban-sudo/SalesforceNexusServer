"""Call a configured external REST endpoint and return its JSON body."""
import json
from typing import Optional

import httpx

from .logging_config import log_event
from .template_renderer import render_template


def run_rest(processor: dict, payload: dict, transaction_id: Optional[str] = None) -> dict:
    url = (processor.get("url") or "").strip()
    if not url:
        raise RuntimeError("REST processor has no URL")

    method = (processor.get("method") or "POST").upper()
    timeout = float(processor.get("timeout") or 60)
    headers = {"Content-Type": "application/json"}
    for row in processor.get("headers") or []:
        name = (row.get("name") or "").strip()
        if name:
            headers[name] = row.get("value") or ""

    rendered = render_template(processor.get("body_template") or "{{ payload | tojson }}", {"payload": payload or {}})
    try:
        body = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"REST body is not valid JSON: {exc}") from exc

    log_event("info", f"REST {method} {url}", logger_name="nexus.rest", transaction_id=transaction_id)
    verify = False if processor.get("verify_ssl") is False else True
    with httpx.Client(timeout=timeout, verify=verify, headers=headers) as client:
        resp = client.request(method, url, json=body)

    text = resp.text or ""
    try:
        data = resp.json()
    except json.JSONDecodeError:
        data = {"text": text}

    if resp.status_code >= 400:
        raise RuntimeError(f"REST {resp.status_code}: {text[:500]}")

    return {
        "status": "ok",
        "status_code": resp.status_code,
        "body": data,
        "steps": [{"name": "rest", "status": "ok", "detail": f"{method} {resp.status_code}"}],
    }
