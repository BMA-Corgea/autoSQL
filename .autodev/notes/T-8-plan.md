# T-8 plan — order of work, and where it can go wrong

Test-first throughout: each step's test is written and seen failing before its code.

## Step 1 — the template and the generator (AC-3, AC-4)
`runtime/runtime.sql.in` is T-1's proto verbatim except the coercion branch, which carries
`{{ND_MAP_FROM}}`, `{{ND_MAP_TO}}`, `{{PY_WS}}`. `runtime/generate.py` derives all three from the
running `unicodedata` and writes `runtime/runtime.sql`.

**Where it goes wrong:** `btrim` takes a literal character LIST, not a pattern — T-6 shipped that bug
once and a probe caught it. The whitespace set is emitted as 29 individual escapes, never ranges.
The `translate()` from/to sets must be the same length; assert it in the generator.

## Step 2 — the standing tests (AC-2, AC-3, AC-4, AC-5)
Promote T-6's `P0` and `P1` probes from one-off spike scripts into `runtime/tests/`, run against a
throwaway container. Add the drift test (regenerate, compare bytes) and the structural test that
`translate(` appears **inside** the failure branch, not above the ASCII gate.

**Where it goes wrong:** a timing assertion on a shared machine is flaky. AC-5's budget is a loose
1.5× of a baseline measured in the same run, not an absolute millisecond figure.

## Step 3 — install and prove (AC-1)
Throwaway container on 55434, install, count 21 functions, run the promoted tests.
**Never 55433.**

## Step 4 — re-vendor (AC-6)
Copy to `demo/vendor/runtime.sql`, update `demo/manifest.json`, correct `demo/vendor/NOTICE.md` —
which today claims everything under `vendor/` came from a GIMS checkout, never true of this file.

## Step 5 — step 11 (AC-7)
Re-point to `edge-03`'s magnitude refusal. Four places: `SEVEN_STATES["disagree"]`,
`ACCEPTED_PICKS["the disagreement"]`, `test_walkthrough.py::test_ac22_*`, and
`demo/expected-answers.json` (regenerate via `python -m demo.seed.expectations`).

**Where it goes wrong — the one to watch.** The state's *name* is `disagree` and its expected verdict
is `"disagree"`. A refusal is `no-compare` with `accepted: False`. So this is not a value swap: the
state's whole shape changes, and `test_the_disagreement_state_is_located_and_not_merely_announced`
asserts a differing row that will no longer exist. **Re-point it at what now happens; do not weaken
it.** AC-22's own text — *"if the two panes ever agree here … the build is not accepted"* — must be
amended in the spec, not quietly broken.

## Step 6 — the frozen-file check (AC-8)
Assert the three spike runtimes still hash to their recorded values. This is the guard against the
single worst outcome of this ticket: editing evidence.

## Rollback
`demo/vendor/runtime.sql` pinned back to its pre-T-8 bytes restores the demo Evan accepted.
