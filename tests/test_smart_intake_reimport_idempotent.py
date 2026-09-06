"""Regression test: re-importing the identical Smart Intake document into the
same estimate must not inflate the material allowance (jobhub-audit-2026-09,
JH-COST-001).

attach_intake_package_to_job()'s merge path matches an incoming take-off
line against an existing one by (description, location, colour). For a
matched line it updates qty and estimated_labour_hours with max(new, old) --
deliberately idempotent, so reprocessing the same document twice leaves them
unchanged -- but updated material_allowance with old + new, which is
additive. Re-uploading the identical intake pack (e.g. a corrected re-scan
of the same document) silently doubles the recorded material allowance and
therefore the estimate's sell price, every time it's re-processed.

This test drives the real parse_intake_upload/parts_to_intake_package/
attach_intake_package_to_job functions against a temporary SQLite database
(same pattern as tests/test_smart_intake_integration.py) and proves that
attaching the exact same parsed package a second time leaves the estimate's
total material_allowance unchanged, while qty/hours (already correct) also
stay unchanged.
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
app.connect().close()

from jobhub.smart_intake import parse_intake_upload, parts_to_intake_package

scope = (
    b"PROJECT: REIMPORT-1\n"
    b"1. 150m2 interior walls, two coats, white, $450 material allowance\n"
)
part = parse_intake_upload(scope, "scope.txt")
parsed = parts_to_intake_package([part], source_name="reimport_intake.zip")
# The free-text parser doesn't itself price a dollar material allowance
# (that's computed later, during a full job-pack import, from product/rate
# lookups this minimal test database doesn't have) -- set one directly on
# the parsed line so this test can prove the merge arithmetic itself.
assert not parsed["lines"].empty, "expected the scope text to parse at least one take-off line"
parsed["lines"].loc[parsed["lines"].index[0], "Material Allowance"] = 450.0

conn = app.connect()
cur = conn.cursor()
cur.execute(
    "INSERT INTO jobs (job_no, job_name, site_address, status) VALUES (?, ?, ?, ?)",
    ("JOB-REIMPORT-1", "Reimport Test Job", "1 Test St", "Not Started"),
)
job_id = int(cur.lastrowid)
now = app.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
summary = dict(parsed["summary"])
summary["labour_hours"] = 0
summary["material_allowance"] = 0
est_id = app._takeoff_insert_id(
    cur,
    app._takeoff_new_estimate_insert_sql(),
    app._takeoff_new_estimate_values(job_id, "JOB-REIMPORT-1-E1", "1", summary, now),
)
conn.commit()
conn.close()

def total_allowance():
    df = app.df_query(
        "SELECT COALESCE(SUM(material_allowance), 0) AS total FROM estimate_line_items WHERE estimate_id = ?",
        (est_id,),
    )
    return float(df.iloc[0]["total"])

def total_hours():
    df = app.df_query(
        "SELECT COALESCE(SUM(estimated_labour_hours), 0) AS total FROM estimate_line_items WHERE estimate_id = ?",
        (est_id,),
    )
    return float(df.iloc[0]["total"])

app.attach_intake_package_to_job(job_id, parsed, merge=True, import_materials=True, attach_documents=False)
after_first = total_allowance()
hours_after_first = total_hours()

# Re-process the IDENTICAL parsed package -- e.g. the user re-uploads the
# same document because they weren't sure the first import worked. Sleep
# past the intake pack folder's one-second timestamp granularity so this
# doesn't collide with the first call's folder (a separate, unrelated
# naming detail this test isn't exercising).
import time
time.sleep(1.1)
app.attach_intake_package_to_job(job_id, parsed, merge=True, import_materials=True, attach_documents=False)
after_second = total_allowance()
hours_after_second = total_hours()

print("RESULT_JSON:" + json.dumps({
    "after_first": after_first,
    "after_second": after_second,
    "hours_after_first": hours_after_first,
    "hours_after_second": hours_after_second,
}))
"""


class SmartIntakeReimportIdempotentTest(unittest.TestCase):
    def test_reimporting_identical_document_does_not_double_material_allowance(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_reimport_it_")
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
            timeout=300,
        )
        output = completed.stdout or ""
        if completed.returncode != 0:
            self.fail("subprocess failed:\n" + (completed.stderr or "") + "\n" + output)
        result_line = next((ln for ln in output.splitlines() if ln.startswith("RESULT_JSON:")), None)
        self.assertIsNotNone(result_line, "no result line in output:\n" + output)
        result = json.loads(result_line[len("RESULT_JSON:"):])

        self.assertGreater(result["after_first"], 0, "First import should record a material allowance")
        self.assertEqual(
            result["after_second"],
            result["after_first"],
            "Re-importing the identical document must not change the total material allowance",
        )
        self.assertEqual(
            result["hours_after_second"],
            result["hours_after_first"],
            "Re-importing the identical document must not change total labour hours (already correct via max())",
        )


if __name__ == "__main__":
    unittest.main()
