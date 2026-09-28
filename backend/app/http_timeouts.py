"""Shared outbound timeouts. Use these on every Salesforce / Graph / SSO / sink call."""
from .config import settings


def requests_timeout():
    """(connect, read) tuple for the requests library."""
    connect = float(getattr(settings, "http_connect_timeout", 5.0) or 5.0)
    read = float(getattr(settings, "http_read_timeout", 30.0) or 30.0)
    return (connect, read)


def httpx_timeout():
    try:
        import httpx
        return httpx.Timeout(
            connect=float(getattr(settings, "http_connect_timeout", 5.0) or 5.0),
            read=float(getattr(settings, "http_read_timeout", 30.0) or 30.0),
            write=float(getattr(settings, "http_write_timeout", 30.0) or 30.0),
            pool=float(getattr(settings, "http_connect_timeout", 5.0) or 5.0),
        )
    except Exception:
        return float(getattr(settings, "http_read_timeout", 30.0) or 30.0)
