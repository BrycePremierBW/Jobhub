"""Regression test for wrong-target deletes/edits via colliding dropdown labels
(jobhub-audit-2026-09, JH-WRONGTARGET-001).

Several "select a record, then delete/edit it" flows in pb_jobhub_app.py built
their selectbox options as a dict keyed by a human-readable label (name,
description, job/item text) mapped to the record's database ID. If two rows
produce the same label -- two builders/clients with the same name, two
identically-priced estimate lines, two equipment checklist entries for the
same job/item -- the dict silently collapses to whichever row iterates last,
and the user has no way to pick the other one: the wrong record gets edited
or permanently deleted.

The already-correct instances elsewhere in the same file (User Access delete,
Employee delete, Merge Duplicate Contacts) always suffix the label with the
row's ID, which guarantees uniqueness. This test extracts the real dict
comprehension source for each fixed call site directly from pb_jobhub_app.py
and evaluates it against a synthetic DataFrame with two colliding rows, so it
fails the moment someone reverts one of these back to a label without an ID
-- it is not a string-match test, it proves the resulting mapping stays
unambiguous.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pandas as pd

APP_SOURCE_PATH = Path(__file__).resolve().parents[1] / "pb_jobhub_app.py"


def _extract_dict_comprehension(source: str, anchor: str) -> str:
    """Return the `{...}` dict-comprehension source starting at `anchor`."""
    start = source.index(anchor)
    brace_start = source.index("{", start)
    depth = 0
    for index in range(brace_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start:index + 1]
    raise AssertionError(f"Unbalanced braces scanning from anchor: {anchor!r}")


class WrongTargetDeleteLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_SOURCE_PATH.read_text(encoding="utf-8")

    def test_remove_builder_client_label_disambiguates_same_name_rows(self):
        expression = _extract_dict_comprehension(self.source, "builder_map = {\n                f\"{row['name']}")
        builders_df = pd.DataFrame(
            [{"id": 1, "name": "ABC Constructions"}, {"id": 2, "name": "ABC Constructions"}]
        )
        result = eval(expression, {}, {"builders_df": builders_df})
        self.assertEqual(len(result), 2, f"Same-name builders collided: {result}")
        self.assertEqual(set(result.values()), {1, 2})

    def test_edit_builder_client_label_disambiguates_same_name_rows(self):
        expression = _extract_dict_comprehension(
            self.source,
            "# name can't collide into one option and get the wrong one edited.\n            builder_map = {",
        )
        builders_df = pd.DataFrame(
            [{"id": 1, "name": "ABC Constructions"}, {"id": 2, "name": "ABC Constructions"}]
        )
        result = eval(expression, {}, {"builders_df": builders_df})
        self.assertEqual(len(result), 2, f"Same-name builders collided: {result}")
        self.assertEqual(set(result.values()), {1, 2})

    def test_delete_estimate_line_item_label_disambiguates_identical_rows(self):
        expression = _extract_dict_comprehension(self.source, "delete_options = {\n                f\"{r['Section']}")
        lines_df = pd.DataFrame(
            [
                {"id": 10, "Section": "Bedroom 2", "Description": "2 coats", "Line Total": 250.0},
                {"id": 11, "Section": "Bedroom 2", "Description": "2 coats", "Line Total": 250.0},
            ]
        )
        result = eval(expression, {"float": float, "int": int}, {"lines_df": lines_df})
        self.assertEqual(len(result), 2, f"Identical estimate lines collided: {result}")
        self.assertEqual(set(result.values()), {10, 11})

    def test_delete_equipment_checklist_line_label_disambiguates_identical_rows(self):
        expression = _extract_dict_comprehension(self.source, "delete_map = {\n                    f\"{row['Job No']}")
        all_df = pd.DataFrame(
            [
                {"Record ID": 100, "Job No": "PB25001", "Equipment Item": "Scaffold tower"},
                {"Record ID": 101, "Job No": "PB25001", "Equipment Item": "Scaffold tower"},
            ]
        )
        result = eval(expression, {"int": int}, {"all_df": all_df})
        self.assertEqual(len(result), 2, f"Identical equipment lines collided: {result}")
        self.assertEqual(set(result.values()), {100, 101})

    def test_established_correct_pattern_still_includes_id_for_reference(self):
        # Sanity check on the extraction helper itself, against the two
        # call sites that were already correct before this fix (User Access
        # delete, Employee delete) -- confirms the ID-suffix pattern this
        # test enforces matches the codebase's own established convention.
        for anchor, id_column in (
            ("delete_options = {\n                f\"{row['Username']}", "ID"),
            ("employee_delete_options = {\n                f\"{row['Employee']}", "ID"),
        ):
            expression = _extract_dict_comprehension(self.source, anchor)
            self.assertIn(f"row['{id_column}']", expression)


if __name__ == "__main__":
    unittest.main()
