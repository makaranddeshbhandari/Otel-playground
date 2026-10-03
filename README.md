# OpenTelemetry Playground

Learn distributed tracing by clicking buttons instead of reading specs.

Most OpenTelemetry tutorials end with one trace printed to your terminal. That's not the moment it clicks. It clicks when you press a button and watch a single request travel through three services, and you can finally see which one was slow.

So that's what this is. Press a button, get a trace, read it.

```bash
git clone git@github.com:LondheShubham153/otel-playground.git
cd otel-playground
make up
```

Open http://localhost:8501 and hit **Place an order**.

First run takes 2-3 minutes to build. After that it's a few seconds.

## What's running

```
   you click a button
         |
    gui (Streamlit)          :8501    sets up OTel by hand
         |
    orders-api               :8001    has zero OTel code in it
         |
    payments-api             :8002    custom spans, errors, a metric
         |
    otel-collector           :4317    prints every span to its log
         |
    Jaeger                   :16686   the UI you'll actually search in
```

Five containers, all disposable. Nothing gets installed on your machine.

## Then what

Work through [LEARN.md](LEARN.md). It's a 2 hour workshop that goes from "what even is a span" to "why aren't my spans showing up". Every section ends with something you have to do yourself, including one where you deliberately break context propagation so you know what that looks like when it happens for real.

If you'd rather just read code, go in this order. About 20 minutes.

1. `gui/app.py` - what a button press actually does
2. `gui/otel_setup.py` - the entire SDK setup. It's ten lines. That's the point
3. `services/orders/main.py` and its `Dockerfile` - spans without writing any OTel code
4. `services/payments/main.py` - your own spans, attributes, events, errors
5. `collector/config.yaml` - where the data goes and why a collector exists

Every file starts with one line telling you which step it is and which part of LEARN.md explains it. The rest is left uncommented on purpose, because the code is short enough to read.

The supporting files are `docker-compose.yml` (every OTEL_ env var in one block), `gui/jaeger_client.py` (reads traces back out of Jaeger), and `scripts/traffic.py` (load generator so Jaeger has something to search).

## Commands

```
make up               start everything
make down             stop
make logs-collector   watch your spans scroll past as plain text
make traffic          generate background load
make health           check every endpoint is answering
make urls             print the links
make rebuild          after you change requirements.txt or a Dockerfile
make clean            nuke it all
```

`make logs-collector` is the one worth remembering. If spans show up there but not in Jaeger, your app is fine and your exporter isn't. That one check saves a lot of guessing.

## Ports

| Port | What |
|---|---|
| 8501 | the playground UI |
| 16686 | Jaeger |
| 8001 / 8002 | orders-api / payments-api, both have `/docs` |
| 4317 / 4318 | collector, OTLP gRPC and HTTP |
| 13133 | collector health check |

## When it doesn't work

**"No spans found yet"** - give it a second. Spans travel app to collector to Jaeger and that takes a moment. If it stays empty, `make logs-collector`.

**Nothing in Jaeger at all** - almost always protocol vs port. `grpc` is 4317, `http/protobuf` is 4318. Mix them up and nothing reaches Jaeger. It looks silent, but it isn't: the exporter logs failures on every flush, so `docker compose logs gui` will tell you. This is the single most common OTel mistake and you will make it at least once.

**Spans in the collector log but not Jaeger** - then it's the exporter, not your app. Check the `otlp/jaeger` block in `collector/config.yaml`.

**Only one or two services in the trace** - context propagation broke. LEARN.md step 4 covers exactly this.

**Jaeger is empty after a restart** - that's expected, storage is in memory.

**Port already in use** - something else owns 8501, 16686 or 4317. Change the left side of the mapping in `docker-compose.yml`.

**Your code change did nothing** - `main.py` and `app.py` hot reload. Anything in `requirements.txt` or a Dockerfile needs `make rebuild`.

## Shortcuts I took

This is teaching code, so a few things are simpler than they'd be in production:

Jaeger stores traces in memory, so a restart wipes them. Real setups use Elasticsearch or Tempo. Sampling is at 100%, which is fine for a workshop and expensive at real traffic. There's no TLS or auth anywhere. The Dockerfiles are single stage because they're meant to be read, not shipped.

Only traces go to a real backend. Metrics are in there so you've seen the API once, but they only land in the collector's log. Adding Prometheus and Grafana is the first exercise at the end of LEARN.md.

Built for the Udaan batch, but it works fine on its own.
