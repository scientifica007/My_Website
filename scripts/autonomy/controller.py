#!/usr/bin/env python3
"""Run at most one autonomous PDSA product cycle or one final audit."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

from core import (
    METRICS,
    POLICY,
    ROOT,
    STATE,
    GovernanceError,
    assert_executor_path_allowed,
    assert_plan_frozen,
    bootstrap_errors,
    freeze_plan,
    load_json,
    save_json,
)
from provider import AIProvider

CYCLES = ROOT / "cycles"
FINAL_AUDITS = ROOT / "final-audits"

EXCLUDED_PREFIXES = (
    ".git/",
    "node_modules/",
    ".venv/",
    "dist/",
    "build/",
    "coverage/",
    "cycles/",
    "final-audits/",
)

CORE_CONTEXT = (
    "PRODUCT_GOAL.md",
    "DEFINITION_OF_DONE.md",
    "AGENTS.md",
    "PROJECT_MEMORY.md",
    "README.md",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def role_system(role: str) -> str:
    common = """You are one logical role in an autonomous software-development experiment.
The product mission is in PRODUCT_GOAL.md and completion criteria are in DEFINITION_OF_DONE.md.
Follow AGENTS.md and the fixed PDSA governance. Return JSON only.
Do not ask a human to make product-development decisions.
Do not weaken tests, product requirements, or governance to claim success.
The repository is public: use synthetic data only and never request, reveal, or commit secrets.
"""
    roles = {
        "collector": """Role: COLLECTOR.
Assess current evidence, classify the most important gaps, and choose exactly one cycle-sized SMART objective.
The objective must measurably reduce the gap to the final product. Do not create a fixed long-term roadmap.
""",
        "planner": """Role: PLANNER.
Create a bounded plan for the supplied SMART objective. Include deterministic acceptance evidence.
Do not execute. Anticipate allowed fallbacks before freeze; unexpected repairs cannot be added during Do.
""",
        "reviewer": """Role: REVIEWER.
Critically assess the plan. APPROVE only if it is relevant, measurable, cycle-sized, safe, and verifiable.
Otherwise return REVISE with specific defects. You do not execute or silently rewrite the plan.
""",
        "executor": """Role: EXECUTOR.
Execute only the frozen plan. You may write/delete product files, tests, and product documentation.
Never modify protected experiment infrastructure, cycle history, the frozen plan, or Definition of Done.
Do not introduce an unplanned repair because an error appeared; report deviations for Study instead.
""",
        "study_analyst": """Role: STUDY ANALYST.
Compare expected outcomes with Do and deterministic Verify evidence. Diagnose gaps without altering history.
Distinguish plan error, execution error, assumption error, verification gap, and useful learning.
""",
        "act_analyst": """Role: ACT ANALYST.
Turn Study evidence into durable learning for later cycles and assess remaining product gaps.
Recommend FINAL_AUDIT_PENDING only when evidence plausibly covers the full Definition of Done.
""",
        "final_auditor": """Role: INDEPENDENT FINAL AUDITOR.
