## Cross-cutting A — is `expr` total? The premise FRAMING §5 rests on

FRAMING §5 argues from one premise: *"`expr` is **total** — it never throws, it returns `null`.
SQL is not."* Two finding sections read that premise oppositely **as first drafted**. **f2 §2.4**
wrote: "0 `PYTHON_RAISED` over 403 adversarial inputs is 403 independent confirmations of the
totality premise the design rests on". **f1 §1.9.3** wrote: "`expr` itself raises, contradicting
`expr.py:640` and `recon/semantics.md` §11."

**[punch] Reading note on the f2 quotation.** That f2 sentence is quoted here, and again in §A.3,
in the form it was **originally written**. It no longer stands in f2: on this section's
adjudication (§A.6) f2 has **deleted the inference and kept the bare count**, and §2.4 now carries
a forward footnote to §A.6 giving the reason. Nothing below is a rebuttal of live f2 text; it is
the adjudication that caused the withdrawal, set out with the evidence that forced it. f1 §1.9.3's
sentence, by contrast, **stands** — and f1 has since widened its own basis for it from four date
witnesses to the eight mechanisms enumerated in §A.2 (§A.6).

**Both statements are true of their own evidence, and the premise as stated is false.** This
section establishes the truth from source and re-verified witnesses, reconciles the two
instruments, and states what falls out for §5 and for the fallback design.

`core/dashboard/expr.py` is byte-identical across both GIMS trees (`md5 5bd9db65de20678d4e070c8ad823c3ce`,
`GIMS-Project@995cc59` and `gims-ledger@7b7a049`), so everything below holds for both. Every
witness in this section was re-run by this seat in `GIMS-Project/.venv` (Python 3.12.3) through the
**public** entry point `expr.evaluate(parse(src), record, ctx)` — not through `_FUNCTIONS[...]`
directly — and every raise reached the caller.

### A.1 What the totality claim actually says, and what it is being used to mean

| where | text | scope it actually claims |
|---|---|---|
| `expr.py:640` | "Evaluate a parsed AST against one record. **Never raises for data reasons (→ null).**" | `evaluate()`, unconditional. This is the strongest form and it is the one cited. |
| `expr.py:17-19` | "**Total, not throwing.** Every operation returns `null` rather than raising on bad input (missing field, non-numeric operand, unparseable date, divide-by-zero). Only a *syntax* error (at `parse` time) raises `ExprError`." | Enumerates **four** bad-input classes. All four are genuinely handled. It does not say "these are the only ways bad input arrives." |
| `expr.py:306` | `_to_num`: "never raises, **never returns NaN**" | True — and load-bearing in the wrong direction. `_to_num` **does** return `±inf` (verified: `abs($.a)` on `{"a":"1e400"}` → `inf`). That `inf` is the direct feedstock of four of the eight raise sites below. |
| `recon/semantics.md` §11 | "**`expr.py` never raises for data reasons** … every function surveyed above (§2-§10) independently confirms it" | The survey is a *reading of the guarded paths*. It is correct about every path it enumerates; it did not enumerate the unguarded ones. |
| `sources.py:136` | "Missing/bad data yields None (**evaluator is total**)" | The consuming code has adopted the strong form as an invariant. |
| `sources.py:335` | "data problems degrade to empty/None, **never crash**" | The public contract of `resolve()`. Falsified in §A.4. |

**INFERENCE (this seat):** the four classes at `:17-19` are the *designed* total behaviour and are
airtight. The `:640` docstring generalises them to "never raises for data reasons", and that
generalisation is what §5, `semantics.md` §11 and `sources.py` all consume. The generalisation is
the false step, not the design.

### A.2 Every mechanism by which `evaluate()` raises on data — 8 mechanisms, 9 lines, 4 exception types

Each row was re-verified by this seat. "Witness" is a complete `(source, record)` pair; every one
raised out of `evaluate()` with the traceback's last frame at the cited line.

