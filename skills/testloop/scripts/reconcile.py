#!/usr/bin/env python3
"""Reconcile a Test Results record against the Validation Test Matrix it came from.

This is the third document in the loop, and the only one that does arithmetic.
It answers three questions the results document cannot answer about itself:

  * **Coverage** — which planned cases were never executed. An untested case is
    not a neutral absence; it is the plan making a claim nobody checked.
  * **Outcome** — what passed, failed, was blocked, split by priority and by
    regulatory flag, because a failing regulatory case and a failing cosmetic
    one do not carry the same weight.
  * **Plan gaps** — behaviour observed during the run that no row covers. These
    are the matrix's debts, and they set the agenda for the next revision.

It then applies the gate criteria and states a verdict. The verdict is computed
from the counts, not written by hand — which is precisely what makes it worth
auditing in the next step.

Both the counts and the verdict come from the results *spec*, not from the
rendered results document, so `audit.py` can recount independently and catch a
document that has been edited after it was generated.

Usage:
    reconcile.py results.json --auto-name RUNDIR
    reconcile.py results.json --auto-name RUNDIR --require-full-coverage
"""

import argparse
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

import lib
from lib import LoopError
from build_results import merge

HEADERS = [
    ("Test ID", "id"),
    ("Test Case Title", "title"),
    ("Priority", "priority"),
    ("Regulatory / Compliance-Critical", "regulatory"),
    ("Executed", "executed"),
    ("Status", "status"),
    ("Evidence", "evidence"),
    ("Defect", "defect"),
    ("Gate", "gate"),
]
WIDTHS = [11, 38, 9, 14, 10, 11, 28, 12, 30]


def assess(rows, unplanned, require_full_coverage):
    """Apply the gate criteria. Returns (criteria, blocking) — no prose."""
    not_run = [r for r in rows if r["status"] == "Not run"]
    blocked = [r for r in rows if r["status"] == "Blocked"]
    partial = [r for r in rows if r["status"] == "Partial"]
    failed = [r for r in rows if r["status"] == "Fail"]
    reg_fail = [r for r in failed if str(r["regulatory"]).strip().lower() == "yes"]
    high_fail = [r for r in failed if str(r["priority"]).strip().lower() == "high"]
    undefected = [r for r in failed if not r["defect"]]
    high_unplanned = [u for u in unplanned
                      if str(u.get("severity", "")).strip().lower() in ("high", "critical")]

    criteria = [
        {"name": "Every planned case was executed",
         "ok": not not_run,
         "detail": ", ".join(f"`{r['id']}`" for r in not_run) or "—",
         "blocking": require_full_coverage},
        {"name": "No regulatory case failed",
         "ok": not reg_fail,
         "detail": ", ".join(f"`{r['id']}`" for r in reg_fail) or "—",
         "blocking": True},
        {"name": "No High-priority case failed",
         "ok": not high_fail,
         "detail": ", ".join(f"`{r['id']}`" for r in high_fail) or "—",
         "blocking": True},
        {"name": "No case was blocked or left partial",
         "ok": not (blocked or partial),
         "detail": ", ".join(f"`{r['id']}`" for r in blocked + partial) or "—",
         "blocking": True},
        {"name": "Every failure carries a defect reference",
         "ok": not undefected,
         "detail": ", ".join(f"`{r['id']}`" for r in undefected) or "—",
         "blocking": False},
        {"name": "No High-severity behaviour outside the matrix",
         "ok": not high_unplanned,
         "detail": "; ".join(lib.md_cell(u.get("title", "")) for u in high_unplanned) or "—",
         "blocking": True},
    ]
    blocking = [c for c in criteria if c["blocking"] and not c["ok"]]
    return criteria, blocking


def gate_note(row):
    status = row["status"]
    reg = str(row["regulatory"]).strip().lower() == "yes"
    high = str(row["priority"]).strip().lower() == "high"
    if status == "Fail" and reg:
        return "Blocks — regulatory failure"
    if status == "Fail" and high:
        return "Blocks — High-priority failure"
    if status == "Fail":
        return "Failure, non-blocking"
    if status in ("Blocked", "Partial"):
        return f"Blocks — {status.lower()}, outcome unknown"
    if status == "Not run":
        return "Coverage gap"
    return "—"


