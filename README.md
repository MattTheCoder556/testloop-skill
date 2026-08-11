# testloop-skill

`/testloop` — runs one qmsWrapper module through a full, closed test cycle and
either confirms the iteration or refuses it.

Wraps the existing `/validation` and `/howto` skills rather than replacing them:
those two write the plan and the user guide, this one executes the plan, records
what happened, reconciles the record against the plan, audits the reconciliation
against the record, and applies a stated gate.

Five documents per iteration, sharing one module token, timestamp and version:

| | Document | Built by |
|---|---|---|
| A | Validation Test Matrix | `/validation` |
| B | How-To | `/howto` |
| C | Test Results (.xlsx + .md) | `scripts/build_results.py` |
| D | Reconciliation (.xlsx + .md) | `scripts/reconcile.py` |
| E | Audit & Confirmation (.md) | `scripts/audit.py` |

All three scripts read one `results.json`, so every count is computed rather
than asserted — and the audit recounts the rendered documents, catching one that
was edited after it was generated.

## Layout

```
skills/testloop/
  SKILL.md                      the workflow
  reference/results-spec.md     the results.json schema
  scripts/lib.py                matrix loading, house naming, sheet styling
  scripts/build_results.py      C — results spec + matrix → results document
  scripts/reconcile.py          D — coverage, tallies, plan gaps, gate verdict
  scripts/audit.py              E — evidence + integrity checks, confirmation
```

## Install on a new machine

```bash
git clone https://github.com/MattTheCoder556/testloop-skill
cd testloop-skill
./install.sh
```

Idempotent — re-run to upgrade. It installs the skill, installs `openpyxl` if
missing, smoke-tests the three scripts, and checks the two skills testloop
drives rather than replaces. `./install.sh --check` verifies without changing
anything.

**`/validation` is a hard dependency**, not a nice-to-have: without it there is
no module registry and no matrix to execute, so the loop has nothing to start
from. `/howto` is softer — the rest of the loop runs without it, but then
nothing tests whether a person can follow the module unaided.

```
/plugin marketplace add MattTheCoder556/validation-skill
/plugin install validation@validation-skill
```

### As a plugin

`.claude-plugin/` carries the manifests, so the repo doubles as a marketplace:

```
/plugin marketplace add MattTheCoder556/testloop-skill
/plugin install testloop@testloop-skill
```

### Working copy

The live copy is `~/.claude/skills/testloop/`; edit here and re-run
`./install.sh`, or sync directly:

```bash
rsync -a --delete --exclude __pycache__ skills/testloop/ ~/.claude/skills/testloop/
```

## Run

```bash
S=~/.claude/skills/testloop/scripts
python3 $S/build_results.py results.json --auto-name .
python3 $S/reconcile.py     results.json --auto-name .   # exit 1 on HOLD
python3 $S/audit.py         results.json --run-dir .     # exit 1 on REFUSED
```

Add `--require-full-coverage` to the last two when the run is meant to be a
complete pass of the matrix.

## Status

Working and tested end to end against
`NewTest/qmsWrapper_FormBuilder_2026-08-10_1105_v2.xlsx` (both the .xlsx and
its .md twin parse): a messy run yields HOLD / REFUSED with the expected
blocking findings, a clean run yields PASS / CONFIRMED, and hand-editing the
reconciliation's tally or verdict is caught.

### Open question

The gate treats `Blocked` and `Partial` as blocking, on the grounds that an
unknown outcome is not a neutral result. If runs routinely hit environment
blocks that cannot be cleared, that criterion should become advisory by default.
Not decided.
