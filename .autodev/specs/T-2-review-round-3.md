# T-2 · auto-review round 3 — CLEAN

Scope: `git diff 950b36d..HEAD` — 4 files (`legality.py`, `server/app.py`, `tests/test_vendor.py`,
`tests/test_isolation.py`), ~452 insertions. **No defects found.**

The brief was pointed: this build's recurring pattern is **guards that look thorough and cannot
fail**, and it had appeared twice. Round 3's primary job was to find out whether it had appeared a
third time wearing the costume of a generative sweep.

## It had not — and that was PROVEN, not asserted, three independent ways

1. **The completeness test genuinely fails when a slot is added.** `legality.default_pick()` was
   monkeypatched to return an extra key;
   `test_the_malformed_pick_schema_covers_every_slot_of_the_pick` went **PASS → FAIL** with the exact
   *"schema no longer matches the pick's pinned slots"* message. The table cannot silently fall behind
   the pick it is supposed to cover.
2. **The pick sweep genuinely reaches the crash sites.** The **pre-diff holder-only**
   `shape_violations` was reconstructed from git at `950b36d` and monkeypatched back in; re-running the
   177-case sweep turned **24 cases red**, one of them a real 500. **That is precisely the defect class
   round 2's enumerated test stayed green through.** Against current code all 177 resolve to 200/422
   with **zero 500s**, and all 153 type-illegal cases refuse through the shape guard naming their own
   operation — the layer-1 escape hatch is never taken.
3. **The isolation sweep is non-vacuous.** `_spellings_of` derives 14 spellings; **13 non-canonical
   ones reach 200**, all stripped, all byte-identical at 16,412 bytes — so the anti-vacuity assertion is
   robustly satisfied, and all five of round 2's measured bypasses are in the generator's output, making
   the subset assertion real. Driven as raw ASGI scopes, so no client-side dot-segment collapse hides
   them; confirmed to match `curl --path-as-is`.

## Everything else attacked, and holding
- **Directory traversal is prevented at every spelling** — `/vendor/../static/demo.css`,
  `/vendor/styles/../../static/demo.css`, `/vendor/../../etc/passwd`, `%2e%2e`, `..%2f`, `....//` all
  404. No symlinks in `demo/vendor`; `follow_symlink` defaults False behind a realpath/commonpath fence.
- **The override signature matches Starlette 1.6.0 exactly** — the installed version calls
  `self.file_response(full_path, stat_result, scope)`, three positional, which is what the subclass
  declares. It decides on the **resolved** suffix, so no request spelling can make a `.css` resolve to a
  non-`.css` decision.
- **`shape_violations` refuses nothing legitimate.** Valid picks of every shape — ROWS/SCALAR/BUCKET,
  computed name+expr, filter, sort field+dir, cap, aggregate sum+field, count with null/absent field,
  bucket+aggregate, window field, changed true/false, `aggregate.field=null` — **all 200 accepted.** The
  single 422 seen (`sort` with a field but no dir) comes from a pre-existing closed-set check present at
  `950b36d`, untouched by this diff and unreachable from the screen.
- **The cap type/range split** — a genuine "subtly wrong number" candidate, since the type check moved
  to `shape_violations` while the range check stayed in `evaluate` with an inverted boolean. Verified
  live at the boundaries: 1 and 20000 accepted; 0 and 20001 range-refused; `True`/`False` (**the
  bool-is-int trap**), `2.5`, `"5"`, `[]`, `{}` all type-refused. Exactly one violation per case —
  **no gap and no fall-through** between the two checks.
- **No regressions.** Full suite rerun: **1133 passed, 10 skipped, 0 failed.** `1e400` still gives a
  layer-1 named refusal (construct `"inf"`); the empty-array ordering pick still returns
  **verdict=agree, 0 differing**, live. No lingering references to the three deleted names.

## Two honest non-findings, recorded rather than inflated
The CSS response through the subclass returns a plain `Response`, dropping ETag/304 conditional
handling — the round-1 route did the same, so no regression, and it is a caching nicety. And a
malformed cap on a SCALAR pick can attract a second, redundant "unavailable" violation — both refusals
are honest 422s. **Neither is a defect**, and the reviewer said so rather than padding the round.

EVIDENCE: round-3 review of feat/T-2-demo diff 950b36d..HEAD (4 files) — NO DEFECTS. The generative sweeps proved load-bearing three ways: the completeness test fails when a slot is added (monkeypatch), a reconstructed holder-only shape_violations turns 24 sweep cases red (the class round 2's enumerated test could not see), and 13 non-canonical spellings reach the isolation assertion non-vacuously. Traversal blocked at every spelling; file_response signature matches Starlette 1.6.0; every valid pick shape still accepted; cap boundaries correct with the bool-is-int trap closed; suite 1133 passed / 10 skipped / 0 failed with the ordering fix and the 1e400 named refusal reconfirmed live
