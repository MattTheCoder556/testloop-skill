---
name: testloop
description: >-
  Run one module through the full qmsWrapper test cycle as a closed loop:
  explore it, draft the Validation Test Matrix with `/validation` and the user
  guide with `/howto`, execute the matrix, record the results, reconcile the
  record against the plan, then audit the reconciliation against the record and
  either confirm the iteration or refuse it. Five documents, one version, one
  run directory; every count is computed, never asserted; an iteration that does
  not confirm becomes the agenda for the next one.
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

**One iteration produces five documents that share a module, a timestamp and a
version number.** They are not five views of the same thing — each answers a
question the one before it cannot answer about itself:

| | Document | Question it answers | Built by |
|---|---|---|---|
| **A** | Validation Test Matrix | What should be tested? | `/validation` |
| **B** | How-To | Can an ordinary user do it unaided? | `/howto` |
| **C** | Test Results | What happened when the matrix was executed? | `scripts/build_results.py` |
| **D** | Reconciliation | Does the record cover the plan, and what does it say? | `scripts/reconcile.py` |
| **E** | Audit & Confirmation | Is the record strong enough to carry that conclusion? | `scripts/audit.py` |

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
was generated. Title, expected result, priority and the regulatory flag are
copied from the matrix into C — never from the spec — so the record cannot
quietly paraphrase the plan it is being measured against.

Report all seven paths and the two exit states. Then read D and E rather than
just quoting their verdicts: the plan gaps and the advisory findings are the
part that tells you what to do next, and neither is blocking.

## 6. Close, or go round again

**CONFIRMED and PASS** — say plainly what that does and does not mean: the
matrix's cases were executed on the named environment and behaved as specified,
each outcome backed by evidence that exists, and the five documents agree. It
does not mean the module is correct. Everything outside the matrix is untested,
and the plan gaps in D are the known part of that.

**REFUSED, or HOLD** — the iteration does not close. Sort what came back:

| What came back | Where it goes |
|---|---|
| A case failed | Defect report; the case stays in the matrix and is re-run at v+1 |
| A case was blocked or the steps were wrong | Fix the case — `/validation` at v+1 |
| A case was never executed | Execute it, or cut the row and say why |
| Something observed with no row (`unplanned`) | A new row — `/validation` at v+1 |
| A reader of the how-to had to guess | A new row, and a `/howto` revision |
| The audit found thin evidence | Re-run that case properly; do not edit the record |

Then bump the version, make a fresh run directory at `v<N+1>`, and go round from
step 1. **Never amend a closed iteration's documents.** A record of a run that
happened is not editable — that is the whole reason it can be evidence. The
iteration before it stays on disk as the account of what was known then.

## Rules

- **Five documents, one iteration, one stamp.** A, B, C, D, E share the module
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
  character, in every filename and in the prose of all five documents.
- **Never stand in for a missing skill.** If `/validation` is not installed,
  stop and say what to install. A hand-written matrix keeps the cycle moving and
  destroys the only thing it was measuring.
