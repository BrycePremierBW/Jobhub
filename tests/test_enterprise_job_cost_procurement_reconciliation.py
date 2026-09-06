"""Regression test: enterprise_job_cost_dataframe() (the "Live Job Control
& Forecast-to-Complete" page) must treat Procurement as the authoritative
source for committed/invoiced material cost and reconcile with
material_entries, not blend the two with max() (architecture decisions
#1, #2, #3).

Before this fix, this function computed:
    Actual Material Cost = max(received_material_cost, supplier_invoiced)
    Material Commitment = max(Budget Materials, committed_material_cost,
                               received_material_cost, po_committed,
                               po_approved, supplier_invoiced)
using a `committed_material_cost`/`received_material_cost` pair computed
from the FULL material_entries table (including rows already converted
onto an active PO). max() meant whichever source was bigger silently won
-- not genuinely "Procurement is authoritative," and not a real
reconciliation of the two sources per decision #2's "consume/reconcile...
rather than maintain a second independent commercial truth." This mirrors
the exact bug already fixed for job_cost_summary_dataframe()/
pb_job_cost_frame() in pb_jobhub_app.py (PR #122).

This test extracts the real materials/po/supplier_invoices queries and
the final reconciliation formula from this function and proves: Procurement
(po_committed, supplier_invoiced) is now added directly into the totals,
material_entries contributes only via non-PO-linked rows, and a PO with a
different (adjusted) subtotal than its source material_entries row is
reflected accurately rather than the bigger of the two winning.
"""
from __future__ import annotations

import sqlite3
import textwrap
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "jobhub_enterprise.py"


class EnterpriseJobCostProcurementReconciliationTests(unittest.TestCase):
    def setUp(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        start_anchor = source.index(
            '    materials = _query(\n'
            "        ctx,\n"
            '        """\n'
            "        SELECT m.job_id,\n"
            "               COALESCE(SUM(CASE WHEN po_link.material_entry_id IS NULL"
        )
        start = source.rfind("\n", 0, start_anchor) + 1
        end = source.index("FROM supplier_invoices", start)
        end = source.index('"""', end) + 3
        end = source.index(")", end) + 1
        self.query_source = textwrap.dedent(source[start:end])

        formula_anchor = source.index(
            'result["Actual Material Cost"] = result["supplier_invoiced"] + result["non_po_received_material_cost"]'
        )
        fstart = source.rfind("\n", 0, formula_anchor) + 1
        fend = source.index('result["Material Commitment"] = result[[', fstart)
        fend = source.index("]].max(axis=1)", fend)
        fend = source.index("\n", fend) + 1
        self.formula_source = textwrap.dedent(source[fstart:fend])

        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, price_ex_gst REAL)")
        self.conn.execute(
            "CREATE TABLE material_entries (id INTEGER PRIMARY KEY, job_id INTEGER, product_id INTEGER, "
            "qty_required REAL, qty_received REAL, custom_unit_price REAL, price_snapshot REAL)"
        )
        self.conn.execute(
            "CREATE TABLE purchase_orders (id INTEGER PRIMARY KEY, job_id INTEGER, status TEXT, subtotal_ex_gst REAL)"
        )
        self.conn.execute(
            "CREATE TABLE purchase_order_lines (id INTEGER PRIMARY KEY, purchase_order_id INTEGER, material_entry_id INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE supplier_invoices (id INTEGER PRIMARY KEY, job_id INTEGER, purchase_order_id INTEGER, "
            "status TEXT, subtotal_ex_gst REAL)"
        )
        self.conn.commit()

    def _query(self, ctx, sql, params=()):
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=columns)

    def _run(self):
        namespace = dict(ctx={}, _query=self._query)
        exec(self.query_source, namespace)
        materials = namespace["materials"]
        po = namespace["po"]
        supplier_invoices = namespace["supplier_invoices"]

        job_ids = sorted({
            *(materials["job_id"] if not materials.empty else []),
            *(po["job_id"] if not po.empty else []),
            *(supplier_invoices["job_id"] if not supplier_invoices.empty else []),
        })
        result = pd.DataFrame({"job_id": job_ids, "Budget Materials": 0.0})
        for extra in (materials, po, supplier_invoices):
            if extra is not None and not extra.empty:
                result = result.merge(extra, on="job_id", how="left")
        for col in (
            "non_po_committed_material_cost", "non_po_received_material_cost",
            "po_committed", "po_approved", "supplier_invoiced",
        ):
            if col not in result.columns:
                result[col] = 0.0
            result[col] = result[col].fillna(0.0)

        formula_namespace = dict(result=result)
        exec(self.formula_source, formula_namespace)
        return formula_namespace["result"].set_index("job_id")

    def test_po_linked_material_entry_is_excluded_and_po_subtotal_used_instead(self):
        self.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 1, 10, 5, 20.0)"
        )
        self.conn.execute(
            "INSERT INTO purchase_orders (id, job_id, status, subtotal_ex_gst) VALUES (1, 1, 'Approved', 150.0)"
        )
        self.conn.execute(
            "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id) VALUES (1, 1)"
        )
        self.conn.commit()
        result = self._run()
        self.assertEqual(
            result.loc[1, "Procurement Committed Material Cost"], 150.0,
            "The PO's own (possibly adjusted) subtotal must be used, not material_entries' qty*price",
        )

    def test_non_po_material_entry_still_contributes(self):
        self.conn.execute(
            "INSERT INTO material_entries (job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 10, 5, 20.0)"
        )
        self.conn.commit()
        result = self._run()
        self.assertEqual(result.loc[1, "Procurement Committed Material Cost"], 200.0)
        self.assertEqual(result.loc[1, "Actual Material Cost"], 100.0)

    def test_supplier_invoice_is_added_not_maxed_against_non_po_cost(self):
        self.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 1, 10, 10, 20.0)"
        )
        self.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (2, 1, 5, 5, 10.0)"
        )
        self.conn.execute(
            "INSERT INTO purchase_orders (id, job_id, status, subtotal_ex_gst) VALUES (1, 1, 'Approved', 200.0)"
        )
        self.conn.execute(
            "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id) VALUES (1, 1)"
        )
        self.conn.execute(
            "INSERT INTO supplier_invoices (job_id, purchase_order_id, status, subtotal_ex_gst) VALUES (1, 1, 'Received', 210.0)"
        )
        self.conn.commit()
        result = self._run()
        # Item 2 (never PO'd, $50 received) + the supplier invoice ($210) for item 1's PO = $260.
        # The old max()-based formula would have compared against
        # received_material_cost (200+50=250) and picked the larger of the
        # two single numbers, never genuinely combining PO-invoiced and
        # non-PO actual cost together.
        self.assertEqual(result.loc[1, "Actual Material Cost"], 260.0)


if __name__ == "__main__":
    unittest.main()
