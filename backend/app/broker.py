"""
Message broker abstraction.

This decouples the CometD Salesforce listener from the "internal function"
that processes events, and decouples that processor from the component that
publishes results back to Salesforce.

Two backends are available, chosen from Admin Configuration -> Message Broker
(admin_settings id="broker_config"):

  - "internal" (default): in-process asyncio queues. Zero external infra,
    but messages are lost if the process restarts mid-flight and this only
    works for a single running instance.
  - "rabbitmq": a real RabbitMQ broker via `aio-pika`, so multiple app
    instances could eventually share the same queues and messages survive a
    restart (RabbitMQ persists them).

Every other module (`worker.py`, `cometd_client.py`, routers) imports the
single module-level `broker` object below and only ever calls
`publish()`/`consume_forever()`/`queue_depth()` on it - they never know or
care which backend is actually active. That's done via a small proxy object
whose internal implementation is swapped out once at startup based on the
admin_settings config (see `configure_from_settings()`, called from
main.py's lifespan startup) - switching backends takes effect on next
restart, it does not hot-swap a running broker out from under in-flight
messages.
"""
import asyncio
import json
from typing import Dict, Callable, Awaitable, Any, Optional

from .config import settings
from .logging_config import log_event

BROKER_CONFIG_ID = "broker_config"


# ---------------------------------------------------------------- in-memory
class InMemoryBroker:
    def __init__(self, max_queue: int = 10000):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._max_queue = max_queue

    def _get_queue(self, topic: str) -> asyncio.Queue:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue(maxsize=self._max_queue)
        return self._queues[topic]

    async def publish(self, topic: str, message: dict):
        queue = self._get_queue(topic)
        await queue.put(message)
        log_event("debug", f"Broker: message published to topic '{topic}'", topic=topic)

    async def consume_forever(self, topic: str, handler: Callable[[dict], Awaitable[Any]]):
        """
        Pulls messages off the queue as fast as they arrive and hands each
        one to `handler` as an independent concurrent task, instead of
        awaiting each handler to finish before dequeuing the next message.
        A semaphore bounds how many run at once (settings.worker_max_concurrency)
        so a burst of events can't spawn unbounded threads/tasks - once the
        limit is hit, newly dequeued messages simply wait their turn on the
        semaphore while already-running ones continue, rather than blocking
        the dequeue loop itself.
        """
        queue = self._get_queue(topic)
        semaphore = asyncio.Semaphore(settings.worker_max_concurrency)

        async def run_one(message: dict):
            async with semaphore:
                try:
                    await handler(message)
                except Exception as exc:  # noqa: BLE001
                    log_event("error", f"Broker: handler for topic '{topic}' raised an exception: {exc}", topic=topic)
                finally:
                    queue.task_done()

        while True:
            message = await queue.get()
            asyncio.create_task(run_one(message))

    def queue_depth(self, topic: str) -> int:
        return self._get_queue(topic).qsize()

    async def close(self):
        pass


