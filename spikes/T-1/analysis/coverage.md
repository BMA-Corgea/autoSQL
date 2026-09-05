# T-1 · Coverage + fallback — which constructs compile, which cannot, and what happens when they don't

**Seat:** coverage + fallback (`FRAMING.md` §4, finding #2).
**Stage:** `sp-investigate`. **Decision authority:** recommend-and-wait — this document
supplies evidence for the `sp_decide` gate, it does not decide.

**The two questions this document owns, and nothing else:**

1. Which grammar constructs compile, which cannot, what is the explicit fallback rule for
   each — and is that fallback **detectable and reported at query time, or could it be
   silent** (`FRAMING.md` §4, the GO bar)?
2. Confirm the `query` source does not push down, and **bound** it.

**Not this seat's question:** per-case conformance (finding #1, already run — 130/130), the
index shape (#3), the measurement (#4), the recommendation (#5).

**Read and built on, not redone:** `recon/fixture.md` (complete 130-case inventory, 16
groups), `recon/semantics.md`, `recon/query-source.md` (establishes `cascade_deep_search`
is a pure in-memory scored cascade), `proto/CONFORMANCE.md` + `proto/results.json`.

---

## 0. Headline

| | count | |
|---|---|---|
| Named grammar constructs, total | **48** | mechanically enumerated from `expr.py`, §1 |
| **Compile AND proven by a fixture case** | **46** | §3 |
| **Compile but NOT exercised by the fixture** | **2** | `<=` and bare `$` — §4 |
| **Do not compile** | **0** | `compile.py` refuses no construct — §2 |

That third column being empty is the single most important structural fact in this
document, and it is a two-edged one. It means there is no construct-level fallback to
design. It also means **`Uncompilable` is almost never the thing that will fire in
production** — so a fallback mechanism keyed on `Uncompilable` would be a mechanism that
almost never runs, guarding against a failure mode that is not the real one.

The real exposure is not the construct column at all. It is the **value domain**: the same
48 constructs applied to JSON values the 130 hand-authored cases never feed them. Sized
honestly, the fixture leaves **29 of 36** `_eq` operand-kind cells and **32 of 36**
`_order_cmp` cells untouched (§4.2). I probed that gap directly rather than reporting it as
unknown: **403 out-of-fixture probes, 403 agree** (§5), which closes both matrices to 36/36.

**Fallback detectability verdict (the GO bar): as the code stands, nothing would report a
fallback — and two of the four ways compilation actually fails today (`RecursionError` on a
665-char expression, `MemoryError` on a 300-char one) do not raise `Uncompilable` at all, so
a caller that catches `Uncompilable` would not even catch them.**
Neither is silently-wrong-number (FRAMING §5 is not breached), but neither is reportable
either. Detail and the exact code trace in §7. This is a fixable gap, not a defect in the
compiler's arithmetic, and §7.4 says what would have to be added.

---

## 1. The construct universe — enumerated mechanically, not by eye

Source of truth is the evaluator, not the design doc. Two lists were extracted from
`GIMS-Project/core/dashboard/expr.py` @995cc59 (byte-identical in `gims-ledger`@7b7a049 per
`FRAMING.md` §2/C2) by script, not transcription:

- **AST node tags** — every `if tag == "..."` branch in `_eval` (`expr.py:578-641`).
- **Function whitelist** — the keys of `_FUNCTIONS` (`expr.py:530-553`).

```
$ .venv/bin/python  (script: scratchpad/inv1.py)
AST_TAGS_IN_EVAL   12  ['num','str','bool','null','field','neg','not','and','or','cmp','bin','call']
FUNCS_IN_EXPR      22  ['abs','avg','ceil','coalesce','concat','contains','count','date_add',
                        'days_between','floor','if','length','lower','max','min','now',
                        'number','round','string','sum','today','upper']
```

Cross-checked against `proto/compile.py`'s dispatch (`_t_<tag>` methods at
`compile.py:196`, `_f_<name>` methods at `compile.py:299`):

```
COMPILE_TAGS             12   TAGS_MISSING_IN_COMPILE   []
COMPILE_FUNCS            22   FUNCS_MISSING_IN_COMPILE  []
COMPILE_EXTRA_TAGS       []   COMPILE_EXTRA_FUNCS       []
```

**Every AST tag and every whitelisted function has a compiler method. The two sets are
exactly equal in both directions** — the compiler implements no construct the language
does not have, and omits none that it does.

Two grammar productions correctly appear as *no* AST node and so are not constructs to
compile:

- **unary `+`** — `_unary` (`expr.py:180-182`) consumes the token and returns the operand
  unchanged. There is no `("pos", …)` node, so there is nothing for `compile.py` to handle.
- **parentheses** — `_primary` (`expr.py:196-199`) returns the inner node directly.

### The 48 named constructs

Counted so nothing is double-counted: the `cmp` and `bin` tags are counted through their
operators rather than as tags, since that is the granularity at which they can differ.

| family | n | members |
|---|---|---|
| leaf / structural node types | 10 | `num` `str` `bool` `null` `field` `neg` `not` `and` `or` `call` |
| arithmetic operators (`bin`) | 5 | `+` `-` `*` `/` `%` |
| comparison operators (`cmp`) | 6 | `==` `!=` `<` `<=` `>` `>=` |
| whitelisted functions (`call`) | 22 | the `_FUNCTIONS` list above |
| field-path forms (`field`) | 5 | bare `$` · `.ident` key · `["quoted"]` key · `[n]` index · `[-n]` index |
| **total** | **48** | |

`.ident` and `["quoted key"]` produce the *identical* AST step `("key", k)`
(`expr.py:238,242`) and so are one construct to the compiler; they are listed separately
only because they are distinct source syntax and the fixture exercises both.

---

## 2. Column 3 — "does not compile": **0 of 48 constructs**

No construct in the language is refused by `compile.py`. §1 establishes this by set
equality, and every one of the 48 was compiled individually to confirm it (§3, §5).

So there is **no construct-keyed fallback rule to write** — the table people expect here
("`X` doesn't compile, so fall back when you see `X`") does not exist, because there is no
such `X`.

### 2.1 But compilation can still fail — on *shape*, not construct

`Uncompilable` (`compile.py:54-59`) is raised from seven places. Five are unreachable
guards against a malformed AST (`compile.py:194,200,237,274,294` — the parser's tag,
path-step and operator universes are closed, so these are defensive only). **Two are
reachable from a valid, in-sandbox expression**, and both are keyed on the *shape or
magnitude* of an expression, never on which constructs it contains:

| # | trigger | site | reachable? |
|---|---|---|---|
| R1 | a numeric **literal** that overflows float8 | `compile.py:204-209` | **yes** |
| R2 | generated SQL exceeds `MAX_SQL_CHARS` = 200 000 | `compile.py:172-176` | **yes** |

**R1 — numeric literal overflow.** `parse()` builds `("num", inf)` via bare `float()` on the
token (`expr.py:193`); jsonb has no representation for infinity, so the compiler refuses.
Measured (`scratchpad/inv2.py`):

```
1e308  -> COMPILES
1e309  -> UNCOMPILABLE  numeric literal overflows to inf/nan; jsonb has no representation for it
1e400  -> UNCOMPILABLE       (expr.parse('1e400') == ('num', inf))
-1e400 -> UNCOMPILABLE
$.a + 1e400 -> UNCOMPILABLE  (the whole expression, not just the literal)
```
This is the *good* failure: a named, catchable refusal, correctly preferring an honest gap
to a wrong value. It is column-3 behaviour at the level of a literal rather than a construct.

### 2.2 Two failure modes that are NOT `Uncompilable` — the finding of this section

A caller writing the obvious fallback —

```python
try:    sql = compile_ast(ast)
except  Uncompilable: fall_back_to_memory()
```

would **not** catch either of the following. Both come from expressions that `expr.parse()`
accepts and `expr.evaluate()` answers correctly, and both are well inside the language's own
sandbox limits (`MAX_SOURCE_LEN = 2000` at `expr.py:39`, enforced `expr.py:268`; `MAX_DEPTH = 64` at
`expr.py:40`, enforced `expr.py:187`).

**F1 — `RecursionError` on a flat operator chain.** `compile.py` recurses ~3 Python frames
per AST level (`_j` → `_t_bin` → `_num` → `_j`), against CPython's default limit of 1000.
A left-deep chain adds one AST level per operand, and the parser's `MAX_DEPTH` guard does
**not** catch it — `_primary`'s depth counter is incremented and decremented around each
primary (`expr.py:184-208`), so a flat `1+1+1+…` never exceeds depth 1.

Measured by bisection (`scratchpad/inv3.py`, `inv4.py`):

| expression | first failing size | source length | `expr.parse` | `expr.evaluate` | `compile_ast` |
|---|---|---|---|---|---|
| `1+1+1+…` | n = **332** | **665 chars** (cap 2000) | OK | OK → `332.0` | **`RecursionError`** |
| `1 or 1 or …` | n = 399 at 1996 chars | 1996 | OK | OK | **`RecursionError`** |
| `1 and 1 and …` | n = 333 at 1999 chars | 1999 | OK | OK | **`RecursionError`** |
| `not not not …1` | n = 499 at 1997 chars | 1997 | OK | OK | **`RecursionError`** |

A **665-character** expression — one third of the language's own limit — is enough.

**F2 — `MemoryError` from exponential SQL growth.** `_f_date_add` (`compile.py:318-326`)
compiles its first argument **twice**: once inside `xpr.pdate_ms(...)` and again inside
`xpr.pdate_only(...)`, because the date-only flag comes from the input and cannot be
recovered from the timestamp (the comment at `compile.py:322-323` states this). Nesting
`date_add` therefore **quadruples** the generated SQL per level. Measured
(`scratchpad/inv5.py`, `inv6.py`):

| nesting depth | source length | generated SQL | outcome |
|---|---|---|---|
| 1 | 24 | 168 chars | compiles |
| 4 | 60 | 2 184 | compiles |
| 8 | 108 | 36 744 | compiles |
| 12 | 156 | 589 711 | `Uncompilable` (over the 200 000 cap) |
| 20 | 252 | 150 996 871 | `Uncompilable` — **after materialising 151 MB** |
| **24** | **300** | ~2.4 GB | **`MemoryError`** (measured under a 2 GiB `RLIMIT_AS`) |

The cap at `compile.py:172-176` is checked **after** `self._j(node)` has already built the
whole string, so it cannot prevent the blow-up it exists to bound — it only reports it
afterwards, and only while the string still fits in RAM. The parser permits nesting to
depth 64 and 2000 chars permits depth 165, so the reachable worst case is far past 24.

At depth 24 the source is **300 characters**; `expr.evaluate` answers it correctly and
instantly (`2026-01-25`). This is a denial-of-service shape, not a wrong-answer shape.

**Severity, stated plainly.** Neither F1 nor F2 produces a wrong number, so neither
breaches the FRAMING §5 non-negotiable — they are loud failures. But both breach the
**other** half of the GO bar ("every non-compiling construct has a named fallback"): the
named fallback signal is `Uncompilable`, and these do not raise it. Per the `sp-investigate`
stop rules these are **recorded, not fixed**; `compile.py` and `runtime.sql` were not
touched (§9). The fix is small and is named in §7.4 for whoever picks it up.

---

## 3. Column 1 — compiles **and** proven by a fixture case: 46 of 48

"Proven" here means strictly: the construct occurs in at least one of the 130 cases, that
case was compiled, executed against live PostgreSQL 16.14, and its SQL value matched the
Python evaluator's under the rule mirrored from
`GIMS-Project/tests/test_dashboard_expr.py:20-25`. The conformance seat's run is the
evidence (`proto/results.json`, 130/130 `COMPILED_AGREES`, 0 gaps, 0 raises); this seat did
not re-run it, it mapped constructs onto it.

Counts below are per fixture **case** — a construct occurring twice in one case counts
once — produced by walking the AST of each of the 130 cases with the real parser
(`scratchpad/cover.py`), not by grepping text. (`==` for instance occurs 12 times across
11 cases.)

| construct | cases | construct | cases | construct | cases |
|---|---|---|---|---|---|
| `field` | 68 | `num` | 55 | `str` | 34 |
| `call` | 72 | `cmp` | 24 | `bin` | 18 |
| `neg` | 10 | `not` | 8 | `bool` | 7 |
| `null` | 5 | `and` | 3 | `or` | 3 |
| `+` | 5 | `-` | 2 | `*` | 4 |
| `/` | 2 | `%` | 7 | `==` | 11 |
| `!=` | 1 | `<` | 9 | `>` | 3 |
| `>=` | 1 | `.ident` key | 67 | `["quoted"]` key | 1 |
| `[n]` index | 2 | `[-n]` index | 1 | | |

All 22 functions occur at least once; the thinnest are `upper` (1 case), `min` (1), `now`
(1), `count` (2), `abs`/`ceil`/`floor`/`lower`/`avg` (2 each). `days_between` (9),
`string` (9), `date_add` (7) and `round` (5) are the best covered.

**One case is enough to prove a construct compiles. It is nowhere near enough to prove the
construct is *right*.** `upper` is proven by exactly one case, on ASCII input — and the
conformance seat's own out-of-fixture probe found `upper("straße")` diverging
(Python `STRASSE` vs SQL `STRAßE`). That is the shape of the risk this whole section
understates, and §4 is where it is measured.

---

## 4. Column 2 — compiles but **NOT** exercised by the fixture

This is the column that hides silent wrong answers, and it has two very different layers.
Conflating them is the mistake; they are reported separately.

### 4.1 Layer 1 — named constructs never exercised: **2 of 48**

| construct | why it matters | status |
|---|---|---|
| **`<=`** | 1 of the 6 comparison operators. `==`(11) `!=`(1) `<`(9) `>`(3) `>=`(1) all occur; **`<=` occurs zero times in all 130 cases.** It routes through `xpr.ord` (`compile.py:273`) with an operator string the fixture never sends. | **closed by probe** (§5) |
| **bare `$`** | the whole-record read. `_resolve_field(record, [])` returns the record itself (`expr.py:562-575`); `compile.py:222-240` emits `nullif(data, 'null'::jsonb)` with an empty path loop. Never exercised — every one of the 68 field cases has at least one path step. | **closed by probe** (§5) |

Verified by script (`scratchpad/cover.py`, and the operator/field-form recount): the
fixture contains 0 occurrences of `<=` and 0 occurrences of an empty field path.

### 4.2 Layer 2 — the value domain: the real gap, and it is large

Every one of the 48 constructs is *polymorphic over JSON value kinds*
(`null`/`bool`/`number`/`string`/`list`/`dict`). A construct being "exercised" says nothing
about which of those kinds reached it. `compile.py` dispatches these kinds inside the `xpr`
SQL functions, so an unexercised kind is unexercised SQL.

Measured by wrapping the evaluator's own helper functions and replaying all 130 cases
(`scratchpad/domain.py` — observation only, no behaviour change):

| helper | drives | kinds exercised | **never exercised** |
|---|---|---|---|
| `_truthy` (`expr.py:282`) | `not` `and` `or` `if` | 5/6 | **dict** |
| `_to_num` (`expr.py:305`) | all arithmetic, `neg`, `number`, `abs`/`floor`/`ceil`/`round`, all aggregates | 4/6 | **list, dict** |
| `_to_str` (`expr.py:351`) | `string`, `concat`, `lower`, `upper` | 4/6 | **list, dict** |
| `_parse_date_ms` (`expr.py:409`) | `days_between`, `date_add`, `today`/`now` | **1/6** | **null, bool, number, list, dict** |

And the two-operand relations, as full 6×6 operand-kind matrices:

```
_eq  (== / != / deep equality / contains-in-list)        cells exercised:  7/36
            null    bool  number  string    list    dict
    null       2       .       .       .       .       .
    bool       .       1       1       .       .       .
  number       1       .       2       .       .       .
  string       .       .       1       8       .       .
    list       .       .       .       .       .       .        <-- entire row empty
    dict       .       .       .       .       .       .        <-- entire row empty

_order_cmp  (< <= > >=)                                  cells exercised:  4/36
            null    bool  number  string    list    dict
    null       .       .       1       .       .       .
    bool       .       .       .       .       .       .        <-- entire row empty
  number       .       .      10       1       .       .
  string       .       .       .       1       .       .
    list       .       .       .       .       .       .        <-- entire row empty
    dict       .       .       .       .       .       .        <-- entire row empty
```

**29 of 36 `_eq` cells and 32 of 36 `_order_cmp` cells are never exercised by the fixture.**
No fixture case ever compares a list or a dict to anything, orders a boolean, or feeds a
container to `number()`/`string()`/`length()`-via-`_to_num`. No fixture case ever passes a
non-string to a date function.

This is not a criticism of the fixture — `recon/fixture.md` correctly describes it as 130
hand-authored contract cases, and its own note says "Hand-authored expected values — do NOT
regenerate from either evaluator". It is a coverage tool's job to find these, and the
fixture is not a coverage tool. **The point is only that 130/130 must not be read as
"the compiler is proven", and this is the size of the difference.**

---

## 5. Closing column 2 — 403 out-of-fixture probes, 403 agree

An unmeasured gap is not a finding, it is an excuse. Rather than report §4.2 as unknown, I
probed it directly against the same live database, through the **same oracle**: the probe
harness imports `matches()`, `deep_strict()`, `run_sql()`, `SqlRaised` and `DSN` from
`proto/conformance.py` rather than reimplementing them, so a probe is scored by exactly the
rule the 130-case run used. Harness: `proto/coverage_probe.py`; raw results:
`proto/coverage_probe_results.json`.

| probe group | n | what it closes |
|---|---|---|
| `cmp-matrix` | 216 | all 6 comparison operators × the full 6×6 operand-kind matrix — **including every `<=` cell** |
| `deep-eq` | 28 | list/dict deep equality: same, reordered keys, differing length, `1` vs `1.0`, `true` vs `1`, nested nulls, `0.0` vs `-0.0` |
| `truthy` | 24 | `_truthy` over all 6 kinds + empty list/dict/string, `0`, `false`, nested |
| `to_str` | 24 | `string`/`concat`/`lower` over all 6 kinds |
| `arity-edge` | 24 | zero-arg and over-arg calls across the whole whitelist (`lower()`, `contains(1,2,3)`, `if(1,2)`, `today(1)`, `round(1.5,-1)`, …) |
| `agg-arity` | 21 | `count`/`sum`/`avg`/`min`/`max` — empty, one-list, varargs, mixed-type lists |
| `to_num` | 18 | `number`/arithmetic/`neg` over all 6 kinds |
| `length` `contains` `date` | 12 each | `length` over all kinds; `contains` hay **and** needle over all kinds; date functions fed all 6 kinds |
| `bare-$` | 12 | the whole-record read, populated and empty |
| **total** | **403** | |

**Result: 403 `COMPILED_AGREES`, 0 divergences, 0 `Uncompilable`, 0 SQL errors.**

Coverage before and after, same instrumentation as §4.2:

| | fixture only (130) | probes only (403) | combined |
|---|---|---|---|
| `_eq` operand-kind cells | 7/36 | **36/36** | 36/36 |
| `_order_cmp` operand-kind cells | 4/36 | **36/36** | 36/36 |
| `_truthy` kinds | 5/6 | **6/6** | 6/6 |
| `_to_num` kinds | 4/6 | **6/6** | 6/6 |
| `_to_str` kinds | 4/6 | **6/6** | 6/6 |
| `_parse_date_ms` kinds | 1/6 | **6/6** | 6/6 |

Both §4.1 constructs are now proven: `<=` across all 36 operand-kind pairs, and bare `$`
across 12 probes.

### 5.1 Proof the probe harness can fail

A 403/403 sheet is exactly what `FRAMING.md` §8 warns will look green when it is wrong, so
the harness was tested against known-wrong inputs before its result is quoted
(`scratchpad/nc.py`). **11/11 negative controls behave as required:**

| control | expected | got |
|---|---|---|
| NC1 genuine `<=` probe | AGREES | AGREES |
| NC2 wrong boolean injected | DIVERGES | DIVERGES |
| **NC3 a number injected where Python has `null`** (FRAMING §5's disqualifying direction) | DIVERGES | DIVERGES |
| NC4 `NULL` injected where Python has `3.0` | DIVERGES | DIVERGES |
| NC5 jsonb `'null'` at top level distinguished from SQL `NULL` | DIVERGES | DIVERGES |
| NC5b SQL `NULL` vs Python `None` | AGREES | AGREES |
| NC6 a deliberate Postgres raise surfaces, not swallowed | `SQL_ERROR(22012)` | `SQL_ERROR(22012)` |
| NC7 `true` not accepted as `1.0` | DIVERGES | DIVERGES |
| NC8 wrong deep-equality verdict | DIVERGES | DIVERGES |
| **NC9 record `{}` vs `{a:2}`** — proves the record actually reaches SQL | DIVERGES | DIVERGES |
| NC10 epsilon is absolute, not relative (`1e9+1` vs `1e9`) | DIVERGES | DIVERGES |

NC3 and NC9 are the load-bearing ones: NC3 is FRAMING §5 stated as a test, and NC9 rules out
the possibility that the probes were passing because the SQL ignored the data.

### 5.2 What the probes do **not** close

Honest residue. These remain unproven by this seat and are not claimed otherwise:

- **The 7 `KNOWN_DIVERGENCES` in `compile.py:71-146`** are the compiler author's own list;
  6 of 7 are marked `in_fixture: false`. The conformance seat probed them and confirmed
  three (float8 overflow **raises** — a real totality violation; `num` out-of-range → NULL;
  Unicode case mapping) plus found a new one (the 297-digit `xpr.f8` range guard, which
  should be 309 digits, silently NULLing finite values above ~1.8e296). Those are that
  seat's findings and are not re-litigated here — but they are all **value-domain** issues,
  i.e. exactly the column-2 category this section is about, which is why they were invisible
  to 130/130.
- **String collation and case mapping beyond ASCII.** My probes use ASCII strings; ordering
  is pinned to `COLLATE "C"` (`runtime.sql`, `xpr.ord`) but case mapping is not.
- **Numeric precision beyond IEEE double.** `jsonb` stores `numeric`; a JSON literal with
  more than 17 significant digits cannot be reached through a Python-built record (it has
  already collapsed to a double), so `jsonb_numeric_is_not_ieee_double` stays **unconfirmed,
  not refuted** — same conclusion the conformance seat reached, for the same reason.
- **Date format variants.** `_parse_date_ms` accepts 6 shapes (`expr.py:402-407`); the
  fixture covers several and my probes covered the *kind* axis, not the *format* axis.
- **Coverage is not proof of correctness.** 36/36 cells exercised means every cell has one
  witness, not that every value in every cell agrees.

---

## 6. The explicit fallback rules

Because column 3 is empty (§2), **there is no construct for which the rule is "this
construct never compiles, always fall back".** Every fallback rule below is keyed on a
*condition* — a shape, a magnitude, a runtime value, or a source type — not on a construct.
That is the correct answer to the question as asked, and it is a more awkward answer than
the expected one, because a condition-keyed rule cannot be decided by inspecting the
expression text alone.

Legend — **Detectable**: could a caller mechanically know this happened?
**Reported today**: does any code path in GIMS as it stands surface it? (§7 proves the
"no"s.)

### 6.1 Compile-time conditions — decided before any SQL runs

| # | condition | fallback rule | detectable | reported today |
|---|---|---|---|---|
| C1 | numeric literal overflows float8 (`1e309`+) — `compile.py:204` | raises `Uncompilable` → evaluate this expression in memory | **yes** — catch `Uncompilable` | **no** |
| C2 | generated SQL > 200 000 chars — `compile.py:172` | raises `Uncompilable` → in-memory | **yes** — catch `Uncompilable` | **no** |
| C3 | **flat operator chain ≥ ~332 operands** (§2.2 F1) | **none — raises `RecursionError`** | only by also catching `RecursionError` | **no** |
| C4 | **nested `date_add` ≥ ~24 deep** (§2.2 F2) | **none — raises `MemoryError` / exhausts RAM** | only by also catching `MemoryError` | **no** |

C1 and C2 are correct and complete. C3 and C4 are the gap: the contract says the refusal
signal is `Uncompilable`, and these two do not honour it.

### 6.2 Run-time conditions — the SQL compiled, then Postgres disagreed or refused

These cannot be predicted from the expression; they depend on the row.

| # | condition | `expr` (Python) | compiled SQL | fallback rule | detectable | reported today |
|---|---|---|---|---|---|---|
| R1 | **float8 overflow in `+ - * /`** (e.g. `1e200 * 1e200`) | returns `inf` (`expr.py:614-621`, no guard) | **RAISES** `22003 value out of range` — aborts the whole query | catch SQLSTATE `22003` → re-run the widget in memory | **yes** — a raise is loud, but it kills the transaction, so the fallback must re-run from scratch | **no** |
| R2 | JSON number / numeric string beyond DBL_MAX | `inf` | guarded to `NULL` (`compile.py:84-93`, deliberate) | none — value silently differs | **no** | **no** |
| R3 | **finite value between ~1.8e296 and DBL_MAX passed through arithmetic** — the 297-digit guard literal in `xpr.f8` should be 309 digits | returns the number | **silently `NULL`** | none | **no** | **no** |
| R4 | `lower()`/`upper()` on non-ASCII (`"straße"`) | `STRASSE` | `STRAßE` under `C.UTF-8` | none — silently different string | **no** | **no** |
| R5 | `extra_float_digits` GUC ≠ 1 | shortest round-trip (`repr`) | `xpr.ecma_num` reads float8 text, which is shortest-round-trip only at `extra_float_digits ≥ 0` | pin the GUC per session | **no** at query time | **no** |
| R6 | `today()`/`now()` with **no** `context.now` | re-read **per record** (`expr.py:456`) | `now()` = **transaction** timestamp — pinned for the whole query | inject `context.now` always (every fixture case does; `resolve()` passes `ctx` through) | **yes** — the caller controls whether `context.now` is set | n/a |
| R7 | `==`/`!=` on JSON numbers with >17 significant digits | compares as IEEE doubles | `jsonb` compares as `numeric` — finer | none | **no** | **no** |

**R6 is the one KNOWN_DIVERGENCE this seat exercised that the fixture cannot.**
`compile.py:143-144` records that every fixture case injects `context.now`, so the
wall-clock path is never tested. Two of my `arity-edge` probes (`today(1)`, `now($.a)`)
pass `context = {}` and therefore do hit it — they agreed, but agreement in a single-row
probe proves little, so I measured the mechanism directly. Inside one transaction, 1.2 s
apart (`scratchpad`, live against `autosql_spike`):

```
probe1: SQL now()=2026-08-19 18:02:20   python now()=2026-08-19T18:02:20Z
probe2: SQL now()=2026-08-19 18:02:20   python now()=2026-08-19T18:02:22Z
        ^ pinned (transaction timestamp)          ^ advanced (re-read per record)
```

The divergence is **real and reachable**, not theoretical: a pushdown query is one
statement in one transaction, so every row shares one clock, whereas the in-memory path
re-reads the clock per row. For `now()` (second granularity) a 20 000-row scan will
routinely straddle a second; for `today()` it only bites across midnight. Note the
direction is arguably *better* — one consistent clock per result set — but it is still a
silent behavioural change, and it disappears entirely if `context.now` is always injected,
which is the stated fallback rule.

R3 and R4 are the ones that matter for FRAMING §5. Neither turns a `null` into a number —
the *disqualifying* direction — but both **silently produce a wrong value**, and R3 turns a
value into a null, which is the same defect mirrored. They are recorded here rather than
fixed, per the stop rules; R3 was found by the conformance seat and is **not** in
`compile.py`'s own `KNOWN_DIVERGENCES` list.

### 6.3 Source-level conditions — decided before the expression is even looked at

| # | condition | fallback rule | detectable | reported today |
|---|---|---|---|---|
| S1 | `source.type == "query"` | **whole source falls back** — `cascade_deep_search` is not a SQL statement, there is nothing to push into (§8) | **yes** — statically, from the spec | **no** |
| S2 | `source.type == "verb"` | falls back — compilable in principle, but `load_verb_group_log` bypasses `core.storage` entirely, so there is no seam to attach a predicate to (`recon/query-source.md` §4, §6) | **yes** — statically | **no** |
| S3 | `sort.field` names a **derived** column | the sort can only be pushed down if the `derive` that produced the column was also pushed | **yes** — statically, by comparing `sort.field` against `derive` keys | **no** |

S3 is not hypothetical: it is exactly what the one real dashboard on this machine does
(§8.3) — `derive: {days_left: …}` then `sort: {field: "days_left"}`. A pushdown design that
handles `where` but not `derive` cannot push that widget's sort at all.

---

## 7. Is the fallback detectable and **reported at query time**? — the GO-bar answer

`FRAMING.md` §4 makes this the GO bar, and §5 makes it the non-negotiable. Answering it
requires tracing the actual mechanism, not asserting one.

### 7.1 What `resolve()` does today — there is no fallback concept at all

`api/dashboard/sources.py:330-357`, the whole of it:

```python
loader = _LOADERS.get(stype)                         # :340   noun | verb | query
if loader is None: raise AppError("DASHBOARD_SOURCE_TYPE_UNKNOWN", ..., status=400)
ctx = dict(context or {})

raw = loader(project_path, source)                   # :347   ALWAYS in-memory today
truncated = len(raw) > MAX_SCAN                      # :348
if truncated:
    log.warning("dashboard source hit MAX_SCAN cap", {...})   # :350
rows = raw[:MAX_SCAN] if truncated else raw          # :351

rows = _apply_derive(rows, source.get("derive"), ctx)                       # :353
rows = _filter_rows(rows, source.get("filters"), source.get("where"), ctx)  # :354
rows = _apply_sort(rows, source.get("sort"))                               # :355
rows = _apply_limit(rows, source.get("limit"))                             # :356
return {"records": rows, "count": len(rows), "truncated": truncated}        # :357
```

There is **exactly one** evaluation path. `_apply_derive` (`:133-148`) and `_filter_rows`
(`:151-165`) call `evaluate(ast, row, context)` per row unconditionally. Nothing in this
module knows what a compiled query is, so today there is nothing to fall back *from* —
which is why "is the fallback reported?" is a question about code that does not exist yet,
and must be answered as a requirement on the design rather than as an observation.

### 7.2 Where the fallback would be detected

Pushdown has to **replace the loader call at `:347`**, not post-process its output — the
whole point is to avoid materialising up to `MAX_SCAN = 20 000` rows (`:61`). So the
compile attempt must sit between `:345` and `:347`, and the detection points are:

| detection point | signal | which rules from §6 |
|---|---|---|
| before `:347`, on the source spec | `stype != "noun"`; `sort.field ∈ derive` | S1, S2, S3 |
| before `:347`, calling `compile_ast()` on each `derive` expression and on `where` | `Uncompilable` — **plus `RecursionError` and `MemoryError`**, which the current contract does not name | C1, C2, **C3, C4** |
| at execution, around the `SELECT` | `psycopg2.Error`, notably SQLSTATE `22003` | R1 |
| **nowhere** | — | **R2, R3, R4, R5, R7 — these have no detection point at all** |

That last row is the important one. R2–R5 and R7 are silent by construction: the SQL runs
successfully and returns a value that simply differs from what Python would have produced.
No exception, no flag, no signal. **They cannot be detected at query time by any mechanism,
because from the database's point of view nothing went wrong.**

### 7.3 What would report it — nothing, today

Three candidate reporting channels exist in the current code, and none is adequate:

1. **The return contract.** `resolve()` returns exactly `{"records", "count", "truncated"}`
   (`:357`). There is **no field for how the result was computed** — no `pushed_down`, no
   `fallback_reason`. A caller cannot tell an in-database result from an in-memory one.
2. **`truncated`.** The only existing completeness signal, and it means something else
   entirely — the raw scan hit `MAX_SCAN`. The module docstring says it is surfaced "so the
   UI can warn" (`:58-60`), which makes it the *precedent* for reporting a degradation, but
   overloading it to also mean "fell back" would conflate two unrelated conditions.
3. **`log.warning` at `:350`.** Server-side only. A tenant looking at a dashboard sees
   nothing. Useful for operators, not a query-time report.

The one loud path — `_compile`'s `AppError("DASHBOARD_EXPR_INVALID", status=400)` at
`:121-131` — fires only on `ExprError`, i.e. a **syntax** error, and 400 is the wrong
response for "this valid expression cannot be pushed down": the correct behaviour there is
to compute it in memory and *say so*, not to reject the widget.

> **Verdict, stated plainly for the `sp_decide` gate:**
> **Nothing currently would report a fallback.** The detection points for the
> compile-time and source-level rules (C1, C2, S1, S2, S3) exist and are cheap; the
> *reporting* channel does not exist in the return contract at all. Two compile-time
> conditions (C3, C4) are not even detectable through the documented `Uncompilable`
> signal. And five run-time divergences (R2, R3, R4, R5, R7) are **undetectable in
> principle** by this design — they are silent by construction.
>
> Against the GO bar as written — "every non-compiling construct has a named fallback, and
> the fallback is detectable and reported at query time, never silent" — the first clause
> is vacuously satisfied (no construct fails), the second is **not met today**, and the
> third is **not achievable for R2–R5/R7 by detection alone**; those must be fixed at the
> source or accepted as known divergences with pinned deployment conditions.
>
> This is a **CONDITIONAL-GO shape**, which `FRAMING.md` §4 names as a legitimate verdict.
> The decision is the owner's; this seat supplies the evidence, not the verdict.

### 7.4 What closing the gap would take (named, not built — stop rules apply)

Small and mechanical, listed so the cost is visible at the gate:

- **Return contract:** add `pushed_down: bool` and `fallback: [{"scope", "reason"}]` to
  `resolve()`'s dict. This is the missing reporting channel; everything else depends on it.
- **C3:** convert AST recursion to an explicit stack, or raise `Uncompilable` past a depth
  budget. One guard, checked *before* recursing.
- **C4:** bind `date_add`'s first argument to a CTE / `LATERAL` so it is compiled once
  instead of twice, **and** move the `MAX_SQL_CHARS` check to accumulate during
  construction rather than after it (`compile.py:171-176`), so it bounds the work instead of
  reporting on it afterwards.
- **C3/C4 belt-and-braces:** have the adapter catch `RecursionError` and `MemoryError`
  alongside `Uncompilable` and treat them as fallback, so the contract holds even if the
  root causes are not fixed.
- **R1:** catch SQLSTATE `22003` and re-run in memory — note the transaction is already
  aborted, so this is a full retry, not a resume.
- **R3:** fix the `xpr.f8` range-guard literal to 309 digits (the conformance seat's
  finding; a one-line change to `runtime.sql`).
- **R5:** pin `extra_float_digits` on every pushdown session.

---

## 8. Half 2 — the `query` source: confirmed non-pushdown, and bounded

`FRAMING.md` §3's stop rule is explicit: **bound and confirm, do not attempt to make it
push down.** Nothing here attempts to.

### 8.1 Confirmation

`recon/query-source.md` establishes the mechanism and I confirm it rather than redo it.
Re-reading `api/dashboard/sources.py:237-317` and `core/deep_search.py:381` against its
claims, all hold:

- `cascade_deep_search` is a **pure function** — its docstring says "This function does NO
  I/O… Inputs must already be loaded into memory" (`core/deep_search.py:389-390`).
- `_query_records` loads **every noun instance of every noun type** (`sources.py:256-267`,
  no limit) and **every run of every verb group** (`sources.py:269-293`, no limit) into
  Python lists, then calls the cascade (`sources.py:301-308`).
- It searches three heterogeneous inputs — schema *definitions* (all four word types),
  noun instances, and verb runs — and schema definitions have no data-row shape at all.
- Matching is a **scored cascade with early exit** (`core/deep_search.py:154-341`), with
  per-row dynamic resolution of which key counts as the primary id, falling back to a
  hardcoded list of ~13 candidate id-field names.

**Confirmed: it does not push down, and cannot.** The blocker is architectural, not
expressive: pushing `derive`/`where`/`sort`/`limit` into Postgres means compiling them into
the *same statement* that acquires the rows. `query`'s row-acquisition is not a statement —
there is no `SELECT` upstream of the cascade to extend. Materialising the cascade's output
into a scratch table and querying that is today's in-memory behaviour plus a round trip, not
a pushdown, and is out of scope by the stop rule.

### 8.2 Bounding — what can and cannot be known

**What is certain (structural, from the code):**

- `RECORD_SOURCE_TYPES = ("noun", "verb", "query")` — `sources.py:53-56`. `query` is
  **1 of 3 record source types**.
- But the dashboard surface is **larger than the resolver**. The module docstring
  (`sources.py:1-14`) states there are **five** DataSource types: three record sources
  handled here, plus **two table/file sources — the CSV data-dump and the artifacts tree —
  "served by their own dedicated endpoints … not through this resolver"**
  (`/runlog/{p}/{g}/{run}/data/{tab}/parsed` and `/runlog/{p}/{g}/data_dumps/tree`).
  Those two never run `expr` at all, so they are outside T-1 entirely: nothing to push
  down, and nothing lost.
- So the honest structural fraction is: **`query` is 1 of 3 sources that reach the
  expression pipeline, and 1 of 5 DataSource types on the dashboard surface.**
- Within those 3, the picture is not "2 of 3 work": per `recon/query-source.md` §6, only
  **`noun`** has both a plausible SQL shape *and* an existing `RecordStore` seam. **`verb`**
  is compilable in principle but `load_verb_group_log` bypasses `core.storage` entirely, so
  it has no attachment point today. **The realistic near-term denominator is 1 of 3 — `noun`
  is the only source that can actually be pushed down without new integration work.**

**What cannot be known from this repository:** the *usage* distribution. Dashboards are
tenant data, persisted per project in a `dashboards` table
(`api/routers/dashboards/store.py:35`, `layout_json` column), not in either GIMS tree.
There is no default dashboard catalog, no seeded fixture, and no telemetry in the repo. **A
"1 of 3 source types" count is emphatically not "1/3 of usage", and this spike cannot
compute the real ratio.** Anyone quoting a usage fraction at the gate would be inventing it.

### 8.3 The one empirical data point on this machine — n = 1, and it is labelled as such

Searching every SQLite database in the `gims-ledger` tree read-only
(`sqlite3 "file:…?mode=ro"`, `select name from sqlite_master where name='dashboards'`)
found exactly **one** dashboard, present in two `LIMS-System` backups as the same row id
`143c987947874e36b728bb66f5a9125c` — so **one distinct dashboard, three widgets**:

| widget | `source.type` | reaches `resolve()`? |
|---|---|---|
| "Chart Widget" | **`csv`** | no — dedicated endpoint |
| "Table widget" | **`csv`** | no — dedicated endpoint |
| "Submissions in progress" | **`noun`** | yes |

Its actual spec:

```json
{"type": "noun", "noun_type": "Submission",
 "derive": {"days_left": "round(days_between(today(), $.due_date), 1)"},
 "where":  "$.status == \"in progress\"",
 "sort":   {"field": "days_left", "dir": "asc"}}
```

Three observations, each carrying its own weight:

1. **`query` usage here is zero; `verb` usage is zero.** Consistent with `query` not being
   the common case — but n = 1 dashboard bounds nothing statistically and must not be
   quoted as a rate. It is one data point, offered because it is the only one that exists.
2. **Two of three widgets use `csv`, a type that never reaches the resolver.** This is
   direct evidence for §8.2's point that "1 of 3" overstates `query`'s share of the
   *surface* — most widgets in the only real dashboard available do not touch this code path
   at all.
3. **The one widget that does reach the resolver compiles completely, and agrees.** I
   compiled its real `derive` and `where` expressions and ran them against live Postgres
   over six representative `Submission` records including the awkward ones — missing
   `due_date`, an unparseable `"not a date"`, an explicit JSON `null`, and a full timestamp
   (`scratchpad/realwidget.py`): **12 checks, 12 agree, 0 diverge.** All three null-ish
   records correctly produced SQL `NULL` where Python produced `None`.
   It also instantiates fallback rule **S3**: its `sort.field` is `days_left`, a *derived*
   column, so the sort is only pushable if the `derive` is pushed too.

### 8.4 What is lost if `query` never pushes down

Precisely, and no more:

- **Nothing is lost against today's behaviour.** The `query` source is fully in-memory now;
  not pushing it down leaves it exactly as it is. There is no regression, only a
  non-improvement.
- **The `MAX_SCAN` protection does not apply to it** — and this is the real cost.
  `recon/query-source.md` §8 establishes it and it is worth carrying to the gate:
  `MAX_SCAN = 20 000` is applied in `resolve()` at `sources.py:348` to the loader's
  *output*, i.e. to the post-cascade match list. It is **not** applied to the candidate pool
  the cascade scans — the `noun_instances` and `verb_runs` loops at `sources.py:256-293` are
  unbounded. So a project with more than 20 000 total instances-plus-runs pays the full
  O(rows × fields) string-comparison scan on **every** `query` widget resolution, and the
  cap only truncates the results *after* the expensive work is done. Pushdown would not have
  fixed this either — it is a pre-existing scaling exposure in the loader, not something the
  compiler was ever going to address — but it means "`query` stays as it is" is a worse
  status quo than the `MAX_SCAN` constant suggests.
- **`derive`/`where`/`sort`/`limit` still work for `query` widgets**, unchanged, in Python.
  Those four functions are already source-agnostic (`sources.py:353-356` take no source-type
  argument), so a pushdown layer for `noun` does not break them.

---

## 9. Reproducibility, compliance, and honest limits

### 9.1 Artifacts

| path | what |
|---|---|
| `spikes/T-1/proto/coverage_probe.py` | the 403-probe harness (throwaway; imports its oracle from `conformance.py`) |
| `spikes/T-1/proto/coverage_probe_results.json` | raw per-probe results |
| `spikes/T-1/analysis/coverage.md` | this document |

Scratch scripts that produced the counts, kept out of the repo (session scratchpad):
`inv1.py` (construct universe), `inv2.py`–`inv6.py` (C1–C4 bounds), `cover.py` (fixture
construct walk), `domain.py`/`domain2.py` (value-domain matrices), `nc.py` (negative
controls), `realwidget.py` (the real dashboard widget). Every number in this document came
from one of these or from a cited file:line — none was transcribed by hand.

### 9.2 Environment

PostgreSQL **16.14** in container `glp-strong-db`, scratch database `autosql_spike`, schema
`xpr` as already installed. `extra_float_digits` pinned to 1 for every probe run.
Python 3.12.3 from `GIMS-Project/.venv`, `sys.getrecursionlimit()` = 1000 (the default —
C3's threshold is a function of it, and a deployment that raises the limit moves the
threshold without removing the failure).

**Reproducibility:** two consecutive full probe runs produced **402 of 403 entries
byte-identical**, and identical verdicts on all 403. The single differing entry is
`now($.a)` with `context = {}` — the wall-clock probe of §6.2/R6, which is
nondeterministic by design. Nothing else in the run reads a clock.

### 9.3 Read-only compliance

- `GIMS-Project` HEAD `995cc59`, `gims-ledger` HEAD `7b7a049` — both unchanged.
  `core/dashboard/expr.py` still dated 2026-07-02.
- **Nothing was written to either GIMS tree.** All reads; the `_eval` helper wrapping in
  `domain.py` patches the module *in memory* within a throwaway process.
- The `dashboards` tables were opened with `sqlite3 "file:…?mode=ro"` — read-only URI,
  no write possible.
- **`compile.py` (mtime 11:23) and `runtime.sql` (11:20) were not touched** — both predate
  this seat's first artifact (11:52). Per the stop rules, C3, C4 and R3 are **recorded, not
  fixed**.
- All database work was `SELECT`-only against the spike's own `autosql_spike`; `glp_strong`
  was never opened.

### 9.4 What this document does not establish

- **It does not re-verify the 130/130.** That is the conformance seat's result, taken as
  given and used as the definition of "proven" in column 1.
- **403/403 is coverage of the *kind* axis, not proof of correctness.** One witness per
  operand-kind cell is one witness, not exhaustion. §5.2 lists the axes still open
  (collation, >17-digit numerics, date formats).
- **The `RecursionError` and `MemoryError` thresholds are specific to this machine's
  recursion limit and RAM.** The *existence* of the failure is general; the exact numbers
  are not.
- **The `n = 1` dashboard proves nothing about usage rates** and is labelled as such
  everywhere it appears.
- **No verdict is offered.** `decision_authority` is `recommend-and-wait`; §7.3 describes
  the shape the evidence takes against the GO bar, and stops there.
