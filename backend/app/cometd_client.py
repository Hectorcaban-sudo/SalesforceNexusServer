"""
CometD (Bayeux protocol) client used to subscribe to Salesforce Platform
Events / Change Data Capture / custom streaming channels.

For each active org this module:
  1. Authenticates via `salesforce_client` to obtain a session token.
  2. Opens a CometD long-polling connection to
     `{instance_url}/cometd/{api_version}/`.
  3. Subscribes to every channel configured with direction=subscribe for
     that org.
  4. On every message received, records a transaction and publishes the
     raw event onto the internal broker's `inbound.<org_id>` topic for the
     worker to process.

Connections are managed per-org and can be started/stopped independently so
admins can add/remove orgs and channels at runtime without restarting the
whole server.
"""
import asyncio
from typing import Dict, Optional

try:
    # Primary target: aiocometd_ng (actively maintained fork, required on
    # newer Python versions where the original `aiocometd` package may not
    # install cleanly).
    from aiocometd_ng import Client, ConnectionType
    from aiocometd_ng.extensions import AuthExtension
except ImportError:  # pragma: no cover - fallback for environments with the original package
    from aiocometd import Client, ConnectionType
    from aiocometd.extensions import AuthExtension

from .config import settings
from .salesforce_client import sf_client, SalesforceAuthError
from .broker import broker
from .logging_config import log_event
from .database import orgs_table, event_configs_table, Q
from . import transactions as tx
from .tracing import start_span


class SalesforceAuthHeaderExtension(AuthExtension):
    """Injects the Salesforce OAuth bearer token into every CometD request."""

    def __init__(self, token_provider):
        self._token_provider = token_provider

    async def incoming(self, payload, headers=None):
        return None

    async def outgoing(self, payload, headers=None):
        if headers is not None:
            headers["Authorization"] = f"Bearer {self._token_provider()}"

    async def authenticate(self):
        return None


