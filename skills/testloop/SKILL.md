---
name: testloop
description: >-
  Run one module through the full qmsWrapper test cycle as a closed loop:
  explore it, draft the Validation Test Matrix with `/validation` and the user
  guide with `/howto`, execute the matrix, record the results, reconcile the
  record against the plan, audit the reconciliation against the record, then
  validate that record against the source the build came from, and either
  confirm the iteration or refuse it. Six documents, one version, one run
  directory; every count is computed and every code citation is fetched and
  checked, never asserted; an iteration that does not confirm becomes the
  agenda for the next one.
  Trigger: the user types `/testloop`, or says "run the full test cycle for
  <X>", "test this module end to end", "close the loop on <X>", "validate and
  sign off <module>".
---

# /testloop — one module, one closed test cycle

`/validation` writes the plan. `/howto` writes the user guide. Neither knows
whether the module works, and neither can tell you whether the testing that
happened covered what the plan asked for. This skill is the loop around them:
it executes the plan, records what happened, reconciles the two, audits the
reconciliation, and either confirms the iteration or says why it cannot.

**One iteration produces six documents that share a module, a timestamp and a
version number.** They are not five views of the same thing — each answers a
question the one before it cannot answer about itself:

| | Document | Question it answers | Built by |
|---|---|---|---|
| **A** | Validation Test Matrix | What should be tested? | `/validation` |
| **B** | How-To | Can an ordinary user do it unaided? | `/howto` |
| **C** | Test Results | What happened when the matrix was executed? | `scripts/build_results.py` |
| **D** | Reconciliation | Does the record cover the plan, and what does it say? | `scripts/reconcile.py` |
| **E** | Audit & Confirmation | Is the record strong enough to carry that conclusion? | `scripts/audit.py` |
| **F** | Code Validation | Does the source the build came from support what the record claims? | `scripts/codevalidate.py` |

## The shape of the loop, and why it is this shape

```
   ┌─ 0. explore the module (undirected)
   │        ↓
   │  1. A: /validation matrix     ──→  B: /howto guide
   │        ↓                                ↓
   │  2. execute A, case by case  ←── user feedback
   │        ↓
   │  3. C: test results  (one row per matrix case, incl. the ones nobody ran)
   │        ↓
   │  4. D: reconciliation = A × C   → coverage, outcome, plan gaps, verdict
   │        ↓
   │  5. E: audit = D × C, on different criteria → CONFIRMED or REFUSED
   │        ↓
   │  6. F: code validation = C × source@ref → CONFIRMED or REFUSED
   │        ↓
   └──── REFUSED, or gaps → next iteration at v+1
            CONFIRMED → close
```

Three things about this are deliberate, and undoing them breaks the loop.

**Execution comes after the matrix, not before it.** Exploring first is right —
`/validation` forbids rows that are not grounded in a control you have seen, so
you must look before you can plan. But the *results* must come from executing
the matrix as written, case by case. If you write the matrix from an exploratory
pass and then declare that same pass to be the results, step 4 compares a
document against its own source and always agrees. That is the failure mode this
skill exists to prevent: a loop that certifies itself.

**Step 5 checks something different from step 4.** Comparing the reconciliation
back against the results with the same criteria would recompute the same join
and reach the same answer — a second opinion from the same head. So the audit
asks about the *record's strength* instead: does every Pass have evidence that
actually exists on disk, does every Fail have a reproduction, does the observed
text merely restate what the plan predicted (the tell for a row filled in from
the matrix rather than from the screen), and do the rendered documents still
recount correctly against the spec they came from. A reconciliation can be
arithmetically perfect and still rest on ten rows somebody ticked.

**A–E are all black-box, which is their limit.** The matrix is grounded in
controls the tester saw, the results say what the screen did, the reconciliation
joins them and the audit weighs the record. Not one of them can tell you the
*product* is right — only that the paperwork is. A module can behave exactly as
the matrix specifies while the code underneath is wrong in a way no row thought
to ask about, and the loop will confirm it, correctly and uselessly. Document F
is the different witness: it reads the branch the tested build came from and
asks whether the source supports what the record claims. It has overturned
recorded defects that turned out to be the harness misreading the product, and
settled cases nobody could execute.

