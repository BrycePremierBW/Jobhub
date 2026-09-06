"""Regression test: JobHub's core startup bootstrap must create and seed
the organisation tenant-metadata schema, not just when someone happens to
open Xero setup (architecture decision #9, multi-tenant scoping design
Phase 1 -- see docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md).

Before this fix, `ensure_organization_schema()` was only ever called from
`jobhub/xero_setup_guard.py`, lazily, the first time a user opened the
Xero integration setup page. On a fresh deployment where nobody has done
that yet, the `organizations` table (and its seeded default
"premier-brushworks" row) simply would not exist -- any other code
relying on it existing would fail. This proves
`initialise_jobhub_runtime()` (JobHub's actual startup entrypoint, run
once per server process) now bootstraps this schema itself.

This must run as its own fresh process (like
tests/material_order_workflow_test.py and tests/run_stage_control_ci.py)
rather than as a pytest-collected function in the shared suite: DATA_DIR
is only read once, at pb_jobhub_app's module-import time
(`DATA_DIR = os.getenv("DATA_DIR", "/var/data")`), so once that module is
already imported by any other test in the same process, this test could
only ever observe whatever database an earlier test already initialised
-- including one where Xero setup was already exercised, which would
mask exactly the gap this test exists to catch.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="jobhub_org_bootstrap_test_")

import pb_jobhub_app as app  # noqa: E402  (DATA_DIR must be set first)

app.initialise_jobhub_runtime(app.DATABASE_URL, app.DATA_DIR)
df = app.df_query(
    "SELECT organization_slug, company_name, subscription_status FROM organizations"
)

assert not df.empty, (
    "initialise_jobhub_runtime() must bootstrap the organizations table on every "
    "fresh startup, not only when Xero setup happens to be opened first"
)
row = df.iloc[0]
assert row["organization_slug"] == "premier-brushworks"
assert row["company_name"] == "Premier Brushworks"
assert row["subscription_status"] == "Active"

print("PASS: startup bootstraps and seeds the default organisation without needing Xero setup opened first.")
