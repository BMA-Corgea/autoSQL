# T-6 · Findings — the correctness re-run

Stage: `sp-investigate` (spike@v2) · Run: **2026-09-01**, 20:33–20:34 UTC ·
Bar: `spikes/T-6/FRAMING.md`, fixed before any battery ran.

**Throwaway container only.** Everything ran against a `pgvector/pgvector:pg16` container created
for this run on **port 55434**, torn down at the end. `glp_strong` on 55433 was never contacted;
`differ.py`'s fail-closed guard on that port is untouched.

---

## The answer

> **PASS at the pinned setting.** At `extra_float_digits = 1`, across all three subset batteries —
> **11,367 expressions** — the compiled SQL returns **zero wrong numbers** under the recursive
> comparison rule, with **zero unexplained raises** and **zero nullness violations**. The 130-case
> contract fixture is **130/130 at all three settings**. T-3's 55 divergences at this setting are
> gone: **26 became named refusals** and **29 were the comparison rule's own defect**.
>
> **And the fix costs more than it fixes.** Of 86 coercion refusals, **26 replaced a silent wrong
> number and 60 replaced an answer that was already correct** — see §5. That is the headline for
> `sp-decide`, not the pass.

## 1. Controls, first — the run is void without them

| setting | requested | read back | `to_jsonb(1/3)` | verdict |
| --- | --- | --- | --- | --- |
| efd 1 | 1 | **1** | `0.3333333333333333` (16 digits) | AGREE |
| efd 0 | 0 | **0** | `0.333333333333333` (15 digits) | AGREE |
| efd −3 | −3 | **−3** | `0.333333333333` (12 digits) | AGREE |

Three settings, three distinct values: the plumbing changed what it claimed to change (FRAMING §6).
`spikes/T-6/out/efd_control.txt`.

## 2. The counts — both rules, three settings, nothing pooled

`ran` = agree + diverge + refusal + raise + nullness. Refusals stay **in** the denominator.

### At `extra_float_digits = 1` — the pinned, contracted setting

| battery | rule | AGREE | **DIVERGE** | REFUSAL | RAISE | NULLNESS |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `sub_ordinary` | strict | 3787 | **0** | 14 | 0 | 0 |
| `sub_ordinary` | recursive | 3787 | **0** | 14 | 0 | 0 |
| `sub_unicode` | strict | 3750 | **0** | 49 | 0 | 0 |
| `sub_unicode` | recursive | 3750 | **0** | 49 | 0 | 0 |
| `sub_extreme` | strict | 3706 | **29** | 32 | 0 | 0 |
| `sub_extreme` | **recursive** | 3735 | **0** | 32 | 0 | 0 |

**Both numbers are printed, as FRAMING §4 requires.** The only place the rule makes any difference
is `sub_extreme`, and §3 accounts for every one of those 29 cases individually.

### At efd 0 and −3 — out of contract, reported separately, never pooled

| battery | efd | DIVERGE (strict) | DIVERGE (recursive) |
| --- | --- | ---: | ---: |
| `sub_ordinary` | 0 / −3 | 0 / 0 | 0 / 0 |
| `sub_unicode` | 0 / −3 | 0 / 0 | 0 / 0 |
| `sub_extreme` | 0 | 91 | **62** |
| `sub_extreme` | −3 | 95 | **66** |

These are **M3, the value-channel truncation**, which fix 2.1 declares a **configuration defect**
rather than a compiler defect: at efd ≠ 1 Postgres prints fewer digits than a double carries, and
the number that comes back is short. They are named here rather than dropped. **Nothing at efd 0 or
−3 is claimed as a pass**, and the pin is what makes that legitimate — if the setting is ever not 1
in production, these 62–66 wrong numbers are live.

### The contract fixture

**130 / 130 compiled agreements, 0 divergences, 0 SQL errors, at each of efd 1, 0 and −3.**
`fixture_sha256=0091df64283d91cb`, unchanged. `spikes/T-6/out/fixture_summary.txt`.

## 3. What the rule change absorbed — all 29, not a sample

FRAMING §4 made this mandatory. `probes/P2_rule_delta.py`:

- **No case ever moved `AGREE → DIVERGE`.** Checked arithmetically at every setting: agree+diverge
  is identical under both rules, so the population is the same and only the classification moved.
  This mattered because the recursive rule also **tightens** — inside a container it stops
  conflating `True` with `1`, which the suite already asserts at top level — so a new divergence was
  possible in principle. There are none.
