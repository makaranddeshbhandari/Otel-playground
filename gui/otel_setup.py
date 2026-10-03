"""Step 2 of 5 — OpenTelemetry wired by hand. See LEARN.md §5.3."""

import os

import streamlit as st
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SERVICE = os.environ.get("OTEL_SERVICE_NAME", "gui")


def sampling_ratio() -> float:
    try:
        return float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1.0"))
    except ValueError:
        return 1.0


# Required, not tidiness: Streamlit reruns this script on every click.
@st.cache_resource(show_spinner=False)
def get_tracer() -> trace.Tracer:
    resource = Resource.create(
        {
            SERVICE_NAME: SERVICE,
            SERVICE_VERSION: "1.0.0",
            "workshop.component": "control-panel",
        }
    )
    sampler = ParentBased(root=TraceIdRatioBased(sampling_ratio()))
    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # This one line is what keeps the trace connected across services.
    RequestsInstrumentor().instrument()

    return trace.get_tracer("gui.tracer")
