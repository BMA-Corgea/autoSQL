# `runtime/` — autoSQL's shipping SQL runtime

`runtime.sql` installs schema `xpr`: **21 functions** that give Postgres the same
value semantics as GIMS's Python expression evaluator (`core/dashboard/expr.py`), so a
dashboard expression compiled to SQL answers what the Python pane answers.

## The one rule

**`runtime.sql` is generated. Never edit it.**

```
python3 runtime/generate.py            # regenerate
python3 runtime/generate.py --check    # exit 1 if the committed file is stale
```

Edit `runtime.sql.in` — the template — and regenerate.

## Why it is generated, and not just a file

Three tables in it are derived from the **running Python's** `unicodedata`: the 670
non-ASCII decimal digits, the digits they map to, and Python's 29-code-point whitespace
set.

Python's `float()` accepts *any* Unicode decimal digit by its numeric value — `float("１２３")`
is `123.0`. Postgres has no equivalent: `[[:digit:]]` matches ASCII only, and its ctype
classes `１` as `[[:alpha:]]`, so the obvious tricks do not work either. The runtime closes
the gap by mapping those code points onto `0`–`9` before the numeric gate.

**Freeze that table as a literal and a Python upgrade splits the two engines silently.**
Python starts coercing a digit the SQL mapping has never heard of, the divergence class T-6
closed reopens, a dashboard shows a wrong number, and not one line of code has changed.

`runtime/tests/test_runtime.py::test_the_generated_runtime_is_not_stale` is what stands
between this project and that. **If it fails after a Python upgrade, do not just regenerate
and commit** — check whether the digit set itself moved, because that means the two engines
have drifted apart and the compiled SQL has been wrong for as long as the new interpreter
has been in use.

## The nesting in `xpr.num` is load-bearing

`translate()` runs **inside** the failure branch, after the plain-ASCII numeric gate has
already missed. Hoisting it above the gate makes every ordinary numeric string pay for a
670-character mapping: **852 ms → 4553 ms per 300k coercions, 5.3×**, measured in T-6. Nested,
it costs nothing measurable (812 ms against an 852 ms baseline).

That matters more than it sounds: in the one tenant project examined (T-5), **every
number-declared field is stored as text**, so coercion is the common path, not an edge case.

Two tests hold it there — a structural one on the template and a differential timing one that
fails if the ASCII path stops being faster than the fallback.

## Where this came from

| | |
|---|---|
| **T-1** | built the prototype and the compiler |
| **T-3** | found the compiled SQL returns wrong numbers; catalogued the mechanisms |
| **T-5** | measured whether the trigger occurs in real data (0 of 144 — but GIMS's CSV import admits it by design) |
| **T-6** | fixed and re-ran: 0 wrong numbers over 11,367 expressions, and found that T-3's premise — that SQL could not cheaply match Python — was false |
| **T-8** | this directory: promoted the runtime out of the spike, made the mapping regenerable |

**The spike copies under `spikes/` are frozen evidence, not source.**
`spikes/T-1/proto/runtime.sql` (`1c58d548a6045aa6…`) and `spikes/T-6/runtime.sql`
(`871b1b4c2df95719…`) have their digests cited in T-3's and T-6's findings and in all 42 of
T-6's battery outputs. Editing either breaks the chain that lets anyone re-derive those
results. A test asserts they have not moved.

## Running the tests

Pure-Python guards run anywhere. The database tests need a throwaway Postgres — **never
port 55433, which is a live database**:

```
docker run -d --name autosql-t8-db -e POSTGRES_PASSWORD=throwaway \
  -e POSTGRES_USER=glp_owner -e POSTGRES_DB=autosql_spike \
  -p 55434:5432 pgvector/pgvector:pg16
docker exec -i autosql-t8-db psql -U glp_owner -d autosql_spike < runtime/runtime.sql
AUTOSQL_RUNTIME_DSN="host=127.0.0.1 port=55434 user=glp_owner password=throwaway dbname=autosql_spike" \
  demo/.venv/bin/python -m pytest runtime/tests -q
```

## Known, and not this directory's job

- **The float-digit setting must be pinned to 1** or the value channel truncates and returns
  short numbers (62–66 wrong answers at the other settings, T-6). Nothing here enforces it —
  that is **T-9**.
