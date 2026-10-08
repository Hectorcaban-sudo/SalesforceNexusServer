"""processingMode "flow_action" runs a saved reusable action."""
import asyncio


def install():
    from . import worker

    original = worker.process_payload

    async def process_payload(payload, mode_override=None, processor_id_override=None, org_id=None, transaction_id=None):
        if mode_override == "flow_action":
            if not processor_id_override:
                raise RuntimeError("flow_action mode requires a flow action id")
            from .flow_actions import run_flow_action
            return await asyncio.to_thread(run_flow_action, processor_id_override, payload, org_id)
        return await original(payload, mode_override, processor_id_override, org_id, transaction_id)

    worker.process_payload = process_payload
