#!/usr/bin/env python3
"""Document F — validate an iteration's record against the source it was run on.

A–E are black-box. The matrix is grounded in controls the tester saw, the
results say what the screen did, the reconciliation joins the two, and the
audit weighs the record's strength. None of them can say whether the *product*
is right — only whether the paperwork is. A module can behave exactly as the
matrix specifies while the code underneath is wrong in a way no row asked about,
and the loop will confirm it.

So document F asks the one question the other five cannot: **does the source
support what the record claims?** It reads the branch the tested build came
from and, case by case, corroborates, strengthens, contradicts or settles what
was recorded.

    Corroborated  source agrees with the recorded outcome
    Strengthened  source supports it AND adds something the UI could not show
    Contradicted  source says the recorded outcome is wrong
    Unsupported   the record asserts a mechanism the source does not show
    Settled       a Blocked / Not-run case that source answers without executing it
    Absent        the behaviour is not in this repository (usually an API tier)

This is not a second opinion on the same evidence. It is a different witness.

## What this script does, and does not

It does NOT read the code for you. Judgement about what a file means is the
validator's, and it belongs in `codecheck.json`. What the script does is make
that judgement *checkable*:

  * every citation is fetched from the repository at a **pinned commit** and the
    quoted text must actually appear at the line claimed (±`--slack` lines);
  * a citation that does not resolve is a blocking finding, because a plausible
    file path is exactly what an invented reading looks like;
  * the ref is pinned to a commit sha, not a branch name, so the document still
    means something after the branch moves;
  * if `--build` is given, it is compared against the ref and a mismatch is
    reported — validating against code the tested build never ran is the
    quietest way to reach a confident wrong answer.

The gate refuses on: an unresolvable citation, a `Contradicted` verdict against
a case the record passed, and a citation-free verdict that claims source support.

## Access

    --token / $GITLAB_TOKEN         a personal access token (read_api), or
    --cookie / $GITLAB_COOKIE       a signed-in browser's cookie header, or
    --cookie-file <path>            the same, from a file

GitLab answers unauthenticated API calls with `404 Project Not Found` rather
than 401, which reads like a wrong project id instead of a missing login — the
script says so explicitly when it sees a 404 on the ref lookup.

## Usage

    codevalidate.py codecheck.json --run-dir . \
        --project 11 --ref development2 --build v.10.3064.ce9870f50_debug

`codecheck.json`:

    {
      "base": "https://gitlab.example.com",
      "project": 11,
      "ref": "development2",
      "checks": [
        {"id": "VIG-18", "verdict": "Corroborated",
         "finding": "The 15-day tier is computed from the aware date, not stored.",
         "citations": [
           {"path": "common/models/VigilanceClock.php", "line": 88,
            "quote": "case self::TIER_15D:"}
         ]},
        {"id": "VIG-23", "verdict": "Strengthened",
         "finding": "Every export resolves a reporting-server URL through one dispatcher.",
         "citations": [
           {"path": "frontend/controllers/GeneralController.php", "line": 141,
            "quote": "elseif ($type == 'medwatch')"}
         ]}
      ],
      "not_in_repo": [
        {"topic": "PIN storage", "why": "decided by the API tier, not this repository"}
      ]
    }
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lib  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

VERDICTS = {
    "Corroborated": "source agrees with the recorded outcome",
    "Strengthened": "source agrees and adds what the UI could not show",
    "Contradicted": "source says the recorded outcome is wrong",
    "Unsupported": "the record asserts a mechanism the source does not show",
    "Settled": "source answers a case that was not executed",
    "Absent": "not in this repository",
}
# Verdicts that assert the source backs the claim, so must cite something.
NEEDS_CITATION = {"Corroborated", "Strengthened", "Contradicted", "Unsupported", "Settled"}
DEFAULT_BASE = "https://gitlab.example.com"


class Gl:
    """Minimal read-only GitLab client. Session cookie or token, either works."""

    def __init__(self, base, project, token=None, cookie=None):
        self.base = base.rstrip("/")
        self.project = project
        self.headers = {"User-Agent": "testloop-codevalidate"}
        if token:
            self.headers["PRIVATE-TOKEN"] = token
        elif cookie:
            self.headers["Cookie"] = cookie
        else:
            raise lib.LoopError(
                "no GitLab credential: pass --token/$GITLAB_TOKEN, or "
                "--cookie/--cookie-file/$GITLAB_COOKIE with a signed-in browser's cookies")
        self._cache = {}

    def _get(self, path):
        url = f"{self.base}/api/v4/projects/{self.project}/{path}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            raise lib.LoopError(f"cannot reach {self.base}: {e.reason}")

    def resolve(self, ref):
        """Branch or tag name -> commit sha, so the document pins a commit."""
        status, body = self._get(
            f"repository/branches/{urllib.parse.quote(str(ref), safe='')}")
        if status == 404:
            raise lib.LoopError(
                f"ref '{ref}' not found in project {self.project}. GitLab answers "
                "unauthenticated calls with 404 Project Not Found, so check the "
                "credential before the ref — a stale cookie looks exactly like this.")
        if status != 200:
            raise lib.LoopError(f"ref lookup failed: HTTP {status} {body[:160]}")
        commit = json.loads(body)["commit"]
        return {"sha": commit["id"], "short": commit["short_id"],
                "title": commit.get("title", "")[:110], "when": commit.get("created_at", "")}

    def file(self, path, sha):
        key = (path, sha)
        if key in self._cache:
            return self._cache[key]
        status, body = self._get(
            f"repository/files/{urllib.parse.quote(path, safe='')}/raw?ref={sha}")
        result = body.splitlines() if status == 200 else None
        self._cache[key] = result
        return result


def verify_citation(gl, sha, cite, slack):
    """Fetch the cited file at the pinned commit and look for the quote.

    Returns (ok, note). The line number is a hint, not the assertion — files
    drift. What must be true is that the quoted text is in the file, and near
    where the validator said it was.
    """
    path = (cite.get("path") or "").strip()
    if not path:
        return False, "citation has no path"
    lines = gl.file(path, sha)
    if lines is None:
        return False, f"{path} does not exist at this commit"
    quote = (cite.get("quote") or "").strip()
    if not quote:
        return False, f"{path} has no quote to verify against"

    def norm(s):
        return re.sub(r"\s+", " ", s).strip()

    needle = norm(quote)
    hits = [i + 1 for i, l in enumerate(lines) if needle in norm(l)]
    if not hits:
        joined = norm(" ".join(lines))
        if needle in joined:
            return True, f"{path} — quote spans lines (exact line not pinned)"
        return False, f"{path} — quote not found in the file at this commit"
    claimed = cite.get("line")
    if claimed is None:
        return True, f"{path}:{hits[0]}"
    nearest = min(hits, key=lambda h: abs(h - int(claimed)))
    if abs(nearest - int(claimed)) > slack:
        return False, (f"{path} — quote found at line {nearest}, "
                       f"but the citation says {claimed} (>{slack} lines out)")
    return True, f"{path}:{nearest}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("codecheck", help="codecheck.json — the validator's readings")
    ap.add_argument("--run-dir", default=".", help="iteration directory (holds the matrix)")
    ap.add_argument("--results", help="results.json (default: <run-dir>/results.json)")
    ap.add_argument("--matrix", help="override the matrix path")
    ap.add_argument("--base-url", help="GitLab base URL")
    ap.add_argument("--project", help="GitLab project id")
    ap.add_argument("--ref", help="branch, tag or sha to validate against")
    ap.add_argument("--build", help="build string the tests ran on, to compare with the ref")
    ap.add_argument("--token", help="GitLab token; else $GITLAB_TOKEN")
    ap.add_argument("--cookie", help="Cookie header; else $GITLAB_COOKIE")
    ap.add_argument("--cookie-file", help="file holding the Cookie header")
    ap.add_argument("--slack", type=int, default=25,
                    help="how far a quote may sit from its cited line (default 25)")
    ap.add_argument("--token-name", dest="token", help=argparse.SUPPRESS)
    ap.add_argument("--stamp", help="iteration timestamp 'YYYY-MM-DD HHMM'")
    ap.add_argument("--version", type=int, help="iteration version")
    args = ap.parse_args(argv)

    run_dir = pathlib.Path(args.run_dir).expanduser()
    spec = lib.load_json(args.codecheck)
    checks = spec.get("checks") or []
    if not checks:
        raise lib.LoopError("codecheck.json has no `checks` — nothing to validate")

    matrix_path = args.matrix
    if not matrix_path:
        candidates = sorted(run_dir.glob("qmsWrapper_*_v*.xlsx"))
        if not candidates:
            raise lib.LoopError(
                f"no matrix found in {run_dir} — pass --matrix")
        matrix_path = str(candidates[-1])
    matrix = lib.load_matrix(matrix_path)
    cases = matrix.get("rows", [])
    module_name = matrix.get("module") or ""
    by_id = {c["id"]: c for c in cases}

    results_path = pathlib.Path(args.results) if args.results else run_dir / "results.json"
    recorded = {}
    if results_path.exists():
        for row in lib.load_json(results_path).get("results", []):
            recorded[row.get("id")] = lib.canon_status(row.get("status"))

    identity_args = argparse.Namespace(token=None, stamp=args.stamp, version=args.version)
    token, stamp, version = lib.derive_identity(identity_args, matrix_path)

    base = args.base_url or spec.get("base") or DEFAULT_BASE
    project = args.project or spec.get("project")
    ref = args.ref or spec.get("ref")
    if not project:
        raise lib.LoopError("no GitLab project id: pass --project or set `project` in codecheck.json")
    if not ref:
        raise lib.LoopError("no ref: pass --ref or set `ref` in codecheck.json")

    cookie = args.cookie or os.environ.get("GITLAB_COOKIE")
    if not cookie and args.cookie_file:
        cookie = pathlib.Path(args.cookie_file).expanduser().read_text().strip()
    gl = Gl(base, project, args.token or os.environ.get("GITLAB_TOKEN"), cookie)
    head = gl.resolve(ref)

    build = args.build or spec.get("build")
    build_note = None
    if build:
        short = head["short"]
        build_note = ("matches" if short.lower() in str(build).lower()
                      else "DOES NOT MATCH")

    # --- verify every citation against the pinned commit --------------------
    rows, blocking, advisory = [], [], []
    for check in checks:
        cid = check.get("id", "")
        verdict = (check.get("verdict") or "").strip().capitalize()
        if verdict not in VERDICTS:
            raise lib.LoopError(
                f"{cid}: verdict {check.get('verdict')!r} is not one of {', '.join(VERDICTS)}")
        notes, ok_all = [], True
        for cite in check.get("citations") or []:
            ok, note = verify_citation(gl, head["sha"], cite, args.slack)
            notes.append(("ok" if ok else "FAIL") + " — " + note)
            if not ok:
                ok_all = False
                blocking.append(f"`{cid}` — citation does not resolve: {note}")
        if verdict in NEEDS_CITATION and not (check.get("citations") or []):
            ok_all = False
            blocking.append(
                f"`{cid}` — verdict {verdict} claims the source settles it, but cites nothing")
        if cid and cid not in by_id:
            advisory.append(f"`{cid}` is not a case in {pathlib.Path(matrix_path).name}")
        if verdict == "Contradicted" and recorded.get(cid) == "Pass":
            blocking.append(
                f"`{cid}` — recorded Pass, but source contradicts it; the iteration cannot stand")
        rows.append({
            "id": cid,
            "title": by_id.get(cid, {}).get("title", ""),
            "recorded": recorded.get(cid, "—"),
            "verdict": verdict,
            "finding": check.get("finding", ""),
            "citations": "; ".join(c.get("path", "") + (f":{c['line']}" if c.get("line") else "")
                                   for c in check.get("citations") or []),
            "checked": "; ".join(notes) or "—",
            "ok": ok_all,
        })

    # cases the record could not settle, that nobody looked at in source
    unchecked_fail = [cid for cid, st in recorded.items()
                      if st in ("Fail", "Blocked", "Partial", "Not run")
                      and cid not in {r["id"] for r in rows}]
    for cid in sorted(unchecked_fail):
        advisory.append(f"`{cid}` was recorded {recorded[cid]} and was not looked for in source")

    if build_note == "DOES NOT MATCH":
        advisory.append(
            f"the tested build ({build}) is not the ref being read ({head['short']}) — "
            "readings may not describe the code that was exercised")

    confirmed = not blocking
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    # --- render -------------------------------------------------------------
    md_path = lib.house_path(run_dir, "CodeValidation", token, stamp, version, "md")
    xlsx_path = lib.house_path(run_dir, "CodeValidation", token, stamp, version, "xlsx")

    out = []
    out.append(f"# Code Validation — {module_name or token}\n")
    out.append(f"**Iteration:** `{pathlib.Path(matrix_path).name}`  ")
    out.append(f"**Repository:** {base} — project {project}  ")
    out.append(f"**Ref:** `{ref}` pinned at **`{head['short']}`** "
               f"({head['when'][:19]}) — _{head['title']}_  ")
    if build:
        out.append(f"**Tested build:** `{build}` — **{build_note}** the ref  ")
    out.append(f"\n**Verdict: {'CONFIRMED' if confirmed else 'REFUSED'}** — "
               f"{len(rows)} case(s) read against source, "
               f"{sum(1 for r in rows if not r['ok'])} with unverifiable citations.\n")
    out.append("> Document F asks what A–E cannot: does the source support what the record\n"
               "> claims? Every quotation below was fetched from the pinned commit and located\n"
               "> in the file at validation time. This says nothing about code the matrix never\n"
               "> exercised, and nothing about tiers this repository does not contain.\n")

    out.append("\n## Tally\n")
    out.append("| Verdict | Cases | Means |")
    out.append("|---|---:|---|")
    for v, meaning in VERDICTS.items():
        if counts.get(v):
            out.append(f"| {v} | {counts[v]} | {meaning} |")

    out.append("\n## Case by case\n")
    out.append("| Case | Recorded | Source verdict | Finding | Citations |")
    out.append("|---|---|---|---|---|")
    for r in rows:
        out.append(f"| `{r['id']}` | {r['recorded']} | **{r['verdict']}** | "
                   f"{lib.md_cell(r['finding'])} | {lib.md_cell(r['citations']) or '—'} |")

    out.append("\n## Citation check\n")
    out.append("Each quotation was fetched at the pinned commit and located in the file.\n")
    out.append("| Case | Result |")
    out.append("|---|---|")
    for r in rows:
        out.append(f"| `{r['id']}` | {lib.md_cell(r['checked'])} |")

    if spec.get("not_in_repo"):
        out.append("\n## Not answerable from this repository\n")
        out.append("| Topic | Why |")
        out.append("|---|---|")
        for item in spec["not_in_repo"]:
            out.append(f"| {lib.md_cell(item.get('topic',''))} | {lib.md_cell(item.get('why',''))} |")

    if blocking:
        out.append("\n## Blocking findings\n")
        for b in blocking:
            out.append(f"- {b}")
    if advisory:
        out.append("\n## Advisory\n")
        for a in advisory:
            out.append(f"- {a}")

    out.append("\n## What this changes\n")
    if not rows:
        out.append("Nothing — no cases were read.")
    else:
        changed = [r for r in rows if r["verdict"] in ("Contradicted", "Unsupported", "Settled")]
        if changed:
            for r in changed:
                out.append(f"- `{r['id']}` — **{r['verdict']}**: {r['finding']}")
        else:
            out.append("No recorded outcome was overturned; the source corroborates the record "
                       "as far as it was read.")
    md_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    wb = Workbook()
    ws = wb.active
    ws.title = "Code Validation"
    headers = [("Test ID", "id"), ("Test Case Title", "title"), ("Recorded Outcome", "recorded"),
               ("Source Verdict", "verdict"), ("Finding", "finding"),
               ("Citations", "citations"), ("Citation Check", "checked")]
    colour = {"Contradicted": "C00000", "Unsupported": "C00000",
              "Strengthened": "1F6F3D", "Settled": "1F4E78"}

    def style(row, field):
        if field == "verdict" and row["verdict"] in colour:
            return Font(bold=True, color=colour[row["verdict"]], size=11)
        return None

    lib.write_sheet(ws, headers, rows, [11, 34, 16, 16, 52, 34, 40],
                    shade=lambda r: not r["ok"], cell_style=style)
    wb.save(xlsx_path)

    print(f"md:   {md_path.name}")
    print(f"xlsx: {xlsx_path.name}")
    print(f"ref:  {ref} @ {head['short']}" + (f"  (build {build_note})" if build else ""))
    print("tally: " + ", ".join(f"{n} {v}" for v, n in counts.items()))
    print(f"validation: {'CONFIRMED' if confirmed else 'REFUSED'}")
    for b in blocking:
        print("  blocking: " + re.sub(r"[`*]", "", b))
    return 0 if confirmed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except lib.LoopError as exc:
        print(f"codevalidate: {exc}", file=sys.stderr)
        sys.exit(2)
