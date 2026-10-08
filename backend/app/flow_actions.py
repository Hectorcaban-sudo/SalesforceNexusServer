"""Reusable flow actions. Not tied to one script.

A processor node with mode "flow_action" runs one saved action and returns
its result for the next node. Actions:
  salesforce_get     read one record
  salesforce_delete  delete one record
  sharepoint_file    run a saved SharePoint file action, optionally deleting
                     the destination file first and skipping names that do
                     not match a prefix
"""
import asyncio
from typing import Optional
from urllib.parse import quote

import requests

from .database import _db, orgs_table, sharepoint_file_actions_table, Q
from .logging_config import log_event
from .salesforce_client import sf_client
from .template_renderer import render_template

flow_actions_table = _db.table("flow_actions")


class FlowActionError(RuntimeError):
    pass


def _action(action_id: str) -> dict:
    row = flow_actions_table.get(Q.id == action_id)
    if not row:
        raise FlowActionError(f"Flow action not found: {action_id}")
    if row.get("enabled", True) is False:
        raise FlowActionError(f"Flow action '{row.get('name')}' is disabled")
    return row


def _render(template: str, payload: dict, previous: dict) -> str:
    return render_template(template or "", {"payload": payload or {}, "result": previous or {}})


async def _salesforce(action: dict, payload: dict, org_id: Optional[str]) -> dict:
    if not org_id:
        raise FlowActionError("Salesforce action requires the event org")
    org = orgs_table.get(Q.id == org_id)
    if not org:
        raise FlowActionError("Org not found")
    previous = payload.get("_previous") if isinstance(payload, dict) else {}
    object_name = _render(action.get("object_template") or "ContentDocument", payload, previous).strip()
    record_id = _render(action.get("id_template") or "{{ payload.ContentDocumentId }}", payload, previous).strip()
    if not object_name or not record_id:
        raise FlowActionError("Salesforce action object or id rendered empty")
    operation = (action.get("operation") or "get").lower()
    api = org.get("api_version", "60.0")
    if operation == "delete":
        resp = await sf_client._request(org, "DELETE", f"/services/data/v{api}/sobjects/{object_name}/{record_id}")
        if resp.status_code not in (200, 204):
            raise FlowActionError(f"Salesforce delete failed ({resp.status_code}): {resp.text[:300]}")
        log_event("info", f"Deleted {object_name}/{record_id}", org_id=org_id)
        return {
            "status": "ok",
            "summary": f"Deleted {object_name} {record_id}",
            "salesforce": {"operation": "delete", "object": object_name, "id": record_id},
            "steps": [{"name": "salesforce_delete", "status": "ok", "detail": record_id}],
            "previous": previous or None,
        }
    record = await sf_client.get_sobject(org, object_name, record_id)
    return {
        "status": "ok",
        "summary": f"Read {object_name} {record_id}",
        "record": record,
        "salesforce": {"operation": "get", "object": object_name, "id": record_id},
        "steps": [{"name": "salesforce_get", "status": "ok", "detail": record_id}],
    }


def _replace_existing(action: dict, payload: dict, org_id: Optional[str]) -> None:
    from .sharepoint import _get_connection, get_graph_token, _headers, GRAPH_ROOT, _render as sp_render, _jinja_ctx, SharePointError

    file_action = sharepoint_file_actions_table.get(Q.id == action.get("sharepoint_action_id"))
    if not file_action:
        raise FlowActionError("SharePoint file action not found")
    org = orgs_table.get(Q.id == org_id) if org_id else None
    ctx = _jinja_ctx(payload, org)
    conn = _get_connection(file_action["connection_id"])
    token = get_graph_token(conn)
    drive_id = file_action.get("drive_id") or ""
    folder = sp_render(file_action.get("folder_path_template") or "", ctx)
    name = sp_render(file_action.get("file_name_template") or "", ctx)
    if not drive_id or not name:
        return
    path = f"{folder.rstrip('/')}/{name}" if folder else name
    url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{quote(path.lstrip('/'))}"
    resp = requests.get(url, headers=_headers(token), timeout=30)
    if resp.status_code == 404:
        return
    if resp.status_code >= 400:
        raise SharePointError(f"SharePoint file lookup failed ({resp.status_code}): {resp.text[:300]}")
    deleted = requests.delete(url, headers=_headers(token), timeout=30)
    if deleted.status_code not in (200, 204):
        raise SharePointError(f"SharePoint delete failed ({deleted.status_code}): {deleted.text[:300]}")


def _sharepoint(action: dict, payload: dict, org_id: Optional[str]) -> dict:
    from .sharepoint import run_sharepoint_file

    prefix = (action.get("name_prefix") or "").strip()
    if action.get("replace_existing"):
        _replace_existing(action, payload, org_id)
    result = run_sharepoint_file(action.get("sharepoint_action_id"), payload, org_id)
    file_name = ((result.get("sharepoint") or {}).get("file_name") or "")
    if prefix and not file_name.startswith(prefix):
        return {
            "status": "skipped",
            "summary": f"File name does not start with {prefix}",
            "sharepoint": result.get("sharepoint"),
            "steps": [{"name": "name_prefix", "status": "skipped", "detail": file_name}],
        }
    steps = list(result.get("steps") or [])
    steps.append({"name": "sharepoint_file", "status": "ok", "detail": file_name})
    result["steps"] = steps
    return result


def run_flow_action(action_id: str, payload: dict, org_id: Optional[str] = None) -> dict:
    action = _action(action_id)
    kind = (action.get("type") or "").lower()
    if kind in ("salesforce_get", "salesforce_delete"):
        action = dict(action)
        action["operation"] = "delete" if kind == "salesforce_delete" else "get"
        return asyncio.run(_salesforce(action, payload, org_id))
    if kind == "sharepoint_file":
        return _sharepoint(action, payload, org_id)
    raise FlowActionError(f"Unknown flow action type '{kind}'")
