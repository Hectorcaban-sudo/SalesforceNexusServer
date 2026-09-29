"""SharePoint Online (GCC High) connections and file/list action configs."""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

from ..auth import get_current_user, require_role
from ..database import (
    sharepoint_connections_table,
    sharepoint_file_actions_table,
    sharepoint_list_actions_table,
    Q,
)
from ..sharepoint_models import (
    SharePointConnectionCreate,
    SharePointConnectionUpdate,
    SharePointConnectionOut,
    SharePointFileActionCreate,
    SharePointFileActionUpdate,
    SharePointFileActionOut,
    SharePointListActionCreate,
    SharePointListActionUpdate,
    SharePointListActionOut,
)
from ..models import new_id
from ..logging_config import log_event

router = APIRouter(prefix="/api/sharepoint", tags=["sharepoint"], dependencies=[Depends(get_current_user)])


def _mask_conn(row: dict) -> dict:
    out = dict(row)
    if out.get("client_secret"):
        out["client_secret"] = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    return out


def _stamp_project(record: dict) -> dict:
    record["project_id"] = (record.get("project_id") or "").strip() or None
    return record


@router.post("/connections/test-credentials", dependencies=[Depends(require_role("admin"))])
def test_credentials(body: SharePointConnectionCreate):
    import requests
    from ..sharepoint import get_graph_token, GRAPH_ROOT, SharePointError
    conn = {
        "name": body.name or "test",
        "tenant_id": body.tenant_id,
        "client_id": body.client_id,
        "client_secret": body.client_secret,
        "enabled": True,
        "cloud": "gcchigh",
    }
    if not conn["client_secret"]:
        raise HTTPException(400, "client_secret is required to test")
    try:
        token = get_graph_token(conn)
    except SharePointError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Token request failed: {exc}")
    probe = {"token_ok": True, "message": "Access token acquired successfully (GCC High)."}
    try:
        r = requests.get(
            f"{GRAPH_ROOT}/organization",
            headers={"Authorization": f"Bearer {token}"},
            params={"$select": "id,displayName"},
            timeout=30,
        )
        if r.status_code < 400:
            orgs = (r.json() or {}).get("value") or []
            name = (orgs[0].get("displayName") if orgs else None) or "OK"
            probe["message"] = f"Token OK. Graph organization probe succeeded ({name})."
        elif r.status_code == 403:
            probe["message"] = (
                "Token OK, but /organization returned 403 (common). Credentials work; "
                "enter Site/Drive/List IDs manually if site search is also blocked."
            )
        else:
            probe["message"] = f"Token OK. Graph probe returned {r.status_code}."
    except Exception as exc:
        probe["message"] = f"Token OK. Probe skipped: {exc}"
    return probe


@router.get("/connections", response_model=List[SharePointConnectionOut])
def list_connections(project_id: Optional[str] = None):
    from ..project_scope import filter_by_project
    rows = filter_by_project(sharepoint_connections_table.all(), project_id, include_global=False)
    return [_mask_conn(r) for r in rows]


@router.post("/connections", response_model=SharePointConnectionOut, dependencies=[Depends(require_role("admin"))])
def create_connection(body: SharePointConnectionCreate):
    record = _stamp_project(body.model_dump())
    record["id"] = new_id()
    record["cloud"] = "gcchigh"
    sharepoint_connections_table.insert(record)
    log_event("info", f"SharePoint connection '{record['name']}' created")
    return _mask_conn(record)


