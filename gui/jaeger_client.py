"""Reads traces back from Jaeger's query API — the same data the Jaeger UI uses."""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional

JAEGER_QUERY_URL = os.environ.get("JAEGER_QUERY_URL", "http://jaeger:16686")


# urllib, not the instrumented `requests` — tracing our own polling would bury your real traces.
def _get_json(path: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"{JAEGER_QUERY_URL}{path}", timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def fetch_trace(
    trace_id: str,
    attempts: int = 20,
    delay: float = 0.7,
    require_span_id: Optional[str] = None,
) -> Optional[dict]:
    """Poll until the trace looks complete, so we never show a half-arrived one.

    Complete means the span count held steady for three polls and, when the caller
    knows the root span's ID, that span has actually landed. Each service flushes
    on its own schedule, so a trace can sit incomplete for a couple of seconds.
    """
    previous_count = -1
    stable_polls = 0
    latest: Optional[dict] = None

    for _ in range(attempts):
        payload = _get_json(f"/api/traces/{trace_id}")
        data = (payload or {}).get("data") or []
        if data and data[0].get("spans"):
            latest = data[0]
            count = len(latest["spans"])
            has_root = require_span_id is None or any(
                s.get("spanID") == require_span_id for s in latest["spans"]
            )
            if count == previous_count:
                stable_polls += 1
                if stable_polls >= 3 and has_root:
                    return latest
            else:
                stable_polls = 0
            previous_count = count
        time.sleep(delay)

    return latest


def list_services() -> list[str]:
    payload = _get_json("/api/services")
    return sorted((payload or {}).get("data") or [])


def _tag(span: dict, key: str) -> Any:
    for tag in span.get("tags", []):
        if tag.get("key") == key:
            return tag.get("value")
    return None


def _is_error(span: dict) -> bool:
    return _tag(span, "error") is True or str(_tag(span, "otel.status_code")) == "ERROR"


def _row(span: dict, processes: dict, depth: int, total: int, trace_start: int) -> dict:
    return {
        "depth": depth,
        "span_id": span["spanID"],
        "service": processes.get(span.get("processID"), {}).get("serviceName", "unknown"),
        "operation": span.get("operationName", ""),
        "start_offset_us": span["startTime"] - trace_start,
        "duration_us": span["duration"],
        "error": _is_error(span),
        "total_us": total,
    }


def flatten(trace_json: dict) -> list[dict]:
    """Turn Jaeger's flat span list into an ordered, depth-annotated tree."""
    spans = trace_json.get("spans", [])
    processes = trace_json.get("processes", {})
    if not spans:
        return []

    by_id = {s["spanID"]: s for s in spans}
    children: dict[Optional[str], list[dict]] = {}

    for span in spans:
        parent = None
        for ref in span.get("references", []):
            if ref.get("refType") == "CHILD_OF" and ref.get("spanID") in by_id:
                parent = ref["spanID"]
                break
        children.setdefault(parent, []).append(span)

    for bucket in children.values():
        bucket.sort(key=lambda s: s["startTime"])

    trace_start = min(s["startTime"] for s in spans)
    trace_end = max(s["startTime"] + s["duration"] for s in spans)
    total = max(trace_end - trace_start, 1)

    rows: list[dict] = []

    def walk(parent_id: Optional[str], depth: int) -> None:
        for span in children.get(parent_id, []):
            rows.append(_row(span, processes, depth, total, trace_start))
            walk(span["spanID"], depth + 1)

    walk(None, 0)

    # Spans whose parent is outside this trace would otherwise be dropped.
    if len(rows) < len(spans):
        rendered = {r["span_id"] for r in rows}
        for span in sorted(spans, key=lambda s: s["startTime"]):
            if span["spanID"] not in rendered:
                rows.append(_row(span, processes, 0, total, trace_start))

    return rows
