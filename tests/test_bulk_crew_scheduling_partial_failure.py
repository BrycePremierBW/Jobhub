"""Regression test: an unexpected failure partway through a bulk
crew-scheduling batch must not crash the whole handler before its
added/skipped summary is shown (jobhub-audit-2026-09 architecture
decision #7).

"Allocate crew", "Approve and add suggested crew" and "Copy first week to
next week" each loop over every employee/day combination calling
add_assignment() with no per-item exception handling. A single unexpected
failure partway through a batch (a dropped DB connection, a Postgres
advisory lock timeout under contention) used to propagate straight out of
the loop, crashing the handler with an unhandled traceback -- skipping the
deterministic added/skipped summary entirely and leaving no way to tell
which of the earlier iterations had already committed.

This test extracts the real "Allocate crew" per-item loop body from source
(the other two loops follow the identical pattern) and execs it with a
fake add_assignment that raises for one specific employee/day, proving the
loop still completes, the failure is folded into the same deterministic
report every other outcome already uses, and the other, unaffected
iterations still succeed normally.
"""
from __future__ import annotations

import textwrap
import unittest
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pb_jobhub_visual_scheduler.py"


def _daterange(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _extract_allocate_crew_loop() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    start_anchor = "for work_day in daterange(to_date(range_start), to_date(range_end)):"
    start = source.index(start_anchor)
    line_start = source.rfind("\n", 0, start) + 1
    end_anchor = 'if clash_items:\n                    st.session_state[bulk_pending_key]'
    end = source.index(end_anchor, start)
    return textwrap.dedent(source[line_start:end])


class _RecordingWarning:
    def __init__(self):
        self.messages: list[str] = []

    def warning(self, message, *args, **kwargs):
        self.messages.append(message)


class BulkCrewSchedulingPartialFailureTests(unittest.TestCase):
    def setUp(self):
        self.loop_source = _extract_allocate_crew_loop()

    def _run(self, add_assignment_impl):
        staff = pd.DataFrame([
            {"id": 1, "name": "River"},
            {"id": 2, "name": "Salty"},
        ])

        def overlapping_assignment_rows(employee_id, work_day, start_time, finish_time):
            return pd.DataFrame()  # no conflicts, ever, for this test

        st = _RecordingWarning()
        namespace = dict(
            daterange=_daterange,
            to_date=lambda value: value,
            range_start=date(2026, 8, 3),
            range_end=date(2026, 8, 4),
            selected_day_numbers={0, 1, 2, 3, 4, 5, 6},
            crew=["River", "Salty"],
            staff=staff,
            overlapping_assignment_rows=overlapping_assignment_rows,
            add_assignment=add_assignment_impl,
            job_id=1,
            job_stage_id=None,
            job_label="PB25001 - Test",
            start_time=time(7, 0),
            finish_time=time(15, 0),
            hours=8.0,
            site_role="Painter",
            notes="",
            linked_dates=True,
            user={"username": "admin"},
            clash_items=[],
            skipped=[],
            added=0,
        )
        exec(self.loop_source, namespace)
        return namespace

    def test_unexpected_exception_is_folded_into_skipped_report_not_raised(self):
        def add_assignment(employee_id, *args, **kwargs):
            if employee_id == 2:
                raise ConnectionError("simulated dropped DB connection")
            return True, "Assignment added to JobHub."

        result = self._run(add_assignment)

        self.assertEqual(result["added"], 2, "River's two days must still succeed")
        self.assertEqual(len(result["skipped"]), 2, "Salty's two days must be reported, not silently lost")
        self.assertTrue(
            all("unexpected error" in message and "simulated dropped DB connection" in message
                for message in result["skipped"]),
            result["skipped"],
        )

    def test_no_failure_reports_everyone_added_with_nothing_skipped(self):
        def add_assignment(*args, **kwargs):
            return True, "Assignment added to JobHub."

        result = self._run(add_assignment)
        self.assertEqual(result["added"], 4)
        self.assertEqual(result["skipped"], [])


if __name__ == "__main__":
    unittest.main()
