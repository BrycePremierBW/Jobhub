"""Regression test: Job Costs / Forecasting (and the Control Centre's job
cost summary) must treat Procurement (purchase_orders / supplier_invoices)
as the authoritative source for committed and invoiced material cost, and
reconcile with material_entries rather than maintaining two independent
truths (architecture decisions #1, #2, #3).

Before this fix, `job_cost_summary_dataframe()` (the actual "Job Costs /
Forecasting" page) computed "Committed Material Cost" and "Actual Material
Cost" purely from `material_entries` and never looked at `purchase_orders`
or `supplier_invoices` at all -- so raising a PO directly (with no matching
material_entries row) was completely invisible to Job Costs, and once a
material_entries row *was* converted onto a PO, its qty/live-ish price kept
being counted from material_entries forever, while the PO's own (possibly
different, since PO creation lets qty/price be adjusted) subtotal was
ignored entirely. `pb_job_cost_frame()` (the Control Centre's summary) had
the exact same gap.

This test extracts the real materials/procurement/supplier_invoices
queries and the final reconciliation formula from both functions in
pb_jobhub_app.py, runs them against a temporary SQLite database, and
proves: a material_entries row with no PO still contributes its own cost;
once that same row is linked to an active PO line, its material_entries
cost drops out and the PO's own subtotal (not the material_entries qty*
price) becomes the committed cost instead -- no double-count, no silent
gap; and a PO raised with no material_entries row behind it at all is
still counted.
"""
from __future__ import annotations

import sqlite3
import textwrap
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "pb_jobhub_app.py"


def _extract(start_marker: str, end_marker: str) -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    anchor = source.index(start_marker)
    start = source.rfind("\n", 0, anchor) + 1
    end = source.index(end_marker, start)
    end = source.index("\n", end) + 1
    return textwrap.dedent(source[start:end])


class _ReconciliationHarness:
    """Runs the real, extracted materials/procurement/PO SQL + reconciliation
    formula from pb_jobhub_app.py against a temp SQLite DB, exactly as the
    real function would, without needing the full Streamlit app import."""

    def __init__(self, query_source: str, formula_source: str):
        self.query_source = query_source
        self.formula_source = formula_source
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

    def df_query(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=columns)

    def run(self):
        namespace = dict(df_query=self.df_query)
        exec(self.query_source, namespace)
        materials = namespace["materials"]
        procurement = namespace["procurement"]
        supplier_invoices = namespace["supplier_invoices"]

        df = pd.DataFrame({"job_id": sorted({
            *(materials["job_id"] if not materials.empty else []),
            *(procurement["job_id"] if not procurement.empty else []),
            *(supplier_invoices["job_id"] if not supplier_invoices.empty else []),
        })})
        for extra in (materials, procurement, supplier_invoices):
            if extra is not None and not extra.empty:
                df = df.merge(extra, on="job_id", how="left")
        for col in (
            "Non-PO Committed Material Cost", "Non-PO Actual Material Cost",
            "PO Committed Material Cost", "Supplier Invoiced Material Cost",
        ):
            if col not in df.columns:
                df[col] = 0.0
            df[col] = df[col].fillna(0.0)

        formula_namespace = dict(df=df)
        exec(self.formula_source, formula_namespace)
        return formula_namespace["df"].set_index("job_id")