Audit every material Definition of Done requirement conservatively from repository evidence and verification.
PASS only when the product is genuinely ready for human user evaluation as a final candidate.
""",
    }
    return common + roles[role]


def file_tree(limit: int = 350) -> str:
    names: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        names.append(rel)
        if len(names) >= limit:
            names.append("... tree truncated ...")
            break
    return "\n".join(names)


def read_file(rel: str, limit: int = 8000) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except UnicodeDecodeError:
        return None


def latest_learning() -> str:
    if not CYCLES.exists():
        return "No earlier autonomous product cycle."
    dirs = sorted(p for p in CYCLES.glob("PDSA-*") if p.is_dir())
    if not dirs:
        return "No earlier autonomous product cycle."
    latest = dirs[-1]
    parts: list[str] = [f"Latest cycle: {latest.name}"]
    for name in ("cycle-status.json", "study.json", "act.json", "verification.json"):
        path = latest / name
        if path.exists():
            parts.append(f"## {name}\n{path.read_text(encoding='utf-8')[:5000]}")
    return "\n\n".join(parts)


def context(extra: list[str] | None = None) -> str:
    policy = load_json(POLICY)
    max_chars = int(policy.get("max_context_characters", 16000))
    sections: list[str] = []
    for rel in CORE_CONTEXT:
        text = read_file(rel)
        if text is not None:
            sections.append(f"## FILE {rel}\n{text}")
    sections.append("## LATEST LEARNING\n" + latest_learning())
    sections.append("## REPOSITORY TREE\n" + file_tree())
    for rel in extra or []:
        if rel in CORE_CONTEXT or rel.startswith("cycles/"):
            continue
        text = read_file(rel)
        if text is not None:
            sections.append(f"## REQUESTED FILE {rel}\n{text}")
    return "\n\n".join(sections)[:max_chars]


def write_once(path: pathlib.Path, data: dict[str, Any]) -> None:
    if path.exists():
        raise GovernanceError(f"historical artifact already exists: {path.relative_to(ROOT)}")
    save_json(path, data)


def render_plan(objective: dict[str, Any], plan: dict[str, Any]) -> str:
    criteria = objective.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        criteria = []
    return (
        "# Frozen PDSA Plan\n\n"
        "## SMART Objective\n\n"
        f"{objective.get('smart_objective', '')}\n\n"
        "## Acceptance Criteria\n\n"
        + "\n".join(f"- {item}" for item in criteria)
        + "\n\n## Approved Plan\n\n```json\n"
        + json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n"
    )


def snapshot(paths: list[str]) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {}
    for rel in paths:
        path = ROOT / rel
        result[rel] = path.read_bytes() if path.exists() and path.is_file() else None
    return result


def restore(originals: dict[str, bytes | None]) -> None:
    for rel, content in originals.items():
        path = ROOT / rel
        if content is None:
            if path.exists() and path.is_file():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def apply_operations(
    operations: list[dict[str, Any]], cycle_dir: pathlib.Path
) -> tuple[dict[str, bytes | None], list[dict[str, str]]]:
    policy = load_json(POLICY)
    limit = int(policy.get("max_executor_operations", 30))
    if len(operations) > limit:
        raise GovernanceError(f"too many executor operations: {len(operations)} > {limit}")

    validated: list[tuple[dict[str, Any], pathlib.Path]] = []
    touched: list[str] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise GovernanceError("executor operation must be an object")
        action = operation.get("action")
        rel = operation.get("path")
        if action not in {"write", "delete"} or not isinstance(rel, str):
            raise GovernanceError(f"invalid operation: {operation!r}")
        target = assert_executor_path_allowed(rel)
        if action == "write" and not isinstance(operation.get("content"), str):
            raise GovernanceError(f"write requires complete string content: {rel}")
        validated.append((operation, target))
        if rel not in touched:
            touched.append(rel)

    originals = snapshot(touched)
    applied: list[dict[str, str]] = []
    try:
        for operation, target in validated:
            action = str(operation["action"])
            rel = str(operation["path"])
            if action == "write":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(operation["content"]), encoding="utf-8")
            else:
                if target.exists():
                    if not target.is_file():
                        raise GovernanceError(f"cannot delete directory: {rel}")
                    target.unlink()
            applied.append({"action": action, "path": rel})
        assert_plan_frozen(cycle_dir)
        return originals, applied
    except Exception:
        restore(originals)
        raise


def sanitized_env() -> dict[str, str]:
    policy = load_json(POLICY)
    fragments = [str(x).upper() for x in policy.get("forbidden_secret_name_fragments", [])]
    clean: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if key in {"GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"}:
            continue
        if any(fragment in upper for fragment in fragments):
            continue
        clean[key] = value
    return clean


def run(command: list[str], timeout: int = 900) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=sanitized_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[-7000:],
            "stderr": result.stderr[-7000:],
        }
    except FileNotFoundError as exc:
        return {"command": command, "exit_code": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "exit_code": 124, "stdout": "", "stderr": str(exc)}


def verify_product() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        run([sys.executable, "scripts/autonomy/validate.py"]),
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests/autonomy", "-v"]),
    ]

    package_path = ROOT / "package.json"
    if package_path.exists():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        if (ROOT / "package-lock.json").exists():
            checks.append(run(["npm", "ci"]))
        else:
            checks.append(run(["npm", "install", "--no-package-lock"]))
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        for name in ("lint", "typecheck", "test", "build"):
            if name in scripts:
                checks.append(run(["npm", "run", name]))

    if (ROOT / "pyproject.toml").exists():
        checks.append(run([sys.executable, "-m", "compileall", "-q", "."]))

    return {
        "passed": all(item["exit_code"] == 0 for item in checks),
        "checks": checks,
        "verified_at": utc_now(),
    }


def ask_executor(
    ai: AIProvider,
    objective: dict[str, Any],
    frozen_plan: str,
    base_context: str,
) -> dict[str, Any]:
    response = ai.ask_json(
        "executor",
        role_system("executor"),
        f"""Return one of two JSON forms.

