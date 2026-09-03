"""
SQLite-backed local datasource for the Salesforce Nexus AI Server.

This replaces the earlier TinyDB (flat JSON file) storage with a real SQLite
database file (backend/data/nexus.db), while keeping the exact same
lightweight "table + query object" interface the rest of the app already
uses (`table.get(Q.field == value)`, `table.search(...)`, `table.update(...)`,
`table.remove(...)`, `table.all()`, `table.truncate()`, `len(table)`, and
`record.doc_id` on rows returned from `.all()`). Each logical row is stored
as a JSON blob in a real SQLite table (one physical table per logical
table), which gives us proper ACID writes and a single-file database without
having to rewrite every call site across the app.

Tables:
  - users           : admin interface accounts
  - orgs            : configured Salesforce org connections
  - event_configs   : per-org subscribe/publish event channel configuration
  - transactions    : full lifecycle record of every event that flows through
                       the system (received -> queued -> processed -> published)
  - logs            : structured application log records (mirrors the log file
                       so the admin UI can query/filter them without tailing files)
  - admin_settings  : named admin configuration blocks (e.g. the DSSClient
                       configuration used by the payload processor)
"""
import json
import sqlite3
from threading import RLock
from typing import Optional, Callable, List, Dict, Any

from .config import settings

_lock = RLock()

_conn = sqlite3.connect(settings.db_path, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA foreign_keys=OFF")


class Document(dict):
    """A plain dict that also carries the SQLite rowid as `.doc_id`,
    mirroring TinyDB's Document interface used elsewhere in the app."""

    def __init__(self, data: Dict[str, Any], doc_id: int):
        super().__init__(data)
        self.doc_id = doc_id


class Condition:
    """A composable predicate over a record dict, built up via QueryField."""

    def __init__(self, fn: Callable[[dict], bool]):
        self._fn = fn

    def __call__(self, record: dict) -> bool:
        return self._fn(record)

    def __and__(self, other: "Condition") -> "Condition":
        return Condition(lambda rec: self._fn(rec) and other._fn(rec))

    def __or__(self, other: "Condition") -> "Condition":
        return Condition(lambda rec: self._fn(rec) or other._fn(rec))


class QueryField:
    def __init__(self, name: str):
        self._name = name

    def __eq__(self, value) -> Condition:  # type: ignore[override]
        name = self._name
        return Condition(lambda rec: rec.get(name) == value)

    def __ne__(self, value) -> Condition:  # type: ignore[override]
        name = self._name
        return Condition(lambda rec: rec.get(name) != value)


class Query:
    """Usage: Q.field_name == value, combined with & / |"""

    def __getattr__(self, name: str) -> QueryField:
        return QueryField(name)


Q = Query()


class Table:
    def __init__(self, conn: sqlite3.Connection, name: str):
        self._conn = conn
        self._name = name
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch == "_")
        if safe_name != name:
            raise ValueError(f"Invalid table name: {name}")
        with _lock:
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self._name} "
                "(doc_id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)"
            )
            self._conn.commit()

    def _row_to_doc(self, row) -> Document:
        doc_id, data = row
        return Document(json.loads(data), doc_id)

    def insert(self, record: Dict[str, Any]) -> int:
        with _lock:
            cur = self._conn.execute(
                f"INSERT INTO {self._name} (data) VALUES (?)", (json.dumps(record),)
            )
            self._conn.commit()
            return cur.lastrowid

    def all(self) -> List[Document]:
        with _lock:
            rows = self._conn.execute(f"SELECT doc_id, data FROM {self._name}").fetchall()
        return [self._row_to_doc(r) for r in rows]

    def get(self, condition: Optional[Condition] = None) -> Optional[Document]:
        for doc in self.all():
            if condition is None or condition(doc):
                return doc
        return None

    def search(self, condition: Condition) -> List[Document]:
        return [doc for doc in self.all() if condition(doc)]

    def update(self, fields: Dict[str, Any], condition: Optional[Condition] = None) -> List[int]:
        updated_ids = []
        with _lock:
            for doc in self.all():
                if condition is None or condition(doc):
                    merged = dict(doc)
                    merged.update(fields)
                    self._conn.execute(
                        f"UPDATE {self._name} SET data = ? WHERE doc_id = ?",
                        (json.dumps(merged), doc.doc_id),
                    )
                    updated_ids.append(doc.doc_id)
            self._conn.commit()
        return updated_ids

    def remove(self, condition: Optional[Condition] = None, doc_ids: Optional[List[int]] = None) -> List[int]:
        removed_ids: List[int] = []
        with _lock:
            if doc_ids is not None:
                removed_ids = list(doc_ids)
                self._conn.executemany(
                    f"DELETE FROM {self._name} WHERE doc_id = ?", [(i,) for i in doc_ids]
                )
            elif condition is not None:
                for doc in self.all():
                    if condition(doc):
                        removed_ids.append(doc.doc_id)
                self._conn.executemany(
                    f"DELETE FROM {self._name} WHERE doc_id = ?", [(i,) for i in removed_ids]
                )
            else:
                raise ValueError("remove() requires a condition or doc_ids")
            self._conn.commit()
        return removed_ids

    def truncate(self):
        with _lock:
            self._conn.execute(f"DELETE FROM {self._name}")
            self._conn.commit()

    def __len__(self) -> int:
        with _lock:
            (count,) = self._conn.execute(f"SELECT COUNT(*) FROM {self._name}").fetchone()
        return count


class Database:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._tables: Dict[str, Table] = {}

    def table(self, name: str) -> Table:
        if name not in self._tables:
            self._tables[name] = Table(self._conn, name)
        return self._tables[name]


_db = Database(_conn)

users_table = _db.table("users")
orgs_table = _db.table("orgs")
event_configs_table = _db.table("event_configs")
transactions_table = _db.table("transactions")
logs_table = _db.table("logs")
admin_settings_table = _db.table("admin_settings")
integrations_table = _db.table("integrations")
processors_table = _db.table("processors")
alerts_table = _db.table("alerts")
rules_table = _db.table("rules")


def db_lock():
    return _lock


def flush():
    """Kept for compatibility with callers (e.g. shutdown hooks). SQLite
    commits on every write already, so this just makes sure everything is
    synced to disk before shutdown."""
    with _lock:
        _conn.commit()
