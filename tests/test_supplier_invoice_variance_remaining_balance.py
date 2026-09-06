"""Regression test: supplier invoice variance must compare against the PO's
remaining (un-invoiced) balance, not its full subtotal every time
(jobhub-audit-2026-09, JH-COST-002).

render_procurement()'s "Supplier Invoice Match" tab computed
`variance = invoice_subtotal - po_row["subtotal_ex_gst"]` for every invoice
matched to a PO, regardless of any invoices already matched to that same
PO. For a job with genuine partial deliveries billed across multiple
supplier invoices against one PO, each invoice's "Variance" showed the same
number computed against the PO's entire subtotal -- giving no real signal
that a PO was being invoiced twice over (or was still short), since a
second, unrelated invoice matched to an already-fully-invoiced PO showed
the same "on target" variance as the first.

This test extracts the real remaining-balance/variance calculation from
source and execs it against a temporary SQLite database (via jobhub_core's
own query_df-style helper), proving the variance is computed against what's
left to invoice after prior invoices, not the PO's full subtotal.
"""
from __future__ import annotations

import sqlite3
import textwrap
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "jobhub_enterprise.py"


def _extract_calculation() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    anchor = source.index("invoice_subtotal = sum(")
    start = source.rfind("\n", 0, anchor) + 1
    end = source.index("x1, x2, x3, x4 = st.columns(4)", start)
    return textwrap.dedent(source[start:end])


class SupplierInvoiceVarianceRemainingBalanceTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE supplier_invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_order_id INTEGER, subtotal_ex_gst REAL)"
        )
        self.conn.commit()
        self.calculation = _extract_calculation()

    def _query(self, ctx, sql, params=()):
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=columns)

    def _f(self, value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _compute(self, po_subtotal, po_id, invoice_line_totals):
        invoice_lines = pd.DataFrame(
            [{"Invoice Line Total Ex GST": total} for total in invoice_line_totals]
        )
        namespace = dict(
            invoice_lines=invoice_lines,
            po_row={"subtotal_ex_gst": po_subtotal},
            po_id=po_id,
            ctx={},
            _f=self._f,
            _query=self._query,
        )
        exec(self.calculation, namespace)
        return namespace["already_invoiced"], namespace["remaining_balance"], namespace["variance"]

    def test_first_invoice_against_a_fresh_po_compares_to_full_subtotal(self):
        already_invoiced, remaining_balance, variance = self._compute(1000.0, po_id=1, invoice_line_totals=[1000.0])
        self.assertEqual(already_invoiced, 0.0)
        self.assertEqual(remaining_balance, 1000.0)
        self.assertEqual(variance, 0.0)

    def test_second_partial_invoice_compares_to_remaining_balance_not_full_subtotal(self):
        self.conn.execute(
            "INSERT INTO supplier_invoices (purchase_order_id, subtotal_ex_gst) VALUES (?, ?)", (1, 600.0)
        )
        self.conn.commit()
        already_invoiced, remaining_balance, variance = self._compute(1000.0, po_id=1, invoice_line_totals=[400.0])
        self.assertEqual(already_invoiced, 600.0)
        self.assertEqual(remaining_balance, 400.0)
        self.assertEqual(
            variance, 0.0,
            "A correctly-sized second invoice covering exactly what's left must show zero variance",
        )

    def test_invoicing_an_already_fully_invoiced_po_again_shows_a_real_overage(self):
        self.conn.execute(
            "INSERT INTO supplier_invoices (purchase_order_id, subtotal_ex_gst) VALUES (?, ?)", (1, 1000.0)
        )
        self.conn.commit()
        already_invoiced, remaining_balance, variance = self._compute(1000.0, po_id=1, invoice_line_totals=[500.0])
        self.assertEqual(already_invoiced, 1000.0)
        self.assertEqual(remaining_balance, 0.0)
        self.assertEqual(
            variance, 500.0,
            "A second invoice on an already-fully-invoiced PO must show the full overage, "
            "not the same ~on-target variance the old full-subtotal comparison would have shown",
        )


if __name__ == "__main__":
    unittest.main()
