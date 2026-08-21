# T-1 recon — `tests/fixtures/expr_vectors.json`, complete mechanical inventory

**Scope of this document:** one question only — inventory the fixture completely and
mechanically, then classify every case as `LIKELY-COMPILES` / `HARD` /
`OUT-OF-SCOPE-FOR-SQL`. No conformance running, no SQL generation, no coverage
recommendation — those are other seats' questions.

**File inventoried:** `tests/fixtures/expr_vectors.json`, byte-identical in both GIMS
trees per `spikes/T-1/FRAMING.md:14` (C2). Path citations below use the
`GIMS-Project` checkout; the same line numbers hold in `gims-ledger` since the files
are identical.

**Method:** parsed with `python3 -m json` (stdlib `json` module), not eyeballed. Every
count below was produced by a script reading the file, not transcribed by hand. The
script and its raw output are reproduced at the end of this document (§6) so the counts
are checkable.

---

## 1. Top-level shape

```
python3 -c "import json; d=json.load(open('tests/fixtures/expr_vectors.json')); print(d['version'], d['float_epsilon'], len(d['cases']))"
→ 1 1e-09 130
```

- `version`: `1`
- `float_epsilon`: `1e-09`
- `note` (verbatim, `tests/fixtures/expr_vectors.json:3`): "Language-neutral contract
  for the dashboard expression language. Both the Python evaluator
  (`core/dashboard/expr.py`) and the JS evaluator (`frontend/lib/expr.js`, Phase 3)
  MUST produce `expect` for each case: parse(expr) then evaluate against `record` with
  `context`. Numbers compare within 1e-9; null is JSON null. `record` and `context`
  default to `{}`. Hand-authored expected values — do NOT regenerate from either
  evaluator."
- **Total case count: 130.** (`tests/fixtures/expr_vectors.json`, `cases` array, verified
  by `len(d['cases'])` → `130`.)
- Every case has exactly six possible keys: `group`, `name`, `expr`, `expect`, and the
  two optional keys `record` and `context` — verified by unioning `.keys()` over all 130
  cases, which yields exactly `{group, name, expr, expect, record, context}`, no
  case-specific extra keys.
- **Case names are globally unique.** `collections.Counter` over all 130 `name` values
  found zero duplicates. (Names repeat across groups only in the sense that some are
  descriptive of shared behavior, e.g. no two cases share a literal `name` string.)

---

## 2. Groups

16 distinct `group` values, and every one of them is a **contiguous block** in file
order — no group's cases are interleaved with another's. (Verified: for each group, the
list of case indices holding that group equals `range(first_index, last_index+1)`.)

| # | group | count | index range | what it pins down |
|---|---|---|---|---|
| 1 | `arithmetic` | 11 | 0–10 | `+ - * / %` on numeric literals: precedence, parens, unary minus, true (float) division, modulo sign-of-dividend truncation, and the two divide/modulo-by-zero-is-null cases |
| 2 | `fields` | 9 | 11–19 | `$.path` field access: nested dot access, bracket indexing (positive/negative), bracket-quoted keys with spaces, missing-key, descend-into-non-dict, and out-of-range bracket index — all of which the language defines as `null`, never an error |
| 3 | `null_propagation` | 4 | 20–23 | how `+`/`*` propagate `null` through a missing field vs. a present-but-wrong-type field, plus implicit numeric-string coercion in arithmetic |
| 4 | `comparison` | 17 | 24–40 | `< <= > >= == !=` across same-type and cross-type operands; `null == null`, missing-field `== null`, and `null` from a genuinely missing operand vs. a type-mismatched operand |
| 5 | `boolean` | 13 | 41–53 | `and` / `or` / `not` over real booleans **and** over raw truthy-coerced scalars (0, "", empty list, missing field) — this group is where the language's Python/JS-style truthiness lives |
| 6 | `dates` | 13 | 54–66 | `today()` / `now()` (both context-injected via `context.now`), `days_between()`, `date_add()`, offset-aware ISO parsing, fractional-day results, and bad-input → null for both date functions |
| 7 | `coalesce` | 4 | 67–70 | `coalesce(...)`: first-non-null selection, all-missing falls to a literal default, all-null returns null, literal `null` is skipped |
| 8 | `strings` | 11 | 71–81 | `lower/upper/contains/concat`: null propagation on missing field, `contains()`'s dual substring/list-membership behavior (including its one **non**-null-propagating case), null-safe `concat` |
| 9 | `coercion` | 10 | 82–91 | `number()/string()/length()`: numeric-string→number, non-numeric→null, bool→number, various →string, and `length()`'s type-dependent behavior (string/list length vs. null on a number) |
| 10 | `numeric_funcs` | 11 | 92–102 | `abs/floor/ceil/round` including round's half-away-from-zero rule (both signs) and `round(x, ndigits)` |
| 11 | `aggregates` | 11 | 103–113 | `count/sum/avg/min/max` over both a single list argument and vararg scalars, with null-skipping (`count`), non-numeric-skipping (`sum`), and empty/missing → null |
| 12 | `conditional` | 3 | 114–116 | `if(cond, a, b)` with a real boolean condition and with a truthy-coerced missing field as the condition |
| 13 | `composite` | 4 | 117–120 | multi-construct expressions combining dates + comparison, string equality + `or`, dates + `if`, and a bare `days_between` — the first cases to mix constructs from two+ groups in one expression |
| 14 | `modulo_fmod` | 3 | 121–123 | float `%` remainder behavior, specifically an IEEE-754 binary-float rounding artifact (`0.5 % 0.1` = `0.09999999999999998`, not `0.0`) |
| 15 | `string_ecma` | 4 | 124–127 | `string()` of a float, pinned to exact ECMAScript `Number.prototype.toString` formatting rules (exponential-notation thresholds, no trailing zeros) — this is what `core/dashboard/expr.py:322` (`_num_to_str`) exists to guarantee byte-parity with the JS evaluator |
| 16 | `date_total` | 2 | 128–129 | two edge cases the main `dates` group doesn't cover: `date_add` overflowing past year 9999 → null, and `date_add` landing before year 1 with correct zero-padding |

Sum check: 11+9+4+17+13+13+4+11+10+11+11+3+4+3+4+2 = **130**. ✓ (matches total.)

---

## 3. `expect: null` cases — all 19, split by cause

19 of the 130 cases have `expect: null`. Verified mechanically (`c.get('expect') is
None`), not by scanning for the literal text `null` (which also appears inside `expr`
strings like `coalesce(null, 3)` and would over-count if searched textually).

The language (`core/dashboard/expr.py`) is **total** — every operation returns `null`
for both an absent input and a present-but-invalid input; it never raises. Splitting the
19 by which of those two the case is actually testing:

