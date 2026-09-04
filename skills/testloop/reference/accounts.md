# Run accounts

One account per entitlement tier. Step 0 of `SKILL.md` asks the user which
**tier** an iteration is executed on and resolves the login from this table.
**The user is never asked to pick an account by name** — they are asked for the
tier, which is what the record states and what makes a `Blocked` row defensible
later.

| Tier | Plan name | Account | Org |
|---|---|---|---|
| 1 | Foundation | `<fill in>` | `<fill in>` |
| 2 | Control | `<fill in>` | `<fill in>` |
| 3 | Vigilance | `<fill in>` | `<fill in>` |

## No credentials in this file

It ships with a published plugin. Record only the identifier needed to pick the
right session — the passwords live wherever the rest of the test logins are
kept, and never here.

## Two different tier questions

The tier in the **matrix** is the entitlement gate a feature sits behind: a
property of the module, one per row, set by `/validation`. The tier of the
**run** is the plan the test org is on: a property of the environment, one per
iteration, asked here. They are compared in step 2, and a row whose gate is
above the run's plan is `Blocked` rather than `Fail`.

Keeping them apart is the whole point. A matrix written for a Vigilance feature
is correct; running it on a Foundation org is a provisioning fact about the run,
not a defect in the module.

## The tier names

**Tier 1 = Foundation, Tier 2 = Control, Tier 3 = Vigilance.** Write the plan
name into `results.json`, not the number — it is read by people who recognise
*Control* on an invoice and have never seen "Tier 2".

## Keeping it current

Accounts get recreated more often than tiers get renumbered, which is the whole
reason the question is worded by tier: a rotated login is a one-line edit here
and no change to `SKILL.md`. Add a row rather than repurposing one if a fourth
tier appears.

## If a tier has no working account

Say so and hold the run. Do not execute on a neighbouring tier: the run tier is
what every `Blocked` row is justified against, so a record that names a plan the
run was not actually on is worse than no record.
