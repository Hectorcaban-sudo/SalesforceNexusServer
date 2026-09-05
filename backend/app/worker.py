"""
The "internal function" referenced in the system design:

  Salesforce --CometD--> [inbound topic] --> WORKER (this module) -->
      [outbound topic] --> Salesforce publisher --> Salesforce

The worker consumes raw platform-event messages from the broker's "inbound"
topic, runs them through a processing hook (business/AI logic lives here -
swap `process_payload` out for a call to any model or rules engine), and
publishes the result onto the "outbound" topic. A separate consumer
(`outbound_publisher`) picks results off that topic and pushes them back to
Salesforce as a new platform event, so the whole pipeline is decoupled at
every stage via the broker and can be scaled independently later.

THREADING: `process_payload`, the Salesforce publish call, and integration
dispatch are all potentially slow, blocking I/O (HTTP calls, subprocess
execution, DB client calls). Since this module runs inside the same asyncio
event loop that also serves the FastAPI admin UI, calling any of that
directly would freeze the entire web app for the duration of the call. Every
such call is therefore routed through `asyncio.to_thread(...)` so event
processing runs on a worker thread and the web app stays fully responsive
(navigable, API-reachable) the whole time events are being processed.
"""
import asyncio
import json
from typing import Optional, Tuple

import urllib3

from .broker import broker
from .database import orgs_table, event_configs_table, Q
from .logging_config import log_event
from . import transactions as tx
from .salesforce_client import sf_client
from .tracing import start_span, inject_trace_context
from .integrations import dispatch_integrations
from .alerts import fire_alert_for_transaction
from . import processors as proc_module

# ---------------------------------------------------------------------------
# Cancellation support for genuinely async operations (Langflow, Salesforce
# publish). Unlike custom_script/DSSClient (which run as real OS subprocesses
# and are cancelled via a polled `cancel_requested` flag - see
# processors.py/dss_runner.py), these run as native asyncio coroutines, so
# they can be cancelled immediately and directly via asyncio.Task.cancel()
# instead of waiting for a poll interval to notice. This registry is how
# routers/transactions.py's cancel endpoint finds the right task to cancel.
# ---------------------------------------------------------------------------
_inflight_tasks: dict = {}


class OperationCancelled(RuntimeError):
    """Raised when an async operation (Langflow call, Salesforce publish) is
    cancelled mid-flight via asyncio.Task.cancel() - distinct from a genuine
    failure, same spirit as processors.ProcessorCancelled for subprocesses."""


def cancel_inflight_task(transaction_id: str) -> bool:
    """Called by routers/transactions.py's cancel endpoint. Returns True if
    a real asyncio task was found and cancelled immediately."""
    task = _inflight_tasks.get(transaction_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _run_cancellable(coro, transaction_id: str):
    """
    Runs `coro` as a task registered under `transaction_id` so it can be
    cancelled immediately (via cancel_inflight_task, called directly from the
    cancel API endpoint) OR by the usual `cancel_requested` flag (polled here
    too, for the case where cancellation was requested just before this
    function even got called and nothing is registered yet to catch it).
    """
    task = asyncio.create_task(coro)
    _inflight_tasks[transaction_id] = task
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.1)
            if task in done:
                return task.result()
            current = tx.get_transaction(transaction_id)
            if current and current.get("cancel_requested") and not task.cancelled():
                task.cancel()
    except asyncio.CancelledError:
        raise OperationCancelled("Operation was cancelled") from None
    finally:
        _inflight_tasks.pop(transaction_id, None)

# Several integrations/DSSClient deployments sit behind internally-issued or
# self-signed certificates; disabling verification is a deliberate operator
# choice (see integrations.py and the dss_client branch below) so we also
# silence the resulting urllib3 warning spam globally.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


from . import dss_runner