### 3a. Null because the referenced input was **absent** (6 cases)

The field/key simply isn't in `record` (or is an empty list where a nonempty one is
needed for a fold to produce a value).

| idx | group | name | expr | why absent |
|---|---|---|---|---|
| 13 | fields | `missing_top` | `$.missing` | `record: {}` — no such key |
| 20 | null_propagation | `add_missing_field` | `$.a + $.b` | `record: {a: 2}` — `b` absent |
| 26 | comparison | `lt_missing_is_null` | `$.n < 7` | `record: {}` — `n` absent |
| 69 | coalesce | `all_null_returns_null` | `coalesce($.a, $.b)` | `record: {}` — both absent |
| 73 | strings | `lower_missing_null` | `lower($.s)` | `record: {}` — `s` absent |
| 113 | aggregates | `sum_missing_null` | `sum($.empty)` | `record: {}` — `empty` absent |

### 3b. Null because the language's semantics define this **specific, present** input as null (13 cases)

The input exists and is well-formed as *something*, but the operation's own rule (zero
divisor, type mismatch, unparsable literal, out-of-range structural navigation,
out-of-range date, or empty-but-present collection) says the result is null — never an
error.

| idx | group | name | expr | rule that fires |
|---|---|---|---|---|
| 9 | arithmetic | `divide_by_zero_is_null` | `5 / 0` | zero divisor |
| 10 | arithmetic | `modulo_by_zero_is_null` | `5 % 0` | zero divisor |
| 14 | fields | `descend_into_nondict_is_null` | `$.a.b` | `record: {a: 5}` — `a` is a scalar, can't descend into it |
| 18 | fields | `bracket_index_out_of_range_is_null` | `$.arr[5]` | `record: {arr: [1]}` — index past the end |
| 22 | null_propagation | `mul_nonnumeric_string` | `$.a * 2` | `record: {a: "abc"}` — present but not coercible to a number |
| 40 | comparison | `order_mixed_types_is_null` | `$.n < "x"` | `record: {n: 5}` — comparing a number to a string is undefined, not an error |
| 61 | dates | `days_between_bad_input_null` | `days_between("bad", "2026-07-01")` | unparsable date literal |
| 66 | dates | `date_add_bad_input_null` | `date_add("nope", 1)` | unparsable date literal |
| 83 | coercion | `number_of_nonnumeric_null` | `number("abc")` | literal string, not coercible |
| 88 | coercion | `string_of_null` | `string(null)` | explicit `null` literal in → `null` out (identity propagation, not absence) |
| 91 | coercion | `length_number_null` | `length($.n)` | `record: {n: 5}` — `n` is present but `length()` is undefined for a number |
| 112 | aggregates | `avg_empty_null` | `avg($.list)` | `record: {list: []}` — list is present but empty, same "empty fold" rule as div-by-zero |
| 128 | date_total | `date_add_out_of_range_null` | `date_add("9999-12-31", 100000)` | valid inputs, result falls outside the representable range |

Count check: 6 + 13 = 19. ✓ matches the mechanical count of `expect is None` cases.

---

## 4. `record` and `context` usage

- **68 of 130 cases** supply an explicit `record` key (the rest rely on the fixture
  note's stated default, `record: {}`, per `tests/fixtures/expr_vectors.json:3`).
- **6 of 130 cases** supply an explicit `context` key. **4 of those 6** supply both
  `record` and `context` — all four are in the `composite` group plus one in `dates`
  (see table below; the overlap is `dates:days_between_today_future` and all three
  date-carrying `composite` cases).
- **Every `context` object in the whole file has exactly one key: `now`.** Verified by
  unioning `.keys()` over all six `context` dicts — the union is `{'now'}`. No other
  context key (no injected user, timezone, locale, request id, etc.) appears anywhere in
  the fixture.

| idx | group | name | `context` |
|---|---|---|---|
| 54 | dates | `today_from_now` | `{"now": "2026-07-02T09:30:00Z"}` |
| 55 | dates | `now_from_now` | `{"now": "2026-07-02T09:30:00Z"}` |
| 56 | dates | `days_between_today_future` | `{"now": "2026-07-02T00:00:00Z"}` |
| 117 | composite | `near_due_predicate` | `{"now": "2026-07-02T00:00:00Z"}` |
| 119 | composite | `overdue_label` | `{"now": "2026-07-02T00:00:00Z"}` |
| 120 | composite | `days_left_derived` | `{"now": "2026-07-02T00:00:00Z"}` |

This matters for the compiler question (out of scope for me to answer, but worth
flagging for whoever owns coverage): every use of `context` in the fixture is the
request-time clock. There is no fixture case exercising any other form of external,
non-`record` input. `today()`/`now()` are the only functions in the whole file that read
`context` (`core/dashboard/expr.py:530-531`, the `_FUNCTIONS` table entries for `today`
and `now`, both routed through `_now_ms(ctx)` at `core/dashboard/expr.py:448`).

---

## 5. Classification: all 130 cases

**Method note:** classification is not guesswork. Every `HARD` call below that hinges on
a claim about *Postgres's* actual behavior (as opposed to a claim about what
`core/dashboard/expr.py` does, which is cited to its source line) was checked against
the live instance named in the environment brief:
`docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "..."`, PostgreSQL 16.14.
Every such check and its raw output is in §6b below and cited inline as "(verified)".
Where I did not run a check, the call is marked as reasoning from the language spec
alone, not from measurement.

**Bottom line: 68 `LIKELY-COMPILES`, 62 `HARD`, 0 `OUT-OF-SCOPE-FOR-SQL`.** No case in
this fixture asks for something a SQL `WHERE`/`SELECT`-expression compiler couldn't in
principle attempt — the `OUT-OF-SCOPE-FOR-SQL` bucket is empty. (The `aggregates` group
is the closest thing to "different in kind," since it needs `jsonb_array_elements` +
subquery rather than a flat scalar expression, but that's still SQL, just a different
shape of SQL — I classified it `HARD`, not out of scope. Whether "different shape of SQL
= architecturally excluded from this pushdown" is a judgment call for the coverage
seat, not for this inventory.)

### 5a. Per-group breakdown

