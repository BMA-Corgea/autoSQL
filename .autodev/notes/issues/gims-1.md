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
