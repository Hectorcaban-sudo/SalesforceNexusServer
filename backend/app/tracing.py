"""
OpenTelemetry tracing setup.

Gives you a single trace per event flowing through the pipeline:
  CometD receive -> broker (inbound) -> worker.process_payload -> broker
  (outbound) -> Salesforce publish -> integration fan-out
all tied together by carrying the transaction_id as a span attribute, so a
single slow or failed event can be traced end-to-end in Jaeger/Tempo/
Honeycomb/Datadog/whatever you point OTEL_EXPORTER_OTLP_ENDPOINT at.

Tracing is safe to leave fully unconfigured: spans are still created (near-
zero overhead) but nothing is exported unless OTEL_EXPORTER_OTLP_ENDPOINT or
OTEL_CONSOLE_EXPORTER is set, so this never requires a collector to run the
app locally.
"""
from contextlib import contextmanager
from typing import Optional

from .config import settings
from .logging_config import log_event

_tracer = None


def setup_tracing(app=None):
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    except ImportError:
        log_event("warning", "OpenTelemetry packages not installed - tracing disabled. "
                              "Install with: pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi")
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    exporter_attached = False
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
            exporter_attached = True
            log_event("info", f"OpenTelemetry: exporting traces to {settings.otel_exporter_otlp_endpoint}")
        except ImportError:
            log_event("warning", "OTEL_EXPORTER_OTLP_ENDPOINT is set but the OTLP exporter package isn't installed. "
                                  "Install with: pip install opentelemetry-exporter-otlp-proto-http")

    if settings.otel_console_exporter:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        exporter_attached = True
        log_event("info", "OpenTelemetry: printing spans to console (OTEL_CONSOLE_EXPORTER=true)")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(settings.otel_service_name)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        RequestsInstrumentor().instrument()
    except ImportError:
        pass

    if not exporter_attached:
        log_event("info", "OpenTelemetry: initialized with no exporter configured (spans are created but not sent anywhere). "
                           "Set OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_CONSOLE_EXPORTER=true to see them.")


def get_tracer():
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace
            _tracer = trace.get_tracer(settings.otel_service_name)
        except ImportError:
            _tracer = None
    return _tracer


@contextmanager
def start_span(name: str, carrier: Optional[dict] = None, **attributes):
    """
    Convenience context manager: no-ops cleanly if OTel isn't installed.

    `carrier` is an extracted trace context (see `inject_trace_context`) -
    passing it makes this span a *child* of whatever span produced that
    carrier, even if that happened in a completely different asyncio task at
    an earlier point in time (which is exactly what happens every time an
    event crosses the broker: OpenTelemetry's automatic context propagation
    only works within a single task's call chain, so without this, every
    stage of the pipeline - CometD receive, processing, publish, integration
    fan-out - would show up as its own disconnected trace instead of one
    unified trace per event).
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    ctx = extract_trace_context(carrier) if carrier else None
    with tracer.start_as_current_span(name, context=ctx) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


def inject_trace_context(span=None) -> dict:
    """
    Captures the current (or given) span's trace context as a plain dict
    (W3C traceparent format) that's JSON-serializable - safe to embed
    directly in a broker message so the next stage of the pipeline can pick
    up the same trace. Returns {} if tracing isn't configured.
    """
    tracer = get_tracer()
    if tracer is None:
        return {}
    try:
        from opentelemetry import context as otel_context, trace
        from opentelemetry.propagate import inject

        carrier: dict = {}
        if span is not None:
            ctx = trace.set_span_in_context(span)
            inject(carrier, context=ctx)
        else:
            inject(carrier)
        return carrier
    except ImportError:
        return {}


def extract_trace_context(carrier: dict):
    """The inverse of `inject_trace_context` - turns a carrier dict back into
    a Context object usable as `context=` for `tracer.start_as_current_span`
    or passed straight to `start_span(..., carrier=carrier)`."""
    if not carrier:
        return None
    try:
        from opentelemetry.propagate import extract
        return extract(carrier)
    except ImportError:
        return None
