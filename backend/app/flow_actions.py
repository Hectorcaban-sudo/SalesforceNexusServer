def run_flow_action(action_id: str, payload: dict, org_id: Optional[str] = None) -> dict:
    action = _action(action_id)
    kind = (action.get("type") or "").lower()
    if kind in ("salesforce_get", "salesforce_delete"):
        action = dict(action)
        action["operation"] = "delete" if kind == "salesforce_delete" else "get"
        return asyncio.run(_salesforce(action, payload, org_id))
    if kind == "sharepoint_file":
        return _sharepoint(action, payload, org_id)
    if kind == "chroma":
        from .routers.chroma import run_saved
        processor_id = action.get("chroma_processor_id")
        if not processor_id:
            raise FlowActionError("Chroma flow action requires a Chroma processor")
        raw = run_saved(processor_id, payload)
        steps = list((raw or {}).get("steps") or [])
        steps.append({"name": "chroma", "status": "ok", "detail": f"{(raw or {}).get('collection') or ''} hits"})
        raw = dict(raw or {})
        raw["steps"] = steps
        return raw
    raise FlowActionError(f"Unknown flow action type '{kind}'")
