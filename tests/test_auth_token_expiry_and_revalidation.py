"""Regression test: persistent "Stay logged in on this device" auth tokens
must expire and must be re-validated against the live app_users row on every
restore, not trust the cached snapshot (jobhub-audit-2026-09, JH-AUTHZ-004).

_get_user_by_auth_token() previously returned whatever JSON blob was cached
in app_settings at login time, forever, with no expiry and no re-check
against app_users. A deactivated or role-demoted user kept their old cached
role and full access indefinitely on any device that still had the token in
localStorage (jobhub/persistent_login.py stores it there and re-attaches it
via the `auth` query param on every visit).

This test drives the real login/save/restore functions against a temporary
SQLite database (same schema/helpers as the live app) and proves:
- immediately after login, restoring the token returns the current user;
- deactivating the account makes the token stop working AND deletes it
  server-side (so persistent_login.py's stale-token cleanup fires too);
- demoting the account's role makes a restore return the NEW role, not the
  role cached at login time;
- a token whose cached issued_at is older than the configured max age is
  rejected even though the account is untouched.
"""
from __future__ import annotations

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
    ("tokentest", app.hash_password("Irrelevant-Test-Pw-2026!"), "manager"),
)
user_id = int(cur.lastrowid)
conn.commit()
conn.close()

user_dict = {
    "id": user_id,
    "username": "tokentest",
    "role": "manager",
    "employee_id": None,
    "employee_name": "",
    "must_change_password": False,
}
token = "test-token-0000000000000000000000000000"
app._save_user_auth_token(token, user_dict)

restored = app._get_user_by_auth_token(token)
print("STEP1_ROLE:" + str(restored and restored.get("role")))

app.execute("UPDATE app_users SET active = 0 WHERE id = ?", (user_id,))
after_deactivate = app._get_user_by_auth_token(token)
print("STEP2_RESULT:" + repr(after_deactivate))
token_row = app.df_query(
    "SELECT COUNT(*) AS c FROM app_settings WHERE setting_key = ?", (f"auth_token:{token}",)
).iloc[0]["c"]
print("STEP2_TOKEN_ROWS:" + str(token_row))

app.execute("UPDATE app_users SET active = 1, role = 'employee' WHERE id = ?", (user_id,))
token2 = "test-token-1111111111111111111111111111"
app._save_user_auth_token(token2, user_dict)  # cached role is still "manager"
after_demote = app._get_user_by_auth_token(token2)
print("STEP3_ROLE:" + str(after_demote and after_demote.get("role")))

old_payload = dict(user_dict)
old_payload["role"] = "employee"
old_payload["issued_at"] = "2020-01-01T00:00:00"
token3 = "test-token-2222222222222222222222222222"
app.execute(
    "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
    (f"auth_token:{token3}", json.dumps(old_payload)),
)
after_expiry = app._get_user_by_auth_token(token3)
print("STEP4_RESULT:" + repr(after_expiry))
"""


class AuthTokenExpiryAndRevalidationTest(unittest.TestCase):
    def test_token_expiry_and_live_revalidation(self):
        temp_dir = tempfile.mkdtemp(prefix="jobhub_authtoken_")
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
        self.assertEqual(lines["STEP1_ROLE"], "manager")
        self.assertEqual(lines["STEP2_RESULT"], "None", "A deactivated account's token must stop working")
        self.assertEqual(lines["STEP2_TOKEN_ROWS"], "0", "The token row must be deleted once the account is inactive")
        self.assertEqual(
            lines["STEP3_ROLE"],
            "employee",
            "Restoring a token must use the LIVE role, not the role cached at login time",
        )
        self.assertEqual(
            lines["STEP4_RESULT"],
            "None",
            "A token issued far beyond the max age must be rejected even for an active, unchanged account",
        )


if __name__ == "__main__":
    unittest.main()
