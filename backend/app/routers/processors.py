from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import Response
from typing import List, Optional

from ..auth import require_role
from ..database import processors_table, Q
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
    existing = processors_table.get(Q.id == processor_id)
    if not existing:
        raise HTTPException(404, "Processor not found")
    code = body.get("code") or ""
    if len(code.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024}KB)")
    err = proc_module.validate_syntax(code)
    if err:
        raise HTTPException(400, f"Not valid Python: {err}")
    proc_module.save_processor_file(processor_id, code)
    processors_table.update(
        {"last_status": None, "last_run_at": None, "last_error": None},
        Q.id == processor_id,
    )
    log_event("info", f"Processor '{existing.get('name')}' code saved", processor_id=processor_id)
    return {"ok": True, "id": processor_id}


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


@router.post("")
async def upload_processor(name: str = Form(...), file: UploadFile = File(...), project_id: Optional[str] = Form(None)):
    if not file.filename.endswith(".py"):
        raise HTTPException(400, "Only .py files are accepted")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024}KB)")
    code = contents.decode("utf-8", errors="replace")
    syntax_error = proc_module.validate_syntax(code)
    if syntax_error:
        raise HTTPException(400, f"Uploaded file is not valid Python: {syntax_error}")
    processor_id = new_id()
    proc_module.save_processor_file(processor_id, code)
    record = {
        "id": processor_id,
        "name": name,
        "filename": file.filename,
        "uploaded_at": now_ts(),
        "last_status": None,
        "last_run_at": None,
        "last_error": None,
        "project_id": project_id,
    }
    processors_table.insert(record)
    log_event("info", f"Processor script '{name}' uploaded", processor_id=processor_id, filename=file.filename)
    return record


@router.post("/{processor_id}/upload")
async def override_processor(processor_id: str, name: Optional[str] = Form(None), file: UploadFile = File(...)):
    existing = processors_table.get(Q.id == processor_id)
    if not existing:
        raise HTTPException(404, "Processor not found")
    if not file.filename.endswith(".py"):
        raise HTTPException(400, "Only .py files are accepted")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // 1024}KB)")
    code = contents.decode("utf-8", errors="replace")
    syntax_error = proc_module.validate_syntax(code)
    if syntax_error:
        raise HTTPException(400, f"Uploaded file is not valid Python: {syntax_error}")
    proc_module.save_processor_file(processor_id, code)
    updates = {"filename": file.filename, "last_status": None, "last_run_at": None, "last_error": None}
    if name:
        updates["name"] = name
    processors_table.update(updates, Q.id == processor_id)
    log_event("info", f"Processor script '{existing['name']}' overridden", processor_id=processor_id)
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