@router.put("/connections/{connection_id}", response_model=SharePointConnectionOut, dependencies=[Depends(require_role("admin"))])
def update_connection(connection_id: str, updates: SharePointConnectionUpdate):
    existing = sharepoint_connections_table.get(Q.id == connection_id)
    if not existing:
        raise HTTPException(404, "Connection not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if data.get("client_secret") in (None, "", "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"):
        data.pop("client_secret", None)
    sharepoint_connections_table.update(data, Q.id == connection_id)
    log_event("info", f"SharePoint connection '{existing.get('name')}' updated")
    return _mask_conn(sharepoint_connections_table.get(Q.id == connection_id))


@router.delete("/connections/{connection_id}", dependencies=[Depends(require_role("admin"))])
def delete_connection(connection_id: str):
    existing = sharepoint_connections_table.get(Q.id == connection_id)
    if not existing:
        raise HTTPException(404, "Connection not found")
    used_file = sharepoint_file_actions_table.search(Q.connection_id == connection_id)
    used_list = sharepoint_list_actions_table.search(Q.connection_id == connection_id)
    if used_file or used_list:
        raise HTTPException(400, "Connection is used by one or more SharePoint actions; delete or reassign them first")
    sharepoint_connections_table.remove(Q.id == connection_id)
    log_event("warning", f"SharePoint connection '{existing.get('name')}' deleted")
    return {"detail": "deleted"}


@router.post("/connections/{connection_id}/test", dependencies=[Depends(require_role("admin"))])
def test_connection(connection_id: str):
    import requests
    from ..sharepoint import _get_connection, get_graph_token, GRAPH_ROOT, SharePointError
    try:
        conn = _get_connection(connection_id)
        token = get_graph_token(conn)
    except SharePointError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Token request failed: {exc}")
    probe = {"token_ok": True, "graph_probe": None, "message": "Access token acquired successfully (GCC High)."}
    try:
        r = requests.get(
            f"{GRAPH_ROOT}/organization",
            headers={"Authorization": f"Bearer {token}"},
            params={"$select": "id,displayName"},
            timeout=30,
        )
        if r.status_code < 400:
            orgs = (r.json() or {}).get("value") or []
            name = (orgs[0].get("displayName") if orgs else None) or "OK"
            probe["graph_probe"] = "organization"
            probe["message"] = f"Token OK. Graph organization probe succeeded ({name})."
        elif r.status_code == 403:
            probe["graph_probe"] = "organization_forbidden"
            probe["message"] = "Token OK, but /organization returned 403. Enter Site/Drive/List IDs manually if browse is blocked."
        else:
            probe["graph_probe"] = f"http_{r.status_code}"
            probe["message"] = f"Token OK. Graph probe returned {r.status_code}."
    except Exception as exc:
        probe["graph_probe"] = "error"
        probe["message"] = f"Token OK. Probe skipped: {exc}"
    return probe


@router.get("/file-actions", response_model=List[SharePointFileActionOut])
def list_file_actions(project_id: Optional[str] = None):
    from ..project_scope import filter_by_project
    return filter_by_project(sharepoint_file_actions_table.all(), project_id, include_global=False)


@router.post("/file-actions", response_model=SharePointFileActionOut, dependencies=[Depends(require_role("admin"))])
def create_file_action(body: SharePointFileActionCreate):
    if not sharepoint_connections_table.get(Q.id == body.connection_id):
        raise HTTPException(400, "connection_id not found")
    record = _stamp_project(body.model_dump())
    record["id"] = new_id()
    sharepoint_file_actions_table.insert(record)
    log_event("info", f"SharePoint file action '{record['name']}' created")
    return record


@router.put("/file-actions/{action_id}", response_model=SharePointFileActionOut, dependencies=[Depends(require_role("admin"))])
def update_file_action(action_id: str, updates: SharePointFileActionUpdate):
    existing = sharepoint_file_actions_table.get(Q.id == action_id)
    if not existing:
        raise HTTPException(404, "File action not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if "connection_id" in data and not sharepoint_connections_table.get(Q.id == data["connection_id"]):
        raise HTTPException(400, "connection_id not found")
    sharepoint_file_actions_table.update(data, Q.id == action_id)
    return sharepoint_file_actions_table.get(Q.id == action_id)


@router.delete("/file-actions/{action_id}", dependencies=[Depends(require_role("admin"))])
def delete_file_action(action_id: str):
    existing = sharepoint_file_actions_table.get(Q.id == action_id)
    if not existing:
        raise HTTPException(404, "File action not found")
    sharepoint_file_actions_table.remove(Q.id == action_id)
    return {"detail": "deleted"}


@router.get("/list-actions", response_model=List[SharePointListActionOut])
def list_list_actions(project_id: Optional[str] = None):
    from ..project_scope import filter_by_project
    return filter_by_project(sharepoint_list_actions_table.all(), project_id, include_global=False)


@router.post("/list-actions", response_model=SharePointListActionOut, dependencies=[Depends(require_role("admin"))])
def create_list_action(body: SharePointListActionCreate):
    if not sharepoint_connections_table.get(Q.id == body.connection_id):
        raise HTTPException(400, "connection_id not found")
    record = _stamp_project(body.model_dump())
    record["id"] = new_id()
    sharepoint_list_actions_table.insert(record)
    log_event("info", f"SharePoint list action '{record['name']}' created")
    return record


@router.put("/list-actions/{action_id}", response_model=SharePointListActionOut, dependencies=[Depends(require_role("admin"))])
def update_list_action(action_id: str, updates: SharePointListActionUpdate):
    existing = sharepoint_list_actions_table.get(Q.id == action_id)
    if not existing:
        raise HTTPException(404, "List action not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    sharepoint_list_actions_table.update(data, Q.id == action_id)
    return sharepoint_list_actions_table.get(Q.id == action_id)


@router.delete("/list-actions/{action_id}", dependencies=[Depends(require_role("admin"))])
def delete_list_action(action_id: str):
    existing = sharepoint_list_actions_table.get(Q.id == action_id)
    if not existing:
        raise HTTPException(404, "List action not found")
    sharepoint_list_actions_table.remove(Q.id == action_id)
    return {"detail": "deleted"}


def _conn_token(connection_id: str) -> str:
    from ..sharepoint import _get_connection, get_graph_token
    return get_graph_token(_get_connection(connection_id))


@router.get("/connections/{connection_id}/sites", dependencies=[Depends(require_role("admin"))])
def browse_sites(connection_id: str, q: str = "*"):
    import requests
    from ..sharepoint import GRAPH_ROOT
    try:
        token = _conn_token(connection_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    resp = requests.get(
        f"{GRAPH_ROOT}/sites",
        headers={"Authorization": f"Bearer {token}"},
        params={"search": q or "*", "$select": "id,name,displayName,webUrl,siteCollection"},
        timeout=45,
    )
    if resp.status_code >= 400:
        hint = " Enter Site ID manually if 403." if resp.status_code == 403 else ""
        raise HTTPException(400, f"Graph sites search failed ({resp.status_code}): {resp.text[:300]}.{hint}")
    return [{"id": s.get("id"), "name": s.get("displayName") or s.get("name") or s.get("id"), "web_url": s.get("webUrl")} for s in (resp.json().get("value") or [])]


@router.get("/connections/{connection_id}/sites/{site_id}/drives", dependencies=[Depends(require_role("admin"))])
def browse_drives(connection_id: str, site_id: str):
    import requests
    from ..sharepoint import GRAPH_ROOT
    try:
        token = _conn_token(connection_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    resp = requests.get(
        f"{GRAPH_ROOT}/sites/{site_id}/drives",
        headers={"Authorization": f"Bearer {token}"},
        params={"$select": "id,name,webUrl,driveType"},
        timeout=45,
    )
    if resp.status_code >= 400:
        raise HTTPException(400, f"Graph drives list failed ({resp.status_code}): {resp.text[:300]}")
    return [{"id": d.get("id"), "name": d.get("name") or d.get("id"), "web_url": d.get("webUrl"), "drive_type": d.get("driveType")} for d in (resp.json().get("value") or [])]


@router.get("/connections/{connection_id}/sites/{site_id}/lists", dependencies=[Depends(require_role("admin"))])
def browse_lists(connection_id: str, site_id: str):
    import requests
    from ..sharepoint import GRAPH_ROOT
    try:
        token = _conn_token(connection_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    resp = requests.get(
        f"{GRAPH_ROOT}/sites/{site_id}/lists",
        headers={"Authorization": f"Bearer {token}"},
        params={"$select": "id,name,displayName,webUrl,list"},
        timeout=45,
    )
    if resp.status_code >= 400:
        raise HTTPException(400, f"Graph lists failed ({resp.status_code}): {resp.text[:300]}")
    return [{"id": lst.get("id"), "name": lst.get("displayName") or lst.get("name") or lst.get("id"), "web_url": lst.get("webUrl"), "template": (lst.get("list") or {}).get("template")} for lst in (resp.json().get("value") or [])]


@router.get("/connections/{connection_id}/sites-by-path", dependencies=[Depends(require_role("admin"))])
def resolve_site_by_path(connection_id: str, hostname: str, path: str = ""):
    import requests
    from ..sharepoint import GRAPH_ROOT
    try:
        token = _conn_token(connection_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    rel = path.lstrip("/")
    url = f"{GRAPH_ROOT}/sites/{hostname}:/{rel}" if rel else f"{GRAPH_ROOT}/sites/{hostname}:/"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params={"$select": "id,name,displayName,webUrl"}, timeout=45)
    if resp.status_code >= 400:
        raise HTTPException(400, f"Site resolve failed ({resp.status_code}): {resp.text[:400]}")
    s = resp.json()
    return {"id": s.get("id"), "name": s.get("displayName") or s.get("name") or s.get("id"), "web_url": s.get("webUrl")}
