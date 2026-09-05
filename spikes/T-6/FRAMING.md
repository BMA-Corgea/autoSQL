# T-6 · Framing — the correctness re-run, and the bar it is judged against

Stage: `sp-frame` (spike@v2) · **lean: OFF**, and **risk: HIGH vetoes lean regardless** — this
ticket decides whether a SQL compiler returns wrong numbers · Framed: **2026-09-01**

**Authority.** the owner, 2026-09-01: *"Go to T-6. Go ahead and loop through the tickets. Try to use my
best judgement instead of asking me for any others"* — recorded as **GA-10**. Two decisions this
document would otherwise have put to him are therefore ruled here, **before any evidence exists**,
and both are flagged so he can overturn either in one line: **§4 (the container comparison rule)**
and **§7 (what happens if the re-run fails)**.

Figures marked **[measured 2026-09-01]** were produced on this machine while writing this, against a
throwaway container, before any battery ran.

---

> ## Vocabulary
>
> **The subset** — the restricted set of dashboard expressions autoSQL is allowed to compile.
> **A battery** — a large pile of generated expressions run through both engines and compared.
> **The contract rule (`_matches`)** — the single function that decides whether the two engines
> agreed. It lives in GIMS's own test suite and this spike mirrors it **unchanged**; §4 is about the
> one place where "unchanged" turned out to be the wrong thing to be.
> **`extra_float_digits` (efd)** — a Postgres setting controlling how many digits it prints when
> turning a float into text. T-3 ran everything at three values (1, 0, −3) because the setting
> changes the answer.
> **A named refusal** — the compiled SQL raising a specific, labelled error instead of quietly
> returning a wrong number. Under the standing ruling a loud refusal is allowed; a silent wrong
> number is not.
> **Class 1 / class 4** — T-3's taxonomy. Class 1 is *both engines answered and the answers differ*.
> Class 4 is *Python raised where SQL answered cleanly*.

---

## 1. The question, unchanged

> **Does the restricted expression subset return a wrong number, once the two mechanisms T-3 found
> are fixed? Bar: ZERO wrong answers, at each of three Postgres float settings, reported
> separately.**

**The bar is T-3's, not a new one.** It is not renegotiated because a previous run failed against
it. Same instruments, same batteries, same fixture, same domain gate, same controls.

## 2. What changes before the batteries run

Three changes, from T-3's ruling (GA-7 q5), plus one from T-5's (GA-9 Q2).

### 2.1 Pin `extra_float_digits = 1`

T-3 proved the value-channel truncation (M3) is **entirely** a product of efd 0 and −3. Pinning
cures it. From here, **efd ≠ 1 is a configuration defect, not a compiler defect.**

**But all three settings still run, and are still reported separately.** The bar says three
settings; the bar does not move. What changes is the *reading*: failures that occur only at 0 or −3
are reported as **configuration defects against a pinned contract**, counted and named, never
pooled with efd-1 results and never quietly dropped.

### 2.2 Convert the Unicode-digit gap (M1) into a named refusal

`float("１２３")` is `123.0` in Python and `NULL` in SQL. It cannot cheaply be made to *match* —
so the compiled SQL must **refuse by name** rather than answer `NULL`.

**The mechanism, verified before writing this [measured 2026-09-01]:**

- Postgres's `[[:digit:]]` does **not** match `１`, `١`, `۱`, `๑` or `१`. Worse, Postgres's ctype
  classes all five as **`[[:alpha:]]`**, so the obvious "alnum but not alpha" trick fails too.
  T-3's claim that Postgres has no Unicode-digit class is **confirmed, and is stronger than stated**.
- So the class is written out explicitly: Python's own **670** non-ASCII `Nd` code points collapse
  to **63 contiguous ranges**, emitted as a Postgres regex character class using `\uXXXX` escapes.