If more repository contents are required:
{{"status":"NEED_CONTEXT","read_files":["path", ...]}}

Otherwise:
{{
 "status":"EXECUTE",
 "summary":"...",
 "operations":[
   {{"action":"write","path":"relative/path","content":"COMPLETE UTF-8 CONTENT"}},
   {{"action":"delete","path":"relative/path"}}
 ],
 "deviations":[],
 "acceptance_evidence_expected":[]
}}

FROZEN PLAN:
{frozen_plan}

SMART OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}

REPOSITORY CONTEXT:
{base_context}
""",
        max_tokens=3500,
    )
    if response.get("status") != "NEED_CONTEXT":
        return response

    requested = response.get("read_files", [])
    if not isinstance(requested, list):
        raise GovernanceError("NEED_CONTEXT requires read_files array")
    max_files = int(load_json(POLICY).get("max_executor_read_files", 12))
    clean = [
        rel for rel in requested[:max_files]
        if isinstance(rel, str) and (ROOT / rel).is_file() and not rel.startswith("cycles/")
    ]
    return ai.ask_json(
        "executor",
        role_system("executor"),
        f"""Now execute the frozen plan using the requested file contents.
Return status EXECUTE with summary, operations, deviations, acceptance_evidence_expected.
Operations must contain complete file contents, not patches.

FROZEN PLAN:
{frozen_plan}

SMART OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}

EXTENDED CONTEXT:
{context(clean)}
""",
        max_tokens=3500,
    )


def close_planning_failure(
    cycle_dir: pathlib.Path,
    state: dict[str, Any],
    metrics: dict[str, Any],
    review_history: list[dict[str, Any]],
) -> None:
    write_once(
        cycle_dir / "cycle-status.json",
        {
            "status": "ABORTED_BEFORE_FREEZE",
            "reason": "plan failed autonomous review after allowed revisions",
            "closed_at": utc_now(),
        },
    )
    write_once(
        cycle_dir / "study.json",
        {
            "cycle_conclusion": "Planning process did not reach an approvable frozen plan.",
            "review_history_summary": review_history,
            "errors_to_remember": ["Do not repeat unresolved critical review defects."],
        },
    )
    write_once(
        cycle_dir / "act.json",
        {
            "knowledge_to_carry_forward": [
                "The latest proposed plan was not acceptable under governance; next cycle must re-assess from evidence."
            ],
            "candidate_improvements": [
                "Choose a narrower or better-verifiable SMART objective and address recorded review defects."
            ],
            "final_audit_recommended": False,
        },
    )
    state["current_stage"] = "READY_FOR_NEXT_CYCLE"
    state["last_run_result"] = "PLANNING_ABORT_RECORDED"
    metrics["autonomous_decision_blocks"] = int(metrics.get("autonomous_decision_blocks", 0)) + 1


def run_cycle(ai: AIProvider, state: dict[str, Any], metrics: dict[str, Any]) -> None:
    policy = load_json(POLICY)
    cycle_number = int(state.get("current_cycle", 0)) + 1
    cycle_dir = CYCLES / f"PDSA-{cycle_number:04d}"
    if cycle_dir.exists():
        raise GovernanceError(f"cycle already exists: {cycle_dir.name}")
    cycle_dir.mkdir(parents=True)
    state["current_cycle"] = cycle_number
    state["current_stage"] = "COLLECT"
    metrics["cycles_started"] = int(metrics.get("cycles_started", 0)) + 1
    save_json(STATE, state)
    save_json(METRICS, metrics)

    base_context = context()
    objective = ai.ask_json(
        "collector",
        role_system("collector"),
        f"""Collect/classify current evidence and choose exactly one next SMART objective.