# ------------------------------------------------------------------ RabbitMQ
class RabbitMQBroker:
    """Backs each topic with a durable RabbitMQ queue (via the default
    exchange, routing key == queue name - the simplest reliable point-to-point
    pattern, equivalent to what most brokers call a "work queue")."""

    def __init__(self, rmq_config: dict):
        self._config = rmq_config
        self._connection = None
        self._channel = None
        self._queues: Dict[str, Any] = {}

    def _url(self) -> str:
        scheme = "amqps" if self._config.get("use_tls") else "amqp"
        host = self._config.get("host", "localhost")
        port = self._config.get("port") or (5671 if self._config.get("use_tls") else 5672)
        user = self._config.get("username", "guest")
        password = self._config.get("password", "guest")
        vhost = self._config.get("vhost", "/").lstrip("/")
        return f"{scheme}://{user}:{password}@{host}:{port}/{vhost}"

    async def connect(self):
        import aio_pika
        self._connection = await aio_pika.connect_robust(self._url())
        self._channel = await self._connection.channel()
        # Prefetch at least as many unacked messages as we're willing to
        # process concurrently, or RabbitMQ will only ever hand us one at a
        # time regardless of how the consumer loop is written below.
        await self._channel.set_qos(prefetch_count=max(settings.worker_max_concurrency, 10))
        log_event("info", f"RabbitMQ broker connected to {self._config.get('host')}:{self._config.get('port')}")

    async def _get_queue(self, topic: str):
        if topic not in self._queues:
            self._queues[topic] = await self._channel.declare_queue(topic, durable=True)
        return self._queues[topic]

    async def publish(self, topic: str, message: dict):
        import aio_pika
        await self._get_queue(topic)  # ensure it exists before publishing
        body = json.dumps(message).encode("utf-8")
        await self._channel.default_exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=topic,
        )
        log_event("debug", f"Broker (RabbitMQ): message published to topic '{topic}'", topic=topic)

    async def consume_forever(self, topic: str, handler: Callable[[dict], Awaitable[Any]]):
        """Same bounded-concurrency approach as InMemoryBroker.consume_forever
        - each message is handed to an independent task rather than awaited
        in-line, so multiple events can be in flight at once."""
        queue = await self._get_queue(topic)
        semaphore = asyncio.Semaphore(settings.worker_max_concurrency)

        async def process_one(message):
            async with semaphore:
                async with message.process():
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                        await handler(payload)
                    except Exception as exc:  # noqa: BLE001
                        log_event("error", f"Broker (RabbitMQ): handler for topic '{topic}' raised an exception: {exc}", topic=topic)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                asyncio.create_task(process_one(message))

    def queue_depth(self, topic: str) -> int:
        # aio-pika queue objects expose declaration_result.message_count only
        # right after declare; treat as "unknown" (0) rather than blocking on
        # a fresh synchronous re-declare from a sync call site.
        q = self._queues.get(topic)
        if q is not None and hasattr(q, "declaration_result") and q.declaration_result:
            return q.declaration_result.message_count or 0
        return 0

    async def close(self):
        if self._connection:
            await self._connection.close()


# --------------------------------------------------------------------- proxy
class BrokerProxy:
    """Stable object every other module imports. Internally delegates to
    whichever backend was configured at startup."""

    def __init__(self):
        self._impl = InMemoryBroker(max_queue=settings.broker_max_queue)
        self.backend_name = "internal"
        self.last_error: Optional[str] = None

    async def configure_from_settings(self):
        from .database import admin_settings_table, Q  # local import avoids a circular import at module load time

        cfg = admin_settings_table.get(Q.id == BROKER_CONFIG_ID) or {"type": "internal"}

        if cfg.get("type") == "rabbitmq":
            try:
                impl = RabbitMQBroker(cfg.get("rabbitmq", {}))
                await impl.connect()
                old_impl = self._impl
                self._impl = impl
                self.backend_name = "rabbitmq"
                self.last_error = None
                if hasattr(old_impl, "close"):
                    await old_impl.close()
                return
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                log_event("error", f"Failed to connect to RabbitMQ, falling back to internal broker: {exc}")
                try:
                    from .alerts import fire_alert  # local import avoids a circular import at module load time
                    fire_alert("broker_degraded", {"error": str(exc)})
                except Exception:  # noqa: BLE001
                    pass  # alert delivery must never prevent broker startup fallback

        self._impl = InMemoryBroker(max_queue=settings.broker_max_queue)
        self.backend_name = "internal"

    async def publish(self, topic: str, message: dict):
        await self._impl.publish(topic, message)

    async def consume_forever(self, topic: str, handler: Callable[[dict], Awaitable[Any]]):
        await self._impl.consume_forever(topic, handler)

    def queue_depth(self, topic: str) -> int:
        return self._impl.queue_depth(topic)

    async def close(self):
        await self._impl.close()


broker = BrokerProxy()