**The loop terminates on stated criteria, not on judgement.** `reconcile.py`
applies a fixed gate — full coverage, no regulatory failure, no High-priority
failure, nothing blocked or partial, no High-severity off-plan finding — and
prints PASS or HOLD. `audit.py` recomputes it independently and confirms or
refuses. Both exit non-zero when they do not pass, so the loop can be driven
without reading the prose. Without a stated exit condition, "final confirmation"
means whoever is tired first.

## Preflight — before the first question

```bash
python3 scripts/preflight.py
```

testloop drives `/validation` and `/howto`; it does not contain either of them.
Someone who installed testloop on its own has a working `/testloop` and no
matrix generator, and `install.sh` only said so once, advisorily, at install
time. So check here, where it binds.

| Reported | What it means | What to do |
|---|---|---|
| `/validation` **not installed** | Document A cannot be produced | **Stop.** Give the user the two `/plugin` lines preflight prints, and start again once it is installed |
| no `reference/modules.md` | Module names cannot be checked against the registry | Say so, and confirm the module name with the user before stamping it into filenames |
| `/howto` **not installed** | Document B cannot be produced | Say so and offer the install lines. The user may choose to continue without it — then C, D and E still run, and the iteration simply never tests whether a person can follow the module |

**A missing `/validation` is a stop, not a degradation.** Do not write the
matrix yourself to keep the cycle moving. `/validation` forbids rows that are
not grounded in a control you have actually seen, and that rule is what makes
document A worth executing against; a matrix invented by the model that then
executes it is precisely the self-certifying loop this skill exists to prevent.
C, D and E will not catch it — they read `results.json` and any matrix that
parses, and will render five correctly-named documents and a confident verdict
on top of a plan nobody validated.

## 0. Establish the run

Ask two things before anything else, and only these two:

1. **Which module** — then take its name and filename token from the
   `/validation` registry (`reference/modules.md` in that skill, or
   `build_test_matrix_xlsx.py --list-modules`). Not in the registry? Stop and
   ask. It is **Form Builder** and **Process Builder**, never "Editor".
2. **Where the run directory goes.**

Everything else follows from those. Create the run directory:

```
TestLoop_<Module>_<YYYY-MM-DD>_<HHMM>_v<N>/
  qmsWrapper_<Module>_<date>_<time>_v<N>.xlsx    ← A, from /validation
  qmsWrapper_<Module>_<date>_<time>_v<N>.md
  HowTo/                                          ← B, from /howto
    qmsWrapper_<Module>_<date>_<time>_v<N>.pdf
    qmsWrapper_<Module>_<date>_<time>_v<N>.md
    screenshots/
  results.json                                    ← the record's source
  screenshots/                                    ← evidence for C
  Results_<Module>_<date>_<time>_v<N>.xlsx        ← C
  Results_<Module>_<date>_<time>_v<N>.md
  Reconciliation_<Module>_<date>_<time>_v<N>.xlsx ← D
  Reconciliation_<Module>_<date>_<time>_v<N>.md
  Audit_<Module>_<date>_<time>_v<N>.md            ← E
  codecheck.json                                  ← F's source, stays local
  CodeValidation_<Module>_<date>_<time>_v<N>.xlsx ← F
  CodeValidation_<Module>_<date>_<time>_v<N>.md
```

The five-field house name is unchanged — `<Prefix>_<Module>_<date>_<time>_v<N>`
— only the fixed prefix varies, so everything in one iteration sorts together
and nothing has to be parsed to be understood. **The date, time and version are
stamped once**, from the matrix's own filename, and every derived document
inherits them: the scripts read them off the matrix path so you cannot end up
with four documents timestamped four minutes apart. `v<N>` is the iteration
number, not a draft counter.

## 1. Explore, then plan