class OrgStreamManager:
    """Owns the CometD connection + subscription task for a single org.

    Runs a persistent supervisor loop: if the connection is lost or fails to
    establish for any reason (network blip, Salesforce-side restart, auth
    token expiry, etc.) it is retried automatically with exponential backoff
    rather than giving up - the org just shows as "error"/"connecting" in the
    admin UI until it recovers. Every blocking call (Salesforce OAuth login)
    is offloaded to a thread so a slow/hanging network call here can never
    freeze the rest of the web app, which keeps running and stays fully
    navigable throughout.
    """

    def __init__(self, org: dict):
        self.org = org
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[Client] = None
        self._running = False
        self._stopped = False
        self._alert_fired_for_current_outage = False

    @property
    def status(self) -> str:
        if self._running and self._client:
            return "connected"
        if self._task and not self._task.done() and not self._stopped:
            return "connecting"
        return "disconnected"

    def start(self):
        if self._task and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self):
        self._stopped = True
        self._running = False
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()

    def _subscribed_channels(self):
        rows = event_configs_table.search(
            (Q.org_id == self.org["id"]) & (Q.direction == "subscribe") & (Q.enabled == True)  # noqa: E712
        )
        return [r["channel"] for r in rows]

    async def _run_forever(self):
        """Supervisor loop: keep trying to (re)connect with exponential
        backoff until `stop()` is called. A successful connection that later
        drops resets the backoff delay back to the minimum."""
        delay = settings.cometd_reconnect_min_delay_seconds

        while not self._stopped:
            channels = self._subscribed_channels()
            if not channels:
                log_event("info", f"CometD: no subscribe channels configured for org '{self.org['name']}'", org_id=self.org["id"])
                orgs_table.update({"status": "disconnected"}, Q.id == self.org["id"])
                return  # nothing to do until sync() restarts this manager with new config

            connected_at_least_once = await self._connect_and_stream(channels)

            if self._stopped:
                return

            if connected_at_least_once:
                self._alert_fired_for_current_outage = False  # a fresh outage after this would alert again
                delay = settings.cometd_reconnect_min_delay_seconds
            else:
                delay = min(delay * settings.cometd_reconnect_backoff_factor, settings.cometd_reconnect_max_delay_seconds)
                if not self._alert_fired_for_current_outage:
                    self._alert_fired_for_current_outage = True
                    from .alerts import fire_alert  # local import avoids a circular import at module load time
                    org_row = orgs_table.get(Q.id == self.org["id"]) or {}
                    fire_alert(
                        "connection_failed",
                        {
                            "org_id": self.org["id"], "org_name": self.org["name"],
                            "error": org_row.get("last_error", "CometD connection failed"),
                        },
                        org_id=self.org["id"],
                    )

            log_event(
                "info",
                f"CometD: will retry connecting to org '{self.org['name']}' in {delay:.0f}s",
                org_id=self.org["id"],
            )
            orgs_table.update({"status": "error"}, Q.id == self.org["id"])
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

    async def _connect_and_stream(self, channels) -> bool:
        """One connection attempt. Returns True if the connection was
        successfully established at any point (even if it later dropped),
        so the caller knows whether to reset backoff or keep increasing it."""
        org = self.org
        connected = False
        try:
            # Offloaded to a thread: this is a blocking `requests` call and
            # must never freeze the web app's event loop while retrying.
            session = await asyncio.to_thread(sf_client.get_session, org)
        except SalesforceAuthError as exc:
            log_event("error", f"CometD: auth failed for org '{org['name']}': {exc}", org_id=org["id"])
            orgs_table.update({"status": "error", "last_error": str(exc)}, Q.id == org["id"])
            return connected

        url = f"{session.instance_url}/cometd/{org.get('api_version', '60.0')}/"
        auth_ext = SalesforceAuthHeaderExtension(lambda: session.access_token)

        try:
            async with Client(url, auth=auth_ext, connection_types=ConnectionType.LONG_POLLING) as client:
                self._client = client
                self._running = True
                connected = True
                orgs_table.update(
                    {"status": "connected", "last_error": None, "last_connected_at": tx.now_ts()},
                    Q.id == org["id"],
                )
                log_event("info", f"CometD: connected to org '{org['name']}'", org_id=org["id"])

                for channel in channels:
                    await client.subscribe(channel)
                    log_event("info", f"CometD: subscribed to '{channel}' on org '{org['name']}'", org_id=org["id"], channel=channel)

                async for message in client:
                    await self._handle_message(message)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"CometD: connection error for org '{org['name']}': {exc}", org_id=org["id"])
            orgs_table.update({"status": "error", "last_error": str(exc)}, Q.id == org["id"])
        finally:
            self._running = False

        return connected

    async def _handle_message(self, message: dict):
        org = self.org
        channel = message.get("channel", "unknown")
        payload = message.get("data", {}).get("payload", message.get("data", {}))

        with start_span("cometd.receive_event", org_id=org["id"], channel=channel):
            record = tx.record_transaction(
                org_id=org["id"],
                org_name=org["name"],
                direction="subscribe",
                channel=channel,
                status="received",
                payload=payload,
            )
            log_event("info", f"CometD: event received on '{channel}' from org '{org['name']}'", org_id=org["id"], channel=channel)

            tx.update_transaction(record["id"], status="queued")
            await broker.publish(
                "inbound",
                {"transaction_id": record["id"], "org_id": org["id"], "channel": channel, "payload": payload},
            )


class CometDManager:
    """Tracks one OrgStreamManager per active Salesforce org."""

    def __init__(self):
        self._managers: Dict[str, OrgStreamManager] = {}

    async def sync(self):
        """Reconcile running connections against the current org configuration.
        Call this after any org/event-config change so the admin UI can hot-apply
        subscription changes without a server restart."""
        active_orgs = {o["id"]: o for o in orgs_table.search(Q.active == True)}  # noqa: E712

        # stop managers for orgs that were removed/deactivated
        for org_id in list(self._managers.keys()):
            if org_id not in active_orgs:
                await self._managers[org_id].stop()
                del self._managers[org_id]

        # (re)start managers for active orgs; simplest approach is to restart
        # whenever sync() is called so channel changes take effect immediately
        for org_id, org in active_orgs.items():
            if org_id in self._managers:
                await self._managers[org_id].stop()
            manager = OrgStreamManager(org)
            self._managers[org_id] = manager
            manager.start()

    def status_for(self, org_id: str) -> str:
        mgr = self._managers.get(org_id)
        return mgr.status if mgr else "disconnected"

    async def stop_all(self):
        for mgr in self._managers.values():
            await mgr.stop()
        self._managers.clear()


cometd_manager = CometDManager()
