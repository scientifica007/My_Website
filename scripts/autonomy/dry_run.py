#!/usr/bin/env python3
"""Run a non-product technical PDSA dry run required before experiment START."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from core import AUTONOMY, PROVIDER, load_json, save_json

ARTIFACT = AUTONOMY / "prestart-dryrun.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def call_json(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    cfg = load_json(PROVIDER)
    key = os.environ.get(cfg.get("api_key_env", "AI_API_KEY"))
    if not key:
        raise RuntimeError("missing AI_API_KEY")
    base_env = cfg.get("base_url_env", "AI_BASE_URL")
    base = (os.environ.get(base_env) or cfg["default_base_url"]).rstrip("/")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if "qwen/qwen3.6" in model:
        payload["reasoning_format"] = "hidden"
        payload["reasoning_effort"] = "none"
    elif "gpt-oss" in model:
        payload["reasoning_effort"] = "low"

    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "My_Website-Prestart-DryRun/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details[:900]}") from exc
    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)
    if not isinstance(result, dict):
        raise RuntimeError("response is not a JSON object")
    return result


def require_keys(name: str, value: dict[str, Any], keys: set[str]) -> None:
    missing = sorted(keys - set(value))
    if missing:
        raise RuntimeError(f"{name} missing keys: {missing}")


def main() -> int:
    cfg = load_json(PROVIDER)
    models = cfg["models"]
    started = utc_now()
    try:
        collector_prompt = (
            "Technical dry run only; do not design the real product. "
            "Given a synthetic empty demo repository whose goal is to create one Arabic RTL hello page, "
            "return concise JSON with keys summary, classifications, evidence, smart_objective, "
            "acceptance_criteria, rationale, remaining_goal_gaps. Use at most 3 items per array and "
            "keep each string under 30 words."
        )
        collector = call_json(models["collector"], collector_prompt, 900)
        require_keys(
            "collector",
            collector,
            {
                "summary",
                "classifications",
                "evidence",
                "smart_objective",
                "acceptance_criteria",
                "rationale",
                "remaining_goal_gaps",
            },
        )

        planner_prompt = (
            "Technical dry run only; do not affect the real repository. "
            "Create a tiny plan for this synthetic objective and return concise JSON with keys "
            "objective_alignment, steps, intended_files, verification, risks, allowed_fallbacks, "
            "expected_evidence. Maximum 4 steps. Objective: "
            + str(collector.get("smart_objective", "create an Arabic RTL hello page"))
        )
        planner = call_json(models["planner"], planner_prompt, 1100)
        require_keys(
            "planner",
            planner,
            {
                "objective_alignment",
                "steps",
                "intended_files",
                "verification",
                "risks",
                "allowed_fallbacks",
                "expected_evidence",
            },
        )

        reviewer_prompt = (
            "Technical dry run only. Review this synthetic plan. Return concise JSON with keys "
            "decision, critical_issues, verification_gaps, risks, comments. decision must be "
            "APPROVE or REVISE. PLAN: " + json.dumps(planner, ensure_ascii=False)
        )
        reviewer = call_json(models["reviewer"], reviewer_prompt, 700)
        require_keys(
            "reviewer",
            reviewer,
            {"decision", "critical_issues", "verification_gaps", "risks", "comments"},
        )
        if reviewer.get("decision") not in {"APPROVE", "REVISE"}:
            raise RuntimeError("reviewer returned invalid decision")

        save_json(
            ARTIFACT,
            {
                "schema_version": 1,
                "passed": True,
                "started_at": started,
                "completed_at": utc_now(),
                "scope": "synthetic technical PDSA dry run; no product-development decision",
                "checks": ["collector_json", "planner_json", "reviewer_json"],
                "models": {
                    "collector": models["collector"],
                    "planner": models["planner"],
                    "reviewer": models["reviewer"],
                },
            },
        )
        print("Pre-START technical PDSA dry run: PASS")
        return 0
    except Exception as exc:
        save_json(
            ARTIFACT,
            {
                "schema_version": 1,
                "passed": False,
                "started_at": started,
                "completed_at": utc_now(),
                "scope": "synthetic technical PDSA dry run; no product-development decision",
                "error": str(exc)[:1600],
            },
        )
        print(f"Pre-START technical PDSA dry run: FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
