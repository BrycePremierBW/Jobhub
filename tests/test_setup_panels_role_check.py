"""Regression test: Setup Defaults, Subscriber Setup and Xero panels must
refuse to render for a non-admin/manager role, independent of whichever
menu injection guard is currently wrapping them (jobhub-audit-2026-09,
JH-AUTHZ-003).

These three render functions previously had no role check of their own --
only relying on the "management_menu" radio being invisible to the employee
role for protection. jobhub.subscriber_setup_guard and jobhub.xero_setup_guard
both wrap the *previous* render function by calling `original()` then always
calling their own panel afterwards, regardless of what `original()` did --
so even after gating jobhub.setup_defaults_guard.render_setup_defaults_page(),
the subscriber and Xero panels chained after it would still render unless
each of them also checks the role itself. This mirrors the pattern already
used correctly elsewhere in the app (e.g. blip_integration_guard's
_allowed() check inside render_blip_attendance_page).

Every test here also patches jobhub.permission_policy_guard.current_role
directly, not just each guard module's _st(). setup_defaults_guard.py,
subscriber_setup_guard.py and xero_setup_guard.py all resolve the caller's
role via a fresh `from . import permission_policy_guard as _permissions`
then `_permissions.current_role()` at call time -- and current_role()
itself prefers pb_jobhub_app.current_role() (if pb_jobhub_app is already
imported, true for virtually the whole suite) over its own _st() mock.
Patching only _st() here left this test's outcome dependent on whatever
role real global state (pb_jobhub_app's session state, or other cached
state reachable from current_role()) happened to hold, left over from an
unrelated, earlier-running test elsewhere in the full suite. It passed in
isolation and under `python -m unittest discover` (which never actually
executed this file's sibling bare-function test modules, so that global
state was never mutated first) but failed under a full pytest run once
those modules started actually running. Patching current_role() itself,
at the exact module attribute _permissions.current_role() looks up,
removes the dependency on any of current_role()'s own internal fallback
chain -- and therefore on test execution order -- entirely.
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from jobhub import permission_policy_guard, setup_defaults_guard, subscriber_setup_guard, xero_setup_guard


class _FakeTab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit(types.SimpleNamespace):
    def __init__(self, role: str):
        super().__init__()
        self.session_state = {"user": {"role": role}}
        self.rendered = []

    def tabs(self, labels):
        self.rendered.append("tabs")
        return [_FakeTab() for _ in labels]

    def __getattr__(self, name):
        # Any Streamlit call the render function makes if the gate fails to
        # stop it (header, caption, divider, subheader, ...) gets recorded
        # here instead of raising, so a bypass shows up as a render, not a
        # crash that could mask the real bug.
        def _record(*args, **kwargs):
            self.rendered.append(name)
        return _record


class SetupPanelsRoleCheckTests(unittest.TestCase):
    def _run_with_role(self, render_callable, role: str, ensure_schema_target: str) -> FakeStreamlit:
        fake_st = FakeStreamlit(role)
        with mock.patch.object(sys.modules["jobhub.permission_policy_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.setup_defaults_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.subscriber_setup_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.xero_setup_guard"], "_st", return_value=fake_st), \
             mock.patch("jobhub.permission_policy_guard.current_role", return_value=role), \
             mock.patch(ensure_schema_target, side_effect=AssertionError(
                 f"{ensure_schema_target} ran even though the caller is role={role!r}"
             )):
            render_callable()
        return fake_st

    def test_setup_defaults_page_refuses_employee_role(self):
        fake_st = self._run_with_role(
            setup_defaults_guard.render_setup_defaults_page,
            "employee",
            "jobhub.setup_defaults_guard._ensure_schema",
        )
        self.assertEqual(fake_st.rendered, ["info"])

    def test_setup_defaults_page_renders_for_manager_role(self):
        # Manager is in scope (setup.manage = {admin, manager}); the new gate
        # must not block it from any of the three chained render functions
        # that setup_defaults_guard.render_setup_defaults_page() now resolves
        # to (subscriber_setup_guard and xero_setup_guard both wrap it).
        # Everything below the gate is mocked as a no-op so this test proves
        # only that the gate itself doesn't over-block a legitimate manager.
        fake_st = FakeStreamlit("manager")
        with mock.patch.object(sys.modules["jobhub.permission_policy_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.setup_defaults_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.subscriber_setup_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.xero_setup_guard"], "_st", return_value=fake_st), \
             mock.patch("jobhub.permission_policy_guard.current_role", return_value="manager"), \
             mock.patch("jobhub.setup_defaults_guard._ensure_schema"), \
             mock.patch("jobhub.setup_defaults_guard._render_rates_tab"), \
             mock.patch("jobhub.setup_defaults_guard._render_stage_tab"), \
             mock.patch("jobhub.setup_defaults_guard._render_crews_tab"), \
             mock.patch("jobhub.subscriber_setup_guard._ensure_schema"), \
             mock.patch("jobhub.subscriber_setup_guard._load_brand_into_session"), \
             mock.patch("jobhub.subscriber_setup_guard._render_health"), \
             mock.patch("jobhub.subscriber_setup_guard._render_company_profile"), \
             mock.patch("jobhub.subscriber_setup_guard._render_import_panel"), \
             mock.patch("jobhub.subscriber_setup_guard._setting_enabled", return_value=False), \
             mock.patch("jobhub.xero_setup_guard._ensure_org", side_effect=Exception("org not ready in test")):
            setup_defaults_guard.render_setup_defaults_page()
        self.assertIn("header", fake_st.rendered)
        self.assertIn("subheader", fake_st.rendered)  # from render_subscriber_setup
        self.assertIn("divider", fake_st.rendered)  # from render_xero_setup_panel, reached and not blocked

    def test_subscriber_setup_refuses_employee_role_even_when_called_directly(self):
        # This is the specific bypass: subscriber_setup_guard's own install
        # wrapper always calls render_subscriber_setup() after the (now
        # correctly gated) render_setup_defaults_page(), so this function
        # must refuse on its own rather than relying on the caller.
        fake_st = self._run_with_role(
            subscriber_setup_guard.render_subscriber_setup,
            "employee",
            "jobhub.subscriber_setup_guard._ensure_schema",
        )
        self.assertEqual(fake_st.rendered, [])

    def test_xero_setup_panel_refuses_employee_role_even_when_called_directly(self):
        fake_st = FakeStreamlit("employee")
        with mock.patch.object(sys.modules["jobhub.permission_policy_guard"], "_st", return_value=fake_st), \
             mock.patch.object(sys.modules["jobhub.xero_setup_guard"], "_st", return_value=fake_st), \
             mock.patch("jobhub.permission_policy_guard.current_role", return_value="employee"), \
             mock.patch("jobhub.xero_setup_guard._ensure_org", side_effect=AssertionError(
                 "xero_setup_guard._ensure_org ran even though the caller is role='employee'"
             )):
            xero_setup_guard.render_xero_setup_panel()
        self.assertEqual(fake_st.rendered, [])


if __name__ == "__main__":
    unittest.main()
