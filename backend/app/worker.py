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
from .tracing import start_span
from .integrations import dispatch_integrations
from .alerts import fire_alert_for_transaction

# Several integrations/DSSClient deployments sit behind internally-issued or
# self-signed certificates; disabling verification is a deliberate operator
# choice (see integrations.py and the dss_client branch below) so we also
# silence the resulting urllib3 warning spam globally.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_dss_client(payload: dict) -> dict:
    """Calls a Dataiku DSS LLM endpoint via `dataikuapi`. Raises on failure -
    callers decide whether to fall back or propagate (process_payload falls
    back to local; the direct /api/execute/dss-client endpoint propagates so
    the caller sees the real error)."""
    import dataikuapi  # imported lazily so the app still runs if this optional dependency isn't installed
    from .routers.admin_config import get_dss_client_config_raw

    config = get_dss_client_config_raw()
    conversation_id = payload.get("Conversation_Id__c")

    if not config.get("url"):
        raise RuntimeError("DSSClient is not configured (no URL set in Admin Configuration)")

    end_user_client = dataikuapi.DSSClient(
        config.get("url"), config.get("api_key"), no_check_certificate=True,
    )
    agent = end_user_client.get_project(config["project_name"]).get_llm(config["llm"])
    completion = agent.new_completion()
    completion.with_message(payload.get("User_Message__c", ""))
    response = completion.execute()

    return {
        "Conversation_Id__c": conversation_id,
        "Status__c": "Ok",
        "Payload_Json__c": json.dumps({"replyText": response.text}),
    }


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


def run_langflow(payload: dict) -> dict:
    """Calls a Langflow flow's /api/v1/run/{flow_id} endpoint. Raises on
    failure - see `run_dss_client` docstring for why."""
    import requests as _requests
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
    resp = _requests.post(url, json=body, headers=headers, timeout=60, verify=False)
    resp.raise_for_status()
    response_json = resp.json()

    text = _extract_langflow_text(response_json, config.get("output_path", ""))
    return {
        "status": "ok",
        "summary": "Event processed by Langflow",
        "reply": text,
        "raw": response_json,
    }


