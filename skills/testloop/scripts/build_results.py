#!/usr/bin/env python3
"""Build a Test Results document (.xlsx + .md) from a results spec and its matrix.

The results document is the *record*: one row per test case in the Validation
Test Matrix, carrying what actually happened when that case was executed.

Test ID, title, expected result, priority, regulatory flag and tier are copied from
the matrix, never from the spec — a results document that paraphrases the plan
cannot be reconciled against it. The spec supplies only the outcome: status,
what was observed, the evidence, and any defect reference.

Every matrix row appears, including ones nobody executed: those come out as
"Not run" rather than silently vanishing, because an untested case is a finding.

Usage:
    build_results.py results.json --auto-name RUNDIR
    build_results.py results.json --auto-name RUNDIR --matrix path/to/matrix.xlsx
    build_results.py results.json --out Results_FormBuilder_2026-08-10_1105_v2.xlsx

Spec schema (JSON):
{
  "matrix": "qmsWrapper_FormBuilder_2026-08-10_1105_v2.xlsx",  # or pass --matrix
  "sheet": "Form Builder",              # optional; needed for multi-sheet workbooks
  "environment": "wrapper.example.com — DEV tenant, test data",
  "build": "2026-08-10 nightly",
  "tester": "who or what executed the run",
  "results": [
    {
      "id": "FORM-01",
      "status": "Pass",                 # Pass | Fail | Blocked | Partial | Not run
      "observed": "What actually happened, in your own words.",
      "evidence": ["screenshots/01-create-form.png"],
      "repro": ["Step 1", "Step 2"],    # required for Fail
      "defect": "BUG-123",              # optional
      "notes": ""                       # optional
    }
  ],
  "unplanned": [                        # seen during the run, no matrix row covers it
    {"title": "...", "observed": "...", "evidence": [...], "severity": "Medium"}
  ]
}
"""

import argparse
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

import lib
from lib import LoopError

HEADERS = [
    ("Test ID", "id"),
    ("Module / Suite", "module"),
    ("Test Case Title", "title"),
    ("Priority", "priority"),
    ("Regulatory / Compliance-Critical", "regulatory"),
    ("Tier", "tier"),
    ("Expected Result", "expected"),
    ("Status", "status"),
    ("Observed Result", "observed"),
    ("Evidence", "evidence"),
    ("Defect", "defect"),
    ("Notes", "notes"),
]
WIDTHS = [11, 22, 34, 9, 14, 13, 44, 11, 46, 26, 12, 26]


def merge(matrix, spec, allow_unknown):
    """Join spec outcomes onto matrix rows. Returns (rows, unknown_ids)."""
    by_id = {r["id"]: r for r in matrix["rows"]}
    outcomes, unknown = {}, []
    for entry in spec.get("results", []):
        test_id = str(entry.get("id", "")).strip()
        if not test_id:
            raise LoopError("a result entry has no 'id'")
        if test_id not in by_id:
            unknown.append(test_id)
            continue
        if test_id in outcomes:
            raise LoopError(f"two result entries for {test_id}")
        outcomes[test_id] = entry
    if unknown and not allow_unknown:
        raise LoopError(
            "result ids not in the matrix: " + ", ".join(sorted(unknown))
            + "\nEither the id is a typo, or the case is genuinely unplanned — "
              "in which case it belongs in 'unplanned', not 'results'. "
              "--allow-unknown-id drops them with a warning."
        )

    rows = []
    for row in matrix["rows"]:
        entry = outcomes.get(row["id"], {})
        status = lib.canon_status(entry.get("status")) if entry else "Not run"
        rows.append({
            "id": row["id"],
            "module": row["module"] or matrix["module"],
            "title": row["title"],
            "priority": row["priority"],
            "regulatory": row["regulatory"],
            "tier": row.get("tier") or lib.TIER_UNSTATED,
            "expected": row["expected"],
            "status": status,
            "observed": lib.md_cell(entry.get("observed", "")),
            "evidence": lib.md_cell(entry.get("evidence", "")),
            "defect": lib.md_cell(entry.get("defect", "")),
            "notes": lib.md_cell(entry.get("notes", "")),
            "_repro": entry.get("repro", []),
        })
    return rows, unknown


def write_xlsx(path, matrix, spec, rows):
    book = Workbook()
    ws = book.active
    ws.title = (matrix["sheet"] or matrix["module"])[:26] + " Res"

    def style(row, field):
        if field != "status":
            return None
        s = lib.STATUS_STYLE[row["status"]]
        return Font(size=11, color=s["color"], bold=s["bold"], italic=s["italic"])

    lib.write_sheet(
        ws, HEADERS, rows, WIDTHS,
        shade=lambda r: str(r.get("regulatory", "")).strip().lower() == "yes",
        cell_style=style,
    )
    book.save(path)


