"""Regression test: the Equipment page must only run the selected
section's queries, not every section's queries on every page load
(jobhub-audit-2026-09, JH-PERF-JOBS-001 follow-up).

Before this fix, `elif menu == "Equipment":` rendered all five sections
(Import Filled PDF Checklist, Job Equipment Checklist, Job Equipment
Master List, All Saved Equipment, Manage Checklist Items) inside
st.tabs(...), with a shared get_job_options() lookup computed eagerly at
the top for all of them. Streamlit executes every `with tab_x:` body on
every rerun regardless of which tab is visible, so every load of this
page ran get_job_options() plus the checklist-items query, the
all-saved-records query, and the checklist-items management query --
four separate queries every time, no matter which one section a user
was actually looking at. The same class of fix was drafted once for this
page's dead jobhub/pages/equipment.py counterpart (still-open PR #99,
never merged) but never ported into this production path.

This test extracts the real Equipment block from pb_jobhub_app.py and
executes it with fakes that record every query and every get_job_options
call, proving that selecting one section runs only that section's
lookups.
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


class EquipmentLazySectionsTests(unittest.TestCase):
    def setUp(self):
        self.block_source = _extract_equipment_block()
        self.queries: list[str] = []
        self.job_options_calls = 0

    def _get_job_options(self):
        self.job_options_calls += 1
        return {}

    def _fake_st(self, section: str) -> MagicMock:
        st = MagicMock()
        st.radio = MagicMock(return_value=section)
        st.columns = lambda n, *a, **k: [MagicMock() for _ in range(n)]
        st.form_submit_button = MagicMock(return_value=False)
        st.button = MagicMock(return_value=False)
        st.checkbox = MagicMock(return_value=False)
        st.selectbox = MagicMock(return_value="")
        st.multiselect = MagicMock(return_value=[])
        st.text_input = MagicMock(return_value="")
        st.text_area = MagicMock(return_value="")
        st.number_input = MagicMock(return_value=0.0)
        st.file_uploader = MagicMock(return_value=None)
        st.expander = MagicMock()
        st.session_state = {}
        return st

    def _df_query(self, sql, params=()):
        self.queries.append(sql)
        return pd.DataFrame()

    def _run_section(self, section: str) -> None:
        namespace = dict(
            menu="Equipment",
            st=self._fake_st(section),
            pd=pd,
            df_query=self._df_query,
            execute=MagicMock(),
            pb_error=MagicMock(),
            pb_success=MagicMock(),
            refresh=MagicMock(),
            record_audit_event=MagicMock(),
            get_job_options=self._get_job_options,
            parse_master_checklist_pdf=MagicMock(),
            import_master_checklist_to_job=MagicMock(return_value=(0, 0)),
            jobhub_today=MagicMock(return_value="2026-09-06"),
        )
        wrapped = "def _run():\n" + textwrap.indent(self.block_source, "    ") + "\n_run()\n"
        exec(wrapped, namespace)

    def test_manage_checklist_items_does_not_look_up_job_options(self):
        self._run_section("Manage Checklist Items")
        self.assertEqual(
            self.job_options_calls, 0,
            "Manage Checklist Items doesn't use jobs; it must not look up job options",
        )

    def test_all_saved_equipment_does_not_look_up_job_options(self):
        self._run_section("All Saved Equipment")
        self.assertEqual(self.job_options_calls, 0)

    def test_job_equipment_checklist_looks_up_job_options_exactly_once(self):
        self._run_section("Job Equipment Checklist")
        self.assertEqual(self.job_options_calls, 1)

    def test_manage_checklist_items_does_not_run_all_saved_equipment_query(self):
        self._run_section("Manage Checklist Items")
        self.assertFalse(any("equipment_checklist_records r" in q for q in self.queries))

    def test_job_equipment_master_list_does_not_run_all_saved_equipment_query(self):
        self._run_section("Job Equipment Master List")
        self.assertFalse(any("equipment_checklist_records r" in q for q in self.queries))

    def test_all_saved_equipment_does_not_look_up_master_list_query(self):
        self._run_section("All Saved Equipment")
        self.assertFalse(any("CROSS JOIN jobs j" in q for q in self.queries))


if __name__ == "__main__":
    unittest.main()
