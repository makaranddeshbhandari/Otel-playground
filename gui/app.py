"""Step 1 of 5 — what happens when you press a button. See LEARN.md §3."""

import os
import time

import requests
import streamlit as st
from opentelemetry.trace import SpanKind, Status, StatusCode

import jaeger_client
from otel_setup import get_tracer

ORDERS_URL = os.environ.get("ORDERS_URL", "http://orders-api:8001")
JAEGER_UI_URL = os.environ.get("JAEGER_UI_URL", "http://localhost:16686")
AMOUNT = 499.0

st.set_page_config(page_title="OpenTelemetry Playground", page_icon="🔭")


def fire(action: str, scenario: str) -> dict:
    """Open a root span, call orders-api inside it, return what happened."""
    tracer = get_tracer()

    with tracer.start_as_current_span(f"ui.{action}", kind=SpanKind.CLIENT) as span:
        span.set_attribute("app.action", action)
        span.set_attribute("app.scenario", scenario)
        span.set_attribute("app.order.amount", AMOUNT)
        span.set_attribute("enduser.id", "student-01")

        ctx = span.get_span_context()
        result = {
            "action": action,
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            # False means the sampler dropped it and Jaeger will never see it.
            "sampled": ctx.trace_flags.sampled,
        }

        started = time.perf_counter()
        try:
            response = requests.post(
                f"{ORDERS_URL}/orders",
                json={"amount": AMOUNT, "customer_id": "student-01", "scenario": scenario},
                timeout=30,
            )
            result["ok"] = response.ok
            result["detail"] = ""
            if not response.ok:
                span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                # FastAPI answers 500 with plain text, not JSON, so don't assume.
                try:
                    body = str(response.json().get("detail", ""))
                except ValueError:
                    body = response.text.strip()[:200]
                result["detail"] = f"HTTP {response.status_code} — {body}"
        except requests.RequestException as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            result.update(ok=False, detail=str(exc))

        result["ms"] = round((time.perf_counter() - started) * 1000)
        span.set_attribute("app.latency_ms", result["ms"])
        return result


def describe_trace(trace_id: str, root_span_id: str) -> None:
    with st.spinner("Waiting for the spans to reach Jaeger…"):
        # Waiting for our own root span means a slow batch can't be mistaken
        # for broken propagation below.
        trace_json = jaeger_client.fetch_trace(trace_id, require_span_id=root_span_id)

    if not trace_json:
        st.warning(
            "No spans found yet. Either they're still in flight, or the sampler "
            "dropped this trace. Run `make logs-collector` to see what's moving."
        )
        return

    rows = jaeger_client.flatten(trace_json)
    services = sorted({r["service"] for r in rows})

    # 0 ms ASGI internals — real, but noise at this zoom level. Jaeger shows them.
    visible = [r for r in rows if not r["operation"].endswith(("http send", "http receive"))]
    hidden = len(rows) - len(visible)

    st.write(f"**{len(rows)} spans** across **{len(services)} services**: {' → '.join(services)}")

    lines = []
    for row in visible:
        indent = "  " * row["depth"]
        mark = "✗ " if row["error"] else ""
        label = f"{indent}{mark}{row['service']}  {row['operation']}"
        lines.append(f"{label:<54}{row['duration_us'] / 1000:>8.1f} ms")
    st.code("\n".join(lines), language=None)

    if hidden:
        st.caption(f"{hidden} low-level ASGI spans hidden here. Jaeger shows all {len(rows)}.")

    if len(services) < 3:
        st.warning(
            f"This trace only reached {len(services)} service(s). A healthy one spans "
            "gui → orders-api → payments-api. Either a service is down (`make health`) "
            "or context propagation is broken — see LEARN.md step 4."
        )


def report(result: dict) -> None:
    if result["ok"]:
        st.success(f"Done in {result['ms']} ms.")
    else:
        st.error(f"Failed after {result['ms']} ms — {result['detail']}")
        st.caption("That failure is on purpose. Now go find it in Jaeger.")

    if not result["sampled"]:
        st.warning(
            "This trace was **not sampled**, so it was never recorded and won't "
            "appear in Jaeger. That's OTEL_TRACES_SAMPLER_ARG at work."
        )
        return

    st.write("**Trace ID**")
    st.code(result["trace_id"], language=None)
    st.link_button("Open this trace in Jaeger ↗", f"{JAEGER_UI_URL}/trace/{result['trace_id']}")

    describe_trace(result["trace_id"], result["span_id"])


st.title("🔭 OpenTelemetry Playground")
st.write("Press a button. Each press creates one trace across three services.")
st.caption("gui → orders-api → payments-api")

col1, col2 = st.columns(2)
col3, col4 = st.columns(2)

if col1.button("🛒 Place an order", use_container_width=True, type="primary"):
    st.session_state.result = fire("place_order", "happy")
    st.session_state.batch = None
if col2.button("🐢 Make it slow", use_container_width=True):
    st.session_state.result = fire("slow_call", "slow")
    st.session_state.batch = None
if col3.button("💥 Break it", use_container_width=True):
    st.session_state.result = fire("cause_error", "error")
    st.session_state.batch = None
if col4.button("📈 Send 25 orders", use_container_width=True):
    progress = st.progress(0.0, "Sending…")
    batch = []
    for i in range(25):
        scenario = "happy" if i % 5 else ("error" if i % 10 == 5 else "slow")
        batch.append(fire("load_test", scenario))
        progress.progress((i + 1) / 25, f"Sending… {i + 1}/25")
    progress.empty()
    st.session_state.batch = batch
    st.session_state.result = batch[-1]

st.divider()

result = st.session_state.get("result")
batch = st.session_state.get("batch")

if not result:
    st.info("Nothing yet. Press a button above.")
elif batch:
    dropped = sum(1 for r in batch if not r["sampled"])
    failed = sum(1 for r in batch if not r["ok"])
    st.success(f"Sent {len(batch)} orders. {failed} failed on purpose.")
    if dropped:
        st.warning(f"{dropped} of {len(batch)} traces were dropped by the sampler and never recorded.")
    else:
        st.write("All 25 traces were sampled and recorded.")
    st.write("Open Jaeger, search for service `gui`, and compare them.")
    st.link_button("Open Jaeger ↗", JAEGER_UI_URL)
    st.divider()
    st.write("**The last one of the 25:**")
    report(result)
else:
    report(result)