def run_dss_client(payload: dict, cancel_check=None) -> dict:
    """Re-exported from dss_runner.py (kept here so existing imports of
    `from .worker import run_dss_client` - e.g. routers/execute.py - don't
    need to change). See dss_runner.py for why this runs in a subprocess."""
    return dss_runner.run_dss_client(payload, cancel_check)


def _extract_langflow_text(response_json: dict, output_path: str = "") -> str:
    """Langflow's /run response is deeply nested and shape varies by flow.
    If an explicit dotted `output_path` is configured, use that; otherwise
    try the common `outputs[0].outputs[0].results.message.text` path, then
    fall back to stringifying the whole response so nothing is silently lost."""
    if output_path:
        node = response_json
        try:
            for key in output_path.split("."):
                node = node[int(key)] if key.isdigit() else node[key]
            return node
        except (KeyError, IndexError, TypeError):
            pass  # fall through to best-effort extraction below

    try:
        return response_json["outputs"][0]["outputs"][0]["results"]["message"]["text"]
    except (KeyError, IndexError, TypeError):
        return json.dumps(response_json)


async def run_langflow(payload: dict) -> dict:
    """Calls a Langflow flow's /api/v1/run/{flow_id} endpoint. Raises on
    failure - see `run_dss_client` docstring for why. Native async (httpx),
    so a Task running this can be cancelled mid-flight - see `_run_cancellable`
    and its use in process_payload's langflow branch below."""
    import httpx
    from .routers.admin_config import get_langflow_config_raw

    config = get_langflow_config_raw()
    if not config.get("base_url") or not config.get("flow_id"):
        raise RuntimeError("Langflow is not configured (base URL and/or flow ID missing in Admin Configuration)")

    input_field = config.get("input_field") or "input_value"
    body = {
        input_field: json.dumps(payload),
        "input_type": "chat",
        "output_type": "chat",
    }
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["x-api-key"] = config["api_key"]

    url = f"{config['base_url'].rstrip('/')}/api/v1/run/{config['flow_id']}"
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        resp = await client.post(url, json=body, headers=headers)
    resp.raise_for_status()
    response_json = resp.json()

    text = _extract_langflow_text(response_json, config.get("output_path", ""))
    return {
        "status": "ok",
        "summary": "Event processed by Langflow",
        "reply": text,
        "raw": response_json,
    }


