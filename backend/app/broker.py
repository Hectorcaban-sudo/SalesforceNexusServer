"""
Internal message broker.

This decouples the CometD Salesforce listener from the "internal function"
that processes events, and decouples that processor from the component that
publishes results back to Salesforce. It is implemented with in-process
asyncio queues (topic -> queue) so the whole app runs with zero external
infra, but it is written behind a small interface so it could be swapped for
a real broker (Kafka/RabbitMQ/SQS/etc.) later without touching callers.

Topics used by the app:
  - "inbound.<org_id>"   : raw platform events received from Salesforce via CometD
  - "outbound.<org_id>"  : processed results ready to be published back to Salesforce
"""
import asyncio
from typing import Dict, Callable, Awaitable, Any
from .config import settings
from .logging_config import log_event


class InMemoryBroker:
    def __init__(self, max_queue: int = 10000):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._max_queue = max_queue
        self._subscribers: Dict[str, list] = {}

    def _get_queue(self, topic: str) -> asyncio.Queue:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue(maxsize=self._max_queue)
        return self._queues[topic]

    async def publish(self, topic: str, message: dict):
        queue = self._get_queue(topic)
        await queue.put(message)
        log_event("debug", f"Broker: message published to topic '{topic}'", topic=topic)

    async def consume_forever(
        self, topic: str, handler: Callable[[dict], Awaitable[Any]]
    ):
        """Continuously pop messages from `topic` and pass to async `handler`."""
        queue = self._get_queue(topic)
        while True:
            message = await queue.get()
            try:
                await handler(message)
            except Exception as exc:  # noqa: BLE001
                log_event(
                    "error",
                    f"Broker: handler for topic '{topic}' raised an exception: {exc}",
                    topic=topic,
                )
            finally:
                queue.task_done()

    def queue_depth(self, topic: str) -> int:
        return self._get_queue(topic).qsize()

    def all_topics(self):
        return list(self._queues.keys())


broker = InMemoryBroker(max_queue=settings.broker_max_queue)
