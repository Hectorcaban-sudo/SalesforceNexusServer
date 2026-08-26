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
from tinydb.middlewares import CachingMiddleware
from threading import Lock
from .config import settings

_lock = Lock()

_db = TinyDB(settings.db_path, storage=CachingMiddleware(JSONStorage))

users_table = _db.table("users")
orgs_table = _db.table("orgs")
event_configs_table = _db.table("event_configs")
transactions_table = _db.table("transactions")
logs_table = _db.table("logs")

Q = Query()


def db_lock():
    return _lock


def flush():
    with _lock:
        _db.storage.flush()
