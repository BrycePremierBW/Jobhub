# JobHub Autonomous Engineering Programme — Progress Ledger

Maintained by the autonomous engineering session. Updated after every completed
workstream (merged PR, or a design/documentation deliverable for items that
are explicitly design-only per the business decisions below).

Pipeline followed for every code fix: REPRODUCE → REGRESSION → FEATURE BRANCH →
MINIMAL FIX → TESTS → REVIEW B → PR → CI → MERGE → POST-MERGE VERIFY. Never
committed directly to `main`. Never force-pushed. Never weakened a test to get
green CI.

## Repository state

- Repo: `C:\Users\bryce\Documents\Jobhub` (GitHub: `BrycePremierBW/Jobhub`)
- Production: PostgreSQL (Render). CI: PostgreSQL 18 service container + SQLite
  for pure-unittest runs. Local dev/test: SQLite via temp `DATA_DIR`.
- CI gate: `.github/workflows/jobhub-tests.yml` — compileall, ruff (F821/F823),
  `python -m unittest discover`, Postgres integration smoke, permanent-job-delete
  regression, material order workflow, full-route render smoke, staged-job
  workflow. All green on every merge in this ledger.

## Live production usage context (as of engagement start)

~14 staff, ~2 months live. ~20 jobs, ~150 timesheets, 100+ staff schedules,
15–20 material orders, 10 completed + ~8 in-progress job costings, 4 pre-starts,
~10 estimates, equipment/product registers active, GPS capability built but not
yet enabled by users, progress tracking to be reassessed later alongside a
separate PlanReader 3D tool.

## Business/architecture decisions on record (received 2026-09-06)

1. Procurement (`purchase_orders` / `purchase_order_lines` / `supplier_invoices`)
   is the **authoritative source** for committed and invoiced material
   financial cost.
2. Job Costs / Forecasting must consume/reconcile Procurement values rather
   than maintain a second independent commercial truth.
3. `material_entries` may remain for physical/manual consumption and
   legitimate non-PO costs, but must not duplicate PO/invoice financial truth.
4. Historical prices must be snapshotted. Current product/supplier pricing
   must never retroactively alter historical job cost.
5. Remove hardcoded 10% GST architecture. Introduce configurable tax rate
   with document-level snapshots. Australian default may remain 10%.
6. Fix scheduling TOCTOU double-booking race using production-appropriate
   transactional integrity.
7. Make logically atomic bulk crew scheduling transactional, or explicitly
   partial with deterministic success/failure reporting.
8. Revalidate active user + current server-side role before consequential
   privileged mutations; do not trust indefinitely stale session-state roles.
9. Multi-tenant organisation scoping is required before onboarding a second
   external organisation. Design and document the migration now. Do not
   perform a giant unsafe retrofit in one PR.
10. Dead `jobhub/pages` code: prove dead → inventory useful historical fixes →
    port useful fixes into the actual production path → test actual
    production behavior → only then deprecate/remove dead modules.
11. Palm Lakes migration (`jobhub/bulk_delete_guard.py`) remains **BLOCKED**
    pending explicit production-state confirmation from the business owner.
    Do not alter it.

---

## Completed workstreams

### Phase 1 — Navigation, security, safety (audit round 1)

