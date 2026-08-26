"""Machine-enforced invariants for the autonomous PDSA experiment."""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUTONOMY = ROOT / ".autonomy"
STATE = AUTONOMY / "state.json"
POLICY = AUTONOMY / "policy.json"
PROVIDER = AUTONOMY / "provider.json"
METRICS = AUTONOMY / "metrics.json"

REQUIRED_DOCS = (
    "EXPERIMENT_PROTOCOL.md",
    "PRODUCT_GOAL.md",
    "DEFINITION_OF_DONE.md",
    "GOVERNANCE.md",
    "PDSA_PROTOCOL.md",
    "AGENTS.md",
)

ALLOWED_EXPERIMENT_STATES = {
    "BOOTSTRAP",
    "ACTIVE",
    "FINAL_AUDIT_PENDING",
    "FINAL_CANDIDATE",
    "INFRASTRUCTURE_BLOCKED",
}

ALLOWED_STAGES = {
    "BOOTSTRAP_VALIDATION",
    "READY_FOR_FIRST_CYCLE",
    "COLLECT",
    "CLASSIFY",
    "SMART_OBJECTIVE",
    "PLAN",
    "PLAN_REVIEW",
    "PLAN_REVISION",
    "PLAN_FROZEN",
    "DO",
    "VERIFY",
    "STUDY",
    "ACT",
    "READY_FOR_NEXT_CYCLE",
    "FINAL_AUDIT_PENDING",
    "COMPLETE",
    "INFRASTRUCTURE_BLOCKED",
}


class GovernanceError(RuntimeError):
    pass


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_protected(rel_path: str, policy: dict[str, Any] | None = None) -> bool:
    policy = policy or load_json(POLICY)
    rel = pathlib.PurePosixPath(rel_path).as_posix()
    if rel in set(policy.get("protected_exact_paths", [])):
        return True
    return any(rel.startswith(prefix) for prefix in policy.get("protected_prefixes", []))


def assert_executor_path_allowed(rel_path: str) -> pathlib.Path:
    policy = load_json(POLICY)
    rel = pathlib.PurePosixPath(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise GovernanceError(f"unsafe path: {rel_path}")
    normalized = rel.as_posix()
    if normalized.startswith(".git/"):
        raise GovernanceError("executor cannot modify .git")
    if any(normalized.startswith(prefix) for prefix in policy.get("historical_prefixes", [])):
        raise GovernanceError(f"executor cannot modify historical evidence: {normalized}")
    if is_protected(normalized, policy):
        raise GovernanceError(f"protected path: {normalized}")
    target = (ROOT / normalized).resolve()
    if target != ROOT.resolve() and ROOT.resolve() not in target.parents:
        raise GovernanceError(f"path escapes repository: {normalized}")
    return target


def freeze_plan(cycle_dir: pathlib.Path) -> str:
    plan = cycle_dir / "plan.md"
    freeze = cycle_dir / "plan.freeze.json"
    if not plan.exists():
        raise GovernanceError("plan.md does not exist")
    if freeze.exists():
        raise GovernanceError("plan is already frozen")
    digest = sha256_file(plan)
    save_json(
        freeze,
        {
            "algorithm": "sha256",
            "sha256": digest,
            "immutable_for_cycle": True,
        },
    )
    return digest


def assert_plan_frozen(cycle_dir: pathlib.Path) -> None:
    plan = cycle_dir / "plan.md"
    freeze = cycle_dir / "plan.freeze.json"
    if not plan.exists() or not freeze.exists():
        raise GovernanceError("frozen plan artifacts are incomplete")
    expected = load_json(freeze).get("sha256")
    actual = sha256_file(plan)
    if expected != actual:
        raise GovernanceError(
            f"frozen plan changed: expected {expected}, actual {actual}"
        )


def bootstrap_errors() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_DOCS:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required document: {rel}")

    for path in (STATE, POLICY, PROVIDER, METRICS):
        if not path.is_file():
            errors.append(f"missing configuration: {relative(path)}")
            continue
        try:
            load_json(path)
        except Exception as exc:
            errors.append(f"invalid JSON {relative(path)}: {exc}")

    if errors:
        return errors

    state = load_json(STATE)
    policy = load_json(POLICY)

    if state.get("experiment_state") not in ALLOWED_EXPERIMENT_STATES:
        errors.append(f"invalid experiment_state: {state.get('experiment_state')!r}")
    if state.get("current_stage") not in ALLOWED_STAGES:
        errors.append(f"invalid current_stage: {state.get('current_stage')!r}")
    if state.get("experiment_state") == "ACTIVE" and not state.get("armed"):
        errors.append("ACTIVE requires armed=true")

    must_protect = set(REQUIRED_DOCS) | {
        ".autonomy/policy.json",
        ".autonomy/provider.json",
        ".github/workflows/autonomous-cycle.yml",
        ".github/workflows/governance-validation.yml",
    }
    missing = must_protect - set(policy.get("protected_exact_paths", []))
    if missing:
        errors.append(f"policy fails to protect: {sorted(missing)}")

    if "scripts/autonomy/" not in policy.get("protected_prefixes", []):
        errors.append("scripts/autonomy/ must be protected")
    if "tests/autonomy/" not in policy.get("protected_prefixes", []):
        errors.append("tests/autonomy/ must be protected")

    historical = set(policy.get("historical_prefixes", []))
    if not {"cycles/", "final-audits/"}.issubset(historical):
        errors.append("cycle and final-audit histories must be protected")

    if not policy.get("rollback_product_changes_on_verification_failure"):
        errors.append("rollback on failed verification must remain enabled")

    return errors