- **All 29 reclassified cases are M2's container shape**, verified mechanically rather than by
  eye: both engines returned a container, and every leaf pair is equal as floats. 29 of 29
  classified, **0 unparsed**.
- The same **29** move at every setting — it is one mechanism, not a setting artefact.

One witness, so the shape is visible:

```
$.o  rec {"o": ["1e3", 1.7976931348623155e+296]}
     py  ['1e3', 1.7976931348623155e+296]
     sql ['1e3', 17976931348623155000000000000...000]   (jsonb's exact decimal)
```

Read as a scalar these agree. Read inside a list they did not, because Python decodes SQL's exact
integer to `int` and `int == float` is exact. **Under the recursive rule the leaf pair goes through
`float()` — exactly as a top-level number always did — and agrees.** The tolerance never moved.

## 4. The refusal — it fires exactly where it should

`probes/P1_refusal_predicate.py`, 52 hand-chosen strings covering every shape that reaches
`xpr.num`'s string branch:

- **22 XPR02 refusals**, every one on a string the Python evaluator coerces.
- **0 refusals where Python also refused.** `'Item ３'`, `'３abc'`, `'１２３ ４５６'`, `'．５'`,
  `'٣,٥'` all still return NULL on both sides and agree. This was FRAMING stop-condition 4, and it
  is the failure mode that would have been worse than the bug.
- **0 silent NULLs remain where Python coerced.**
- The predicate covers **both** T-3 mechanisms it should: non-ASCII digits (M1) **and** non-ASCII
  whitespace at a string edge (D10) — a `7` wrapped in non-breaking spaces refuses rather than
  silently returning NULL. That is slightly wider than FRAMING §2.2's wording ("contains a
  non-ASCII `Nd` digit") and is stated here rather than glossed: the rule implemented is the more
  general one that section's own sentence asks for — *refuse exactly where Python would have
  coerced and SQL cannot*.

**A defect this probe caught in the fix itself, recorded because it nearly shipped.** The first
build wrote the whitespace set as ranges. `btrim`'s second argument is a **literal character list,
not a pattern**: Postgres expanded the `\uXXXX` escapes but the `-` stayed a hyphen and the interior
code points fell out of the set, so a value wrapped in `U+001C` / `U+001F` survived the trim and
went back to being a silent NULL. The rebuilt version lists all **29** characters individually, and
the runtime carries a comment telling the next reader not to tidy it into ranges.

## 5. THE FINDING — the refusal is 3.3× broader than the bug it fixes

`probes/P4_refusal_cost.py`, at the pinned setting, over identical seeds and populations:

| battery | T-3 divergences | T-6 coercion refusals | wrong numbers fixed | **correct answers lost** |
| --- | ---: | ---: | ---: | ---: |
| `sub_ordinary` | 2 | 14 | 2 | **12** |
| `sub_unicode` | 17 | 49 | 17 | **32** |
| `sub_extreme` | 36 | 23 | 7 | **16** |
| **total** | | **86** | **26** | **60** |

**Of 86 refusals, 26 (30 %) replaced a silent wrong number — a straight win. 60 (70 %) replaced an
answer that was already correct.**

Those 60 are expressions where the bad `NULL` was **absorbed downstream** and never reached the
result: another term dominated a `max()`, a comparison went the same way regardless, a `coalesce`
supplied the same fallback. Python and SQL agreed. Now SQL raises.

**This is inherent to the design, not a defect in it.** `xpr.num` refuses at the moment of
coercion, and at that moment nothing knows whether the value will matter. "Refuse only when it
changes the answer" is not expressible in the compiled SQL — it would require evaluating the whole
expression twice.

