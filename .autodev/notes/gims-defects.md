# GIMS defect reports — four issues, ready to file

Drafted 2026-08-21. Target repo: `BMA-Corgea/GIMS-Project`, branch **`main`** at commit **`7b7a049`**.

Every file:line below was read on `main` (via the up-to-date checkout at
`GUTS/spine/L1-memory/gims-ledger`, `origin/main` fetched 2026-08-21), **not** on the stale
`refactor/foundation` checkout at `../GIMS-Project`. `api/dashboard/sources.py`,
`core/dashboard/expr.py` and `frontend/lib/dashboard/widgets.jsx` are byte-identical on both
branches; `core/errors.py` is not, and the line numbers here are `main`'s.

All four defects are **present on main**. Each was re-verified by running `main`'s own code, not by
trusting the research notes — every "Verified here" block below is real output from this machine.
The GIMS issue tracker currently has **no open or closed issues** (`gh issue list --state all`
returned `[]`), so none of these are duplicates.

---

## Issue 1

**Title:** `One record with an out-of-range date turns a whole dashboard widget into a 500`

*(74 characters)*

### What happens

A dashboard widget whose data source uses a `derive` or a `where` expression is evaluated one record
at a time, in Python, in the API process. If **any single record** in the scan holds a date string
that the evaluator cannot handle, the evaluator raises, nothing between it and FastAPI catches the
exception, and the request ends as `HTTP 500 INTERNAL_ERROR`. The widget renders nothing — not a
partial result, not an error message about that row, just an empty card.

One row in twenty thousand is enough, and its position in the scan does not matter.

The record that triggers it looks completely ordinary:

```json
{"id": "P", "d": "0001-01-01T00:00:00+14:00"}
```

That is a legal ISO date string. Any client, importer or integration can write it. The evaluator
parses the calendar part successfully, then subtracts the `+14:00` timezone offset — which pushes
the result before year 1, which Python's `datetime` cannot represent.

### Where it is, on `main`

* `core/dashboard/expr.py:409-431` — `_parse_date_ms`. The `try` at `:418` wraps only the
  `datetime(...)` constructor and catches only `ValueError` (`:425-426`). The offset subtraction at
  **`core/dashboard/expr.py:430`** sits *outside* that `try`, and it raises `OverflowError`, which
  `except ValueError` does not catch:

  ```python
  418      try:
  419          dt = datetime(
  ...
  425      except ValueError:
  426          return None
  427      if off and off != "Z":
  428          sign = 1 if off[0] == "+" else -1
  429          digits = off[1:].replace(":", "")
  430          dt = dt - timedelta(minutes=sign * (int(digits[:2]) * 60 + int(digits[2:4])))
  ```

* `api/dashboard/sources.py:147` — `_apply_derive` calls `evaluate(...)` per row. **Not** inside a
  `try`.
* `api/dashboard/sources.py:162` — `_filter_rows` calls `evaluate(...)` per row. **Not** inside a
  `try`.
* `api/dashboard/sources.py:121-130` — `_compile` wraps `parse()` in an `AppError`, so a *syntax*
  error becomes a clean 400. Nothing gives `evaluate()` the same treatment.
* `api/dashboard/sources.py:330-336` — the public docstring of `resolve()` promises the opposite of
  what happens: *"Raises `AppError` (400) for a malformed spec / expression; **data problems degrade
  to empty/None, never crash**."*
* `core/errors.py:237-241` — the catch-all handler. `OverflowError` is not an `HTTPException`, so it
  lands here and becomes `status_code=500`, `INTERNAL_ERROR`.
* `api/routers/dashboards/routes.py:237-245` — `POST /dashboards/{project}/resolve`, the endpoint the
  widget calls. Line `:245` is `return sources.resolve(...)`, unguarded.

### How to reproduce

From the repo root on `main`:

```python
import sys; sys.path.insert(0, ".")
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.errors import register_error_handlers
from api.dashboard import sources

rows = [{"id": "R0", "d": "2026-01-01"},
        {"id": "P",  "d": "0001-01-01T00:00:00+14:00"},   # <-- the one bad row
        {"id": "R2", "d": "2026-02-01"}]
sources.get_noun_items = lambda p, n: [dict(r) for r in rows]

app = FastAPI(); register_error_handlers(app)

@app.post("/resolve")                       # mirrors api/routers/dashboards/routes.py:237-245
def _resolve(body: dict):
    return sources.resolve(body["source"], Path("."), {"now": "2026-08-21T00:00:00Z"})

c = TestClient(app, raise_server_exceptions=False)
src = {"type": "noun", "noun_type": "X",
       "derive": {"age": 'days_between($.d,"2024-01-02")'}}
print(c.post("/resolve", json={"source": src}).status_code)
```

**Verified here (`main`, 2026-08-21):**

```
poison row + derive    HTTP 500  body={"error_code":"INTERNAL_ERROR","message":"Internal server error",...}
poison row + where     HTTP 500  body={"error_code":"INTERNAL_ERROR","message":"Internal server error",...}
control, no expr       HTTP 200  body={"records":[{"id":"R0",...},{"id":"P",...},{"id":"R2",...}]}
```

The uncaught traceback ends:

```
File ".../api/dashboard/sources.py", line 353, in resolve
File ".../api/dashboard/sources.py", line 147, in _apply_derive
    row[name] = evaluate(ast, row, context)
File ".../core/dashboard/expr.py", line 641, in evaluate
File ".../core/dashboard/expr.py", line 635, in _eval
File ".../core/dashboard/expr.py", line 472, in _fn_days_between
File ".../core/dashboard/expr.py", line 430, in _parse_date_ms
    dt = dt - timedelta(minutes=sign * (int(digits[:2]) * 60 + int(digits[2:4])))
OverflowError: date value out of range
```

Position does not matter — with the bad row at index 0, 5 or 9 of a 10-row list, both
`_apply_derive` and `_filter_rows` raise; with the bad row removed, both return normally (9 rows and
5 rows respectively).

### Why it matters

* **Blast radius is the entire widget, from one row.** There is no partial result and no per-row
  skip. A tenant sees a blank card and has no way to tell which record caused it.
* **The failure mode is a 500, not a 4xx.** It reads to whoever is on call as a server fault rather
  than as bad data, and it emits a full traceback into the logs on every poll — dashboards refresh,
  so this repeats indefinitely until the record is found and edited.
* **A 500 is loud but useless.** The response carries no indication of which row, which field or
  which expression failed.
* **It contradicts a documented contract** (`api/dashboard/sources.py:334-336`) that other code and
  future work are entitled to rely on.
* **Nothing in CI catches it.** The cross-runtime fixture `tests/fixtures/expr_vectors.json` (130
  cases) contains exactly one offset-bearing date, `"2026-07-01T00:00:00+02:00"` — a mid-calendar
  date nowhere near the year-1 boundary. The fixture cannot reach this code path, so it is green.

### The smallest fix that would work

Guard the two per-row `evaluate()` calls so a bad row degrades to `null` / drops out instead of
killing the request. That restores the `resolve()` docstring's promise regardless of *which*
evaluator bug is behind the raise:

```python
# api/dashboard/sources.py:146-147, in _apply_derive
        for name, ast in compiled:
            try:
                row[name] = evaluate(ast, row, context)
            except Exception:
                row[name] = None
                bad_rows += 1
```

```python
# api/dashboard/sources.py:161-163, in _filter_rows
        if where_ast is not None:
            try:
                keep = truthy(evaluate(where_ast, row, context))
            except Exception:
                keep = False
                bad_rows += 1
            if not keep:
                continue
```

and surface the count in `resolve()`'s return value alongside `truncated`, so the UI can say
"3 records could not be evaluated" rather than showing a silently short list.

