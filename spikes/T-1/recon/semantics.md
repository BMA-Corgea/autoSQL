# T-1 recon — exact operational semantics of `core/dashboard/expr.py`

**Question owner:** this document only. Scope: the Python evaluator's exact behaviour,
at the level a SQL-compiler author needs to reproduce it. No compiler design, no
conformance run, no index work — those are other seats' questions.

**Source file (byte-identical in both trees per FRAMING.md §2):**
`core/dashboard/expr.py`, 646 lines. All line citations below are to this path as it
exists at `GIMS-Project` commit `995cc59` (= `gims-ledger` `7b7a049`, verified
byte-identical in FRAMING.md). Read in full before writing this document.

Verification method: every runtime claim below was checked against the real evaluator,
imported live —
`cd "GIMS-Project" && .venv/bin/python -c "from core.dashboard.expr import ..."`
(Python 3.12.3, per FRAMING.md §7) — and against live PostgreSQL 16.14 in
`glp-strong-db` via `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "..."`.
Commands and their exact output are quoted inline as citations; nothing below is
asserted from memory of the source alone where a runtime check was possible.

---

## 1. AST node shapes `parse()` emits

Every node is a tagged tuple (`AST = Tuple`, `expr.py:44`). The tags actually
constructed by `_Parser`/`_call` are:

| tag | shape | built at |
| --- | --- | --- |
| `("num", float)` | numeric literal | `expr.py:193` |
| `("str", str)` | string literal (already unescaped) | `expr.py:196` |
| `("bool", bool)` | `true`/`false` | `expr.py:199` |
| `("null",)` | `null` keyword | `expr.py:202` |
| `("field", path)` | `$`-access; `path` is `List[Tuple[str, Any]]` of `("key", name_str)` or `("index", int)` steps | `expr.py:247` (built in `_field`, `expr.py:216-247`) |
| `("neg", operand)` | unary `-` | `expr.py:179` |
| `("not", operand)` | keyword `not` | `expr.py:151` |
| `("and", left, right)` | keyword `and` | `expr.py:138`(sic, `_and` builds it at `:145`) |
| `("or", left, right)` | keyword `or` | `expr.py:138` |
| `("cmp", op_str, left, right)` | one of `== != < <= > >=` | `expr.py:159`, ops enumerated `:157` |
| `("bin", op_str, left, right)` | one of `+ - * /  %` | `expr.py:166` (`+ -`), `:173` (`* / %`) |
| `("call", name_str, args_list)` | function call; `name` pre-validated against `_FUNCTIONS` **at parse time** | `expr.py:261`, whitelist check `:259-260` |