Drive the module. Open every screen, click the controls, note which ones behave
oddly — this is where the click-paths and the real warnings come from, and it is
the only honest source for a matrix that may not contain inferred requirements.

Then run **`/validation`** for document A and **`/howto`** for document B. Both
have their own rules and you follow them; this skill does not restate them. Two
things it does add:

- **B is not optional and not decorative.** The how-to is the only part of the
  loop that tests whether a *person* can do the thing, as against whether the
  software permits it. Where a reader had to guess, backtrack or ask a
  colleague, that is a finding, and it belongs in the next matrix revision as a
  case or in the reconciliation's plan gaps. Wire it back in — a how-to that
  gets written and never read closes nothing.
- **B is built from A**, not from a second exploration, so the guide and the
  plan cover the same ground and a reader's failure maps onto a Test ID.

## 2. Execute the matrix

Work the cases in order, as written. For each: perform the steps exactly as the
matrix states them, look at what the product does, and capture evidence.

**Do not improve the steps as you go.** If a case's steps are wrong, that is a
finding about the plan — record the case as `Blocked` or `Partial`, say why, and
fix the matrix in the next iteration. Silently executing a better version of the
test means the plan and the record describe different work.

**Capture evidence for passes, not just failures.** A Pass is the claim that
most needs backing, because nobody goes looking for the screenshot behind a
result they liked. `audit.py` refuses an unevidenced Pass.

**Check the tier before you run the case, not after it fails.** If the row says
`Control` or `Vigilance` and the org you are testing on cannot reach that
feature, the case is `Blocked` — say which plan you were on and what the row
needed. It is not a `Fail`, and it is emphatically not a defect: recording a
gated feature as broken because the test account could not see it puts a false
bug in front of whoever reads the record. A row marked `Tier: Unknown` is the
same situation one step earlier — the plan never established the gate, so settle
it and fix the row at v+1 rather than guessing which plan to test on.

Write outcomes into `results.json` as you go — never at the end from memory. The
schema is in `reference/results-spec.md`; the short version:

```json
{
  "matrix": "qmsWrapper_FormBuilder_2026-08-10_1105_v2.xlsx",
  "environment": "wrapper.example.com — DEV tenant, test data",
  "build": "2026-08-10 nightly",
  "tester": "who or what executed the run",
  "results": [
    {"id": "FORM-01", "status": "Pass",
     "observed": "A form named ZZ-Test appeared and the builder opened on Version: 1.",
     "evidence": ["screenshots/01-create.png"]},
    {"id": "FORM-05", "status": "Fail",
     "observed": "Saving with no edits bumped the revision counter to 2.",
     "repro": ["Open the form", "Click Save without editing"],
     "evidence": ["screenshots/05-revision.png"], "defect": "BUG-441"}
  ],
  "unplanned": [
    {"title": "Created-at and audit trail differ by ~2h",
     "observed": "…", "severity": "Medium"}
  ]
}
```

Statuses are `Pass` / `Fail` / `Blocked` / `Partial` / `Not run`. Cases you
leave out come through as `Not run` — you cannot lose one by omission.

**`observed` is what you saw, in the product's words.** Not the expected result
copied down. The audit measures the two against each other and flags rows that
are ≥90% identical, because that similarity is almost always a row completed
from the plan.

**`unplanned` is for behaviour the matrix does not cover.** It is not a results
row and never becomes one in this iteration — it is a debt against the plan,
carried into the reconciliation and discharged by a new matrix row next time.

## 3–5. Build C, D and E

Three commands, in order, from inside the run directory:

```bash
S=~/.claude/skills/testloop/scripts

python3 $S/build_results.py results.json --auto-name .      # C
python3 $S/reconcile.py     results.json --auto-name .      # D  → exit 1 on HOLD
python3 $S/audit.py         results.json --run-dir .        # E  → exit 1 on REFUSED
```

Add `--require-full-coverage` to both `reconcile.py` and `audit.py` when a case
left un-executed should block the iteration rather than merely be reported.
Use it whenever the run is meant to be a complete pass of the matrix.

