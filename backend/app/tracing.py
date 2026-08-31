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
def start_span(name: str, **attributes):
    """Convenience context manager: no-ops cleanly if OTel isn't installed."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span