Rule for a compiler: this is a fixed, closed tag set (10 tags). A compiler can pattern-match
exhaustively on `node[0]` with no default/fallback branch needed for unknown tags coming out
of `parse()` — the parser itself guarantees the tag universe (`_eval`'s own `raise
ExprError(f"Unknown AST node {tag!r}")` at `expr.py:636` is annotated `# pragma: no cover -
parser guarantees tags`).

**Precedence (low→high), confirmed by the recursive-descent structure**
(`expr.py:105`, `_or→_and→_not→_cmp→_add→_mul→_unary→_primary`):
`or` < `and` < `not` < comparison (`== != < <= > >=`, **non-associative** — `_cmp` at
`expr.py:154-160` consumes at most one comparison operator, so `a < b < c` is a syntax error,
not chained comparison) < `+ -` (left-assoc) < `* / %` (left-assoc) < unary `- +` < primary.
A compiler that flattens this into SQL's own operator precedence must reproduce the
**non-chaining** of comparisons explicitly (SQL has no such restriction, so a naive
transliteration of `a < b < c` would silently compile to something SQL accepts — this input
never reaches the compiler as valid AST because `parse()` already rejects it via
`expr.py:130-131` trailing-token check, so this is a parse-time guarantee, not something the
SQL compiler must separately enforce).

Field-path steps: `("key", str)` from `.name` (`expr.py:227`) or `["quoted"]`
(`expr.py:237`); `("index", int)` from `[N]` or `[-N]` (`expr.py:238-241`), where the
literal must be a bare, non-scientific, non-decimal integer token (`"." not in iv and "e"
not in iv.lower()`, `expr.py:238`) — `$[1.0]` and `$[1e0]` are **syntax errors**, not valid
index literals.

---

## 2. `_to_num` — numeric coercion (`expr.py:305-319`)

```
_NUM_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")   # expr.py:302
```

Rule, by input type:

- **bool → number.** `True → 1.0`, `False → 0.0` (`expr.py:307-308`). This runs *before*
  the `_is_num` check, and `_is_num` itself explicitly excludes `bool`
  (`isinstance(v, (int, float)) and not isinstance(v, bool)`, `expr.py:279`) — so bool is
  numeric only through this dedicated branch, never through the general numeric branch.
- **int/float (non-bool) → number**, but NaN collapses to `None`: `f if f == f else None`
  (`expr.py:311`, `f == f` is `False` only for NaN). Verified live: `_to_num` never returns
  NaN — every NaN-producing path becomes `None` upstream.
- **str → number only if the WHOLE trimmed string matches `_NUM_RE`.** `v.strip()` first
  (`expr.py:313`), so leading/trailing whitespace is fine, but the pattern requires a plain
  decimal literal with optional sign and optional exponent — **no hex (`0x10`), no
  underscore-separated digits (`5_000`), no `NaN`/`Infinity` literal, no trailing-only dot
  survives except `\d+\.\d*` (so `"5."` IS accepted — the regex allows an empty fractional
  part), no leading `.` alone (`"."` fails, `.5` succeeds), no thousands separators, no
  `+`/`-` for `Infinity`.** All confirmed live:
  ```
  '  12  ' -> 12.0   '1e3' -> 1000.0   '.5' -> 0.5   '5.' -> 5.0
  '0x10' -> None     'NaN' -> None     'Infinity' -> None   '+5' -> 5.0
  '5_000' -> None    '' -> None        ' ' -> None   '12abc' -> None
  ```
  (verified via `.venv/bin/python -c "from core.dashboard.expr import _to_num; ..."`, run
  during this recon).
- **list/dict/None → `None`** always (falls through, `expr.py:319`; verified live:
  `_to_num([1]) -> None`, `_to_num({'a':1}) -> None`, `_to_num(None) -> None`).

**One-line rule for the compiler:** a SQL numeric cast of an arbitrary JSONB scalar must
replicate this exact regex-gated coercion, not Postgres's native `::float8` cast — Postgres's
cast is **stricter in some ways** (rejects `"5."`? — no, `'5.'::float8` succeeds in PG too)
**and looser/different in ways that matter**: Postgres accepts `'NaN'::float8` and
`'Infinity'::float8` as valid (giving actual IEEE NaN/Infinity), which `_to_num` explicitly
rejects to `None`; and critically, Postgres's cast **raises** on non-numeric input
(`invalid input syntax for type double precision: "abc"` — confirmed live via
`docker exec glp-strong-db psql ... "select 'abc'::float;"`) where `_to_num` returns `None`
silently. **A bare `::float8` cast is not a safe translation of `_to_num` under any
circumstance** — the compiler must gate every cast behind a regex match (`~ '^[+-]?...$'` in
SQL) against the same pattern as `_NUM_RE`, and use `CASE WHEN col ~ '<pattern>' THEN
col::float8 ELSE NULL END`, never a bare cast, to keep `expr`'s totality (§5, FRAMING.md's
non-negotiable).

---

## 3. `_truthy` (`expr.py:282-293`)

```
None, False        -> False
True                -> True
number              -> v != 0 and v == v      # zero AND NaN are both falsy
str                 -> len(v) > 0             # "" is falsy, "0" and "false" are TRUTHY
list/tuple/dict     -> len(v) > 0             # empty container falsy
anything else       -> True                   # unreachable in practice (closed Value universe)
```
Confirmed by direct read; note the double condition on numbers at `expr.py:288`
(`v != 0 and v == v`) — the second clause is a NaN guard. This guard **is load-bearing, and
the leak it guards against was confirmed live, not just reasoned from code**:
```
.venv/bin/python -c "from core.dashboard.expr import parse, evaluate;
print(evaluate(parse('1e400 - 1e400'), {}, {}))   # -> nan
print(evaluate(parse('1e400'), {}, {}))            # -> inf"
```
A bare numeric literal `1e400` overflows Python `float()` parsing straight to `inf` at parse
time (`expr.py:193`, `float(v)` on the token text — no overflow guard), so `("num", inf)` is a
constructible literal AST node, and `inf - inf` (or any NaN-producing arithmetic) reaches
`_eval`'s `bin` branch (`expr.py:608-624`) unfiltered — `_to_num`'s NaN-guard
(`expr.py:311`) only runs when a value is *coerced into* numeric position, never on the
*output* of `+ - * /`. **`evaluate()` can and does return a raw, un-nulled Python
`nan`/`inf` as its final result** — a genuine gap in the file's own "total, never raises, bad
values become null" design rule (`expr.py:17-19`): overflow is silently let through as IEEE
`inf`/`nan` rather than coerced to `None`. `_truthy(nan)` still correctly evaluates `False`
via the `v == v` guard at `expr.py:288` (so `if`/`and`/`or`/`not` never mis-branch on it), but
a `derive` column or a raw returned scalar can surface literal `nan`/`inf`.
**For the compiler this is a real hazard in the opposite direction from most of this
document**: SQL `double precision` also has `inf`/`nan` as representable values (Postgres
accepts `'Infinity'::float8`, confirmed in §2), so a literal-for-literal translation of
`1e400 - 1e400` might actually reproduce this leak faithfully — but the compiler author must
decide *deliberately* whether to preserve it (matching Python byte-for-byte) or clamp it to
NULL at the boundary; assuming "everything numeric here is already null-safe" and doing
neither would be the actual mistake. Not chased further per FRAMING.md stop-rules — the
fixture does not test this (`grep -c 'e400\|1e30\|inf' tests/fixtures/expr_vectors.json` finds
nothing) — but it is now a **confirmed**, not merely reasoned, code-behaviour finding.

**One-line rule:** `_truthy` is `NOT (v IS NULL OR v = false OR (is_number(v) AND (v = 0 OR v
<> v)) OR (is_string_or_array_or_object(v) AND length/cardinality(v) = 0))`. In SQL/JSONB
terms this must inspect the JSONB type tag (`jsonb_typeof`), not just compare to `0`/`''`,
because JSONB `0` and JSONB `false` and JSONB `null` and SQL `NULL` are four distinct things
that must map to exactly this rule.

---

## 4. `_eq` (`expr.py:363-378`) — used for `==`/`!=` and list-membership in `contains`

Order of checks, all must be reproduced in this order because later branches assume earlier
ones failed:

1. `None == None -> True`; `None` vs. anything-non-None `-> False` (`expr.py:364-367`).
   **No "NULL propagates to NULL" here** — equality with a NULL operand is a concrete
   `bool`, never itself `None`. This is the single most important divergence from naive SQL:
   SQL's `a = b` is `NULL` (three-valued) whenever either side is `NULL`; `expr`'s `==` is
   **two-valued** and defines `NULL == NULL` as `true` and `NULL == <anything-else>` as
   `false`. A compiler must NEVER translate `expr`'s `==`/`!=` to bare SQL `=`/`<>` — it must
   use `IS NOT DISTINCT FROM` / `IS DISTINCT FROM` (Postgres's null-safe equality operators,
   which implement exactly this two-valued, NULL-equals-NULL semantics) or an explicit `CASE`.
2. **Type-gated, no cross-type coercion for `==`.** Bool is compared only to bool
   (`isinstance(a, bool) or isinstance(b, bool)` gate at `expr.py:368-369`, requiring BOTH be
   bool and Python-`==`) — **`true == 1` is `False`**, confirmed live:
   `_eq(True, 1.0) -> False`, `_eq(True, True) -> True`, `_eq(False, 0.0) -> False`. This
   is a real trap for a compiler tempted to write `col = 1` for `col == true` — they are not
   the same predicate.
3. Number vs number (both `_is_num`, i.e. int/float excluding bool): `float(a) == float(b)`
   (`expr.py:370-371`) — ordinary numeric equality (IEEE double), no epsilon.
4. String vs string: exact Python string equality, no normalization (`expr.py:372-373`).
5. List vs list: same length AND element-wise `_eq` (recursive), position-order-sensitive
   (`expr.py:374-375`).
6. Dict vs dict: **same key set** (`a.keys() == b.keys()`, set-equality, order-independent)
   AND every value recursively `_eq` (`expr.py:376-377`).
7. **Any other type combination (including num-vs-str, list-vs-dict, str-vs-list, etc.)
   → `False`**, the catch-all at `expr.py:378`. No implicit stringification, no implicit
   numeric parse of a string for `==` (contrast this with `_to_num`/`_order_cmp` below, which
   DO parse — `==` never does).

**One-line rule:** `expr`'s `==` is a strict, same-type, two-valued equality with an explicit
NULL-equals-NULL carve-out; compile to `IS NOT DISTINCT FROM` gated by matching
`jsonb_typeof`, never bare `=`.

---

## 5. `_order_cmp` (`expr.py:381-396`) — `< <= > >=`

```python
if a is None or b is None: return None          # :382-383  (three-valued here, UNLIKE _eq)
if is_num(a) and is_num(b): a,b = float(a), float(b)   # :384-385
elif isinstance(a,str) and isinstance(b,str): pass       # :386-387 (str-str: lexicographic)
else: return None                                        # :388-389  (mixed/other types -> None)
```
Then a plain Python `<`/`<=`/`>`/`>=` on the coerced pair (`expr.py:390-396`).

Key points for the compiler:

- **Ordering comparisons ARE three-valued / NULL-propagating** (`None` if either operand is
  `None`, `expr.py:382-383`) — this is the OPPOSITE convention from `_eq`, which is
  two-valued. A compiler cannot reuse one NULL strategy for both `==`/`!=` and `<`/`<=`/`>`/
  `>=`: `==`/`!=` need `IS [NOT] DISTINCT FROM`; ordering comparisons can use plain SQL `<`
  etc. **because SQL's native three-valued NULL behaviour for `<` already matches**
  (`NULL < 5` is SQL `NULL`, matching `_order_cmp(None, 5) -> None`) — confirmed live:
  `_order_cmp('<', None, 5) -> None`.
- **No cross-type coercion**: number-vs-string returns `None`, not a parse attempt. Confirmed
  live: `_order_cmp('<', 1, '1') -> None` (contrast with `_to_num("1") -> 1.0` — the string
  IS numeric-parseable, but `_order_cmp` still refuses to compare it against a raw number,
  because the branch requires BOTH operands already be `_is_num` or BOTH already be `str`).
  A naive SQL compiler that casts both sides to numeric before comparing would silently
  produce a value (`1 < 1` → false) where the real semantics is `NULL`(undefined/falsy)  —
  **this is exactly the "silent divergence" the FRAMING.md non-negotiable (§5) forbids.**
- **Bool is excluded from both branches** (not `_is_num`, not `str`) → any comparison
  involving a bool operand is unconditionally `None`. Confirmed live:
  `_order_cmp('<', True, 5) -> None`.
- String comparison is **plain Python `str` `<` `str`**, i.e. codepoint-by-codepoint
  lexicographic (`expr.py:386-387,390-396`) — must map to SQL string comparison under a
  byte/codepoint (`C`/`POSIX`-equivalent) collation, not the database's default locale
  collation, or ordering will silently diverge on non-ASCII text. Not independently verified
  against the DB's actual default collation in this pass — flagged as a gap; the compiler
  author must pin the collation explicitly (e.g. `COLLATE "C"`) and verify.

**One-line rule:** ordering comparisons are type-homogeneous (num-num or str-str only), NULL
if either side is NULL, `None` (not an error, not a coercion) for ANY type mismatch including
bool and cross num/str — compile to native SQL comparison operators (their native
three-valued NULL behaviour already matches) but ONLY after a `jsonb_typeof` guard that
forces the result to SQL `NULL` for any non-matching-type pair, and pin `COLLATE "C"` for
string comparisons.

---

## 6. Modulo, division, and division-by-zero (`expr.py:608-624`)

```python
if op == "/":
    return None if rn == 0 else ln / rn      # :620-621
if op == "%":
    # math.fmod == C fmod == JS `%` (truncated remainder, sign of the dividend).
    return None if rn == 0 else math.fmod(ln, rn)   # :622-624
```

- **Division by zero → `None`, silently, always** (`rn == 0` covers `+0.0` and `-0.0`
  identically under Python float equality) — never a Python exception, never propagated as
  `inf`/`-inf`/`nan`. Confirmed against fixture: `"modulo_by_zero_is_null"`,
  `expr: "5 % 0", expect: null` (`tests/fixtures/expr_vectors.json:16`); division-by-zero
  has an analogous case in the `arithmetic` group (not individually re-verified by name in
  this pass, but the code path at `expr.py:620-621` is unconditional and identical in
  structure — the `/` and `%` guards are the same `rn == 0` test).
- **Modulo uses `math.fmod`, NOT Python's native `%` operator**, and the file's own comment
  says why (`expr.py:623`): "`math.fmod == C fmod == JS`%`(truncated remainder, sign of the
  dividend)". **This is confirmed to matter, not just a style choice** — measured live:
  ```
  python native:  -5 % 3 = 1     5 % -3 = -1      (floor/Euclidean-leaning, sign of DIVISOR)
  math.fmod:      fmod(-5,3) = -2.0   fmod(5,-3) = 2.0   (sign of DIVIDEND — truncation toward zero)
  ```
  and the fixture asserts the `fmod` values: `"modulo_neg_dividend_truncates": "-5 % 3"
  expect -2` and `"modulo_neg_divisor_truncates": "5 % -3" expect 2`
  (`tests/fixtures/expr_vectors.json:11-12`).
- **Postgres's native `%` operator matches `math.fmod`, not Python's native `%`.** Verified
  live against `glp-strong-db`:
  `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "select -5 % 3, 5 % -3, mod(-5,3), mod(5,-3);"`
  → `-2|2|-2|2`. So **the naive/obvious compilation `expr %` → SQL `%` is actually
  CORRECT** — the trap here is the opposite direction: an author who "fixes" what looks like
  a sign bug by porting Python's native `%` semantics into the compiler (e.g. emitting
  `MOD()`-with-floor-adjustment logic) would introduce a real divergence where none exists.
  **This must be called out explicitly in the compiler's design notes** so nobody "fixes" it.
