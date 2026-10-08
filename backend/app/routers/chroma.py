"""Admin-managed Chroma query processors, shared CA certs, and embedding models."""
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import require_role
from ..config import DATA_DIR
from ..database import admin_settings_table, Q
from ..logging_config import log_event

router = APIRouter(prefix="/api/chroma", tags=["chroma"], dependencies=[Depends(require_role("admin"))])
CERTS_ID, MODELS_ID, PROCESSORS_ID = "chroma_certs", "embedding_models", "chroma_processors"
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
    payload: dict = {}

class ChromaQueryIn(BaseModel):
    processor_id: str
    text: str
    n_results: int = 5

def _mask(row):
    out = dict(row)
    if out.get("embed_api_key"):
        out["embed_api_key"] = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    if out.get("chroma_token"):
        out["chroma_token"] = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    out["scope"] = "global" if not out.get("project_id") else "project"
    return out

def _resolve(processor_id: str):
    row = next((r for r in _load(PROCESSORS_ID, []) if r.get("id") == processor_id), None)
    if not row:
        raise HTTPException(404, "processor not found")
    models = _load(MODELS_ID, None) or DEFAULT_MODELS
    model = next((m for m in models if m.get("id") == row.get("embedding_model_id")), None)
    cert_path = None
    if row.get("cert_id"):
        path = CERT_DIR / f"{row['cert_id']}.pem"
        if not path.exists():
            raise HTTPException(400, "Selected CA cert file is missing")
        cert_path = str(path)
    return row, model, cert_path

def run_saved(processor_id: str, payload: dict, transaction_id: str = None, query_template: str = None):
    from ..chroma_runner import run_chroma_query
    row, model, cert_path = _resolve(processor_id)
    if query_template:
        row = dict(row)
        row["query_template"] = query_template
    result = run_chroma_query(row, payload, cert_path=cert_path, model=model, transaction_id=transaction_id)
    result["collection_metadata"] = _collection_meta(row)
    return result

def _collection_meta(row):
    try:
        import chromadb
        headers = {}
        if row.get("chroma_token"):
            headers[row.get("chroma_header") or "Authorization"] = row.get("chroma_token")
        client = chromadb.HttpClient(host=row.get("host"), port=int(row.get("port") or 8000), ssl=bool(row.get("ssl")), headers=headers or None)
        collection = client.get_collection(row.get("collection") or "")
        return {"name": collection.name, "metadata": collection.metadata, "count": collection.count()}
    except Exception as exc:
        return {"error": str(exc)}

@router.get("/certs")
def list_certs():
    return _load(CERTS_ID, [])

@router.post("/certs")
def upload_cert(name: str = "company-ca", file: UploadFile = File(...)):
    raw = file.file.read()
    if b"BEGIN" not in raw:
        raise HTTPException(400, "Upload a PEM certificate")
    cert_id = _new_id()
    (CERT_DIR / f"{cert_id}.pem").write_bytes(raw)
    items = _load(CERTS_ID, [])
    items.append({"id": cert_id, "name": name, "filename": file.filename or "ca.pem"})
    _save(CERTS_ID, items)
    return items[-1]

@router.get("/models")
def list_models():
    items = _load(MODELS_ID, None)
    if items is None:
        _save(MODELS_ID, DEFAULT_MODELS)
        return DEFAULT_MODELS
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
    found = None
    for row in items:
        if row.get("id") == model_id:
            row.update(body.model_dump())
            found = row
    if not found:
        raise HTTPException(404, "model not found")
    _save(MODELS_ID, items)
    return found

@router.get("/processors")
def list_processors(project_id: Optional[str] = None):
    rows = _load(PROCESSORS_ID, [])
    if project_id:
        rows = [r for r in rows if r.get("project_id") in (None, "", project_id)]
    return [_mask(r) for r in rows]

@router.post("/processors")
def create_processor(body: ChromaProcessorIn):
    items = _load(PROCESSORS_ID, [])
    row = body.model_dump()
    row["id"] = _new_id()
    items.append(row)
    _save(PROCESSORS_ID, items)
    log_event("info", f"Chroma processor created: {row['name']}")
    return _mask(row)

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
    return _mask(found)

@router.post("/processors/{processor_id}/test")
def test_processor(processor_id: str, body: ChromaTestIn):
    try:
        return run_saved(processor_id, body.payload or {})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc))

@router.post("/query")
def query_chroma(body: ChromaQueryIn):
    """Free-text query. Each hit includes document text and Chroma file metadata."""
    try:
        return run_saved(body.processor_id, {"User_Message__c": body.text}, query_template=body.text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc))
