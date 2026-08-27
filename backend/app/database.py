"""
TinyDB-backed local datasource for the Salesforce Nexus AI Server.

Tables:
  - users           : admin interface accounts
  - orgs            : configured Salesforce org connections
  - event_configs   : per-org subscribe/publish event channel configuration
  - transactions    : full lifecycle record of every event that flows through
                       the system (received -> queued -> processed -> published)
  - logs            : structured application log records (mirrors the log file
                       so the admin UI can query/filter them without tailing files)
"""
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from threading import Lock
from .config import settings

_lock = Lock()

# NOTE: intentionally using plain JSONStorage (no CachingMiddleware) so every
# insert/update/delete is flushed to disk immediately. Admin configuration
# (orgs, event channels, users) must never be at risk of being lost if the
# process is killed before a clean shutdown, and transaction/log volume in
# this system is low enough that writing on every operation is not a
# meaningful performance concern.
_db = TinyDB(settings.db_path, storage=JSONStorage)

users_table = _db.table("users")
orgs_table = _db.table("orgs")
event_configs_table = _db.table("event_configs")
transactions_table = _db.table("transactions")
logs_table = _db.table("logs")

Q = Query()


def db_lock():
    return _lock


def flush():
    """Kept for compatibility with callers (e.g. shutdown hooks). With plain
    JSONStorage every write is already durable immediately, so this is a
    no-op unless the storage backend defines an explicit flush()."""
    with _lock:
        if hasattr(_db.storage, "flush"):
            _db.storage.flush()