- Both fixture float-`fmod` cases (`modulo_fmod` group, `expr.py` n/a — fixture-only) confirm
  IEEE-754 double rounding must be bit-for-bit reproduced: `"0.5 % 0.1"` expects
  `0.09999999999999998` (`tests/fixtures/expr_vectors.json:141`), not the mathematically
  "clean" `0.1`. Postgres `%` on `double precision` uses the same IEEE fmod under the hood in
  principle, but this specific value pair was **not** independently re-verified against
  Postgres in this pass (only the integer sign cases above were) — flagged as a gap for the
  conformance-harness seat to close, not assumed here.
- `+ - *` have no special-casing beyond `_to_num` coercion returning `None` for either operand
  (`expr.py:610-619`) — ordinary IEEE arithmetic, no overflow guard, no total-order guard.

**One-line rule:** `/` and `%` compile to `CASE WHEN rhs = 0 THEN NULL ELSE lhs OP rhs END`
using SQL's native `/`(for numeric/float division, not integer floor-division) and `%`
operators unmodified — Postgres's `%` already implements C/JS truncating-toward-zero
semantics identically to `math.fmod`, confirmed by direct measurement, not derivation.

---

## 7. Date parsing/formatting — `_parse_date_ms` / `_format_date_ms` (`expr.py:402-445`)

Grammar (`_DATE_RE`, `expr.py:402-406`):
```
^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:?\d{2})?)?$
```

