"""Statically inventory every ``st.tabs()`` call in JobHub's live pages and
prove each one is covered by ``navigation_state_guard``'s rerun-persistence
patch.

Regression context (jobhub-audit-2026-09, JH-NAV-TABS-002): navigation_state_guard.py
only restores the active tab after a Streamlit rerun for label sets listed in
``_TRACKED_TAB_SETS``. Any other ``st.tabs()`` call site silently loses its
selection the moment a widget inside it triggers a rerun (the exact bug already
fixed once for the Job Register and Timesheets tabs). A hand-maintained
string-matching test cannot catch this drifting out of date -- it only proves
today's known tab sets still contain today's known strings. This test instead
parses the real source with ``ast`` and fails the moment a live tab set stops
being covered, whether because a new ``st.tabs()`` call was added, an existing
one was renamed, or the tracked list was edited incorrectly.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from jobhub.navigation_state_guard import _TRACKED_TAB_SETS, _is_tracked

ROOT = Path(__file__).resolve().parents[1]

# Every source file that is actually imported by the running Streamlit app,
# traced from app.py / pb_jobhub_app.py / jobhub/__init__.py during the
# 2026-09 audit. Deliberately excludes jobhub/pages/*, jobhub/operations.py,
# jobhub/documents.py, jobhub/estimating.py, jobhub/job_views.py,
# jobhub/mapping.py, jobhub/material_orders.py, jobhub/navigation.py,
# jobhub/control_centre.py and jobhub/takeoff_pages.py: none of those modules
# are imported anywhere in the app, so their st.tabs() calls never execute in
# production (see the JH-DEADCODE-001 finding from the same audit).
LIVE_SOURCE_FILES = [
    ROOT / "pb_jobhub_app.py",
    ROOT / "jobhub_enterprise.py",
    ROOT / "jobhub_progress_tracker.py",
    ROOT / "pb_jobhub_visual_scheduler.py",
    ROOT / "jobhub_v4" / "streamlit_painting.py",
    ROOT / "jobhub" / "permission_policy_guard.py",
    ROOT / "jobhub" / "setup_defaults_guard.py",
    ROOT / "jobhub" / "subscriber_setup_guard.py",
    ROOT / "jobhub" / "system_health_v2_guard.py",
]


def _string_list_literal(node: ast.AST) -> list[str] | None:
    """Return the literal strings in a List/Tuple node, or None if not literal."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    labels: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            labels.append(element.value)
        else:
            return None
    return labels


def _find_tabs_calls(source_path: Path) -> list[tuple[int, list[str]]]:
    """Return (line_number, labels) for every literal ``st.tabs([...])`` call."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    found: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "tabs"):
            continue
        if not node.args:
            continue
        labels = _string_list_literal(node.args[0])
        if labels is None:
            continue
        found.append((node.lineno, labels))
    return found


class NavigationTabCoverageTests(unittest.TestCase):
    def test_every_live_tabs_call_has_literal_string_labels(self):
        # Sanity check on the scanner itself: if a new st.tabs() call is ever
        # added with a computed (non-literal) label list, the AST walk below
        # cannot see it and would silently skip it. Fail loudly instead.
        for source_path in LIVE_SOURCE_FILES:
            source = source_path.read_text(encoding="utf-8")
            call_count = source.count("st.tabs(")
            found = _find_tabs_calls(source_path)
            self.assertEqual(
                call_count,
                len(found),
                f"{source_path.name}: found {call_count} 'st.tabs(' occurrences "
                f"but only parsed {len(found)} literal-label calls -- a new "
                "st.tabs() call may use a non-literal label list that this "
                "scanner cannot inventory. Extend the scanner, or add the "
                "tracked set by hand with a comment explaining why.",
            )

    def test_every_live_tab_set_is_tracked_for_rerun_persistence(self):
        missing = []
        for source_path in LIVE_SOURCE_FILES:
            for line, labels in _find_tabs_calls(source_path):
                if not _is_tracked(labels):
                    missing.append(
                        f"{source_path.relative_to(ROOT)}:{line} {labels}"
                    )
        self.assertEqual(
            [],
            missing,
            "The following st.tabs() call sites are not covered by "
            "navigation_state_guard._TRACKED_TAB_SETS, so any widget "
            "interaction inside them loses the active tab on rerun:\n"
            + "\n".join(missing),
        )

    def test_tracked_tab_sets_all_correspond_to_a_real_call_site(self):
        # Catches the opposite drift: an entry that no longer matches any
        # live st.tabs() call (e.g. after a tab was renamed or removed),
        # which would otherwise sit in the guard forever as dead weight.
        observed = [
            frozenset(labels)
            for source_path in LIVE_SOURCE_FILES
            for _, labels in _find_tabs_calls(source_path)
        ]
        unused = [
            sorted(tracked)
            for tracked in _TRACKED_TAB_SETS
            if not any(tracked.issubset(labels) for labels in observed)
        ]
        self.assertEqual(
            [],
            unused,
            "The following _TRACKED_TAB_SETS entries no longer match any "
            "live st.tabs() call site (rename/removal drift) -- update or "
            "remove them:\n" + "\n".join(str(entry) for entry in unused),
        )


if __name__ == "__main__":
    unittest.main()
