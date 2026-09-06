"""Regression test: saving the Job Equipment Checklist must not re-query
the database once per checklist item (jobhub-audit-2026-09,
JH-PERF-JOBS-001 follow-up).

Before this fix, the "Job Equipment Checklist" save handler in
pb_jobhub_app.py already loaded every existing equipment_checklist_records
row for the selected job once, into `existing_by_item`, purely to
populate the form's default widget values. But then, inside the
`if submitted:` save loop, it re-ran
`SELECT id FROM equipment_checklist_records WHERE job_id = ? AND
checklist_item_id = ?` again for every single checklist item -- a
checklist that can easily have dozens of items meant dozens of redundant
SELECT statements on every save, duplicating a query whose answer had
already been loaded moments earlier in the very same script run.

This test extracts the real Equipment block, drives the "Job Equipment
Checklist" section through a submitted save with two checklist items (one
with an existing record, one without), and proves the save loop issues
zero additional per-item SELECT queries -- reusing the one upfront query
instead.
"""
from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pb_jobhub_app.py"


def _extract_equipment_block() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    start = source.index('elif menu == "Equipment":')
    end = source.index('elif menu == "Job Photos":')
    block = source[start:end]
    block = block.replace('elif menu == "Equipment":', "if True:", 1)
    return textwrap.dedent(block)


class EquipmentChecklistSaveNPlusOneTests(unittest.TestCase):
    def setUp(self):
        self.block_source = _extract_equipment_block()
        self.queries: list[tuple[str, tuple]] = []
        self.executed: list[tuple[str, tuple]] = []

    def _df_query(self, sql, params=()):
        self.queries.append((sql, params))
        if "FROM equipment_checklist_items" in sql:
            return pd.DataFrame([
                {"id": 1, "category": "Ladders", "item_name": "Extension Ladder", "default_qty": 1.0, "notes": ""},
                {"id": 2, "category": "Ladders", "item_name": "Step Ladder", "default_qty": 1.0, "notes": ""},
            ])
        if "FROM equipment_checklist_records" in sql:
            # Item 1 already has a saved record; item 2 does not.
            return pd.DataFrame([
                {
                    "id": 100, "job_id": 1, "checklist_item_id": 1,
                    "qty_required": 1.0, "qty_taken": 1.0, "qty_returned": 0.0,
                    "is_required": 1, "is_packed": 1, "is_returned": 0,
                    "date_out": "", "date_in": "", "taken_by": "", "returned_by": "",
                    "condition_out": "", "condition_in": "", "notes": "",
                }
            ])
        return pd.DataFrame()

    def _execute(self, sql, params=()):
        self.executed.append((sql, params))

    def _fake_st(self) -> MagicMock:
        st = MagicMock()
        st.radio = MagicMock(return_value="Job Equipment Checklist")
        st.columns = lambda spec, *a, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
        st.selectbox = MagicMock(return_value="Job 1 - Test Job")
        st.checkbox = MagicMock(return_value=True)
        st.number_input = MagicMock(return_value=0.0)
        st.text_input = MagicMock(return_value="")
        st.text_area = MagicMock(return_value="")
        st.form_submit_button = MagicMock(return_value=True)
        st.session_state = {}
        return st

    def test_save_does_not_re_query_per_checklist_item(self):
        namespace = dict(
            menu="Equipment",
            st=self._fake_st(),
            pd=pd,
            df_query=self._df_query,
            execute=self._execute,
            pb_error=MagicMock(),
            pb_success=MagicMock(),
            refresh=MagicMock(),
            record_audit_event=MagicMock(),
            get_job_options=MagicMock(return_value={"Job 1 - Test Job": 1}),
            parse_master_checklist_pdf=MagicMock(),
            import_master_checklist_to_job=MagicMock(return_value=(0, 0)),
            jobhub_today=MagicMock(return_value="2026-09-06"),
        )
        wrapped = "def _run():\n" + textwrap.indent(self.block_source, "    ") + "\n_run()\n"
        exec(wrapped, namespace)

        per_item_select_queries = [
            (sql, params) for sql, params in self.queries
            if "SELECT id FROM equipment_checklist_records" in sql
        ]
        self.assertEqual(
            per_item_select_queries, [],
            "The save loop must reuse the upfront existing_df query instead of "
            "re-querying per checklist item",
        )

        # Two checklist items: item 1 already exists (-> UPDATE), item 2 is
        # new (-> INSERT). Both writes must still happen correctly using the
        # reused lookup, proving the fix didn't just skip the query but
        # actually keeps the same save behaviour.
        insert_calls = [c for c in self.executed if "INSERT INTO equipment_checklist_records" in c[0]]
        update_calls = [c for c in self.executed if "UPDATE equipment_checklist_records" in c[0]]
        self.assertEqual(len(insert_calls), 1, "The new item (no existing record) must be inserted")
        self.assertEqual(len(update_calls), 1, "The existing item must be updated, not re-inserted")
        self.assertEqual(update_calls[0][1][-1], 100, "The update must target the existing record's real id")


if __name__ == "__main__":
    unittest.main()