- **Strict ISO-8601-subset, not a general parser.** Requires 4-digit year, exactly
  2-digit month/day (no `2024-1-5`; confirmed live: `_parse_date_ms('2024-1-5') -> None`).
  Date-only (`YYYY-MM-DD`) is valid on its own; time part is fully optional but if present
  requires `T` or a literal space as separator, `HH:MM` mandatory, `:SS` optional,
  `.ffffff` (1–6 fractional digits) optional, and an optional trailing offset (`Z` or
  `±HH:MM`/`±HHMM`).
  **No support for**: week-dates, ordinal dates, `T` with only hour, missing leading zeros,
  more than 6 fractional digits (regex caps at 6, so a 7th+ digit would fail the whole match
  since the pattern is anchored with `$`).
- **Calendar validity is enforced by constructing a real `datetime`, not the regex.**
  `2024-13-01` matches nothing structurally wrong in digit-count terms but fails at
  `datetime(...)` construction → `ValueError` → caught, returns `None`
  (`expr.py:418-426`); confirmed live: `_parse_date_ms('2024-13-01') -> None`.
- **Fractional seconds**: right-padded to 6 digits then truncated to 6
  (`(frac or "0").ljust(6, "0")[:6]`, `expr.py:422`) and used as Python microseconds — so
  `.1` means `100000` microseconds (100ms), not 1 microsecond. Confirmed live:
  `'2024-01-15T10:30:00.123456Z' -> (1705314600123.456, False)` (the `.456` ms fraction in
  the result is exactly `123456` µs / 1000).
- **No offset present (bare date+time, no `Z`, no `±HH:MM`) is treated as UTC**, not local
  time and not an error. Confirmed live:
  `_parse_date_ms('2024-01-15T10:30:00')` and `_parse_date_ms('2024-01-15T10:30:00Z')` give
  the **identical** `1705314600000.0`. This is the "UTC-only" design rule stated in the
  module docstring (`expr.py:20-21`) made concrete: absence of a zone is not "unknown zone",
  it is defined as UTC.
- **Non-`Z` numeric offsets are subtracted** to normalize to UTC
  (`expr.py:427-430`: `dt - timedelta(minutes=sign*(hh*60+mm))`) — sign convention:
  `+02:00` means the wall-clock time is 2 hours ahead of UTC, so UTC = local − offset, which
  is what the code does (`sign=1` for `+`, then subtracts). Confirmed live:
  `'2024-01-15 10:30:00+02:00' -> (1705307400000.0, False)`, which is exactly 2 hours (=
  7,200,000 ms) earlier than the no-offset/Z case above (`1705314600000.0 −
  1705307400000.0 = 7200000`).
- **Return shape is `(utc_epoch_ms: float, date_only: bool)` or `None`.** `date_only = (not
  has_time)`, i.e. **true iff no time-of-day component was present in the input string at
  all** (`expr.py:417,431`) — not based on whether the time was `00:00:00`. `"2024-01-15"` →
  `date_only=True`; `"2024-01-15T00:00:00Z"` → `date_only=False` even though both denote
  midnight UTC. This distinction is **load-bearing downstream**: `date_add` reuses the
  input's `date_only` flag to decide whether its *output* is formatted as a bare date or a
  full timestamp (`expr.py:485`, `base[1]`) — so `date_add("2024-01-15", 1)` returns a
  bare-date string, but `date_add("2024-01-15T00:00:00Z", 1)` returns a full timestamp
  string, even though the arithmetic result is numerically identical.
- **Only a string is ever accepted** — `_parse_date_ms` returns `None` immediately for any
  non-`str` input (`expr.py:411-412`); numbers/epoch-ms are never accepted directly as a date
  argument to `days_between`/`date_add` (they'd fail `_parse_date_ms` and the function
  returns `None` overall, per `expr.py:472-474`, `481-484`).

`_format_date_ms(ms, date_only)` (`expr.py:434-445`):
- Constructs `datetime.fromtimestamp(ms/1000.0, tz=utc)`; **catches
  `ValueError`/`OverflowError`/`OSError` and returns `None`** for out-of-range results
  (`expr.py:438-441`) — e.g. a `date_add` that walks past year 9999 or before year 1 produces
  `None`, not a raised error or a wrapped/clamped date. This is the "total" behaviour
  explicitly called out in the code comment at `expr.py:435-437`.
- **Year is manually zero-padded to 4 digits** (`f"{dt.year:04d}"`) specifically because
  `strftime('%Y')` on glibc does *not* zero-pad (code comment, `expr.py:436-437`) — confirmed
  live against Postgres: `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc
  "select to_char(make_date(1,1,1),'YYYY-MM-DD');"` → `0001-01-01`. Postgres's `to_char`
  already zero-pads, so this specific padding requirement is a non-issue for a
  `to_char`-based SQL formatter, matching `_format_date_ms`'s manual padding by default.
- Two output shapes only: `date_only=True → "YYYY-MM-DD"`; `date_only=False →
  "YYYY-MM-DDTHH:MM:SSZ"` (seconds precision, always literal trailing `Z`, no fractional
  seconds ever emitted on output even if the input had them — confirmed by the format string
  itself, `expr.py:444-445`, which has no fractional-second field).

**One-line rule:** date parsing is a fixed ISO-8601 subset with mandatory 4-digit year/2-digit
month/day, calendar-validated via real date construction (not just digit-shape), UTC-assumed
when no offset is given, and every operation is total — unparseable input and out-of-range
results both yield SQL `NULL`, never an error and never a clamped/wrapped date. A compiler
must implement this exact grammar (e.g. a matching `to_timestamp`/regex-gated cast in SQL,
NOT Postgres's lenient `::timestamp` cast, which accepts many more formats than `_DATE_RE`
does and would silently accept-and-parse strings this evaluator rejects to `None` — a silent
divergence of exactly the kind FRAMING.md §5 forbids). The `date_only` flag must be tracked as
a second, separate piece of state through any SQL compilation of `date_add`/`today`/`now` —
it cannot be recovered later from the timestamp value alone.

### `today()` / `now()` and the context-supplied clock (`expr.py:448-456`, `531-532`)

```python
def _now_ms(ctx):
    injected = ctx.get("now") if ctx else None
    if isinstance(injected, str):
        parsed = _parse_date_ms(injected)
        if parsed is not None: return parsed[0]
    if _is_num(injected):
        return float(injected)
    return datetime.now(timezone.utc).timestamp() * 1000.0
```
- The evaluation context (`ctx: Dict[str, Any]`, the third arg to `evaluate()`/`_eval`,
  `expr.py:578,639`) may carry a `"now"` key that **overrides the wall clock**, for
  deterministic testing/preview. It accepts either an ISO string (parsed via the same
  `_parse_date_ms`, so it must satisfy the same strict grammar or it's silently ignored and
  falls through) or a raw number (treated directly as epoch-ms, no further validation).
  **Any other type, or an unparseable string, or no `"now"` key at all → real wall clock**
  (`datetime.now(timezone.utc)`, `expr.py:456`).