Return JSON keys:
summary, classifications (array), evidence (array), smart_objective,
acceptance_criteria (array), rationale, remaining_goal_gaps (array).

REPOSITORY:
{base_context}
""",
        max_tokens=2600,
    )
    write_once(cycle_dir / "collection.json", objective)

    state["current_stage"] = "PLAN"
    save_json(STATE, state)
    plan = ai.ask_json(
        "planner",
        role_system("planner"),
        f"""Design the cycle plan.
Return JSON keys:
objective_alignment, steps (array), intended_files (array), verification (array),
risks (array), allowed_fallbacks (array), expected_evidence (array).

OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}

CONTEXT:
{base_context}
""",
        max_tokens=3200,
    )

    history: list[dict[str, Any]] = []
    approved = False
    max_revisions = int(policy.get("max_plan_revisions", 3))
    for index in range(max_revisions + 1):
        state["current_stage"] = "PLAN_REVIEW"
        save_json(STATE, state)
        review = ai.ask_json(
            "reviewer",
            role_system("reviewer"),
            f"""Review the plan and return:
{{"decision":"APPROVE|REVISE","critical_issues":[],"verification_gaps":[],"risks":[],"comments":"..."}}.

OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}

PLAN:
{json.dumps(plan, ensure_ascii=False)}
""",
            max_tokens=2000,
        )
        history.append({"revision": index, "plan": plan, "review": review})
        if review.get("decision") == "APPROVE":
            approved = True
            break
        metrics["plans_rejected"] = int(metrics.get("plans_rejected", 0)) + 1
        if index == max_revisions:
            break
        state["current_stage"] = "PLAN_REVISION"
        save_json(STATE, state)
        metrics["plan_revisions"] = int(metrics.get("plan_revisions", 0)) + 1
        plan = ai.ask_json(
            "planner",
            role_system("planner"),
            f"""Revise the plan to resolve the review while keeping the SMART objective fixed.
Return the full plan object with the same keys.

OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}
CURRENT PLAN:
{json.dumps(plan, ensure_ascii=False)}
REVIEW:
{json.dumps(review, ensure_ascii=False)}
""",
            max_tokens=3200,
        )

    write_once(cycle_dir / "plan-review.json", {"approved": approved, "history": history})
    if not approved:
        close_planning_failure(cycle_dir, state, metrics, history)
        metrics["cycles_completed"] = int(metrics.get("cycles_completed", 0)) + 1
        state["last_completed_cycle"] = cycle_number
        save_json(STATE, state)
        save_json(METRICS, metrics)
        return

    plan_path = cycle_dir / "plan.md"
    plan_path.write_text(render_plan(objective, plan), encoding="utf-8")
    digest = freeze_plan(cycle_dir)
    state["current_stage"] = "PLAN_FROZEN"
    save_json(STATE, state)

    state["current_stage"] = "DO"
    save_json(STATE, state)
    executor = ask_executor(ai, objective, plan_path.read_text(encoding="utf-8"), base_context)
    if executor.get("status") != "EXECUTE":
        raise GovernanceError("executor did not return EXECUTE after context allowance")
    operations = executor.get("operations", [])
    if not isinstance(operations, list):
        raise GovernanceError("executor operations must be an array")

    originals: dict[str, bytes | None] = {}
    applied: list[dict[str, str]] = []
    execution_error: str | None = None
    try:
        originals, applied = apply_operations(operations, cycle_dir)
    except Exception as exc:
        execution_error = str(exc)

    execution_record = {
        "frozen_plan_sha256": digest,
        "summary": executor.get("summary"),
        "requested_operations": [
            {"action": item.get("action"), "path": item.get("path")}
            for item in operations if isinstance(item, dict)
        ],
        "applied_operations": applied,
        "reported_deviations": executor.get("deviations", []),
        "acceptance_evidence_expected": executor.get("acceptance_evidence_expected", []),
        "execution_error": execution_error,
        "executed_at": utc_now(),
    }
    write_once(cycle_dir / "execution.json", execution_record)
    assert_plan_frozen(cycle_dir)

    state["current_stage"] = "VERIFY"
    save_json(STATE, state)
    verification = (
        verify_product()
        if execution_error is None
        else {
            "passed": False,
            "checks": [],
            "execution_error": execution_error,
            "verified_at": utc_now(),
        }
    )

    if not verification["passed"]:
        metrics["execution_failures"] = int(metrics.get("execution_failures", 0)) + 1
        metrics["verification_failures"] = int(metrics.get("verification_failures", 0)) + 1
        if originals:
            restore(originals)
            metrics["rollbacks"] = int(metrics.get("rollbacks", 0)) + 1
            verification["product_changes_rolled_back"] = True
    write_once(cycle_dir / "verification.json", verification)
    assert_plan_frozen(cycle_dir)

    state["current_stage"] = "STUDY"
    save_json(STATE, state)
    study = ai.ask_json(
        "study_analyst",
        role_system("study_analyst"),
        f"""Study the cycle evidence. Return JSON keys:
expected_vs_actual, findings (array), root_causes (array),
errors_to_remember (array), successful_learning (array),
unresolved_gaps (array), cycle_conclusion.

OBJECTIVE:
{json.dumps(objective, ensure_ascii=False)}
FROZEN PLAN:
{plan_path.read_text(encoding='utf-8')}
EXECUTION:
{json.dumps(execution_record, ensure_ascii=False)}
VERIFICATION:
{json.dumps(verification, ensure_ascii=False)}
""",
        max_tokens=2800,
    )
    write_once(cycle_dir / "study.json", study)

    state["current_stage"] = "ACT"
    save_json(STATE, state)
    act = ai.ask_json(
        "act_analyst",
        role_system("act_analyst"),
        f"""Produce Act output. Return JSON keys:
knowledge_to_carry_forward (array), candidate_improvements (array),
risks_for_next_cycle (array), remaining_goal_gaps (array),
final_audit_recommended (boolean), final_audit_rationale.

CURRENT PRODUCT CONTEXT:
{context()}

STUDY:
{json.dumps(study, ensure_ascii=False)}
""",
        max_tokens=2500,
    )
    write_once(cycle_dir / "act.json", act)
    write_once(
        cycle_dir / "cycle-status.json",
        {
            "status": "CLOSED",
            "verification_passed": bool(verification["passed"]),
            "closed_at": utc_now(),
        },
    )

    metrics["cycles_completed"] = int(metrics.get("cycles_completed", 0)) + 1
    state["last_completed_cycle"] = cycle_number
    state["last_run_result"] = "CYCLE_COMPLETED"
    if bool(act.get("final_audit_recommended")):
        state["experiment_state"] = "FINAL_AUDIT_PENDING"
        state["current_stage"] = "FINAL_AUDIT_PENDING"
    else:
        state["current_stage"] = "READY_FOR_NEXT_CYCLE"
    save_json(STATE, state)
    save_json(METRICS, metrics)


def run_final_audit(ai: AIProvider, state: dict[str, Any], metrics: dict[str, Any]) -> None:
    FINAL_AUDITS.mkdir(exist_ok=True)
    number = int(metrics.get("final_audits", 0)) + 1
    metrics["final_audits"] = number
    verification = verify_product()
    audit = ai.ask_json(
        "final_auditor",
        role_system("final_auditor"),
        f"""Audit the product against every material requirement in DEFINITION_OF_DONE.md.