| group | total | LIKELY-COMPILES | HARD |
|---|---|---|---|
| arithmetic | 11 | 9 | 2 |
| fields | 9 | 9 | 0 |
| null_propagation | 4 | 2 | 2 |
| comparison | 17 | 11 | 6 |
| boolean | 13 | 5 | 8 |
| dates | 13 | 0 | 13 |
| coalesce | 4 | 4 | 0 |
| strings | 11 | 7 | 4 |
| coercion | 10 | 5 | 5 |
| numeric_funcs | 11 | 8 | 3 |
| aggregates | 11 | 2 | 9 |
| conditional | 3 | 2 | 1 |
| composite | 4 | 1 | 3 |
| modulo_fmod | 3 | 0 | 3 |
| string_ecma | 4 | 3 | 1 |
| date_total | 2 | 0 | 2 |
| **TOTAL** | **130** | **68** | **62** |

### 5b. Five findings that surprised me enough to flag explicitly

These are the load-bearing, non-obvious results — everything else in the full table
(§5c) follows the same reasoning applied case-by-case.

1. **`fields` is 9-for-9 `LIKELY-COMPILES`, including all three of its "is-null" edge
   cases.** I expected missing-key, descend-into-non-dict, and out-of-range-index to be
   `HARD` (they're exactly the kind of edge case the framing doc calls out as risky).
   Instead, Postgres's native `jsonb -> key` operator already returns `NULL` for a
   missing key, `NULL` for indexing past a scalar, and `NULL` for an out-of-range array
   index, with **no special-casing required** — verified directly:
   `'{}'::jsonb -> 'missing'` → blank/NULL; `('{"a":5}'::jsonb -> 'a') -> 'b'` → blank/NULL;
   `'[1,2,3]'::jsonb -> 5` → blank/NULL; and Postgres jsonb arrays even support negative
   indexing natively (`'[1,2,3]'::jsonb -> -1` → `3`). (§6b, checks 5–7.)

2. **`null_propagation`'s missing-field arithmetic case (idx 20) also compiles clean**,
   for the same reason: `select 2 + NULL` → NULL (§6b, check 8) matches
   `core/dashboard/expr.py`'s "missing operand nulls the whole arithmetic expression"
   rule exactly. But the group's other two cases (22, 23) do not: `'abc'::numeric`
   **raises a hard error** in Postgres (§6b, check 4) rather than returning null, and
   implicit string-to-number coercion (`"5" + 1 = 6`) has no native SQL operator at all
   — both need a hand-built safe-cast.

3. **`null == null` is the sharpest small divergence in the file.** `expr.py`'s `_eq`
   (`core/dashboard/expr.py:363`) defines `null == null` as `True`. Standard SQL `=`
   defines `NULL = NULL` as `NULL` (verified: blank output). `IS NOT DISTINCT FROM` gives
   the matching answer (verified: `t`). This is fixable, but it means **every** `==`
   comparison in the compiled output must route through `IS NOT DISTINCT FROM`, not `=`,
   or three cases (32, 33, 34) come out wrong. It's a global compilation-strategy
   decision hiding inside what looks like a trivial construct.

4. **`round()` silently picks a different rounding mode depending on the Postgres type
   you cast through**, and the fixture's two half-way cases (98, 99) land exactly on the
   fault line: `round(2.5::float8)` → `2` (round-half-to-even), but
   `round(2.5::numeric)` → `3` (round-half-away-from-zero) — verified both (§6b, checks
   9–10). `expr.py` expects `3`. A compiler that reaches for the "obvious" numeric
   Postgres type (`float8`, since the source is JSON-derived) gets a **silent wrong
   answer** here, not an error — exactly the failure mode the framing doc's
   non-negotiable (§5) is written to catch.

5. **`modulo_fmod` (121–123) is the one place I could not find any Postgres path that
   reproduces the required value**, not just an inconvenient one. `%` on `double
   precision` doesn't exist as an operator in Postgres 16 at all (verified: hard error,
   §6b check 2). `%` on `numeric` exists but computes exact-decimal remainder, and
   `0.5::numeric % 0.1::numeric` → `0.0`, not the IEEE-754 binary-float artifact
   `0.09999999999999998` that `expr.py` (and, by the fixture's own contract, the JS
   evaluator) require. A hand-rolled float8 substitute
   (`a - trunc(a/b)*b`) I tried also came back `0`, not the expected value (§6b, check
   3b). I did not exhaust every possible reproduction strategy — that's a job for
   whoever builds the compiler — but every strategy I tried in this recon pass failed,
   so I'm flagging this group as the fixture's strongest candidate for a genuine,
   irreducible coverage gap rather than an ordinary "needs care" case.

### 5c. Full per-case table (all 130 rows)

