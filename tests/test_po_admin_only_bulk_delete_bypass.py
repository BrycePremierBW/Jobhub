"""Regression test for a PO admin-only boundary bypass (jobhub-audit-2026-09).

jobhub.po_admin_only_guard blanks PO-backed st.dataframe() calls for non-admin
roles by returning a restricted result instead of rendering the real table
(see jobhub/po_admin_only_guard.py's docstring: "Premier Brushworks requires
purchase orders to be visible only to JobHub admin accounts.").

jobhub.bulk_delete_guard separately wraps st.dataframe() to add a "bulk
delete" panel underneath eligible tables (job_purchase_orders is one of its
TARGETS). Before this fix, that wrapper read the raw, unredacted DataFrame
straight out of the call arguments -- bypassing po_admin_only_guard entirely
and rendering a fully working delete panel with real PO numbers, for any
role, directly below the correctly-blanked table.

This test proves the wrapper now refuses to render bulk-delete controls for
a PO-sensitive key when the current user is not an admin, while continuing
to work normally for admins and for non-PO targets.
"""
from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from jobhub import bulk_delete_guard


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    """Minimal stand-in for the bits of `st` _render_bulk_delete_controls uses."""

    def __init__(self):
        self.session_state = {}
        self.expander_calls = []

    def expander(self, *args, **kwargs):
        self.expander_calls.append((args, kwargs))
        return _FakeExpander()

    def multiselect(self, *args, **kwargs):
        return []

    def caption(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class FakeOwner:
    """Stand-in for the `streamlit` module / DeltaGenerator class being patched."""

    def __init__(self, real_dataframe):
        self.dataframe = real_dataframe


PO_FRAME = pd.DataFrame(
    [{"id": 1, "PO Number": "PO-100", "Description": "Real PO data"}]
)


class PoAdminOnlyBulkDeleteBypassTests(unittest.TestCase):
    def _install(self, fake_st):
        calls = []

        def real_dataframe(*args, **kwargs):
            calls.append((args, kwargs))
            return "rendered"

        owner = FakeOwner(real_dataframe)
        installed = bulk_delete_guard._patch_dataframe(owner, fake_st)
        self.assertTrue(installed)
        return owner, calls

    def test_non_admin_gets_no_bulk_delete_controls_for_po_table(self):
        fake_st = FakeStreamlit()
        owner, calls = self._install(fake_st)

        with mock.patch.object(bulk_delete_guard, "is_admin", return_value=False), \
             mock.patch.object(bulk_delete_guard, "_maybe_consolidate_palm_lakes_villas"):
            result = owner.dataframe(
                PO_FRAME,
                key="selectable_job_purchase_orders_42",
            )

        # The real table render still happens (po_admin_only_guard's own
        # wrapper -- installed separately in the real app -- is what blanks
        # it; this fake owner just proxies straight to "real_dataframe").
        self.assertEqual(result, "rendered")
        self.assertEqual(len(calls), 1)
        # The bug: this used to render a fully-functional delete panel here
        # regardless of role. It must not, for a PO-sensitive key, when the
        # caller is not an admin.
        self.assertEqual(
            fake_st.expander_calls,
            [],
            "Bulk-delete controls were rendered for a PO table to a non-admin",
        )

    def test_admin_still_gets_bulk_delete_controls_for_po_table(self):
        fake_st = FakeStreamlit()
        owner, calls = self._install(fake_st)

        with mock.patch.object(bulk_delete_guard, "is_admin", return_value=True), \
             mock.patch.object(bulk_delete_guard, "_maybe_consolidate_palm_lakes_villas"):
            owner.dataframe(PO_FRAME, key="selectable_job_purchase_orders_42")

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(fake_st.expander_calls), 1)

    def test_non_po_target_is_unaffected_by_the_admin_check(self):
        fake_st = FakeStreamlit()
        owner, calls = self._install(fake_st)
        staff_requests_frame = pd.DataFrame([{"id": 7, "title": "Order more paint"}])

        with mock.patch.object(bulk_delete_guard, "is_admin", return_value=False), \
             mock.patch.object(bulk_delete_guard, "_maybe_consolidate_palm_lakes_villas"):
            owner.dataframe(
                staff_requests_frame,
                key="selectable_staff_requests_admin",
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            len(fake_st.expander_calls),
            1,
            "Non-PO bulk-delete targets should not be gated by the PO admin check",
        )


if __name__ == "__main__":
    unittest.main()