def process_payload(payload: dict, mode_override: Optional[str] = None, processor_id_override: Optional[str] = None, org_id: Optional[str] = None) -> dict:
    """
    Business / AI processing logic for every inbound event.

    Which processing mode runs is controlled by Admin Configuration ->
    Payload Processors by default, but an individual subscribed event
    channel can override it (see `_resolve_processing`):
      - "local"          : simple built-in echo/fallback (default)
      - "dss_client"     : calls into a Dataiku DSS LLM endpoint via
                            `dataikuapi.DSSClient(...).get_project(...).get_llm(...)`
      - "custom_script"  : runs the currently-active (or per-event-selected)
                            uploaded Python script in an isolated subprocess.
                            `org_id` (the triggering event's Salesforce org,
                            when known) is made available to the script via
                            environment variables - see `processors.py:_build_processor_env`.
      - "langflow"        : calls a Langflow flow's /run endpoint

    (The rule engine is NOT a processing mode - it's a pre-processing gate
    that decides whether an event gets processed at all. See
    `_resolve_rule_gate` and its use in `inbound_worker`.)

    Any failure in dss_client/custom_script/langflow mode falls back to a
    local result so the pipeline never breaks because of a downstream outage
    or a bug in an uploaded script.
    """
    from .routers.admin_config import get_processing_mode_raw  # local import avoids a circular import at module load time
    from . import processors as proc_module

    if mode_override:
        mode = mode_override
        active_processor_id = processor_id_override
    else:
        mode_cfg = get_processing_mode_raw()
        mode = mode_cfg.get("mode", "local")
        active_processor_id = mode_cfg.get("active_processor_id")

    if mode == "custom_script" and active_processor_id:
        try:
            return proc_module.run_processor(active_processor_id, payload, org_id)
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
            return run_dss_client(payload)
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
            return run_langflow(payload)
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

        _, _, routed_alert_ids = _resolve_routes(org_id, source_channel)

        # Validation gate: if this channel has a rule assigned, it runs
        # BEFORE any processing - a "false" result skips processing entirely
        # (the event is still recorded, just never handed to
        # process_payload or published). This is deliberately separate from
        # the processing modes below.
        rule_id = _resolve_rule_gate(org_id, source_channel)
        if rule_id:
            with start_span("worker.rule_gate", transaction_id=transaction_id, org_id=org_id, rule_id=rule_id):
                gate = await asyncio.to_thread(evaluate_rule_gate, rule_id, payload)

            if gate.error:
                tx.update_transaction(transaction_id, status="failed", error=f"Rule gate evaluation failed: {gate.error}")
                log_event("error", f"Worker: rule gate evaluation failed: {gate.error}", transaction_id=transaction_id, rule_id=rule_id)
                failed_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, failed_tx)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            if not gate.should_process:
                tx.update_transaction(transaction_id, status="skipped", result=gate.rule_output)
                log_event(
                    "info", "Worker: rule gate decided this event should not be processed",
                    transaction_id=transaction_id, org_id=org_id, rule_id=rule_id, rule_output=gate.rule_output,
                )
                return

        with start_span("worker.process_payload", transaction_id=transaction_id, org_id=org_id):
            tx.update_transaction(transaction_id, status="processing")
            log_event("info", "Worker: processing event", transaction_id=transaction_id, org_id=org_id)

            mode_override, processor_override = _resolve_processing(org_id, source_channel)

            try:
                # Offloaded to a thread: process_payload may do blocking HTTP/
                # subprocess work and must never stall the web app's event loop.
                result = await asyncio.to_thread(process_payload, payload, mode_override, processor_override, org_id)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Worker: processing failed: {exc}", transaction_id=transaction_id)
                failed_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, failed_tx)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            tx.update_transaction(transaction_id, status="processed", result=result)

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
            await asyncio.to_thread(dispatch_integrations, processed_tx, routed_integration_ids)
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
                    },
                )
            else:
                log_event(
                    "warning",
                    "Worker: no publish channel configured for org; result will not be sent back to Salesforce",
                    org_id=org_id,
                )
                no_channel_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, no_channel_tx, routed_integration_ids)
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

        with start_span("worker.publish_to_salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel):
            org = orgs_table.get(Q.id == org_id)
            if not org:
                tx.update_transaction(transaction_id, status="failed", error="Org no longer exists")
                failed_tx = tx.get_transaction(transaction_id)
                await asyncio.to_thread(dispatch_integrations, failed_tx, routed_integration_ids)
                await asyncio.to_thread(fire_alert_for_transaction, failed_tx, routed_alert_ids)
                return

            if not tx.get_transaction(transaction_id).get("org_name"):
                tx.update_transaction(transaction_id, org_name=org["name"])

            tx.update_transaction(transaction_id, status="publishing")
            try:
                # Offloaded to a thread: this is a blocking `requests` call.
                await asyncio.to_thread(sf_client.publish_platform_event, org, channel, payload)
                tx.update_transaction(transaction_id, status="published")
                log_event("info", "Publisher: event published back to Salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Publisher: failed to publish to Salesforce: {exc}", transaction_id=transaction_id)

        final_tx = tx.get_transaction(transaction_id)
        await asyncio.to_thread(dispatch_integrations, final_tx, routed_integration_ids)
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
    with start_span("worker.publish_manual_event", transaction_id=record["id"], org_id=org_id, channel=channel):
        try:
            result = await asyncio.to_thread(sf_client.publish_platform_event, org, channel, payload)
            tx.update_transaction(record["id"], status="published", result=result)
        except Exception as exc:  # noqa: BLE001
            tx.update_transaction(record["id"], status="failed", error=str(exc))
            failed_tx = tx.get_transaction(record["id"])
            await asyncio.to_thread(dispatch_integrations, failed_tx)
            await asyncio.to_thread(fire_alert_for_transaction, failed_tx)
            raise
    final_tx = tx.get_transaction(record["id"])
    await asyncio.to_thread(dispatch_integrations, final_tx)
    await asyncio.to_thread(fire_alert_for_transaction, final_tx)
    return record
