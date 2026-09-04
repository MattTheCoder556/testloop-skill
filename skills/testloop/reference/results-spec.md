# `results.json` — the record's source

One file per iteration, living in the run directory beside the matrix it was
executed against. All three scripts read it; nothing else is a source of truth
about what happened.

Write it **as you execute**, one entry per case, not at the end from memory. The
whole chain rests on this file being an account of what was seen.

## Schema

```json
{
  "matrix": "qmsWrapper_FormBuilder_2026-08-10_1105_v2.xlsx",
  "sheet": "Form Builder",
  "environment": "wrapper.example.com — DEV tenant, test data",
  "tier": "Foundation",
  "build": "2026-08-10 nightly",
  "tester": "Claude Code, driven session",
  "date": "2026-08-10",

  "results": [
    {
      "id": "FORM-01",
      "status": "Pass",
      "observed": "A form named ZZ-Test appeared in the list and the builder opened on Version: 1.",
      "evidence": ["screenshots/01-create.png"],
      "repro": ["Open Forms", "Click + Create Form", "Enter a name and prefix"],
      "defect": "BUG-441",
      "notes": "Prefix field accepted lowercase and upper-cased it silently."
    }
  ],

  "unplanned": [
    {
      "title": "Created-at and audit trail differ by about two hours",
      "observed": "The forms list showed 09:14; the audit trail entry for the same event showed 11:14.",
      "evidence": ["screenshots/u1-timestamps.png"],
      "severity": "Medium",
      "action": "Add a matrix row covering timestamp consistency"
    }
  ]
}
```

## Top level

| Field | Required | Notes |
|---|---|---|
| `matrix` | yes* | Path to the Validation Test Matrix `.xlsx` or its `.md` twin, relative to this file. `--matrix` overrides it. |
| `sheet` | only for multi-sheet workbooks | The tab this iteration covers. |
| `environment` | yes | Where it ran. A result with no environment cannot be reproduced or challenged. |
| `tier` | yes | The plan the org was on: `Foundation` \| `Control` \| `Vigilance`. Asked at step 0, in the product's vocabulary, never as a number. This is what every `Blocked` row is justified against — without it, "the org couldn't reach it" is an assertion nobody can check. Not to be confused with the matrix's per-row `Tier`, which is the gate a feature sits behind. |
| `build` | recommended | Which build. Without it, a fix cannot be tied to a re-run. |
| `tester` | recommended | Who or what executed the run. |
| `date` | optional | Run date, if not the matrix's stamp. |
| `results` | yes | One entry per executed case. |
| `unplanned` | optional | Behaviour seen that no matrix row covers. |

## A `results` entry

| Field | Required | Notes |
|---|---|---|
| `id` | yes | A Test ID that exists in the matrix. An unknown id stops the build — it is a typo, or the case belongs in `unplanned`. |
| `status` | yes | `Pass` \| `Fail` \| `Blocked` \| `Partial` \| `Not run`. Common synonyms (`passed`, `skipped`, `n/a`, …) are accepted and normalised. |
| `observed` | yes for Pass/Fail/Partial | What the screen did, in the product's own words. Not the expected result copied down — the audit flags text ≥90% identical to `expected`. |
| `evidence` | yes for Pass | Paths (relative to the run directory) or URLs. The audit checks that local paths resolve. |
| `repro` | yes for Fail | Ordered steps someone else can follow to see the same failure. |
| `defect` | recommended for Fail | The defect id. Without it the failure exists only in this document. |
| `notes` | optional | Anything a reader of the record would want and the columns do not hold. |

**Cases you omit are not lost.** Every matrix row appears in the results
document; the ones with no entry come through as `Not run` and are counted as a
coverage gap.

**Never invent a status to make the gate pass.** `Blocked` and `Partial` exist
precisely so that "we could not find out" has somewhere honest to live.

## An `unplanned` entry

| Field | Required | Notes |
|---|---|---|
| `title` | yes | One line naming the behaviour. |
| `observed` | yes | What happened. A title alone cannot become a test case. |
| `evidence` | recommended | Same rules as a result's. |
| `severity` | recommended | `High` / `Critical` blocks the iteration; anything else is reported. |
| `action` | optional | What the next matrix revision owes. Defaults to "add a row, or record why not". |

These are **not results**. They have no Test ID because no case planned them,
and giving them one here would mean the record contains cases the plan does not.
They are debts against the matrix, discharged at the next `/validation` revision.

## Statuses, and what each one commits you to

| Status | You are saying | The audit will require |
|---|---|---|
| `Pass` | The case behaved as the matrix specified | An observation and evidence that exists |
| `Fail` | It did something else | An observation and reproduction steps; a defect id is advisory |
| `Blocked` | You could not execute it | A reason, in `observed` or `notes` |
| `Partial` | Some steps ran, the outcome is unknown | A reason, as above |
| `Not run` | Nobody attempted it | Nothing — but it counts against coverage |

`Blocked` and `Partial` both block the gate. That is intentional: an unknown
outcome is not a neutral result, and a loop that closes over unknowns is not
closing anything.
