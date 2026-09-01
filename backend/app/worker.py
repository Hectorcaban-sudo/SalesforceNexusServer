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
"""
from typing import Optional
import requests
from .broker import broker
from .database import orgs_table, event_configs_table, Q
from .logging_config import log_event
from . import transactions as tx
from .salesforce_client import sf_client
from .tracing import start_span
from .integrations import dispatch_integrations


def process_payload(payload: dict) -> dict:
    """
    Business / AI processing logic for every inbound event.

    Which processing mode runs is controlled by Admin Configuration ->
    Payload Processors:
      - "local"          : simple built-in echo/fallback (default)
      - "dss_client"     : forwards the payload to the configured DSSClient
                            HTTP endpoint and returns its JSON response
      - "custom_script"  : runs the currently-active uploaded Python script
                            in an isolated subprocess and returns its result

    Any failure in dss_client/custom_script mode falls back to the local
    result so the pipeline never breaks because of a downstream outage or a
    bug in an uploaded script.
    """
    from .routers.admin_config import get_dss_client_config_raw, get_processing_mode_raw  # local import avoids a circular import at module load time
    from . import processors as proc_module

    mode_cfg = get_processing_mode_raw()
    mode = mode_cfg.get("mode", "local")

    if mode == "custom_script" and mode_cfg.get("active_processor_id"):
        try:
            return proc_module.run_processor(mode_cfg["active_processor_id"], payload)
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"Custom processor failed, falling back to local processing: {exc}")
            return {
                "status": "error",
                "summary": "Custom processor failed; returning local fallback result",
                "error": str(exc),
                "echo": payload,
            }

    if mode == "dss_client":
        config = get_dss_client_config_raw()
        if not config.get("url"):
            return {
                "status": "ok",
                "summary": "Event processed by Salesforce Nexus AI Server (no DSSClient configured)",
                "echo": payload,
            }
        try:
            response = requests.post(
                config["url"],
                json={
                    "project": config.get("project_name", ""),
                    "llm": config.get("llm", ""),
                    "input": payload,
                },
                headers={"Authorization": f"Bearer {config.get('api_key', '')}"},
                timeout=20,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"DSSClient call failed, falling back to local processing: {exc}")
            return {
                "status": "error",
                "summary": "DSSClient call failed; returning local fallback result",
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


def _resolve_routes(org_id: str, source_channel: str):
    """Looks up the subscribe event config that triggered this event to find
    its explicit routing selections (publish channels + integrations). Falls
    back to (None, None) when no explicit routing is configured, so callers
    know to use legacy single-channel/auto-match behavior instead."""
    source_cfg = event_configs_table.get(
        (Q.org_id == org_id) & (Q.channel == source_channel) & (Q.direction == "subscribe")
    )
    if not source_cfg:
        return [], None

    publish_ids = source_cfg.get("route_publish_channel_ids") or []
    integration_ids = source_cfg.get("route_integration_ids") or None  # None = no explicit selection -> legacy auto-match

    publish_channels = []
    for pid in publish_ids:
        cfg = event_configs_table.get(Q.id == pid)
        if cfg and cfg.get("enabled") and cfg.get("direction") == "publish":
            publish_channels.append(cfg["channel"])

    return publish_channels, integration_ids


async def inbound_worker():
    """Consumes 'inbound' topic messages forever - the internal function."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        source_channel = message["channel"]
        payload = message["payload"]

        with start_span("worker.process_payload", transaction_id=transaction_id, org_id=org_id):
            tx.update_transaction(transaction_id, status="processing")
            log_event("info", "Worker: processing event", transaction_id=transaction_id, org_id=org_id)

            try:
                result = process_payload(payload)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Worker: processing failed: {exc}", transaction_id=transaction_id)
                dispatch_integrations(tx.get_transaction(transaction_id))
                return

            tx.update_transaction(transaction_id, status="processed", result=result)

        routed_channels, routed_integration_ids = _resolve_routes(org_id, source_channel)

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
                    },
                )
            else:
                log_event(
                    "warning",
                    "Worker: no publish channel configured for org; result will not be sent back to Salesforce",
                    org_id=org_id,
                )
                dispatch_integrations(tx.get_transaction(transaction_id), only_ids=routed_integration_ids)

    await broker.consume_forever("inbound", handle)


async def outbound_publisher():
    """Consumes 'outbound' topic messages and publishes them back to Salesforce."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        channel = message["channel"]
        payload = message["payload"]
        routed_integration_ids = message.get("routed_integration_ids")

        with start_span("worker.publish_to_salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel):
            org = orgs_table.get(Q.id == org_id)
            if not org:
                tx.update_transaction(transaction_id, status="failed", error="Org no longer exists")
                dispatch_integrations(tx.get_transaction(transaction_id), only_ids=routed_integration_ids)
                return

            if not tx.get_transaction(transaction_id).get("org_name"):
                tx.update_transaction(transaction_id, org_name=org["name"])

            tx.update_transaction(transaction_id, status="publishing")
            try:
                sf_client.publish_platform_event(org, channel, payload)
                tx.update_transaction(transaction_id, status="published")
                log_event("info", "Publisher: event published back to Salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel)
            except Exception as exc:  # noqa: BLE001
                tx.update_transaction(transaction_id, status="failed", error=str(exc))
                log_event("error", f"Publisher: failed to publish to Salesforce: {exc}", transaction_id=transaction_id)

        dispatch_integrations(tx.get_transaction(transaction_id), only_ids=routed_integration_ids)

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
            result = sf_client.publish_platform_event(org, channel, payload)
            tx.update_transaction(record["id"], status="published", result=result)
        except Exception as exc:  # noqa: BLE001
            tx.update_transaction(record["id"], status="failed", error=str(exc))
            dispatch_integrations(tx.get_transaction(record["id"]))
            raise
    dispatch_integrations(tx.get_transaction(record["id"]))
    return record