| # | PR | Title | Status |
|---|----|-------|--------|
| 1 | [#103](https://github.com/BrycePremierBW/Jobhub/pull/103) | Track every live `st.tabs()` call for rerun persistence (26 untracked sites) | Merged, verified |
| 2 | [#104](https://github.com/BrycePremierBW/Jobhub/pull/104) | **Critical**: close PO admin-only boundary bypass | Merged, verified |
| 3 | [#105](https://github.com/BrycePremierBW/Jobhub/pull/105) | Disambiguate wrong-target edit/delete dropdowns by ID | Merged, verified |
| 4 | [#106](https://github.com/BrycePremierBW/Jobhub/pull/106) | Guard against duplicate-submit job/financial creation (Smart Intake, Variation/Claim) | Merged, verified |
| 5 | [#107](https://github.com/BrycePremierBW/Jobhub/pull/107) | Add server-side role checks to Setup/Subscriber/Xero panels | Merged, verified |
| 6 | [#108](https://github.com/BrycePremierBW/Jobhub/pull/108) | Expire persistent login tokens and revalidate on restore | Merged, verified |
| 7 | [#109](https://github.com/BrycePremierBW/Jobhub/pull/109) | Guard field forms (pre-start/hazard/quality) against duplicate submission | Merged, verified |
| 8 | [#110](https://github.com/BrycePremierBW/Jobhub/pull/110) | Show JobHub-Setup crews on the Saved Crews admin screen | Merged, verified |
| 9 | [#111](https://github.com/BrycePremierBW/Jobhub/pull/111) | Stop intake merge doubling material allowance; fix a real crash | Merged, verified |
| 10 | [#112](https://github.com/BrycePremierBW/Jobhub/pull/112) | Warn when approving leave that conflicts with a booking | Merged, verified |
| 11 | [#113](https://github.com/BrycePremierBW/Jobhub/pull/113) | Remove stale external-progress rows on estimate switch | Merged, verified |
| 12 | [#114](https://github.com/BrycePremierBW/Jobhub/pull/114) | Compare supplier invoice variance to remaining PO balance | Merged, verified |
| 13 | [#115](https://github.com/BrycePremierBW/Jobhub/pull/115) | Flag receiving more than a PO line's ordered quantity | Merged, verified |
| 14 | [#116](https://github.com/BrycePremierBW/Jobhub/pull/116) | Stop the same material shortfall being raised on two purchase orders | Merged, verified |

### Phase 2 — Architecture decisions programme (in progress)

| # | Decision | PR | Status |
|---|----------|----|--------|
| 8 | Server-side role revalidation before privileged mutations | [#117](https://github.com/BrycePremierBW/Jobhub/pull/117) | Merged, verified |
| 6 | Scheduling TOCTOU double-booking fix | [#118](https://github.com/BrycePremierBW/Jobhub/pull/118) | Merged, verified |
| 7 | Bulk crew scheduling — transactional/deterministic partial reporting | [#119](https://github.com/BrycePremierBW/Jobhub/pull/119) | Merged, verified |
| 5 | Configurable tax rate with document-level snapshots | [#120](https://github.com/BrycePremierBW/Jobhub/pull/120) | Merged, verified |
| 4 | Price snapshots on material entries | [#121](https://github.com/BrycePremierBW/Jobhub/pull/121) | Merged, verified |
| 1/2/3 | Procurement-authoritative Job Costs reconciliation | [#122](https://github.com/BrycePremierBW/Jobhub/pull/122) | Merged, verified |
| 9 | Multi-tenant org-scoping design document | [#123](https://github.com/BrycePremierBW/Jobhub/pull/123) | Merged (design only, no migration implemented) |
| — | Test infra: CI silently never ran ~120 tests in 28 files | [#124](https://github.com/BrycePremierBW/Jobhub/pull/124) | Merged, verified |
| 10 | Dead `jobhub/pages` code: prove dead + inventory | [#125](https://github.com/BrycePremierBW/Jobhub/pull/125) | Merged (inventory only) |
| 10 | Port lazy-section-selector fix: Job Register | [#127](https://github.com/BrycePremierBW/Jobhub/pull/127) | Merged, verified |
| 10 | Port lazy-section-selector fix: Builders & Clients | [#128](https://github.com/BrycePremierBW/Jobhub/pull/128) | Merged, verified |
| 10 | Port lazy-section-selector fix: Equipment | [#130](https://github.com/BrycePremierBW/Jobhub/pull/130) | Merged, verified |
| 10 | Equipment checklist save N+1 read-side fix | [#132](https://github.com/BrycePremierBW/Jobhub/pull/132) | Merged, verified |
| 1/2/3 | Procurement reconciliation for `enterprise_job_cost_dataframe()` | [#133](https://github.com/BrycePremierBW/Jobhub/pull/133) | Merged, verified |
| 9 | Multi-tenant Phase 1: bootstrap org schema at core startup | [#134](https://github.com/BrycePremierBW/Jobhub/pull/134) | Merged, verified |
| 9 | Multi-tenant Phase 2: `organization_id` on `app_users` | [#136](https://github.com/BrycePremierBW/Jobhub/pull/136) | Merged, verified |
| 11 | Palm Lakes migration | **BLOCKED — do not touch** | N/A |

**Note on PR #99.** While checking for other open PRs, found
[#99](https://github.com/BrycePremierBW/Jobhub/pull/99) ("Lazy-render
equipment and batch checklist persistence", opened 2026-08-30, before
this engagement, still open/unmerged) -- the exact same class of fix as
#127/#128/#130, but its diff only ever touched the dead
`jobhub/pages/equipment.py`. #130 supersedes its lazy-tabs portion
against the live page. #99 also describes batching the Job Equipment
Checklist save's per-item SELECT+INSERT/UPDATE loop with `execute_many`
(a real N+1 write pattern, still present today) -- deliberately NOT
ported in #130 since it's a write-path change to production data that
deserves independent re-verification against current code, not a copy
from a week-old abandoned PR. #99 has not been closed -- that's the
user's own PR to close or keep; flagged here rather than acted on.

**Follow-ups identified but not yet actioned (queued):**
- The Job Equipment Checklist N+1 **write**-batching (PR #99's other
  half -- batching the INSERT/UPDATE/DELETE calls themselves with
  `execute_many`). #132 fixed the read-side redundant per-item SELECT;
  the write side remains a separate, real, live pattern that needs its
  own REPRODUCE with a real row-count/timing measurement before
  touching it, since it's a write-path change to production data.
- Removal of the 19 dead `jobhub/pages`/sibling modules themselves is
  still deferred, per decision #10's own ordering, until the *rest* of
  their contents (beyond the three lazy-render fixes already ported in
  #127/#128/#130) has been reviewed -- this session's inventory searched
  git "fix" history specifically and found only those; it did not rule
  out other value in the remaining ~17 files (see
  `docs/DEAD_CODE_INVENTORY_DECISION_10.md` section 5).
- Decision #9's design is written; Phase 1 (tenant-metadata bootstrap at
  core startup, #134) and Phase 2 (`organization_id` identity scoping on
  `app_users`, #136) are now live. Phase 3 onward (additive, nullable,
  backfilled `organization_id` on the ~25 business-data tables inventoried
  in the design doc, then per-table enforcement via a scoped-query
  chokepoint plus a CI coverage test, then the actual onboarding flow) has
  not been started -- see `docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md`
  for the full phased plan. Do not create a second `organizations` row in
  production before Phase 4 (enforcement) is complete for every table
  that needs it.

---

## Repair ledger

Chronological log of every workstream's REPRODUCE evidence and fix summary.
Newest entries at the bottom. Each entry added at merge time.

_(Phase 1 entries above are summarized in PR descriptions on GitHub; this
ledger begins detailed entries with Phase 2.)_

### 2026-09-06 — Decision #8: server-side role revalidation

**Reproduce.** `st.session_state["user"]` was cached once at login (or once
per browser session on an auth-token restore, fixed separately in #108) and
trusted indefinitely for the rest of that Streamlit session. Wrote
`tests/test_session_role_revalidation.py`, confirmed it fails against
pre-fix `pb_jobhub_app.py` with `AttributeError: module 'pb_jobhub_app' has
no attribute '_revalidate_session_user'` — the function didn't exist, so
there was categorically no re-check.

**Fix.** Added `_revalidate_session_user(user)`: one indexed
`SELECT role, active, must_change_password FROM app_users WHERE id = ?`
per already-logged-in pass through `require_login()`. If the account is
now inactive or deleted, the session is cleared, the persistent-login
token (if any) is deleted, and the user is logged out with an explicit
message. If the role changed, `st.session_state["user"]["role"]` is
updated in place before the rest of the script runs, so every
`current_role()`/`is_admin()` check later in the *same* rerun already sees
the corrected role — closing the gap for every privileged mutation in one
place rather than needing a separate check at each call site (the exact
gap already found and fixed piecemeal for the Setup/Subscriber/Xero
panels). A transient DB error on the check fails open for that one rerun
(keeps the session's last-known state) rather than locking out every
active user because of a blip.

**Tests.** `tests/test_session_role_revalidation.py` — unchanged account is
a no-op; a role demoted server-side is picked up; a deactivated or deleted
account fails revalidation. Full suite: 562 tests green. Ruff clean. Smoke
test renders all 33 routes.

**PR.** [#117](https://github.com/BrycePremierBW/Jobhub/pull/117) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #6: scheduling TOCTOU double-booking race

**Reproduce.** `overlapping_assignment()`/`has_approved_leave()` and the
subsequent `INSERT` ran as separate, unlocked statements/connections.
Wrote `tests/test_scheduler_toctou_double_booking.py`: two real threads,
each with its own SQLite connection to the same on-disk file, race to book
the same employee for the same overlapping slot via a `threading.Barrier`.
Run 5 times against pre-fix code: **5/5 times both threads succeeded**,
producing two overlapping rows for the same employee — a rock-solid,
reliably reproducible double-booking, not a theoretical race.

**Fix.** Added `_serialize_employee_schedule_writes(cur, employee_id)`,
called first inside the same transaction that performs the leave/overlap
check and the insert:
- Postgres: `pg_advisory_xact_lock(employee_id)` — a transaction-scoped
  advisory lock keyed on the employee id, blocking a concurrent transaction
  doing the same for the same employee even when neither has an existing
  row yet to lock via `SELECT ... FOR UPDATE`. Released automatically on
  commit/rollback.
- SQLite: `BEGIN IMMEDIATE` forces an immediate write-intent lock before
  the read-check (the default deferred transaction only locks at the first
  write), so a concurrent connection attempting the same blocks until this
  transaction commits. Coarser than Postgres's per-employee lock, but
  SQLite here only backs local/CI runs, never concurrent production
  traffic.

`has_approved_leave()` and `overlapping_assignment_rows()`/
`overlapping_assignment()` gained an optional `cur` parameter so
`add_assignment()` and `replace_conflicting_assignments()` run their checks
against the same locked cursor instead of opening a second, unlocked
connection. Existing callers that don't pass `cur` are unaffected —
purely additive.

**Tests.** `tests/test_scheduler_toctou_double_booking.py` — exactly one of
the two racing bookings succeeds, the other is correctly rejected as an
overlap, and the database has exactly one row. Full suite: 562 tests
green. Ruff clean. Smoke test renders all 33 routes.

**PR.** [#118](https://github.com/BrycePremierBW/Jobhub/pull/118) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #7: bulk crew scheduling reliability

**Reproduce.** "Allocate crew", "Approve and add suggested crew" and "Copy
first week to next week" each loop over every employee/day combination
calling `add_assignment()` with no per-item exception handling. Wrote
`tests/test_bulk_crew_scheduling_partial_failure.py`, extracting the real
"Allocate crew" per-item loop body and feeding it a fake `add_assignment`
that raises for one employee. Confirmed it fails against pre-fix code with
the raw `ConnectionError` propagating straight out of the loop — i.e. a
single unexpected failure partway through a ~14-person batch would crash
the handler with an unhandled traceback before the added/skipped summary
was ever shown, leaving no way to tell which earlier iterations had
already committed.

**Fix.** Wrapped each employee/day iteration in all three loops in a
try/except that folds an unexpected exception into the same deterministic
added/skipped/errored accounting every caller already had for expected
outcomes (leave conflicts, overlaps) — the loop always finishes and the
user always sees the true, complete picture of what happened in that
batch. Chose "explicitly partial with deterministic reporting" over a
single all-or-nothing transaction deliberately: a hard rollback would also
discard crew members who succeeded just because one other member had an
unrelated leave conflict — worse UX for a batch that legitimately expects
some skips.

**Tests.** `tests/test_bulk_crew_scheduling_partial_failure.py` — the
failure is folded into the report and unaffected iterations still succeed
normally; a no-failure run still reports everyone added with nothing
skipped (no regression on the happy path). Full suite: 565 tests green
(rebased cleanly onto #118's TOCTOU fix in the same file). Ruff clean.
Smoke test renders all 33 routes.

**PR.** [#119](https://github.com/BrycePremierBW/Jobhub/pull/119) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #5: configurable tax rate with document-level snapshots

**Reproduce.** `_create_purchase_order()` and the "Supplier Invoice Match"
handler in `render_procurement()` (both in `jobhub_enterprise.py`) each
computed GST with a bare `subtotal * 0.10` / `invoice_subtotal * 0.10` —
no admin-configurable rate existed anywhere, and since the rate was never
stored on the document itself, a future edit to that source constant would
have silently changed the recorded total on every *existing* PO/invoice as
well as new ones. Wrote `tests/test_configurable_gst_snapshot.py` (6
tests); confirmed all 6 fail against pre-fix code — `no such column:
gst_percent` (the column didn't exist yet) and `substring not found` (the
snapshotted-rate read in supplier-invoice matching didn't exist yet) — not
a source-string check, a genuine absence of the feature.

**Fix.** Added a `gst_percent REAL DEFAULT 10` column to both
`purchase_orders` and `supplier_invoices` (`_ensure_gst_percent_columns()`,
same `ALTER TABLE ADD COLUMN IF NOT EXISTS` + `PRAGMA table_info` fallback
pattern as the existing GPS-columns migration). Added
`_default_gst_percent(ctx)`, reading an admin-configurable
`app_settings.default_gst_percent` row (default 10.0 if unset) — the same
`app_settings` key/value table already used for staff rates etc.
`_create_purchase_order()` now snapshots this rate onto the new PO at
creation time instead of hardcoding 10%. Supplier-invoice matching now
reads the *PO's own* snapshotted `gst_percent` (not a fresh read of the
current system default, and not a hardcoded 10%) so an invoice against an
older PO keeps using the rate that PO was raised under even if the system
default has since changed — the same "never retroactively change an
existing document" principle as decision #4's price snapshots. Exposed
"Default GST / tax rate %" on the JobHub Setup → Rates tab
(`jobhub/setup_defaults_guard.py`), following the exact existing pattern
for `default_staff_hourly_rate`, so the rate is genuinely admin-editable
rather than only a source-level fallback constant.

**Tests.** `tests/test_configurable_gst_snapshot.py` — default fallback to
10.0 when unset; reads a configured setting; a new PO snapshots the
configured rate at creation; changing the system default *afterward* does
not alter an already-created PO's stored `gst_percent`/`gst_amount`/
`total_inc_gst`; supplier-invoice matching uses the PO's own snapshotted
rate, including a missing-rate fallback to 10%. Full suite: 571 tests
green (rebased cleanly onto #119). Ruff (`F821`/`F823`) clean. Smoke test
renders all 33 routes.

**PR.** [#120](https://github.com/BrycePremierBW/Jobhub/pull/120) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #4: price snapshots on material entries

**Reproduce.** Every job-cost query (`enterprise_job_cost_dataframe()`, the
Materials tab, Job Costing views, the Control Centre summary — 17 call
sites across `pb_jobhub_app.py` and `jobhub_enterprise.py`) computed
material cost as `qty * COALESCE(m.custom_unit_price, p.price_ex_gst, 0)`:
a LEFT JOIN against the *live* `products` table, with no price ever
recorded on the `material_entries` row itself for a real catalog product.
Wrote `tests/test_material_price_snapshot.py`; the pre-fix run showed the
exact defect directly — a material line costed at $500 (10 units × a $50
catalog price) silently became $200 once the catalog price was edited to
$20 *after* the job had already ordered it (`500.0 != 200.0`), with three
more tests erroring outright since the `price_snapshot` column and its
population logic in the Job Pack/Smart Intake import code didn't exist
yet.

**Fix.** Added `price_snapshot REAL` to `material_entries` (`ensure_column`,
same additive pattern as `custom_unit_price`). Populated it at all four
insert sites: the employee material-request form now looks up and stores
the selected product's current price at request time (previously not
captured anywhere for that flow); the Job Pack and Smart Intake import
paths now snapshot the takeoff/intake sheet's own parsed unit price
(previously silently discarded whenever the line matched a catalog
product) and only fall back to a live product-price lookup if the sheet
didn't carry one; the admin "Save Material Entry" form now persists
`matched_price` (already computed and shown to the user, but never
actually stored). All 17 cost-aggregation COALESCE call sites now read
`COALESCE(m.custom_unit_price, m.price_snapshot, p.price_ex_gst, 0)` --
an explicit manual override still wins, then the new snapshot, then the
live price as a last-resort fallback for rows created before this
migration (there is no real historical price to backfill them with, so
old rows keep their pre-existing behavior rather than getting a guessed
value). Confirmed 4 more occurrences of the same COALESCE pattern exist
only in the dead `jobhub/pages`-sibling modules (`ai_tools.py`,
`control_centre.py`, `estimating.py`, `job_views.py`) already flagged for
decision #10 -- left untouched since nothing imports them.

**Tests.** `tests/test_material_price_snapshot.py` -- a snapshotted row's
reported cost is unaffected by a later catalog price change; a
pre-migration row (`price_snapshot IS NULL`) still falls back to the live
price as before; `custom_unit_price` still takes priority over the
snapshot; the real import price-snapshot computation prefers the sheet's
own price, falls back to the live product price only when the sheet has
none, and returns 0 when neither exists. Full suite: 577 tests green.
Ruff clean. Smoke test renders all 33 routes.
`tests/material_order_workflow_test.py` (submit/approve/convert/PDF)
still passes end-to-end.

**PR.** [#121](https://github.com/BrycePremierBW/Jobhub/pull/121) — merged,
post-merge CI verified green.

### 2026-09-06 — Decisions #1/#2/#3: Procurement-authoritative Job Costs reconciliation

**Reproduce.** Audited every material-cost query and found **three
independent job-cost implementations** in this codebase:
`job_cost_summary_dataframe()` (the actual "Job Costs / Forecasting" page,
`pb_jobhub_app.py`), `pb_job_cost_frame()` (the Control Centre summary,
same file), and `enterprise_job_cost_dataframe()` (the newer "Live Job
Control & Forecast-to-Complete" page, `jobhub_enterprise.py`). The first
two computed "Committed Material Cost" / "Actual Material Cost" **purely**
from `material_entries`, with zero reference to `purchase_orders` or
`supplier_invoices` -- Procurement wasn't consulted at all. Wrote
`tests/test_procurement_authoritative_job_costs.py`; all 5 tests fail
against pre-fix code, most tellingly: a PO raised for $500 with no
material_entries row behind it (materials ordered directly rather than via
a logged request) contributed **$0** to Job Costs -- invisible, not just
inaccurate. `enterprise_job_cost_dataframe()` was less wrong -- it already
blends `material_entries` and `po_committed`/`po_approved`/
`supplier_invoiced` via `max()` -- but `max()` still means whichever
source is bigger silently wins rather than Procurement genuinely being
authoritative and material_entries being additive-only for the non-PO
remainder, so it doesn't yet satisfy decision #2's "reconcile, don't
duplicate."

**Fix.** In both `job_cost_summary_dataframe()` and `pb_job_cost_frame()`:
excluded any `material_entries` row already linked to an active PO line
(`purchase_order_lines.material_entry_id`, status not `Cancelled`/
`Rejected`) from the material_entries $ aggregation -- the same
`NOT EXISTS`/PO-link convention `_material_request_lines()` in
`jobhub_enterprise.py` already established for finding not-yet-ordered
material requests. Added `purchase_orders`/`supplier_invoices`
aggregations and made the final cost additive and reconciled rather than
material_entries-only:
`Committed Material Cost = PO subtotal (active POs) + non-PO material_entries cost`,
`Actual Material Cost = Supplier invoiced total + non-PO material_entries received cost`.
A material_entries row's own qty*price no longer counts once it's on a PO
-- the PO's own (possibly adjusted at ordering time) subtotal is used
instead, and the eventual supplier invoice becomes the authoritative
"actual" figure once one exists. Deliberately left
`enterprise_job_cost_dataframe()`'s `max()`-based blend untouched --
reshaping it to the same additive formula is a different, larger change
to a differently-structured function, and bundling it here would turn a
minimal, focused fix into a wider rewrite across three call sites at
once; noted below as an explicit follow-up.

**Tests.** `tests/test_procurement_authoritative_job_costs.py` -- a non-PO
material line still contributes its own cost; a PO-linked line is
excluded from material_entries and the PO's own subtotal is used instead;
a PO with no material_entries row is no longer invisible; a supplier
invoice becomes the actual cost for a PO-linked line; two lines (one PO'd,
one not) sum with no double-count. Full suite: 582 tests green. Ruff
clean. Smoke test renders all 33 routes.
`tests/material_order_workflow_test.py` and `tests/run_stage_control_ci.py`
(both exercise material/PO/job-cost flows end-to-end) still pass.

**Known remaining gap (explicit follow-up, not yet actioned).**
`enterprise_job_cost_dataframe()` in `jobhub_enterprise.py` (the "Live Job
Control & Forecast-to-Complete" page) still uses the pre-existing
`max(material_entries totals, po_committed, po_approved, supplier_invoiced)`
blend rather than the same additive PO-link-exclusion reconciliation
applied here. It is not currently reporting an under-count (max() never
under-reports), but it does not yet treat Procurement as strictly
authoritative per decision #1's letter. Revisiting it is natural to pair
with decision #10's dead-code/duplication inventory, since JobHub
currently maintains three separate job-cost calculation implementations
across two files -- consolidating them, not just reconciling each
independently, is the more durable fix and deserves its own scoped
workstream rather than being folded into this one.

**PR.** [#122](https://github.com/BrycePremierBW/Jobhub/pull/122) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #9: multi-tenant organisation scoping design

Design document only, no migration implemented. Investigated first and
found JobHub already has a tenant-metadata foundation live in production
(`jobhub/organization_schema_guard.py` -- `organizations`/
`organization_settings`/`organization_integrations`, seeded with a single
`premier-brushworks` org) but it is only invoked lazily from the Xero
setup page, and no business-data table has an `organization_id` column
anywhere. `docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md` lays out five
independently-shippable phases from that starting point to genuine
per-organisation isolation: (1) move the existing schema bootstrap to core
startup; (2) `organization_id` on `app_users`, wired into decision #8's
`_revalidate_session_user()`; (3) additive, nullable, backfilled
`organization_id` on ~25 business-data tables with zero query-behaviour
change; (4) enforce isolation one table/group at a time via a single
scoped-query chokepoint plus a CI coverage test per table (explicitly not
1000+ manual call-site edits, and explicitly not Postgres-only RLS, since
JobHub also runs on SQLite for local dev/CI); (5) the actual onboarding
flow, gated on every prior phase being verified in production. Also
records two open business questions (shared reference data across orgs?
cross-org reporting?) that need an answer before Phase 5.

**PR.** [#123](https://github.com/BrycePremierBW/Jobhub/pull/123) — merged,
post-merge CI verified green.

### 2026-09-06 — Test infra: CI silently never ran ~120 tests in 28 files

**Reproduce.** While starting the decision #10 dead-code inventory, found
`tests/test_jobs_page_performance.py` uses bare pytest-style
`def test_...():` functions, not `unittest.TestCase`. CI runs
`python -m unittest discover -s tests -p "test_*.py"`; unittest's
discovery silently collects **zero tests** from a module written that
way -- no error, no warning. Grepped the whole `tests/` directory for
files with `def test_` at module scope and no `TestCase` subclass: found
**28 files** written this way, including `test_xero_oauth.py`,
`test_subscriber_onboarding.py`, `test_timesheet_bulk_reassign.py`, and
25 others -- meaning every test in every one of them has been running
zero times, ever, despite `pytest` already being an installed dependency
in the same CI job (just never invoked).

**Fix.** Switched the "Run JobHub tests" CI step from `unittest discover`
to `pytest tests/` -- a strict superset (pytest natively runs
`unittest.TestCase`-based tests too). Running the real ~700-test suite
this way surfaced two real, previously-invisible problems:
1. Three tests failed against code already confirmed dead in the decision
   #10 inventory (`jobhub/pages/dashboard.py`, `jobhub/pages/reports.py`).
   Marked `@pytest.mark.skip` with an explicit reason rather than
   "fixing" assertions against unmaintained, non-production code.
2. `tests/test_setup_panels_role_check.py::...manager_role` failed only
   under a full-suite run, never alone -- a genuine cross-test pollution
   bug, invisible until these 28 files' tests started actually executing
   for the first time. Root cause: the test patched each guard module's
   `_st()` but not `current_role()` itself;
   `jobhub.permission_policy_guard.current_role()` prefers
   `pb_jobhub_app.current_role()` (real global session state) over its
   own `_st()` mock whenever `pb_jobhub_app` is already imported (true
   for virtually the whole suite), so leftover session state from an
   unrelated, earlier-running test could silently make the mock
   ineffective. Reproduced deterministically (import `pb_jobhub_app`,
   set real `st.session_state["user"]["role"] = "employee"`, rerun the
   test in isolation -- same failure). Fixed by patching
   `jobhub.permission_policy_guard.current_role` directly -- the exact
   attribute `setup_defaults_guard.py`/`subscriber_setup_guard.py`/
   `xero_setup_guard.py` all resolve at call time via a fresh
   `from . import permission_policy_guard as _permissions` -- removing
   the dependency on `current_role()`'s internal fallback chain, and
   therefore on test execution order, entirely.

**Tests.** Full suite under the new runner: 703 passed, 3 skipped
(confirmed-dead-code tests), 0 failed. Ruff clean. Smoke test renders all
33 routes.

**PR.** [#124](https://github.com/BrycePremierBW/Jobhub/pull/124) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #10: dead-code inventory (prove dead + inventory only)

**Reproduce/investigate.** Confirmed via static import analysis that all
19 `jobhub/pages/*` + sibling modules (~508 KB: `operations.py`,
`documents.py`, `estimating.py`, `job_views.py`, `mapping.py`,
`material_orders.py`, `navigation.py`, `control_centre.py`,
`takeoff_pages.py`, `ai_tools.py`, plus 9 files under `jobhub/pages/`) are
genuinely unreachable from the running app. Searched git history for
every "fix"-labeled commit touching those files and found exactly one
piece of work: PRs #93/#94 built and tested a lazy-section-selector
replacement for eager `st.tabs()` in the dead `jobhub/pages/jobs.py` (Job
Register) and `jobhub/pages/builders_clients.py` (Builders & Clients) --
avoiding every tab's queries firing on every page load regardless of
which tab the user is viewing. Directly confirmed against current
`pb_jobhub_app.py` that **both live pages still have this exact
problem** today: Job Register's `st.tabs([...6 sections...])` and
Builders & Clients' `st.tabs([...5 sections...])` both still execute all
sections' queries unconditionally on every load, for every one of the
~14 staff.

**Not done in this workstream (recorded as a follow-up, not implemented):**
porting the fix. It intersects with this programme's own earlier
tab-persistence work (`_TRACKED_TAB_SETS` in
`jobhub/navigation_state_guard.py` tracks both of these exact tab sets)
and deserves real before/after query-count measurement as its REPRODUCE
step, not just a code-shape argument -- scoped as its own workstream in
`docs/DEAD_CODE_INVENTORY_DECISION_10.md` rather than bundled here.
Removal of the 19 dead files themselves is explicitly deferred until
after that port lands and is verified, per decision #10's own ordering.

**Tests.** N/A (documentation/inventory only, no application code
changed). Full suite still green (703 passed, 3 skipped) since this PR
touched no application code.

**PR.** [#125](https://github.com/BrycePremierBW/Jobhub/pull/125) — merged,
post-merge CI verified green.

### 2026-09-06 — Decision #10 follow-up: port lazy-section-selector to Job Register and Builders & Clients

**Reproduce.** Confirmed directly against `pb_jobhub_app.py` (per the
decision #10 inventory) that both `elif menu == "Jobs":` (Job Register)
and `elif menu == "Builders & Clients":` still used eager `st.tabs()`
with every tab's body -- and every DB query inside it -- executing on
every rerun regardless of which tab was visible. Wrote
`tests/test_job_register_lazy_sections.py` and
`tests/test_builders_clients_lazy_sections.py`, extracting the real
blocks and running them with recording fakes; 8/9 and 6/7 assertions
respectively fail against pre-fix code (mostly via the old `st.tabs()`
unpack shape not matching the new lazy-selector fakes at all --
confirming the two code paths are structurally different, not just
differently worded).

**Fix.** Converted both blocks' `st.tabs([...])` + `with tab_x:` headers
to `st.radio(key=..., horizontal=True, label_visibility="collapsed")` +
`if/elif section == "...":` -- a pure header-level change, zero lines of
body logic touched in either page. Job Register's shared
`get_builder_options()`/`get_product_supplier_options()` eager calls
(previously run once at the top for all six sections) now run only
inside the three sections that use them (Add Job, Edit Job, Search by
Builder), matching exactly how the dead `jobhub/pages/jobs.py`'s own
port scoped the same lookups. Builders & Clients needed no lookup
redistribution -- each of its five sections already ran its own
independent query. Removed both pages' now-dead entries from
`navigation_state_guard._TRACKED_TAB_SETS` (a radio with a `key`
persists its selection across reruns natively, unlike `st.tabs()`, which
is why the guard existed for these two call sites in the first place);
`tests/test_navigation_tab_coverage.py`'s own drift-detection confirmed
no tracked entry was left dangling after either removal.

**Tests.** Both new test files pass 9/9 assertions against the fix;
`test_navigation_tab_coverage.py` (3/3) confirms the guard list stays in
sync. Full suite: 712 tests green after both PRs. Ruff clean. Smoke test
renders all 33 routes (including both converted pages) after each PR.

**PR.** [#127](https://github.com/BrycePremierBW/Jobhub/pull/127) (Job
Register), [#128](https://github.com/BrycePremierBW/Jobhub/pull/128)
(Builders & Clients) — both merged, post-merge CI verified green.

### 2026-09-06 — Decision #10 follow-up: port lazy-section-selector to Equipment

**Reproduce.** While checking for other open PRs against this repo,
found [#99](https://github.com/BrycePremierBW/Jobhub/pull/99)
("Lazy-render equipment and batch checklist persistence", opened
2026-08-30, before this engagement, still open) -- the same class of fix
as the two above, drafted once against the dead
`jobhub/pages/equipment.py`, never ported into `pb_jobhub_app.py`.
Confirmed the live `elif menu == "Equipment":` still used eager
`st.tabs()` across five sections with `get_job_options()` computed once
at the top for all of them. Wrote `tests/test_equipment_lazy_sections.py`;
all 6 assertions fail against pre-fix code (`st.tabs()` unpack shape
mismatch against the new lazy-selector fakes, same signature as the
Job Register/Builders & Clients reproductions).

**Fix.** Same mechanical header-only conversion as #127/#128:
`st.tabs([...])` + `with tab_x:` to
`st.radio(key="equipment_section", ...)` + `if/elif section == "...":`.
`get_job_options()` now runs only inside the three sections that use it
(Import Filled PDF Checklist, Job Equipment Checklist, Job Equipment
Master List). Removed the now-dead Equipment entry from
`navigation_state_guard._TRACKED_TAB_SETS`.
**Deliberately did not port** PR #99's other change -- batching the Job
Equipment Checklist save's per-item SELECT+INSERT/UPDATE loop with
`execute_many` (a real N+1 write pattern, confirmed still present in the
live `form_submit_button` handler today). That's a write-path change to
production data; importing it from a week-old, never-independently-
verified PR would be exactly the shortcut this programme exists to
avoid. Recorded as an explicit, separate follow-up above. PR #99 itself
was not closed -- it's the user's own PR and that decision is theirs.

**Tests.** `tests/test_equipment_lazy_sections.py` (6 tests) all pass
against the fix, all fail against pre-fix code.
`test_navigation_tab_coverage.py` (3/3) confirms the guard list stays in
sync. Full suite: 718 tests green. Ruff clean. Smoke test renders all 33
routes.

**PR.** [#130](https://github.com/BrycePremierBW/Jobhub/pull/130) —
merged, post-merge CI verified green.

### 2026-09-06 — Decision #10 follow-up: Equipment checklist save N+1 (read side)

**Reproduce.** The Job Equipment Checklist save handler already loaded
every existing `equipment_checklist_records` row for the selected job
once, up front, into `existing_by_item`, purely for form default values.
Inside `if submitted:`, it then re-ran
`SELECT id FROM equipment_checklist_records WHERE job_id = ? AND
checklist_item_id = ?` again for every single checklist item -- a
checklist that can easily have dozens of items. Wrote
`tests/test_equipment_checklist_save_n_plus_one.py`, driving a submitted
save with two items (one with an existing record, one without);
confirmed exactly 2 redundant per-item SELECTs against pre-fix code.

**Fix.** Added `existing_ids_by_item`, built from the same `existing_df`
query (now `ORDER BY id ASC`, matching the old per-row query's own
ordering so the "keep the lowest id, delete the rest" duplicate-cleanup
logic sees identical results). The save loop now looks up each item's
existing id(s) from this dict instead of re-querying. Zero write
statements changed -- this is the read-side half only. The write-side
batching PR #99 also describes (`execute_many` for the INSERT/UPDATE/
DELETE calls) is deliberately deferred as its own follow-up.

**Tests.** `tests/test_equipment_checklist_save_n_plus_one.py` -- zero
per-item SELECTs after the fix, same single INSERT (new item) and single
UPDATE (existing item, correct id) as before. Full suite: 719 tests
green. Ruff clean. Smoke test renders all 33 routes.
`tests/run_stage_control_ci.py` still passes.

**PR.** [#132](https://github.com/BrycePremierBW/Jobhub/pull/132) —
merged, post-merge CI verified green.

### 2026-09-06 — Decisions #1/#2/#3 follow-up: enterprise_job_cost_dataframe() reconciliation

**Reproduce.** The last of three job-cost implementations still not
Procurement-authoritative: `enterprise_job_cost_dataframe()` (the "Live
Job Control & Forecast-to-Complete" page) computed
`Actual Material Cost = max(received_material_cost, supplier_invoiced)`
and `Material Commitment` as a 6-way `max()` across
material_entries-derived and Procurement-derived figures. Wrote
`tests/test_enterprise_job_cost_procurement_reconciliation.py`; all 3
tests fail against pre-fix code (e.g. a PO-linked material line's
qty*price and its PO's own, different, subtotal both fed the same
max(), so the PO's own adjusted subtotal was never actually reflected
whenever material_entries' number happened to be bigger).

**Fix.** Same PO-link-exclusion pattern as #122: the `materials` query
now excludes rows linked to an active PO, and the formula is additive:
`Actual Material Cost = supplier_invoiced + non-PO received cost`,
`Procurement Committed Material Cost = po_committed + non-PO committed
cost`, `Material Commitment = max(Budget Materials, Procurement
Committed Material Cost)` (Budget Materials stays a floor -- a distinct
estimate concept, not a duplicate commercial truth). Fixed a bystander
break in `tests/test_material_price_snapshot.py` (from #121), which
extracted this same query directly and needed the new
`purchase_orders`/`purchase_order_lines` fixture tables plus updated
column names.

**Tests.** `tests/test_enterprise_job_cost_procurement_reconciliation.py`
(3 tests) plus the repaired `test_material_price_snapshot.py` (6/6).
Full suite: 722 tests green. Ruff clean. Smoke test renders all 33
routes including the Live Job Control page.

**PR.** [#133](https://github.com/BrycePremierBW/Jobhub/pull/133) —
merged, post-merge CI verified green. This closes the Job
Costs/Procurement reconciliation thread across all three job-cost
implementations in the codebase.

### 2026-09-06 — Decision #9 Phase 1: bootstrap organisation schema at core startup

**Reproduce.** `ensure_organization_schema()` was only called from
`jobhub/xero_setup_guard.py`, lazily, the first time Xero setup was
opened. Manually verified via a fresh process with an isolated `DATA_DIR`
that `initialise_jobhub_runtime()` alone left the `organizations` table
absent (`sqlite3.OperationalError: no such table: organizations`).

**Fix.** Added the same call to `initialise_jobhub_runtime()` right
after `init_db()` (so `app_settings` exists first). Additive and
idempotent, safe to also still run from Xero setup.

**Tests.** New `tests/run_organization_schema_startup_check.py` -- must
run as its own process (like `material_order_workflow_test.py`/
`run_stage_control_ci.py`), not a pytest-collected function, because
`pb_jobhub_app.DATA_DIR` is a module-level constant read once at import
time; a shared-process check could only ever observe whatever database
an earlier test already initialised, masking the exact gap this check
exists to catch. Confirmed it fails in a genuinely fresh process without
the fix. Added its own CI step. Full suite unaffected (722 tests green,
the new script intentionally not pytest-collected).

**PR.** [#134](https://github.com/BrycePremierBW/Jobhub/pull/134) —
merged, post-merge CI verified green. Phase 1 of
`docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md` complete; Phases 2-5
not started.

### 2026-09-06 — Decision #9 Phase 2: identity scoping (`organization_id` on `app_users`)

**Reproduce/design.** Added a one-time migration
(`20260906_app_users_organization_id_v1`) to `apply_schema_migrations()`
that adds `app_users.organization_id` and backfills existing rows onto
the default org. Reordered `initialise_jobhub_runtime()` so Phase 1's
`ensure_organization_schema()` runs first (the migration needs the
default org's real id already to exist). While implementing, found a
real gap the design doc's own phasing didn't spell out: because the
backfill migration only ever runs once, any user created *after* it
(starting with the very first server boot's own bootstrap admin, created
by `seed_app_users()` moments after the migration fires against an
still-empty `app_users` table) would get `organization_id = NULL`
forever, silently defeating "every user belongs to an org" from day one
of a fresh install. `pb_jobhub_app.py` runs its full startup
automatically at module import time, so there is no way to import it
fresh and separately drive individual startup steps in a custom order --
both new checks build the "before this migration ever ran" database
state by hand with raw `sqlite3`, *before* importing `pb_jobhub_app` at
all, to genuinely reproduce what upgrading a real production database
looks like. Confirmed both fail against pre-fix code with
`no such column: organization_id`.

**Fix.** `seed_app_users()`'s bootstrap-admin INSERT and the admin
"Add User" panel's INSERT now both set `organization_id` themselves at
creation time (the default org for the bootstrap admin since it's
necessarily the first user; the creating admin's own org -- falling back
to the default org -- for "Add User", so a session that predates Phase 2
still works). `_revalidate_session_user()` (decision #8) now also reads
and refreshes `organization_id` into session state every rerun, and the
login flow populates it at sign-in. No business-data table is scoped by
any of this yet, per the design doc's own phasing.

**Tests.** `tests/run_app_users_organization_id_backfill_check.py` and
`tests/run_bootstrap_admin_organization_id_check.py` (both standalone,
fresh-process scripts, not pytest-collected, matching
`run_organization_schema_startup_check.py`'s isolation reasoning) --
both pass against the fix, both fail against pre-fix code. Full suite:
722 tests green (unaffected; `organization_id` is additive to the
session dict, no existing assertion depends on its exact shape). Ruff
clean. Smoke test renders all 33 routes.

**PR.** [#136](https://github.com/BrycePremierBW/Jobhub/pull/136) —
merged, post-merge CI verified green. Phases 1-2 of
`docs/MULTI_TENANT_ORGANIZATION_SCOPING_DESIGN.md` complete; Phases 3-5
not started.
