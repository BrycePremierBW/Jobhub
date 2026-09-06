# Dead Code Inventory — Architecture Decision #10

**Architecture decision #10:** *"Dead jobhub/pages code: prove dead;
inventory useful historical fixes; port useful fixes into actual
production path; test actual production behavior; only then
deprecate/remove dead modules."*

This document is the "prove dead" and "inventory" steps. It does **not**
port or remove anything — one concrete, high-value port is identified and
recommended as its own follow-up workstream (Section 4), scoped narrowly
enough to follow the standard REPRODUCE → MINIMAL FIX → TESTS pipeline on
its own, rather than being bundled in here.

## 1. Proving dead

`jobhub/__init__.py` installs every module that actually participates in
the running app (the ~50 `*_guard.py` modules, in a specific order). The
following modules are **not** imported by `jobhub/__init__.py`, by
`pb_jobhub_app.py`, or by any guard module — confirmed by grepping the
entire tree for `import <module>` / `from ... import <module>` /
`<module>.` outside the file itself:

| Module | Size | Status |
|---|---|---|
| `jobhub/pages/builders_clients.py` | 8.4 KB | Dead |
| `jobhub/pages/dashboard.py` | 8.7 KB | Dead |
| `jobhub/pages/employees.py` | 9.8 KB | Dead |
| `jobhub/pages/equipment.py` | 18.9 KB | Dead |
| `jobhub/pages/jobs.py` | 19.4 KB | Dead |
| `jobhub/pages/materials.py` | 13.6 KB | Dead |
| `jobhub/pages/products.py` | 1.9 KB | Dead |
| `jobhub/pages/reports.py` | 25.1 KB | Dead |
| `jobhub/pages/wages.py` | 7.2 KB | Dead |
| `jobhub/operations.py` | 19.8 KB | Dead |
| `jobhub/documents.py` | 59.1 KB | Dead |
| `jobhub/estimating.py` | 78.9 KB | Dead |
| `jobhub/job_views.py` | 37.3 KB | Dead |
| `jobhub/mapping.py` | 133.0 KB | Dead |
| `jobhub/material_orders.py` | 36.0 KB | Dead |
| `jobhub/navigation.py` | 3.7 KB | Dead |
| `jobhub/control_centre.py` | 36.2 KB | Dead |
| `jobhub/takeoff_pages.py` | 18.3 KB | Dead |
| `jobhub/ai_tools.py` | 49.6 KB | Dead (imported only by its own test file directly, never by production code) |

~508 KB total, 19 files. All confirmed dead by static import analysis, not
inference — see the grep methodology in the repair ledger entry for this
document's PR.

