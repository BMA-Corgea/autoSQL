# T-3 · Findings — the correctness run (`sp-investigate`)

Run started: 2026-08-22. Seat: `coder`, stage `sp-investigate`. Bar and rules: `spikes/T-3/FRAMING.md`
(refreshed 2026-08-22); specification: `spikes/T-1/EXPERIMENTS.md` §1. This document is written
incrementally as results land; every number in it postdates the section-5.1 negative control per the
ordering rule (no real number is quoted before the control passed).

**Status: COMPLETE — run finished 2026-08-22; verdict in §10.**

---

## 0. Environment for this run

- Throwaway Postgres container **`autosql-t3-throwaway`** (named to be obviously disposable),
  image `pgvector/pgvector:pg16`, bound to `127.0.0.1:55434` (loopback only), database
  `autosql_spike`, role `glp_owner`, throwaway password. **PostgreSQL 16.14** (Debian
  16.14-1.pgdg12+1) — same version as the record's measurements.
- The live container `glp-strong-db` (port 55433) was **never connected to**. Every instrument used
  here fails closed without `AUTOSQL_SPIKE_DSN` and refuses port 55433 outright (verified in source:
  `differ.py`, `conformance.py`).
- `proto/runtime.sql` installed into the throwaway container; completion check = **21 functions in
  schema `xpr`** (per `REGENERATE-CORPUS.md` §4) — passed for the pristine install, and re-run after
  the step-zero edit (§2).
- Python: `GIMS-Project/.venv`, CPython 3.12.3, psycopg2 2.9.12. `PYTHONDONTWRITEBYTECODE=1`
  exported for every invocation; the pre-existing `__pycache__` under
  `GIMS-Project/core/dashboard/` was snapshotted before the run and re-checked after it (§9).
- Disk at start: 96% used, 20 GB free (`df` re-checked before every large step; no large tables are
  created by this run).
- Both GIMS checkouts: read-only throughout, imports only.

## 1. What was edited before any number was produced (all permitted by Q7)

Recorded here first so the instruments' state is unambiguous. Full diffs are in git.

| file | change | why |
|---|---|---|
| `spikes/T-1/analysis/fuzz/differ.py` | (a) `extra_float_digits` parameterised via `AUTOSQL_EFD` env (allowed: `1`, `0`, `-3`), value read back from the session and recorded in every Outcome; (b) `SQL_RAISE` split into **`SQL_REFUSAL`** (named: SQLSTATE `XPR01` = the new guard refusal, or `22003` overflow / underflow / out-of-range, kind recorded) and **`SQL_RAISE`** (everything else — an *unexplained* raise, still a defect line); (c) `statement_timeout = '20s'` on the session (same value `conformance.py` always used) | corrections C3 and C4 of the framing; ruling R7 |
| `spikes/T-1/proto/conformance.py` | the `SET extra_float_digits = 1` pin (found by content, not line number) parameterised via the same `AUTOSQL_EFD` env; the read-back value was already recorded in the output meta | correction C2; spec §1.4 item 1 |
| `spikes/T-1/proto/runtime.sql` | **step zero** — the guard literal extended from 297 to 309 digits at **both** sites (`xpr.f8`, `xpr.num`), and per the GA-4 ruling the out-of-range branch now **raises SQLSTATE `XPR01`** (a named, catchable refusal) instead of returning `NULL`. Both functions converted `LANGUAGE sql` → `plpgsql` to carry the `RAISE` | spec §1.2 step zero + THE RULING |
| `spikes/T-1/analysis/fuzz/H_ast_fuzz.py` | subset profiles added (`sub_ordinary`, `sub_extreme`, `sub_unicode`): construct allowlist (7 functions, no `%`, no date/string builtins), widened value domain per framing §5.3, per-expression mechanical subset gate, runtime `_eq` container-operand witness with discard-and-count, per-battery fingerprints and wall clock; `main()` put under a `__main__` guard | spec §1.4 items 2–4 |
| `spikes/T-1/analysis/fuzz/A_range.py`, `A2_boundary.py`, `B2_overflow.py` | the three missing producers written (their `.txt` outputs existed with no script); added to `run_all.sh` | spec §1.4 item 5 |
| new: `spikes/T-3/differ_injection_test.py` | the §5.1 negative control for `differ.py` — deliberately wrong compilations pushed through the real `run_case` path, each declaring its class in advance | spec §1.4 item 6; framing §5.1 |
| new: `spikes/T-3/efd_control.py` | the §5.2 positive control — setting read-back plus a value that must differ across settings | framing §5.2 |
| new: `spikes/T-3/t3_domain_gate.py` | framing §5.3 input-domain gate, both halves, with printed witnesses (py and raw ingestion modes) | framing §5.3 |
| new: `spikes/T-3/fixture_driver.py` | thin driver calling `conformance.run()` and writing results JSON to `spikes/T-3/out/` (so `proto/results.json` / `CONFORMANCE.md` are not overwritten) | keeps T-1's committed outputs intact |

## 2. Step zero — the guard literal, before and after

