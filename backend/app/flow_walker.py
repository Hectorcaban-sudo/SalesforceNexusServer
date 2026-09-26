"""Walk a saved Event Flow graph instead of the linear Events routing form.

Node types
----------
source, schema, rule, processor, transform, publishMap,
publish, integration, alert, stop, if, switch

Edges
-----
Ordinary nodes fan out to *all* outgoing edges (parallel side-effects).
`if` follows sourceHandle "true" or "false".
`switch` follows sourceHandle matching the field value, else "default".

Stop aborts the rest of the walk (no further publish / hooks).
Hooks already visited have already fired.
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
    """Simple field/op/value condition. Missing field => False."""
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
    ctx.result = None
    ctx.publish_payload = None
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
                "routed_integration_ids": [],  # hooks already fired in-graph
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
        visited_nodes.add(node_id)
        ntype = node.get("type")
        data = node.get("data") or {}

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

        elif ntype == "processor":
            tx.update_transaction(transaction_id, status="processing")
            mode = data.get("processingMode") or src_cfg.get("processing_mode") or None
            pid = data.get("processorId") or src_cfg.get("processor_id") or None
            try:
                ctx.result = await process_payload(payload, mode, pid, org_id, transaction_id)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                ctx.aborted = True
                return
            tx.update_transaction(transaction_id, status="processed", result=ctx.result)

        elif ntype == "transform":
            tmpl = data.get("resultTransform") or src_cfg.get("result_transform_template") or ""
            if tmpl.strip() and ctx.result is not None:
                try:
                    ctx.result = apply_result_transform(ctx.result, payload, tmpl)
                    tx.update_transaction(transaction_id, result=ctx.result)
                except Exception as exc:  # noqa: BLE001
                    log_event("warning", f"Walker transform failed: {exc}")

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
                if fmap:
                    ctx.publish_payload = apply_publish_field_map(ctx.result or {}, payload, fmap)
                else:
                    ctx.publish_payload = ctx.result
            except Exception:
                ctx.publish_payload = ctx.result

        elif ntype == "integration":
            iid = data.get("refId")
            if iid:
                await fire_one_integration(iid)

        elif ntype == "alert":
            aid = data.get("refId")
            if aid:
                await fire_one_alert(aid)

        elif ntype == "publish":
            if ctx.stop_publish:
                return
            rid = data.get("refId")
            if rid:
                await publish_channel(rid)

        elif ntype == "stop":
            ctx.stop_publish = True
            ctx.aborted = True
            rec = tx.get_transaction(transaction_id)
            st = (rec or {}).get("status")
            # Stop with no processor leaves the tx in queued forever otherwise.
            if st in (None, "queued", "processing"):
                tx.update_transaction(
                    transaction_id,
                    status="skipped",
                    result=ctx.result,
                    error="Stopped by flow node — remaining graph skipped",
                )
            log_event("info", "Walker: stop node — remaining graph skipped", transaction_id=transaction_id)
            return

        elif ntype == "if":
            truth = eval_if(data, payload, ctx.result)
            handle = "true" if truth else "false"
            for e in outgoing.get(node_id, []):
                if (e.get("sourceHandle") or "true") == handle:
                    await visit(e.get("target"))
            return

        elif ntype == "switch":
            handle = eval_switch_handle(data, payload, ctx.result)
            matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == handle]
            if not matched:
                matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == "default"]
            for e in matched:
                await visit(e.get("target"))
            return

        for e in outgoing.get(node_id, []):
            await visit(e.get("target"))

    await visit(start.get("id"))
    rec = tx.get_transaction(transaction_id)
    st = (rec or {}).get("status")
    if st in (None, "queued", "processing"):
        # Graph ended without a processor (or stop already handled). Never leave queued.
        if ctx.aborted and ctx.stop_publish:
            tx.update_transaction(
                transaction_id,
                status="skipped",
                result=ctx.result,
                error="Stopped by flow node — remaining graph skipped",
            )
        else:
            tx.update_transaction(transaction_id, status="processed", result=ctx.result)
    log_event(
        "info",
        "Walker finished",
        transaction_id=transaction_id,
        integrations=ctx.fired_integrations,
        published=ctx.published_channels,
        aborted=ctx.aborted,
    )
    return ctx


def simulate_flow_graph(graph: dict, payload: dict, src_cfg: Optional[dict] = None) -> dict:
    """Dry-run: walk if/switch/stop/schema. No Salesforce, integrations, or broker."""
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
    steps = []
    visited = set()
    result = None
    aborted = False

    def step(node, status, detail, extra=None):
        steps.append({
            "id": node.get("id"),
            "type": node.get("type"),
            "label": (node.get("data") or {}).get("label") or node.get("type"),
            "status": status,
            "detail": detail,
            **(extra or {}),
        })

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
        elif ntype == "schema":
            schema = None
            try:
                import json
                raw = (data.get("payloadSchemaText") or "").strip()
                if raw:
                    schema = json.loads(raw)
            except Exception:
                schema = src_cfg.get("payload_schema")
            mode = (data.get("schemaMode") or src_cfg.get("schema_validation_mode") or "off").lower()
            if schema and mode in ("reject", "warn"):
                from .worker import validate_payload_schema
                ok, errs = validate_payload_schema(payload if isinstance(payload, dict) else {}, schema)
                if not ok:
                    step(node, "fail" if mode == "reject" else "warn", "; ".join(errs[:8]))
                    if mode == "reject":
                        aborted = True
                        return
                else:
                    step(node, "ok", "Schema valid")
            else:
                step(node, "ok", f"Schema mode={mode or 'off'}")
        elif ntype == "rule":
            step(node, "skip", "Rule not evaluated in dry-run (no side effects; use live reprocess to run JDM)")
        elif ntype == "processor":
            mode = data.get("processingMode") or src_cfg.get("processing_mode") or "local"
            result = {"dry_run": True, "mode": mode, "echo": payload}
            step(node, "skip", f"Would run processor mode={mode} (not executed)")
        elif ntype == "transform":
            tmpl = data.get("resultTransform") or src_cfg.get("result_transform_template") or ""
            if tmpl.strip():
                try:
                    from .worker import apply_result_transform
                    result = apply_result_transform(result or {}, payload, tmpl)
                    step(node, "ok", "Transform applied")
                except Exception as exc:
                    step(node, "warn", f"Transform failed: {exc}")
            else:
                step(node, "ok", "No transform template")
        elif ntype == "publishMap":
            step(node, "ok", "Publish map would apply on live run")
        elif ntype == "integration":
            step(node, "skip", f"Would fire integration {data.get('refId') or '(unbound)'} — not called")
        elif ntype == "alert":
            step(node, "skip", f"Would fire alert {data.get('refId') or '(unbound)'} — not called")
        elif ntype == "publish":
            step(node, "skip", f"Would publish {data.get('label') or data.get('refId')} — not sent")
        elif ntype == "stop":
            step(node, "ok", "Stop — remaining nodes skipped")
            aborted = True
            return
        elif ntype == "if":
            truth = eval_if(data, payload, result)
            handle = "true" if truth else "false"
            step(node, "ok", f"Condition → {handle}", {"branch": handle})
            for e in outgoing.get(node_id, []):
                if (e.get("sourceHandle") or "true") == handle:
                    visit(e.get("target"))
            return
        elif ntype == "switch":
            handle = eval_switch_handle(data, payload, result)
            step(node, "ok", f"Switch → {handle}", {"branch": handle})
            matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == handle]
            if not matched:
                matched = [e for e in outgoing.get(node_id, []) if (e.get("sourceHandle") or "") == "default"]
            for e in matched:
                visit(e.get("target"))
            return
        else:
            step(node, "ok", ntype)

        for e in outgoing.get(node_id, []):
            visit(e.get("target"))

    visit(start.get("id"))
    return {
        "ok": True,
        "aborted": aborted,
        "side_effects": False,
        "result": result,
        "steps": steps,
    }
