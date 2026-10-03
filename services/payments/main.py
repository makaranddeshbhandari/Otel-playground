"""Step 4 of 5 — your own spans, attributes, events, errors. See LEARN.md §5.2."""

import random
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

# The API only. The SDK was already configured by `opentelemetry-instrument`.
tracer = trace.get_tracer("payments.tracer")
meter = metrics.get_meter("payments.meter")

payments_counter = meter.create_counter(
    "payments.processed",
    description="Number of payment attempts, split by outcome",
    unit="1",
)

app = FastAPI(title="payments-api", version="1.0.0")


class PaymentRequest(BaseModel):
    order_id: str
    amount: float = Field(gt=0)
    customer_id: str = "student-01"
    scenario: str = "happy"  # happy | slow | error


@app.get("/health")
def health():
    return {"status": "ok", "service": "payments-api"}


@app.get("/echo-headers")
def echo_headers(request: Request):
    """Echoes back every header received, so you can see traceparent. LEARN.md §4.1."""
    return {"received_headers": dict(request.headers)}


# Decorator form of span creation.
@tracer.start_as_current_span("payment.fraud_check")
def fraud_check(customer_id: str, amount: float) -> float:
    span = trace.get_current_span()
    time.sleep(random.uniform(0.01, 0.05))
    score = round(random.uniform(0, 0.4), 3)
    span.set_attribute("fraud.customer_id", customer_id)
    span.set_attribute("fraud.amount", amount)
    span.set_attribute("fraud.score", score)
    return score


@app.post("/payments")
def charge(req: PaymentRequest):
    with tracer.start_as_current_span("payment.authorize") as span:
        span.set_attribute("payment.order_id", req.order_id)
        span.set_attribute("payment.amount", req.amount)
        span.set_attribute("payment.currency", "INR")
        span.set_attribute("payment.scenario", req.scenario)
        span.set_attribute("enduser.id", req.customer_id)

        score = fraud_check(req.customer_id, req.amount)
        span.add_event("fraud_check.completed", {"fraud.score": score})

        with tracer.start_as_current_span("payment.gateway_call") as gateway:
            if req.scenario == "slow":
                gateway.set_attribute("gateway.name", "slowbank")
                delay = random.uniform(1.5, 3.0)
            else:
                gateway.set_attribute("gateway.name", "fastbank")
                delay = random.uniform(0.02, 0.12)
            time.sleep(delay)
            gateway.set_attribute("gateway.latency_ms", round(delay * 1000, 1))

        declined = None
        authorized = None

        if req.scenario == "error":
            error = RuntimeError("card declined by issuer (insufficient funds)")
            span.record_exception(error)
            # set_status is what marks the span failed. record_exception alone does not.
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("payment.status", "declined")
            payments_counter.add(1, {"payment.status": "declined"})
            declined = str(error)
        else:
            span.set_attribute("payment.status", "authorized")
            payments_counter.add(1, {"payment.status": "authorized"})
            authorized = {
                "payment_id": f"pay-{uuid.uuid4().hex[:10]}",
                "order_id": req.order_id,
                "status": "authorized",
                "amount": req.amount,
                "currency": "INR",
                "fraud_score": score,
                "gateway_latency_ms": round(delay * 1000, 1),
            }

    # Raised outside the span: raising inside makes the SDK record a second
    # exception event and overwrite the status message set above.
    if declined:
        raise HTTPException(status_code=402, detail=declined)
    return authorized
