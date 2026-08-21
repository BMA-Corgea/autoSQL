### What happens

The dashboard expression language is documented, in three places, as *total*: every operation
returns `null` rather than raising, and only a **syntax** error (at parse time) throws. Callers are
built on that promise — `api/dashboard/sources.py` wraps `parse()` in an error handler but calls
`evaluate()` bare, because `evaluate()` is not supposed to be able to fail.

It can. On `main`, `evaluate()` raises on ordinary data through **8 distinct mechanisms, across 9
source lines, in 4 different exception types**. Three of them (`round` with a large, small or
infinite second argument, over a literal first argument) need no stored data at all — they are
reachable from the expression text a tenant types, against an empty record.

The browser mirror of the same language, `frontend/lib/expr.js`, **is** total on these inputs. So
the live preview in the dashboard builder shows a value while the server, given the identical
expression and record, returns a 500 — which breaks the cross-runtime contract those two files exist
to uphold.

### Where it is, on `main`

The documented promise:

* `core/dashboard/expr.py:17-19` — *"**Total, not throwing.** Every operation returns `null` rather
  than raising on bad input... Only a *syntax* error (at `parse` time) raises `ExprError`."*
* `core/dashboard/expr.py:640` — `evaluate()`'s own docstring: *"Never raises for data reasons (→
  null)."*
* `design/dashboard_expr_grammar.md:4-5`, `:63-65`, `:146` — the same claim, three times, in the
  language spec.

The eight mechanisms, every one re-run against `main`'s `core/dashboard/expr.py`:

| # | line | exception | why | witness expression / record |
|---|---|---|---|---|
| 1 | `expr.py:430` | `OverflowError` | offset arithmetic is outside the `try` at `:418-426`, which only catches `ValueError` | `days_between($.d,"2024-01-02")` / `{"d":"0001-01-01T00:00:00+14:00"}` |
| 2 | `expr.py:521` | `OverflowError` | `int(_to_num(args[1]))` where the coerced value is infinite | `round($.a,$.n)` / `{"a":1.0,"n":"1e400"}` |
| 3 | `expr.py:525` | `OverflowError` | `10 ** ndig` is an unbounded integer; multiplying it by a float has to convert it | `round($.a,400)` / `{"a":1.0}` |
| 4 | `expr.py:526` | `OverflowError` | `int(abs(scaled) + 0.5)` where `scaled` already overflowed to infinity | `round($.a,3)` / `{"a":1.7976931348623157e308}` |
| 5 | `expr.py:527` | `ZeroDivisionError` | `r / factor` where `10 ** ndig` underflowed to `0.0` | `round($.a,-324)` / `{"a":1.0}` |
| 6 | `expr.py:545`, `:546` | `OverflowError` | `math.floor` / `math.ceil` of infinity; the lambdas only guard `is not None` | `floor($.a)` / `{"a":"1e400"}` |
| 7 | `expr.py:624` | `ValueError` | `math.fmod(inf, 2)`; the guard checks only `rn == 0` | `$.a % 2` / `{"a":"1e400"}` |
| 8 | `expr.py:375` (and `:377`) | `RecursionError` | `_eq` recurses through nested lists/dicts with no depth cap | `$.a == $.b` / two lists nested 498 deep |

Shared root cause behind mechanisms 2, 4, 6 and 7: `_to_num` returns `±inf` freely — from a JSON *string*
(`"1e400"`), from a JSON *number* (`1.7976931348623157e308`), or from ordinary arithmetic
(`1e200 * 1e200`) — and nothing downstream re-checks for a finite value before `int()`,
`math.floor`, `math.ceil` or `math.fmod`.

### How to reproduce

```python
import sys; sys.path.insert(0, ".")
from core.dashboard.expr import parse, evaluate

cases = [
    ('days_between($.d,"2024-01-02")', {"d": "0001-01-01T00:00:00+14:00"}),
    ('round($.a,$.n)',                 {"a": 1.0, "n": "1e400"}),
    ('round($.a,400)',                 {"a": 1.0}),
    ('round($.a,3)',                   {"a": 1.7976931348623157e308}),
    ('round($.a,-324)',                {"a": 1.0}),
    ('floor($.a)',                     {"a": "1e400"}),
    ('$.a % 2',                        {"a": "1e400"}),
    ('round(1.7976931348623157e308, 3)', {}),      # no stored data at all
]
for src, rec in cases:
    try:
        print(src, "->", evaluate(parse(src), rec, {"now": "2026-08-21T00:00:00Z"}))
    except Exception as e:
        print(src, "-> RAISED", type(e).__name__, e)
```

