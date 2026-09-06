from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "jobhub" / "setup_scheduler_crew_bridge_guard.py"
_SPEC = importlib.util.spec_from_file_location(
    "jobhub_setup_scheduler_crew_bridge_guard_test", MODULE_PATH
)
BRIDGE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(BRIDGE)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class SetupSchedulerCrewBridgeGuardTests(unittest.TestCase):
    def test_bridge_guard_source_parses(self):
        ast.parse(read("jobhub/setup_scheduler_crew_bridge_guard.py"))

    def test_bridge_reads_setup_crews_into_scheduler_picker(self):
        source = read("jobhub/setup_scheduler_crew_bridge_guard.py")
        required = [
            "jobhub_crews",
            "jobhub_crew_members",
            "scheduler.saved_crews = saved_crews_with_setup_bridge",
            "active_only",
            "Negative ids prevent clashes with scheduler_crews ids",
            "JobHub Setup",
            "member_ids",
            "member_names",
            "lead_employee_id",
        ]
        for marker in required:
            self.assertIn(marker, source)

    def test_combine_crews_includes_setup_crews_when_active_only_is_false(self):
        # Regression: the "Saved crews" management screen calls
        # saved_crews(active_only=False) specifically to list every crew
        # (active + inactive) for editing/deleting. _combine_crews used to
        # return the Staff Scheduler crews alone whenever active_only was
        # False, making every JobHub-Setup-sourced crew permanently
        # invisible on that screen once any native crew existed.
        primary = pd.DataFrame([
            {"id": 1, "crew_name": "Scheduler Crew", "active": 1},
        ])
        setup = pd.DataFrame([
            {"id": -1, "crew_name": "Setup Crew", "active": 0, "source": "JobHub Setup"},
        ])
        combined = BRIDGE._combine_crews(primary, setup, active_only=False)
        self.assertIn(
            "Setup Crew",
            combined["crew_name"].tolist(),
            "A JobHub-Setup-sourced crew must still appear when listing all crews",
        )
        self.assertIn("Scheduler Crew", combined["crew_name"].tolist())

    def test_combine_crews_lets_setup_win_on_name_collision(self):
        primary = pd.DataFrame([
            {"id": 1, "crew_name": "Crew A", "active": 1},
        ])
        setup = pd.DataFrame([
            {"id": -1, "crew_name": "Crew A", "active": 1, "source": "JobHub Setup"},
        ])
        combined = BRIDGE._combine_crews(primary, setup, active_only=True)
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined.iloc[0]["source"], "JobHub Setup")

    def test_bridge_is_installed_after_setup_defaults(self):
        source = read("jobhub/__init__.py")
        self.assertIn("from .setup_scheduler_crew_bridge_guard import install_setup_scheduler_crew_bridge_guard", source)
        self.assertIn("install_setup_scheduler_crew_bridge_guard()", source)
        self.assertLess(
            source.index("install_setup_defaults_guard()"),
            source.index("install_setup_scheduler_crew_bridge_guard()"),
        )


if __name__ == "__main__":
    unittest.main()
