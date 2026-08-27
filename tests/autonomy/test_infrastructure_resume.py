from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "autonomy"))

import controller  # noqa: E402
import core  # noqa: E402
import provider  # noqa: E402


class InfrastructureResumeTests(unittest.TestCase):
    def test_provider_capacity_envelope_stays_below_observed_tpm_limit(self) -> None:
        config = core.load_json(core.PROVIDER)
        capacity = config["capacity"]
        self.assertLessEqual(
            int(capacity["max_admitted_request_tokens"])
            + int(capacity["safety_margin_tokens"]),
            int(capacity["organization_tpm_limit"]),
        )
        self.assertEqual(int(capacity["organization_tpm_limit"]), 8000)
        self.assertEqual(int(capacity["max_admitted_request_tokens"]), 6500)

    def test_executor_compaction_preserves_frozen_plan_and_objective_prefix(self) -> None:
        config = core.load_json(core.PROVIDER)
        system_prompt = "Executor governance contract. Return JSON only."
        frozen_plan = "FROZEN_PLAN_SENTINEL\n" + ("approved-plan-line\n" * 180)
        objective = {
            "smart_objective": "SMART_OBJECTIVE_SENTINEL",
            "acceptance_criteria": ["criterion-a", "criterion-b"],
        }
        repository_context = "repository-evidence-line\n" * 1800
        marker = "\nREPOSITORY CONTEXT:\n"
        user_prompt = (
            "Execute only the immutable cycle.\n\n"
            f"FROZEN PLAN:\n{frozen_plan}\n\n"
            f"SMART OBJECTIVE:\n{json.dumps(objective)}"
            + marker
            + repository_context
        )
        original_prefix = user_prompt.split(marker, 1)[0] + marker

        fitted_system, fitted_user, completion, diagnostics = provider.fit_prompt_to_capacity(
            config,
            "executor",
            system_prompt,
            user_prompt,
            3500,
        )

        self.assertTrue(fitted_system)
        self.assertEqual(
            fitted_user.split(marker, 1)[0] + marker,
            original_prefix,
            "Frozen Plan + SMART Objective prefix must remain byte-for-byte unchanged",
        )
        self.assertIn("FROZEN_PLAN_SENTINEL", fitted_user)
        self.assertIn("SMART_OBJECTIVE_SENTINEL", fitted_user)
        self.assertLess(len(fitted_user), len(user_prompt))
        self.assertTrue(diagnostics["compacted"])
        self.assertTrue(diagnostics["executor_frozen_prefix_preserved"])
        self.assertLessEqual(
            int(diagnostics["estimated_admitted_tokens"]),
            int(config["capacity"]["max_admitted_request_tokens"]),
        )
        self.assertEqual(
            completion,
            int(config["capacity"]["role_completion_caps"]["executor"]),
        )

    def test_oversized_executor_prompt_without_context_marker_fails_closed(self) -> None:
        config = core.load_json(core.PROVIDER)
        with self.assertRaises(core.GovernanceError):
            provider.fit_prompt_to_capacity(
                config,
                "executor",
                "executor system",
                "X" * 40000,
                3500,
            )

    def test_current_hiic_resume_checkpoint_matches_frozen_cycle_when_pending(self) -> None:
        state = core.load_json(core.STATE)
        if state.get("resume_required") is not True:
            self.skipTest("HIIC-001 frozen-cycle resume already completed")

        self.assertEqual(state.get("experiment_state"), "INFRASTRUCTURE_BLOCKED")
        self.assertEqual(state.get("resume_stage"), "DO")
        self.assertEqual(state.get("resume_cycle"), state.get("current_cycle"))
        self.assertGreater(
            int(state.get("resume_cycle", 0)),
            int(state.get("last_completed_cycle", 0)),
        )
        self.assertEqual(state.get("resume_intervention_id"), "HIIC-001")
        self.assertEqual(int(state.get("human_development_interventions", 0)), 0)
        self.assertGreaterEqual(int(state.get("human_infrastructure_interventions", 0)), 1)

        cycle = controller.CYCLES / f"PDSA-{int(state['resume_cycle']):04d}"
        core.assert_plan_frozen(cycle)
        freeze = core.load_json(cycle / "plan.freeze.json")
        self.assertEqual(freeze.get("sha256"), state.get("resume_frozen_plan_sha256"))
        review = core.load_json(cycle / "plan-review.json")
        self.assertTrue(review.get("approved"))
        self.assertTrue((cycle / "collection.json").is_file())
        for name in ("execution.json", "verification.json", "study.json", "act.json", "cycle-status.json"):
            self.assertFalse((cycle / name).exists(), name)

    def test_resume_cycle_mismatch_is_rejected_before_ai_use(self) -> None:
        state = {
            "resume_required": True,
            "resume_cycle": 4,
            "current_cycle": 3,
            "last_completed_cycle": 2,
            "resume_stage": "DO",
        }
        with self.assertRaises(core.GovernanceError):
            controller.resume_frozen_cycle(None, state, {})  # type: ignore[arg-type]

    def test_partial_lifecycle_artifact_blocks_reexecution(self) -> None:
        old_cycles = controller.CYCLES
        try:
            with tempfile.TemporaryDirectory() as td:
                controller.CYCLES = pathlib.Path(td)
                cycle = controller.CYCLES / "PDSA-9999"
                cycle.mkdir(parents=True)
                (cycle / "plan.md").write_text("immutable synthetic plan", encoding="utf-8")
                core.freeze_plan(cycle)
                (cycle / "execution.json").write_text("{}\n", encoding="utf-8")
                with self.assertRaises(core.GovernanceError):
                    controller.execute_frozen_cycle(
                        None,  # type: ignore[arg-type]
                        {},
                        {},
                        9999,
                        {"smart_objective": "synthetic"},
                        base_context="synthetic",
                    )
        finally:
            controller.CYCLES = old_cycles


if __name__ == "__main__":
    unittest.main()