| # | site | exception | why it is unguarded | witness (`src` / `record`) | trigger threshold (measured) |
|---|---|---|---|---|---|
| **R1** | `expr.py:430` `_parse_date_ms` | `OverflowError: date value out of range` | the `try/except ValueError` at `:418-426` wraps only the `datetime(...)` constructor; the UTC-offset subtraction at `:430` is **outside** it, and `datetime.min - timedelta` raises `OverflowError`, not `ValueError` | `days_between($.d,"2024-01-02")` / `{"d":"0001-01-01T00:00:00+14:00"}` | an ISO date whose offset pushes it outside years 1–9999. Regex `expr.py:402-406` (offset group at `:405`) admits offsets to `+99:99` = **6039 min = 4.194 d**. Exhaustive scan: **9 dates** in the whole calendar can raise (`0001-01-01..05` with `+00:01/+24:01/+48:01/+72:01/+96:01` and up; `9999-12-28..31` with `-24:00` and down) = **2.464e-06** of the 3 652 059-day parseable domain |
| **R2** | `expr.py:521` `_fn_round` | `OverflowError: cannot convert float infinity to integer` | `int(_to_num(args[1]))` — `_to_num` returns `inf` for `"1e400"`, and `int(inf)` raises | `round($.a,$.n)` / `{"a":1.0,"n":"1e400"}` | 2nd arg coerces to `±inf` |
| **R3** | `expr.py:525` `_fn_round` | `OverflowError: int too large to convert to float` | `factor = 10 ** ndig` is an arbitrary-precision **int**; `x * factor` must convert it to `float` | `round($.a,400)` / `{"a":1.0}` | bisected: **ndig = 308 ok, ndig ≥ 309 raises** |
| **R4** | `expr.py:526` `_fn_round` | `OverflowError: cannot convert float infinity to integer` | `int(abs(scaled) + 0.5)` where `scaled = x * factor` overflowed to `inf` | `round($.a,3)` / `{"a":1.7976931348623157e308}`; also `round($.a,20)` / `{"a":1.7e296}` | `\|x · 10^ndig\| ≥ ~1.8e308` |
| **R5** | `expr.py:527` `_fn_round` | `ZeroDivisionError: float division by zero` | `r / factor` where `factor = 10 ** ndig` underflowed to `0.0` | `round($.a,-324)` / `{"a":1.0}` | bisected: **ndig = −323 ok (`10**-323 = 1e-323`), ndig ≤ −324 raises (`10**-324 == 0.0`)** |
| **R6** | `expr.py:545` / `:546` `floor` / `ceil` | `OverflowError: cannot convert float infinity to integer` | `math.floor/ceil` of `±inf`; the lambdas guard only `is not None` | `floor($.a)` / `{"a":"1e400"}`; `ceil($.a)` / `{"a":"-1e400"}`; `floor($.a * $.a)` / `{"a":1e200}` | argument evaluates to `±inf` |
| **R7** | `expr.py:624` `_eval` (`%`) | `ValueError: math domain error` | `math.fmod(ln, rn)`; the guard is `rn == 0` only. `fmod(inf, 2)` raises; `fmod(2, inf)` = `2.0` | `$.a % 2` / `{"a":"1e400"}`; `($.a * $.a) % 2` / `{"a":1e200}` | **dividend** is `±inf` (divisor being infinite is safe) |
| **R8** | `expr.py:375` `_eq` | `RecursionError: maximum recursion depth exceeded` | `_eq` recurses structurally through lists/dicts with no depth cap | `$.a == $.b` / two lists nested 498 deep | bisected: **depth 497 ok, depth 498 raises** at `sys.getrecursionlimit() = 1000` |

**Root cause shared by R2, R4, R6, R7 (4 of 8):** `_to_num` promises "never returns NaN" and
delivers it, but returns `±inf` freely — from a JSON *string* (`"1e400"`), from a JSON *number*
(`1.7976931348623157e308`), or from ordinary arithmetic (`1e200 * 1e200`). Nothing downstream
re-checks finiteness before `int()` / `math.floor` / `math.ceil` / `math.fmod`.

