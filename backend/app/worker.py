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
from .broker import broker
from .database import orgs_table, event_configs_table, Q
from .logging_config import log_event
from . import transactions as tx
from .salesforce_client import sf_client


def process_payload(payload: dict) -> dict:
    """
    Placeholder for the real business / AI processing logic.
    Replace this function with a call into your model, rules engine, or
    downstream service. It must return a JSON-serialisable dict.
    """
    return {
        "status": "ok",
        "summary": "Event processed by Salesforce Nexus AI Server",
        "echo": payload,
    }


def _default_publish_channel(org_id: str) -> Optional[str]:
    row = event_configs_table.get(
        (Q.org_id == org_id) & (Q.direction == "publish") & (Q.enabled == True)  # noqa: E712
    )
    return row["channel"] if row else None


async def inbound_worker():
    """Consumes 'inbound' topic messages forever - the internal function."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        payload = message["payload"]

        tx.update_transaction(transaction_id, status="processing")
        log_event("info", "Worker: processing event", transaction_id=transaction_id, org_id=org_id)

        try:
            result = process_payload(payload)
        except Exception as exc:  # noqa: BLE001
            tx.update_transaction(transaction_id, status="failed", error=str(exc))
            log_event("error", f"Worker: processing failed: {exc}", transaction_id=transaction_id)
            return

        tx.update_transaction(transaction_id, status="processed", result=result)

        publish_channel = _default_publish_channel(org_id)
        if publish_channel:
            await broker.publish(
                "outbound",
                {
                    "transaction_id": transaction_id,
                    "org_id": org_id,
                    "channel": publish_channel,
                    "payload": result,
                },
            )
        else:
            log_event(
                "warning",
                "Worker: no publish channel configured for org; result will not be sent back to Salesforce",
                org_id=org_id,
            )

    await broker.consume_forever("inbound", handle)


async def outbound_publisher():
    """Consumes 'outbound' topic messages and publishes them back to Salesforce."""

    async def handle(message: dict):
        transaction_id = message["transaction_id"]
        org_id = message["org_id"]
        channel = message["channel"]
        payload = message["payload"]

        org = orgs_table.get(Q.id == org_id)
        if not org:
            tx.update_transaction(transaction_id, status="failed", error="Org no longer exists")
            return

        tx.update_transaction(transaction_id, status="publishing")
        try:
            sf_client.publish_platform_event(org, channel, payload)
            tx.update_transaction(transaction_id, status="published")
            log_event("info", "Publisher: event published back to Salesforce", transaction_id=transaction_id, org_id=org_id, channel=channel)
        except Exception as exc:  # noqa: BLE001
            tx.update_transaction(transaction_id, status="failed", error=str(exc))
            log_event("error", f"Publisher: failed to publish to Salesforce: {exc}", transaction_id=transaction_id)

    await broker.consume_forever("outbound", handle)


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
    try:
        result = sf_client.publish_platform_event(org, channel, payload)
        tx.update_transaction(record["id"], status="published", result=result)
    except Exception as exc:  # noqa: BLE001
        tx.update_transaction(record["id"], status="failed", error=str(exc))
        raise
    return record