async def process_payload(payload: dict, mode_override: Optional[str] = None, processor_id_override: Optional[str] = None, org_id: Optional[str] = None, transaction_id: Optional[str] = None) -> dict:
    """
    Business / AI processing logic for every inbound event.

    Which processing mode runs is controlled by Admin Configuration ->
    Payload Processors by default, but an individual subscribed event
    channel can override it (see `_resolve_processing`):
      - "local"          : simple built-in echo/fallback (default)
      - "dss_client"     : calls into a Dataiku DSS LLM endpoint via
                            `dataikuapi.DSSClient(...).get_project(...).get_llm(...)`,
                            run in its own subprocess (dss_runner.py) so it can
                            be hard-cancelled - dataikuapi is a sync-only
                            third-party SDK with no async variant, so a
                            subprocess is the only way to make it killable.
      - "custom_script"  : runs the currently-active (or per-event-selected)
                            uploaded Python script in an isolated subprocess.
                            `org_id` (the triggering event's Salesforce org,
                            when known) is made available to the script via
                            environment variables - see `processors.py:_build_processor_env`.
      - "langflow"        : calls a Langflow flow's /run endpoint - native
                            async (httpx), run as a genuinely cancellable task.

    (The rule engine is NOT a processing mode - it's a pre-processing gate
    that decides whether an event gets processed at all. See
    `_resolve_rule_gate` and its use in `inbound_worker`.)

    Any failure in dss_client/custom_script/langflow mode falls back to a
    local result so the pipeline never breaks because of a downstream outage
    or a bug in an uploaded script - EXCEPT a cancellation, which propagates
    up as ProcessorCancelled/OperationCancelled so the caller marks the
    transaction "cancelled" instead of silently substituting a fallback
    result for an event the admin explicitly stopped.
    """
    from .routers.admin_config import get_processing_mode_raw  # local import avoids a circular import at module load time

    if mode_override:
        mode = mode_override
        active_processor_id = processor_id_override
    else:
        mode_cfg = get_processing_mode_raw()
        mode = mode_cfg.get("mode", "local")
        active_processor_id = mode_cfg.get("active_processor_id")

    def _cancel_check():
        if not transaction_id:
            return False
        current = tx.get_transaction(transaction_id)
        return bool(current and current.get("cancel_requested"))

    if mode == "custom_script" and active_processor_id:
        try:
            return await asyncio.to_thread(proc_module.run_processor, active_processor_id, payload, org_id, _cancel_check)
        except proc_module.ProcessorCancelled:
            raise  # let the caller (inbound_worker) mark this "cancelled", not "failed"
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"Custom processor failed, falling back to local processing: {exc}")
            return {
                "status": "error",
                "summary": "Custom processor failed; returning local fallback result",
                "error": str(exc),
                "echo": payload,
            }

    if mode == "dss_client":
        try:
            return await asyncio.to_thread(run_dss_client, payload, _cancel_check)
        except dss_runner.DSSClientCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"DSSClient call failed, falling back to local processing: {exc}")
            return {
                "status": "error",
                "summary": "DSSClient call failed; returning local fallback result",
                "error": str(exc),
                "echo": payload,
                "Conversation_Id__c": payload.get("Conversation_Id__c"),
            }

    if mode == "langflow":
        try:
            if transaction_id:
                return await _run_cancellable(run_langflow(payload), transaction_id)
            return await run_langflow(payload)
        except OperationCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"Langflow call failed, falling back to local processing: {exc}")
            return {
                "status": "error",
                "summary": "Langflow call failed; returning local fallback result",
                "error": str(exc),
                "echo": payload,
            }

    return {
        "status": "ok",
        "summary": "Event processed by Salesforce Nexus AI Server (local mode)",
        "echo": payload,
    }


def _default_publish_channel(org_id: str) -> Optional[str]:
    row = event_configs_table.get(
        (Q.org_id == org_id) & (Q.direction == "publish") & (Q.enabled == True)  # noqa: E712
    )
    return row["channel"] if row else None


def _source_event_config(org_id: str, source_channel: str) -> Optional[dict]:
    return event_configs_table.get(
        (Q.org_id == org_id) & (Q.channel == source_channel) & (Q.direction == "subscribe")
    )


def _resolve_routes(org_id: str, source_channel: str):
    """Looks up the subscribe event config that triggered this event to find
    its explicit routing selections (publish channels + integrations +
    alerts). Falls back to ([], None, None) when no explicit routing is
    configured, so callers know to use legacy auto-match behavior instead."""
    source_cfg = _source_event_config(org_id, source_channel)
    if not source_cfg:
        return [], None, None

    publish_ids = source_cfg.get("route_publish_channel_ids") or []
    integration_ids = source_cfg.get("route_integration_ids") or None  # None = no explicit selection -> legacy auto-match
    alert_ids = source_cfg.get("route_alert_ids") or None

    publish_channels = []
    for pid in publish_ids:
        cfg = event_configs_table.get(Q.id == pid)
        if cfg and cfg.get("enabled") and cfg.get("direction") == "publish":
            publish_channels.append(cfg["channel"])

    return publish_channels, integration_ids, alert_ids


def _resolve_processing(org_id: str, source_channel: str) -> Tuple[Optional[str], Optional[str]]:
    """Per-subscribed-event processor override: a channel can pin itself to
    "local" / "dss_client" / "custom_script" (+ which processor) instead of
    using the global Admin Configuration default. Returns (mode, processor_id),
    both None if this channel has no override configured."""
    source_cfg = _source_event_config(org_id, source_channel)
    if not source_cfg:
        return None, None
    return source_cfg.get("processing_mode") or None, source_cfg.get("processor_id") or None


