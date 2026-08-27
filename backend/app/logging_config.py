"""
Application-wide logging.

Every log record is:
  1. Written to a rotating file on disk (logs/nexus.log)
  2. Mirrored into the SQLite `logs` table so the React admin interface can
     query/filter/paginate logs through the API without needing file access.
"""
import logging
import logging.handlers
from .config import settings

_MAX_DB_LOG_RECORDS = 5000


class DBLogHandler(logging.Handler):
    """Logging handler that mirrors records into the SQLite-backed logs table."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # imported lazily to avoid circular import at module load time
            from .database import logs_table
            from .models import new_id, now_ts

            context = getattr(record, "context", None)
            logs_table.insert(
                {
                    "id": new_id(),
                    "timestamp": now_ts(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "context": context,
                }
            )
            # trim to keep the local DB small
            if len(logs_table) > _MAX_DB_LOG_RECORDS:
                all_ids = [r.doc_id for r in logs_table.all()]
                excess = len(all_ids) - _MAX_DB_LOG_RECORDS
                if excess > 0:
                    logs_table.remove(doc_ids=all_ids[:excess])
        except Exception:
            # Never let logging itself crash the app
            pass


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("nexus")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(settings.log_level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file, maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    db_handler = DBLogHandler()

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(db_handler)

    return logger


def log_event(level: str, message: str, **context):
    logger = logging.getLogger("nexus")
    extra = {"context": context} if context else {}
    getattr(logger, level.lower(), logger.info)(message, extra=extra)