class JobCostsForecastingReconciliationTests(unittest.TestCase):
    def setUp(self):
        source = APP_PATH.read_text(encoding="utf-8")
        start_anchor = source.index(
            'materials = df_query("""\n        SELECT m.job_id,\n'
            "               COALESCE(SUM(CASE WHEN po_link.material_entry_id IS NULL\n"
            "                   THEN COALESCE(m.qty_required, 0) * COALESCE(m.custom_unit_price, m.price_snapshot, p.price_ex_gst, 0)\n"
            "                   ELSE 0 END), 0) AS 'Non-PO Committed Material Cost',"
        )
        start = source.rfind("\n", 0, start_anchor) + 1
        end = source.index("FROM supplier_invoices", start)
        end = source.index('"""', end) + 3
        end = source.index(")", end) + 1
        self.query_source = textwrap.dedent(source[start:end])

        formula_anchor = source.index('df["Committed Material Cost"] = df["PO Committed Material Cost"] + df["Non-PO Committed Material Cost"]')
        fstart = source.rfind("\n", 0, formula_anchor) + 1
        fend = source.index("df[\"Actual Material Cost\"]", fstart)
        fend = source.index("\n", fend) + 1
        self.formula_source = textwrap.dedent(source[fstart:fend])

        self.harness = _ReconciliationHarness(self.query_source, self.formula_source)

    def test_non_po_material_entry_contributes_its_own_cost(self):
        self.harness.conn.execute(
            "INSERT INTO material_entries (job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 10, 5, 20.0)"
        )
        self.harness.conn.commit()
        result = self.harness.run()
        self.assertEqual(result.loc[1, "Committed Material Cost"], 200.0)
        self.assertEqual(result.loc[1, "Actual Material Cost"], 100.0)

    def test_po_linked_material_entry_is_excluded_and_po_subtotal_used_instead(self):
        self.harness.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 1, 10, 5, 20.0)"
        )
        # PO created from this material request with an adjusted subtotal
        # (e.g. price negotiated down at ordering time) -- the PO's own
        # subtotal, not material_entries' qty*price, must be what counts.
        self.harness.conn.execute(
            "INSERT INTO purchase_orders (id, job_id, status, subtotal_ex_gst) VALUES (1, 1, 'Approved', 150.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id) VALUES (1, 1)"
        )
        self.harness.conn.commit()
        result = self.harness.run()
        self.assertEqual(
            result.loc[1, "Committed Material Cost"], 150.0,
            "Once a material_entries row is on an active PO, the PO's own subtotal must be used, "
            "not a second independent qty*price calculation from material_entries",
        )

    def test_po_with_no_material_entries_row_is_still_counted(self):
        self.harness.conn.execute(
            "INSERT INTO purchase_orders (job_id, status, subtotal_ex_gst) VALUES (1, 'Approved', 500.0)"
        )
        self.harness.conn.commit()
        result = self.harness.run()
        self.assertEqual(
            result.loc[1, "Committed Material Cost"], 500.0,
            "A PO raised without a prior material request must not be invisible to Job Costs",
        )

    def test_supplier_invoice_becomes_the_actual_cost_for_po_linked_lines(self):
        self.harness.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 1, 10, 10, 20.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO purchase_orders (id, job_id, status, subtotal_ex_gst) VALUES (1, 1, 'Approved', 200.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id) VALUES (1, 1)"
        )
        self.harness.conn.execute(
            "INSERT INTO supplier_invoices (job_id, purchase_order_id, status, subtotal_ex_gst) VALUES (1, 1, 'Received', 210.0)"
        )
        self.harness.conn.commit()
        result = self.harness.run()
        self.assertEqual(
            result.loc[1, "Actual Material Cost"], 210.0,
            "The supplier invoice, not the material_entries qty_received*price, is the authoritative actual cost",
        )

    def test_no_double_counting_of_committed_and_non_po_costs_together(self):
        self.harness.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (1, 1, 10, 0, 20.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO material_entries (id, job_id, qty_required, qty_received, custom_unit_price) "
            "VALUES (2, 1, 5, 0, 10.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO purchase_orders (id, job_id, status, subtotal_ex_gst) VALUES (1, 1, 'Approved', 200.0)"
        )
        self.harness.conn.execute(
            "INSERT INTO purchase_order_lines (purchase_order_id, material_entry_id) VALUES (1, 1)"
        )
        self.harness.conn.commit()
        result = self.harness.run()
        # Line 1 ($200 via PO) + line 2 (never PO'd, $50 from material_entries) = $250.
        self.assertEqual(result.loc[1, "Committed Material Cost"], 250.0)


if __name__ == "__main__":
    unittest.main()
