"""Walk a saved Event Flow graph instead of the linear Events routing form.

Publish nodes on the continuing path wait until that path finishes.
An edge with sourceHandle side or isolated runs as a child transaction.
Each visited node is stored on the transaction as flow_trace.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from .database import event_configs_table, Q
from .logging_config import log_event
from . import transactions as tx
from .integrations import dispatch_integrations
from .alerts import fire_alert_for_transaction
from .broker import broker

_WALK_RANK = {
    "schema": 0, "rule": 1, "processor": 2, "flowAction": 2, "transform": 3, "publishMap": 4,
    "if": 5, "switch": 5, "integration": 8, "alert": 8, "publish": 9, "stop": 10,
}


def _ordered(edges, by_id):
    return sorted(edges or [], key=lambda e: _WALK_RANK.get((by_id.get(e.get("target")) or {}).get("type"), 6))


def _dig(root: Any, path: str):
    if not path:
        return None
    cur = root
    for part in str(path).replace("[", ".").replace("]", "").split("."):
        part = part.strip()
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def eval_if(data: dict, payload: dict, result: Optional[dict]) -> bool:
    field = (data.get("condField") or "payload").strip()
    op = (data.get("condOp") or "eq").strip()
    expected = data.get("condValue")
    scope = {"payload": payload or {}, "result": result or {}}
    if field.startswith("result."):
        actual = _dig(scope, field)
    elif field.startswith("payload."):
        actual = _dig(scope, field)
    else:
        actual = _dig(scope["payload"], field)
    if op == "exists":
        return actual is not None
    if op == "eq":
        return str(actual) == str(expected)
    if op == "ne":
        return str(actual) != str(expected)
    if op == "contains":
        return expected is not None and str(expected) in str(actual or "")
    if op == "gt":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    return False


def eval_switch_handle(data: dict, payload: dict, result: Optional[dict]) -> str:
    field = (data.get("switchField") or "payload").strip()
    scope = {"payload": payload or {}, "result": result or {}}
    if field.startswith("result.") or field.startswith("payload."):
        actual = _dig(scope, field)
    else:
        actual = _dig(scope["payload"], field)
    return str(actual) if actual is not None else "default"


class FlowWalkResult:
    def __init__(self):
        self.aborted = False
        self.stop_publish = False
        self.result: Optional[dict] = None
        self.publish_payload: Optional[dict] = None
        self.fired_integrations: list[str] = []
        self.fired_alerts: list[str] = []
        self.published_channels: list[str] = []
        self.trace: list[dict] = []
        self.deferred_publish: list[str] = []


async def run_flow_graph(
    *,
    src_cfg: dict,
    transaction_id: str,
    org_id: str,
    source_channel: str,
    payload: dict,
    parent_carrier,
    process_payload,
    apply_result_transform,
    apply_publish_field_map,
    validate_payload_schema,
    evaluate_rule_gate,
    start_span,
    inject_trace_context,
) -> Optional[FlowWalkResult]:
    graph = src_cfg.get("flow_graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return None

    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    outgoing: dict[str, list[dict]] = {}
    for e in edges:
        outgoing.setdefault(e.get("source"), []).append(e)

    start = next((n for n in nodes if n.get("type") == "source"), nodes[0])
    ctx = FlowWalkResult()
    visited_nodes: set[str] = set()

    async def fire_one_integration(iid: str):
        rec = tx.get_transaction(transaction_id)
        await asyncio.to_thread(dispatch_integrations, rec, [iid], parent_carrier)
        ctx.fired_integrations.append(iid)

    async def fire_one_alert(aid: str):
        rec = tx.get_transaction(transaction_id)
        await asyncio.to_thread(fire_alert_for_transaction, rec, [aid])
        ctx.fired_alerts.append(aid)

    async def publish_channel(pub_cfg_id: str):
        cfg = event_configs_table.get(Q.id == pub_cfg_id)
        if not cfg or not cfg.get("enabled") or cfg.get("direction") != "publish":
            return
        channel = cfg["channel"]
        body = ctx.publish_payload if ctx.publish_payload is not None else (ctx.result or payload)
        fanout = tx.record_transaction(
            org_id=org_id, org_name=None, direction="publish", channel=channel,
            status="queued", payload=body, parent_transaction_id=transaction_id,
        )
        await broker.publish(
            "outbound",
            {
                "transaction_id": fanout["id"],
                "org_id": org_id,
                "channel": channel,
                "payload": body,
                "routed_integration_ids": [],
                "routed_alert_ids": [],
                "_trace": parent_carrier,
            },
        )
        ctx.published_channels.append(channel)

    async def visit(node_id: str):
        if ctx.aborted or not node_id or node_id in visited_nodes:
            return
        node = by_id.get(node_id)
        if not node:
            return
        ntype = node.get("type")
        if ntype != "publish":
            # Publish nodes stay out of visited_nodes: they are deferred and must still run at the end.
            visited_nodes.add(node_id)
        data = node.get("data") or {}
        incoming = {"payload": payload, "result": ctx.result}
        if ntype == "publish":
            ctx.deferred_publish.append(node_id)
            ctx.trace.append({"id": node_id, "type": ntype, "label": data.get("label") or ntype, "status": "deferred", "input": incoming, "output": None})
            return
        if ntype == "schema":
            schema = None
            try:
                raw = (data.get("payloadSchemaText") or "").strip()
                if raw:
                    import json
                    schema = json.loads(raw)
            except Exception:
                schema = src_cfg.get("payload_schema")
            mode = (data.get("schemaMode") or src_cfg.get("schema_validation_mode") or "off").lower()
            if schema and mode in ("reject", "warn"):
                ok, errs = validate_payload_schema(payload if isinstance(payload, dict) else {}, schema)
                if not ok:
                    msg = "Payload schema validation failed: " + "; ".join(errs[:12])
                    if mode == "reject":
                        tx.update_transaction(transaction_id, status="failed", error=msg)
                        ctx.aborted = True
                        return
                    log_event("warning", f"Walker: schema warn — {msg}", transaction_id=transaction_id)
        elif ntype == "rule":
            rule_id = data.get("ruleId") or src_cfg.get("rule_id")
            if rule_id:
                gate = await asyncio.to_thread(evaluate_rule_gate, rule_id, payload)
                if gate.error:
                    tx.update_transaction(transaction_id, status="failed", error=f"Rule gate failed: {gate.error}")
                    ctx.aborted = True
                    return
                if not gate.should_process:
                    tx.update_transaction(transaction_id, status="skipped", result=gate.rule_output)
                    ctx.aborted = True
                    return
        elif ntype in ("processor", "flowAction"):
            tx.update_transaction(transaction_id, status="processing")
            mode = data.get("processingMode") or ("flow_action" if ntype == "flowAction" else None) or src_cfg.get("processing_mode") or None
            pid = data.get("processorId") or src_cfg.get("processor_id") or None
            try:
                ctx.result = await process_payload(payload, mode, pid, org_id, transaction_id)
            except Exception as exc:
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                ctx.aborted = True
                return
            tx.update_transaction(transaction_id, status="processed", result=ctx.result)
        elif ntype == "transform":
            tmpl = data.get("resultTransform") or src_cfg.get("result_transform_template") or ""
            if tmpl.strip() and ctx.result is not None:
                try:
                    ctx.result = apply_result_transform(ctx.result, payload, tmpl)
                    ctx.publish_payload = None
                    tx.update_transaction(transaction_id, result=ctx.result)
                except Exception as exc:
                    tx.update_transaction(transaction_id, status="failed", error=f"Transform failed: {exc}")
                    ctx.aborted = True
                    return
        elif ntype == "publishMap":
            fmap = {}
            try:
                import json
                raw = (data.get("publishMapText") or "").strip()
                if raw:
                    fmap = json.loads(raw)
            except Exception:
                fmap = src_cfg.get("publish_field_map") or {}
            try:
                ctx.publish_payload = apply_publish_field_map(ctx.result or {}, payload, fmap) if fmap else ctx.result
            except Exception:
                ctx.publish_payload = ctx.result
        elif ntype == "integration":
            if data.get("refId"):
                await fire_one_integration(data.get("refId"))
        elif ntype == "alert":
            if data.get("refId"):
                await fire_one_alert(data.get("refId"))
        elif ntype == "stop":
            ctx.stop_publish = True
            ctx.aborted = True
            rec = tx.get_transaction(transaction_id)
            if (rec or {}).get("status") in (None, "queued", "processing"):
                tx.update_transaction(transaction_id, status="skipped", result=ctx.result, error="Stopped by flow node — remaining graph skipped")
            return
        elif ntype == "if":
            handle = "true" if eval_if(data, payload, ctx.result) else "false"
            ctx.trace.append({"id": node_id, "type": ntype, "label": data.get("label") or ntype, "status": handle, "input": incoming, "output": {"branch": handle}})
            for e in outgoing.get(node_id, []):
                if (e.get("sourceHandle") or "true") == handle:
                    await visit(e.get("target"))
            return
        elif ntype == "switch":
            handle = eval_switch_handle(data, payload, ctx.result)
            ctx.trace.append({"id": node_id, "type": ntype, "label": data.get("label") or ntype, "status": handle, "input": incoming, "output": {"branch": handle}})
            matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == handle]
            if not matched:
                matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == "default"]
            for e in matched:
                await visit(e.get("target"))
            return

        ctx.trace.append({"id": node_id, "type": ntype, "label": data.get("label") or ntype, "status": "ok", "input": incoming, "output": ctx.result})
        continuing, isolated = [], []
        for e in _ordered(outgoing.get(node_id, []), by_id):
            target = by_id.get(e.get("target")) or {}
            if target.get("type") == "publish":
                ctx.deferred_publish.append(e.get("target"))
                continue
            handle = e.get("sourceHandle") or ""
            if handle in ("side", "isolated") or (e.get("data") or {}).get("isolated"):
                isolated.append(e)
            else:
                continuing.append(e)
        for e in continuing:
            await visit(e.get("target"))
        for e in isolated:
            await run_isolated(e.get("target"))

    async def run_isolated(node_id: str):
        child = tx.record_transaction(
            org_id=org_id, org_name=None, direction="internal", channel=source_channel,
            status="processing", payload=payload, parent_transaction_id=transaction_id,
        )
        saved = ctx.result
        start = len(ctx.trace)
        await visit(node_id)
        failed = ctx.aborted and not ctx.stop_publish
        tx.update_transaction(child["id"], status="failed" if failed else "processed", result=ctx.result, flow_trace=list(ctx.trace[start:]))
        ctx.result = saved

    await visit(start.get("id"))
    if not ctx.aborted:
        for node_id in list(dict.fromkeys(ctx.deferred_publish)):
            if node_id in visited_nodes:
                continue
            node = by_id.get(node_id) or {}
            data = node.get("data") or {}
            rid = data.get("refId")
            if rid and not ctx.stop_publish:
                await publish_channel(rid)
                ctx.trace.append({"id": node_id, "type": "publish", "label": data.get("label") or "publish", "status": "published", "input": ctx.publish_payload or ctx.result, "output": {"channel": rid}})
    rec = tx.get_transaction(transaction_id)
    st = (rec or {}).get("status")
    if st in (None, "queued", "processing"):
        if ctx.aborted and ctx.stop_publish:
            tx.update_transaction(transaction_id, status="skipped", result=ctx.result, error="Stopped by flow node — remaining graph skipped", flow_trace=ctx.trace)
        else:
            tx.update_transaction(transaction_id, status="processed", result=ctx.result, flow_trace=ctx.trace)
    else:
        tx.update_transaction(transaction_id, flow_trace=ctx.trace)
    log_event("info", "Walker finished", transaction_id=transaction_id, integrations=ctx.fired_integrations, published=ctx.published_channels, aborted=ctx.aborted)
    return ctx


def simulate_flow_graph(graph: dict, payload: dict, src_cfg: Optional[dict] = None) -> dict:
    src_cfg = src_cfg or {}
    nodes = (graph or {}).get("nodes") or []
    edges = (graph or {}).get("edges") or []
    if not nodes:
        return {"ok": False, "error": "No nodes in graph", "steps": []}
    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    outgoing: dict[str, list] = {}
    for e in edges:
        outgoing.setdefault(e.get("source"), []).append(e)
    start = next((n for n in nodes if n.get("type") == "source"), nodes[0])
    steps, visited, result, aborted = [], set(), None, False

    def step(node, status, detail, extra=None):
        steps.append({"id": node.get("id"), "type": node.get("type"), "label": (node.get("data") or {}).get("label") or node.get("type"), "status": status, "detail": detail, **(extra or {})})

    def visit(node_id: str):
        nonlocal result, aborted
        if aborted or not node_id or node_id in visited:
            return
        node = by_id.get(node_id)
        if not node:
            return
        visited.add(node_id)
        ntype = node.get("type")
        data = node.get("data") or {}
        if ntype == "source":
            step(node, "ok", "Subscribe entry")
        elif ntype in ("processor", "flowAction"):
            mode = data.get("processingMode") or src_cfg.get("processing_mode") or "local"
            result = {"dry_run": True, "mode": mode, "echo": payload}
            step(node, "skip", f"Would run processor mode={mode} (not executed)")
        elif ntype == "stop":
            step(node, "ok", "Stop — remaining nodes skipped")
            aborted = True
            return
        elif ntype == "if":
            handle = "true" if eval_if(data, payload, result) else "false"
            step(node, "ok", f"Condition → {handle}", {"branch": handle})
            for e in outgoing.get(node_id, []):
                if (e.get("sourceHandle") or "true") == handle:
                    visit(e.get("target"))
            return
        elif ntype == "switch":
            handle = eval_switch_handle(data, payload, result)
            step(node, "ok", f"Switch → {handle}", {"branch": handle})
            matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == handle] or [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == "default"]
            for e in matched:
                visit(e.get("target"))
            return
        else:
            step(node, "ok", ntype)
        for e in _ordered(outgoing.get(node_id, []), by_id):
            visit(e.get("target"))

    visit(start.get("id"))
    return {"ok": True, "aborted": aborted, "side_effects": False, "result": result, "steps": steps}