**Reachability, stated plainly.** R2–R5 need no unusual *data* at all — `round($.x, 400)` and
`round(1.7976931348623157e308, 3)` are triggered by the **expression text a tenant writes**, and
that text is accepted by `parse()` without complaint (verified: `round(1.7976931348623157e308, 3)`
with record `{}` raises `OverflowError` out of `evaluate()`). R1, R6 and R7 need one field value;
`"1e400"` and `"0001-01-01T00:00:00+14:00"` are both ordinary JSON strings, storable in any jsonb
or SQLite column. **Not established by this spike:** whether any real GIMS project holds such a
value. Establishing it would need a read-only value-domain sweep of the record stores — the same
sweep f2 §2.9 ran for dashboards, re-pointed at field values.

### A.3 Reconciling f2's 403/403 with the measured raise rates — both are correct

The two instruments do not sample the same input space. **The 403 coverage probes cannot reach a
single one of the eight sites**, by construction, not by luck. Domain re-derived by this seat
directly from `proto/coverage_probe_results.json` (403 entries) and the generator
`proto/coverage_probe.py:26-105`:

| site | needs | what the 403-probe domain actually contains |
|---|---|---|
| R1 | date within 4.194 d of the year-1/9999 boundary **and** a non-`Z` offset | **0** offset-bearing date strings; the only ISO dates are `2026-01-01`, `2026-01-02` |
| R2 | `\|ndigits\|` → `inf` | the only `round()` ndigits literals are **`-1`** and **`2`** |
| R3 | ndigits ≥ 309 | max ndigits **2** |
| R4 | `\|x·10^n\| ≥ 1.8e308` | **max \|numeric value\| anywhere in all 403 records + literals = 2026.0** — and that bound is loose in the safe direction. Re-derived exactly for this pass **[punch]**: max \|value\| in any *record* is **9**; max bare numeric *literal* in any probe source is **4.0**; the 2026.0 is the year inside the string `"2026-01-01"`, not a number either engine ever holds. The real domain is **smaller** than stated, so R4 is further out of reach, not nearer. `f2` §2.4's footnote reports the same re-derivation |
| R5 | ndigits ≤ −324 | min ndigits **−1** |
| R6 | `floor`/`ceil` argument `±inf` | `floor()` / `ceil()` appear **zero-arg only** |
| R7 | `%` with infinite dividend | the token `%` occurs in **0 of 403** probe sources |
| R8 | container nesting ≥ 498 | **max record nesting depth = 4** |

f2 §2.4's original "403 independent confirmations" was therefore **403 confirmations of a claim the
probe set cannot test** — which is why §A.6 ordered the inference deleted, and why f2 has since
deleted it while retaining the count. **[punch]** The probes are excellent at what they were built
for — the 6×6 operand-*kind* matrix, closing `_eq` 7/36→36/36 and `_order_cmp` 4/36→36/36 — and a kind matrix is orthogonal to a
*magnitude/boundary* domain. The correct reading of the row is: **0 `PYTHON_RAISED` because the
generator's value domain tops out at 2026.0, depth 4, and two mid-calendar dates.**

The same explanation covers the other clean batteries, and it is structural, not statistical:

| instrument | n | Python raises | why |
|---|---|---|---|
| `expr_vectors.json` via `evaluate()` (re-run by this seat) | 130 | **0 / 130** | the conformance contract fixture contains no boundary case. This is why the spike's primary instrument never saw it. |
| `proto/coverage_probe_results.json` | 403 | **0 / 403** | table above |
| `fuzz/H_ordinary.txt` + `H_extreme.txt` + `H_unicode.txt` (`differ.run_case`, which **has** a `PY_RAISE` bucket — `differ.py:77,150`, `H_ast_fuzz.py:159`) | 12 000 | **0 / 12 000** | `H_ast_fuzz.py:28-30` `DATES` holds `"0001-01-01"`, `"9999-12-31"` and `"…T00:00:00+05:30"` but **never an extreme year combined with an offset** → R1 unreachable. `round` is in `UNARY` only (`:100-101`), and is absent from `BINARY_FN` (`:102-103`), never called with 2 args → R2/R3/R4/R5 unreachable. R6/R7 need a composed `inf` and are reachable but were not sampled in 12 000 draws. |
| `fuzz/E_dates.txt` | 45 | **4 `PY_RAISE`** (8.9%) | the only battery that combined an extreme year with an offset. Its own comment at `E_dates.py:46-47` names the mechanism: *"the offset is applied to the datetime, and that arithmetic is OUTSIDE the try/except (expr.py:418-431)"*. |
| `fuzz/G2b_round_raises.txt` | 8 000 | **65 `BOTH_RAISE`** = 0.8125%, `PY_RAISE_ONLY` 0 | the only battery that varied `round`'s ndigits. **Re-derived by this seat**, same seed 13, Python side only, no DB: **exactly 65 raises, 100% of them at `expr.py:526` (R4)**, witness `round(1.7976931348623157e+308, 3.0)`. Its ndigits domain is `[-20,20]`, so it cannot reach R2/R3/R5. |
| `fuzz/B2_overflow.txt:11-14` | — | 1 `BOTH_RAISE` | `round($.a, 20)` / `{"a":1.7e296}` → R4 |

**Verdict on the contradiction: f1 §1.9.3 is right and f2 §2.4's inference was wrong — and f2 has
since withdrawn it. [punch]** f2's *count* is accurate and is retained; the inference drawn from it
was not, because a zero over a domain that cannot reach the failure is not evidence about the
failure.

### A.4 The premise in its narrow true form

The strong form ("`evaluate()` never raises for data reasons") is **false**. The narrow form, which
is what §A.2's eight sites leave standing, is true and is the form the compiler author should hold:

> `evaluate()` returns a value rather than raising **provided all four hold**:
> **N1** — no date-shaped operand carries a non-`Z` UTC offset that pushes it outside years 1–9999
> (i.e. every offset-bearing date is more than 4.194 days inside both boundaries);
> **N2** — no `floor()` / `ceil()` / `round()` argument and no `%` dividend evaluates to `±inf`;
> **N3** — `round()`'s second argument, after `_to_num`, is in **[−323, +308]**;
> **N4** — no `==` / `!=` operand is a container nested ≥ 498 levels.
>
> `expr.py:17-19`'s four *named* classes — missing field, non-numeric operand, unparseable date,
> divide-by-zero — are total without qualification. Nothing in the file checks N1–N4, and N2/N3 are
> reachable from tenant-written expression text alone, with no unusual stored data.

### A.5 Consequence for FRAMING §5 — and the part FRAMING §5 did not consider **[consistency]**

**(i) The "raise → value" clause needs restating.** §5 forbids "a raise into a value" while
assuming only *SQL* can raise. The real direction matrix is the reverse of what §5 imagines. Every
mechanism was put through the existing differential instrument `analysis/fuzz/differ.py`
(`run_case`, read-only `SELECT`s against `autosql_spike`, `extra_float_digits = 1`) by this seat:

| mech | Python | compiled SQL | direction | §5 status |
|---|---|---|---|---|
| R1 `days_between` yr-1 `+14:00` | `OverflowError` | `738886.5833333334` | **raise → value** | §5 clause 2 breached |
| R1 `date_add` yr-1 `+00:01` | `OverflowError` | `'0001-01-01T23:59:00Z'` | **raise → value** | breached |
| R2 `round($.a,"1e400")` | `OverflowError` | `1` | **raise → value** | breached |
| R8 depth-498 `==` | `RecursionError` | `True` | **raise → value** | breached |
| R3 `round($.a,400)` | `OverflowError` | `SQLSTATE 22003 overflow` | both raise | — |
| R4 `round($.a,20)` @ `1.7e296` | `OverflowError` | `SQLSTATE 22003 overflow` | both raise | — |
| R5 `round($.a,-324)` | `ZeroDivisionError` | `SQLSTATE 22003 underflow` | both raise | — |
| R4 `round($.a,3)` @ DBL_MAX | `OverflowError` | `NULL` (masked by the f8 guard, f1 D1–D5) | raise → null | not named by §5 |
| R6 `floor("1e400")` / `ceil("-1e400")` | `OverflowError` | `NULL` | raise → null | not named by §5 |
| R7 `$.a % 2` @ `"1e400"` | `ValueError` | `NULL` | raise → null | not named by §5 |