- `today()` = `_format_date_ms(_now_ms(ctx), date_only=True)` (`expr.py:531`); `now()` =
  `_format_date_ms(_now_ms(ctx), date_only=False)` (`expr.py:532`). Both are ordinary
  zero-arg builtin calls — `args` is ignored/unused for these two.
- **For a SQL compiler**: `today()`/`now()` are the one place per-query wall-clock state
  enters — the compiler must bind them once per query execution (e.g. via a query-time
  parameter or `now()`/`current_date` bound at plan time, NOT re-evaluated per row, since the
  Python evaluator computes `_now_ms` once per `evaluate()` call, i.e. effectively once per
  record-evaluation in the current per-record architecture — whether that must become
  once-per-query in a set-oriented SQL compilation is a compiler-design question out of scope
  here, but the row-level Python semantics is: one instant per call). Not independently
  timed/measured in this pass.

---

## 8. `_resolve_field` — field access (`expr.py:562-575`)

```python
def _resolve_field(record, path):
    cur = record
    for kind, key in path:
        if kind == "key":
            if isinstance(cur, dict) and key in cur: cur = cur[key]
            else: return None
        else:  # index
            if isinstance(cur, (list, tuple)) and -len(cur) <= key < len(cur): cur = cur[key]
            else: return None
    return cur
```

- **Every step is independently guarded; the first failure short-circuits the whole path to
  `None`** — there is no partial result. Confirmed live: `_resolve_field({'x':'str'},
  [('key','x'),('key','b')])` (descending a `.b` key-step into a **string**, not a dict) →
  `None`, not an error, not string-indexing behaviour.
- **`key in cur` uses real dict membership** — a dict value equal to `None`
  (`{"a": None}`) is a *present* key and resolves to `None`, which is
  observationally identical to a missing key from the caller's point of view (both yield
  Python `None`), but internally these are different code paths (`key in cur` is `True` vs.
  `False`). Not independently distinguished by any behavioural test in this pass (would
  require an observation that can tell "no such field" apart from "field is null", and
  nothing in `expr` exposes that distinction) — noted as: **the compiler does not need to
  distinguish JSONB-key-absent from JSONB-key-present-with-null**, because Python doesn't
  either. This is directly useful: `data -> 'key'` (returns SQL NULL for either absent-key or
  JSON-null value) already gives the right merged behaviour without needing `?` key-existence
  checks.
- **Negative indices are supported and resolved Python-style** (`-len(cur) <= key`, i.e.
  `key` in `[-len, len-1]`) — `[-1]` is last element. Confirmed live:
  `_resolve_field({'a':{'b':[1,2,3]}}, [('key','a'),('key','b'),('index',-1)]) -> 3`.
- **Out-of-range index (either direction) → `None`, not an error, not clamped.** Confirmed
  live: index `5` into a 3-element list → `None`; index `-4` into a 3-element (`arr`, len 3,
  valid range `[-3,2]`) list → `None`.
- **Indexing into a non-list (e.g. a dict, when an `[N]` step is used), or a `.key` step into
  a non-dict, or ANY step into `None`/a scalar** → `None`, uniformly, via the same
  `isinstance` guard failing (`expr.py:566,571`). There is no special "index into a dict by
  position" or "key into a list" behaviour — type mismatch is just another form of
  not-found.
- `record` itself may be anything; `evaluate()` substitutes `{}` if `record is None`
  (`expr.py:641`), so a totally missing record behaves as an empty dict — every field access
  on it resolves to `None` via the same dict-miss path, not a special top-level case.

**One-line rule:** field access is `#>` / `->`-chain style total JSONB traversal where EVERY
step — key-into-non-object, index-into-non-array, index-out-of-range (including Python-style
negative indices bounds-checked against actual length) — collapses to SQL `NULL` with no
error and no distinction between "path doesn't exist" and "path resolves to a JSON null".
**Confirmed live against `glp-strong-db`**:
`docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "select '[10,20,30]'::jsonb ->
-1, '[10,20,30]'::jsonb -> -4, '[10,20,30]'::jsonb -> 5;"` → `30 | (empty/NULL) |
(empty/NULL)`. This is an exact match to `_resolve_field`'s behaviour on the same inputs
(`_resolve_field(..., [('index',-1)]) -> 3`-analogue = last element; both out-of-range
directions → `None`) — Postgres's `->` on a jsonb array supports negative indexing
(last-element-relative) and returns SQL NULL for any out-of-range index, positive or
negative, with no error. This construct is a direct, low-risk compile target.

---

## 9. `_num_to_str` and `_to_str` (`expr.py:322-360`)

- `_to_str(v)`: `None -> None` (propagates, does not become the string `"null"`); bool →
  literal `"true"`/`"false"` (`expr.py:354-355`); number → `_num_to_str(float(v))`; string →
  itself unchanged; **list/dict → `None`** (no JSON-stringification; falls through the final
  `return None` at `expr.py:360`). This feeds `string()`, `concat()`, `lower()`, `upper()`,
  and the string-branch of `contains()`.
- `_num_to_str(x)` is a deliberate re-implementation of **ECMAScript `Number::toString`**
  formatting (module comment, `expr.py:323-327`), NOT Python's `str(float)`/`repr` and NOT
  SQL's default numeric-to-text cast. Special cases spelled out in code:
  `0 -> "0"` (not `"0.0"` or `"-0"` for negative zero — `x == 0` catches both signs since
  Python `-0.0 == 0.0`); NaN → literal `"NaN"` string, annotated **unreachable in the intended
  design** because NaN is meant to be coerced to `null` upstream — but §3 above now shows
  raw NaN CAN reach a caller through `bin` arithmetic overflow, so this "unreachable" branch
  is reachable in practice, just not exercised by the fixture; `±inf ->
  "Infinity"/"-Infinity"`. For finite non-zero values it uses
  `Decimal(repr(abs(x))).normalize()` to get shortest-round-trip significant digits (mirrors
  Python's `repr`, which the comment asserts equals JS's shortest-digit algorithm) and then
  reformats per ECMA-262 rules: plain decimal notation when the decimal point falls in
  `(-6, 21]` relative to the significant digits, exponential notation (`d.dddde±N`) outside
  that window — e.g. `1e21` prints as `"1e+21"` not as a 22-digit integer, and `0.00001`
  prints as `"0.00001"` not `"1e-05"` (module comment, `expr.py:326-327`, matching the
  `-6 < n <= 0` branch at `expr.py:342-343`). **All of the following were confirmed live**
  (`.venv/bin/python -c "from core.dashboard.expr import _num_to_str; print(_num_to_str(-0.0),
  _num_to_str(1.0), _num_to_str(1e21), _num_to_str(0.00001))"`) → `0`, `1`, `1e+21`,
  `0.00001` — matching every claim above exactly.