**The fix**: both literals in `proto/runtime.sql` extended from 297 to 309 digits (append 12 zeros
per site — 24 characters total, both sites, exactly as the framing corrected the spec's "twelve
characters"), and the out-of-range branch converted from `NULL::float8` to a **named raise**,
SQLSTATE **`XPR01`**, message naming the function, DETAIL carrying the (truncated) value, HINT
naming the fallback contract. Verified mechanically after the edit: 2 literal sites, 309 digits
each; 3 `XPR01` raise sites (`xpr.f8`; `xpr.num` string path; `xpr.num` numeric-exponent-overflow
path). Runtime reinstalled; the 21-function completion check passed again.

**Spot checks of the new behaviour (psql, throwaway container):**

| probe | result |
|---|---|
| `xpr.f8('1e300')` | **`1e+300`** (was `NULL` before the fix) |
| `xpr.f8('1.7976931348623157e308')` (DBL_MAX itself) | `1.7976931348623157e+308` — passes |
| `xpr.f8('1e309')` | **raises `XPR01`** — the named refusal |
| `xpr.num('"1e400"')` (string path) | raises `XPR01` |
| `xpr.num('"1e200000"')` (exponent beyond `numeric` itself) | raises `XPR01` |
| `xpr.num('"1e-400"')` (tiny) | raises native `22003` "out of range for type double precision" — the pre-existing unguarded-underflow behaviour, surfaced not masked (measured, not redesigned, per framing §7) |

**Before** (pristine runtime, `out/A_range_before.txt`): the twenty `A_range` paths at `a = 1e300`
reproduce the record **exactly, at each of the three settings separately**: **16 of 20 diverge, 8 of
the 12 in-subset paths among them** — same counts at efd 1, 0 and −3.

**After** (`out/A_range_after.txt`): **0 of 20 diverge — at each of the three settings.** Not just
the eight in-subset paths: all twenty close, including the out-of-subset ones (`sum`, `avg`,
`round`, `floor`, `string`, `concat`, `contains`, `number`). **Stop rule 4 does not fire: the cause
was the literal, and nothing else was hiding under it at `a = 1e300`.**

**The 130-case fixture, both states, all three settings** (`out/fixture_{before,after}_efd*.json`):
130/130 `COMPILED_AGREES` in all six runs. The fix moved nothing in the fixture — consistent with
the record's claim that no fixture case reaches the guard — and the before/after is on file per
admissibility item 7. (130/130 is quoted as *one input set among several*, never as the acceptance
test — Q2.)

## 3. The negative control (§5.1) — run FIRST, per setting

`spikes/T-3/differ_injection_test.py` swaps `compile_ast` for an injector keyed by the parsed AST
and pushes deliberately wrong compilations through the **real** `run_case` path. Ten injections,
each declaring its class in advance, plus a non-injected sanity case that must stay `AGREE`:

| id | what was injected | must land as | landed |
|---|---|---|---|
| N1 | constant wrong number (`999` where Python says `3.0`) | `DIVERGE` (class 1) | ✓ |
| N2 | `NULL::jsonb` where Python says `3.0` | `DIVERGE`, SQL NULL (class 2) | ✓ |
| N3 | `7` where Python says `None` | `DIVERGE` (class 3) | ✓ |
| N4 | SQL value where Python raises `OverflowError` | `PY_RAISE` (class 4) | ✓ |
| N5 | `xpr.f8('1e309')` — the step-zero guard | `SQL_REFUSAL`, kind `guard` | ✓ (post-fix runs) |
| N6 | `1e308::float8 * 10` | `SQL_REFUSAL`, kind `overflow` | ✓ |
| N7 | `1e-300::float8 * 1e-300` | `SQL_REFUSAL`, kind `underflow` | ✓ |
| N8 | call to a nonexistent function (SQLSTATE 42883) | `SQL_RAISE` (unexplained), kind None | ✓ |
| N9 | compiler raises `Uncompilable` | `UNCOMPILABLE` | ✓ |
| N10 | `'null'::jsonb` where Python has `None` | `NULLNESS` | ✓ |

Run **once per setting** (efd 1, 0, −3), pre-fix (N5 skipped — no named refusal exists yet, which is
the point of step zero) and post-fix (all ten). **All runs pass; no injection was ever scored as
agreement.** Outputs: `out/negctl_prefix.txt`, `out/negctl_postfix.txt`.

Worth the record, in this project especially: **the control's own first run failed** — the injector
was keyed by AST and three pairs of injections shared an expression source, so later entries
silently overwrote earlier ones, and two expectations mis-guessed jsonb's integer text form. The
control caught its own defects before anything real was measured; the defect and its fix are
recorded in the control script's own comment block (the rerun overwrote the failing output file).
The rig under test — `differ.py` — classified
correctly in every case where the intended injection actually fired.

The five outcomes the framing §10 demands stay distinct end to end — agrees · diverges ·
named refusal · unexplained raise · did-not-compile — are each individually provoked above, plus
`NULLNESS` and `PY_RAISE` on their own lines.

## 4. The positive control (§5.2) — the setting demonstrably changed

Per setting, before the batteries (`out/posctl_prefix.txt`, `out/posctl_postfix.txt`), through the
session `differ.py` actually uses **and** through the real compiled path (`1 / 3` via `compile.py` +
the `xpr` runtime):

| requested | read-back | `to_jsonb(1.0/3.0)` | compiled path `1 / 3` |
|---|---|---|---|
| 1 | 1 | `0.3333333333333333` (16 sig. digits) | `0.3333333333333333` |
| 0 | 0 | `0.333333333333333` (15) | `0.333333333333333` |
| −3 | −3 | `0.333333333333` (12) | `0.333333333333` |

Three pairwise-distinct value-channel outputs, matching `M_encoding_guc.txt` §M1's prediction —
the new plumbing is live on the exact path the batteries use, in both instruments (`differ.py` via
`AUTOSQL_EFD`, `conformance.py` likewise — its meta records the read-back). The negative control
also ran once per setting (§3), which is §5.2's third condition.

## 5. The batteries, per setting — counts and denominators

All batteries post-step-zero, all with the §5.1 control already passed, seed 2026, N = 4,000 draws
per fuzz battery. `ran` = agree + diverge + refusal + raise + nullness — refusals stay in the
denominator (framing §4.7). Parse errors (generator noise, counted, not run) and container-`==`
discards (out-of-subset by the closure qualifier, reading A — witnessed at runtime, discarded,
counted) are excluded from `ran` and shown. **No number below is pooled across settings.**

### `sub_ordinary` (dashboard-shaped values + the §5.3 coercing strings) — ran 3,801

| efd | AGREE | class 1 | class 2 | class 3 | class 4 | refusals | unexplained raises |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3,799 | **2** | 0 | 0 | 0 | 0 | 0 |
| 0 | 3,799 | **2** | 0 | 0 | 0 | 0 | 0 |
| −3 | 3,799 | **2** | 0 | 0 | 0 | 0 | 0 |

(4,000 drawn; 125 parse errors; 74 container-`==` discards.)

### `sub_unicode` (non-ASCII strings) — ran 3,799

| efd | AGREE | class 1 | class 2 | class 3 | class 4 | refusals | unexplained raises |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3,782 | **5** | **12** | 0 | 0 | 0 | 0 |
| 0 | 3,782 | **5** | **12** | 0 | 0 | 0 | 0 |
| −3 | 3,782 | **5** | **12** | 0 | 0 | 0 | 0 |

(4,000 drawn; 133 parse errors; 68 discards.)

### `sub_extreme` (the §5.3 magnitude table) — ran 3,767

| efd | AGREE | class 1 | class 2 | class 3 | class 4 | refusals (guard/overflow/underflow) | unexplained |
|---|---:|---:|---:|---:|---:|---|---:|
| 1 | 3,722 | **32** | **4** | 0 | 0 | 9 (0 / 6 / 3) | 0 |
| 0 | 3,625 | **94** | **3** | 0 | 0 | 45 (**37** / 5 / 3) | 0 |
| −3 | 3,656 | **98** | **4** | 0 | 0 | 9 (0 / 6 / 3) | 0 |

(4,000 drawn; 148 parse errors; 85 discards. The 94 at efd 0 includes 11 scored "SQL value not
representable in Python" — jsonb numerics the 15-digit round-trip pushed past DBL_MAX.)

### The other batteries

- **130-case fixture**: 130/130 agree, before and after step zero, at each setting separately
  (§2). One input set among several; not the bar.
- **`A_range`** (20 guard-blast paths at `a = 1e300`): before 16/20 diverge (8 in-subset);
  after **0/20**, per setting (§2).
- **`A2_boundary`** (bisect of where `number($.a)` stops agreeing, `out/A2_boundary_after.txt`):
  - efd **1**: boundary at **DBL_MAX itself** — no corrupted region among Python-representable
    doubles; the first magnitude past it (raw `1e309`) is a **named guard refusal**.
  - efd **0**: first wrong number at **≈ 4.16e9** (`4.16075161600000048e+09`, bisect-path witness).
  - efd **−3**: first wrong number at **≈ 3.22e9**.
- **`B2_overflow`** (overflow/underflow probes, `out/B2_overflow_after.txt`): all overflow and
  underflow sites are **named 22003 refusals**, counted separately, at every setting; addition
  overflow — impossible pre-fix because the mistyped guard clamped operands — now overflows and
  **refuses** rather than answering. `count()` control agrees. At efd 0 one probe's refusal
  arrives as kind `guard` instead of `overflow` (the 15-digit round-trip pushes the operand past
  the guard before the multiply) — same mechanism as §6 M3.
- **`t3_domain_gate`** (§8) and the single-case witnesses of §6.
- Wall clock: ≈ 3 s per 4,000-draw battery (recorded per battery in the outputs, per §7 of the
  framing — for T-4's planning, no performance claim made).

## 6. Wrong answers found — each with witness, class, and detectability

**The answer to the ticket's question is YES: the restricted subset returns wrong numbers, at every
one of the three settings, including the default.** Five distinct mechanisms, M1–M5; M5 is the
allowed refusal class and is in §7, not here. Witnesses below are quoted verbatim from the outputs;
every full case list is in `spikes/T-3/out/`.

### M1 — the Unicode-digit coercion gap (classes 1 and 2; every setting; ordinary `py`-mode data)

Python's `_to_num` gates numeric strings with `_NUM_RE`, whose `\d` matches **Unicode** decimal
digits — `float("１２３")` is `123.0`, and Arabic-Indic `"١٢٣"` likewise. `xpr.num`'s regex gate is
ASCII `[0-9]`, so the same strings become SQL `NULL`. Every one of `sub_ordinary`'s 2 and
`sub_unicode`'s 17 wrong answers per setting traces to this one gap. Witnesses:

| expression | record | Python | SQL | class |
|---|---|---|---|---|
| `max("ΣΊΣΥΦΟΣ", coalesce($.flag, …))` | `flag = "١٢٣"` | `123.0` | **SQL NULL** | 2 |
| `coalesce(min($.b), 0.1)` | `b = "１２３"` | `123.0` | **`0.1`** | 1 — a wrong number a dashboard would display |
| `max(count(- ($.t)), $.d) - count(…)` | `d = "１２３"` | `122.0` | **`-1`** | 1 |
| `($.s > max($.l, …))` | comparison fed by the gap | `False` | **SQL NULL** — filter path: the row silently vanishes | 2 |

**This falsifies the framing §3 expectation** that restricting to the 32 constructs sends the broad
batteries to zero (*"every construct blamed for those 27 is outside the subset"*): the blamed
constructs (`number()`, `string()`, `concat`…) are outside, but the **mechanism** lives in
`xpr.num`, and `xpr.num` is reached by in-subset arithmetic, comparisons, `min`/`max`/`count`
coercion and `if`/`coalesce` plumbing. T-1's construct-level blame assignment was too coarse.

*Detectability at query time:* none today — the SQL side returns clean values and nulls. It could
be **converted to a named refusal** (raise on any regex-rejected string that contains non-ASCII
digits), but it cannot be silently *fixed* to match Python cheaply: Python's `\d` (Unicode
category Nd) has no direct equivalent in Postgres regexes. Reachability in real data: §D.6 measured
tolerant string-coercion as *actually reached, repeatedly* in GIMS data; whether **non-ASCII**
numeric strings occur in Evan's data was not measured by any sweep on the record.

### M2 — containers returned whole: jsonb's exact decimal vs Python's float (class 1; every setting)

When an in-subset expression returns a **container** (bare field read of a list/object, or
`if`/`coalesce` passing one through), the mirrored contract rule (`matches`, from
`tests/test_dashboard_expr.py:20-25`) compares element-wise with **no float tolerance inside
containers** — and jsonb stores the record's numbers as exact decimals. `json.dumps(1e181)` writes
`1e+181`; jsonb holds exactly 10¹⁸¹; the double `1e181` is not that number. Witness (efd 1):

> `$.t` on `t = [1e+181]` → Python `[1e+181]`, SQL `[10000000000000000000000000000000000…]` —
> equal to a consumer that parses JSON numbers as doubles, **unequal under the contract's own rule**
> (Python decodes the SQL answer to `int`, and `int == float` is exact).

32 of `sub_extreme`'s 36 wrong answers at efd 1 are this shape. Scalar reads of the same values
pass, because `matches` applies the 1e-9 epsilon only to top-level numbers. **This is a defect of
the contract rule as much as of the compiler** — but under §4's definitions both engines produced
an answer and the answers differ under the mirrored rule, so it is counted as class 1, not
explained away. It needs magnitudes ≳ 1e17 inside a returned container.

*Detectability:* not a runtime error condition; only visible by changing what the compiled SQL
emits for containers (normalising numbers through `float8` on the way out) — a redesign, out of
T-3's scope, priced here.

### M3 — the value channel truncates at efd 0 and −3 (class 1, plus setting-dependent refusals)

`to_jsonb(float8)` prints 15 significant digits at efd 0 and 12 at efd −3 — **on the value
channel** (M_encoding_guc §M1), i.e. inside every arithmetic result the compiled SQL produces. Any
value whose digits exceed that truncates to a **different number**; the 1e-9 absolute epsilon stops
absorbing the error at ≈ 4.16e9 (efd 0) and ≈ 3.22e9 (efd −3) on the bisect path (§5,
`A2_boundary`). The single most consequential witness (`out/timestamp_witness.txt`), on the
**largest number any GIMS writer on this machine has ever stored** — the epoch-millisecond
timestamp `1,787,169,706,037` (FINDINGS.md §D.3):

| efd | `$.ts + 0` | `$.ts / 1000` |
|---|---|---|
| 1 | agrees | agrees |
| 0 | agrees (13 digits ≤ 15) | agrees |
| **−3** | **`1787169706040`** — wrong number, off by 3 ms | **`1787169706.04`** — wrong number |

**At efd −3 the subset returns a wrong number on data shaped exactly like Evan's own.** No exotic
magnitudes required.

And the same mechanism interacts with the (now correct) guard mid-expression: at efd 0,
`to_jsonb(DBL_MAX)` prints `1.79769313486232e+308`, which is **above** DBL_MAX, so a nested
consumption refuses. One expression, one row, three behaviours
(`out/domain_gate.txt`, and reproduced standalone):

| efd | `($.a + 0) * 1` at `a = DBL_MAX` |
|---|---|
| 1 | **AGREE** |
| 0 | **`XPR01` guard refusal** (37 such refusals in `sub_extreme`) |
| −3 | **class-1 wrong number** (`1.79769313486e+308`) |

This is the `IMMUTABLE` mis-declaration **priced**, as §7 of the framing required: four runtime
functions promise setting-independence while the pipeline's every intermediate value depends on the
setting (`out/immutable_price.txt` shows `xpr.ecma_num(1/3)` returning two different strings in one
session). Q11 closed the index route; the value channel itself is the remaining exposure, and it is
not theoretical — it is 37 refusals and ~60 extra wrong numbers per 3,767 expressions at efd 0.

*Detectability:* fully — **pin the setting**. Every number above says the compiled path is only
correct at efd 1; a production query would have to `SET extra_float_digits = 1` (or per-transaction
`SET LOCAL`) and treat any other value as a configuration defect.

### M4 — raw-JSON rows (non-Python writers): exact storage the Python contract cannot represent

`differ.py`'s `raw` mode is the shape of rows written by anything that is not the GIMS Python
process (ETL, psql, another service) — precisely the high-volume territory Q15 aims autoSQL at.
Four sub-mechanisms, all witnessed at every setting (`out/domain_gate.txt`):

1. **CLASS 4 FOUND — and it is a ninth, uncatalogued Python raise site (soft stop 8).**
   A full-digit JSON integer of 10⁴⁰⁰ decodes to a Python `int`; `_eq` calls `float()` on it
   unguarded and **raises `OverflowError`** while SQL's `IS NOT DISTINCT FROM` answers cleanly:
   > `$.a == 1` at `a = 10⁴⁰⁰` (raw) → Python **raises**, SQL returns `false` — class 4.
   > `$.a != 3` likewise. (`$.a > 1` lands `BOTH_RAISE`: Python raises, the guard refuses.)
   The catalogued eight raise sites (R1–R8) all need out-of-subset constructs; this ninth —
   `float(int)` overflow inside `_eq`/`_order_cmp`/`_to_num` — is reachable **in-subset** on raw
   data. Recorded as a finding; blast radius not chased, per the stop rule.
2. **Subnormal-below-minimum numbers** (`1e-400`): Python's `json.loads` collapses to `0.0`;
   jsonb keeps `1e-400` exactly. `if($.a, 1, 2)` → Python `2`, SQL **`1`** (class 1 — the exact
   case framing §5.3 predicted via `xpr.truthy`); `$.a == 0` → Python `True`, SQL `false`
   (class 1, filter path); `$.a + 0` → **refusal** (`22003` out-of-range, the unguarded underflow).
3. **The 2⁵³ boundary**: `$.a == 9007199254740992` at raw `a = 9007199254740993` → Python `True`
   (float collapse), SQL `false` (exact numeric) — class 1.
4. **Above DBL_MAX**: guarded paths refuse by name (`XPR01` — correct per the ruling), but a
   **bare field read** `$.a` at raw `1e309` routes through no `xpr` function and returns the exact
   numeric where Python has `inf` — class 1 under the mirrored rule.

*Detectability:* 1 and 3 are not detectable by SQL (SQL is the side that answers); they are
Python-side contract gaps on inputs Python's own writer never produces. 2 is partially convertible
to refusals; 4's bare-read case would need the compiler to route bare reads through a guard —
a redesign, priced not fixed.

### Class-3 note

**Zero null → value flips were observed anywhere in the run** — every counted battery, every
setting, both modes.

## 6. Wrong answers found — each with witness, class, and detectability

**The answer to the ticket's question is YES: the restricted subset returns wrong numbers, at every
one of the three settings, including the default.** Five distinct mechanisms, M1–M5; M5 is the
allowed refusal class and is in §7, not here. Witnesses below are quoted verbatim from the outputs;
every full case list is in `spikes/T-3/out/`.

### M1 — the Unicode-digit coercion gap (classes 1 and 2; every setting; ordinary `py`-mode data)

Python's `_to_num` gates numeric strings with `_NUM_RE`, whose `\d` matches **Unicode** decimal
digits — `float("１２３")` is `123.0`, and Arabic-Indic `"١٢٣"` likewise. `xpr.num`'s regex gate is
ASCII `[0-9]`, so the same strings become SQL `NULL`. Every one of `sub_ordinary`'s 2 and
`sub_unicode`'s 17 wrong answers per setting traces to this one gap. Witnesses:

| expression | record | Python | SQL | class |
|---|---|---|---|---|
| `max("ΣΊΣΥΦΟΣ", coalesce($.flag, …))` | `flag = "١٢٣"` | `123.0` | **SQL NULL** | 2 |
| `coalesce(min($.b), 0.1)` | `b = "１２３"` | `123.0` | **`0.1`** | 1 — a wrong number a dashboard would display |
| `max(count(- ($.t)), $.d) - count(…)` | `d = "１２３"` | `122.0` | **`-1`** | 1 |
| `($.s > max($.l, …))` | comparison fed by the gap | `False` | **SQL NULL** — filter path: the row silently vanishes | 2 |

**This falsifies the framing §3 expectation** that restricting to the 32 constructs sends the broad
batteries to zero (*"every construct blamed for those 27 is outside the subset"*): the blamed
constructs (`number()`, `string()`, `concat`…) are outside, but the **mechanism** lives in
`xpr.num`, and `xpr.num` is reached by in-subset arithmetic, comparisons, `min`/`max`/`count`
coercion and `if`/`coalesce` plumbing. T-1's construct-level blame assignment was too coarse.

*Detectability at query time:* none today — the SQL side returns clean values and nulls. It could
be **converted to a named refusal** (raise on any regex-rejected string that contains non-ASCII
digits), but it cannot be silently *fixed* to match Python cheaply: Python's `\d` (Unicode
category Nd) has no direct equivalent in Postgres regexes. Reachability in real data: §D.6 measured
tolerant string-coercion as *actually reached, repeatedly* in GIMS data; whether **non-ASCII**
numeric strings occur in Evan's data was not measured by any sweep on the record.

### M2 — containers returned whole: jsonb's exact decimal vs Python's float (class 1; every setting)

When an in-subset expression returns a **container** (bare field read of a list/object, or
`if`/`coalesce` passing one through), the mirrored contract rule (`matches`, from
`tests/test_dashboard_expr.py:20-25`) compares element-wise with **no float tolerance inside
containers** — and jsonb stores the record's numbers as exact decimals. `json.dumps(1e181)` writes
`1e+181`; jsonb holds exactly 10¹⁸¹; the double `1e181` is not that number. Witness (efd 1):

> `$.t` on `t = [1e+181]` → Python `[1e+181]`, SQL `[10000000000000000000000000000000000…]` —
> equal to a consumer that parses JSON numbers as doubles, **unequal under the contract's own rule**
> (Python decodes the SQL answer to `int`, and `int == float` is exact).

32 of `sub_extreme`'s 36 wrong answers at efd 1 are this shape. Scalar reads of the same values
pass, because `matches` applies the 1e-9 epsilon only to top-level numbers. **This is a defect of
the contract rule as much as of the compiler** — but under §4's definitions both engines produced
an answer and the answers differ under the mirrored rule, so it is counted as class 1, not
explained away. It needs magnitudes ≳ 1e17 inside a returned container.

*Detectability:* not a runtime error condition; only visible by changing what the compiled SQL
emits for containers (normalising numbers through `float8` on the way out) — a redesign, out of
T-3's scope, priced here.

### M3 — the value channel truncates at efd 0 and −3 (class 1, plus setting-dependent refusals)

`to_jsonb(float8)` prints 15 significant digits at efd 0 and 12 at efd −3 — **on the value
channel** (M_encoding_guc §M1), i.e. inside every arithmetic result the compiled SQL produces. Any
value whose digits exceed that truncates to a **different number**; the 1e-9 absolute epsilon stops
absorbing the error at ≈ 4.16e9 (efd 0) and ≈ 3.22e9 (efd −3) on the bisect path (§5,
`A2_boundary`). The single most consequential witness (`out/timestamp_witness.txt`), on the
**largest number any GIMS writer on this machine has ever stored** — the epoch-millisecond
timestamp `1,787,169,706,037` (FINDINGS.md §D.3):

| efd | `$.ts + 0` | `$.ts / 1000` |
|---|---|---|
| 1 | agrees | agrees |
| 0 | agrees (13 digits ≤ 15) | agrees |
| **−3** | **`1787169706040`** — wrong number, off by 3 ms | **`1787169706.04`** — wrong number |

**At efd −3 the subset returns a wrong number on data shaped exactly like Evan's own.** No exotic
magnitudes required.

And the same mechanism interacts with the (now correct) guard mid-expression: at efd 0,
`to_jsonb(DBL_MAX)` prints `1.79769313486232e+308`, which is **above** DBL_MAX, so a nested
consumption refuses. One expression, one row, three behaviours
(`out/domain_gate.txt`, and reproduced standalone):

| efd | `($.a + 0) * 1` at `a = DBL_MAX` |
|---|---|
| 1 | **AGREE** |
| 0 | **`XPR01` guard refusal** (37 such refusals in `sub_extreme`) |
| −3 | **class-1 wrong number** (`1.79769313486e+308`) |

This is the `IMMUTABLE` mis-declaration **priced**, as §7 of the framing required: four runtime
functions promise setting-independence while the pipeline's every intermediate value depends on the
setting (`out/immutable_price.txt` shows `xpr.ecma_num(1/3)` returning two different strings in one
session). Q11 closed the index route; the value channel itself is the remaining exposure, and it is
not theoretical — it is 37 refusals and ~60 extra wrong numbers per 3,767 expressions at efd 0.

*Detectability:* fully — **pin the setting**. Every number above says the compiled path is only
correct at efd 1; a production query would have to `SET extra_float_digits = 1` (or per-transaction
`SET LOCAL`) and treat any other value as a configuration defect.

### M4 — raw-JSON rows (non-Python writers): exact storage the Python contract cannot represent

`differ.py`'s `raw` mode is the shape of rows written by anything that is not the GIMS Python
process (ETL, psql, another service) — precisely the high-volume territory Q15 aims autoSQL at.
Four sub-mechanisms, all witnessed at every setting (`out/domain_gate.txt`):

1. **CLASS 4 FOUND — and it is a ninth, uncatalogued Python raise site (soft stop 8).**
   A full-digit JSON integer of 10⁴⁰⁰ decodes to a Python `int`; `_eq` calls `float()` on it
   unguarded and **raises `OverflowError`** while SQL's `IS NOT DISTINCT FROM` answers cleanly:
   > `$.a == 1` at `a = 10⁴⁰⁰` (raw) → Python **raises**, SQL returns `false` — class 4.
   > `$.a != 3` likewise. (`$.a > 1` lands `BOTH_RAISE`: Python raises, the guard refuses.)
   The catalogued eight raise sites (R1–R8) all need out-of-subset constructs; this ninth —
   `float(int)` overflow inside `_eq`/`_order_cmp`/`_to_num` — is reachable **in-subset** on raw
   data. Recorded as a finding; blast radius not chased, per the stop rule.
2. **Subnormal-below-minimum numbers** (`1e-400`): Python's `json.loads` collapses to `0.0`;
   jsonb keeps `1e-400` exactly. `if($.a, 1, 2)` → Python `2`, SQL **`1`** (class 1 — the exact
   case framing §5.3 predicted via `xpr.truthy`); `$.a == 0` → Python `True`, SQL `false`
   (class 1, filter path); `$.a + 0` → **refusal** (`22003` out-of-range, the unguarded underflow).
3. **The 2⁵³ boundary**: `$.a == 9007199254740992` at raw `a = 9007199254740993` → Python `True`
   (float collapse), SQL `false` (exact numeric) — class 1.
4. **Above DBL_MAX**: guarded paths refuse by name (`XPR01` — correct per the ruling), but a
   **bare field read** `$.a` at raw `1e309` routes through no `xpr` function and returns the exact
   numeric where Python has `inf` — class 1 under the mirrored rule.

*Detectability:* 1 and 3 are not detectable by SQL (SQL is the side that answers); they are
Python-side contract gaps on inputs Python's own writer never produces. 2 is partially convertible
to refusals; 4's bare-read case would need the compiler to route bare reads through a guard —
a redesign, priced not fixed.

### Class-3 note

**Zero null → value flips were observed anywhere in the run** — every counted battery, every
setting, both modes.

## 7. Refusals — counted, named, never pooled

Every refusal in the run carried an identifiable SQLSTATE, was verified distinct from parse/type/
missing-function errors (the §5.1 control's N8 proves an unidentifiable raise lands in a different
class), aborted rather than answering, and stayed in the denominator. Kinds per battery and
setting:

| battery | efd | guard (`XPR01`) | overflow (`22003`) | underflow (`22003`) | out-of-range (`22003`) |
|---|---|---:|---:|---:|---:|
| `sub_ordinary` | 1 / 0 / −3 | 0 | 0 | 0 | 0 |
| `sub_unicode` | 1 / 0 / −3 | 0 | 0 | 0 | 0 |
| `sub_extreme` | 1 | 0 | 6 | 3 | 0 |
| `sub_extreme` | 0 | **37** | 5 | 3 | 0 |
| `sub_extreme` | −3 | 0 | 6 | 3 | 0 |

Refusal rate at the default setting, adversarial magnitudes: **9 / 3,767 ≈ 0.24%**; at efd 0 it
rises to 45 / 3,767 ≈ 1.2%, all but eight of them manufactured by the value channel itself
(§6 M3). Ordinary- and unicode-profile data never refused at all. The domain gate and `B2` add the
per-shape witnesses: overflow refusals for products/sums/quotients past DBL_MAX (`$.qty * $.price`
at 1e200², addition of two DBL_MAXes — newly reachable post-fix, and refused), underflow refusals
for products below the subnormal floor including inside a filter-shaped `if`, `out_of_range` for
raw `1e-400` arithmetic, and `XPR01` for everything the guard turns away. `BOTH_RAISE` occurred
once (raw huge-int `$.a > 1`: Python raised, the guard refused) and is reported here, not as a
wrong answer.

**No refusal-rate threshold is applied** — deliberately, per framing §4.7. The rate is produced;
the line across it is Evan's to draw.

**Ruling R6 (NULLNESS) discharged:** zero `NULLNESS` cases arose in every counted battery at every
setting. The representations were still tested rather than assumed (`out/nullness_probe.txt`):
in a `WHERE xpr.truthy(v)` filter, SQL `NULL` and jsonb `'null'` behave **identically** (both
dropped); in `ORDER BY` they land at **opposite ends** (jsonb `'null'` sorts before every value,
SQL `NULL` after). So a representation leak *would* reorder rows — but no in-subset expression was
observed producing one, so there is nothing to promote to class 2.

## 8. The domain gate (§5.3) — what was reached, what was not

**Half one — class-4 emptiness.** Mechanically, every counted expression passed the subset walker
(no `round`/`floor`/`ceil`/`%`/date builtins; `==`/`!=` container-operand draws witnessed at
runtime via the real `_eq` and discarded, 68–85 per battery). Infinity was composed from permitted
arithmetic (`$.a * $.b` at 1e200²) and pushed through `abs`, a comparison, `min`, and `if`:
**Python raised in 0 of 5 cases** (it answers `inf`/`True`/`1.0`), SQL refused by name — so on
`py`-mode data the class-4 emptiness is demonstrated, not assumed, and the fuzz batteries' class-4
zeros mean something. **On raw data the demonstration produced the opposite**: a ninth raise site
(§6 M4.1), so class 4 is *not* structurally empty once non-Python writers exist. That is a
finding, not a gate failure — the gate did exactly what it exists to do.

**Half two — every magnitude row reached, with witnesses** (battery witness tables +
`out/domain_gate.txt`; nothing reported `untested`):

| required row | reached by | representative outcome |
|---|---|---|
| old guard boundary, both sides | `sub_extreme` pool + gate | AGREE at efd 1; class 1 at efd 0/−3 (M3) |
| real limit DBL_MAX, below/at | `sub_extreme` + gate | AGREE at efd 1; class 1 / `XPR01` at 0/−3 |
| real limit, above | gate, **raw mode** (no Python float can carry it) | `XPR01` refusals; bare read class 1 (M4.4) |
| infinity composed by arithmetic | gate half one | Python answers, SQL refuses `overflow` |
| subnormals `5e-324`, `1e-320` | `sub_extreme` + gate | AGREE (py mode); raw `1e-400` → M4.2 |
| `2**53`, `2**53 + 2` | `sub_extreme` + gate | AGREE at efd 1; class 1 at efd 0/−3; raw `…993` class 1 |
| `0.0`, `-0.0` | `sub_extreme` + gate | AGREE everywhere tested (sign-of-zero not visible in-subset) |
| coercing strings `" 7 "`, `"1e3"`, `"１２３"` | all three batteries + gate | ASCII ones AGREE; `"１２３"`/`"١٢٣"` → M1 |

The A.3 mistake was not repeated: the domain provably reaches the places where the measured
failures live, and the witnesses are printed in the outputs.

## 9. Admissibility checklist (§5) — verified / not verified, item by item

| # | condition | status |
|---|---|---|
| 1 | every battery at all three settings, never pooled | **verified** — §5's tables are per-setting; no pooled figure appears anywhere in this document |
| 2 | input-domain gate passed and printed, both halves | **verified** — §8; witnesses printed in `out/`; no row `untested` |
| 3 | `differ.py` shown able to report a failure | **verified** — §3, ten injection classes, per setting, pre- and post-fix |
| 4 | no out-of-subset construct counted | **verified mechanically** — the closure walker ran on every generated expression (a leak aborts the battery; none did), plus the runtime `_eq` container witness with discard counts printed |
| 5 | input fingerprints recorded | **verified** — sha256 of `expr.py`, `compile.py`, `runtime.sql` + efd read-back + seed + N in every battery output; conformance JSON carries its own |
| 6 | no production-traffic fraction; fixture not presented as the bar | **verified** — no such fraction exists in this document; the fixture appears only as one input set (§2, §5) |
| 7 | guard fix with before-and-after | **verified** — §2, both states, all three settings, fixture included |
| 8 | above-DBL_MAX divergence on its own line | **verified** — §7 guard-refusal column and §6 M4.4's bare-read case, never folded into pass or fail |
| 9 | nothing written into either GIMS checkout | **verified** — imports only, `PYTHONDONTWRITEBYTECODE=1` on every invocation; the pre-existing `core/dashboard/__pycache__` snapshot compared clean after the run (§0) |
| 10 | no real number before the negative control passed | **verified** — the control ran and passed (pre-fix form) before the first before-state number; run order is preserved in `out/` and in this document's history |
| 11 | float-digit setting proven changed | **verified** — §4, read-back + three pairwise-distinct value-channel outputs, plus the control per setting |
| 12 | `SQL_RAISE` split before quoting | **verified** — the split is in `differ.py` itself (`SQL_REFUSAL` + kind vs `SQL_RAISE`), exercised by control injections N5–N8; unexplained raises were **zero** everywhere |

**Not verified / honest limits of this run:**

- The `raw`-mode findings (§6 M4) come from **directed single-case probes**, not from a broad
  random raw-JSON fuzz battery; a raw-mode analogue of battery H was not built (the record's
  `D_rawjson` battery exists but was not extended to the subset under the timebox). The witnesses
  are real; the *rates* on raw data are unmeasured.
- The A2 truncation boundaries (≈ 4.16e9 / ≈ 3.22e9) are bisect-path witnesses, not proofs of the
  exact frontier — the first wrong value depends on digit pattern, not only magnitude.
- Whether non-ASCII numeric strings (M1) occur in Evan's actual data was not measured (no sweep on
  the record covers string *content*; §D.6 measured coercion reachability, not scripts).
