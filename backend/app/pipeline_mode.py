"""Run another saved pipeline as a processor step.

processingMode "pipeline" and processorId = pipeline id. The child graph
runs with the same payload. Its result becomes this step's result, so a
Transform or Publish after it can use the child output. A cycle fails.
"""
import contextvars

_stack = contextvars.ContextVar("nexus_subflow_stack", default=())


async def run_subflow(pipeline_id: str, payload: dict, org_id: str, transaction_id: str):
    stack = _stack.get()
    if pipeline_id in stack:
        raise RuntimeError(f"Pipeline cycle: {pipeline_id}")
    from .database import event_pipelines_table, Q
    from .flow_walker import run_flow_graph
    from . import worker

    row = event_pipelines_table.get(Q.id == pipeline_id)
    if not row:
        raise RuntimeError(f"Pipeline not found: {pipeline_id}")
    graph = row.get("flow_graph") or {}
    if not graph.get("nodes"):
        raise RuntimeError(f"Pipeline {row.get('name') or pipeline_id} has no flow")
    from . import transactions as tx
    # Run under its own child transaction so the child's status/trace never overwrite the parent's.
    child = tx.record_transaction(
        org_id=org_id, org_name=None, direction="internal", channel=row.get("name") or "subflow",
        status="processing", payload=payload or {}, parent_transaction_id=transaction_id,
    )
    token = _stack.set(stack + (pipeline_id,))
    try:
        ctx = await run_flow_graph(
            src_cfg={"flow_graph": graph},
            transaction_id=child["id"],
            org_id=org_id,
            source_channel=row.get("name") or "subflow",
            payload=payload or {},
            parent_carrier=None,
            process_payload=worker.process_payload,
            apply_result_transform=worker.apply_result_transform,
            apply_publish_field_map=worker.apply_publish_field_map,
            validate_payload_schema=worker.validate_payload_schema,
            evaluate_rule_gate=worker.evaluate_rule_gate,
            start_span=lambda *a, **k: None,
            inject_trace_context=lambda *a, **k: {},
        )
        rec = tx.get_transaction(child["id"]) or {}
        if rec.get("status") == "failed":
            raise RuntimeError(f"Pipeline {row.get('name') or pipeline_id} failed: {rec.get('error') or 'unknown error'}")
        return (ctx.result if ctx else None) or {"status": "ok", "summary": "Subflow finished with no result"}
    finally:
        _stack.reset(token)


def install():
    from . import worker

    original = worker.process_payload

    async def process_payload(payload, mode_override=None, processor_id_override=None, org_id=None, transaction_id=None):
        mode = mode_override
        processor_id = processor_id_override
        if mode == "pipeline":
            if not processor_id:
                raise RuntimeError("pipeline mode requires a pipeline id")
            return await run_subflow(processor_id, payload, org_id, transaction_id)
        return await original(payload, mode_override, processor_id_override, org_id, transaction_id)

    worker.process_payload = process_payload
