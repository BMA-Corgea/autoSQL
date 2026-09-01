# The correctness re-run passed — and found a better fix than the one that was ruled

**Status:** synthesis + recorded verdict · **Ticket:** T-6 · **Written:** 2026-09-01 ·
**Authority:** GA-10 (*"Go to T-6. Go ahead and loop through the tickets. Try to use your best
judgement instead of asking me for any others"*) · **Extends
[decision-t5-homework.md](decision-t5-homework.md) and
[decision-t3-correctness-run.md](decision-t3-correctness-run.md)**

> **The headline, in one line:** the re-run **passes** — zero wrong numbers at the pinned setting
> across 11,367 expressions — **and one of T-3's own premises turned out to be false**, which buys a
> fix that is strictly better than the one you signed off.

---

## What was asked

T-3 found the compiled SQL returns wrong numbers and ruled *"homework first, then fix-and-re-run."*
T-5 was the homework and came back clean. T-6 is the fix and the re-run, judged against the **same
unchanged bar**: zero wrong answers, three Postgres float settings, reported separately.

## What came back

**PASS at the pinned setting.** At `extra_float_digits = 1`, across three batteries and 11,367
expressions: **zero wrong numbers**, zero unexplained raises, zero nullness violations. The 130-case
contract fixture is 130/130 at all three settings. T-3's 55 divergences at this setting are gone.

Two things are worth more of your attention than the pass itself.

### 1. The refusal you signed off costs three times what it fixes

The ruled fix converts the Unicode-digit gap into a **loud refusal**. Built and measured, it works —
but it refuses at the moment a value is *read*, and at that moment nothing yet knows whether the
value will matter to the answer. So:

| | |
| --- | ---: |
| refusals it raises | **86** |
| of those, replacing a **silent wrong number** — a straight win | **26** |
| of those, replacing an answer that was **already correct** | **60** |

Those 60 are expressions where the bad `NULL` was absorbed downstream — another term dominated a
`max()`, a comparison went the same way regardless. Both engines agreed. Under the ruled fix, SQL
now raises instead. **That is 86 queries that stop working to fix 26 that were wrong.**

### 2. T-3's premise was wrong — SQL can just *match* Python, for free

Both T-3's ruling and this ticket's charter rest on one sentence:

> *"It cannot cheaply be made to match Python — Postgres regexes have no equivalent of Python's
> any-Unicode-digit class — so the generated SQL raises a named error."*

The first half is true, and was re-confirmed independently. **The conclusion does not follow.**
Matching Python does not need a digit *class*; it needs a digit *mapping*. Python's `float()`
accepts `１２３` because it reads each character's **numeric value** — so mapping the 670 non-ASCII
digit code points onto `0`–`9` with one `translate()` call reproduces Python exactly, and there is
nothing left to refuse.

It was built and run through the same batteries, seeds and fixture.

---

## The options

| | **A — refuse** (as ruled) | **B — translate, unguarded** | **C — translate, guarded** |
| --- | --- | --- | --- |
| wrong numbers at efd 1 | **0** | **0** | **0** |
| refusals raised | 86 | 0 | 0 |
| correct answers lost | **60** | 0 | **0** |
| contract fixture | 130/130 | 130/130 | 130/130 |
| cost, 300k ordinary coercions | 853 ms | **4553 ms** | **812 ms** |

*(Baseline, unfixed: 852 ms.)*

**A — refuse.** What T-3 ruled and you re-confirmed. Correct by the bar. Costs 60 working queries,
and every one of those is a user seeing an error where they used to see a right answer.

**B — translate, unguarded.** Fixes everything, but runs the 670-character mapping on *every* string
it ever coerces: a **5.3× tax on ordinary numbers**. That matters more here than it sounds, because
T-5 found that in your LIMS project **every number-declared field is stored as text** — so coercion
is the common path, not an edge case.

**C — translate, guarded.** Same fix, but the mapping only runs *after* the plain-ASCII check has
already failed. Ordinary numbers never touch it. **812 ms against an 852 ms baseline — no
measurable cost at all** — and it loses nothing.

---

## Recommendation, and what was recorded

**Recommended and adopted: C.** It dominates A on every measured axis: same zero wrong numbers, no
refusals, no lost answers, no performance cost.

**This is a deviation from the mechanism you ruled, and it is flagged rather than buried.** Your
GA-9 Q1 answer was *"A — proceed as ruled"*, and "as ruled" included the named refusal. That design
was chosen **because matching was believed impossible**. It isn't. Adopting C follows your own
stated preference ordering — a correct answer beats a refusal, a refusal beats a silent wrong number
— applied to a fact nobody had when the ruling was made. **One line from you puts A back.**

**The verdict itself (PASS) was recorded on this seat's authority**, as T-6's framing reserved
before any evidence existed: a pass is a factual verdict against a fixed bar with both numbers
published. A *failure* would have gone back to you, and did not need to.

## What this does NOT settle

- **The GIMS gate stays shut.** A passed re-run buys admission to **T-4, the speed run**, and
  nothing else. T-4 has still never run.
- **The pass depends entirely on the float setting being pinned to 1.** At 0 and −3 there are still
  **62 and 66** wrong numbers — a different mechanism (truncation), which the pin cures. **Nothing
  yet enforces the pin.** That is a build item, not a finished thing.
- **The comparison rule changed**, and that was this seat's call too. The test rule that decides
  pass/fail never descended into lists, so jsonb's exact `10¹⁸¹` and Python's `1e181` compared
  unequal *inside* a list while the identical pair passed as a scalar. It now recurses; the
  tolerance is untouched. Every battery published **both** numbers, and all **29** cases the change
  absorbed were verified individually as that one shape.
- **The mapping table is generated, and nothing re-generates it.** A Unicode version bump needs it
  rebuilt, and no build step does that today.
- **`raw`-mode data was not re-run**, and no mutation testing was done in this pass.

## Evidence

`spikes/T-6/FRAMING.md` (the bar, fixed before evidence) · `spikes/T-6/FINDINGS.md` (+ its addendum,
marked as produced at synthesis) · `spikes/T-6/out/` — 42 battery runs, 5 fixture runs, controls,
domain gate · `spikes/T-6/probes/` — 5 re-runnable probes · `spikes/T-6/runtime{,-variantB,-variantC}.sql`

**Read-only attestation:** every run used a throwaway `pg16` container on port **55434**, destroyed
afterwards. `glp_strong` on 55433 was never contacted, and the fail-closed guard on that port is
untouched. Nothing in GIMS was changed (your Q3 park).