- The fixture's 130/130 says nothing beyond the fixture (Q2 stands).

## 10. Verdict against §3's bar

**The bar is zero wrong answers of any kind, per setting. The subset FAILS it at every setting —
including the default — and the failure is not the guard defect, which step zero closed.**

| setting | class 1 | class 2 | class 3 | class 4 | bar |
|---|---:|---:|---:|---:|---|
| efd = 1 | 39 across the three batteries (+ raw-mode probe cases) | 16 | 0 | 0 in py mode; **found in raw mode** | **FAIL** |
| efd = 0 | 101 | 15 | 0 | same | **FAIL** |
| efd = −3 | 105 | 16 | 0 | same | **FAIL** |

(Battery-level breakdowns in §5; these row totals are sums across the three subset batteries at one
setting, shown only to make the verdict line readable — the per-battery, per-setting counts are the
result of record.)

What the failure is made of matters more than the count:

1. **At efd 1** — the setting production would pin — the wrong answers come from two mechanisms:
   the Unicode-digit coercion gap (M1: real class-2 row-loss and class-1 wrong numbers on
   string-bearing data) and the container/exact-decimal contract gap (M2: wrong under the
   contract's own comparison rule, invisible to a double-parsing consumer). **Neither is the
   1e300 guard defect; both survive step zero.**
2. **At efd 0 and −3** the value channel itself lies (M3), starting at magnitudes as small as a
   few billion — and at −3 it corrupts an epoch-millisecond timestamp, the exact shape of the
   largest value in Evan's real data. Q10's three-settings requirement earned its keep: a
   one-setting run at efd 1 would have called this "close to green".
3. **On raw-written rows** (M4) the Python evaluator itself stops being total (ninth raise site,
   class 4) and exact storage splits from float semantics. autoSQL is aimed at high-volume data
   GIMS does not hold yet (Q15); if any of that data is written by anything other than the GIMS
   Python process, this class is live.
4. **The refusal machinery works as ruled**: the guard refuses loudly and identifiably, overflow
   and underflow refuse natively, the caller can tell every refusal from a defect, and refusal
   rates are small and quoted (§7). The GA-4 ruling's shape — loud refusal, zero-wrong-answer
   bar retained — was implementable and is implemented. **It is the remaining mechanisms, not the
   refusal design, that fail the bar.**

Per the seat's scope this is the report of `sp-investigate`; the synthesis and the go/no-go
recommendation belong to `sp-synth` / `sp-decide`. Stop rules honoured: hard stops 1–5 never
fired; soft stop 6 fired (wrong answers found — the run continued only to characterise, across all
three settings, and never hunted a better-looking configuration); soft stop 8 fired once (the
ninth raise site, recorded, not chased).

---

## 11. Run hygiene, closed out

- Throwaway container `autosql-t3-throwaway` torn down with `-v` after the run; no dangling
  volume left; `glp-strong-db` verified still up, healthy, and never connected to.
- GIMS checkouts verified byte-clean of new artifacts (pycache snapshot match).
- Disk: 96% at start, 96% at end; no large tables were ever created.
- Every instrument edit and new script is in the working tree (uncommitted — committing is the
  dispatching session's call); raw outputs in `spikes/T-3/out/`.
