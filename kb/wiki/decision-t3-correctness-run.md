# Decision — the correctness run failed, and what happens because of it

**Status:** decided · **Ruled by:** Evan, 2026-08-23 05:08 UTC · **Recorded as:** GA-7,
`scope_confirmed: true` · **Ticket:** T-3 · **Supersedes nothing; extends
[decision-expr-to-sql.md](decision-expr-to-sql.md)**

## The question

T-1 ruled *don't build the compiler into GIMS yet; fund two experiments and let a build be earned
from their results.* T-3 was the first of the two: **does the restricted expression subset ever
return a wrong number?** The bar was fixed before any evidence existed — **zero wrong answers**, at
each of three Postgres output settings, reported separately.

## The answer

**It failed, at all three settings** — and not because of the guard defect everyone expected. That
one was fixed first (a range literal 297 digits where it needed 309, silently turning every finite
value above ~1.8e296 into a null) and confirmed *not* to be the cause. Two other mechanisms did it:

1. **The Unicode-digit coercion gap**, which survives even the setting production would pin.
   `float("１２３")` is `123.0` in Python and `NULL` in SQL, so `coalesce(min($.b), 0.1)` returns
   **0.1** where Python says **123.0**. It **falsified the framing's own prediction** that
   restricting constructs would drive the batteries to zero — the gap is not in any construct, it
   lives in the shared string-to-number routine every construct passes through.
2. **Value-channel truncation** above ≈4.16e9. At the lowest setting, `$.ts + 0` on GIMS's largest
   real stored value returns **1,787,169,706,040** instead of **…037**.

Counts: 39+16 wrong at efd 1, 101+15 at efd 0, 105+16 at efd −3. Class 3 zero, unexplained raises
zero, NULLNESS zero. Raw mode added a **class-4** — a ninth, previously uncatalogued site where
Python's own evaluator raises while SQL answers cleanly.

## THE RULING

> **"Homework first, then fix-and-re-run."**

Evan took the synthesis's recommendation, from a form listing all four options with the honest case
for each. In order:

1. **The homework, first and cheapest.** A **read-only sweep of the real data for strings containing
   non-ASCII digits**, plus a one-question inventory: *is anything other than the GIMS Python process
   ever going to write rows autoSQL reads?* Hours of work, touches nothing.
2. **Then the cheap form of fix-and-re-run.** Pin `extra_float_digits = 1` per session. Convert the
   Unicode-digit gap into a **named refusal** — it cannot cheaply be made to *match* Python, and
   under the standing ruling a loud refusal is an allowed outcome where a silent wrong number is not.
   Put the container comparison-rule question back to Evan as its own one-line decision.
3. **Re-run the same batteries against the same unchanged zero bar.** Same instruments, same target.
4. **Hold T-4 until the re-run reports.** His own ordering — correctness before speed — and a failed
   correctness path leaves less worth timing.

**Not abandoned. Not accepted with a carve-out.**

## Why this and not the others

The failure is **narrow and structured**, not diffuse: one mechanism survives the pinned setting on
ordinary data, one is cured by a configuration pin, one is partly a defect of the comparison rule,
and one is contingent on writers that do not exist yet. That is a shape with treatments — and the
treatments are mostly **conversions to loudness rather than silent patches**, which is the design
philosophy already ruled for.

**The homework goes first because the alternatives rest on the same missing fact.** Abandoning
because of a mechanism whose trigger may never occur in this data, and accepting a carve-out for a
trigger that may be common, are both bets on the unmeasured prevalence of non-ASCII digits. Hours of
read-only sweeping buys that fact before any bigger money moves.

## What this does NOT settle — carried forward honestly

- **The GIMS gate stays shut.** Nothing enters GIMS until T-3 *and* T-4 pass. A passed re-run buys
  admission to the speed run, **not to GIMS**.
- **Speed is untouched.** T-4 has not run at all; T-1's 3.8×–7.2× measurement stands unrefined.
- **The recommendation's own weakest point, restated:** if the sweep finds non-ASCII digits are
  *common*, the fix turns those cases from silent wrong numbers into **frequent visible refusals** —
  correct by the bar, but potentially a worse product than a properly narrowed language or stopping.
  **That is the trigger to revisit this ruling**, and it is one line to overturn.
- **Whether a repaired runtime passes is unknown.** This run twice found mechanisms nobody predicted.

## Consequences already applied

- **The demo (T-2) adopts the corrected runtime** — Evan's form answer q4, *"Adopt it — update the
  four criteria."* The demo had been pinning the pre-fix 427-line `runtime.sql` so its signed
  criteria kept meaning what they said; it now moves to T-3's corrected version, and B15, B24, AC-13
  and AC-17 are amended to match. **Note the interaction:** step 2 above will change the runtime
  *again*, so the demo will need a second update after the re-run. He was told this and chose adopt.
- **T-4 remains framed and unstarted**, waiting on a quiet-machine window he has not yet named
  (form answer q7 said *"see my notes"*, and the notes box was empty).

## Evidence

`spikes/T-3/FINDINGS.md` (599 lines) · 29 raw outputs in `spikes/T-3/out/` ·
`spikes/T-3/SYNTHESIS.md` (406 lines — the four options and the recommendation) ·
`spikes/T-3/FRAMING.md` (751 lines — the bar, fixed before any evidence) ·
the decision form at `https://claude.ai/code/artifact/79700309-4e45-45fa-9d4e-998a5f5c51fb`

**Evidence integrity:** `spikes/T-1/FINDINGS.md` is untouched (sha256 `bcda73d6…`, matching its
recorded digest), but T-1's numbers can no longer be reproduced byte-identically from the current
instruments — they now carry T-3's guard fix. Reproducing T-1 exactly requires a checkout of
`01e75b0`.
