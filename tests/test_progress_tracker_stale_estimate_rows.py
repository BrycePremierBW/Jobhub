"""Regression test: switching a job's linked estimate must not leave stale
external-progress rows from the previous estimate double-counted in the
summary (jobhub-audit-2026-09, JH-PROGRESS-001).

_sync_external_from_estimate() matches an incoming estimate's external-
substrate line items against existing job_external_progress rows by
estimate_line_id. It correctly adds/updates rows for the *currently* linked
estimate, but never removed rows tied to a *previously* linked estimate
(job_progress_settings.linked_estimate_id can be changed at any time, a
normal action when a job's estimate is revised). _summary() then sums every
job_external_progress row for the job regardless of which estimate produced
it, so switching estimate revisions inflated (or deflated) the reported
external m2 and overall progress percentage with data from an estimate the
job is no longer linked to.

This test drives the real ensure_progress_schema/_sync_external_from_estimate
functions against a temporary SQLite database (via pb_jobhub_app's own
connect/execute/df_query, same pattern as tests/test_smart_intake_integration.py),
proving that syncing from a second estimate removes the first estimate's
rows instead of leaving them alongside the new ones.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

INTEGRATION_SCRIPT = r"""
import json, os
os.environ["DATA_DIR"] = os.environ["INTEGRATION_DATA_DIR"]
import pb_jobhub_app as app
app.USE_POSTGRES = False
app.init_db()

import jobhub_progress_tracker as tracker

context = app.jobhub_enterprise_context()
tracker.ensure_progress_schema(context)

conn = app.connect()
cur = conn.cursor()
cur.execute(
    "INSERT INTO jobs (job_no, job_name, site_address, status) VALUES (?, ?, ?, ?)",
    ("JOB-PROG-1", "Progress Test Job", "1 Test St", "Not Started"),
)
job_id = int(cur.lastrowid)

cur.execute(
    "INSERT INTO estimate_working_sheets (job_id, estimate_no, revision) VALUES (?, ?, ?)",
    (job_id, "JOB-PROG-1-E1", "1"),
)
estimate_a = int(cur.lastrowid)
cur.execute(
    "INSERT INTO estimate_line_items (estimate_id, section, item_description, qty, unit, work_location) VALUES (?, ?, ?, ?, ?, ?)",
    (estimate_a, "External", "External weatherboards", 100.0, "m2", "External"),
)

cur.execute(
    "INSERT INTO estimate_working_sheets (job_id, estimate_no, revision) VALUES (?, ?, ?)",
    (job_id, "JOB-PROG-1-E2", "2"),
)
estimate_b = int(cur.lastrowid)
cur.execute(
    "INSERT INTO estimate_line_items (estimate_id, section, item_description, qty, unit, work_location) VALUES (?, ?, ?, ?, ?, ?)",
    (estimate_b, "External", "External fibre cement", 60.0, "m2", "External"),
)
conn.commit()
conn.close()

def total_external_m2():
    df = app.df_query(
        "SELECT COALESCE(SUM(measured_m2), 0) AS total FROM job_external_progress WHERE job_id = ?",
        (job_id,),
    )
    return float(df.iloc[0]["total"])

def row_count():
    df = app.df_query(
        "SELECT COUNT(*) AS c FROM job_external_progress WHERE job_id = ?", (job_id,)
    )
    return int(df.iloc[0]["c"])

# Job is initially linked to estimate A (100m2 external).
tracker._sync_external_from_estimate(context, job_id, estimate_a, "tester")
after_a = total_external_m2()
rows_after_a = row_count()

# The estimate is revised -- job now links to estimate B (60m2 external)
# instead. This is the normal "estimate switched to a new revision" action.
tracker._sync_external_from_estimate(context, job_id, estimate_b, "tester")
after_b = total_external_m2()
rows_after_b = row_count()

print("RESULT_JSON:" + json.dumps({
    "after_a": after_a,
    "rows_after_a": rows_after_a,
    "after_b": after_b,
    "rows_after_b": rows_after_b,
}))
"""


class ProgressTrackerStaleEstimateRowsTest(unittest.TestCase):
    def test_switching_linked_estimate_removes_previous_estimate_rows(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_progress_stale_")
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        data_dir = os.path.join(temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        env = dict(os.environ)
        env["DATA_DIR"] = data_dir
        env["INTEGRATION_DATA_DIR"] = data_dir

        completed = subprocess.run(
            [sys.executable, "-c", INTEGRATION_SCRIPT],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}",
        )
        result_line = next(
            (ln for ln in completed.stdout.splitlines() if ln.startswith("RESULT_JSON:")), None
        )
        self.assertIsNotNone(result_line, "no result line in output:\n" + completed.stdout)
        result = json.loads(result_line[len("RESULT_JSON:"):])

        self.assertEqual(result["after_a"], 100.0)
        self.assertEqual(result["rows_after_a"], 1)
        self.assertEqual(
            result["rows_after_b"],
            1,
            "Switching the linked estimate must remove the previous estimate's row, not add alongside it",
        )
        self.assertEqual(
            result["after_b"],
            60.0,
            "Total external m2 must reflect only the currently linked estimate, not both",
        )


if __name__ == "__main__":
    unittest.main()