- **Verified exhaustively in Postgres, not assumed:** across **21,437** probed code points (all 670
  `Nd`, plus 20,767 non-`Nd` controls and a strided sample) the class returns **0 false negatives
  and 0 false positives**. The single apparent miss was `U+1D7CE` MATHEMATICAL BOLD DIGIT ZERO,
  which is genuinely `Nd` and was mislabelled in the control set, not by the class.

**The refusal fires narrowly, and this is the part to get wrong slowly.** `xpr.num` must still
return `NULL` for a string Python *also* refuses (`'n/a'`) — otherwise a refusal replaces an
agreement. It refuses **only** where the ASCII gate rejects the string **and** the string contains a
non-ASCII `Nd` digit, i.e. exactly where Python would have coerced and SQL cannot.

### 2.3 Count the refusals (GA-9 Q2)

The owner's Q2: *"yes — build it into T-6."* Every refusal the runtime raises is **recorded**, so the
first real occurrence in production is seen rather than inferred. T-5 measured prevalence at **0 of
144 coercible strings** and could not measure the future; the counter is what converts that into a
question that answers itself later.

**Scope guard:** the counter is autoSQL's own. The owner's Q3 **parked** the GIMS-side validator fix, so
**nothing in GIMS is changed by this ticket.**

### 2.4 The container comparison rule — see §4. It is the one genuinely contested change.

## 3. What is NOT changed

- **The bar.** Zero, three settings, reported separately.
- **The instruments.** `differ.py`, `conformance.py`, the fuzz batteries, the domain gate, the
  controls — same files, same seeds.
- **GIMS.** Not one line (Q3, parked).
- **The subset.** No construct is added or removed. If the subset needs narrowing, that is a finding
  for `sp-decide`, not a change smuggled in before the batteries.

## 4. RULING — the container comparison rule (fixed before evidence)

**The problem.** When an in-subset expression returns a **container**, `_matches`
(`GIMS-Project/tests/test_dashboard_expr.py:19-24`) compares it with `actual == expected` — it never
descends. Verbatim:

```python
def _matches(actual, expected) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected or actual == expected and type(actual) is type(expected)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=_EPS)
    return actual == expected          # <-- containers fall through to here
```

jsonb stores `1e181` as the exact decimal 10¹⁸¹. Python holds the double. Read as a **scalar** the
two agree; read **inside a list** they do not, because `int == float` in Python is exact. **32 of
`sub_extreme`'s 36 wrong answers at efd 1 are this one shape** (T-3 §6 M2), and T-3 said plainly:
*"This is a defect of the contract rule as much as of the compiler."*

**The ruling: `_matches` recurses. The tolerance itself does not change.**

Read the two branches above again. A top-level number goes through `math.isclose(float(actual),
float(expected), rel_tol=0, abs_tol=1e-9)` — and **`float(10**181) == 1e181` exactly**, so the same
pair that fails inside a list *passes* at the top level. The failure is not that the tolerance is
too tight. **The failure is that the rule stops at depth 0.** So:

> **Apply `_matches` element-wise to lists and value-wise to dicts, at every depth. Lengths and keys
> must still match exactly. Strings, booleans and nulls compare exactly as before. The epsilon stays
> `rel_tol=0, abs_tol=1e-9`, unchanged, at every depth.**

**Why this and not the alternatives.**

- *Normalise the SQL side* (push container numbers through `float8` on the way out) makes SQL throw
  away precision it genuinely has, and T-3 priced it as a redesign outside scope.
- *Leave it strict* keeps counting a harness artefact as a compiler defect. A JSON consumer that
  parses numbers as doubles — which is every consumer of this dashboard — sees the two answers as
  identical.
- *Loosen the tolerance inside containers* would be the dishonest fix, and is **not** what this
  ruling does. Nothing about the tolerance moves.

**The guard that keeps this honest, and it is not optional.** Changing the rule that decides
pass/fail, in the middle of a re-run that previously failed, is exactly the move that turns a
correctness spike into theatre. So:

> **Every battery reports BOTH numbers, always, side by side: counts under the ORIGINAL strict rule
> and counts under the recursive rule.** Neither is hidden, neither is a footnote. A pass claimed
> only under the recursive rule is reported as *exactly that*, with the strict number printed next
> to it. **If the two numbers differ, the verdict names every case the change absorbed** so the owner can
> see precisely what was reclassified and overturn this ruling in one line.

## 5. Decision criteria — fixed now

| band | at efd 1, class-1 wrong answers | verdict |
| --- | --- | --- |
| **PASS** | **0** under the recursive rule, **and** every difference from the strict count is M2's container shape and nothing else | The re-run passes. Admission to **T-4**, the speed run — **not** to GIMS. |
| **PASS-WITH-NOTE** | **0** under the recursive rule, but the strict/recursive gap contains something that is *not* M2 | Report as a pass **and name the reclassified cases individually**. The owner sees exactly what the rule change absorbed. |
| **FAIL** | **> 0** under the recursive rule | The re-run fails. See §7. |

**Refusals are counted and named, never pooled with wrong answers** — that is the whole design.
A refusal where Python answered is an **allowed** outcome; it is reported as a refusal, with its
count, not as a pass and not as a failure.

**Class 4 (Python raises, SQL answers) is reported separately** and does not enter the band. T-3
found class 4 empty on `py`-mode data and non-empty on `raw` data; if that changes, it is a finding.

## 6. What would make the result unusable

- **Never port 55433.** The live database. The instruments already fail closed on it; that guard is
  not touched. This run uses a throwaway container on **55434**, torn down at the end.
- **A battery whose controls did not run first.** T-3's negative and positive controls run per
  setting, before the batteries. If the efd control shows two settings printing identically, the
  plumbing failed and the run is void.
- **A changed instrument other than §2 and §4.** Any other edit to the harness invalidates the
  comparison with T-3's numbers.
- **A pass reported without its strict-rule twin** (§4).
- **A refusal counted as an agreement.** Refusals are their own column.
- **Comparing against T-3's numbers without re-stating that the runtime changed.** T-3's figures
  came from a different runtime; the comparison is a narrative aid, never evidence of a pass.

## 7. RULING — what happens if it fails (fixed before evidence)

Under GA-10 this seat rules on the re-run's verdict rather than putting it back to the owner. **That
authority has a limit, and here it is:**

- **A PASS is recorded on this seat's authority.** It is a factual verdict against a bar fixed
  before evidence, with both numbers published. No new judgement is involved.
- **A FAIL is NOT.** A failure means a *third* layer of unpredicted mechanism after T-3 found two,
  and the honest options at that point (narrow the subset, abandon, carve out) are the same product
  choices T-3's ruling weighed and the owner decided. **A failing re-run stops and goes back to him**,
  because "use your best judgement" is authority to finish the work, not authority to re-take a
  decision he already made once on evidence.
- **A PASS-WITH-NOTE is recorded, and the reclassified cases are surfaced to him anyway** — recorded
  because the bar was met, surfaced because §4 was this seat's call and he should see what it bought.

## 8. Timebox

**One working day for `sp-investigate`.** If the day ends with batteries unrun, report what ran and
what did not, per setting, with both numbers. Do not take a second day without asking.

## 9. Stop conditions

1. **Any connection attempt to port 55433** — stop, report.
2. **A control fails** (§6) — the instrument is the finding; stop.
3. **FAIL band** (§5) — stop at `sp-synth`, hand to the owner (§7).
4. **A refusal fires where Python also refused** — the refusal is too broad (§2.2); fix the
   predicate and re-run, do not accept the number.
5. **The timebox expires** (§8).

## Attestation

Framed 2026-09-01 on branch `spike/T-6-correctness-rerun`, before any battery ran. The only
database touched was a throwaway container created for this run on port 55434. The `Nd` class
verification (§2.2) and the `_matches` reading (§4) were done against the real files and the real
Postgres, and are reproducible from `spikes/T-6/probes/`.
