from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "autonomy"))

from core import (  # noqa: E402
    GovernanceError,
    assert_executor_path_allowed,
    assert_plan_frozen,
    bootstrap_errors,
    freeze_plan,
)


class GovernanceTests(unittest.TestCase):
    def test_bootstrap_is_valid(self) -> None:
        self.assertEqual(bootstrap_errors(), [])

    def test_product_file_is_allowed(self) -> None:
        path = assert_executor_path_allowed("src/example.ts")
        self.assertEqual(path, (ROOT / "src/example.ts").resolve())

    def test_governance_file_is_protected(self) -> None:
        with self.assertRaises(GovernanceError):
            assert_executor_path_allowed("GOVERNANCE.md")

    def test_autonomy_engine_is_protected(self) -> None:
        with self.assertRaises(GovernanceError):
            assert_executor_path_allowed("scripts/autonomy/core.py")

    def test_cycle_history_is_protected(self) -> None:
        with self.assertRaises(GovernanceError):
            assert_executor_path_allowed("cycles/PDSA-0001/study.json")

    def test_path_escape_is_rejected(self) -> None:
        with self.assertRaises(GovernanceError):
            assert_executor_path_allowed("../outside.txt")

    def test_frozen_plan_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            cycle = pathlib.Path(temp)
            plan = cycle / "plan.md"
            plan.write_text("immutable plan", encoding="utf-8")
            freeze_plan(cycle)
            assert_plan_frozen(cycle)
            plan.write_text("changed plan", encoding="utf-8")
            with self.assertRaises(GovernanceError):
                assert_plan_frozen(cycle)


if __name__ == "__main__":
    unittest.main()