- **This is a real compile hazard, confirmed against live Postgres, not a nicety.** Ran
  `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "select 1.0::text,
  1e21::float8::text, 0.00001::float8::text, (-0.0)::float8::text;"` →
  `1.0 | 1e+21 | 1e-05 | 0`. Comparing pairwise against `_num_to_str`:
  | value | `_num_to_str` (expr) | Postgres `::text` | match? |
  | --- | --- | --- | --- |
  | `1.0` | `"1"` | `"1.0"` | **DIVERGES** — every whole-number float prints with a trailing `.0` in Postgres, never in `_num_to_str` |
  | `1e21` | `"1e+21"` | `"1e+21"` | matches |
  | `0.00001` | `"0.00001"` | `"1e-05"` | **DIVERGES** — Postgres switches to exponential notation far sooner on the small-magnitude side than ECMA-262's `(-6,0]` window |
  | `-0.0` | `"0"` | `"0"` | matches |

  **A bare `col::text` translation of `string(x)`/`concat(...)` involving a number is
  confirmed wrong for two of four sampled cases** — this is not a hypothetical edge, it is the
  ordinary case of any whole-number-valued float (`string(5)` → expr `"5"`, naive SQL `"5.0"`)
  and any small-magnitude decimal (`string(0.00001)` → expr `"0.00001"`, naive SQL `"1e-05"`).
  This construct should be treated as **non-compiling / forced fallback** unless a hand-built
  `to_char`-based ECMA-262 formatter is written and independently verified against all 4 cases
  in the fixture's `string_ecma` group (`tests/fixtures/expr_vectors.json`), which exists
  precisely to pin this contract but was not itself re-run against SQL output in this pass.

**One-line rule:** any expr construct that stringifies a number (`string()`, `concat()`,
implicit numeric-to-string anywhere) must NOT use Postgres's native numeric-to-text cast —
confirmed to diverge on whole numbers (`"1.0"` vs `"1"`) and on small-magnitude decimals
(`"1e-05"` vs `"0.00001"`) — and should be treated as a forced, reported fallback unless a
custom ECMA-262-matching formatter is built and verified case-by-case.

---

## 10. Every builtin function (`_FUNCTIONS`, `expr.py:530-553`, plus `if` as a special form)

General call semantics (`expr.py:625-635`): a call's arguments are **evaluated eagerly, all
of them, left to right**, into a plain `Value` list, THEN passed to the function
(`args = [_eval(a,...) for a in node[2]]`, `expr.py:634`) — **except `if`**, which is handled
as a special form before the generic dispatch and evaluates only the taken branch
(`expr.py:627-632`, confirmed live: `if(true, 1, $.nonexistent...)` never errors regardless of
what the untaken branch contains, because it is never evaluated — though since `expr` is
total this specific test can't distinguish "not evaluated" from "evaluated but happened to
return None too"; the code at `expr.py:631-632` (`return _eval(argsn[1] if cond else
argsn[2], ...)`) is unambiguous by inspection: only one branch is ever passed to `_eval`).
**This laziness is compiler-load-bearing**: SQL is not total (§2, §6 above — bad casts and
zero-division raise), so `if(cond, a, b)` MUST compile to a genuinely short-circuiting `CASE
WHEN cond THEN a ELSE b END`, never to a function/subquery form that evaluates both `a` and
`b` unconditionally before selecting — the latter would turn `if($.n > 0, 1/$.n, 0)` from
always-succeeding (Python) into a query that raises whenever `$.n` is 0, even for rows where
the `false` branch was the one that mattered. This is one of the highest-severity naive-SQL
divergence risks in the whole file.

Per-function contract (arg-count/type failures always → `None`, never an error):

- **`today()` / `now()`** — zero-arg (args ignored). See §7. Return ISO date / ISO
  timestamp string from the context clock.
- **`days_between(a, b)`** (`expr.py:469-475`) — exactly 2 args required (else `None`,
  `:470-471`); both parsed via `_parse_date_ms`; either unparseable → `None`
  (`:473-474`); else `(b_ms − a_ms) / MS_PER_DAY` (`:475`, `MS_PER_DAY = 86_400_000.0` at
  `expr.py:41`) — **a signed float, can be negative, can be fractional** (time-of-day
  differences produce fractional days), NOT calendar-day subtraction.
- **`date_add(base, n)`** (`expr.py:478-485`) — exactly 2 args; `base` parsed via
  `_parse_date_ms`, `n` coerced via `_to_num` (so `n` can be a numeric **string** too, and can
  be negative or fractional); either failing → `None`; else
  `_format_date_ms(base_ms + n*MS_PER_DAY, date_only=base's own date_only flag)`
  (`:485`) — output format inherits the **input's** date-only-ness, per §7.
- **`coalesce(...)`** (`expr.py:535`) — first non-`None` arg in evaluation order, or `None`
  if all are `None`/no args. Plain `next((a for a in args if a is not None), None)` — note
  this checks Python-`None` only, so `coalesce(false, 1)` returns `false` (not `1`) since
  `False is not None`; only an actual `null` value is skipped.
- **`if(cond, a, b)`** — special form, exactly 3 args required else `None`
  (`expr.py:629-630`); `cond` is passed through `_truthy` (§3); lazy branch evaluation as
  above.
- **`lower(s)` / `upper(s)`** (`expr.py:537-538`) — `_to_str(arg)` first (so this accepts
  numbers/bools too, stringified per §9, not just literal strings — e.g.
  `upper(5)` → `"5"`, `upper(true)` → `"TRUE"`); `None` if no args or `_to_str` yields `None`
  (i.e. arg is a list/dict/None). Uses Python `str.lower/upper` — **Unicode case-folding
  rules are Python's, not necessarily identical to SQL `lower()`/`upper()` for non-ASCII text**
  (e.g. Turkish dotless-I, German ß) — not tested here, flagged as a gap.
- **`contains(hay, needle)`** (`expr.py:488-499`) — exactly 2 args; `hay is None → False`
  (**not** `None` — this function never returns null for a null haystack, only `false`,
  `:492-493`); if `hay` is a list/tuple, membership via `_eq` (§4's typed equality, so
  `contains([1,2,3], "2")` is `False`, confirmed live) — **element-wise `_eq`, not substring**;
  otherwise both sides go through `_to_str` and it's Python `in` substring test
  (`:496-499`) — if either side fails to stringify (e.g. `hay` is a dict, or `needle` is a
  list), returns `False`, not `None`. Confirmed live: `contains([1,2,3], 2) -> True`;
  `contains([1,2,3], "2") -> False`; `contains("abcd","bc") -> True`.
- **`number(x)`** (`expr.py:540`) — literally `_to_num(x)` (§2), or `None` for zero args.
- **`string(x)`** (`expr.py:541`) — literally `_to_str(x)` (§9), or `None` for zero args.
- **`concat(...)`** (`expr.py:542`) — `"".join(_to_str(a) or "" for a in args)` — **`None`
  operands become the empty string, silently**, NOT propagated as an overall `None`
  (unlike almost every other function in this file). This is the one place where a `None`
  input does not make the whole call `None` — flag prominently, it's an easy thing for a
  compiler to get backwards by pattern-matching "expr is total, null propagates" everywhere.
- **`length(x)`** (`expr.py:543`) — Python `len()` of the arg if it's a str/list/tuple/dict,
  else `None` (including for numbers, bools, and zero args) — dict length is key-count
  (confirmed live: `length({'a':1,'b':2}) -> 2`).
- **`abs(x)` / `floor(x)` / `ceil(x)`** (`expr.py:544-546`) — `_to_num` first, `None` if that
  fails; `floor`/`ceil` explicitly `float(math.floor(...))`/`float(math.ceil(...))` — always
  returned as float, never Python `int`, matching `expr`'s float-only numeric model.
- **`round(x, ndigits=0)`** (`_fn_round`, `expr.py:517-527`) — `x` via `_to_num`; `ndigits`
  optional, defaults to `0`, itself coerced via `_to_num` then truncated to `int(...)`
  (so a fractional/string `ndigits` is accepted and truncated, e.g. `round(x, "2")` works,
  `round(x, 2.9)` behaves as `ndigits=2`); **explicit round-half-AWAY-FROM-ZERO**, chosen
  deliberately over both Python's own `round()` (banker's rounding) and JS's `Math.round`
  (half-toward-+∞) per the code comment (`expr.py:522-523`) — implemented as
  `sign(scaled) * int(abs(scaled) + 0.5) / factor` (`:524-527`). Confirmed live:
  `round(2.5) -> 3.0`, `round(-2.5) -> -3.0` (both away from zero, not toward +∞ — Python's
  native `round(-2.5)` would give `-2` under banker's rounding, and JS `Math.round(-2.5)`
  gives `-2` under half-toward-+∞; neither matches this function, confirming the comment is
  accurate and load-bearing); `round(2.345, 2) -> 2.35`; `round(1234.5, -2) -> 1200.0`
  (negative `ndigits` supported, rounds to the left of the decimal point). **Confirmed live
  against Postgres's two-arg `round(numeric, int)`** (which requires a cast to `numeric`,
  since the two-arg form does not accept `double precision`):
  `docker exec glp-strong-db psql -U glp_owner -d glp_strong -tAc "select
  round(-2.5::numeric,0), round(1234.5::numeric,-2);"` → `-3 | 1200` — **matches
  `_fn_round` exactly**, including the negative-number-away-from-zero case (`-3`, not `-2`)
  and the negative-`ndigits` case (`1200`, matching `round(1234.5,-2) -> 1200.0`). This is a
  direct, low-risk compile target *provided* the compiler always casts the operand to
  `numeric` before calling the two-arg `round` — a bare `double precision` value passed to
  the two-arg form is a Postgres type error, not a semantic mismatch, but still something the
  compiler must handle (`ROUND(x::numeric, n)`, not `ROUND(x, n)` on a float column).
