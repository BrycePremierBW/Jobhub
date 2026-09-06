# Multi-Tenant Organisation Scoping — Design Document

**Status:** Design only. No data-table migration has been implemented from
this document. Do not begin implementation without re-reading the "Rollout
phasing" section and getting explicit sign-off on which phase to start.

**Architecture decision #9:** *"Multi-tenant organisation scoping is
required before onboarding a second external organisation. Design and
document the migration now. Do not perform a giant unsafe retrofit in one
PR."* This document is that design. It is intentionally a plan to execute
across several small, independently-revertable PRs — not a single
retrofit.

## 1. Current state (already in production)

JobHub already has a **tenant metadata foundation**, added ahead of this
document and currently live: `jobhub/organization_schema_guard.py`
(imported by `jobhub/xero_setup_guard.py`, exercised by
`tests/test_organization_schema_guard.py`). It creates three tables,
non-destructively, alongside the existing schema:

- `organizations` — one row per tenant (`organization_slug`, company
  details, `subscription_status`).
- `organization_settings` — per-org key/value settings.
- `organization_integrations` — per-org external integration credentials
  (currently used for Xero).

A single default row is seeded: `organization_slug = 'premier-brushworks'`.
**Crucially, `ensure_organization_schema()` only runs lazily when a user
opens the Xero setup page** (`jobhub/xero_setup_guard.py:108`) — it is not
called from core app startup, and **no other table in the schema has an
`organization_id` column yet.** Every business-data table (`jobs`,
`app_users`, `employees`, `products`, `builders_clients`,
`purchase_orders`, `estimate_working_sheets`, and ~70 others — see the
full table inventory in `JobHub-Autonomous-Progress.md`'s decision #10
notes) is implicitly single-tenant: every query in `pb_jobhub_app.py` and
`jobhub_enterprise.py` reads and writes across the whole table with no
tenant filter, because there has only ever been one tenant.

This document defines the phases needed to go from "tenant metadata
exists but nothing is scoped by it" to "a second organisation can be
onboarded with a hard data-isolation guarantee."

## 2. Goals and non-goals

**Goals**
- A second organisation's staff can use JobHub without ever being able to
  see, query, export, or mutate Premier Brushworks' data (or vice versa).
- Existing Premier Brushworks production data and behaviour is untouched
  until the org-scoping is actually enforced for a given table — no
  window where existing users see broken or empty data.
- Every phase is independently shippable, testable, and revertable.
- Works identically on the SQLite (local/dev) and PostgreSQL (Render
  production) backends this app already supports side-by-side.

**Non-goals (explicitly out of scope for this document)**
- Billing/subscription logic for multiple paying tenants.
- Per-organisation feature flagging or plan tiers.
- Migrating Palm Lakes data (decision #11 remains blocked and unrelated —
  that is a data-cleanup issue *within* the existing single tenant, not a
  multi-tenant boundary).
- A UI for self-service org signup. This document assumes a second
  organisation is onboarded by an administrator, not a public signup flow.

## 3. Why application-layer scoping, not database-native RLS

PostgreSQL supports Row-Level Security (RLS) policies, which would let the
database itself enforce `WHERE organization_id = current_setting(...)` on
every query automatically. **This is not viable here** because:

