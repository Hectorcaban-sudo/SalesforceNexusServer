"""No-op tracing stubs. OpenTelemetry was removed from this deployment."""
from contextlib import contextmanager
from typing import Optional


def setup_tracing(app=None):
    return None


def get_tracer():
    return None


@contextmanager
def start_span(name: str, attributes: Optional[dict] = None, parent=None):
    yield None


def inject_trace_context(headers: Optional[dict] = None) -> dict:
    return dict(headers or {})


def extract_trace_context(headers: Optional[dict] = None):
    return None
