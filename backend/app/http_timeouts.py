"""Shared outbound timeouts. Use these on every Salesforce / Graph / SSO / sink call."""
from .config import settings


def requests_timeout():
    """(connect, read) tuple for requests."""
    return (settings.http_connect_timeout, settings.http_read_timeout)


def httpx_timeout():
    try:
        import httpx
        return httpx.Timeout(
            connect=settings.http_connect_timeout,
            read=settings.http_read_timeout,
            write=settings.http_write_timeout,
            pool=settings.http_connect_timeout,
        )
    except Exception:
        return settings.http_read_timeout
