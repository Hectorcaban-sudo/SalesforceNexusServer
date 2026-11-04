"""REST is a processing mode, same as Chroma or a custom script."""
import asyncio
import json


def to_dss_event(payload, raw):
    source = payload if isinstance(payload, dict) else {}
    body = (raw or {}).get("body")
    return {
        "Conversation_Id__c": source.get("Conversation_Id__c") or source.get("conversationId") or "",
        "Status__c": "Ok" if (raw or {}).get("status") == "ok" else "Error",
        "Payload_Json__c": json.dumps(body, default=str),
    }


def install():
    from . import worker

    original = worker.process_payload

    async def process_payload(payload, mode_override=None, processor_id_override=None, org_id=None, transaction_id=None):
        mode = mode_override
        processor_id = processor_id_override
        if not mode:
            from .routers.admin_config import get_processing_mode_raw
            cfg = get_processing_mode_raw() or {}
            mode = cfg.get("mode")
            processor_id = processor_id or cfg.get("active_processor_id")
        if mode == "rest":
            from .routers.rest import run_saved
            if not processor_id:
                raise RuntimeError("rest mode requires a REST processor id")
            raw = await asyncio.to_thread(run_saved, processor_id, payload, transaction_id)
            event = to_dss_event(payload, raw)
            event["_steps"] = (raw or {}).get("steps") or []
            event["_rest"] = {"status_code": (raw or {}).get("status_code"), "body": (raw or {}).get("body")}
            return event
        return await original(payload, mode_override, processor_id_override, org_id, transaction_id)

    worker.process_payload = process_payload