**Why it matters for `sp-decide`:** the loud-refusal design was chosen on the argument that a
refusal is better than a silent wrong number. That argument holds. But its price is now measured,
and it is not the 26 cases the bug actually broke — **it is 86 queries that stop working**, on data
that contains a single non-ASCII digit anywhere the expression touches. Paired with T-5's finding
(prevalence in real data is 0 of 144, but GIMS's CSV import admits these by design), this is
precisely what the owner's Q2 refusal counter exists to watch.

## 6. Verdict against the bar

**FRAMING §5, at efd 1, under the recursive rule: DIVERGE = 0 in all three batteries.**
The PASS band's second condition — *every difference from the strict count is M2's container shape
and nothing else* — is met, 29 of 29 verified (§3).

> ### PASS.
>
> A pass buys **admission to T-4, the speed run. It does not buy admission to GIMS.**

Recorded on this seat's authority per FRAMING §7, which reserved that only for a pass: a factual
verdict against a bar fixed before evidence, with both numbers published.

## 7. Evidence integrity — one defect in the instrument, named

**Every battery output in this run prints `runtime.sql sha256=1c58d548a6045aa6`, and that is the
wrong runtime.** The harness hashes the *file it expects* (`spikes/T-1/proto/runtime.sql`, which is
unchanged) rather than the functions actually installed. Left unchecked it would attribute T-6's
numbers to T-3's runtime.

Closed by `probes/P3_installed_fingerprint.py`, which reads the installed definitions out of
`pg_proc`:

| | |
| --- | --- |
| functions installed in schema `xpr` | **21** |
| sha256 of the **installed** definitions | `799a9e62a798ec37` |
| `spikes/T-1/proto/runtime.sql` (what the batteries print) | `1c58d548a6045aa6` |
| `spikes/T-6/runtime.sql` (what was installed) | `871b1b4c2df95719` |
| installed `xpr.num` carries the XPR02 refusal | **yes** |
| installed `xpr.num` carries the `RAISE LOG` record | **yes** |

**Confirmed: the batteries ran against T-6's patched runtime.** The harness's fingerprint line
should be fixed to hash `pg_get_functiondef` instead; that is a one-line change and it is listed in
§9.

## 8. Q2 — the refusal record, and why it is a log and not a counter

The owner's GA-9 Q2: *"yes — build it into T-6."* Implemented as **`RAISE LOG` immediately before the
`RAISE EXCEPTION`**, carrying the offending value truncated to 60 characters. **589 such lines
landed in this run's server log**, each with a timestamp and backend PID:

```
2026-09-01 20:34:28.500 UTC [225] LOG:  xpr.refusal XPR02 non-ascii-numeric value=１２３
```

**Not an in-database counter, deliberately.** A sequence or table write would make `xpr.num`
**VOLATILE**, and its `IMMUTABLE` declaration is load-bearing — expression indexes over compiled
paths require it (T-1 `f3` §3.6, the H3 hazard). A counter is not worth trading indexability for.
`RAISE LOG` is durable, immediate, carries the value, and — unlike a table write — **does not roll
back with the aborted statement**. The runtime carries that reasoning in a comment.

## 9. What this run does NOT establish

1. **Admission to GIMS.** T-4 has still never run. A passed re-run buys the speed run, nothing more.
2. **efd 0 and −3 remain broken** (62 and 66 divergences). The pass depends entirely on the pin
   holding in production. **Nothing in this run enforces the pin** — that is a build item.
3. **The 60 lost answers (§5) are a measured cost, not an accepted one.** Nobody has ruled on
   whether that price is worth paying.
4. **`raw`-mode data was not re-run.** T-3 found a ninth Python-raise site (class 4) on rows written
   by something other than the Python process. T-5 established the writer is Python, so this prices
   low — but it was not re-measured here.
5. **The harness fingerprint defect (§7) is reported, not fixed.**
6. **The container comparison rule is now this project's, not GIMS's.** `differ.py` diverges from
   `tests/test_dashboard_expr.py`. If GIMS's own suite is not changed to match, the two drift.
7. **No mutation testing.** The batteries were not re-checked for the ability to fail on a seeded
   defect in this run; T-3's injection test was not re-run.

## Attestation

Instruments fingerprinted before the run and identical to T-3's: `expr.py` `90cbb56d04b08b82`,
`compile.py` `b71b153802d0df94`, `runtime.sql` (T-1 file) `1c58d548a6045aa6`. A baseline battery was
run **before any change** and reproduced T-3's `sub_ordinary` efd-1 line exactly (AGREE 3799,
DIVERGE 2, PARSE_ERROR 125, DISCARDED 74, ran 3801), proving the instrument still fails the way it
did. Two files were then changed, both declared: `spikes/T-6/runtime.sql` (new; the named refusal)
and `spikes/T-1/analysis/fuzz/differ.py` (the recursive rule behind `AUTOSQL_MATCH_MODE`, defaulting
to **strict** so an unset environment reproduces T-3 byte-for-byte; and `XPR02` registered as a
named refusal kind so a deliberate refusal is not counted as an unexplained raise). The original
`differ.py` is preserved at `spikes/T-6/differ.py.orig`. Seeds and N unchanged: `N=4000 seed=2026`.