def write_md(path, matrix, spec, rows, unplanned, unknown, criteria, blocking,
             results_doc):
    tally = {s: sum(1 for r in rows if r["status"] == s) for s in lib.STATUSES}
    total = len(rows)
    executed = total - tally["Not run"]
    verdict = "PASS" if not blocking else "HOLD"

    out = []
    out.append(f"# Reconciliation — {matrix['module']}\n")
    out.append(f"**Module / Suite:** {matrix['module']}  ")
    out.append(f"**Matrix (plan):** `{Path(matrix['path']).name}`, sheet `{matrix['sheet']}`  ")
    out.append(f"**Results (record):** `{results_doc}`  ")
    for label, key in (("Environment", "environment"), ("Build", "build"),
                       ("Executed by", "tester"), ("Run date", "date")):
        if spec.get(key):
            out.append(f"**{label}:** {spec[key]}  ")
    out.append("")
    out.append("Generated by joining the two documents above on Test ID. Every number "
               "below is counted from the results record — none of it is asserted. "
               "Edit the record and regenerate; do not correct this file by hand.\n")

    out.append(f"## Verdict — {verdict}\n")
    if verdict == "PASS":
        out.append("Every blocking criterion is met. The iteration can close, subject to "
                   "the audit pass confirming the record supports these numbers.\n")
    else:
        out.append(f"{len(blocking)} blocking criterion(s) not met. The iteration does not "
                   "close; the failures below set the agenda for the next one.\n")
    out.append("| Gate criterion | Met | Blocking | Cases |")
    out.append("|---|---|---|---|")
    for c in criteria:
        out.append(f"| {c['name']} | {'Yes' if c['ok'] else '**No**'} | "
                   f"{'Yes' if c['blocking'] else 'No'} | {c['detail']} |")
    out.append("")

    out.append("## Coverage\n")
    pct = (executed / total * 100) if total else 0.0
    out.append(f"- **Planned cases:** {total}")
    out.append(f"- **Executed:** {executed} ({pct:.0f}%)")
    out.append(f"- **Never executed:** {tally['Not run']}")
    out.append("")
    if tally["Not run"]:
        out.append("These cases are in the plan and have no outcome. Until they are run, "
                   "the plan's claim about them is unverified:\n")
        out.append("| Test ID | Title | Priority | Regulatory |")
        out.append("|---|---|---|---|")
        for r in rows:
            if r["status"] == "Not run":
                out.append(f"| `{r['id']}` | {lib.md_cell(r['title'])} | "
                           f"{r['priority']} | {r['regulatory']} |")
        out.append("")

    out.append("## Outcome tally\n")
    out.append("| Status | Count |")
    out.append("|---|---|")
    for s in lib.STATUSES:
        out.append(f"| {s} | {tally[s]} |")
    out.append(f"| **Total** | {total} |")
    out.append("")

    out.append("### By priority\n")
    out.append("| Priority | " + " | ".join(lib.STATUSES) + " | Total |")
    out.append("|---" * (len(lib.STATUSES) + 2) + "|")
    for priority in ("High", "Medium", "Low"):
        group = [r for r in rows if str(r["priority"]).strip().lower() == priority.lower()]
        if not group:
            continue
        counts = [sum(1 for r in group if r["status"] == s) for s in lib.STATUSES]
        out.append(f"| {priority} | " + " | ".join(str(c) for c in counts)
                   + f" | {len(group)} |")
    out.append("")

    out.append("### Regulatory / compliance-critical\n")
    reg = [r for r in rows if str(r["regulatory"]).strip().lower() == "yes"]
    if not reg:
        out.append("No case in this matrix is flagged regulatory.\n")
    else:
        counts = {s: sum(1 for r in reg if r["status"] == s) for s in lib.STATUSES}
        out.append(f"{len(reg)} regulatory case(s) — "
                   + ", ".join(f"{counts[s]} {s.lower()}" for s in lib.STATUSES if counts[s])
                   + ".\n")

    failures = [r for r in rows if r["status"] in ("Fail", "Blocked", "Partial")]
    out.append("## Failures, blocks and partials\n")
    if not failures:
        out.append("None.\n")
    else:
        out.append("| Test ID | Status | Title | Priority | Regulatory | Defect | Gate |")
        out.append("|---|---|---|---|---|---|---|")
        for r in failures:
            out.append(f"| `{r['id']}` | **{r['status']}** | {lib.md_cell(r['title'])} | "
                       f"{r['priority']} | {r['regulatory']} | {r['defect'] or '_none_'} | "
                       f"{gate_note(r)} |")
        out.append("")
        for r in failures:
            out.append(f"**`{r['id']}`** — expected: {lib.md_cell(r['expected'])}  ")
            out.append(f"observed: {r['observed'] or '_not recorded_'}\n")

    out.append("## Plan gaps — observed, but not in the matrix\n")
    if not unplanned:
        out.append("None. Everything the run touched was covered by a planned case.\n")
    else:
        out.append(f"{len(unplanned)} observation(s) with no matrix row. Each is a debt "
                   "against the plan: either it becomes a row in the next revision of the "
                   "matrix, or someone records why it should not be tested.\n")
        out.append("| # | Observation | Severity | Owed action |")
        out.append("|---|---|---|---|")
        for n, u in enumerate(unplanned, 1):
            out.append(f"| U{n} | {lib.md_cell(u.get('title', ''))} | "
                       f"{u.get('severity', '—')} | "
                       f"{lib.md_cell(u.get('action', 'Add a matrix row, or record why not'))} |")
        out.append("")

    if unknown:
        out.append("## Results with no planned case\n")
        out.append("These ids appeared in the record but not in the matrix — a typo, or a "
                   "case executed off-plan:\n")
        for test_id in sorted(unknown):
            out.append(f"- `{test_id}`")
        out.append("")

    out.append("## What the next iteration must do\n")
    actions = []
    for c in criteria:
        if not c["ok"]:
            actions.append(f"{'**Blocking** — ' if c['blocking'] else ''}"
                           f"{c['name'].lower()}: {c['detail']}")
    for n, u in enumerate(unplanned, 1):
        actions.append(f"Add a matrix row for U{n} ({lib.md_cell(u.get('title', ''))}), "
                       "or record why it should not be tested")
    if not actions:
        out.append("Nothing. Close the iteration once the audit pass confirms it.\n")
    else:
        for action in actions:
            out.append(f"- {action}")
        out.append("")
        out.append("Fold these into the next `/validation` revision and re-run, bumping the "
                   "version. Do not amend this iteration's documents — the record of a run "
                   "that happened is not editable.\n")

    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return verdict, tally