Git history shows this was an **earlier, page-based UI architecture**
(commit messages: "Add selected job status editor", "Make all job
details editable with calendars", "Add staged job control and staff
requests") that was superseded by the current single-monolith-with-guards
architecture (`pb_jobhub_app.py` + `jobhub/*_guard.py`), not code that
was ever deliberately "soft-deleted" — it was left in place when the
newer architecture took over the same features.

## 2. Searching for useful historical fixes

Searched the full git history for every commit whose message mentions
"fix" and touches one of the 19 dead files above:

```
016f5cb Lazy-render builders and clients sections (#94)
bc720e7 Lazy-render job register sections (#93)
e1fb0a5 Fix SQL string delimiters in builder/client lazy refactor
768da06 Fix SQL string delimiters in lazy Job Register refactor
```

No other "fix"-labeled commits touch any of the 19 dead files. These four
are all one piece of work across two files: `jobhub/pages/jobs.py` and
`jobhub/pages/builders_clients.py` were each reworked from an eager
`st.tabs()` (all tab bodies -- and every DB query inside them -- execute
on *every* page load, regardless of which tab the user is looking at) to
a lazy single-section selector (only the selected section's code, and its
queries, execute). Both changes shipped with real regression tests
(`tests/test_jobs_page_performance.py`, 4 tests;
`tests/test_builders_clients_page_performance.py`, 3 tests) that still
exist in the repo and (as of the CI fix in the companion PR to this one)
now actually execute — and pass, confirming the lazy pattern in both dead
files still works exactly as documented.

## 3. Is the same problem live in production?

**Yes, in both cases, confirmed by direct inspection of `pb_jobhub_app.py`
as it stands today:**

- **Job Register** (`pb_jobhub_app.py`, `elif menu == "Jobs":`, ~line
  23878): still `st.tabs(["Add Job", "Edit Job", "Remove / Archive",
  "Archived Jobs", "Search by Builder", "Job Register"])` — all six
  sections' bodies execute on every load of this page, for every one of
  the ~14 staff, however many times a day they open it.
- **Builders & Clients** (`pb_jobhub_app.py`, ~line 24390): still
  `st.tabs(["Add", "Edit", "Remove", "Merge", "List"])` — same pattern,
  five sections. Note this live tab set has a "Merge" section that the
  dead code's `BUILDER_SECTIONS = ["Add", "Edit", "Remove", "List"]`
  does not — the live page has evolved since the dead fix was written, so
  porting is not a direct copy-paste; the lazy-selector pattern needs to
  be re-applied to the *current* five-section version, with "Merge"
  included.

This is exactly the class of problem architecture decision #10 exists to
catch: real, working performance fixes were built, tested, and then
never made it into the code path users actually hit, because they were
built against a UI structure ("pages") that was already being phased out
in favour of the monolith in parallel.

## 4. Recommended follow-up (not implemented in this document)

Port the lazy-section-selector pattern into both live blocks in
`pb_jobhub_app.py`, re-derived against the *current* code (not a literal
copy of the dead files, since both have drifted — Builders & Clients
gained a "Merge" tab; Job Register may have gained fields/validation
since #93 was written). This should be its own scoped workstream, run
through the full REPRODUCE → MINIMAL FIX → TESTS → CI → MERGE pipeline,
because:

- **It intersects with this programme's own earlier work.** Both tab
  sets are registered in `jobhub/navigation_state_guard.py`'s
  `_TRACKED_TAB_SETS` (added to fix the 26-site tab-persistence gap found
  earlier in this audit). Replacing `st.tabs()` with a section selector
  removes the tab set entirely, so `_TRACKED_TAB_SETS` and
  `tests/test_navigation_tab_coverage.py`'s static scan need a
  corresponding update in the same change, not as an afterthought.
- **It deserves real measurement, not just a code-shape argument.** The
  REPRODUCE step for this workstream should count/time the actual DB
  queries executed per page load before and after (the same style of
  proof already used throughout this session, e.g. the TOCTOU race's
  5/5-failure reproduction), not just cite "the old code lacked
  `st.tabs()`" as sufficient evidence of a perf win.
- **It is a real, live UI behaviour change** for a page every staff
  member uses, on every load — worth its own focused review rather than
  being bundled into a dead-code paperwork PR.

No other dead file produced a "fix"-labeled commit, so no other concrete
port candidate was found by this method. This does not prove the other
17 files contain nothing of value — only that a targeted search for
explicit historical bug/perf fixes (the specific thing decision #10 asks
to inventory) found exactly these two, and no others.

## 5. What this document does not claim

This is not an exhaustive line-by-line audit of ~508 KB of dead code.
Given the scale, a full manual diff of every dead file against its
(sometimes nonexistent) live counterpart was not attempted. What was
done: (a) prove every listed file is genuinely unreachable from the
running app, and (b) search git history specifically for *fix* commits
against those files, which is the concrete, checkable proxy for "useful
historical fix" decision #10 asks about. If a specific dead file is
suspected to hold other value beyond what a "fix" commit message would
surface (e.g. a feature that was built but never wired up, rather than a
bug that was fixed), that needs a separate, explicitly-scoped review —
this document does not rule that out, it just didn't find evidence of it
through this method.

## 6. Deprecation/removal

Per decision #10's own ordering ("only then deprecate/remove dead
modules"), removal of these 19 files should wait until after the Section
4 port lands and is verified in production — removing the source of a
fix before confirming the fix has been successfully re-applied elsewhere
would destroy the evidence needed to verify the port was faithful.
