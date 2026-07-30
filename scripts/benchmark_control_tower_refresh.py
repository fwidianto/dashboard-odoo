"""Repeatable, host-gated Control Tower refresh benchmark."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.control_tower.refresh import (
    BENCHMARK_THRESHOLD_SECONDS,
    benchmark_classification,
    run_refresh_pipeline,
    sanitize_diagnostic,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark a safe Control Tower refresh.")
    parser.add_argument(
        "--confirm-pilot-host",
        help="Must match CT_PILOT_HOST_ID; prevents accidental runs on an unapproved host.",
    )
    parser.add_argument(
        "--confirm-read-only",
        action="store_true",
        help="Confirm that Odoo credentials and the environment are read-only.",
    )
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("CT_BATCH_SIZE", "500")))
    parser.add_argument("--log-file", type=Path)
    args = parser.parse_args()

    started_at = now_iso()
    host_id = os.getenv("CT_PILOT_HOST_ID")
    host_confirmed = bool(args.confirm_pilot_host and host_id and args.confirm_pilot_host == host_id)
    result = {
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "threshold_seconds": BENCHMARK_THRESHOLD_SECONDS,
        "outcome": "PENDING_HOST",
        "host_confirmed": host_confirmed,
        "run_id": None,
        "model_counts": {},
        "stage_timings": {},
        "log_file": str(args.log_file) if args.log_file else None,
    }

    if not host_confirmed or not args.confirm_read_only:
        print(json.dumps(result, indent=2))
        return 0

    started = perf_counter()
    try:
        refresh = run_refresh_pipeline(
            company_id=3,
            batch_size=args.batch_size,
            trigger="benchmark",
            requested_by="benchmark",
        )
        result["run_id"] = refresh.get("run_id")
        result["model_counts"] = refresh.get("model_counts") or {}
        result["stage_timings"] = refresh.get("stage_timings") or {}
        result["outcome"] = "COMPLETED"
    except Exception as exc:
        result["outcome"] = "FAILED"
        result["error_message"] = sanitize_diagnostic(exc)
    result["finished_at"] = now_iso()
    result["duration_seconds"] = round(perf_counter() - started, 3)
    if result["outcome"] == "COMPLETED":
        result["classification"] = benchmark_classification(
            outcome="COMPLETED",
            duration_seconds=result["duration_seconds"],
        )
    else:
        result["classification"] = "FAILED"

    output = json.dumps(result, indent=2, default=str)
    print(output)
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        args.log_file.write_text(output + "\n", encoding="utf-8")
    return 0 if result["classification"] in {"PASS", "PENDING_HOST"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