**4 of 11 witnesses are §5's own disqualifying direction, arriving from the side §5 did not
anticipate.** **[punch]** *(The table has **10 rows** and **11 witnesses**: the R6 row carries both
`floor("1e400")` and `ceil("-1e400")`. Row-wise the split is 4 raise→value / 3 raise→null /
3 both-raise; witness-wise 4 / 4 / 3. The disqualifying count is **4** under either reading.)*
The restatement §5 needs: *the compiler must not turn a raise into a value **in
either runtime's direction**, and the reference runtime is not a total function, so "agrees with
Python" is undefined on N1–N4 inputs — the compiler must **refuse** them, not compile them.*

**(ii) The in-memory fallback can itself raise. This is the finding.** **[consistency]** `xc` C.3
(the `D7` row) and `xc` C.11(a) reach the same fact from the divergence-register side — "on the
0.81% `BOTH_RAISE` subset the in-memory retry raises too" — and this section is the one that
measures it end-to-end, at the call sites, with the blast radius. The
fallback target is `sources.py:147` (`row[name] = evaluate(ast, row, context)`) and `sources.py:162`
(`if not truthy(evaluate(where_ast, row, context))`). **Neither is inside a `try`.** `_compile` at
`:122-130` wraps `parse()` in an `AppError`; nothing wraps `evaluate()`. Measured by this seat, by
calling `sources.py`'s own projection functions on a 10-row list with one poison row
`{"d":"0001-01-01T00:00:00+14:00"}`:

| poison row position | `_apply_derive` | `_filter_rows` |
|---|---|---|
| first (index 0) | **uncaught `OverflowError`**, last frame `expr.py:430` | **uncaught `OverflowError`** |
| middle (index 5) | **uncaught `OverflowError`** | **uncaught `OverflowError`** |
| last (index 9) | **uncaught `OverflowError`** | **uncaught `OverflowError`** |
| control: same 9 rows, no poison | 9 rows returned | 5 rows returned |

`OverflowError` / `ValueError` / `ZeroDivisionError` / `RecursionError` are not `HTTPException`
subclasses, so `core/errors.py:115-119`'s `@app.exception_handler(Exception)` catches them and
returns **HTTP 500 `INTERNAL_ERROR`**, not the 400 `AppError` path — **INFERENCE (this seat)**, read
off the handler registration at `core/errors.py:113-119`; the raises above are measured, the HTTP
status they surface as is not (no request was issued against a running GIMS app). **[consistency]**
Blast radius is the **entire widget**: one row in 20 000 loses all of them, at any position, with no partial result and no
fallback signal. `sources.py:335`'s public contract — "data problems degrade to empty/None, never
crash" — is false today, independently of this spike.

**What that does to the fallback design, said plainly:**

1. **"SQL raised → fall back to in-memory" is not a safe harbour.** The raise sets overlap.
   Measured on the one battery that quantifies it (`G2b_round_raises.txt`, n = 8000): Postgres
   raised on `94 + 65 = 159` probes; Python raised on **65 of those same 159**. The fallback
   rescues **59.1%** of SQL raises in that domain and **40.9% (65/159) die in the fallback too** —
   the request 500s after paying the full pushdown-plus-rescan cost. A fallback whose rescue rate is
   ~59% on the only measured domain cannot be presented as a totality guarantee.
2. **The fallback is not currently a *reported* failure — it is an uncaught 500.** FRAMING §5 says
   a fallback must be "reported, never silent". A 500 is loud but it is not a *report*: it carries
   no `pushed_down: false`, no reason, no partial result. Making the fallback reportable requires
   wrapping `evaluate()` per row — which is a **change to `sources.py`, in the GIMS tree**, not to
   the compiler. That cost belongs in FRAMING §4 #5's "cost of the fallback machinery" and is
   currently priced nowhere (f2 §2.8, f4 §4.9).
