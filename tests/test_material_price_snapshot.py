"""Regression test: material cost reporting must snapshot the product price
at order time rather than joining live against the current catalog price
(architecture decision #4).

Before this fix, every job-cost query computed material cost as
`qty * COALESCE(m.custom_unit_price, p.price_ex_gst, 0)` -- a LEFT JOIN
against the live `products` table with no price stored on the
material_entries row itself. Editing a product's price in the catalog
today silently changed the reported "Committed Material Cost" and
"Actual Material Cost" of every job that had ever ordered that product,
including jobs completed months earlier, with no way to reproduce what a
job actually cost at the time.

This test extracts the real materials-cost aggregation query from
`enterprise_job_cost_dataframe()` in jobhub_enterprise.py and runs it
against a temporary SQLite database, proving a material_entries row with
a populated price_snapshot keeps reporting the price it was created with
even after the catalog price changes -- and separately proves the actual
price_snapshot computation used by the Job Pack / Smart Intake import
code (in pb_jobhub_app.py) picks the sheet's own price over a live
product re-lookup, falling back to the live price only when the sheet
didn't carry one.
"""
from __future__ import annotations

import sqlite3
import textwrap
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENTERPRISE_PATH = ROOT / "jobhub_enterprise.py"
APP_PATH = ROOT / "pb_jobhub_app.py"


def _extract_materials_query() -> str:
    source = ENTERPRISE_PATH.read_text(encoding="utf-8")
    anchor = source.index("materials = _query(")
    start = source.rfind("\n", 0, anchor) + 1
    end = source.index("FROM material_entries m", start)
    end = source.index('"""', end) + 3
    end = source.index(")", end) + 1
    return textwrap.dedent(source[start:end])


def _extract_price_snapshot_line() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    anchor = source.index('price_snapshot = row["unit_price"] or (float(product_match[1] or 0) if product_match else 0.0)')
    start = source.rfind("\n", 0, anchor) + 1
    end = source.index("\n", anchor) + 1
    return textwrap.dedent(source[start:end])


class MaterialPriceSnapshotAggregationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, price_ex_gst REAL)")
        self.conn.execute(
            "CREATE TABLE material_entries (id INTEGER PRIMARY KEY, job_id INTEGER, product_id INTEGER, "
            "qty_required REAL, qty_received REAL, custom_unit_price REAL, price_snapshot REAL)"
        )
        self.conn.commit()
        self.query_source = _extract_materials_query()

    def _query(self, ctx, sql, params=()):
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=columns)

    def _run_materials_query(self):
        namespace = dict(ctx={}, _query=self._query)
        exec(self.query_source, namespace)
        return namespace["materials"]

    def test_committed_cost_uses_snapshot_not_live_price(self):
        self.conn.execute("INSERT INTO products (id, price_ex_gst) VALUES (1, 50.0)")
        self.conn.execute(
            "INSERT INTO material_entries (job_id, product_id, qty_required, qty_received, price_snapshot) "
            "VALUES (1, 1, 10, 10, 20.0)"
        )
        self.conn.commit()

        result = self._run_materials_query().set_index("job_id")
        self.assertEqual(result.loc[1, "committed_material_cost"], 200.0)

        # The catalog price changes after the order was placed.
        self.conn.execute("UPDATE products SET price_ex_gst = 999.0 WHERE id = 1")
        self.conn.commit()

        result_after_price_change = self._run_materials_query().set_index("job_id")
        self.assertEqual(
            result_after_price_change.loc[1, "committed_material_cost"], 200.0,
            "Editing the live catalog price must not retroactively change an already-recorded job's material cost",
        )

    def test_pre_snapshot_rows_still_fall_back_to_live_price(self):
        self.conn.execute("INSERT INTO products (id, price_ex_gst) VALUES (1, 50.0)")
        self.conn.execute(
            "INSERT INTO material_entries (job_id, product_id, qty_required, qty_received, price_snapshot) "
            "VALUES (1, 1, 10, 10, NULL)"
        )
        self.conn.commit()
        result = self._run_materials_query().set_index("job_id")
        self.assertEqual(
            result.loc[1, "committed_material_cost"], 500.0,
            "A row created before this migration (no snapshot) should keep using the live price, as before",
        )

    def test_custom_unit_price_still_takes_priority_over_snapshot(self):
        self.conn.execute("INSERT INTO products (id, price_ex_gst) VALUES (1, 50.0)")
        self.conn.execute(
            "INSERT INTO material_entries (job_id, product_id, qty_required, qty_received, "
            "custom_unit_price, price_snapshot) VALUES (1, 1, 10, 10, 5.0, 20.0)"
        )
        self.conn.commit()
        result = self._run_materials_query().set_index("job_id")
        self.assertEqual(result.loc[1, "committed_material_cost"], 50.0)


class MaterialImportPriceSnapshotComputationTests(unittest.TestCase):
    def setUp(self):
        self.line = _extract_price_snapshot_line()

    def _compute(self, unit_price, product_match):
        namespace = dict(row={"unit_price": unit_price}, product_match=product_match)
        exec(self.line, namespace)
        return namespace["price_snapshot"]

    def test_sheet_price_wins_even_when_product_matched(self):
        self.assertEqual(self._compute(75.0, (1, 999.0)), 75.0)

    def test_falls_back_to_live_product_price_when_sheet_has_no_price(self):
        self.assertEqual(self._compute(0.0, (1, 42.5)), 42.5)

    def test_zero_when_neither_sheet_price_nor_product_match(self):
        self.assertEqual(self._compute(0.0, None), 0.0)


if __name__ == "__main__":
    unittest.main()