def write_xlsx(path, matrix, rows):
    book = Workbook()
    ws = book.active
    ws.title = "Reconciliation"
    table = []
    for r in rows:
        table.append({**r,
                      "executed": "No" if r["status"] == "Not run" else "Yes",
                      "gate": gate_note(r)})

    def style(row, field):
        if field != "status":
            return None
        s = lib.STATUS_STYLE[row["status"]]
        return Font(size=11, color=s["color"], bold=s["bold"], italic=s["italic"])

    lib.write_sheet(ws, HEADERS, table, WIDTHS,
                    shade=lambda r: str(r.get("regulatory", "")).strip().lower() == "yes",
                    cell_style=style)
    book.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="results spec JSON — the same one build_results.py used")
    ap.add_argument("--matrix", help="matrix .xlsx or .md (overrides spec.matrix)")
    ap.add_argument("--sheet", help="sheet name, for multi-sheet workbooks")
    ap.add_argument("--auto-name", metavar="DIR", help="write house-named files into DIR")
    ap.add_argument("--out", help="explicit .md path")
    ap.add_argument("--xlsx", help="explicit .xlsx path")
    ap.add_argument("--token")
    ap.add_argument("--stamp", help="iteration timestamp 'YYYY-MM-DD HHMM'")
    ap.add_argument("--version", type=int)
    ap.add_argument("--require-full-coverage", action="store_true",
                    help="treat any un-executed case as blocking, not advisory")
    ap.add_argument("--allow-unknown-id", action="store_true")
    args = ap.parse_args(argv)

    spec = lib.load_json(args.spec)
    matrix_path = args.matrix or spec.get("matrix")
    if not matrix_path:
        raise LoopError("no matrix given — set 'matrix' in the spec or pass --matrix")
    matrix_path = (Path(matrix_path) if Path(matrix_path).is_absolute()
                   else Path(args.spec).expanduser().parent / matrix_path)
    matrix = lib.load_matrix(matrix_path, args.sheet or spec.get("sheet"))
    rows, unknown = merge(matrix, spec, True)
    if unknown and not args.allow_unknown_id:
        raise LoopError(
            "result ids not in the matrix: " + ", ".join(sorted(unknown))
            + " — fix the spec, or pass --allow-unknown-id to report them as off-plan")
    unplanned = spec.get("unplanned", [])
    criteria, blocking = assess(rows, unplanned, args.require_full_coverage)

    token, stamp, version = lib.derive_identity(args, matrix_path)
    if args.auto_name:
        Path(args.auto_name).expanduser().mkdir(parents=True, exist_ok=True)
        md = lib.house_path(args.auto_name, "Reconciliation", token, stamp, version, "md")
        xlsx = lib.house_path(args.auto_name, "Reconciliation", token, stamp, version, "xlsx")
    elif args.out:
        md = Path(args.out).expanduser()
        xlsx = Path(args.xlsx).expanduser() if args.xlsx else md.with_suffix(".xlsx")
    else:
        raise LoopError("give --auto-name DIR (preferred) or --out PATH")

    results_doc = lib.house_path(md.parent, "Results", token, stamp, version, "md").name
    verdict, tally = write_md(md, matrix, spec, rows, unplanned, unknown,
                              criteria, blocking, results_doc)
    write_xlsx(xlsx, matrix, rows)

    print(f"md:   {md}")
    print(f"xlsx: {xlsx}")
    print("tally: " + ", ".join(f"{tally[s]} {s}" for s in lib.STATUSES if tally[s]))
    print(f"verdict: {verdict}")
    for c in blocking:
        print(f"  blocking: {c['name']} — {c['detail']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