- JobHub runs the same SQL (via `sql_text()`'s `?` → `%s` translation)
  against SQLite in local dev, CI, and (per the architecture) potentially
  smaller self-hosted deployments. SQLite has no RLS equivalent.
- Adopting RLS would mean the isolation guarantee only exists on Postgres,
  silently regressing to "no isolation" in every SQLite-backed test and
  local-dev session — exactly the kind of gap that would let an isolation
  bug ship undetected.

Instead, isolation must be enforced **in the application layer**, the same
way this codebase already handles the Postgres/SQLite split for query
syntax (`sql_text()`) — one mechanism, portable across both backends, and
therefore testable against SQLite in CI with the same guarantees Postgres
gets in production.

## 4. The core mechanism: a scoped query helper, not 1000+ manual edits

`pb_jobhub_app.py` alone has hundreds of raw `df_query(...)`/`execute(...)`
call sites against organisation-owned tables. Manually adding
`AND organization_id = ?` to every one of them is exactly the "giant
unsafe retrofit" this decision explicitly forbids — it is not reviewable,
and a single missed call site is a cross-tenant data leak with no
compile-time or test-time signal.

Proposed mechanism instead:

1. **A single source of truth for "which org is this request for."**
   Add `organization_id INTEGER NOT NULL` to `app_users` (backfilled to
   the default org for all existing accounts — see Phase 2). On login,
   `st.session_state["user"]["organization_id"]` is set once and
   revalidated on every rerun by the *same* `_revalidate_session_user()`
   function added for decision #8 (`pb_jobhub_app.py`) — that function
   already re-reads `app_users` on every already-logged-in pass, so
   folding `organization_id` into that same read is a one-line addition,
   not a new mechanism.

2. **A registry of which tables are organisation-scoped**, and a thin
   wrapper that append-only rewrites a query to add the tenant filter,
   e.g. (illustrative, not final):
   ```python
   def org_scoped_query(sql: str, params: tuple = (), org_id: int | None = None) -> pd.DataFrame:
       org_id = org_id or current_organization_id()
       # Only rewrites queries against tables registered as org-scoped;
       # raises loudly if a scoped table is queried without going through
       # this helper, once a table is migrated (see Phase 4).
       ...
   ```
   The exact rewrite strategy (SQL string wrapping vs. requiring every
   scoped query to be written as `... WHERE organization_id = :org_id
   AND ...` and merely *validating* that clause is present) is an
   implementation-time decision, not a decision this document needs to
   pre-commit to. What **is** decided here: there must be one chokepoint,
   not per-call-site edits, and it must be enforced by a test that fails
   loudly (not silently) if a scoped table's query bypasses it.

3. **A CI-enforced coverage test**: once a table is migrated to
   org-scoped (Phase 4), a static-analysis test (grep/AST, same technique
   already used elsewhere in this codebase for dead-code proof) asserts
   every `df_query`/`execute` call referencing that table's name either
   goes through the scoped helper or appears on an explicit, reviewed
   allowlist (for genuinely cross-org admin tooling, if any is ever
   needed). This turns "did we miss a call site" from a manual audit into
   an automated gate, the same way `ruff --select F821,F823` already
   gates undefined names in this CI pipeline.

## 5. Rollout phasing

Each phase is its own PR, following the standard
REPRODUCE → FEATURE BRANCH → MINIMAL FIX → TESTS → CI → MERGE pipeline.
**No phase after Phase 1 should begin until the previous phase has been
running in production without incident.**

### Phase 1 — Tenant metadata (already done, live)
`organizations` / `organization_settings` / `organization_integrations`.
No action needed. Recommendation: move `ensure_organization_schema()` out
of the lazy Xero-only call site and into core startup schema bootstrap
(alongside `ensure_enterprise_schema()`), so the tables and the default
org row reliably exist regardless of whether anyone has opened Xero
setup. This is a trivial, additive, low-risk PR on its own and should be
done first, ahead of Phase 2.

### Phase 2 — Identity scoping
Add `organization_id INTEGER NOT NULL DEFAULT <default org id>` to
`app_users` (additive migration, same `ensure_column`/`ALTER TABLE ADD
COLUMN IF NOT EXISTS` pattern used throughout this codebase). Backfill
every existing row to the default org. Extend
`_revalidate_session_user()` (decision #8) to also read and refresh
`organization_id` into session state. Add `current_organization_id()` as
a small helper. **No business-data table is touched in this phase** — it
only establishes "who belongs to which org," which is a prerequisite for
every later phase and is safe to ship on its own since it changes no
query behaviour yet (there is still only one org, so nothing observable
changes for Premier Brushworks users).

### Phase 3 — Tag business-data tables (additive, nullable, no enforcement)
Add `organization_id INTEGER` (nullable at first) to the tables that
actually need tenant isolation. Backfill every existing row to the
default org's id in the same migration. Candidate table list (derived
from the schema inventory — confirm against the live schema at
implementation time, since new tables may have been added since this
document was written):

- Core: `jobs`, `builders_clients`, `employees`, `products`
- Estimating: `estimate_working_sheets`, `estimate_line_items`,
  `estimate_baselines`, `estimate_baseline_lines`, `estimating_rates`,
  `estimate_rate_register`
- Procurement: `purchase_orders`, `purchase_order_lines`,
  `supplier_invoices`, `supplier_invoice_lines`, `material_entries`,
  `material_order_requests`, `material_order_items`
- Scheduling/time: `staff_schedule`, `staff_requests`,
  `timesheet_entries`, `wage_entries`, `field_clock_entries`,
  `jobhub_crews`, `jobhub_crew_members`
- Job lifecycle: `job_budgets`, `job_stages`, `job_variations`,
  `invoice_claims`, `invoice_claim_items`, `job_documents`,
  `job_document_blobs`, `job_photos`, `job_comments`, `job_swms`,
  `job_swms_signatures`, `job_progress_snapshots`,
  `job_extra_daysheets`, `job_extra_daysheet_items`, `job_colour_schedules`
- `app_users` (organization_id added in Phase 2, not repeated here)

Explicitly **not** org-scoped (genuinely global/shared infrastructure,
not tenant data): `schema_migrations`, `app_error_events`,
`app_code_changes`, `app_learning_sources`, `backup_runs`. Decide
per-table at implementation time whether a given table belongs in this
list or the scoped list above — this document's list is a starting
inventory, not a final ruling.

Because `organization_id` is added nullable with a backfill and **no
query is changed yet**, this phase is purely additive — a column exists,
is populated, but nothing reads it. This is deliberately the safest
possible way to land ~25 schema migrations: they can be reviewed and
merged as pure schema changes with zero behavioural risk, well before any
query-isolation logic exists to depend on them.

### Phase 4 — Enforce isolation, one table (or tightly related table
group) at a time
For each table (or small related group, e.g. `purchase_orders` +
`purchase_order_lines` together, since they're always queried jointly):
route its reads/writes through the scoped-query mechanism from Section 4,
add the CI coverage test for that table, and change the column to
`NOT NULL` once every write path is confirmed to always supply it. This
is the phase where the actual "giant unsafe retrofit" risk lives, which
is exactly why it's broken into ~10-15 small PRs (one per table/group)
instead of one. Suggested order: start with tables that have the fewest
call sites and the lowest blast radius if isolation is briefly imperfect
(e.g. `builders_clients` before `jobs`, `jobs` before the high-traffic
`material_entries`/`purchase_orders`/`timesheet_entries`), so the
mechanism itself gets validated on low-stakes tables first.

### Phase 5 — Onboarding flow
Only after Phase 4 is complete for every table that needs it: build the
actual "create a new organisation" admin flow (new `organizations` row,
first admin user with that `organization_id`, seed any org-level default
settings). Until Phase 4 is complete, do not create a second
`organizations` row in production — doing so before enforcement exists
would let a second org's users see Premier Brushworks data, which is the
exact failure this document exists to prevent.

## 6. Testing strategy

Every Phase 4 PR must include, at minimum:

- An isolation regression test: seed two organisations, seed data for
  both, assert org A's session can never retrieve org B's rows through
  the newly-scoped query paths (mirroring the existing pattern in this
  codebase of extracting real query/function code and running it against
  a temp SQLite DB — see `tests/test_procurement_authoritative_job_costs.py`
  for the most recent example of this style).
- The CI coverage test described in Section 4, item 3, for that table.
- A check that existing single-org (Premier Brushworks) behaviour is
  byte-for-byte unchanged when only one organisation exists — the whole
  point of the backfill in Phase 3 is that a single-tenant deployment
  should never notice Phase 4 landing.

## 7. Rollback strategy

- Phases 1-3 are purely additive (new tables, new nullable/backfilled
  columns). Rollback is trivial: the column/table can be ignored or
  dropped without any data loss, since nothing depends on it yet.
- Phase 4 rollbacks (per table) mean reverting that table's queries back
  to unscoped reads — safe as long as a second organisation's data has
  not yet been created in that table (true until Phase 5 for that table
  actually runs), since an unscoped query on a single-tenant table
  returns the same rows either way.
- Phase 5 (creating a real second organisation) is the only phase that is
  hard to "undo" cleanly, which is exactly why it is sequenced last and
  gated on every other phase being complete and verified.

## 8. Open questions for the business (not engineering decisions)

- Does a second organisation need to share any data with Premier
  Brushworks (e.g. a shared product/supplier catalog), or is full
  isolation correct? This document assumes full isolation; if shared
  reference data is wanted, that needs its own design (e.g. a
  `organization_id IS NULL` convention for "global" catalog rows) rather
  than being retrofitted after Phase 4 ships.
- Will organisations ever need cross-org reporting (e.g. a franchise
  parent company reviewing multiple orgs)? If yes, that access pattern
  should be designed explicitly (a distinct "super-admin" role scoped
  across orgs) rather than left to accidentally fall out of how
  `has_permission()` currently works.
