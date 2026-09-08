# T-23 — the raw-mode re-run

**The headline claim has a scope nobody wrote down.** *"Zero wrong numbers over 11,367
expressions"* is true, and it is true **of `py`-mode data only**. In `raw` mode — the shape of
any row written by something that is not this Python process — **the two engines disagree.**

**7 divergences in 204 cases.** Every one is an equality or an inequality. No arithmetic
diverges, and the reason is mechanical rather than lucky.

---

## 1. What T-6 actually ran, and how the gap hid

`spikes/T-1/analysis/fuzz/H_ast_fuzz.py:339` calls `run_case(src, rec, ctx)` — **no `mode`
argument**, so it takes `differ.py`'s default `mode="py"`. All 18 H batteries and the VB/VC
variants inherit it.

**T-6's `run_matrix.sh` has a variable called `mode`, and it is the comparison rule** (strict
vs recursive), not the ingestion mode. Its output filenames read
`H_sub_ordinary_efd1_strict.txt` — a reader scanning them sees "mode" varying and concludes the
axis was covered. It was a different axis.

T-6's own decision doc lists *"`raw`-mode data was not re-run"* as an open item, and T-6's
framing §5 said, of the one signal T-3 had already seen there, **"if that changes, it is a
finding."**

## 2. A negative result first, because it changes what the re-run can mean

**Re-running the same records with `mode="raw"` is very nearly a no-op**, and `differ.py:245`
says why:

```python
params["rec"] = json.dumps(record) if mode == "py" else raw
```

**In py mode the SQL side is already handed `json.dumps(record)` — the identical text.** The
only thing raw changes for such a record is that *Python* re-parses it, and for a
py-representable value that round trip returns the same object. Measured on four cases: 0 of 4
changed verdict.

**So the experiment only exists where the record itself cannot be built in Python** — a JSON
number carrying more precision or magnitude than a double. That is the population `py` mode
excludes *by construction*, which is exactly why 11,367 expressions could not have found any of
what follows.

## 3. The result

**204 expressions — 17 shapes over 12 raw-only JSON numbers, against the shipping runtime
(`runtime/runtime.sql`, variant C).**

| verdict | count | |
|---|---:|---|
| AGREE | 145 | |
| SQL_REFUSAL | 49 | the XPR01 magnitude guard on `1e309`, `-1e309`, `1e-400`. **Designed behaviour** — an allowed outcome, counted, never a pass and never a failure |
| **DIVERGE** | **7** | **wrong numbers** |
| BOTH_RAISE | 3 | neither side answered; nothing can be wrong |

### The seven

| expression | `a` | Python | SQL |
|---|---|---|---|
| `$.a == 0.1` | `0.1000000000000000000000001` | **True** | **False** |
| `$.a != 0.1` | `0.1000000000000000000000001` | **False** | **True** |
| `$.a == $.b` | `0.1000000000000000000000001` (b = 0.1) | **True** | **False** |
| `$.a == 0.1` | `0.1000000000000000055511151231257827` | **True** | **False** |
| `$.a != 0.1` | `0.1000000000000000055511151231257827` | **False** | **True** |
| `$.a == $.b` | `0.1000000000000000055511151231257827` | **True** | **False** |
| `$.a == 1` | `0.99999999999999999` | **True** | **False** |

**The second value is the exact decimal expansion of the double `0.1`.** A writer that
serialises a float at full precision — a perfectly ordinary thing for an ETL job to do —
produces it.

## 4. Why equality diverges and arithmetic does not

Measured, not reasoned:

```sql
SELECT '0.1000000000000000000000001'::jsonb = '0.1'::jsonb;                    -- false
SELECT xpr.f8('0.1000000000000000000000001'::jsonb) = xpr.f8('0.1'::jsonb);    -- true
```

**Arithmetic routes through `xpr.num` / `xpr.f8`, which coerces to `float8` — the same
precision Python's parse lands on, so the two agree.** Equality does not route through it: the
compiled predicate compares the **jsonb values directly**, and jsonb stores a `numeric` — exact
decimal, arbitrary precision. Python compares *after* a `float` parse, where the tail is gone.

So the divergence is not a rounding accident. It is **two different comparison domains**:
exact decimal on one side, IEEE double on the other, on inputs whose difference lives below the
double's resolution.

## 5. What this is, and what it is not

**It is not a new bug in the compiler.** Nothing here is a regression; T-6's fix stands and its
numbers are sound for what they measured.

**It is a blind spot in the battery that produced this project's headline claim.** `py` mode
cannot express these inputs, so a bigger `py` run — 100,000 expressions, a million — would
never find them. The gap is not sample size, it is **domain**.

**And it points at real data.** `differ.py` calls raw *"the shape of any row written by
something that is not this Python process (ETL, migration, psql, another service)"*, and T-7
established that **six of seven GIMS write paths never check the declared type**. Non-Python
writers are the norm, not the exception.

## 6. What is NOT claimed here

- **No frequency estimate.** 7-in-204 is the rate over a hand-picked adversarial set, not a
  rate over real data. What has been established is that the class is **non-empty and
  reachable**, not how often it fires.
- **No fix.** Making equality route through `xpr.f8` would close it and would change what
  equality *means* on exact data — that is a design decision with its own consequences, and it
  belongs to whoever owns the bar.
- **No claim about the other batteries.** Only the 17 shapes above were run in raw mode.

## Reproduce

```
docker exec autosql-corpus psql -U glp_owner -d postgres -c 'CREATE DATABASE t23_raw'
docker exec -i autosql-corpus psql -U glp_owner -d t23_raw -q < runtime/runtime.sql
AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=… dbname=t23_raw" \
  python spikes/T-23/raw_battery.py
```

Never port 55433. `spikes/` is frozen: `raw_battery.py` imports `differ.run_case` and modifies
nothing.
