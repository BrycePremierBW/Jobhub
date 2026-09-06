"""Regression test: two concurrent add_assignment() calls for the same
employee and an overlapping time slot must not both succeed
(jobhub-audit-2026-09 architecture decision #6).

overlapping_assignment() and the subsequent INSERT used to run as separate,
unlocked statements. Two concurrent requests booking the same employee for
an overlapping slot could both pass the overlap check before either
committed its insert, producing a genuine double-booking. This is a real
check-then-insert (TOCTOU) race, not just a theoretical one -- "Approve and
add suggested crew" and "Allocate crew" both call add_assignment in a tight
loop for several employees at once.

This test drives two real threads, each with its own SQLite connection to
the same on-disk database file (matching how two concurrent Streamlit
sessions would each get their own connection in production), racing to
book the same employee for the same overlapping slot at the same moment via
a threading.Barrier. It proves that with the fix, exactly one of the two
succeeds and the other is correctly rejected as an overlap -- never both.
"""
from __future__ import annotations

import importlib
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import date, time
from pathlib import Path


class SchedulerToctouDoubleBookingTests(unittest.TestCase):
    def setUp(self):
        streamlit_module = sys.modules.get("streamlit")
        if streamlit_module is not None and not hasattr(streamlit_module, "dialog"):
            del sys.modules["streamlit"]
        scheduler = importlib.import_module("pb_jobhub_visual_scheduler")
        self.scheduler = scheduler
        self.temp_dir = tempfile.TemporaryDirectory(prefix="jobhub_toctou_test_")
        self.original_path = scheduler.SQLITE_PATH
        self.original_postgres = scheduler.USE_POSTGRES
        scheduler.SQLITE_PATH = Path(self.temp_dir.name) / "jobhub.db"
        scheduler.USE_POSTGRES = False
        scheduler.init_linked_schema.clear()

        connection = sqlite3.connect(scheduler.SQLITE_PATH)
        connection.executescript(
            """
            CREATE TABLE builders_clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
            CREATE TABLE employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, role TEXT, phone TEXT, status TEXT);
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_no TEXT, job_name TEXT,
                builder_client_id INTEGER, site_address TEXT, status TEXT,
                leading_hand TEXT, start_date TEXT, end_date TEXT
            );
            CREATE TABLE app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password_hash TEXT,
                role TEXT, employee_id INTEGER, active INTEGER
            );
            """
        )
        connection.execute("INSERT INTO builders_clients(name) VALUES ('Runtime Builder')")
        connection.execute("INSERT INTO employees(name, role, status) VALUES ('River', 'Painter', 'Active')")
        connection.executemany(
            "INSERT INTO jobs (job_no,job_name,builder_client_id,status,start_date,end_date) VALUES (?,?,?,?,?,?)",
            [
                ("PB001", "First Job", 1, "Active", "2026-08-03", "2026-08-31"),
                ("PB002", "Second Job", 1, "Active", "2026-08-03", "2026-08-31"),
            ],
        )
        connection.commit()
        connection.close()
        scheduler.init_linked_schema()

    def tearDown(self):
        scheduler = self.scheduler
        scheduler.init_linked_schema.clear()
        scheduler.SQLITE_PATH = self.original_path
        scheduler.USE_POSTGRES = self.original_postgres
        self.temp_dir.cleanup()

    def test_concurrent_overlapping_bookings_for_the_same_employee_do_not_both_succeed(self):
        scheduler = self.scheduler
        work_date = date(2026, 8, 4)
        barrier = threading.Barrier(2)
        results: list[tuple[bool, str]] = [None, None]  # type: ignore[list-item]
        errors: list[BaseException] = []

        def book(job_id: int, index: int) -> None:
            try:
                barrier.wait(timeout=5)
                results[index] = scheduler.add_assignment(
                    1, job_id, None, work_date, time(7), time(15), 8,
                    "Leading Hand", f"Booking {index}", "admin",
                )
            except BaseException as exc:  # pragma: no cover - surfaced via errors list
                errors.append(exc)

        threads = [
            threading.Thread(target=book, args=(1, 0)),
            threading.Thread(target=book, args=(2, 1)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [], f"Unexpected exceptions during concurrent booking: {errors}")
        self.assertIn(None, [None], "sanity")  # results are always populated below
        successes = [result for result in results if result and result[0]]
        failures = [result for result in results if result and not result[0]]

        self.assertEqual(
            len(successes), 1,
            f"Exactly one concurrent overlapping booking must succeed, got results={results}",
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("overlapping assignment", failures[0][1])

        # Confirm the database agrees: only one row exists for this employee/date.
        rows = scheduler.query_df(
            "SELECT COUNT(*) AS c FROM staff_schedule WHERE employee_id=? AND schedule_date=?",
            (1, work_date.isoformat()),
        )
        self.assertEqual(int(rows.iloc[0]["c"]), 1)


if __name__ == "__main__":
    unittest.main()
