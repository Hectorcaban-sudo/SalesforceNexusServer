"""Query a Chroma collection with a company embedding endpoint.

The OpenAI SDK is only the HTTP client for the embedding API (custom base URL,
ca cert, apikey header). It does not summarize the Chroma hits.
"""
import json
from typing import Optional

from .logging_config import log_event


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

    _log(f"chroma query collection={processor.get('collection')}")
    import chromadb

    headers = {}
    if processor.get("chroma_token"):
        headers[processor.get("chroma_header") or "Authorization"] = processor.get("chroma_token")
    chroma = chromadb.HttpClient(
        host=processor.get("host") or "localhost",
        port=int(processor.get("port") or 8000),
        ssl=bool(processor.get("ssl")),
        headers=headers or None,
    )
    collection = chroma.get_collection(processor.get("collection") or "")
    n = int(n_results or processor.get("n_results") or 5)
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
        "query": query_text,
        "model": model.get("name") or model_id,
        "collection": processor.get("collection"),
        "matches": matches,
        "steps": [{"name": "embed", "status": "ok"}, {"name": "chroma query", "status": "ok", "detail": f"{len(matches)} hits"}],
    }