Return JSON keys:
decision ("PASS" or "FAIL"), criteria (array of objects with requirement,status,evidence,gap),
critical_gaps (array), rationale.
PASS requires positive evidence, not optimism.

REPOSITORY:
{context()}

DETERMINISTIC VERIFICATION:
{json.dumps(verification, ensure_ascii=False)}
""",
        max_tokens=4800,
    )
    save_json(
        FINAL_AUDITS / f"audit-{number:04d}.json",
        {"audit": audit, "verification": verification, "audited_at": utc_now()},
    )
    if audit.get("decision") == "PASS" and verification["passed"]:
        state["experiment_state"] = "FINAL_CANDIDATE"
        state["current_stage"] = "COMPLETE"
        state["finished_at"] = utc_now()
        state["last_run_result"] = "FINAL_AUDIT_PASS"
        metrics["final_candidate_at"] = state["finished_at"]
    else:
        state["experiment_state"] = "ACTIVE"
        state["current_stage"] = "READY_FOR_NEXT_CYCLE"
        state["last_run_result"] = "FINAL_AUDIT_FAIL"
        metrics["final_audit_failures"] = int(metrics.get("final_audit_failures", 0)) + 1
    save_json(STATE, state)
    save_json(METRICS, metrics)


def main() -> int:
    errors = bootstrap_errors()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    state = load_json(STATE)
    metrics = load_json(METRICS)
    state["last_run_at"] = utc_now()

    if not state.get("armed"):
        state["infrastructure_status"] = "UNARMED"
        state["last_run_result"] = "NOOP_UNARMED"
        save_json(STATE, state)
        print("Autonomy engine is valid but not armed.")
        return 0

    if state.get("experiment_state") == "FINAL_CANDIDATE":
        state["last_run_result"] = "NOOP_FINAL_CANDIDATE"
        save_json(STATE, state)
        return 0

    try:
        ai = AIProvider(metrics)
        state["infrastructure_status"] = "AVAILABLE"
        if state["experiment_state"] == "FINAL_AUDIT_PENDING":
            run_final_audit(ai, state, metrics)
        elif state["experiment_state"] == "ACTIVE":
            run_cycle(ai, state, metrics)
        elif state["experiment_state"] == "INFRASTRUCTURE_BLOCKED":
            state["experiment_state"] = "ACTIVE"
            state["current_stage"] = "READY_FOR_NEXT_CYCLE"
            run_cycle(ai, state, metrics)
        else:
            raise GovernanceError(
                f"armed controller refuses state {state.get('experiment_state')!r}"
            )
    except GovernanceError as exc:
        state = load_json(STATE)
        state["experiment_state"] = "INFRASTRUCTURE_BLOCKED"
        state["current_stage"] = "INFRASTRUCTURE_BLOCKED"
        state["infrastructure_status"] = "BLOCKED"
        state["last_run_result"] = "AUTONOMY_ERROR"
        state["last_error"] = str(exc)[:2000]
        save_json(STATE, state)
        save_json(METRICS, metrics)
        print(f"AUTONOMY ERROR: {exc}", file=sys.stderr)
        return 3

    state = load_json(STATE)
    state["last_run_at"] = utc_now()
    save_json(STATE, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
