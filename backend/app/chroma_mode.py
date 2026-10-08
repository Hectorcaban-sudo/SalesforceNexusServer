"""Chroma is a processing mode, same as custom_script or SharePoint.

The flow processor node already passes processingMode and processorId into
process_payload. This wrapper handles mode == "chroma" and leaves every
other mode alone.
"""
import asyncio


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
        if mode == "chroma":
            from .routers.chroma import run_saved
            if not processor_id:
                raise RuntimeError("chroma mode requires a chroma processor id")
            return await asyncio.to_thread(run_saved, processor_id, payload, transaction_id)
        return await original(payload, mode_override, processor_id_override, org_id, transaction_id)

    worker.process_payload = process_payload
