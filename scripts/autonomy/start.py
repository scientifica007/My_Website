#!/usr/bin/env python3
"""Perform the one-time transition from BOOTSTRAP to ACTIVE."""
from __future__ import annotations

import datetime as dt
import os
import sys

from core import AUTONOMY, METRICS, STATE, bootstrap_errors, load_json, save_json

DRY_RUN = AUTONOMY / "prestart-dryrun.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    errors = bootstrap_errors()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if os.environ.get("CONFIRM_EXPERIMENT_START") != "YES":
        print("Refusing START without CONFIRM_EXPERIMENT_START=YES", file=sys.stderr)
        return 3
    if not os.environ.get("AI_API_KEY"):
        print("Refusing START: AI_API_KEY is unavailable", file=sys.stderr)
        return 4
    if not DRY_RUN.is_file():
        print("Refusing START: required technical dry run has not been recorded", file=sys.stderr)
        return 7
    dry_run = load_json(DRY_RUN)
    if dry_run.get("passed") is not True:
        print("Refusing START: technical dry run did not pass", file=sys.stderr)
        return 8

    state = load_json(STATE)
    metrics = load_json(METRICS)
    if state.get("started_at") or state.get("armed"):
        print("Refusing START: experiment has already been armed", file=sys.stderr)
        return 5
    if state.get("experiment_state") != "BOOTSTRAP":
        print(f"Refusing START from state {state.get('experiment_state')!r}", file=sys.stderr)
        return 6

    now = utc_now()
    state["armed"] = True
    state["experiment_state"] = "ACTIVE"
    state["current_stage"] = "READY_FOR_FIRST_CYCLE"
    state["infrastructure_status"] = "AVAILABLE"
    state["started_at"] = now
    state["last_run_result"] = "EXPERIMENT_STARTED"
    metrics["started_at"] = now
    save_json(STATE, state)
    save_json(METRICS, metrics)
    print(f"EXPERIMENT STARTED at {now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
