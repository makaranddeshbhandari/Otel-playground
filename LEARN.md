# Learn OpenTelemetry in 2 Hours

A single-session, hands-on workshop. You will finish it able to instrument a
Python service, read a distributed trace, and debug the classic "my spans
aren't showing up" problem.

**No prior observability experience needed.** You need Docker, a terminal, and
a browser.

| # | Section | Time |
|---|---|---|
| 0 | [Before you start](#0-before-you-start) | 5 min |
| 1 | [Why traces exist](#1-why-traces-exist) | 10 min |
| 2 | [Boot the stack](#2-boot-the-stack) | 10 min |
| 3 | [Your first trace](#3-your-first-trace) | 20 min |
| 4 | [The one header that makes it work](#4-the-one-header-that-makes-it-work) | 20 min |
| 5 | [Two ways to instrument](#5-two-ways-to-instrument) | 25 min |
| 6 | [Finding errors and slowness](#6-finding-errors-and-slowness) | 15 min |
| 7 | [The collector, and what sampling costs you](#7-the-collector-and-what-sampling-costs-you) | 10 min |
| 8 | [Where to go next](#8-where-to-go-next) | 5 min |
| — | [Glossary](#glossary) · [Cheatsheet](#cheatsheet) · [Troubleshooting](#troubleshooting) · [Self-check](#self-check) | — |

---

## 0. Before you start

```bash
docker --version          # any recent Docker Desktop / Engine with Compose v2
cd otel-playground
```

That's the whole setup. Python, OpenTelemetry, and Jaeger all run in containers —
nothing gets installed on your machine.

---

## 1. Why traces exist

You already know two kinds of telemetry:

- **Logs** — "something happened, here's a line of text."
- **Metrics** — "here's a number over time: 400 requests/sec, 2% errors."

Both are per-service. So when a user says *"checkout took 9 seconds"*, logs and
metrics can tell you **that** it was slow, but not **where**. You end up SSHing
into five services and correlating timestamps by hand.

**A trace is the third kind.** It follows one request across every service it
touches and records how long each step took:

```
ui.place_order ────────────────────────────────────── 151 ms
  └ POST /orders (orders-api) ───────────────────────  150 ms
      └ POST /payments (payments-api) ───────────────  147 ms
          ├ payment.fraud_check ──────                  47 ms
          └ payment.gateway_call ────────────           99 ms   ← there it is
```

Two words to learn right now:

- **Span** — one unit of work. Has a name, a start time, a duration, and a parent.
- **Trace** — the tree of spans that belong to one request. Identified by a
  **trace ID** shared by every span in it.

**OpenTelemetry** is the vendor-neutral standard for producing this data. You
instrument once, and you can send it to Jaeger, Tempo, Datadog, or anything
else without touching your code again. That neutrality is the entire point —
it's why OTel is a CNCF project second only to Kubernetes in activity.

---

## 2. Boot the stack

```bash
make up
```

First run takes 2–3 minutes (building images). Then:

```bash
make health
```

You should see:

```
collector : 200
jaeger    : 200
orders    : 200
payments  : 200
```

Open the two URLs you'll live in for the next two hours:

- **Playground GUI** → <http://localhost:8501>
- **Jaeger UI** → <http://localhost:16686>

Jaeger is empty right now. That's correct — nothing has produced a trace yet.

> ✅ **Checkpoint:** five containers running (`make ps`), all four health checks green.

---

## 3. Your first trace

### 3.1 Make one

In the Playground, press **🛒 Place an order**.

You get back:
- a **trace ID** — 32 hex characters
- the **list of spans** the click produced, read back from Jaeger

Read that list. It says **14 spans across 3 services**, and prints them nested
by parent:

```
gui  ui.place_order                                     84.8 ms
  gui  POST                                             83.5 ms
    orders-api  POST /orders                            81.8 ms
      orders-api  POST                                  80.6 ms
        payments-api  POST /payments                    79.2 ms
          payments-api  payment.authorize               78.6 ms
            payments-api  payment.fraud_check           17.0 ms
            payments-api  payment.gateway_call          61.5 ms
```

Only 8 lines for 14 spans — the app hides six 0 ms `http send` / `http receive`
spans that the ASGI instrumentation emits for each chunk of the response. They
are real, and Jaeger shows all 14. This is your first taste of a permanent
observability question: *which spans are signal, and which are noise?*

`gui/jaeger_client.py` answers the same question a second way: it fetches
traces with `urllib` rather than the instrumented `requests`, because tracing
the GUI's own polling would bury your real traces under hundreds named `GET`.

Indentation is parentage: each span was started **by** the one above it, and
its duration is contained within it.

**One button press. Three services. One trace.** That's the whole idea.

### 3.2 Read it properly

Click **Open this trace in Jaeger ↗**. In the Jaeger UI, expand the
`payment.authorize` span and find:

| What you're looking at | Where in Jaeger | Why it matters |
|---|---|---|
| **Trace ID** | top of the page | The join key. Every span here shares it. |
| **Span name** | left column | Should describe an *operation*, not an instance. `POST /orders`, never `POST /orders/12345`. |
| **Duration bar** | the Jaeger waterfall | Nested = called by. Side by side = concurrent. |
| **Tags** | expand a span → *Tags* | Attributes: `payment.amount`, `payment.currency`, `enduser.id`. Searchable. |
| **Logs** | expand a span → *Logs* | Span **events**: `fraud_check.completed` with a `fraud.score`. |
| **Process** | expand a span → *Process* | The **resource**: `service.name`, `service.version`, `deployment.environment`. |

### 3.3 Where the numbers came from

Open `services/payments/main.py` and match the code to what you just saw:

```python
with tracer.start_as_current_span("payment.authorize") as span:
    span.set_attribute("payment.amount", req.amount)          # -> Tags
    span.add_event("fraud_check.completed", {"fraud.score": score})  # -> Logs
```

> ✅ **Checkpoint:** you can point at any span in Jaeger and say which line of
> Python produced it, and name the difference between an *attribute* and an *event*.

---

## 4. The one header that makes it work

The most common beginner question is: *how does payments-api know it's part of
the same trace as a click in the GUI?*

The answer is unglamorous. It's one HTTP header.

### 4.1 See it

```bash
curl -s localhost:8001/debug/headers
```

```json
{
  "received_headers": {
    "host": "payments-api:8002",
    "user-agent": "python-requests/2.34.2",
    "traceparent": "00-c02db0985bc1733df5c1dc8323be70bf-d578e5989d38ed62-03"
  }
}
```

That's the [W3C Trace Context](https://www.w3.org/TR/trace-context/) standard:

```
00  -  c02db0985bc1733df5c1dc8323be70bf  -  d578e5989d38ed62  -  03
^^     ^                              ^     ^              ^     ^^
version          trace-id (32 hex)              parent span-id     flags
```

`flags` is a bitfield; its lowest bit means **sampled**. So `01` and `03` both
mean "recorded", `00` and `02` mean "dropped".

The receiving service reads this header and makes its spans children of
`parent span-id`. **That is the entire mechanism.** Anything you can put an
HTTP header on, you can propagate a trace through.

### 4.2 Break it on purpose

This is the most valuable five minutes of the workshop.

1. Open `gui/otel_setup.py`.
2. Find this line near the bottom and comment it out:

   ```python
   RequestsInstrumentor().instrument()
   ```

3. Restart the GUI so the change is picked up:

   ```bash
   docker compose restart gui
   ```

4. Wait ~10 seconds, reload <http://localhost:8501>, press **Place an order**.

**What you see:** the GUI reports the trace ID of its own root span, but the
span list now shows **only `gui`**, and the app warns you that propagation is
broken. In Jaeger, search for service `orders-api` — its work is still there,
but as a **separate, orphaned trace** with its own trace ID.

That's what a broken distributed trace looks like in real life: not an error,
not a crash — just quietly disconnected data that makes you chase ghosts.

5. **Put the line back**, `docker compose restart gui`, and confirm all three
   services return to the span list.

> ✅ **Checkpoint:** you can explain context propagation in one sentence, and
> you recognise what its absence looks like.

---

## 5. Two ways to instrument

There are exactly two, and this repo has one of each.

### 5.1 Zero-code (auto) instrumentation

Open `services/orders/main.py` and search for `opentelemetry`.

**There are no matches.** Not one import. And yet orders-api produces spans,
propagates context, and shows up in Jaeger.

The reason is one word in `services/orders/Dockerfile`:

```dockerfile
CMD ["opentelemetry-instrument", "uvicorn", "main:app", ...]
```

`opentelemetry-instrument` reads your `OTEL_*` environment variables, builds
the SDK, and monkey-patches every supported library (FastAPI, requests,
SQLAlchemy, Redis, boto3, …) *before* your code is imported.

Two commands are all you need on any Python project:

```bash
pip install "opentelemetry-distro[otlp]"
opentelemetry-bootstrap -a install     # detects your libs, installs their instrumentation
opentelemetry-instrument python app.py
```

**Use this when:** you're onboarding an existing service, or you can't modify
the code. It gets you HTTP, DB, and queue spans for free — usually 80% of the value.

### 5.2 Manual instrumentation

Auto-instrumentation knows about HTTP. It knows nothing about *your business*.
It cannot tell you that fraud checking took 47 ms, because "fraud check" isn't
a library — it's your code.

Open `services/payments/main.py`. That's manual instrumentation layered on top
of auto-instrumentation, and it's four techniques:

```python
tracer = trace.get_tracer("payments.tracer")

with tracer.start_as_current_span("payment.authorize") as span:
    span.set_attribute("payment.amount", req.amount)                  # 1. attributes
    span.add_event("fraud_check.completed", {"fraud.score": score})   # 2. events
    ...
    span.record_exception(error)                                      # 3. the stack trace
    span.set_status(Status(StatusCode.ERROR, str(error)))             # 4. makes it RED
```

> ⚠️ `record_exception` alone does **not** mark a span as failed. Only
> `set_status(ERROR)` does. Doing one without the other is the single most
> common OpenTelemetry mistake, and it's why teams end up with dashboards
> showing 0% errors during an outage.

### 5.3 Full manual SDK setup

`gui/otel_setup.py` is what `opentelemetry-instrument` does for you, written
out longhand. Read it top to bottom — it's five objects:

| Object | Question it answers |
|---|---|
| `Resource` | Who am I? (`service.name`, version, environment) |
| `Sampler` | Should I record this trace at all? |
| `TracerProvider` | The factory that owns the above and hands out tracers |
| `Exporter` | Where do finished spans go? (OTLP → collector) |
| `SpanProcessor` | How do they get there? (batched, background thread) |

The `@st.cache_resource` above `get_tracer()` is load-bearing, not tidiness:
Streamlit re-runs the whole script on every click, so without it you'd register
a new TracerProvider and a new export thread every time you press a button.

### 5.4 🛠 Your turn — add a span

In `services/payments/main.py`, inside `charge()`, just before the return,
add your own child span:

```python
        with tracer.start_as_current_span("payment.write_ledger") as ledger:
            ledger.set_attribute("ledger.account", "merchant-001")
            ledger.set_attribute("ledger.amount", req.amount)
            time.sleep(0.03)
            ledger.add_event("ledger.entry_written")
```

Save. The container hot-reloads (`--reload` is on). Press **Place an order** and
find `payment.write_ledger` in the span list.

**Naming rules to internalise now:**
- Span names are **low-cardinality**: `payment.write_ledger`, not `write_ledger_for_order_2231`.
- The high-cardinality stuff goes in **attributes**: `ledger.account`, `payment.order_id`.
- Prefer the [semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
  where one exists (`http.request.method`, `db.system`, `enduser.id`) — tooling
  builds dashboards automatically off those names.

> ✅ **Checkpoint:** you added a span that appears in Jaeger, and you can say
> when to reach for auto vs manual instrumentation.

---

## 6. Finding errors and slowness

This is what the whole thing is for.

### 6.1 Errors

Press **💥 Break it** in the Playground. You get a red failure message, and the
failing spans are marked with `✗` in the span list.

Now find it the way you would in production — in Jaeger:

1. **Service** = `payments-api`
2. **Tags** = `error=true`
3. **Find Traces**

Open one. Expand `payment.authorize` → **Logs** → the `exception` event carries
`exception.type`, `exception.message`, and the full `exception.stacktrace`.

Notice the error propagates *up* the tree: `payment.authorize`, `orders-api POST`,
and `gui ui.cause_error` are all marked failed. That's why you can spot a broken
dependency from the top-level span alone.

### 6.2 Latency

Press **🐢 Make it slow**, then in Jaeger:

1. **Service** = `gui`, **Operation** = `ui.slow_call`
2. **Min Duration** = `1s`
3. **Find Traces**

Open the trace and look at the waterfall. `payment.gateway_call` visibly owns
almost the entire duration. In a real incident that single glance replaces an
hour of guessing.

### 6.3 Get some real data in there

```bash
make traffic          # 2 requests/sec, Ctrl-C to stop
```

Let it run ~60 seconds, then in Jaeger:

- **Search** with service `orders-api` — see the scatter plot of durations.
  The dots at the top are your slow calls. Click one.
- **System Architecture** tab → **DAG** — Jaeger derives the service graph
  purely from the parent/child relationships in your traces:
  `gui → orders-api → payments-api`.

Nobody drew that diagram. It came from the data.

> ✅ **Checkpoint:** you can find an error trace by tag and a slow trace by
> duration without being told the trace ID.

---

## 7. The collector, and what sampling costs you

### 7.1 Why not send straight to Jaeger?

Your apps send to the **collector** (`otel-collector:4317`), not to Jaeger.
Look at `docker-compose.yml`: not one service knows Jaeger exists.

That indirection buys you:

- **Swap backends by editing one file.** Jaeger → Tempo → Datadog → Grafana Cloud
  is a change to `collector/config.yaml`, not to twelve services.
- **Batching and retries** outside your app's request path.
- **Scrubbing** — strip PII before it leaves your network.
- **Sampling decisions** made centrally, with the whole trace in view.

Open `collector/config.yaml`. The mental model is three lists plus a pipeline
that wires them:

```
receivers  →  processors  →  exporters
 (take in)     (reshape)      (send out)
```

A component that isn't listed in `service.pipelines` does nothing, no matter
how carefully you configured it. That's mistake #1 with collectors.

### 7.2 Watch your spans as plain text

```bash
make logs-collector
```

Press a button in the GUI and watch spans scroll past — names, attributes,
trace IDs, all of it. This is the **debug exporter**, and it's your best
diagnostic tool:

- **Spans here but not in Jaeger** → the exporter or the backend is the problem.
- **Nothing here at all** → your app isn't sending. Wrong endpoint, wrong
  protocol, or the SDK was never configured.

Search the same log for `payments.processed` — that's the **metric** counter.
Metrics are pushed on a timer rather than per-request, so give it a few seconds
(this repo sets `OTEL_METRIC_EXPORT_INTERVAL=5000`; the SDK default is 60s)
from `payments/main.py`. Same pipeline, same collector, different signal.

### 7.3 Sampling: the cost lever

At real traffic, keeping 100% of traces is expensive. **Head sampling** decides
at the start of a trace whether to keep it.

Try it. In `docker-compose.yml`, change:

```yaml
  OTEL_TRACES_SAMPLER_ARG: "1.0"    →    "0.1"
```

```bash
docker compose up -d
```

Now press **📈 Send 25 orders**. The app reports that roughly 22 of the 25
traces were dropped by the sampler — those were never recorded at all. That's a 90% cost reduction and a 90%
chance the one trace you need is gone.

Note the sampler is `parentbased_traceidratio`: the root service decides, and
every downstream service **obeys**. That's what keeps a trace all-or-nothing
instead of half-recorded.

**Set it back to `1.0`** and `docker compose up -d`.

The production answer to this trade-off is **tail sampling** in the collector:
buffer the whole trace, then keep it if it errored or was slow, and keep only a
small percentage of the boring ones. Best of both, at the cost of collector memory.

> ✅ **Checkpoint:** you can explain why apps point at a collector instead of a
> backend, and what changing the sampler ratio actually does.

---

## 8. Where to go next

In rough order of value:

1. **Add metrics properly.** Add Prometheus + Grafana to `docker-compose.yml`,
   add a `prometheus` exporter to `collector/config.yaml`, and graph
   `payments.processed`. Your Grafana skills apply directly.
2. **Add logs, correlated to traces.** Ship logs with `trace_id` attached and
   you can jump log → trace → span. This is where observability stops feeling
   like three separate tools.
3. **Tail sampling.** Keep 100% of errors and slow traces, 5% of the rest.
4. **Instrument a database.** Add Postgres; `opentelemetry-bootstrap` will
   instrument the driver and every query becomes a span with `db.statement`.
5. **Kubernetes.** The OpenTelemetry Operator injects instrumentation into pods
   with a single annotation — no Dockerfile changes at all.
6. **Read the semantic conventions.** Standard attribute names are what make
   dashboards portable between teams and vendors.

Reference docs:
- <https://opentelemetry.io/docs/languages/python/> — the Python SDK
- <https://opentelemetry.io/docs/collector/configuration/> — collector config
- <https://opentelemetry.io/docs/specs/semconv/> — attribute naming
- <https://www.jaegertracing.io/docs/> — Jaeger

---

## Glossary

| Term | Meaning |
|---|---|
| **Trace** | Everything that happened while serving one request. |
| **Span** | One unit of work inside a trace: name, start time, duration, parent. |
| **Trace ID** | 32 hex chars shared by every span in a trace. The join key. |
| **Span ID** | 16 hex chars identifying one span. |
| **Parent span** | The span that caused this one. Nesting draws the waterfall. |
| **Attribute** | Searchable key/value on a span (`payment.amount=499`). |
| **Event** | Timestamped note inside a span (`fraud_check.completed`). |
| **Status** | `OK` / `ERROR`. Only `ERROR` makes a span red. |
| **Resource** | Facts about the *process*: `service.name`, version, environment. |
| **Context propagation** | Passing the trace ID onward, via the `traceparent` header. |
| **Tracer** | What your code calls to create spans. |
| **TracerProvider** | Owns the resource, sampler, and processors; creates tracers. |
| **Exporter** | Sends finished spans somewhere (OTLP, console, Jaeger…). |
| **Span processor** | Batches spans and hands them to the exporter. |
| **Sampler** | Decides which traces get recorded. |
| **OTLP** | OpenTelemetry Protocol. gRPC on 4317, HTTP on 4318. |
| **Collector** | Standalone service that receives, processes, and routes telemetry. |
| **Instrumentation** | Code that creates spans — auto (library patches) or manual (yours). |
| **Signal** | One kind of telemetry: traces, metrics, or logs. |

---

## Cheatsheet

```bash
# Install
pip install "opentelemetry-distro[otlp]"
opentelemetry-bootstrap -a install

# Run with zero code changes
opentelemetry-instrument python app.py
opentelemetry-instrument uvicorn main:app --port 8001
```

| Env var | Purpose |
|---|---|
| `OTEL_SERVICE_NAME` | The name you search for in Jaeger |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` (4317) or `http/protobuf` (4318) |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=prod,service.version=1.2` |
| `OTEL_TRACES_SAMPLER` / `_ARG` | `parentbased_traceidratio` / `0.1` |
| `OTEL_PYTHON_EXCLUDED_URLS` | `health,metrics` — skip noisy endpoints |
| `OTEL_BSP_SCHEDULE_DELAY` | Flush interval in ms (default 5000; this repo uses 500 so clicks feel instant) |
| `OTEL_TRACES_EXPORTER` | `otlp` (default) or `console` for quick local checks |

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer("my.tracer")

with tracer.start_as_current_span("checkout") as span:
    span.set_attribute("cart.items", 3)
    span.add_event("coupon.applied", {"code": "OTEL10"})
    try:
        do_work()
    except Exception as e:
        span.record_exception(e)
        span.set_status(Status(StatusCode.ERROR, str(e)))
        raise

@tracer.start_as_current_span("helper")      # decorator form
def helper(): ...

# Get the current trace ID (e.g. to log it or return it in a header)
ctx = trace.get_current_span().get_span_context()
trace_id = format(ctx.trace_id, "032x")
```

---

## Troubleshooting

| Symptom | Most likely cause | Check |
|---|---|---|
| No spans anywhere | SDK never configured | Is `opentelemetry-instrument` in the command? Is `otel_setup` imported? |
| Nothing reaches Jaeger | Protocol/port mismatch | `grpc` → 4317, `http/protobuf` → 4318. Nothing shows in Jaeger, but the app logs export failures — `docker compose logs gui`. |
| Spans in `make logs-collector`, none in Jaeger | Exporter/backend | Check `otlp/jaeger` endpoint in `collector/config.yaml`; is Jaeger up? |
| Trace has only 1 service | Propagation broken | Is the HTTP client instrumented? Does a proxy strip `traceparent`? |
| Half the spans missing | You looked too early | Spans batch. Wait ~2s, or lower `OTEL_BSP_SCHEDULE_DELAY`. |
| Trace ID exists but Jaeger 404s | Sampler dropped it | Check `OTEL_TRACES_SAMPLER_ARG`. |
| Everything green during an outage | `set_status` never called | `record_exception` alone does not mark failure. |
| Jaeger empty after restart | In-memory storage | Expected here. Use a real backend in production. |
| Spans under Gunicorn/uWSGI missing | Providers built pre-fork | Re-initialise the SDK in a post-fork hook. |
| Thousands of junk traces | Health checks / polling instrumented | `OTEL_PYTHON_EXCLUDED_URLS=health`, or don't use the instrumented client. |

---

## Self-check

Answer before expanding.

<details><summary>1. What single piece of data makes a set of spans one trace?</summary>

The **trace ID** — 32 hex characters carried in the `traceparent` header and
stamped on every span. Parent span IDs give the tree its shape, but the trace
ID is what groups them.
</details>

<details><summary>2. orders-api has zero OpenTelemetry code. Where do its spans come from?</summary>

The `opentelemetry-instrument` prefix in its Dockerfile CMD. It configures the
SDK from `OTEL_*` env vars and monkey-patches FastAPI and requests before the
app is imported.
</details>

<details><summary>3. Attribute or event: "the user's cart had 3 items"? And "the coupon was applied at 10:32:01"?</summary>

The cart size is an **attribute** (a fact about the span, searchable). The
coupon application is an **event** (something that happened at a moment inside
the span).
</details>

<details><summary>4. You call record_exception but Jaeger shows the span as OK. Why?</summary>

`record_exception` only attaches an exception event. You must also call
`span.set_status(Status(StatusCode.ERROR, ...))` to mark the span failed.
</details>

<details><summary>5. Why send telemetry to a collector instead of straight to Jaeger?</summary>

So applications don't know or care what the backend is. Swapping backends,
batching, retrying, scrubbing PII, enriching, and sampling all become one
config file instead of a code change in every service.
</details>

<details><summary>6. Your sampler is set to 0.1 and the trace you need is missing. What would have saved you?</summary>

**Tail sampling** in the collector: buffer the full trace, then keep it if it
errored or exceeded a latency threshold, and keep only a small percentage of
the rest. Head sampling decides before it knows whether the trace was interesting.
</details>

<details><summary>7. Should a span be named "POST /orders/2231" or "POST /orders"?</summary>

`POST /orders`. Span names must be **low cardinality** — one name per operation,
not per instance. The order ID belongs in an attribute.
</details>

---

**Done.** `make down` to stop everything, `make clean` to remove images and volumes.
