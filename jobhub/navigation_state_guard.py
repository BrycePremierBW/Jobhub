"""Preserve user-selected Streamlit tabs across reruns.

Streamlit re-runs the script after many normal interactions. Native ``st.tabs``
then reopens the first tab, which makes JobHub feel like it keeps jumping back
to Add Job after an employee or manager selects a job in Job Register, or
snapping back to Add Timesheet when selecting an employee, date, or action on
the Timesheets page.  This small browser-side guard remembers the last clicked
tracked tab and restores it after the rerun finishes rendering.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Iterable


_TRACKED_TAB_SETS = (
    # Job Register no longer uses st.tabs() -- it was converted to a lazy
    # st.radio(key="job_register_section") selector (jobhub-audit-2026-09,
    # JH-PERF-JOBS-001), which persists its own selection across reruns
    # natively and so needs no entry here.
    frozenset({
        "Add Timesheet",
        "Review Timesheets",
        "Add Timesheet",
        "Review Timesheets",
        "Timesheets by Job",
        "Timesheets by Employee",
        "Hours Summary",
    }),
    frozenset({
        "Submit Timesheet",
        "My Timesheets",
    }),
    # Everything below closes the same rerun-reset gap for every other live
    # st.tabs() call site in the app (jobhub-audit-2026-09, JH-NAV-TABS-002).
    # tests/test_navigation_tab_coverage.py statically scans the live source
    # files for st.tabs() calls and fails if a new one is added here without
    # being tracked, so this list cannot silently drift out of date again.
    frozenset({  # Employee Portal "More employee tools" secondary view.
        "My Jobs",
        "Timesheet",
        "Requests",
        "Equipment",
        "Forms",
        "Photos",
        "Password",
    }),
    frozenset({"Add User", "Edit / Disable / Delete User", "User List"}),
    frozenset({"Application Changes", "Login Activity"}),
    frozenset({"Upload Photos", "View / Delete Photos"}),
    frozenset({"Import / Export", "Browse Rates", "Manage Rates"}),
    frozenset({
        "Summary / Pricing",
        "Line Items",
        "Production / Progress",
        "View / Export",
    }),
    frozenset({"Take-off", "Colour Schedule", "Documents"}),
    frozenset({  # Job Register -> full job detail (Summary ... Notes).
        "Summary",
        "Colours",
        "Documents",
        "Forms / Safety",
        "Stages / POs",
        "Costs & Estimates",
        "Materials",
        "Wages & Timesheets",
        "Equipment",
        "Control / Claims",
        "Photos",
        "Notes",
    }),
    frozenset({"Add", "Edit", "Remove", "Merge", "List"}),
    frozenset({"Add", "Edit", "Remove / Deactivate", "List"}),
    frozenset({"Edit selected line", "Delete selected line"}),
    frozenset({
        "Import Filled PDF Checklist",
        "Job Equipment Checklist",
        "Job Equipment Master List",
        "All Saved Equipment",
        "Manage Checklist Items",
    }),
    frozenset({"Job Pack by Job", "General Reports"}),
    frozenset({
        "Create Purchase Order",
        "PO Register / Receiving",
        "Supplier Invoice Match",
        "Export",
    }),
    frozenset({"Submit Form", "Form Register / Approval"}),
    frozenset({"System Health", "Audit Trail", "Backups", "Xero-Ready Export"}),
    frozenset({"Internal Dwellings", "External Substrates", "Summary / Export"}),
    frozenset({
        "Clickable tile board",
        "Add assignment",
        "Allocate crew",
        "Saved crews",
        "Edit / delete",
    }),
    frozenset({"Add request", "Approve / reject", "Leave register"}),
    frozenset({"Employees", "Jobs", "Target hours"}),
    frozenset({"Add staff", "Edit / remove bookings"}),
    frozenset({
        "Paint & packs",
        "Colour approvals",
        "Plan evidence",
        "Revision compare",
        "Handover",
    }),
    frozenset({"Role matrix", "User account audit", "Findings"}),
    frozenset({"Rates & forecast", "Stage defaults", "Crews"}),
    frozenset({
        "Company",
        "Employees",
        "Builders & clients",
        "Products & pricing",
        "Integrations",
    }),
    frozenset({"Health checks", "Data snapshot", "Runtime", "Unresolved errors"}),
)


def _labels_from_tabs(tabs: Any) -> list[str]:
    if isinstance(tabs, str):
        return [tabs]
    try:
        return [str(value) for value in list(tabs)]
    except Exception:
        return []


def _safe_id(labels: Iterable[str]) -> str:
    joined = "-".join(str(label) for label in labels)
    return re.sub(r"[^A-Za-z0-9_-]+", "-", joined).strip("-")[:80] or "tabs"


def _is_tracked(labels: list[str]) -> bool:
    label_set = frozenset(labels)
    return any(required.issubset(label_set) for required in _TRACKED_TAB_SETS)


def _restore_tabs_script(labels: list[str]) -> str:
    labels_json = json.dumps(labels)
    guard_id = json.dumps(f"pb-tab-state-{_safe_id(labels)}")
    return f"""
