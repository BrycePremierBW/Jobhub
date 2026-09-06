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
| 6 | Scheduling TOCTOU double-booking fix | [#118](https://github.com/BrycePremierBW/Jobhub/pull/118) | In review |
| 7 | Bulk crew scheduling — transactional/deterministic partial reporting | _pending_ | Not started |
| 4/5 | Price snapshots on material entries + configurable tax rate | _pending_ | Not started |
| 1/2/3 | Procurement-authoritative Job Costs reconciliation | _pending_ | Not started |
| 10 | Dead `jobhub/pages` code: inventory → port → test → remove | _pending_ | Not started |
| 9 | Multi-tenant org-scoping design document | _pending_ | Not started |
| 11 | Palm Lakes migration | **BLOCKED — do not touch** | N/A |

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

**PR.** [#118](https://github.com/BrycePremierBW/Jobhub/pull/118)