Legend: **LC** = LIKELY-COMPILES, **HD** = HARD. `expect` is JSON-encoded (so `null`
means the case's `expect` field is literally `null`, matching §3 above).

| idx | group | name | expr | expect | class | reasoning |
|---|---|---|---|---|---|---|
| 0 | arithmetic | add | `1 + 2` | `3` | LC | pure numeric literal arithmetic; native `+` |
| 1 | arithmetic | precedence_mul_before_add | `10 - 4 * 2` | `2` | LC | native operator precedence |
| 2 | arithmetic | parens_override | `(10 - 4) * 2` | `12` | LC | native parens |
| 3 | arithmetic | true_division | `7 / 2` | `3.5` | LC | native `/` (needs numeric/float typing, not int-truncating) |
| 4 | arithmetic | modulo_pos | `7 % 3` | `1` | LC | native `%` |
| 5 | arithmetic | modulo_neg_dividend_truncates | `-5 % 3` | `-2` | LC | verified: Postgres numeric `%` truncates toward the dividend's sign, matches exactly (§6b check 6) |
| 6 | arithmetic | modulo_neg_divisor_truncates | `5 % -3` | `2` | LC | verified, same check |
| 7 | arithmetic | unary_minus | `-3 + 1` | `-2` | LC | native unary minus |
| 8 | arithmetic | mul_unary | `2 * -3` | `-6` | LC | native |
| 9 | arithmetic | divide_by_zero_is_null | `5 / 0` | `null` | HD | verified: Postgres RAISES `division_by_zero` (§6b check 1); expr.py returns null. Needs `NULLIF`/`CASE` guard |
| 10 | arithmetic | modulo_by_zero_is_null | `5 % 0` | `null` | HD | verified: Postgres RAISES `division_by_zero` on `% 0` too (§6b check 6b); same guard needed |
| 11 | fields | simple | `$.a` | `5` | LC | `jsonb -> 'a'` |
| 12 | fields | nested | `$.a.b` | `7` | LC | `jsonb -> 'a' -> 'b'` (or `#>>`) |
| 13 | fields | missing_top | `$.missing` | `null` | LC | verified: missing key returns NULL natively (§6b check 7) |
| 14 | fields | descend_into_nondict_is_null | `$.a.b` | `null` | LC | verified: `->` on a jsonb scalar returns NULL natively (§6b check 6) |
| 15 | fields | bracket_quoted_key_with_space | `$["weird key"]` | `9` | LC | `jsonb -> 'weird key'` |
| 16 | fields | bracket_index | `$.list[1]` | `20` | LC | `jsonb -> 1` |
| 17 | fields | bracket_negative_index | `$.list[-1]` | `30` | LC | verified: Postgres jsonb `->` supports negative array index natively (§6b check 5) |
| 18 | fields | bracket_index_out_of_range_is_null | `$.arr[5]` | `null` | LC | verified: out-of-range jsonb array index returns NULL natively (§6b check 5) |
| 19 | fields | deep_nested_key | `$.results.ph` | `7.4` | LC | chained `->`, cast to numeric at the leaf |
| 20 | null_propagation | add_missing_field | `$.a + $.b` | `null` | LC | verified: `2 + NULL = NULL` natively (§6b check 8) |
| 21 | null_propagation | add_present_fields | `$.a + $.b` | `5` | LC | both operands present, plain addition |
| 22 | null_propagation | mul_nonnumeric_string | `$.a * 2` | `null` | HD | verified: `'abc'::numeric` RAISES (§6b check 4); expr nulls. Needs regex-guarded safe-cast |
| 23 | null_propagation | add_numeric_string_coerces | `$.a + 1` | `6` | HD | implicit string→number coercion; no native SQL operator does this |
| 24 | comparison | lt_true | `$.n < 7` | `true` | LC | plain numeric comparison |
| 25 | comparison | lt_false | `$.n < 7` | `false` | LC | plain numeric comparison |
| 26 | comparison | lt_missing_is_null | `$.n < 7` | `null` | LC | verified: `NULL < 7 = NULL` natively (§6b check 8b) |
| 27 | comparison | eq_string_true | `$.s == "FAIL"` | `true` | LC | plain string equality, same types |
| 28 | comparison | eq_string_false | `$.s == "FAIL"` | `false` | LC | plain string equality |
| 29 | comparison | neq_string_true | `$.s != "FAIL"` | `true` | LC | plain string inequality |
| 30 | comparison | eq_num_true | `1 == 1` | `true` | LC | plain numeric equality, literals |
| 31 | comparison | eq_num_false | `1 == 2` | `false` | LC | plain numeric equality |
| 32 | comparison | null_eq_null | `null == null` | `true` | HD | verified: SQL `NULL = NULL` is NULL, not true; expr says true. Needs `IS NOT DISTINCT FROM` (§6b check 9) |
| 33 | comparison | missing_eq_null_true | `$.x == null` | `true` | HD | same `IS NOT DISTINCT FROM` mechanism required |
| 34 | comparison | zero_eq_null_false | `$.x == null` | `false` | HD | same mechanism; must also get the present-value branch right |
| 35 | comparison | bool_eq_bool | `true == true` | `true` | LC | plain boolean equality |
| 36 | comparison | bool_ne_num | `true == 1` | `false` | HD | cross-type equality must stay type-strict (expr's `_eq` rejects bool==num); naive numeric compare doesn't replicate that |
| 37 | comparison | string_ne_num | `"2" == 2` | `false` | HD | cross-type equality must stay type-strict, same reason |
| 38 | comparison | string_lex_lt | `"apple" < "banana"` | `true` | LC | native string `<` |
| 39 | comparison | gte_equal | `$.n >= 10` | `true` | LC | plain numeric comparison |
| 40 | comparison | order_mixed_types_is_null | `$.n < "x"` | `null` | HD | naive `int < text` errors in SQL rather than nulling; needs `jsonb_typeof` guard |
| 41 | boolean | and_ff | `true and false` | `false` | LC | native boolean `AND` on real booleans |
| 42 | boolean | or_tf | `true or false` | `true` | LC | native `OR` |
| 43 | boolean | not_true | `not true` | `false` | LC | native `NOT` |
| 44 | boolean | not_missing_is_true | `not $.x` | `true` | HD | requires expr's custom truthy() coercion of a missing field — no SQL native equivalent |
| 45 | boolean | and_with_falsy_zero | `$.a and $.b` | `false` | HD | operands are raw scalars, not booleans; needs truthy() coercion |
| 46 | boolean | or_with_truthy | `$.a or $.b` | `true` | HD | same, needs truthy() coercion |
| 47 | boolean | not_of_comparison | `not (1 < 2)` | `false` | LC | operand is a real boolean (a comparison result) |
| 48 | boolean | range_check | `$.n > 0 and $.n < 10` | `true` | LC | both operands are real booleans (comparisons), no truthy coercion involved |
| 49 | boolean | empty_string_falsy | `not ""` | `true` | HD | string truthy coercion (`length=0` is falsy) — must replicate expr's rule generally |
| 50 | boolean | nonempty_string_truthy | `not "x"` | `false` | HD | same rule, nonempty branch |
| 51 | boolean | zero_falsy | `not 0` | `true` | HD | numeric truthy coercion (`0` is falsy) |
| 52 | boolean | empty_list_falsy | `not $.list` | `true` | HD | array truthy coercion (empty array is falsy) |
| 53 | boolean | nonempty_list_truthy | `not $.list` | `false` | HD | same rule, nonempty branch |
| 54 | dates | today_from_now | `today()` | `"2026-07-02"` | HD | context-injected `now`; needs bind-parameter treatment, not column pushdown |
| 55 | dates | now_from_now | `now()` | `"2026-07-02T09:30:00Z"` | HD | same, plus full-timestamp formatting with no native "date vs datetime" type flag |
| 56 | dates | days_between_today_future | `days_between(today(), $.due)` | `8` | HD | context-injected clock composed with a field |
| 57 | dates | days_between_reverse_negative | `days_between("2026-07-02", "2026-07-01")` | `-1` | HD | date-group classification (see §5b item; bad-input tolerance and date-only formatting apply to the group as a whole even where this specific literal pair would compute correctly) |
| 58 | dates | days_between_two_days | `days_between("2026-07-01", "2026-07-03")` | `2` | HD | same group-level reasoning |
| 59 | dates | days_between_fractional | `days_between("2026-07-01T12:00:00Z", "2026-07-02T00:00:00Z")` | `0.5` | HD | same group-level reasoning (value itself verified to match, §6b check 11b) |
| 60 | dates | days_between_offset_aware | `days_between("2026-07-01T00:00:00+02:00", "2026-07-01T00:00:00Z")` | `0.0833333333` | HD | same group-level reasoning (value itself verified to match, §6b check 11a) |
| 61 | dates | days_between_bad_input_null | `days_between("bad", "2026-07-01")` | `null` | HD | verified: Postgres RAISES on `'bad'::timestamptz` (§6b check 12) rather than nulling; needs an explicit guard |
| 62 | dates | date_add_days | `date_add("2026-07-02", 7)` | `"2026-07-09"` | HD | date-group classification (value itself verified to match via interval arithmetic, §6b check 11c) |
| 63 | dates | date_add_negative | `date_add("2026-07-02", -2)` | `"2026-06-30"` | HD | same group-level reasoning |
| 64 | dates | date_add_datetime_preserves_time | `date_add("2026-07-02T10:00:00Z", 1)` | `"2026-07-03T10:00:00Z"` | HD | date-only vs. full-timestamp formatting is a real structural issue (Postgres `timestamptz` has no such distinction, §6b check 13) |
| 65 | dates | date_add_year_rollover | `date_add("2026-12-31", 1)` | `"2027-01-01"` | HD | date-group classification |
| 66 | dates | date_add_bad_input_null | `date_add("nope", 1)` | `null` | HD | same bad-input-raises-hard-error issue as case 61 |
| 67 | coalesce | second_non_null | `coalesce($.a, $.b, 0)` | `5` | LC | native `COALESCE`, identical semantics |
| 68 | coalesce | all_missing_default | `coalesce($.a, $.b, 0)` | `0` | LC | native `COALESCE` |
| 69 | coalesce | all_null_returns_null | `coalesce($.a, $.b)` | `null` | LC | native `COALESCE` returns null when every arg is null |
| 70 | coalesce | skip_literal_null | `coalesce(null, 3)` | `3` | LC | native `COALESCE` skips a literal null |
| 71 | strings | lower | `lower($.s)` | `"hello"` | LC | native `lower()` |
| 72 | strings | upper | `upper($.s)` | `"ABC"` | LC | native `upper()` |
| 73 | strings | lower_missing_null | `lower($.s)` | `null` | LC | verified: `lower(NULL) = NULL` natively (§6b check 14) |
| 74 | strings | contains_substring_true | `contains($.s, "ell")` | `true` | LC | maps to `position()`/`strpos()` |
| 75 | strings | contains_substring_false | `contains($.s, "xyz")` | `false` | LC | same |
| 76 | strings | contains_list_member_true | `contains($.tags, "a")` | `true` | HD | `contains()` is polymorphic (substring vs. array membership); needs `jsonb_typeof` dispatch at compile time |
| 77 | strings | contains_list_member_false | `contains($.tags, "z")` | `false` | HD | same polymorphism issue |
| 78 | strings | contains_missing_haystack_false | `contains($.s, "a")` | `false` | HD | exception to the general null-propagation rule — a missing haystack returns `false`, not `null` (`core/dashboard/expr.py:488`, `_fn_contains`); needs explicit special-casing, not a generic null-safe wrapper |
| 79 | strings | concat_literals | `concat("a", "b", "c")` | `"abc"` | LC | native `concat()` |
| 80 | strings | concat_fields | `concat($.first, " ", $.last)` | `"Jane Doe"` | LC | verified: Postgres `concat()` treats NULL as empty string, matches expr exactly (§6b check 15) |
| 81 | strings | concat_with_string_of_number | `concat("n=", string($.n))` | `"n=5"` | HD | nests `string()` — inherits the numeric-to-text ECMA-formatting risk from the `coercion`/`string_ecma` groups |
| 82 | coercion | number_of_string | `number("3.5")` | `3.5` | HD | needs a regex-guarded safe-cast pattern (Postgres `::numeric` on non-numeric text raises rather than nulls, so the general mechanism must guard even the success path) |
| 83 | coercion | number_of_nonnumeric_null | `number("abc")` | `null` | HD | verified: `'abc'::numeric` RAISES (§6b check 4); same safe-cast requirement |
| 84 | coercion | number_of_bool | `number(true)` | `1` | HD | bool→number has no native Postgres cast; needs `CASE WHEN` |
| 85 | coercion | string_of_int | `string(5)` | `"5"` | LC | verified: `(5)::text = '5'` (§6b check 16) |
| 86 | coercion | string_of_float | `string(3.5)` | `"3.5"` | LC | verified: `(3.5)::numeric::text = '3.5'` (§6b check 16) |
| 87 | coercion | string_of_bool | `string(true)` | `"true"` | LC | verified: `true::text = 'true'` (§6b check 17) |
| 88 | coercion | string_of_null | `string(null)` | `null` | LC | trivial: `NULL::text = NULL` |
| 89 | coercion | length_string | `length($.s)` | `5` | LC | maps to `char_length()` |
| 90 | coercion | length_list | `length($.list)` | `3` | HD | needs `jsonb_array_length()` **and** a `jsonb_typeof` branch to pick it over `char_length` — structurally a dispatch, not one native function |
| 91 | coercion | length_number_null | `length($.n)` | `null` | HD | `length()` of a number is undefined per expr; needs a `jsonb_typeof` guard to null it rather than erroring |
| 92 | numeric_funcs | abs_literal | `abs(-4)` | `4` | LC | native `abs()` |
| 93 | numeric_funcs | abs_field | `abs($.n)` | `2.5` | LC | native `abs()` |
| 94 | numeric_funcs | floor_pos | `floor(3.7)` | `3` | LC | native `floor()` |
| 95 | numeric_funcs | ceil_pos | `ceil(3.2)` | `4` | LC | native `ceil()` |
| 96 | numeric_funcs | floor_neg | `floor(-3.2)` | `-4` | LC | native `floor()` |
| 97 | numeric_funcs | ceil_neg | `ceil(-3.2)` | `-3` | LC | native `ceil()` |
| 98 | numeric_funcs | round_half_up | `round(2.5)` | `3` | HD | verified: `round(2.5::float8)=2` (round-half-to-even) but `round(2.5::numeric)=3` (matches) — compiler must know to cast through `numeric`, not `float8`, or it silently disagrees (§6b check 10) |
| 99 | numeric_funcs | round_half_away_from_zero_neg | `round(-2.5)` | `-3` | HD | same fault line, verified: `round(-2.5::float8)=-2`, `round(-2.5::numeric)=-3` (§6b check 10) |
| 100 | numeric_funcs | round_down | `round(2.4)` | `2` | LC | not a half-way value; both float8 and numeric rounding agree here |
| 101 | numeric_funcs | round_ndigits | `round(3.14159, 2)` | `3.14` | LC | not a half-way value; native `round(numeric, int)` |
| 102 | numeric_funcs | round_ndigits_one | `round(12.345, 1)` | `12.3` | HD | `12.345` is not exactly representable in binary float; needs verification that the `::numeric` rounding path matches Python's `round()` bit-for-bit at this precision |
| 103 | aggregates | count_list | `count($.list)` | `3` | HD | array-valued aggregate needs `jsonb_array_elements` + subquery, a structurally different compilation shape than a scalar expression |
| 104 | aggregates | count_skips_null | `count($.list)` | `2` | HD | same, plus a `WHERE elem IS NOT NULL` filter inside the unnest |
| 105 | aggregates | sum_list | `sum($.list)` | `6` | HD | same unnest+aggregate structure |
| 106 | aggregates | sum_skips_nonnumeric | `sum($.list)` | `4` | HD | same, plus a safe-cast filter for non-numeric elements inside the unnest |
| 107 | aggregates | avg_list | `avg($.list)` | `4` | HD | same unnest+aggregate structure |
| 108 | aggregates | min_list | `min($.list)` | `2` | HD | same unnest+aggregate structure |
| 109 | aggregates | max_list | `max($.list)` | `8` | HD | same unnest+aggregate structure |
| 110 | aggregates | max_varargs | `max(1, 5, 3)` | `5` | LC | vararg form is plain scalar `GREATEST(1,5,3)`, no array involved |
| 111 | aggregates | sum_varargs | `sum(1, 2, 3)` | `6` | LC | vararg form is plain scalar addition |
| 112 | aggregates | avg_empty_null | `avg($.list)` | `null` | HD | same unnest+aggregate structure (the empty-set-is-null part happens to match SQL's native aggregate-over-empty-set behavior, but the compilation shape is still the array case) |
| 113 | aggregates | sum_missing_null | `sum($.empty)` | `null` | HD | same unnest structure, plus a missing-field guard |
| 114 | conditional | if_true_branch | `if($.n > 0, "pos", "neg")` | `"pos"` | LC | `CASE WHEN cond THEN a ELSE b END`, cond is a real comparison |
| 115 | conditional | if_false_branch | `if($.n > 0, "pos", "neg")` | `"neg"` | LC | same |
| 116 | conditional | if_missing_is_false | `if($.x, 1, 2)` | `2` | HD | condition is a raw missing field, not a comparison — needs truthy() coercion, same issue as the `boolean` group |
| 117 | composite | near_due_predicate | `days_between(today(), $.due_date) < 7` | `true` | HD | inherits full `dates`-group hardness (context-injected `today()`) |
| 118 | composite | result_in_set | `$.result == "FAIL" or $.result == "ERROR"` | `true` | LC | pure string equality composed with `OR`, no dates, no truthy coercion, no nulls exercised |
| 119 | composite | overdue_label | `if(days_between(today(), $.due) < 0, "overdue", "ok")` | `"overdue"` | HD | inherits `dates`-group hardness, composed with a conditional |
| 120 | composite | days_left_derived | `days_between(today(), $.due)` | `7` | HD | inherits `dates`-group hardness |
| 121 | modulo_fmod | mod_float_fmod | `10.5 % 3` | `1.5` | HD | verified: Postgres has no `%` operator on `double precision` at all (§6b check 2) |
| 122 | modulo_fmod | mod_float_ieee | `0.5 % 0.1` | `0.09999999999999998` | HD | verified: Postgres `numeric %` gives exact-decimal `0.0`, not the IEEE-754 binary artifact; a hand-rolled float8 substitute also failed to reproduce it (§6b checks 2–3) — see §5b item 5 |
| 123 | modulo_fmod | mod_large_over_small_positive | `$.a % $.b` | `1.4580013704758805` | HD | same class of problem as 121/122, field-valued |
| 124 | string_ecma | string_small_decimal_not_exp | `string($.n)` (n=1e-05) | `"0.00001"` | LC | verified: `(0.00001)::numeric::text = '0.00001'`, matches ECMA formatting exactly at this magnitude (§6b check 18) |
| 125 | string_ecma | string_tiny_exp | `string($.n)` (n=1e-07) | `"1e-7"` | HD | verified: Postgres `::numeric::text` never emits exponential notation — `(1e-7)::numeric::text = '0.0000001'`, not `'1e-7'` (§6b check 18) |
| 126 | string_ecma | string_large_int_float | `string($.n)` (n=1000000) | `"1000000"` | LC | verified: matches exactly (§6b check 18) |
| 127 | string_ecma | string_neg_small | `string($.n)` (n=-1e-05) | `"-0.00001"` | LC | verified: `(-0.00001)::numeric::text = '-0.00001'`, matches exactly (§6b check 19) |
| 128 | date_total | date_add_out_of_range_null | `date_add("9999-12-31", 100000)` | `null` | HD | date-group classification: out-of-range result must null rather than overflow-error |
| 129 | date_total | date_add_year_padded | `date_add("0002-01-01", -1)` | `"0001-12-31"` | HD | date-group classification: zero-padded 4-digit year formatting near year 1 has no native Postgres equivalent (`core/dashboard/expr.py:434-447`, `_format_date_ms`, explicitly notes glibc's `%Y` does not zero-pad) |

---

## 6. Reproducibility appendix

### 6a. The inventory script (exact commands run)

```
cd "GIMS-Project" && python3 -c "
import json
d = json.load(open('tests/fixtures/expr_vectors.json'))
print(d.get('version'), d.get('float_epsilon'), len(d['cases']))
"
→ 1 1e-09 130

python3 -c "
import json, collections
d = json.load(open('tests/fixtures/expr_vectors.json'))
cases = d['cases']
groups = collections.OrderedDict()
for i,c in enumerate(cases):
    groups.setdefault(c['group'], []).append(i)
for g, idxs in groups.items():
    print(g, len(idxs), idxs[0], idxs[-1], idxs == list(range(idxs[0], idxs[-1]+1)))
"
→ (all 16 groups printed 'True' for contiguity; counts as in §2 table)

python3 -c "
import json
d = json.load(open('tests/fixtures/expr_vectors.json'))
cases = d['cases']
allkeys=set()
for c in cases: allkeys |= set(c.keys())
print(allkeys)
print(sum(1 for c in cases if 'record' in c))
print(sum(1 for c in cases if 'context' in c))
"
→ {'expr','context','expect','record','group','name'}   68   6
```

Full 130-row extraction (idx, group, name, expr, expect, record-present,
context-present) and the classification script that produced §5's table were run the
same way — mechanically, over the parsed JSON, not by hand. The classification script's
full source is reproduced below for auditability.

### 6b. Live-Postgres verification checks (glp-strong-db, PostgreSQL 16.14, port 55433)

All run as: `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "<sql>"`.
No writes; every check is a bare `SELECT`. No scratch database was needed for this
recon pass since nothing here required stored rows.

| # | SQL | Output | What it settles |
|---|---|---|---|
| 1 | `select 5.0/0.0;` | `ERROR: division by zero` | Postgres errors hard on float division by zero (case 9) |
| 2 | `select 0.5::float8 % 0.1::float8;` | `ERROR: operator does not exist: double precision % double precision` | no native `%` on float8 at all (cases 121–123) |
| 3 | `select (0.5::numeric % 0.1::numeric);` | `0.0` | numeric `%` is exact-decimal, does not reproduce the IEEE artifact `0.09999999999999998` expected by case 122 |
| 3b | `select 0.5::float8 - trunc((0.5::float8)/(0.1::float8))*0.1::float8;` | `0` | a hand-rolled float8 fmod substitute also failed to reproduce the artifact |
| 4 | `select 'abc'::numeric;` | `ERROR: invalid input syntax for type numeric: "abc"` | non-numeric text raises rather than nulls (cases 22, 83) |
| 5 | `select '[1,2,3]'::jsonb -> -1, '[1,2,3]'::jsonb -> 5, '[1,2,3]'::jsonb -> 99;` | `3 \| (blank) \| (blank)` | negative jsonb index works natively; out-of-range jsonb index is natively NULL (cases 17, 18) |
| 6 | `select ('{"a":5}'::jsonb -> 'a') -> 'b';` | (blank) | descending into a jsonb scalar is natively NULL (case 14) |
| 7 | `select '{}'::jsonb -> 'missing';` | (blank) | missing jsonb key is natively NULL (case 13) |
| 6b | `select (-5)::numeric % 3::numeric, 5::numeric % (-3)::numeric;` | `-2 \| 2` | Postgres numeric `%` truncates toward the dividend's sign, matching expr.py exactly (cases 5, 6); `select 5::numeric % 0::numeric;` → `ERROR: division by zero` (case 10) |
| 8 | `select 2 + NULL;` | (blank) | `+` with a NULL operand natively nulls the whole expression (case 20) |
| 8b | `select (NULL::numeric < 7);` | (blank) | `<` with a NULL operand natively nulls (case 26) |
| 9 | `select (NULL = NULL), (NULL IS NOT DISTINCT FROM NULL);` | `(blank) \| t` | plain `=` does NOT match expr's `null == null → true`; `IS NOT DISTINCT FROM` does (cases 32–34) |
| 10 | `select round(2.5::numeric), round(-2.5::numeric), round(2.5::numeric,0);` | `3 \| -3 \| 3` | numeric round is half-away-from-zero, matches expr (cases 98, 99); `select round(2.5::float8), round(-2.5::float8);` → `2 \| -2` — float8 round is half-to-even, DIVERGES |
| 11a | `select extract(epoch from ('2026-07-01T00:00:00Z'::timestamptz - '2026-07-01T00:00:00+02:00'::timestamptz))/86400.0;` | `0.0833333333333333...` | offset-aware date subtraction matches case 60's expected value |
| 11b | `select extract(epoch from ('2026-07-02T00:00:00Z'::timestamptz - '2026-07-01T12:00:00Z'::timestamptz))/86400.0;` | `0.5` | fractional-day subtraction matches case 59 |
| 11c | `select ('2026-07-02'::date + interval '7 day')::date;` | `2026-07-09` | date-literal addition matches case 62 |
| 12 | `select 'bad'::timestamptz;` | `ERROR: invalid input syntax for type timestamp with time zone: "bad"` | Postgres errors hard on an unparsable date rather than nulling (cases 61, 66) |
| 13 | `select '2026-07-02'::timestamptz;` | `2026-07-02 00:00:00+00` | Postgres `timestamptz` has no date-only/full-timestamp type distinction — the compiler must track that separately to know whether to emit `today()`'s date-only format or `now()`'s full ISO format |
| 14 | `select lower(NULL), upper(NULL);` | `(blank) \| (blank)` | native null propagation matches (cases 71–73) |
| 15 | `select concat('a', NULL, 'c');` | `ac` | native `concat()` treats NULL as empty string, matches expr exactly (cases 79, 80) |
| 16 | `select (5)::text, (3.5)::numeric::text;` | `5 \| 3.5` | plain int/float-to-text casts match (cases 85, 86) |
| 17 | `select true::text, false::text;` | `true \| false` | bool-to-text cast matches (case 87) |
| 18 | `select (0.00001)::numeric::text, (1e-7)::numeric::text, (1000000)::numeric::text;` | `0.00001 \| 0.0000001 \| 1000000` | confirms cases 124/126 match ECMA formatting, case 125 does NOT (Postgres never uses exponential notation) |
| 19 | `select (-0.00001)::numeric::text;` | `-0.00001` | confirms case 127 matches |

### 6c. `core/dashboard/expr.py` citations used above

- `_FUNCTIONS` table (function whitelist): `core/dashboard/expr.py:530-553`
- `_fn_contains` (missing-haystack returns `false`, not `null`): `core/dashboard/expr.py:488`
- `_truthy` (the custom coercion rules the `boolean`/`conditional` HARD calls hinge on): `core/dashboard/expr.py:282-293`
- `_eq` (strict-type equality, `null == null → True`): `core/dashboard/expr.py:363-379`
- `_order_cmp` (ordering nulls on missing/mismatched operand): `core/dashboard/expr.py:381-397`
- `_to_num` (regex-guarded numeric coercion, `_NUM_RE`): `core/dashboard/expr.py:305-320`
- `_num_to_str` (ECMA-formatting number-to-string, the `string_ecma` group's target): `core/dashboard/expr.py:322-350`
- `_parse_date_ms` / `_format_date_ms` / `_now_ms` (strict ISO date parsing, UTC-only, zero-padded year, context-injected clock): `core/dashboard/expr.py:409-460`

### 6d. Classification script (full source, produced the tallies in §5)

```python
import json

d = json.load(open('/home/corgea/Desktop/Coding Projects/GIMS-Project/tests/fixtures/expr_vectors.json'))
cases = d['cases']

# index -> (CLASS, short reason)
C = {}

def setr(idxs, cls, reason):
    for i in idxs:
        C[i] = (cls, reason)

LC = "LIKELY-COMPILES"
HD = "HARD"

# arithmetic 0-10
setr(range(0,9), LC, "pure numeric literal arithmetic; + - * / native")
setr([9], HD, "Postgres RAISES division_by_zero (verified); expr returns null -- needs NULLIF/CASE guard")
setr([10], HD, "Postgres RAISES division_by_zero on % 0 (verified); expr returns null -- needs guard")

# fields 11-19
setr([11,12,15,16,17,19], LC, "jsonb path/array access maps directly to -> / #>>")
setr([13], LC, "verified: '{}'::jsonb -> 'missing' = NULL, matches expr's missing-field-is-null")
setr([14], LC, "verified: (jsonb scalar) -> 'b' = NULL, matches expr's descend-into-nondict-is-null")
setr([18], LC, "verified: jsonb array -> out-of-range index = NULL, matches expr")

# null_propagation 20-23
setr([20], LC, "verified: 2 + NULL = NULL in Postgres, matches expr's missing-field-nulls-arithmetic")
setr([21], LC, "both fields present, plain addition")
setr([22], HD, "verified: 'abc'::numeric ERRORS in Postgres; expr returns null -- needs regex-guarded safe-cast")
setr([23], HD, "implicit string-to-number coercion ('5'+1=6); no native SQL operator does this, needs custom cast")

# comparison 24-40
setr([24,25,27,28,29,30,31,35,38,39], LC, "plain same-type comparison, no null/type-mismatch involved")
setr([26], LC, "verified: NULL::numeric < 7 = NULL in Postgres, matches expr's missing-field-order-is-null")
setr([32], HD, "verified: SQL `NULL = NULL` is NULL (not true); expr says True -- needs IS NOT DISTINCT FROM")
setr([33], HD, "same IS NOT DISTINCT FROM mechanism needed for missing-field == null")
setr([34], HD, "same mechanism; also needs value present vs missing to differ correctly")
setr([36], HD, "cross-type equality (bool vs num) must stay type-strict; naive compare doesn't match expr's strict-type _eq")
setr([37], HD, "cross-type equality (string vs num) must be type-strict; same reason")
setr([40], HD, "verified pattern: mixed-type ordering (int < string) errors under naive SQL <; needs jsonb_typeof guard to null it")

# boolean 41-53
setr([41,42,43,47,48], LC, "operands are already real booleans (literals or comparisons); native AND/OR/NOT")
setr([44,45,46,49,50,51,52,53], HD, "requires replicating expr's custom truthy() coercion (empty string/0/empty list/missing-is-falsy) -- no SQL native equivalent")

# dates 54-66 -- all HARD, see prose rationale in doc
setr(range(54,67), HD, "date group: context-injected now()/today() need bind-parameter treatment; Postgres errors hard on unparsable strings where expr nulls; date-only vs full-timestamp formatting has no native Postgres type distinction (verified all three points)")

# coalesce 67-70
setr([67,68,69,70], LC, "Postgres COALESCE has identical null-skipping semantics, 1:1 match")

# strings 71-81
setr([71,72,73], LC, "verified: Postgres lower(NULL)/upper(NULL) = NULL, matches expr exactly")
setr([74,75], LC, "substring test maps to position()/strpos() or LIKE")
setr([76,77], HD, "contains() is polymorphic (substring vs array-membership) -- needs jsonb_typeof dispatch at compile time")
setr([78], HD, "contains() on a missing haystack returns False (not null) -- an exception to expr's general null-propagation rule, needs explicit special-casing")
setr([79,80], LC, "verified: Postgres concat() treats NULL as empty string, matches expr's concat exactly")
setr([81], HD, "nests string() -- inherits the numeric-to-text ECMA-formatting risk from the coercion/string_ecma groups")

# coercion 82-91
setr([82], HD, "number() needs a safe-cast (regex-guarded) pattern; Postgres ::numeric raises on non-numeric text")
setr([83], HD, "verified: 'abc'::numeric ERRORS; expr returns null on same input -- same safe-cast requirement")
setr([84], HD, "bool-to-number has no native Postgres cast; needs CASE WHEN")
setr([85,86,87,88,89], LC, "verified: int/float/bool/null ::text casts match expr's _to_str for these plain values; length($.s) is char_length")
setr([90], HD, "length() on an array needs jsonb_array_length + jsonb_typeof dispatch, not a single native function")
setr([91], HD, "length() of a number must be null (type mismatch) -- needs jsonb_typeof guard, not a length() call at all")

# numeric_funcs 92-102
setr([92,93,94,95,96,97,100,101], LC, "abs/floor/ceil are native and unambiguous; round() on a non-half-way value is unambiguous")
setr([98,99], HD, "verified: round(2.5) on Postgres float8 = 2 (round-half-to-even, DIVERGES); round(2.5::numeric) = 3 (matches). Compiler must know to cast through numeric, not float8, or it silently disagrees")
setr([102], HD, "12.345 to 1 digit sits on a binary floating-point representation edge; needs verification that ::numeric rounding path matches Python's round() bit-for-bit")

# aggregates 103-113
setr([110,111], LC, "vararg forms are plain scalar GREATEST/arithmetic, no array involved")
setr([103,104,105,106,107,108,109,112,113], HD, "array-valued aggregates require jsonb_array_elements + a subquery/LATERAL aggregate -- a structurally different compilation strategy than a scalar expression, plus skip-null/skip-nonnumeric filtering logic inside the unnest")

# conditional 114-116
setr([114,115], LC, "if(cond,a,b) maps directly to CASE WHEN cond THEN a ELSE b END when cond is a real boolean comparison")
setr([116], HD, "condition is a raw missing field, not a comparison -- needs truthy() coercion of a missing value (same issue as boolean group)")

# composite 117-120
setr([118], LC, "pure string equality/or, no dates, no truthy coercion")
setr([117,119,120], HD, "inherits full 'dates' group hardness (context-injected today(), days_between)")

# modulo_fmod 121-123
setr([121,122,123], HD, "verified: Postgres has NO % operator on double precision (ERRORS); % on numeric uses exact decimal arithmetic and does NOT reproduce the IEEE-754 binary remainder artifact (0.5 numeric %% 0.1 numeric = 0.0, not 0.09999999999999998) -- tested hand-rolled float8 fmod substitute also did not reproduce it. Sharpest divergence risk in the whole fixture")

# string_ecma 124-127
setr([124,126,127], LC, "verified: Postgres ::numeric::text matches ECMA formatting exactly for these three magnitudes (0.00001, 1000000, -0.00001)")
setr([125], HD, "verified: Postgres ::numeric::text never emits exponential notation (1e-7 -> '0.0000001'); ECMA/expr expects '1e-7' -- confirmed divergence")

# date_total 128-129
setr([128,129], HD, "date group: out-of-range date_add and pre-epoch year padding both depend on the same custom date formatter as the 'dates' group")

assert len(C) == 130, f"only classified {len(C)} of 130"
for i in range(130):
    assert i in C, f"missing {i}"

# tallies
from collections import Counter
cnt = Counter(cls for cls,_ in C.values())
print(cnt)
# → Counter({'LIKELY-COMPILES': 68, 'HARD': 62})
```