**Verified here (`main`, 2026-08-21) — 9 witnesses, 9 raises, 0 nulls:**

```
R1 date offset:     RAISED OverflowError: date value out of range                       | expr.py:430
R2 round inf ndig:  RAISED OverflowError: cannot convert float infinity to integer      | expr.py:521
R3 round ndig 400:  RAISED OverflowError: int too large to convert to float             | expr.py:525
R4 round DBL_MAX:   RAISED OverflowError: cannot convert float infinity to integer      | expr.py:526
R5 round ndig -324: RAISED ZeroDivisionError: float division by zero                    | expr.py:527
R6 floor 1e400:     RAISED OverflowError: cannot convert float infinity to integer      | expr.py:545
R7 mod inf:         RAISED ValueError: math domain error                                | expr.py:624
R8 deep eq:         RAISED RecursionError: maximum recursion depth exceeded             | expr.py:370 *
R2b literal only:   RAISED OverflowError: cannot convert float infinity to integer      | expr.py:526
```

`*` the frame reported for mechanism 8 is wherever the stack happened to run out inside `_eq`; the
recursion itself is the `_eq(...)` calls at `core/dashboard/expr.py:375` (lists) and `:377` (dicts).

The same seven witnesses through the browser mirror, `frontend/lib/expr.js`, under Node 22:

```
R1 days_between yr-1 +14:00    JS -> 738886.5833333334
R2 round($.a,$.n) n=1e400      JS -> null
R3 round($.a,400)              JS -> null
R4 round(DBL_MAX,3)            JS -> null
R5 round($.a,-324)             JS -> null
R6 floor("1e400")              JS -> null
R7 $.a % 2 @ 1e400             JS -> null
```

**Every one of the seven disagrees with Python.** On six of them JS returns `null` (the documented
behaviour) where Python raises; on the seventh JS returns a number where Python raises.

### Why it matters

* **Callers were written against the promise.** `api/dashboard/sources.py:147` and `:162` call
  `evaluate()` per row with no guard, precisely because the docstring says they don't need one. The
  consequence is a `HTTP 500` for the whole widget — filed separately.
* **Three of the eight need no stored data.** `round(1.0, 400)`, `round(1.0, -324)` and
  `round(1.0, 1e400)` are accepted by `parse()` without complaint and raise even on an empty
  record — `OverflowError: int too large to convert to float`, `ZeroDivisionError: float division
  by zero`, and `OverflowError: cannot convert float infinity to integer` respectively. (Writing
  the first argument as a field reference instead, e.g. `round($.x, 400)`, returns `null` on an
  empty record rather than raising: `_fn_round` short-circuits at `core/dashboard/expr.py:520`
  when the first argument is missing. The literal forms above are the reachable ones.) A tenant
  can type one into the dashboard builder and 500 their own widget.
* **The two runtimes are supposed to be interchangeable.** `core/dashboard/expr.py:10-14` and
  `frontend/lib/expr.js:3-8` both state that the two must produce the identical value for every
  fixture case. On these inputs they don't — the builder preview shows a value and the saved widget
  errors.
* **CI cannot see it.** `tests/fixtures/expr_vectors.json` (130 cases) has exactly one
  offset-bearing date (`"2026-07-01T00:00:00+02:00"`, mid-calendar) and calls `round` with a second
  argument of only `1` or `2`. The fixture's value range cannot reach any of the eight sites, so
  green is not evidence here.

### The smallest fix that would work

Make the documented contract true at the one place it is documented — `evaluate()` — so every caller
gets it for free and the Python side matches what the JS side already does:

```python
# core/dashboard/expr.py:639-641
def evaluate(ast: AST, record: Any, context: Optional[Dict[str, Any]] = None) -> Value:
    """Evaluate a parsed AST against one record. Never raises for data reasons (→ null)."""
    try:
        return _eval(ast, record if record is not None else {}, context or {})
    except (ArithmeticError, ValueError, TypeError, RecursionError):
        return None
```

(`ArithmeticError` is the parent of both `OverflowError` and `ZeroDivisionError`. `ExprError` is not
in the list and still propagates, as documented.)

This is three lines and closes all eight mechanisms at once. It is deliberately a blanket guard
rather than eight point fixes, because the eight sites are symptoms of one design gap — nothing
checks for a non-finite number between `_to_num` and the functions that cannot accept one.

Worth doing alongside, but not required to close this issue:

* fix `_to_num` to return `None` instead of `±inf` (`core/dashboard/expr.py`), which removes the
  shared root cause of mechanisms 2, 4, 6 and 7;
* add the eight witnesses above to `tests/fixtures/expr_vectors.json`, so the Python and JS runtimes
  are pinned to the same answer on them.
