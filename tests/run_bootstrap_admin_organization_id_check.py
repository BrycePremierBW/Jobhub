"""Regression test: a brand-new app_users row created after the one-time
organization_id backfill migration has already run (the bootstrap admin,
seeded by seed_app_users() during startup) must still get a real
organization_id of its own, not NULL (architecture decision #9,
multi-tenant scoping design Phase 2).

The backfill migration in apply_schema_migrations() only ever runs once
per database. seed_app_users() -- which creates the bootstrap admin --
runs on every startup, including the very first one, immediately after
that migration has already fired (and found no rows to backfill, since
app_users was still empty at that point). If seed_app_users() didn't set
organization_id itself, every fresh JobHub install's first admin account
would have organization_id permanently NULL.

pb_jobhub_app.py runs its full startup automatically at module import
time, so setting JOBHUB_BOOTSTRAP_ADMIN_USERNAME/PASSWORD before import
is enough to exercise the real bootstrap-admin-creation path. Runs as
its own fresh process, matching
tests/run_organization_schema_startup_check.py and
tests/run_app_users_organization_id_backfill_check.py, for the same
DATA_DIR-is-a-module-level-constant reason documented there.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="jobhub_bootstrap_admin_org_test_")
os.environ["JOBHUB_BOOTSTRAP_ADMIN_USERNAME"] = "orgtestadmin"
os.environ["JOBHUB_BOOTSTRAP_ADMIN_PASSWORD"] = "Sup3r-Str0ng-Bootstrap-Pw!"

import pb_jobhub_app as app  # noqa: E402  (env vars must be set first)

from jobhub.organization_schema_guard import get_organization_id, DEFAULT_ORGANIZATION_SLUG  # noqa: E402

default_org_id = get_organization_id(DEFAULT_ORGANIZATION_SLUG)
assert default_org_id is not None, "the default organisation must exist after startup"

bootstrap_admin = app.df_query(
    "SELECT organization_id FROM app_users WHERE username = 'orgtestadmin'"
)
assert not bootstrap_admin.empty, "the bootstrap admin must have been created"
assert int(bootstrap_admin.iloc[0]["organization_id"]) == default_org_id, (
    "the bootstrap admin is created after the one-time backfill migration has already run, "
    "so it must set its own organization_id rather than relying on that migration"
)

print("PASS: the bootstrap admin gets a real organization_id even though it's created after the one-time backfill migration.")
