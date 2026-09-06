"""Regression test: purchase orders and supplier invoices must snapshot a
configurable tax rate rather than a hardcoded 10% GST (architecture decision
#5), and that snapshot must not retroactively change once the system default
is later edited (architecture decision #4).

Before this fix, `_create_purchase_order()` computed GST with a bare
`subtotal * 0.10` and supplier-invoice matching in `render_procurement()`
computed `invoice_subtotal * 0.10` -- both ignored any admin-configured tax
rate and, worse, would have silently changed old documents' totals if the
hardcoded constant were ever edited in source. This test drives the real
`_create_purchase_order()` and `_default_gst_percent()` functions against a
temporary SQLite database, and execs the real supplier-invoice GST
calculation extracted from `render_procurement()`, to prove:

1. `_default_gst_percent()` reads an admin-configurable `app_settings` row,
   defaulting to 10.0 when unset.
2. A new purchase order snapshots whatever rate was configured *at creation
   time* onto its own `gst_percent` column.
3. Changing the system default afterward does not alter the already-created
   PO's stored gst_percent/gst_amount/total_inc_gst.
4. Supplier-invoice matching computes GST from the PO's own snapshotted
   rate, not a hardcoded 10%.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "jobhub_enterprise.py"


def _extract_invoice_gst_calculation() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    anchor = source.index("invoice_gst_percent = _f(po_row[\"gst_percent\"])")
    start = source.rfind("\n", 0, anchor) + 1
    end = source.index("cur.execute(", start)
    return textwrap.dedent(source[start:end])


class ConfigurableGstSnapshotTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT))
        self.jobhub_enterprise = importlib.import_module("jobhub_enterprise")

        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        self.addCleanup(lambda: os.remove(self.db_path) if os.path.exists(self.db_path) else None)

        setup_conn = sqlite3.connect(self.db_path)
        setup_conn.execute(
            "CREATE TABLE app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT)"
        )
        setup_conn.commit()
        setup_conn.close()
        self.jobhub_enterprise.ensure_enterprise_schema(lambda: sqlite3.connect(self.db_path))

        self.ctx = {
            "connect": lambda: sqlite3.connect(self.db_path),
            "df_query": self._df_query,
            "execute": self._execute,
            "get_current_user": lambda: {"username": "tester", "role": "admin"},
        }

    def _df_query(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description]
            return pd.DataFrame(rows, columns=columns)
        finally:
            conn.close()

    def _execute(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        finally:
            conn.close()

    def _set_gst_setting(self, value):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO app_settings (setting_key, setting_value) VALUES ('default_gst_percent', ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
            (str(value),),
        )
        conn.commit()
        conn.close()

    def _make_lines(self, qty=10.0, price=100.0):
        return pd.DataFrame([
            {"Include": True, "Description": "Paint", "Qty": qty, "Unit Price Ex GST": price, "Unit": "L"}
        ])

    def test_default_gst_percent_falls_back_to_ten_when_unset(self):
        self.assertEqual(self.jobhub_enterprise._default_gst_percent(self.ctx), 10.0)

    def test_default_gst_percent_reads_configured_setting(self):
        self._set_gst_setting(15)
        self.assertEqual(self.jobhub_enterprise._default_gst_percent(self.ctx), 15.0)

    def test_new_purchase_order_snapshots_configured_rate(self):
        self._set_gst_setting(15)
        po_id = self.jobhub_enterprise._create_purchase_order(
            self.ctx, job_id=1, supplier="Acme Paint", po_no="PO-1001",
            order_date="2026-01-01", expected_date="2026-01-08", status="Requested",
            notes="", lines=self._make_lines(qty=10, price=100),
        )
        row = self._df_query(
            "SELECT subtotal_ex_gst, gst_percent, gst_amount, total_inc_gst FROM purchase_orders WHERE id = ?",
            (po_id,),
        ).iloc[0]
        self.assertEqual(row["subtotal_ex_gst"], 1000.0)
        self.assertEqual(row["gst_percent"], 15.0)
        self.assertEqual(row["gst_amount"], 150.0)
        self.assertEqual(row["total_inc_gst"], 1150.0)

    def test_changing_default_afterward_does_not_alter_existing_po(self):
        self._set_gst_setting(15)
        po_id = self.jobhub_enterprise._create_purchase_order(
            self.ctx, job_id=1, supplier="Acme Paint", po_no="PO-1002",
            order_date="2026-01-01", expected_date="2026-01-08", status="Requested",
            notes="", lines=self._make_lines(qty=10, price=100),
        )
        self._set_gst_setting(20)
        row = self._df_query(
            "SELECT gst_percent, gst_amount, total_inc_gst FROM purchase_orders WHERE id = ?",
            (po_id,),
        ).iloc[0]
        self.assertEqual(
            row["gst_percent"], 15.0,
            "Editing the system default afterward must not retroactively change an already-created PO's snapshot",
        )
        self.assertEqual(row["gst_amount"], 150.0)
        self.assertEqual(row["total_inc_gst"], 1150.0)

        new_default = self.jobhub_enterprise._default_gst_percent(self.ctx)
        self.assertEqual(new_default, 20.0, "The next NEW document should pick up the updated default")

    def test_supplier_invoice_match_uses_pos_own_snapshotted_rate_not_hardcoded_ten_percent(self):
        calculation = _extract_invoice_gst_calculation()
        namespace = dict(
            po_row={"gst_percent": 15.0},
            invoice_subtotal=1000.0,
            _f=self.jobhub_enterprise._f,
        )
        exec(calculation, namespace)
        self.assertEqual(namespace["invoice_gst_percent"], 15.0)
        self.assertEqual(
            namespace["gst"], 150.0,
            "Invoice GST must follow the PO's own snapshotted rate, not a hardcoded 10%",
        )

    def test_supplier_invoice_match_falls_back_to_ten_percent_when_po_row_missing_rate(self):
        calculation = _extract_invoice_gst_calculation()
        namespace = dict(
            po_row={"gst_percent": None},
            invoice_subtotal=1000.0,
            _f=self.jobhub_enterprise._f,
        )
        exec(calculation, namespace)
        self.assertEqual(namespace["gst"], 100.0)


if __name__ == "__main__":
    unittest.main()
