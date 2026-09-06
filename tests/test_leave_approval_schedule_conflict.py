"""Regression test: approving staff leave now surfaces existing schedule
conflicts instead of silently ignoring them (jobhub-audit-2026-09,
JH-SCHED-001).

page_leave() previously never checked whether an employee already had
schedule bookings inside a leave request's date range before approving it
(from either the "Add request" form with an initial status of Approved, or
the "Approve / reject" review tab) -- has_approved_leave() only checks the
opposite direction (given a scheduled date, is there approved leave), and
nothing ran the reverse check. A staff member could end up simultaneously
"on approved leave" and rostered to a job with no warning anywhere.

This is intentionally a warning, not a block or an automatic unassignment:
deciding whether to remove the existing bookings is a call for whoever is
approving the leave, and this audit avoids taking destructive action on
production schedule data without an explicit decision from the business.

This test extracts the real conflict-detection SQL added to page_leave()
and runs it directly via the module's own query_df against a temporary
SQLite database (same harness as tests/test_scheduler_stage_crews.py),
proving it correctly finds a job the employee is already rostered to
inside the leave window, and correctly finds nothing when there's no
overlap.
"""
from __future__ import annotations

import importlib
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pb_jobhub_visual_scheduler.py"


def _extract_conflict_sql() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    anchor = "already rostered during this leave window"
    index = source.index(anchor)
    block_start = source.rindex("query_df(", 0, index)
    sql_start = source.index('"""', block_start) + 3
    sql_end = source.index('"""', sql_start)
    return source[sql_start:sql_end]


class LeaveApprovalScheduleConflictTests(unittest.TestCase):
    def setUp(self):
        streamlit_module = sys.modules.get("streamlit")
        if streamlit_module is not None and not hasattr(streamlit_module, "dialog"):
            del sys.modules["streamlit"]
        scheduler = importlib.import_module("pb_jobhub_visual_scheduler")
        self.scheduler = scheduler
        self.temp_dir = tempfile.TemporaryDirectory(prefix="jobhub_leave_conflict_test_")
        self.original_path = scheduler.SQLITE_PATH
        self.original_postgres = scheduler.USE_POSTGRES
        scheduler.SQLITE_PATH = Path(self.temp_dir.name) / "jobhub.db"
        scheduler.USE_POSTGRES = False
        scheduler.init_linked_schema.clear()

        connection = sqlite3.connect(scheduler.SQLITE_PATH)
        connection.executescript(
            """
            CREATE TABLE employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
            CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_no TEXT, job_name TEXT);
            CREATE TABLE staff_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER, employee_id INTEGER, schedule_date TEXT
            );
            """
        )
        connection.execute("INSERT INTO employees(name) VALUES ('River')")
        connection.execute("INSERT INTO jobs(job_no, job_name) VALUES ('PB25001', 'Test Job')")
        connection.execute(
            "INSERT INTO staff_schedule(job_id, employee_id, schedule_date) VALUES (1, 1, '2026-09-10')"
        )
        connection.commit()
        connection.close()
        scheduler.init_linked_schema()
        self.sql = _extract_conflict_sql()

    def tearDown(self):
        scheduler = self.scheduler
        scheduler.init_linked_schema.clear()
        scheduler.SQLITE_PATH = self.original_path
        scheduler.USE_POSTGRES = self.original_postgres
        self.temp_dir.cleanup()

    def test_detects_a_booking_inside_the_leave_window(self):
        result = self.scheduler.query_df(self.sql, (1, "2026-09-08", "2026-09-12"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["job_no"], "PB25001")

    def test_finds_nothing_when_the_leave_window_does_not_overlap(self):
        result = self.scheduler.query_df(self.sql, (1, "2026-10-01", "2026-10-05"))
        self.assertTrue(result.empty)

    def test_finds_nothing_for_a_different_employee(self):
        result = self.scheduler.query_df(self.sql, (2, "2026-09-08", "2026-09-12"))
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
