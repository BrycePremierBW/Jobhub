"""Regression test: the Builders & Clients page must only run the
selected section's query, not every section's query on every page load
(jobhub-audit-2026-09, JH-PERF-JOBS-001 follow-up).

Before this fix, `elif menu == "Builders & Clients":` rendered all five
sections (Add, Edit, Remove, Merge, List) inside `st.tabs(...)`.
Streamlit executes every `with tab_x:` body on every rerun regardless of
which tab is visible, so every load of this page ran the Edit section's
`SELECT * FROM builders_clients`, the Remove section's
`SELECT id, name FROM builders_clients`, the Merge section's own
builders_clients query, and the List section's `SELECT ... FROM
builders_clients` -- four separate queries against the same table, every
time, no matter which one section a user was actually looking at.

This test extracts the real Builders & Clients block from
pb_jobhub_app.py and executes it with fakes that record every query,
proving that selecting one section runs only that section's query.
"""
from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "pb_jobhub_app.py"


def _extract_builders_clients_block() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    start = source.index('elif menu == "Builders & Clients":')
    end = source.index('elif menu == "Employees":')
    block = source[start:end]
    block = block.replace('elif menu == "Builders & Clients":', "if True:", 1)
    return textwrap.dedent(block)


class BuildersClientsLazySectionsTests(unittest.TestCase):
    def setUp(self):
        self.block_source = _extract_builders_clients_block()
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
        st.text_input = MagicMock(return_value="")
        st.text_area = MagicMock(return_value="")
        st.session_state = {}
        return st

    def _df_query(self, sql, params=()):
        self.queries.append(sql)
        return pd.DataFrame()

    def _run_section(self, section: str) -> None:
        namespace = dict(
            menu="Builders & Clients",
            st=self._fake_st(section),
            pd=pd,
            df_query=self._df_query,
            execute=MagicMock(),
            pb_error=MagicMock(),
            pb_success=MagicMock(),
            refresh=MagicMock(),
            record_audit_event=MagicMock(),
            clean_contact_merge_value=MagicMock(return_value=""),
            builder_client_merge_defaults=MagicMock(return_value={}),
            merge_builder_client_records=MagicMock(return_value={
                "primary_name": "x", "duplicates_removed": 0, "jobs_moved": 0,
            }),
            job_lookup_dataframe=MagicMock(return_value=pd.DataFrame()),
            select_job_from_dataframe=MagicMock(return_value=None),
            go_to_linked_job_view=MagicMock(),
        )
        wrapped = "def _run():\n" + textwrap.indent(self.block_source, "    ") + "\n_run()\n"
        exec(wrapped, namespace)

    def test_add_section_runs_no_query_until_form_submission(self):
        self._run_section("Add")
        self.assertEqual(self.queries, [])

    def test_edit_section_runs_only_its_own_query(self):
        self._run_section("Edit")
        self.assertEqual(len(self.queries), 1)
        self.assertIn("FROM builders_clients", self.queries[0])
        self.assertNotIn("linked_jobs", "".join(self.queries).lower())

    def test_remove_section_does_not_run_edit_or_list_queries(self):
        self._run_section("Remove")
        self.assertTrue(any("SELECT id, name FROM builders_clients" in q for q in self.queries))
        self.assertFalse(any("SELECT * FROM builders_clients" in q for q in self.queries))

    def test_list_section_does_not_run_edit_or_merge_queries(self):
        # List legitimately runs its own "SELECT id, name FROM
        # builders_clients" for the "view linked jobs" lookup below the
        # main list -- that's expected, not cross-section leakage. What
        # must not happen is Edit's full-row query or Merge's query.
        self._run_section("List")
        self.assertFalse(any("SELECT * FROM builders_clients" in q for q in self.queries))
        self.assertFalse(any("qbcc, abn, terms, notes" in q for q in self.queries))

    def test_only_the_selected_sections_query_runs(self):
        markers = {
            "Edit": "SELECT * FROM builders_clients",
            "Remove": "SELECT id, name FROM builders_clients",
        }
        for section, own_marker in markers.items():
            with self.subTest(section=section):
                self.queries = []
                self._run_section(section)
                for other_section, other_marker in markers.items():
                    if other_section == section:
                        continue
                    self.assertFalse(
                        any(other_marker in q for q in self.queries),
                        f"{section!r} must not run {other_section!r}'s query",
                    )


if __name__ == "__main__":
    unittest.main()
