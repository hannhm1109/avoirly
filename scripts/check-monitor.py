"""Run on a private scheduler; a nonzero exit triggers the scheduler's alert."""

import json
import os
from decimal import Decimal

import httpx


def main():
    try:
        origin = os.environ["AVOIRLY_API_ORIGIN"]
        if not origin.startswith("https://"):
            raise ValueError("HTTPS required")
        result = httpx.get(
            origin + "/ops/metrics",
            headers={"Authorization": "Bearer " + os.environ["AVOIRLY_METRICS_TOKEN"]},
            timeout=15,
        )
        result.raise_for_status()
        state = result.json()
        spend = sum(
            (Decimal(x["estimated_usd"] or "0") for x in state["reported_usage_24h"]),
            Decimal(0),
        )
        checks = {
            "worker": state["worker_healthy"],
            "leases": state["expired_leases"] == 0,
            "deletion_queue": state["pending_file_deletions"] == 0,
            "failures": state["failures_24h"]
            < int(os.environ.get("AVOIRLY_ALERT_FAILURES", "3")),
            "reported_spend": spend < Decimal(os.environ["AVOIRLY_ALERT_USD_24H"]),
            "pricing": all(
                x["unpriced_records"] == 0 for x in state["reported_usage_24h"]
            ),
        }
        print(json.dumps(checks))
        return 0 if all(checks.values()) else 1
    except Exception as exc:  # noqa: BLE001 - redact all network details
        print(json.dumps({"monitor_error": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