<script id={guard_id}>
(() => {{
  const trackedLabels = {labels_json};
  const labelSet = new Set(trackedLabels.map((value) => String(value).trim()));
  const storageKey = 'pb-jobhub-active-tab::' + trackedLabels.join('|');
  const normalise = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

  function getRootDocument() {{
    try {{
      if (window.parent && window.parent.document) return window.parent.document;
    }} catch (error) {{}}
    return document;
  }}

  function trackedTabs() {{
    const doc = getRootDocument();
    return Array.from(doc.querySelectorAll('[role="tab"]')).filter((tab) =>
      labelSet.has(normalise(tab.textContent))
    );
  }}

  function remember(label) {{
    if (!labelSet.has(label)) return;
    try {{
      window.localStorage.setItem(storageKey, label);
    }} catch (error) {{}}
  }}

  function restore() {{
    let desired = '';
    try {{
      desired = normalise(window.localStorage.getItem(storageKey));
    }} catch (error) {{
      desired = '';
    }}
    if (!labelSet.has(desired)) return false;

    const tab = trackedTabs().find((candidate) => normalise(candidate.textContent) === desired);
    if (!tab) return false;
    const selected = String(tab.getAttribute('aria-selected') || '').toLowerCase() === 'true';
    if (!selected && typeof tab.click === 'function') {{
      tab.click();
    }}
    return true;
  }}

  function installClickListener() {{
    const doc = getRootDocument();
    if (doc.__pbJobHubTabStateClickListener) return;
    doc.__pbJobHubTabStateClickListener = true;
    doc.addEventListener('click', (event) => {{
      const tab = event.target && event.target.closest ? event.target.closest('[role="tab"]') : null;
      if (!tab) return;
      const label = normalise(tab.textContent);
      remember(label);
    }}, true);
  }}

  installClickListener();

  let attempts = 0;
  const maxAttempts = 40;
  const interval = window.setInterval(() => {{
    attempts += 1;
    restore();
    if (attempts >= maxAttempts) window.clearInterval(interval);
  }}, 80);

  try {{
    const doc = getRootDocument();
    const observer = new MutationObserver(() => restore());
    observer.observe(doc.body || doc.documentElement, {{ childList: true, subtree: true }});
    window.setTimeout(() => observer.disconnect(), 5000);
  }} catch (error) {{}}
}})();
</script>
"""


def install_navigation_state_guard() -> bool:
    streamlit_module = sys.modules.get("streamlit")
    if streamlit_module is None:
        return False
    original = getattr(streamlit_module, "tabs", None)
    if original is None or getattr(original, "_pb_navigation_state_guard", False):
        return False

    def pb_stateful_tabs(tabs: Any, *args: Any, **kwargs: Any):
        labels = _labels_from_tabs(tabs)
        result = original(tabs, *args, **kwargs)
        if labels and _is_tracked(labels):
            html_renderer = getattr(streamlit_module, "html", None)
            if html_renderer is not None:
                try:
                    html_renderer(_restore_tabs_script(labels), unsafe_allow_javascript=True)
                except Exception:
                    pass
        return result

    pb_stateful_tabs._pb_navigation_state_guard = True  # type: ignore[attr-defined]
    pb_stateful_tabs._pb_original_tabs = original  # type: ignore[attr-defined]
    streamlit_module.tabs = pb_stateful_tabs
    return True
