"""Regression test: pre-start/hazard/quality/completion form submission must
not create duplicate rows (and, for a Hazard/Incident Report, duplicate
management alerts) on a double-click or resubmit (jobhub-audit-2026-09,
JH-DUPCREATE-003).

jobhub_enterprise._render_form_submission() had no duplicate-submit guard at
all -- unlike the Variation/Claim forms (already fixed) it has no natural
"number" field to check for an existing row, and the field_forms table has
no unique constraint on (job_id, employee_id, form_type, form_date). A
double-click, or a re-click after a slow response, inserted two identical
rows and, for a Hazard / Incident Report, fired _notify_management twice.

A per-day uniqueness rule would be the wrong fix: a second genuine Hazard /
Incident Report for the same job on the same day must still be allowed. The
fix instead guards on the *exact submitted content* (job, form type, date,
answers, signature) via a session-scoped signature, matching the same
pattern already used for Smart Intake's duplicate-submit guard.

This test extracts the real `if submitted:` block from source and execs it
twice against a temporary SQLite database with the exact same answers,
proving the first submission inserts one row and the second is rejected
without inserting or re-notifying, while a submission with different
answers is never blocked.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jobhub_enterprise as enterprise

MODULE_PATH = ROOT / "jobhub_enterprise.py"


def _extract_submit_block() -> str:
    source = MODULE_PATH.read_text(encoding="utf-8")
    anchor = "if submitted:"
    func_start = source.index("def _render_form_submission(")
    anchor_start = source.index(anchor, func_start)
    block_start = source.rfind("\n", 0, anchor_start) + 1
    # The block ends right before the following top-level "def " at column 0.
    next_def = source.index("\ndef render_compliance(", anchor_start)
    dedented = textwrap.dedent(source[block_start:next_def])
    # The real block relies on being inside a function (it "return"s early on
    # a duplicate submission), so wrap it in one for exec().
    wrapped = "def _run():\n" + textwrap.indent(dedented, "    ")
    return wrapped + "\n_run()\n"


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}


class FieldFormDuplicateSubmitTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE field_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER, employee_id INTEGER, form_type TEXT,
                form_date TEXT, status TEXT, answers_json TEXT,
                signature_name TEXT, created_by TEXT, created_at TEXT
            )
            """
        )
        self.conn.commit()
        self.notifications = []
        self.errors = []
        self.successes = []
        block = _extract_submit_block()
        self.block = block

    def _execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def _df_query(self, sql, params=()):
        import pandas as pd
        cur = self.conn.execute(sql, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=columns)

    def _submit(self, fake_st, job_id=1, job_label="PB25001 - Test Job", form_type="Hazard / Incident Report",
                answers=None, signature="Jane Foreman", acknowledgement=True):
        ctx = {
            "execute": self._execute,
            "df_query": self._df_query,
            "get_current_user": lambda: {"employee_id": 7, "username": "jane"},
            "record_audit_event": lambda *a, **k: None,
            "pb_success": lambda msg: self.successes.append(msg),
            "pb_error": lambda msg: self.errors.append(msg),
            "pb_rerun": lambda: None,
            "connect": lambda: self.conn,
        }
        namespace = dict(
            ctx=ctx,
            st=fake_st,
            submitted=True,
            acknowledgement=acknowledgement,
            signature=signature,
            job_id=job_id,
            job_label=job_label,
            form_type=form_type,
            answers=answers if answers is not None else {"area": "Lounge", "scope_complete": "Yes"},
            json=json,
            _user=enterprise._user,
            _execute=enterprise._execute,
            _query=enterprise._query,
            _audit=lambda *a, **k: None,
            _notify_management=lambda *a, **k: self.notifications.append(a),
            _today=enterprise._today,
            _now=enterprise._now,
            log_error=lambda *a, **k: None,
        )
        exec(self.block, namespace)

    def test_second_identical_submission_is_rejected_and_does_not_duplicate(self):
        fake_st = FakeStreamlit()
        self._submit(fake_st)
        self._submit(fake_st)  # the double-click / resubmit, identical content

        rows = self._df_query("SELECT COUNT(*) AS c FROM field_forms").iloc[0]["c"]
        self.assertEqual(rows, 1, "A duplicate submission of identical content must not insert a second row")
        self.assertEqual(len(self.notifications), 1, "The duplicate must not fire a second management alert")
        self.assertEqual(len(self.successes), 1)
        self.assertEqual(len(self.errors), 1)

    def test_a_second_genuine_report_with_different_answers_is_not_blocked(self):
        # Two real Hazard/Incident Reports on the same job, same day, same
        # person -- a legitimate scenario the fix must not prevent.
        fake_st = FakeStreamlit()
        self._submit(fake_st, answers={"area": "Lounge", "scope_complete": "Yes"})
        self._submit(fake_st, answers={"area": "Kitchen", "scope_complete": "No"})

        rows = self._df_query("SELECT COUNT(*) AS c FROM field_forms").iloc[0]["c"]
        self.assertEqual(rows, 2, "A genuinely different report must not be blocked as a duplicate")
        self.assertEqual(len(self.notifications), 2)

    def test_empty_signature_is_rejected(self):
        fake_st = FakeStreamlit()
        self._submit(fake_st, signature="   ")
        rows = self._df_query("SELECT COUNT(*) AS c FROM field_forms").iloc[0]["c"]
        self.assertEqual(rows, 0)
        self.assertEqual(len(self.errors), 1)


if __name__ == "__main__":
    unittest.main()