All three read the same `results.json` and the same matrix, which is what lets
the audit recount the rendered documents and catch one that was edited after it
was generated. Title, expected result, priority, the regulatory flag and the
tier are copied from the matrix into C — never from the spec — so the record
cannot quietly paraphrase the plan it is being measured against.

**Tier travels with the case.** C and D carry the matrix's `Tier` column, and D
breaks the outcomes down by it beside the per-priority table. That breakdown is
how you catch the failure this loop is otherwise blind to: a column of Blocked
or Not run all sitting in one tier is almost never a broken feature, it is a
test org on the wrong plan, and it should send you back to provisioning rather
than to a defect report. A matrix written before `/validation` grew the column
loads with the tier unstated, prints `—`, and D omits the breakdown entirely —
an old plan still executes, it just cannot tell you this.

Report every path and exit state — nine files by the end of 5a, and three exit
states. Then read D, E and F rather than just quoting their verdicts: the plan
gaps, the advisory findings and the source readings are the part that tells you
what to do next, and none of them is blocking on its own.

## 5a. F: validate the record against the source

A–E never leave the browser. Document F reads the branch the tested build came
from and asks, case by case, whether the source supports what the record says.

```bash
S=~/.claude/skills/testloop/scripts

python3 $S/codevalidate.py codecheck.json --run-dir . \
        --project 11 --ref development2 --build "$BUILD"      # F → exit 1 on REFUSED
```

**Read the code yourself; the script only makes your reading checkable.** What a
file means is a judgement, and it goes in `codecheck.json` as a verdict, a
finding and the lines it rests on. The full schema is in
`reference/codecheck-spec.md`; the short version:

| Verdict | Use it when |
|---|---|
| `Corroborated` | source agrees with the recorded outcome |
| `Strengthened` | source agrees *and* shows something the UI could not — a lockout, a hash, a shared code path |
| `Contradicted` | source says the recorded outcome is wrong |
| `Unsupported` | the record asserts a mechanism the source does not show |
| `Settled` | a `Blocked` or `Not run` case that source answers without executing it |
| `Absent` | the behaviour lives somewhere this repository does not contain |

```json
{"id": "VIG-23", "verdict": "Strengthened",
 "finding": "Every export resolves a reporting-server URL through one dispatcher; the error branches catch only failures the app's own call returns.",
 "citations": [{"path": "frontend/controllers/GeneralController.php", "line": 141,
                "quote": "elseif ($type == 'medwatch')"}]}
```

**Every citation is fetched from the repository and checked.** The file must
exist at the pinned commit, and the quoted text must actually be in it, within
`--slack` lines of where you said. This is the analogue of *no Pass without
evidence*: a confident reading of a file that does not exist is precisely what
an invented answer looks like, and it is the failure mode this step is most
prone to. The gate refuses on an unresolvable citation, on a verdict that claims
source support while citing nothing, and on a `Contradicted` verdict against a
case the record passed.

**Pin the commit, and check it against the build.** The script resolves the ref
to a sha and quotes that, so the document still means something after the branch
moves. Pass `--build` and it compares: reading code the tested build never ran
is the quietest way to reach a confident wrong answer. A mismatch is reported,
not suppressed — sometimes it is the right trade, but it has to be visible.

**Credential:** `--token`/`$GITLAB_TOKEN`, or `--cookie`/`--cookie-file`/
`$GITLAB_COOKIE` from a signed-in browser. GitLab answers unauthenticated API
calls with `404 Project Not Found` rather than 401, so a stale cookie looks
exactly like a wrong project id — the script says so when it sees one.

**What F cannot do.** It cannot confirm the module: it only reads what the
matrix already asked about. It says nothing about a tier the repository does not
contain — an API backend, a reporting server, a database. Record those under
`not_in_repo` with the reason, rather than leaving a silent hole.

**F never rescues a failed iteration, and never fails one on its own.** A
`Contradicted` verdict against a recorded Pass means the *record* is wrong and
the case is re-run at v+1 — it does not flip the case to Fail by decree. A
`Settled` verdict does not turn a `Not run` into a Pass; the case still has to
be executed. Source is a witness, not a substitute for running the test.