3. **The direction to refuse at compile time is now larger than f2 §2.7's fallback table.** N1–N4
   are *value*-domain conditions, not *construct*-domain conditions, so they are not statically
   decidable from the AST for R1, R4, R6, R7 and R8 (they depend on the row). Only R2, R3 and R5 are
   statically refusable when `round`'s second argument is a literal. **OPINION (this seat):** the
   only design that keeps §5's guarantee is a per-row `try/except` around *both* runtimes that
   degrades that row to `null` and sets a reported flag — i.e. the compiler cannot fix this, and the
   in-memory path has to be made total first, in GIMS, before pushdown can claim to match it.

**Not established by this spike** (and not chased, per FRAMING §3): the production frequency of
N1–N4 inputs; whether R6/R7 are reachable at all under `H_ast_fuzz`'s generator given enough draws
(0 in 12 000 bounds it only at ≲0.025% at 95% confidence, and that generator is not production
traffic); and the raise behaviour of `frontend/lib/expr.js`, the third contract runtime — JS has no
`OverflowError`, so the JS mirror almost certainly **diverges from Python on all eight sites**,
which would make the two runtimes disagree on the very inputs the fixture is supposed to bind. What
would establish the last one: run the eight witnesses through `frontend/lib/expr.js` under node and
compare. That is one instrument the spike never built.

### A.6 Corrections this section forces on the other sections

| section | text | correction |
|---|---|---|
| f2 §2.4 | "0 `PYTHON_RAISED` over 403 adversarial inputs is **403 independent confirmations of the totality premise**" | **Delete the inference, keep the count.** The 403-probe domain (max \|value\| 2026.0, max nesting 4, ndigits ∈ {−1,2}, zero `%`, zero offset-bearing dates) cannot reach any of the 8 raise sites. Correct wording: "0 `PYTHON_RAISED` — the probe set's value domain does not reach any known raise site (§A.3); it neither confirms nor tests totality." |
| f1 §1.9.3, row "raise → value" | "4 witnesses of 45 date probes" | Understated. **8 mechanisms across 9 source lines and 4 exception types** (§A.2); the date class is 1 of them. **[punch]** Counted off §A.5(i) exactly: **10 tabulated direction rows** carrying **11 witnesses** (the `floor`/`ceil` row holds two) — **4 rows raise→value** (R1×2, R2, R8), 3 raise→null (R4 @ DBL_MAX, R6, R7), 3 both-raise (R3, R4 @ 1.7e296, R5); as witnesses that is 4 / 4 / 3. The §5-breaching number is **4** under either reading. *(This replaces the drafted sub-clause "Of 11 re-verified witnesses, 4 are raise→value, 3 raise→null, 3 both-raise", whose 4 + 3 + 3 summed to 10, not 11; `f1` correctly declined to copy it — `f6` closure log, "Reported, not fixed".)* |
| `recon/semantics.md` §11 | "**`expr.py` never raises for data reasons** … every function surveyed above independently confirms it" | False as a universal. True in the narrow form of §A.4. The survey covered the *guarded* paths and missed `:430`, `:521`, `:525`, `:526`, `:527`, `:545`, `:546`, `:624`, `:375`. |
| FRAMING §5 | "`expr` is *total* — it never throws, it returns `null`. SQL is not." | Both halves need qualifying. `expr` throws on N1–N4. Postgres, on the same inputs, more often returns a **value or NULL** than raises (**7 of the 10 rows in §A.5(i)** = 8 of its 11 witnesses; Postgres raises on 3 of 10 rows) **[punch]**. The asymmetry §5 assumes is real for `CAST('abc' AS REAL)` and division by zero; it inverts at the numeric and calendar boundaries. |

