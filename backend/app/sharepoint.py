"""
SharePoint Online (GCC High) processors.

Uses Microsoft Graph on graph.microsoft.us with app-only client credentials.
Connections and action configs are stored in the DB; Jinja2 templates map
event payload fields into paths, filenames, and column values.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Optional
from urllib.parse import quote

import requests

from .database import (
    sharepoint_connections_table,
    sharepoint_file_actions_table,
    sharepoint_list_actions_table,
    orgs_table,
    Q,
)
from .logging_config import log_event
from .template_renderer import render_template

GRAPH_ROOT = "https://graph.microsoft.us/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.us/{tenant}/oauth2/v2.0/token"
SCOPE = "https://graph.microsoft.us/.default"


class SharePointError(RuntimeError):
    pass


def _get_connection(connection_id: str) -> dict:
    conn = sharepoint_connections_table.get(Q.id == connection_id)
    if not conn:
        raise SharePointError(f"SharePoint connection '{connection_id}' not found")
    if not conn.get("enabled", True):
        raise SharePointError(f"SharePoint connection '{conn.get('name')}' is disabled")
    if not conn.get("client_secret"):
        raise SharePointError(f"SharePoint connection '{conn.get('name')}' has no client_secret configured")
    return conn


def get_graph_token(conn: dict) -> str:
    token_url = TOKEN_URL_TMPL.format(tenant=conn["tenant_id"])
    data = {
        "client_id": conn["client_id"],
        "scope": SCOPE,
        "client_secret": conn["client_secret"],
        "grant_type": "client_credentials",
    }
    resp = requests.post(token_url, data=data, timeout=30)
    if resp.status_code >= 400:
        raise SharePointError(f"Graph token request failed ({resp.status_code}): {resp.text[:500]}")
    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise SharePointError(f"Graph token response missing access_token: {body}")
    return token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _jinja_ctx(payload: dict, org: Optional[dict] = None, extra: Optional[dict] = None) -> dict:
    now = datetime.utcnow()
    ctx = {
        "payload": payload or {},
        "org": org or {},
        "year": now.year,
        "month": f"{now.month:02d}",
        "day": f"{now.day:02d}",
        "now": now.isoformat() + "Z",
        "title": "",
        "extension": "",
        "business": "",
    }
    if extra:
        ctx.update(extra)
    return ctx


def _render(template: str, ctx: dict) -> str:
    if not template:
        return ""
    return render_template(template, ctx).strip()


def _render_map(mapping: dict, ctx: dict) -> dict:
    out = {}
    for key, expr in (mapping or {}).items():
        if key is None or key == "":
            continue
        try:
            out[str(key)] = _render(str(expr), ctx)
        except Exception as exc:  # noqa: BLE001
            raise SharePointError(f"Failed to render metadata/field '{key}': {exc}") from exc
    return out


def _salesforce_client(org: dict):
    from simple_salesforce import Salesforce
    from urllib.parse import urlparse

    login_url = org.get("login_url") or ""
    host = urlparse(login_url).hostname or login_url
    parts = host.replace("https://", "").split(".")
    # baesystemsins--uat.sandbox.my.salesforce.com -> baesystemsins--uat.sandbox.my
    if parts[-2:] == ["salesforce", "com"] or (len(parts) >= 2 and parts[-1] == "com"):
        domain = ".".join(parts[:-2]) if parts[-2] == "salesforce" else ".".join(parts[:-1])
    else:
        domain = host.replace(".salesforce.com", "").replace("https://", "")
    return Salesforce(
        consumer_key=org.get("client_id"),
        consumer_secret=org.get("client_secret"),
        domain=domain,
    )


def _download_salesforce_content(org: dict, content_document_id: str) -> tuple[bytes, str, str]:
    """Return (file_bytes, title, extension)."""
    sf = _salesforce_client(org)
    q = (
        "SELECT Id, Title, FileExtension, VersionData "
        f"FROM ContentVersion WHERE ContentDocumentId = '{content_document_id}' "
        "ORDER BY VersionNumber DESC LIMIT 1"
    )
    result = sf.query(q)
    records = result.get("records") or []
    if not records:
        raise SharePointError(f"No ContentVersion found for ContentDocumentId={content_document_id}")
    cv = records[0]
    version_id = cv["Id"]
    title = cv.get("Title") or version_id
    extension = (cv.get("FileExtension") or "").lstrip(".")
    download_url = f"{sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
    file_resp = requests.get(
        download_url,
        headers={"Authorization": f"Bearer {sf.session_id}"},
        timeout=120,
    )
    if file_resp.status_code >= 400:
        raise SharePointError(f"Salesforce file download failed ({file_resp.status_code})")
    return file_resp.content, title, extension


def _download_url(url: str) -> bytes:
    resp = requests.get(url, timeout=120)
    if resp.status_code >= 400:
        raise SharePointError(f"File URL download failed ({resp.status_code}): {url[:200]}")
    return resp.content


def _ensure_folder_path(token: str, drive_id: str, folder_path: str) -> None:
    """Create nested folders under drive root if missing (best-effort)."""
    if not folder_path:
        return
    parts = [p for p in folder_path.replace("\\", "/").split("/") if p]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        # Try to get the folder; if 404, create it under parent
        encoded = quote(current)
        get_url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{encoded}"
        r = requests.get(get_url, headers=_headers(token), timeout=30)
        if r.status_code == 200:
            continue
        parent = "/".join(current.split("/")[:-1])
        create_url = (
            f"{GRAPH_ROOT}/drives/{drive_id}/root/children"
            if not parent
            else f"{GRAPH_ROOT}/drives/{drive_id}/root:/{quote(parent)}:/children"
        )
        body = {
            "name": part,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }
        cr = requests.post(create_url, headers={**_headers(token), "Content-Type": "application/json"}, json=body, timeout=30)
        # 409 = already exists (race); anything else non-2xx is an error
        if cr.status_code not in (200, 201, 409):
            # conflictBehavior fail may 409; also accept nameAlreadyExists
            if cr.status_code == 409:
                continue
            raise SharePointError(f"Failed to create folder '{part}' ({cr.status_code}): {cr.text[:300]}")


def _upload_file(token: str, drive_id: str, folder_path: str, file_name: str, content: bytes) -> dict:
    path = f"{folder_path.rstrip('/')}/{file_name}" if folder_path else file_name
    path = path.lstrip("/")
    encoded = quote(path)
    url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{encoded}:/content"
    resp = requests.put(url, headers=_headers(token), data=content, timeout=180)
    if resp.status_code >= 400:
        raise SharePointError(f"SharePoint upload failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def _patch_list_item_fields(token: str, site_id: str, list_id: str, item_id: str, fields: dict) -> dict:
    url = f"{GRAPH_ROOT}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields"
    resp = requests.patch(
        url,
        headers={**_headers(token), "Content-Type": "application/json"},
        json=fields,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise SharePointError(f"SharePoint list field update failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json() if resp.text else {}


def _set_drive_item_list_fields(token: str, drive_id: str, item_id: str, fields: dict) -> None:
    """Update library columns associated with a drive item (listItem fields)."""
    if not fields:
        return
    # Resolve listItem id for the drive item
    meta_url = f"{GRAPH_ROOT}/drives/{drive_id}/items/{item_id}/listItem"
    meta = requests.get(meta_url, headers=_headers(token), timeout=30)
    if meta.status_code >= 400:
        raise SharePointError(f"Could not resolve listItem for drive item ({meta.status_code}): {meta.text[:300]}")
    list_item = meta.json()
    list_item_id = list_item.get("id")
    parent = list_item.get("parentReference") or {}
    site_id = parent.get("siteId")
    # Prefer fields endpoint on the listItem
    fields_url = f"{GRAPH_ROOT}/drives/{drive_id}/items/{item_id}/listItem/fields"
    resp = requests.patch(
        fields_url,
        headers={**_headers(token), "Content-Type": "application/json"},
        json=fields,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise SharePointError(f"SharePoint file metadata update failed ({resp.status_code}): {resp.text[:500]}")


def _checkin(token: str, drive_id: str, item_id: str, comment: str = "Checked in via Nexus") -> None:
    url = f"{GRAPH_ROOT}/drives/{drive_id}/items/{item_id}/checkin"
    resp = requests.post(
        url,
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"comment": comment},
        timeout=30,
    )
    # Some libraries don't require check-in; ignore 400 bad request for not checked out
    if resp.status_code >= 400 and resp.status_code != 400:
        raise SharePointError(f"SharePoint check-in failed ({resp.status_code}): {resp.text[:300]}")


def run_sharepoint_file(action_id: str, payload: dict, org_id: Optional[str] = None) -> dict:
    action = sharepoint_file_actions_table.get(Q.id == action_id)
    if not action:
        raise SharePointError(f"SharePoint file action '{action_id}' not found")
    if not action.get("enabled", True):
        raise SharePointError(f"SharePoint file action '{action.get('name')}' is disabled")

    conn = _get_connection(action["connection_id"])
    org = orgs_table.get(Q.id == org_id) if org_id else None
    ctx = _jinja_ctx(payload, org)

    # Optional SF enrichment for business area etc.
    record_id = _render(action.get("salesforce_record_id_template") or "", ctx)
    sf_object = (action.get("salesforce_object") or "").strip()
    if org and record_id and sf_object:
        try:
            sf = _salesforce_client(org)
            getter = getattr(sf, sf_object, None)
            if getter is not None:
                rec = getter.get(record_id)
                ctx["sf_record"] = rec
                ctx["business"] = rec.get("Business_Area__c") or ctx.get("business") or ""
        except Exception as exc:  # noqa: BLE001
            log_event("warning", f"SharePoint SF enrichment failed: {exc}")

    token = get_graph_token(conn)
    site_id = action.get("site_id") or ""
    drive_id = action.get("drive_id") or ""
    if not drive_id:
        raise SharePointError("SharePoint file action is missing drive_id")

    # Resolve file bytes
    file_source = action.get("file_source") or "salesforce_content_version"
    title, extension = "", ""
    if file_source == "url":
        url = _render(action.get("file_url_template") or "", ctx)
        if not url:
            raise SharePointError("file_url_template rendered empty")
        content = _download_url(url)
        # best-effort name from URL
        title = url.rstrip("/").split("/")[-1]
        if "." in title:
            extension = title.rsplit(".", 1)[-1]
            title = title[: -(len(extension) + 1)]
    else:
        if not org:
            raise SharePointError("salesforce_content_version source requires an org context")
        doc_id = _render(action.get("content_document_id_template") or "{{ payload.ContentDocumentId }}", ctx)
        if not doc_id:
            raise SharePointError("content_document_id_template rendered empty")
        content, title, extension = _download_salesforce_content(org, doc_id)

    ctx["title"] = title
    ctx["extension"] = extension

    folder_path = _render(action.get("folder_path_template") or "", ctx)
    file_name = _render(action.get("file_name_template") or "{{ title }}.{{ extension }}", ctx)
    if not file_name:
        raise SharePointError("file_name_template rendered empty")

    if action.get("create_missing_folders", True) and folder_path:
        _ensure_folder_path(token, drive_id, folder_path)

    uploaded = _upload_file(token, drive_id, folder_path, file_name, content)
    item_id = uploaded.get("id")
    web_url = uploaded.get("webUrl")

    metadata = _render_map(action.get("metadata_map") or {}, ctx)
    if metadata and item_id:
        _set_drive_item_list_fields(token, drive_id, item_id, metadata)

    if action.get("check_in_after_upload", True) and item_id:
        _checkin(token, drive_id, item_id)

    log_event(
        "info",
        f"SharePoint file uploaded: {file_name}",
        action_id=action_id,
        drive_id=drive_id,
        item_id=item_id,
    )
    return {
        "status": "ok",
        "summary": f"Uploaded '{file_name}' to SharePoint",
        "sharepoint": {
            "item_id": item_id,
            "web_url": web_url,
            "drive_id": drive_id,
            "folder_path": folder_path,
            "file_name": file_name,
            "metadata": metadata,
        },
    }


def run_sharepoint_list(action_id: str, payload: dict, org_id: Optional[str] = None) -> dict:
    action = sharepoint_list_actions_table.get(Q.id == action_id)
    if not action:
        raise SharePointError(f"SharePoint list action '{action_id}' not found")
    if not action.get("enabled", True):
        raise SharePointError(f"SharePoint list action '{action.get('name')}' is disabled")

    conn = _get_connection(action["connection_id"])
    org = orgs_table.get(Q.id == org_id) if org_id else None
    ctx = _jinja_ctx(payload, org)
    token = get_graph_token(conn)

    site_id = action.get("site_id") or ""
    list_id = action.get("list_id") or ""
    if not site_id or not list_id:
        raise SharePointError("SharePoint list action requires site_id and list_id")

    fields = _render_map(action.get("field_map") or {}, ctx)
    operation = action.get("operation") or "create"

    if operation == "update":
        item_id = _render(action.get("item_id_template") or "", ctx)
        if not item_id:
            raise SharePointError("item_id_template rendered empty for list update")
        result_fields = _patch_list_item_fields(token, site_id, list_id, item_id, fields)
        return {
            "status": "ok",
            "summary": f"Updated SharePoint list item {item_id}",
            "sharepoint": {"list_id": list_id, "item_id": item_id, "fields": fields, "operation": "update"},
        }

    # create
    url = f"{GRAPH_ROOT}/sites/{site_id}/lists/{list_id}/items"
    body = {"fields": fields}
    resp = requests.post(
        url,
        headers={**_headers(token), "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise SharePointError(f"SharePoint list create failed ({resp.status_code}): {resp.text[:500]}")
    created = resp.json()
    return {
        "status": "ok",
        "summary": f"Created SharePoint list item {created.get('id')}",
        "sharepoint": {
            "list_id": list_id,
            "item_id": created.get("id"),
            "fields": fields,
            "operation": "create",
        },
    }
