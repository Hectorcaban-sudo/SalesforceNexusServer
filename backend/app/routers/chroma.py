"""Admin-managed Chroma query processors, shared CA certs, and embedding models."""
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..auth import require_role
from ..config import DATA_DIR
from ..database import admin_settings_table, Q
from ..logging_config import log_event

router = APIRouter(prefix="/api/chroma", tags=["chroma"], dependencies=[Depends(require_role("admin"))])

CERTS_ID = "chroma_certs"
MODELS_ID = "embedding_models"
PROCESSORS_ID = "chroma_processors"
CERT_DIR = DATA_DIR / "certs"
CERT_DIR.mkdir(exist_ok=True)

DEFAULT_MODELS = [
    {"id": "nemotron-8b", "name": "Nemotron Embed 8B", "url_slug": "bae-nemotron-embed-8b", "model_id": "/genai/Nemotron-3-Embed-8B-BF16", "max_tokens": 3276},
    {"id": "snowflake-large", "name": "Snowflake Embedding Large", "url_slug": "bae-api-snowflake", "model_id": "/genai/snowflake-arctic-embed-l-v2.0", "max_tokens": 8192},
    {"id": "e5-mistral-7b", "name": "E5 Embed Model 7B", "url_slug": "bae-api-e5-mistral7b", "model_id": "/genai/e5-mistral-7b", "max_tokens": 4096},
    {"id": "gemma-300m", "name": "EmbeddingGemma 300M", "url_slug": "bae-api-gemma300m", "model_id": "/genai/embeddinggemma-300m", "max_tokens": 2048},
    {"id": "minilm-l6", "name": "All MiniLM L6 V2", "url_slug": "bae-api-all-MiniLM-L6-v2", "model_id": "/genai/all-MiniLM-L6-v2", "max_tokens": 256},
]


def _load(key, default):
    row = admin_settings_table.get(Q.id == key) or {}
    items = row.get("items")
    return items if isinstance(items, list) else default


def _save(key, items):
    existing = admin_settings_table.get(Q.id == key)
    record = {"id": key, "items": items}
    if existing:
        admin_settings_table.update(record, Q.id == key)
    else:
        admin_settings_table.insert(record)


def _new_id():
    return uuid.uuid4().hex[:12]


class EmbeddingModelIn(BaseModel):
    name: str
    url_slug: str
    model_id: str = ""
    max_tokens: int = 2048


class ChromaProcessorIn(BaseModel):
    name: str
    project_id: Optional[str] = None
    host: str = "localhost"
    port: int = 8000
    ssl: bool = False
    chroma_header: str = "Authorization"
    chroma_token: str = ""
    collection: str
    cert_id: Optional[str] = None
    embedding_model_id: Optional[str] = None
    embed_base_url: str = "https://devmissionassist.api.us.baesystems.com/{url}/v1"
    embed_header_name: str = "apikey"
    embed_api_key: str = ""
    query_template: str = "{{ payload.User_Message__c or payload.Description or payload }}"
    n_results: int = 5
    enabled: bool = True


class ChromaTestIn(BaseModel):
    payload: dict = Field(default_factory=dict)


def _mask_processor(row):
    out = dict(row)
    if out.get("embed_api_key"):
        out["embed_api_key"] = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    if out.get("chroma_token"):
        out["chroma_token"] = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    out["scope"] = "global" if not out.get("project_id") else "project"
    return out


@router.get("/certs")
def list_certs():
    return _load(CERTS_ID, [])


@router.post("/certs")
def upload_cert(name: str = "company-ca", file: UploadFile = File(...)):
    raw = file.file.read()
    if b"BEGIN CERTIFICATE" not in raw and b"BEGIN" not in raw:
        raise HTTPException(400, "Upload a PEM certificate or CA bundle")
    cert_id = _new_id()
    path = CERT_DIR / f"{cert_id}.pem"
    path.write_bytes(raw)
    items = _load(CERTS_ID, [])
    items.append({"id": cert_id, "name": name, "filename": file.filename or "ca.pem"})
    _save(CERTS_ID, items)
    log_event("info", f"Chroma CA cert stored: {name}")
    return items[-1]