**Status of these four corrections — two applied, two recorded. [punch]** The two ordered onto
sections of this document have been **applied in place**, and this seat read both as they now stand
to confirm it: **f2 §2.4** has deleted the "403 independent confirmations of the totality premise"
inference, retained the bare `0 PYTHON_RAISED` count, and added a forward footnote to this section
carrying the domain evidence and stating that the zero "neither confirms nor tests totality";
**f1 §1.9.3**'s *raise → value* row now reads "**8 mechanisms across 9 source lines and 4 exception
types**" in place of "4 witnesses of 45 date probes", with the eight cross-referenced to §A.2 R1–R8.
A reader meeting either section earlier in the document meets the corrected text, not the text
quoted in the middle column above — that column is the record of what was ordered, not of what f1
and f2 now say. The remaining two rows target `recon/semantics.md` §11 and `FRAMING.md` §5, both of
which are **read-only to this pass**; they are therefore **recorded, not applied**, and a decision at
the `sp_decide` gate should treat those two documents as still carrying the wording this table
disputes.

---

**Compliance. [consistency]** Read-only throughout. Both GIMS trees (`GIMS-Project@995cc59`,
`gims-ledger@7b7a049`), `spikes/T-1/recon/`, `proto/`, `analysis/`, `FRAMING.md`, `.autodev/` and
`kb/` were read and not written; the only file this seat wrote is `spikes/T-1/.parts/xa-totality.md`.
**Nothing was fixed.** The eight raise sites (`expr.py:375/430/521/525/526/527/545/546/624`) and the
two unguarded `evaluate()` call sites (`sources.py:147`, `:162`) are **recorded, not repaired**, per
the `sp-investigate` stop rules and FRAMING §3; `proto/compile.py` and `proto/runtime.sql` were not
touched. Every A.2 witness was re-run through the public `expr.evaluate(parse(src), record, ctx)` in
`GIMS-Project/.venv`, importing `core.dashboard.expr` read-only. **The A.5(ii) poison-row probes ran
entirely in memory**: `sources.py`'s `_apply_derive` and `_filter_rows` were called directly on a
10-element Python list constructed by this seat — no HTTP server was started, no database was
opened, no GIMS file was read or written by them, and they left nothing behind. The A.3 re-derivation
of `G2b_round_raises` (seed 13) ran Python-side only, no DB. The eleven direction witnesses in A.5(i)
went through the existing instrument `analysis/fuzz/differ.py` (`run_case`) against the spike's own
scratch database `autosql_spike`, `SELECT` only; **no Postgres object was created, altered or
dropped**, and `glp_strong` was not touched. **What is not fully attestable:** importing `differ.py`
leaves a CPython bytecode cache — `analysis/fuzz/__pycache__/differ.cpython-312.pyc` exists with
mtime `14:19:06`, inside this section's working window, though three other seats also imported
`differ.py` and it cannot be attributed to one of them; no source byte changed. And the HTTP-500
surfacing in A.5(ii) is read off `core/errors.py`, not measured against a running app (labelled
INFERENCE in place).

**Punch pass addendum. [punch]** The `[punch]`-marked edits above were made in a later pass whose
only writes were to this file. To re-verify §A.2's enumeration without leaving a bytecode cache in
either GIMS tree, `core/dashboard/expr.py` was **copied** to the session scratchpad (`md5`
`5bd9db65de20678d4e070c8ad823c3ce`, re-confirmed identical in `GIMS-Project` and `gims-ledger` at
copy time) and every §A.2 witness was re-run there — ten raise cases covering all eight mechanisms,
R6 and R4 contributing two each — through `expr.evaluate(expr.parse(src), rec, {})` under the
system Python **3.12.3**, the same interpreter version as the `.venv` used above. All eight
mechanisms reproduced, each with its traceback's last frame
at the line §A.2 cites — `430 · 521 · 525 · 526 · 527 · 545 · 546 · 624 · 375` — across four
exception types. No database was contacted in this pass, no GIMS file was opened for writing, and
`proto/`, `analysis/`, `recon/` and the other parts were read only.
