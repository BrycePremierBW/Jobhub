"""Regression test: an already-logged-in session must pick up a role/active
change on its very next action, not only when a new login or a token
restore happens (jobhub-audit-2026-09 architecture decision #8).

require_login() used to trust st.session_state["user"] indefinitely for the
life of a browser session -- only a fresh login or an auth-token restore
(fixed separately, see test_auth_token_expiry_and_revalidation.py)
re-checked the database. An admin deactivating or demoting a currently
logged-in user had no effect until that user's own Streamlit session ended.
Streamlit reruns the whole script on almost every interaction, so this test
proves _revalidate_session_user() -- called on every already-logged-in pass
through require_login() -- makes that change apply on the next action
instead.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import json, os, sys
os.environ["DATA_DIR"] = os.environ["INTEGRATION_DATA_DIR"]
sys.path.insert(0, os.getcwd())
import pb_jobhub_app as app
app.USE_POSTGRES = False
app.init_db()

conn = app.connect()
cur = conn.cursor()
cur.execute(
    "INSERT INTO app_users (username, password_hash, role, active) VALUES (?, ?, ?, 1)",
    ("revaltest", app.hash_password("Irrelevant-Test-Pw-2026!"), "manager"),
)
user_id = int(cur.lastrowid)
conn.commit()
conn.close()

session_user = {
    "id": user_id,
    "username": "revaltest",
    "role": "manager",
    "employee_id": None,
    "employee_name": "",
    "must_change_password": False,
}

# Unchanged account: revalidation must be a no-op.
unchanged = app._revalidate_session_user(dict(session_user))
print("UNCHANGED_ROLE:" + str(unchanged and unchanged.get("role")))

# Role demoted server-side after the session's user dict was cached.
app.execute("UPDATE app_users SET role = 'employee' WHERE id = ?", (user_id,))
demoted = app._revalidate_session_user(dict(session_user))
print("DEMOTED_ROLE:" + str(demoted and demoted.get("role")))

# Account deactivated server-side.
app.execute("UPDATE app_users SET active = 0 WHERE id = ?", (user_id,))
deactivated = app._revalidate_session_user(dict(session_user))
print("DEACTIVATED_RESULT:" + repr(deactivated))

# Account deleted outright.
app.execute("DELETE FROM app_users WHERE id = ?", (user_id,))
deleted = app._revalidate_session_user(dict(session_user))
print("DELETED_RESULT:" + repr(deleted))
"""


class SessionRoleRevalidationTest(unittest.TestCase):
    def test_role_and_active_changes_apply_on_next_revalidation(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_session_reval_")
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        data_dir = os.path.join(temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        env = dict(os.environ)
        env["DATA_DIR"] = data_dir
        env["INTEGRATION_DATA_DIR"] = data_dir

        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}",
        )
        lines = dict(
            line.split(":", 1) for line in completed.stdout.splitlines() if ":" in line
        )
        self.assertEqual(lines["UNCHANGED_ROLE"], "manager")
        self.assertEqual(
            lines["DEMOTED_ROLE"], "employee",
            "A role change made after the session cached its user dict must apply on revalidation",
        )
        self.assertEqual(
            lines["DEACTIVATED_RESULT"], "None",
            "A deactivated account must fail revalidation (forcing logout)",
        )
        self.assertEqual(
            lines["DELETED_RESULT"], "None",
            "A deleted account must fail revalidation (forcing logout)",
        )


if __name__ == "__main__":
    unittest.main()