---

# ADDENDUM — produced at `sp-synth`, not `sp-investigate`

**Stated plainly because the stage boundary matters:** everything above was produced and recorded
before `sp-investigate` passed. What follows was produced *afterwards*, while weighing the options
for `sp-decide`. It is evidence, so it belongs in the findings rather than only in the synthesis —
but it did not exist when the pass was recorded, and the §6 verdict does not depend on it.

## A. T-3's premise was wrong — SQL *can* cheaply match Python

T-3's ruling, and this ticket's own charter, both rest on one sentence:

> *"It cannot cheaply be made to match Python — Postgres regexes have no equivalent of Python's
> any-Unicode-digit class — so the generated SQL raises a named error."*

The first clause is true and §2.2 confirmed it independently. **The conclusion does not follow.**
Matching Python does not need a Unicode-digit *class*; it needs a Unicode-digit *mapping*. Python's
`float()` accepts a non-ASCII digit by its **numeric value**, so mapping the 670 `Nd` code points
onto `'0'`–`'9'` with a single `translate()` reproduces Python's behaviour exactly — and then there
is nothing to refuse.

Two variants were built and measured against the same batteries, seeds and fixture:

| | **A — refuse** (§2–§6) | **B — translate, hoisted** | **C — translate, nested** |
| --- | --- | --- | --- |
| `sub_ordinary` efd 1 | 3787 agree, **14 refusals** | 3801 agree, 0 refusals | **3801 agree, 0 refusals** |
| `sub_unicode` efd 1 | 3750 agree, **49 refusals** | 3799 agree, 0 refusals | **3799 agree, 0 refusals** |
| `sub_extreme` efd 1 (recursive) | 3735 agree, **32 refusals** | 3758 agree, 9 refusals | **3758 agree, 9 refusals** |
| divergences at efd 1 | **0** | **0** | **0** |
| coercion refusals | **86** | **0** | **0** |
| correct answers lost (§5) | **60** | **0** | **0** |
| contract fixture | 130/130 | 130/130 | **130/130** |
| P1 predicate contract | holds | holds | **holds** |
| **300k ASCII coercions** | **853 ms** | **4553 ms** | **812 ms** |

Baseline, for the timing column: **852 ms**.

**The 9 refusals remaining under B and C are the magnitude guard (`XPR01`, overflow/underflow) —
legitimate, unchanged, and nothing to do with coercion.**

## B. Why C and not B — the nesting is load-bearing

B hoists `translate()` above the ASCII gate, so **every ordinary numeric string pays it**: 852 ms →
4553 ms, a **5.3× tax on the common path**. That matters more here than it looks, because T-5 found
that in the one tenant project **every number-declared field is stored as a string** — so the
coercion path is not an edge case, it is how every number is read.

C runs `translate()` **only after the ASCII gate has already failed**. Ordinary strings never touch
it, and the measured cost is **812 ms against an 852 ms baseline — no measurable cost at all**.
The runtime carries that measurement in a comment, so the next reader does not "tidy" the nesting
away.

## C. What C changes about the answer

- **The 26 real wrong numbers are fixed** — not refused, *fixed*. Both engines now agree.
- **The 60 collateral losses of §5 do not happen.** There is nothing to lose, because nothing
  refuses.
- **§5's finding stands as a finding about variant A**, and it is the reason C was looked for.
- **Q2's refusal record still applies** — to `XPR01`, the magnitude guard, which still refuses.
  There is simply no `XPR02` any more.
- **efd 0 and −3 are unchanged** (62 / 66 divergences, M3). C fixes coercion, not truncation; the
  pin is still what the pass depends on.

## D. What C does NOT change

- It does not touch GIMS (Q3 stayed parked).
- It does not alter the container comparison rule; the 29 M2 cases are still absorbed by §4's
  recursive rule, identically under A, B and C.
- It does not buy admission to GIMS. T-4 still has not run.
- **The `translate()` mapping is generated, not hand-written.** Regenerating it is part of any
  Unicode-version bump, and nothing in the build enforces that today.

## E. Evidence

`spikes/T-6/runtime-variantB.sql` · `spikes/T-6/runtime-variantC.sql` ·
`out/VB_*.txt` (6 runs) · `out/VC_*.txt` (18 runs) ·
`probes/P1_variantB_predicate.txt` · `probes/P1_variantC_predicate.txt` ·
fixture tags `t6vb` and `t6vc` in `out/fixture_*.json`.