## 5b. File the iteration into Wrapper Storage

**Filing is bookkeeping after the fact, and it is optional.** The six documents
are complete and valid whether or not this succeeds, so treat a failure here as a
problem with the step rather than with the run. It needs a Wrapper tenant and an
upload-scoped token; skip it entirely if you have neither.

Run it after `audit.py`, from inside the run directory:

```bash
S=~/.claude/skills/testloop/scripts/publish.py

python3 $S --run-dir . --folder-name "Logs - Mate" --dry-run   # check first
python3 $S --run-dir . --folder-name "Logs - Mate"             # file it
python3 $S --run-dir . --ask                                   # pick elsewhere
python3 $S --list-folders --under "/library/Wrapper"           # show the choices
```

**The standing convention.** Iterations go to
`/library/Wrapper/Validation And How Tos` — that is the default destination, so
`--dest-path` / `--dest-folder-id` are only for filing somewhere else. Inside it,
each module has **one folder named `<module tested> - Mate`**, and the
iteration's files go **directly into it** — no per-iteration sub-folder, because
the stamped filenames already keep iterations apart. `HowTo/` and `screenshots/`
are the only sub-folders.

**Ask for the short name; do not derive it.** The existing folders are
`Settings - Mate`, `Storage - Mate`, `Logs - Mate`, `Approvals - Mate`,
`QMSManual - Mate` — friendlier than the registry tokens they came from
(`SettingsAdministration`, `StorageDocumentManagement`, `Dashboard`). There is no
rule mapping one to the other, so the name is the tester's call: propose one and
confirm it. Without `--folder-name` the script falls back to the run directory's
name and says so, which is almost never what you want here.

**A second iteration of the same module lands in the same folder.** The five
documents carry `_v<N>` so they sit alongside their predecessors, but the
screenshots do not — same filename means a **new revision** of the existing file,
not a second copy. That is usually right, and it is worth knowing before you go
looking for last week's capture.

**To file somewhere else, `--ask`** walks the Storage tree — a number opens a
folder, `s` files into the one you are in, `u` goes up, `q` cancels without
uploading anything. It needs a terminal; with no terminal to ask at — the usual
case when Claude is driving — it refuses and says so rather than picking
somewhere plausible. In that situation run `--list-folders`, put the options to
the user, and pass the id back as `--dest-folder-id`.

`--dry-run` resolves the destination for real before listing the files, so a
mistyped path or a dead id fails there rather than half way through an upload.

It mirrors the run directory into a folder of the same name under the
destination, **keeping the house filenames exactly as the chain produced them**.
Nothing is renamed and nothing is re-organised: `audit.py` recounts the rendered
documents against their own filenames, so a tidied-up copy in Storage would no
longer be the thing that was audited.

| | |
|---|---|
| Uploaded | every file under the run directory, `HowTo/` and `screenshots/` included |
| Left local | `results.json` (`--skip-ext`), because it is the record's *source*, not an output |
| Folders | created idempotently — a re-run reports `existed` and uploads new revisions rather than duplicates |
| Verified | every returned id is re-fetched and checked on name, byte size and folder path |
| Written back | `MANIFEST.md` in the run directory: local path → Storage id, plus the gate verdict at the time of upload |

**A reported id is not proof.** The upload API has been seen to answer
`phase:complete` with an id that does not resolve, so the script verifies each
one and exits non-zero if any fails. Two details that make the check real:
Storage keeps a file's stem and its extension in **separate fields**, so compare
the rejoined name rather than the stem; and the expected folder path is built
from the root folder's own path, never from the record being checked — a check
that reads its expectation off its subject always passes.

**File every iteration, including the ones that did not close.** A HOLD or a
REFUSED is exactly the record worth keeping, and the manifest states the verdict.
Filing only the clean runs would quietly turn the archive into a highlight reel.

