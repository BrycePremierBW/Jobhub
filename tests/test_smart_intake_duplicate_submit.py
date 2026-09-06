"""Regression test: Smart Intake's duplicate-submit guard (jobhub-audit-2026-09,
JH-DUPCREATE-001).

smart_intake_import_page() showed no confirmation state that removes or
disables its "Create Job and Import" button after a successful import, and
assigns a fresh job number on every run when the intake pack doesn't state
one (the common case for free-form documents). A user re-clicking the button
-- because a slow import gave no visible feedback, or because they clicked
again after seeing the success message -- re-ran the whole import and created
a second, fully duplicated job (its own estimate lines, materials, and
attached documents).

pb_jobhub_app.py is a 1.1MB monolith with ~50 monkey-patch guards installed
at import time, which makes driving it end-to-end through
streamlit.testing.v1.AppTest for one specific nested page extremely brittle
(widget-tree identity breaks across reruns in ways unrelated to this fix).
Instead, this test extracts the real `intake_signature = (...)` expression
from the source and executes it directly against fake uploaded-file objects,
proving: the same upload + job-choice always produces the same signature
(so re-clicking is detected), a different upload or a different target job
produces a different signature (so a genuinely new import is never blocked),
and marking a signature as imported (exactly as the success path does) makes
`disabled=intake_signature in already_imported` evaluate True on the next
render -- the same condition wired into the real `st.button(..., disabled=...)`
call a few lines below the extracted expression.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_SOURCE_PATH = Path(__file__).resolve().parents[1] / "pb_jobhub_app.py"


def _extract_signature_expression(source: str) -> str:
    start = source.index("intake_signature = (")
    open_paren = source.index("(", start)
    depth = 0
    for index in range(open_paren, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren:index + 1]
    raise AssertionError("Unbalanced parens scanning intake_signature expression")


def _uploaded_file_size(f) -> int:
    return f.size


class SmartIntakeSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = APP_SOURCE_PATH.read_text(encoding="utf-8")
        cls.expression = _extract_signature_expression(source)
        # Confirm the extracted expression is really wired into a disabled
        # button and a post-success "mark as imported" call, not dead code.
        cls.assertIn_ = None
        button_block_start = source.index("if st.button(", source.index("intake_signature = ("))
        button_block = source[button_block_start:button_block_start + 400]
        assert "disabled=intake_signature in already_imported" in button_block, (
            "intake_signature is no longer wired into the Create Job and "
            "Import button's disabled= condition"
        )
        assert "already_imported.add(intake_signature)" in source, (
            "Nothing marks a successful import's signature as done any more"
        )

    def _signature(self, files, create_new_job, selected_job_id, intake_job_name):
        namespace = {
            "uploaded_documents": files,
            "create_new_job": create_new_job,
            "selected_job_id": selected_job_id,
            "intake_job_name": intake_job_name,
            "uploaded_file_size": _uploaded_file_size,
        }
        return eval(self.expression, dict(namespace))

    def test_same_upload_and_target_produces_the_same_signature(self):
        files = [SimpleNamespace(name="scope.txt", size=1234)]
        sig1 = self._signature(files, True, None, "New Job A")
        sig2 = self._signature(files, True, None, "New Job A")
        self.assertEqual(sig1, sig2)

    def test_reimporting_the_same_signature_is_detected_as_already_done(self):
        files = [SimpleNamespace(name="scope.txt", size=1234)]
        signature = self._signature(files, True, None, "New Job A")
        already_imported = set()
        self.assertNotIn(signature, already_imported)  # first click: allowed

        already_imported.add(signature)  # what the success path does

        # A re-click with the exact same upload and job choice still visible
        # on the page must now be recognised as already done.
        repeat_signature = self._signature(files, True, None, "New Job A")
        self.assertIn(repeat_signature, already_imported)

    def test_a_different_upload_is_not_blocked_by_a_previous_import(self):
        first_files = [SimpleNamespace(name="scope.txt", size=1234)]
        second_files = [SimpleNamespace(name="scope-v2.txt", size=999)]
        already_imported = {self._signature(first_files, True, None, "New Job A")}

        second_signature = self._signature(second_files, True, None, "New Job B")
        self.assertNotIn(
            second_signature,
            already_imported,
            "A genuinely different upload/job must not be blocked as a duplicate",
        )

    def test_attach_to_existing_job_ignores_the_new_job_name_field(self):
        # When create_new_job is False, intake_job_name is intentionally
        # excluded from the signature (it's blank/irrelevant on that path) --
        # the target job id is what disambiguates instead.
        files = [SimpleNamespace(name="scope.txt", size=1234)]
        sig_a = self._signature(files, False, 42, "")
        sig_b = self._signature(files, False, 42, "unused text")
        self.assertEqual(sig_a, sig_b)

        sig_other_job = self._signature(files, False, 43, "")
        self.assertNotEqual(sig_a, sig_other_job)


if __name__ == "__main__":
    unittest.main()
