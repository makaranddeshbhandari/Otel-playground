"""Step 3 of 5 — spans with zero OpenTelemetry code. See LEARN.md §5.1."""

import os
import uuid

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://payments-api:8002")

app = FastAPI(title="orders-api", version="1.0.0")


class OrderRequest(BaseModel):
    amount: float = Field(default=499.0, gt=0)
    customer_id: str = "student-01"
    scenario: str = "happy"  # happy | slow | error


@app.get("/health")
def health():
    return {"status": "ok", "service": "orders-api"}


@app.post("/orders")
def create_order(req: OrderRequest):
    order_id = f"ord-{uuid.uuid4().hex[:8]}"

    if req.amount > 100_000:
        raise HTTPException(status_code=400, detail="amount exceeds order limit")

    # `requests` is patched, so this call carries a traceparent header.
    response = requests.post(
        f"{PAYMENTS_URL}/payments",
        json={
            "order_id": order_id,
            "amount": req.amount,
            "customer_id": req.customer_id,
            "scenario": req.scenario,
        },
        timeout=15,
    )

    if response.status_code == 402:
        raise HTTPException(
            status_code=402,
            detail=f"payment declined for {order_id}: {response.json().get('detail')}",
        )
    response.raise_for_status()

    return {
        "order_id": order_id,
        "status": "confirmed",
        "customer_id": req.customer_id,
        "amount": req.amount,
        "payment": response.json(),
    }


@app.get("/debug/headers")
def debug_headers():
    """Shows the traceparent header this service sends onward. Used by LEARN.md §4.1."""
    return requests.get(f"{PAYMENTS_URL}/echo-headers", timeout=10).json()