Credential: `--token`, else `$WRAPPER_PAT`, else `~/.claude.json`. It needs
`storage:upload` (and `storage:write` for the folders); `storage:delete` is worth
having so a mis-filed run can be removed without going into the web UI. The
script never writes the token anywhere.

## 6. Close, or go round again

**CONFIRMED and PASS** — say plainly what that does and does not mean: the
matrix's cases were executed on the named environment and behaved as specified,
each outcome backed by evidence that exists, the documents agree, and the
source was read where it could speak. It
does not mean the module is correct. Everything outside the matrix is untested,
and the plan gaps in D are the known part of that.

**REFUSED, or HOLD** — the iteration does not close. Sort what came back:

| What came back | Where it goes |
|---|---|
| A case failed | Defect report; the case stays in the matrix and is re-run at v+1 |
| A case was blocked or the steps were wrong | Fix the case — `/validation` at v+1 |
| A case was blocked because the org could not reach its tier | Provision an org on that plan and re-run — the row is right, the environment was wrong |
| A row carried `Tier: Unknown`, or its tier proved wrong | Settle the gate and correct the column — `/validation` at v+1 |
| A case was never executed | Execute it, or cut the row and say why |
| Something observed with no row (`unplanned`) | A new row — `/validation` at v+1 |
| A reader of the how-to had to guess | A new row, and a `/howto` revision |
| The audit found thin evidence | Re-run that case properly; do not edit the record |
| Source contradicts a recorded outcome | The record is wrong — re-run that case at v+1, do not edit it |
| Source settles a case nobody could run | Execute it anyway, or cut the row and cite the source as the reason |
| Source shows behaviour no row covers | A new row — `/validation` at v+1 |

Then bump the version, make a fresh run directory at `v<N+1>`, and go round from
step 1. **Never amend a closed iteration's documents.** A record of a run that
happened is not editable — that is the whole reason it can be evidence. The
iteration before it stays on disk as the account of what was known then.

## Rules

- **Six documents, one iteration, one stamp.** A, B, C, D, E, F share the module
  token, date, time and version. The scripts inherit all four from the matrix
  filename — do not name them by hand.
- **The matrix is executed, not paraphrased.** Results come from working the
  cases as written. If the results and the matrix came out of the same
  exploratory pass, there is no loop, only a document that agrees with itself.
- **Every count is computed.** Coverage, tallies, the gate and the verdict come
  out of the scripts. Never write a number into D or E by hand, and never edit
  either after generation — the audit recounts them and will say so.
- **No Pass without evidence, no Fail without a reproduction.** Both are
  blocking findings, and both are refusals to certify rather than complaints
  about paperwork.
- **No source claim without a citation that resolves.** Document F fetches every
  quotation from the pinned commit and refuses the ones that are not there. A
  file path that looks right is what an invented reading looks like.
- **Pin the commit, and say whether it is the build that was tested.** A ref name
  is not a version. Reading code the tested build never ran is the quietest way
  to be confidently wrong, so the mismatch is printed rather than smoothed over.
- **Source is a witness, not a substitute for running the test.** `Settled` does
  not promote a `Not run` to a Pass, and `Contradicted` does not flip a case to
  Fail by decree — it means the record is wrong and the case is re-run at v+1.
- **`observed` is what the screen did.** Restating the expected result is the
  signature of a row nobody ran.
- **Off-plan observations never become results.** They are plan gaps, and they
  are discharged by a matrix row in the next iteration or by a written reason
  not to have one.
- **The how-to feeds back.** Where a reader had to guess, a case is missing.
  Collect it and carry it into the next matrix revision.
- **The loop terminates on the gate, not on fatigue.** CONFIRMED closes it;
  anything else is the next iteration's agenda. Say which, plainly, and never
  describe a HOLD as a pass with caveats.
- **The module name comes from the `/validation` registry**, character for
  character, in every filename and in the prose of all six documents.
- **Never stand in for a missing skill.** If `/validation` is not installed,
  stop and say what to install. A hand-written matrix keeps the cycle moving and
  destroys the only thing it was measuring.
