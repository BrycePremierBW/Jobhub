"""Regression test: the Job Register page must only run the selected
section's queries, not every section's queries on every page load
(jobhub-audit-2026-09, JH-PERF-JOBS-001).

Before this fix, `elif menu == "Jobs":` rendered all six sections (Add
Job, Edit Job, Remove / Archive, Archived Jobs, Search by Builder, Job
Register) inside `st.tabs(...)`. Streamlit executes every `with tab_x:`
body on every rerun regardless of which tab is visible, so every load of
this page ran get_builder_options(), get_product_supplier_options(), the
full job list query, the archived-jobs query, and the builder-search
query -- all six sections' worth of database work -- no matter which one
section the user was actually looking at. The same problem, and the same
fix (an explicit lazy section selector instead of eager tabs), was
already built and tested once for this exact page in the now-dead
jobhub/pages/jobs.py (PR #93) but never made it into this file.

This test extracts the real Job Register block from pb_jobhub_app.py and
executes it with fakes that record every call, proving that selecting
one section runs only that section's lookups and none of the others'.
"""
from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pb_jobhub_app.py"


def _extract_job_register_block() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    start = source.index('elif menu == "Jobs":')
    end = source.index('elif menu == "Import Take-off Job Pack":')
    block = source[start:end]
    # Replace the elif header with a bare `if True:` so the extracted block
    # is a valid standalone statement once wrapped in a function.
    block = block.replace('elif menu == "Jobs":', "if True:", 1)
    return textwrap.dedent(block)


class JobRegisterLazySectionsTests(unittest.TestCase):
    def setUp(self):
        self.block_source = _extract_job_register_block()
        self.calls = {
            "get_builder_options": 0,
            "get_product_supplier_options": 0,
            "get_employee_options": 0,
        }
        self.queries: list[str] = []

    def _fake_st(self, section: str) -> MagicMock:
        st = MagicMock()
        st.radio = MagicMock(return_value=section)
        st.columns = lambda n, *a, **k: [MagicMock() for _ in range(n)]
        st.form_submit_button = MagicMock(return_value=False)
        st.button = MagicMock(return_value=False)
        st.checkbox = MagicMock(return_value=False)
        st.selectbox = MagicMock(return_value="")
        st.multiselect = MagicMock(return_value=[])
        st.date_input = MagicMock(return_value=None)
        st.number_input = MagicMock(return_value=0.0)
        st.text_input = MagicMock(return_value="")
        st.text_area = MagicMock(return_value="")
        st.session_state = {}
        return st

    def _df_query(self, sql, params=()):
        self.queries.append(sql)
        return pd.DataFrame()

    def _get_builder_options(self):
        self.calls["get_builder_options"] += 1
        return {}

    def _get_product_supplier_options(self):
        self.calls["get_product_supplier_options"] += 1
        return []

    def _get_employee_options(self, active_only=True):
        self.calls["get_employee_options"] += 1
        return {}

    def _run_section(self, section: str) -> None:
        namespace = dict(
            menu="Jobs",
            st=self._fake_st(section),
            pd=pd,
            df_query=self._df_query,
            execute=MagicMock(),
            execute_with_rowcount=MagicMock(return_value=1),
            get_builder_options=self._get_builder_options,
            get_product_supplier_options=self._get_product_supplier_options,
            get_employee_options=self._get_employee_options,
            pb_error=MagicMock(),
            pb_success=MagicMock(),
            refresh=MagicMock(),
            record_audit_event=MagicMock(),
            serialise_material_supplier_list=MagicMock(return_value=""),
            parse_material_supplier_list=MagicMock(return_value=[]),
            next_job_no=MagicMock(return_value="J-0001"),
            pb_date=MagicMock(return_value=None),
            linked_job_counts=MagicMock(return_value={}),
            permanently_delete_job_and_linked_data=MagicMock(),
            get_current_user=MagicMock(return_value={"username": "tester"}),
            jobhub_now=MagicMock(),
            go_to_linked_job_view=MagicMock(),
            job_lookup_dataframe=MagicMock(return_value=pd.DataFrame()),
            select_job_from_dataframe=MagicMock(return_value=None),
        )
        wrapped = "def _run():\n" + textwrap.indent(self.block_source, "    ") + "\n_run()\n"
        exec(wrapped, namespace)

    def test_remove_archive_section_never_looks_up_builder_or_supplier_options(self):
        self._run_section("Remove / Archive")
        self.assertEqual(
            self.calls["get_builder_options"], 0,
            "Remove / Archive doesn't use builder options; it must not be looked up when this section runs",
        )
        self.assertEqual(self.calls["get_product_supplier_options"], 0)
        self.assertTrue(any("FROM jobs" in q for q in self.queries))
        self.assertFalse(any("Archived" in q and "job_no" in q for q in self.queries if "WHERE j.status = 'Archived'" in q))

    def test_add_job_section_looks_up_builder_and_supplier_options_but_not_archived_query(self):
        self._run_section("Add Job")
        self.assertEqual(self.calls["get_builder_options"], 1)
        self.assertEqual(self.calls["get_product_supplier_options"], 1)
        self.assertFalse(
            any("WHERE j.status = 'Archived'" in q for q in self.queries),
            "Add Job must not run the Archived Jobs section's query",
        )

    def test_job_register_list_section_does_not_look_up_builder_or_supplier_options(self):
        self._run_section("Job Register")
        self.assertEqual(
            self.calls["get_builder_options"], 0,
            "The full register list doesn't need builder/supplier options; it must not look them up",
        )
        self.assertEqual(self.calls["get_product_supplier_options"], 0)

    def test_only_one_sections_primary_query_runs_per_load(self):
        # Archived Jobs is the one section whose primary marker query
        # ("WHERE j.status = 'Archived'") should appear only when that
        # section itself is selected, never for any other section.
        for section in ["Add Job", "Edit Job", "Remove / Archive", "Search by Builder", "Job Register"]:
            with self.subTest(section=section):
                self.queries = []
                self._run_section(section)
                self.assertFalse(
                    any("WHERE j.status = 'Archived'" in q for q in self.queries),
                    f"{section!r} must not run the Archived Jobs query",
                )


if __name__ == "__main__":
    unittest.main()