def _resolve_auto_publish(org_id: str, source_channel: str) -> bool:
    """Whether processing an event on this channel should automatically
    publish its result back to Salesforce. Defaults to True (existing
    behavior) when the channel has no explicit config, or the field is
    simply absent on an older record."""
    source_cfg = _source_event_config(org_id, source_channel)
    if not source_cfg:
        return True
    return source_cfg.get("auto_publish", True)


def _resolve_rule_gate(org_id: str, source_channel: str) -> Optional[str]:
    """The rule (if any) assigned to gate whether events on this channel get
    processed at all - returns the rule id, or None if no rule is assigned
    (meaning: always process, the existing default behavior)."""
    source_cfg = _source_event_config(org_id, source_channel)
    if not source_cfg:
        return None
    return source_cfg.get("rule_id") or None


class RuleGateResult:
    """Outcome of evaluating a channel's assigned validation rule."""
    def __init__(self, should_process: bool, rule_output: Optional[dict] = None, error: Optional[str] = None):
        self.should_process = should_process
        self.rule_output = rule_output
        self.error = error


def evaluate_rule_gate(rule_id: str, payload: dict) -> RuleGateResult:
    """
    Evaluates the assigned rule against `payload`. The rule's decision graph
    output must contain a boolean `process` field: `true` (or the field
    simply being absent) lets the event continue to normal processing;
    `false` means skip it. Raising during evaluation (bad rule, missing
    referenced field, etc.) is treated as a processing failure, not a quiet
    skip - a broken gate should be visible, not silently swallow events.
    """
    from . import rules as rules_module
    try:
        output = rules_module.evaluate_rule(rule_id, payload)
    except Exception as exc:  # noqa: BLE001
        return RuleGateResult(should_process=False, error=str(exc))

    should_process = bool(output.get("process", True)) if isinstance(output, dict) else True
    return RuleGateResult(should_process=should_process, rule_output=output)


