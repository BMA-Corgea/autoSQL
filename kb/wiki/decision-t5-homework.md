# Decision — the homework reported, and the ruling stands

**Status:** decided · **Ruled by:** the owner, 2026-09-01 · **Recorded as:** GA-9 · **Ticket:** T-5 ·
**Extends [decision-t3-correctness-run.md](decision-t3-correctness-run.md); supersedes nothing**

## The question

T-3 ruled *"homework first, then fix-and-re-run"* and named its own trigger to be overturned: **if
non-ASCII digits turn out to be common in real data, the chosen fix converts silent wrong numbers
into frequent visible refusals**, and narrowing the language or stopping become the honest choices
instead. T-5 was that homework. The bar — four bands, ZERO / RARE / PRESENT / COMMON, against a
denominator of *coercible* strings — was fixed in writing before any evidence existed
(`spikes/T-5/FRAMING.md` §9).

## The answer

**Band ZERO, and the trigger did not fire.** Nothing found, in a corpus that could have carried it.

- **0 of 144** coercible strings, tier A and tier B both zero, across 38,457 rows / 1,141,929
  strings in 8 read-only SQLite stores. **Four independent instruments now agree** (T-1 ran three;
  T-5 added a fourth, 11 days and ~1,379 rows later).
- **The zero is load-bearing:** 48,297 strings carry *other* non-ASCII characters, so the corpus was
  not ASCII-only.
- **But the published denominator overstated it ~7,600×.** T-1's headline "0 of 1,096,202" counts
  every string and object key, most of which can never coerce. The decision-relevant base is **144**,
  of which **137** sit in the one tenant project.
- **And the trigger is reachable by design.** GIMS's own CSV/XLSX import admits **8 of 10** tested
  non-ASCII digit forms straight into number-declared fields, because the gate meant to enforce
  *"this field is a number"* (`core/words/validation.py:88-97`) is bare `float(str(value))`, which
  accepts all 670 non-ASCII `Nd` digits. All 6 number-declared fields that carry rows hold **strings**,
  so this coercion path is how every number in the project is read.

**It has not happened. Nothing stops it happening.**

## THE RULING

> **"A - proceed as ruled."**

The owner took the synthesis recommendation from a form listing four options with the honest case for
each, answering all six questions and accepting every recommendation. In full:

| | question | ruling |
|---|---|---|
| **Q1** | Does T-3's ruling stand? | **A — proceed exactly as ruled.** Harden autoSQL to refuse loudly, re-run the batteries against the unchanged zero bar. |
| **Q2** | Should autoSQL count its own refusals? | **Yes — build it into T-6.** |
| **Q3** | The GIMS-side validator fix | **Park it.** Revisit if a refusal ever fires. |
| **Q4** | T-2's missing disagreement | **Seed a new one using T-5's witness** — a non-ASCII digit row. |
| **Q5** | When T-4 gets the machine | **After T-6 reports.** His own ordering, re-affirmed. |
| **Q6** | The `Glove.size` write path | **Log it as a ticket; don't chase it now.** |

## Why this and not the others

**The homework did its job: it priced the risk the ruling was betting on, and the bet was good.** A
refusal that fires on a value occurring zero times regresses nothing that exists today. That is the
whole case for A, and it is the case T-3 said it wanted evidence for.

**Option C — fix GIMS's validator *instead* of hardening autoSQL — was argued against on two
independent grounds**, and the owner agreed:

1. **His own architecture ruling, this same day:** *"The autoSQL should be its own project. If it's
   not we have a much bigger problem on our hands."* C makes autoSQL's correctness depend on
   another project's validator.
2. **The `Glove.size` finding.** A field declared `type: float` contains `'lmao im a changling'`.
   `is_number()` rejects that, so **something already writes past the check**. A door-only fix
   guards a door with a hole beside it.

**Option D — narrow or abandon — had nothing behind it.** The band that would have pointed there was
fixed before evidence and did not fire. Choosing D would have meant setting aside the homework.

**Q3's park is the interesting one.** The GIMS fix is genuinely good, and it was still parked —
because it changes what users may upload, which is a product decision, not a cleanup, and because
**Q2's refusal counter tells us when it stops being hypothetical.** Together Q2 and Q3 convert an
unanswerable question ("will this ever happen?") into one that answers itself later.

## Consequences applied

- **T-6 is released**, with an added scope item from Q2: the compiled runtime must **record every
  refusal** so a first real occurrence is seen rather than inferred.
- **T-2's disagreement question is settled** (Q4): the demo seeds a non-ASCII digit row. This is a
  strictly better showcase than the original — the old one displayed a divergence that was itself a
  symptom of the guard defect T-3 fixed; this one is real, current, in-subset, and survives the
  corrected runtime. **T-2's other two blockers are untouched:** AC-22's amendment note, and the
  q8 layout fix that GA-8 requires before acceptance.
- **T-4 stays held** until T-6 reports (Q5).
- **A new ticket is opened** for the `Glove.size` write path (Q6), to be logged and not chased.
- **No GIMS-side ticket is opened** (Q3).

## What this does NOT settle — carried forward honestly

- **The GIMS gate stays shut.** Nothing enters GIMS until T-6 *and* T-4 pass. A clean homework buys
  the re-run, not admission.
- **Production data was never examined and cannot be from here.** *n* = 1 machine, 1 operator, and
  the tenant project is a sandbox whose noun list includes `Soup Ladel` and `LL Cool J`. The 144 is
  a sandbox's denominator.
- **`glp_strong` was deliberately not examined**, on the owner's ruling that it is the wrong corpus. The
  fail-closed fence on port 55433 stays shut and was never contacted.
- **How often anyone imports a CSV, and in what locale, is unmeasured.** An open door says nothing
  about traffic through it — which is precisely why Q2's counter exists.
- **Whether a repaired runtime passes is still unknown.** T-3 twice found mechanisms nobody predicted.

## Evidence

`spikes/T-5/FRAMING.md` (428 lines — the bar, fixed before evidence, plus the owner's two rulings) ·
`spikes/T-5/FINDINGS.md` (229 lines) · three re-runnable read-only probes in `spikes/T-5/probes/` ·
[nonascii-digits-in-real-data.md](nonascii-digits-in-real-data.md) (the four options in full) ·
the decision form at `https://claude.ai/code/artifact/8dd8424f-11db-40df-a035-272e495b115d`

**Read-only attestation:** no Postgres connection was opened by any part of T-5; every SQLite store
was opened `mode=ro&immutable=1`; no compiler was run; nothing was written outside `spikes/T-5/`,
`kb/` and the ticket record.