(The narrower fix for *this particular* date bug — moving the offset arithmetic inside the `try` at
`core/dashboard/expr.py:418` and catching `OverflowError` as well as `ValueError` — is worth doing
too, but it only closes one of eight ways the evaluator can raise. See the separate issue on the
evaluator's totality contract.)

---

## Issue 2

**Title:** `Postgres and SQLite disagree on records carrying both run_id and _runID`

*(70 characters)*

### What happens

GIMS looks up a record field tolerantly: if the exact key is not present, it retries after
lowercasing the key and deleting spaces, underscores and hyphens, so a dashboard filter on `run_ID`
finds a record keyed `run id`, `RunID` or `runid`. That is deliberate and there is a test locking it
in place.

The problem is what happens when **two different keys in the same record normalise to the same
thing**. `find_actual_key` walks the record's keys in whatever order they arrive and returns the
first one that matches. So the answer depends on the order the keys came out of storage — and the
two storage backends GIMS supports return them in **different orders**.

* The local SQLite store keeps the record as a JSON **string**, so the keys come back in the exact
  order they were written.
* The Postgres store keeps the record in a `JSONB` column. `JSONB` is a parsed, normalised
  representation, not the original text — Postgres discards the document's key order and stores keys
  sorted by length first, then alphabetically. They come back in that sorted order instead.

So the same record, read through the two backends, resolves the same tolerant filter to a
**different key, holding a different value**, with no error on either side.

This is not hypothetical and it is not about some future migration: **`main` already ships both
backends**, and the Postgres one already uses `JSONB`.

### Where it is, on `main`

* `api/storage_aws.py:33-40` — the Postgres table: `data JSONB NOT NULL`.
* `core/storage/sql.py:122-129` — the SQLite table: `data TEXT NOT NULL`.
* `core/storage/factory.py:153-159` — `get_record_store()` picks between them:
  *"RDS enabled -> Postgres/JSONB adapter... Otherwise -> the unified-SQL `instances` table in the
  project's local `objects.db`."*
* `core/deep_search.py:29-39` — `find_actual_key`. The whole mechanism:

  ```python
  35      want = _norm_key(desired_key)
  36      for k in obj.keys():          # <-- first match in key order wins
  37          if _norm_key(k) == want:
  38              return k
  39      return None
  ```

  `_norm_key` is at `core/deep_search.py:19-26` (lowercase, drop ` `, `_`, `-`).

* `api/dashboard/sources.py:74` — `_field_value` calls it, which is what
  `_pass_filters` (`api/dashboard/sources.py:88-96`) and `_apply_sort`
  (`api/dashboard/sources.py:177`) use for every dashboard `filters` and `sort` field.
* `api/iostore/nouns.py:52-60` — `get_noun_items`, the read seam the dashboard's noun source uses,
  goes straight through `get_record_store(...).list_records(...)`.
* `api/storage_aws.py:693-694` and `:728-731` — the Postgres read path decodes the `JSONB` cell into
  a Python dict; the key order it hands back is Postgres's, not the writer's.
* Other callers of the same function, so the blast radius is wider than dashboards:
  `core/deep_search.py:88`, `:216`, `:231`, `:244`, `:251`, `:365` (primary-ID resolution in search).

### How to reproduce

Postgres side — no table needed, this is pure value behaviour (run against any PG 16):

```sql
SELECT ('{"run_id":"","_runID":"one-body-phase-1"}'::jsonb)::text;
```

**Verified here (PostgreSQL 16.14):**

```
{"_runID": "one-body-phase-1", "run_id": ""}
```

The keys came out in the opposite order to the way they went in. A four-key check makes the rule
visible — shortest key first, then alphabetical:

```
input:  {"run_id":…, "_runID":…, "zz":…, "a":…}
jsonb:  a, zz, _runID, run_id
json:   run_id, _runID, zz, a          <-- the non-binary json type, which does preserve order
```

Python side, using `main`'s own `find_actual_key`:

```python
import json
from core.deep_search import find_actual_key

sqlite_text = '{"run_id":"","_runID":"one-body-phase-1"}'          # SQLite TEXT: as written
jsonb_text  = '{"_runID": "one-body-phase-1", "run_id": ""}'       # what Postgres returned

for label, txt in (("SQLite", sqlite_text), ("Postgres", jsonb_text)):
    row = json.loads(txt)
    k = find_actual_key(row, "runID")
    print(label, "->", k, "=", repr(row[k]))
```

**Verified here (`main`, 2026-08-21):**

```
SQLite TEXT path       keys in order ['run_id', '_runID']
     filter 'runID'   -> resolves key 'run_id'   value ''
     filter 'run id'  -> resolves key 'run_id'   value ''
     filter 'RUN_ID'  -> resolves key 'run_id'   value ''
Postgres jsonb path    keys in order ['_runID', 'run_id']
     filter 'runID'   -> resolves key '_runID'   value 'one-body-phase-1'
     filter 'run id'  -> resolves key '_runID'   value 'one-body-phase-1'
     filter 'RUN_ID'  -> resolves key '_runID'   value 'one-body-phase-1'
```

Same record, same query, two different answers — one an empty string, the other a real run ID.

### Why it matters

**Records like this already exist, in bulk, in the stores on this machine.** A read-only census of
the local `instances` tables (`mode=ro&immutable=1`, so nothing was written), run 2026-08-21:

| store | dict rows | rows with two keys normalising the same | colliding pair |
|---|---:|---:|---|
| `projects/guts-ledger/objects.db` | 17,637 | **4,228 (24.0%)** | `run_id` / `_runID` |
| `projects/guts/objects.db` | 12,109 | **1,966 (16.2%)** | `run_id` / `_runID` |
| `projects/guts-code/objects.db` | 6,710 | 0 | — |

In **4,216 of the 4,228** colliding rows (99.7%) the two keys hold **different values** — typically
`run_id = ""` against `_runID = "one-body-phase-1"` or `"WO-ED6D7224"`. So this is not a
distinction without a difference; it is the difference between a blank field and the actual run.

(These are live stores, so the totals move as rows are appended — an earlier read of the same tables
gave 17,345 / 4,166 and 12,095 / 1,966. The *rate* and the colliding pair have been identical at
every read.)

Concretely:

* A dashboard filtered or sorted on `runID` returns **different rows** depending on whether the
  deployment runs on SQLite or on Postgres.
* Neither backend reports anything. There is no warning, no log line, no error — just a different
  answer.
* Moving an existing project from local to RDS silently changes what its saved dashboards show.
* Because the tolerant lookup is also used by search's primary-ID resolution
  (`core/deep_search.py:88`, `:244`, `:251`), the same ambiguity can steer which record is treated
  as the match.

The tolerant behaviour itself is locked by
`tests/test_dashboard_sources.py:169-177` (`test_tolerant_and_dotted_field_access_in_filters`), so
it cannot simply be removed.

### The smallest fix that would work

Make `find_actual_key` **deterministic**, so both backends give the same answer. Collect every
matching key instead of returning the first, and when there is more than one, pick by a rule that
does not depend on storage:

```python
# core/deep_search.py:29-39
def find_actual_key(obj: dict, desired_key: str) -> str | None:
    want = _norm_key(desired_key)
    if desired_key in obj:            # an exact key always wins
        return desired_key
    matches = [k for k in obj.keys() if _norm_key(k) == want]
    if not matches:
        return None
    if len(matches) > 1:
        log.warning("ambiguous tolerant key match", {"wanted": desired_key, "matched": sorted(matches)})
    return sorted(matches)[0]         # stable regardless of storage key order
```

That is a behaviour change for the colliding rows (they will now consistently resolve `_runID`
rather than "whichever came first"), but it is the minimum needed for the two backends to agree, and
the warning gives someone a way to find the records that need their duplicate keys cleaned up.

---

## Issue 3

**Title:** `Expression evaluator documented as never raising, but raises 8 ways on data`

*(73 characters)*

### What happens

The dashboard expression language is documented, in three places, as *total*: every operation
returns `null` rather than raising, and only a **syntax** error (at parse time) throws. Callers are
built on that promise — `api/dashboard/sources.py` wraps `parse()` in an error handler but calls
`evaluate()` bare, because `evaluate()` is not supposed to be able to fail.

It can. On `main`, `evaluate()` raises on ordinary data through **8 distinct mechanisms, across 9
source lines, in 4 different exception types**. Three of them (`round` with a large, small or
infinite second argument) need no unusual stored data at all — they are reachable from the
expression text a tenant types, with an empty record.

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

Shared root cause behind #2, #4, #6 and #7: `_to_num` returns `±inf` freely — from a JSON *string*
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

`*` the frame reported for #8 is wherever the stack happened to run out inside `_eq`; the
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
* **Three of the eight need no stored data.** `round($.x, 400)`, `round($.x, -324)` and
  `round(1.7976931348623157e308, 3)` are accepted by `parse()` without complaint and raise on an
  empty record. A tenant can type one into the dashboard builder and 500 their own widget.
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
  shared root cause of #2/#4/#6/#7;
* add the eight witnesses above to `tests/fixtures/expr_vectors.json`, so the Python and JS runtimes
  are pinned to the same answer on them.

---

## Issue 4

**Title:** `The 20,000-row dashboard scan cap changes the answer, not just the speed`

*(72 characters)*

### What happens

A dashboard widget's data source loads every candidate record into memory, then keeps the first
20,000 and throws the rest away — **before** applying the widget's `filters`, `where`, `sort` and
`limit`. Whatever was in rows 20,001 and beyond is never looked at.

So on a collection larger than 20,000 records, the widget is not showing you "the top 50, computed a
bit slower". It is showing you "the top 50 *of an arbitrary 20,000-record slice*", and the rows that
should have been in the answer may all be in the part that was discarded.

The UI reports this with a badge that says **`capped`**, with the tooltip **"Result capped for
performance"**. That is the wrong word: nothing about the answer is late, it is *different*.

The 20,000 rows that survive are whichever ones the store happened to return first — neither the
SQLite nor the Postgres read issues an `ORDER BY`, so it is not a defined subset either.

### Where it is, on `main`

* `api/dashboard/sources.py:57-61` — the cap and its stated rationale:

  ```python
  57  # Safety cap: v1 materialises every candidate row in memory before filtering. This bounds
  58  # how many raw rows a single widget will scan so a pathological collection can't exhaust
  59  # memory; `truncated` is surfaced so the UI can warn. (Pushdown filtering removes this.)
  60  MAX_SCAN = 20_000
  ```

* `api/dashboard/sources.py:347-357` — the truncation, and the fact that it happens first:

  ```python
  347      raw = loader(project_path, source)
  348      truncated = len(raw) > MAX_SCAN
  349      if truncated:
  350          log.warning("dashboard source hit MAX_SCAN cap", {"type": stype, "scanned": len(raw)})
  351      rows = raw[:MAX_SCAN] if truncated else raw
  352
  353      rows = _apply_derive(rows, source.get("derive"), ctx)
  354      rows = _filter_rows(rows, source.get("filters"), source.get("where"), ctx)
  355      rows = _apply_sort(rows, source.get("sort"))
  356      rows = _apply_limit(rows, source.get("limit"))
  357      return {"records": rows, "count": len(rows), "truncated": truncated}
  ```

* `frontend/lib/dashboard/widgets.jsx:277` — what the tenant is told:

  ```jsx
  {state.data?.truncated && <span className="w-trunc" title="Result capped for performance">capped</span>}
  ```

* `core/storage/sql.py:342-347` and `api/storage_aws.py:728-731` — `list_records` on both backends,
  neither with an `ORDER BY`. Which 20,000 rows survive is therefore undefined.

Note the stated rationale does not hold either: `raw` is fully materialised at `:347` *before* the
slice at `:351`, so the cap bounds how many rows are *evaluated*, not how much memory is allocated.

### How to reproduce

A synthetic collection shaped like a "near-due items" widget — roughly 5% of records fall inside a
7-day window, sorted by due date, limit 50 — run through `main`'s own `sources.resolve`, once with
the shipped cap and once uncapped, comparing the two answers:

```python
import sys, random; sys.path.insert(0, ".")
from pathlib import Path
from datetime import datetime, timedelta, timezone
from api.dashboard import sources

REAL_CAP, NOW = sources.MAX_SCAN, "2026-08-21T00:00:00Z"
BASE = datetime(2026, 8, 21, tzinfo=timezone.utc)

def corpus(n, seed=7):
    rng = random.Random(seed); out = []
    for i in range(n):
        mins = rng.randrange(0, 7*24*60) if rng.random() < 0.05 else rng.randrange(30*24*60, 900*24*60)
        out.append({"id": f"S-{i:07d}",
                    "status": "open" if rng.random() < 0.6 else "closed",
                    "due_date": (BASE + timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out

SRC = {"type": "noun", "noun_type": "X",
       "where": 'days_between(today(), $.due_date) < 7 and $.status == "open"',
       "sort": {"field": "due_date", "dir": "asc"}, "limit": 50}

def run(rows, cap):
    sources.MAX_SCAN = cap
    sources.get_noun_items = lambda p, t, _r=rows: [dict(r) for r in _r]
    return sources.resolve(SRC, Path("."), {"now": NOW})

for n in (1_000, 10_000, 20_000, 22_000, 25_000, 100_000, 1_000_000):
    rows = corpus(n)
    truth = [r["id"] for r in run(rows, 10**12)["records"]]     # uncapped = the right answer
    got   = [r["id"] for r in run(rows, REAL_CAP)["records"]]   # what the widget shows
    print(n, f"{100*len(set(truth)&set(got))/len(truth):.0f}% of the true top 50",
          "rank-1 correct" if truth[:1] == got[:1] else "RANK-1 WRONG")
sources.MAX_SCAN = REAL_CAP
```

**Verified here (`main`, 2026-08-21):**

```
     rows  truncated  qualifying  examined    never examined  top-50 recall  rank-1 ok
--------------------------------------------------------------------------------------
    1,000      False          33     1,000          0 (  0%)           100%        yes
   10,000      False         304    10,000          0 (  0%)           100%        yes
   20,000      False         613    20,000          0 (  0%)           100%        yes
   22,000       True         670    20,000         57 (  9%)            88%        yes
   25,000       True         756    20,000        143 ( 19%)            78%        yes
  100,000       True       2,997    20,000      2,384 ( 80%)            14%         NO
1,000,000       True      29,831    20,000     29,218 ( 98%)             0%         NO
```

Read the last row: of the 29,831 records that genuinely qualify, **29,218 (98%) were never looked
at**, **none** of the 50 rows displayed belong in the true top 50, and the record shown at rank 1 is
not the real rank-1 — under a badge saying the result was capped *for performance*.

(An independent measurement against a Postgres-backed rig, using a coarser sort key, gave
100% / 88% / 38% / 4% at 20k / 25k / 100k / 1M. The exact percentages depend on how the qualifying
rows are distributed; the direction and the mechanism are the same. Degradation was monotonic in
both.)

### Why it matters

* **The widget answers a different question than the one asked, and says nothing.** "Show me the 50
  most overdue samples" quietly becomes "show me the 50 most overdue samples among an undefined
  20,000-row slice."
* **The badge actively misleads.** "Result capped for performance" tells a tenant the number is
  slow-but-right. It is fast-but-wrong. Someone acting on a near-due or out-of-spec dashboard is
  being shown a list that can be 100% wrong.
* **Which rows survive is undefined**, because neither backend orders the read
  (`core/storage/sql.py:342-347`, `api/storage_aws.py:728-731`). The same widget can give different
  answers on two consecutive loads if the storage layer returns rows in a different order.
* **The stated justification does not hold.** The cap is documented as protecting memory
  (`api/dashboard/sources.py:57-59`), but the full row set is already materialised at `:347` before
  the slice at `:351`. It caps evaluation, not allocation.
* **It is not far off today.** The largest collection in the local stores is 17,430 records —
  87% of the cap. One busy project crosses it, and nothing announces that the dashboards changed
  meaning.

### The smallest fix that would work

Apply the cap **after** the filter, so the widget answers the right question and `truncated` means
"there was more than we could show" rather than "we may have thrown away the answer":

```python
# api/dashboard/sources.py:347-357
    raw = loader(project_path, source)

    rows = _apply_derive(raw, source.get("derive"), ctx)
    rows = _filter_rows(rows, source.get("filters"), source.get("where"), ctx)
    rows = _apply_sort(rows, source.get("sort"))

    truncated = len(rows) > MAX_SCAN
    if truncated:
        log.warning("dashboard source hit MAX_SCAN cap",
                    {"type": stype, "scanned": len(raw), "matched": len(rows)})
        rows = rows[:MAX_SCAN]

    rows = _apply_limit(rows, source.get("limit"))
    return {"records": rows, "count": len(rows), "truncated": truncated}
```

Memory is unchanged — `raw` was already fully materialised either way — and the answer becomes
correct. The cost is CPU: the expression evaluator now runs on every candidate row instead of the
first 20,000.

If that cost is judged unacceptable and the cap must stay a *scan* cap, then the minimum acceptable
change is to stop calling it a performance cap. `truncated` must be reported as
**"this result is incomplete — records were not examined"**, the badge at
`frontend/lib/dashboard/widgets.jsx:277` must say so, and the response should carry how many rows
were skipped so a tenant can tell how wrong the number in front of them might be.
