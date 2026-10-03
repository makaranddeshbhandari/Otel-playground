#!/usr/bin/env python3
"""Background load so Jaeger has data to explore. Stdlib only: `make traffic`."""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request


def post_order(base_url: str, scenario: str, timeout: float = 30.0) -> int:
    payload = json.dumps(
        {
            "amount": round(random.uniform(99, 4999), 2),
            "customer_id": f"student-{random.randint(1, 40):02d}",
            "scenario": scenario,
        }
    ).encode()

    request = urllib.request.Request(
        f"{base_url}/orders",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        print(f"  ! cannot reach {base_url}: {exc.reason}", file=sys.stderr)
        return 0


def pick_scenario(error_rate: float, slow_rate: float) -> str:
    roll = random.random()
    if roll < error_rate:
        return "error"
    if roll < error_rate + slow_rate:
        return "slow"
    return "happy"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8001", help="orders-api base URL")
    parser.add_argument("--rps", type=float, default=2.0, help="requests per second")
    parser.add_argument("--duration", type=float, default=0, help="seconds (0 = forever)")
    parser.add_argument("--error-rate", type=float, default=0.05, help="fraction of 'error' scenarios")
    parser.add_argument("--slow-rate", type=float, default=0.10, help="fraction of 'slow' scenarios")
    args = parser.parse_args()

    interval = 1.0 / max(args.rps, 0.01)
    deadline = time.time() + args.duration if args.duration else None
    counts = {"happy": 0, "slow": 0, "error": 0, "unreachable": 0}

    print(f"→ {args.url}  |  {args.rps} req/s  |  Ctrl-C to stop")
    try:
        while deadline is None or time.time() < deadline:
            scenario = pick_scenario(args.error_rate, args.slow_rate)
            status = post_order(args.url, scenario)
            counts["unreachable" if status == 0 else scenario] += 1
            total = sum(counts.values())
            print(
                f"\r  sent {total:5d}   happy {counts['happy']:5d}   "
                f"slow {counts['slow']:4d}   error {counts['error']:4d}   "
                f"unreachable {counts['unreachable']:4d}",
                end="",
                flush=True,
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        pass

    print("\nDone. Now open Jaeger → Search → service `orders-api`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
