from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional

from ..auth import require_role
from ..database import processors_table, Q
from ..models import ProcessorOut, ProcessorTestRequest, new_id, now_ts
from ..logging_config import log_event
from .. import processors as proc_module

router = APIRouter(prefix="/api/processors", tags=["processors"], dependencies=[Depends(require_role("admin"))])

MAX_UPLOAD_BYTES = 512 * 1024  # 512KB is plenty for a processing script


@router.get("", response_model=List[ProcessorOut])
def list_processors():
    return processors_table.all()


@router.get("/example")
def get_example_template():
    """Returns a starter script showing the required stdin/stdout contract,
    so the admin UI can offer a "download example" / pre-fill link."""
    return {"code": proc_module.EXAMPLE_TEMPLATE}


@router.get("/{processor_id}/code")
def get_processor_code(processor_id: str):
    if not processors_table.get(Q.id == processor_id):
        raise HTTPException(404, "Processor not found")
    return {"code": proc_module.read_processor_code(processor_id)}


@router.post("", response_model=ProcessorOut)
async def upload_processor(name: str = Form(...), file: UploadFile = File(...)):
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
    }
    processors_table.insert(record)
    log_event("info", f"Processor script '{name}' uploaded", processor_id=processor_id, filename=file.filename)
    return record


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
    except Exception as exc:  # noqa: BLE001
        processors_table.update({"last_status": "error", "last_run_at": now_ts(), "last_error": str(exc)}, Q.id == processor_id)
        raise HTTPException(400, f"Processor failed: {exc}")
