"""Query a Chroma collection with a company embedding endpoint.

The OpenAI SDK is only the HTTP client for the embedding API (custom base URL,
ca cert, apikey header). It does not summarize the Chroma hits.
"""
import json
import re
from typing import Optional

from .logging_config import log_event

_PROJECT_ID = re.compile(r"\b(\d{4,8})\b")
_LAST_N = re.compile(r"\b(?:last|latest|newest)\s+(\d+)?", re.I)
_DOC_WORDS = ("modification", "mod", "sow", "pws", "contract", "drawing", "attachment")


def _metadata_filter(question: str, processor: dict) -> Optional[dict]:
    """Build a Chroma where clause from the processor's metadata field list."""
    text = question or ""
    lowered = text.lower()
    fields = processor.get("metadata_fields") or []
    clauses = []
    date_field = ""
    for item in fields:
        name = (item.get("field") or "").strip()
        how = (item.get("read_as") or "").strip()
        hint = (item.get("keyword") or "").strip()
        if not name or not how:
            continue
        if how == "project_number":
            found = _PROJECT_ID.search(text)
            if found:
                clauses.append({name: found.group(1)})
        elif how == "keyword":
            words = [w.strip().lower() for w in (hint or "modification,sow,pws,contract").split(",") if w.strip()]
            for word in words:
                if word in lowered:
                    clauses.append({name: {"$contains": word}})
                    break
        elif how == "after_word":
            marker = hint or "by"
            found = re.search(rf"\b{re.escape(marker)}\s+([A-Za-z0-9][A-Za-z0-9 .'-]*)", text, re.I)
            if found:
                clauses.append({name: found.group(1).strip()})
        elif how == "sort_date":
            date_field = name
    if not clauses and not date_field:
        return None
    content_words = ("about", "regarding", "describe", "explain", "what is", "how does")
    if any(w in lowered for w in content_words) and not clauses:
        return None
    where = clauses[0] if len(clauses) == 1 else ({"$and": clauses} if clauses else None)
    return {"where": where, "date_field": date_field, "latest": bool(_LAST_N.search(lowered))}


def _chroma_server_version(host: str, port: int, ssl: bool) -> str:
    import httpx
    scheme = "https" if ssl else "http"
    for path in ("/api/v2/version", "/api/v1/version"):
        try:
            resp = httpx.get(f"{scheme}://{host}:{port}{path}", timeout=5.0, verify=False)
            if resp.status_code == 200 and resp.text.strip():
                return resp.text.strip().strip('"')
        except Exception:
            continue
    return ""


def run_chroma_query(processor: dict, payload: dict, cert_path: Optional[str] = None, model: Optional[dict] = None, transaction_id: Optional[str] = None, query_text: Optional[str] = None, n_results: Optional[int] = None) -> dict:
    from .template_renderer import render_template

    def _log(msg):
        extra = {"transaction_id": transaction_id} if transaction_id else {}
        log_event("info", msg, logger_name="nexus.chroma", **extra)

    if query_text is None:
        # Only saved templates are rendered; literal text from the admin query box is used as-is.
        query_text = render_template(processor.get("query_template") or "{{ payload.User_Message__c or payload }}", {"payload": payload or {}})
    query_text = (query_text or "").strip()
    if not query_text:
        raise RuntimeError("Chroma query text is empty. Set query_template.")

    model = model or {}
    slug = model.get("url_slug") or processor.get("embed_url_slug") or ""
    base = (processor.get("embed_base_url") or "https://devmissionassist.api.us.baesystems.com/{url}/v1").replace("{url}", slug).rstrip("/")
    api_key = processor.get("embed_api_key") or ""
    header_name = processor.get("embed_header_name") or "apikey"
    model_id = model.get("model_id") or processor.get("embed_model_id") or ""

    _log(f"chroma query collection={processor.get('collection')}")
    import chromadb

    headers = {}
    if processor.get("chroma_token"):
        headers[processor.get("chroma_header") or "Authorization"] = processor.get("chroma_token")
    host = processor.get("host") or "localhost"
    port = int(processor.get("port") or 8000)
    try:
        chroma = chromadb.HttpClient(
            host=host,
            port=port,
            ssl=bool(processor.get("ssl")),
            headers=headers or None,
        )
        collection = chroma.get_collection(processor.get("collection") or "")
    except KeyError as exc:
        if str(exc).strip("'") == "_type":
            server_version = _chroma_server_version(host, port, bool(processor.get("ssl")))
            where = f"{host}:{port}"
            hint = " In Docker, localhost is the Nexus container, not the Chroma box." if host in ("localhost", "127.0.0.1") else ""
            raise RuntimeError(
                "Chroma client/server version mismatch (KeyError: _type). "
                f"Client chromadb {getattr(chromadb, '__version__', 'unknown')} talking to {where}"
                f"{f' (server {server_version})' if server_version else ''}. "
                "The deployed image must use the same chromadb version as that server."
                + hint
            ) from exc
        raise
    n = int(n_results or processor.get("n_results") or 5)
    meta = _metadata_filter(query_text, processor)
    if meta and meta.get("where"):
        _log(f"chroma metadata get where={meta['where']}")
        raw = collection.get(where=meta["where"], limit=max(n, 25), include=["documents", "metadatas"])
        ids = raw.get("ids") or []
        docs = raw.get("documents") or []
        metas = raw.get("metadatas") or []
        rows = []
        for i, hit_id in enumerate(ids):
            rows.append({
                "id": hit_id,
                "document": docs[i] if i < len(docs) else None,
                "metadata": metas[i] if i < len(metas) else None,
                "distance": None,
            })
        if meta.get("latest") and meta.get("date_field"):
            field = meta["date_field"]
            rows.sort(key=lambda r: str((r.get("metadata") or {}).get(field) or ""), reverse=True)
        matches = rows[:n]
        _log(f"chroma metadata hits={len(matches)}")
        return {
            "status": "ok",
            "path": "query_files",
            "query": query_text,
            "where": meta["where"],
            "model": None,
            "collection": processor.get("collection"),
            "matches": matches,
            "steps": [{"name": "metadata filter", "status": "ok", "detail": f"{len(matches)} hits"}],
        }

    _log(f"embed start model={model.get('name') or slug}")
    import httpx
    import openai

    http_client = httpx.Client(verify=cert_path or True, headers={header_name: api_key} if api_key else None, timeout=60.0)
    try:
        client = openai.OpenAI(api_key=api_key or "unused", base_url=base, http_client=http_client)
        if not model_id:
            listed = client.models.list()
            model_id = listed.data[0].id
        embedded = client.embeddings.create(input=[query_text], model=model_id)
        vector = embedded.data[0].embedding
    finally:
        http_client.close()

    raw = collection.query(query_embeddings=[vector], n_results=n, include=["documents", "metadatas", "distances"])
    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]
    matches = []
    for i, hit_id in enumerate(ids):
        matches.append({
            "id": hit_id,
            "document": docs[i] if i < len(docs) else None,
            "metadata": metas[i] if i < len(metas) else None,
            "distance": dists[i] if i < len(dists) else None,
        })
    _log(f"chroma hits={len(matches)}")
    return {
        "status": "ok",
        "path": "semantic_search",
        "query": query_text,
        "model": model.get("name") or model_id,
        "collection": processor.get("collection"),
        "matches": matches,
        "steps": [{"name": "embed", "status": "ok"}, {"name": "chroma query", "status": "ok", "detail": f"{len(matches)} hits"}],
    }
