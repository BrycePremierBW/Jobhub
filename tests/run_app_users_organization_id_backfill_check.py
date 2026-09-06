"""Regression test: an app_users row that already existed before the
organization_id column was introduced must be backfilled onto the
default organisation the first time this app version starts up against
that database (architecture decision #9, multi-tenant scoping design
Phase 2 -- see docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md, and the
one-time migration 20260906_app_users_organization_id_v1 in
apply_schema_migrations()).

pb_jobhub_app.py runs its full startup sequence automatically at module
import time (`initialise_jobhub_runtime(DATABASE_URL, DATA_DIR)` inside a
bare `try:` at module scope) -- so there is no way to import this module
against a fresh database and then separately drive individual startup
steps in a custom order; the only way to genuinely exercise "a database
that predates this migration" is to build that database's app_users
table by hand, with a real user row already in it, *before* importing
pb_jobhub_app at all. That reproduces exactly what upgrading a real
existing production database looks like.

This must run as its own fresh process (like
tests/run_organization_schema_startup_check.py,
tests/material_order_workflow_test.py and tests/run_stage_control_ci.py)
rather than as a pytest-collected function in the shared suite, for the
same DATA_DIR-is-a-module-level-constant reason documented in those
files.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = tempfile.mkdtemp(prefix="jobhub_org_id_backfill_test_")
os.environ["DATA_DIR"] = DATA_DIR

# Build the "existing production database" state by hand: app_users with
# its original (pre-decision-9) columns only, and one real user row in it
# -- before pb_jobhub_app ever touches this file.
db_path = os.path.join(DATA_DIR, "jobhub.db")
seed_conn = sqlite3.connect(db_path)
seed_conn.execute("""
    CREATE TABLE app_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        employee_id INTEGER,
        active INTEGER DEFAULT 1,
        notes TEXT
    )
""")
seed_conn.execute(
    "INSERT INTO app_users (username, password_hash, role, active) VALUES (?, ?, ?, ?)",
    ("pre_existing_user", "not-a-real-hash", "employee", 1),
)
seed_conn.commit()
seed_conn.close()

# Now import: this triggers the real, full startup sequence for the first
# time against the database built above.
import pb_jobhub_app as app  # noqa: E402  (DATA_DIR must be set first)

from jobhub.organization_schema_guard import get_organization_id, DEFAULT_ORGANIZATION_SLUG  # noqa: E402

default_org_id = get_organization_id(DEFAULT_ORGANIZATION_SLUG)
assert default_org_id is not None, "the default organisation must exist after startup"

result = app.df_query(
    "SELECT organization_id FROM app_users WHERE username = 'pre_existing_user'"
)
assert not result.empty, "the pre-existing user row must survive startup"
assert int(result.iloc[0]["organization_id"]) == default_org_id, (
    "an app_users row that already existed before organization_id was introduced "
    "must be backfilled onto the default organisation by the one-time migration"
)

print("PASS: a pre-existing app_users row is backfilled onto the default organisation on first startup.")