@router.delete("/certs/{cert_id}")
def delete_cert(cert_id: str):
    items = [c for c in _load(CERTS_ID, []) if c.get("id") != cert_id]
    _save(CERTS_ID, items)
    path = CERT_DIR / f"{cert_id}.pem"
    if path.exists():
        path.unlink()
    return {"detail": "deleted"}


@router.get("/models")
def list_models():
    items = _load(MODELS_ID, None)
    if items is None:
        _save(MODELS_ID, DEFAULT_MODELS)
        items = DEFAULT_MODELS
    return items


@router.post("/models")
def create_model(body: EmbeddingModelIn):
    items = list_models()
    row = body.model_dump()
    row["id"] = _new_id()
    items.append(row)
    _save(MODELS_ID, items)
    return row


@router.put("/models/{model_id}")
def update_model(model_id: str, body: EmbeddingModelIn):
    items = list_models()
    found = False
    for row in items:
        if row.get("id") == model_id:
            row.update(body.model_dump())
            found = True
    if not found:
        raise HTTPException(404, "model not found")
    _save(MODELS_ID, items)
    return next(r for r in items if r.get("id") == model_id)


@router.delete("/models/{model_id}")
def delete_model(model_id: str):
    items = [m for m in list_models() if m.get("id") != model_id]
    _save(MODELS_ID, items)
    return {"detail": "deleted"}


@router.get("/processors")
def list_processors(project_id: Optional[str] = None):
    rows = _load(PROCESSORS_ID, [])
    if project_id:
        rows = [r for r in rows if r.get("project_id") in (None, "", project_id)]
    return [_mask_processor(r) for r in rows]


@router.post("/processors")
def create_processor(body: ChromaProcessorIn):
    items = _load(PROCESSORS_ID, [])
    row = body.model_dump()
    row["id"] = _new_id()
    items.append(row)
    _save(PROCESSORS_ID, items)
    log_event("info", f"Chroma processor created: {row['name']}", project_id=row.get("project_id"))
    return _mask_processor(row)


@router.put("/processors/{processor_id}")
def update_processor(processor_id: str, body: ChromaProcessorIn):
    items = _load(PROCESSORS_ID, [])
    found = None
    for row in items:
        if row.get("id") == processor_id:
            incoming = body.model_dump()
            if not incoming.get("embed_api_key"):
                incoming["embed_api_key"] = row.get("embed_api_key") or ""
            if not incoming.get("chroma_token"):
                incoming["chroma_token"] = row.get("chroma_token") or ""
            row.update(incoming)
            found = row
    if not found:
        raise HTTPException(404, "processor not found")
    _save(PROCESSORS_ID, items)
    return _mask_processor(found)


@router.delete("/processors/{processor_id}")
def delete_processor(processor_id: str):
    items = [r for r in _load(PROCESSORS_ID, []) if r.get("id") != processor_id]
    _save(PROCESSORS_ID, items)
    return {"detail": "deleted"}


def _resolve(processor_id: str):
    row = next((r for r in _load(PROCESSORS_ID, []) if r.get("id") == processor_id), None)
    if not row:
        raise HTTPException(404, "processor not found")
    model = next((m for m in list_models() if m.get("id") == row.get("embedding_model_id")), None)
    cert_path = None
    if row.get("cert_id"):
        path = CERT_DIR / f"{row['cert_id']}.pem"
        if not path.exists():
            raise HTTPException(400, "Selected CA cert file is missing. Upload it again.")
        cert_path = str(path)
    return row, model, cert_path


@router.post("/processors/{processor_id}/test")
def test_processor(processor_id: str, body: ChromaTestIn):
    from ..chroma_runner import run_chroma_query
    row, model, cert_path = _resolve(processor_id)
    try:
        return run_chroma_query(row, body.payload or {}, cert_path=cert_path, model=model)
    except Exception as exc:
        raise HTTPException(400, str(exc))
