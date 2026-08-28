# `codecheck.json` — the source readings behind document F

Document C records what the screen did. `codecheck.json` records what the
*source* says about it, one entry per case you actually read code for. The
script fetches every citation from the pinned commit and refuses the ones that
are not there, so this file is a set of claims that get checked — not notes.

You do not have to cover every case. Cover the ones where source can change or
strengthen the answer: the failures, the blocked and not-run cases, the starred
regulatory rows, and any Pass whose mechanism you could not see from the UI.

## Shape

```json
{
  "base": "https://gitlab.example.com",
  "project": 11,
  "ref": "development2",
  "build": "v.10.3064.ce9870f50_debug",

  "checks": [
    {
      "id": "VIG-23",
      "verdict": "Strengthened",
      "finding": "Every export resolves a reporting-server URL through one dispatcher and returns it as JSON for the browser to open. The error branches catch only failures the app's own call returns, so a URL that resolves and then fails in the new tab has no in-app error path.",
      "citations": [
        {"path": "frontend/controllers/GeneralController.php", "line": 141,
         "quote": "elseif ($type == 'medwatch')"}
      ]
    }
  ],

  "not_in_repo": [
    {"topic": "SLA band thresholds",
     "why": "computed by the API tier; the frontend renders whatever band it is given"}
  ]
}
```

`base`, `project`, `ref` and `build` may be given here or on the command line;
the flags win.

## Fields

| Field | Rule |
|---|---|
| `id` | A Test ID from the matrix this iteration was built against. An id the matrix does not contain is reported as advisory, not silently accepted. |
| `verdict` | One of the six below, exactly. |
| `finding` | What the source says, in your words — the reasoning the citation supports. Not a restatement of the code. |
| `citations` | `{path, line, quote}`. `path` is repo-relative. `quote` must be text that is really in the file; `line` is a hint checked to within `--slack` lines (default 25), because files drift. |
| `not_in_repo` | `{topic, why}` for anything this repository cannot answer. Write it down rather than leaving a silent hole. |

## Verdicts

| Verdict | Use it when | Needs a citation |
|---|---|---|
| `Corroborated` | source agrees with the recorded outcome | yes |
| `Strengthened` | source agrees **and** shows what the UI could not — a lockout, a hash, a shared code path | yes |
| `Contradicted` | source says the recorded outcome is wrong | yes |
| `Unsupported` | the record asserts a mechanism the source does not show | yes |
| `Settled` | a `Blocked` or `Not run` case that source answers without executing it | yes |
| `Absent` | the behaviour is not in this repository at all | no |

## What makes the document REFUSE

- a citation whose file does not exist at the pinned commit;
- a citation whose quote is not in that file, or sits more than `--slack` lines
  from the line claimed;
- a verdict that claims source support while citing nothing;
- a `Contradicted` verdict against a case the record marked `Pass` — the record
  and the source cannot both stand, so the iteration does not close.

## Two things this file is not

**Not a second execution.** `Settled` does not promote a `Not run` case to a
Pass. The case still has to be run; source only tells you what to expect and
sometimes that the test is worth cutting.

**Not a verdict on the module.** F reads only what the matrix already asked
about. Everything outside it is as untested after F as before, and a tier this
repository does not contain — an API backend, a reporting server, a database —
is not covered by any verdict here. That is what `not_in_repo` is for.
