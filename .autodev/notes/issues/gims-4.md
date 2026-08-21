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
  58  # Safety cap: v1 materialises every candidate row in memory before filtering. This bounds
  59  # how many raw rows a single widget will scan so a pathological collection can't exhaust
  60  # memory; `truncated` is surfaced so the UI can warn. (Pushdown filtering removes this.)
  61  MAX_SCAN = 20_000
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
  (`api/dashboard/sources.py:58-60`), but the full row set is already materialised at `:347` before
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
