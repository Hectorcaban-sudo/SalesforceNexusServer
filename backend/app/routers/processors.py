from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import Response
from typing import Optional
import json

from ..auth import require_role
from ..database import processors_table, event_pipelines_table, event_configs_table, Q
from ..models import ProcessorOut, ProcessorTestRequest, new_id, now_ts
from ..logging_config import log_event
from .. import processors as proc_module

router = APIRouter(prefix="/api/processors", tags=["processors"], dependencies=[Depends(require_role("admin"))])

MAX_UPLOAD_BYTES = 512 * 1024


@router.get("")
def list_processors(project_id: Optional[str] = None, include_global: bool = True):
    from ..project_scope import filter_by_project
    return filter_by_project(processors_table.all(), project_id, include_global=include_global)


@router.get("/example")
def get_example_template():
    return {"code": proc_module.EXAMPLE_TEMPLATE}


@router.get("/example.py")
def download_example():
    return Response(
        content=proc_module.EXAMPLE_TEMPLATE,
        media_type="text/x-python",
        headers={"Content-Disposition": 'attachment; filename="nexus_processor_sample.py"'},
    )


def _ids_in_pipeline(row: dict):
    found = set()
    if row.get("processor_id"):
        found.add(row["processor_id"])
    graph = row.get("flow_graph") or {}
    if isinstance(graph, str):
        try:
            graph = json.loads(graph)
        except Exception:
            graph = {}
    for node in graph.get("nodes") or []:
        data = node.get("data") or {}
        for key in ("processor_id", "processorId", "processor"):
            val = data.get(key)
            if isinstance(val, str) and val:
                found.add(val)
    return found


@router.get("/usage")
def processor_usage():
    events = {e["id"]: e for e in event_configs_table.all()}
    out = {}
    for row in event_pipelines_table.all():
        ev = events.get(row.get("event_id")) or {}
        hit = {
            "pipeline_id": row.get("id"),
            "name": row.get("name") or "Pipeline",
            "event_id": row.get("event_id"),
            "event_name": ev.get("name") or ev.get("channel") or "",
        }
        for pid in _ids_in_pipeline(row):
            out.setdefault(pid, []).append(hit)
    return out


@router.get("/{processor_id}/code")
def get_processor_code(processor_id: str):
    if not processors_table.get(Q.id == processor_id):
        raise HTTPException(404, "Processor not found")
    return {"code": proc_module.read_processor_code(processor_id)}


@router.post("/validate")
def validate_processor_code(body: dict = Body(...)):
    code = body.get("code") or ""
    err = proc_module.validate_syntax(code)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "error": None}


@router.put("/{processor_id}/code")
def save_processor_code(processor_id: str, body: dict = Body(...)):
    raise HTTPException(405, "Inline edits are disabled. Upload a .py to replace this processor.")


@router.get("/{processor_id}/download")
def download_processor(processor_id: str):
    record = processors_table.get(Q.id == processor_id)
    if not record:
        raise HTTPException(404, "Processor not found")
    code = proc_module.read_processor_code(processor_id)
    filename = record.get("filename") or f"{record['name']}.py"
    return Response(
        content=code,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=ProcessorOut)
async def upload_processor(name: str = Form(...), file: UploadFile = File(...), project_id: Optional[str] = Form(None)):
    filename = (file.filename or "").strip() or f"{name}.py"
    if not filename.lower().endswith(".py"):
        raise HTTPException(400, "Only .py files are accepted")
    try:
        contents = await file.read()
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded file: {exc}") from exc
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024}KB)")
    code = contents.decode("utf-8", errors="replace")
    if not code.strip():
        raise HTTPException(400, "Uploaded file is empty")
    syntax_error = proc_module.validate_syntax(code)
    if syntax_error:
        raise HTTPException(400, f"Uploaded file is not valid Python: {syntax_error}")
    processor_id = new_id()
    try:
        proc_module.save_processor_file(processor_id, code)
        record = {
            "id": processor_id,
            "name": name,
            "filename": filename,
            "uploaded_at": now_ts(),
            "last_status": None,
            "last_run_at": None,
            "last_error": None,
            "project_id": (project_id or "").strip() or None,
        }
        processors_table.insert(record)
    except Exception as exc:
        raise HTTPException(500, f"Failed to store processor: {exc}") from exc
    log_event("info", f"Processor script '{name}' uploaded", processor_id=processor_id, filename=filename)
    return record


@router.post("/{processor_id}/upload", response_model=ProcessorOut)
async def override_processor(processor_id: str, name: Optional[str] = Form(None), file: UploadFile = File(...)):
    existing = processors_table.get(Q.id == processor_id)
    if not existing:
        raise HTTPException(404, "Processor not found")
    filename = (file.filename or "").strip() or f"{existing.get('name') or 'processor'}.py"
    if not filename.lower().endswith(".py"):
        raise HTTPException(400, "Only .py files are accepted")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024}KB)")
    code = contents.decode("utf-8", errors="replace")
    if not code.strip():
        raise HTTPException(400, "Uploaded file is empty")
    syntax_error = proc_module.validate_syntax(code)
    if syntax_error:
        raise HTTPException(400, f"Uploaded file is not valid Python: {syntax_error}")
    proc_module.save_processor_file(processor_id, code)
    updates = {"filename": filename, "last_status": None, "last_run_at": None, "last_error": None}
    if name:
        updates["name"] = name
    processors_table.update(updates, Q.id == processor_id)
    log_event("info", f"Processor script '{existing['name']}' replaced by upload", processor_id=processor_id)
    return processors_table.get(Q.id == processor_id)


@router.delete("/{processor_id}")
def delete_processor(processor_id: str):
    existing = processors_table.get(Q.id == processor_id)
    if not existing:
        raise HTTPException(404, "Processor not found")
    proc_module.delete_processor_file(processor_id)
    processors_table.remove(Q.id == processor_id)
    log_event("warning", f"Processor script '{existing['name']}' deleted", processor_id=processor_id)
    return {"detail": "deleted"}


@router.post("/{processor_id}/test")
def test_processor(processor_id: str, req: ProcessorTestRequest):
    existing = processors_table.get(Q.id == processor_id)
    if not existing:
        raise HTTPException(404, "Processor not found")
    try:
        result = proc_module.run_processor(processor_id, req.payload, req.org_id)
        processors_table.update({"last_status": "ok", "last_run_at": now_ts(), "last_error": None}, Q.id == processor_id)
        return {"detail": "Processor ran successfully", "result": result}
    except Exception as exc:
        processors_table.update({"last_status": "error", "last_run_at": now_ts(), "last_error": str(exc)}, Q.id == processor_id)
        raise HTTPException(400, f"Processor failed: {exc}")
