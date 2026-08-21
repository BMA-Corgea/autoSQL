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
