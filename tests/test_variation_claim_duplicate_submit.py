"""Regression test: Variation and Claim forms must not create duplicate rows
on a double-submit (jobhub-audit-2026-09, JH-DUPCREATE-002).

The "Add purchase order" form on the same job-detail view already guards
against a double-submit by checking for an existing PO Number before
inserting. The Variation and Claim forms (job_variations, invoice_claims)
had no equivalent check: a fast double-click, or a re-click after a slow
network round trip, inserted two rows with the same variation_no/claim_no
and amount, silently duplicating a dollar figure in the job's financial
ledger.

This test extracts the real "check then insert" block for both forms
straight from pb_jobhub_app.py's source and execs it twice against a real
temporary SQLite database (same schema/helpers as the live app), proving:
the first submission inserts exactly one row and calls pb_success, and a
second submission with the same job_id + variation_no/claim_no calls
pb_error instead of inserting a second row.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import os, re, sys, textwrap
os.environ["DATA_DIR"] = os.environ["INTEGRATION_DATA_DIR"]
sys.path.insert(0, os.getcwd())

import pb_jobhub_app as app
app.USE_POSTGRES = False
app.init_db()

conn = app.connect()
cur = conn.cursor()
cur.execute(
    "INSERT INTO jobs (job_no, job_name, site_address, status) VALUES (?, ?, ?, ?)",
    ("JOB-DUP-1", "Duplicate Submit Test Job", "1 Test St", "Not Started"),
)
job_id = int(cur.lastrowid)
conn.commit()
conn.close()

source = open("pb_jobhub_app.py", encoding="utf-8").read()


def extract_block(anchor, insert_marker):
    anchor_start = source.index(anchor)
    start = source.rfind("\n", 0, anchor_start) + 1  # keep the first line's indent for dedent()
    end = source.index(insert_marker, start)
    # walk forward to the end of the else branch (next blank line at the
    # enclosing indentation level after the INSERT's closing refresh() call)
    tail_marker = "refresh()"
    tail = source.index(tail_marker, end) + len(tail_marker)
    return textwrap.dedent(source[start:tail])


variation_block = extract_block(
    "if not safe_df_query(\n                \"SELECT id FROM job_variations",
    "INSERT INTO job_variations",
)
claim_block = extract_block(
    "if not safe_df_query(\n                \"SELECT id FROM invoice_claims",
    "INSERT INTO invoice_claims",
)

calls = {"errors": [], "successes": []}


def run_variation_submit(variation_no):
    namespace = dict(
        job_id=job_id,
        variation_no=variation_no,
        description="Extra work",
        reason="Client request",
        amount=500.0,
        status="Draft",
        sent_date="",
        approved_date="",
        approved_by="",
        notes="",
        safe_df_query=app.safe_df_query,
        execute=app.execute,
        jobhub_now=app.jobhub_now,
        pb_error=lambda msg: calls["errors"].append(msg),
        pb_success=lambda msg: calls["successes"].append(msg),
        refresh=lambda: None,
    )
    exec(variation_block, namespace)


def run_claim_submit(claim_no):
    namespace = dict(
        job_id=job_id,
        claim_no=claim_no,
        description="Progress claim",
        amount=1000.0,
        invoice_date="2026-09-01",
        due_date="",
        paid_date="",
        status="Draft",
        notes="",
        safe_df_query=app.safe_df_query,
        execute=app.execute,
        jobhub_now=app.jobhub_now,
        pb_error=lambda msg: calls["errors"].append(msg),
        pb_success=lambda msg: calls["successes"].append(msg),
        refresh=lambda: None,
    )
    exec(claim_block, namespace)


run_variation_submit("V-1")
run_variation_submit("V-1")  # the double-click / resubmit
variation_rows = app.df_query(
    "SELECT COUNT(*) AS c FROM job_variations WHERE job_id = ? AND variation_no = ?",
    (job_id, "V-1"),
).iloc[0]["c"]

run_claim_submit("C-1")
run_claim_submit("C-1")  # the double-click / resubmit
claim_rows = app.df_query(
    "SELECT COUNT(*) AS c FROM invoice_claims WHERE job_id = ? AND claim_no = ?",
    (job_id, "C-1"),
).iloc[0]["c"]

print(f"RESULT:{variation_rows}:{claim_rows}:{len(calls['errors'])}:{len(calls['successes'])}")
"""


class VariationClaimDuplicateSubmitTest(unittest.TestCase):
    def test_double_submit_does_not_duplicate_variation_or_claim_rows(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_dupsubmit_")
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        data_dir = os.path.join(temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        env = dict(os.environ)
        env["DATA_DIR"] = data_dir
        env["INTEGRATION_DATA_DIR"] = data_dir

        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT],
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
            line for line in completed.stdout.splitlines() if line.startswith("RESULT:")
        )
        _, variation_rows, claim_rows, error_count, success_count = result_line.split(":")
        self.assertEqual(int(variation_rows), 1, "Double-submitting the same Variation No duplicated it")
        self.assertEqual(int(claim_rows), 1, "Double-submitting the same Claim No duplicated it")
        self.assertEqual(int(success_count), 2, "Expected exactly one success message per form (first submit)")
        self.assertEqual(int(error_count), 2, "Expected exactly one error message per form (the duplicate resubmit)")


if __name__ == "__main__":
    unittest.main()