async def inbound_worker():
    """Consumes 'inbound' topic messages forever - the internal function."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        source_channel = message["channel"]
        payload = message["payload"]
        # The carrier injected by whatever produced this message (CometD
        # receive, or an earlier fan-out hop) - passing it to every span
        # below keeps this event's whole journey as ONE trace instead of a
        # new disconnected trace per pipeline stage.
        parent_carrier = message.get("_trace")

        # Cancellation checkpoint: an admin may have cancelled this
        # transaction while it was still sitting in the queue, before we
        # ever got here - honor that instead of processing it anyway.
        current = tx.get_transaction(transaction_id)
        if current and current.get("status") == "cancelled":
            log_event("info", "Worker: skipping cancelled transaction", transaction_id=transaction_id)
            return

        _, _, routed_alert_ids = _resolve_routes(org_id, source_channel)

        rule_id = _resolve_rule_gate(org_id, source_channel)
        if rule_id:
            with start_span("worker.rule_gate", carrier=parent_carrier, transaction_id=transaction_id, org_id=org_id, rule_id=rule_id) as gate_span:
                gate = await asyncio.to_thread(evaluate_rule_gate, rule_id, payload)
            gate_carrier = inject_trace_context(span=gate_span) or parent_carrier

            if gate.error:
                tx.update_transaction(transaction_id, status="failed", error=f"Rule gate evaluation failed: {gate.error}")
                log_event("error", f"Worker: rule gate evaluation failed: {gate.error}", transaction_id=transaction_id, rule_id=rule_id)
                failed_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, failed_tx, None, gate_carrier)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            if not gate.should_process:
                tx.update_transaction(transaction_id, status="skipped", result=gate.rule_output)
                log_event(
                    "info", "Worker: rule gate decided this event should not be processed",
                    transaction_id=transaction_id, org_id=org_id, rule_id=rule_id, rule_output=gate.rule_output,
                )
                return

            parent_carrier = gate_carrier  # keep the chain going through the gate span

        with start_span("worker.process_payload", carrier=parent_carrier, transaction_id=transaction_id, org_id=org_id) as process_span:
            tx.update_transaction(transaction_id, status="processing")
            log_event("info", "Worker: processing event", transaction_id=transaction_id, org_id=org_id)

            mode_override, processor_override = _resolve_processing(org_id, source_channel)

            try:
                # process_payload is itself async now and decides its own
                # threading/async strategy per mode (subprocess+thread for
                # custom_script/dss_client, native async task for langflow,
                # instant for local) - no to_thread wrapper needed here.
                result = await process_payload(payload, mode_override, processor_override, org_id, transaction_id)
            except (proc_module.ProcessorCancelled, dss_runner.DSSClientCancelled, OperationCancelled):
                tx.update_transaction(transaction_id, status="cancelled", error="Cancelled during processing")
                log_event("warning", "Worker: processing was cancelled", transaction_id=transaction_id)
                return
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Worker: processing failed: {exc}", transaction_id=transaction_id)
                failed_tx = tx.get_transaction(transaction_id)
                fail_carrier = inject_trace_context(span=process_span) or parent_carrier
                await asyncio.to_thread(dispatch_integrations, failed_tx, None, fail_carrier)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            # Soft-cancel checkpoint: cancellation was requested while this
            # was running, but the processing mode couldn't be hard-killed
            # (only custom_script subprocesses can be - see ProcessorCancelled
            # above). Honor it now rather than proceeding to publish a result
            # for a transaction the admin asked to stop.
            if tx.get_transaction(transaction_id).get("cancel_requested"):
                tx.update_transaction(transaction_id, status="cancelled", error="Cancelled after processing completed")
                log_event("warning", "Worker: honoring cancellation requested during processing", transaction_id=transaction_id)
                return

            tx.update_transaction(transaction_id, status="processed", result=result)

        # process_span's `with` block has closed by this point, but the span
        # object itself is still valid to read a fresh carrier from - this is
        # what lets the NEXT broker hop (outbound publish) continue the same trace.
        next_carrier = inject_trace_context(span=process_span) or parent_carrier

        routed_channels, routed_integration_ids, _ = _resolve_routes(org_id, source_channel)

        if not _resolve_auto_publish(org_id, source_channel):
            # This channel is configured to process events without
            # automatically publishing the result back to Salesforce.
            # "processed" is the terminal state here - still fan out to any
            # routed (or globally auto-matched) integrations/alerts off of
            # it, since those don't require a publish step to have meaning.
            log_event(
                "info",
                "Worker: auto-publish is disabled for this channel; result will not be sent back to Salesforce",
                transaction_id=transaction_id, org_id=org_id, channel=source_channel,
            )
            processed_tx = tx.get_transaction(transaction_id)
            await asyncio.to_thread(dispatch_integrations, processed_tx, routed_integration_ids, next_carrier)
            await asyncio.to_thread(fire_alert_for_transaction, processed_tx, routed_alert_ids)
            return

        if routed_channels:
            # Explicit fan-out: publish the same result to every selected
            # channel, each tracked as its own transaction so success/failure
            # of one delivery is independent of the others.
            for channel in routed_channels:
                fanout_record = tx.record_transaction(
                    org_id=org_id, org_name=None, direction="publish", channel=channel,
                    status="queued", payload=result, parent_transaction_id=transaction_id,
                )
                await broker.publish(
                    "outbound",
                    {
                        "transaction_id": fanout_record["id"],
                        "org_id": org_id,
                        "channel": channel,
                        "payload": result,
                        "routed_integration_ids": routed_integration_ids,
                        "routed_alert_ids": routed_alert_ids,
                        "_trace": next_carrier,
                    },
                )
            log_event("info", f"Worker: fanned out to {len(routed_channels)} publish channel(s)", transaction_id=transaction_id)
        else:
            publish_channel = _default_publish_channel(org_id)
            if publish_channel:
                await broker.publish(
                    "outbound",
                    {
                        "transaction_id": transaction_id,
                        "org_id": org_id,
                        "channel": publish_channel,
                        "payload": result,
                        "routed_integration_ids": routed_integration_ids,
                        "routed_alert_ids": routed_alert_ids,
                        "_trace": next_carrier,
                    },
                )
            else:
                log_event(
                    "warning",
                    "Worker: no publish channel configured for org; result will not be sent back to Salesforce",
                    org_id=org_id,
                )
                no_channel_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, no_channel_tx, routed_integration_ids, next_carrier)
                await asyncio.to_thread(fire_alert_for_transaction, no_channel_tx, routed_alert_ids)

    await broker.consume_forever("inbound", handle)


async def outbound_publisher():
    """Consumes 'outbound' topic messages and publishes them back to Salesforce."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        channel = message["channel"]
        payload = message["payload"]
        routed_integration_ids = message.get("routed_integration_ids")
        routed_alert_ids = message.get("routed_alert_ids")
        parent_carrier = message.get("_trace")

        # Cancellation checkpoint: may have been cancelled while sitting in
        # the outbound queue, or flagged while it was still being processed
        # upstream (auto-publish path) - honor it before attempting to
        # publish rather than sending it to Salesforce anyway.
        current = tx.get_transaction(transaction_id)
        if current and (current.get("status") == "cancelled" or current.get("cancel_requested")):
            tx.update_transaction(transaction_id, status="cancelled", error="Cancelled before publishing to Salesforce")
            log_event("warning", "Worker: skipping publish for cancelled transaction", transaction_id=transaction_id)
            return

        with start_span("worker.publish_to_salesforce", carrier=parent_carrier, transaction_id=transaction_id, org_id=org_id, channel=channel) as publish_span:
            org = orgs_table.get(Q.id == org_id)
            if not org:
                tx.update_transaction(transaction_id, status="failed", error="Org no longer exists")
                failed_tx = tx.get_transaction(transaction_id)
                fail_carrier = inject_trace_context(span=publish_span) or parent_carrier
                await asyncio.to_thread(dispatch_integrations, failed_tx, routed_integration_ids, fail_carrier)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            if not tx.get_transaction(transaction_id).get("org_name"):
                tx.update_transaction(transaction_id, org_name=org["name"])

            tx.update_transaction(transaction_id, status="publishing")
            try:
                # Native async now (httpx), run as a registered, genuinely
                # cancellable task - a cancellation requested during this
                # call now aborts the actual in-flight HTTP request instead
                # of waiting for it to finish first.
                await _run_cancellable(sf_client.publish_platform_event(org, channel, payload), transaction_id)
                if tx.get_transaction(transaction_id).get("cancel_requested"):
                    tx.update_transaction(transaction_id, status="cancelled", error="Cancelled during publish (Salesforce may still have received it)")
                    log_event("warning", "Worker: honoring cancellation requested during publish", transaction_id=transaction_id)
                else:
                    tx.update_transaction(transaction_id, status="published")
                    log_event("info", "Publisher: event published back to Salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel)
            except OperationCancelled:
                tx.update_transaction(transaction_id, status="cancelled", error="Cancelled during publish (Salesforce may still have received it)")
                log_event("warning", "Publisher: publish cancelled mid-flight", transaction_id=transaction_id)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Publisher: failed to publish to Salesforce: {exc}", transaction_id=transaction_id)

        final_carrier = inject_trace_context(span=publish_span) or parent_carrier
        final_tx = tx.get_transaction(transaction_id)
        await asyncio.to_thread(dispatch_integrations, final_tx, routed_integration_ids, final_carrier)
        await asyncio.to_thread(fire_alert_for_transaction, final_tx, routed_alert_ids)

    await broker.consume_forever("outbound", handle)


async def reprocess_transaction(transaction_id: str) -> dict:
    """
    Re-drive a transaction back through the broker so it can be handled again.

    - A 'subscribe' transaction that already has a processed `result` (i.e. it
      failed only at the publish-back-to-Salesforce step) is requeued straight
      onto the 'outbound' topic with that same result, so it isn't reprocessed
      twice.
    - A 'subscribe' transaction that never made it past processing (or has no
      stored result) is requeued onto the 'inbound' topic to run through
      `process_payload` again from scratch, using its original payload.
    - A 'publish' transaction (a manual/outbound-only event) is requeued
      directly onto the 'outbound' topic with its original payload.

    In every case the transaction's existing record is reused (its status/
    error are reset) rather than creating a new transaction, so the audit
    trail shows the retry history on the same row.
    """
    record = tx.get_transaction(transaction_id)
    if not record:
        raise ValueError("Transaction not found")

    org_id = record["org_id"]
    channel = record["channel"]
    attempts = record.get("attempts", 0) + 1

    if record["direction"] == "publish":
        tx.update_transaction(transaction_id, status="publishing", error=None, attempts=attempts)
        await broker.publish(
            "outbound",
            {"transaction_id": transaction_id, "org_id": org_id, "channel": channel, "payload": record["payload"]},
        )
        log_event("info", f"Transaction requeued to outbound for republish (attempt {attempts})", transaction_id=transaction_id)

    elif record.get("result"):
        publish_channel = _default_publish_channel(org_id) or channel
        tx.update_transaction(transaction_id, status="publishing", error=None, attempts=attempts)
        await broker.publish(
            "outbound",
            {"transaction_id": transaction_id, "org_id": org_id, "channel": publish_channel, "payload": record["result"]},
        )
        log_event("info", f"Transaction requeued to outbound using existing processed result (attempt {attempts})", transaction_id=transaction_id)

    else:
        tx.update_transaction(transaction_id, status="queued", error=None, result=None, attempts=attempts)
        await broker.publish(
            "inbound",
            {"transaction_id": transaction_id, "org_id": org_id, "channel": channel, "payload": record["payload"]},
        )
        log_event("info", f"Transaction requeued to inbound for full reprocessing (attempt {attempts})", transaction_id=transaction_id)

    return tx.get_transaction(transaction_id)


async def publish_manual_event(org_id: str, channel: str, payload: dict) -> dict:
    """Used by the admin API to let a user manually push an event to Salesforce
    outside of the automatic inbound->process->outbound pipeline."""
    org = orgs_table.get(Q.id == org_id)
    if not org:
        raise ValueError("Org not found")

    record = tx.record_transaction(
        org_id=org_id, org_name=org["name"], direction="publish", channel=channel,
        status="publishing", payload=payload,
    )
    with start_span("worker.publish_manual_event", transaction_id=record["id"], org_id=org_id, channel=channel) as manual_span:
        try:
            result = await sf_client.publish_platform_event(org, channel, payload)
            tx.update_transaction(record["id"], status="published", result=result)
        except Exception as exc:  # noqa: BLE001
            tx.update_transaction(record["id"], status="failed", error=str(exc))
            failed_tx = tx.get_transaction(record["id"])
            fail_carrier = inject_trace_context(span=manual_span)
            await asyncio.to_thread(dispatch_integrations, failed_tx, None, fail_carrier)
            await asyncio.to_thread(fire_alert_for_transaction, failed_tx)
            raise
    final_tx = tx.get_transaction(record["id"])
    final_carrier = inject_trace_context(span=manual_span)
    await asyncio.to_thread(dispatch_integrations, final_tx, None, final_carrier)
    await asyncio.to_thread(fire_alert_for_transaction, final_tx)
    return record
