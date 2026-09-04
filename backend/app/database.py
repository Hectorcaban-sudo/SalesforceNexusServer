"""
Pluggable SQL datasource for the Salesforce Nexus AI Server: SQLite (default),
PostgreSQL, SQL Server, or Oracle - selected via DATABASE_TYPE (see
config.py and Admin Configuration -> Database in the admin UI).

Regardless of which backend is active, the rest of the app sees the exact
same lightweight "table + query object" interface (`table.get(Q.field ==
value)`, `table.search(...)`, `table.update(...)`, `table.remove(...)`,
`table.all()`, `table.truncate()`, `len(table)`, `record.doc_id`) - every
router and module in this codebase is written against that interface and
none of them need to know or care which SQL engine is actually underneath.

How this works across four different databases with one code path: each
logical "table" is a real SQL table with exactly two columns - an
auto-incrementing integer primary key (`doc_id`) and a text column holding
the whole record as a JSON blob (`data`). Filtering happens in Python (load
matching-enough rows, evaluate the Condition on each) rather than translating
Query objects into SQL WHERE clauses - this trades a bit of raw query
performance for something much more valuable here: the SAME code works
identically against SQLite, Postgres, SQL Server, and Oracle, because none of
it depends on a dialect-specific JSON query feature. SQLAlchemy Core (not the
ORM) provides the thin abstraction over CREATE TABLE / INSERT / SELECT /
UPDATE / DELETE syntax differences between those four engines.

Tables:
  - users, orgs, event_configs, transactions, logs, admin_settings,
    integrations, processors, alerts, rules, audit_log, auth_events
  (see each module for what's actually stored in it)
"""
import json
from threading import RLock
from typing import Optional, Callable, List, Dict, Any

import sqlalchemy as sa

from .config import settings

_lock = RLock()


def _build_engine() -> "sa.engine.Engine":
    db_type = (settings.database_type or "sqlite").lower()

    if db_type == "sqlite":
        engine = sa.create_engine(f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False})
        with engine.connect() as conn:
            conn.execute(sa.text("PRAGMA journal_mode=WAL"))
            conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        return engine

    if db_type == "postgres":
        # Driver: psycopg2-binary (pip install psycopg2-binary)
        port = settings.database_port or 5432
        url = sa.URL.create(
            "postgresql+psycopg2", username=settings.database_user, password=settings.database_password,
            host=settings.database_host, port=port, database=settings.database_name,
        )
        return sa.create_engine(url)

    if db_type == "sqlserver":
        # Driver: pyodbc (pip install pyodbc) + the "ODBC Driver 18 for SQL
        # Server" system package installed separately (Microsoft doesn't
        # ship this as a pip-installable wheel) - see README "Database
        # backends" for the exact install steps, which are OS-specific.
        port = settings.database_port or 1433
        url = sa.URL.create(
            "mssql+pyodbc", username=settings.database_user, password=settings.database_password,
            host=settings.database_host, port=port, database=settings.database_name,
            query={"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"},
        )
        return sa.create_engine(url)

    if db_type == "oracle":
        # Driver: oracledb (pip install oracledb) - pure Python, no Oracle
        # Instant Client required in "thin" mode (oracledb's default).
        port = settings.database_port or 1521
        url = sa.URL.create(
            "oracle+oracledb", username=settings.database_user, password=settings.database_password,
            host=settings.database_host, port=port,
            query={"service_name": settings.database_name},
        )
        return sa.create_engine(url)

    raise ValueError(f"Unknown DATABASE_TYPE: '{db_type}' - expected sqlite, postgres, sqlserver, or oracle")


_engine = _build_engine()
_metadata = sa.MetaData()


class Document(dict):
    """A plain dict that also carries the row's primary key as `.doc_id`,
    mirroring the TinyDB-style Document interface used elsewhere in the app."""

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
    """Same 'table + query object' interface regardless of which SQL engine
    `_engine` actually points at - see module docstring."""

    def __init__(self, engine: "sa.engine.Engine", metadata: sa.MetaData, name: str):
        self._engine = engine
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch == "_")
        if safe_name != name:
            raise ValueError(f"Invalid table name: {name}")

        self._table = sa.Table(
            name, metadata,
            sa.Column("doc_id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("data", sa.Text, nullable=False),
            extend_existing=True,
        )
        with _lock:
            metadata.create_all(engine, tables=[self._table], checkfirst=True)

    def _row_to_doc(self, row) -> Document:
        return Document(json.loads(row.data), row.doc_id)

    def insert(self, record: Dict[str, Any]) -> int:
        with _lock, self._engine.begin() as conn:
            result = conn.execute(sa.insert(self._table).values(data=json.dumps(record)))
            return result.inserted_primary_key[0]

    def all(self) -> List[Document]:
        with _lock, self._engine.connect() as conn:
            rows = conn.execute(sa.select(self._table)).fetchall()
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
        with _lock, self._engine.begin() as conn:
            for doc in self.all():
                if condition is None or condition(doc):
                    merged = dict(doc)
                    merged.update(fields)
                    conn.execute(
                        sa.update(self._table).where(self._table.c.doc_id == doc.doc_id).values(data=json.dumps(merged))
                    )
                    updated_ids.append(doc.doc_id)
        return updated_ids

    def remove(self, condition: Optional[Condition] = None, doc_ids: Optional[List[int]] = None) -> List[int]:
        removed_ids: List[int] = []
        with _lock, self._engine.begin() as conn:
            if doc_ids is not None:
                removed_ids = list(doc_ids)
                conn.execute(sa.delete(self._table).where(self._table.c.doc_id.in_(doc_ids)))
            elif condition is not None:
                for doc in self.all():
                    if condition(doc):
                        removed_ids.append(doc.doc_id)
                if removed_ids:
                    conn.execute(sa.delete(self._table).where(self._table.c.doc_id.in_(removed_ids)))
            else:
                raise ValueError("remove() requires a condition or doc_ids")
        return removed_ids

    def truncate(self):
        with _lock, self._engine.begin() as conn:
            conn.execute(sa.delete(self._table))

    def __len__(self) -> int:
        with _lock, self._engine.connect() as conn:
            (count,) = conn.execute(sa.select(sa.func.count()).select_from(self._table)).fetchone()
        return count


class Database:
    def __init__(self, engine: "sa.engine.Engine", metadata: sa.MetaData):
        self._engine = engine
        self._metadata = metadata
        self._tables: Dict[str, Table] = {}

    def table(self, name: str) -> Table:
        if name not in self._tables:
            self._tables[name] = Table(self._engine, self._metadata, name)
        return self._tables[name]


_db = Database(_engine, _metadata)

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
audit_log_table = _db.table("audit_log")
auth_events_table = _db.table("auth_events")


def db_lock():
    return _lock


def flush():
    """Kept for compatibility with callers (e.g. shutdown hooks). Every
    write already commits inside its own transaction (see Table methods
    above using `engine.begin()`), so there's nothing outstanding to flush -
    this just disposes pooled connections cleanly on shutdown."""
    with _lock:
        _engine.dispose()
