# T-1 · FINDINGS — compiling the GIMS dashboard expression AST to Postgres SQL

**Stage:** `sp-investigate` (spike@v2) · **ticket:** T-1 · **branch:** `spike/T-1-expr-sql`
**Decision authority:** `recommend-and-wait` — this document *recommends*; `human:owner` decides at
the `sp_decide` gate.
**Bar:** set in advance by [`FRAMING.md`](FRAMING.md) §4/§5, before any evidence was collected, so
the result could not be rationalised afterwards.

---

## The question

> Can the AST produced by `core/dashboard/expr.py` be compiled to Postgres SQL that agrees with the
> Python evaluator on **every** case in `tests/fixtures/expr_vectors.json` (within `float_epsilon`
> = 1e-9), well enough that `api/dashboard/sources.py` can push `derive` / `where` / `sort` /
> `limit` into the database instead of materialising up to `MAX_SCAN = 20_000` rows and filtering
> them in Python?

## Provenance — verified live on this machine, 2026-08-19

| | |
| --- | --- |
| Expression oracle | `GIMS-Project` @ `995cc59` (branch `refactor/foundation`) — `core/dashboard/expr.py`, `tests/fixtures/expr_vectors.json` |
| Storage reference | `GUTS/spine/L1-memory/gims-ledger` @ `7b7a049` — `migrations/pg/`, `list_records_where`, the RAG pushdown profile |
| Both trees | **read-only for this spike** (`FRAMING.md` §7). **No file in either tree was opened for writing by any seat of this spike**, and both HEADs are still the `FRAMING.md` §7 values. **[consistency]** The drafted form of this row — *"Nothing was written to either"* — claimed more than a read-only seat can observe: `xd` D.11 records a **concurrent non-spike writer** (AutoDev's own ingestion verb) creating `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` **inside** the spike window, and moving `LedgerRecord` 17,145 → 17,148 during the sweep. Re-verified here: `git status --porcelain` shows 8 dirty entries in `GIMS-Project` and 9 in `gims-ledger`, HEADs `995cc59` / `7b7a049`. |
| Expression stack | **byte-identical across both trees** (`FRAMING.md` §2/C2) — one fixture, one meaning, no "which evaluator is canonical?" risk |
| Postgres | docker `glp-strong-db`, `pgvector/pgvector:pg16`, **PostgreSQL 16.14** (Debian 16.14-1.pgdg12+1), host port 55433 |
| Database | **`autosql_spike`** — the spike's own scratch db. `glp_strong`'s contents were not touched. |
| Python | `GIMS-Project/.venv`, CPython **3.12.3** — the reference runtime, imported directly |
| Fingerprints | fixture `sha256 0091df64…` · `expr.py` `90cbb56d…` · `compile.py` `b71b1538…` · `runtime.sql` `32628b45…` |

## How to read this document

Five findings, in the order `FRAMING.md` §4 requires them, **plus four cross-cutting sections** that
exist because the findings were written in parallel and some questions only became visible when they
were read together. Each finding is a **synthesis** — the full working lives in the artifact it
cites, and every number here is traceable to a file:

| § | Section | Full working |
| --- | --- | --- |
| §1 | Finding 1 · Conformance | [`proto/CONFORMANCE.md`](proto/CONFORMANCE.md), [`proto/results.json`](proto/results.json), [`analysis/fuzz/`](analysis/fuzz/) |
| §2 | Finding 2 · Coverage + fallback | [`analysis/coverage.md`](analysis/coverage.md), [`proto/coverage_probe_results.json`](proto/coverage_probe_results.json), [`recon/query-source.md`](recon/query-source.md) |
| §3 | Finding 3 · Index shape | [`analysis/index-shape.md`](analysis/index-shape.md), [`proto/idxshape_plans.json`](proto/idxshape_plans.json), [`recon/storage.md`](recon/storage.md) |
| §4 | Finding 4 · Measurement | [`analysis/measurement.md`](analysis/measurement.md), [`analysis/measurements.json`](analysis/measurements.json), [`recon/baseline.md`](recon/baseline.md) |
| §A | Cross-cutting · is `expr` total? | the premise `FRAMING.md` §5 rests on — and it is **false as a universal** |
| §B | Cross-cutting · `filters` / `sort` / `limit` | the half of the question with no conformance evidence |
| §C | Cross-cutting · the divergence → fallback register | every class, its direction, and whether anything can detect it |
| §D | Cross-cutting · reachability in real data | whether the breaches occur in the corpora actually on this machine |
| §5 | Finding 5 · Recommendation | this document |

**Read §A–§D before §5.** They are not appendices: three of the four changed the recommendation, and
§A revises what the non-negotiable in `FRAMING.md` §5 actually means.

Semantics reference for all of it: [`recon/semantics.md`](recon/semantics.md) (operational semantics
of `expr.py`) and [`recon/fixture.md`](recon/fixture.md) (complete 130-case inventory) — **with one
correction**: `recon/semantics.md` §11's totality claim ("`expr.py` never raises for data reasons")
is false as a universal, and §A gives the narrower form that is true.

**Conventions, kept from the source documents.** Numbers, not adjectives. Every claim carries a
citation. Anything that is an inference or a judgement rather than a measurement is labelled
**OPINION** or **INFERENCE** in place. A thing the evidence does not establish is written as
*not established*, with what would establish it — never rounded up to a conclusion.

**This document has been adversarially audited, and the audit is part of the record.** Each finding
was drafted, then re-derived from the raw machine data by a separate seat that did not trust the
prose (43 corrections, 2 load-bearing); a completeness critic checked the body against `FRAMING.md`
§4/§5/§8 (16 gaps, since closed or recorded as *not established*); three seats independently
adjudicated the go/no-go bar and **did not agree**; and a consistency read — not the last one,
see below **[punch]** — checked the assembled document against itself and found **24 defects in the
drafted prose**. Those records are kept beside this file in [`.parts/`](.parts/) —
`verifications.json`, `critic.md`, `panel.json`, `consistency.md`. **[consistency]** Those 24 items
were then worked by nine seats, one per section, each required to re-verify the repair against the
raw artifact before writing it — repairs were **refused** where the artifact disagreed with the consistency read, and the seats found further
defects it had missed.

**[punch] Then a third pass, over the repaired document.** Three adversarial lenses read the
assembled file independently. All three reported the same bottom line — the evidence is sound and
`f5`'s **NO-GO** still follows — and returned **21 items, every one classed *credibility* or *minor*
and none decision-blocking**. A punch-list round worked those items under the same verify-first
rule. It corrected citations and denominators, restated figures that mixed an id count with a class
count, withdrew claims the artifacts did not support — including two in the closure log's own
account of itself and the refusal count in this paragraph — and added the round's one new number:
`f5` §5.7's CONDITIONAL-GO subset covers **68 of 130 fixture cases (52.3%)**, where the figure had
stood as *not established*. **The lens reads are not retained as files**, unlike the four audit
records named above; the closure log is their only account.

**[punch] Refusals, counted the same way here as in the log: 5 refusals across 4 seats in the repair
pass — 3 of them refusing a prescribed repair outright, 2 applying the repair and refusing a
supporting claim** (a characterisation in one, an evidentiary premise in the other); **1 recorded in
the punch-list round**, whose refusal record the log itself flags as incomplete. The drafted form of
this paragraph said **three were refused**, which is the count of prescribed repairs refused
outright, not the number of refusals; the log's prose said four, which is the number of seats.
**Every repair, refusal and residual is logged, with its raw artifact, in the final section of this
document, [Closure log — what the audit passes changed](#closure-log--what-the-audit-passes-changed).**
Read it if you want to know what the audits changed rather than that they happened.

## Contents

| § | Section |
| --- | --- |
| §1 | [Finding 1 — Conformance](#finding-1--conformance) |
| §2 | [Finding 2 — Coverage and fallback](#finding-2--coverage-and-fallback) |
| §3 | [Finding 3 — Index shape](#finding-3--index-shape) |
| §4 | [Finding 4 — Measurement](#finding-4--measurement) |
| §A | [Cross-cutting A — is `expr` total? The premise FRAMING §5 rests on](#cross-cutting-a--is-expr-total-the-premise-framing-5-rests-on) |
| §B | [Cross-cutting B — `filters`, `sort` and `limit`: the half of the question with no evidence](#cross-cutting-b--filters-sort-and-limit-the-half-of-the-question-with-no-evidence) |
| §C | [Cross-cutting C — the complete divergence → fallback register, and what the machinery costs](#cross-cutting-c--the-complete-divergence--fallback-register-and-what-the-machinery-costs) |
| §D | [Cross-cutting D — is any of this reachable from real GIMS data?](#cross-cutting-d--is-any-of-this-reachable-from-real-gims-data) |
| §5 | [Finding 5 — Recommendation](#finding-5--recommendation) |
| — | [Closure log — what the audit passes changed](#closure-log--what-the-audit-passes-changed) **[punch]** |

## The bar, restated from `FRAMING.md` §4 — quoted, not paraphrased

> - **GO** requires: 100% of compiled cases agree within `float_epsilon`; every non-compiling
>   construct has a named fallback; and the fallback is **detectable and reported at query time**,
>   never silent.
> - **NO-GO** if any case diverges *silently* — i.e. produces a number rather than an error or an
>   explicit fallback. One silently-wrong number is disqualifying on its own.
> - **CONDITIONAL-GO** is a legitimate verdict: compile the subset that provably agrees, fall back
>   loudly for the rest, and name the subset.

And the non-negotiable, `FRAMING.md` §5:

> A fallback to in-memory evaluation must be **reported, never silent.**

## What the stop rules mean for what follows

`FRAMING.md` §3 bounded this investigation to one pass and forbade chasing what it found: a case
that cannot compile is *recorded as a coverage gap*, not designed around; a divergence whose cause
is identified is *recorded with its cause and fallback rule*, not fixed; the `query` source is
*bounded and confirmed* as non-pushdown, not made to work. **Several real defects appear below
un-fixed. That is the contract, not an oversight** — each is reported with its cause, its blast
radius, and its direction against `FRAMING.md` §5.

The prototype in `proto/` is **throwaway by contract** (`sp-investigate@v1`). It is not a library,
has no API, and nothing may import it later.

---

## Finding 1 — Conformance

*Revised at closure. Every correction from `.parts/verifications.json` was re-checked against the
raw source it names before being written in; where the verifier was wrong that is said in place
(§1.5, §1.9.4). Closure work is marked **[closure]**. A later adversarial consistency read
(`.parts/consistency.md`) forced three further corrections and one attestation; those are marked
**[consistency]** so the two passes stay distinguishable.*

### 1.1 What was run, and that it is the thing it claims to be

A third runtime — `proto/compile.py` (AST→SQL) plus `proto/runtime.sql` (the `xpr` plpgsql
runtime) — was executed against `tests/fixtures/expr_vectors.json`, the same fixture the Python
and JS runtimes already satisfy, under the comparison rule copied unchanged from the existing
consumer test `GIMS-Project/tests/test_dashboard_expr.py:20-25` (`rel_tol=0, abs_tol=1e-9`;
bools never equal to 0/1). Environment: PostgreSQL 16.14, db `autosql_spike`, CPython 3.12.3,
`extra_float_digits` pinned to `1` (`results.json` `meta`) — a **condition on the result**, not a
detail; see §1.2.

**"The same fixture the Python and JS runtimes already satisfy" is half measured, half assumed
[closure, gap 16d].** The *Python* leg is measured twice: `results.json`
`control_python_vs_fixture_expect` = `{"checked": 130, "failures": []}`, and the verification
pass independently re-ran `expr.evaluate` over all 130 and reproduced every recorded
`python_value`/`python_type` with 0 mismatches (`verifications.json` → Finding 1 → `notes`).
The *JS* leg was **never executed**. `frontend/lib/expr.js` is not run by any artifact in this
spike and no captured output in either GIMS tree records it being run against the fixture; the
claim rests on the fixture's own docstring ("the JS evaluator … MUST produce `expect`"). Partial
mitigation, and it is real but partial: FRAMING §2/C2 verified `frontend/lib/expr.js` **byte-identical**
across `GIMS-Project` and `gims-ledger`, so there is exactly one JS oracle rather than two that
might disagree — byte-identity of the file, not evidence that the file passes. FRAMING §6 also
puts the UI out of scope. **Label: the JS leg of FRAMING §4 #1 is an assumption. It would be
established by running the JS vector suite once and recording its pass count.**

Provenance re-verified by this seat, not taken from the prose: `sha256sum` of `proto/compile.py`
(`b71b1538…`), `proto/runtime.sql` (`32628b45…`), `GIMS-Project/core/dashboard/expr.py`
(`90cbb56d…`) and `tests/fixtures/expr_vectors.json` (`0091df64…`) all match `results.json`
`meta` exactly. `compile.py` (mtime 11:23:10) and `runtime.sql` (11:20:29) predate the
conformance run (`results.json`, 11:45:53). **The mtime argument alone does not carry the
"same compiler bytes" conclusion** — mtime records the last write, not the absence of writes, and
what the fuzz batteries actually executed is the `xpr` schema *installed in the database*, whose
load time no artifact records. Two re-derivations do carry it: (a) re-parsing and re-compiling all
130 fixture expressions with the current `proto/compile.py` reproduces `results.json`
`cases[i].sql` byte-identically for all 130; (b) the live `xpr.f8` body in `autosql_spike` still
carries the 297-digit guard literal that `runtime.sql:33` defines (both in
`verifications.json` `unverifiable[1]`; (b) is visible in raw form in the `Index Cond:` of
`fuzz/F_ecma_num.txt` §F3, which prints the 297-digit constant). The three evidence sets are
comparable **on compiler bytes**.

**Reproducibility boundary of the evidence set [closure, gap 16c] — stated honestly, because
§1.9 leans on it.**

| | count | note |
| --- | ---: | --- |
| battery scripts in `analysis/fuzz/` | **19** | 20 `.py` files minus `differ.py`, which is the shared driver, not a battery |
| captured outputs (`.txt`) | **25** | — |
| runs issued by `fuzz/run_all.sh` | **21** | `H_ast_fuzz.py` is invoked three times (ordinary / extreme / unicode) |

My earlier "twenty batteries" was wrong on both readings. More important: **`run_all.sh` does not
regenerate the whole evidence set — it regenerates 21 of the 25, and the four it does not are
named here in full.** **[consistency]** `A_range.txt`, `A2_boundary.txt`, `B2_overflow.txt` and
`H_parse_errors.txt` have no producing `.py` in the directory and are not among its 21 runs — they
are captures of superseded probe scripts. (The other three `.py`-less captures, `H_ordinary.txt` /
`H_extreme.txt` / `H_unicode.txt`, **are** regenerable: `H_ast_fuzz.py` produces them under three
profiles, which is why 19 batteries issue 21 runs. 25 − 21 = 4, and the four are the four above —
verified by listing `analysis/fuzz/` and matching every `.txt` against `run_all.sh`'s 21 `run`
lines.) `A_f8_guard.txt` §A2/§A3 supersedes both `A_range.txt` and `A2_boundary.txt` with
the same numbers and **is** regenerable, so every D1–D5 claim below is now cited to `A_f8_guard.txt`;
`B2_overflow.txt` (§1.9.7) has no regenerable equivalent. `H_parse_errors.txt` is a superseded
`N=3000` capture whose header and histogram come from different runs (§1.10).
One further boundary: the traceback in `D_rawjson.txt:47-56` names `differ.py:148 elif matches(...)`,
whereas the current `differ.py` wraps `matches()` in `except (OverflowError, ValueError, TypeError)`
at lines 156-161. **`differ.py` was edited after that crash (mtime 11:58), so captures taken before
11:58 — `A_range`, `A2_boundary`, `B2_overflow`, `C_numgate`, and the first block of `D_rawjson` —
ran against a different comparator than everything after.** The edit only added the
`compare_error → agree=False` path; it touches neither `compile.py` nor `runtime.sql`, which is what
the provenance argument above is actually about.

### 1.2 The four outcomes — totals, with the denominator stated

Denominator is **every fixture case (130)**, not every compiled case.

| outcome | meaning | count | of |
| --- | --- | ---: | ---: |
| `COMPILED_AGREES` | compiled, executed, matched under the mirrored rule | **130** | 130 |
| `COMPILED_DIVERGES` | compiled and executed, but did not match (or leaked a top-level jsonb `null`) | **0** | 130 |
| `DID_NOT_COMPILE` | `compile.py` raised `Uncompilable`; no SQL ran. A gap, never a pass | **0** | 130 |
| `SQL_ERROR` | Postgres raised. A totality violation; never a pass | **0** | 130 |

**Pass rate = 130/130 = 100.0% of all fixture cases**, *at `extra_float_digits = 1`.* Agreement
among cases that compiled and executed is also 130/130, because every case compiled
(`proto/CONFORMANCE.md` §Totals).

**The condition on the headline, stated because it is not a formatting detail [closure, gap 9].**
`results.json` `meta.extra_float_digits = "1"`, set by `conformance.py:341`; the fixture was never
run at any other value. `fuzz/M_encoding_guc.txt` §M1 — cited by no section before this pass —
measures `to_jsonb(float8)` **itself** at three GUC settings and gets three different jsonb values
for one double:

| `extra_float_digits` | `to_jsonb(1.0/3.0)` renders as |
| ---: | --- |
| `1` (the pinned value, PG12+ default) | `0.3333333333333333` |
| `0` | `0.333333333333333` |
| `-3` | `0.333333333333` |

with the file's own note: *"if these rows differ, the compiled expression's RETURNED VALUE is
GUC-dependent, not merely its `string()` rendering."* They differ. `to_jsonb(<float8>)` is the
return path for **every** numeric result the compiler produces (`compile.py:210, 244, 281-293, 359,
382-392, …`), and `xpr.str` routes text through `xpr.ecma_num(xpr.f8(j))` (`runtime.sql:133-139`).
So the GUC is on the **value** channel, not only the text channel — which is where D16/D17 come
from and which makes "pin the GUC per session" a correctness requirement.
**How much of the 130 is exposed, counted [closure]:** 54 cases return a numeric value and 14 more
have `xpr.str` in their compiled SQL, disjointly — **68 of the 130 carry a value that reaches
Python through a float8→jsonb or float8→text conversion and would have to be re-checked at any
other GUC value.** The remaining 62 (booleans, nulls, strings that never pass through a number)
would not. **Whether those 68 still agree at `efd = 0` or `-3` is NOT ESTABLISHED.** It was not
run because `conformance.py:341` hard-codes `SET extra_float_digits = 1` and re-running at another
value would require editing an instrument this pass may not edit (FRAMING §3, and the stop rules
for this seat). One concrete step would establish it: parameterise that one line and re-run the
130 twice. INFERENCE on the likely shape of the answer, labelled as such: the 1e-9 epsilon absorbs
the `efd=0`/`efd=-3` difference for small magnitudes (3.3e-13 for 1/3) but not for large ones, so
the numeric cases are unlikely to be uniformly affected — that is a guess and is not a result.

Independent control on the oracle: the Python evaluator was also run against the fixture's
**hand-authored** `expect` values (the fixture note forbids regenerating them from an
evaluator). 130/130 agree, 0 failures — `results.json` `control_python_vs_fixture_expect`
= `{"checked": 130, "failures": []}`. The oracle is not a tautology.

### 1.3 Raw data vs. the prose report — totals check

Every headline number in `proto/CONFORMANCE.md` was recomputed by this seat directly from
`proto/results.json` `cases[]` rather than read off the prose, and independently again by the
verification pass (`verifications.json` → Finding 1 → `notes`), which reports every one confirmed.

| claim in CONFORMANCE.md | recomputed from `results.json` `cases[]` | verdict |
| --- | --- | --- |
| 130 cases, 16 groups | `len(cases)==130`, 130 unique names, 11/9/4/17/13/13/4/11/10/11/11/3/4/3/4/2 = 130 | matches |
| `COMPILED_AGREES` 130, other outcomes 0 | `Counter(outcome) == {COMPILED_AGREES: 130}`; `cause` non-null: 0; `harness_errors: []` | matches |
| no mirrored-passes-but-strict-fails case; no top-level jsonb `null` leak | `mirrored_rule_agrees` False: 0; `strict_deep_equal` False: 0; `sql_jsonb_typeof=='null'`: 0 | matches |
| 54 numeric / 22 string / 19 both-null | 54 / 22 / 19 (+35 boolean = 130) | matches |
| max abs delta 0.0; 0 cases needed the epsilon | max delta 0.0; 0 cases with non-zero delta | matches |
| 6 clock cases, 0 on the real clock | 6 clock cases, 0 without injected `context.now` | matches |
| degenerate baselines 20/19/15/1/0 | recomputed under the same mirrored rule: 20/19/15/1/0 | matches |

**The raw data agrees with the prose report on every total in the 130-case run.** The three places
where prose and raw record part company are all outside the totals and are stated in §1.10.

### 1.4 Per-case results — all 130 cases, one row each

FRAMING §4 finding #1: *"Pass/fail per case, all cases, never a summary count."* Every fixture
case is below. `PASS` = `COMPILED_AGREES`; a `FAIL` (`COMPILED_DIVERGES`), `GAP`
(`DID_NOT_COMPILE`) or `RAISE` (`SQL_ERROR`) would appear literally in the outcome column and
none does. Order and `#` are the fixture's own order (`results.json` `cases[i]`). The `cause`
column of `results.json` is null for all 130, so no case carries a named divergence cause. The
table was diffed cell-by-cell against `cases[]` by the verification pass: 130 cells, no missing
index, no mismatch.

| # | group | case | outcome | # | group | case | outcome |
| ---: | --- | --- | --- | ---: | --- | --- | --- |
| 1 | `arithmetic` | `add` | PASS | 66 | `dates` | `date_add_year_rollover` | PASS |
| 2 | `arithmetic` | `precedence_mul_before_add` | PASS | 67 | `dates` | `date_add_bad_input_null` | PASS |
| 3 | `arithmetic` | `parens_override` | PASS | 68 | `coalesce` | `second_non_null` | PASS |
| 4 | `arithmetic` | `true_division` | PASS | 69 | `coalesce` | `all_missing_default` | PASS |
| 5 | `arithmetic` | `modulo_pos` | PASS | 70 | `coalesce` | `all_null_returns_null` | PASS |
| 6 | `arithmetic` | `modulo_neg_dividend_truncates` | PASS | 71 | `coalesce` | `skip_literal_null` | PASS |
| 7 | `arithmetic` | `modulo_neg_divisor_truncates` | PASS | 72 | `strings` | `lower` | PASS |
| 8 | `arithmetic` | `unary_minus` | PASS | 73 | `strings` | `upper` | PASS |
| 9 | `arithmetic` | `mul_unary` | PASS | 74 | `strings` | `lower_missing_null` | PASS |
| 10 | `arithmetic` | `divide_by_zero_is_null` | PASS | 75 | `strings` | `contains_substring_true` | PASS |
| 11 | `arithmetic` | `modulo_by_zero_is_null` | PASS | 76 | `strings` | `contains_substring_false` | PASS |
| 12 | `fields` | `simple` | PASS | 77 | `strings` | `contains_list_member_true` | PASS |
| 13 | `fields` | `nested` | PASS | 78 | `strings` | `contains_list_member_false` | PASS |
| 14 | `fields` | `missing_top` | PASS | 79 | `strings` | `contains_missing_haystack_false` | PASS |
| 15 | `fields` | `descend_into_nondict_is_null` | PASS | 80 | `strings` | `concat_literals` | PASS |
| 16 | `fields` | `bracket_quoted_key_with_space` | PASS | 81 | `strings` | `concat_fields` | PASS |
| 17 | `fields` | `bracket_index` | PASS | 82 | `strings` | `concat_with_string_of_number` | PASS |
| 18 | `fields` | `bracket_negative_index` | PASS | 83 | `coercion` | `number_of_string` | PASS |
| 19 | `fields` | `bracket_index_out_of_range_is_null` | PASS | 84 | `coercion` | `number_of_nonnumeric_null` | PASS |
| 20 | `fields` | `deep_nested_key` | PASS | 85 | `coercion` | `number_of_bool` | PASS |
| 21 | `null_propagation` | `add_missing_field` | PASS | 86 | `coercion` | `string_of_int` | PASS |
| 22 | `null_propagation` | `add_present_fields` | PASS | 87 | `coercion` | `string_of_float` | PASS |
| 23 | `null_propagation` | `mul_nonnumeric_string` | PASS | 88 | `coercion` | `string_of_bool` | PASS |
| 24 | `null_propagation` | `add_numeric_string_coerces` | PASS | 89 | `coercion` | `string_of_null` | PASS |
| 25 | `comparison` | `lt_true` | PASS | 90 | `coercion` | `length_string` | PASS |
| 26 | `comparison` | `lt_false` | PASS | 91 | `coercion` | `length_list` | PASS |
| 27 | `comparison` | `lt_missing_is_null` | PASS | 92 | `coercion` | `length_number_null` | PASS |
| 28 | `comparison` | `eq_string_true` | PASS | 93 | `numeric_funcs` | `abs_literal` | PASS |
| 29 | `comparison` | `eq_string_false` | PASS | 94 | `numeric_funcs` | `abs_field` | PASS |
| 30 | `comparison` | `neq_string_true` | PASS | 95 | `numeric_funcs` | `floor_pos` | PASS |
| 31 | `comparison` | `eq_num_true` | PASS | 96 | `numeric_funcs` | `ceil_pos` | PASS |
| 32 | `comparison` | `eq_num_false` | PASS | 97 | `numeric_funcs` | `floor_neg` | PASS |
| 33 | `comparison` | `null_eq_null` | PASS | 98 | `numeric_funcs` | `ceil_neg` | PASS |
| 34 | `comparison` | `missing_eq_null_true` | PASS | 99 | `numeric_funcs` | `round_half_up` | PASS |
| 35 | `comparison` | `zero_eq_null_false` | PASS | 100 | `numeric_funcs` | `round_half_away_from_zero_neg` | PASS |
| 36 | `comparison` | `bool_eq_bool` | PASS | 101 | `numeric_funcs` | `round_down` | PASS |
| 37 | `comparison` | `bool_ne_num` | PASS | 102 | `numeric_funcs` | `round_ndigits` | PASS |
| 38 | `comparison` | `string_ne_num` | PASS | 103 | `numeric_funcs` | `round_ndigits_one` | PASS |
| 39 | `comparison` | `string_lex_lt` | PASS | 104 | `aggregates` | `count_list` | PASS |
| 40 | `comparison` | `gte_equal` | PASS | 105 | `aggregates` | `count_skips_null` | PASS |
| 41 | `comparison` | `order_mixed_types_is_null` | PASS | 106 | `aggregates` | `sum_list` | PASS |
| 42 | `boolean` | `and_ff` | PASS | 107 | `aggregates` | `sum_skips_nonnumeric` | PASS |
| 43 | `boolean` | `or_tf` | PASS | 108 | `aggregates` | `avg_list` | PASS |
| 44 | `boolean` | `not_true` | PASS | 109 | `aggregates` | `min_list` | PASS |
| 45 | `boolean` | `not_missing_is_true` | PASS | 110 | `aggregates` | `max_list` | PASS |
| 46 | `boolean` | `and_with_falsy_zero` | PASS | 111 | `aggregates` | `max_varargs` | PASS |
| 47 | `boolean` | `or_with_truthy` | PASS | 112 | `aggregates` | `sum_varargs` | PASS |
| 48 | `boolean` | `not_of_comparison` | PASS | 113 | `aggregates` | `avg_empty_null` | PASS |
| 49 | `boolean` | `range_check` | PASS | 114 | `aggregates` | `sum_missing_null` | PASS |
| 50 | `boolean` | `empty_string_falsy` | PASS | 115 | `conditional` | `if_true_branch` | PASS |
| 51 | `boolean` | `nonempty_string_truthy` | PASS | 116 | `conditional` | `if_false_branch` | PASS |
| 52 | `boolean` | `zero_falsy` | PASS | 117 | `conditional` | `if_missing_is_false` | PASS |
| 53 | `boolean` | `empty_list_falsy` | PASS | 118 | `composite` | `near_due_predicate` | PASS |
| 54 | `boolean` | `nonempty_list_truthy` | PASS | 119 | `composite` | `result_in_set` | PASS |
| 55 | `dates` | `today_from_now` | PASS | 120 | `composite` | `overdue_label` | PASS |
| 56 | `dates` | `now_from_now` | PASS | 121 | `composite` | `days_left_derived` | PASS |
| 57 | `dates` | `days_between_today_future` | PASS | 122 | `modulo_fmod` | `mod_float_fmod` | PASS |
| 58 | `dates` | `days_between_reverse_negative` | PASS | 123 | `modulo_fmod` | `mod_float_ieee` | PASS |
| 59 | `dates` | `days_between_two_days` | PASS | 124 | `modulo_fmod` | `mod_large_over_small_positive` | PASS |
| 60 | `dates` | `days_between_fractional` | PASS | 125 | `string_ecma` | `string_small_decimal_not_exp` | PASS |
| 61 | `dates` | `days_between_offset_aware` | PASS | 126 | `string_ecma` | `string_tiny_exp` | PASS |
| 62 | `dates` | `days_between_bad_input_null` | PASS | 127 | `string_ecma` | `string_large_int_float` | PASS |
| 63 | `dates` | `date_add_days` | PASS | 128 | `string_ecma` | `string_neg_small` | PASS |
| 64 | `dates` | `date_add_negative` | PASS | 129 | `date_total` | `date_add_out_of_range_null` | PASS |
| 65 | `dates` | `date_add_datetime_preserves_time` | PASS | 130 | `date_total` | `date_add_year_padded` | PASS |

**Totals from this table: 130 PASS, 0 FAIL, 0 GAP, 0 RAISE — the per-case rows and
`results.json` `totals` are the same 130 facts counted twice.**

### 1.5 How strong is the agreement (a pass count alone says nothing)

All figures recomputed by this seat from `results.json` `cases[]`; they match
`results.json` `agreement_strength`.

| measure | value | denominator |
| --- | ---: | --- |
| numeric cases compared | 54 | 130 |
| **max \|SQL − Python\| over all numeric cases** | **0.0** | 54 |
| cases whose delta was non-zero, i.e. that needed the 1e-9 epsilon at all | **0** | 54 |
| string cases | 22 | 130 |
| string cases exact, character-for-character | **22** | 22 |
| agreements of the weak "both sides are null" form | **19** | 130 |
| boolean cases (20 `True`, 15 `False`) | 35 | 130 |
| cases calling `today()`/`now()` | 6 | 130 |
| of those, running on the **real** clock | **0** — all 6 inject `context.now` | 6 |

The numeric agreement is bit-exact, not epsilon-assisted: **inside the fixture** the tolerance the
fixture defines was never consumed.

**What that sentence does not cover, and it is the most decision-relevant thing this section was
missing [closure, `verifications.json` notes #1].** `fuzz/L_misc.txt` §L1 shows that where the
epsilon *does* apply it **hides a divergence the user sees**. `sum($.l)` over `[0.1]×10` gives
Python `1.0` and SQL `0.9999999999999999`: a numeric **AGREE** (inside 1e-9) — while `string()` of
that same value gives `'1'` vs `'0.9999999999999999'` and `concat()` gives `'total=1'` vs
`'total=0.9999999999999999'`, both **DIVERGE**. `string()`/`concat()` are exact and the epsilon does
not reach them. So "agrees within `float_epsilon`" and "shows the same thing on a dashboard" are
not the same property, and the fixture's own tolerance is what separates them. This is a general
qualification on every numeric agreement claimed anywhere in this finding, not a one-off witness.

**Reproducibility: the claim every other number leans on is now MEASURED, not asserted
[closure, gap 16e — CLOSED].** `CONFORMANCE.md` §How strong states "Two consecutive runs produce
byte-identical `cases` in `results.json`", and `conformance.py:681` shows that sentence is a
hard-coded string in the report writer, not a computed check. It was checked here by a read-only
re-run of the existing instrument: `conformance.run()` is `SELECT`-only (`conformance.py:331-460`,
`out_of_fixture_probes:298-323` — no DDL, no INSERT) and returns a dict, so it was called **twice
in-process** and the `cases` arrays canonicalised and hashed. `main()` — which would rewrite
`proto/results.json` and `proto/CONFORMANCE.md` — was never called and `proto/` is byte-unchanged
(`results.json` mtime still 11:45:53).

| | sha256 of canonicalised `cases` |
| --- | --- |
| run 1 (this pass) | `9fc3664475e91330670886d758163b804977e59cb589abc7e3edf00b87762291` |
| run 2 (this pass) | `9fc3664475e91330670886d758163b804977e59cb589abc7e3edf00b87762291` |
| the committed `proto/results.json` (11:45:53, ~2 h earlier) | `9fc3664475e91330670886d758163b804977e59cb589abc7e3edf00b87762291` |

**Byte-identical, three ways.** Totals identical (`130/130`), `meta.extra_float_digits = 1` in both.
The prose sentence was true; it is now backed. This also means the 130-case run is stable across a
two-hour gap and a different process, not merely within one invocation. A second, independent
determinism datum from a different instrument [closure]: re-running `H_ast_fuzz.py extreme 4000 99`
reproduced its captured counts exactly (AGREE 3833 / DIVERGE 44 / SQL_RAISE 3 / PARSE_ERROR 120 and
the 30/14/3 cluster split) — see §1.9.6.

`KNOWN_DIVERGENCES/wall_clock_granularity` is untested **by this run** — all 6 clock cases inject
`context.now` (`compile.py:134-145`, `in_fixture: False`). It is *not* untested altogether; the
verifier is right and my §1.9.4 was wrong. See §1.9.4.

### 1.6 Degenerate baselines — what the fixture cannot distinguish

A compiler that ignores its input and emits one constant, scored under the identical rule
(`conformance.py:500-506`; recomputed independently by this seat, identical results):

| do-nothing compiler | scores | of | what it is really matching |
| --- | ---: | ---: | --- |
| `always 'true'::jsonb` | 20 | 130 | the 20 cases whose answer is `True` |
| `always NULL::jsonb` | 19 | 130 | **exactly the 19 both-null agreements** |
| `always 'false'::jsonb` | 15 | 130 | the 15 cases whose answer is `False` |
| `always to_jsonb(0::float8)` | 1 | 130 | `all_missing_default` (`coalesce($.a,$.b,0)` → 0) |
| `always to_jsonb(''::text)` | 0 | 130 | — |

- The strongest single do-nothing compiler scores **20/130 (15.4%)**, so **110 of the 130
  agreements are agreement no single constant could fake** (`CONFORMANCE.md` §Degenerate
  baselines). A tighter figure, recomputed here and absent from `CONFORMANCE.md`: the **union**
  of all five constants covers **55/130** (19 null + 35 boolean + 1 zero), so **75 of 130 cases
  are unreachable by *any* of the five** — the number of agreements that required the compiler
  to actually compute something.
- Read the other way: the whole boolean class (35 cases, 26.9%) and the whole null class (19,
  14.6%) are individually constant-fakeable. **55 of 130 fixture cases carry no discriminating
  power against a constant emitter** (35 boolean + 19 null + the one numeric case whose answer
  is 0); the 75 that do are the remaining 53 numeric and all 22 string cases.

### 1.7 Proof the harness can fail — 23 negative controls, and exactly what they do not prove

FRAMING §8: a harness that cannot report the other three outcomes makes every downstream
finding green and worthless. `conformance.py` runs 23 controls **before** the conformance pass
and refuses to emit a report at all (exit 2) if any fails. **23/23 pass**
(`results.json` `negative_controls`, all `ok: true`).

| group | controls | what they prove |
| --- | --- | --- |
| compile-side | NC1 unknown AST tag → `Uncompilable`; NC14 stray `%` → `AssertionError` | `compile_ast` refuses an unknown tag; parameter binding cannot be silently corrupted |
| epsilon | NC2; NC3a `3.0+1e-10` passes; NC3b `3.0+1e-8` fails; NC3c `1e9+1.0` vs `1e9` fails | the epsilon is **absolute**, not relative — a large-magnitude near-miss is caught |
| type identity | NC4a–d (`True` vs `1`, `False` vs `0.0`); NC5a–c (`None` vs `0.0`, both directions) | booleans never score as 0/1; null is not zero either way |
| container strictness | NC6a mirrored rule accepts `[True]` vs `[1]`; NC6b strict check rejects it | the known hole in the mirrored rule is measured, not hidden — and §1.9.6 now measures its *contribution* |
| Postgres-side | NC7 division-by-zero → `SqlRaised`; NC8a `NULL::jsonb` → `(True, None)`; NC8b `'null'::jsonb` → `(False,'null')` | Postgres raises are captured as a value, not a crash; SQL NULL and jsonb `null` are held apart |
| liveness | NC9 same SQL over `{"k":1}`/`{"k":2}` → `'1'`/`'2'`; NC10 the `ctx` bind is live | the record column and the context bind actually reach Postgres |
| injected wrong answers | NC11 wrong SQL for case `add` (`python=3.0 sql=999`) caught; NC12 SQL NULL where Python has a value caught; **NC13 a number where Python has null caught (`python=None sql=0`)** | the comparator rejects each wrong-answer shape, including FRAMING §5's |

**NC13 is FRAMING §5 written as an executable test** — the disqualifying direction (a `null`
turned into a number) is demonstrably detected, not scored as agreement
(`results.json` `negative_controls[21]`, `detail: "python=None sql=0"`).

**Correction applied [`verifications.json`, material]. My earlier wording — "`COMPILED_DIVERGES`
is reachable from a real case", "injected end-to-end failures" — overstated what the code does,
and I confirmed the verifier by reading it.** `conformance.py:1010-1031`: NC11/12/13 each build a
value from a hand-written SQL string (`to_jsonb(999::float8)`, `NULL::jsonb`, `to_jsonb(0::float8)`)
and call `matches()` on it **directly**. None constructs a case entry; none asserts
`outcome == "COMPILED_DIVERGES"`. Likewise NC1 proves `compile_ast` raises `Uncompilable` at the
call site and NC7 proves `run_sql` raises `SqlRaised`, but neither drives the per-case loop, so the
**outcome-assignment branches at `conformance.py:376-455` are exercised by nothing.**
Corrected claim: *the 23 controls prove the comparator rejects each wrong-answer shape and that the
DB plumbing (record column, ctx bind, NULL/jsonb-`null` discrimination, raise capture) is live.*
That the three non-pass outcome **labels** are reachable is an **INFERENCE** from reading three
short unexercised `entry.update(outcome=…)` statements that sit immediately after the same
`try/except` blocks the controls do exercise. **What would establish it:** inject a wrong compiler
for one fixture case through the real per-case loop and assert the emitted `outcome` string. Not
done; a new injection point would have to be added to an instrument this pass may not edit.

Limits, restated plainly: the controls prove the *comparator and plumbing* can fail. They do not
prove the compiler is right for any construct the fixture does not contain — that is §1.9's job.

### 1.8 Mutation probe — is the record actually reaching Postgres?

Every compiled case was re-executed against an **empty record**, context unchanged
(`CONFORMANCE.md` §Mutation probe; recomputed from `results.json` `reads_a_field` /
`mutation_changed`): **68 / 130** cases read a field; **44** of those changed their answer on an
empty record; **24** did not, of which **10** already have a record of `{}` (the probe is a
literal no-op for them) and **14** are genuinely invariant with a non-empty record, each with a
semantic reason given individually in `CONFORMANCE.md` §Mutation probe (e.g. `add_missing_field`
— `$.b` is absent in both records; `eq_string_false` — `'pass' != 'FAIL'` and `null != 'FAIL'`
are both false).

**Honest limit:** the probe is a coarse liveness check with a 10-case blind spot and it cannot
separate "the field reached Postgres and the answer is genuinely invariant" from "the field
never reached Postgres". The *proof* that the `data` column is live is NC9, not the probe.
INFERENCE: 44/68 is a lower bound on field liveness, not a measurement of it.

---

### 1.9 Out-of-fixture divergences — the decision-relevant part of this finding

**The 130/130 is a statement about the fixture, not about the compiler.** Six of the seven
entries in `compile.py`'s own `KNOWN_DIVERGENCES` are marked `in_fixture: False`
(`compile.py:71-146`), so the fixture is structurally incapable of confirming or refuting them.
(`CONFORMANCE.md`:157 says *every* entry is — that is wrong, and it is the third prose-vs-raw
disagreement; see §1.10.) Two evidence sets probe outside the fixture: the 8 probes in
`results.json` `out_of_fixture_probes`, and the **19 battery scripts** in `analysis/fuzz/`
(§1.1). Neither changes any total in §1.2. Per FRAMING §3 nothing found was fixed.

#### 1.9.1 The 8 probes recorded in `CONFORMANCE.md`

| probe | expr | record | Python | SQL | cause | direction | in `KNOWN_DIVERGENCES`? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `overflow_via_multiply` | `$.a * $.b` | `{a:1e200, b:1e200}` | `inf` | **RAISED 22003 overflow** | `expr.py:614-621` has no overflow guard; float8 `*` aborts the query | **value → raise** (totality violation) | yes — `float8_overflow_raises`, `guarded:false` |
| `overflow_via_add` | `$.a + $.a` | `{a:1e296}` | `2e296` | `2e296` | — | agrees | n/a |
| `f8_guard_1e300_arith` | `$.a + 0` | `{a:1e300}` | `1e300` | **SQL NULL** | `xpr.f8`'s range-guard literal is 297 digits (`1.797693134862316e+296`) where DBL_MAX needs 309 | **value → null**, silent | **NO — undocumented** |
| `f8_guard_1e297_arith` | `$.a * 1` | `{a:1e297}` | `1e297` | **SQL NULL** | same guard literal | value → null, silent | **NO — undocumented** |
| `f8_guard_1e290_arith` | `$.a + 0` | `{a:1e290}` | `1e290` | `1e290` | below the guard — bounds the defect | agrees | n/a |
| `f8_readback_1e300_no_arith` | `$.a` | `{a:1e300}` | `1e300` | `1e300` | a bare field read never calls `xpr.f8` | agrees — **but only because the value is a scalar; see §1.9.6** | n/a |
| `num_of_1e999_string` | `number($.s)` | `{s:'1e999'}` | `inf` | SQL NULL | deliberate guard: NULL instead of an aborted query | value → null, **declared** | yes — `num_out_of_float8_range`, `guarded:true` |
| `unicode_upper_sharp_s` | `upper($.s)` | `{s:'straße'}` | `'STRASSE'` | `'STRAßE'` | PG `upper()` follows DB collation; Python does full Unicode case mapping | **value → different value**, silent | yes — `unicode_case_and_collation`, `guarded:false` |

`CONFORMANCE.md` §Out-of-fixture calls the `xpr.f8` guard defect *"a silent value-to-null
divergence — not the disqualifying direction under FRAMING §5"*. §1.9.2 shows that
characterisation is incomplete: through `sum`/`max`/`avg`/`concat`/`contains` the same defect
produces a silently wrong **value**, and §1.9.5 shows that under `if()` it produces a
**null → value**, which *is* the disqualifying direction.

#### 1.9.2 What `analysis/fuzz/` found that `CONFORMANCE.md` does not report

Same `compile.py` and `runtime.sql` bytes (§1.1), same mirrored rule (`fuzz/differ.py:44-50`),
same database. Every row below is a confirmed divergence outside the 130. Rates carry their
**method**, because two of them were previously stated in a way that implied the wrong one.

| # | class + witness | Python | SQL | rate measured (and how) | direction | in `KNOWN_DIVERGENCES`? |
| ---: | --- | --- | --- | --- | --- | --- |
| D1 | **`xpr.f8` guard → a wrong NUMBER, not a null.** `sum($.l)`, `{l:[1e300, 1]}` | `1e+300` | **`1`** | **16 of 20 probed paths diverge at `a=1e300`**; the 4 that agree (`count()`, bare field read, `==`, `if()`/truthy) are annotated in the raw output as **not routing through `xpr.f8`**, so it is **16 of 16 f8-reachable paths**. `max` → `1`, `avg` → `1` (`fuzz/A_f8_guard.txt` §A2) | **value → different value**, silent | **NO** |
| D2 | same defect through the text path: `concat($.a)` → `''`, and `string($.a)` → **SQL NULL**, `{a:1e300}` | `'1e+300'` | **`''`** / **NULL** | both in the same 16 (`fuzz/A_f8_guard.txt` §A2) | value → different value; value → null | **NO** |
| D3 | same defect, `contains($.s,$.a)`, `{s:'x1e+300x', a:1e300}` | `True` | **`False`** | ibid. | value → different value | **NO** |
| D4 | same defect on the **predicate path**: `$.a < 1e301`, `$.a > 1`, `$.a >= $.a` | `True` | SQL NULL | 3 of 3 order comparisons (`fuzz/A_f8_guard.txt` §A2) | value → null → **rows dropped** | **NO** |
| D5 | guard boundary, bisected live: largest magnitude that round-trips `1.79769313486231551e+296`; smallest corrupted `1.79769313486231587e+296` | — | — | every finite double with \|v\| ≥ 1.797693e+296 is mishandled — **about 12 of the float8 exponent's 632 decimal decades** (`fuzz/A_f8_guard.txt` §A3). The superseded `A2_boundary.txt` renders the same 12/632 as "1.8987% of representable doubles by exponent"; that is a share of the **decimal exponent range**, not of representable doubles, which are not uniform per decade — do not read it as "1.9% of all doubles" | — | **NO** |
| D6 | **float8 UNDERFLOW raises.** `$.a * $.a`, `{a:1e-200}` | `0.0` | **RAISED 22003 underflow** | 9 of 13 overflow/underflow probes made PG raise (`fuzz/B_overflow.txt`) | **value → raise** | **NO** — `KNOWN_DIVERGENCES` names overflow only |
| D7 | `round($.a, -2)` on a subnormal | `0.0` | RAISED 22003 underflow | per-probe run: `SQL_RAISE_ONLY` 94/8000 = **1.18%**, `BOTH_RAISE` 65/8000 = 0.81% (`fuzz/G2b_round_raises.txt`). The larger 40 000-pair run records **raises on either side 756/40 000 = 1.89%** with 0 value mismatches (`fuzz/G_fmod_round.txt` §G2) — quote both, because "0 value mismatches" alone reads as "round is clean" | value → raise | **NO** |
| D8 | **`xpr.num`'s ASCII gate vs Python's Unicode-aware `_to_num`.** `number('١٢٣')` (Arabic-Indic), `'１２３'` (fullwidth), Devanagari, NKO; NBSP / thin / ideographic space, unit-separator, NEL, U+2028 padding | `123.0` / `12.0` | SQL NULL | **10 of 27** `C_numgate` probes are this class (4 Unicode digit systems + 6 Unicode space code points). *Corrected:* the file's own "15 of 27" is its **total non-AGREE** count, which also contains 3 true DBL_MAX-overflow cases (`'1e400'`,`'-1e400'`,`'1e309'` — the declared `num_out_of_float8_range`), 1 f8-guard case (`'1.7976931348623158e296'`, i.e. D1–D5) and the 1 raise reported as D9 (`fuzz/C_numgate.txt`, all 27 rows) | value → null, silent | **NO** |
| D9 | same gate, `'1e-400'` | `0.0` | RAISED 22003 out of range | **1 of 27**, and **not** part of D8's 10 — the earlier text double-counted it | value → raise | **NO** |
| D10 | **date-string trimming**: `str.strip()` strips Unicode spaces that `btrim(E' \t\n\r\f\v')` does not (`expr.py:413` — `m = _DATE_RE.match(v.strip())`; `:415` is a bare `return None` — vs `runtime.sql:273`) | `1.0` | SQL NULL | **10 of 12** whitespace code points diverge (only U+0020 and U+000C agree); + **12** Unicode-digit divergences (6 digit systems × date and `number()`) = **22 in E2** (`fuzz/E2_dates_ws.txt`) | value → null, silent | **NO** |
| D11 | **Python raises, SQL returns a number.** `days_between($.d,"2024-01-02")`, `{d:'0001-01-01T00:00:00+14:00'}` | **`OverflowError`** | `738886.5833333334` | **4 `PY_RAISE` of 45** date probes (`fuzz/E_dates.txt`: 40 AGREE / 1 DIVERGE / 4 PY_RAISE); one witness is inside a boolean a dashboard would write, where SQL answers `True` | **raise → value** — FRAMING §5's second named direction | **NO** |
| D12 | **jsonb `numeric` ≠ IEEE double, CONFIRMED.** raw-JSON row `{"a": 1.00000000000000001}`, `$.a == 1` | `True` | **`False`** | 10 of 18 raw-JSON probes diverge (`fuzz/D_rawjson.txt`) | value → different value | yes — `jsonb_numeric_is_not_ieee_double`, which `CONFORMANCE.md` calls **unconfirmed** |
| D13 | `if($.a,1,2)` / `not $.a` / `$.a and true` on raw `{"a": 1e-400}` (`xpr.truthy` casts to `numeric`, where 1e-400 is non-zero; Python parses it to `0.0`) | `2.0` / `True` / `False` | **`1`** / `False` / `True` | 4 of 18 (`fuzz/D_rawjson.txt`) | value → different value, silent | **NO** |
| D14 | `number($.a)` / `$.a + 0` / `string($.a)` on raw `{"a": 1e-400}` | `0.0` / `0.0` / `'0'` | RAISED 22003 out of range | 3 of 18 | value → raise | **NO** |
| D15 | **CPython 3.12's `sum()` is Neumaier-compensated; Postgres `sum(float8)` is not.** `sum($.l)`, `{l:[1e16, 1.0, -1e16]}` | `1.0` | **`0`** | two numbers, two methods. **(a) proxy: 4368 of 20 000 random lists = 21.84%** — measured `expr._FUNCTIONS["sum"]` against a hand-written `SELECT sum(v ORDER BY o) FROM unnest(…)`, **not through `compile.py`** (`fuzz/K_sum_neumaier.py:92-95`); it is a faithful proxy because `runtime.sql:411` implements `sum` as exactly `sum(v ORDER BY ord)`. 99.73% on the "big value ± small corrections" profile; witnessed \|diff\| up to **35.4**. **(b) end-to-end through the compiler: 6 of 10 probes diverge** (`sum`/`avg` on `[1e16,1,-1e16]`, `[1e17,3,-1e17]`, `[1e9,1e-4,-1e9]`) (`fuzz/K_sum_neumaier.txt` §K2) | **value → different value**, silent | **NO** |
| D16 | `xpr.ecma_num` vs `_num_to_str` **at the pinned `extra_float_digits = 1`** | `'52990648348713780'` | `'52990648348713776'` | **56 of 200 000 doubles = 0.0280%**, 1 in 3571; all 56 round-trip to the same double, so it is a TEXT divergence (`fuzz/F1b_ecma_rate.txt`) | value → different value (string) | partially — `extra_float_digits_guc` describes a GUC dependency and implies agreement at `efd ≥ 0`; **the efd=1 mismatch itself is undocumented** |
| D17 | **`IMMUTABLE` + a GUC ⇒ index/seq-scan split brain.** 200 identical rows, index built at `efd=-3`: `WHERE string($.a)='0.3333333333333333'` returns **0 rows via index scan, 200 rows via seq scan** (`fuzz/F3_immutable_index.txt`) | 200 | 0 or 200, **plan-dependent** | **1 of 2 configurations.** The other — value `0.1`, index built at `efd=-5` — printed *"(no split-brain observed in this configuration — see notes)"* (`fuzz/F_ecma_num.txt` §F3). Reproduced once, attempted twice | silent row loss | consequence implied by `extra_float_digits_guc`'s note; **the split-brain witness is new** |
| D18 | Unicode case mapping | e.g. `'FF'` | `'ﬀ'` | **two rates, and the small one is misleading alone.** Single-code-point sweep: `upper()` **102 / 286 718** (0.036%), `lower()` **1 / 286 718** (`fuzz/I_case_collate.txt` §I1/§I2). **String-level, end-to-end through the compiler (§I3, 10 named strings): `upper()` diverges on 4 of 10, `lower()` on 3 of 10** — `'İstanbul'` → py `'i̇stanbul'` vs sql `'istanbul'`; `'ΣΊΣΥΦΟΣ'` → py `'σίσυφος'` vs sql `'σίσυφοσ'`; `'ΑΣ'` → py `'ας'` vs sql `'ασ'`. Greek final sigma is **context-dependent**, so every Greek word ending in Σ diverges under `lower()` and a per-code-point sweep is structurally blind to it. Reading "lower(): 1 in 286 718" as "lower() is safe" is wrong. The string-level *rate* is not established | value → different value | yes — `unicode_case_and_collation`. String **ordering** under `COLLATE "C"` was **0 / 1996 mismatches**, so the ordering half of that entry is not reproduced |
| D19 | array index beyond int4: `$.a[2147483648]` | `None` | RAISED 22003 integer out of range | 3 of 5 (`fuzz/L_misc.txt` §L2) | value → raise | **NO** |
| D20 | a NUL byte inside a string value cannot be stored as jsonb at all (`22P05`) | `3` | RAISED | 1 of 1 (`fuzz/L_misc.txt` §L3) | unreachable row — a fallback trigger, not a wrong answer | **NO** |
| D21 | broad AST fuzz, `extreme` profile: **44 diverge of 3880 that ran = 1.134%** (the file's 4000 is generated source strings, of which 120 were `PARSE_ERROR`), plus **3 `SQL_RAISE` overflow = 0.077%**. **Decomposed at closure: 21 of the 44 are comparator artifacts and 23 are real — §1.9.6** (`fuzz/H_extreme.txt`) | — | — | as stated | mixed | mixed |
| D22 | broad AST fuzz, `unicode` profile: **4 diverge of 3867 that ran = 0.103%** (133 `PARSE_ERROR` of 4000) — 2 "different value", 1 "value → NULL", **1 "NULL → value"** (`py: None` → `sql: True`). **Reduced to a 31-character reproducer and its cause named at closure — §1.9.5** (`fuzz/H_unicode.txt`) | `None` | **`True`** | 1 of 3867; but see §1.9.5 — the *mechanism* is not rare | **null → value** — FRAMING §5's first named direction | **NO** |
| D23 | **the same defects as a `WHERE` predicate, at the row level.** `$.amount > 100` over 8 rows: in-memory keeps `[2,3,5]`, SQL keeps `[2,5]` → **row 3 silently dropped**. `number($.amount) > 100`: **rows 3, 6, 7 silently dropped**. `not ($.amount > 100)`: **row 3 silently ADDED** (`fuzz/O_row_loss.txt`) | — | — | 4 of 4 predicates lose or gain rows | **silent wrong result set** | **NO** |

Batteries that found **no** divergence, reported so the picture is not one-sided:
`xpr.fmod` vs `math.fmod` **0 / 40 000** and `xpr.round` **value** mismatches **0 / 40 000**
(`fuzz/G_fmod_round.txt` — but see D7 for its 1.89% raise rate, which the "no divergence" framing
hides); evaluation-order / short-circuit **0 / 11** (`fuzz/N_shortcircuit.txt`);
95 language-convention corners **1 / 95** (the D15 sum case) (`fuzz/J_conventions.txt`);
`ordinary`-profile AST fuzz **0 divergences / 3881 that ran** (119 `PARSE_ERROR` of 4000)
(`fuzz/H_ordinary.txt`); string ordering **0 / 1996** (`fuzz/I_case_collate.txt` §I4); date parsing
agrees on **40 of 45** probes including every leap-year, offset, fraction-digit and range boundary
(`fuzz/E_dates.txt`) — **with one caveat recorded in §1.10: one of those 40 agreements is a
mislabelled control.**

#### 1.9.3 Direction verdict against FRAMING §5 and the §4 NO-GO bar — stated per class

FRAMING §5 names two disqualifying directions: *"turns a `null` into a number, or a raise into a
value."* FRAMING §4 adds: *"NO-GO if any case diverges silently — i.e. produces a number rather
than an error or an explicit fallback. One silently-wrong number is disqualifying on its own."*

| direction | classes | breaches §5 as literally written? | breaches §4's NO-GO bar? |
| --- | --- | --- | --- |
| **null → value** | D22, **now with a named cause and a 31-char reproducer (§1.9.5)** | **YES** on the first clause, with one caveat: the value produced is a boolean, not a number. INFERENCE: in a `where` predicate a spurious `True` keeps a row, which is the harm the clause exists to prevent. **What changed at closure: this is no longer a 1-in-3867 curiosity.** §1.9.5 shows it is the *composition* of any value→null divergence under an `if()` condition, demonstrated for three independent causes (D8, D1–D5, D10) | **YES** |
| **raise → value** | D11 (Python `OverflowError`, SQL returns `738886.58…`), 4 `PY_RAISE` of 45 date probes. **Understated as a statement about `expr` [consistency]:** all four of those witnesses are the *same* mechanism — `expr.py:430`'s offset arithmetic outside the `try/except`, `xa` R1. `expr.evaluate()` raises on data by **8 mechanisms across 9 source lines and 4 exception types** (`OverflowError`, `ValueError`, `ZeroDivisionError`, `RecursionError`), enumerated with re-verified witnesses at `xa` A.2 R1–R8; the date class is 1 of the 8. On `xa` A.5(i)'s direction matrix — 10 tabulated rows, which `xa` counts as 11 witnesses because its R6 row carries two — **4 rows are raise → value** (R1×2, R2, R8), 3 are raise → null (R4 @ DBL_MAX, R6, R7) and 3 are both-raise (R3, R4 @ 1.7e296, R5); `xa`'s own summary phrases this as "4 of 11". Correction ordered on this row by `xa` A.6 | **YES** — this is §5's second clause literally. Caveat recorded: §5's prose assumes `expr` never raises; here `expr` itself raises, contradicting `expr.py:640` and `recon/semantics.md §11`. The compiler still turns a raise into a value | **YES** |
| **value → different value (silently wrong number/string/bool)** | D1, D2, D3, D12, D13, D15, D16, D18, D21 (**9 of its 30 "different value", after §1.9.6 removes 21 comparator artifacts**), and probe `unicode_upper_sharp_s` | not one of the two directions §5 names | **YES** — D15 alone is a silently wrong number at **21.84%** by proxy and **6 of 10** end-to-end, with witnessed error 35.4; D1 turns `1e300` into `1` |
| **value → null (silently missing)** | D4, D8, D10, D21 (14 of 44, all real), probes `f8_guard_1e300_arith` / `f8_guard_1e297_arith` | no | not literally ("a number rather than an error"), but D23 shows it becomes **silent row loss** at the query level, and §1.9.5 shows it becomes **null → value** the moment it sits under an `if()` — i.e. this class is one composition step away from the §5 breach |
| **value → raise (totality violation)** | D6, D7, D9, D14, D19, D21 (3 SQL_RAISE), probe `overflow_via_multiply` | no — this is the *loud* failure Postgres was chosen for | no. It aborts the query rather than lying. It is still the harness's most severe outcome class, is unbounded in production, and §1.9.7 records that fixing D1–D5 would **enlarge** it |
| **silent wrong result set** | D17 (plan-dependent row count, 1 of 2 configurations), D23 (rows dropped **and added**) | — | **YES** — the answer changes with no error and no fallback signal |

**Bottom line of this sub-section, stated without softening: outside the 130-case fixture the
compiler as built breaches FRAMING §5 in both of its named directions and breaches the §4 NO-GO
bar in at least four independent ways. Inside the fixture, at `extra_float_digits = 1`, it
breaches neither.** Both statements are true simultaneously, and the gap between them is what a
decision-maker is being asked to price.

**One leg of that bottom line is WEAKER than it reads, and it is said here rather than left for the
gate to find [consistency].** The two breaches are not equally reachable. The **raise → value**
breach needs no unusual stored data at all — `xa` A.2 R2–R5 fire on the *expression text a tenant
writes* (`round($.x, 400)`, `round(1.797…e308, 3)`), which `parse()` accepts without complaint — so
that leg stands at full strength. The **null → value** breach (D22) is different: every one of its
three demonstrated causes (D8 fullwidth/Arabic-Indic digits, D10 Unicode whitespace, D1–D5
magnitudes ≥ 1.797693e+296) requires a *stored field value* of a kind that `xd` D.3–D.4 then
searched for and did not find — **0 of 1,096,202 string values + object keys** (the string-values-only
figure is 495,115, `xd` D.2) and **0 of 5,235,942 numeric nodes** on this machine (§1.11 item 6). The mechanism is real, named and reproduced in 31 characters; its
**frequency on real data is measured at zero for these corpora and remains unmeasured at production
scale** (`xd` D.8). OPINION (this seat): that makes the null → value leg an argument about
*exposure*, not about *observed harm*, and a decision-maker should price it that way.

#### 1.9.4 `KNOWN_DIVERGENCES` coverage — declared vs. found

`compile.py:71-146` declares 7 divergences. Against the evidence:

| id | `in_fixture` | status after this evidence |
| --- | --- | --- |
| `float8_overflow_raises` | no | **confirmed with a witness** (`overflow_via_multiply`); D6/D7 extend it to *underflow*, which the entry does not name; `fuzz/B2_overflow.txt` adds that the overflow it names is currently **masked** by D1–D5 (§1.9.7) |
| `num_out_of_float8_range` | no | confirmed (`num_of_1e999_string`; 3 of the 27 `C_numgate` probes) |
| `numeric_literal_inf` | no | **CONFIRMED AND GUARDED — my earlier "not tested" was wrong [closure, gap 16a].** `analysis/coverage.md:133-142` (f2 §2.6 C1) already ran it: `1e309 → UNCOMPILABLE`, `1e400 → UNCOMPILABLE`, `-1e400 → UNCOMPILABLE`, `$.a + 1e400 → UNCOMPILABLE` *(the whole expression, not just the literal)*. Re-verified live by this seat against the current `compile.py`: `1e308` compiles to `to_jsonb((%(p0)s)::float8)`; `expr.parse('1e309')` yields `('num', inf)` and `compile_ast` raises `Uncompilable("numeric literal overflows to inf/nan; jsonb has no representation for it")` at `compile.py:204-209`. The body no longer both asserts and denies this |
| `jsonb_numeric_is_not_ieee_double` | no | **confirmed** (D12). `CONFORMANCE.md` §Out-of-fixture records it as *"could not be probed… stays unconfirmed"* — the fuzz seat's `mode="raw"` ingestion did probe it |
| `unicode_case_and_collation` | no | case-mapping half **confirmed and rate-measured at two granularities** (D18: 102/286 718 code points for `upper()`, 1/286 718 for `lower()`; but 4/10 and 3/10 on named strings end-to-end); ordering half **not reproduced** (0/1996 under `COLLATE "C"`) |
| `extra_float_digits_guc` | **yes** | GUC dependency confirmed (4 of 8 values change with the GUC, `fuzz/F_ecma_num.txt` §F2); **understated in two directions.** (a) D16 shows a 0.028% mismatch at the pinned `efd=1`, which the entry's "shortest round-trip only while `efd ≥ 0`" implies away. (b) **The entry scopes itself to `string()`/`concat()` — the text channel. `fuzz/M_encoding_guc.txt` §M1 shows `to_jsonb(float8)` *itself* is GUC-dependent, so the compiled expression's RETURNED VALUE is too (§1.2, 68 of 130 cases exposed).** D17 then shows the `IMMUTABLE` mis-declaration turns that into plan-dependent answers, and `fuzz/L_misc.txt` §L5 shows **four** functions are mis-declared, not one: `ecma_num`, `f8`, `num` and `str` are all `IMMUTABLE` while depending on `extra_float_digits`; only `now_ms` is `STABLE` |
| `wall_clock_granularity` | no | **correction applied [`verifications.json`, material]: not "unexercised".** It is untested *by the conformance run* (all 6 clock cases inject `context.now`, §1.5) — which is all the entry itself claims — but `fuzz/E_dates.txt` runs `now()` and `today()` twice with record `{}` and **no** injected context, labelled *"wall clock, no ctx — expr uses per-record, SQL uses per-query"*, and **both are `<AGREE>`**. I verified both lines in the raw file. The real gap is different and sharper: **a single-row, single-query probe cannot distinguish a per-record clock from a per-query clock at all**, so those two AGREEs are not evidence the entry is refuted. Establishing it needs one query over ≥2 rows spanning a clock tick |

**Divergence classes `KNOWN_DIVERGENCES` does not name at all:** D1–D5 (the 297-digit `xpr.f8`
guard literal and its blast radius), D6–D7 (float8 **underflow** raising), D8 (`xpr.num`'s ASCII
gate vs Python's Unicode-aware `_to_num`) and D9, D10 (`btrim` vs `str.strip` date trimming),
D11 (`expr`'s own date `OverflowError` where SQL answers), D13–D14 (`xpr.truthy` and arithmetic
on sub-float8 jsonb numerics), D15 (`sum()` compensation), D19 (int4 index overflow), D20 (NUL
byte), D22 (null → value), D23 (row-level loss and gain). **That is the majority of the
confirmed out-of-fixture divergences, including both of the FRAMING §5 breaches.**

#### 1.9.5 D22 reduced — the `null → value` breach, its cause named [closure, gap 3 — CLOSED]

FRAMING §4 #1 requires every divergence to be **named with its cause**. D22 decides the go/no-go
bar and had neither a cause nor a reproducer: the witness in `fuzz/H_unicode.txt:30-33` is an
unreduced ~200-character generated AST. It was reduced here by reading plus read-only re-runs of
the **existing** `fuzz/differ.py` driver (no new instrument, nothing fixed, per FRAMING §3).

The witness, with the record `{"a":"１２３", "c":{"t":3}, "d":{"flag":"ÅNGSTRÖM"}, "e":"１２３",
"l":[-1], "o":2, "n":[], "flag":{}}`:

```
if( round(min(if($.t, $.b, "１２３"), $.e)),          <- the CONDITION
    max(("🙂" * days_between(true, $.a))),            <- the THEN branch
    (not (if(0.1,$.n,$.t)) > (($.d and null) or ("ﬀ" and $.d))) )   <- the ELSE branch
```

Sub-term results, each re-run through `differ.run_case` against the same live database:

| sub-term | Python | SQL | verdict |
| --- | --- | --- | --- |
| whole expression (the D22 witness) | `None` | **`True`** | DIVERGE — reproduced |
| **the condition** `round(min(if($.t,$.b,"１２３"), $.e))` | **`123.0`** (truthy) | **SQL NULL** (falsy) | **DIVERGE — this is the whole cause** |
| its leaves `if($.t,$.b,"１２３")` and `$.e` | `'１２３'` | `'１２３'` | AGREE |
| the THEN branch `max(("🙂" * days_between(true,$.a)))` | `None` | SQL NULL | **AGREE** |
| the ELSE branch `(not(if(0.1,$.n,$.t)) > (($.d and null) or ("ﬀ" and $.d)))` | `True` | `True` | **AGREE** |

**The cause, named: D8 — `xpr.num`'s ASCII-only numeric gate versus Python's Unicode-aware
`_to_num`.** `"１２３"` is U+FF11-FF13, fullwidth digits; Python's `_to_num` reads it as `123.0`,
`xpr.num` returns NULL. That single **value → null** divergence sits in an `if()` **condition**, so
the two runtimes take **different branches**. Python evaluates the then-branch, which is `None`;
Postgres evaluates the else-branch, which is `True`. **Neither branch is itself wrong — both agree
in isolation.** The `null → value` breach is manufactured entirely by branch selection.

**Minimal reproducer, 31 characters, record-independent:**

```
if(number("１２３"), null, true)     →   Python None   |   SQL True
```

**The mechanism is not specific to Unicode digits, which is the part that matters for the bar.**
Any `value → null` divergence placed in an `if()` condition inverts direction the same way — three
independent causes, each verified live in this pass:

| condition sub-term | its own direction | `if(<it>, null, true)` |
| --- | --- | --- |
| `number("１２３")` (D8, ASCII gate) | value → null | py `None` → **sql `True`** |
| `number("١٢٣")` (D8, Arabic-Indic) | value → null | py `None` → **sql `True`** |
| `$.a + 0` on `{a:1e300}` (D1–D5, the 297-digit `xpr.f8` guard) | value → null | py `None` → **sql `True`** |
| `days_between($.d,"2024-01-02")` on `{d:"٢٠٢٤-٠١-٠١"}` (D10) | value → null | py `None` → **sql `True`** |
| control: `if($.d, null, true)` on `{d:" 2024-01-01"}`, no divergent sub-term | — | **AGREE** |

So D22's headline rate (1 in 3867 generated `unicode`-profile expressions) measures **how often the
generator emits that shape**, not how reachable the defect is. The reachable population is
"any `if()` whose condition can hit D1–D5, D8 or D10" — which includes the ordinary dashboard shape
`if(number($.field) > 100, …)` over a field that ever holds a fullwidth or Arabic-Indic digit
string, or a magnitude ≥ 1.797693e+296. **Per FRAMING §3 this is recorded, not fixed.**
**Reachability, updated [consistency]:** whether such a field value occurs in real GIMS data was
**not established when this sub-section was written and was measured afterwards** — `xd` D.4 found
0 non-ASCII digits in 1,096,202 string values + object keys and `xd` D.3 found 0 values with
|v| ≥ 1.797693e+296 in 5,235,942 numeric nodes, so the reachable population named above is **empty
in the corpora on this machine**. Production-scale reachability remains open (`xd` D.8) — see §1.11
item 6.

#### 1.9.6 D21 decomposed — how much of the 44 is a comparator artifact [closure, gap 6 — CLOSED]

The critique is correct in its premise: the "30 different value / 14 value → NULL" split in
`fuzz/H_extreme.txt` is produced by `H_ast_fuzz.py:182-204` `_classify`, which buckets by
**direction**, not cause; and both published "different value" witnesses are field reads of arrays
containing `1e300`, where the mirrored rule compares containers with bare `==`
(`differ.py:44-50`, `test_dashboard_expr.py:25`) while giving scalars the 1e-9 epsilon. The share
was recoverable, because `H_ast_fuzz.py` is seeded (`random.Random(99)`) and the driver consumes
no randomness.

**Method:** a read-only re-run of the existing instrument. `H_ast_fuzz.py`'s generator was executed
with the identical profile/N/seed, producing the same 4000 `(src, record, ctx)` triples; each was
sent through the same `differ.run_case`; every non-`AGREE` outcome was kept instead of 2 witnesses
per class; and each `DIVERGE` was **re-scored with `conformance.py:114-127` `deep_strict`** — the
existing stricter comparator that applies the same 1e-9 epsilon **recursively into containers**.
A `DIVERGE` under the mirrored rule that `deep_strict` calls equal is a container-comparator
artifact by construction. No expression, record, seed, database object or comparator was invented.

**The re-run reproduced the capture exactly** — AGREE 3833, DIVERGE 44, SQL_RAISE 3,
PARSE_ERROR 120, cluster split 30 / 14 / 3 — which is itself a determinism datum (§1.5).

| | count | of 44 | of 3880 that ran |
| --- | ---: | ---: | ---: |
| **comparator artifact** — mirrored rule says DIVERGE, `deep_strict` says equal | **21** | 47.7% | 0.541% |
| **real divergence** — both comparators say DIVERGE | **23** | 52.3% | **0.593%** |
| of which `value → NULL` | 14 | | |
| of which `different value` (scalars) | 9 | | |
| `compare_error` (value not representable in Python) | **0** | | |

**All 21 artifacts are container-valued** (`isinstance(py, (list, dict))` is True for every one);
**all 23 real divergences are scalars.** The artifact mechanism, confirmed on the witnesses: jsonb
stores `1e+300` as `numeric` and renders it as a 301-digit integer, which `json.loads` decodes to a
Python **int**; `matches(10**300, 1e300)` on a *scalar* coerces via `float()` and passes the
epsilon, but inside a list Python's `==` compares int to float **exactly** and fails. That is
precisely the hole NC6a/NC6b measures (§1.7) — **its contribution to D21 is now measured at 21 of
44, not merely acknowledged.**

**Corrected D21 headline: 23 real divergences in 3880 expressions = 0.593%, not 44 in 4000 =
1.100%.** The 14 `value → NULL` remain real and the 9 `different value` remain real; nothing was
downgraded from "real" except the 21 container comparisons.

**And the 23 real ones have a single named cause [closure].** Regenerating each of the 23 records
offline from the same seed and screening for a magnitude ≥ `1.7976931348623157e+296` (the
`xpr.f8` guard bound, `runtime.sql:33`) in either the record or the source literals:
**23 of 23 carry one; 0 of 23 do not.** Witnesses across the range: `round(1.7976931348623157e+308)`
→ py `1.797…e308` / sql NULL; `min($.b, 1.7976931348623157e+308)` → py value / sql NULL;
`concat(1e+300)` → py `'1e+300'` / sql `''`; `sum($.o, …)` → py `1.797…e308` / sql `1`;
`lower(not((max($.b,$.b) != $.l)))` on `{b: 1e300}` → py `'false'` / sql `'true'`.
INFERENCE, labelled: the screen is a necessary-condition test, not a per-case proof of causation
for all 23 — but combined with the mechanism and with 0 counter-examples, **the `extreme` profile
found no divergence class that D1–D5 does not already explain.** It is one defect seen 23 ways, not
23 defects. The 3 `SQL_RAISE` are 22003 overflow (the D6 class).

The `unicode` profile was re-run the same way: **4 DIVERGE, 0 comparator artifacts, 4 real** —
so D22's breach is not an artifact of the container hole. Its index in the stream is 1312.

#### 1.9.7 The three captured outputs no section cited [closure, gap 16b — CLOSED]

`A_range.txt`, `A2_boundary.txt` and `M_encoding_guc.txt`/`B2_overflow.txt` were cited by no
section of the body. Two of them carry facts that change conclusions.

1. **`A_range.txt` — superseded, and folded in.** It is the fuller earlier form of the D1–D4 blast
   radius, and its content is reproduced identically in `A_f8_guard.txt` §A2, which **is**
   regenerable by `run_all.sh`. Everything it uniquely carried is now in D1/D2: `string($.a)` →
   **SQL NULL** (not only `concat($.a)` → `''`), and the explicit annotation that the four agreeing
   paths do not route through `xpr.f8`. Its final line — "16 of 20 **f8-reachable** paths diverge" —
   is the source of a wording error corrected in D1: the qualifier makes the denominator wrong and
   understates the defect. `A_f8_guard.txt` says "16 of 20 paths"; of paths that do reach `xpr.f8`
   it is **16 of 16**. `A2_boundary.txt` is likewise superseded by `A_f8_guard.txt` §A3, minus the
   "1.8987% of representable doubles by exponent" phrasing that D5 now flags as a share of the
   decimal exponent range rather than of doubles.
2. **`M_encoding_guc.txt` — changes a conclusion.** §M1 is now the stated condition on the headline
   (§1.2) and the second understatement in `extra_float_digits_guc` (§1.9.4): the GUC moves the
   **returned value**, not just `string()`'s rendering. §M2/M3 record two facts nothing else covers:
   jsonb **accepts `1e100000` as a `number`** and `xpr.truthy` calls it `True` (while Python parses
   `1e400` to `inf` and `1e-400` to `0.0` — the D13 mechanism, at a magnitude far beyond it), and
   beyond that `numeric` itself raises *"value overflows numeric format"*. `xpr.num` on `1e-400` is
   an **unguarded** underflow that raises (D9/D14), while `xpr.f8` on `1e400` is guarded to NULL —
   the two guards are inconsistent with each other.
3. **`B2_overflow.txt` — changes a conclusion, and is not regenerable.** Its own header states:
   *"The f8 guard clamps operands to ≤1.7976931348623157e296, so `+` `-` and `sum()` **CANNOT
   overflow TODAY**. That is an accident of defect #1, not a design."* **Consequence, recorded not
   chased (FRAMING §3):** D1–D5 and `float8_overflow_raises` are **coupled**. Correcting the
   297-digit guard literal converts today's silent value→null / value→wrong-value population on
   `+`, `-` and `sum()` into a new population of query-aborting SQLSTATE 22003 raises. The file also
   supplies overflow witnesses at magnitudes an order of magnitude smaller than the recorded probe
   (`$.a * $.b` on `{1e150, 1e160}`; `$.qty * $.price` on `{1e200, 1e200}` — "the shape a real
   dashboard writes"; `sum($.l) * sum($.l)`), both underflow witnesses behind D6
   (`$.a * $.a` on `1e-200`, `$.a / $.b` on `{1e-300, 1e100}`), and a **third mechanism by which
   `expr` itself raises**: `round($.a, 20)` on `1.7e296` → `BOTH_RAISE`, Python
   `OverflowError: cannot convert float infinity to integer`. That third mechanism belongs to the
   cross-section question of whether `expr` is total (`recon/semantics.md` §11, `expr.py:640`),
   which this finding records but does not adjudicate.

### 1.10 Where the raw data disagreed with the prose document

**Three places** (the third was missing from this list and is the one that licenses the whole of
§1.9). None changes a total in §1.2; all three matter to how the totals should be read.

1. **`CONFORMANCE.md`:157 says "Every entry in `compile.py`'s own `KNOWN_DIVERGENCES` is marked
   `in_fixture: False`". It is six of seven.** `compile.py:124-133` sets `"in_fixture": True` on
   `extra_float_digits_guc`. **The raw data wins.** The distinction is load-bearing: it is exactly
   the entry the 130-case run *does* touch, and §1.2 shows it touches 68 of the 130.
2. **`CONFORMANCE.md` calls `jsonb_numeric_is_not_ieee_double` unconfirmed. The raw record shows
   it confirmed.** `fuzz/D_rawjson.txt` witnesses `$.a == 1` on raw row `{"a":
   1.00000000000000001}` returning `True` in Python and `False` in SQL. **The raw data wins.**
   The reason `CONFORMANCE.md` gave (a record built from Python floats has already collapsed to
   IEEE doubles) is correct about *its own* ingestion path and wrong as a general claim —
   `fuzz/differ.py` `mode="raw"` casts JSON *text* to jsonb and reaches it.
3. **`CONFORMANCE.md` classes the `xpr.f8` guard defect as "a silent value-to-null divergence —
   not the disqualifying direction under FRAMING §5". The raw record shows the same defect also
   produces a silently wrong NUMBER** (`sum`/`max`/`avg` → `1` where Python gives `1e+300`,
   `fuzz/A_f8_guard.txt` §A2), a silently ADDED row via `not(...)` (`fuzz/O_row_loss.txt`), and —
   under an `if()` condition — the **null → value** direction §5 names first (§1.9.5).
   **The raw data wins: the defect's worst direction is not value → null.**

**Defects in the raw captures themselves [closure]** — none is this finding's error, none changes
a total, and each would mislead a reader who read that file alone:

- **`fuzz/E_dates.py`:42 mislabels a control.** The probe is captioned "NBSP U+00A0 padding" but its
  record is `{"d": " 2024-01-01"}` with a plain ASCII space (verified by reading the file's bytes:
  `' 2024-01-01'`, not `'\xa0…'`). It is scored `<AGREE>`. The **real** NBSP, tested at
  `E2_dates_ws.py:14`, **DIVERGES**. So one of the 40 agreements in "date parsing agrees on 40 of
  45" is a mislabelled ASCII control, and `E_dates.txt` read alone says NBSP padding is safe when
  E2 shows it is not. The 40/45 count is unaffected.
- **`fuzz/D_rawjson.txt` is not "a crashed run followed by a completed run"**, as this section
  previously described it. It is a crashed run printing probes 1–13 plus the traceback, then a
  second block containing only probes 10–18 and the summary; the overlap is probes 10–13
  (13 verdict lines before the traceback, 9 after; 18 distinct probes). The "10 of 18" tally is
  arithmetically correct once both blocks are read together. The traceback is `differ.py`'s
  `matches()` raising `OverflowError: int too large to convert to float` on a jsonb `1e400` against
  Python `inf` — the mirrored rule itself cannot compare those two values — and it is also the
  evidence that `differ.py` was edited mid-session (§1.1, reproducibility boundary).
- **`fuzz/H_parse_errors.txt`** reports `N=3000 / 92 parse errors` in its header but a `119`-count
  histogram from the `N=4000` run: a capture artifact of a superseded run, not a divergence.
- `results.json` `agreement_strength.max_abs_difference_case` is `"unary_minus"` while
  `max_abs_difference` is `0.0` — every delta is zero, so the "max" case is just the first element
  after a sort (`conformance.py:469-474`). Not a defect in the result.

### 1.11 Not established — the edge of what was measured

Each line names what is missing and the one concrete step that would close it.

1. **Whether the 130 still agree at any `extra_float_digits` other than `1`.** 68 of the 130 carry a
   value produced by a float8→jsonb or float8→text conversion and would need re-checking (§1.2).
   Not run: `conformance.py:341` hard-codes the GUC and this pass may not edit instruments.
   *Step:* parameterise that line; re-run the 130 at `efd = 0` and `efd = -3`.
2. **That the harness's three non-pass outcome LABELS are reachable** (§1.7). The comparator and the
   plumbing are proven; `conformance.py:376-455` is exercised by nothing. *Step:* drive one fixture
   case through the real per-case loop with a deliberately wrong compiler and assert the emitted
   `outcome` string.
3. **The JS leg of FRAMING §4 #1's "third runtime"** (§1.1). `frontend/lib/expr.js` was never
   executed; byte-identity across trees (FRAMING §2/C2) is a mitigation, not a measurement.
   *Step:* run the JS vector suite once against `expr_vectors.json` and record its pass count.
4. **`KNOWN_DIVERGENCES/wall_clock_granularity`** (§1.9.4). Two out-of-fixture probes exercise the
   no-context clock path and agree, but a single-row single-query probe cannot distinguish a
   per-record clock from a per-query one. *Step:* one query over ≥2 rows spanning a clock tick.
5. **The string-level rate of the `lower()`/`upper()` case-mapping divergence** (D18). The
   286 718-code-point sweep is structurally blind to context-dependent mappings such as Greek final
   sigma; only 10 named strings were run end-to-end. *Step:* sweep a word corpus, not a code-point
   range.
6. **Whether any of D1–D23 is reachable from real GIMS dashboard data — closed for this corpus by
   `xd` D.3–D.5; production-scale reachability remains open (`xd` D.8).** **[consistency]** Every
   witness in §1.9 is still a constructed record, and `fuzz/D_rawjson.py:12-17` still records the one
   reachability note this seat found: `gims-ledger/api/storage_aws.py:743-754` writes via
   `Jsonb(record)` from Python objects and so cannot produce the raw-JSON rows D12–D14 need, while
   `:694` reads with `json.loads`, so it *will* mis-read them if anything else wrote them. **The
   read-only scan this item prescribed was then run — `xd` D.3–D.5 — and returned zero on all three
   predicates:** `|v| ≥ 1.797693e+296` **0 of 5,235,942** numeric nodes (largest magnitude anywhere is
   1.787e+12, 284 decades short — `xd` D.3); non-ASCII digits or non-ASCII whitespace **0 of 1,096,202**
   string values + object keys, in a corpus that does carry 206,567 non-ASCII code points (`xd` D.4);
   `>17` significant digits and the writer-signature test (literal ≠ `repr(float(lit))`) **0 of
   5,236,427** numeric literals (`xd` D.5). So **D1–D5, D8, D10 and D12–D14 have no witness in the
   corpora on this machine.** *What remains open, and it is not small:* production-scale reachability
   — `xd` D.8 states the limit against itself (n = 1 machine, 1 operator, one writer signature,
   60.2% of rows written by AutoDev itself, 222 rows in the only tenant-shaped project, WAL not
   swept, 158 backup snapshots not swept, "nothing here extrapolates to production"). Note also that
   `xd` D.6/D.7 finds the *tolerant-coercion* class **reached at scale** on real rows, which is a
   different class from D1–D23's numeric/Unicode edges. *Step, restated for what is still open:*
   run `xd`'s predicates read-only against a production `instances` table (`xd` D.10 item 3).
7. **Whether a "loud fallback" mechanism can detect any of D1–D23 at query time.** No such mechanism
   exists in the prototype; its cost is Finding 5's question, not this one's.

**Compliance [consistency].** Read-only throughout, and stated at instrument level rather than by
tree state, because tree state alone cannot carry it here (`xd` D.1 documents a *live writer* in
`gims-ledger` during this spike, so "the tree looks unchanged" is not available as evidence).

- **Nothing was fixed.** D1–D23, the two FRAMING §5 breaches (§1.9.3), the `KNOWN_DIVERGENCES` gaps
  (§1.9.4) and the capture defects (§1.10) are **recorded, not repaired**, per the `sp-investigate`
  stop rules (FRAMING §3). `proto/compile.py` and `proto/runtime.sql` were not edited: their
  `sha256` today — `b71b1538…` and `32628b45…` — still equal `results.json` `meta`
  `compile_py_sha256` / `runtime_sql_sha256`, re-checked by this pass.
- **The §1.5 determinism re-run wrote nothing.** `conformance.run()` is `SELECT`-only
  (`conformance.py:331-460`, `out_of_fixture_probes:298-323` — no DDL, no `INSERT`); it was called
  twice in-process and its return value hashed. `main()`, which is what rewrites `proto/results.json`
  and `proto/CONFORMANCE.md`, was **never called**, and `proto/` is byte-unchanged —
  `results.json` mtime is still **11:45:53**, verified again at the time of writing. (Independently
  confirmed at `.parts/consistency.md` item 24, "Stop rules — no violation found".)
- **The §1.9.5 and §1.9.6 re-runs used existing instruments only.** `fuzz/differ.py` `run_case`
  issues `SELECT` only against `autosql_spike` and sets one session GUC
  (`SET extra_float_digits = 1`, `differ.py:60-62`) — no object created, altered or dropped;
  `H_ast_fuzz.py`'s generator was re-executed at the identical profile/N/seed and re-scored with
  `conformance.py:114-127` `deep_strict`. No expression, record, seed, database object or comparator
  was invented.
- **Neither GIMS tree was opened for writing by this finding's work**; both were read at the
  FRAMING §7 commits (`GIMS-Project` `995cc59`, `gims-ledger` `7b7a049`, re-checked). Working
  scripts ran in the session scratchpad, outside the repository, throwaway by contract (FRAMING §3).
- **What is NOT attestable from the artifacts, said rather than glossed:** this section's own
  scratch scripts (the §1.5 canonicalise-and-hash driver, the §1.9.6 re-score driver, the §1.9.5
  sub-term reductions) were **not retained**, so their read-only character is attested from the
  instruments they call and from `proto/`'s unchanged bytes — not from the scripts themselves.
  Same caveat, in the same direction, as `f3` §3.5(d)(ii)'s scratchpad comparison.

---

## Finding 2 — Coverage and fallback

**Question (FRAMING §4 #2):** which constructs compile, which cannot, the explicit fallback rule for each — and is that
fallback *detectable and reported at query time* (FRAMING §5)? Plus: confirm `query`/`cascade_deep_search` does not push down,
and bound it. Deep document: `analysis/coverage.md` (769 lines), cited by section, not copied. Every headline below was
re-derived by this seat from the raw artifacts before being quoted; the audit is §2.10, and it found three discrepancies with
the prose, none of which move the verdict.

| | count | where |
|---|---|---|
| Named grammar constructs, total | **48** | §2.1 |
| Compile **and** proven by a fixture case | **46** | §2.1 |
| Compile but **not** exercised by the fixture | **2** (`<=`, bare `$`) | §2.1 |
| **Do not compile** | **0** | §2.2 |
| Out-of-fixture probes run / agreeing — **value-domain *kind* probes only**, see the note below the table | **403 / 403** | §2.4 |
| Ways compilation actually fails today | **4**, all shape-keyed; **2 never raise `Uncompilable`** | §2.6 |
| Fallbacks reported at query time today | **0** | §2.8 |

**[amend-2026-08-21] The out-of-fixture row was unscoped, and read alone it said the wrong thing.** It
published a bare **403 / 403**, which invites the reading that probing *outside the 130-case test fixture*
("out-of-fixture") found nothing wrong anywhere. It did not. The 403 are the **value-domain kind** probes in
`proto/coverage_probe_results.json` — 403 entries, every one `COMPILED_AGREES`, re-counted from the raw file
during this amendment. A **second and entirely separate** out-of-fixture set exists in the raw data and was
never folded into this table: `proto/results.json → out_of_fixture_probes` holds **8** probes, of which
**3 agree**, **4 are recorded `DIVERGES`** (`f8_guard_1e300_arith`, `f8_guard_1e297_arith`,
`num_of_1e999_string`, `unicode_upper_sharp_s`) and **1 is `SQL_ERROR (totality violation)`**
(`overflow_via_multiply` — Postgres refused `1e200 * 1e200` with SQLSTATE **22003**, *value out of range*,
where Python's evaluator answers `inf` and never raises). §2.5 and §2.7 R1–R4 carry those four divergences
honestly, so nothing was hidden in the body — but a reader who scanned only this summary table came away with
"out-of-fixture probing: 100% clean", and now does not. **Authority:** `.parts/verifications.json` →
`Finding 2 — Coverage and fallback` → `corrections[1]`, severity **material** — a correction the closure pass
produced but never applied, because the seat that was to apply it died. Both counts re-derived from the raw
JSON here. See the closure-log entry *Amendment round*.

### 2.1 The construct census — enumerated mechanically, so the count is auditable

The universe came from the evaluator, not the design doc, and by script rather than by eye (`analysis/coverage.md` §1): **AST
node tags** = every `if tag == "…"` branch in `_eval` (`expr.py:580-635`); **function whitelist** = the keys of `_FUNCTIONS`
(`expr.py:530-553`); then the same for the compiler's `_t_<tag>` / `_f_<name>` dispatch in `proto/compile.py`. **This seat
re-ran the enumeration independently** rather than trusting the transcription:

```
AST_TAGS_IN_EVAL 12  and bin bool call cmp field neg not null num or str
FUNCS_IN_EXPR    22  abs avg ceil coalesce concat contains count date_add days_between floor if
                     length lower max min now number round string sum today upper
COMPILE_TAGS 12 / COMPILE_FUNCS 22    MISSING_IN_COMPILE []    EXTRA_IN_COMPILE []
```

The two sets are equal in **both** directions: the compiler omits no construct the language has and invents none it does not.
Counted at the granularity at which constructs can differ (operators through the `cmp`/`bin` tags, not as tags): **10**
leaf/structural node types (`num` `str` `bool` `null` `field` `neg` `not` `and` `or` `call`) + **5** arithmetic operators (`+
- * / %`) + **6** comparisons (`== != < <= > >=`) + **22** whitelisted functions + **5** field-path forms (bare `$`, `.ident`,
`["quoted"]`, `[n]`, `[-n]`) = **48**. Unary `+` (`expr.py:180-182`) and parentheses (`expr.py:196-199`) emit **no AST node**
and are correctly excluded.

Which of the 48 the fixture exercises was computed by walking the real parser's AST over all 130 cases, not by grepping text;
this seat re-ran the walk and reproduced `analysis/coverage.md` §3 **cell for cell** (`call` 72 cases, `field` 68, `num` 55,
`str` 34, `cmp` 24, `bin` 18 … `!=`/`>=` 1 each; all 22 functions occur at least once, thinnest at one case — `upper`, `min`,
`now`). **`<=` occurs 0 times; bare `$` occurs 0 times.**

So: **46 of 48 compile and are fixture-proven** — proven meaning the construct occurs in ≥1 of the 130 cases, and that case
compiled, ran against live PostgreSQL 16.14 and agreed (`proto/results.json`, 130/130 `COMPILED_AGREES`); **2 of 48 compile
but are unexercised**; **0 do not compile**. One case proves a construct *compiles*, not that it is *right*: `upper` is proven
by exactly one ASCII case, and the conformance seat's probing found `upper("straße")` → Python `STRASSE` vs SQL `STRAßE`. §2.3
sizes that risk.

### 2.2 The "does not compile" column is empty — a structural problem, not a win

`compile.py` refuses **no construct** (§2.1's set equality; every one of the 48 was also compiled individually —
`analysis/coverage.md` §2). So **there is no construct-keyed fallback rule to write**: the table a reader expects — "construct
`X` never compiles, therefore fall back whenever you see `X`" — does not exist, because there is no such `X`. The compiler
holds **exactly one** construct-keyed refusal path, `compile.py:301` (`raise Uncompilable(f"builtin {name!r} has no SQL
compilation")`), and it is provably dead: it fires only when a whitelisted function has no `_f_` method, and
`FUNCS_MISSING_IN_COMPILE == []`.

**Consequence for the design.** The contract's named refusal signal is the `Uncompilable` exception (`compile.py:54-59`). A
fallback keyed on catching it is a mechanism that **almost never fires, guarding a failure mode that is not the real one**:
the two things it does catch are magnitude guards, not constructs (§2.6 C1/C2); two of the four ways compilation actually
fails do not raise it at all (§2.6 C3/C4); and the whole silent-divergence class is invisible to it by construction (§2.7
R2–R5/R7).

**The real exposure is the value domain** — the same 48 constructs applied to JSON values the 130 hand-authored cases never
feed them. Every construct is polymorphic over six JSON value kinds (`null` `bool` `number` `string` `list` `dict`), and
`compile.py` dispatches those kinds inside the `xpr` SQL functions, so an unexercised kind is unexercised SQL.

### 2.3 Sizing the value-domain gap — what the fixture leaves untouched

Measured by wrapping the evaluator's own helpers in memory and replaying all 130 cases (`analysis/coverage.md` §4.2). **This
seat re-derived every number below independently and reproduced them exactly.**

| helper | drives | kinds | never exercised |
|---|---|---|---|
| `_truthy` (`expr.py:282`) | `not` `and` `or` `if` | 5/6 | **dict** |
| `_to_num` (`expr.py:305`) | arithmetic, `neg`, `number`, `abs`/`floor`/`ceil`/`round`, aggregates | 4/6 | **list, dict** |
| `_to_str` (`expr.py:351`) | `string`, `concat`, `lower`, `upper` | 4/6 | **list, dict** |
| `_parse_date_ms` (`expr.py:409`) | `days_between`, `date_add`, `today`/`now` | **1/6** | **null, bool, number, list, dict** |

```
_eq (== != deep-equality contains-in-list)  7/36 cells    _order_cmp (< <= > >=)      4/36 cells
         null  bool   num   str  list  dict                    null  bool   num   str  list  dict
 null       2     .     .     .     .     .          null         .     .     1     .     .     .
 bool       .     1     1     .     .     .          bool         .     .     .     .     .     .  <-empty
  num       1     .     2     .     .     .           num         .     .    10     1     .     .
  str       .     .     1     8     .     .           str         .     .     .     1     .     .
 list       .     .     .     .     .     .  <-empty  list        .     .     .     .     .     .  <-empty
 dict       .     .     .     .     .     .  <-empty  dict        .     .     .     .     .     .  <-empty
```

**29 of 36 `_eq` cells and 32 of 36 `_order_cmp` cells are never touched by the fixture.** No fixture case compares a list or
a dict to anything, orders a boolean, feeds a container to `number()`/`string()`, or passes a non-string to a date function.
That is not a criticism of the fixture: it is 130 hand-authored *contract* cases whose own note says "Hand-authored expected
values — do NOT regenerate from either evaluator" (`expr_vectors.json`, `note`), and a contract fixture is not a coverage
tool. The point is that **130/130 must not be read as "the compiler is proven", and this is the size of the difference.**

### 2.4 Closing the gap — 403 value-domain *kind* probes, 403 agree

**[amend-2026-08-21] This heading was unscoped as well, and the amendment round above missed it.** It read
*"2.4 Closing the gap — 403 out-of-fixture probes, 403 agree"*. Exactly like the summary row that cites this
section, that wording reads as though **all** probing outside the 130-case test fixture came back clean. It
did not. These 403 are the **value-domain *kind* probes only** — `proto/coverage_probe_results.json`, 403
entries, every one `COMPILED_AGREES`, re-counted from the raw file here. The **second and entirely separate**
out-of-fixture set, `proto/results.json → out_of_fixture_probes`, is **8 probes — 3 agree, 4 `DIVERGES`, 1
`SQL_ERROR (totality violation)`**, also re-counted here; it is outside this section's scope and is carried
by §2.5 and §2.7 R1–R4. Same authority and the same figures as the summary-row note above
(`.parts/verifications.json` → `Finding 2 — Coverage and fallback` → `corrections[1]`, severity
**material**). Scoped on 2026-08-21 by the parts-reconciliation pass; see `.parts/README.md`.

Harness `proto/coverage_probe.py`; raw record `proto/coverage_probe_results.json`. It imports `matches()`, `deep_strict()`,
`run_sql()`, `SqlRaised` and `DSN` from `proto/conformance.py` rather than reimplementing them, so a probe is scored by
exactly the rule the 130-case run used (mirrored from `GIMS-Project/tests/test_dashboard_expr.py:20-25`). **403 probes in 11
groups:** `cmp-matrix` 216 (6 comparison operators × the full 6×6 operand-kind matrix, **all 36 `<=` cells included**),
`deep-eq` 28 (reordered keys, differing length, `1` vs `1.0`, `true` vs `1`, nested nulls, `0.0` vs `-0.0`), `truthy` 24,
`to_str` 24, `arity-edge` 24 (zero- and over-arg calls across the whitelist), `agg-arity` 21, `to_num` 18, `length` 12,
`contains` 12 (hay **and** needle over 6 kinds), `date` 12, `bare-$` 12.

**Result, read from the raw file rather than the prose: 403 entries, 403 `COMPILED_AGREES`** — zero `COMPILED_DIVERGES`,
`COMPILED_AGREES_LOOSE_ONLY`, `DID_NOT_COMPILE`, `SQL_ERROR`, `COMPILER_CRASHED`, `PARSE_ERROR`, `PYTHON_RAISED`; per-group
counts match the raw file exactly. Coverage before → after, same instrumentation as §2.3: `_eq` **7/36 → 36/36**, `_order_cmp`
**4/36 → 36/36**, `_truthy` 5/6 → 6/6, `_to_num` 4/6 → 6/6, `_to_str` 4/6 → 6/6, `_parse_date_ms` 1/6 → 6/6 (**reject path
only** — §2.5). Both unexercised constructs are now proven: re-parsing every `cmp-matrix` entry's expression and record from
the raw file gives 36 distinct operand-kind pairs for **each** of the six operators, `<=` included; bare `$` has 12 probes.

**What the 403 agreements are made of** — a raw-data reading the prose does not state, and it governs how much weight the
number carries:

| | n | share |
|---|---|---|
| Python `None` **and** SQL `NULL` (both refuse) | **196** | 48.6% |
| Both returned a concrete value, agreeing | **207** | 51.4% |
| Python non-`None` but SQL `NULL` (value → null) | **0** | — |
| Python `None` but SQL non-`NULL` (**null → value: FRAMING §5's disqualifying direction**) | **0** | — |

Roughly half the set proves both engines *refuse* in the same places — a weaker claim than agreeing on a computed value — but
the last two rows are what the go/no-go bar turns on, and both are **zero across all 403**. Separately, the probe set
records `0 PYTHON_RAISED` over 403 inputs. **That count is kept; the inference this paragraph originally drew from it —
that it is "403 independent confirmations of the totality premise the design rests on" (`recon/semantics.md` §11:
"`expr.py` never raises for data reasons") — is deleted, on the adjudication of `xa` A.6.** †

> **† Why the zero licenses no conclusion about totality — forward pointer to `xa` A.6 [consistency].** `xa` A.2 finds
> **8 raise mechanisms across 9 source lines and 4 exception types** in `expr.py` (R1–R8), and `xa` A.3 shows that **the
> 403-probe domain cannot reach a single one of them** — by construction, not by luck. Re-derived by this seat directly
> from `proto/coverage_probe_results.json` (403 entries), against `xa` A.2's measured thresholds: max |numeric value|
> anywhere in the 403 records is **9.0**; the largest number appearing anywhere in their sources is **2026.0**, and that
> is the year inside the string `"2026-01-01"` — the largest bare numeric literal is **4.0** (R4 needs ≥ ~1.8e308, so
> `xa` A.3's 2026.0 is a conservative bound on a domain that is in fact smaller); max record
> nesting depth is **4**, containers only (R8 needs ≥ 498); the only `round()` ndigits literals present are **−1 and 2**
> (R3 needs ≥ 309, R5 needs ≤ −324, R2 needs ±inf); the token `%` occurs in **0 of 403** probe sources (R7);
> `floor()`/`ceil()` appear **zero-arg only** (R6); and there are **0** offset-bearing date strings — the only ISO dates
> anywhere in the set are `2026-01-01` and `2026-01-02` (R1 needs a non-`Z` offset within 4.194 d of the year-1/9999
> boundary). `xa` A.6 also rules `recon/semantics.md` §11 **false as a universal**; its narrow true form is `xa` A.4's
> N1–N4. So the 0 is a zero over a domain that cannot reach the failure: it neither confirms nor tests totality.
>
> **Direction of this repair [consistency]:** it removes evidence that was reading *for* the design's premise, so §2.4
> now supports the go-bar by less than it did. It adds nothing against compilation as such — the two null-mismatch rows
> above, which are what FRAMING §5 turns on, are **0 / 0** and are untouched. What the 403/403 does still establish is
> stated in §2.3–§2.4 and bounded in §2.5: the 6×6 operand-*kind* matrix, not a magnitude or boundary domain.

Substantive witnesses by raw index, hitting all three NULL regimes `recon/semantics.md` §11 warns are **not** interchangeable
— two-valued (`==`/`!=`), three-valued (comparisons, arithmetic, dates), null-as-a-concrete-value (`contains`, `concat`,
`count`, `coalesce`, `_truthy`). A compiler assuming one uniform NULL rule would fail this table:

| probe | expression | inputs | Python | SQL | raw index |
|---|---|---|---|---|---|
| `dict_keyorder` | `$.a == $.b` | `{"a":1,"b":2}` vs `{"b":2,"a":1}` | `true` | `true` | `cases[344]` |
| `list_bool_one` / `num_neg_zero` | `$.a == $.b` | `[true]` vs `[1]` / `0.0` vs `-0.0` | `false` / `true` | `false` / `true` | `cases[334,356]` |
| `length_dict` / `not_empty_dict` | `length($.a)` / `not $.a` | `{"k":1}` / `{}` | `1` / `true` | `1` / `true` | `cases[295,303]` |
| `concat_null` / `hay_null` | `concat($.a)` / `contains($.a,1)` | `null` | `""` / `false` | `""` / `false` | `cases[220,228]` |
| `count()` / `sum()` | `count()` / `sum()` | — | `0.0` / `null` | `0` / `SQL NULL` | `cases[358,359]` |

**Proof the probe harness can itself fail.** A 403/403 sheet is what FRAMING §8 warns will look green when it is wrong, so two
checks apply. (1) **Outcome vocabulary** — `coverage_probe.py`'s `main()` ladder emits **eight** distinct outcomes
(`PARSE_ERROR`, `PYTHON_RAISED`, `DID_NOT_COMPILE`, `COMPILER_CRASHED`, `SQL_ERROR`, `COMPILED_DIVERGES`,
`COMPILED_AGREES_LOOSE_ONLY`, `COMPILED_AGREES`); FRAMING §8 requires three distinguishable outcomes, and "did not compile" is
a separate label from "agrees" by construction, so it cannot be scored as a pass. (2) **11/11 negative controls**
(`analysis/coverage.md` §5.1) run against known-wrong inputs before the result was quoted; the load-bearing two are **NC3**,
injecting a number where Python has `null` (FRAMING §5's disqualifying direction) → reported DIVERGES, and **NC9**, record
`{}` vs `{a:2}` → reported DIVERGES, ruling out that probes passed because the SQL never read the record. Also confirmed
there: SQL `NULL` distinguished from jsonb `'null'`, a deliberate Postgres raise surfacing as `SQL_ERROR(22012)` rather than
being swallowed, and the epsilon absolute rather than relative.

### 2.5 What the 403 probes do **not** close

- **The date row is weaker than it reads.** All **12** `date` probes returned Python `None` and SQL `NULL`
  (`coverage_probe_results.json` `cases[226,227,240,241,254,255,268,269,282,283,296,297]`) — including the `string` kind,
  because the probe's representative string is `"5"`, not a parseable date. "`_parse_date_ms` 6/6 kinds" therefore means
  *every kind was fed and both engines rejected it identically*; **no probe exercises a successful date computation on any
  kind.** Date arithmetic is covered by the fixture (`days_between` 9 cases, `date_add` 7, `today` 5, `now` 1) and by nothing
  else here.
- **Coverage is not correctness.** 36/36 cells means one witness per cell, not exhaustion.
- **The 7 `KNOWN_DIVERGENCES` at `compile.py:71-146`** are the compiler author's own list, 6 of 7 marked `in_fixture: false`.
  The conformance seat confirmed three and found a fourth (the `xpr.f8` range guard written to 297 digits where it should be
  309, silently NULLing finite values above ~1.8e296) — all **value-domain** issues, which is exactly why 130/130 could not
  see them. Not re-litigated here.
- **Open axes** (`analysis/coverage.md` §5.2): collation and case mapping beyond ASCII (ordering is pinned `COLLATE "C"` in
  `runtime.sql`, case mapping is not); numeric precision beyond IEEE double, which stays **unconfirmed, not refuted**, because
  a >17-digit literal cannot be reached through a Python-built record; and date *format* variants (`_parse_date_ms` accepts 6
  shapes, `expr.py:402-407` — the kind axis was probed, the format axis was not).

### 2.6 How compilation actually fails today — four ways, shape-keyed, two invisible to `Uncompilable`

`Uncompilable` is raised from **eight** sites in `compile.py` (173, 194, 200, 207, 237, 274, 294, 301). Five (194, 200, 237,
274, 294) are defensive guards against a malformed AST — the parser's tag, path-step and operator universes are closed. One
(301) is the only construct-keyed refusal and is provably dead (§2.2). **Two are reachable from a valid, in-sandbox
expression, and neither is keyed on which constructs appear:**

| # | trigger, as measured | signal | site |
|---|---|---|---|
| **C1** | numeric **literal** overflowing float8 — `1e308` compiles, `1e309` does not; `$.a + 1e400` refuses the whole expression | `Uncompilable` ✅ | `compile.py:204-209` |
| **C2** | generated SQL exceeds `MAX_SQL_CHARS = 200 000` | `Uncompilable` ✅ | `compile.py:51,172-176` |
| **C3** | flat operator chain — **first failure at 333 `+` operands, source length 665 chars** (language cap 2000) | **`RecursionError`** ❌ | recursion in `compile.py`, no guard |
| **C4** | nested `date_add` — **first refusal at depth 11 (294 795 chars of SQL); at depth ~24 (300-char source) the process dies before the cap is checked** | **`MemoryError`** ❌ | `compile.py:318-326` + `172-176` |

**C3, re-measured by this seat.** `compile.py` recurses ~3 Python frames per AST level against CPython's default limit of
1000, and the parser's `MAX_DEPTH = 64` cannot catch it: `_primary`'s depth counter is incremented and decremented around each
primary (`expr.py:184-208`), so a flat `1+1+1+…` never exceeds depth 1. Bisected fresh — every row parses and evaluates
correctly in Python, then fails to compile:

| expression | first failing size | source length | `expr.evaluate` | `compile_ast` |
|---|---|---|---|---|
| `1+1+1+…` | **333 operands** | **665** (cap 2000) | OK → `333.0` | **`RecursionError`** |
| `1 or 1 or …` / `1 and 1 and …` / `not not …1` | **333 / 333 / 332** | **1661 / 1993 / 1329** | OK | **`RecursionError`** |

**[amend-2026-08-21] The or / and / not row published the wrong quantity.** It read **400 / 334 / 499**
operands at **1996 / 1999 / 1997** characters, under a column headed *"first failing size"*. Those are not
first failures — they are the **largest** chains of each shape that still fit under the language's own
`MAX_SOURCE_LEN = 2000` (one operand more and each exceeds 2000 characters). All three of them do fail; so
does every size down to the figures now shown. Publishing the ceiling as though it were the floor made this
failure look far harder to reach than it is — `not not …1` bites at **1 329** characters, not 1 997. The
figures now shown were re-bisected during this amendment through the real parser
(`GIMS-Project/core/dashboard/expr.py`) into `proto/compile.py`: for each of the three, `n−1` compiles
cleanly and `n` raises, so each boundary is sharp, and all three still evaluate correctly in Python at the
failing size. The `1+1+1+…` row was already correct and is unchanged. **Authority:**
`.parts/verifications.json` → `Finding 2 — Coverage and fallback` → `corrections[0]`, severity **material** —
a correction the closure pass produced but never applied, because the seat that was to apply it died. This is
now the third independent reproduction of 333 / 333 / 332. See the closure-log entry *Amendment round*.

At 332 operands (663 chars) it compiles cleanly, so the boundary is sharp. **A 665-character expression — one third of the
language's own `MAX_SOURCE_LEN = 2000` — is enough.** The threshold is a function of `sys.getrecursionlimit()` (1000 here)
*and* of how deep the caller's stack already is: the existence of the failure is general, the integer is not.

**C4, re-measured by this seat.** `_f_date_add` (`compile.py:318-326`) emits its compiled first argument **twice** — once
inside `xpr.pdate_ms(...)`, again inside `xpr.pdate_only(...)` — because the date-only flag comes from the input and cannot be
recovered from the timestamp (the comment at `compile.py:322-323` says so). Each nesting level therefore **doubles** the SQL:

| depth | source | generated SQL | ratio/level | outcome |
|---|---|---|---|---|
| 1 | 24 | 168 | — | compiles |
| 8 | 108 | 36 744 | 2.01× | compiles |
| 10 | 132 | 147 337 | 2.00× | compiles |
| **11** | **144** | **294 795** | 2.00× | **`Uncompilable`** (first refusal) |
| ~24 | ~300 | ~2.4 GB | 2.00× | **`MemoryError`** (`analysis/coverage.md` §2.2, under a 2 GiB `RLIMIT_AS`) |

The cap at `compile.py:172-176` is checked **after** `self._j(node)` has built the entire string, so it cannot prevent the
blow-up it exists to bound — it reports it afterwards, and only while the string still fits in RAM. The parser permits depth
**63** — and it is that depth guard, not the character budget, that binds — so the reachable worst case is far past 24; at
depth 24 the source is 300 characters and `expr.evaluate` answers it correctly and instantly.

**[amend-2026-08-21] The depth figure was one too high.** This sentence read *"The parser permits depth 64
and 2000 characters permit depth 165"*. `MAX_DEPTH = 64` (`expr.py:40`) is enforced by `_primary` as an
increment **and then** a test — `self.depth += 1` followed by `if self.depth > MAX_DEPTH: raise`
(`expr.py:185-187`) — so the counter only ever reaches 64 on the expression that gets rejected. The deepest
nesting that actually survives is therefore **63**, one below the constant. Re-verified against the GIMS
source during this amendment, and measured live: a 63-deep `date_add` nest parses, a 64-deep one raises
`ExprError("Expression nesting too deep")`. The dropped second clause was moot as well — a 165-deep nest is
refused by the depth guard long before the 2 000-character budget is anywhere near reached, so the character
count never binds. The conclusion does not move: 63 is still far past 24. **Authority:**
`.parts/verifications.json` → `Finding 2 — Coverage and fallback` → `corrections[5]` — a correction the
closure pass produced but never applied, because the seat that was to apply it died. See the closure-log
entry *Amendment round*.

**Severity.** Neither C3 nor C4 produces a wrong number, so neither breaches FRAMING §5 — they are loud, in-process failures.
But both breach the other half of the GO bar: the named refusal signal is `Uncompilable`, and **a caller writing `except
Uncompilable: fall_back()` would catch neither.** Per the stop rules these are **recorded, not fixed**.

### 2.7 The explicit fallback rules — every one keyed on a condition, none on a construct

Because column 3 is empty, no rule reads "construct `X` never compiles". Each is keyed on a *shape*, a *magnitude*, a *runtime
value*, or a *source type* — a more awkward answer than the expected one, because a condition-keyed rule cannot be decided
from the expression text alone. **Detectable** = could a caller mechanically know? **Reported** = does any code path in GIMS
as it stands surface it? (§2.8 proves the "no"s.)

| # | when | condition | fallback rule | detectable | reported |
|---|---|---|---|---|---|
| C1 | compile | numeric literal overflows float8 (`compile.py:204`) | `Uncompilable` → evaluate in memory | yes (catch `Uncompilable`) | **no** |
| C2 | compile | generated SQL > 200 000 chars (`compile.py:172`) | `Uncompilable` → in memory | yes (catch `Uncompilable`) | **no** |
| C3 | compile | flat operator chain ≥ ~333 operands | **none — `RecursionError`** | only if `RecursionError` also caught | **no** |
| C4 | compile | nested `date_add` ≥ ~24 | **none — `MemoryError` / RAM exhaustion** | only if `MemoryError` also caught | **no** |
| R1 | run | float8 overflow in `+ - * /` (`1e200*1e200`): Python → `inf`, SQL **raises** `22003` and aborts the transaction | catch SQLSTATE `22003` → re-run in memory (full retry, not a resume) | yes | **no** |
| R2 | run | JSON number / numeric string beyond DBL_MAX: Python `inf`, SQL guarded to `NULL` (`compile.py:84-93`, deliberate) | none — value silently differs | **no** | **no** |
| R3 | run | finite value ~1.8e296 … DBL_MAX through arithmetic → **silently `NULL`** (`xpr.f8` guard literal 297 digits, should be 309) | none | **no** | **no** |
| R4 | run | `lower()`/`upper()` on non-ASCII: `"straße"` → Python `STRASSE`, SQL `STRAßE` | none — silently different string | **no** | **no** |
| R5 | run | `extra_float_digits` GUC ≠ 1 changes float text | pin the GUC per session | **no** at query time | **no** |
| R6 | run | `today()`/`now()` with no `context.now`: Python re-reads the clock **per record** (`expr.py:456`), SQL `now()` is the **transaction** timestamp | always inject `context.now` | yes (caller controls it) | n/a |
| R7 | run | `==`/`!=` on JSON numbers >17 significant digits: Python compares IEEE doubles, `jsonb` compares `numeric` | none | **no** | **no** |
| S1 | source | `source.type == "query"` | **whole source falls back** — nothing to push into (§2.9) | yes, statically | **no** |
| S2 | source | `source.type == "verb"` | falls back — compilable in principle, but `load_verb_group_log` bypasses `core.storage`, so no seam to attach a predicate to | yes, statically | **no** |
| S3 | source | `sort.field` names a **derived** column | pushable only if its `derive` was pushed too | yes, statically (`sort.field` vs `derive` keys) | **no** |

**R6 is real and reachable**, and it is the one `KNOWN_DIVERGENCE` the fixture structurally cannot test (`compile.py:143-144`:
every fixture case injects `context.now`). Measured live in one transaction 1.2 s apart (`analysis/coverage.md` §6.2), SQL
`now()` returned `2026-08-19 18:02:20` for both probes while Python returned `18:02:20` then `18:02:22`: a pushdown query is
one statement in one transaction so every row shares one clock, where the in-memory path re-reads it per row and a 20 000-row
scan will routinely straddle a second. The direction is arguably *better* — one consistent clock per result set — but it is
still a silent behavioural change, and it vanishes if `context.now` is always injected. **R3 and R4 are the ones that matter
against FRAMING §5**: neither turns a `null` into a number (the disqualifying direction), but both **silently produce a wrong
value**, and R3 turns a value into a `null`, the same defect mirrored. **S3 is not hypothetical** — it is exactly what the
only real dashboard on this machine does (§2.9).

### 2.8 The go-bar answer — is a fallback detectable and reported at query time?

FRAMING §4 makes this the GO bar and §5 the non-negotiable. Answered by tracing the mechanism.

**What `resolve()` does today** — `api/dashboard/sources.py:330-357`, the load-bearing lines:

```python
loader = _LOADERS.get(stype)                                  # :340  noun | verb | query
raw = loader(project_path, source)                            # :347  ALWAYS in-memory today
truncated = len(raw) > MAX_SCAN                               # :348
if truncated: log.warning("dashboard source hit MAX_SCAN cap", {...})  # :350
rows = _apply_derive(...); rows = _filter_rows(...)           # :353-354
rows = _apply_sort(...);   rows = _apply_limit(...)           # :355-356
return {"records": rows, "count": len(rows), "truncated": truncated}   # :357
```

There is **exactly one evaluation path**: `_apply_derive` (`:133-148`) and `_filter_rows` (`:151-165`) call `evaluate(ast,
row, context)` per row unconditionally. Nothing in this module knows what a compiled query is — so today there is nothing to
fall back *from*, and "is the fallback reported?" is a question about code that does not exist yet. It must be answered as a
**requirement on the design**, not as an observation of current behaviour.

Pushdown must replace the loader call at `:347`, not post-process its output — the whole point is to avoid materialising up to
`MAX_SCAN = 20 000` rows (`:61`, whose own comment already reads "(Pushdown filtering removes this.)"). So the compile attempt
sits between `:345` and `:347`:

| detection point | signal | rules |
|---|---|---|
| before `:347`, on the source spec | `stype != "noun"`; `sort.field ∈ derive` | S1, S2, S3 |
| before `:347`, `compile_ast()` on each `derive` expression and on `where` | `Uncompilable` — **plus `RecursionError` and `MemoryError`**, which the contract does not name | C1, C2, **C3, C4** |
| at execution, around the `SELECT` | `psycopg2.Error`, notably SQLSTATE `22003` | R1 |
| **nowhere** | — | **R2, R3, R4, R5, R7** |

That last row is the important one: R2–R5 and R7 are silent *by construction*. The SQL runs successfully and returns a value
that simply differs from what Python would have produced — no exception, no flag, no signal. **They cannot be detected at
query time by any mechanism, because from the database's point of view nothing went wrong.**

Three candidate reporting channels exist and none is adequate. (1) **The return contract**: `resolve()` returns exactly
`{"records","count","truncated"}` (`:357`) — **no field for how the result was computed**, no `pushed_down`, no
`fallback_reason`, so a caller cannot distinguish an in-database result from an in-memory one. (2) **`truncated`**: the only
existing completeness signal, meaning something else — the raw scan hit `MAX_SCAN`; the docstring says it is surfaced "so the
UI can warn" (`:58-60`), the *precedent* for reporting a degradation, but overloading it would conflate two unrelated
conditions. (3) **`log.warning` at `:350`**: server-side only; a tenant sees nothing. The one loud path — `_compile`'s
`AppError("DASHBOARD_EXPR_INVALID", status=400)` at `:121-131` — fires only on `ExprError`, a **syntax** error; 400 is the
wrong response for "this valid expression cannot be pushed down", where the correct behaviour is to compute it in memory and
*say so*.

> **Verdict for the `sp_decide` gate: nothing currently would report a fallback.**
>
> Detection points for the compile-time and source-level rules (C1, C2, S1, S2, S3) exist and are cheap. The **reporting
> channel does not exist in the return contract at all.** Two compile-time conditions (C3, C4) are not even detectable through
> the documented `Uncompilable` signal. Five run-time divergences (R2, R3, R4, R5, R7) are **undetectable in principle** under
> this design. Against the bar as written — "every non-compiling construct has a named fallback, and the fallback is
> detectable and reported at query time, never silent" — the first clause is **vacuously satisfied** (no construct fails), the
> second is **not met today**, and the third is **not achievable for R2–R5/R7 by detection alone**; those must be fixed at the
> source or accepted as known divergences under pinned deployment conditions. This seat supplies the evidence; the verdict is
> The owner's.

**What closing the gap would take — named, not built** (stop rules apply; nothing was implemented, `compile.py` and
`runtime.sql` untouched): add **`pushed_down: bool` and `fallback: [{"scope","reason"}]` to `resolve()`'s returned dict** —
the missing reporting channel, which everything else depends on; **C3** — convert the AST recursion to an explicit stack, or
raise `Uncompilable` past a depth budget checked *before* recursing; **C4** — bind `date_add`'s first argument through a
CTE/`LATERAL` so it is emitted once, and accumulate the `MAX_SQL_CHARS` check during construction instead of after it
(`compile.py:171-176`); **C3/C4 belt-and-braces** — have the adapter catch `RecursionError` and `MemoryError` alongside
`Uncompilable` and treat them as fallback, so the contract holds even if the root causes are not fixed; **R1** — catch
SQLSTATE `22003` and re-run in memory (transaction already aborted: full retry); **R3** — fix the `xpr.f8` range-guard literal
to 309 digits (one line in `runtime.sql`); **R5** — pin `extra_float_digits` on every pushdown session.

### 2.9 The `query` source — confirmed non-pushdown, and bounded

FRAMING §3's stop rule is explicit: **bound and confirm, do not attempt to make it push down.** Nothing here attempts to.
`recon/query-source.md` §1-§3 establishes the mechanism; re-reading `api/dashboard/sources.py:237-317` and
`core/deep_search.py:381` confirms every claim. `cascade_deep_search` is a **pure function** — "This function does NO I/O…
Inputs must already be loaded into memory" (`core/deep_search.py:389-390`); `_query_records` loads **every noun instance of
every noun type** (`sources.py:256-267`, no limit) and **every run of every verb group** (`sources.py:269-293`, no limit) into
Python lists before calling it (`sources.py:301-308`); its three inputs are *heterogeneous* (schema definitions for all four
word types, noun instances, verb runs — schema definitions have no data-row shape at all); and matching is a **scored cascade
with early exit** (`core/deep_search.py:154-341`) with per-row dynamic resolution of the primary id key.

**The blocker is architectural, not expressive.** Pushing `derive`/`where`/`sort`/`limit` into Postgres means compiling them
into the *same statement* that acquires the rows. `query`'s row-acquisition is not a statement — there is no `SELECT` upstream
of the cascade to extend. Materialising the cascade's output into a scratch table and querying that is today's in-memory
behaviour plus a round trip, not a pushdown, and is out of scope by the stop rule.

**The bound, structurally certain from the code.** `RECORD_SOURCE_TYPES = ("noun","verb","query")` (`sources.py:53-56`) →
`query` is **1 of 3 record source types**. But the dashboard surface is larger than the resolver: the module docstring
(`sources.py:1-14`) states there are **five** DataSource types — the three record sources handled here plus **two table/file
sources, the CSV data-dump and the artifacts tree, "served by their own dedicated endpoints … not through this resolver"**,
which never run `expr` at all and so are outside T-1 entirely (nothing to push down, nothing lost). So the honest structural
fraction is **1 of 3 sources that reach the expression pipeline, and 1 of 5 DataSource types on the dashboard surface**.
Within those 3 it is *not* "2 of 3 work": per `recon/query-source.md` §6 only **`noun`** has both a plausible SQL shape *and*
an existing `RecordStore` seam; **`verb`** is compilable in principle but `load_verb_group_log` bypasses `core.storage`
entirely, so it has no attachment point today. **The realistic near-term denominator is 1 of 3 — `noun` is the only source
pushable without new integration work.**

**What is lost if `query` never pushes down:** nothing against today's behaviour — `query` is fully in-memory now, so this is
a non-improvement, not a regression — and `derive`/`where`/`sort`/`limit` keep working for `query` widgets unchanged, since
those four functions take no source-type argument (`sources.py:353-356`). **The real cost is that `MAX_SCAN` does not protect
`query`:** the cap is applied at `sources.py:348` to the *loader's output* (the post-cascade match list), not to the candidate
pool the cascade scans, and the `noun_instances`/`verb_runs` loops (`sources.py:256-293`) are unbounded
(`recon/query-source.md` §8). A project with more than 20 000 total instances-plus-runs pays the full O(rows × fields)
string-comparison scan on **every** `query` widget resolution, with the cap truncating only the results, after the expensive
work is done. Pushdown was never going to fix that — it is a pre-existing loader exposure — but it means "`query` stays as it
is" is a worse status quo than the constant suggests.

**What could NOT be established about this bound**, stated so nobody quotes a number that does not exist: **the usage
distribution.** Dashboards are tenant data, persisted per project in a `dashboards` table
(`api/routers/dashboards/store.py:35`, `layout_json` column), not in either GIMS tree — no default catalog, no seeded fixture,
no telemetry in the repo. **"1 of 3 source types" is emphatically not "1/3 of usage", and this spike cannot compute the real
ratio**; anyone quoting a usage fraction at the gate would be inventing it. The one empirical data point is **n = 1 and is
labelled as such**: a read-only sweep of every SQLite database in the `gims-ledger` tree found exactly one dashboard (row id
`143c987947874e36b728bb66f5a9125c`, in two `LIMS-System` backups) with three widgets — two `csv` (never reach `resolve()`) and
one `noun`; `query` usage **zero**, `verb` usage **zero**, consistent with `query` not being the common case and bounding
**nothing** statistically. That one `noun` widget — `derive: {days_left: "round(days_between(today(), $.due_date), 1)"}`,
`where: "$.status == \"in progress\""`, `sort: {field: "days_left", dir: "asc"}` — was compiled and run against live Postgres
over six representative `Submission` records including a missing `due_date`, an unparseable `"not a date"`, an explicit JSON
`null` and a full timestamp: **12 checks, 12 agree, 0 diverge** (`analysis/coverage.md` §8.3). It also instantiates fallback
rule S3 — its `sort.field` is a *derived* column.

### 2.10 Cross-check — raw data against the prose document

Re-derived by this seat from `proto/coverage_probe_results.json`, `proto/compile.py`, `expr.py` and
`tests/fixtures/expr_vectors.json`. **Confirmed exactly:** the 48-construct census (12 tags, 22 functions, dispatch equal both
ways); `<=` and bare `$` at 0 occurrences in the 130 cases; the per-construct case counts of `analysis/coverage.md` §3, cell
for cell; the fixture-side matrices `_eq` 7/36, `_order_cmp` 4/36, `_truthy` 5/6, `_to_num` 4/6, `_to_str` 4/6,
`_parse_date_ms` 1/6, cell for cell; 403 probes with 403 `COMPILED_AGREES` and zero of every other outcome; the per-group
probe counts; and 36/36 operand-kind cells for each of the six comparison operators. **Where the raw data and the prose
differ:**

| prose claim (`analysis/coverage.md`) | raw-data check | verdict |
|---|---|---|
| "`date_add` **quadruples** the generated SQL per level" (§2.2) | measured ratio is **2.00× per level** (168 → 36 744 → 147 337 → 294 795); the document's own figures are consistent with doubling — only the word is wrong | **prose disagrees with its own data**; §2.6 states 2× |
| `Uncompilable` "is raised from seven places" (§2.1) | `grep -c 'raise Uncompilable' compile.py` = **8**; the omitted site is `compile.py:301`, the only construct-keyed refusal, provably dead | **undercount by one**; strengthens §2.2 rather than weakening it |
| `1+1+…` first failure "n = 332, 665 chars, evaluates to 332.0" | 665 chars is **333 operands**, evaluating to `333.0`; 332 operands is 663 chars and **compiles**. The document counts operators where §2.6 counts operands | **off by one in one cell**; the 665-char headline is correct |
| first `Uncompilable` for nested `date_add` at depth 12 | **depth 11** (294 795 chars); depth 10 still compiles at 147 337 | refinement — §2.6 uses the measured boundary |
| `_parse_date_ms` closed to 6/6 by probes | all **12** date probes return Python `None` / SQL `NULL`, `string` kind included (`"5"` is not a date) | **true but weaker than it reads** — reject path only (§2.5) |
| — (not stated in the prose) | 196 of 403 agreements are `None`/`SQL NULL` on both sides; **0** in either null-mismatch direction | added here, §2.4 |

None of these moves the verdict: the construct census, the 403/403 result, the coverage closure and the "nothing would report
a fallback" conclusion all stand as written.

**Compliance.** Read-only throughout. Both GIMS trees, `spikes/T-1/recon/`, `proto/`, `analysis/`, `FRAMING.md`, `.autodev/`
and `kb/` were read and not written; the only file this seat created is `spikes/T-1/.parts/f2.md`. Re-measurement scripts ran
in the session scratchpad against read-only imports; `compile.py` and `runtime.sql` were not touched, so C3, C4 and R3 are
**recorded, not fixed**, per the `sp-investigate` stop rules.

**Compliance, consistency pass [consistency].** The single §2.4 edit above is the only change made to this file after it was
first written; this paragraph is written by that later, consistency-repair seat. The edit is document-accuracy work only:
nothing was fixed, no database was contacted, no DDL was issued, and no file other than `spikes/T-1/.parts/f2.md` was
written. The figures in the §2.4 footnote were re-derived read-only from `proto/coverage_probe_results.json` in the session scratchpad; `xa` A.2/A.3/A.6
were read, not edited.

---

## Finding 3 — Index shape

**Question (FRAMING §4 #3, restated in FRAMING §2):** what does the generated SQL actually look
like over JSONB arbitrary-key records, what index does it need, and does
`migrations/pg/0002_instances_data_gin.sql`'s `GIN (data jsonb_path_ops)` serve it — including
the honest answer if that index is the wrong shape.

**Answer.** No — and the index is not the reason. Across **36 measured plans** (9 compiled
predicates × 4 index configurations) the production index's name appeared **0 times**, as did every
other non-PK index; `enable_seqscan = off` changed **0 of 36**. The blocker is upstream of any
index: `compile.py` emits **no indexable operator at any level**, and the `to_jsonb()` it wraps
round every subexpression is `STABLE`, so PostgreSQL **refuses to create any index whose expression
or predicate contains a compiled WHERE predicate** (W1–W9) **or the compiled `derive` column** (D1).
That absolute stops there: the compiled *sort key* S1 carries no wrapper and is both indexable and
measured index-backed (§3.6 H4), and the bare compiled operand indexes fine (§3.3 T4a) — it is the
`to_jsonb` wrapper, not "compiled output", that is refused. Four compiler changes must land before
the right index is reachable (§3.4). Four measured correctness hazards are in §3.6 — two where an index
changes a read answer, one where the index-friendly rewrite does, one where the index rejects a
legal write — FRAMING §5's failure mode relocated into the storage layer. **The one route that needs no per-key DDL (jsonpath, §3.5) is not a safe route:**
measured this pass, its index acceleration covers `==` only, it is lost the moment the predicate is
written in the form correctness requires outside a top-level `WHERE` conjunct, and it contains a
**measured silent divergence inside the fixture** (case 33). Routable — index-accelerated **and**
every fixture record of the shape measured to agree with `expr`: **2 of 130 fixture cases (1.5%)**,
**one distinct expression shape** (§3.5(c), §3.9 rule 1). *(Counted per case rather than per shape,
3 of 130 (2.3%) are index-accelerated and individually agree; the third is case 34, whose shape
`$.x == null` is the shape that silently diverges at case 33, and a shape cannot be routed when one
of its records is silently wrong. 1.5% is the operative figure for a gate reader; 2.3% is its
per-case upper bound.)* **[consistency]**

**Revised at closure.** All 13 verification corrections for this finding were checked against the
raw sources they name and applied (`.parts/verifications.json`, "Finding 3 — Index shape"); the two
**load-bearing** ones both hit §3.5 and are re-derived independently below (§3.5). Critic gap 10 is
closed by two measurements run this pass: `idxshape_jsonpath.sql` J5's four unreported counts, and
all 130 fixture cases through the strict-jsonpath form (§3.5). New at closure: §3.9, the emission
rule these measurements support, carrying FRAMING §5's storage-layer clause.

Deep document: `analysis/index-shape.md` (1280 lines) — bare `§n` below cite **its** sections;
references to this finding's own subsections are written `§3.1`–`§3.9` and always name a heading
that exists here. Raw data: `proto/idxshape_plans.json`, `proto/idxshape_preds.json`,
independently re-parsed (§3.7).

### 3.1 What the compiled SQL actually looks like

Every widget predicate becomes one statement of this shape (`index-shape.md §2`):

```sql
SELECT data FROM instances WHERE collection = %(coll)s AND xpr.truthy( <compiled expression> )
```

**The atom.** Every field read — `$.status`, `$.score`, `$.due_date`, `$.actor` — compiles to
exactly one construct and to nothing else (§2.1; present in **11 of 11** compiled predicates,
verified by re-extraction from `proto/idxshape_preds.json`):

```sql
nullif((data -> (%(p0)s)::text), 'null'::jsonb)
```

Three properties of that atom decide the whole index question: `->` not `->>`, so the result stays
`jsonb`, never a scalar an operator class can order; the **JSON key is a bind parameter**, not a
literal, because it comes from tenant expression text; and `nullif(…, 'null'::jsonb)` collapses
JSON-null and absent-key to SQL NULL — faithful to `expr.py:562-575`, but a second function layer
above `->`.

**One compiled predicate verbatim**, so the shape is not taken on trust — `W2 = $.score > 90`,
exactly as `compile_ast()` returned it (`proto/idxshape_preds.json` `W2.sql`; §2.2):

```sql
to_jsonb(xpr.ord((%(p2)s)::text, nullif((data -> (%(p0)s)::text), 'null'::jsonb), to_jsonb((%(p1)s)::float8)))
-- params {'p0': 'score', 'p1': 90.0, 'p2': '>'}
```

**`>` reaches the planner, but never in a position it can index.** In the emitted text `>` is a
*string bind parameter* passed to `xpr.ord(op text, a jsonb, b jsonb) RETURNS boolean`
(`proto/runtime.sql:160-161`) — but `xpr.ord` and `xpr.f8` are `LANGUAGE sql IMMUTABLE` and the
planner **inlines** them, so a native `double precision` `>` does appear inside the filter:
config B's W2 plan reads `… END > CASE WHEN (to_jsonb('90'::double precision) IS NULL) …`
(`idxshape_plans.json` `B_gin_jsonb_path_ops.queries.W2.plan_analyze`; `index-shape.md §4.2` records
the inlining). **Correction applied** — the earlier draft said "the planner never sees a comparison",
which the raw plan text falsifies. What the planner never sees is an indexable operator **at the
root of the clause with an indexed expression as its left operand**, which is exactly what T4a
measures (§3.3). `xpr.truthy` is likewise inlined for W1 and W6 — their filters begin
`Filter: CASE WHEN (to_jsonb(…) IS NULL) THEN false …` — and survives as the clause root for
W2–W5, W7–W9. **And the predicate that matters most here** — `W6 = $.actor == "goms"`, the ledger's
own `_INDEXABLE_FIELDS` filter written as `expr` (`idxshape_preds.json` `W6.sql`):

```sql
to_jsonb(nullif((data -> (%(p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(p1)s)::text))
-- params {'p0': 'actor', 'p1': 'goms'}
```

`PgRecordStore.list_records_where` emits, for the **identical filter**, `... AND data @> %s` with
`Jsonb({"actor": "goms"})` (`gims-ledger/api/storage_aws.py:1029-1039`; `recon/storage.md §3`).
Same intent, structurally unrelated SQL. That one line is why the existing index cannot be reused.

**The shape as a class** (§2.3): across the **9 compiled `where` predicates** there are exactly four
root node types — `xpr.ord(text,jsonb,jsonb)` (W2/W3/W4), `xpr.contains(jsonb,jsonb)` (W8),
`<jsonb> IS NOT DISTINCT FROM <jsonb>` (W1/W6/W7), `xpr.truthy(bool AND/OR bool)` (W5/W9) — each
then wrapped in `xpr.truthy(…)` to become the WHERE clause. **Correction applied:** that census
covers 9 of the 11 compiled outputs, not 11. The other two are the `derive` column **D1**, whose
root is a `float8` division `(xpr.pdate_ms(...) - xpr.pdate_ms(...)) / 86400000.0` inside `to_jsonb`,
and the sort key **S1**, whose root is a bare `nullif(...)` with no wrapper at all
(`idxshape_preds.json` `D1.sql`/`S1.sql`; `proto/idxshape_explain.py:88` `continue`s on both, so
neither appears in the 36 plans). S1's different root is the whole reason §3.6 H4 exists.
**To the planner, every compiled WHERE predicate is one opaque boolean clause per row** — for seven
of the nine an `xpr.truthy(...)` call, for W1/W6 an inlined `CASE`. Neither form is an indexable
operator clause.

### 3.2 Does the existing GIN index serve dashboard pushdown? — 36 measured plans

Four configurations, each built from scratch (all non-PK indexes dropped, created, `VACUUM
ANALYZE`), then all nine compiled `where` predicates run under `EXPLAIN (ANALYZE, BUFFERS)` and
again under `EXPLAIN (COSTS OFF)` with `enable_seqscan = off` (§4; raw
`proto/idxshape_plans.json`):

| cfg | DDL | build | size |
| --- | --- | ---: | ---: |
| **A** | none — the `PRIMARY KEY (collection,key)` B-tree only | — | 9 288 kB (PK) |
| **B** | `USING GIN (data jsonb_path_ops)` — **the production index, `0002_instances_data_gin.sql:36-37`** | 2 341 ms | **50 MB** |
| **C** | `USING GIN (data jsonb_ops)` | 4 785 ms | **90 MB** |
| **D** | 4 B-tree expression indexes: `((data->>'score')::float8)`, `(data->>'status')`, `(data->>'actor')`, `(data->>'due_date')` | 84+95+107+83 = **369 ms** | **8.4 MB** |

Probe table `idxprobe`: DDL verbatim from `migrations/pg/0001_instances.sql:13-18`, **200 000 rows
/ 100 MB** — 150 000 `LedgerRecord` rows whose key frequencies were measured against the real
17 087-row ledger, plus 50 000 `Submission` rows shaped from `LIMS-System/noun_types.json`,
including a key with spaces and parentheses (§1.2). **Provenance caveat, folded in at closure:**
only `submission_id`, `status`, `received_date`, `comments`, `due_date`, `priority` come from that
noun type; `score`, `client`, `Sample Weight (g)`, `Analyte Type` and `vials` are invented by the
generator (`proto/idxshape_gen_rows.py:82-100`), and `score`'s 5% numeric-string rate — the premise
under H2/H3/H4 — is a modelling choice patterned on the real ledger storing `human_required` as the
string `"false"`, not a rate measured on real `Submission` data. The baseline is not a strawman
full-table scan: the PK's leading `collection` column already scopes every widget to one noun type.

**Per-predicate result — all four configurations produced the identical plan, so the config column
collapses.** `exec` = `Execution Time` from the `ANALYZE` run, min–max across the four configs.
`buffers` = **total shared buffers touched by the heap-scan node (hit + read)**, which is what is
config-invariant; the `hit`/`read` split is not (W1 config B reads `hit=3538 read=1550`, config C
`hit=64 read=5024 written=271` — both total 5 088). *(Correction applied: the earlier draft labelled
this column `Buffers: shared hit`.)*

| pred | expression | est (A/B/C/D) | act | removed by filter | buffers | exec ms (min–max) | index used |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| W1 | `$.status == "open"` | 25190/24883/24853/24937 | 9 985 | 40 015 | 5 088 | 134.4 – 146.6 | `idxprobe_pkey` |
| W2 | `$.score > 90` | 16793/16589/16569/16624 | 4 807 | 45 193 | 5 088 | 362.5 – 371.5 | `idxprobe_pkey` |
| W3 | `$.score * 2 > 180` | 16793/16589/16569/16624 | 5 040 | 44 960 | 5 088 | 1 149.2 – 1 198.7 | `idxprobe_pkey` |
| W4 | `days_between(today(), $.due_date) < 7` | 16793/16589/16569/16624 | 16 071 | 33 929 | 5 088–5 155 | 3 285.0 – 3 414.3 | `idxprobe_pkey` |
| W5 | `$.status == "done" or $.status == "blocked"` | 16793/16589/16569/16624 | 20 028 | 29 972 | 5 088 | 417.2 – 435.3 | `idxprobe_pkey` |
| W6 | `$.actor == "goms"` | 74810/75117/75147/75063 | 21 308 | 128 692 | 11 530 | 406.2 – 436.7 | `idxprobe_pkey` |
| W7 | `lower($.status) == "open"` | 16793/16589/16569/16624 | 9 985 | 40 015 | 5 088 | 285.3 – 295.1 | `idxprobe_pkey` |
| W8 | `contains($.summary, "hold")` | 49873/50078/50098/50042 | 21 423 | 128 577 | 11 530+ | 870.6 – 883.2 | `idxprobe_pkey` |
| W9 | `$.actor == "goms" and $.risk_level == "high"` | 49873/50078/50098/50042 | 1 967 | 148 033 | 11 530 | 969.4 – 992.4 | `idxprobe_pkey` |

**The measured answers to the questions the framing asked:**

- **Plan count: 36** (9 predicates × 4 configs), plus 36 re-plans under `enable_seqscan = off`.
  All 11 predicates compiled, 0 `Uncompilable` — nothing here is selection bias (§1.3).
- **Did the production index's name ever appear? No — 0 of 36.** Re-extracting every index
  reference from all 72 plan texts yields exactly one name, `idxprobe_pkey`.
  `idxprobe_data_gin_path`, `idxprobe_data_gin_default`, `idxprobe_score_f8`,
  `idxprobe_status_txt`, `idxprobe_actor_txt`, `idxprobe_due_txt`: **zero** plans each.
- **Did `enable_seqscan = off` change anything? No — 0 of 36.** Node chains 36/36 identical to the
  `ANALYZE` run. Load-bearing distinction: the planner is not *declining* an index on cost,
  **there is no index path to decline** (§4.3).
- **Cost of its presence: none beyond noise.** 50 MB, 90 MB or 8.4 MB of index changed no plan and
  no timing materially (largest per-predicate spread across configs: **9.0% on W1** — §3.7
  corrects the document's stated 3.9%).
- **A quieter cost** (§4.4): **no statistic is consulted for any of the nine.** The two predicates
  whose `xpr.truthy` the planner inlined get PostgreSQL's **0.5** fallback for the resulting
  CASE-rooted clause (W1 24883/49767, W6 75117/150235); the seven that keep `xpr.truthy(...)` at the
  root get the **0.3333** fallback for an opaque boolean clause (W2–W5, W7–W9, e.g. W7
  16589/49767 = 0.3333). *(Correction applied: the earlier draft attributed 0.5 to
  `IS NOT DISTINCT FROM` roots, which W7 — an `IS NOT DISTINCT FROM` root estimated at 0.3333 —
  falsifies. The mechanism is inlining, not the operator.)* Actual selectivities span **1.3%** (W9)
  to **40%** (W5); **W9 is over-estimated 25×**. Harmless for a single-table filter; real once
  `sort`/`limit` is pushed down or the source is joined.

#### The fair control — the same index, doing the job it was built for

"It doesn't help" is only honest if the index is shown working. Same table, same session
(§5, `proto/idxshape_jsonpath.sql` J0):

```
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT data FROM idxprobe WHERE collection='LedgerRecord' AND data @> '{"actor":"goms"}'::jsonb;

 Bitmap Heap Scan on idxprobe (actual time=2.203..26.108 rows=21308 loops=1)
   Recheck Cond: (data @> '{"actor": "goms"}'::jsonb)
   ->  Bitmap Index Scan on idxprobe_data_gin_path (actual time=1.338..1.338 rows=21308 loops=1)
         Index Cond: (data @> '{"actor": "goms"}'::jsonb)
         Buffers: shared hit=9
 Execution Time: 26.701 ms
```

That is `list_records_where`'s exact SQL shape (`api/storage_aws.py:1032-1036`): 21 308 of 200 000
rows in **1.3 ms of index scan reading 9 index buffers**, 26.7 ms total. **The same filter through
the compiler** — W6, identical 21 308-row result — is a PK bitmap scan with the GIN untouched at
**419.1 ms: 15.7× slower**, purely because the compiler emits `IS NOT DISTINCT FROM` over
`to_jsonb(...)` instead of `@>`.

Verdict: **"wrong shape for this", not "bad index"**. `idx_instances_data_gin` is correctly chosen
for containment over a fixed 11-field whitelist (`_INDEXABLE_FIELDS`, `core/storage/sql.py:252-262`,
11 fields, count confirmed; per `recon/storage.md §3`), is measured doing that job, and costs
dashboard pushdown nothing. It simply has no strategy for what pushdown asks.

### 3.3 Why nothing matched — three catalog-level causes, isolated from each other

**Cause 1 — no comparison operator exists in either jsonb GIN operator class.** Catalog fact from
`pg_opclass`/`pg_amop`, re-derived this session (`index-shape.md §3.1`, `idxshape_exprindex.sql` T1):
`jsonb_path_ops` carries **three** operators — `@>(jsonb,jsonb)`, `@?(jsonb,jsonpath)`,
`@@(jsonb,jsonpath)`; `jsonb_ops` carries those three plus `?(jsonb,text)`, `?|(jsonb,text[])`,
`?&(jsonb,text[])` — **six**. Neither family contains `<`, `<=`, `>`, `>=`, or anything meaning
"the number at path X compares to a literal". Not the planner declining a strategy — **the
strategy does not exist** in PostgreSQL 16. Consequence: **switching operator class cannot help**,
and configuration C measured exactly that (0 of 9 plans changed, §3.2).

> **Reconciled at closure — a cross-document contradiction a gate reader would otherwise hit.**
> `recon/storage.md §2` prints **eleven** operators for `jsonb_ops`, including `=`, `<`, `>`, `<=`,
> `>=`; this section says six. Both are right about different objects: the recon's `pg_amop` query
> omitted `am.amname='gin'` and merged in the **btree** opclass, a separate opfamily that is also
> named `jsonb_ops`. Re-derived live this pass on the container:
> `btree/jsonb_ops = 5 · gin/jsonb_ops = 6 · gin/jsonb_path_ops = 3 · hash/jsonb_ops = 1`.
> Six is the correct number for the question asked here (which GIN strategies exist); the btree
> family's `<`/`>` order whole `jsonb` values and are the same ordering §3.6 H4 shows disagrees
> with `_sort_key`.

**Cause 2 — `to_jsonb()` is `STABLE`, not `IMMUTABLE`, and `compile.py` emits it everywhere.**
Catalog fact (`index-shape.md §3.2`, `idxshape_hazard.sql` H1): `to_jsonb(anyelement) | STABLE`, vs
`jsonb_typeof(jsonb) | IMMUTABLE`, `lower(text) | IMMUTABLE`, `upper(text) | IMMUTABLE`.
`compile.py`'s representation contract — *"Every compiled subexpression has SQL type `jsonb`"*
(`proto/compile.py:15-17`) — is implemented with `to_jsonb(...)`, which appears in **10 of the 11**
compiled predicates (verified by re-extraction from `proto/idxshape_preds.json`; between 2 and 5
occurrences each — the sole exception is `S1`, the bare sort key, and §3.6 H4 shows that exception
is the one place an index is reachable today). PostgreSQL refuses the DDL outright — exact errors
(§6.1, `proto/idxshape_exprindex.sql` T5/T6):

```
CREATE INDEX ... ON idxprobe ((xpr.truthy(to_jsonb(xpr.ord(...)))));
ERROR:  functions in index expression must be marked IMMUTABLE

CREATE INDEX ... ON idxprobe (collection, key) WHERE xpr.truthy(to_jsonb(xpr.ord(...)));
ERROR:  functions in index predicate must be marked IMMUTABLE
```

> **No compiled dashboard predicate, exactly as `compile.py` emits it, can appear in any index
> expression or any index predicate — regardless of how good the `xpr` runtime is.**

That statement is scoped to *predicates* and stays scoped: re-derived live this pass in a
rolled-back transaction, `CREATE INDEX v_operand ON idxprobe ((nullif((data -> 'score'::text),
'null'::jsonb)))` and `CREATE INDEX v_t7d ON idxprobe ((xpr.pdate_ms(nullif((data -> 'due_date'),
'null'::jsonb))))` **both succeed** — compiled output can be indexed once the `to_jsonb` wrapper and
the clock term are gone.

**Cause 3 — `xpr.now_ms` is `STABLE`, so any expression containing `today()`/`now()` is
permanently unindexable.** `proto/runtime.sql:345-346` declares it `LANGUAGE sql STABLE` —
correctly, since it falls back to `now()` when `ctx.now` is absent. Measured (§6.3, T7):

| test | DDL attempted | result |
| --- | --- | --- |
| T7b | `((xpr.now_ms('{}'::jsonb)))` | `ERROR: functions in index expression must be marked IMMUTABLE` |
| T7c | the compiled **D1** derive column (`days_left`) in full | `ERROR: functions in index expression must be marked IMMUTABLE` |
| T7d | `((xpr.pdate_ms(nullif(data -> 'due_date', 'null'::jsonb))))` — D1 with the clock term removed | **created** |

This bites the single most common dashboard predicate there is: `sources.py:23`'s own docstring
example is `{"days_left": "days_between(today(), $.due_date)"}`.

**Most consequential: cause 2.** Causes 1 and 3 bound *which* predicates an index could serve;
cause 2 forbids *building the index at all*, so it gates the other two. FRAMING §2 anticipated
cause 1's conclusion by the wrong mechanism — it named key-existence (`?`/`?|`/`?&`) as the gap.
That is a red herring: `expr` has **no key-existence operator** (`$.missing` → null; `not $.x` on
`{}` is `truthy(null)` = `False`); `jsonb_ops` supplies `?` at **0.585 ms** but costs 90 MB vs
50 MB and 3.52× vs 1.94× write amplification, and changed **zero** of the nine plans (§5; §3.2
config C). The framing did **not** anticipate cause 2 — and cause 2 decides the finding.

#### Blame: the emitted SQL, or the runtime? — the isolating experiment

Same expression, with and without the wrapper (§6.1, `proto/idxshape_hazard.sql` H2):

| test | index expression | result |
| --- | --- | --- |
| H2a | `((xpr.ord('>'::text, nullif(data->'score','null'::jsonb), '90'::jsonb)))` | **index CREATED** |
| H2b | `((to_jsonb(xpr.ord(...))))` — exactly as `compile.py` emits it | `ERROR: ... must be marked IMMUTABLE` |
| H2c | `((xpr.truthy(to_jsonb(xpr.ord(...)))))` — the full WHERE clause | `ERROR: ... must be marked IMMUTABLE` |

and the H2a index **is used** when the predicate is written without the wrapper (H2d,
`enable_seqscan=off`): `BitmapAnd` → `Bitmap Index Scan on h2a` + `… on idxprobe_pkey`.

**So the `xpr` runtime is not the obstacle — `compile.py`'s "everything is jsonb" representation
contract is.** A fixable prototype decision, not a law of Postgres, but load-bearing: no index work
is possible until it changes.

A second isolating result rules out the easy fix: an index on the **character-exact compiled
operand**, `((nullif((data -> 'score'::text), 'null'::jsonb)))`, is created successfully and is
still **not used** for compiled W2, even with `enable_seqscan = off` (§6.2, T4a). An expression
index is reachable only through an *indexable operator clause* whose left side is the indexed
expression; `xpr.truthy(to_jsonb(CASE ...))` has no such operator at its root. The index exists,
holds exactly the right values, and is unreachable.

### 3.4 The index autoSQL actually requires — DDL, prerequisites, cost

`0002_instances_data_gin.sql` needs no change on this finding's evidence — it is not autoSQL's
index, it serves `list_records_where` at 1.3 ms index scan, and it costs pushdown nothing (§8.1).
**The shape pushdown needs is per `(collection, key, extractor)` B-tree** (§8.2):

```sql
CREATE INDEX idx_instances_num_score    ON instances (collection, (xpr_safe_num(data -> 'score')));
CREATE INDEX idx_instances_txt_status   ON instances (collection, (xpr_safe_str(data -> 'status')));
CREATE INDEX idx_instances_ms_due_date  ON instances (collection, (xpr_pdate_ms(data -> 'due_date')));
```

Four properties, each earned by a measurement: **`collection` leads** (§3.6 H4 measured a 429×
swing on exactly this); **the extractor is total** — NULL-on-failure, never a bare `::float8`
(§3.6 H3); **the extractor must be genuinely `IMMUTABLE`, not merely declared so** (§3.6 H1 —
`xpr.ecma_num` fails that audit today and must not appear in an index); **the compiler must emit
the indexed expression verbatim**, which today it does not.

**Four compiler changes must land before any of that DDL is reachable** (§8.3) — the DDL is inert
without them:

1. **Drop the `to_jsonb` wrapper from indexable leaf positions** — while it wraps every
   subexpression, no index containing a compiled *predicate* can be *created* (cause 2).
2. **Emit a real operator at the root of a comparison** — `xpr.ord('>', a, b)` → `xpr_safe_num(a)
   > <bound>`, or no B-tree strategy can ever match (cause 2's corollary, T4a).
3. **Constant-fold the context clock** out of `today()`/`now()` (cause 3; T7d shows the remainder
   is then indexable).
4. **Emit the JSON key as a literal, not a bind parameter,** wherever it must match an index.

**Measured cost** on the 200 000-row / 100 MB probe table (§9.1–9.2,
`proto/idxshape_writecost.py`; one `COPY` of 20 000 rows per config, no client round-trip in the
number):

| configuration | index MB | COPY 20k | µs/row | vs no index |
| --- | ---: | ---: | ---: | ---: |
| none (PK only) | 0.0 | 225 ms | 11.2 | 1.00× |
| `GIN (data jsonb_path_ops)`, default `fastupdate=on` | 58.0 | 436 ms | 21.8 | **1.94×** |
| `GIN (data jsonb_path_ops) WITH (fastupdate=off)` | 62.6 | 1 189 ms | 59.4 | **5.29×** |
| `GIN (data jsonb_ops)` | 93.7 | 792 ms | 39.6 | **3.52×** |
| 1 B-tree expression index | 6.5 | 266 ms | 13.3 | 1.18× |
| 4 B-tree expression indexes | 13.3 | 302 ms | 15.1 | 1.34× |
| 12 B-tree expression indexes | 31.7 | 402 ms | 20.1 | **1.79×** |

> **CORRECTION — that table's B-tree rows are a lower bound, not the dashboard workload's cost,
> and the direction of the bias favours the shape this section recommends.**
> `proto/idxshape_writecost.py:23` COPYs `lines[:20000]` of the generator output, and
> `proto/idxshape_gen_rows.py:115-118` emits all 150 000 `LedgerRecord` rows **before** any
> `Submission` row. Re-derived this pass by regenerating the deterministic TSV (`random.Random(
> 20260819)`) and counting key presence over those first 20 000 lines: **20 000 / 20 000 are
> `LedgerRecord`**, and of the twelve indexed keys only `actor` and `kind` are present on any row —
> `score`, `status`, `due_date`, `received_date`, `client`, `comments`, `submission_id`, `priority`,
> `Sample Weight (g)`, `Analyte Type` are **absent on 20 000/20 000**. The "1 B-tree" config indexes
> `((data->>'score')::float8)`, which is NULL for **every** copied row; 3 of the 4 in the "4 B-tree"
> config are all-NULL. NULL btree entries are far cheaper to insert than real keys, and the GIN rows
> pay full cost on the same input, so the GIN-vs-B-tree comparison is apples-to-oranges.
> The verifier re-ran the COPY both ways in rolled-back transactions
> (`.parts/verifications.json`, Finding 3, correction 3 — **not re-run by this seat**, the
> structural cause above **was**): LedgerRecord rows 8.0 → 10.9 → 13.7 → **22.5** µs/row at
> 0/1/4/12 indexes; `Submission` rows 8.3 → 10.7 → 15.0 → **39.7** µs/row, i.e. marginal per-index
> cost **rises** at 12 (2.4 → 1.68 → 2.62) and total amplification at 12 indexes is **4.8×**, not
> 2.8×. **The "cheap, and improving with count" property does not survive on rows that actually
> carry the indexed keys.** Everything below that leans on 0.74 µs/row is optimistic by ~2.2×.

Marginal cost per B-tree index against the 11.2 µs/row baseline **as measured on the all-NULL
input**: 2.10 → 0.98 → 0.74 µs/row and 6.50 → 3.33 → 2.64 MB at 1/4/12 indexes. Read the two GIN
rows together: `fastupdate=on` does not make GIN cheap to write, it **defers** the cost to the
pending-list flush, so the honest steady-state figure for the production index is nearer 5.29×
than 1.94×.

**The problem is not the cost of one index; it is how many you need.** Real declared fields in
`gims-ledger/projects/*/noun_types.json` (§9.3): LIMS-System has **36 noun types / 98 distinct
field names / 111 `(noun type, field)` pairs** (reproduced exactly this pass); the union across all
seven projects is **51 noun types and 152 distinct field names** — *correction applied:* the earlier
150 dropped `Sterility`, whose `fields` is a JSON **list** (`["sample_id","received_date",
"temperature","location","comments"]`, 5 fields) rather than an object, and re-parsing both forms
adds `temperature` and `location`. The error was in the conservative direction.

> **EXTRAPOLATION — labelled as such.** Applying the 12-index marginal rate (2.64 MB, 0.74 µs/row)
> to LIMS-System's 111 pairs, doubled for keys needing two extractors: **111–222 indexes, ≈290–580
> MB on a 100 MB table, ≈8×–15× write amplification.** **What was actually measured: 1, 4 and 12
> single-column B-tree expression indexes of the form `(data->>'key')` on one 200 000-row table,
> against a 20 000-row COPY in which 10 of the 12 indexed keys never appear.** Nothing above 12 was
> measured; the two-column `(collection, expr)` shape prescribed above was **not** the shape
> measured; the marginal rate was still falling at 12 *on that input* and rises at 12 on
> `Submission`-shaped rows, so the size figure is likelier to hold than the write figure, and the
> write figure is optimistic.

Still optimistic for a second reason: it covers only *declared* noun fields. `derive` columns are
arbitrary tenant-authored expressions (`sources.py:23`), absent from `noun_types.json`, with no
finite enumeration — and cause 3 shows the most common one cannot be indexed regardless.

### 3.5 The no-per-key-DDL route (jsonpath) — measured, and **not** safe to recommend

`jsonb_path_ops` carries `@?` and `@@` (cause 1), and PG16 extracts index conditions from *some*
jsonpath expressions. That is the only route found in this finding that serves **arbitrary keys with
no DDL per key**, so it got the closest adversarial reading — and it does not survive it. Two
**load-bearing** corrections from the verification (`.parts/verifications.json`, Finding 3), both
re-derived independently by this seat, are applied below; the section's earlier headline
("11.2× for equality on *any* key") is **withdrawn from the recommended form**.

**What was originally measured** (§10; the artifact labels were wrong and are corrected here —
`proto/idxshape_jsonpath.sql` J2 is the **lax** `@?` range test and J3 the **lax** `@@` equality
test; the file contains **no `strict` query at all**, so the strict plans below have no committed
script, and `proto/idxshape_jsonpath_agree.py:39` hardcodes `('strict ' || %s)`, so its lax column
requires editing that line out):

| predicate | plan | exec ms |
| --- | --- | ---: |
| `data @@ '$."status" == "open"'` (lax) | `BitmapAnd` → **`Bitmap Index Scan on idxprobe_data_gin_path`** + pkey | **7.640** |
| `data @@ 'strict $."status" == "open"'` | `BitmapAnd` → **`Bitmap Index Scan on idxprobe_data_gin_path`** + pkey | **12.504** (7 index buffers) |
| `data @? '$."score" ? (@ > 90)'` | pkey bitmap + `Filter` — **index not used** | 21.773 |
| compiled `$.status == "open"` (W1) | pkey bitmap + `xpr.truthy` filter | 139.9 |
| compiled `$.score > 90` (W2) | pkey bitmap + `xpr.truthy` filter | 371.3 |

**Measured on one key** (`$.status`, `Submission`, 9 985 of 50 000 rows) — *correction applied:*
"on any key" is an **INFERENCE** from `jsonb_path_ops` indexing whole key/value paths, not a
measurement; a second key was never tested.

#### (a) The index condition survives `==` only — and `IS TRUE` destroys it

**LOAD-BEARING CORRECTION 1, reproduced by this seat.** The 7.640 / 12.504 ms plans are the **bare**
`@@` form. Wrapping it in the `… IS TRUE` the earlier draft declared mandatory removes the GIN index
condition entirely. Re-measured this pass on the same 200 000-row `idxprobe`, with
`GIN (data jsonb_path_ops)` rebuilt inside a **rolled-back** transaction, all six statements in one
session (`EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)`):

| # | form | plan | exec ms |
| --- | --- | --- | ---: |
| A | `data @@ '$."status" == "open"'` (lax, bare) | `BitmapAnd` → **Bitmap Index Scan on the GIN** (7 index buffers) + pkey | **10.498** |
| B | `data @@ 'strict $."status" == "open"'` (bare) | `BitmapAnd` → **Bitmap Index Scan on the GIN** (7 index buffers) + pkey | **9.709** |
| C | `(data @@ 'strict …') IS TRUE` | `Gather` → **`Parallel Seq Scan`**, jsonpath demoted to `Filter` — **no index** | 29.800 |
| D | C again with `enable_seqscan = off` | `Bitmap Heap Scan on idxprobe_pkey` + `Filter`, `Rows Removed by Filter: 40015` | 21.685 |
| D2 | `(data @@ '$."status" == "open"') IS TRUE` (**lax**), `enable_seqscan = off` | identical to D — pkey bitmap + `Filter` | 21.850 |
| E | compiled W1, same session | pkey bitmap + inlined `CASE` filter | 177.344 |

All six return 9 985 rows. Three things follow, and D2 is the one the verification did not have:
**it is `IS TRUE` that removes the index condition, not `strict`** — the lax form loses it just the
same. Under `enable_seqscan = off` there is **no index path to decline** (the same distinction §3.2
makes load-bearing). And the prescribed form is still ~8.2× faster than the compiled predicate
(21.685 vs 177.344) — but as a **native C filter over a full collection scan**, with the 50 MB GIN
contributing exactly nothing. The bare form's advantage in this session is **18.3×** (9.709 vs
177.344); the earlier draft's 11.2× came from the strict plan against a contended compiled baseline
(12.504 vs 139.9 ms). **Both are bare-form numbers. Neither applies to the form §3.5(b) prescribes
outside a top-level conjunct.**

**Which operators earn an index condition at all** — closure measurement, same rolled-back GIN,
`enable_seqscan = off`, `EXPLAIN (COSTS OFF)`, bare strict `@@`, `collection='Submission'`:

| jsonpath predicate | result |
| --- | --- |
| `strict $."status" == "open"` | `BitmapAnd` → **Bitmap Index Scan on the GIN**, `Index Cond: (data @@ …)` |
| `strict $."score" == null` | **Bitmap Index Scan on the GIN**, `Index Cond: (data @@ …)` |
| `strict $."status" != "open"` | pkey bitmap + `Filter` — **no index path** |
| `strict $."score" < 90` | pkey bitmap + `Filter` — **no index path** |
| `strict $."score" >= 90` | pkey bitmap + `Filter` — **no index path** |

So the earlier point (a) — "ranges get no index condition", measured via `@?` at 21.8 vs 371.3 ms,
and unchanged by `jsonb_ops` (24.9 ms, still `Filter`) — is **narrower than stated**: in the `@@`
form too, **everything except `==` is a filter**, `!=` included. `@?`-with-filter and `@@`-with-
comparison both scan. The index-accelerated shape set is exactly `cmp(literal-path, literal)` with
`==`.

#### (b) `IS TRUE` is required exactly where the index is lost — the requirement, narrowed and justified

The earlier draft asserted `… IS TRUE` as an unqualified requirement (strict returns SQL NULL, not
false, on a structural error). Measured resolution, this pass:

- **At a top-level `WHERE` conjunct the wrapper is unnecessary**: SQL drops a row on NULL exactly as
  it drops it on false. Measured on the corpus — bare strict `9985` = strict `IS TRUE` `9985` = lax
  bare `9985`.
- **Anywhere the predicate's *value* is consumed it is mandatory, and then the index is gone.**
  Measured over all 200 000 rows: `WHERE NOT (data @@ 'strict $."status" == "open"')` keeps
  **40 015**; `WHERE NOT ((data @@ 'strict …') IS TRUE)` keeps **190 015**. The Python oracle keeps
  **190 015**: `expr.evaluate` on a record with no `status` gives `$.status == "open"` → `False`
  (not null — `_eq` is total, `expr.py:363-367`), so `not (…)` → `True` (re-run this pass through
  `GIMS-Project/.venv` + `core.dashboard.expr`). **The bare form under negation silently drops
  150 000 of 200 000 rows.**
- The expressible subset (point (c)) contains **no boolean composition and no negation**, so as long
  as the router matches only a *whole* `where` clause — which §3.9 rule 1 requires — the jsonpath
  form appears only as a top-level conjunct, where bare is safe. **Rule:** emit
  bare `@@` only as a top-level `WHERE` conjunct; the moment a rewrite would place it under `not`,
  inside an `or` branch, in a `derive` column or in a sort key, `IS TRUE` becomes mandatory and the
  measured acceleration is forfeited. **Not established:** whether any index-accelerated form of the
  value-position (`IS TRUE`) predicate exists — D/D2 say there is no index path to decline, which is
  evidence against, not proof. Establishing it would need a test of `@@` under an index-only or
  expression-index formulation, which this spike did not build.

**Lax vs strict, restated.** 11 adversarial records were run through the real `expr.evaluate()` and
through Postgres jsonpath side by side (`proto/idxshape_jsonpath_agree.py`): **lax 9/11, strict
11/11** — both reproduced by the verification (strict as committed; lax only after removing the
hardcoded `'strict '`). Both lax failures are array auto-unwrapping — `$.tags == "a"` on
`{"tags":["a","b"]}` and `$.arr > 1` on `{"arr":[0,5]}` are `True` in lax and `False` in `expr`,
which compares the list as one value. **On the fixture, that distinction is never exercised:** of
the 16 expressible cases below, lax and strict give the *same* row decision on **16/16** (§3.5(d)),
because no fixture case in the expressible subset has an array at the path.

#### (c) It expresses 12.3% of the fixture and routes 1.5% of it

Classifying every AST in `expr_vectors.json` (`proto/idxshape_fixture_subset.py`, **re-run and
reproduced exactly by this seat**): **114 (87.7%) OTHER · 10 (7.7%) `cmp(path, literal)` · 6 (4.6%)
bare path · 130 total.** No arithmetic, no `days_between`/`date_add`/`today`, no `coalesce`, no
`if`, no `concat`/`lower`/`upper`, no aggregates, no boolean composition of two keys.

The `@@` form can also be *written* for the 6 bare-path cases (`data @@ '$."a"'`), so **16 of 130
(12.3%)** are expressible; §3.5(d) measures what that costs. Denominator nuance, folded in at
closure: `expr_vectors.json` has 130 cases but only **113 distinct expressions**; the 10
`cmp(path, literal)` cases collapse to **6** distinct expressions (`$.n < 7`, `$.s == "FAIL"`,
`$.s != "FAIL"`, `$.x == null`, `$.n >= 10`, `$.n < "x"`), the 6 bare-path cases to **5**. By
distinct construct the route reads **11/113 = 9.7%**, not 12.3% — a reader taking "7.7% of the
language" as construct coverage was reading a per-case figure.

**The operator split of the 10 `cmp` cases is `<`×4, `==`×4, `!=`×1, `>=`×1.** Point (a) measured
that only `==` earns an index condition, so *index-accelerated* = **4/130 = 3.1%** — and of those 4,
one diverges (§3.5(d)). **Index-accelerated and measured to agree: 3/130 = 2.3%.** The two distinct
`==` shapes are `$.s == "FAIL"` (agrees on both its cases) and `$.x == null` (agrees on `{"x":0}`,
**diverges on `{}`**) — a shape cannot be routed if one of its records is silently wrong, so the
**routable, index-accelerated, agreeing fraction is 2/130 = 1.5% of cases, 1 of 113 distinct
expressions (0.9%)**. That is the honest replacement for the withdrawn headline.

#### (d) Conformance of the jsonpath route against the fixture — critic gap 10, closed

**(i) J5, the measurement that already existed and was never reported.** `proto/idxshape_jsonpath.sql`
J5 re-run read-only this pass against `autosql_spike` (four counts, no DDL):

| count | value |
| --- | ---: |
| `@? '$.score ? (@ > 90)'` | **4 807** |
| compiled `$.score > 90` (W2 form) | **4 807** |
| `@@ '$.status == "open"'` | **9 985** |
| compiled `$.status == "open"` (W1 form) | **9 985** |

Exact row-count agreement on 50 000 `Submission` rows. **Read it with its denominator:** every row
in that collection carries both keys — measured this pass, `Submission` rows lacking `score` = **0**,
lacking `status` = **0** (4 059 lack `due_date`, which no J5 predicate touches). J5's corpus
therefore cannot contain the one shape that diverges. **Corpus row-count agreement is not
conformance**, and treating it as such is exactly the failure mode FRAMING §8 warns about.

**(ii) All 130 fixture cases through the strict-jsonpath form.** The cheapest remaining check, built
only from instruments that already exist — `idxshape_fixture_subset.py`'s classifier plus
`idxshape_jsonpath_agree.py`'s comparison method (`expr.truthy(expr.evaluate(...))` vs
`record::jsonb @@ ('strict ' || path)::jsonpath IS TRUE`), one read-only `SELECT` per case, run
under `GIMS-Project/.venv`. *(Script written to this session's scratchpad, not to `proto/` — that
tree is read-only for this closure pass; the consequence is that this measurement is re-derivable
from the two named committed instruments but is not itself a committed artifact.)*

| case class | cases | expressible in jsonpath | strict form agrees | diverges |
| --- | ---: | ---: | ---: | ---: |
| OTHER (no jsonpath equivalent) | 114 | **0** | — | — |
| `cmp(path, literal)` | 10 | 10 | **9** | **1** |
| bare path | 6 | 6 | **2** | **4** |
| **total** | **130** | **16** | **11** | **5** |

Per case, all 16 expressible cases (`expr` = `truthy(evaluate())`; `strict raw` = the raw `@@`
result before `IS TRUE`; lax shown because it is the default a naive implementation would emit):

| # | fixture name | expr text | jsonpath | expr | strict raw | strict IS TRUE | lax IS TRUE | verdict |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | `simple` | `$.a` | `$."a"` | True | NULL | False | False | **DIVERGES** |
| 12 | `nested` | `$.a.b` | `$."a"."b"` | True | NULL | False | False | **DIVERGES** |
| 13 | `missing_top` | `$.missing` | `$."missing"` | False | NULL | False | False | agrees |
| 14 | `descend_into_nondict_is_null` | `$.a.b` | `$."a"."b"` | False | NULL | False | False | agrees |
| 15 | `bracket_quoted_key_with_space` | `$["weird key"]` | `$."weird key"` | True | NULL | False | False | **DIVERGES** |
| 19 | `deep_nested_key` | `$.results.ph` | `$."results"."ph"` | True | NULL | False | False | **DIVERGES** |
| 24 | `lt_true` | `$.n < 7` | `$."n" < 7` | True | True | True | True | agrees |
| 25 | `lt_false` | `$.n < 7` | `$."n" < 7` | False | False | False | False | agrees |
| 26 | `lt_missing_is_null` | `$.n < 7` | `$."n" < 7` | False | NULL | False | False | agrees |
| 27 | `eq_string_true` | `$.s == "FAIL"` | `$."s" == "FAIL"` | True | True | True | True | agrees |
| 28 | `eq_string_false` | `$.s == "FAIL"` | `$."s" == "FAIL"` | False | False | False | False | agrees |
| 29 | `neq_string_true` | `$.s != "FAIL"` | `$."s" != "FAIL"` | True | True | True | True | agrees |
| 33 | `missing_eq_null_true` | `$.x == null` | `$."x" == null` | **True** | **NULL** | **False** | **False** | **DIVERGES** |
| 34 | `zero_eq_null_false` | `$.x == null` | `$."x" == null` | False | False | False | False | agrees |
| 39 | `gte_equal` | `$.n >= 10` | `$."n" >= 10` | True | True | True | True | agrees |
| 40 | `order_mixed_types_is_null` | `$.n < "x"` | `$."n" < "x"` | False | NULL | False | False | agrees |

**LOAD-BEARING CORRECTION 2 — case 33 is not an open question, it is a measured silent divergence
inside the fixture, reachable through the exact subset this section recommends.**
`$.x == null` on `{}`: `expr.evaluate()` returns **True** (absent key → `null`, and `null == null` is
true; `expr.py:363-367` `_eq` returns a `bool` on every path and `:603-606` routes `==`/`!=` through
it, so `==` is **total** and never yields null — unlike `<`/`>`, which go to `_order_cmp`), while `'{}'::jsonb @@ '$."x" == null'`
returns **False** in lax and **SQL NULL** in strict, so both drop the row. No error, no warning:
**a row `expr` keeps is silently dropped**, and the shape that does it (`== null`) is one of the two
that *are* index-accelerated (§3.5(a)). By FRAMING §5 — "any compiler output that turns a `null`
into a number, or a raise into a value, is a defect of the highest severity" — and by the §4 NO-GO
bar ("NO-GO if any case diverges *silently*"), **this route as written is disqualifying.** Recorded,
not fixed, per FRAMING §3.

**The bare-path class is worse, and it is new at closure.** 4 of its 6 cases diverge, and the 2
"agreements" are coincidental — both sides are falsy for a missing key. The mechanism, measured this
pass with five literals: `@@` yields the item only when it is a JSON **boolean**
(`'{"a":true}'` → t, `'{"a":false}'` → f) and **SQL NULL** for everything else
(`'{"a":5}'`, `'{"a":"x"}'`, `'{}'` → NULL), whereas `expr._truthy` keeps any non-zero number,
non-empty string, non-empty array or object. So a widget whose `where` is a bare path —
`"where": "$.flag"`, which `sources.py:156-162` accepts like any other expression (`where` is
compiled then `truthy(evaluate(...))` decides the row) — silently drops every row whose value is
truthy-but-not-boolean.
`cmp(path, literal)` and bare path must be treated as **two different routing decisions**; the
earlier draft's "the only shape jsonpath can express" elided the second.

**Summary of the route, as a fraction of the language:** expressible 16/130 (12.3%) · agrees under
strict `IS TRUE` 11/130 (8.5%) · index-accelerated 4/130 (3.1%) · **index-accelerated and agreeing
3/130 (2.3%)** · **routable without a divergent sibling record 2/130 (1.5%), one distinct
expression**. Against that, the route's cost: a second semantics to keep aligned with `expr`, a
divergence class (`== null`) that is invisible at query time, and a form (`IS TRUE`) that is
mandatory outside a top-level conjunct and un-accelerated when used.

### 3.6 Correctness hazards — two where an index changes the ANSWER, one where the index-friendly rewrite does, one where the index rejects a legal write

*(Heading corrected: the earlier "four places where an index changes the ANSWER" over-claimed. H1 and
H4 are an index changing a read answer; **H2** is a **predicate rewrite** changing the answer — the
same 5 040 comes back with no index at all; **H3** is a **rejected write**. The rows themselves were
always accurate; the heading was not.)* Each is FRAMING §5's failure mode (*a silently different
answer*) relocated from the compiler into the storage layer. None raises. None warns. All four are
measured, and all four were replayed and reproduced by the verification. **Not buried — these are as
decision-relevant as any timing above.**

| # | exact query / DDL | the two behaviours | why |
| --- | --- | --- | --- |
| **H1** | `SELECT count(*) FROM idxprobe WHERE xpr.ecma_num(xpr.f8(data -> 'score')) = '0.3';` one row `{"score":0.30000000000000004}`, index built at `extra_float_digits=1`, then GUC set to `-3` | **0 rows** with `Index Scan using idxprobe_ecma`; **1 row** with `enable_indexscan/bitmapscan=off` → `Seq Scan` | `xpr.ecma_num` is *declared* `IMMUTABLE` but reads `float8`'s text output, which is GUC-dependent (`runtime.sql:15-18` records this openly). `IMMUTABLE` is a promise the author makes, not a property the server verifies. Reachable through the real language: `string($.score)` compiles to `xpr.ecma_num(xpr.f8(...))`, and `string($.n)` is a fixture case. §6.4 / `idxshape_immutable.sql` I1–I3 |
| **H2** | `(data->>'score')::float8 > 90` vs the compiled `$.score > 90`, same session, same data | **5040** rows vs **4807** rows (and `jsonb_typeof(data->'score')='string'` = **2409**) | The 233-row gap is the **numeric strings above 90**: 2 409 rows store `score` as a numeric string, and 233 of those exceed 90 *(phrasing tightened at closure — the earlier "the 233-row gap **is** the numeric strings" read as 233 = 2 409)*. `expr`'s `>` does not coerce across types — `xpr.ord` compares number-to-number or string-to-string and yields NULL otherwise, pinned by fixture `$.n < "x"` on `{"n":5}` → null. `::float8` coerces. The compiler is right; the index-friendly rewrite is wrong. Control: `$.score * 2 > 180` returns **5040**, because arithmetic *does* coerce via `xpr.num` — confirming coercion, not artefact. §7.2 / `idxshape_hazard.sql` H4 |
| **H3** | `CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8));` then `INSERT … '{"score":"n/a", …}'` | **`ERROR: invalid input syntax for type double precision: "n/a"` — write rejected** (0 rows); drop the index and the identical `INSERT` succeeds (1 row); re-`CREATE INDEX` then fails with the same error — **the index can no longer be built**. The compiled predicate over that row returns **4807, no error** | `expr` is total; a `::float8` index is not. `{"score":"n/a"}` is legal GIMS data — the real `LedgerRecord` collection stores `human_required` as the **string** `"false"`, and `noun_types.json` field types are advisory. A read-side optimisation crossed FRAMING §6's "anything touching writes, invariants" line. A `NULL`-on-failure wrapper (`safe_f8`) fixes the write but **still returns 5040, not 4807** — two defects; fixing one does not fix the other. §7.3 / `idxshape_hazard.sql` H5 |
| **H4** | `ORDER BY nullif(data->'score','null')` — the compiled sort key `S1`, the one output with no `to_jsonb` wrapper, hence index-reachable **today** | `_sort_key` ascending: `[false, true, 2.5, 5, "Zebra", "apple", [1,2], {"a":1}, null]`; `jsonb` B-tree ascending: `[null, "Zebra", "apple", 2.5, 5, false, true, [1,2], {"a":1}]` — **SAME ORDER? False** | `sources.py:99-115`'s `_sort_key` orders `bool < number < string < other < None-last`; `jsonb`'s B-tree orders `Null < String < Number < Boolean < Array < Object`. They agree only on a uniformly-numeric column, and nothing in GIMS enforces that — `score` is a string on 5% of probe rows *by construction, modelled on real ledger behaviour but not a measured `Submission` rate* (§1.2, §3.2 provenance caveat). §7.4 / `idxshape_sort_semantics.py` |

**H4 is also where the only working pushdown lives today**, and its numbers are three lessons in
three rows (§7.4, `ORDER BY … LIMIT 50` over 50 000 `Submission` rows):

| ORDER BY | plan | exec ms |
| --- | --- | ---: |
| `nullif(data->'score','null') ASC` | `Index Scan using idxprobe_score_operand` | **0.065** |
| `… DESC` | `Index Scan Backward`, `Rows Removed by Filter: 150000` | 27.918 |
| `… DESC NULLS LAST` | `Gather Merge` → `Sort` (top-N heapsort) — index **not used** | 15.564 |

**429×** when everything lines up; *worse than sorting* when the index is not collection-scoped;
not used at all when `NULLS` placement mismatches — which is where §3.4's `collection`-leading rule
comes from. And the fastest available pushdown is, on a mixed-type column, a different answer.

**H2 in context — the performance prize and the correctness price are the same rewrite.** The
hand-written indexable form runs in **4.294 ms** (`Bitmap Index Scan on idxprobe_score_f8`) against
the compiled form's **382.247 ms** — **89×**, re-measured later under contention as **19×**; plan
shapes and row counts are stable, the ratio is not, so quote the plans, not the ratio (§7.1). That
89× is the reward for accepting H2's wrong answer and H3's rejected write. *(Not falsified, not
proven: two other `IMMUTABLE`-declared `xpr` date functions were probed under `TimeZone` and
`lc_time` and did not exhibit H1's lie — but both call `STABLE` builtins inside `IMMUTABLE` bodies,
so both carry the same structural risk, §6.4.)*

### 3.7 Cross-check of the plan table against the raw data

`proto/idxshape_plans.json` (185 KB) was re-parsed independently of `analysis/index-shape.md` —
every plan text re-scanned for index names, node chains, estimates, actual rows, buffers and
`Execution Time`. **Raw data wins over prose.** The adversarial verification re-parsed it a third
time and reproduced every one of these confirmations, plus a live replay of the catalog facts, all
five DDL refusals, T4a, H1, H2's 5040/4807/2409 and H3's write rejection
(`.parts/verifications.json`, Finding 3, `notes`).

**Confirmed exactly:** the 4 configuration DDLs; build times (2 341 / 4 785 / 83.6+95.1+106.8+83.3
ms); index sizes (52 617 216 B = 50 MB, 94 134 272 B = 90 MB, 8.4 MB across four B-trees); 36
`ANALYZE` plans + 36 `enable_seqscan=off` plans; **every `est`, `act`, `Rows Removed by Filter`
and total-buffers value in §3.2's table**; one index name across all 72 plan texts,
`idxprobe_pkey`; 36/36 node chains identical between the two runs. `proto/idxshape_preds.json`
confirms 11/11 `"compiled": true`, the atom in 11/11, `to_jsonb` in 10/11 (absent only in `S1`).

**Where the raw data disagrees with, or outruns, the prose:**

| # | claim in `analysis/index-shape.md` | what the raw data shows |
| --- | --- | --- |
| 1 | §4.1: *"the largest spread on any single predicate across the four configurations is 3.9%, on W4"* | Recomputed from `plan_analyze` `Execution Time`, the largest is **9.02% on W1** (134.449 → 146.580 ms); W6 is 7.50%; W4 is 3.937%, which is where the 3.9% came from. Using the file's own `median_ms` field, the largest is **11.54% on W6** (540.5 → 602.9 ms). Conclusion unaffected — no plan changed — but the noise floor is ~2–3× wider than stated, which matters to anyone reusing these timings. |
| 2 | §9.1 lists `((data->>'score')::float8)` at **4 416 kB**; §9.2's write-cost row for the identical DDL lists **6.5 MB** | A 51% difference on the same DDL and the same 200 000-row table, quoted one section apart without reconciliation. **Settled at closure to this extent:** rebuilding the four B-trees on the live table reproduces the `plans.json` lineage exactly (`idxprobe_score_f8` = 4 521 984 B = 4 416 kB; four B-trees = 8 568 kB), and does **not** reproduce 6.5 MB / 13.3 MB for the same DDL on the same table. So §3.4's 2.64 MB-per-index rate inherits from the **unreproducible** lineage. **Cause still not established;** re-running `idxshape_writecost.py` with the live row count printed per config would establish it (the script reads `isize` before its COPY, so a stale row count is the natural suspect — but the GIN rows do not scale with any single row-count multiplier). |
| 3 | §9.2's 12-index row is used to price §8.2's `(collection, extractor(...))` DDL | `idxshape_writecost.py:18-21` builds twelve **single-column text** indexes `((data->>'k'))` over heterogeneous keys (`comments`, `Sample Weight (g)`, `kind`, …) — not the two-column shape §8.2 prescribes. 2.64 MB/index is an average over widely differing value widths, not a per-index constant. **And**, per §3.4's correction block, all 20 000 COPYed rows are `LedgerRecord`, so 10 of those 12 keys — including the 1-index config's only key — are absent on every row. |
| 4 | §§5–10 quote ~40 measured figures | Only `idxshape_preds.json` and `idxshape_plans.json` are machine-readable outputs. The fair control, every DDL error, 5040/4807/2409, 0-vs-1, the sort orders, the jsonpath timings and the write-cost table come from psql/stdout **not captured to a file** — re-runnable scripts, but prose transcription. **Narrower than stated:** the strict-jsonpath plans (12.504 ms, 7 index buffers) are re-runnable from **no** committed script — `idxshape_jsonpath.sql` has no `strict` query, and `idxshape_jsonpath_agree.py:39` hardcodes `strict`, so its lax figure needs a source edit. The two claims re-derivable without the database — the 130-case classification (10 / 7.7%) and the predicate/atom/wrapper counts — **both reproduced exactly by this seat.** |
| 5 | — | **Closed at closure:** `idxshape_jsonpath.sql` J5's four counts are now reported (§3.5(d)(i): 4807 / 4807 / 9985 / 9985). Still unreported and now moot: `idxshape_exprindex.sql` T6b (partial index reused at a different threshold; T6 errored). Citation drift **fixed in this section**: `derive` docstring `sources.py:23`; `_sort_key` `sources.py:99-115`; production index `0002_instances_data_gin.sql:36-37`; `indisvalid` warning `0002:33-34`; `CREATE TABLE instances` `0001_instances.sql:13-18`; `_INDEXABLE_FIELDS` `core/storage/sql.py:252-262`; 12-index config `idxshape_writecost.py:18-21`. Verified-correct as previously cited: `storage_aws.py:1029-1039`, `runtime.sql:160-161`, `:345-346`, `:15-18`, `compile.py:15-17`, `expr.py:562-575`. |
| 6 | — | **Re-derived live this pass** (rolled-back transactions only; `idxprobe` left at 200 000 rows with `idxprobe_pkey` as its only index, verified after rollback): the `IS TRUE` index loss (§3.5(a) A–E), the operator/index-condition matrix, J5's four counts, the key-presence counts on `Submission`, the negation counts (40 015 vs 190 015), the 130-case jsonpath run, the GIN/btree/hash `jsonb_ops` opclass split, `v_operand`/`v_t7d` creation, the 20 000-row COPY key-presence audit, and the 51 noun types / 152 field names recount. |

### 3.8 What this finding does not establish

11 predicates, not 130 — fixture-derived, hand-picked to span the access patterns an index could
plausibly serve. One table shape, one server (PG 16.14, `shared_buffers` 128 MB, `work_mem` 4 MB,
`jit=on`): a different deployment can move absolute costs, not the catalog facts or the DDL
refusals. **Absolute millisecond figures carry unknown contention** — another seat's
`measure_instances_*` load ran on the same container during part of these sweeps (§12.2), and the
verification's re-runs land at different absolute times while reproducing every plan shape, index
name, row count and buffer relationship (control 38.5 vs 26.7 ms; sorts 0.088/40.5/21.4 vs
0.065/27.918/15.564; strict jsonpath 9.99 vs 12.504). **Ratios move; shapes, row counts, catalog
results, DDL success/failure and every correctness divergence do not.**

**Tested and rejected, so not a live option** (folded in at closure from `index-shape.md §10.3`,
which this section previously omitted): **BRIN over the extracted key** — `((data->>'score')::float8)`
at **24 kB**, 200× smaller than any B-tree, and **not used even with `enable_seqscan = off`**
(`Bitmap Index Scan on idxprobe_pkey`, `Rows Removed by Filter: 49937`, 27.067 ms). BRIN prunes only
when the indexed value correlates with physical row order, and records arriving by `(collection,
key)` have no correlation with an arbitrary JSON field. A gate reader asking "why not BRIN?" has a
measured answer, not a silence.

**Open, with the one step that would close each:**

| # | not established | the step that would establish it |
| --- | --- | --- |
| 1 | Whether **any** index-accelerated form of the value-position (`IS TRUE`) jsonpath predicate exists (§3.5(a) D/D2 show no path to decline, which is evidence, not proof) | one `EXPLAIN` sweep of `@@ … IS TRUE` against an expression index on `((data @@ '<lit jsonpath>'))` — needs a literal-jsonpath emission the compiler does not have |
| 2 | The **cause** of the 4 416 kB vs 6.5 MB size lineage split (§3.7 item 2); §3.4's 2.64 MB/index inherits the unreproducible side | re-run `idxshape_writecost.py` printing `count(*)` per config alongside `isize` |
| 3 | Write cost on **representative** rows — the published B-tree µs/row are all-NULL entries (§3.4 correction); the verification's re-run is cited, not re-run here | re-run the write-cost sweep over `Submission`-shaped rows (`tail -n 50000` of the generator output) and publish both columns |
| 4 | `jsonb_ops`'s `?` at **0.585 ms** and the `jsonb_ops` jsonpath range at **24.9 ms** — prose-transcribed, no captured artifact | re-run `idxshape_jsonpath.sql` J4 with output redirected to a file (costs a 90 MB GIN build) |
| 5 | H2's **19×** re-measurement under contention — prose only in `index-shape.md §7.1` | re-run `idxshape_hazard.sql` H4 on a quiet host, capturing stdout |
| 6 | That the jsonpath speedup holds **on any key** (§3.5) — one key, one collection was measured | repeat §3.5(a)'s A/B plans for a second key in a second collection |
| 7 | Whether the jsonpath route diverges on **real** GIMS arrays (the lax/strict array-unwrap split is exercised by 2 hand-made records and **0 fixture cases**) | classify array-valued keys in `gims-ledger` `objects.db` and run those records through `idxshape_jsonpath_agree.py` |
| 8 | The `17 087`-row ledger snapshot behind the generator's key frequencies is no longer re-readable (the live file now holds **17 110** rows); the hardcoded frequencies match today's file to within 0.1pp on every key | re-measure the frequencies against the current `objects.db` and diff |
| 9 | The 130-case jsonpath run (§3.5(d)(ii)) has **no committed artifact** — `proto/` is read-only for this closure pass | copy the scratchpad script into `proto/` when the tree is writable again; it is re-derivable today from `idxshape_fixture_subset.py` + `idxshape_jsonpath_agree.py` |

**Untested, and named so it is not mistaken for measured:** `CREATE INDEX CONCURRENTLY` cost and the
`indisvalid` trap `0002_instances_data_gin.sql:33-34` warns about; partitioning `instances` by
`collection` (which would moot the leading-column rule); generated columns / `jsonb_to_record` /
per-widget sidecars; multi-key composite expression indexes; and `pg_trgm` for `contains()`
(→ `LIKE '%…%'`), a real untested option. Whether pushdown beats the in-memory `MAX_SCAN` path is
finding #4's question.

### 3.9 The emission rule these measurements support — with FRAMING §5's storage-layer clause

New at closure. `analysis/index-shape.md §10.2` ends with a four-rule routing scheme that this
section previously gave in pieces (the DDL in §3.4, the compiler changes in §3.4, the jsonpath
option in §3.5) and never assembled — including its FRAMING §5 clause. Assembled here, **with rule 1
rewritten**, because §3.5's two load-bearing corrections make the original rule 1 unsafe as written:

```
For each widget predicate:
  1. If the AST is cmp(literal-path, literal) with `==` AND the literal is not `null`
     AND the clause is a top-level WHERE conjunct
        -> emit  data @@ 'strict $."k" == <lit>'   (BARE, no IS TRUE)
           index-accelerated, no DDL, measured on one key; 2/130 of the fixture
           NOT `== null`      -- fixture case 33 is a silent row drop (S3.5(d))
           NOT a bare path    -- 4/6 fixture cases are silent row drops (S3.5(d))
           NOT `!=`,`<`,`<=`,`>`,`>=`  -- no index condition (S3.5(a))
           NOT under not/or/derive/sort -- there `IS TRUE` is mandatory and the index is lost
  2. Else if a (collection, key, extractor) index exists for the key
        -> emit the operator form of S3.4  -- index-accelerated, DDL per key,
           and inert until all four compiler changes land
  3. Else
        -> emit the compiled xpr predicate as a filter
           -- A CORRECT ANSWER AT SCAN SPEED: 134 ms - 3.4 s for one widget over a
              50,000-row collection (S3.2). Not a failure mode; whether it beats the
              in-memory path is finding #4's question, not this one.
  4. Else (today(), now(), or Uncompilable)
        -> fall back to in-memory, REPORTED (FRAMING S5)
```

**The FRAMING §5 clause, in the storage layer.** §5 makes "reported, never silent" non-negotiable,
and this finding shows the storage layer can violate it three ways the compiler cannot see:
an index whose `IMMUTABLE` declaration is a lie returns fewer rows than a scan (§3.6 H1); an
index-friendly rewrite returns a different row set (§3.6 H2); a jsonpath route drops rows `expr`
keeps (§3.5(d)). **None of the three raises.** Rule 3 is the reason that is survivable: the
un-indexed compiled filter is the correct answer, so the routing may only leave rule 3 for rule 1 or
rule 2 on a shape whose agreement has been *measured*, and rules 1 and 2 must be recorded per query
alongside the fallback report rule 4 emits. On the evidence here, rule 1's measured-agreeing shape
set is **one distinct expression shape** — which is an argument for shipping rule 3 and rule 4 first,
and treating rules 1 and 2 as optimisations that must earn their way in case by case. **OPINION**,
labelled as such: that reading of the numbers is a recommendation, and §5's verdict is the owner's at the
`sp_decide` gate.

---

**Compliance.** Read-only outside this file, on all three passes this section carries (investigation,
closure, consistency). Both GIMS trees are unchanged and were re-verified this pass: `GIMS-Project`
HEAD `995cc59`, `gims-ledger` HEAD `7b7a049` — the FRAMING §7 values; `gims-ledger`'s SQLite record
databases were opened `mode=ro&immutable=1`, for the key-frequency measurement only (§1.2). **No
defect found here is fixed:** `proto/compile.py` (mtime `2026-08-19 11:23:10`) and
`proto/runtime.sql` (`11:20:29`) both predate this finding's first pass and are unchanged, so cause
2's `to_jsonb` wrapper, §3.6 H1's false `IMMUTABLE`, H2's coercion divergence, H3's rejected write
and §3.5(d)'s case-33 row drop are **recorded, not fixed**, per FRAMING §3. All Postgres work was in
the spike's own scratch database `autosql_spike`, in the `idxprobe` table this finding created;
`glp_strong` was never opened, and another seat's `instances` / `measure_instances_*` tables were
read for `pg_stat` accounting only (`analysis/index-shape.md §12.4`). The only file written by this
finding's seats is `spikes/T-1/.parts/f3.md`. **[consistency]**

**The DDL discipline, stated precisely rather than uniformly.** The *closure* pass's DDL probes did
run inside explicit transactions that were rolled back, with post-rollback verification — `idxprobe`
left at 200 000 rows with `idxprobe_pkey` as its only index (§3.7 item 6). The *investigation*
pass's committed scripts did not: `proto/idxshape_exprindex.sql`, `idxshape_hazard.sql`,
`idxshape_immutable.sql` and `idxshape_jsonpath.sql` contain **no `BEGIN` and no `ROLLBACK`** — each
experimental index is created and dropped in autocommit, `idxshape_exprindex.sql` leaves its indexes
standing for `idxshape_jsonpath.sql:2-4` to drop, and H5 inserts one `SUB-NAN` row and deletes it
(`idxshape_hazard.sql:40,49`). Cleanup on that pass was therefore by explicit `DROP`/`DELETE` plus a
final catalog and row-count check (`analysis/index-shape.md §12.4`), **not** by transaction
rollback. Both forms stay inside the scratch database FRAMING §7 provisions and neither touches
either GIMS tree; the distinction is recorded because "all of f3's DDL ran in rolled-back
transactions" would over-state the investigation pass. **[consistency]**

**Grey area, disclosed rather than smoothed.** §3.5(d)(ii)'s 130-case strict-jsonpath run was driven
by a script written to the session scratchpad, not to `proto/` (read-only for the closure pass): one
read-only `SELECT` per case, no DDL, method taken unchanged from
`proto/idxshape_fixture_subset.py` + `proto/idxshape_jsonpath_agree.py`. It is re-derivable from
those two committed instruments but is **not itself a committed artifact** (§3.8 open item 9).
**[consistency]**

**This consistency pass specifically.** No Postgres connection was opened and nothing was written
anywhere except this file. `proto/idxshape_fixture_subset.py` was re-run under `GIMS-Project/.venv`
(114 / 10 / 6 / 130, reproduced exactly); the operator split of the 10 `cmp` cases and the four `==`
cases' `expr` values were re-derived through `core.dashboard.expr` (`<`×4, `==`×4, `!=`×1, `>=`×1;
`$.x == null` on `{}` → `True`); and `proto/idxshape_preds.json` was re-counted with `python3` (11
compiled outputs, `to_jsonb` in 10, `S1` a bare `nullif(...)`) — all read-only, no DDL, no writes.
**[consistency]**

---

## Finding 4 — Measurement

End-to-end numbers for the near-due dashboard widget against the current in-memory path, six table sizes, in the
comment form of the RAG pushdown profile (`gims-ledger/core/storage/sql.py:240-251`). The deep document is
`analysis/measurement.md`; it is cited by section, not copied. Every number below was re-derived from
`analysis/measurements.json` / `analysis/probes.json` by this seat — §4.10 lists the ten places where the raw data
and the prose document do not match.

**This section has been revised after adversarial verification.** Thirteen corrections were raised against it; twelve
are applied in place and one is rejected with evidence (§4.12 is the ledger). **Every headline wall-clock, recall,
payload and per-row µs figure reproduced exactly** — what changed is four *stated causes* and a set of citations:
§4.1's representativeness warrant, §4.6's B2-vs-B3 proof, §4.6/§4.8's attribution of the 99.6% gap to "plpgsql call
overhead", and — found by this seat rather than by the verifier, from the captured plan text — §4.6's claim that the
`today()` chain cannot be folded. Two figures moved: the 10 k relation size (8 256 → 8 216 kB) and the compile-time
refusal cost (0.0266 → 0.0307 ms, a mis-labelling of `fallback.plan_ms`); two were withdrawn as uncitable (the
COPY/GIN-build seconds).

**No recommendation is made here.** Three results hold simultaneously and are reported without being reconciled
(§4.9).

---

### 4.0 Provenance

| | |
|---|---|
| What | one widget (§4.1), two paths, six table sizes 1 000 → 1 000 000 rows |
| When | 2026-08-19 (`analysis/measurement.md` §0; file mtimes 11:57–12:44) |
| Postgres | 16.14 (Debian 16.14-1.pgdg12+1), container `glp-strong-db`, image `pgvector/pgvector:pg16`, host port 55433 — re-verified live by this seat: `SELECT version()` returns the same string as `measurements.json → pg.version` |
| Database | `autosql_spike` (spike scratch db; `glp_strong` never opened — asserted at `analysis/measurement.md` §11, **not established by any artifact**; `bench.py:27-28`'s DSN names `dbname=autosql_spike`, which is consistent but is not proof) |
| Server settings | `shared_buffers` 128 MB, `work_mem` 4 MB, `max_parallel_workers_per_gather` 2 (`measurements.json → pg`); `extra_float_digits` pinned to 1 at `proto/bench.py:507` **only** — `measurements.json → pg` does not record it |
| Host / Python | 20 cores, 46 GB RAM (re-verified: `nproc` → 20, `free -g` → 46); Python 3.12.3, `GIMS-Project/.venv`, psycopg2 2.9.12 |
| Reference runtime | the **real** `GIMS-Project@995cc59` `expr.py` and `sources.py`, imported and called stage by stage — not reimplemented (`proto/bench.py:111-156`) |
| Unit under test | `proto/compile.py` + `proto/runtime.sql` (schema `xpr`), stated **unmodified** by the measuring seat (`analysis/measurement.md` §11) — **unverifiable**: both files are untracked in git, so no diff exists; mtimes (compile.py 11:23, runtime.sql 11:20) predate `bench.py` 11:57 and `measurements.json` 12:27, which is consistent but not proof. Harness `proto/bench.py` + `gen_data.py` + `load_data.py`, throwaway per `FRAMING.md` §3 |

Command, verbatim (`analysis/measurement.md` §0): for each `N` in `1000 10000 20000 25000 100000 1000000`,
`gen_data.py N n$N.csv` then `load_data.py N n$N.csv gin`; then `bench.py 1000,10000,20000,25000` and `bench.py
100000,1000000`.

**Statistic: median.** Repetitions per cell: **9** at 1 k/10 k/20 k/25 k, **7** at 100 k, **3** at 1 M
(`proto/bench.py:501`). min/max/stdev recorded for every cell. Each arm is warmed once, result discarded, before the
repetitions (`proto/bench.py:537`). Connection setup is excluded from both arms. Three exceptions to "median of N",
material enough to state:

**(a)** §4.6's per-row isolation is **median of 5** at every size (`proto/bench.py:491-494`), though
`analysis/measurement.md` §5's preamble says otherwise.

**(b)** the acquisition control in §4.5 is **n = 1** per size — at `proto/bench.py:563-564`, not `:571`
(`:571` is `entry["identity"] = identity_check(...)`; corrected citation, verified by reading the file).

**(c)** `EXPLAIN (ANALYZE)` timings are used for **plan shape only, and cannot be described as a uniform
instrumentation inflation** — the earlier wording ("instrumented and inflated, +37%") was wrong about the cause. At
1 M the pair reads B2 **81 532.134 ms** / B3 **64 314.895 ms** against timed medians of 59 590.03 / 59 609.77 ms,
i.e. **+36.8%** and **+7.9%**; worse, EXPLAIN says B3 is **21.1% faster** than B2 while the medians say **+0.03%**.
Instrumentation cannot produce a 17.2 s gap between two plans that evaluate the `xpr` chain on the same ~599 k rows
(§4.6) — that would be ~43 µs per extra instrumented row. **The cause of the spread is not established**; it is most
consistent with host-load variance between two single captures (INFERENCE). What would establish it: the two
EXPLAINs re-run back to back on a quiet host, three captures each. §4.6's index conclusion leans on this same pair,
and is restated below so that it no longer does.

---

### 4.1 The widget, and the evidence that it is representative

```json
{ "type": "noun", "noun_type": "Sample",
  "filters": {"status": "open"},
  "derive":  {"days_left": "days_between(today(), $.due_date)"},
  "where":   "$.days_left != null and $.days_left < 7",
  "sort":    {"field": "days_left", "dir": "asc"}, "limit": 50 }
```

Taken unchanged from `recon/baseline.md` §3.2 (`measurements.json → widget` is byte-equal to it).

**Correction applied — it is a defensible assembly of three attested fragments, not a verbatim quotation of any one
of them.** The earlier draft claimed the `sources.py` docstring example matched "clause for clause" and that the
full-pipeline test was "populated with these clauses". Both are false, checked line by line against
`GIMS-Project@995cc59`:

| clause | docstring example `sources.py:15-28` | full-pipeline test `tests/test_dashboard_sources.py:85-95` | derive/where test `:45-57` | **measured widget** |
|---|---|---|---|---|
| `type`/`noun_type` | `noun` / `Sample` ✅ | via `noun_source` fixture ✅ | via fixture ✅ | `noun` / `Sample` |
| `filters` | `{"status":"open"}` ✅ | `{"status":"open"}` ✅ | absent | `{"status":"open"}` |
| `derive` | `days_between(today(), $.due_date)` ✅ | identical ✅ | identical ✅ | identical |
| `where` | **`"$.days_left < 7"`** ❌ | **`"$.days_left != null"`** ❌ | **`"$.days_left != null and $.days_left < 7"`** ✅ | the `:45-57` form |
| `sort` | `days_left` asc ✅ | `days_left` asc ✅ | absent | `days_left` asc |
| `limit` | `50` ✅ | **`1`** ❌ | absent | `50` |

`recon/baseline.md` §3.2 states this honestly ("The only assembly step is combining the docstring's `where` clause
… with the null-guard the tests use"); the earlier draft dropped that qualification. **No single test or docstring
in the tree contains the measured widget.** The three attestations that do survive: `api/dashboard/sources.py:7-8`
(not `:6-7`) names the use case — *"'days_left', 'near-due', 'status' are all composed by the tenant through the
derive/where expressions … never built in"*; the docstring's worked example matches on five of six clauses; and
`test_full_pipeline_order_derive_then_where_then_sort_then_limit` is the **only** test in that suite populating
every pipeline stage at once, and matches on four of six.

**The `!= null` conjunct is not cosmetic, and it moves the number in the harder direction.** It is exactly what makes
the compiled `WHERE` carry the derive expression **twice** (§4.6) — four `xpr.pdate_ms` calls per scanned row instead
of two. So the measured widget is the **more expensive** of the two documented variants: had the docstring's bare
`"$.days_left < 7"` been measured, B2's per-scanned-row filter cost would have been roughly halved. Direction stated,
magnitude **not measured** — no run of the docstring variant exists.

#### The one real tenant widget on this machine — n = 1, and it matches the shape

`f2` §2.9 / `analysis/coverage.md` §8.3 record a read-only sweep of every SQLite database in the `gims-ledger` tree.
It found exactly **one** dashboard (row `143c987947874e36b728bb66f5a9125c`, present in two `LIMS-System` backups),
three widgets, two of them `csv` (which never reach `resolve()`), and **one `noun` widget**:

```json
{"type": "noun", "noun_type": "Submission",
 "derive": {"days_left": "round(days_between(today(), $.due_date), 1)"},
 "where":  "$.status == \"in progress\"",
 "sort":   {"field": "days_left", "dir": "asc"}}
```

| | measured widget (§4.1) | LIMS-System real widget |
|---|---|---|
| derive | `days_between(today(), $.due_date)` | same, wrapped in `round(…, 1)` |
| sort | `days_left` asc — a **derived** column | **identical** |
| where | `$.days_left != null and $.days_left < 7` — reads the **derived** column | `$.status == "in progress"` — reads a **stored** field |
| filters / limit | `{"status":"open"}` / 50 | none / none |

**This raises the warrant from "the codebase documents it" to "the codebase documents it *and* the one real widget
found on this machine has the same shape, n = 1."** The shared core is the part that makes pushdown hard: a date
`derive` over a possibly-missing key, and a **sort on the derived column**. That widget was compiled and run against
live Postgres over six representative `Submission` records including a missing `due_date`, an unparseable
`"not a date"`, an explicit JSON `null` and a full timestamp: **12 checks, 12 agree, 0 diverge**
(`analysis/coverage.md` §8.3). It was never *timed* — the two seats' work does not overlap there.

**The difference matters and runs in the easier direction.** The real widget's `where` reads a **stored** field, so
its compiled filter is an equality test (the W1 shape, ≈2.7 µs/row on the `f3` rig — §4.6) and the date chain appears
only in the `SELECT` and `ORDER BY`, on surviving rows, instead of four `xpr.pdate_ms` calls on every scanned row.
**INFERENCE, not measured:** the real widget is therefore cheaper to push down than the one measured, so §4.9(2)'s
3.79×–7.15× penalty is an upper bound for that shape. Against it: the real widget has **no `limit`**, so there is no
top-N heapsort to bound the sort, and `round(…, 1)` adds one more `xpr` call per surviving row. Neither effect was
measured; what would establish it is one `bench.py` run with the LIMS-System spec substituted for `WIDGET`.

**The honest gap, narrowed but not closed.** n = 1 bounds nothing statistically, there is no telemetry, and no corpus
of tenant-authored `DataSource` JSON exists in either tree (`recon/baseline.md` §6, `f2` §2.9). That this widget is
the **most common** in production remains **not established**; what would establish it is a sample of real
`DataSource` JSON from a deployment, or widget-type counters in the dashboards router.

---

### 4.2 The corpus

`proto/gen_data.py`, seeded `SEED = 1729`, implementing the generator rule specified in `recon/baseline.md` §4.2.
**All three `gen_data.py` line citations in the earlier draft were off by 4–5 lines and are corrected here** (the
`:36` one was load-bearing — it was the sole warrant for the claim that B4's raising `::date` is invisible on this
corpus, and a reader who opened it found `t = rnd.randint(0, 4)`).

| | |
|---|---|
| Record shape | `{id, status, due_date?, priority}` + 5–15 arbitrary `field_N` keys of mixed type (string / float / bool / null / small nested object) — `proto/gen_data.py:26-47` |
| `status` | ~60% `"open"` (`gen_data.py:27`, not `:31`); measured at 1 M, the GIN index returns **598 997** of 1 000 000 rows for `status=open` (`explain_B3`, Bitmap Index Scan) |
| `due_date` | ISO date, uniform −30…+370 days from 2026-08-19; **5% of rows omit the key entirely** (`gen_data.py:30`, not `:35-37`) — never malformed, always parseable, because line **31** (not `:36`) emits only `datetime.date.isoformat()` |
| Mean stored JSON | 283 bytes/row compact (`gen_data.py` `avg_json_bytes`). **Prose-only — stdout was not captured — but independently re-derivable**: re-running the generator at `SEED = 1729` gives 283.3 / 282.7 / 283.0 at N = 1 000 / 10 000 / 100 000, and 60.13% `open`, 4.94% missing `due_date` at N = 100 000. **On the wire as `jsonb::text` it is 315–317 bytes/row** (`measurements.json → sizes.*.floor.payload_bytes ÷ N`) — the larger figure is the one the payload column uses |
| Selectivity | `filters` + `where` keep **5.00%–5.35%** of rows (measured: 50/1 000, 510/10 000, 1 055/20 000, 1 338/25 000, 5 202/100 000, 52 327/1 000 000). `analysis/measurement.md` §3 states "~5.1%"; the measured range is 5.0–5.35% |
| Storage | one table per size, `measure_instances_<N>`; DDL at `proto/load_data.py:10-17` (not `:13-20`) is identical to `gims-ledger/migrations/pg/0001_instances.sql:13-18` **except the table name** (`{t}` vs `instances`) — column and PK definitions byte-identical; each carries the `GIN (data jsonb_path_ops)` index of `0002_instances_data_gin.sql:36-37` (`load_data.py:31`) |
| `now` | pinned to `2026-08-19T12:00:00Z` in ctx — no run reads the wall clock (`measurements.json → ctx`) |

One table per size, not one shared table, so a size-N scan never reads size-M rows (`proto/gen_data.py` header
comment).

**The 5% `due_date` miss rate is the one corpus parameter a real collection now contradicts, by 8.6×.
[consistency]** `xd` D.7 opened the only real dashboard's own collection (`GIMS-Project/projects/LIMS-System/…`,
`Submission`, **7 rows**) and found `due_date` **absent on 3 of 7 = 42.9%**; this corpus omits it on **5%**
(`gen_data.py:30`). What that does to the selectivity, derive-cost and recall figures below is worked through in
§4.11, where the net direction is **not established** and the two legs that push it are stated separately.

**Sizes, live today** (`pg_total_relation_size`, re-read read-only by this seat): **968 kB / 8 216 kB / 16 MB / 20 MB
/ 78 MB / 700 MB** (419 MB heap + 281 MB GIN at 1 M). The earlier draft printed 8 256 kB at 10 k; the live figure is
8 216 kB, a 0.5% error.

**Load cost is withdrawn as uncitable.** The earlier draft published COPY 0.01/0.08/0.17/0.21/0.89 s and GIN build
0.01/0.09/0.18/0.23/1.11 s from `load_data.py` stdout. **That stdout was not captured**, and no load-timing key
exists in `measurements.json` or `probes.json`. §4.10 item 5 applies the "prose-only, uncitable" standard to
`analysis/measurement.md`; it applies here too, and these figures are struck. Re-running the loader would establish
them; that is a write, and out of bounds for this pass.

**`reltuples` on the 1 M table is 999 634, not 1 000 000** (live `pg_class`) — a stale estimate from the `ANALYZE`
that aborted. The table genuinely holds 1 000 000 rows (`explain_B2`: 947 673 removed + 52 327 returned). No result
here depends on it, but a re-run that trusts the planner's row estimate starts 0.04% off.

The 1 M load timings are **not established** for a second reason: the loader aborted at its `VACUUM ANALYZE` with
`DiskFull: could not resize shared memory segment` — prose-only in `analysis/measurement.md` §3, no artifact records
the exception, though both live re-verifications it implies do check out: this container's `/dev/shm` is the docker
default **64 MB** (`docker exec glp-strong-db df -h /dev/shm` → `64M`) and the cluster-level
`max_parallel_maintenance_workers=0` used to finish that load has been **reverted** (`SHOW
max_parallel_maintenance_workers` → `2`). COPY and the GIN build had already succeeded. **The sweep stopped at 1 M**,
50× `MAX_SCAN`, for a stated reason: ~20 GB free disk against 700 MB of database + 359 MB of CSV per size
(`analysis/measurement.md` §3).

---

### 4.3 What each arm is, and every deviation between them

**Path A — today's in-memory pipeline.** The real `sources.resolve` sequence (`sources.py:347-356`), called function
by function so each stage times separately (`proto/bench.py:111-156`): `fetch_wire` = `SELECT data::text … WHERE
collection = %s` + `fetchall()` (the acquisition seam of `PgRecordStore.list_records`,
`gims-ledger/api/storage_aws.py:728-731`); `deserialize` = `[json.loads(s) …]` (`api/storage_aws.py:693-694`);
`truncate` = `raw[:MAX_SCAN]`, `MAX_SCAN = 20_000` at `sources.py:61`; then the real `_apply_derive` →
`_filter_rows` → `_apply_sort` → `_apply_limit` (`sources.py:353-356` → `:133`, `:151`, `:168`, `:180`).

**Path B — the compiled pushdown**, four variants from the real `expr.parse()` AST through the unmodified
`compile.py` (SQL verbatim in `analysis/measurement.md` Appendix A; `measurements.json → generated_sql`):

- **B1 faithful** — materialise `data || jsonb_build_object('days_left', <derive>)` in a subquery, then filter/sort
  over the augmented document; mirrors what `_apply_derive` literally does (`sources.py:146`).
- **B2 inlined** — the derive AST substituted into `where` and `sort` (`proto/bench.py:73`), so the augmented
  document is built only for surviving rows.
- **B3 inlined + containment** — B2 with `filters` as `data @> '{"status":"open"}'` so the `jsonb_path_ops` GIN is
  usable. *(Whether that is the right index shape is finding #3.)*
- **B4 ceiling — UNSAFE, not a candidate** — `days_left` as `((data->>'due_date')::date - DATE
  '2026-08-19')::float8`.

#### Deviations, stated rather than hidden

Six, and their direction:

1. **`::text` + `json.loads` instead of psycopg2's jsonb decoding**, to split wire from decode. Controlled (§4.5):
   **five of six sizes** say the `list_records` form is 3%–344% *slower* than the split, so the split
   **under-reports Path A's acquisition** at those five. **At N = 1 000 the driver form is 2% faster** (5.38 vs
   5.50 ms), so the split *over*-reports there and Path A's 1 000-row total is **not** a lower bound. Each control is
   n = 1, so the ±2–4% cells are inside any plausible noise floor. **Favours Path A at five of six sizes**, and the
   earlier universal claim ("every Path A number is a lower bound") is withdrawn.
2. **`_noun_records`/`get_noun_items` (`sources.py:193-211`) is not in the loop** — the harness issues the single
   local-TCP `SELECT` that seam prefers, skipping manifest resolution and S3 shims, i.e. the **fastest** acquisition
   that seam has. **Favours Path A.**
3. **Connection setup excluded from both** — `connect_ms` = **7.1 ms** (the prose says 7.6; §4.10 item 6).
4. **The deterministic `$.id` tiebreak is added to *both* arms**, and only for the identity and answer-quality runs;
   timing runs use the widget's own `ORDER BY` untouched (`proto/bench.py:175-179` — `:180-181` are blank lines).
   Symmetric, and necessary — Python's `sorted()` is stable, Postgres' sort is not.
5. **B3 changes the `filters` predicate form** (containment, not `->` equality) — the variable under test in that
   arm, not a defect.
6. **B4 is not "B2 with native operators". It differs in FIVE ways** — the earlier draft enumerated four and missed
   the fifth. All make it faster, none is free. Read off `measurements.json → generated_sql.B4`:

   | # | B2 does | B4 does | why it matters |
   |---|---|---|---|
   | a | `xpr.pdate_ms(…)` on the field | `(data->>'due_date')::date` | `::date` **raises** on a malformed date; `xpr.pdate_ms` returns null. This is the totality violation `FRAMING.md` §5 forbids (`compile.py:28-31`, `expr.py:409-431`) |
   | b | emits `xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms(ctx), true)))` for `today()` | inlines the literal `DATE '2026-08-19'` | B4 does not read `ctx` at all. **The planner folds part of B2's chain but not all of it** — see §4.6: `now_ms` and `fmt_date_ms` vanish from the executed plan, one `xpr.pdate_ms` per copy does not |
   | c | compiles `$.days_left != null` to an `IS DISTINCT FROM NULL::jsonb` test on the derived value | `(data ? 'due_date')` key-existence | different semantics, and `?` is exactly the operator `jsonb_path_ops` deliberately does **not** index (`FRAMING.md` §2) |
   | d | emits the full 3-key `_sort_key` tuple (type-rank, number, string COLLATE "C") mirroring `sources.py:99-116` | a single scalar `ORDER BY` | B4 drops the type-rank fidelity |
   | **e** | compares with `xpr.truthy(to_jsonb(xpr.ord('<', …, …)))` — `expr`'s **total cross-type ordering** | a bare `float8 <` | a cross-type comparison that `expr` defines, B4 either raises on or orders differently. Invisible here for the same reason as (a) and (d): `days_left` is always numeric on this corpus |

   On this corpus all five simplifications are invisible: **B4's answer is row-for-row identical to the compiled
   arm's at all six sizes** (`measurements.json → sizes.*.b4_ceiling_matches_compiled_answer = {"ok": true,
   "detail": "identical"}`). **INFERENCE for why:** `gen_data.py:31` only ever emits `date.isoformat()`, so no
   malformed date exists to raise on, and `days_left` is always a number, so the type-rank tuple collapses to rank 1
   and the cross-type ordering never fires. A corpus with one malformed date string would separate (a) immediately —
   that case is the conformance seat's territory, not measured here.

---

### 4.4 Results — the full sweep

**End-to-end wall clock, median ms** (`measurements.json → sizes.*.path_a/path_B*.total_ms`; min–max in brackets):

| rows | reps | **Path A** in-memory | **B1** faithful | **B2** inlined | **B3** inlined+GIN | **B4** ceiling *(unsafe)* | A ÷ B2 | B2 ÷ A | A ÷ B4 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 000 | 9 | **13.84** [13.37–14.30] | 87.95 | 57.47 [57.28–62.55] | 58.00 | 1.14 [1.09–1.32] | 0.24× | 4.15× | **12.1×** |
| 10 000 | 9 | **142.34** [138.52–162.18] | 854.07 | 554.05 [545.34–564.45] | 547.53 | 6.72 | 0.26× | 3.89× | **21.2×** |
| 20 000 | 9 | **300.10** [277.15–313.17] | 1 754.20 | 1 138.61 [1 117.16–1 155.25] | 1 128.87 | 13.19 | 0.26× | 3.79× | **22.8×** |
| 25 000 | 9 | **331.70** [309.17–359.01] | 2 231.87 | 1 447.17 [1 431.95–1 454.12] | 1 461.54 | 16.36 | 0.23× | 4.36× | **20.3×** |
| 100 000 | 7 | **899.26** [879.17–921.43] | 9 188.50 | 6 036.41 [5 951.94–6 184.39] | 5 950.58 | 33.95 | 0.15× | 6.71× | **26.5×** |
| 1 000 000 | 3 | **8 331.43** [8 109.92–8 389.56] | 95 384.20 | 59 590.03 [59 269.94–60 409.79] | 59 609.77 | 229.99 [228.54–236.09] | 0.14× | **7.15×** | **36.2×** |

**Rows, memory, payload** (`sizes.*.path_a_shape`, `.path_a_peak_rss_mb`, `.floor.payload_bytes`; Path B payload
from `probes.json → payload`):

| rows in table | rows Path A pulls into Python | rows Path A actually **evaluates** | Path A peak RSS | Path A payload | Path B rows | Path B payload | payload ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 000 | 1 000 | 1 000 | 72.3 MB | 0.32 MB | 50 | 16 957 B | **18.7×** |
| 10 000 | 10 000 | 10 000 | 97.9 MB | 3.16 MB | 50 | 16 465 B | **191.7×** |
| 20 000 | 20 000 | 20 000 | 124.8 MB | 6.30 MB | 50 | 16 561 B | **380.7×** |
| 25 000 | 25 000 | **20 000** | 137.4 MB | 7.88 MB | 50 | 16 873 B | **467.1×** |
| 100 000 | 100 000 | **20 000** | 337.5 MB | 31.59 MB | 50 | 16 119 B | **1 960.0×** |
| 1 000 000 | 1 000 000 | **20 000** | **2 764.9 MB** | **317.02 MB** | 50 | 16 119 B | **19 667.5×** |

**Read the RSS column with its method.** `path_a_peak_rss_mb` is `getrusage(RUSAGE_SELF).ru_maxrss` read once after
the repetition block (`proto/bench.py:540-547`) — a **monotonic process high-water mark**, not a per-call figure,
and the sweep ran as two invocations. So 72.3 MB at 1 k is mostly interpreter + psycopg2 + imported GIMS modules,
and the 1 M figure carries the 100 k arm's residue. **Marginal heap attributable to Path A (INFERENCE, derived):** 2
764.9 − 337.5 = **2 427 MB for 1 M rows ≈ 2.4 kB of Python heap per 316-byte record**, a ~7.7× inflation; the 100 k
arm gives 265 MB ≈ 2.7 kB/row, consistent. The sibling `path_a_rss_growth_mb` (0.3–7.8 MB) is small only because the
high-water was already reached in the discarded warm-up call — it is **not** "the memory Path A uses".

#### The database-side floor — measured, and never used by the earlier draft

`sizes.*.floor` holds two figures the earlier draft ignored except for `payload_bytes`
(`proto/bench.py:264-280`): `count_only_ms`, a full scan of the collection evaluating nothing, and
`payload_scan_ms`, the same scan **materialising `data::text` for every row server-side** and returning one
aggregate — i.e. everything Path A's `fetch_wire` does except moving the bytes to the client.

| rows | `count(*)` scan | full `data::text` payload scan | Path A `fetch_wire` | fetch ÷ payload-scan | B2 total ÷ payload-scan |
|---:|---:|---:|---:|---:|---:|
| 1 000 | 0.44 | 1.82 | 2.24 | 1.2× | 31.6× |
| 10 000 | 1.35 | 15.77 | 20.30 | 1.3× | 35.1× |
| 20 000 | 2.44 | 31.33 | 40.58 | 1.3× | 36.3× |
| 25 000 | 2.79 | 40.33 | 57.83 | 1.4× | 35.9× |
| 100 000 | 10.56 | 53.39 | 210.02 | 3.9× | 113.1× |
| 1 000 000 | **53.92** | **502.20** | 2 237.40 | **4.5×** | **118.7×** |

**This is the tighter bound on the prize.** At 1 M the database can touch and serialise all 1 000 000 records in
**502 ms**; Path A's wire phase alone is 4.5× that (the difference is client transfer + psycopg2), and B2 is
**118.7×** it. B4's 230 ms is the more flattering ceiling but it is not comparable — B4 returns 50 rows, the floor
scans all 1 M. For "how much of the 8 331 ms is collectable", **502 ms is the number a decision should use**, and it
is measured rather than inferred. (n = 1 per cell; `scan_floor` is called once per size.)

---

### 4.5 Where Path A's time goes — the lever

`measurements.json → sizes.*.path_a.*` (medians). Two reasons the sub-phases do not sum to `process`: phase medians
are computed per-repetition then aggregated (`proto/bench.py:126,152-153`), and the **`truncate` phase is inside
`process` but was omitted from the earlier draft's table** — it is 0.00 ms at the three under-cap sizes and **0.29 /
0.33 / 0.36 ms** at 25 k / 100 k / 1 M. It is restored as its own column:

| rows | fetch (wire) | deserialize | **acquire** | trunc | derive | filter | sort | limit | **process** | **total** | acquire % | process % |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 000 | 2.24 | 3.15 | **5.50** | 0.00 | 7.25 | 1.07 | 0.03 | 0.00 | **8.35** | **13.84** | 40% | 60% |
| 10 000 | 20.30 | 33.73 | **54.40** | 0.00 | 74.81 | 12.20 | 0.34 | 0.00 | **87.82** | **142.34** | 38% | 62% |
| 20 000 | 40.58 | 89.00 | **129.43** | 0.00 | 145.34 | 24.53 | 0.73 | 0.00 | **171.06** | **300.10** | 43% | 57% |
| 25 000 | 57.83 | 99.24 | **159.17** | 0.29 | 145.88 | 24.54 | 0.80 | 0.00 | **171.73** | **331.70** | 48% | 52% |
| 100 000 | 210.02 | 519.48 | **728.00** | 0.33 | 146.36 | 24.81 | 0.86 | 0.00 | **172.28** | **899.26** | 81% | 19% |
| 1 000 000 | 2 237.40 | 5 938.95 | **8 161.42** | 0.36 | 143.88 | 24.98 | 0.77 | 0.00 | **170.01** | **8 331.43** | **98%** | **2%** |

**The regime flips at `MAX_SCAN`, and the table shows it.** `process` is **flat at 170–172 ms from 20 000 rows
upward** — the cap, visible in the timings, because `derive`/`filter`/`sort` only ever see 20 000 rows — while
`acquire` grows without bound because `raw` is materialised in full *before* the slice (`sources.py:347` then
`:351`). So: **below the cap** the dominant cost is Python expression evaluation (62% at 10 k), with `derive` alone
**48–53%** of the un-truncated total at **7.25–7.48 µs/row** (`days_between` calls `_parse_date_ms` twice per row,
`expr.py:469-475`); **above the cap** it is acquisition of rows discarded unexamined — **98% at 1 M, deserializing
980 000 records that never reach `_apply_derive`**. The pipeline's back half is free: `sort` never exceeds 0.3% of
total and `limit` measures 0.00 ms at every size.

**Acquisition control**, `SELECT data` with psycopg2's own jsonb decoding, **n = 1 per size**
(`measurements.json → path_a_driver_acquire_ms`, written at `proto/bench.py:563-564`): **5.38 / 75.81 / 133.78 /
165.38 / 900.04 / 36 256.46 ms** against the split's 5.50 / 54.40 / 129.43 / 159.17 / 728.00 / 8 161.42 — i.e.
**−2%, +39%, +3%, +4%, +24%, +344%**. **Five of six observations say the harness split under-reports Path A; the
sixth (N = 1 000) says it over-reports by 2%.** The 1 M control is a single observation and could be GC under a
2.8 GB heap rather than driver cost — **not established** either way.

---

### 4.6 The `xpr` runtime's per-row cost, isolated — and where inside the runtime it lives

Four queries over the same scan, median of **5** samples each (`proto/bench.py:477-495`; `measurements.json →
runtime_microcost_ms`). µs/row columns are `(with − plus_field_read) ÷ N`, recomputed by this seat and matching
`analysis/measurement.md` §5.4 to the stated precision:

| rows | `count(*)` | `+ data->'due_date'` | `+ xpr.pdate_ms(…)` | `+ (data->>'due_date')::date` | **xpr µs/row** | **native µs/row** | ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 000 | 0.32 | 0.33 | 11.85 | 0.55 | **11.52** | 0.220 | **52×** |
| 10 000 | 0.88 | 2.45 | 113.05 | 3.16 | **11.06** | 0.071 | **156×** |
| 20 000 | 1.71 | 5.09 | 224.49 | 6.95 | **10.97** | 0.093 | **118×** |
| 25 000 | 2.00 | 6.52 | 287.27 | 8.47 | **11.23** | 0.078 | **144×** |
| 100 000 | 7.51 | 25.74 | 1 253.52 | 23.55 | **12.28** | **−0.022** *(negative — native is inside the noise floor)* | *n/a* |
| 1 000 000 | 42.92 | 106.23 | 12 059.43 | 247.42 | **11.95** | 0.141 | **85×** |

**Constant in N — but not constant in host load.** Across three orders of magnitude of table size the per-call cost
is **10.97, 11.06, 11.23, 11.52, 11.95, 12.28 µs/row**, a 12% spread with no trend in N: a per-call constant *at the
load the sweep ran under*. **The level itself is not stable.** This seat re-ran the identical four queries against
`measure_instances_100000`, read-only, three times, at a 1-minute load average of **28.98**. (**The sweep's own load
was never recorded** — `analysis/measurement.md` §10.11; the only load figure in the raw data is
`probes.json → recheck.loadavg_at_start` **13.79 / 17.92 / 15.16**, which belongs to the later re-run, so "load 15"
below is a proxy, not the sweep's measured condition.)

| query | sweep, 100 k | this seat's re-check, 100 k (3 runs) | delta |
|---|---:|---|---|
| `count(*)` | 7.51 ms | 10.8 / 13.0 / 24.5 ms | +44% … +226% |
| `+ data->'due_date'` | 25.74 ms | 33.7 / 34.0 / 34.4 ms | **+31% … +34%** |
| `+ xpr.pdate_ms(…)` | 1 253.52 ms | 4 341.9 / 4 621.3 / 4 786.2 ms | **+246% … +282%** |
| `+ (data->>'due_date')::date` | 23.55 ms | 19.5 / 24.8 / 26.0 ms | **−17% … +10%** |

Recomputed, the xpr per-row cost at 100 k is **43.1–47.5 µs/row** at load 29 against **12.28 µs/row** in the sweep —
a **3.5×–3.9× move in the level**, with load the only variable this seat changed. The native cast again lands below the noise floor (both differences
negative), so the xpr:native ratio is *at least* ~170× under load. **The ordering and the ratio survive; the absolute
µs/row does not.** This is the concrete basis for §4.11's revised error band.

#### The mechanism the earlier draft named for B2's cost was wrong — the plan text settles it

B2's per-row cost at 1 M is 59 590 ÷ 1 000 000 = **59.6 µs/row**. The earlier draft attributed four `xpr.pdate_ms`
calls per row to `today()` "not being foldable because `xpr.now_ms` is `LANGUAGE sql STABLE`". **That is refuted by
the captured plan.** In `measurements.json → sizes.1000000.explain_B2` the executed `Filter` reads, in part:

```
xpr.pdate_ms(NULLIF((data -> 'due_date'::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb('2026-08-19'::text))
```

Counting occurrences in the captured plan text (mechanical, by this seat): the `Filter` node contains **4
`xpr.pdate_ms`, 0 `xpr.now_ms`, 0 `xpr.fmt_date_ms`** and 2 occurrences of the folded literal `'2026-08-19'`; the
`Sort Key` node contains **22 `xpr.pdate_ms`, 0 `now_ms`, 0 `fmt_date_ms`**, 11 folded literals and 11 field reads.
The generated SQL text (`generated_sql.B2`) carries 28 `xpr.pdate_ms`, 14 `xpr.now_ms`, 14 `xpr.fmt_date_ms`. So:

- **the clock chain IS folded at plan time.** `xpr.now_ms` is a single-statement SQL function (`runtime.sql:345-352`)
  and inlines; with `ctx` a client-side literal the result is constant, and `xpr.fmt_date_ms` (plpgsql, IMMUTABLE)
  then folds too. Live catalog check by this seat: of the 21 `xpr` functions, **`now_ms` is the only STABLE one;
  all 20 others are IMMUTABLE**, and `truthy` / `ord` / `f8` / `num` / `str` are `LANGUAGE sql`, not plpgsql.
- **what does *not* fold is `xpr.pdate_ms(to_jsonb('2026-08-19'::text))`, and the blocker is `to_jsonb`, which
  PostgreSQL marks STABLE** (live `pg_proc`: `to_jsonb` provolatile `s`). A STABLE argument makes the enclosing
  IMMUTABLE call non-foldable, so **half of the four `xpr.pdate_ms` calls per scanned row re-parse a constant date**.
- **the count of 4 stands; the cause does not.** 4 × 11.95 = **47.8 µs/row, 80% of the measured 59.6** — but that is
  now an arithmetic coincidence of the corrected mechanism, not evidence for the old one.

**The remainder is not "the scan and the sort" as the earlier draft said.** The `ORDER BY` re-emits the whole derive
**11 times** (22 textual `xpr.pdate_ms`) because the 3-key `_sort_key` tuple repeats it in every `CASE` arm; `CASE`
short-circuits, so on the order of 12–16 of those execute per **surviving** row, i.e. on 52 327 rows at 1 M ≈
**8–10 s, 13–17% of the 59 590 ms** (INFERENCE, from counting the plan text and applying the 11.95 µs/row constant —
no experiment isolates it). With 80% in the filter and ~15% in the sort there is almost nothing left for the scan,
which is consistent with the 502 ms floor of §4.4 being 0.8% of B2.

A direct per-function decomposition was attempted and **discarded, not reported** — it ran under host contention and
returned self-contradictory results: `probes.json → xpr_decomposition_100k_ms` shows adding `xpr.truthy` made the
query **faster**, `5_plus_xpr_ord` 25 065.86 ms → `6_plus_xpr_truthy` **14 072.30 ms (−44%)**, and the full filter
then measures 8 573.77 ms, below every step from 3 onward. (The earlier draft cited the wrong pair for this — step 7
is the full filter, not "step 5 plus truthy".) The inference is therefore **unconfirmed**; a quiet-host decomposition
plus one run with the constant `xpr.pdate_ms` hoisted out of the row loop would settle it.

#### A second per-row constant, free from the sweep: the cost of materialising the augmented document

B1 computes the derive **once** per scanned row and stores it; B2 computes it up to four times per scanned row — and
**B2 is faster at every size**. B1 − B2, per row scanned: **30.5 / 30.0 / 30.8 / 31.4 / 31.5 / 35.8 µs/row** at 1 k →
1 M (from the §4.4 medians). That is the cost of `data || jsonb_build_object(...)` — rebuilding a 283-byte jsonb
document — for **every** scanned row rather than only for the 5% that survive. It is as stable across three orders of
magnitude as the `xpr.pdate_ms` constant is, and it is why the "faithful" translation of `_apply_derive` is the wrong
shape even before the runtime is considered.

#### B2 vs B3 is a predicted null result, not evidence about indexing

The earlier draft wrote "the index is not the binding constraint while the runtime is", resting it on B3 cutting
`Rows Removed by Filter` from **947 673 to 546 670** while moving wall clock **+0.03%** (59 590.03 → 59 609.77 ms).
**The proof was invalid.** In B2 the planner already applies the cheap `(data -> 'status') = '"open"'::jsonb`
*before* the `xpr` chain — visible in the captured `Filter` clause, where the equality is the second conjunct and the
`xpr.truthy(...)` tree the third. So the `xpr` predicate runs on the same ~599 k `status=open` rows in **both** arms.
**B3's index removes zero `xpr` calls**; it removes ~401 003 cheap `->` comparisons. Equal wall clock is what should
be expected.

Measured directly by this seat, read-only, on `measure_instances_100000` (2 runs, load ~40):

| query | run 1 | run 2 | rows reaching `xpr.pdate_ms` |
|---|---:|---:|---:|
| `count(*) … AND xpr.pdate_ms(data->'due_date') IS NOT NULL` | 6 137.7 ms | 6 144.8 ms | 100 000 |
| the same, with `AND (data->'status')='"open"'::jsonb` first | 3 723.8 ms | 3 887.8 ms | ~60 134 |

Ratio **0.607 / 0.633** against the expected 60 134 ÷ 100 000 = **0.601** (the row count the GIN bitmap index scan
returns at 100 k, `explain_B3`). The cheap equality predicate is already doing the index's job. **What B2-vs-B3
therefore does NOT bound is what a different index shape could do** — an expression index on the derive would remove
`xpr` calls, which no index measured here does. That is finding #3's question, and §4.6 no longer answers it.

Neither arm went parallel at any size (no `Gather` node in any of the twelve captured plans).

#### Cross-read with `f3` §3.2 — the penalty is not "plpgsql", it is the date path

No section performed this cross-read and a recommendation turns on it. `f3` §3.2 ran nine *other* compiled `where`
predicates over a 200 000-row probe table (`proto/idxshape_plans.json`), all four index configurations producing the
identical plan. Dividing `f3`'s own published columns — rows scanned = `act` + `Rows Removed by filter`, over its
`exec ms` (minimum across the four configs) — gives a per-row cost per predicate shape. Arithmetic re-derived by this
seat directly from `idxshape_plans.json`, not read from `f3`'s prose. The "in the executed plan" column is a
mechanical count of the plan's own `Filter:` text, which matters because `LANGUAGE sql` helpers are **inlined** by
the planner (they vanish as calls and reappear as `CASE` towers that repeat the field read) while plpgsql helpers
stay opaque function calls:

| pred | expression | `xpr` **calls** left in the executed `Filter:` | field reads | rows scanned | exec ms | **µs/row** | vs W1 |
|---|---|---|---:|---:|---:|---:|---:|
| W1 | `$.status == "open"` | *none* — `truthy` fully inlined | 12 | 50 000 | 134.4 | **2.69** | 1.0× |
| W6 | `$.actor == "goms"` | *none* — same shape | 12 | 150 000 | 406.2 | **2.71** | 1.0× |
| W7 | `lower($.status) == "open"` | 1 × `truthy`; `str` inlined | 11 | 50 000 | 285.3 | **5.71** | 2.1× |
| W8 | `contains($.summary, "hold")` | 1 × `truthy` + **1 × `contains` (plpgsql)** | 1 | 150 000 | 870.5 | **5.80** | 2.1× |
| W9 | `$.actor=="goms" and $.risk_level=="high"` | 1 × `truthy`; two inlined towers | 24 | 150 000 | 969.4 | **6.46** | 2.4× |
| W2 | `$.score > 90` | 1 × `truthy`; `ord` inlined | 8 | 50 000 | 362.5 | **7.25** | 2.7× |
| W5 | `$.status=="done" or $.status=="blocked"` | 1 × `truthy`; two inlined towers | 24 | 50 000 | 417.2 | **8.34** | 3.1× |
| W3 | `$.score * 2 > 180` | 1 × `truthy` + 1 × `ord`; `num` inlined as a 4-arm numeric CASE | 7 | 50 000 | 1 149.2 | **22.98** | **8.5×** |
| W4 | `days_between(today(), $.due_date) < 7` | 1 × `truthy` + 1 × `ord` + **2 × `pdate_ms` (plpgsql)** | 1 | 50 000 | 3 285.0 | **65.70** | **24.4×** |

Two structural facts fall out of that column and matter for reading the µs: **inlining is not free but it is cheap**
(W1/W6 pay 12 field reads and no calls, for 2.7 µs/row), and **inlining stops the moment a plpgsql call enters the
argument** — W4 and W8, the only two rows with a plpgsql call, are also the only two whose `Filter:` text is short
(236 and 116 characters against 1 150–3 513) because PostgreSQL declined to inline the surrounding `LANGUAGE sql`
helpers at all.

**The date predicate costs ~24× an equality predicate on the same table in the same session** — and W4's 65.7 µs/row
is within 10% of this rig's B2 at **59.6 µs/row** for the same expression shape, on a different table, different
corpus and a different day. Two independent rigs agree on the level.

Reading the differences, which is where it localises:

- **The two `xpr.pdate_ms` calls cost 43–60 µs/row, i.e. ≈21–30 µs per call.** W4 − W2 = **58.45 µs/row** (W4 adds
  2 `pdate_ms` and an un-inlined `ord`, and drops 7 field reads ≈ 1.3 µs); W4 − W3 = **42.72 µs/row** (same `truthy`
  + `ord` call shape on both sides, so this end is a floor). W4's executed plan carries 2 `pdate_ms`, 0 `now_ms`,
  0 `fmt_date_ms` and one folded `'2026-08-19'` literal — **the same planner fold as B2**, on a different rig.
- **W8 − W6 = 3.09 µs/row** buys one `xpr.contains` call, **which is also plpgsql** (`proto/runtime.sql:358-359`),
  and it is the cleanest pair here: both are 150 000-row `LedgerRecord` scans returning 21 308 and 21 423 rows.
- **W3 − W2 = 15.73 µs/row** buys the numeric-coercion tower of `xpr.num` — `LANGUAGE sql`, inlined into a
  `CASE jsonb_typeof(...)` with a 1.79769e+308 overflow guard, no call left in the plan — plus one un-inlined `ord`.
- **W1 at 2.69 µs/row is almost entirely field reads**: 12 inlined `data->'status'` reads × the 0.18 µs/read the
  *other* rig measures (`runtime_microcost_ms` at 100 k: `plus_field_read − count_only` = 18.2 ms ÷ 100 000) ≈
  2.2 µs, plus a 0.08 µs/row scan = 2.3 µs. The two rigs agree to ~20% on a number neither was built to produce.

**So "plpgsql call overhead" is the wrong category, in both directions.** A plpgsql `xpr.contains` costs 3.1 µs per
call; a fully-inlined `xpr.truthy` tower that re-reads the field twelve times costs 2.7 µs/row *in total*; an inlined
`LANGUAGE sql` `xpr.num` tower costs 15.7; a plpgsql `xpr.pdate_ms` costs 21–30 — a **7×–10× spread inside the
runtime**, with the two date functions at the top and the language of implementation predicting nothing. The penalty is
concentrated in `xpr.pdate_ms` (and, before the planner folds them, `xpr.fmt_date_ms` / `xpr.now_ms`). Bare
comparisons are cheap; **arithmetic through the jsonb numeric tower is already 8.5×**, so a fix confined to dates
does not make the runtime cheap in general.

**Caveats, in place.** (i) Two rigs, two tables (200 000 × 452-byte rows vs 1 000 000 × 316-byte rows), different
collections and acknowledged host contention on both — every figure here is **order-of-magnitude**, not ±5%.
(ii) The subtractions assume a pair differs only in the named calls; the pairs also differ in how many rows they
*return* (W4 returns 16 071, W2 4 807). The control for that confound is W1 vs W2 on the same table: W1 returns
**more** rows (9 985) and costs **less** (2.69 vs 7.25), so output volume is not what these differences measure.
(iii) `f3`'s non-instrumented `median_ms` column gives the same picture at a higher level — W1 3.48, W4 66.48
µs/row, ratio **19.1×** rather than 24.4×; the ratio is the robust part, the level is not.

**The decision this changes.** *"Replace the runtime"* and *"fix the date path and stop re-parsing the folded
constant"* are **different recommendations with different costs**, and nothing measured licenses collapsing them.
The first is a rewrite of 21 functions plus re-qualification against all 130 fixture cases. The second is bounded:
two functions, plus arranging that the constant `today()` is not re-parsed per row (`to_jsonb`'s STABLE marking is
what defeats the planner there — above). **Neither is priced by this spike**, and per `FRAMING.md` §3 nothing was
attempted. What would establish the size of the second prize: one run of B2 with the constant
`xpr.pdate_ms(to_jsonb('…'))` hoisted to a scalar subquery, on a quiet host, against the same six tables — a
read-only re-run of an existing instrument, not new machinery.

---

### 4.7 `MAX_SCAN` is a correctness boundary, not a performance boundary

`sources.py:348-351` truncates the **raw** scan before `filters`, `where`, `sort`, `limit`:

```python
truncated = len(raw) > MAX_SCAN
if truncated:
    log.warning("dashboard source hit MAX_SCAN cap", {"type": stype, "scanned": len(raw)})
rows = raw[:MAX_SCAN] if truncated else raw
```

Ground truth is the compiled query run without `LIMIT` over the whole table, tiebreak on both arms
(`proto/bench.py:246-253`, `407-434`). `rank1_correct` is an **identity** test on the top row's `$.id`
(`proto/bench.py:430`), not on its value.

| rows | `truncated` | qualifying rows in table | rows Python examined | qualifying rows **never examined** | **top-50 recall** | rank-1 record correct? | row-for-row identity vs Path B |
|---:|:--:|---:|---:|---:|---:|:--:|---|
| 1 000 | no | 50 | 1 000 | 0 (0%) | **100%** (50/50) | yes | **IDENTICAL** (50 rows) |
| 10 000 | no | 510 | 10 000 | 0 (0%) | **100%** (50/50) | yes | **IDENTICAL** (50 rows) |
| 20 000 | no | 1 055 | 20 000 | 0 (0%) | **100%** (50/50) | yes | **IDENTICAL** (50 rows) |
| 25 000 | **yes** | 1 338 | 20 000 | **284 (21%)** | **88%** (44/50) | yes | not comparable — arms answer different questions |
| 100 000 | **yes** | 5 202 | 20 000 | **4 146 (80%)** | **38%** (19/50) | yes | not comparable |
| 1 000 000 | **yes** | 52 327 | 20 000 | **51 271 (98%)** | **4%** (2/50) | **NO** | not comparable |

- At **25 000** rows — 25% over the cap — 6 of the 50 displayed rows do not belong in the true top 50
  (`answer.path_a_ids_not_in_truth` lists `S-2202, S-2207, S-2265, S-2380, S-2862, S-4612`).
- At **100 000**, 31 of 50 displayed rows are wrong (62% of the answer).
- At **1 000 000**, 48 of 50 are wrong and the rank-1 **record** is not the true rank-1.
- **Degradation is monotonic across the six measured points** — 100% / 100% / 100% / 88% / 38% / 4%.

**Correction — the onset row is not measured, and the earlier draft asserted it.** The claim "degradation begins at
row 20 001, there is no safe margin above the cap" was stated as a measurement; it is not one. Nothing was measured
between N = 20 000 (recall 100%) and N = 25 000 (recall 88%); `measurements.json → sizes` contains no size in that
interval. Whether the answer degrades at 20 001 rows depends on whether the 20 001st row in physical order both
qualifies and ranks inside the true top 50 — **not established by this rig**. What is established: the smallest
over-cap size tested is 25 000, 25% over, and it already loses 12% of the answer. What would establish the onset: a
sweep of N over 20 001 … 25 000 on the existing harness.

**What the UI says while this happens.** `truncated` propagates untouched and renders as a badge reading
**`capped`**, tooltip **"Result capped for performance"** — `GIMS-Project/frontend/lib/dashboard/widgets.jsx:277`,
re-verified verbatim by this seat:

```jsx
{state.data?.truncated && <span className="w-trunc" title="Result capped for performance">capped</span>}
```

"For performance" is the part the numbers contradict: the answer is not late, it is different. The cap's stated
rationale (`sources.py:57-60`) is that "a pathological collection can't exhaust memory" — §4.4 shows it does not do
that either: `raw` is materialised in full before the slice, so peak RSS still reaches **2 765 MB at 1 M** while
Python-side work is frozen at 170 ms. The cap bounds evaluation, not allocation.

**Two qualifications, both against this seat's own result.** (i) Which 20 000 rows survive is whatever order the
store returned — `list_records` issues no `ORDER BY` (`gims-ledger/api/storage_aws.py:730`) — and here that physical
order correlates with `$.id`, which is also the tiebreak, so these recall figures are if anything **optimistic for
Path A**. (ii) The `never examined` column is a pure count and carries no such caveat. **These are counts, not
timings** — the only numbers here immune to the host-load caveat.

**(iii) Added at closure: these counts are exact for this corpus and say nothing about how often the cap is crossed
in production. [consistency]** The recall column is a function of the qualifying-row rate (5.00–5.35% here) against
the 20 000-row cap, and this corpus's `due_date` miss rate is **5%** against the **42.9%** `xd` D.7 measures on the
one real collection — §4.11 works the two opposing effects through and returns **not established** on the net
direction. **No real collection on this machine is over the cap**: the largest is **17 148 rows = 85.7% of
`MAX_SCAN`** and this widget's own collection is **7** (`xd` D.8, D.7). *What this section establishes is that the
cap silently changes the answer once crossed; that it is crossed today is not established here.*

---

### 4.8 The profile, in the RAG profile's own comment form

House style, `gims-ledger/core/storage/sql.py:240-251`: named phases with their row counts, a lever attribution, an
explicit identical-output check. Template from `recon/baseline.md` §2.4, filled with this sweep.

*(Citation dispute, resolved against the verifier: the verification record asserts the block runs to `:252`. It does
not — `awk 'NR>=239 && NR<=253'` on `gims-ledger@7b7a049` shows `:251` is the comment's last line, "profiling proving
the scan is the bottleneck, and it is not.", and `:252` is code, `_INDEXABLE_FIELDS = frozenset({...`. The original
`240-251` stands. `FRAMING.md` §4's `:242` and `analysis/measurement.md` §1's `:241-250` are both narrower than the
block.)*

```
# The dashboard widget's cap is a correctness cap, and the pushdown lever is the scan, not
# the evaluator (T-1 spike, measured 2026-08-19 on autosql_spike / pg16.14: one table per
# size, 283-byte JSON records, GIN jsonb_path_ops, the near-due widget of
# api/dashboard/sources.py:15-28 with the tests' null-guard, median of 9/7/3 reps).
#
#   at N = 10,000 (under MAX_SCAN):
#     acquire  54.4 ms (38%, 10,000 loaded) + evaluate 87.8 ms (62%, 10,000 evaluated, 510 kept)
#                                                            = 142.3 ms
#   at N = 1,000,000 (50x MAX_SCAN):
#     acquire 8,161 ms (98%, 1,000,000 loaded, 980,000 discarded unexamined)
#            + evaluate 170 ms ( 2%,    20,000 evaluated -- the cap -- 1,056 kept)
#                                                            = 8,331 ms
#     (server-side floor for the same scan: 54 ms to count 1,000,000 rows, 502 ms to touch
#      and serialise all 317 MB of them.  That 502 ms is the bound on what pushdown can win.)
#
#   compiled pushdown returns 50 rows / 16.1 kB instead of 1,000,000 rows / 317.0 MB -> 19,668x
#     with the prototype's xpr runtime:            59,590 ms   ->  7.2x SLOWER than Python
#     with native operators (UNSAFE, see below):      230 ms   -> 36.2x faster, row-for-row identical
#
# So the lever is right and the runtime is wrong -- but "the runtime" is too coarse.  The
# 99.6% gap between those two numbers is the COMBINED effect of five simultaneous changes,
# not of the runtime alone: ::date for xpr.pdate_ms, an inlined date literal for the ctx
# clock, jsonb `?` for the null test, a scalar sort key for the 3-key type-rank tuple, and a
# native `<` for xpr.truthy(xpr.ord(...)).  No experiment here isolates the runtime's own
# share of it.  What IS isolated, per compiled predicate over a 200,000-row table:
#     $.status == "open"                       2.7 us/row     (baseline: 12 inlined field reads)
#     contains($.summary, "hold")              5.8 us/row     (a plpgsql call: +3.1 us)
#     $.score * 2 > 180                       23.0 us/row     (numeric coercion tower: 8.5x)
#     days_between(today(), $.due_date) < 7   65.7 us/row     (two xpr.pdate_ms: +21..30 us each, 24x)
# The penalty is concentrated in the DATE functions, not in plpgsql as a category, and not in
# xpr as a category.  Half of the four xpr.pdate_ms calls per scanned row re-parse a CONSTANT:
# the planner folds now_ms/fmt_date_ms away but cannot fold pdate_ms(to_jsonb(const)) because
# to_jsonb is STABLE.  "Replace the runtime" and "fix the date path" are different jobs.
# The index is not the lever either, but B2-vs-B3 does not prove that: both arms already
# evaluate xpr on the same ~599,000 status=open rows (the cheap equality runs first), so the
# GIN cutting Rows-Removed-by-Filter 947,673 -> 546,670 for +0.03% wall clock is the PREDICTED
# result, not evidence.  An expression index on the derive was never measured.
# The native arm is NOT a proposal: ::date RAISES on a malformed date, which is the totality
# violation xpr.pdate_ms exists to prevent (expr.py:409-431, FRAMING.md section 5).
#
# And MAX_SCAN is not a performance cap: past 20,000 rows the in-memory widget answers a
# different question -- top-50 recall 100% / 88% / 38% / 4% at 20k / 25k / 100k / 1M, with 98%
# of qualifying records never examined at 1M and the rank-1 record wrong -- under a UI badge
# reading "Result capped for performance" (frontend/lib/dashboard/widgets.jsx:277).
```

---

### 4.9 Three results, not one story

They are all true at once and this section does not reconcile them.

**(1) Pushdown is the right lever.** At 1 M rows **98% of Path A's time is acquiring 980 000 records it never
examines** (§4.5); it holds ~2.4 GB of marginal Python heap and moves **317.02 MB** over the wire to return 16.1 kB
— **19 667.5×** more payload than needed (§4.4). Pushdown removes the whole 98%, not a share of it — the same shape
of conclusion the RAG profile reached, by the same method. **The measured ceiling on that removal is the 502 ms
server-side payload scan** (§4.4), 6.0% of Path A's 8 331 ms; the residue below it is client transfer and psycopg2.

**(2) The prototype's runtime is slower than today's path, at every size measured.** B2 is **3.79×–7.15× slower**
than Path A (4.15, 3.89, 3.79, 4.36, 6.71, 7.15 at 1 k → 1 M). No crossover in the measured range; the gap
**widens** with N. **3.79×–7.15× is the headline range and the only one this finding publishes**: it is the six
size medians of the sweep (`measurements.json → sizes.*.path_a/path_B2.total_ms` → 4.152 / 3.892 / 3.794 / 4.363 /
6.713 / 7.152), 9/9/9/9/7/3 repetitions per cell. **[consistency]** **Under the one load-controlled re-run in the
record the bottom of that range collapses by a third**: B2 ÷ A at N = 20 000 moves **3.79× → 2.55×**
(492.63 / 1 257.03) and at N = 1 000 **4.15× → 3.62×** (24.24 / 87.79) — `probes.json → recheck`. **That 2.55× is
not a headline figure and must not be quoted as one, here or downstream: it is a single re-run at two sizes, and the
`recheck` block has NO RETAINED PRODUCER** — nothing in `proto/` writes it (`probe_extra.py` writes only
`out["payload"]` and `out["poison"]`; verified again this pass by `grep -n 'out\[' proto/probe_extra.py`), so it can
be read but not audited or re-derived (§4.11). **[consistency]** The direction is stable across every observation; the multiplier is not.
The cause is localised to the `xpr` **date** functions (§4.6 cross-read) — not to plpgsql as a category, not to the
plan, not to the index, not to the scan.

**(3) A native-operator ceiling is far faster than either — and it is unsafe.** B4 runs the same widget in **229.99
ms at 1 M, 36.2× faster than Path A**, row-for-row identical to the compiled arm at all six sizes. It is **not
directly available**, for five separate reasons (§4.3 deviation 6): `::date` **raises** where `expr` returns `null`,
the violation `FRAMING.md` §5 forbids; it inlines `today()` as a literal instead of reading `ctx`; it substitutes
jsonb key-existence `?` for the compiled null test, and `?` is precisely the operator `jsonb_path_ops` does not
index; it drops the 3-key `_sort_key` type-rank tuple; and it replaces `expr`'s total cross-type ordering with a bare
`float8 <`. On this corpus none of the five is visible — `gen_data.py:31` never emits a malformed date and
`days_left` is always numeric.

**OPINION, labelled:** nothing measured here says whether a fast runtime is *achievable* while keeping `expr`'s
totality. B4 being 259× faster than B2 **bounds the size of the prize; it does not show the prize is collectable.**
The §4.6 cross-read narrows *where* the prize sits (two date functions, plus a constant re-parsed per row) without
showing it is reachable. Not established; §4.6 names the experiments that would settle it.

#### Fallback cost — what was measured is the TRIGGER, not the machinery

`FRAMING.md` §4 #5 requires "the cost of the fallback machinery". **This section does not supply that.** What it
supplies is the cost of *firing* a fallback, in the two places a fallback can fire, and the distinction is
load-bearing at the gate:

| | measured | what it is |
|---|---|---|
| **compile-time refusal** | **0.0307 ms** per widget request — **0.0004%–0.22% of Path A**. Composition, re-derived by this seat: `fallback.plan_ms` = **0.026605 ms** is exactly parse 0.008845 + 0.010212 and compile 0.002780 + 0.004768, and **excludes** `detect_uncompilable_ms` **0.004079**; the earlier draft quoted `plan_ms` alone as the refusal cost, which understates it by 15% | the cost of *deciding not to push down* before any SQL runs. Free, on any scale that matters |
| **run-time refusal** | **unbounded**; the unguarded `float8_overflow_raises` case aborts mid-scan (SQLSTATE `22003`) after **40.76 ms with `synchronize_seqscans=on` vs 6 916.85 ms with it off — a 170× spread on the identical query and table** (`probes.json → poison_syncscan`). Worst case is a wasted scan **plus** a whole Path A: 6 917 + 1 494 = **8 411 ms vs 1 494 ms, +463%**. The wasted scan is itself slower than a successful full B2 scan of that table (6 496 ms) | the cost of *discovering* mid-query that the push was wrong, and starting over in Python |

**Three qualifications, all against this seat's own figures.**

1. **The +463% is a construction, not one observed event.** It sums `poison_syncscan.off.median_ms` 6 916.85 and
   `poison.path_a_after_raise_ms` 1 493.92 — two probes run separately, under different host load. It is a
   legitimate worst-case composite and is labelled as one here; the earlier draft headed it "measured". The Path A
   term is itself **66% above** the 899.26 ms the same 100 000 rows measured in the sweep (§4.4).
2. **These figures bound only the RAISE classes.** A run-time fallback can only fire where the database raises.
   `f2` §2.8 finds five divergence classes (R2–R5, R7) that are **silent by construction** — the SQL succeeds and
   returns a different value — and `critic` §1 maps thirteen of `f1`'s twenty-three confirmed classes to no fallback
   rule at all. **For a silent class there is nothing to trigger, so 0.0307 ms and +463% do not bound its cost.**
   Its cost is a wrong number on a dashboard, which this rig cannot price.
3. **The standing cost of the machinery itself is not established by this spike.** Nothing here prices a third
   runtime kept in lockstep with `expr.py` and `frontend/lib/expr.js` against a 130-case contract fixture, nor the
   `pushed_down`/`fallback` return-contract change and the six other items `f2` §2.8 names. That is a scoping
   estimate, not a measurement, and `FRAMING.md` §3 forbids this pass from producing it. What would establish it:
   sizing `f2` §2.8's change list against the three call sites in `sources.py:353-356` and the widget contract in
   `frontend/lib/dashboard/widgets.jsx` — a design task for `sp-synth`, not a measurement.

---

### 4.10 Cross-check: where the raw data disagrees with `analysis/measurement.md`

Every headline number in the source document was re-derived from `analysis/measurements.json` /
`analysis/probes.json`. **All six wall-clock rows, all six recall rows, both payload columns, the six per-row µs
figures, all six ratios, the `Rows Removed by Filter` pair and the 99.6% / 0.03% / +37% figures reproduce exactly**
(their *interpretation* is corrected in §4.0(c), §4.6 and §4.8 — the arithmetic was never in doubt). Ten items do not
reproduce, listed worst first. Raw data wins.

| # | Claim in `analysis/measurement.md` | What the raw data says | Material? |
|---|---|---|---|
| 1 | §7: at 1 M "**the top row itself is wrong** — the single number a `value` widget would render … is not the correct one" | `rank1_correct: false` is an **identity** test on `$.id` (`bench.py:430`). The top-row *value* agrees: `best_days_left_path_a` = `best_days_left_truth` = **−30.0 at all six sizes** | **Yes** — the stronger reading (a `value` widget shows a wrong number) is **not established** by this rig |
| 2 | §10.1: "`EXPLAIN (ANALYZE, BUFFERS)` shows `shared hit` with **no `read`** at every size" | False at the two largest sizes: 100 k B2 `shared hit=1042 read=4294 written=27`; 1 M B2 `shared hit=8820 read=44772`. True only at 1 k–25 k. §5.5 of the same document states the 1 M figure, so the document contradicts itself | **Yes** — it weakens the "everything is warm-cache" caveat exactly where it matters |
| 3 | §5 preamble: "every cell is a median over the repetition count in §4" | §5.4's per-row isolation is **median of 5** at every size (`bench.py:491-494`), not 9/7/3 | Yes, for provenance |
| 4 | §10.11 re-run: B4 at N = 1 000 "+55%" | 1.14 → 1.70 = **+49%**. (+55% follows from the rounded 1.1, not the raw value.) Path A at N = 1 000 "+76%" is **+75%** (13.84 → 24.24) | Minor |
| 5 | §10.11: "`uptime` … read `load average: 13.64, 18.04, 15.17`" | That triple is in neither JSON. `probes.json → recheck` records **13.79 / 17.92 / 15.16** at start and **14.40 / 17.78 / 15.17** at end | Minor — prose-only, uncitable |
| 6 | §4, §10.3: `psycopg2.connect()` took **7.6 ms** | `measurements.json → connect_ms` = **7.1**. (**INFERENCE:** `bench.py:583-591` merges only `sizes` across the two invocations and overwrites the rest, so a first-chunk 7.6 would have been replaced by the second chunk's 7.1) | Minor — excluded from both arms |
| 7 | §3: `filters` + `where` keep "~5.1%" | Measured range **5.00%–5.35%** (5.00, 5.10, 5.28, 5.35, 5.20, 5.23) | Minor |
| 8 | §8.1: `expr.parse(derive)` 0.0085 ms; `compile_ast(where)` 0.0050 ms; total 0.0264 ms | 0.008845, 0.004768, **0.026605**. The downstream "26 µs" claim stands | Immaterial |
| 9 | §1: the RAG profile is at `core/storage/sql.py:241-250` | The comment block spans **240–251** (verified live, and re-verified against the verification record's competing `:252` — see §4.8). `FRAMING.md` §4 cites `:242` | Immaterial |
| 10 | §8.2 supersedes the first poison measurement (33 ms) with the syncscan-controlled one and says so | `probes.json → poison` **still carries the superseded values** `time_to_raise_ms: 33.3`, `total_fallback_ms: 1527.22`, `overhead_pct: 2.2`. A reader who opens the raw file first gets +2.2%, not +463% | Yes, for anyone re-deriving |

---

### 4.11 What this finding does not establish

- **The error band is not one band. Split it by what the number is bound by.** The earlier draft said "absolute
  milliseconds are ±50–75%"; that is refuted in both directions by re-measurement. **CPU-bound per-row costs are the
  fragile ones**: this seat's re-check of `xpr.pdate_ms` at 100 k moved **+246% … +282%** at load 29 (§4.6), and the
  verification record's independent re-check at 1 M moved **+184% … +278%**. **Scan- and IO-bound costs are the
  robust ones**: `plus_field_read` +21% … +50%, B4 at 1 M +13% … +31%, and the record's own controlled re-run moved
  B2 at N = 20 000 only **+10.4%** (1 138.61 → 1 257.03), *below* the old band's floor. **Ratios move less than
  levels, but not negligibly** — `A ÷ B4` 22.75× → 22.10× and 12.14× → 14.26×, while `B2 ÷ A` moves 3.79× → 2.55×, a
  **33%** reduction in the single multiplier a decision-maker would quote (§4.9(2)) — **that 2.55× being one
  load-controlled re-run at N = 20 000 out of an un-audited `recheck` block with no retained producer (next bullet),
  which is why the headline range stays 3.79×–7.15×** **[consistency]**. §4.7 is counts, unaffected.
- **Three raw blocks have no reproducible producer.** `proto/probe_extra.py` writes only `out["payload"]` and
  `out["poison"]`. Nothing retained in `proto/` produces `probes.json → xpr_decomposition_100k_ms`,
  `poison_syncscan`, or `recheck` — so those three can be read, but not audited or re-derived, and every claim
  resting on them (§4.6's discarded decomposition, §4.9's 170× syncscan spread and +463% composite, §4.11's band)
  inherits that. **Not established:** that they were produced by the code described. What would establish it:
  retaining the probe scripts, which this pass may not write.
- **Two provenance claims are asserted, not established** (§4.0): that `glp_strong` was never opened, and that
  `compile.py`/`runtime.sql` were unmodified by the measuring seat. Both files are untracked, so no diff exists.
- **The corpus's `due_date` miss rate is 8.6× below the one real collection's, and that is no longer a generic
  caveat — the number exists. [consistency]** This corpus omits `due_date` on **5%** of rows (`gen_data.py:30`);
  `xd` D.7 measures **42.9% (3 of 7)** on the only real dashboard's own `Submission` collection — **8.6×**. (`xd`
  D.7 compares itself only to `f3` / `index-shape.md` §1.2's 8% generator, so this pairing is stated here for the
  first time.) Applied to the three families of figure this section publishes:
  - **Selectivity — net direction NOT ESTABLISHED, because two legs push it opposite ways.** *Down:* the widget's
    `$.days_left != null` conjunct rejects every row with no parseable `due_date`, so raising absence from 5% to
    42.9% removes rows that currently qualify — the measured `qualifying_rows_total ÷ N` of **5.00 / 5.10 / 5.28 /
    5.35 / 5.20 / 5.23%** (`measurements.json`) is computed over a population where **95%** of rows carry a date.
    *Up, and harder:* the four real rows that **do** carry `due_date` are `2026-07-02 / 07-04 / 07-05 / 07-10`
    (`xd` D.7's table), all **before** the pinned `now` of 2026-08-19, so `days_left` is negative and this section's
    `< 7` predicate would hold on **4 of 4** — where this generator spreads `due_date` uniformly over −30…+370 days
    and keeps "~9% before the status filter, ~5.5% after it" (`gen_data.py:28-29`, corroborated by the measured
    5.0–5.35%). (That is **this** widget's predicate applied to those rows; the real dashboard's own `where` is
    `$.status == "in progress"` and does not test `days_left` at all — `xd` D.7.) **INFERENCE: on n = 4 the real
    date distribution is nothing like the generator's, and it moves selectivity up by about an order of magnitude
    where the miss rate moves it down by well under a factor of two — so the up leg dominates.** No corrected
    selectivity is offered: samples of 7 and 4 rows do not support one, and no run of any corpus but the 5% one
    exists.
  - **Derive cost — both arms fall, and the *ratio* moves less than either level (INFERENCE, not measured).** An
    absent key short-circuits before any parsing on **both** sides: `expr.py:411-412` returns `None` on a non-`str`
    value, and `runtime.sql:272` returns `NULL` when the jsonb is null or not a string — the SQL function's own
    comment cites that Python line. The saving is proportionally the same on both arms: Path A skips **1 of the 2**
    `_parse_date_ms` calls `days_between` makes per row (both args are parsed eagerly, `expr.py:472`), and B2 skips
    **2 of the 4** `xpr.pdate_ms` calls per scanned row, the other two being the folded constant (§4.6). So a
    42.9%-absent corpus lowers Path A's 7.25–7.48 µs/row derive and B2's 59.6 µs/row together, and **§4.9(2)'s
    3.79×–7.15× is the figure least disturbed by this difference**. Magnitude **not established** — nothing was
    re-run at any other miss rate.
  - **Recall (§4.7) inherits selectivity's direction, so it too is not established**, and one bound is worth stating
    plainly: recall degrades only once qualifying rows exceed what 20 000 scanned rows contain, and **no real
    collection on this machine reaches the cap at all** — the largest is 17 148 rows, 85.7% of `MAX_SCAN` (`xd`
    D.8), and this widget's own collection is **7**. §4.7's 88% / 38% / 4% cliff is a property of the synthetic
    sweep; that any production collection is past the cap today is **not established** (`xd` D.8 gives 0.8–3.5 days
    of headroom at observed growth rates, which is the nearest thing to an answer).
- **Untested:** cold buffer pool; concurrency (one connection throughout — Path A's cost is per-request Python heap,
  Path B's per-request database CPU, and they do not degrade alike); selectivity, held constant at ~5.2%, the
  single biggest lever on both arms, and now known to be modelled on a `due_date` miss rate 8.6× below the one real
  collection's (previous bullet); anything beyond 1 M rows; the onset of `MAX_SCAN` degradation between 20 000
  and 25 000 rows (§4.7); the LIMS-System widget's *timing* (§4.1); an expression index on the derive (§4.6); and
  whether a total-**and**-fast SQL runtime exists at all (§4.9, OPINION).
- **One widget measured, one synthetic corpus.** The representativeness warrant is now "documented in the codebase
  **and** matched in shape by the one real tenant widget on this machine, n = 1" (§4.1) — still not a distribution.
- **Two correctness items outside `compile.py`'s contract**, surfaced by this rig and recorded as measurement facts
  only: the obvious jsonb-equality `filters` pushdown **silently dropped 2 of 3 rows** that `sources._field_value`'s
  tolerant key matching keeps (`measurements.json → tolerant_key_probe`: `path_a_ids ["T-1","T-2","T-3"]` vs
  `path_b_ids ["T-1"]`; keys `"status"` / `"Status"` / `"status "`) — this one **is** in the raw data and reproduces
  exactly; and a compiled `sort` on a non-unique key is nondeterministic where Python's stable `sorted()` is not —
  this one is **prose-only** (`analysis/measurement.md` §9.2), with no corresponding record in `measurements.json`
  or `probes.json`, and the earlier draft called both "measurement facts". Both belong to the conformance and
  coverage seats; per `FRAMING.md` §3 they are recorded, not chased.

---

### 4.12 Verification ledger — what changed in this section, and what did not

Thirteen corrections were raised against the first draft. Twelve applied, one rejected. Every applied correction was
checked against the raw source it names before being written; none of the twelve was found wrong.

| # | sev | correction | where applied |
|---:|---|---|---|
| 1 | material | the `sources.py` docstring example does **not** match the measured widget's `where` | §4.1 clause table |
| 2 | material | the full-pipeline test's `where`/`limit` differ (`!= null`, `1`) — widget is an assembly, not a quotation | §4.1 clause table |
| 3 | material | "every Path A number is a lower bound" is false at N = 1 000 (−2%) | §4.3 dev. 1, §4.5 |
| 4 | material | B2-vs-B3's null result is **predicted**, not proof about indexing — both evaluate `xpr` on the same ~599 k rows | §4.6, re-measured live by this seat |
| 5 | material | "~99.6% is plpgsql call overhead" is an inference in a comment block meant for the codebase | §4.8 block rewritten; §4.6 cross-read localises it |
| 6 | material | the EXPLAIN pair is not uniform instrumentation inflation (+36.8% / +7.9%, and B3 21% *faster* under EXPLAIN) | §4.0(c) |
| 7 | material | "degradation begins at row 20 001" was never measured | §4.7 |
| 8 | material | "±50–75%" is one band for two kinds of number | §4.11, with this seat's own re-check |
| 9 | material | the recheck was reported in the softer ratio form (`A ÷ B2`), not the headline's (`B2 ÷ A`) | §4.9(2), §4.11 |
| 10 | material | three `gen_data.py` citations off by 4–5 lines, one of them load-bearing | §4.2 |
| 11 | cosmetic | the decomposition's "truthy made it faster" cited the wrong pair (step 7, not step 6) | §4.6 |
| 12 | cosmetic | six line citations off (`bench.py:571`→`563-564`, `:180-181`→`175-179`, `extra_float_digits` not in `pg`, `sources.py:6-7`→`7-8`, `load_data.py:13-20`→`10-17` and not byte-identical) | §4.0, §4.2, §4.3 |
| 13 | cosmetic | 10 k relation size is 8 216 kB, not 8 256; the COPY/GIN-build seconds exist in no artifact | §4.2 |

**Rejected, with evidence: correction 12's claim that the RAG profile comment "runs to `sql.py:252`".** It does not.
`gims-ledger@7b7a049`, `core/storage/sql.py:251` is `# profiling proving the scan is the bottleneck, and it is not.`
and `:252` is `_INDEXABLE_FIELDS = frozenset({"proposal_slug", …` — code, not comment. The section's original
**240–251** is correct and is retained (§4.8). Every other item in correction 12 was confirmed and applied.

**Folded in from the verification record's "raw data the fragment omits" list**, none of which was in the first
draft: the `sizes.*.floor` scan floor (§4.4 — 54 ms to count 1 M rows, 502 ms to serialise all 317 MB, the tighter
bound on the prize); the `ORDER BY`'s eleven re-emissions of the derive and the 22 textual `xpr.pdate_ms` in the
1 M sort key (§4.6); B4's fifth semantic difference, `xpr.ord` → native `<` (§4.3 dev. 6e); the `truncate` phase
missing from the §4.5 table (0.29/0.33/0.36 ms); `reltuples` = 999 634 on the 1 M table (§4.2); the `LANGUAGE
sql`/plpgsql and IMMUTABLE/STABLE split across the 21 `xpr` functions (§4.6, re-read live from `pg_proc`); and the
+463% figure being a two-probe composite rather than one event (§4.9).

**Found by this seat during the re-check, in neither the verification record nor the critique:** (a) the earlier
draft's mechanism for B2's four `xpr.pdate_ms` calls — "`xpr.now_ms` is STABLE so `today()` cannot be folded" — is
refuted by the captured plan, which contains **zero** `now_ms` and `fmt_date_ms` and a folded `'2026-08-19'` literal;
the real blocker is `to_jsonb`'s STABLE marking (§4.6). (b) `fallback.plan_ms` **excludes** `detect_uncompilable_ms`,
so the compile-time refusal costs **0.0307 ms**, not 0.0266 (§4.9). (c) B1 − B2 is a second stable per-row constant,
30–36 µs/row, the price of rebuilding the jsonb document for every scanned row (§4.6). (d) The `LANGUAGE sql`
helpers are inlined out of the executed plan entirely, and inlining stops as soon as a plpgsql call enters the
argument — which is why W1 pays 12 field reads and W4 pays 1 (§4.6 cross-read).

**Gaps assigned to this section and their status:** critic §11 (localise the 259× prize) — **closed**, §4.6
cross-read, with its order-of-magnitude caveat and the two-recommendations conclusion. Critic §14 (connect the real
LIMS-System widget to the representativeness gap) — **closed**, §4.1, including the direction of the difference.
Critic §12's measurement half (fallback cost) — **closed as far as the evidence reaches**: the trigger cost is
stated as a trigger cost, its blindness to the silent classes is stated, and the machinery's standing cost is marked
**not established by this spike** with the one step that would establish it (§4.9). Critic §12's other half — the
third-runtime maintenance obligation — is a scoping estimate and belongs to finding #5.

**Compliance. [consistency]** Split by what is verifiable, because not all of this section's work is.

- **This closure pass (the edits marked `[consistency]`) was read-only and opened no database connection.** Read and
  not written: both GIMS trees, `spikes/T-1/{recon,proto,analysis}/`, `FRAMING.md`, the other `.parts/` sections,
  `.autodev/` and `kb/`. The only file written is `spikes/T-1/.parts/f4.md`. No Postgres object was created, altered
  or dropped; no defect was fixed; nothing in `proto/` was touched — `probes.json`'s three producer-less blocks stay
  producer-less (§4.11) because retaining a producer would be a write.
- **The revising seat's re-checks were reads, but they were reads that cost server CPU** and are declared as such:
  `SELECT version()`, `pg_total_relation_size`, `pg_class.reltuples`, `pg_proc.provolatile`, `SHOW
  max_parallel_maintenance_workers`, `docker exec glp-strong-db df -h /dev/shm`, and the timed re-runs of §4.6's four
  micro-cost queries and the two B2-vs-B3 predicate queries against `measure_instances_100000`. All `SELECT`/`SHOW`;
  **no DDL, no DML, no `EXPLAIN (ANALYZE)` on a writing statement**.
- **The measuring seat's work was NOT read-only, by design, and its objects were NOT rolled back.** `proto/load_data.py`
  issues `DROP TABLE IF EXISTS` / `CREATE TABLE` / `COPY` / `CREATE INDEX … GIN` / `VACUUM ANALYZE` for each of six
  `measure_instances_<N>` tables (`load_data.py:10-35`) in the spike's own scratch database `autosql_spike`
  (`load_data.py:8`, DSN) — which is what `FRAMING.md` §7 licenses ("The spike creates its **own scratch
  database**"). Those six tables are **still live** and were re-read this pass (§4.2, sizes 968 kB → 700 MB); nothing
  requires their removal, and removing them would itself be a write.
- **Not attestable from the artifacts, and stated rather than glossed:** that `glp_strong` was never opened, and that
  `compile.py` / `runtime.sql` were unmodified while the sweep ran. Both are asserted in `analysis/measurement.md`
  §11 and both files are untracked, so **no diff exists** (§4.0, §4.11). This attestation does not cover them.
- **Neither GIMS tree was written by this section — but neither was static during it.** Verified read-only this pass:
  `GIMS-Project` HEAD `995cc59`, `gims-ledger` HEAD `7b7a049` (the `FRAMING.md` §7 values). `GIMS-Project`'s 8 dirty
  paths all predate the spike (six 2026-08-13, one 2026-07-03, one 2026-06-28). `gims-ledger` carries **9**, two of
  them dated **2026-08-19**: `backups/_config/schedules.json` (10:40:07, ten minutes before `sp-investigate` opened)
  and the untracked `projects/guts/verbs/ingestion/data_dumps/`, whose `decompose-*` output directories carry mtimes
  of **11:22, 12:20, 12:25, 12:38, 12:58, 14:04, 14:10, 14:16 and 14:32** — i.e. **a live GIMS application was
  writing into `gims-ledger` across the sweep window** (`bench.py` 11:57 → `measurements.json` 12:27). Those
  directories hold `adverbs.json` / `Instructions.md` / `Status.json` / `DataEntry.json`, which no `spikes/T-1`
  instrument produces, so **INFERENCE: none of it is this spike's** — for the closure pass that is direct (it opened
  no file for writing); for the measuring and revising seats it is mtime evidence, not a diff. This is the same
  concurrent writer `xd` D.1 observed on the ledger itself (17,145 → 17,148 rows in six minutes). **INFERENCE, not measured:** it is a named candidate for the uncontrolled host load that §4.6 and §4.11
  make the largest error term in this section, and it means the sweep's own load condition is not merely unrecorded
  (§4.6) but was **not quiet**. What would establish the size of that term: the re-run §4.6 already names, on a host
  with the GIMS application stopped.

---

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

---

## Cross-cutting B — `filters`, `sort` and `limit`: the half of the question with no evidence

*(Closure pass; closes critic gaps 4 and 15. Every number is re-derived from a raw spike artifact or measured
this pass by a read-only re-check of an existing instrument. Nothing below is fixed — FRAMING §3 forbids it;
each defect is recorded with cause, blast radius and direction.)*

*(**Compliance** — extended here to the form `f2`, `xd` and `f5` use. **[consistency 23]** Read-only throughout:
both GIMS trees, `proto/`, `analysis/`, `recon/`, `FRAMING.md`, `.autodev/` and `kb/` were read and not written;
the only file written is this one. Every SQLite connection carries `mode=ro&immutable=1` (B.4, and the
re-derivation in the unit note below). No defect is fixed and no grammar redesigned. **What is attestable and what
is not:** the committed instrument re-run in B.6, `proto/idxshape_sort_semantics.py`, was verified this pass to
contain no `CREATE`/`ALTER`/`DROP`/`INSERT`/`UPDATE`/`DELETE` — `SELECT`-only against the scratch db
`autosql_spike`, so no Postgres object was created, altered or dropped and nothing required rolling back. The
one-off `::jsonb` probes reported in B.4-B.6 ran in the session scratchpad and were **not retained**, so their
read-only character rests on this attestation rather than on an artifact a reader can open; the scratch db
`autosql_spike` is the spike's own, not `glp_strong` (FRAMING §7).)*

*(**Punch pass addendum. [punch]** The `[punch]`-marked edits in B.4 were made in a later pass whose only writes
were to this file. That pass re-censused all three `gims-ledger` stores read-only — `sqlite3.connect("file:…?
mode=ro&immutable=1", uri=True)`, `SELECT count(*)` / `SELECT collection, count(*)` / `SELECT data` only, no
`-wal` or `-shm` opened — and re-read the spike's own retained sweep output `xd_sweep.json` from the earlier
session's scratchpad. `core/deep_search.py`'s `_norm_key` was imported from `GIMS-Project` as the oracle, exactly
as the original census did; that import reused the **pre-existing** `core/__pycache__/deep_search.cpython-312.pyc`
(mtime **2026-06-26**) and **no `.pyc` in either GIMS tree carries an mtime inside this pass's window** — both
trees hold only the pre-existing dirty entries `xd` D.11 records. **No Postgres connection was opened at all**,
nothing was written to any database, and no defect was fixed (FRAMING §3); the working script lives in the session
scratchpad, outside the repository. **What this pass could not re-verify, said plainly:** the **14:16:56** mtime in
B.4 is the checkpoint's own timestamp, read live while it was still that store's last checkpoint — `guts-ledger`
has since been checkpointed again (mtime **16:15:17**), so it is no longer re-readable from the file. What this
pass did verify independently brackets it on both sides: `xd_sweep.json` holds `LedgerRecord` 17 145 and was
written at 14:16:57, and `xd` D.1's 14:20 read holds 17 148.)*

### B.1 Why this section exists

FRAMING §1 asks whether `sources.py` can push **`derive` / `where` / `sort` / `limit`** into the database.
`derive` and `where` reduce to `expr` evaluation and are the subject of findings 1–2. **`filters` and `sort` do
not**: their semantics live outside `expr.py`, in three helpers in `GIMS-Project/api/dashboard/sources.py`. f2's
census is a census of `expr.py`'s grammar (f2 §2.1: 48 constructs) and contains none of them. Measured this pass
(`grep -c` over `.parts/f1.md…f5.md`): `_pass_filters` **0 hits in all five sections**, `find_actual_key` **0 in
all five**, `_field_value` 0/0/0/**1**/0, `_sort_key` 0/0/3/3/1. Over the prototype, `proto/compile.py` has
**0** hits for `filters`, `limit`, `_field_value`, `find_actual_key`, `derive` (its one `sort` hit,
`sorted(params.items())` at `compile.py:453`, is unrelated), and `proto/conformance.py` /
`proto/coverage_probe.py` have 0 for all four. **Nothing in the prototype models `filters` or `sort`;**
`bench.py` hand-writes one `filters` clause and one sort emulation for one widget, and nothing tests either.

### B.2 The exact semantics, as written

**`_field_value(row, key)` — `sources.py:67-85`.** Total, never raises. `:70-71` non-dict row or non-str key →
`None`; `:72-73` **exact** key → `row[key]`; `:74-76` else `find_actual_key(row, key)` — **tolerant**, first hit
wins; `:77-84` else, if `"." in key`, walk the dotted path, any miss → `None`; `:85` else `None`.
`find_actual_key` (`core/deep_search.py:29-39`) iterates `obj.keys()` **in dict order** and returns the first
`k` with `_norm_key(k) == _norm_key(desired)`; `_norm_key` (`deep_search.py:19-26`) is `str(k).lower()` with
every `" "`, `"_"` and `"-"` deleted.

**`_pass_filters(row, filters)` — `sources.py:88-96`.** Conjunctive; each `key → want` fails the row if
`_field_value(row, key) != want` (`:94`) — **Python `!=`, on Python objects**. Absent/empty `filters` passes
(`:91-92`); a missing field yields `None`, so it fails unless `want is None`; non-Mapping `filters` → 400
`DASHBOARD_FILTERS_INVALID` (`:153-155`).

**`_sort_key(value)` — `sources.py:99-115`.** A 3-tuple `(rank, float, str)` giving a total order that never
compares across types. Re-derived this pass: `False`→`(0,0.0,'')`, `True`→`(0,1.0,'')` (rank 0 = bool);
`2.5`→`(1,2.5,'')`, `5`→`(1,5.0,'')` (1 = number); `'Zebra'`→`(2,0.0,'Zebra')`, `'apple'`→`(2,0.0,'apple')` (2 =
string); `[1,2]`→`(3,0.0,'[1, 2]')`, `{'a':1}`→`(3,0.0,"{'a': 1}")` (3 = other, **keyed on Python `str()`**);
`None`→`(4,0.0,'')` (4 = null last).

**`_apply_sort` — `sources.py:168-177`.** Key is `_sort_key(_field_value(r, str(field)))` — **the sort field
goes through the same tolerant resolution as a filter**. `dir` is matched case-insensitively against `"desc"`
(`:176`); everything else ascends. `sorted(..., reverse=descending)` is **stable both directions**: measured,
five rows tied on the key return `r0…r4` for `asc` *and* `desc` — the fact `bench.py:385-389` states, and the
reason the bench bolted a `TIE` column (`bench.py:178-179`) onto every arm before rows could be compared.

**`_apply_limit` — `sources.py:180-187`.** `int(limit)`; `TypeError`/`ValueError` → **all rows**; `n < 0` →
**all rows**; else `rows[:n]`. Measured on 5 rows: `None`→5, `2`→2, `0`→0, `-1`→**5**, `"3"`→**3**,
`"abc"`→**5**, `2.9`→**2**, `True`→**1**. Pipeline order is fixed at `sources.py:353-356` (derive → filter →
sort → limit) over rows already truncated to `MAX_SCAN = 20_000` at `:348-351`.

### B.3 `filters`: the tolerant-key divergence — verified, cause, blast radius

**Verified.** `analysis/measurements.json → tolerant_key_probe` reproduces. Three records —
`{"id":"T-1","status":"open",…}`, `{"id":"T-2","Status":"open",…}`, `{"id":"T-3","status ":"open",…}` — under
`filters: {"status":"open"}`: Path A (Python `_pass_filters`, `sources.py:88`) returns `["T-1","T-2","T-3"]`;
Path B (compiled `(data -> 'status') = %(fstatus)s::jsonb`, `bench.py:226`) returns `["T-1"]`; `agree: false`,
`rows_only_python_finds: ["T-2","T-3"]`, `rows_only_sql_finds: []`. Re-derived independently by calling
`_pass_filters` directly: `T-1/T-2/T-3` all `True`, `_field_value` returns `'open'` on all three, `"status" in
row` **false** for T-2 and T-3.

**Cause.** `_field_value` stage 2 (`sources.py:74`) → `find_actual_key` → `_norm_key`. The SQL is exact-key by
construction; `bench.py:352` says so in a comment (*"compile.py models expressions only, so a compiled `filters`
clause is EXACT-key"*). Not a `compile.py` bug — `compile.py` never claimed `filters`. It is **a clause with no
compiler at all, whose obvious one-line pushdown is silently wrong**. **Direction: silent, toward
under-reporting** — SQL returns a strict subset; the widget shows fewer rows and no error. Under FRAMING §5 and
the §4 NO-GO bar that is disqualifying for a `filters` pushdown. It was never scored: no harness in this spike
has a `filters` case.

**Blast radius.** `_norm_key` lowercases and deletes ASCII space, `_`, `-`. Measured against desired key
`status`: **matched** (SQL exact-key misses each) — `Status`, `STATUS`, `status `, ` status`, `stat us`,
`st-atus`, `st_atus`, `s_t-a t u s`, `Status_`, `-Status-`; **not matched** — `statu\ts`, `statu\ns`
(tab/newline are not stripped), `státus`, `ｓｔａｔｕｓ` (no Unicode folding). The trigger set is exactly **any
difference in ASCII letter case, spaces, underscores or hyphens** — `run_ID` vs `run id` vs `runid` vs `RunID`,
the normal spelling drift of tenant-authored column names. GIMS treats it as **contract, not accident**:
`tests/test_dashboard_sources.py:169-177` (`test_tolerant_and_dotted_field_access_in_filters`) asserts `filters:
{"sample_id": "S-1"}` matches a record keyed `"Sample ID"`, and `filters: {"nested.ph": 6.9}` resolves a dotted
path — so a pushdown that drops tolerant matching breaks a locked upstream test.

### B.4 `filters`: tolerant matching is *ambiguous*, and the ambiguity is in real data

`find_actual_key` returns the **first** key in dict-iteration order that normalises to the target, so when two
keys of one record normalise the same, the answer depends on JSON key order — measured:
`{"Status":"open","status_":"closed"}` → `_field_value(row,"status")` = `'open'`, the same two keys inserted in
the other order → `'closed'`. Not hypothetical; read-only census of the live ledger stores
(`gims-ledger/projects/*/objects.db`, `mode=ro&immutable=1` — the instrument `analysis/index-shape.md §1.2`
already used):

| store / table | dict rows | rows with ≥1 key where `_norm_key(k) != k` | **rows with two keys normalising the same** |
| --- | --- | --- | --- |
| `guts-ledger/instances` | **17 345** *(17 342 one checkpoint earlier; see the unit note)* | 17 345 (100%) | **4 166 (24.0%)** |
| `guts/instances` | 12 095 | 12 095 (100%) | **1 966 (16.3%)** |
| `guts-code/instances`; the three `*_verb_log` tables | 6 710; 197 / 288 / 196 | 100% | 0 |

*(Unit, because the body carries four different ledger row counts: these are **table-wide** — every collection in
that store's `instances` table, **not** `LedgerRecord` alone — whereas `xd` D.2 counts the same bytes per
`(table, collection)`. They reconcile by summation, re-derived read-only this pass with the same
`mode=ro&immutable=1` instrument: `guts` = `Vector` 6 821 + `LedgerRecord` 5 186 + `WorkOrder` 83 + `Repo` 5 =
**12 095** and `guts-code` = `Vector` 6 705 + `Repo` 5 = **6 710**, matching this table exactly; `guts-ledger` =
`LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345**, exactly — that store holds **no `Repo` collection**,
both of `xd` D.2's two `Repo` ×2 (5·5) sitting in `guts` and `guts-code` and already consumed by those two sums.
`xd`'s 17 148 and this table's 17 345 are two units, not two measurements of one number.* **[consistency 12]**

*(Correction, same marker; re-derived at the punch-list pass. **[punch]** The figure first published here was
**17 342**, and the two claims made about it in the earlier draft — that a writer *"cannot move an `immutable=1`
count in either direction"*, and that 17 342 is *"superseded and unexplained"* — are **both withdrawn as
over-claims**. `immutable=1` ignores the live `-wal` and reads the **main db file only**; it does not follow that
the count is fixed. It moves — **exactly when a checkpoint lands**, rather than continuously with the writer — and
one did. **17 342 is fully explained: it is this same table, read one checkpoint earlier.** Re-derived this pass
from the spike's own retained sweep output `xd_sweep.json` (same `mode=ro&immutable=1` instrument, `xd` D.1):
`guts-ledger`/`instances` held `LedgerRecord` **17 145** + `WorkOrder` **197** = **17 342**, the published figure
exactly, and `xd` D.1's 17 145 is that same pre-checkpoint state. The `guts-ledger` main file was then
checkpointed (mtime **14:16:56**, read live before the store was next checkpointed — bracketed by
`xd_sweep.json`'s 14:16:57 write, which still holds 17 145, and `xd` D.1's 14:20 read, which does not), and that
**single event** moved the table to `LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345**. It is the *same*
event behind `xd` D.1's own pair, 17 145 at 14:14 → 17 148 at 14:20 — one checkpoint, two sections, one
explanation. Neither `guts` nor `guts-code` moved across those two reads — their sums in the note above are
identical to `xd_sweep.json`'s — which is what a checkpoint-driven rather than writer-driven count predicts.)*

*(The corrected figure, stated once so a citation can be checked against it. **[punch]** **`guts-ledger`/`instances`
is 17 345 = `LedgerRecord` 17 148 + `WorkOrder` 197, the whole table as of the 14:16:56 checkpoint, and the
collision rate is 4 166 / 17 345 = 24.02 %.** `f5` §5.4(3) quotes "4 166 of 17 342 rows (24.0%)"; the numerator and
the percentage are unchanged, the denominator should read **17 345**. **It is a snapshot, not a standing property
of the store,** and the earlier draft's error was to treat it as one: a read-only re-census at **16:21:55** this
pass — after a further checkpoint, main-file mtime **16:15:17** — returns **17 398** (`LedgerRecord` 17 199 +
`WorkOrder` 199) for the same table and **12 109** for `guts`. Cite 17 345 against its checkpoint; a reader who
re-runs later will get a larger denominator. **What does not move is the numerator:** the colliding-row count is
**4 166**, **1 966** and **0** at every read taken, so the 56 rows `guts-ledger` and the 14 rows `guts` gained
between the first and last of them added **none** — the pair is `run_id` / `_runID` in every one of the 4 166 and
1 966, and all rows still decode to dicts (0 non-dict, 0 parse failures, re-measured on all three stores at
16:21:55). The published **24.0 %** and **16.3 %** belong to the 17 345 and 12 095 denominators; against the
16:21:55 ones the same numerators read 23.9 % and 16.2 %.
**No finding in B.3–B.10, no obligation in B.8 and no verdict changes.**)*

The colliding pair is the same in both: **`run_id` and `_runID`, both → `runid`**, holding *different values*
(first such row: `run_id = ""`, `_runID = "one-body-phase-1"`). A tenant filter or sort on `runID` / `run id` /
`RunID` / `RUN_ID` resolves through `find_actual_key` and gets whichever comes first. Which one comes first is
**a property of the store, not of the record** — measured, one record, one `_field_value(row, "runID")` call:
via SQLite TEXT → `json.loads` (today's path) the keys arrive `['run_id','_runID']` and it resolves to `run_id`
= `''`; via Postgres `jsonb` → `::text` → `json.loads` they arrive `['_runID','run_id']` and it resolves to
`_runID` = `'one-body-phase-1'`. Cause: `jsonb` does not preserve object key order — it stores keys sorted by
length then bytewise (measured: `{"run_id":…,"_runID":…,"zz":…,"a":…}::jsonb` enumerates `a, zz, _runID,
run_id`), while `json.loads` preserves document order. **Moving the store to `jsonb` changes the answer of the
existing Python path on 4 166 real rows, with no pushdown involved.** Direction: silently different value,
either way, no error.

*(Scope, INFERENCE: these are ledger `instances`, not a `Sample` noun collection; whether a production
`DataSource` targets a collection holding this pair is **not established by this spike** — that needs the
`DataSource` corpus f2 §2.9 records as absent. What **is** established: the collision occurs in real stored GIMS
records at 24.0% and 16.3%.)*

### B.5 `filters`: the value comparison diverges too, independently of the key

`_pass_filters` compares with Python `!=` on Python objects (`:94`); any pushdown compares with jsonb `=`. Two
further silent divergence classes follow, neither compiled nor fallback-ruled — **Python's `bool`/`int`
identity** (`1 == True`, jsonb rejects) and **missing-key vs explicit-null** (Python keeps the row, SQL drops
it). Both sides measured this pass:

| case | Python `_pass_filters` | SQL `(data->'k') = <lit>::jsonb` | agree |
| --- | --- | --- | --- |
| row `{"v":1}`, `filters {"v": true}` | **True** (`1 == True`) | **false** | **no** |
| row `{"v":true}`, `filters {"v": 1}` | True | false | **no** |
| row **without** `k`, `filters {"k": null}` | **True** (`None != None` is false) | **false** (`NULL = 'null'` → NULL) | **no** |
| controls: `{"v":1}`/`1.0`; `{"v":"1"}`/`1`; `{"k":null}`/`null` | True / False / True | true / false / true | yes |

### B.6 `sort`: the ordering mismatch — both orderings, and every place they differ

`proto/idxshape_sort_semantics.py`, re-run unchanged this pass against the live container (PostgreSQL 16.14, db
`autosql_spike`), reproduces f3 §3.6 H4 exactly:

```
sources.py _sort_key ascending : [false, true, 2.5, 5, "Zebra", "apple", [1, 2], {"a": 1}, null]
jsonb btree ascending          : [null, "Zebra", "apple", 2.5, 5, false, true, [1, 2], {"a": 1}]
SAME ORDER? False
```

Position by position — `_sort_key` vs `jsonb` — `0: false/null · 1: true/"Zebra" · 2: 2.5/"apple" · 3: 5/2.5 ·
4: "Zebra"/5 · 5: "apple"/false · 6: [1,2]/true · 7: {"a":1}/[1,2] · 8: null/{"a":1}`. **9 of 9 positions
differ.** The orders are `_sort_key` (`:105-106`) **bool < number < string < other < null-last** versus `jsonb`
B-tree (f3 §3.6) **null < string < number < bool < array < object**. They agree only on a
column uniformly one JSON type and non-null, which nothing in GIMS enforces: `_sort_key`'s docstring at
`:104-106` exists because columns *do* mix types, and `tests/test_dashboard_sources.py:182-188`
(`test_sort_never_crashes_on_mixed_bool_and_container`) locks a column mixing `True`, `[1,2]`, `{"k":1}`, `"x"`
and a missing key.

**A rank-triple emulation is possible but partial.** `bench.py:94-101` `sort_sql()` does emit the triple in SQL
(`CASE` on `jsonb_typeof` for ranks 0/1/2/4, `xpr.f8` for the numeric slot, `#>> '{}' COLLATE "C"` for the
string slot). Its own comment at `bench.py:91-92` records the hole: **rank 3 (list/dict, keyed on Python `repr`)
is NOT compilable**, and the harness asserts the corpus never produces it rather than handling it. Measured —
`_sort_key`'s rank-3 slot (Python `str()`) vs `jsonb::text`: **agree** on `[1,2]`, `[]`, `{}`, `[1.0]`;
**disagree** on `{"a":1}` (`{'a': 1}` vs `{"a": 1}`) and `["x"]` (`['x']` vs `["x"]`) — quote style; on
`[true,null]` (`[True, None]` vs `[true, null]`) — Python literals; and on `{"z":1,"a":2}` (`{'z': 1, 'a': 2}`
vs `{"a": 2, "z": 1}`) — jsonb reorders keys. That last case is unfixable in principle: rank-3
ordering depends on **document key order**, which `jsonb` destroys (B.4), so a container-valued sort column is
**uncompilable**, not just uncompiled.

Two further `sort` properties no arm reproduces. **(1) Stability** — `sorted()` at `:177` is stable both
directions, Postgres' sort is not, so `bench.py` added `TIE = ", data->>'id' COLLATE \"C\""` (`:178`) to every
SQL arm *and* mirrored it into the Python reference (`:399-400`): **the comparison that produced f4's numbers
deliberately changed both sides' sort to make them comparable**. Recorded prose-only at `analysis/measurement.md
§9.2`; f4 §4.11 confirms **no record in `measurements.json` or `probes.json`**. **(2) Tolerant resolution** —
`:177` calls `_field_value`, so every defect in B.3–B.5 applies to the sort field; `bench.py`'s arms sidestep it
by sorting on an *inlined derive expression* (`bench.py:218`, `sort_sql(d_sql_sort)`), never on a
tolerantly-resolved stored key.

### B.7 `limit`: inherits, and adds nothing of its own

`LIMIT n` is trivially compilable but **only well-defined relative to a total order**, so it inherits every
defect in B.6: with 9 of 9 positions differing, `LIMIT 50` over a mixed-type column picks a different 50 rows,
silently. It also inherits B.3–B.5 via the `filters` setting the candidate list, and its own coercions (B.2) must
be replicated *before* emitting SQL — `"abc"` and `-1` mean **no `LIMIT` clause**, not `LIMIT 0`.

### B.8 What a pushdown of each clause must reproduce — and its status

"Compiled" = emitted by `proto/compile.py`; "tested" = scored in `proto/conformance.py` / `coverage_probe.py`
under FRAMING §8's three-outcome rule; "fallback ruled" = a named, query-time-detectable fallback (FRAMING §4 #2).

| # | Obligation | Source | Compiled | Tested | Fallback ruled |
| --- | --- | --- | --- | --- | --- |
| 1 | exact-key lookup | `:72-73` | no (hand-written in `bench.py:226` only) | no | no |
| 2 | tolerant key match (case/space/`_`/`-`, first wins) | `:74-76`, `deep_search.py:19-39` | **no** | **no** | **no** |
| 3 | first-wins tie-break under document key order | `deep_search.py:36-38` | no — **input destroyed by `jsonb`** (B.4) | no | no |
| 4 | dotted-path fallback | `:77-84` | no | no | no |
| 5 | Python `!=` value semantics (`1 == True`; missing vs null) | `:94` | no | no | no |
| 6 | 5-rank order `bool<num<str<other<null` | `:99-115` | partial — `bench.py:94-101`, ranks 0/1/2/4, one widget | no | no |
| 7 | rank-3 key = Python `repr` of the container | `:115` | **no — uncompilable** (B.6) | no | no |
| 8 | stable sort in both directions | `:177` | no — bench *replaced* it with a tiebreak on both sides | no | no |
| 9 | sort field resolved via `_field_value` (so 1–4 recur) | `:177` | no | no | no |
| 10 | `limit` coercion (`"3"`→3; `"abc"`/`-1`→unlimited) | `:180-187` | no | no | no |
| 11 | `filters`/`sort` spec validation → 400 | `:153-155`, `:171-172` | n/a | n/a | n/a |

**Ten substantive obligations (1–10). Zero emitted by `proto/compile.py`, zero tested, zero fallback-ruled.**
**[consistency 18]** — stated precisely, because two rows of the table above do carry SQL: "compiled" here means
*emitted by `proto/compile.py`*, per this section's own definition, and by that definition the count is exactly zero.
The SQL that exists for obligations 1 and 6 is **hand-written in `bench.py` for one widget, outside the compiler**:
row 1's exact-key `filters` clause (`bench.py:226` — which B.3 measures dropping 2 of 3 rows) and row 6's partial
rank-triple sort (`bench.py:94-101`, ranks 0/1/2/4, rank 3 excluded by its own comment at `:91-92`). Neither is
scored by any harness, so **zero tested** and **zero fallback-ruled** hold literally for all ten. Obligations 3 and 7
additionally carry a positive argument that they *cannot* be compiled, not merely that they have not been.

### B.9 GAP 15 — `derive` chaining and shadowing

`_apply_derive` (`sources.py:133-148`) compiles each expression once over `derive.items()` (`:142` — **mapping
insertion order**), then per row does `row[name] = evaluate(...)` (`:147`), **writing back into the row being
iterated**. Docstring `:135-136`: *"later derives can reference earlier ones."* Re-checked this pass through the
existing Python path, on row `{"id":"S-1","due_date":"2026-08-21","priority":2}` with `ctx.now =
2026-08-19T12:00:00Z`:

| # | `derive` mapping | result |
| --- | --- | --- |
| A | `days_left`; `urgent: "$.days_left < 7"`; `score: "$.days_left * $.priority"` | `days_left=2.0, urgent=True, score=4.0` — **chaining works, two levels deep** |
| B | the same two entries in **reverse** order | `urgent=None, days_left=2.0` — **silently wrong, no error** |
| C | `priority: "$.priority * 10"` (shadows a stored key) | stored `priority: 2` **overwritten** with `20.0` |
| D | C, then `p2: "$.priority"` | `p2 = 20.0` — a later derive reads the **shadowed** value |
| E | `x: "1"` | the caller's row object is **mutated in place** (`res[0] is r` → `True`) |

No measured arm exercises any of this: f4 §4.3's four arms (B1 faithful, B2 inlined, B3 containment, B4 native)
all handle the **single** derive `days_left` (`bench.py:32-39`); f2's census is per-expression with no notion of
inter-derive dependency; f3's predicates are single-expression. Consequences a pushdown must carry: **(1) order
is semantic** — the compiler must preserve the JSON object's key order, and case B yields `null` rather than an
error when it is lost, the same class as FRAMING §5's non-negotiable; note the collision with B.4, since a spec
round-tripped through a `jsonb` column loses that ordering. **(2) shadowing is legal**, so a compiled `$.k` must
bind to the *derived* `k` when an earlier derive defined it and the stored `k` otherwise — a scoping rule
`compile.py` has no representation for (`column=` names one jsonb source, `compile.py:15-17`). **(3)** B1's
`data || jsonb_build_object(name, …)` (`bench.py:204`) composes by nesting in principle and B2's `subst()`
(`bench.py:216`) inlines one derive into `where`, but **whether either composes correctly for n ≥ 2 derives, and
survives shadowing, is not established by this spike.** What would establish it: a two-derive widget where
`derive2` reads `$.derive1`, plus a third shadowing a stored key, run through `proto/conformance.py`'s existing
three-outcome scorer against `sources._apply_derive` as oracle. That is new machinery; FRAMING §3 forbids
building it here.

### B.10 What this does to the spike's headline

f1 §1.2 reports **130/130** fixture cases `COMPILED_AGREES` (`proto/results.json`). That number is sound, and a
statement about **`expr` evaluation only** — about `derive` and `where`. `tests/fixtures/expr_vectors.json` holds
130 cases with keys `{expr, record, context, expect, group, name}` and **zero** occurrences of `sort`, `filters`
or `limit` (measured this pass). It cannot speak to two of the four clauses, and no other harness here does.

- **130/130 covers `derive` and `where`. It says nothing about `filters`, `sort` or `limit`.**
- On `filters`, the only pushdown anyone actually wrote **silently dropped 2 of 3 rows** on plain ASCII keys
  (B.3). On `sort`, the natural index-backed order disagrees with the Python order at **9 of 9 positions** (B.6).
  `limit` is meaningful only under a matching order and has neither.
- Under FRAMING §4 — *"NO-GO if any case diverges **silently**… One silently-wrong number is disqualifying on
  its own"* — B.3, B.5 and B.6 are each disqualifying **for a pushdown of that clause**. They do not touch f1's
  `expr` result, nor by themselves decide the verdict `f5` reaches (`f5` recommends **NO-GO**); they do establish
  that **any named subset cannot include `filters` or `sort` on the present evidence**, and that shipping either
  without obligations 1–10 of B.8 would breach FRAMING §5 on data that exists today. **[consistency 3]**

### B.11 Not established by this spike

| question | status | what would establish it |
| --- | --- | --- |
| Does any production `DataSource` use `filters`, or `sort` on a mixed-type / colliding key? | not established — no `DataSource` corpus (f2 §2.9) | read the deployed dashboard specs; count clause usage |
| Can tolerant matching be compiled at all (e.g. a normalised-key expression index)? | not established — obligation 3 has an impossibility argument, obligation 2 does not | compile a `jsonb_each` + `_norm_key` lateral and score it three-outcome |
| Does `bench.py`'s rank-triple emulation agree with `_sort_key` over mixed types? | not established — never scored; only asserted absent from one corpus (`bench.py:91-92`) | run it as a conformance battery over a mixed-type column |
| Does derive chaining compile for n ≥ 2, and under shadowing? | not established (B.9) | two-derive + shadowing widget through `proto/conformance.py` |
| How large is the SQL-vs-Python sort instability? | not established — prose-only, `measurement.md §9.2`, absent from raw per f4 §4.11 | re-run one arm without `TIE` and diff the returned id lists |

---

## Cross-cutting C — the complete divergence → fallback register, and what the machinery costs

Closes critic gap 1 (thirteen confirmed divergence classes with no fallback rule anywhere) and the
unmeasured half of critic gap 12 (the machinery, as distinct from the trigger). No new experiment:
every row is assembled from `f1` §1.9.1–§1.9.7 as corrected at closure, `f2` §2.6–§2.9, `f3`
§3.5(d)/§3.6, `f4` §4.9/§4.11 and the raw `analysis/fuzz/*.txt`. Per FRAMING §3 nothing is fixed.

### C.1 The two words the register keeps apart

FRAMING §5 requires a fallback to be **reported, never silent**. Two different mechanisms can satisfy
it, and every prior section conflates them:

- **DETECT** — at query time the adapter can tell that *this* query on *this* data actually diverged.
  Available only where the database raises (SQLSTATE) or the compiler refuses (`Uncompilable`).
- **AVOID** — the adapter cannot tell whether it diverged, but can decide **statically, from the AST
  or the source spec, before any SQL runs**, that this expression *could* reach the class, and refuse
  to push it down. An over-approximation: it fires on every expression containing the construct.

**AVOID satisfies FRAMING §5; it does not satisfy "detectable".** It is the only rule available for
every silent class, and its price is paid in pushdown coverage, not in wrong answers. The `detect`
column below is DETECT-only; the `fallback rule` column gives the AVOID rule where one exists. Codes:
**STATIC** (decidable from the spec/AST at `sources.py:345`, before `:347`) · **RAISE** (the query
aborts, SQLSTATE observable) · **NONE** (SQL succeeds and returns a different answer).

### C.2 Block A — compile-time classes (`f2` §2.6, §2.7)

| id | what diverges | cause | rate + witness | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| C1 | numeric literal overflows float8 | `compile.py:204-209`; `1e308` compiles, `1e309` does not, `$.a + 1e400` refuses the whole expression | boundary bisected, `f2` §2.6 | no answer produced | no | **STATIC** (`Uncompilable`) | catch `Uncompilable` → in-memory. Rule exists; **no reporting channel** (`f2` §2.8) |
| C2 | generated SQL > `MAX_SQL_CHARS` 200 000 | `compile.py:51,172-176`, checked **after** the string is built | first refusal `date_add` depth 11 = 294 795 chars | no answer | no | **STATIC** (`Uncompilable`) | as C1 |
| C3 | flat operator chain | ~3 Python frames/AST level vs `sys.getrecursionlimit()` 1000; parser `MAX_DEPTH=64` cannot see it (`expr.py:184-208`) | **first failure at 333 `+` operands, 665 chars** — one third of `MAX_SOURCE_LEN`; 332 compiles cleanly | no answer, **`RecursionError`** | no | **STATIC but off-contract** — `Uncompilable` never fires | catch `RecursionError` alongside `Uncompilable`. **Not in the contract today**; `except Uncompilable` catches nothing |
| C4 | nested `date_add` doubles SQL per level | `_f_date_add` emits its first argument twice (`compile.py:318-326`) | 2.00×/level; `Uncompilable` at depth 11; **`MemoryError` at ~depth 24 (~300-char source, ~2.4 GB)** under a 2 GiB `RLIMIT_AS` | no answer, or **process death** | no | **partial** | catch `MemoryError`. **INFERENCE:** with no `RLIMIT_AS` the allocation is an OOM event, not a catchable exception — then there is no fallback, there is an outage. Not established by this spike |

### C.3 Block B — run-time value classes (`f1` §1.9.1–§1.9.2 as corrected, plus `f2`'s R1/R2/R5/R6)

Numbering is `f1`'s, so the arithmetic is comparable with critic gap 1. `f2` §2.7's rule id is given
where one exists.

| id | what diverges | cause | rate + witness | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| **D1** | `sum($.l)` on `[1e300,1]` → py `1e+300`, sql **`1`**; `max`,`avg` likewise | `xpr.f8` range-guard literal written to **297 digits** (`1.797693134862316e+296`) where DBL_MAX needs 309 (`runtime.sql:33`) | **16 of 16 f8-reachable paths** diverge (16/20 probed; the 4 that agree do not call `xpr.f8`) — `A_f8_guard.txt` §A2 | **different value** (silent) | not literally; **breaches §4 NO-GO** | **NONE** | =R3. `f2` §2.7 records "**none**". Only AVOID rule: refuse any expression whose operands can exceed 1.797693e+296 — **not decidable from the AST**, so in practice refuse arithmetic entirely; the alternative is to fix the guard (R3) and let R1′ catch the raises it unmasks (§C.12 item 3) |
| **D2** | `concat($.a)` → `''`, `string($.a)` → **SQL NULL** on `{a:1e300}` | same guard | in the same 16 (`A_f8_guard.txt` §A2) | different value; value→null | as D1 | **NONE** | as D1; AVOID by excluding `string`/`concat` |
| **D3** | `contains($.s,$.a)` → py `True`, sql `False` | same guard | ibid. | different value | as D1 | **NONE** | AVOID by excluding `contains` |
| **D4** | `$.a < 1e301`, `$.a > 1`, `$.a >= $.a` → SQL NULL | same guard, predicate path | **3 of 3** order comparisons | value→null → **rows dropped** | see D23 | **NONE** | as D1 |
| **D5** | boundary, bisected live: round-trips at `1.79769313486231551e+296`, corrupts at `…587e+296` | same guard | every finite double of magnitude ≥ 1.797693e+296 — **~12 of the float8 exponent's 632 decimal decades** (`A_f8_guard.txt` §A3) | — | — | **NONE** | bounds the blast radius of D1–D4; no independent rule |
| **D6** | float8 **underflow** raises: `$.a * $.a` on `1e-200` → py `0.0`, sql aborts | PG raises 22003 on underflow; `expr` returns `0.0` | **9 of 13** overflow/underflow probes raise (`B_overflow.txt`); witnesses at `1e150 × 1e160` and `1e-300 / 1e100` (`B2_overflow.txt`) | **value → raise** | no — this is the loud direction | **RAISE** 22003 | **R1′ (new here): catch SQLSTATE `22003` — overflow *and* underflow, any operator — and re-run the whole widget in memory.** `f2` R1 is scoped to "overflow in `+ - * /`" and misses this |
| **D7** | `round($.a,-2)` on a subnormal raises | `xpr.round` computes `x·10^nd` internally | `SQL_RAISE_ONLY` **94/8000 = 1.18%**; `BOTH_RAISE` **65/8000 = 0.81%** (`G2b_round_raises.txt`); 756/40 000 = 1.89% raises either side (`G_fmod_round.txt` §G2) | value → raise | no | **RAISE** 22003 | R1′ — **with a hole: on the 0.81% `BOTH_RAISE` subset the in-memory retry raises too** (`OverflowError: cannot convert float infinity to integer`). The fallback terminates in an error, not an answer |
| **D8** | `number('١٢٣')`, `'１２３'`, Devanagari, NKO, NBSP/thin/ideographic space → py `123.0`, sql NULL | `xpr.num`'s ASCII gate vs Python's Unicode-aware `_to_num` (`expr.py:305`) | **10 of 27** `C_numgate` probes (4 digit systems + 6 space code points) | **value → null**, silent | via D22 — **YES**, see C.6 | **NONE** | **none possible by detection.** AVOID: exclude `number` from pushdown |
| **D9** | `number('1e-400')` → py `0.0`, sql raises 22003 | same gate, unguarded underflow — while `xpr.f8` on `1e400` is *guarded* to NULL: the two guards are inconsistent (`M_encoding_guc.txt`) | **1 of 27**, distinct from D8's 10 | value → raise | no | **RAISE** | R1′ |
| **D10** | date strings padded with Unicode space → py `1.0`, sql NULL | `expr.py:413` `v.strip()` strips Unicode spaces; `runtime.sql:273` `btrim(E' \t\n\r\f\v')` does not; `expr.py:415` is a bare `return None` | **10 of 12** whitespace code points (only U+0020, U+000C agree) + 12 Unicode-digit cases = **22 divergences in E2** (`E2_dates_ws.txt`) | value → null, silent | via D22 — **YES** | **NONE** | none by detection. AVOID: exclude `days_between`/`date_add`/`today`/`now` |
| **D11** | `days_between($.d,"2024-01-02")` on `{d:'0001-01-01T00:00:00+14:00'}` → py **`OverflowError`**, sql `738886.5833333334` | offset pushes the year past `datetime.min`/`max`; SQL's timestamptz range is wider | **4 `PY_RAISE` of 45** date probes (`E_dates.txt:30-41`); one witness is inside a boolean a dashboard would write, where SQL answers `True` | **raise → value** — FRAMING §5 clause 2 | **YES** | **NONE** | **none possible — undetectable in principle, and the direction is inverted:** the reference runtime is the one that fails, so "fall back to in-memory" converts a wrong answer into a 500. AVOID: exclude the date functions |
| **D12** | `$.a == 1` on raw-JSON `{"a": 1.00000000000000001}` → py `True`, sql `False` | jsonb stores `numeric`, not IEEE double | **10 of 18** raw-JSON probes (`D_rawjson.txt`) | different value | no | **NONE** | =R7, `f2` records "none". **Partly bounded by reachability:** `gims-ledger/api/storage_aws.py:743-754` writes via `Jsonb(record)` from Python objects and cannot produce such a row; `:694` reads with `json.loads` and *will* mis-read one if anything else wrote it (`D_rawjson.py:12-17`). AVOID would mean refusing `==`/`!=` on paths — which deletes the only index-accelerated shape `f3` found |
| **D13** | `if($.a,1,2)`, `not $.a`, `$.a and true` on raw `{"a": 1e-400}` | `xpr.truthy` casts to `numeric`, where `1e-400` is non-zero; Python parses it to `0.0` | **4 of 18** | different value, silent | no | **NONE** | none by detection. **No AVOID rule exists**: the constructs are `if`/`not`/`and`, which any subset keeps. Bounded only by D12's reachability argument |
| **D14** | `number($.a)`, `$.a + 0`, `string($.a)` on raw `{"a": 1e-400}` | same | **3 of 18** | value → raise | no | **RAISE** | R1′ |
| **D15** | `sum($.l)` on `[1e16,1,-1e16]` → py `1.0`, sql **`0`** | CPython 3.12 `sum()` is Neumaier-compensated; `sum(float8)` is not (`runtime.sql:411` is exactly `sum(v ORDER BY ord)`) | **4368/20 000 random lists = 21.84%** by proxy; **99.73%** on the "big value ± small corrections" profile; max abs difference **35.39**; **6 of 10 end-to-end through the compiler** (`K_sum_neumaier.txt` §K2) | **different value**, silent | **breaches §4 NO-GO** | **NONE** | none by detection. AVOID: exclude `sum`/`avg` — **the single highest-yield exclusion in the register** |
| **D16** | `string()` of a double at the **pinned** `extra_float_digits = 1`: py `'52990648348713780'`, sql `'52990648348713776'` | `xpr.ecma_num` vs `_num_to_str` | **56 of 200 000 doubles = 0.0280%**, 1 in 3571; all round-trip to the same double (`F1b_ecma_rate.txt`) | different value (string) | no | **NONE** | **not covered by R5.** R5 says "pin the GUC"; D16 is what remains *after* pinning. AVOID: exclude `string`/`concat` |
| **D17** | 200 identical rows: `WHERE string($.a)='0.3333333333333333'` returns **0 rows via index scan, 200 via seq scan** | `xpr.ecma_num` declared `IMMUTABLE` while depending on `extra_float_digits`; index built at `efd=-3` (`F3_immutable_index.txt`) — `L5` shows **four** functions mis-declared (`ecma_num`, `f8`, `num`, `str`) | **1 of 2 configurations**; reproduced once, attempted twice | **silent wrong result set**, plan-dependent | **breaches §4 NO-GO** | **NONE** | none by detection — the planner's choice is invisible to the caller. **Avoidable by DDL policy, not by a query-time rule**: never build an index over an `xpr` function while the GUC dependency stands. **[consistency]** *Not* moot — the absolute this row carried is false. `proto/idxshape_preds.json` holds **11** compiled outputs and `to_jsonb` wraps exactly **10** of them: every compiled predicate W1–W9 and the compiled `derive` column D1, none of which can appear in an index. The compiled **sort key** S1 is `nullif((data -> (%(p0)s)::text), 'null'::jsonb)`, carries **no** wrapper, and `f3` §3.6 H4 measures it index-backed (`Index Scan using idxprobe_score_operand`, **0.065 ms**). A hand-written index over an `xpr` function is buildable too — `f3` §3.6 H1 built `idxprobe_ecma` over `xpr.ecma_num(xpr.f8(data -> 'score'))`, which is how D17 / §C.5 H1 was demonstrated at all. **The DDL policy is live, not moot.** |
| **D18** | `upper('İstanbul')`, `lower('ΣΊΣΥΦΟΣ')`, `upper('straße')` | PG follows DB collation; Python does full Unicode case mapping; Greek final sigma is context-dependent, so a per-code-point sweep is structurally blind to it | code points: `upper()` **102/286 718**, `lower()` **1/286 718**; **strings end-to-end: `upper()` 4 of 10, `lower()` 3 of 10** (`I_case_collate.txt` §I3) | different value, silent | no | **NONE** | =R4, "none". AVOID: exclude `upper`/`lower`. String-level *rate* not established |
| **D19** | `$.a[2147483648]` → py `None`, sql raises 22003 | jsonb array index is int4 | **3 of 5** (`L_misc.txt` §L2) | value → raise | no | **STATIC** *and* RAISE | **fully statically decidable** — the grammar's `[n]`/`[-n]` take an integer **literal** (`expr.py:240-243`), so a compile-time `abs(index) < 2^31` check refuses it before any SQL runs. Cheapest rule in the register |
| **D20** | `length($.s)` on `'a\x00b'` | a NUL byte cannot be stored as jsonb at all (22P05) | **1 of 1** (`L_misc.txt` §L3) | **unreachable row** | no | **RAISE**, at write time | not a read-side fallback: if the pushdown target is `instances.data jsonb` (`0001_instances.sql:13-18`), such a record can never have been written there. Lands on FRAMING §6's writes/invariants line, like `f3` H3 |
| **D21** | `extreme`-profile AST fuzz | — | **23 real divergences in 3880 that ran = 0.593%** after §1.9.6 removes 21 container-comparator artifacts; **23 of 23 carry a magnitude ≥ 1.797693e+296, 0 of 23 do not** | mixed (14 value→null, 9 different value) + 3 `SQL_RAISE` | as D1–D5 | **NONE** / RAISE | **subsumed: at closure D21 is D1–D5 seen 23 ways, not an independent class.** Its 3 raises are R1′ |
| **D22** | `if(number("１２３"), null, true)` → py `None`, sql **`True`** — 31 chars, record-independent | **named at closure: any `value → null` divergence sitting in an `if()` **condition** makes the two runtimes take different branches.** Verified live for three independent causes (D8 ASCII gate, D1–D5 f8 guard, D10 date trimming); control with no divergent sub-term agrees | 1 of 3867 in the `unicode` profile — but that measures **how often the generator emits the shape**, not reachability. 0 comparator artifacts | **null → value** — FRAMING §5 clause 1 | **YES** | **NONE** | **none possible — undetectable in principle.** Both branches agree in isolation; the breach is manufactured entirely by branch selection, so no sub-expression check can see it. AVOID: refuse any `if()` whose condition contains a construct that can yield value→null — i.e. `number`, the date functions, or unbounded arithmetic |
| **D23** | the same defects as a `WHERE` predicate: `$.amount > 100` over 8 rows keeps `[2,3,5]` in memory and `[2,5]` in SQL; `number($.amount) > 100` drops rows 3, 6, 7; **`not($.amount > 100)` silently ADDS row 3** | causes are D1–D5 (row 3, `amount=1e300`) and D8 (rows 6–7, non-ASCII numeric strings) — `O_row_loss.txt` | **4 of 4 predicates** lose or gain rows | **wrong row set**, silent | **breaches §4 NO-GO** | **NONE** | none by detection. **Negation is the sharp edge:** `not()` converts a value→null divergence from row *loss* into row *addition*, so "value→null is the conservative direction" is false at the query level |
| R1 | `$.a * $.b` on `{1e200,1e200}` → py `inf`, sql aborts 22003 | `expr.py:614-621` has no overflow guard | probe `overflow_via_multiply`; declared `float8_overflow_raises` | value → raise | no | **RAISE** | R1′. **Coupled to D1–D5:** `B2_overflow.txt` states in its own header that the 297-digit guard means `+`, `-` and `sum()` **cannot overflow today** — "an accident of defect #1, not a design". Fixing D1–D5 enlarges this class |
| R2 | `number('1e999')` → py `inf`, sql NULL | deliberate guard, `compile.py:84-93` | 3 of 27 `C_numgate` probes | value → null, **declared** | no | **NONE** | `f2` records "none". Declared in `KNOWN_DIVERGENCES`, which is a documentation fact, not a run-time signal |
| R5 | `extra_float_digits` ≠ 1 | `M_encoding_guc.txt` §M1: `to_jsonb(float8)` itself returns `0.3333333333333333` / `0.333333333333333` / `0.333333333333` at `efd = 1/0/-3` | 68 of 130 fixture cases carry a float8→jsonb or →text conversion (`f1` §1.2) | different value — **the returned value, not only `string()`'s rendering** | no | **NONE** at query time | pin the GUC on every pushdown session. **Necessary and not sufficient** — D16 is the residue at the pinned value, and D17 is the residue across index-build sessions |
| R6 | `today()`/`now()` with no `context.now`: Python re-reads the clock **per record** (`expr.py:456`), SQL `now()` is the transaction timestamp | one statement = one clock | measured 1.2 s apart in one transaction: SQL `18:02:20` twice, Python `18:02:20` then `18:02:22` (`analysis/coverage.md` §6.2) | different value | no | **STATIC** (the caller controls `context.now`) | **always inject `context.now`.** The one rule in the register that is both decidable and complete |

### C.4 Block C — source-level classes (`f2` §2.7, §2.9)

| id | what diverges | cause | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|
| S1 | `source.type == "query"` | `cascade_deep_search` is a pure in-memory scored cascade over three heterogeneous inputs (`core/deep_search.py:389-390`; `sources.py:256-308` loads every noun instance and every verb run with no limit) | no pushdown possible | no | **STATIC** | whole source falls back. Confirmed and bounded per FRAMING §3; **not reported** |
| S2 | `source.type == "verb"` | `load_verb_group_log` bypasses `core.storage`, so there is no seam to attach a predicate to | no pushdown possible | no | **STATIC** | whole source falls back; **not reported** |
| S3 | `sort.field` names a **derived** column | ordering depends on a column that only exists after `derive` ran | partial pushdown only | no | **STATIC** (`sort.field` vs `derive` keys) | pushable only if its `derive` was pushed too. **Not hypothetical — it is exactly what the one real tenant dashboard on this machine does** (`f2` §2.9) |

### C.5 Block D — storage-layer classes (`f3` §3.6) — these are FRAMING §5's failure mode relocated where the compiler cannot see it

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| H1 | index scan vs seq scan on the same row | `xpr.ecma_num` declared `IMMUTABLE` while reading GUC-dependent float text (`runtime.sql:15-18`) | **0 rows via `Index Scan using idxprobe_ecma`, 1 row via `Seq Scan`** | wrong row set, plan-dependent | breaches §4 NO-GO | **NONE** | = D17. No query-time rule; DDL policy only |
| H2 | `(data->>'score')::float8 > 90` vs compiled `$.score > 90` | `::float8` coerces across types; `xpr.ord` yields NULL on mixed types (pinned by fixture `$.n < "x"` on `{"n":5}` → null) | **5040 vs 4807 rows**; 2409 rows store `score` as a string, 233 of them exceed 90. Control `$.score * 2 > 180` returns 5040 — arithmetic *does* coerce | wrong row set | breaches §4 NO-GO | **NONE** | **the compiler is right and the index-friendly rewrite is wrong.** Rule: never emit the `::float8` rewrite. Price: it is the 89× (re-measured 19×) speedup |
| H3 | `CREATE INDEX … ((data->>'score')::float8)` then insert `{"score":"n/a"}` | `expr` is total; a `::float8` index is not | **write rejected**, and afterwards the index can no longer be built. A `safe_f8` wrapper fixes the write and **still returns 5040, not 4807** | rejected write | crosses FRAMING §6 | **RAISE**, at write time | do not create the index. Two defects; fixing one does not fix the other |
| H4 | `ORDER BY` the compiled sort key | `sources.py:99-115` `_sort_key` orders `bool < number < string < other < None-last`; jsonb's B-tree orders `Null < String < Number < Boolean < Array < Object` | `[false,true,2.5,5,"Zebra","apple",[1,2],{"a":1},null]` vs `[null,"Zebra","apple",2.5,5,false,true,[1,2],{"a":1}]` — **SAME ORDER? False** | wrong row **order**, and with `LIMIT` a wrong row **set** | breaches §4 NO-GO | **STATIC-able** (the column's type mix is a data property, not an AST property — so in practice **NONE**) | **no rule exists.** They agree only on a uniformly-numeric column and nothing in GIMS enforces that. This is where the only working pushdown lives (429× at 0.065 ms) |

### C.6 Block E — route-conditional classes (`f3` §3.5(d)) — only live if the jsonpath route is adopted

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| J1 | `$.x == null` on `{}` | `expr`'s `==` is **total** and never yields null (`expr.py:363-367`, `:603-606`): absent key → `null`, `null == null` → `True`. `'{}'::jsonb @@ '$."x" == null'` is `False` in lax and SQL NULL in strict | **fixture case 33** — inside the 130, and reachable through the exact subset the jsonpath route recommends | **a row `expr` keeps is silently dropped** | **YES** (`f3`'s own reading) | **NONE** | exclude `== null` from the jsonpath route. Note it is one of the two shapes that *are* index-accelerated |
| J2 | bare path as `where`, e.g. `"where": "$.flag"` | `@@` yields the item only when it is a JSON **boolean**, SQL NULL otherwise; `expr._truthy` keeps any non-zero number, non-empty string/array/object | **4 of 6** bare-path fixture cases diverge; the 2 "agreements" are coincidental (both sides falsy on a missing key) | silently drops every row whose value is truthy-but-not-boolean | breaches §4 NO-GO | **STATIC** (the AST shape is visible) | refuse the jsonpath route for bare paths. Whole route: expressible 16/130, agreeing 11/130, index-accelerated **and** agreeing 3/130, routable **1.5% — one distinct expression shape** |

### C.7 Block F — clause-level classes outside `expr` (critic gaps 4 and 15; listed so the register is complete, counted separately)

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| K1 | tolerant key resolution | `sources.py:67` resolves exact key → **case/space/underscore-tolerant** → dotted path; SQL `data->'status'` is exact-only | records keyed `"status"`/`"Status"`/`"status "`: Path A returns `["T-1","T-2","T-3"]`, Path B returns `["T-1"]` — **2 of 3 rows silently dropped** (`measurements.json → tolerant_key_probe`) | wrong row set | breaches §4 NO-GO | **NONE** | **no rule exists anywhere in the spike.** Pushing `where` or `filters` requires reproducing tolerant key resolution in SQL; nothing compiles it |
| K2 | `sort` semantics | `_sort_key`'s 3-key type-rank tuple (`sources.py:99-115`) has no SQL equivalent | = H4 | wrong order → wrong `LIMIT` set | breaches §4 NO-GO | **NONE** | none; `limit` inherits it, since `LIMIT 50` is only well-defined under a matching total order |
| K3 | `derive` chaining | `_apply_derive` writes each result back into the row and "later derives can reference earlier ones" (`sources.py:133-148`) | **nothing compiles, measures or fallback-rules it** | not established | — | **STATIC** (dependency between `derive` keys is visible in the spec) | **not established by this spike.** What would establish it: one two-derive widget where `derive2` reads `$.derive1`, through `compile.py` |

### C.8 The count — the answer the gate actually needs

Counted over the **34 `expr`-layer ids** in Blocks A–C (C1–C4, D1–D23, R1/R2/R5/R6, S1–S3) — the
population critic gap 1 is about. Folding D21 into D1–D5 (`f1` §1.9.6: "one defect seen 23 ways")
gives **33 distinct classes**. Blocks D, E and F add **9 more** ids (4 storage, 2 route-conditional,
3 clause-level) and are counted separately, because D and E are conditional on a storage decision and
F is outside `expr` entirely.

| | count | ids |
|---|---:|---|
| **DETECTABLE at query time** | **15** | C1, C2 (`Uncompilable`) · C3, C4 (off-contract `RecursionError`/`MemoryError`) · D6, D7, D9, D14, D19, R1 (SQLSTATE `22003`) · D20 (write-time `22P05`) · S1, S2, S3 (static, from the source spec) · R6 (caller-controlled) |
| **UNDETECTABLE in principle** | **19 ids = 18 classes** | D1, D2, D3, D4, D5, D8, D10, D11, D12, D13, D15, D16, D17, D18, D21, D22, D23, R2, R5 — **18 once D21 folds into D1–D5** |
| carried a rule in `f2` §2.7, directly or by the critic's mapping | 21 | C1–C4 · R1, R2, R5, R6 · D1–D5 (R3), D18 (R4), D12 (R7), D9, D17, D21 (loosely) · S1–S3 |
| **had no fallback rule anywhere** | **13** | D6, D7, D8, D10, D11, D13, D14, D15, D16 (at `efd`=1), D19, D20, D22, D23 — critic gap 1's list, reproduced exactly |
| **breach FRAMING §5 as literally written** | **2** | **D22** (null → value) · **D11** (raise → value) — **and both are in the unruled 13** |
| **breach the §4 NO-GO bar** (silent wrong number or wrong row set) | **9** in Blocks A–C | D1, D12, D13, D15, D16, D17, D18, D21, D23 · **+7 outside**: H1, H2, H4, J1, J2, K1, K2 |

**15 detectable ids, 19 undetectable ids — and 15 + 19 = 34, the whole register. Folding D21 into
D1–D5 restates the identical split in classes: 15 detectable, 18 undetectable, 15 + 18 = 33. In
either unit more than half the register cannot be seen at query time by any mechanism — 19 of 34
ids (55.9%), 18 of 33 classes (54.5%).** **[punch]** *Units: an id count and a class count are
different denominators and may not be added. This headline previously read "15 detectable, 18
undetectable", which sums to 33 while naming the 34-id register. The arithmetic was mixed, not the
claim — the "half the register" force survives in both units, as the two percentages show.*

**What this section changes in that count.** One rule that already half-existed closes six ids:
**R1′ — catch SQLSTATE `22003`, overflow *and* underflow, on any operator, including `xpr.round`'s
internal overflow, and re-run the whole widget in memory.** It covers D6, D7, D9, D14, D19 and R1;
**four of those (D6, D7, D14, D19) are among the unruled 13.** `f2` R1's condition ("float8 overflow
in `+ - * /`") was too narrow by inspection, not by measurement. D19 additionally admits a
**compile-time** check (`abs(index) < 2^31`), decidable because the grammar accepts only integer literals
in `[n]`/`[-n]` (`expr.py:240-243`). D20 is a write-side fact, not a read-side fallback.
**That leaves eight of the thirteen — D8, D10, D11, D13, D15, D16, D22, D23 — with no possible
detection rule at all**, and for those the only FRAMING §5-compliant answer is AVOID (§C.10).

### C.9 The correction to `f2` §2.8, stated plainly

> `f2` §2.8 concludes: "Five run-time divergences (R2, R3, R4, R5, R7) are **undetectable in
> principle** under this design."

That verdict is scoped to `f2`'s own list of seven run-time rules, not to `f1`'s twenty-three
confirmed classes. Mapped across the whole register the undetectable set is **18 of 33 distinct
classes — 3.6× `f2`'s figure**, and it contains **both** of FRAMING §5's named directions, which
`f2`'s five do not. The critic's estimate of "roughly 2.5×" is confirmed and is if anything low.
Every one of the 13 extra undetectable classes was measured by the same spike, in the same batteries,
on the same database and in the same pass; none of it is new evidence. **The body understates the
undetectable set because it never mapped `f1`'s inventory onto `f2`'s rule table.**

### C.10 The only rule that reaches the silent classes, and its measured price

For all 18 undetectable classes the sole FRAMING §5-compliant rule is AVOID: a **static,
construct-keyed refusal**, evaluated at `sources.py:345` before any SQL runs, reported through a
return-contract field that does not exist yet.

The one place in the record where that rule is written down is `panel.json` verdict [0], which names
the subset: all 10 leaf/structural node types, all 5 arithmetic operators, all 6 comparisons, all 5
field-path forms (with the D19 compile-time index check) and **10 of 22 functions** — `abs ceil
coalesce count floor if length max min round`. Excluded: `days_between date_add today now` (D10, D11),
`sum avg` (D15), `string concat contains` (D16, D2, D3), `lower upper` (D18), `number` (D8, D9).

**Its price, computed by that adjudicator by walking the real `expr.parse` AST over the fixture and
not re-derived by this seat: 36 of 48 constructs** and **84 of 130 cases (64.6%)** — so the rule
refuses **46 of 130 cases, 35.4% of the contract fixture**, including the canonical widget `f4`
measured end-to-end, which is a date widget. **Its coverage of this register has at least two holes, and the larger one is
measured rather than inferred** **[punch]**. **First, D1–D5 — the highest-rate silent class in this
register — survives the subset.** The corrected subset (`f5` §5.7) retains `+ - * /`, all six
comparisons and `abs`/`max`/`min`, and `analysis/fuzz/A_f8_guard.txt` §A2 measures **8 of the 16 paths
that diverge at `a = 1e300`** as composed entirely of constructs the subset keeps: `$.a + 0`, `$.a * 1`,
`- $.a`, `abs($.a)`, `$.a < 1e301`, `$.a > 1`, `$.a >= $.a` and `max($.l)`. Three of the eight are order
comparisons, which that file labels *"the pushdown-predicate path"*. And `max($.l)` returns SQL **`1`**
where Python returns **`1e+300`** — a silently wrong *number*, FRAMING §4's disqualifying clause verbatim,
**inside the subset the AVOID rule exists to make safe**. §C.8's own D1 row concedes the mechanism: its
only AVOID rule is *"refuse any expression whose operands can exceed 1.797693e+296 — not decidable from
the AST, so in practice refuse arithmetic entirely"*, and the subset keeps arithmetic. **Second**, D13
(`xpr.truthy` on a sub-float8 raw-JSON numeric) reaches
through `if`/`not`/`and`, which every subset keeps, and is bounded only by the reachability argument
that `Jsonb(record)` cannot write such a row (`D_rawjson.py:12-17`) — an argument about GIMS's
*current* writer, not an invariant. **OPINION, labelled:** a rule whose completeness rests on no other
process ever writing raw JSON into `instances.data` is a deployment assumption, not a compiler
property, and it is the kind of assumption that fails silently.

### C.11 Sizing the machinery — OPINION, with the reasoning shown

`FRAMING` §4 #5 requires "the cost of the fallback machinery". `f2` §2.8 lists seven changes with no
effort attached; `f4` §4.9 prices the *trigger*. Neither prices the machinery. This spike cannot
measure it, so what follows is a **scoping estimate, labelled OPINION**, every input a counted artifact.

**(a) The one-time build — `f2` §2.8's list, sized by what each touches.**

| item | what it touches | scope, OPINION |
|---|---|---|
| `pushed_down: bool` + `fallback: [{scope,reason}]` on `resolve()`'s dict | `sources.py:357` (one return), its three call sites `:353-356`, plus every UI consumer of the widget contract | **the load-bearing item — everything else is inert without it.** One return shape, but it is a public contract change: `frontend/lib/dashboard/widgets.jsx` already renders a "Result capped for performance" badge for `truncated`, so a precedent exists; a second badge and its copy do not |
| C3 — recursion → explicit stack, or a depth budget checked before recursing | `compile.py`'s whole `_j`/`_t_*` dispatch | rewriting the traversal of a 464-line compiler, not a guard |
| C4 — bind `date_add`'s argument through a CTE/`LATERAL`; accumulate `MAX_SQL_CHARS` during construction | `compile.py:318-326` + `:171-176` | changes the emitted SQL's *shape*, so every conformance number is re-earned |
| C3/C4 belt-and-braces — catch `RecursionError`/`MemoryError` as fallback | the adapter | genuinely small; the only cheap item on this list |
| R1′ — catch SQLSTATE 22003 and re-run in memory | the adapter | small, **but the transaction is already aborted: it is a full retry, not a resume**, and on D7's `BOTH_RAISE` subset the retry raises too |
| R3 — widen the `xpr.f8` guard literal 297 → 309 digits | one line of `runtime.sql` | **mispriced as "one line".** `B2_overflow.txt` states the 297-digit guard is why `+`, `-` and `sum()` cannot overflow today; correcting it converts D1–D5's silent population into a new population of query-aborting 22003 raises, which R1′ must then absorb |
| R5 — pin `extra_float_digits` on every pushdown session | session setup | small, and **incomplete** (D16, D17) |

**(b) The standing obligation — the part nothing in the spike prices.** "Standalone compiler + thin
GIMS adapter" creates a **third runtime** of the expression language, and the contract fixture's own
note makes the obligation explicit: *"Both the Python evaluator … and the JS evaluator … MUST produce
`expect` for each case … Hand-authored expected values — do NOT regenerate from either evaluator"*
(`expr_vectors.json`, `note`). Counted inputs: `expr.py` **646** lines · `frontend/lib/expr.js`
**373** lines · the third runtime is **two artifacts in two languages** — `compile.py` **464** lines
plus `runtime.sql` **427** lines defining **21** `xpr.*` SQL functions · **48** constructs ·
**130** contract cases · **6** JSON value kinds per construct, of which the fixture exercises
`_eq` **7 of 36** cells and `_order_cmp` **4 of 36** (`f2` §2.3).

**OPINION, and the reasoning:** the maintenance cost is not proportional to the 891 lines. It is
proportional to (i) the number of places a language change must land — **three runtimes, four
artifacts, three languages (Python, JS, PL/pgSQL)**, up from two and two; (ii) the number of
*semantic* surfaces re-verified per change — this register is **33 distinct classes** (34 ids, D21 folded into D1–D5), of which **18 classes are invisible** to any test that only checks the 130 cases, because that is exactly how 130/130 was
achieved while both §5 directions were breached **[punch]**; and (iii) the fact that the SQL runtime's behaviour
depends on things the other two runtimes have no analogue for — a session GUC (R5, D16, D17), a
collation (D18), a planner choice (D17, H1), an `IMMUTABLE` declaration the server does not verify,
and the target server's version. **Any future edit to `expr.py` must be mirrored into two
artifacts, one of which is SQL whose correctness is deployment-conditional.** No measurement in this
spike bounds that; the honest statement is that it is a **permanent, unbounded coupling**, and the
130-case fixture demonstrably does not detect its violation.

**(c) What would establish it, since this spike cannot:** size `f2` §2.8's change list against the
three call sites at `sources.py:353-356` and the widget contract in
`frontend/lib/dashboard/widgets.jsx`; then run this register as an acceptance battery against the
proposed subset and count how many of the 34 ids it actually closes. **The batteries already exist**
(`analysis/fuzz/run_all.sh`, 21 of them, plus `O_row_loss.py` as a ready-made regression test) — but
**no run of them against any subset exists**, so the subset's completeness is asserted, not measured.
A `sp-synth` design task; FRAMING §3 forbids this pass from producing it.

### C.12 Why the measured trigger figures do not bound the cost

`f4` §4.9 measures compile-time refusal at **0.0307 ms** (0.0004%–0.22% of Path A) and run-time
refusal at a constructed worst case of **6 917 + 1 494 = 8 411 ms vs 1 494 ms, +463%**. Both are
correct and both are **out of scope for most of this register**:

1. **A run-time fallback can only ever fire on the RAISE classes.** That is 6 of 34 (D6, D7, D9, D14,
   R1, and D19's run-time half). For the **18 undetectable classes (19 ids) there is nothing to
   trigger** —
   the SQL succeeds, the number is wrong, and no timer starts. The +463% figure prices the loud
   failure mode and says nothing about the silent one, whose cost is a wrong number on a tenant's
   dashboard and which this rig cannot price at all.
2. **The 0.0307 ms prices deciding not to push down — which is the AVOID rule, and it is cheap.**
   That is the good news in this section: the only rule that reaches the silent classes costs
   essentially nothing per request. **Its cost is not latency, it is coverage: 46 of 130 fixture
   cases, 12 of 22 functions, and the canonical measured widget.**
3. **Fixing the loudest silent class makes the loud class larger.** R3 (widen the `xpr.f8` guard)
   moves D1–D5 out of "undetectable" and into "RAISE" — which is FRAMING §5's own logic, Postgres
   having been chosen because it fails loudly — but it does so by converting silently-wrong answers on
   `+`, `-` and `sum()` into aborted queries priced at up to +463%. **The register's undetectable
   count and its run-time trigger cost move in opposite directions.** That trade is the decision, and
   no number in this spike prices which side of it a tenant prefers.

### C.13 What this register does not establish

- **Reachability in real GIMS data — closed for this corpus, open at production scale. [consistency]**
  Every witness in Blocks A–C is a constructed record. The read-only sweep this bullet originally
  prescribed was performed and reported by `xd` D.3–D.5, which ran those four predicates over every
  `objects.db`/`archive.db` in both trees: magnitude ≥ 1.797693e+296 → **0 of 5,235,942 numeric nodes**
  (D.3, largest observed `|v|` = 1.787e+12, 284 decades short); non-ASCII decimal digit or non-ASCII
  whitespace → **0 of 1,096,202 string values *plus object keys*** (D.4, in a corpus carrying 206,567
  non-ASCII code points, so the zero is not an artifact of an ASCII-only corpus); >17 significant
  digits **and** the writer-signature test (literal ≠ `repr(float(lit))` / `str(int(lit))`) → **0 of
  5,236,427 numeric literals** on both (D.5). D1–D5, D8, D10 and D12–D14 therefore have **no witness
  in this corpus, and D12–D14 no writer here that could make one**. What remains open is
  **production-scale reachability — `xd` D.8**, which states its own limits against itself: n = 1
  machine, 1 operator, 60.2% of the 37,078 swept rows written by AutoDev itself, and the one
  tenant-shaped project contributing 222 rows. **Scope of this closure, stated so it is not
  over-read:** it covers the exotic-numeric and Unicode classes only. `xd` D.6/D.9 finds the
  tolerant/coercion classes — §C.7's K1, and the string-where-a-number-belongs shape §C.5's H2 is
  about — **reached at scale** in the same corpus (17,144 bool-strings on one key; weight fields 100%
  string; `'60824'` as a `received_date`), and §C.7's K1 still has no rule anywhere in the spike.
- **That the AVOID subset is complete.** It is asserted from cause attribution, never run against the
  register. D13 is already a known hole in it.
- **A rate for D18 at string level, or for D22 in reachable-shape terms**; and **K3 (`derive`
  chaining) in any respect** — uncompiled, unmeasured, unruled.
- **Whether an in-memory fallback always succeeds — mechanism adjudicated in `xa` A.5(ii); what
  remains open is a frequency, not a mechanism. [consistency]** D7's `BOTH_RAISE` (0.81%), D11's four
  `PY_RAISE` witnesses and `B2_overflow.txt`'s `round($.a,20)` on `1.7e296` are three mechanisms by
  which `expr` itself raises, against `expr.py:640` and `recon/semantics.md` §11 — and §C.3's D7 row
  and §C.11(a)'s R1′ row already carry the consequence into the register. **A fallback whose target
  can raise is not a fallback.** `xa` A.5(ii) measures exactly that: one poison row
  `{"d":"0001-01-01T00:00:00+14:00"}` placed at index **0, 5 or 9** of a 10-row list produces an
  **uncaught `OverflowError` in both `_apply_derive` (`sources.py:147`) and `_filter_rows`
  (`sources.py:162`)** — neither `evaluate()` call is inside a `try` — which
  `core/errors.py:115-119`'s `@app.exception_handler(Exception)` returns as **HTTP 500
  `INTERNAL_ERROR`**, i.e. loud but not a *report*: no `pushed_down: false`, no reason, no partial
  result. On the one battery that quantifies the overlap (`G2b_round_raises.txt`, n = 8000) Postgres
  raised on 94 + 65 = 159 probes and Python raised on 65 of those same 159, so **40.9% (65/159) of SQL
  raises also raise in the retry** and R1′ rescues ~59% of that domain, not 100%. **What genuinely
  remains open is the production frequency of `xa`'s N1–N4 raise conditions**, which `xa` A.5 records
  as not established and does not chase, per FRAMING §3. Note the bound from `xd` does not extend to
  it: `xd` D.3–D.5 screens magnitudes, non-ASCII digits/whitespace and writer signature, and runs **no
  predicate for offset-bearing or out-of-`datetime`-range date strings**, which is the shape carrying
  D11 and `xa`'s R1. The D11 half of this frequency is therefore unbounded by any sweep in this spike.

**Net effect of the two closures above on this section's argument — labelled, because it cuts both
ways. [consistency]** The first weakens a leg this register leaned on: "no witness in production data"
is no longer an open unknown for D1–D5, D8, D10 and D12–D14 on this machine, so the exotic-numeric
half of the undetectable set is, for this corpus, a hazard with **zero observed instances** rather than
an unquantified one. The second strengthens the opposite leg: the fallback of last resort is not
merely unruled, it is **measured to fail 40.9% of the time on the only domain that quantifies it** and
to surface as a 500 rather than a report. Neither closure changes the counts in §C.8 — detectability is
a property of the mechanism, not of its rate — and this section still recommends nothing. **OPINION,
this seat:** on the register as a whole the second closure is the heavier of the two, because the
classes `xd` finds *reached at scale* (tolerant keys, string-typed numbers, null propagation through
`derive`) are the ones with no rule at all, and R1′ does not touch them.

### C.14 Compliance attestation **[consistency]**

**Compliance.** Read-only throughout, and **no new experiment**: every row in Blocks A–F is assembled
from `f1` §1.9.1–§1.9.7 as corrected at closure, `f2` §2.6–§2.9, `f3` §3.5(d)/§3.6, `f4` §4.9/§4.11
and the already-captured `analysis/fuzz/*.txt`. No figure in this section originates in a run made for
this section: every cell carries a citation to a prior section or to a committed capture, so no fuzz
battery was re-run, no capture was regenerated, and no database object was required, created, altered
or dropped. Both GIMS trees, `FRAMING.md`, `recon/`, `proto/`, `analysis/`, `.autodev/` and `kb/` were
read and not written; the only file this seat wrote is `spikes/T-1/.parts/xc-fallback-register.md`.

**Nothing is fixed, per FRAMING §3.** C1–C4, R3, R5 and the absent reporting channel are **recorded,
not repaired**. In particular **R1′ — the one new rule this section proposes (§C.3, §C.8, §C.11(a)) —
is proposed as a *rule* and is not implemented**: `compile.py`, `runtime.sql` and `sources.py` are
byte-unchanged by this seat. FRAMING §3's stop rule ("a divergence whose cause is identified → record
cause + fallback rule, do not fix it") requires that form rather than merely permitting it. §C.11 is
labelled **OPINION** and is a scoping estimate, not a measurement; §C.11(c) records that the existing
batteries have **never been run against any proposed subset**, so the AVOID subset's completeness is
asserted, not measured, and this section says so rather than closing it.

**What is not independently attestable from the artifacts, stated rather than glossed:** this section
produced no run log, script or capture of its own — by design, since it ran nothing — so its read-only
status rests on the citation audit above rather than on a recorded transcript. The closure edits marked
**[consistency]** in §C.13 were made in this document only, against `xa` A.5(ii), `xd` D.3–D.5/D.8 and
`analysis/fuzz/G2b_round_raises.txt` as read; no artifact outside this file was modified to make them
true.

---

## Cross-cutting D — is any of this reachable from real GIMS data?

Closes `critic.md` §5. **`f1` §1.11 item 6** — "whether any of D1–D23 is reachable from real GIMS dashboard
data… every witness is a constructed record", declared **not established** there, and now carrying a forward
pointer to this section instead **[punch]** — together with `f2` §2.9 and `f4` §4.1/§4.11, declared the same
gap independently — while `index-shape.md:113-126` records that a real 17,087-row `LedgerRecord` collection was opened
read-only *during this spike*. This pass asks those questions of that corpus and every other real corpus here.

**What this pass is, labelled exactly [consistency].** It is **a new read-only instrument, built this pass**
(`xd_sweep.py`, §D.1), **cross-checked against `json_tree`** — not a re-read of artifacts that already existed.
It reads only: no compiler run, no Postgres connection, no write to any file in either GIMS tree, no fix
(FRAMING §3, attested §D.11). The earlier draft called this "a read-only sweep, not a new experiment"; the
*read-only* half is true and attested, the *not a new experiment* half was a stretch and is withdrawn. Nothing
is fixed and nothing is written, so no stop rule is touched — but the instrument is new, and a reader weighing
§D.3–§D.6 is weighing an instrument built here, whose only independent check is the `json_tree` agreement in
§D.1. It matters because `f1` §1.9.3 breaches FRAMING §4's bar *outside the fixture*, and a bar tripped only by
inputs no production writer can generate is a different fact from one tripped by ordinary tenant data.

### D.1 Method and the read-only guarantee

Every database opened `sqlite3.connect("file:<path>?mode=ro&immutable=1", uri=True)` — the form
`index-shape.md:1271` used. Two independent instruments over the same bytes, so a defect in one is visible against
the other (FRAMING §8). **W** — Python walker (`…/scratchpad/xd_sweep.py` → `xd_sweep.json`):
`json.loads(txt, parse_float=FNum, parse_int=INum)` captures the **raw number literal** of every scalar, then
recurses over the decoded tree classifying every value and key. **T** — SQLite `json_tree`, no Python in the path:
`SELECT count(*), max(abs(t.value)) FROM instances i, json_tree(i.data) t WHERE t.type IN ('integer','real')`.

**They agree exactly.** W: **5,236,427** numeric JSON nodes. T: **5,235,942** over `instances` only. The
difference, **485**, is precisely the numeric nodes W found in the `*_verb_log` tables T did not scan
(`guts_verb_log` 289 + `guts-code_verb_log` 196) — an instrument miscount of the kind FRAMING §8 warns about
would not produce that identity.

**One honest complication:** `guts-ledger/objects.db` is being written *by another process* during this session
(AutoDev's own ledger) — `LedgerRecord` read 17,145 at 14:14 and 17,148 at 14:20 — and `immutable=1` **ignores
the `-wal`**; both effects are quantified in §D.8.

### D.2 The corpus — what actually exists here

Every `objects.db` / `archive.db` under `gims-ledger/projects/` and `GIMS-Project/projects/`. Counts are per
`(table, collection)`, the unit `sources.py` scans (§D.7).

| tree · project | collection | rows | vs `MAX_SCAN` = 20,000 |
| --- | --- | ---: | --- |
| gims-ledger · guts-ledger | `LedgerRecord` | **17,148** | **85.7 %** |
| gims-ledger · guts | `Vector` | 6,821 | 34.1 % |
| gims-ledger · guts-code | `Vector` | 6,705 | 33.5 % |
| gims-ledger · guts | `LedgerRecord` | 5,186 | 25.9 % |
| gims-ledger · guts, guts-ledger, guts-code | `verb_log` ×3 (289·197·196) · `WorkOrder` ×2 (197·83) · `Repo` ×2 (5·5) | 972 | ≤ 1.4 % |
| GIMS-Project · LIMS-System | 18 collections, largest `Star Spirit Lore` 68, smallest 1 | **222 total** | ≤ 0.34 % |
| GIMS-Project · LIMS-System | **`Submission`** — the one real dashboard's source (one of the 222) | **7** | 0.04 % |
| GIMS-Project · LIMS-System | `archive.db` `noun_Sample`; 3 other `noun_*` + `instances` are empty | 28 | — |

**Swept: 37,078 rows · 5,236,427 numeric nodes · 495,115 string values.** `DurationDemo` (0 bytes), `RunlogTest`
and `Sterility` hold 0 rows in both trees. `gims-ledger/projects/LIMS-System/` has `noun_types.json` (98 declared
fields, `index-shape.md:1003`) but **no `objects.db`** — those 98 fields have zero rows here. **Excluded and
named:** 91 backup snapshot dirs under `gims-ledger/backups/*/*/` + 67 under `GIMS-Project/backups/*/*/`,
historical copies of LIMS-System whose live originals are above.

**How the table adds to 37,078 — the reconciliation, stated because it does not close as printed [punch].** The
table is a census read at 14:20; the **Swept** totals are the sweep's own read (`xd_sweep.json`, re-aggregated
read-only for this pass). Three details separate them, each verified against that file. **(i)** The sweep counted
`guts-ledger` · `LedgerRecord` at **17,145**, not the 17,148 in the table — the §D.1 concurrent writer, +3 in six
minutes; 85.7 % of `MAX_SCAN` either way. **(ii)** The `verb_log` group names three logs and omits a fourth,
`LIMS-System_verb_log`, **27 rows**, which *was* swept: four logs totalling 709 rows, not three totalling 682.
**(iii)** The 28 `archive.db` `noun_Sample` rows were **not** swept — that table is column-per-field (`_rowid`,
`_runID`, `image`, `received_date`, …) rather than a `data` JSON blob, so `xd_sweep.py` skipped it; that is what
the "—" in its `MAX_SCAN` column means, and it is why the row is listed but adds nothing. Corrected, it closes
exactly: 17,145 + 6,821 + 6,705 + 5,186 + 280 (`WorkOrder` ×2) + 10 (`Repo` ×2) + 222 (LIMS `instances`) =
**36,369 `instances` rows**; 289 + 197 + 196 + 27 = **709 `*_verb_log` rows**; **36,369 + 709 = 37,078**. The
published total is right; the table's legs were not printed in a form a reader could add.

### D.3 Q1 — does any stored number reach the 297-digit guard (D1–D5)?

D1–D5: every finite double with `|v| ≥ 1.797693e+296` is mishandled by `xpr.f8`, and 16 of 16 `f8`-reachable paths
diverge (`f1` §1.9.2 rows **D5** and **D1** **[punch]**, `fuzz/A_f8_guard.txt` §A2/§A3). Instrument T, run per database:

```sql
SELECT count(*) FROM instances i, json_tree(i.data) t
WHERE t.type IN ('integer','real') AND abs(t.value) >= 1.797693e296;
```

| | |
| --- | ---: |
| numeric nodes examined (T, `instances`) | 5,235,942 |
| **rows matching `abs(v) >= 1.797693e296`** | **0** |
| rows matching the one-decade-early tripwire `abs(v) >= 1e290` (W) | **0** |
| **largest `abs(v)` in the whole corpus** | **1,787,169,706,037** (≈1.787e+12) |
| where | `$.payload.blocked_since`, `LedgerRecord` key `52580851-018e-422a-ab38-a479ea6f3bed` — epoch **ms** |

**0 rows matched; the query is shown.** The gap between the largest number any GIMS writer here has stored and
the guard D1–D5 needs is **284 decimal orders of magnitude**; next largest magnitudes are embedding components,
`|v| ≤ 3,054`. *Absence in one corpus, not safety* — §D.8.

### D.4 Q2 — non-ASCII digits or whitespace in coercible strings (D8, D10)?

D8 is `xpr.num`'s ASCII gate vs Python's Unicode-aware `_to_num` (`f1` §1.9.2 row **D8** **[punch]**); D10 is `str.strip()` vs
`btrim(E' \t\n\r\f\v')` on dates — 10 of 12 whitespace code points diverge (`f1` §1.9.2 row **D10** **[punch]**,
`expr.py:413` vs `runtime.sql:273`). W decodes every string value and key, classifying non-ASCII chars by `unicodedata.category`:

| | |
| --- | ---: |
| string values + object keys examined | 1,096,202 |
| **strings carrying a non-ASCII decimal digit (`Nd`)** | **0** |
| **strings carrying non-ASCII whitespace (`Zs`/`Zl`/`Zp`/`isspace`)** | **0** |
| …of those, at a string edge, where `strip`/`btrim` actually differ | **0** |

> **What 1,096,202 counts, and the one gap in its producer — re-verified at the consistency pass [consistency].**
> `f1` §1.9.5 and §1.11 item 6 now quote this denominator, and `f5` §5.4(4)/§5.6/§5.9(5) quote it alongside
> §D.2's **495,115**, so both are pinned here. **1,096,202 is string values *plus* object keys, over the
> `instances` tables only** (36,372 rows). **495,115 is string values *only*, over all 37,078 swept rows**
> (`instances` + the four `*_verb_log` tables). Different unit *and* different scope — neither is a subset
> label for the other, and neither can be substituted for the other in a rate.
>
> **The two tie exactly, and the tie is this [punch].** Of §D.2's 495,115 string values, **491,813** are in
> `instances` and **3,302** are in the four `*_verb_log` tables — 491,813 + 3,302 = 495,115, exact, re-aggregated
> read-only from `xd_sweep.json` for this pass. **491,813 is therefore the string-value half of 1,096,202**, and
> the remaining **604,389** is the object-key half — *arithmetic*, 1,096,202 − 491,813, and arithmetic precisely
> because the key count itself was never retained (the gap below). That is why the larger number covers the
> *smaller* corpus: it adds ≈604 k object keys and drops the 3,302 `verb_log` string values. The `instances`
> row count behind it, **36,372**, is §D.2's swept **36,369** plus the same **+3** `LedgerRecord` drift the census table's 17,148
> carries — one writer, one offset, stated in both places.
>
> **The gap in its producer, stated exactly [punch].** `xd_sweep.py` tallies object keys in memory
> (`a.keys[k] += 1`) but **emits no key count into `xd_sweep.json`** — the per-unit fields it writes are `rows`,
> `nums`, `ints`, `floats`, `strs` and the witness lists, and none of them is a key count — and it passes only
> string *values* through the `unicodedata.category` classifier. So at the time of drafting the object-key half
> of this denominator had **neither a retained producer for its count nor any producer for its zero**; only the
> 491,813 string-value half is re-derivable from the retained artifact.
>
> **Closed by re-running it:** a second independent walker that classifies keys *and* values, `mode=ro&immutable=1`,
> over the same corpora, returns **0 non-ASCII `Nd` digits and 0 non-ASCII whitespace across 491,861 string values
> + 604,350 object keys = 1,096,211** on `instances` (1,103,311 including `verb_log`). The nine-node difference
> from 1,096,202 is the concurrent writer of §D.1, not a correction. The Unicode-tolerance control re-derives too:
> **218** distinct non-ASCII code points, **29,773 of 36,372** rows, `U+2500` ×**144,265**, `U+26A0` ×**27,736** —
> all exact; occurrences **206,571** vs the drafted 206,567 and em-dash **28,708** vs 28,704, the same +4 rows of
> drift. **The claim stands; its provenance is now two instruments rather than one** — three as of this pass
> **[punch]**: a further read-only walker, run for the punch list against the same corpora with
> `mode=ro&immutable=1` and classifying **both** halves, returns the same two zeros. Its denominators are larger
> again (the §D.1 writer has kept writing) and are **not** published here; it was run to check the split and the
> zeros, not to restate them.

**The zero is load-bearing only because the corpus is demonstrably Unicode-tolerant:** the same sweep found **218
distinct non-ASCII code points, 206,567 occurrences, in 29,773 of 36,372 rows (81.86 %)** — `U+2500` ×144,265,
em-dash ×28,704, `U+26A0` ×27,736, arrows, smart quotes, emoji, Greek delta. What GIMS writers have never once
put in is a non-ASCII **digit** or **space**. An ASCII-only corpus would make this zero worthless; this one is
not. **In passing:** the raw stored JSON *text* holds **0 non-ASCII bytes in all 36,372 rows** — every code point
is `\uXXXX`-escaped, i.e. `json.dumps()` at default `ensure_ascii=True`, matching `core/storage/sql.py:362,563`.
Corroborates §D.5.

### D.5 Q3 — >17 significant digits, or any sign of a non-Python writer (D12–D14)?

D12–D14 need a number **not** produced by a Python float (`f1` §1.9.2 rows **D12–D14** **[punch]**). `fuzz/D_rawjson.py:12-17` already
fixed the direction: `gims-ledger/api/storage_aws.py:743-754` writes via psycopg `Jsonb(record)` and therefore
**cannot** produce such rows, while `:694` (`json.loads(cell)`) **will mis-read them if another writer does**. The
open question was the **writer**, not the reader. W answers it, keeping every number's literal text:

| test, over all 5,236,427 numeric literals | matches |
| --- | ---: |
| significant digits > 17 | **0** |
| **literal ≠ `repr(float(lit))`** (floats) **or ≠ `str(int(lit))`** (ints) — a literal `json.dumps` of a Python number could not have emitted | **0 of 5,236,427** |
| JSON parse failures on the stored text | 0 |
| maximum significant digits observed | **17** — e.g. `-0.017092391848564148` at `$.embedding[1]`, `Vector` key `geds::api/index.py` |

> **INFERENCE:** every row in every corpus on this machine was written by `json.dumps()` over a Python object —
> the `ensure_ascii` signature (§D.4) and the writer at `core/storage/sql.py:362,563` agree. No ETL, no `psql`, no
> restored dump, no second-language service has written these tables. D12–D14 have **no witness here, and no
> writer here that could make one.**

A claim about this machine's writers, not about Postgres: `storage_aws.py:326-335`'s own comment documents this
disagreement as a parity bug they fixed once (`fuzz/D_rawjson.py:16-18`) — evidence a non-Python writer *has*
existed in this system's history.

### D.6 Q4 — the tolerant/coercion class. **This one is reached, repeatedly.**

The `human_required = "false"` shape (`index-shape.md:126`). W censused every `(project, collection, JSON path)`
by JSON type. **D.6.1 — boolean-looking STRING where a boolean belongs:**

| project · collection | path | string `"true"`/`"false"` | real JSON bool |
| --- | --- | ---: | ---: |
| guts-ledger · `LedgerRecord` | `$.human_required` | **17,144** | **4** |
| guts · `LedgerRecord` | `$.human_required` | **5,182** | **4** |

Not 4 stray typos — a key **99.977 % string and 0.023 % boolean** in the largest real collection on the machine.
`index-shape.md:126` reported the string; the **mixture** is new here, and is the harder fact.

**D.6.2 — a key holding a NUMBER on some rows and a STRING on others:**

| project · collection | path | number | string | the strings are |
| --- | --- | ---: | ---: | --- |
| guts-ledger · `LedgerRecord` | `$.payload.blocked_since` | **315** | **9** | ISO-8601, e.g. `2026-08-14T16:40:15+00:00` |
| guts · `LedgerRecord` | `$.payload.blocked_since` | **57** | **4** | same |

One key, one collection, two incompatible physical types at **2.8 %** of the rows that have it — a **real witness
for hazard H3, which was demonstrated with a constructed `{"score":"n/a"}` record** (`f3` §3.6, row H3) **[punch]**:
`CREATE INDEX … (((data->>'blocked_since')::float8))` cannot be built over this table, because 9 real rows raise
`invalid input syntax for type double precision`. The constructed record was not a straw man. Corpus-wide: **0**
keys mix a number with a *numeric-looking* string; **2** mix a number with a non-numeric string.

**D.6.3 — semantically numeric fields stored 100 % as strings:**

| project · collection | path | numeric-looking strings | other types | samples |
| --- | --- | ---: | --- | --- |
| LIMS · `Potency Sample` | `$."Sample Weight (g)"` / `$."Dilution Weight (g)"` | 7 / 7 | null ×7 | `'1'`, `'24'` |
| LIMS · `Terpene Sample` | the same two paths | 3 / 3 | — | `'1'`, `'24'` |
| LIMS · `Sample` | `$.sample_id` · `$.received_date` | **20** · 7 | string ×35 · ×43, null ×5 | `'14190.52'`, `'12345'` |
| LIMS · `Instrument Type List` | `$."ID #"` | 4 | — | **`'0002'`, `'0000'`, `'0003'`** |
| LIMS · `Submission` | `$.received_date` | **5** | string ×1, null ×1 | **`'60824'`** (×5), `'2025-06-11'` |

A field literally named *"Sample Weight (g)"* is a **string** in 100 % of the rows that have it. `ID #` is
`'0002'` — leading zeros, so `number('0002')` = 2.0 destroys the identity and text sort disagrees with numeric
sort. `Submission.received_date` is `'60824'` on 5 of 7 rows: numeric-looking and **not a date** — `_DATE_RE`
(`expr.py:402`) and its mirror (`runtime.sql:273-276`) reject it, so date functions over it yield null. **The
coercion class is not exotic; it is the ordinary condition of this data, in both trees.**

### D.7 The one real dashboard, against its own real rows

`coverage.md:652-670` found one dashboard in two backups. It is also **live**:
`GIMS-Project/projects/LIMS-System/project_nodes/nodes.db`, table `dashboards`, **1 row**, id
`143c987947874e36b728bb66f5a9125c` ("Testy Test") — same id, so still **n = 1 distinct dashboard**, 3 widgets, 2
of them `csv` (never reach `resolve()`). Its one resolver-reaching widget, verbatim from `layout_json`:

```json
{"type": "noun", "noun_type": "Submission",
 "derive": {"days_left": "round(days_between(today(), $.due_date), 1)"},
 "where": "$.status == \"in progress\"", "sort": {"field": "days_left", "dir": "asc"}}
```

`sources.py:193-206` (`_noun_records`) loads one noun type and `:348-351` caps that loader's result, so the scan
unit is `Submission` — **all 7 rows**:

| `submission_id` | `status` | `due_date` | `priority` | kept by `where`? |
| --- | --- | --- | --- | --- |
| Sub0608250000 | `in progress` | `2026-07-02T17:00:00` | `true` (bool) | **yes** |
| Sub0608250001 | `in progress` | `2026-07-04T17:00:00` | `false` (bool) | **yes** |
| Sub0611250001 | `in progress` | `2026-07-10T17:00:00` | `true` | **yes** |
| Sub0608250002 | `completed` | `2026-07-05T17:00:00` | `false` | no |
| Sub0608250003 · Sub0608250004 · asdfasdfasdf | **null** | **ABSENT** | ABSENT | no |

1. **Null propagation is live in real data.** `due_date` is absent on **3 of 7 (42.9 %)** rows, so
   `days_between(today(), $.due_date)` → `expr` null → SQL `NULL` on 43 % of the collection — the
   `index-shape.md` §1.2 generator modelled this at 8 %, so the real rate is **5× higher**.
   **Cross-reference — the corpus `f4` actually measured on is at 5 %, not 8 % [consistency].** 8 % is
   `index-shape.md` §1.2's *modelled* rate; the generator that produced every row behind `f4`'s numbers omits
   `due_date` on **5 %** (`proto/gen_data.py:30`, `if rnd.random() >= 0.05:`, quoted at `f4` §4.2). Against
   42.9 % that is **8.6×**, and it bears on `f4`'s selectivity, derive-cost and recall figures rather than on
   anything in this section; `f4` §4.2 now records it and works the direction through in `f4` §4.11, where the
   net effect is left **not established**. Re-verified for this pass, read-only, against
   `GIMS-Project/projects/LIMS-System/objects.db` (`instances`, `collection = 'Submission'`): 7 rows, `due_date`
   absent on `Sub0608250003`, `Sub0608250004` and `asdfasdfasdf` = **3 of 7 = 42.857 %**. **Stated against this
   section: n = 7.** The rate is exact for this collection and extrapolates to nothing (§D.8) — it is a real
   counter-example to the 5 % assumption, not a replacement parameter.
2. **On this corpus the widget's own filter removes exactly those rows** — `status` is null on precisely the 3 rows
   lacking `due_date`, so *kept ∧ due_date-absent = 0* and `sort` never orders a null. **OPINION: an n = 7
   coincidence, not a property of the widget.** One tenant adding an `in progress` submission with no due date
   puts a null into `sort`, which is `f3` §7.4's ordering divergence.
3. **The date shape is real datetime, not bare `YYYY-MM-DD`** — `2026-07-02T17:00:00` is inside both parsers'
   `[T ]` branch (`expr.py:402-406`, `runtime.sql:273-276`) and the fixture exercises it (13 datetime-with-time
   vs 19 bare-date literals): not a gap, recorded because it could have been. `received_date` = `'60824'` is in
   the same collection (§D.6.3) — no widget reads it today, nothing prevents one.

### D.8 `MAX_SCAN`, and how representative this corpus is

`MAX_SCAN = 20_000` (`sources.py:61`), per loader result (`:348-351`) — one collection for `noun` sources.
Largest real collection (`guts-ledger` · `LedgerRecord`): **17,148 = 85.7 % of MAX_SCAN**, headroom **2,852
rows**, `created_at` spanning 2026-07-06 → 2026-08-19 (**44.2 days**, 27 distinct days with rows). Growth is
bursty, so the answer is a range, not a point:

| rate basis | rows/day | days to cross `MAX_SCAN` |
| --- | ---: | ---: |
| largest observed single day (2026-08-06) | 3,515 | **0.8** |
| mean, last 14 full days | 807 | **3.5** |
| mean, whole 44.2-day history | 388 | **7.4** |
| mean, last 7 full days (a quiet week) | 58 | 49.4 |

**No collection here exceeds `MAX_SCAN` today**; one is within a week of it on three of four bases. **OPINION:
"nothing is over the cap" is the weakest available argument against pushdown.**

**Representativeness — stated against the spike, not for it.** *n = 1 machine, 1 operator*; no second machine, no
tenant sample, no production snapshot in scope. *The corpus is the tooling, not tenants*: 22,334 of 37,078 rows
(60.2 %) are `LedgerRecord` written by AutoDev itself, 13,526 (36.5 %) are code-embedding `Vector` rows, and the
LIMS tenant project — the only one shaped like the dashboard use case — contributes **222 rows across 18
collections**, the one real dashboard's source **7**. Every claim about "ordinary tenant data" rests on those 222
rows. *One writer*: §D.5 shows a single writer signature across 5.2M literals, and a corpus with one writer cannot
answer a question about a second writer — exactly what D12–D14 ask; the sharpest limit on this section. *The WAL
is invisible*: `immutable=1` ignores `objects.db-wal`, **543,872 bytes** for `guts-ledger` at 14:20 and growing;
the checkpointed count moved 17,145 → 17,148 in six minutes, small against 17,148 but **not zero and not
measured**. *158 backup snapshots not swept* (§D.2). **Nothing here extrapolates to production.**

### D.9 What this changes

| class | reachable from real GIMS data here? | basis |
| --- | --- | --- |
| **D1–D5** (297-digit `f8` guard) | **No witness.** 0 / 5,235,942 numeric nodes; max `|v|` is 284 decades short | §D.3, two instruments |
| **D8, D10** (non-ASCII digits / whitespace) | **No witness.** 0 / 1,096,202 **string values + object keys** **[punch]** — in a corpus with 206,567 non-ASCII code points | §D.4 |
| **D12–D14** (jsonb `numeric` ≠ IEEE double) | **No witness, and no writer here that could make one.** 0 / 5,236,427 literals deviate from `json.dumps` output | §D.5, `D_rawjson.py:12-17` |
| **coercion / tolerant class** | **REACHED, at scale** — 17,144 bool-strings on one key; a number/string key at 2.8 %; weight fields 100 % string; `'0002'`; `'60824'` | §D.6 |
| **null propagation through `derive`** | **REACHED** — 42.9 % of the one real dashboard's own collection | §D.7 |
| `f3` §3.6 **H3 index hazard** **[punch]** (`::float8` expression index un-buildable) | **REACHED with a real record**, not a constructed one | §D.6.2 |

**INFERENCE — the only judgement this section makes.** The `f1` §1.9.3 breach of FRAMING §4's NO-GO clause is
carried by causes whose triggering inputs are, on this evidence, **not generated by any writer in this system**,
while the classes that *are* everywhere in real data are the tolerant/coercion ones. That does **not** clear the
bar — FRAMING §5 is about a *silent* wrong answer, and `f1` §1.9.5 shows a value→null divergence becomes
null→value the moment it sits under an `if()`. It changes the **shape of the risk**: from "an exotic float
silently corrupts a dashboard" toward "an ordinary string-typed weight, or a `"false"`, does". Different fallback
costs; `f5` should price them separately.

### D.10 Not established by this spike — each with what would establish it (none attempted, FRAMING §3)

1. **Whether the compiled SQL actually diverges on the real witnesses found here.** §D.6 shows `$.human_required`
   and `$.payload.blocked_since` exist; it does not run them through the compiler. *Would establish it:* feed
   those two real `LedgerRecord` rows to `proto/conformance.py`'s three-outcome harness. **Not run — that would
   execute the compiler.** *(Wording corrected [consistency]: the line to hold is "no compiler run, no database
   write", not "no new instrument" — this section did build a new read-only instrument, see the label note above
   and §D.1.)*
2. **Whether any non-Python writer exists anywhere in GIMS.** §D.5 proves none has written *these* tables. *Would
   establish it:* an audit of every `INSERT`/`COPY` path into `instances` in both trees, plus deploy-time
   migration and restore tooling.
3. **Whether production data resembles this.** *Would establish it:* this section's `xd_sweep.py` predicates run
   read-only against a production `instances` table, or collection of the `MAX_SCAN` warning `sources.py:350`
   already emits and nobody gathers.
4. **The dashboard usage distribution.** Still **n = 1 dashboard, 3 widgets** — confirmed live rather than only in
   backups, which does not increase n. *Would establish it:* the `dashboards` table from >1 deployment.
5. **What is in the un-checkpointed WAL.** *Would establish it:* a `mode=ro` non-immutable read, which touches
   `-shm` and was therefore not done. **6. Array-valued keys vs the lax/strict jsonpath split** (`f3` §3.8 item 7
   **[punch]**): this sweep recorded array presence but did not classify element types against the jsonpath route.

### D.11 Attestation

`GIMS-Project` HEAD `995cc59`, `gims-ledger` HEAD `7b7a049` — the FRAMING §7 values, unchanged; both working
trees carry pre-existing dirty entries, **none this seat's**.

> **Correction to this attestation, re-verified at the consistency pass [consistency].** The drafted line —
> "both working trees carry 8 pre-existing modified files, all mtime **2026-08-13**, six days before this
> spike" — is **wrong in two particulars**, both checked with `git status --porcelain` + `stat` and neither
> touching the read-only claim. **(i) The counts differ:** `GIMS-Project` has **8** dirty entries (7 modified,
> 1 untracked), `gims-ledger` has **9** (7 modified, 2 untracked). **(ii) "all mtime 2026-08-13" is false for
> three of them:** `projects/RunlogTest/verbs/Chemistry/data_dumps/R1/grid_save_debug.log` is **2026-06-28** in
> both trees (older, still pre-existing); `gims-ledger/backups/_config/schedules.json` is **2026-08-19
> 10:40:07 −0600**, ten minutes *before* `sp-investigate` opened (16:50:18Z = 10:50:18 −0600); and the
> untracked directory `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` carries mtime **2026-08-19
> 14:32:46 −0600**, which is **inside** the spike window. That last one is the **same concurrent writer §D.1
> discloses for `objects.db`** — AutoDev's own ingestion verb, which also moved `LedgerRecord` 17,145 → 17,148
> during the sweep — not this spike. **What is attestable stands unchanged:** every connection this section
> opened carries `mode=ro&immutable=1` (`xd_sweep.py`, read here), no file in either tree was opened for
> writing by this seat, and both HEADs are the FRAMING §7 values. **What is not attestable, said plainly:** a
> seat that only reads cannot prove another process did not write, and one demonstrably did.

No file in either tree was opened for writing; every connection string here carries `mode=ro&immutable=1`. **No
Postgres connection was opened at all** — no object created, altered or dropped. `recon/`, `proto/`, `analysis/`,
`FRAMING.md`, `.autodev/` and `kb/` were read only; the only file written is this one. Working scripts live in the
session scratchpad (`…/scratchpad/xd_sweep.py`), outside the repository, throwaway by contract (FRAMING §3).

**Compliance, consistency pass [consistency].** The changes made to this file at the consistency pass are the
five marked **[consistency]** above — the label note in the header, the §D.4 denominator/provenance note, the
§D.7 item 1 cross-reference, the wording of §D.10 item 1, and the correction inside this attestation. **No number
in §D.2–§D.9 was changed**; the §D.4 note adds a second producer for a figure already published, and does not
restate it. Everything re-verified for that pass was re-verified **read-only**: `xd_sweep.json` re-aggregated from the retained scratchpad
output; a second independent walker re-run against the same corpora with `mode=ro&immutable=1` (a `/tmp` script,
outside this repository); `proto/gen_data.py`, `analysis/index-shape.md`, `.autodev/events.jsonl` and the other
`.parts` files read, never written; `git status`/`git rev-parse` in both GIMS trees, which write nothing. **No
Postgres connection was opened in this pass either**, and nothing anywhere was fixed (FRAMING §3). The only file
this seat wrote in either pass is this one.

**Compliance, punch-list pass [punch].** This pass changed **citations and reconciliations only**; it changed no
published measurement. Specifically: **(1)** the seven `.parts/f1.md:NNN` / `.parts/f3.md:NNN` line references —
which resolve only inside the working parts directory, and which the rewritten `f1`/`f3` have since made stale
anyway — were converted to section references (`f1` §1.11 item 6; `f1` §1.9.2 rows D1/D5, D8, D10 and D12–D14;
`f3` §3.6 row H3; `f3` §3.8 item 7), each checked by opening the cited section and matching the quoted claim;
**(2)** §D.9's "`f3` §7.3" was corrected to "`f3` §3.6" — §7.3 is `analysis/index-shape.md`'s section number for
the same hazard and resolves nowhere in this document; **(3)** §D.2 gained the reconciliation of its own census
table to the swept 37,078; **(4)** §D.4's denominator note gained the exact 491,813 + 3,302 = 495,115 tie and a
sharper statement of what `xd_sweep.json` does *not* contain; **(5)** §D.9's D8/D10 row, which read
"0 / 1,096,202 **strings**", now carries the same "string values + object keys" label the §D.4 row it summarises
has always carried — the figure is unchanged, the label was the loose half. **No number already published in
§D.2–§D.9 was changed** — 17,148 · 37,078 · 495,115 · 1,096,202 · 5,236,427 · 5,235,942 and every count in §D.3–§D.7 stand as
written. The figures newly *stated* (36,369 · 709 · 491,813 · 3,302 · 604,389 · 27 · 17,145) are re-aggregations
of the retained `xd_sweep.json` or arithmetic on figures already published, and the derivation is shown in place.
Read-only throughout: `xd_sweep.json` re-aggregated and `xd_sweep.py` re-read; one further walker and one
schema/row-count enumeration run against both GIMS trees with `mode=ro&immutable=1` (`/tmp` scripts, outside this
repository); `consistency.md`, `FRAMING.md`, `f1.md`, `f2.md`, `f3.md`, `f4.md`, `f5.md`,
`xc-fallback-register.md`, `f6-closure-log.md`, `FINDINGS.md`, `analysis/index-shape.md` and `analysis/coverage.md`
read, never written. **No Postgres connection, no write to any file in either GIMS tree, nothing fixed**
(FRAMING §3). The only file this seat wrote is this one; `FINDINGS.md` is regenerated from the parts by a later
seat and was not edited. **The verdict is unaffected** — nothing above moves a reachability result in either
direction, so `f5`'s NO-GO stands exactly as it stood.

---

## Finding 5 — Recommendation

**Question (FRAMING §4 #5):** go / no-go on *a standalone AST→Postgres-SQL compiler plus a thin GIMS adapter*, with the
reasoning **and the cost of the fallback machinery**.

> ### Verdict: **NO-GO** on the architecture as scoped.
>
> The translation works and the architecture does not: the correctness that decides the question lives in
> `api/dashboard/sources.py`, not in the compiler; the only named subset in the record still contains two of the four
> measured FRAMING §5 breaches; and the performance the ticket asked for is negative at every size measured, with its fix
> blocked behind four compiler changes.

**This is a recommendation, not a decision.** `decision_authority` is `recommend-and-wait`; `human:owner` rules at the
`sp_decide` gate. §5.7 sets out what a CONDITIONAL-GO would have to contain if he rules the other way; §5.11 names the two
experiments that would convert this verdict on evidence rather than argument.

### 5.1 The panel did not converge, and that is a first-class result

Three seats adjudicated the same bar from the same evidence (`.parts/panel.json`, dated 13:50 — **before** the four
cross-cutting sections existed, §5.4). Averaged they say nothing; stated separately they localise the disagreement to one
sentence.

| seat | verdict | the **one** fact it turns on |
|---|---|---|
| `panel.json[0]` | **CONDITIONAL-GO** | *Every silent divergence traces to a named construct.* Excluding 12 of 22 functions removes all of them — **36 of 48 constructs, 84 of 130 cases (64.6%)**, computed by that seat by walking the real `expr.parse` AST over the fixture |
| `panel.json[1]` | **NO-GO** | *§5 is written unscoped* — "any **compiler output**… **regardless of its performance**" — and the divergences are keyed on runtime **values**, not constructs (`f2` §2.7: all thirteen rules are shape-, magnitude-, value- or source-keyed, **none** construct-keyed), so §4's CONDITIONAL-GO template **cannot be instantiated** |
| `panel.json[2]` | **CONDITIONAL-GO** | *The economic case reduces to one unmeasured proposition* — that a total-**and**-fast SQL runtime exists — so the only defensible go is one whose **first** condition (C-0, bar ≤ 5.5 µs/row at 1 M) buys that experiment before any build |

**Unanimous.** GO is unavailable: §4's third GO clause fails outright — `resolve()` returns exactly
`{"records","count","truncated"}` (`GIMS-Project/api/dashboard/sources.py:357`, re-verified live by this seat), fallbacks
reported today **0** (`f2` §2.8). FRAMING §5 **is** breached outside the fixture and **is not** breached inside it (each
seat's `framing_s5_breached`; `f1` §1.9.3). The prototype as built must never ship.

**They also split below the label.** [0] keys its subset on functions, [2] on shapes (S-a…S-e); [0]'s first condition is
the subset rule, [2]'s is the performance experiment. Each concedes the other — [0]: *"the two verdicts differ only in
sequencing"*, *"the subset's residual divergence rate is not low, it is **unmeasured**"*; [2]: *"a verdict whose first
condition is 'go find out whether the premise is true' is not a conditional go — it is a no-go with a follow-up spike
attached."*

**Seat [1]'s decisive argument has a rebuttal, and closure supplies it — stated here rather than left standing.
[consistency]** [1] reasons: the divergences are keyed on runtime **values**, not constructs, therefore §4's
CONDITIONAL-GO template cannot be instantiated. `xc` C.1 shows that inference holds for only one of the two mechanisms
that can satisfy §5, and separates them: **DETECT** — *"at query time the adapter can tell that this query on this data
actually diverged… available only where the database raises (SQLSTATE) or the compiler refuses"* — and **AVOID** — *"the
adapter cannot tell whether it diverged, but can decide **statically, from the AST or the source spec, before any SQL
runs**, that this expression could reach the class, and refuse to push it down."* AVOID is **construct-keyed by
construction**, so a value-keyed divergence set does not block a construct-keyed subset; it blocks a *detecting* one.
`xc` C.1's own sentence is the exact boundary: **"AVOID satisfies FRAMING §5; it does not satisfy 'detectable'."**

**What this does to the argument, plainly. [consistency]** It **weakens** seat [1]'s "cannot be instantiated" from a
proof to a scoped one: the template *can* be instantiated — §5.7 of this very finding instantiates it, construct-keyed,
which is a tension a reader would otherwise find unremarked — but only as an AVOID subset, which does **not** meet §4's
GO clause *"the fallback is detectable and reported at query time"*. What survives of [1] is that no subset can be
**detecting**, and that AVOID's price is paid in coverage: **46 of 130 fixture cases (35.4%), 12 of 22 functions and the
canonical measured widget** (`xc` C.10, C.12), before §5.4(1)'s corrections take more. §5.2's ruling therefore rests on
the fixture-adequacy question, not on [1]'s value-vs-construct point, which closure has narrowed.

### 5.2 The contested point, in a form that can be ruled on

> **Does a FRAMING §5 breach found outside the nominated fixture disqualify the ARCHITECTURE, or only this THROWAWAY
> PROTOTYPE?**

**Reading A** (seats [0], [2]): §5 judges *shippable* output; `proto/` is throwaway by contract (FRAMING §3) and the stop
rules **required** its defects to be left unfixed, so the breaches price a rebuild rather than refuse one. **Reading B**
(seat [1]): §5 is written about "any compiler output… regardless of its performance", and FRAMING §8 predicted exactly
this — an instrument that "would reproduce, inside the spike itself, exactly the failure mode the spike exists to rule
out." The readings differ on one decidable sub-question, and it is the one to hand the owner: **is the 130-case fixture an
adequate acceptance test for a third runtime of this language?** The evidence answers **no**: 130/130 was achieved *while
both* §5 directions were breached (`f1` §1.9.3); **6 of 7** `KNOWN_DIVERGENCES` entries are `in_fixture: false`
(`compile.py:71-146`); the fixture holds **zero** `sort`/`filters`/`limit` cases (`xb` B.10) — two of the four clauses in
the question; **68 of 130** cases carry a value through a float8 conversion and the run exists at `extra_float_digits = 1`
only (`f1` §1.2); and **0 of 130** reach any of the eight sites at which the *reference* evaluator raises (`xa` A.3). If
the fixture is not the acceptance test, the artifact that would ship has none today — and Reading B governs. That is the
ruling this section asks for.

### 5.3 Gap 13 — the conjunction the four findings never state

Read separately each finding ends survivably. Read together, four facts that appear side by side in no section, each
verified against the corrected sections and, where marked, re-derived by this seat.

**(a) The compiled arm is slower at every size, in every observation.** B2 ÷ Path A = **4.15 · 3.89 · 3.79 · 4.36 · 6.71 ·
7.15** at 1 k → 1 M, re-derived by this seat from `analysis/measurements.json` (`path_a` vs `path_B2` `total_ms.median`).
No crossover; the gap widens with N. **The headline range is therefore 3.79×–7.15× slower**, the minimum and maximum of
those six sweep medians, and it is the only range this document quotes. **[consistency]** One further observation
exists and is not the headline: a single load-controlled re-run at **N = 20 000** puts B2 ÷ A at **2.55×** (492.63 /
1 257.03) — but it sits in `probes.json → recheck`, one of the three raw blocks `f4` §4.11 records as having **no
retained producer** in `proto/`, so it can be read but not audited or re-derived, and it is a single point, not a range.
Direction is stable across every observation; the multiplier is not.

**(b) No compiled *predicate* and no compiled *`derive`* column can appear in any index today. [consistency]** Across
**36 measured plans** the production GIN index appeared **0 times** and `enable_seqscan = off` changed **0 of 36**
(`f3` §3.2) — there is no index path to decline. `to_jsonb()` is `STABLE` and appears in **10 of the 11 compiled
outputs** in `proto/idxshape_preds.json` — the nine `where` predicates W1–W9 and the `derive` column D1, re-derived by
this seat — so PostgreSQL refuses the DDL: *"functions in index expression must be marked IMMUTABLE"* (`f3` §3.3 cause
2). **Four compiler changes must land before the first `CREATE INDEX` over a compiled predicate succeeds** (`f3` §3.4).

**The eleventh output is the counter-fact, and it is measured. [consistency]** The compiled *sort key* **S1** =
`nullif((data -> 'k'), 'null'::jsonb)` carries no wrapper, indexes today, and `f3` §3.6 H4 measures it **index-backed**:
`Index Scan using idxprobe_score_operand`, **0.065 ms** — *"where the only working pushdown lives today"* (`f3` §3.6).
So the earlier absolute — *no index containing compiled output can be created at all* — is **false**, and this leg is
stated here at its true strength: the refusal is the `to_jsonb` wrapper, not "compiled output". Two facts hold that
counter-fact to its own size: the same H4 measures that index's `jsonb` B-tree order disagreeing with
`sources.py:99-115`'s `_sort_key` at **9 of 9** positions (`xb` B.6), so the one indexable output is index-backed *and*
differently-ordered on a mixed-type column; and the thing (b) is invoked to block — the index that would fix (a) — is **not
blocked by a DDL refusal alone, which is how this leg's prop was stated and is wrong at that strength. [punch]** Two
obstacles sit in series and only the first is a refusal: **(i)** an index whose expression or predicate **is** the
compiled `where` cannot be **created** (cause 2, the `to_jsonb` wrapper, above); **(ii)** the obvious workaround — an
index on the **character-exact compiled operand** — **is created successfully and is still not used** for compiled W2
even with `enable_seqscan = off`, because an expression index is reachable only through an *indexable operator clause*
whose left side is the indexed expression and `xpr.truthy(to_jsonb(CASE …))` has no such operator at its root
(`f3` §3.3 T4a: *"The index exists, holds exactly the right values, and is unreachable"*). **Creatable but unusable**
is the accurate statement of (ii); *refused* is not — and it is the stronger form, because what lifts it is a change
to what `compile.py` **emits**, not a permission: `f3` §3.3 H2d measures the planner **using** that index (`Bitmap
Index Scan on h2a`) once the wrapper is gone and the clause is emitted as the bare boolean. That is why `f3` §3.4
lists **four** compiler changes rather than one, and why the conjunction's coupling survives the correction even
though its absolute does not. It is a `compile.py` representation choice, not a law of
Postgres — `f3`'s isolating experiment creates the same index once the wrapper is gone (H2a, T7d) — but nothing else
moves first.

**(c) Nothing reports a fallback, and half the divergence set is invisible in principle.** `resolve()` has no field for
how a result was computed (`f2` §2.8). The undetectable set is **3.6× larger than the body states**: mapping `f1`'s
inventory onto `f2`'s rule table gives **18 of 33 distinct `expr`-layer classes undetectable at query time by any
mechanism**, against `f2` §2.8's five (`xc` C.8–C.9). **Both** of §5's named directions are inside it; neither is in
`f2`'s five.

**(d) Two of the four clauses in the question have no evidence at all.** `filters`/`sort`/`limit` live outside `expr.py`,
in `sources.py:67-115`. `xb` B.8 enumerates **ten obligations** a pushdown must reproduce and scores **zero compiled, zero
tested, zero fallback-ruled** — two of them with a positive argument that they *cannot* be compiled (the first-wins
tolerant tie-break, because `jsonb` destroys document key order; the rank-3 container sort key, which is Python `repr`).
The only `filters` pushdown anyone wrote silently dropped **2 of 3 rows** on plain ASCII keys (`measurements.json →
tolerant_key_probe`, re-verified by this seat: `["T-1","T-2","T-3"]` vs `["T-1"]`).

> **The sentence a decision needs, and which no finding contains: there is no measured configuration in which pushdown as
> prototyped is simultaneously faster than today's path and no less correct.**

And the four are **not independent**, which is the part that matters: the fix for (a) — indexing — is blocked behind (b);
the fixes for (c) add per-row work to (a), because honouring §5 for the undetectable class means the runtime must check
its own domain per row and raise (`xc` C.12 item 3 — the register's undetectable count and its run-time trigger cost move
in **opposite** directions); and (d) removes the payload win that (a) was supposed to be traded against. **INFERENCE,
arithmetic mine, inputs measured:** the headline **19 667.5×** payload reduction (317.02 MB → 16.1 kB at 1 M, `f4` §4.4)
is produced by `ORDER BY … LIMIT 50`. With `sort` outside any subset, `LIMIT` goes with it (`xb` B.7 — `LIMIT 50` is
well-defined only under a matching total order). A `where`-only pushdown returns the qualifying set, measured at **5.00 ·
5.10 · 5.27 · 5.35 · 5.20 · 5.23 %** across the six sizes (`measurements.json`, `qualifying_rows_total ÷ N`, re-derived
here) — at 1 M that is **16.59 MB, i.e. 19.1×**, not 19 667.5×; the sort+limit half is the other **1 029×**. The largest
confirmed benefit of pushdown is contingent on the clause with the least evidence in the spike.

### 5.4 What closure added that the panel did not have — and it moves both ways

`panel.json` is dated 13:50; `xa` 14:22, `xc` 14:23, `xb` 14:26, `xd` 14:33 — the mtimes at which each section **first
landed**, which is what makes the point: `panel.json` predates all four. **[consistency]** Those four mtimes no longer
read as above: the closure-consistency pass rewrote `xa`–`xd` in place (and this file), so `ls --full-time` now shows
that pass's timestamps. The landing order is preserved in `consistency.md` §2, which cites `xa` 14:22:47 and `xc`
14:23:07 independently; `panel.json` itself is unmodified at 13:50:22.

**(1) `expr` is not total, and 7 of its 8 raise mechanisms sit INSIDE the only named subset.** `xa` A.2 establishes eight
mechanisms across nine source lines and four exception types by which `evaluate()` raises on data, against `expr.py:640`'s
"never raises for data reasons". Against `panel.json[0]`'s subset (`abs ceil coalesce count floor if length max min
round`, all arithmetic operators, all comparisons): **R1** (dates) is excluded; **R2–R5** are `round`, **R6** is
`floor`/`ceil`, **R7** is `%`, **R8** is `==` — all **inside** it. Re-verified live by this seat through the public
`expr.evaluate` in `GIMS-Project/.venv`, tracebacks at `expr.py:521 · 525 · 545 · 624 · 375 · 430`; and both in-subset
**raise → value** witnesses re-run through the existing differential instrument `analysis/fuzz/differ.py` (`run_case`,
read-only `SELECT` against `autosql_spike`):

| expression / record | Python | compiled SQL | in `panel[0]`'s subset? |
|---|---|---|---|
| `round($.a,$.n)` / `{a:1.0, n:"1e400"}` | **`OverflowError`** (`expr.py:521`) | **`1`** (`sql_typeof: number`) | **yes** — `round` |
| `$.a == $.b` / containers nested 498 deep | **`RecursionError`** (`expr.py:375`) | **`true`** | **yes** — `==` |

That is §5's second clause verbatim and §4's "produces a **number** rather than an error or an explicit fallback"
verbatim, **surviving the best subset anyone named** — 2 of the 4 measured raise→value witnesses (`xa` A.5) are in-subset.
Note `differ.py` buckets them `PY_RAISE`, not `DIVERGE`: a reader counting `DIVERGE` lines in `analysis/fuzz/*.txt` does
not see them.

**(2) The fallback target itself raises, uncaught, and the fix is in GIMS.** `sources.py:147` and `:162` call `evaluate()`
outside any `try`; measured in `xa` A.5(ii), one poison row at position 0, 5 or 9 of a 10-row list takes the **entire
widget** to HTTP 500 via `core/errors.py:115-119`, with no partial result and no signal. On the one battery quantifying
overlap, the in-memory retry **also raises on 65 of 159** SQL raises = **40.9%** (`fuzz/G2b_round_raises.txt`). "Fall back
to in-memory" is not a safe harbour, and `sources.py:335`'s contract — "data problems degrade to empty/None, **never
crash**" — is false today, independently of this spike.

**(3) `filters`/`sort` are not merely uninstrumented; two obligations are uncompilable** (§5.3(d)). Plus a real-data fact
no seat had: `find_actual_key` returns the **first** key in document order that normalises to the target, and **4 166 of
17 345 rows (24.0%)** of the live `guts-ledger` `instances` table — **table-wide, every collection, not `LedgerRecord`
alone** — carry two keys that normalise the same (`run_id` and `_runID`, holding *different* values). `jsonb` does not
preserve object key order, so **migrating this store to Postgres changes the answer of the existing Python path on those
4 166 real rows, with no pushdown involved** (`xb` B.4). **`xb`'s scope note, carried across rather than dropped:
[consistency]** the answer changes only **for a query that resolves a `runid`-normalising key** (`runID` / `run id` /
`RunID` / `RUN_ID` through `find_actual_key`), not for every read of those rows; and `xb` labels the production
relevance an **INFERENCE** — *"whether a production `DataSource` targets a collection holding this pair is **not
established by this spike**"*, which needs the `DataSource` corpus `f2` §2.9 records as absent. What **is** established
is that the collision occurs in real stored GIMS records at **24.0%** and **16.3%**. **The denominator is corrected
here, and it is a snapshot rather than a standing property. [punch]** This section first published **17 342**;
`xb` B.4 re-derived it and states it as **17 345 = `LedgerRecord` 17 148 + `WorkOrder` 197, the whole table as of the
14:16:56 checkpoint, with the collision rate 4 166 / 17 345 = 24.02 %** — numerator and the published **24.0 %**
unchanged, only the denominator moves. 17 342 is that same table one checkpoint earlier, re-derived by this seat from
the spike's own retained sweep output (`xd_sweep.json`: `LedgerRecord` **17 145** + `WorkOrder` **197**), and 17 148
is `xd` D.2's 14:20 census. An independent read-only re-census by this seat, at the store's current main-file
checkpoint, returns **17 398** (`LedgerRecord` 17 199 + `WorkOrder` 199) with the numerator still exactly **4 166**
(the pair `run_id`/`_runID` in every one of them, 0 non-dict rows, 0 parse failures) — i.e. **23.9%** against a
denominator that keeps growing. **Cite 17 345 against its checkpoint; the invariant here is the numerator, not the
rate.**

**(4) Reachability — and it cuts against every seat.** `xd` swept 37 078 real rows, **5 236 427** numeric literals and **1 096 202** string values ***plus object keys*** read-only — `xd` D.4's own row label; the string-**values**-only count is **495 115** (`xd` D.2) **[consistency]** — two independent instruments agreeing exactly. **0 witnesses** for D1–D5 (max |v| anywhere
1.787e+12, 284 decades short), **0** for D8/D10 in a corpus carrying 206 567 non-ASCII code points, **0** for D12–D14 and
no writer here that could make one — *that weakens seat [1]'s sharpest witnesses*. But the classes reached **at scale**
are the coercion and tolerant ones: `human_required` the **string** `"false"` on 17 144 rows; one key holding a number on
315 rows and an ISO string on 9 (2.8%); `'0002'`; `'60824'`; weight fields 100% string; `due_date` **absent on 42.9%** of
the one real dashboard's own collection — i.e. exactly the half of the question with zero compiler, zero test and zero
rule; and `f3` H3's constructed `{"score":"n/a"}` index hazard is reproduced by **real rows**. *That weakens both
CONDITIONAL-GO subsets.*

**(5) The DETECT/AVOID distinction — the one closure item that cuts FOR a CONDITIONAL-GO, and it was missing from this
list. [consistency]** `xc` C.1 separates the two mechanisms that satisfy FRAMING §5 and shows AVOID is **static and
construct-keyed**, decidable at `sources.py:345` before any SQL runs. That is a direct answer to seat [1]'s
value-vs-construct argument (§5.1), and this section previously listed only closure items that cut against
CONDITIONAL-GO — an omission that made the synthesis one-sided in the direction of its own verdict. Its limits are as
measured: AVOID does not satisfy §4's *"detectable"* clause, costs **46 of 130 cases (35.4%), 12 of 22 functions and the
canonical measured widget**, and `xc` C.10 records the hole that **D13 reaches through `if`/`not`/`and`, which every
subset keeps**, bounded only by a deployment assumption about writers.

Net: closure weakened seat [1]'s **witnesses**, strengthened its **structural argument**, and — item (5) — **narrowed**
one leg of it.

### 5.5 My recommendation, and the reasoning

**NO-GO on *a standalone compiler plus a thin GIMS adapter*, as scoped by this ticket.** Five reasons.

**1. CONDITIONAL-GO requires a subset that *provably* agrees, and none exists.** The only named subset was derived by
attributing each observed divergence to a construct and assuming the remainder clean — its own author says so: *"the
subset's residual divergence rate is not low, it is **unmeasured**"* (`panel.json[0]`). Closure shows the assumption is
**false, not merely unproven**: two of the four measured raise→value witnesses are inside it (§5.4(1), re-verified live
this pass); the subset's residual is **not merely unmeasured but partly measured and non-empty** —
`analysis/fuzz/A_f8_guard.txt` §A2 measures **8 of the 16 paths diverging at `a = 1e300`** as entirely in-subset,
one of which (`max($.l)`) returns SQL `1` for Python's `1e+300`, a silently wrong *number* rather than a null
(`xc` C.10) **[punch]**; and `xc` C.10 records a further hole — **D13** reaches through `if`/`not`/`and`, which every subset keeps, and
is bounded only by "no non-Python writer", a deployment assumption rather than a compiler property. FRAMING §4's word is
*provably*; attribution is not proof.

**2. The architecture's name is falsified by its own evidence: the adapter cannot be thin.** The compiler is the half that
works. The correctness lives across the seam, in the GIMS tree:

| change | where | why it is required |
|---|---|---|
| `pushed_down` + `fallback:[{scope,reason}]`, plus a UI badge distinct from `capped` | `sources.py:357`; `frontend/lib/dashboard/widgets.jsx:277` | FRAMING §5. Nothing else matters without it (`f2` §2.8) |
| per-row `try/except` around `evaluate()` | `sources.py:147, :162` | otherwise the fallback is an HTTP 500, not a report (`xa` A.5 ii) |
| tolerant key resolution in SQL — **or** `filters` excluded | `sources.py:67-85`, `deep_search.py:19-39` | silently drops 2 of 3 rows today (`xb` B.3) |
| the 5-rank `_sort_key` tuple — **or** `sort` and `limit` excluded | `sources.py:99-115` | jsonb B-tree order differs at **9 of 9** positions (`xb` B.6) |
| `derive` ordering + shadowing semantics | `sources.py:133-148` | order is semantic; reversing two entries yields `null` silently (`xb` B.9 case B) |

The one item the compiler owns — "emit the JSON key as a literal, not a bind parameter" (`f3` §3.4 prerequisite 4) — puts
tenant-authored text into SQL literal position. **OPINION (mine):** a new injection surface, costed nowhere in the
evidence.

**3. The ticket's premise is negative, and the defect the spike found has a cheaper — but not free — fix.** The compiled
arm is **3.79×–7.15×** slower (§5.3a) **[consistency]**. The real finding is that `MAX_SCAN` is a **correctness** cap:
top-50 recall **100 / 88 / 38 / 4 %** at 20 k / 25 k / 100 k / 1 M, 98% of qualifying records never examined at 1 M,
under a badge reading *"Result capped for performance"* (`f4` §4.7; `widgets.jsx:277` verified live here). Pushdown
fixes that. So, more cheaply, does raising `MAX_SCAN` — **but the citation for that must be corrected, and it cuts the
other way. [consistency]** `sources.py:61`'s comment, re-read live this pass, is: *"Safety cap: v1 materialises every
candidate row in memory before filtering… `truncated` is surfaced so the UI can warn. **(Pushdown filtering removes
this.)**"* The change that comment anticipates is **pushdown — this project** — not raising the constant. GIMS's own
author documented the cap as a stopgap for the absence of the thing under review here; an earlier draft of this section
read the comment as endorsing its own alternative, which it does not.

**The alternative's own cost, stated against today and not only against the prototype. [consistency]** **INFERENCE**
(arithmetic `panel.json[2]`'s, re-derived here from `measurements.json → sizes.20000.path_a`: derive 7.27 µs/row +
filter 1.23 µs/row extrapolated to 1 M over the already-paid 8 161 ms acquire): ≈ **16.7 s uncapped and correct**.
Against the prototype that is favourable — B2 measures **59 590 ms** at 1 M, so ≈**3.6×** faster, same answer. Against
**today** it is not: Path A at 1 M measures **8 331 ms** (`measurements.json → sizes.1000000.path_a.total_ms.median`),
so the one-line change is ≈**2.0× slower than today's latency**, and it buys correctness by paying for it in wall clock.
It also leaves **entirely untouched** the two things §5.3 and §5.9(1) call the actual prize: the **98% of Path A's time
spent acquiring 980 000 records it never examines** and the **≈2.4 GB of marginal per-request Python heap** at 1 M
(`f4` §4.4, §4.5). Both are already paid **today**, with the cap in place — `f4` §4.4 measures Path A pulling all
**1 000 000** rows into Python while evaluating only **20 000** — so lifting the cap does not reduce them by one byte or
one millisecond; it adds ≈8.5 s of per-row Python work on top of them, and it does so on the concurrency axis §5.11
names as where that memory win would matter most. To be worth building, the
compiled path must first beat a one-line change — and this point is a claim that the one-line change is **cheaper**, not
that it is **free**.

**4. Gap 13's conjunction and its coupling** (§5.3): nothing measured is both faster and no less correct; the speed fix is
blocked behind the index, the silence fixes cost speed, and the largest measured win belongs to the clause with no
evidence.

**5. Sequencing is not neutral, and both CONDITIONAL-GO seats say so themselves.** **OPINION (mine):** a CONDITIONAL-GO
produces a build carrying sunk cost facing the gate that would have to kill it; a NO-GO plus two named experiments
produces the same experiments with no build attached. The evidential content of the two positions is nearly identical, so
the label should be chosen for what it does to the next decision. **NO-GO here does not mean "the translation is
impossible"** — §5.9 records that it was demonstrated — **nor "discard the work"**: it means do not fund a standalone
compiler + thin adapter on this evidence, run E1 and E2 (§5.11) first, and let a GO be earned.

**Reconciliation with `f3` §3.9 — the document's second recommendation, which this section had not engaged.
[consistency]** `f3` §3.9 assembles a four-rule emission routing and closes, labelled **OPINION**, that rule 1's
measured-agreeing shape set being *"one distinct expression shape"* is *"an argument for shipping **rule 3 and rule 4
first**, and treating rules 1 and 2 as optimisations that must earn their way in case by case."* A gate reader must not
meet that and then meet NO-GO with nothing joining them, so: **I adopt `f3` §3.9's routing as the shape a future GO
would take, and record that `f4` §4.4 removes rule 3's performance premise.** `f3` states rule 3 — *"emit the compiled
`xpr` predicate as a filter… A CORRECT ANSWER AT SCAN SPEED"* — and explicitly defers its open question: *"whether it
beats the in-memory path is finding #4's question, not this one."* Finding 4 answers **no**. **INFERENCE, mine, and the
identification is the load-bearing step: `f4`'s B2 arm *is* rule 3's route measured** — the compiled predicate run
server-side with no usable index, which `f3` §3.2 confirms is the actual condition (the production GIN index appeared
**0 times in 36 plans**, and `f4`'s B3 "inlined+GIN" tracks B2 to within ~1%: 1 128.87 vs 1 138.61 ms at 20 k, 59 609.77
vs 59 590.03 at 1 M). On that identification rule 3 is **3.79×–7.15× slower than Path A at all six sizes, with no
crossover and a widening gap** (§5.3a). So rule 3 survives as **correctness** — it is the correct answer, and that is
why `f3` calls it the reason the three non-raising storage-layer hazards are survivable — and fails as **performance**,
which was the ticket's premise. Rule 4 (*"fall back to in-memory, REPORTED"*) survives intact and is **unbuilt**:
nothing reports a fallback today (§5.3c), it is the top row of the table in point 2 above, and it is a GIMS change, not
a compiler one. **Shipping rules 3 and 4 first therefore means shipping a correct path that is 3.79×–7.15× slower than
today's plus a report GIMS does not yet emit** — which is not a contradiction of NO-GO but its mechanism, and it is why
the two conditions §5.11 names (E1, E2) are the ones that would change it.

**What the closure-consistency repairs did to these five reasons — stated here so the gate is not left to find it.
[consistency]** The recommendation is unchanged; its base is narrower on two legs and firmer on one, and I record which
is which rather than leaving the label to carry the difference. **Weakened: reason 3.** Its cheaper-alternative half now
carries the alternative's own price — ≈**2.0× slower than today's 8 331 ms** at 1 M, with the acquisition cost and the
2.4 GB heap untouched — and the code comment it cited turns out to anticipate *pushdown*, i.e. this project, so
`sources.py:61` is evidence **for** the ticket's premise, not against it. Reason 3 now says only that the cheaper fix is
cheaper **to build**, which is a weaker claim than it made before. **Narrowed: reason 4's leg (b)**, from *no index at
all* to *no **predicate** or **derive** index*, with one compiled output measured index-backed at 0.065 ms (§5.3b) — the
coupling it exists to establish survives, the absolute does not. **Narrowed outside the five: seat [1]'s
value-vs-construct argument** (§5.1), which `xc` C.1 scopes to DETECT. **Firmer: the performance leg** — the headline
range floor rises from 2.55× to **3.79×** once the un-audited `recheck` block is demoted to what it is (§5.3a) — and
**§5.2's fixture-adequacy argument**, which gains the residual that `conformance.py`'s outcome-assignment branches were
never exercised (§5.6, §5.9). Reasons 1, 2 and 5 are untouched. **On the balance of that: I still recommend NO-GO, and
`human:owner` still decides at `sp_decide`** — but a reader who wanted to rule the other way should attack reason 3 and
leg (b) first, because those are the two the evidence now supports least.

### 5.6 The strongest argument against my recommendation

It is `panel.json[0]`'s, and closure made it stronger. At full strength: *the literal question was answered YES and not
narrowly — **130/130** `COMPILED_AGREES`, max |SQL − Python| = **0.0**, **0 of 54** numeric cases consumed the 1e-9
epsilon, 22/22 string cases character-exact (re-derived here from `proto/results.json → agreement_strength`), by a harness
whose **comparator and DB plumbing** are proven able to fail: **23/23** negative controls `ok`, including **NC13**, which
is FRAMING §5 written as an executable test, and `control_python_vs_fixture_expect = {checked:130, failures:[]}`
— **but not, on `f1` §1.7's own correction, a harness proven able to emit a failing *outcome*, and this steel-man may
not claim it: [consistency]** NC11/12/13 each build a value from a hand-written SQL string (`to_jsonb(999::float8)`,
`NULL::jsonb`, `to_jsonb(0::float8)`) and call `matches()` **directly** (`conformance.py:1010-1031`, read by this seat);
**none constructs a case entry, none asserts `outcome == "COMPILED_DIVERGES"`**, and the outcome-assignment branches at
`conformance.py:376-455` are exercised by **nothing**. What 23/23 proves is that the **comparator rejects each
wrong-answer shape** and that the **plumbing is live** (record column, `ctx` bind, SQL-NULL vs jsonb-`null`, raise
capture). That the three non-pass outcome *labels* are reachable is an **INFERENCE**. So the
oracle is not a tautology and the agreement is not degenerate — the **union of all five** constant emitters covers
**55/130** (19 null + 35 boolean + 1 zero), so **75 of 130 agreements are unreachable by any of them**; the strongest
**single** constant scores 20/130, which on its own would leave 110 (`f1` §1.6; `results.json → degenerate_baselines`
= `{true:20, null:19, false:15, zero:1, empty-string:0}`, re-derived here — 75 is the conservative figure and it comes
from the union, not from the 20) **[consistency]**. Every §5 witness relied on is a **constructed** record: `xd` swept
5 236 427 real numeric literals and **1 096 202 real string values *plus object keys*** (`xd` D.4's own row label; the
string-values-only figure is **495 115**, `xd` D.2) **[consistency]** and found **zero** production witnesses for the
float and Unicode classes, and no writer here that could
make one; the two verified live need tenant expression text (`round($.x,"1e400")`) or a 498-deep container. Meanwhile
NO-GO blesses a status quo measurably wrong at a far higher rate — 4% recall at 1 M, monotonic across the six
measured sizes, 100 / 100 / 100 / 88 / 38 / 4% (**"from row 20 001" is struck here [punch]:** `f4` §4.7 withdraws the
onset as never measured — nothing was run between N = 20 000 and N = 25 000 — and `f4` §4.12 row 7 records the
withdrawal a second time; the smallest over-cap size tested is 25 000, already 12% wrong) — on a
machine whose largest real collection is **17 148 rows = 85.7% of `MAX_SCAN`** and **0.8–7.4 days from crossing it** on
three of four measured growth bases (`xd` D.8). And both CONDITIONAL-GOs are structured so nothing ships before the
acceptance battery passes, making NO-GO the more expensive label if that battery would have passed.*

**Why it does not move me.** (i) `xd`'s zero cuts the *witness* argument, not the *instrument* argument — and `xd` says so
against itself: *n* = 1 machine, 1 operator, **one writer signature across 5.2 M literals**, 60.2% of the corpus written
by AutoDev's own tooling, the only tenant-shaped project contributing **222 rows across 18 collections** and the real
dashboard's own source **7 rows**; its closing words are *"Nothing here extrapolates to production."* "No witness in the
corpus we could reach" is not "no witness", and a corpus with one writer cannot answer a question about a second writer —
which is exactly what D12–D14 ask. (ii) The classes `xd` **did** find at scale are the ones with no compiler, no test and
no rule at all (§5.4(4)); reachability does not clear the subset, it relocates the risk into the half of the question this
spike never instrumented. (iii) On the status quo I accept the force entirely — which is why §5.5 point 3 carries a named
alternative rather than a shrug. `MAX_SCAN`'s wrongness is **bounded and signalled** (`truncated` exists and propagates,
however badly worded); the compiler's is unbounded and unsignalled, 18 of 33 classes invisible in principle. Replacing a
signalled bounded error with an unsignalled unbounded one is the trade §5 forbids, and the cheapest fix for it is not this
project.

### 5.7 If the owner rules CONDITIONAL-GO — the subset, and what "provably" would cost

I do not recommend one, so this names the subset he would have to adopt instead, corrected by closure. **Start from
`panel.json[0]`'s subset** — all 10 leaf/structural node types, all 5 arithmetic operators, all 6 comparisons, all 5
field-path forms with a compile-time `|literal index| < 2³¹` check (D19), and 10 of 22 functions: `abs ceil coalesce count
floor if length max min round`. **36 of 48 constructs, 84 of 130 cases (64.6%)** — that seat's computation, not re-derived
when this section was drafted; **re-derived and reproduced exactly at closure [punch]**, as the control on the
corrected figure below.

**Closure removes more**, on §5.4(1): `round` (R2–R5), `floor`/`ceil` (R6), `%` (R7), and `==`/`!=` over container
operands (R8) — 7 of the 8 mechanisms by which the *reference* runtime raises, and 2 of the 4 measured raise→value
witnesses. **The resulting fixture coverage was NOT ESTABLISHED when this section was drafted. It has since been
MEASURED, at closure, and the answer is 32 of 48 constructs, 68 of 130 cases (52.3%). [punch]** The instrument is
`proto/closure_subset_coverage.py` → `analysis/subset-coverage.json`: **built during the closure pass, not part of the
original investigation** — no seat ran it while the findings were being collected — read-only, importing the **real**
parser (`core.dashboard.expr`, `GIMS-Project` @ 995cc59) and walking all 130 fixture ASTs at `f2` §2.1's granularity,
with no database connection and nothing written into either GIMS tree. **Re-derived independently by this seat with a
separately-written walker** over the same two files (`expr.py` md5 `5bd9db65…`, `expr_vectors.json` md5 `5b028492…`):
**84/130** for `panel.json[0]`'s uncorrected subset — reproducing that seat's published figure exactly, which is the
control that makes the second number credible — and **68/130** for the corrected one. **The correction's price is 16
further fixture cases**, and it decomposes exactly, each construct the *sole* blocker of the cases it removes:
`%` **7**, `round` **5**, `floor` **2**, `ceil` **2**. Construct arithmetic, auditable: 48 − the panel's 12 excluded
functions = 36; − `round`/`floor`/`ceil` = 33; − `%` = 32. **Corrected function list, 7 of 22: `abs coalesce count if
length max min`.** The `==`/`!=` container-operand clause costs **0** cases here — across all 130, `expr._eq` is
called 16 times and never once on a list or a dict, which is `f2` §2.3's 7-of-36-cells table reproduced cell for cell
— so **its price is paid entirely outside the fixture**, which is the same place §5.2 says the fixture's own
inadequacy lives. That clause is also the one genuinely ambiguous term (whether an operand *is* a container is a
property of the **row**, not the AST — the grammar has no container literal, `expr.py:185-214`), so all three
defensible readings were measured rather than guessed: **68** literal · **62** any operand that *could* be a container
· **56** any `==`/`!=` at all. 68 is the clause as written. Do not quote 84/130 for the corrected subset.

**What that number does to the CONDITIONAL-GO reading — stated plainly, not buried. [punch]** It **weakens**
CONDITIONAL-GO, modestly, and it does **not** move my verdict, which never rested on this figure. The corrected subset
compiles **just over half** the contract fixture — not most of it, and not a tenth: **68 of 130**, against the **84**
the panel seat argued from, so that seat's coverage claim was **12.3 points of the fixture too high**. What leaves
with the 16 is the whole of `round`/`floor`/`ceil`/`%`; what was already outside is every date function, every string
function, `sum`, `avg`, `concat`, `contains`, `number`, `lower`/`upper`. **AVOID's price, restated at the corrected
subset: 62 of 130 cases refused, 47.7% — not the 46 of 130 (35.4%) that §5.1, §5.4(5) and §5.8(b) quote from `xc`
C.10/C.12, which is the uncorrected subset's complement.** Three things stop this from being decisive in either
direction, and they are why it does not move the verdict: **(i)** 52.3% is a **contract-surface** measure, and §5.2
rules the fixture is not the acceptance test — it is not a fraction of production traffic, and none may be quoted at
the gate (`f2` §2.9, no `DataSource` corpus); **(ii)** the residual divergence rate **inside** the surviving 68 is
**not fully measured — but it is no longer zero-by-assumption**: `xc` C.10 now measures 8 of `A_f8_guard.txt`
§A2's 16 diverging paths as in-subset, including one silently-wrong number **[punch]**. What remains unmeasured
is the *rate*, which is §5.5 reason 1 and is untouched by a coverage count — E1 is what would measure it;
**(iii)** the one widget measured end to end is a **date** widget, outside the subset at 84/130 and still outside at
68/130, so no existing measurement is subset-legal either way. **If the owner rules CONDITIONAL-GO, the honest headline is
that the named subset compiles 52.3% of the contract fixture with an unmeasured residual — not 64.6%.**

**"Provably" is not satisfied today, and the reason must be stated plainly:** the subset was derived by attribution.
`string`'s 0.0280% and `sum`'s up-to-99.73% rates were found only because a seat went looking outside the fixture; the
surviving functions have **not** been probed at comparable depth. **The subset's residual divergence rate is UNMEASURED,
not low.** The experiment that would measure it, as an explicit condition:

> **E1 — the subset acceptance battery.** Re-run all **21** batteries in `analysis/fuzz/run_all.sh` — plus `A_range`,
> `A2_boundary` and `B2_overflow`, which the script does **not** regenerate (`critic` §16c) — plus the 130 conformance
> cases and the 403 coverage probes, with AST generation **restricted to the corrected subset** and the value domain
> widened to reach the eight raise sites (`xa` A.3 shows every clean battery is clean because its generator tops out at
> |value| 2026.0, nesting depth 4, `round` ndigits ∈ {−1, 2} and zero offset-bearing dates). **Bar: zero outcomes in the
> classes "different value", "value → NULL" and "NULL → value", AND zero cases bucketed `PY_RAISE` in which SQL returned a
> value.** The second clause is new and is what catches §5's raise→value direction, which the existing runs bucket away
> from `DIVERGE`. **State to beat**, all three as **expressions that ran**, i.e. `AGREE + DIVERGE (+ SQL_RAISE)`, not
> `AGREE` **[consistency]**: `H_ordinary` **0/3 881** · `H_unicode` **4/3 867** · `H_extreme` **23/3 880** real
> (`f1` §1.9.2 D22, §1.9.6 D21; re-derived here from `analysis/fuzz/H_*.txt` — `H_unicode` reads AGREE 3 863 /
> DIVERGE 4 / PARSE_ERROR 133 of 4 000, so **3 867 ran** and the earlier 3 863 was the AGREE count; `H_ordinary` 3 881
> AGREE + 119 `PARSE_ERROR`; `H_extreme` 3 833 AGREE + 44 DIVERGE + 3 `SQL_RAISE` + 120 `PARSE_ERROR` = 3 880 ran).

Four further conditions closure forces that no seat wrote:

1. **The 130-case fixture may not be the acceptance test** (§5.2). E1 is, and it must gate every future change to
   `expr.py` in all three runtimes, or the coupling in §5.8(d) is unmanaged.
2. **`sources.py`'s `evaluate()` calls must be made total first, in GIMS.** *Test:* the poison row
   `{"d":"0001-01-01T00:00:00+14:00"}` at index 0, 5 and 9 of a 10-row list returns 10 derived / 5 filtered rows, not an
   uncaught `OverflowError` (`xa` A.5 ii — currently fails).
3. **`filters` and `sort` stay OUT until obligations 1–10 of `xb` B.8 are compiled and tested**; two carry an
   impossibility argument. *Test that already exists and currently FAILS:* `measurements.json → tolerant_key_probe` must
   return `["T-1","T-2","T-3"]`, not `["T-1"]`. **With `sort` out, `limit` is out, and the payload win is 19.1×, not 19 667.5×** (§5.3d).
4. **The performance gate nobody ran.** *Test:* `proto/bench.py`'s Path A against a compiled **subset-legal** widget on
   the **same** table and corpus at 20 k / 100 k / 1 M, quiet host, load recorded. Bar: below Path A's measured
   **13.3–15.0 µs/row** under the cap (`f4` §4.5) and below the ≈**16.7 µs/row** uncapped alternative (§5.5 point 3,
   INFERENCE); `panel.json[2]`'s C-0 states the same gate at ≤ 5.5 µs/row. Note the canonical measured widget is a
   **date** widget, outside every proposed subset — **no existing measurement is a subset-legal one.**

None of these is "fix the bugs": each names an artifact, a bar and a test that exists or is one run away.

### 5.8 The cost of the fallback machinery — the item FRAMING §4 #5 names by hand

**(a) The trigger is measured and bounds almost nothing.** Compile-time refusal **0.0307 ms/widget**, 0.0004%–0.22% of
Path A — re-derived here from `measurements.json → fallback` as parse 0.008845 + 0.010212 and compile 0.002780 + 0.004768
(`plan_ms` 0.026605) **plus** `detect_uncompilable_ms` 0.004079. Run-time refusal: a constructed worst case of **6 916.85
+ 1 493.92 = 8 410.77 ms vs 1 493.92 ms, +463%**, composed from two separately-run probes and labelled a composite by `f4`
§4.9 itself. **A run-time fallback can only fire on the RAISE classes — 6 of the 34 register ids;** for the 18
undetectable classes (19 ids) there is nothing to trigger (`xc` C.12). **[consistency]** Units, per `xc` C.8: those two
figures are counted in different denominators — ids and classes — and may not be summed. **(b) The only rule reaching the silent classes is AVOID, and its price
is coverage, not latency** — the same ~0.03 ms per request, costing **46 of 130 fixture cases (35.4%), 12 of 22 functions,
and the canonical measured widget** (`xc` C.10, C.12), and more under the corrected subset (§5.7). **(c) The one-time
build — 7 items (`f2` §2.8), one mispriced, two rewrites.** The `pushed_down`/`fallback` field is a **public GIMS contract
change plus a frontend change**; C3 (recursion → explicit stack) rewrites a 464-line compiler's traversal; C4 changes the
emitted SQL's *shape*, so **every conformance number is re-earned**; and "R3 — one line in `runtime.sql`" is wrong in a
way that matters — `fuzz/B2_overflow.txt`'s own header records that the 297-digit guard is **why `+`, `-` and `sum()`
cannot overflow today**, *"an accident of defect #1, not a design"*, so correcting it converts D1–D5's silent population
into `22003` aborts priced at up to +463% (`critic` §8; `xc` C.12 item 3). **(d) The standing obligation nothing prices.**
The architecture creates a **third runtime**: `expr.py` **646** lines, `frontend/lib/expr.js` **373**, `compile.py`
**464** + `runtime.sql` **427** defining **21** `xpr.*` functions — three languages, four artifacts, 48 constructs, and
one 130-case fixture that **demonstrably cannot detect its violation**. The SQL leg is additionally conditional on a
session GUC, a collation, a planner choice, an `IMMUTABLE` declaration the server does not verify, and the server version.
**OPINION (mine, following `xc` C.11b):** a permanent, unbounded coupling; the figure is *not established*. *What would
establish it:* size `f2` §2.8's change list against `sources.py:353-356` and the widget contract, then run E1 and count
how many of the 34 register ids the subset closes — a `sp-synth` task FRAMING §3 forbids here.

### 5.9 What the spike delivered, regardless of the verdict

**1. The literal question, answered yes and audited.** 130/130 `COMPILED_AGREES`, 0 diverges, 0 did-not-compile, 0 SQL
errors; max |Δ| **0.0**; **0 of 54** numeric cases needed the epsilon; 23/23 negative controls including NC13; oracle
control 130/130 — all re-derived here from `proto/results.json`. Plus **403/403** **value-domain *kind*** probes
closing `_eq` 7/36→36/36 and `_order_cmp` 4/36→36/36 (`f2` §2.4). **[amend-2026-08-21]** That 403/403 is scoped to
those probes and **not** to out-of-fixture probing at large: the separate `proto/results.json →
out_of_fixture_probes` set is **8 probes — 3 agree, 4 `DIVERGES`, 1 `SQL_ERROR (totality violation)`**, so this
line previously overstated a clean sheet. Same authority and figures as `f2` §2.4's summary-row note; this site was
missed by that round and scoped on 2026-08-21 by the parts-reconciliation pass (`.parts/README.md`). **2. A complete divergence register** — **34 `expr`-layer ids** with
cause, direction, rate, blast radius and detectability, of which **15 ids are detectable** and **19 ids = 18 classes**
are undetectable; folding D21 into D1–D5 gives **33 distinct classes**, which is the denominator §5.3(c) uses (`xc`
C.8). **[consistency]** An id count and a class count may not be added: the earlier "34 ids, 15 detectable / 18
undetectable" mixed the two and did not sum. Blocks D, E and F add **9 further ids** (4 storage, 2 route-conditional,
3 clause-level), counted separately by `xc` because they are conditional on a storage decision or sit outside `expr`.
The register is the artifact a future attempt starts from instead of rediscovering. **3. Four GIMS defects that exist with or without pushdown:** `expr` is **not total** (8
mechanisms, 9 lines, 4 exception types — `xa` A.2), falsifying `expr.py:640` and `recon/semantics.md` §11;
`sources.py:335`'s "never crash" contract is **false** (one poison row 500s the widget); `MAX_SCAN` is a silent
**correctness** cap (recall 100/88/38/4%); and migrating `instances` to `jsonb` would change **today's** Python answer on
**4 166 real rows** — *for a query that resolves a `runid`-normalising key*, with the production relevance labelled an
**INFERENCE** by `xb` itself because no `DataSource` corpus exists to say whether one targets that collection (`xb` B.4;
`f2` §2.9) **[consistency]**. Only the third was suspected in advance. **4. The index answer, including the negative
one:** `0002_instances_data_gin.sql` needs **no change** and costs pushdown nothing; the shape needed is per `(collection,
key, extractor)` B-tree; no compiled predicate and no compiled `derive` column can appear in **any** index today, while
the compiled **sort key** can and is measured index-backed at **0.065 ms** (`f3` §3.2–§3.4, §3.6 H4) **[consistency]**
— and FRAMING §2
anticipated the conclusion by the wrong mechanism, which the finding says. **5. A reachability baseline** — 37 078 rows, 5 236 427 numeric literals, 1 096 202 string values **+ object keys** (495 115 string values alone, `xd` D.2) **[consistency]**, two agreeing instruments (`xd` D.1–D.6). **6. Instruments** — `proto/` 14
Python + 5 SQL files (2 912 + 427 lines), `analysis/fuzz/` 20 scripts (1 990 lines) + 25 outputs, 5 recon and 5 analysis
docs. *Stated against the spike:* three raw blocks in `probes.json` have **no retained producer** (`f4` §4.11);
`run_all.sh` regenerates 21 of 25 outputs (`critic` §16c); `differ.py` and `bench.py` have **no negative controls**
(`critic` §7) — the instrument that produced every decision-relevant divergence has not itself been shown able to fail;
and, **the most FRAMING §8-relevant residual on the 130/130 headline itself [consistency]**, `conformance.py`'s **23
negative controls never drive the per-case loop**: NC11/12/13 call `matches()` directly on hand-written SQL, construct
no case entry and assert no `outcome`, leaving the outcome-assignment branches at `conformance.py:376-455` exercised by
**nothing** (`f1` §1.7, re-read here at `conformance.py:1010-1031`). FRAMING §8 asked for three outcomes visibly
distinct from two; 130/130 was scored by a harness in which *"compiled and diverges"* and *"did not compile"* have never
once been **emitted**, only inferred from unexercised code. **What would establish it:** inject a wrong compiler for one
fixture case through the real per-case loop and assert the emitted `outcome` string — one run, on an instrument FRAMING
§3 forbids this pass to edit.

### 5.10 What it cost to learn

**Corrected at closure, both endpoints re-derived by this seat. [consistency]** `sp-investigate` opened
**2026-08-19T16:50:18.060Z** — the `stage.advanced` event carrying T-1 from `sp-frame`, the one endpoint that is an
event (`.autodev/events.jsonl`, re-read here). The last body section to land is **this one**: `.parts/f5.md`,
mtime `2026-08-19 14:51:51 −0600` = **20:51:51Z** — a **file mtime, not an
event**, because no event marks a section landing. **That mtime is no longer readable off the filesystem, and the
endpoint is restated against the record that survives. [punch]** The closure and punch-list passes rewrote `.parts/`
in place — this file included — so `ls --full-time` now returns those passes' timestamps, not the landing ones; the
defect is **systemic across every `.parts/` mtime citation**, and the closure log records it as such (`f6`, "New
concerns the consistency read missed"), which is why §5.4 carries the same note. The surviving independent record was
taken **before** any rewrite, by the consistency read: `consistency.md` §5 states *"**f5 itself landed at
`20:51:51Z`**"* and derives the same **4 h 01 min** (`consistency.md` §2 is the matching record for the `xa`–`xd`
landing order §5.4 cites). Citations to `proto/` and `analysis/` mtimes are unaffected. **This endpoint therefore
rests on that record, not on a file property a reader can re-read today** — and it is the weaker of the two endpoints
for exactly that reason. The span is therefore **4 h 01 min**, not the 3 h 43 min an earlier
draft of this section gave: that figure ran to **20:33:32Z**, which is `xd-reachability.md`'s mtime and not in
`events.jsonl` at all, and it excluded f5 itself. Three `worker.started` events on T-1/`sp-investigate` fall inside the
span — **16:50:56.424Z · 17:28:51.208Z · 18:49:12.087Z**, all model `claude-opus-5[1m]`, the last of which was
`events.jsonl`'s final record at the time this section was written. (A fourth, **21:32:32.536Z**, opened the closure
and consistency pass that produced these repairs; it is outside the 4 h 01 min and is not counted in it. **[punch]**
The punch-list pass that produced the `[punch]` edits emitted **no** `worker.started` of its own — as read this pass,
`events.jsonl`'s last record of any kind is `ticket.created` at **21:37:26.830Z** — so the closure-side effort is
**under-**counted by the event record, not over-counted.) Output: **2.1 MB** under
`spikes/T-1/`, ~117 000 words of working documents and findings. **Token and currency cost is NOT ESTABLISHED** —
`.autodev/metrics.jsonl` holds one row (`stage.advanced`) with no cost fields; establishing it needs per-worker usage
logging the harness does not do. One cost is in no file: **the spike spent the contract fixture's standing as an
acceptance test.** It remains the right conformance contract for the two existing runtimes; §5.2 shows it cannot be the
acceptance test for a third — and the next seat will be tempted to reuse it, and it will pass.

### 5.11 Not established by this finding — and what would convert the verdict

**Two experiments would convert NO-GO into a decision on evidence rather than argument. E1 — the subset acceptance
battery** (§5.7): if it returns zero across the three silent classes *and* zero raise→value under a generator that reaches
the eight raise sites, `panel.json[0]`'s CONDITIONAL-GO becomes available on evidence. **E2 — the like-for-like
performance run** (§5.7 condition 4), which no seat performed: every end-to-end number in the record was measured on a
widget every proposed subset excludes. Both run on instruments that already exist; neither was run here, because FRAMING
§3 forbids new experiments in this pass — which is the correct, contract-compliant answer.

Standing gaps, named rather than rounded up: **whether a total *and* fast SQL runtime exists at all** — `f4` §4.9 labels
it OPINION and refuses to call the 36.2× prize collectable (*"B4 … bounds the size of the prize; it does not show the
prize is collectable"*), and everything economic rests on it; **fixture coverage of the corrected subset** — **no longer open [punch]:** measured at
closure at **68 of 130 (52.3%)**, §5.7, by an instrument built in that pass and independently re-derived there — a
*coverage* count, and not the identically-sized float8-exposure set named next; **whether the 130 still agree at `extra_float_digits` 0 or −3** — 68 of 130 exposed, `conformance.py:341`
hard-codes the value; **production usage and scale** — *n* = 1 dashboard, 3 widgets, 1 `noun`, largest real collection 17 148 rows and **under** the cap, no `DataSource` corpus in either tree (`f2` §2.9), so no fraction of traffic may be quoted
at the gate; **concurrency** — one connection throughout (`f4` §4.11), the axis on which the 2.4 GB-per-request memory win
would matter most; **`derive` chaining for n ≥ 2 and under shadowing** — uncompiled, unmeasured, unruled (`xb` B.9).

**Compliance.** Read-only throughout. Both GIMS trees, `FRAMING.md`, `recon/`, `proto/`, `analysis/`, `.autodev/` and
`kb/` were read and not written; the only file written is `spikes/T-1/.parts/f5.md`. No defect fixed, no grammar
redesigned, no new experiment designed. Re-checks used existing instruments, read-only: `proto/results.json` and
`analysis/measurements.json` re-derived with `python3`; `expr.evaluate` re-run in `GIMS-Project/.venv`; two witnesses
re-run through `analysis/fuzz/differ.py` (`SELECT` only, `autosql_spike`); `sources.py:61/:340-357` and `widgets.jsx:277`
re-read live. No Postgres object was created, altered or dropped.

**Compliance — the closure-consistency pass that produced the `[consistency]` edits above. [consistency]** Read-only
except for this file: `spikes/T-1/.parts/f5.md` is the only file written, and it is the only file this seat was
permitted to write. **No database was contacted at all** in this pass — no connection opened, no statement run, no
object created, altered or dropped; every performance and conformance figure below was re-derived from the **retained
JSON**, not re-measured. **No defect was fixed**, in `proto/`, in either GIMS tree, or anywhere else: FRAMING §3 forbids
it and the repairs are to the accuracy of this document only. Re-verified read-only for these edits:
`proto/idxshape_preds.json` (11 compiled outputs, `to_jsonb` in 10, `S1` bare — re-parsed with `python3`);
`analysis/measurements.json` (six `path_a`/`path_B2` medians; `sizes.20000.path_a` derive/filter; `sizes.1000000`);
`analysis/probes.json → recheck`; `analysis/fuzz/H_ordinary.txt`, `H_unicode.txt`, `H_extreme.txt`;
`proto/results.json → degenerate_baselines`; `proto/conformance.py:376-455` and `:1010-1031`;
`GIMS-Project/api/dashboard/sources.py:55-66` (the `MAX_SCAN` comment, read live); `.autodev/events.jsonl` and
`ls --full-time spikes/T-1/.parts/` for §5.10; and `.parts/f1.md`, `f3.md`, `f4.md`, `xb-…`, `xc-…`, `xd-…` as
cross-references. `.autodev/` was read and **not** written. **What this attestation does not cover:** the closure-pass
figures quoted from sibling sections (`f1` §1.6/§1.7/§1.9, `f3` §3.6, `f4` §4.4/§4.7, `xb` B.4/B.6, `xc` C.1/C.8/C.10,
`xd` D.2/D.4) were verified against those sections and, where the raw file exists, against the raw file — but the
measurements *behind* them were not re-run, and three `probes.json` blocks cannot be, having no retained producer
(§5.9).

**Compliance — the punch-list pass that produced the `[punch]` edits above. [punch]** Read-only except for this file:
`spikes/T-1/.parts/f5.md` is the only file written, and it is the only file this seat was permitted to write.
**No Postgres object was created, altered or dropped and no Postgres connection was opened at all.** Two live reads
were taken, both read-only and both attested here because the closure-pass attestation above does not cover them:
**(i)** a census of `GUTS/spine/L1-memory/gims-ledger/projects/guts-ledger/objects.db` over
`file:…?mode=ro&immutable=1` — the same instrument shape `xb` B.4 and `xd` D.1 used — `SELECT` only, no `ATTACH`, no
`PRAGMA` write, nothing in either GIMS tree opened for writing; and **(ii)** an import of the real parser
`core.dashboard.expr` from `GIMS-Project` with `sys.dont_write_bytecode = True`, so no `__pycache__` could be dropped
into that tree. Re-verified read-only for these edits: `analysis/subset-coverage.json` and
`proto/closure_subset_coverage.py` (read, **not** re-run by this seat — the 68/130 was re-derived instead by an
independent walker written here, in the session scratchpad outside the repository, and reproduced 84/130, 89/130 and
68/130); `GIMS-Project/tests/fixtures/expr_vectors.json` and `core/dashboard/expr.py` (md5 checked against the
measurement seat's published digests); the retained `xd_sweep.json`; `.autodev/events.jsonl` (read, **not** written);
and `.parts/xb-…` B.4, `f3.md` §3.3/§3.4, `proto/idxshape_hazard.sql` H2a–H2d, `f4.md` §4.7/§4.12,
`f6-closure-log.md` and `consistency.md` §2/§5 as cross-references. **No defect found by this spike was fixed** —
nothing in `proto/`, `analysis/`, either GIMS tree or any other part file was modified; FRAMING §3 forbids it and
these repairs are to the accuracy of this document only.

---

## Closure log — what the audit passes changed

**[punch] What this section is, and what its heading used to be.** It now records **two** repair
rounds. The first — the consistency-repair pass — is everything down to *Assembly*, kept as it was
written, with **[punch]** notes inserted only where a later measurement — or a re-read of the file a
row describes — showed something it said to be wrong.
The second is the **punch-list round**, appended at the end under its own heading. The heading above
read *"Closure log — what the consistency pass changed"* until the punch-list round; a link to the
old anchor `#closure-log--what-the-consistency-pass-changed` will not resolve.

The body above was drafted in parallel by nine seats, then read as one document by a tenth
(`.parts/consistency.md`), which found **24 defects in the drafted prose** and prescribed a repair for
each. Nine repair seats — one per section — then worked those items under a standing rule: **every repair
had to be re-verified against the raw artifact before it was written**, and where the artifact disagreed
with the consistency read, the repair was **refused and reported** rather than applied. This log is that
record. Each in-place edit is marked **[consistency]** at the point of change.

Nothing below fixes a defect *found by* the spike. `FRAMING.md` §3 forbids that, and the stop-rule audit
(`consistency.md` item 24) found no violation. This pass repaired the **document's accuracy** only.

### What was repaired

| item | section repaired | what changed | verified against |
| --- | --- | --- | --- |
| **1** | `f5` §5.3(b), §5.9(4) · `xc` C.3 (D17 row) | The bolded absolute *"No index containing compiled output can be created at all"* was **false** and is removed. Restated as **no compiled *predicate* (W1–W9) and no compiled *derive* column (D1)**, with the measured counter-fact in place: the compiled **sort key S1** carries no `to_jsonb` wrapper, is indexable, and was measured index-backed. `xc` C.3's D17 row carried the same false absolute in a parenthetical ("moot today — no such index can be created at all"), **not named by the consistency read**; the `xc` seat found and repaired it under the same adjudication, and D17's DDL-policy obligation is now **live, not moot**. | `proto/idxshape_preds.json` — re-derived here: **11 compiled outputs, `to_jsonb` in exactly 10**; `S1` = `nullif((data -> (%(p0)s)::text), 'null'::jsonb)`, zero wrappers. `f3` §3.6 H4: `Index Scan using idxprobe_score_operand`, **0.065 ms**. `xc` C.5's own H1 row was only obtainable because such an index *was* created |
| **2** | `xa` A.5 (heading + body) · `xc` C.13 (last bullet) | Three sections disagreed about whether *"the in-memory fallback can itself raise"* had been answered. `xa` deleted its own **"No section considers it."** — it is the section that answers it. `xc` C.13's *"no section of this spike adjudicates it"* became a forward pointer to `xa` A.5(ii), naming what genuinely **remains** open: the **production frequency of N1–N4**. `xc` C.3's D7 row and C.11(a)'s R1′ row already considered the retry raising and were left untouched. | `xa` A.5(ii)'s own measurements: poison row at index 0/5/9 → uncaught `OverflowError` in both `_apply_derive` and `_filter_rows` (`sources.py:147`, `:162`); HTTP 500 via `core/errors.py:113-119`; **40.9% (65/159)** of SQL raises also raise in the retry (`analysis/fuzz/G2b_round_raises.txt`) |
| **3** | `xb` B.10 | **Already applied before this pass.** B.10 no longer attributes a CONDITIONAL-GO to `f5`; `grep` finds no "CONDITIONAL-GO" anywhere in `xb`. The seat added only a traceability marker and an explicit *"(`f5` recommends NO-GO)"*. | `f5`'s opening verdict block, verbatim: "**Verdict: NO-GO** on the architecture as scoped"; `grep -c CONDITIONAL-GO` over `xb` = **0** |
| **4** | `f1` §1.11 item 6 and §1.9.5 · `xc` C.13 bullet 1 | Two sections declared reachability open and prescribed the exact sweep the next section performs. Both became forward pointers: **closed for this corpus by `xd` D.3–D.5; production-scale reachability remains open (`xd` D.8)**. `f1` §1.9.5 carried a **second, dependent** stale cross-reference not named by the consistency read; the `f1` seat repaired it too. `xc` added a scope limit the read did not state: **`xd`'s four predicates do not screen for offset-bearing or out-of-range date strings**, so the closure is real for the numeric and Unicode classes and **empty for the §5 clause-2 (raise → value) breach**. | `xd` D.3/D.4/D.5: **0 / 5,235,942**; **0 / 1,096,202** (string values **+ object keys**); **0 / 5,236,427**; plus the writer-signature test. `xd` D.8 for the production-scale limit |
| **5** | `f5` §5.10 and §5.4 | The elapsed-cost figure cited a timestamp not in the file it named and excluded `f5` itself. Corrected to **4 h 01 min** (`sp-investigate` opened `16:50:18.060Z`; `f5` landed `20:51:51Z`), with `20:33:32Z` identified as `xd-reachability.md`'s **file mtime**, not an event. The seat also repaired **§5.4's opening line** (not on the list): this pass rewrote `xa`–`xd` in place, so their landing mtimes no longer read as published; the landing order now cites `consistency.md` §2, which is the only surviving independent record. | `.autodev/events.jsonl` (`stage.advanced` at `16:50:18.060Z`); `ls --full-time spikes/T-1/.parts/`. See the refusal below — `events.jsonl` has since gained records and a **4th** `worker.started` |
| **6** | `f5` §5.7 (E1 "State to beat") | `H_unicode` was published as **4/3 863**, which is the AGREE count, not the ran count. Corrected to the ran count with the unit labelled and the arithmetic shown. The other two entries (3 881, 3 880) were **already correct** ran-counts and were not changed. `f1` §1.9.2 was already right and needed no edit. | `analysis/fuzz/H_unicode.txt`, re-read here: `AGREE 3863 · DIVERGE 4 · PARSE_ERROR 133` of `N=4000` → **ran = 3867** |
| **7 / adj. A** | `f4` §4.9(2), §4.11 · `f5` §5.3(a), §5.5(3) | Two headline ranges for one multiplier. The binding headline is **3.79×–7.15×**, from the six-size sweep medians. **2.55×** may appear only as a single load-controlled re-run at N = 20,000, with its provenance caveat **in the same sentence**, never as the headline. Both files now state it identically. | `analysis/measurements.json`, re-derived here: B2 ÷ A = **4.152 / 3.892 / 3.794 / 4.363 / 6.713 / 7.152**. `analysis/probes.json → recheck` at 20,000: A 492.63 ms, B2 1 257.03 ms = **2.552×** — the block `f4` §4.11 itself records as having **no retained producer** |
| **8** | `f5` §5.5(3) | The cheaper-alternative argument cited `sources.py:61`'s comment as anticipating "the change"; the comment anticipates **pushdown** — this project — so read correctly it is evidence **for** the ticket's premise. And the alternative's cost was stated only against the prototype, never against today. Both corrected in place. | `GIMS-Project/api/dashboard/sources.py:61` comment, read live: *"(Pushdown filtering removes this.)"*. `analysis/measurements.json`: Path A at 1 M = **8 331.43 ms**, so the one-line change is **≈2.0× slower than today's latency** and leaves the 98%-of-time acquisition and the 2.4 GB per-request heap untouched |
| **9** | `f5` §5.6, §5.9(6) | *"a harness proven able to fail"* overstated what the negative controls do, as `f1` §1.7 had already corrected in place. Corrected, and the residual added to `f5` §5.9's "stated against the spike" list, which had omitted it. | `proto/conformance.py:376-455` — the outcome-assignment branches are **exercised by nothing**; the 23/23 controls construct no case entry and assert no `outcome` |
| **10** | `f5` §5.6 | *"best single constant 20/130, **so** 75 of 130 agreements are unreachable by any constant"* switched denominators mid-sentence. The premise yields **110**; **75** comes from the union of all five constants (55/130). Derivation corrected; the conservative number is unchanged. | `proto/results.json` → `degenerate_baselines`, re-read here: `{true: 20, null: 19, false: 15, zero: 1, empty-string: 0}` → 130 − 20 = **110**; 130 − 55 = **75** |
| **11 / adj. D** | `f2` §2.4 · `f1` §1.9.3 | Two corrections `xa` A.6 ordered were never applied in place, and both sections come first in reading order. `f2` **deleted the inference** ("403 independent confirmations of the totality premise") and **kept the count**, with a forward footnote to `xa` A.6. `f1`'s understated "4 witnesses of 45 date probes" became **8 mechanisms across 9 source lines and 4 exception types**, also footnoted. | `xa` A.2 (the eight mechanisms) and A.3 — the 403-probe domain tops out at `\|value\|` 2026.0, nesting depth 4, `ndigits ∈ {−1, 2}`, zero `%`, zero offset-bearing dates, so it **cannot reach any of the eight raise sites**. `proto/coverage_probe_results.json` for the retained 403/403 count |
| **12** | `xb` B.4 | **Already applied before this pass** — the unit note distinguishing the table-wide count from `xd`'s `LedgerRecord`-only count was present, and already said "two units, not two measurements of one number". Its **arithmetic did not hold**, and the seat corrected that in place; see the refusal below. The published figure **17 342 → 17 345**, with the old figure left visible and the residual disclosed as unexplained. The numerator (**4 166**) and the rate (**24.0%**) are exact and unchanged. | `xd` D.2's collection census; a `mode=ro&immutable=1` re-count of `guts-ledger/instances` |
| **13** | `f5` §5.1, §5.2, §5.4 | Seat [1]'s value-vs-construct argument was left unrebutted while §5.7 instantiates a construct-keyed subset. `xc` C.1's DETECT/AVOID distinction — the one closure item that cuts **for** a CONDITIONAL-GO — was missing from §5.4's list and is now item (5) there, with its measured limits. §5.2's ruling now rests on the fixture-adequacy question. | `xc` C.1: **AVOID** is static and construct-keyed, decidable at `sources.py:345`; it satisfies FRAMING §5 but **not** §4's "detectable". `xc` C.10 for its cost (46/130 cases, 12/22 functions) |
| **14** | `f5` §5.5/§5.9 | `f3` §3.9's OPINION recommends shipping **rule 3** first; `f3` explicitly defers rule 3's economics to finding 4, and `f4` answers **no**. No section joined the two. A paragraph now records that `f4` removes rule 3's premise. | `f3` §3.9 (the emission rule); `f4` §4.4 and §4.9(2) (3.79×–7.15× slower) |
| **15 / adj. E** | `f5` §5.9(2), §5.4(4)/§5.6 · (`f5` §5.8(a), beyond the list) | Denominator drift: an **id** count added to a **class** count. Corrected to `xc` C.8's own units — **34 `expr`-layer ids → 15 detectable ids**; **19 undetectable ids = 18 classes**; **33 distinct classes** after folding D21. `f5` §5.3(c) was **already correct** ("18 of 33 distinct classes") and was not touched. Separately, **1 096 202** is labelled as `xd` D.4's *"string values **+ object keys**"*; the string-values-only figure is **495 115**. The seat found and repaired the **same slip in §5.8(a)** ("6 of 34 register ids" next to "18 classes"), which the consistency read did not name. **[punch]** *"`xc` C.8's own units" was true of C.8's **body table** and not of C.8's **bolded headline**, which at the time read "15 detectable, 18 undetectable" — itself an id count added to a class count, summing to 33 while naming the 34-id register. `consistency.md` item 15 had compared the body figures, ruled "**xc is right**" and prescribed no `xc` edit, so the headline went uninspected through this pass; it was repaired in the punch-list round (below). What `f5` was corrected to were C.8's **body** figures, which were and are correct.* | `xc` C.8 (the register counts); `xd` D.2 and D.4 (the two string denominators) |
| **17** | `f1` §1.1 | Three non-regenerable captures were named where the section's own table (25 outputs, 21 runs) requires **four**. The fourth is `H_parse_errors.txt`, which `f1` §1.10 identifies separately as a superseded capture. | The four `.txt` in `analysis/fuzz/` with no corresponding `.py`; `proto/run_all.sh` = 21 `run` lines |
| **18** | `xb` B.8 | *"Ten substantive obligations. Zero compiled, zero tested, zero fallback-ruled"* read against B.8's own rows 1 and 6, which record hand-written SQL in `bench.py`. Restated as **zero emitted by `proto/compile.py`, zero tested, zero fallback-ruled** across all ten obligations, with the exception named: the only SQL anywhere for `filters` or `sort` is hand-written for one widget, and B.3 measures that clause **dropping 2 of 3 rows**. | `proto/compile.py` (emits none of the ten); `proto/bench.py:94-101` and `:226` (the hand-written clauses) |
| **19** | `f5` §5.4(3), §5.9(3) | The flat claim that migrating the store "changes the answer on 4 166 real rows" dropped `xb`'s own scope note. Carried across in place: the answer changes only **for a query that resolves a `runid`-normalising key**, and `xb` labels the production relevance an **INFERENCE** — *whether a production `DataSource` targets a collection holding the colliding pair is not established*. | `xb` B.4's scope note and its INFERENCE label; `f2` §2.9 (the `DataSource` corpus is absent) |
| **20** | `f0` (this header) | **Already applied before this pass**, at 15:07 — the map carries the four cross-cutting sections §A–§D, and the `recon/semantics.md` §11 correction. **Verified at assembly:** all nine map rows match the actual `##` headings in the actual body files, in assembly order, with the right titles. The assembly seat made two further header repairs, marked **[consistency]**: the provenance row *"Nothing was written to either"* (see "new concerns" below), and a pointer to this log. A **Contents** table was added after "How to read this document". | The nine part files' first lines, compared against the map row-by-row; `git status --porcelain` in both GIMS trees |
| **21** | `f3` §3 summary line | The summary led with *"3 of 130 fixture cases (2.3%)"* while §3.5(c) and §3.9 already carried the operative figure. **[punch] Corrected description of the result, read off `f3` as it now stands, because this row did not match it.** The summary paragraph *leads* with "No — and the index is not the reason"; the routable figure sits at the **end** of it and reads **2 of 130 fixture cases (1.5%), one distinct expression shape** (§3.5(c), §3.9 rule 1) — a shape cannot be routed if one of its records is silently wrong. **3 of 130 (2.3%) was not removed**: it is retained in the sentence that follows, labelled *"its per-case upper bound"*, with the third case named (case 34, shape `$.x == null`, the shape that silently diverges at case 33). The form **1 of 113 distinct expressions (0.9%)** is carried by **§3.5(c)**, not by the summary line; the drafted version of this row attributed it to the summary. §3.5's ladder and §3.9 rule 1 were **already correct** and were not touched. | `f3` §3.5(c)'s existing reconciliation; `proto/idxshape_preds.json`, `proto/idxshape_plans.json` |
| **22** | `f4` §4.2, §4.7, §4.11 · `xd` D.7 | The measurement corpus's missing-key rate is **5%**; the one real collection's is **42.9%** — an **8.6×** difference nobody had applied to `f4`'s selectivity, derive-cost or recall figures. Now paired where the 5% lives, with the effect on each, and a reciprocal pointer added in `xd` D.7. The **net direction is returned as *not established***, because the two legs push opposite ways (see "new concerns"). `f4` §4.7 additionally now states that the recall cliff is a property of the **synthetic sweep only** — no collection on this machine is over `MAX_SCAN`. | `proto/gen_data.py:30` (the 5% generator rate); `xd` D.7 (42.9%, **n = 7**); `xd` D.8 (largest real collection 17 148 rows = 85.7% of `MAX_SCAN`) |
| **23 / adj. G** | `f1`, `f3`, `f4`, `xa`, `xc` (added) · `f2`, `xb`, `xd`, `f5` (confirmed / extended) | Compliance attestations were present in four sections and absent from five. Each of the five now carries one, attesting **only to what its artifacts support**. `f2`, `xb`, `xd` and `f5` already had one and were **not given a second**; `xb` extended its existing block to cover the Postgres probes it had been silent on, and `xd` **corrected** its existing block (see "new concerns"). | Each section's own run record; `xd_sweep.py`'s `mode=ro&immutable=1` connection strings; `analysis/index-shape.md` §12.4 (verified end-state: 200,000 rows, `idxprobe_pkey` only) |
| **24** | `xd` D.1 header and §D.10 | The label *"a read-only sweep, not a new experiment"* overstated the case: `xd_sweep.py` is a **new read-only instrument, built this pass, cross-checked against `json_tree`**. Relabelled in both places. No defect is fixed anywhere in the spike; the stop-rule audit's "no violation found" conclusion stands, with the two grey areas disclosed. | `xd_sweep.py` (session scratchpad, outside the repository); `xd` D.1's `json_tree` aggregate cross-check |

**Item 16 is not a repair** — it is the consistency read's list of roughly forty figures it re-derived from
`results.json`, `measurements.json`, `idxshape_preds.json`, the fuzz captures and the GIMS tree that **came
back exact**. It is recorded here so the repairs above are not read as a general indictment of the body's
citation discipline.

### What was refused, and why

Every seat was required to verify a repair against the raw artifact **before** writing it, and to refuse
where the artifact disagreed. **Five refusals stand, across four seats — `xb`, `f1`, `f3` and `f5` (twice).
Three of the five refused a prescribed repair outright and the seat wrote its own corrected version instead
(items 12, 11, 23); in the other two — items 1 and 5, both `f5` — the prescribed repair *was* applied and
what the seat refused was a supporting claim: a characterisation in one, an evidentiary premise in the
other. [punch]** *Reconciliation, because the three places this document counted refusals did not agree.
This line read "Four refusals stand", which is the **seat** count; `f0`'s audit paragraph read "three",
which is the count of **prescribed repairs refused outright**; the table below has **five rows**, one per
refusal. Each number was true of something and none described the table. All three now state the same
thing: **5 refusals · 4 seats · 3 of them prescribed repairs.** Counted off the five rows below, row by
row.* `consistency.md` is authoritative about what is wrong; it is not infallible about the fix.

| item | who refused | what was refused | the raw evidence |
| --- | --- | --- | --- |
| **12** | `xb` | The prescribed reconciliation **"17,148 + 197 + 5 = 17,350, minus six minutes of writer drift"**. The `+ 5` is wrong: the `guts-ledger` store holds **no `Repo` collection at all** — `xd` D.2's two `Repo` collections are in `guts` and `guts-code`, where `xb`'s own sums already consume them. Applying it would have invented a fifth collection. The "writer drift" clause is also unavailable as an explanation: `immutable=1` reads the main db file only, and that file's mtime (**14:16**) predates both reads, so an `immutable=1` count **cannot drift**. The corrected identity **17,148 + 197 = 17,345** was applied instead, and the 3-row residual against the published 17 342 recorded as **unexplained** rather than explained away. **[punch]** *The refusal itself stands: the `+ 5` invents a fifth collection, `xb`'s own per-store sums already consume both `Repo` collections, and **17 345** is still the applied figure. Its **secondary** clause has been superseded — an `immutable=1` count does not drift continuously with the writer, but it does move **when a checkpoint lands**, so the main-file mtime cited here (**14:16**) is not evidence that the count could not have moved; `xb` B.4 now identifies a checkpoint at **14:16:56** as the single event that moved it. The residual is therefore **no longer unexplained** — see the correction under "New concerns" below.* | `xd` D.2's collection census (`Repo` ×2, both outside `guts-ledger`); `xb`'s own per-store sums (guts 12,095 ✓, guts-code 6,710 ✓); the store's main-file mtime |
| **11 / adj. D** | `f1` | The sub-clause *"Of 11 re-verified witnesses, 4 are raise→value, 3 raise→null, 3 both-raise"*, copied verbatim. **4 + 3 + 3 = 10, not 11.** Rather than reproduce arithmetic that does not reconcile, `f1` wrote what is exactly countable from `xa`'s own table — **10 tabulated direction rows** (4 raise → value: R1×2, R2, R8; 3 raise → null: R4 @ `DBL_MAX`, R6, R7; 3 both-raise: R3, R4 @ 1.7e296, R5) — and noted that `xa` counts 11 because its R6 row carries **two** witnesses (`floor("1e400")` *and* `ceil("-1e400")`). The headline figure the adjudication actually turns on — **8 mechanisms, 9 source lines, 4 exception types** — was verified independently and applied verbatim. | `xa` A.5(i)'s direction table (10 data rows); `xa` A.2's R6 row (two witnesses folded into one line) |
| **23 / adj. G** | `f3` | The prescribed attestation wording *"f3's DDL probes all ran in rolled-back transactions with post-rollback verification"*. True of the **closure** pass; **false as a blanket statement**. The four committed investigation-pass SQL scripts contain **no `BEGIN` and no `ROLLBACK`** — indexes are created and dropped in autocommit, one script leaves its indexes for the next to drop, and the H5 probe `INSERT`s a row and `DELETE`s it. This is **not** a stop-rule violation (it is all inside the spike's own scratch database, which `FRAMING.md` §7 provisions), but attesting "all rolled back" would be an untrue attestation. `f3` wrote the **split** version instead. | The four committed `proto/*.sql` scripts (`grep` for `BEGIN`/`ROLLBACK`: none); `idxshape_exprindex.sql` → `idxshape_jsonpath.sql:2-4`; `idxshape_hazard.sql:40`/`:49`; `analysis/index-shape.md` §12.4's verified end-state |
| **1** | `f5` | Not the repair — the **characterisation**. The dispatch described `f5` §5.9(4) (*"no compiled predicate can appear in any index today"*) as a defect to be fixed "so the two agree". Under adjudication F that sentence was **already true as far as it went**, and `consistency.md` item 1 itself quotes it approvingly as "the correct form 230 lines later". Rewriting it as though it had been false would have introduced an error where none existed. `f5` **extended** it with the derive column and the measured S1 counter-fact instead, so §5.3(b) and §5.9(4) now say the same thing at the same strength. | `consistency.md` item 1's own text; `proto/idxshape_preds.json` |
| **5** | `f5` | One **evidentiary premise** of the repair, not the repair. `consistency.md` states that `events.jsonl`'s *"last event of any kind is `18:49:12.087Z`"*. That was true when it was written; **it is not true now**. `f5` time-scoped the statement rather than publish a claim about the file that no longer holds. The prescribed repair is unaffected — **4 h 01 min stands**, because the later worker opened this closure pass, after `f5` landed. | `.autodev/events.jsonl`, re-read at assembly: last record **`21:37:26.830Z`**; a **4th** `worker.started` on `T-1/sp-investigate` at **`21:32:32.536Z`** |

### New concerns the consistency read missed

Each was found by a repair seat while verifying. **Where a seat did not own the file, it reported rather
than edited** — hard rule 1 of this pass. Nothing here is fixed; several are recorded as known rather than
latent errors.

**Repaired in place by the seat that found it** (each marked **[consistency]** in the body):

- **`xc` C.3's D17 row carried the same false indexability absolute as item 1**, in a parenthetical, and it
  contradicted `xc`'s own C.5 H1 measurement — which was only obtainable *because* such an index was
  created. Repaired; D17's DDL-policy obligation is **live**, not moot.
- **`f5` §5.8(a) mixed an id count with a class count** — *"6 of 34 register ids"* next to *"the 18
  undetectable classes"*, unlabelled, inviting the exact subtraction adjudication E forbids. Both figures
  are correct against `xc` C.8; the units were not.
- **`f1` §1.9.5 carried a second stale reachability cross-reference** pointing at the very line item 4
  orders repaired. Left alone it would have recreated the defect. This means the consistency read's own
  sweep for stale *"not established"* lines **was not exhaustive**.
- **`f5` §5.4's opening line cited `.parts/` mtimes as evidence**, which this pass invalidated by rewriting
  those files in place. The mtime-provenance defect is **systemic**: `ls --full-time` now contradicts every
  such citation, and the only surviving independent record of the original landing order is
  `consistency.md` §2. Citations to `proto/` and `analysis/` mtimes are unaffected.
- **`f0`'s provenance row said *"Nothing was written to either [GIMS tree]"***, which a read-only seat
  cannot observe. `xd` D.11 records a **concurrent non-spike writer** — AutoDev's own ingestion verb —
  creating `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` **inside** the spike window and moving
  `LedgerRecord` 17,145 → 17,148 during the sweep. The row is now scoped to what is attestable: no file in
  either tree was opened for writing **by this spike**, and both HEADs are the `FRAMING.md` §7 values.
- **`xd` D.11's attestation was falsified by the tree it attests about** — flagged independently by `f1`
  and `f4`, corrected by `xd` itself. The drafted *"8 pre-existing modified files, all mtime 2026-08-13"*
  is wrong in two particulars: the counts differ per tree (**8** in `GIMS-Project`, **9** in
  `gims-ledger`), and three entries are not 2026-08-13. What is attestable stands unchanged.

**Reported, not fixed — the seat did not own the file:**

- **`xa` A.5(i)/A.6's 10-vs-11 witness count.** *"4 of 11 witnesses"* against a 4/3/3 split summing to 10.
  It reconciles — one row packs two witnesses — but nothing in `xa` says so, and the section mixes a **row**
  count with a **witness** count in the same sentences. `xa` deliberately did **not** unilaterally fix it,
  because `f1` was being repaired in parallel and a one-sided change would have manufactured the very
  cross-file divergence this pass exists to remove. Not decision-blocking: the **4** raise → value
  witnesses — the §5-breaching number — is correct under both readings.
- **`xc` C.8's last row states "9 in Blocks A–C" as an id count that includes D21**, which the same section
  folds into D1–D5. As distinct **classes** it is 8. It is not currently added to a class count anywhere,
  so it does not breach adjudication E as written — but it is one quotation away from reproducing item 15's
  slip. **[punch] The second sentence's reassurance was too broad, and is corrected here.** At the time it
  was written the id/class mix *was* live, in this very section: `xc` C.8's own bolded headline read
  *"15 detectable, 18 undetectable"* — an id count added to a class count, summing to 33 against the 34-id
  register it names — and C.11(b) paired *"18 are invisible"* with the **34-id** denominator. Both were
  repaired in the punch-list round (below). What survives unchanged is the **narrow** claim about this row:
  the "9 in Blocks A–C" is still not summed into a class count anywhere, re-checked across the parts this
  round, and the row itself was not edited.
- **`f2` §2.4/§2.5 cite probe witnesses as `cases[344]`, `cases[226,227]`** — but
  `proto/coverage_probe_results.json` has **no `cases` key**; its top level is a bare list. The integer
  indices are all correct (9 of them re-verified), so no evidence is wrong; the wrapper name is fiction.
- **`f2` §2.4's surviving word "adversarial"** for the 403 probes is false for the magnitude/boundary axis
  (`xa` A.3: max `|value|` 9.0 in records, nesting depth 4, no `%`, no offset-bearing dates). Reduced to
  "403 inputs" in the one sentence the seat was authorised to rewrite; it survives elsewhere.
- **A live GIMS application was writing to `gims-ledger` *during* `f4`'s measurement sweep.**
  `projects/guts/verbs/ingestion/data_dumps/` holds `decompose-*` output directories with 2026-08-19
  mtimes at 11:22, 12:20, 12:25, 12:38, 12:58, 14:04, 14:10, 14:16 and 14:32; the sweep ran 11:57 → 12:27.
  `f4` §4.6 says "the sweep's own load was never recorded"; the truthful statement is stronger — **the host
  was demonstrably not quiet, and a named concurrent writer existed**. Recorded in `f4`'s new compliance
  block as an INFERENCE. It enlarges the declared error term on **absolute levels**; it leaves **ratios and
  counts** — which is what §4.7 and §4.9(2) are — alone.
- **Item 22's implied direction is the opposite of what the evidence supports on net.** On the one real
  collection the four rows that *do* carry `due_date` are all in the past, so the widget's `< 7` predicate
  would hold on 4/4 against the generator's ~9%. Real selectivity plausibly runs an order of magnitude
  **above** the synthetic 5.2%, not below. `f4` states both legs and returns *not established* on the net.
- **`xd` D.2's corpus table has two errors that nearly cancel** — the `verb_log` group omits
  `LIMS-System_verb_log` (27 rows, which *was* swept) and the table lists 28 `noun_Sample` rows that were
  **not** swept (that table is column-per-field, so `xd_sweep.py` skipped it). The arithmetic closes only
  the corrected way: 36,369 + 709 = **37,078** exactly. The published total is right.
- **`xd` D.6.3/D.7 print `Submission.received_date` as `'60824' (×5)`.** The count of numeric-looking
  strings is right (5 of 7); the literal is not uniform (`'60824'` ×4, `'60822'` ×1). Nothing rests on it.
- **`f3` §3.5(d)(i)'s J5 re-run and §3.7 item 6's re-derivations are prose-transcribed with no
  machine-readable capture** — already disclosed in `f3` §3.8 items 4, 5 and 9. Finding 3's
  machine-checkable spine is exactly two files: `proto/idxshape_preds.json` and `proto/idxshape_plans.json`.
- **`xa` A.5(ii)'s poison-row probe has no retained producer.** It is described and tabulated but no script
  survives; it is trivially re-derivable and independently corroborated by `xc` C.3's G2b numbers, which
  *are* backed by a committed capture. This is the same provenance weakness item 7 penalises in
  `probes.json`'s `recheck` block, and it sits on a §5 non-negotiable. Recorded in `xa`'s attestation.
- **`xb` B.4's published 17 342 does not reproduce under any reading of the instrument `xb` names**, and
  the writer-drift explanation is unavailable (see the refusal). Either the original census miscounted by
  3, or it did not use the named instrument. Disclosed rather than papered over. **[punch] Withdrawn — it
  does reproduce, and neither disjunct holds.** 17 342 is this same table read **one checkpoint earlier**.
  `immutable=1` ignores the live `-wal` and reads the main db file only; it does not follow that the count
  is fixed — it moves **when a checkpoint lands** rather than continuously with the writer, and one did.
  Verified here against the spike's own retained sweep output `xd_sweep.json` (session scratchpad, written
  14:16:57, same `mode=ro&immutable=1` instrument): `guts-ledger`/`instances` holds `LedgerRecord` **17 145**
  + `WorkOrder` **197** = **17 342**, the published figure exactly, and `guts` / `guts-code` sum to 12 095 /
  6 710 there as `xb`'s table prints them. The checkpoint (main-file mtime **14:16:56**) moved the table to
  `LedgerRecord` **17 148** + `WorkOrder` **197** = **17 345** — the same single event behind `xd` D.1's
  17 145 at 14:14 → 17 148 at 14:20. `xb` B.4 now carries this reconciliation and withdraws its own
  *"a writer cannot move an `immutable=1` count"* and *"superseded and unexplained"* as over-claims. **The
  refusal recorded above is untouched:** the prescribed `+ 5` was still wrong for the reason given, and
  **17 345** is still the figure — what changes is that the 3-row residual is now explained rather than
  unexplained, and that the figure is a snapshot pinned to a checkpoint, not a standing property of the
  store.
- **`xb`'s one-off `::jsonb` probes in B.4–B.6 were scratchpad-only and are not retained** — unlike `f3`'s
  DDL there is no artifact a reader can open to check them. Same grey-area class as item 24's two.
- **`xb` B.1's grep-derived counts are measured over `f1.md`–`f5.md` only**, and those files were rewritten
  by this pass — the `xb` seat flagged that they could go stale, and ***checked at assembly, two of the four
  have.*** `_pass_filters` (0 in all five) and `_field_value` (0/0/0/1/0) still hold. `find_actual_key`,
  published as **0 in all five**, now returns **2 hits in `f5`** — introduced by item 19's repair, which
  carries `xb`'s own scope note and names the helper. `_sort_key`, published as **0/0/3/3/1**, is now
  **0/0/4/3/2**. B.1's *argument* is unaffected — the identifiers remain absent from findings 1 and 2, and
  `f5`'s new hits exist only because a repair quoted `xb` — but the published counts no longer reproduce.
  Not repaired: `xb` is read-only to the assembly seat.
- **`f3` §3.6 H4 cites `sources.py:99-115` for `_sort_key`; `analysis/index-shape.md` §7.4 cites
  `:99-119`.** `f3` is **right** — `def _sort_key` opens at 99 and its last statement is line 115 — and
  `f3` §3.7 item 5 already records this as a drift fix. Noted so nobody "corrects" `f3` back to the wrong
  number.
- **`xb` B.8 row 6's "ranks 0/1/2/4" is shorthand.** The rank *expression* does emit a rank-3 value
  (`bench.py:94-96`, `ELSE 3`); what is not compiled is rank 3's sort **key**, so all container values tie.
- **The word-count figure in `f5` §5.10 is unresolvable and was left alone.** `f5` says ~117 000 words;
  `consistency.md` §16 says it checked ~119 k. Neither is checkable after the fact — the `.parts/`
  directory has since gained `critic.md`, `consistency.md` and this pass's additions. Per the pass's own
  rule against inventing numbers, no figure was substituted.
- **`f5`'s "stated against the spike" list is now longer than its headline comfortably carries.** Item 9's
  residual — `conformance.py`'s outcome-assignment branches exercised by nothing — is qualitatively
  different from the other three disclosures: it touches **the instrument that produced the 130/130
  headline itself**, and `FRAMING.md` §8 named this exact failure mode in advance. The `f5` seat stated it
  plainly in place rather than softening it, and recorded that whether "130/130, answered yes and audited"
  should still lead §5.9 is a judgement **above the repair seat's authority**.
- **`xd` D.3–D.5 does not bound D11's reachability.** `xd`'s four predicates screen for magnitude,
  non-ASCII digits, non-ASCII whitespace and significant digits — **none** screens for offset-bearing or
  out-of-`datetime`-range date strings, which is the shape carrying D11 and `xa`'s R1/R2 raise → value
  witnesses. Stated in place in `xc` C.13; it means adjudication C's closure is **empty for the FRAMING §5
  clause-2 breach**.
- **`f1` §1.9.2's "40 of 45 agree" is, strictly, 39 measured agreements plus one mislabelled control** —
  `E_dates.py:42` is captioned "NBSP U+00A0 padding" but holds a plain space. `f1` §1.10 already discloses
  the mislabel in place; the 4 `PY_RAISE` are unaffected and were re-verified.
- **`xd` D.7's cross-reference makes one clause in `f4` stale** — `f4` now says "`xd` D.7 compares itself
  only to `f3`'s 8% generator", which stopped being true when `xd` added the reciprocal pointer. Cosmetic.

### What the repairs did to the argument

The verdict was **not** the repair seats' to move, and none moved it: `f5` still recommends **NO-GO**.
Several repairs **weaken** individual legs of it, and each seat was required to say so **in place**, in a
labelled sentence, rather than let the recommendation absorb the change. This table is a finding-aid to
those in-place statements, not a substitute for reading them.

| leg | direction | where it is stated in place |
| --- | --- | --- |
| Gap 13 leg (b) — indexability | **narrowed.** "No index containing compiled output can be created at all" was false. Restated as no compiled *predicate* and no compiled *derive* column, with S1 measured index-backed at 0.065 ms. The coupling the leg exists to establish **survives** — the index that would fix leg (a) is a *predicate* index, still refused — but at its true strength | `f5` §5.3(b), §5.9(4); `f3` §3 opening (which never over-claimed) |
| `f5` §5.5 reason 3 — the cheaper alternative | **weakened, the largest single movement in this pass.** Both halves were overstated: `sources.py:61`'s comment anticipates *pushdown*, so read correctly it is evidence **for** the ticket's premise; and the alternative is **≈2.0× slower than today's latency** while leaving the 98%-of-time acquisition and the 2.4 GB heap in place. Reason 3 now claims only that the alternative is cheaper **to build** | `f5` §5.5(3) and the marked paragraph at the end of §5.5 |
| the performance leg | **firmer.** Demoting the un-audited `recheck` block raises the floor from 2.55× to **3.79×** — worse for the compiled arm | `f4` §4.9(2); `f5` §5.3(a), §5.5(3) |
| the fixture-adequacy leg | **firmer.** 130/130 was scored by a harness whose "compiled and diverges" and "did not compile" branches have **never been emitted, only inferred** | `f5` §5.2, §5.9(6); `f1` §1.7 |
| the FRAMING §5 *null → value* breach | **weakened.** Reachability is no longer "not established"; it is **measured at zero** for these corpora (0/5,235,942; 0/1,096,202; 0/5,236,427). It becomes an argument about **exposure**, not observed harm | `f1` §1.9.3 bottom line, §1.11 item 6; `xc` C.13 bullet 1 |
| the FRAMING §5 *raise → value* breach | **unchanged, and larger than `f1` had stated** — 8 mechanisms across 9 source lines and 4 exception types, firing on the **expression text a tenant writes**, with no unusual stored data. Untouched by the reachability sweep | `f1` §1.9.3; `xa` A.2, A.5(i) |
| the fallback-is-not-a-harbour leg | **firmer.** An unadjudicated worry became a measured failure: uncaught `OverflowError` at any poison-row position, and 40.9% of SQL raises also raise in the retry | `xa` A.5(ii); `xc` C.13; `f5` §5.4(2) |
| the `MAX_SCAN`-urgency leg | **weakened.** The 88%/38%/4% recall collapse is real but is a property of the **synthetic sweep**; no collection on this machine is over the cap. "The cap silently changes the answer once crossed" survives; the implied "and it is being crossed" does not | `f4` §4.7(iii) |
| the totality premise | **the pro-GO datum is retracted**, not replaced. `f2` §2.4's "403 independent confirmations" is deleted and the count kept. `f2`'s two null-mismatch rows (**0** value → null, **0** null → value) are untouched | `f2` §2.4 and its new footnote |
| seat [1]'s value-vs-construct argument | **narrowed.** `xc` C.1 shows it forecloses a *detecting* subset, not a construct-keyed one — and `f5` §5.7 instantiates a construct-keyed subset. §5.2's ruling now rests on fixture adequacy, which is where the evidence is | `f5` §5.1, §5.2, §5.4(5) |
| `f3`'s no-per-key-DDL route | **narrowed at the headline** — 3/130 (2.3%) → **2/130 (1.5%)**, one distinct expression, matching what §3.5(c) already said | `f3` §3 summary line, §3.5(c) |
| `xb`'s 4 166-row claim | **unchanged, arithmetic tightened.** Denominator 17 342 → **17 345**; numerator and rate exact and unchanged. `xb` and `xd` now reconcile with zero residual | `xb` B.4; `f5` §5.4(3) |

`f5`'s own summary of where this leaves a reader who wants to rule the other way, stated in §5.5 so the
gate does not have to find it: **attack reason 3 and leg (b) first, because those are the two the evidence
now supports least.** `human:owner` decides at the `sp_decide` gate.

### Assembly

`FINDINGS.md` is the concatenation of the ten part files in the order `f0 · f1 · f2 · f3 · f4 · xa · xb ·
xc · xd · f5`, copied **byte-for-byte** (verified: each part's bytes occur in the assembled file, in order,
without overlap). The only content the assembly seat wrote is the two header repairs marked
**[consistency]** in §0, the Contents table, and this section. No body part was edited at assembly; the
defects found in body parts at assembly time are reported above, not repaired. Heading structure was
checked, not changed: **one h1** (the title), **ten h2 sections** plus the header's own, all subsections
below them. All artifact links resolve from `spikes/T-1/` — verified by opening all sixteen targets. No
part links to another part file by filename.

**One caveat a reader should have.** The parts cite each other in prose as "`f1` §1.4", "`xa` A.5(ii)",
"`xc` C.8" — that idiom survives concatenation and was left alone. But a handful of citations in `xd` and
`f5` use the **file:line** form (`f1.md:693-701`, `f3.md:611`) against the *part* files, whose line numbers
do not correspond to `FINDINGS.md`'s. Those were **not** rewritten: converting a line range to a section
reference is a judgement, not a mechanical fix, and this pass's rule was to report rather than guess. The
`.parts/` directory is kept beside this file, so they still resolve.

### Punch-list round

The assembled `FINDINGS.md` — 4,926 lines, written at **16:00:42** — was then read by **three adversarial
lenses**. All three returned the same bottom line: the evidence is sound, `f5`'s **NO-GO** still follows, and
**nothing they found is decision-blocking**. Their findings — **21 items, all dispatched as "credibility" or
"minor"** — were turned into a punch list and worked under the same standing rule as the repair pass:
**verify against the raw artifact before writing, and where the artifact disagrees, refuse and report.** Each
in-place edit from this round is marked **[punch]**, so it stays distinguishable from **[consistency]**.

**A weakness in this record, stated before the record.** The three lens reads are **not retained as files.**
`.parts/` keeps `verifications.json`, `critic.md`, `panel.json`, `consistency.md` and `closure-reports.md`
from the earlier passes, but there is no lens artifact — so *"21 items, none decision-blocking"* is the
dispatch's count, not one a reader can re-derive. The same holds one level down: **no repair seat's report is
retained, in either round.** This log is their only record, and it is written from reports that reached the
bookkeeping seat, not from files on disk. Where a report did not reach this seat, the row below says so and
the entry is read off the seat's own in-place text instead.

#### What was repaired

| seat / file | what changed | verified against |
| --- | --- | --- |
| **`xc`** `xc-fallback-register.md` §C.8 headline, §C.11(b) | The register's bolded headline mixed units: *"15 detectable, 18 undetectable"* adds an **id** count to a **class** count, sums to **33**, and names a **34-id** register. Restated in one unit at a time and closed in both — **15 detectable ids + 19 undetectable ids = 34**; folding D21 into D1–D5, **15 + 18 = 33 classes** — with the fractions given rather than the word "half": **19 of 34 ids (55.9%)**, **18 of 33 classes (54.5%)**. §C.11(b)'s *"34 ids, of which 18 are invisible"* now holds the class unit throughout. **No register figure changed**; both fractions are above half, so the section's force is unchanged | Read in place, and the counts taken off C.8's own two id lists rather than off the prose: **15** detectable ids (C1–C4 · D6, D7, D9, D14, D19, R1 · D20 · S1–S3 · R6) and **19** undetectable (D1–D5, D8, D10–D13, D15–D18, D21–D23, R2, R5) — 15 + 19 = 34 ✓, 18 once D21 folds, 19/34 = 55.9%, 18/33 = 54.5%. The Block A/B/C re-extraction behind them is that seat's. `consistency.md` item 15 had already ruled the underlying figures right ("**xc is right**") — the defect was the headline only |
| **`xa`** `xa-totality.md` — nine marked edits: the section preamble, §A.2's R4 row, §A.3 (×2), §A.5(i), §A.6 (×3), and a punch-pass addendum | The f2 sentence `xa` argues against — *"403 independent confirmations of the totality premise"* — **no longer stands in f2**, which deleted the inference and kept the count during the repair pass. The quotation is now introduced as f2 *"as first drafted"*, with a reading note saying so; §A.3's *"is therefore"* became *"was therefore… which is why §A.6 ordered the inference deleted, and why f2 has since deleted it"*; the verdict paragraph's *"is wrong"* became *"was wrong — and f2 has since withdrawn it"*. §A.6 gained a **"two applied, two recorded"** status block: the corrections ordered onto `f1` and `f2` are applied and were re-read to confirm it, while `recon/semantics.md` §11 and `FRAMING.md` §5 are read-only to this pass and are **recorded, not applied**. §A.6's `f1` row dropped the drafted 4+3+3-of-11 sub-clause for the countable form — **10 direction rows carrying 11 witnesses** (the `floor`/`ceil` row holds two), **4** raise→value either way | Read in place. `f2` §2.4 confirmed to carry the deletion, the retained count and the forward footnote; `f1` §1.9.3 confirmed to still carry its quoted clause and the widened "8 mechanisms across 9 source lines and 4 exception types"; `FRAMING.md` §5 confirmed unchanged. The seat's report reached this log truncated before its refusals section — see below |
| **`xb`** `xb-filters-sort.md` §B.4 | The 3-row residual this log recorded as **unexplained** is now explained, and two of `xb`'s own claims are withdrawn as over-claims (*"a writer cannot move an `immutable=1` count"*, *"superseded and unexplained"*). 17 342 is the same table **one checkpoint earlier**; a checkpoint moves the main-file count, a writer does not. B.4 also now states plainly that 17 345 is a **snapshot pinned to the 14:16:56 checkpoint**, not a standing property: a read-only re-census at 16:21:55 returns **17 398**. **The numerator does not move** — 4 166 at every read taken, pair `run_id`/`_runID` in all of them | Re-verified here against `xd_sweep.json` (session scratchpad, written **14:16:57**, `mode=ro&immutable=1`): `guts-ledger`/`instances` = `LedgerRecord` **17 145** + `WorkOrder` **197** = **17 342** exactly, with `guts` 12 095 and `guts-code` 6 710 as B.4 prints them. No report from this seat reached this log; the entry is read off B.4's own `[punch]` paragraphs |
| **`xd`** `xd-reachability.md` — fourteen marked edits in §D.2, §D.4, §D.9 and seven cross-references | **Citations and reconciliations only, by the seat's own attestation, and no published measurement changed.** Seven `.parts/f1.md:NNN` / `f3.md:NNN` line references — which resolve only inside the working directory and which the rewritten files had made stale — became section references; `f3` §7.3 (an `analysis/index-shape.md` number) became `f3` §3.6; §D.2's census table gained the reconciliation to the swept **37,078**; §D.4 gained the exact **491,813 + 3,302 = 495,115** tie; §D.9's D8/D10 row gained the *"string values + object keys"* label the row it summarises already carried | Read in place: `xd`'s own punch-pass compliance block lists each of the five and asserts 17,148 · 37,078 · 495,115 · 1,096,202 · 5,236,427 · 5,235,942 unchanged. No report from this seat reached this log |
| **`f5`** `f5.md` — eleven marked edits across §5.3(b), §5.4(3), §5.6, §5.7, §5.9, §5.10 and its compliance block | Six corrections, one of which is the new measurement below. §5.4(3)'s denominator **17 342 → 17 345** (numerator and 24.0% unchanged), with `xb`'s snapshot caveat carried across. §5.3(b)'s Gap-13 prop restated: **two obstacles in series and only the first is a refusal** — the wrapper makes the index uncreatable; an index on the character-exact compiled operand *is* created and is still unused, which is **"creatable but unusable", not refused**. §5.6 struck *"monotonic from row 20 001"* — never measured, withdrawn by `f4` §4.7 — for *"monotonic across the six measured sizes, 100 / 100 / 100 / 88 / 38 / 4%"*. §5.10 restated the wall-clock endpoint against `consistency.md` §5 rather than `.parts/` mtimes this pass invalidated, and recorded that the punch-list round emitted **no `worker.started` of its own**, so closure-side effort is **under-counted** by the event record | The seat's report carries its own verification per item and reached this log truncated after four of them; those four name `xb` B.4, `xd_sweep.json`, an independent read-only re-census, `.autodev/events.jsonl`, `f4` §4.7/§4.12 and `f3` §3.3 T4a. Re-verified here: the §5.7 measurement (below) and the §5.4(3) identity |
| **measurement seat** — `proto/closure_subset_coverage.py` → `analysis/subset-coverage.json` | Built the round's one **retained** instrument — `xd` and `f5` each wrote a further walker to a session scratchpad, outside the repository, and those are not retained — and produced its one new published number (below). Read-only, no database, imports the real parser and walks all 130 fixture ASTs | Both files carry **mtime 2026-08-19 16:27:39**, inside this round's window — `proto/` and `analysis/` mtimes are the class of citation this pass's systemic `.parts/` mtime defect does **not** touch. No report from this seat reached this log; `f5`'s compliance block names it as a separate seat and states `f5` read the two files without re-running them |
| **`f0` + this log** (this seat) | `f0`'s audit paragraph rewritten to describe **three** passes rather than one, with the refusal count reconciled; this log retitled, given the two over-claim corrections and row 21's correction above, and this section appended | The reconciliation is counted off the refusal table row by row; row 21 is read off `f3`'s summary paragraph as it now stands; the two over-claims are read off `xc` C.8/C.11(b) and `xb` B.4 as they now stand |

#### The new measurement — the one substantive addition this round makes

`f5` §5.7 names the subset a CONDITIONAL-GO would have to adopt, and until this round its fixture coverage
was published as **NOT ESTABLISHED** (*"computing it is one AST walk over `expr_vectors.json`, unrun"*). It
has been run. **The corrected subset is 32 of 48 constructs and covers 68 of 130 fixture cases — 52.3%.**

- **Re-counted here from the raw artifact** — `analysis/subset-coverage.json`, by tallying the **130
  per-case verdicts** rather than reading its headline block: `panel_subset` **84**,
  `corrected_subset_reading_A` **68**, reading B **62**, reading C **56**, all of 130, reproducing every
  published figure. That checks the file against itself, not the walker against the fixture; the
  independent walk of the fixture was `f5`'s. The construct arithmetic checks too: 10 node types + 4
  arithmetic operators + 6 comparisons + 7 functions + 5 field-path forms = **32**.
- **The control is what makes it credible.** The instrument reproduces `panel.json[0]`'s **84 of 130
  (64.6%)** — a figure computed by a different seat in a different pass — before it reports the corrected
  **68**. `f5` re-derived both again with a separately-written walker.
- **What it does to the argument: it weakens CONDITIONAL-GO, modestly, and moves nothing else.** The panel
  seat's coverage claim was **12.3 points of the fixture too high**; the correction costs 16 cases and
  decomposes exactly (`%` 7, `round` 5, `floor` 2, `ceil` 2). AVOID's price at the corrected subset is
  **62 of 130 refused (47.7%)**, not the 46 of 130 (35.4%) that three other places in `f5` still quote
  from the uncorrected subset. `f5` states in place that this does not move its verdict, which never
  rested on it.
- **What it is not.** A **contract-surface** count, not a fraction of production traffic — there is no
  `DataSource` corpus in either tree (`f2` §2.9) — and it says nothing about the **residual divergence rate
  inside** the surviving 68, which remains unmeasured and is what E1 exists to measure.
- **Grey area, disclosed rather than glossed.** This is a **new instrument built during a repair pass**, the
  same class of grey area `consistency.md` item 24 raised about `xd_sweep.py` and which this log records
  above. It fixes nothing and designs nothing (`FRAMING.md` §3); it counts, read-only, over artifacts the
  investigation already had. But the number is **younger than the investigation that surrounds it**, and
  `f5` §5.7 says so in place. Its own provenance block records `analysis/subset-coverage.json` as the only
  file it wrote, and does not list the script; the script exists and carries the same mtime.

#### What was refused

**One refusal is recorded, and the record is incomplete by construction.** Exactly one report — `xc`'s —
reached this log with its refusals section intact; `xa`'s and `f5`'s were truncated before theirs, and
`xb`'s, `xd`'s and the measurement seat's did not reach it at all. Those five entries are read off the
seats' own in-place text, and a refusal a seat made but did not write into its file would not appear here.
That is a gap in this log, not evidence that there were no others.

| seat | what was refused | the raw evidence |
| --- | --- | --- |
| **`xc`** | Extending the same unit repair into **§C.12 item 1**, which carries the identical id/class denominator switch. Refused on scope — the punch list named §C.8's headline and §C.11(b) only — and on merit: unlike the headline, **C.12 never performs the addition**. It says a run-time fallback "can only ever fire on the RAISE classes. That is **6 of 34**", then "for the **18 undetectable classes** there is nothing to trigger". Each is true in its own unit (6 RAISE ids of 34 ids; 18 undetectable classes of 33), so there is no false arithmetic to correct — only an unannotated denominator switch. Reported instead of edited | `xc` C.12 item 1. `f5` §5.8(a) quotes this exact pair, cites `xc` C.12 by name, and was **already annotated** in the repair pass — so the downstream citation now reads more carefully than the source it points at. One-token fix if a later seat is authorised: insert "(19 ids)" after "the **18 undetectable classes**" |

#### New defects found this round, and not fixed

- **`xc` C.12 item 1** carries the id/class denominator switch described in the refusal above. **Not
  decision-blocking** — both figures are true in their own units and the text never sums them — and not
  edited, because the punch list did not name it and three lenses had certified it.
- **`f5`'s "the measurement seat" is not represented in this log by a report.** Its two artifacts are
  self-describing and were re-derived independently here, so nothing rests on the gap; it is recorded so a
  later reader does not mistake the artifacts' provenance for something this log verified end to end.
- **`analysis/subset-coverage.json`'s `files_written` lists only itself**, not the script that generated it,
  which was written in the same second. Cosmetic; the script is present and named in the JSON's
  `generated_by`.
- **Line-length only, no figure involved:** the `xc` §C.11(b) sentence repaired this round sits on a
  ~200-character source line where the file otherwise wraps near 100. It renders identically; it was left
  unwrapped so the diff does not touch certified prose. Flagged so the assembling seat is not surprised.

#### What this round did to the argument

**Nothing moved the verdict, and no seat's in-place text claims otherwise.** `f5` still recommends
**NO-GO**; all three lenses independently said so before this round began, and every `[punch]` edit
either corrects a citation, restates a figure in one unit, or withdraws an over-claim. Three legs moved at
their edges, and a fourth entry records a figure whose residual is now explained rather than open. Each
says so in place:

| leg | direction | where it is stated in place |
| --- | --- | --- |
| Gap 13 leg (b) — indexability | **narrowed again, one level below the repair pass's narrowing.** "The index that would fix (a) is a *predicate* index, which is exactly the class still refused" was the last absolute standing in this leg. Two obstacles sit in series and only the first is a refusal; the second is **creatable but unusable**, and what lifts it is a change to what `compile.py` emits, not a permission — which is why `f3` §3.4 lists four compiler changes rather than one. The coupling the leg exists to establish survives | `f5` §5.3(b); `f3` §3.3 T4a and §3.4 |
| the `MAX_SCAN`-urgency leg | **weakened at the wording, not at the measurement.** "Monotonic from row 20 001" asserted an onset that was never measured; the six measured sizes stand, and the smallest over-cap size tested (25 000) is already 12% wrong | `f5` §5.6; `f4` §4.7 and §4.12 row 7 |
| the CONDITIONAL-GO reading | **weakened, modestly, and for the first time on evidence rather than on a gap.** The subset a CONDITIONAL-GO would name covers **68 of 130** of the contract fixture, not the 84 the panel seat argued from | `f5` §5.7 |
| `xb`'s 4 166-row claim | **unchanged; its residual explained and its shelf life stated.** 17 342 reproduces one checkpoint earlier; 17 345 is a snapshot, and a later reader will measure a larger denominator against the same numerator | `xb` B.4; `f5` §5.4(3) |

#### Assembly, as it now stands — four changes the next assembling seat needs

The *Assembly* note above describes the **previous** round's assembly and was left as written. Four things
have changed since it was written, none of them a change to the body:

- **Eleven parts, not ten.** The closure log was appended to `FINDINGS.md` by the repair pass and has since
  been extracted into `.parts/f6-closure-log.md`, so it assembles like any other part. The concatenation
  order is `f0 · f1 · f2 · f3 · f4 · xa · xb · xc · xd · f5 · f6`.
- **This section's anchor changed** with its heading, to `#closure-log--what-the-audit-passes-changed`.
  `f0`'s two links were updated in the same round; a grep across `.parts/` finds no other link to either
  anchor, and `f5` and `xd` refer to this log by **filename**, which is unaffected.
- **`f1`–`f4` were not edited this round** — no `[punch]` marker appears in any of them — so the five files
  the punch-list round rewrote are `xa`, `xb`, `xc`, `xd` and `f5`, plus `f0` and this log.
- **The part-file `file:line` citations that note flags are gone.** `xd` converted its seven to section
  references this round, and a grep across every part now finds no `f<n>.md:<line>` or `x<x>-….md:<line>`
  citation at all. The `.md:<line>` citations that remain point at `analysis/index-shape.md` and
  `analysis/coverage.md`, which are stable files a reader can open.

#### Compliance — this seat, this round

Read-only except for the two files this seat was permitted to write: `spikes/T-1/.parts/f0-header.md` and
`spikes/T-1/.parts/f6-closure-log.md`. **No defect found by this spike was fixed** (`FRAMING.md` §3), no
database was contacted, no Postgres connection was opened, and nothing in `proto/`, `analysis/`, `recon/`,
either GIMS tree, `.autodev/` or any other part file was modified — `FINDINGS.md` included, which a later
seat regenerates from the parts. Read to verify the entries above: `.parts/consistency.md` (items 12, 15, 21
and the verdict), `FRAMING.md` §3/§4/§5, `.parts/closure-reports.md`, and the current state of `f3`
(§3 summary, §3.5(c)), `xc` (§C.8, §C.11(b), §C.12), `xb` (§B.4), `xa`, `xd` and `f5` (§5.7, §5.9, §5.10 and
the compliance block); `analysis/subset-coverage.json` re-counted with `python3`; `xd_sweep.json` re-read
from the earlier session's scratchpad; `ls --full-time` over `proto/` and `analysis/`. **The verdict was not
this seat's to move and was not moved.**

---

### Final-check round — the one edit the fourth adversarial read asked for

After the punch-list round the assembled document was read once more, adversarially, end to end. That
read returned **gate-ready, 5 defects, none decision-blocking**, and independently re-derived the
round's newest claim: it wrote its own AST walker against the real parser and reproduced **84/130** for
`panel.json[0]`'s subset (the control), **68/130 (52.3%)** for the corrected subset, the `% 7 / round 5 /
floor 2 / ceil 2` decomposition with zero multi-blocker cases, and all three container-operand readings
(68 / 62 / 56). It also confirmed the assembly reproduces byte-identically (sha256
`3032b5f2…`) and that the refusal count reconciles 5/4/3 across `f0`, this log's prose and its table.

Its one substantive finding was that **this document understates its own case**, and one edit was applied
in response — by the dispatching session, inline, against an artifact that already existed:

| where | what changed | verified against |
| --- | --- | --- |
| `xc` §C.10 | "one hole that matters" → **two holes, the larger measured**. D1–D5 survives the corrected subset: `analysis/fuzz/A_f8_guard.txt` §A2 measures **8 of 16** paths diverging at `a = 1e300` as entirely in-subset, three of them order comparisons (the pushdown-predicate path), and `max($.l)` returning SQL `1` for Python's `1e+300` — a silently wrong *number*, FRAMING §4's disqualifying clause verbatim | `analysis/fuzz/A_f8_guard.txt` §A2 (16 of 20 paths diverge); `analysis/subset-coverage.json` → `subset_definition.corrected_functions` = `abs coalesce count if length max min`, `closure_removes.functions` = `ceil floor round`, `closure_removes.operators` = `%` |
| `f5` §5.5 reason 1 | the subset's residual is "not merely unmeasured but **partly measured and non-empty**", citing the same eight paths | same |
| `f5` §5.7(ii) | "still **unmeasured**" → "**not fully measured — but no longer zero-by-assumption**"; what remains unmeasured is the *rate* | same |
| `xc` §C.12 item 1 | "18 undetectable classes" → "18 undetectable classes **(19 ids)**", closing the last unannotated id/class denominator switch, which `f5` §5.8(a) already carried | `xc` §C.8 register rows |

**Direction: every one of these strengthens the NO-GO.** They remove ground a CONDITIONAL-GO advocate
could have taken because the document had conceded it unnecessarily. The four remaining defects from that
read were left as reported — a disclosed units slip, a 24-vs-23 item count the log corrects itself two
paragraphs later, a self-referential grep claim, and a citation-precision slip in an E1 parenthetical.
None is decision-blocking and none touches a measurement.

**The verdict was not moved by this round either.** It was tested a fourth time — against a live read of
`resolve()` in `GIMS-Project/api/dashboard/sources.py`, which returns exactly
`{"records", "count", "truncated"}`, with no `pushed_down` and no `fallback` field — and it held.

---

### Amendment round — three corrections a dead closure seat never applied

**Date: 2026-08-21. Authority: the owner, 2026-08-21 — the ruling recorded as go-ahead `GA-3`** in this ticket's
event log (`.autodev/events.jsonl`), whose item 2 reads *"Fix them — re-fingerprint the document."* Nothing
in this round is discretionary: it applies **three named corrections and nothing else**.

This is the first round to change `FINDINGS.md` since the final-check round above, and the first change of
any kind made to it **after** its contents were fingerprinted — see *Fingerprint* at the end of this entry.

#### Why there was anything left to fix

Two terms, since they are this document's own shorthand and not general English. A **closure pass** is the
round in which one worker per finding takes the list of corrections an independent verifier raised against
that finding, re-checks each one against the raw file it names, and then edits the finding in place. A
**seat** is one such worker — one finding, one worker, one report.

The seat for **Finding 2 — Coverage and fallback** never finished. It lost its API connection mid-response
and died. The only record of this anywhere in the spike is six words in
`.parts/closure-reports.md:13` — *"(agent died: API connection lost mid-response; file untouched)"* — and
`FINDINGS.md` did not disclose it at all. Worse, `f2`'s own compliance block (`:1330`) states that a single
§2.4 edit "is the only change made to this file after it was first written", which reads as a clean bill of
health rather than as the trace of a pass that never ran. Meanwhile the verifier's list survived intact:
`.parts/verifications.json → Finding 2 — Coverage and fallback → corrections` holds **six** corrections. All
six were lost with the seat. The 2026-08-21 re-check found them and re-derived them
(`RECHECK-2026-08-21.md` §3.2, and §6, which assigns the third of them here); **three** were confirmed as
live errors still standing in the published text. Those three are what this round applies.

#### What this round changed — three edits

Each is marked **`[amend-2026-08-21]`** at the point of change, with its own account of what the text used to
say and why it was wrong, so a later reader is never left comparing this file against its recorded checksum
with no explanation for the difference.

| # | where | what changed | re-verified here against |
| --- | --- | --- | --- |
| **A1** | `f2` §2.6, the C3 table (`:1124` as fingerprinted) | *"first failing size"* for `1 or 1 or …` / `1 and 1 and …` / `not not …1` corrected from **400 / 334 / 499** operands at **1996 / 1999 / 1997** chars to **333 / 333 / 332** at **1661 / 1993 / 1329**. The old integers were the *largest* chains fitting under `MAX_SOURCE_LEN = 2000`, not the first that fail — the ceiling published as the floor, which understated how easily C3 is reached. Direction: **against the compiler**, i.e. the defect is worse than published | Fresh bisection through the real `expr.parse` into `proto/compile.py`: `n−1` compiles and `n` raises for each of the three; all three still evaluate correctly in Python at the failing size; and the old 400 / 334 / 499 confirmed to be exactly one operand short of exceeding 2 000 characters. `verifications.json` `corrections[0]`, severity **material** |
| **A2** | `f2` §2.6, the C4 paragraph (`:1143-1144` as fingerprinted) | *"The parser permits depth 64 and 2000 characters permit depth 165"* → **depth 63**, with the second clause dropped as moot. `_primary` increments the depth counter **and then** tests it (`expr.py:185-187`) against `MAX_DEPTH = 64` (`expr.py:40`), so the counter reaches 64 only on the expression that is rejected and the deepest surviving nesting is one below the constant. The character budget never binds, because the depth guard refuses a 165-deep nest first | The GIMS source read directly, plus a live measurement: a 63-deep `date_add` nest parses, a 64-deep one raises `ExprError("Expression nesting too deep")`. Conclusion unaffected — 63 is still far past 24. `verifications.json` `corrections[5]` |
| **A3** | `f2` headline summary table (`:925` as fingerprinted) | The unscoped **403 / 403** out-of-fixture row is now scoped to **value-domain *kind* probes**, with a note recording the second, separate out-of-fixture set the table omitted: `proto/results.json → out_of_fixture_probes`, **8 probes — 3 agree, 4 `DIVERGES`, 1 `SQL_ERROR (totality violation)`**. Direction: **against the compiler**; a gate reader scanning only the table previously took away "100% clean out-of-fixture probing" | `proto/coverage_probe_results.json` re-counted: 403 entries, all `COMPILED_AGREES`. `proto/results.json` re-counted: `Counter({'DIVERGES': 4, 'agrees': 3, 'SQL_ERROR (totality violation)': 1})` over 8 probes. §2.5 and §2.7 R1–R4 confirmed to carry the four divergences already, so the body was never wrong — only the summary row. `verifications.json` `corrections[1]`, severity **material**; assignment per `RECHECK-2026-08-21.md` §6 |

**Every correction was re-verified against its raw artifact before a character was changed**, under the same
standing rule the consistency-repair pass worked to. None was refused: all three held.

#### What this round did NOT change

- **The other three of the six lost corrections are still unapplied.** All three are severity **cosmetic** in
  the verifier's own grading, and none was re-run by either 2026-08-21 seat, so none has been re-verified
  against its source: `corrections[2]` — §2.9's `cascade_deep_search` quotation is a splice of two different
  docstrings presented under one `deep_search.py:389-390` cite (the substantive claim, that the function is
  pure and does no I/O, is correct); `corrections[3]` — §2.9's `gims-ledger` sweep is described as covering
  "every SQLite database" when 2 of 33 files are malformed and were silently skipped (the n=1 result itself
  reproduces); `corrections[4]` — §2.1's line cites for unary `+` and for parentheses are both off by a few
  lines (the claim they support is correct). They are recorded here so the residue is visible rather than
  forgotten a second time.
- **Nothing else in the document was touched.** Every other correction the re-check found — the spent
  "never emitted" residual at `:5193`, the `+463%` framing and its orphan measurement block, the seat-count
  arithmetic, the three non-reproducing command outputs — is recorded in `RECHECK-2026-08-21.md` and was
  **out of scope for this round**, which was authorised for three named items only.
- **The verdict was not moved, and was not this round's to move.** All three corrections point the same way:
  each makes a defect look slightly worse than the published text did, so none of them can weaken a
  **NO-GO**. No measurement was re-run, no database was contacted, and no defect found *by* the spike was
  fixed (`FRAMING.md` §3).
- **Read-only elsewhere:** `FINDINGS.md` is the only file this round wrote. Both GIMS checkouts were read
  only — `expr.py` was read and its parser exercised in-process, nothing written. `proto/`, `analysis/`,
  `.parts/`, `RECHECK-2026-08-21.md`, `tracker.mjs`, `.autodev/tickets/` and `.autodev/events.jsonl` are
  unmodified.

#### Fingerprint

This document's sha256 as fingerprinted before this round — the value carried in `.autodev/events.jsonl` as
the evidence fingerprint of the earlier stage — is:

```
67fbe421adccd5cb8ad80d4f21127c04e2966df2b1d446a07ccc864c195a38c8
```

That value is **superseded** by this amendment and will no longer match this file. It is left standing in the
event log, which is append-only and was not edited here; the driving session records the supersession and the
new digest against `GA-3`. Anyone auditing this document should compare against the new digest, and read this
entry as the reason the two differ.
