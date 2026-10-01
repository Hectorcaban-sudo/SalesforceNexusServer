"""No-op tracing stubs. OpenTelemetry was removed from this deployment.

Call sites still pass org_id=, channel=, carrier=, span=, transaction_id=.
Accept any kwargs so the inbound worker does not crash with TypeError.
"""
from contextlib import contextmanager


class _NullSpan:
    def set_attribute(self, *args, **kwargs):
        return None

    def set_status(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None


def setup_tracing(app=None):
    return None


def get_tracer():
    return None


@contextmanager
def start_span(name: str = "", *args, **kwargs):
    yield _NullSpan()


def inject_trace_context(*args, **kwargs):
    headers = kwargs.get("headers")
    if headers is None and args:
        headers = args[0] if isinstance(args[0], dict) else {}
    if not isinstance(headers, dict):
        carrier = kwargs.get("carrier")
        headers = carrier if isinstance(carrier, dict) else {}
    return dict(headers or {})


def extract_trace_context(*args, **kwargs):
    return None
