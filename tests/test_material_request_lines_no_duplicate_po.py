"""Regression test: an outstanding material shortfall already covered by an
open purchase order must not be offered for a second PO (jobhub-audit-2026-09,
JH-MATERIAL-002).

_material_request_lines() (used by "Create Purchase Order" to list what a
job still needs to order) never checked whether a material_entries row was
already referenced by an open purchase_order_lines row.
_create_purchase_order() never updates material_entries when a PO line is
created, so the same shortfall kept appearing in "Create Purchase Order"
for every job/supplier combination until someone eventually marked it
received -- a second PO could be raised for materials already on an
outstanding first PO, with nothing in the UI to flag it.

This test drives the real _material_request_lines function against a
temporary SQLite database (via jobhub_enterprise_context(), same pattern as
tests/test_progress_tracker_stale_estimate_rows.py) and proves a material
entry already on an open PO line is excluded, one covered only by a
cancelled PO is still offered, and one with no PO line at all is still
offered.
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

import jobhub_enterprise as enterprise

context = app.jobhub_enterprise_context()

conn = app.connect()
cur = conn.cursor()
cur.execute(
    "INSERT INTO jobs (job_no, job_name, site_address, status) VALUES (?, ?, ?, ?)",
    ("JOB-MAT-1", "Material Test Job", "1 Test St", "Not Started"),
)
job_id = int(cur.lastrowid)

# Entry A: already on an open (Requested) PO -- must be excluded.
cur.execute(
    "INSERT INTO material_entries (job_id, qty_required, qty_received, custom_product_name, custom_unit) VALUES (?, ?, ?, ?, ?)",
    (job_id, 10.0, 0.0, "Entry A - already ordered", "Each"),
)
entry_a = int(cur.lastrowid)

cur.execute(
    "INSERT INTO purchase_orders (job_id, po_no, supplier, status, subtotal_ex_gst, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (job_id, "PO-A", "Test Supplier", "Requested", 100.0, "2026-01-01", "2026-01-01"),
)
po_a = int(cur.lastrowid)
cur.execute(
    "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id, description, qty, unit_price_ex_gst, line_total_ex_gst) VALUES (?, ?, ?, ?, ?, ?)",
    (po_a, entry_a, "Entry A", 10.0, 10.0, 100.0),
)

# Entry B: only referenced by a Cancelled PO -- must still be offered.
cur.execute(
    "INSERT INTO material_entries (job_id, qty_required, qty_received, custom_product_name, custom_unit) VALUES (?, ?, ?, ?, ?)",
    (job_id, 5.0, 0.0, "Entry B - cancelled PO only", "Each"),
)
entry_b = int(cur.lastrowid)
cur.execute(
    "INSERT INTO purchase_orders (job_id, po_no, supplier, status, subtotal_ex_gst, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (job_id, "PO-B", "Test Supplier", "Cancelled", 50.0, "2026-01-01", "2026-01-01"),
)
po_b = int(cur.lastrowid)
cur.execute(
    "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id, description, qty, unit_price_ex_gst, line_total_ex_gst) VALUES (?, ?, ?, ?, ?, ?)",
    (po_b, entry_b, "Entry B", 5.0, 10.0, 50.0),
)

# Entry C: no PO line at all -- must still be offered.
cur.execute(
    "INSERT INTO material_entries (job_id, qty_required, qty_received, custom_product_name, custom_unit) VALUES (?, ?, ?, ?, ?)",
    (job_id, 3.0, 0.0, "Entry C - never ordered", "Each"),
)
entry_c = int(cur.lastrowid)

conn.commit()
conn.close()

result = enterprise._material_request_lines(context, job_id)
descriptions = sorted(result["Description"].tolist())
print("RESULT_JSON:" + json.dumps({"descriptions": descriptions}))
"""


class MaterialRequestLinesNoDuplicatePoTest(unittest.TestCase):
    def test_entry_already_on_an_open_po_is_excluded(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_material_dup_")
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

        self.assertNotIn(
            "Entry A - already ordered",
            result["descriptions"],
            "A material entry already on an open PO must not be offered for a second PO",
        )
        self.assertIn(
            "Entry B - cancelled PO only",
            result["descriptions"],
            "A material entry only referenced by a cancelled PO must still be offered",
        )
        self.assertIn(
            "Entry C - never ordered",
            result["descriptions"],
            "A material entry with no PO line at all must still be offered",
        )


if __name__ == "__main__":
    unittest.main()
