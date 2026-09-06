"""Regression test: receiving more of a PO line than was ordered must be
flagged, not saved silently (jobhub-audit-2026-09, JH-MATERIAL-001).

The "PO Register / Receiving" data editor's Received Qty column has no
upper bound tied to that row's own Ordered Qty (st.column_config.NumberColumn
can only set one fixed max_value for the whole column, not a per-row one),
so a typo -- 100 instead of 10 -- previously saved with no signal
whatsoever, silently inflating recorded receipts.

This test extracts the real over-receipt detection expression from source
and evaluates it against representative DataFrames, proving it flags a
line received above its ordered quantity and leaves normal/under-received
lines alone.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "jobhub_enterprise.py"


def _extract_expression() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    anchor = "over_received = edited_lines[\n"
    start = source.index(anchor) + len("over_received = ")
    end = source.index("]\n", start) + 1
    return source[start:end]


class PoReceivingOverQuantityGuardTests(unittest.TestCase):
    def setUp(self):
        self.expression = _extract_expression()

    def _flagged(self, rows):
        edited_lines = pd.DataFrame(rows)
        result = eval(self.expression, {}, {"edited_lines": edited_lines})
        return result["Description"].tolist()

    def test_flags_a_line_received_above_its_ordered_quantity(self):
        flagged = self._flagged([
            {"Description": "10L Paint", "Ordered Qty": 10.0, "Received Qty": 100.0},
        ])
        self.assertEqual(flagged, ["10L Paint"])

    def test_does_not_flag_an_exact_or_partial_receipt(self):
        flagged = self._flagged([
            {"Description": "Exact", "Ordered Qty": 10.0, "Received Qty": 10.0},
            {"Description": "Partial", "Ordered Qty": 10.0, "Received Qty": 4.0},
            {"Description": "Not yet received", "Ordered Qty": 10.0, "Received Qty": None},
        ])
        self.assertEqual(flagged, [])

    def test_only_flags_the_specific_over_received_line_among_several(self):
        flagged = self._flagged([
            {"Description": "Fine", "Ordered Qty": 5.0, "Received Qty": 5.0},
            {"Description": "Over", "Ordered Qty": 5.0, "Received Qty": 50.0},
        ])
        self.assertEqual(flagged, ["Over"])


if __name__ == "__main__":
    unittest.main()
