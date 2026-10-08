@router.put("/processors/{processor_id}")
def update_processor(processor_id: str, body: ChromaProcessorIn):
    items = _load(PROCESSORS_ID, [])
    found = None
    for row in items:
        if row.get("id") == processor_id:
            incoming = body.model_dump()
            if not incoming.get("embed_api_key") or incoming.get("embed_api_key") == "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022":
                incoming["embed_api_key"] = row.get("embed_api_key") or ""
            if not incoming.get("chroma_token") or incoming.get("chroma_token") == "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022":
                incoming["chroma_token"] = row.get("chroma_token") or ""
            row.update(incoming)
            row["id"] = processor_id
            found = row
    if not found:
        raise HTTPException(404, "processor not found")
    _save(PROCESSORS_ID, items)
    return _mask(found)

@router.delete("/processors/{processor_id}")
def delete_processor(processor_id: str):
    items = _load(PROCESSORS_ID, [])
    kept = [r for r in items if r.get("id") != processor_id]
    if len(kept) == len(items):
        raise HTTPException(404, "processor not found")
    _save(PROCESSORS_ID, kept)
    log_event("info", f"Chroma processor deleted: {processor_id}")
    return {"ok": True}
