"""Regression test: every business-data table listed in
_ORGANIZATION_SCOPED_BUSINESS_TABLES gets a real organization_id column,
with existing (and newly inserted) rows backfilled onto the default
organisation -- architecture decision #9, multi-tenant scoping design
Phase 3 (see docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md).

Unlike Phase 2's app_users migration, this is deliberately NOT a one-time
schema_migrations-gated migration: several of these tables (jobhub_crews,
job_swms, material_order_requests, ...) are only created lazily by their
own guard module the first time that feature's page is opened, so they
may not exist yet on any given startup. ensure_business_data_organization_id_columns()
runs on every startup for exactly that reason -- to pick up any such
table as soon as it does exist, and to keep backfilling any row a normal
INSERT missed. This test proves both the "table already existed" and
"already has a column but a fresh row exists" cases.

Runs as its own fresh process (like the other run_*_check.py scripts in
this directory) rather than as a pytest-collected function in the shared
suite, since pb_jobhub_app.DATA_DIR is a module-level constant read once
at import time.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="jobhub_business_org_id_test_")

import pb_jobhub_app as app  # noqa: E402  (DATA_DIR must be set first)

from jobhub.organization_schema_guard import get_organization_id, DEFAULT_ORGANIZATION_SLUG  # noqa: E402

default_org_id = get_organization_id(DEFAULT_ORGANIZATION_SLUG)
assert default_org_id is not None, "the default organisation must exist after startup"

existing_count = 0
missing_count = 0
for table in app._ORGANIZATION_SCOPED_BUSINESS_TABLES:
    columns_df = app.df_query(f"PRAGMA table_info({table})")
    if columns_df.empty:
        # A guard-owned table that hasn't been lazily created yet on this
        # startup -- acceptable, it will be picked up on a later one.
        missing_count += 1
        continue
    existing_count += 1
    assert "organization_id" in list(columns_df["name"]), (
        f"{table} exists but has no organization_id column"
    )

assert existing_count > 30, (
    f"expected the large majority of the {len(app._ORGANIZATION_SCOPED_BUSINESS_TABLES)} "
    f"listed tables to already exist on a fresh startup; only {existing_count} did "
    "-- check whether core startup's schema-ensure calls changed"
)

# A row inserted into an org-scoped table with no organization_id (as any
# ordinary INSERT statement in this codebase still does today, since no
# query has been updated to set it yet -- that's Phase 4) must still get
# backfilled the next time this function runs, not just at first startup.
app.execute("INSERT INTO jobs (job_no, job_name) VALUES ('ORG_ID_CHECK_JOB', 'Org id check')")
app.ensure_business_data_organization_id_columns()
result = app.df_query("SELECT organization_id FROM jobs WHERE job_no = 'ORG_ID_CHECK_JOB'")
assert not result.empty
assert int(result.iloc[0]["organization_id"]) == default_org_id, (
    "a freshly inserted row with no organization_id must be backfilled onto the "
    "default organisation the next time this runs, not just once at startup"
)

print(
    f"PASS: organization_id exists on {existing_count}/{len(app._ORGANIZATION_SCOPED_BUSINESS_TABLES)} "
    "listed tables (the rest not yet lazily created), and new rows keep getting backfilled."
)