- **`count(...)`** (`expr.py:548`) — via `_as_list` (`expr.py:462-466`: if exactly one arg AND
  it's a list/tuple, unwrap it as the operand list; otherwise treat the raw `args` list as the
  operand list — so `count(1,2,3)` and `count($.list_of_3)` both count 3 things, but
  `count($.list_of_3, $.other)` does NOT unwrap, it counts 2 top-level args). Counts entries
  that are **not `None`**, regardless of type — a string, a nested list, anything non-null
  counts (confirmed live: `count([1, null, 2, "x"]) -> 3.0`, i.e. `"x"` counts even though it
  isn't numeric). Always returns a float, never `None` even for an empty/all-null input
  (`sum(1 for x in ... if x is not None)` over an empty generator is `0`, cast to `float` by
  the lambda's `float(...)` wrapper at `:548` — so `count()` of nothing is `0.0`, NOT `None`,
  which is DIFFERENT from `sum`/`avg`/`min`/`max` below).
- **`sum(...)` / `avg(...)` / `min(...)` / `max(...)`** (`_fn_reduce`, `expr.py:502-514`,
  dispatched at `:549-552`) — also via `_as_list`, but then filters through `_to_num` (§2),
  **dropping any element that doesn't coerce to a number** (so, unlike `count`, a non-numeric
  string like `"x"` is silently excluded, while a numeric string like `"3"` IS included —
  confirmed live: `sum([1, null, 2, "x", "3"]) -> 6.0`, i.e. `1+2+3`, `"x"` dropped, `null`
  dropped, `"3"` coerced and included). **If the filtered numeric list is empty, ALL FOUR
  return `None`** (`expr.py:504-505`), not `0`/`0.0` — this is the opposite convention from
  `count`. `avg` divides by the count of numeric elements actually present (post-filter), not
  by the original arg count. `min`/`max` are plain Python `min`/`max` over the coerced float
  list (no tie-breaking concern since they're plain numeric comparisons).

**One-line rule per function, compressed**: every builtin except `if`, `concat`, and `count`
is null-propagating for at least one input path in the ordinary sense; `if` short-circuits
(must become `CASE WHEN`); `concat` turns null args into empty string rather than nulling the
whole result (must become `COALESCE(_to_str(arg),'')` per-argument, concatenated, not a
null-propagating `||`); `count` returns `0` not `NULL` on an empty/all-null operand set while
`sum`/`avg`/`min`/`max` return `NULL` (must NOT reuse one aggregate-null-handling pattern for
`count` vs the other four — Postgres's native `COUNT()` already returns `0` for zero rows and
`SUM`/`AVG`/`MIN`/`MAX` already return `NULL` for zero rows, which conveniently matches this
per-function split by accident of SQL's own aggregate conventions, but this was reasoned from
the code, not independently verified against a live Postgres aggregate in this pass — flagged
as a gap, and note these `expr` functions operate over a single JSON *list value*, not a SQL
row-set, so they'd compile to a JSONB-array-unnest-and-aggregate subquery, not a bare
`COUNT()`, and that translation's null-handling must be re-derived, not assumed identical just
because the words match).

---

## 11. Cross-cutting totality and NULL-propagation summary

Load-bearing overall claim, gathered from all sections above and stated once for the
compiler author: **`expr.py` never raises for data reasons** — the file's own docstring
states this as a design rule (`expr.py:17-19`) and every function surveyed above (§2-§10)
independently confirms it: bad numeric coercion → `None`, bad date parse → `None`,
divide/modulo by zero → `None`, out-of-range field access → `None`, wrong arg count/type to
any builtin → `None`, out-of-range date formatting → `None`. Only `parse()` itself can raise
(`ExprError`, syntax errors only, never data-dependent). **Postgres, by contrast, raises
concretely and by default** on the exact operations that Python here treats as total: bad
numeric cast (`invalid input syntax for type double precision`, confirmed live above),
division by zero (`ERROR: division by zero`, confirmed live above for both `1.0/0` and
`1.0/0.0`). **Every one of these must be wrapped in the compiler's SQL output** — a guard
cast/regex-check before any numeric cast, `CASE WHEN divisor = 0 THEN NULL ELSE ...` around
every `/` and `%`, and (per FRAMING.md §5's non-negotiable) any construct the compiler cannot
wrap this way must be a **named, reported fallback to in-memory evaluation**, never a bare SQL
expression that would raise or silently coerce differently from Python.

Second cross-cutting claim: **NULL-propagation is NOT uniform across the file** — this is the
single easiest place for a compiler author to introduce a silent divergence by assuming one
rule everywhere. The concrete inventory, all independently re-derived above:
- **Two-valued** (NULL only equals NULL, never propagates as "unknown"): `==`/`!=` (§4).
- **Three-valued** (either-NULL-operand → NULL result): `<`/`<=`/`>`/`>=` (§5), `+ - * / %`
  (§6, via `_to_num(None) is None` short-circuit at `expr.py:612-613`), `days_between`,
  `date_add`, `number()`, most single-arg scalar functions.
- **NULL treated as a concrete falsy/empty value, not propagated**: `contains(null, x) →
  false` not null (§10); `concat` treats a null arg as `""` (§10); `count` counts non-null
  entries and returns `0.0` (not null) for zero matches (§10); `coalesce` is explicitly built
  to skip nulls (§10); `_truthy(null) → false` (§3, used by `and`/`or`/`not`/`if`'s condition,
  none of which ever themselves return `null` — `and`/`or`/`not` always return a concrete
  `bool`, confirmed by their unconditional `and`/`or`/`not` Python expressions at
  `expr.py:594,596,598`, no `None`-passthrough path in any of the three).

A compiler that assumes "SQL NULL propagation" is a single interchangeable rule for the whole
grammar will get roughly half of these constructs wrong. Each construct's rule must be
individually encoded.

---

## 12. Explicit fixture cross-references used as ground truth in this document

- `-5 % 3 == -2`, `5 % -3 == 2` — `tests/fixtures/expr_vectors.json:11-12` (group
  `arithmetic`), confirming truncation-toward-zero modulo (§6).
- `5 % 0 == null` — `tests/fixtures/expr_vectors.json:16` (group `arithmetic`), confirming
  modulo-by-zero totality (§6).
- `10.5 % 3 == 1.5`, `0.5 % 0.1 == 0.09999999999999998`,
  `$.a % $.b == 1.4580013704758805` for `a=102410.01626280877, b=1.4580013704841797` —
  `tests/fixtures/expr_vectors.json:140-142` (group `modulo_fmod`), confirming IEEE-754
  fmod precision must be bit-exact (§6).
- Fixture has 130 total cases across 16 groups: `arithmetic`(11), `fields`(9),
  `null_propagation`(4), `comparison`(17), `boolean`(13), `dates`(13), `coalesce`(4),
  `strings`(11), `coercion`(10), `numeric_funcs`(11), `aggregates`(11), `conditional`(3),
  `composite`(4), `modulo_fmod`(3), `string_ecma`(4), `date_total`(2) — enumerated via
  `python3 -c "import json; ... group-by group['group']"` over
  `tests/fixtures/expr_vectors.json`, run during this recon. This document's per-construct
  claims map onto these groups (e.g. `string_ecma`'s 4 cases exist specifically to pin
  `_num_to_str`, §9; `date_total`'s 2 cases exist to pin the out-of-range totality behaviour
  in `_format_date_ms`, §7) but this pass did not exhaustively re-run every one of the 130
  cases against Python or SQL — that is the conformance-harness seat's job
  (FRAMING.md §8/finding #1), not this recon's.

---

## 13. Honest gaps — what this recon did NOT establish

- **Live Postgres was checked for, and results folded into the sections above**: `%` sign
  semantics (§6, both integer sign-cases, confirmed matches `math.fmod`); numeric-cast error
  behaviour (§2/§11, confirmed raises); division-by-zero error behaviour (§11, confirmed
  raises); JSONB negative-array-index access via `->` including both out-of-range directions
  (§8, confirmed matches `_resolve_field` exactly — direct low-risk compile target);
  numeric-to-text formatting `::text` against `_num_to_str`'s ECMA-262 rules across 4 sample
  values (§9, **confirmed to DIVERGE** on whole numbers, `"1.0"` vs `"1"`, and small-magnitude
  decimals, `"1e-05"` vs `"0.00001"` — this construct should be treated as forced fallback,
  not a compile target); `round(numeric, int)` for a negative number and negative `ndigits`
  (§10, confirmed matches `_fn_round` exactly, provided the compiler casts to `numeric`);
  year zero-padding in `to_char('YYYY-MM-DD')` for year 1 (§7, confirmed matches); and the
  `1e400`/NaN-through-arithmetic overflow leak (§3, **confirmed live** — `evaluate()` really
  does return raw Python `nan`/`inf`, not `None`, for this input; this was corrected from an
  earlier reasoned-only draft of this document).
- **Still NOT checked against live Postgres** (flagged inline at each section, not chased
  further per FRAMING.md stop-rules): the `0.5 % 0.1` float-fmod exact IEEE bit pattern (§6,
  only the integer sign-cases of `%` were verified, not this specific fractional case); string
  collation/ordering behaviour under the database's default vs. `C` collation for
  non-ASCII text (§5); `lower()`/`upper()` Unicode case-folding parity for non-ASCII text
  (§10, e.g. Turkish dotless-I, German ß); the `string_ecma` fixture group's actual 4 values
  run end-to-end through SQL (§9 sampled 4 *different*, hand-picked values that were
  sufficient to prove the divergence exists, not the fixture's own literal cases). These are
  exactly the kind of checks the conformance-harness seat (a different question on this panel,
  per FRAMING.md §4 finding #1) should run systematically against all 130 fixture cases — this
  recon hand-picked only the checks needed to resolve specific semantic ambiguities in the
  source code itself, and to decide, for each construct, whether the naive SQL translation is
  safe, divergent, or unverified.
- No JS-side (`frontend/lib/expr.js`) behaviour is covered here — out of scope, this question
  is Python-evaluator-only; the JS file is asserted byte-identical in spirit but not audited
  here (FRAMING.md's identical-tree claim covers the AST/grammar files, not a semantic
  line-by-line JS audit, which nothing in this recon performed).