def write_md(path, matrix, spec, rows, results_dir):
    tally = {s: sum(1 for r in rows if r["status"] == s) for s in lib.STATUSES}
    reg_fail = [r for r in rows
                if r["status"] == "Fail"
                and str(r["regulatory"]).strip().lower() == "yes"]
    out = []
    out.append(f"# Test Results — {matrix['module']}\n")
    out.append(f"**Module / Suite:** {matrix['module']}  ")
    out.append(f"**Matrix:** `{Path(matrix['path']).name}`, sheet `{matrix['sheet']}`  ")
    for label, key in (("Environment", "environment"), ("Run tier", "tier"),
                       ("Build", "build"),
                       ("Executed by", "tester"), ("Run date", "date")):
        if spec.get(key):
            out.append(f"**{label}:** {spec[key]}  ")
    out.append(f"**Cases:** {len(rows)} — "
               + ", ".join(f"{tally[s]} {s.lower()}" for s in lib.STATUSES if tally[s]))
    out.append("")
    out.append("**This is a test record, not a test plan.** Every row is a case from the "
               "matrix above; the matrix decides what is tested, this file records what "
               "happened. Do not add cases here — add them to the matrix and re-run it.\n")
    if reg_fail:
        out.append("> **Regulatory cases failed:** "
                   + ", ".join(f"`{r['id']}`" for r in reg_fail)
                   + ". These gate the iteration.\n")

    out.append("| Test ID | Status | Test Case Title | Priority | Regulatory | Tier | Defect |")
    out.append("|---|---|---|---|---|---|---|")
    for r in rows:
        status = f"**{r['status']}**" if r["status"] in ("Fail", "Blocked") else r["status"]
        out.append(f"| `{r['id']}` | {status} | {lib.md_cell(r['title'])} | "
                   f"{r['priority']} | {r['regulatory']} | {r['tier']} | "
                   f"{r['defect'] or '—'} |")
    out.append("")

    for r in rows:
        out.append(f"## {r['id']} — {lib.md_cell(r['title'])}\n")
        out.append("| | |")
        out.append("|---|---|")
        out.append(f"| **Status** | {r['status']} |")
        out.append(f"| **Priority** | {r['priority']} |")
        out.append(f"| **Regulatory / Compliance-Critical** | {r['regulatory']} |")
        out.append(f"| **Tier** | {r['tier']} |")
        if r["defect"]:
            out.append(f"| **Defect** | {r['defect']} |")
        out.append("")
        out.append(f"**Expected:** {lib.md_cell(r['expected'])}\n")
        out.append(f"**Observed:** {r['observed'] or '_not recorded_'}\n")
        if r["_repro"]:
            out.append("**Reproduction:**\n")
            for n, step in enumerate(r["_repro"], 1):
                out.append(f"{n}. {step}")
            out.append("")
        if r["evidence"]:
            out.append("**Evidence:**\n")
            for item in str(r["evidence"]).split("; "):
                item = item.strip()
                if not item:
                    continue
                if item.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                    out.append(f"- ![{r['id']}]({item})")
                else:
                    out.append(f"- {item}")
            out.append("")
        if r["notes"]:
            out.append(f"**Notes:** {r['notes']}\n")

    unplanned = spec.get("unplanned", [])
    out.append("## Observed outside the matrix\n")
    if not unplanned:
        out.append("Nothing was seen during this run that the matrix does not already "
                   "cover.\n")
    else:
        out.append("Behaviour seen during the run that no matrix row exercises. These are "
                   "**not** results — they are candidate rows for the next revision of the "
                   "matrix, and the reconciliation counts them as plan gaps.\n")
        for n, item in enumerate(unplanned, 1):
            out.append(f"### U{n}. {lib.md_cell(item.get('title', 'Untitled'))}\n")
            if item.get("severity"):
                out.append(f"**Severity:** {item['severity']}  ")
            out.append(f"**Observed:** {lib.md_cell(item.get('observed', ''))}\n")
            if item.get("evidence"):
                for ev in item["evidence"]:
                    out.append(f"- {ev}")
                out.append("")

    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="results spec JSON")
    ap.add_argument("--matrix", help="matrix .xlsx or .md (overrides spec.matrix)")
    ap.add_argument("--sheet", help="sheet name, for multi-sheet workbooks")
    ap.add_argument("--auto-name", metavar="DIR",
                    help="write house-named files into DIR")
    ap.add_argument("--out", help="explicit .xlsx path")
    ap.add_argument("--md", help="explicit .md path")
    ap.add_argument("--token", help="module filename token, if not derivable")
    ap.add_argument("--stamp", help="iteration timestamp 'YYYY-MM-DD HHMM'")
    ap.add_argument("--version", type=int, help="iteration number")
    ap.add_argument("--allow-unknown-id", action="store_true",
                    help="drop result ids absent from the matrix instead of stopping")
    args = ap.parse_args(argv)

    spec = lib.load_json(args.spec)
    matrix_path = args.matrix or spec.get("matrix")
    if not matrix_path:
        raise LoopError("no matrix given — set 'matrix' in the spec or pass --matrix")
    matrix_path = (Path(matrix_path) if Path(matrix_path).is_absolute()
                   else Path(args.spec).expanduser().parent / matrix_path)
    matrix = lib.load_matrix(matrix_path, args.sheet or spec.get("sheet"))

    rows, unknown = merge(matrix, spec, args.allow_unknown_id)

    if args.auto_name:
        token, stamp, version = lib.derive_identity(args, matrix_path)
        Path(args.auto_name).expanduser().mkdir(parents=True, exist_ok=True)
        xlsx = lib.house_path(args.auto_name, "Results", token, stamp, version, "xlsx")
        md = lib.house_path(args.auto_name, "Results", token, stamp, version, "md")
    elif args.out:
        xlsx = Path(args.out).expanduser()
        md = Path(args.md).expanduser() if args.md else xlsx.with_suffix(".md")
    else:
        raise LoopError("give --auto-name DIR (preferred) or --out PATH")
    if args.md:
        md = Path(args.md).expanduser()

    write_xlsx(xlsx, matrix, spec, rows)
    write_md(md, matrix, spec, rows, md.parent)

    tally = {s: sum(1 for r in rows if r["status"] == s) for s in lib.STATUSES}
    if unknown:
        print("warning: dropped result ids not in the matrix: "
              + ", ".join(sorted(unknown)), file=sys.stderr)
    print(f"xlsx: {xlsx}")
    print(f"md:   {md}")
    print("cases: " + ", ".join(f"{tally[s]} {s}" for s in lib.STATUSES if tally[s]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
