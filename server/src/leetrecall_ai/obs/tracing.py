"""OpenTelemetry setup.

Spans come from three layers, all nested in one trace per request:
  generate_card (ours) > ADK agent / LLM / tool spans > anthropic.messages.create (Claude SDK)
The Claude SDK span carries the API's own token usage, so cost and throughput are computed from
the same data the traces show — no separate bookkeeping that could drift.

Exporters (LEETRECALL_OTEL_EXPORTER): "none" (default), "console", "gcp" (Cloud Trace, prod).
The in-memory collector is always on: it's how a request reads back its own spans for metrics.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

SERVICE = "leetrecall-ai"


class SpanCollector(SpanProcessor):
    """Keeps finished spans grouped by trace id (bounded LRU) so a request can compute its metrics."""

    def __init__(self, max_traces: int = 256):
        self._spans: OrderedDict[int, list[ReadableSpan]] = OrderedDict()
        self._max = max_traces
        self._lock = threading.Lock()

    def on_end(self, span: ReadableSpan) -> None:
        with self._lock:
            self._spans.setdefault(span.context.trace_id, []).append(span)
            self._spans.move_to_end(span.context.trace_id)
            while len(self._spans) > self._max:
                self._spans.popitem(last=False)

    def pop(self, trace_id: int) -> list[ReadableSpan]:
        with self._lock:
            return self._spans.pop(trace_id, [])


_collector: SpanCollector | None = None
_lock = threading.Lock()


def setup_tracing() -> SpanCollector:
    """Idempotent. Must run before the first Claude client is created."""
    global _collector
    with _lock:
        if _collector:
            return _collector
        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
        _collector = SpanCollector()
        provider.add_span_processor(_collector)
        exporter = os.environ.get("LEETRECALL_OTEL_EXPORTER", "none")
        if exporter == "console":
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        elif exporter == "gcp":
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter  # installed in the prod image

            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)
        return _collector


def tracer() -> trace.Tracer:
    return trace.get_tracer(SERVICE)
