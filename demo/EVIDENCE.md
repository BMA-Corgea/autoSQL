# T-2 — the build's evidence pack

> **SUPERSEDED IN PARTICULARS — 2026-08-23 (GA-7, Evan's form answers q3 and q4).** This record
> was produced against the build as it stood on 2026-08-22 and is kept intact as evidence of that
> run — nothing below has been rewritten. After it was produced, two of Evan's own decisions
> changed the build, so the following particulars no longer describe the current tree:
>
> 1. **AC-35 was re-scoped** (q3) to the seven files the ticket vendors plus the `__pycache__`
>    window — the two suite failures below (§1.1 of the verify record / the standing red the
>    evidence record discloses) are gone, not by his checkouts becoming clean but by the criterion
>    no longer ranging over his own unrelated edits.
> 2. **T-3's corrected `runtime.sql` was adopted** (q4). The vendored copy is now sha256
>    `1c58d548a6045aa6698b07c167ceb3391a60c2f43b9bd4ff15cf914e6cf7e93d` (472 lines, 309-digit
>    guard, named `XPR01` refusal past DBL_MAX — no longer a silent NULL). Consequences, all
>    measured on the reseeded stack: `max($.l)` over `[1e300, 1]` now **agrees** at `1e+300`;
>    **step 11's shown disagreement moved** to `max($.m)` over `["１２３", 1]` — SQL `1` beside
>    Python `123`, the Unicode-digit gap T-3 measured as surviving the fix; `edge-04`/`edge-05`
>    straddle DBL_MAX itself (`xpr.f8` answers `1.7976931348623155e+308` just below, raises
>    `XPR01` just above); `$.g` picks are probe-refused naming `edge-05` before any statement, so
>    the reachable float8-overflow (22003) vehicle is now `$.a * $.a`; and the seed digest is
>    `65d83e813f47aebd100723723138ba40`.
>
> The current behaviour is asserted by the suite (`./run-demo test`) and recorded in the dated
> notes beside AC-13/AC-17/AC-22/AC-35 in `.autodev/specs/T-2.md` and B15/B24 in
> `.autodev/specs/T-2-plan.md`. T-6 will change the runtime again (the q5 ruling), after which a
> second such update is due.

Plan §6.4, item by item: **not "the tests pass" but numbers.** Everything
below was produced by driving the running demo, not by reading the code.

| | |
|---|---|
| Produced by | work item **W17** — the walkthrough end to end |
| Against | the demo's own database on `127.0.0.1:55440`, app on `127.0.0.1:8787` |
| How | `POST /api/pick` for every step, through `fastapi.testclient`, the same route the screen posts to |
| Seeded rows | 10,410 — 8,400 `noun:Heartbeat`, 2,000 `noun:Sample`, 10 `noun:EdgeCase`, all invented |

**All the data below is invented.** Nothing here describes a real sender, a
real customer, or anything that happened anywhere.

**How to read the row tables.** Each row appears twice — once as the SQL pane
rendered it, once as the Python pane did — with `✓` or `≠` in the last
column, which is the per-row mark the screen draws. The `data` cell is the whole
stored record and is the one thing truncated, at 68 characters, marked with
`…`; every other cell is verbatim. The SQL is never truncated.

**Nothing here is asserted only by this document.** Every number below is also
asserted by a named test in `demo/tests/`, listed in §7, and re-derived on every
`./run-demo test`.

Reproduce with:

```
./run-demo up          # brings up the database and the app
./run-demo test        # the suite, including every assertion quoted here
```

---

## 1. The three digests (plan §6.4 item 5)

| file | sha256 (recomputed now) | matches `demo/manifest.json` | what it is |
|---|---|---|---|
| `spikes/T-1/proto/compile.py` | `b71b153802d0df9479141ac02b662ca94d86268a940f66f1fb7a9782c8d0f3e2` | yes | the pinned T-1 compiler (Q19 said *as-is*; AC-33) |
| `spikes/T-1/proto/runtime.sql` | `32628b45f2d1dd043f71728dc7e100e2f54bd7bff508a775c3c05f5b15f77b23` | yes | the 21 `xpr.*` helpers, installed unmodified (AC-33) |
| `demo/vendor/expr.py` | `90cbb56d04b08b825ef38dbd1b805ad2b877a0f5e5154e2dc38d9944f4ad4c49` | yes | GIMS's evaluator, vendored byte-identically (AC-34) |

`demo/vendor/expr.py` against the live GIMS checkout at
`../GIMS-Project/core/dashboard/expr.py`: `90cbb56d04b08b825ef38dbd1b805ad2b877a0f5e5154e2dc38d9944f4ad4c49` — **identical**.

### The one digest a reviewer must not skim

`spikes/T-1/proto/runtime.sql` in the working tree **differs from `HEAD`**, and
that is not local drift. Three digests tell the whole story:

| version | sha256 | guard |
|---|---|---|
| working tree (what the demo installs) | `32628b45f2d1dd043f71728dc7e100e2f54bd7bff508a775c3c05f5b15f77b23` | 297 digits, returns NULL |
| `54477b5` — *T-2 passes locate and plan*, 2026-08-22 12:13 | `32628b45f2d1dd043f71728dc7e100e2f54bd7bff508a775c3c05f5b15f77b23` | 297 digits, returns NULL |
| `HEAD` (since `5b91973`, T-3, 2026-08-22 12:24) | `1c58d548a6045aa6698b07c167ceb3391a60c2f43b9bd4ff15cf914e6cf7e93d` | 309 digits, RAISES `XPR01` |

The working tree is **byte-identical to the file as committed at the start of
this ticket**, which is exactly what AC-33 asks for. What changed underneath
T-2 is `HEAD`: eleven minutes after T-2's plan was approved, **T-3 fixed the
very defect T-2 exists to demonstrate.** AC-22 below is only satisfiable on the
297-digit guard — with T-3's version the SQL pane reads `1e300` successfully and
the two panes agree, which AC-22 defines as a failing build. This is a
cross-ticket decision for Evan, recorded here rather than left to be discovered
by whoever next rebases.

---

## 2. The fourteen steps: SQL, rows, and the two panes side by side

Plan §6.4 items 1, 2 and 3, per step. For each one: the **parameterised**
statement (what executes) and the **display rendering** (what the SQL pane
shows) — printed one after the other so a reviewer can see they differ only in
substitution — then the rows, then both panes' answers with the verdict.

### Step 1 — `./run-demo up`

No pick. Infrastructure only: the database comes up on `55440` and the app on `8787`, and the seed loads
**10,410** rows — 8,400 + 2,000 + 10. No SQL is generated by a pick, so items 1–3
do not apply to this step.

### Step 2 — Choose a source: `noun:Heartbeat`, nothing else picked yet

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat'
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:Heartbeat |

`statement_sent`: `true` · probes run: **0**

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 8400 | collection, key, data |
| Python pane | answered | 8400 | collection, key, data |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 8400 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `Python · collection` | `Python · key` | `Python · data` | `=` |
|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 1 | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 2 | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 3 | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 4 | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 5 | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 6 | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | ✓ |
| 7 | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 8 | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 9 | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 10 | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 11 | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 12 | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 13 | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 14 | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 15 | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 16 | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 17 | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 18 | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 19 | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |

*(first 20 of 8,400; the comparison above is over all 8,400, not over this page — B25.)*

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 3 — Add a computed column: `alive = $.status == "ok"`

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [
    {
      "name": "alive",
      "expr": "$.status == \"ok\""
    }
  ],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(nullif((r.data -> (%(cc0_p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(cc0_p1)s)::text))  AS "alive"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(nullif((r.data -> ('status')::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb(('ok')::text))  AS "alive"
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat'
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| cc0_p0 | status |
| cc0_p1 | ok |
| collection | noun:Heartbeat |

`statement_sent`: `true` · probes run: **1** (member (b) did not fire)

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 8400 | collection, key, data, alive |
| Python pane | answered | 8400 | collection, key, data, alive |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 8400 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `SQL · alive` | `Python · collection` | `Python · key` | `Python · data` | `Python · alive` | `=` |
|---|---|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 1 | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 2 | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 3 | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 4 | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 5 | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 6 | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | true | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | true | ✓ |
| 7 | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 8 | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 9 | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 10 | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 11 | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 12 | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 13 | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 14 | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 15 | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 16 | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 17 | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 18 | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |
| 19 | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | true | ✓ |

*(first 20 of 8,400; the comparison above is over all 8,400, not over this page — B25.)*

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 4 — Filter: `$.status != "ok"`

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": "$.status != \"ok\"",
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
   AND xpr.truthy( to_jsonb(nullif((r.data -> (%(flt_p0)s)::text), 'null'::jsonb) IS DISTINCT FROM to_jsonb((%(flt_p1)s)::text)) )
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat'
   AND xpr.truthy( to_jsonb(nullif((r.data -> ('status')::text), 'null'::jsonb) IS DISTINCT FROM to_jsonb(('ok')::text)) )
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:Heartbeat |
| flt_p0 | status |
| flt_p1 | ok |

`statement_sent`: `true` · probes run: **1** (member (b) did not fire)

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 857 | collection, key, data |
| Python pane | answered | 857 | collection, key, data |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 857 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `Python · collection` | `Python · key` | `Python · data` | `=` |
|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0148 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0148 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 1 | noun:Heartbeat | hb-01-0149 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0149 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 2 | noun:Heartbeat | hb-01-0150 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0150 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 3 | noun:Heartbeat | hb-01-0151 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0151 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 4 | noun:Heartbeat | hb-01-0152 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0152 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 5 | noun:Heartbeat | hb-01-0153 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0153 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 6 | noun:Heartbeat | hb-01-0154 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0154 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 7 | noun:Heartbeat | hb-01-0155 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0155 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 8 | noun:Heartbeat | hb-01-0156 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0156 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 9 | noun:Heartbeat | hb-01-0157 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0157 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 10 | noun:Heartbeat | hb-01-0158 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0158 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 11 | noun:Heartbeat | hb-01-0159 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0159 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 12 | noun:Heartbeat | hb-01-0160 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0160 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 13 | noun:Heartbeat | hb-02-0034 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0034 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 14 | noun:Heartbeat | hb-02-0035 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0035 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 15 | noun:Heartbeat | hb-02-0036 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0036 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 16 | noun:Heartbeat | hb-02-0037 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0037 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 17 | noun:Heartbeat | hb-02-0038 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0038 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 18 | noun:Heartbeat | hb-02-0039 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0039 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |
| 19 | noun:Heartbeat | hb-02-0040 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0040 | {"payload":{"load":94,"note":"lima"},"sender_id":"hb-02","status":"… | ✓ |

*(first 20 of 857; the comparison above is over all 857, not over this page — B25.)*

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 5 — Sort by `$.ts`, descending, capped at 10 rows

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": {
    "field": "$.ts",
    "dir": "desc"
  },
  "cap": 10,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY ( r.data #> %(sort_path)s ) DESC NULLS LAST, r.key ASC
 LIMIT %(cap)s;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat'
 ORDER BY ( r.data #> '{"ts"}'::text[] ) DESC NULLS LAST, r.key ASC
 LIMIT 10;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| cap | 10 |
| collection | noun:Heartbeat |
| sort_path | ["ts"] |

`statement_sent`: `true` · probes run: **0**

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 10 | collection, key, data |
| Python pane | answered | 10 | collection, key, data |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 10 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `Python · collection` | `Python · key` | `Python · data` | `=` |
|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0167 | {"payload":{"load":45,"note":"india"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0167 | {"payload":{"load":45,"note":"india"},"sender_id":"hb-01","status":… | ✓ |
| 1 | noun:Heartbeat | hb-02-0167 | {"payload":{"load":42,"note":"india"},"sender_id":"hb-02","status":… | noun:Heartbeat | hb-02-0167 | {"payload":{"load":42,"note":"india"},"sender_id":"hb-02","status":… | ✓ |
| 2 | noun:Heartbeat | hb-03-0167 | {"payload":{"load":68,"note":"papa"},"sender_id":"hb-03","status":"… | noun:Heartbeat | hb-03-0167 | {"payload":{"load":68,"note":"papa"},"sender_id":"hb-03","status":"… | ✓ |
| 3 | noun:Heartbeat | hb-04-0167 | {"payload":{"load":54,"note":"echo"},"sender_id":"hb-04","status":"… | noun:Heartbeat | hb-04-0167 | {"payload":{"load":54,"note":"echo"},"sender_id":"hb-04","status":"… | ✓ |
| 4 | noun:Heartbeat | hb-05-0167 | {"payload":{"load":27,"note":"bravo"},"sender_id":"hb-05","status":… | noun:Heartbeat | hb-05-0167 | {"payload":{"load":27,"note":"bravo"},"sender_id":"hb-05","status":… | ✓ |
| 5 | noun:Heartbeat | hb-06-0167 | {"payload":{"load":65,"note":"november"},"sender_id":"hb-06","statu… | noun:Heartbeat | hb-06-0167 | {"payload":{"load":65,"note":"november"},"sender_id":"hb-06","statu… | ✓ |
| 6 | noun:Heartbeat | hb-07-0167 | {"payload":{"load":48,"note":"foxtrot"},"sender_id":"hb-07","status… | noun:Heartbeat | hb-07-0167 | {"payload":{"load":48,"note":"foxtrot"},"sender_id":"hb-07","status… | ✓ |
| 7 | noun:Heartbeat | hb-08-0167 | {"payload":{"load":52,"note":"golf"},"sender_id":"hb-08","status":"… | noun:Heartbeat | hb-08-0167 | {"payload":{"load":52,"note":"golf"},"sender_id":"hb-08","status":"… | ✓ |
| 8 | noun:Heartbeat | hb-09-0167 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-09","status":… | noun:Heartbeat | hb-09-0167 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-09","status":… | ✓ |
| 9 | noun:Heartbeat | hb-10-0167 | {"payload":{"load":8,"note":"mike"},"sender_id":"hb-10","status":"o… | noun:Heartbeat | hb-10-0167 | {"payload":{"load":8,"note":"mike"},"sender_id":"hb-10","status":"o… | ✓ |

`ordered_by`: `$.ts DESC, then key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 6 — Aggregate: sum of `$.payload.load`

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "sum",
    "field": "$.payload.load"
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT round( sum( CASE WHEN jsonb_typeof( r.data #> %(agg_path)s ) = 'number'
                        THEN ( r.data #> %(agg_path)s #>> '{}' )::numeric END ), 6)  AS "agg"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT round( sum( CASE WHEN jsonb_typeof( r.data #> '{"payload","load"}'::text[] ) = 'number'
                        THEN ( r.data #> '{"payload","load"}'::text[] #>> '{}' )::numeric END ), 6)  AS "agg"
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat';
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| agg_path | ["payload", "load"] |
| collection | noun:Heartbeat |

`statement_sent`: `true` · probes run: **1** (member (a) did not fire)

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 1 | agg |
| Python pane | answered | 1 | agg |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 1 | true | 0 | — |

| `#` | `SQL · agg` | `Python · agg` | `=` |
|---|---|---|---|
| 0 | 400207.000000 | 400207.000000 | ✓ |

`ordered_by`: `—` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 7 — Time bucket by day, count per bucket

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "count",
    "field": null
  },
  "bucket": "day",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT to_char( date_trunc('day', (data ->> 'ts')::timestamptz) AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS"Z"' )                      AS "bucket",
       count(*)             AS "agg"
  FROM demo.records
 WHERE collection = %(collection)s
 GROUP BY "bucket"
 ORDER BY "bucket";
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT to_char( date_trunc('day', (data ->> 'ts')::timestamptz) AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS"Z"' )                      AS "bucket",
       count(*)             AS "agg"
  FROM demo.records
 WHERE collection = 'noun:Heartbeat'
 GROUP BY "bucket"
 ORDER BY "bucket";
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:Heartbeat |

`statement_sent`: `true` · probes run: **0**

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 7 | bucket, agg |
| Python pane | answered | 7 | bucket, agg |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 7 | true | 0 | — |

| `#` | `SQL · bucket` | `SQL · agg` | `Python · bucket` | `Python · agg` | `=` |
|---|---|---|---|---|---|
| 0 | 2026-08-14T00:00:00Z | 1200 | 2026-08-14T00:00:00Z | 1200 | ✓ |
| 1 | 2026-08-15T00:00:00Z | 1200 | 2026-08-15T00:00:00Z | 1200 | ✓ |
| 2 | 2026-08-16T00:00:00Z | 1200 | 2026-08-16T00:00:00Z | 1200 | ✓ |
| 3 | 2026-08-17T00:00:00Z | 1200 | 2026-08-17T00:00:00Z | 1200 | ✓ |
| 4 | 2026-08-18T00:00:00Z | 1200 | 2026-08-18T00:00:00Z | 1200 | ✓ |
| 5 | 2026-08-19T00:00:00Z | 1200 | 2026-08-19T00:00:00Z | 1200 | ✓ |
| 6 | 2026-08-20T00:00:00Z | 1200 | 2026-08-20T00:00:00Z | 1200 | ✓ |

`ordered_by`: `bucket` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 8 — Rolling window: 3-point trailing average of `$.payload.load`

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": {
    "field": "$.payload.load"
  },
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data,
       round( avg( CASE WHEN jsonb_typeof( r.data #> %(win_path)s ) = 'number'
                        THEN ( r.data #> %(win_path)s #>> '{}' )::numeric END )
         OVER (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key
               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 6)  AS "rolling_avg"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data,
       round( avg( CASE WHEN jsonb_typeof( r.data #> '{"payload","load"}'::text[] ) = 'number'
                        THEN ( r.data #> '{"payload","load"}'::text[] #>> '{}' )::numeric END )
         OVER (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key
               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 6)  AS "rolling_avg"
  FROM demo.records AS r
 WHERE r.collection = 'noun:Heartbeat'
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:Heartbeat |
| win_path | ["payload", "load"] |

`statement_sent`: `true` · probes run: **1** (member (a) did not fire)

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 8400 | collection, key, data, rolling_avg |
| Python pane | answered | 8400 | collection, key, data, rolling_avg |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 8400 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `SQL · rolling_avg` | `Python · collection` | `Python · key` | `Python · data` | `Python · rolling_avg` | `=` |
|---|---|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 1 | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0001 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 2 | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0002 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 3 | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0003 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 4 | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0004 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 5 | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | noun:Heartbeat | hb-01-0005 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | 18.000000 | ✓ |
| 6 | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | 12.000000 | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | 12.000000 | ✓ |
| 7 | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 9.333333 | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 9.333333 | ✓ |
| 8 | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 6.666667 | noun:Heartbeat | hb-01-0008 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 6.666667 | ✓ |
| 9 | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0009 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 10 | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0010 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 11 | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0011 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 12 | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0012 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 13 | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0013 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 14 | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0014 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 15 | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0015 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 16 | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0016 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 17 | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0017 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 18 | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0018 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |
| 19 | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | noun:Heartbeat | hb-01-0019 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | 10.000000 | ✓ |

*(first 20 of 8,400; the comparison above is over all 8,400, not over this page — B25.)*

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 9 — Show only rows that changed, per sender

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": true
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
WITH picked AS (
  SELECT r.collection,
         r.key,
         r.data,
         ( lag( r.data - 'ts' ) OVER w
             IS DISTINCT FROM ( r.data - 'ts' ) )     AS "changed"
    FROM demo.records AS r
   WHERE r.collection = %(collection)s
  WINDOW w AS (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key)
)
SELECT collection, key, data
  FROM picked
 WHERE "changed"
 ORDER BY key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
WITH picked AS (
  SELECT r.collection,
         r.key,
         r.data,
         ( lag( r.data - 'ts' ) OVER w
             IS DISTINCT FROM ( r.data - 'ts' ) )     AS "changed"
    FROM demo.records AS r
   WHERE r.collection = 'noun:Heartbeat'
  WINDOW w AS (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key)
)
SELECT collection, key, data
  FROM picked
 WHERE "changed"
 ORDER BY key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:Heartbeat |

`statement_sent`: `true` · probes run: **0**

**The two panes, side by side.** Verdict: **`agree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 861 | collection, key, data |
| Python pane | answered | 861 | collection, key, data |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 861 | true | 0 | — |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `Python · collection` | `Python · key` | `Python · data` | `=` |
|---|---|---|---|---|---|---|---|
| 0 | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0000 | {"payload":{"load":18,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 1 | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | noun:Heartbeat | hb-01-0006 | {"payload":{"load":0,"note":"foxtrot"},"sender_id":"hb-01","status"… | ✓ |
| 2 | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0007 | {"payload":{"load":10,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 3 | noun:Heartbeat | hb-01-0041 | {"payload":{"load":32,"note":"hotel"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0041 | {"payload":{"load":32,"note":"hotel"},"sender_id":"hb-01","status":… | ✓ |
| 4 | noun:Heartbeat | hb-01-0056 | {"payload":{"load":2,"note":"hotel"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0056 | {"payload":{"load":2,"note":"hotel"},"sender_id":"hb-01","status":"… | ✓ |
| 5 | noun:Heartbeat | hb-01-0060 | {"payload":{"load":52,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0060 | {"payload":{"load":52,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 6 | noun:Heartbeat | hb-01-0061 | {"payload":{"load":8,"note":"november"},"sender_id":"hb-01","status… | noun:Heartbeat | hb-01-0061 | {"payload":{"load":8,"note":"november"},"sender_id":"hb-01","status… | ✓ |
| 7 | noun:Heartbeat | hb-01-0077 | {"payload":{"load":44,"note":"foxtrot"},"sender_id":"hb-01","status… | noun:Heartbeat | hb-01-0077 | {"payload":{"load":44,"note":"foxtrot"},"sender_id":"hb-01","status… | ✓ |
| 8 | noun:Heartbeat | hb-01-0081 | {"payload":{"load":43,"note":"lima"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0081 | {"payload":{"load":43,"note":"lima"},"sender_id":"hb-01","status":"… | ✓ |
| 9 | noun:Heartbeat | hb-01-0094 | {"payload":{"load":54,"note":"juliet"},"sender_id":"hb-01","status"… | noun:Heartbeat | hb-01-0094 | {"payload":{"load":54,"note":"juliet"},"sender_id":"hb-01","status"… | ✓ |
| 10 | noun:Heartbeat | hb-01-0099 | {"payload":{"load":29,"note":"oscar"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0099 | {"payload":{"load":29,"note":"oscar"},"sender_id":"hb-01","status":… | ✓ |
| 11 | noun:Heartbeat | hb-01-0113 | {"payload":{"load":34,"note":"juliet"},"sender_id":"hb-01","status"… | noun:Heartbeat | hb-01-0113 | {"payload":{"load":34,"note":"juliet"},"sender_id":"hb-01","status"… | ✓ |
| 12 | noun:Heartbeat | hb-01-0116 | {"payload":{"load":61,"note":"november"},"sender_id":"hb-01","statu… | noun:Heartbeat | hb-01-0116 | {"payload":{"load":61,"note":"november"},"sender_id":"hb-01","statu… | ✓ |
| 13 | noun:Heartbeat | hb-01-0127 | {"payload":{"load":21,"note":"echo"},"sender_id":"hb-01","status":"… | noun:Heartbeat | hb-01-0127 | {"payload":{"load":21,"note":"echo"},"sender_id":"hb-01","status":"… | ✓ |
| 14 | noun:Heartbeat | hb-01-0148 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0148 | {"payload":{"load":21,"note":"alpha"},"sender_id":"hb-01","status":… | ✓ |
| 15 | noun:Heartbeat | hb-01-0161 | {"payload":{"load":45,"note":"india"},"sender_id":"hb-01","status":… | noun:Heartbeat | hb-01-0161 | {"payload":{"load":45,"note":"india"},"sender_id":"hb-01","status":… | ✓ |
| 16 | noun:Heartbeat | hb-02-0000 | {"payload":{"load":19,"note":"golf"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0000 | {"payload":{"load":19,"note":"golf"},"sender_id":"hb-02","status":"… | ✓ |
| 17 | noun:Heartbeat | hb-02-0005 | {"payload":{"load":66,"note":"papa"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0005 | {"payload":{"load":66,"note":"papa"},"sender_id":"hb-02","status":"… | ✓ |
| 18 | noun:Heartbeat | hb-02-0015 | {"payload":{"load":82,"note":"mike"},"sender_id":"hb-02","status":"… | noun:Heartbeat | hb-02-0015 | {"payload":{"load":82,"note":"mike"},"sender_id":"hb-02","status":"… | ✓ |
| 19 | noun:Heartbeat | hb-02-0020 | {"payload":{"load":44,"note":"bravo"},"sender_id":"hb-02","status":… | noun:Heartbeat | hb-02-0020 | {"payload":{"load":44,"note":"bravo"},"sender_id":"hb-02","status":… | ✓ |

*(first 20 of 861; the comparison above is over all 861, not over this page — B25.)*

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 10 — Try a computed column using `round(…, 1)`

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [
    {
      "name": "rounded",
      "expr": "round($.payload.load, 1)"
    }
  ],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Generated SQL: none.** This step is refused at layer 1, *before any SQL
exists* — nothing is compiled, nothing is prepared, and the database is
never asked. `statement_sent`: `false`. Probes run: **0**.

**Refused.**

| `field` | `value` |
|---|---|
| layer | 1 |
| kind | expression |
| construct | round |
| row | — |
| sql existed | false |
| statement sent | false |

> `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min

**The two panes, side by side.** Verdict: **`no-compare`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | not-asked | 0 | — |
| Python pane | not-asked | 0 | — |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 0 | true | 0 | — |

*Both panes returned no rows.* What each pane says instead, verbatim:

> **SQL pane (`not-asked`)** — Not asked. Answering a pick the screen has just declared out of scope would be answering a question it refused to accept.
>
> **Python pane (`not-asked`)** — Not asked. Answering a pick the screen has just declared out of scope would be answering a question it refused to accept.
>

`ordered_by`: `—` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 11 — On `noun:EdgeCase`, computed column `biggest = max($.l)`

**The pick, as the API received it:**

```json
{
  "source": "noun:EdgeCase",
  "computed": [
    {
      "name": "biggest",
      "expr": "max($.l)"
    }
  ],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(xpr.reduce_one((%(cc0_p0)s)::text, nullif((r.data -> (%(cc0_p1)s)::text), 'null'::jsonb)))  AS "biggest"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(xpr.reduce_one(('max')::text, nullif((r.data -> ('l')::text), 'null'::jsonb)))  AS "biggest"
  FROM demo.records AS r
 WHERE r.collection = 'noun:EdgeCase'
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| cc0_p0 | max |
| cc0_p1 | l |
| collection | noun:EdgeCase |

`statement_sent`: `true` · probes run: **1** (member (a) did not fire)

**The two panes, side by side.** Verdict: **`disagree`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | answered | 10 | collection, key, data, biggest |
| Python pane | answered | 10 | collection, key, data, biggest |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 10 | true | 1 | 1 |

| `#` | `SQL · collection` | `SQL · key` | `SQL · data` | `SQL · biggest` | `Python · collection` | `Python · key` | `Python · data` | `Python · biggest` | `=` |
|---|---|---|---|---|---|---|---|---|---|
| 0 | noun:EdgeCase | edge-00 | {"a":1e+300,"label":"edge case: 1e300 is a real double, yet seven S… | null | noun:EdgeCase | edge-00 | {"a":1e+300,"label":"edge case: 1e300 is a real double, yet seven S… | null | ✓ |
| 1 | noun:EdgeCase | edge-01 | {"l":[1e+300,1],"label":"edge case: max of [1e300, 1] \u2014 SQL an… | 1 | noun:EdgeCase | edge-01 | {"l":[1e+300,1],"label":"edge case: max of [1e300, 1] \u2014 SQL an… | 1e+300 | ≠ |
| 2 | noun:EdgeCase | edge-02 | {"label":"edge case: one key holds an object and one holds an array… | null | noun:EdgeCase | edge-02 | {"label":"edge case: one key holds an object and one holds an array… | null | ✓ |
| 3 | noun:EdgeCase | edge-03 | {"huge":1e+400,"label":"edge case: 1e400 is larger than any double … | null | noun:EdgeCase | edge-03 | {"huge":1e+400,"label":"edge case: 1e400 is larger than any double … | null | ✓ |
| 4 | noun:EdgeCase | edge-04 | {"g":1.7976931348623156e+296,"label":"edge case: just below the shi… | null | noun:EdgeCase | edge-04 | {"g":1.7976931348623156e+296,"label":"edge case: just below the shi… | null | ✓ |
| 5 | noun:EdgeCase | edge-05 | {"g":1.7976931348623158e+296,"label":"edge case: just above the shi… | null | noun:EdgeCase | edge-05 | {"g":1.7976931348623158e+296,"label":"edge case: just above the shi… | null | ✓ |
| 6 | noun:EdgeCase | edge-06 | {"d":7,"label":"edge case: division by zero \u2014 both panes must … | null | noun:EdgeCase | edge-06 | {"d":7,"label":"edge case: division by zero \u2014 both panes must … | null | ✓ |
| 7 | noun:EdgeCase | edge-07 | {"label":"edge case: the string '12.5' converts to a number and 'no… | null | noun:EdgeCase | edge-07 | {"label":"edge case: the string '12.5' converts to a number and 'no… | null | ✓ |
| 8 | noun:EdgeCase | edge-08 | {"label":"edge case: a present JSON null beside a key absent from e… | null | noun:EdgeCase | edge-08 | {"label":"edge case: a present JSON null beside a key absent from e… | null | ✓ |
| 9 | noun:EdgeCase | edge-09 | {"arr":[],"label":"edge case: an empty array, an empty object and a… | null | noun:EdgeCase | edge-09 | {"arr":[],"label":"edge case: an empty array, an empty object and a… | null | ✓ |

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 12 — Still on `noun:EdgeCase`, filter `$.where == "alpha"`

**The pick, as the API received it:**

```json
{
  "source": "noun:EdgeCase",
  "computed": [],
  "filter": "$.where == \"alpha\"",
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
   AND xpr.truthy( to_jsonb(nullif((r.data -> (%(flt_p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(flt_p1)s)::text)) )
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data
  FROM demo.records AS r
 WHERE r.collection = 'noun:EdgeCase'
   AND xpr.truthy( to_jsonb(nullif((r.data -> ('where')::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb(('alpha')::text)) )
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| collection | noun:EdgeCase |
| flt_p0 | where |
| flt_p1 | alpha |

`statement_sent`: `false` · probes run: **1** (member (b) **fired** on `edge-02`)

**Refused.**

| `field` | `value` |
|---|---|
| layer | 2 |
| kind | probe |
| construct | probe (b) |
| row | edge-02 |
| sql existed | true |
| statement sent | false |

> container operand: an == or != operand resolved to an object or an array, which the safe subset does not compare (first such row, by key: "edge-02")

**The two panes, side by side.** Verdict: **`no-compare`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | abandoned | 0 | — |
| Python pane | answered | 0 | collection, key, data |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 0 | true | 0 | — |

*Both panes returned no rows.* What each pane says instead, verbatim:

> **SQL pane (`abandoned`)** — No number from this side. A probe found the condition below before the pick's own statement ran, so the statement was never sent.
>
> **Python pane (`answered`)** — The same source rows read out of the same database and walked in Python — decimal.Decimal, ROUND_HALF_UP, quantized to six places. Never handed the SQL query's result.
>

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 13 — Still on `noun:EdgeCase`, computed column `scaled = $.huge * 1`

**The pick, as the API received it:**

```json
{
  "source": "noun:EdgeCase",
  "computed": [
    {
      "name": "scaled",
      "expr": "$.huge * 1"
    }
  ],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Parameterised — this is the text that executes (AC-27):**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(xpr.num(nullif((r.data -> (%(cc0_p0)s)::text), 'null'::jsonb)) * xpr.num(to_jsonb((%(cc0_p1)s)::float8)))  AS "scaled"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

**Display rendering — what the SQL pane shows; never handed to the driver:**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(xpr.num(nullif((r.data -> ('huge')::text), 'null'::jsonb)) * xpr.num(to_jsonb((1.0)::float8)))  AS "scaled"
  FROM demo.records AS r
 WHERE r.collection = 'noun:EdgeCase'
 ORDER BY r.key ASC;
```

**Bind parameters:**

| `parameter` | `value` |
|---|---|
| cc0_p0 | huge |
| cc0_p1 | 1.0 |
| collection | noun:EdgeCase |

`statement_sent`: `false` · probes run: **1** (member (a) **fired** on `edge-03`)

**Refused.**

| `field` | `value` |
|---|---|
| layer | 2 |
| kind | probe |
| construct | probe (a) |
| row | edge-03 |
| sql existed | true |
| statement sent | false |

> out-of-range magnitude: this pick reads a number of magnitude >= 1.7976931348623157e+308, which the database's float8 cannot represent (first such row, by key: "edge-03")

**The two panes, side by side.** Verdict: **`no-compare`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | abandoned | 0 | — |
| Python pane | raised | 0 | — |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 0 | true | 0 | — |

*Both panes returned no rows.* What each pane says instead, verbatim:

> **SQL pane (`abandoned`)** — No number from this side. A probe found the condition below before the pick's own statement ran, so the statement was never sent.
>
> **Python pane (`raised`)** — This side could not read the value either. The second calculator is GIMS's own expr.py, vendored byte-identically, and evaluating this pick over these rows raised OverflowError: int too large to convert to float. The SQL side had already refused the same value at layer 2; neither engine can represent it.
>

`ordered_by`: `key` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 14 — Back on `noun:Heartbeat`, a hostile column name

**The pick, as the API received it:**

```json
{
  "source": "noun:Heartbeat",
  "computed": [
    {
      "name": "alive\"; DROP TABLE demo.records; --",
      "expr": "$.status == \"ok\""
    }
  ],
  "filter": null,
  "sort": null,
  "cap": null,
  "aggregate": {
    "fn": "none",
    "field": null
  },
  "bucket": "off",
  "window": null,
  "changed": false
}
```

**Generated SQL: none.** This step is refused at layer 1, *before any SQL
exists* — nothing is compiled, nothing is prepared, and the database is
never asked. `statement_sent`: `false`. Probes run: **0**.

**Refused.**

| `field` | `value` |
|---|---|
| layer | 1 |
| kind | alias |
| construct | alive"; DROP TABLE demo.records; -- |
| row | — |
| sql existed | false |
| statement sent | false |

> `alive"; DROP TABLE demo.records; --` is not a usable column name: letters, digits and underscore only, starting with a letter or underscore, at most 63 characters

**The two panes, side by side.** Verdict: **`no-compare`**.

| `pane` | `state` | `rows returned` | `columns` |
|---|---|---|---|
| SQL pane | not-asked | 0 | — |
| Python pane | not-asked | 0 | — |

| `compared rows` | `columns match` | `differing rows` | `first differing index` |
|---|---|---|---|
| 0 | true | 0 | — |

*Both panes returned no rows.* What each pane says instead, verbatim:

> **SQL pane (`not-asked`)** — Not asked. Answering a pick the screen has just declared out of scope would be answering a question it refused to accept.
>
> **Python pane (`not-asked`)** — Not asked. Answering a pick the screen has just declared out of scope would be answering a question it refused to accept.
>

`ordered_by`: `—` · session pinned at `extra_float_digits = 1`, `TimeZone = UTC`

### Step 14, second half — the name retyped as plain `alive`

**Parameterised:**

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(nullif((r.data -> (%(cc0_p0)s)::text), 'null'::jsonb) IS NOT DISTINCT FROM to_jsonb((%(cc0_p1)s)::text))  AS "alive"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
 ORDER BY r.key ASC;
```

The alias is emitted as `AS "alive"` — a quoted, ordinary column name — and it
is **not** in the bind-parameter list, because SQL has no parameter position for
a column name. The Python pane keys its own answer `alive` too. Verdict: **`agree`**, 8,400 rows compared, 0 differing.

---

## 3. AC-22 — the asserted disagreement, on its own

Plan §6.4 item 3 asks for step 11's disagreement to be *visible in the record*
and not only in a green test. Here it is, lifted out of step 11 above.

| | |
|---|---|
| The pick | source `noun:EdgeCase`, one computed column `biggest = max($.l)` |
| The row | `edge-01`, whose `l` holds the array `[1e300, 1]` |
| **Python pane** | **`1e+300`** |
| **SQL pane** | **`1`** |
| Verdict | **`disagree`** |
| Differing rows | 1 of 10 compared |
| First differing index | 1 |
| Differing column | index 3, `biggest` |
| Both panes' state | `answered` — two answers, not one absence |
| `statement_sent` | `true` — the SQL pane's `1` is a database answer |

**Why each side is right.** Python reads `[1e300, 1]` off the JSON; `1e300` is an
ordinary double (the largest is ~`1.7976931348623157e+308`) and `max` returns it.
The SQL side reads every number through `xpr.f8`, whose shipped guard sits at
`1.7976931348623157e+296` — *below* the true limit — so its read of `1e300`
becomes NULL, `max` ignores NULLs, and the only element left standing is `1`.

**Why this is asserted rather than tolerated.** Spec AC-22: *"If the two panes
ever agree here, either the compiler has been edited (which Q19 forbids and AC-33
catches) or the control has stopped working — and in both cases the build is not
accepted."* The test therefore asserts **both values and the flag**, and asserts
that they differ, in that order.

Run five more times (`test_ac22_the_disagreement_is_reproducible`), the observed
set of outcomes was exactly one element:

```
{('disagree', '1', '1e+300', 1)}
```

Nine of the ten EdgeCase rows agree. The disagreement is local to the one row
that holds the value — not a pane that failed to run.

---

## 4. `demo/expected-answers.json`, with every derivation (plan §6.4 item 4)

The third independent path (B8): written by `demo/seed/expectations.py`, which
imports nothing from `demo/pyrunner/`, `demo/builder.py` or `demo/probes.py` —
asserted by an AST walk, not by good intentions. Every entry carries a
`derivation` saying how the number was reached; **"whatever the code returned"**
is not admissible.

**59 entries.** The file's own `$comment` says it is generated, names the file that generates it, and names the AST test that keeps that file honest.

| path | value | derivation |
|---|---|---|
| `corpus.heartbeat_rows` | `8400` | 50 senders x 168 beats (R5, R17). |
| `corpus.sample_rows` | `2000` | generate.SAMPLES — the literal 2,000 of plan §5.3. |
| `corpus.edge_case_rows` | `10` | The ten rows B24 names individually. |
| `steps[0].expect.db_port` | `55440` | The demo's own Postgres port, fixed at plan §11.2. It is deliberately not the port of the live database on this machine, which this demo must never reach — and AC-3 forbids that number appearing anywhere in the demo tree, including in this sentence. |
| `steps[0].expect.app_port` | `8787` | The demo's own app port, fixed at plan §11.2. |
| `steps[0].expect.rows_loaded` | `10410` | 8400 heartbeats + 2000 samples + 10 edge cases = 10410 rows, counted from the generator's own streams. |
| `steps[1].expect.row_count` | `8400` | 50 senders x 168 hourly beats = 8400. R5 fixes the senders at 50 (hb-01 … hb-50); R17 fixes the span at 7 whole UTC days x 24 hours = 168 beats. Counted from generate.heartbeat_rows(). |
| `steps[1].expect.first_key` | `"hb-01-0000"` | The lowest key under ORDER BY key: sender hb-01's beat 0000. R19's fixed-width keys make text order record order. |
| `steps[1].expect.last_key` | `"hb-50-0167"` | The highest key under ORDER BY key: sender hb-50's beat 0167. |
| `steps[2].expect.true_count` | `7543` | Rows whose status is exactly 'ok': 7543 of 8400, counted one row at a time off the generator. R16 draws status about 90/8/2 across ok/warn/error, so ~90% of 8400 is ~7560 and 7543 sits where that predicts. |
| `steps[2].expect.false_count` | `857` | 8400 - 7543 = 857. The two counts must sum to the step-2 total, and they do; status is never null on this collection so there is no third bucket. |
| `steps[3].expect.row_count` | `857` | The complement of step 3: 8400 - 7543 = 857. Derived as its own count here, then checked against step 3's subtraction — two routes to one number. |
| `steps[3].expect.first_key` | `"hb-01-0148"` | The lowest key among the 857 non-ok rows under ORDER BY key. Its status is 'warn'. |
| `steps[3].expect.first_status` | `"warn"` | Read off row hb-01-0148 — the first non-ok row in key order. It is not 'ok', which is the filter's whole assertion. |
| `steps[4].expect.latest_ts` | `"2026-08-20T23:00:00Z"` | Beat 167 of the span R17 fixes: 2026-08-14T00:00:00Z + 167 hours = 2026-08-20T23:00:00Z. All 50 senders carry it, which is what makes the tie total. |
| `steps[4].expect.keys` | `["hb-01-0167", "hb-02-0167", "hb-03-0167", "hb-04-0167", "hb-05-0167", "hb-06-0167", "hb-…` | The 10 lowest keys at 2026-08-20T23:00:00Z, i.e. senders hb-01 … hb-10 at beat 0167. Derived by sorting key ascending, then STABLE-sorting on ts descending — never reverse=True over a tuple holding key. |
| `steps[4].expect.row_count` | `10` | The row cap, applied after sorting (operation 5). 8,400 rows are available, so the cap binds. |
| `steps[5].expect.sum` | `"400207"` | The sum of payload.load over all 8400 heartbeat rows = 400207. Accumulated in decimal.Decimal, one row at a time, in generator order. Every load is an integer 0–100 (R16), so the total is an integer and floating point never enters: a float8 accumulation could return 400207.000000000001 and be uncheckable by eye, which §7.2 exists to prevent. Bounds a reader can check without adding anything up: 0 <= 400207 <= 8400 x 100 = 840000, and the mean load is 400207/8400 = 47.643690, which sits where a uniform 0–100 draw predicts (~50). |
| `steps[5].expect.row_count` | `8400` | All 8400 rows contribute: payload.load is present and an integer on every heartbeat row, so §7.2 item 5's numeric read returns a number for each and none drops out of the sum. |
| `steps[6].expect.bucket_count` | `7` | R17's span is 7 whole UTC days (2026-08-14 … 2026-08-20) and every beat sits inside it, so a UTC day bucket gives exactly 7. Counted from the distinct ts[:10] values in the generator's rows. |
| `steps[6].expect.rows_per_bucket` | `[1200]` | 50 senders x 24 hourly beats per day = 1200 rows in every bucket. Every bucket holds the same count because the span is whole days and no sender misses a beat — which is also why 7 x 1200 = 8400 must equal step 2's 8400, and it does. |
| `steps[6].expect.buckets` | `[{"bucket": "2026-08-14T00:00:00Z", "count": 1200}, {"bucket": "2026-08-15T00:00:00Z", "c…` | Each label is the day's midnight in the same fixed-width UTC ISO-8601 form ts uses (YYYY-MM-DDTHH:MM:SSZ), which is what to_char(..., 'YYYY-MM-DD"T"HH24:MI:SS"Z"') emits. Counts are rows per day, tallied off the generator. Ordered by label, which is a total order because the labels are distinct and fixed-width. |
| `steps[7].expect.worked_sender` | `"hb-18"` | W6-R1: §10 step 8 does not name a sender, and hb-01 — the obvious pick — has five identical loads, so ÷1, ÷2 and ÷3 all print the same number and the step demonstrates nothing. Selection rule: the lowest-numbered sender whose first three rolling values are pairwise distinct AND whose first three loads do not sum to a multiple of 3. Exactly one sender on this corpus qualifies, so the choice is forced. |
| `steps[7].expect.worked_loads` | `[27, 88, 88, 88, 88]` | The payload.load of hb-18's first five beats, in (ts, key) order, read straight off the generator: [27, 88, 88, 88, 88]. |
| `steps[7].expect.worked_values` | `[{"key": "hb-18-0000", "window": [27], "value": "27.000000"}, {"key": "hb-18-0001", "wind…` | Worked by hand, and every one of these is checkable without running anything: hb-18-0000 = (27) / 1 = 27.000000; hb-18-0001 = (27 + 88) / 2 = 57.500000; hb-18-0002 = (27 + 88 + 88) / 3 = 67.666667; hb-18-0003 = (88 + 88 + 88) / 3 = 88.000000; hb-18-0004 = (88 + 88 + 88) / 3 = 88.000000. Row 1 divides by 1 (its own load, NOT blank and NOT ÷3); row 2 by 2; rows 3–5 by 3. Row 3 is the non-terminating division §7.2 says this step exists to exercise — it does not terminate in decimal, so the 6-place half-up round is what decides its last digit. Note honestly: a ÷3 can never produce an exact half, so this cell does NOT discriminate half-up from banker's rounding; AC-24(b)'s own tie fixture is what tests that, and this file does not claim to. |
| `steps[7].expect.column_sha256` | `"51198c3cf2903f0020ec3db926829bd9491e7993f0ce78d123cc464c28bef06b"` | W6-R2: sha256 over all 8400 rolling cells in key order, each as '<key>\x1f<value at 6dp>\n' with a null cell written 'null'. Five worked cells from one sender cannot catch the 100-cell short-window failure unless that sender is affected; every sender is, but only in its first two rows. This digest makes the whole column one comparison. A pane that divides by 3 always changes it. |
| `steps[7].expect.row_count` | `8400` | One cell per heartbeat row — 8400. The window drops no row and pads no row (§7.1's window rule), so this must equal step 2's 8400. |
| `steps[8].expect.kept_count` | `861` | 861 of 8400 rows kept. Derived by walking each sender's beats in (ts, key) order and keeping a row when {k: v for k, v in record.items() if k != 'ts'} differs from its predecessor's. Two independent checks a reader can do on this number: (a) each of the 50 senders' first beat has no predecessor and is always kept, so the count cannot be below 50; (b) B27 redraws on a 0.10 coin at each of the remaining 167 beats, so the expected total is about 50 + 50 x 167 x 0.10 = 885, and 861 sits there. AC-40's band is 700–1,100 and this is inside it. |
| `steps[8].expect.first_five_keys` | `["hb-01-0000", "hb-01-0006", "hb-01-0007", "hb-01-0041", "hb-01-0056"]` | The five lowest kept keys under §7.4's total order (ORDER BY key over the kept rows), so 'the first five' is defined rather than whatever the plan happened to emit. All five are hb-01's, because key order groups a sender's beats together and hb-01 sorts first; the first of them is hb-01's beat 0000, kept because it has no predecessor. |
| `steps[8].expect.kept_if_ts_included` | `8400` | The NEGATIVE control, stated as a number so the failure is named and not merely counted: if the compared value wrongly included ts, every row would differ from its predecessor and all 8400 would be kept. That is not a near miss but a 10-fold one, visible in a single integer. AC-40 asserts both this and the 861 above. |
| `steps[8].expect.band` | `[700, 1100]` | AC-40's band, quoted from the spec so a reader can see the kept_count sits inside it. The band comes from AC-8's independently-pinned 88–92% repeat rate, which is the same property read from the other side. |
| `steps[9].expect.verdict` | `"refused"` | §4.2: round is one of the 16 refused constructs. Layer 1 catches it, so nothing is compiled and nothing runs. |
| `steps[9].expect.refused_by` | `"static gate (layer 1)"` | §4.4. The gate walks the AST before compilation; no database round trip happens. |
| `steps[9].expect.names_construct` | `"round"` | §4.4 requires every refusal to name the construct or the rule. The message must contain 'round'. |
| `steps[9].expect.sql_pane` | `null` | No SQL is generated at all — this is what distinguishes a layer-1 refusal from a layer-2 one (steps 12 and 13). |
| `steps[9].expect.python_pane` | `null` | Both panes stay empty. The gate is upstream of both, so neither calculator is reached. |
| `steps[9].expect.why_it_proves_something` | `"compile.py implements round at :394"` | Without the gate this step would compile, run and print a number. That is what makes it a real test of the subset rather than a demonstration of something impossible. |
| `steps[10].expect.row` | `"edge-01"` | The only seeded EdgeCase row carrying an `l` key; its value is the array [1e300, 1] (B24). |
| `steps[10].expect.python_value` | `"1e+300"` | Python's max over the parsed array [1e300, 1]. 1e300 is a perfectly ordinary double (max double is ~1.798e308), so Python reads it as a number and returns the larger of the two. |
| `steps[10].expect.sql_value` | `"1"` | Derived from the shipped 297-digit guard, not from running anything: the guard makes SQL's numeric read of a value this large return NULL (edge-00 states the same property, and the edge-04/edge-05 boundary pair brackets it at ~1.7976931348623157e+296). SQL's max ignores NULLs, so with 1e300 read as NULL the only surviving element of [1e300, 1] is 1, and max returns 1. |
| `steps[10].expect.panes_agree` | `false` | The asserted disagreement of AC-22. This one is SUPPOSED to differ; a run where the panes agree here is a FAILING run. |
| `steps[10].expect.flagged` | `true` | §5 requires the screen to flag the disagreement rather than silently show two numbers. |
| `steps[11].expect.verdict` | `"refused"` | Layer 2 fires on the row whose operand is an object. |
| `steps[11].expect.refused_by` | `"runtime probe (layer 2, member (b))"` | §4.5. The SQL pane shows the probe that fired and no number. |
| `steps[11].expect.offending_row` | `"edge-02"` | The one seeded EdgeCase row with a `where` key; it holds the object {"code":"alpha","n":7} (B24). §4.5 requires the refusal to name the row. |
| `steps[11].expect.sql_pane` | `null` | No number — the probe fired before the query returned one. |
| `steps[11].expect.python_pane_rows_kept` | `0` | The REPORTED FALLBACK (§4.5): the Python pane still shows Python's answer, labelled as such. Derived from the seeded rows: exactly one EdgeCase row has a `where` key and it is an object, and an object is not equal to the string "alpha"; the other nine rows have no `where` at all. So Python keeps 0 of the 10 rows. |
| `steps[12].expect.verdict` | `"refused"` | Layer 2 member (a): the magnitude is out of range. |
| `steps[12].expect.refused_by` | `"runtime probe (layer 2, member (a))"` | §4.5. Layer 2 fires while the query runs, on the row whose magnitude is out of range — unlike step 10, SQL WAS generated here, which is the visible difference between a static refusal and a runtime one. |
| `steps[12].expect.offending_row` | `"edge-03"` | The one seeded EdgeCase row with a `huge` key, whose stored JSON number is 1e400 (B24, written as raw JSON text precisely so it survives into the database exactly). |
| `steps[12].expect.sql_pane` | `null` | No number: the probe fired instead of returning a value. The pane shows the probe, not a blank — a blank would be indistinguishable from a query that returned nothing. |
| `steps[12].expect.python_pane` | `"raised"` | No number on this side either — the pane's state is `raised`. jsonb renders its numerics in FULL POSITIONAL DIGITS, so `data::text` carries edge-03's `huge` as a bare 401-digit INTEGER literal (no `.`, no `e`); JSON's grammar calls that an integer, so the parser routes it through `parse_int`, never `parse_float`, and returns an exact arbitrary-precision `int`. The float conversion that would have produced inf is never performed — inf never comes into existence. The `× 1` then has to make a double of that int and raises `OverflowError`, which the pane reports by name. Derived from jsonb's numeric rendering and JSON's integer-vs-float grammar, not by running the pane. AC-17 pins the pair: 1e400 refuses and 1e300 does NOT — the guard must not be a blanket ban on large numbers. **(CORRECTED 2026-08-22 — this row read `"inf"`; see §6.1.)** |
| `steps[13].expect.hostile_alias` | `"alive\"; DROP TABLE demo.records; --"` | The name typed. The expression is irrelevant and valid; it is the NAME that is the attack. |
| `steps[13].expect.verdict` | `"refused"` | §4.10's allowlist refuses it before any SQL exists. |
| `steps[13].expect.refused_before_sql` | `true` | Nothing is sent to the database. This is stronger than escaping: the string never reaches SQL text at all. |
| `steps[13].expect.names_the_name_and_rule` | `true` | §4.10 requires the refusal to name both the offending name and the rule. |
| `steps[13].expect.table_survives` | `8400` | After the refusal, noun:Heartbeat still returns 8400 rows on the next pick — the same count as step 2. That is the assertion that the DROP TABLE never ran; a refusal message alone would not prove it. |
| `steps[13].expect.retyped_alias` | `"alive"` | Retyping the name as a plain identifier is accepted. |
| `steps[13].expect.retyped_emitted_as` | `"AS \"alive\""` | The SQL pane shows the accepted alias emitted as a quoted identifier. |

**Where each is checked.** `demo/tests/test_walkthrough_doc.py` resolves every
annotation in `demo/WALKTHROUGH.md` against these paths (the doc ↔ file leg).
`test_ac31_all_three_producers_agree` compares **50** of them against what the
running app returns (the file ↔ app leg); the other 9 are named in
`NOT_APP_OBSERVABLE` with the reason no pick can produce them, and
`test_ac31_the_sweep_covers_every_entry_in_the_file` asserts the two lists cover
all 59 exactly, so nothing escapes by being in neither.

---

## 5. The suite's final summary line (plan §6.4 item 6)

`./run-demo test`, run twice: once as the machine stands, and once with the two
GIMS checkouts pointed at, because the skip count is a function of that and a
reviewer needs both halves.

### Run A — as the machine stands (no `AUTOSQL_GIMS_TREE`, no `AUTOSQL_GUTS_TREE`)

```
======= 2 failed, 563 passed, 9 skipped, 1 xfailed, 1 warning in 43.53s ========
run-demo test: 9 skipped, and what each was looking for:
    6 x D1 (tree half): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-34 (tree half): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GIMS-Project): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GUTS spine copy): no GIMS checkout at /home/corgea/GUTS/spine/L1-memory/gims-ledger — set AUTOSQL_GUTS_TREE to point at one
run-demo test: 563 passed, 9 skipped, 1 xfailed, 0 xpassed, 2 failed, 0 errors — B10 checksum guard: verified
```

**What was skipped, and why it is the right skip.** All nine are §9.7's loud skip:
`SKIPPED`, naming the path it looked for, counted separately from the passes, and
the tree-independent halves still ran — **AC-34's manifest half is among the
passes, not among the skips**, which is what AC-39(b) requires. The paths are
missed only because this build runs in a git *worktree* at
`/home/corgea/autoSQL-T-2-build`, so `../GIMS-Project` resolves to
`/home/corgea/GIMS-Project` rather than to the checkout beside the main clone.
That is what the two environment variables exist for, and run B uses them.

### Run B — with both checkouts pointed at

```
AUTOSQL_GIMS_TREE="/home/corgea/Desktop/Coding Projects/GIMS-Project" \
AUTOSQL_GUTS_TREE="/home/corgea/Desktop/Coding Projects/GUTS/spine/L1-memory/gims-ledger" \
./run-demo test
```

```
============= 4 failed, 570 passed, 1 xfailed, 1 warning in 43.57s =============
run-demo test: 570 passed, 0 skipped, 1 xfailed, 0 xpassed, 4 failed, 0 errors — B10 checksum guard: verified
```

**Zero skips.** Seven of the nine skipped checks pass with the trees present —
including AC-34's tree half, which confirms `demo/vendor/expr.py` is byte-identical
to the live `core/dashboard/expr.py` at
`90cbb56d04b08b825ef38dbd1b805ad2b877a0f5e5154e2dc38d9944f4ad4c49`. The other two
are **AC-35**, and they fail; §6 below says why that is not a write by this ticket.

### Runs C, D and E — after AC-19 landed (2026-08-22)

Runs A and B above predate `demo/tests/test_expr_vectors.py` and are left exactly
as they were measured; they are the reason the skip breakdown there has no AC-19
line. These three are the current ones. The pass count rises by four (AC-19's one
tree-dependent test plus its three that need no checkout) and the skip count by
one.

**Run C — as the machine stands** (no `AUTOSQL_GIMS_TREE`, no `AUTOSQL_GUTS_TREE`;
this build runs in a git *worktree*, so `../GIMS-Project` resolves to
`/home/corgea/GIMS-Project`, which does not exist):

```
====== 568 passed, 10 skipped, 1 xfailed, 1 warning in 205.71s (0:03:25) =======
run-demo test: 10 skipped, and what each was looking for:
    6 x D1 (tree half): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-19 (the 130 fixture cases at tests/fixtures/expr_vectors.json): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-34 (tree half): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GIMS-Project): no GIMS checkout at /home/corgea/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GUTS spine copy): no GIMS checkout at /home/corgea/GUTS/spine/L1-memory/gims-ledger — set AUTOSQL_GUTS_TREE to point at one
run-demo test: 568 passed, 10 skipped, 1 xfailed, 0 xpassed, 0 failed, 0 errors — B10 checksum guard: verified
```

**Zero failures**, and the AC-19 line is in the breakdown where §6.5 says it
should be.

**Run D — AC-39(a)'s literal test**: both variables pointed at paths that do not
exist (`AUTOSQL_GIMS_TREE=/nope/GIMS-Project`,
`AUTOSQL_GUTS_TREE=/also-nope/gims-ledger`):

```
============ 568 passed, 10 skipped, 1 xfailed, 1 warning in 47.43s ============
run-demo test: 10 skipped, and what each was looking for:
    6 x D1 (tree half): no GIMS checkout at /nope/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-19 (the 130 fixture cases at tests/fixtures/expr_vectors.json): no GIMS checkout at /nope/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-34 (tree half): no GIMS checkout at /nope/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GIMS-Project): no GIMS checkout at /nope/GIMS-Project — set AUTOSQL_GIMS_TREE to point at one
    1 x AC-35 (GUTS spine copy): no GIMS checkout at /also-nope/gims-ledger — set AUTOSQL_GUTS_TREE to point at one
run-demo test: 568 passed, 10 skipped, 1 xfailed, 0 xpassed, 0 failed, 0 errors — B10 checksum guard: verified
```

All **three** criteria AC-39(a) names are in that list, each naming the path it
looked for — which is the first run in which that sentence has been true (§6.5).

**Run E — with both checkouts pointed at**, the same command as run B:

```
======== 2 failed, 576 passed, 1 xfailed, 1 warning in 67.35s (0:01:07) ========
run-demo test: 576 passed, 0 skipped, 1 xfailed, 0 xpassed, 2 failed, 0 errors — B10 checksum guard: verified
```

**Zero skips, and AC-19 passes with the checkout present** — printing the split
quoted in §6.5. The two failures are `test_ac35_gims_tree_not_modified` on both
trees: **§6.2's pre-existing dirt, unchanged**, and not a write by this ticket or
by AC-19's reader, which opens one file and imports nothing from either tree.
Run B recorded four failures here; the other two — §6.1's step-13 claim and
§6.3's AC-37 hit — are gone, which is what run C's zero failures says. These two
remain exactly as §6.2 describes them.

### The B10 checksum guard

`B10 checksum guard: verified — demo.records unchanged across the session (md5
c0929f731ebb499d2af269369da7faeb)`, on every run above, and that md5 equals
`demo/manifest.json`'s `seed:demo.records:md5`. The suite's two sanctioned writes
— AC-23(a)'s mutation and AC-45(b)'s scratch row — were both reverted, and this is
the check that says so rather than the code that promises it.

---

## 6. What is failing, and what it means

Four distinct failures across the two runs. None of them is a wrong number from
the demo; all four are recorded here with the evidence, because a green claim
would be worth less than this. **§6.1 has since been CLOSED** by the correction
recorded below (2026-08-22); the run outputs quoted above predate it and are left
exactly as they were measured. **§6.5 was never a failure at all** — it was a
criterion nothing implemented, and it is now implemented, measured and closed;
runs C, D and E in §5 are the ones that show the current state.

### 6.1 The step-13 `inf` — W17's finding, **now CLOSED**

**Status: CLOSED 2026-08-22. Real, and a documentation decision rather than a
defect in the demo's arithmetic — resolved by correcting the documents.** The
failing test is gone; the check that replaced it is
`test_walkthrough.py::test_step_13_neither_side_can_read_edge_03s_huge_number`,
which asserts the measured behaviour below and fails loudly if any of it moves.
What follows is the finding as W17 recorded it, then the ruling taken.

Walkthrough step 13, spec **AC-17**, and `expected-answers.json`
(`steps[12].expect.python_pane`) all **said** the Python pane reports **`inf`**,
and `demo/pyrunner/rows.py`'s own docstring **said** `record_f` "parses that to
`float('inf')`". Measured on the running demo, none of that happened:

| what | measured |
|---|---|
| `edge-03`'s `data::text` as jsonb renders it | a **401-digit integer literal** — no `.`, no `e` |
| `json.loads(raw)["huge"]` | a Python **`int`** of 401 digits, because `parse_float` never fires on an integer literal |
| `expr.evaluate` on `$.huge * 1` | raises **`OverflowError: int too large to convert to float`** in GIMS's own `expr.py`, `_to_num`, line 310 (`f = float(v)`) |
| the Python pane | `state: "raised"`, no rows, with the exception named in its note |

**This was already known and already ruled — in one place only.**
`demo/server/app.py` carries a `NEW RULING (W13-2)` immediately above
`_fallback_python_pane` that records the same `OverflowError`, explains the same
cause, and rules the raise **correct**: *"it is what GIMS's evaluator really does
with this value, and saying so is a stronger statement of the demo's point than an
`inf` would be — neither side can read it."* That ruling was never carried into
AC-17, `WALKTHROUGH.md`, `expected-answers.json` or `rows.py`'s docstring, so the
three producers AC-31 names now disagree on this one entry.

**Corroborated independently, the same day, by work that shares no code path with
this demo.** T-3's correctness run — different worker, different codebase path,
different purpose — recorded as one of its findings: *"Python `_eq` raises
`OverflowError` on a 10^400 JSON integer while SQL answers — a ninth, uncatalogued
raise site"* (`spikes/T-3/FINDINGS.md`). Two independent measurements, one
conclusion.

**Two ways to close it were open:**

1. Write W13-2 into the documents — AC-17's wording, step 13's prose, and
   `demo/seed/expectations.py`'s `python_pane` entry — so all three say *the
   second calculator refuses this value too, by name*. This keeps GIMS's `expr.py`
   byte-identical, which D1/D2/AC-34 require, and it is the stronger demo point.
2. Change `demo/pyrunner/rows.py`'s `record_f` parse so an integer literal above
   `DBL_MAX` becomes `float('inf')`, which makes the documents true as written.

**THE RULING (2026-08-22, under Evan's standing GA-6, on the strength of the two
independent measurements): option 1. W13-2 stands — the documents are corrected,
and the code is NOT changed to manufacture an `inf`.**

Option 2 was refused on the merits, not on ownership. Making `rows.py` yield an
`inf` for an integer literal would make the demo **lie about what Python actually
does** with that row — the precise failure mode this whole project exists to
prevent, and it would have been invisible: every producer would have agreed, and
the agreement would have been manufactured rather than derived. The true outcome
is also the stronger demo point: **neither** calculator can read this value, which
says more than one side printing an unverifiable `inf` beside the other side's
refusal.

**Corrected at their source, each derived from the true behaviour rather than
edited to match one another:**

| file | what changed |
|---|---|
| `.autodev/specs/T-2.md` | a dated correction note beside **AC-17**, overturning one clause (*"the Python pane shows `inf` as literal text"*). The signed text is left intact above it; the rest of AC-17 is unaffected |
| `demo/seed/expectations.py` | step 13's `python_pane` entry → `"raised"`, with a derivation rewritten from jsonb's numeric rendering and JSON's integer-vs-float grammar; the step's own derivation no longer claims an `inf` |
| `demo/expected-answers.json` | regenerated from the above (`python -m demo.seed.expectations`) |
| `demo/WALKTHROUGH.md` | step 13's prose, in plain language: why **both** sides fail to read the number, and why that is more honest than one side inventing an infinity |
| `demo/pyrunner/rows.py` | `source_row`'s docstring — the `float('inf')` claim replaced with the real mechanism, and the reason manufacturing an inf here would be the wrong fix |
| `demo/pyrunner/evaluate.py` | the aggregate note that cited edge-03 as its non-finite example; the mechanism it documents is real, the example was not |
| `demo/tests/test_walkthrough.py` | the failing test rewritten as `test_step_13_neither_side_can_read_edge_03s_huge_number`, asserting the literal's shape, both parses, and the raise out of GIMS's own `expr.py`. `steps[12].expect.python_pane` also came **off** `NOT_APP_OBSERVABLE`: the corrected value is the pane's published state, which the API does return, so AC-31's third leg is now a real comparison here instead of a carve-out |
| `demo/EVIDENCE.md` | this section, and the mirrored derivation row in §5 |

`demo/vendor/expr.py` was **not** touched: it stays byte-identical to GIMS's, as
D1/D2/AC-34 require. That is the point — the raise is GIMS's real behaviour, and
the demo now reports it instead of contradicting it.

**Everything else about step 13 passes:** it is refused at layer 2 member (a), the
refusal names `edge-03`, SQL *was* generated (the visible difference from step
10's static refusal), the statement was never sent, and the SQL pane shows no
number.

### 6.2 `test_ac35_gims_tree_not_modified` (both trees) — pre-existing dirt, not this ticket

`git status` in both GIMS checkouts is non-empty, so AC-35 fails as written. It is
**not** a write by this ticket, and that is checkable rather than assertable:

| modified file | mtime |
|---|---|
| `api/app.py` | 2026-08-13 10:37 |
| `api/manifest/resolver.py` | 2026-08-13 11:08 |
| `api/routers/account_roles/logins_db.py` | 2026-08-13 11:09 |
| `backups/_config/schedules.json` | 2026-08-13 10:30 |
| `nodes/login_fastapi_users_node.py` | 2026-08-13 11:08 |
| `projects/RunlogTest/autogen_counters.json` | 2026-07-03 21:34 |
| `tests/test_rds_fallback_is_announced.py` (untracked) | 2026-08-13 11:08 |

Every one predates this build window (2026-08-22) by nine days or more. The file
this ticket actually reads, `core/dashboard/expr.py`, has mtime **2026-07-02
14:15** and sha256 `90cbb56d…`, identical to the vendored copy and to the manifest.
So AC-35's *intent* — this ticket never wrote to GIMS — holds and is proven by
mtime and digest; AC-35's *test* — `git status` clean — cannot pass on a working
tree its operator is actively using. That is a criterion wording question for
Evan, and it belongs to W2.

### 6.3 AC-37's timing-vocabulary sweep — W18's, one hit

`test_isolation.py::test_ac37_no_...` reports exactly one hit, at
**`demo/compose.yaml:33`**: a comment describing the readiness poll writes its
interval as a bare number glued to the unit abbreviation, which is precisely the
shape AC-37's grep looks for. (The line is not reproduced here, because quoting it
would put a second hit in this file — which is itself inside the swept tree.)

It is a poll interval in a code comment, not a claim about how quickly the demo
answers anything, but AC-37's grep is deliberately blunt and the fix is to reword
the comment — spell the interval out in words, or move the figure into
`./run-demo`'s own constant, which is outside the swept set. **W18's row in plan
§6.2 owns AC-37.** Not touched here, and this failure predates W17: it is present
in the run recorded before any of W17's tests existed.

### 6.4 One `xfailed`, and nothing `xpassed`

`0 xpassed` on every run — the expected failure is still failing for its stated
reason, which is what makes it evidence rather than a leftover.

### 6.5 AC-19 — was "not implemented anywhere", **now implemented and measured**

**Status: CLOSED 2026-08-22.** This section used to read *"a sweep of
`demo/**/*.py` finds no reference to AC-19 or to
`tests/fixtures/expr_vectors.json`"*, and it was true: nothing ran the gate over
the fixture, and run A's nine skips carried no AC-19 line. Both facts have
changed, and this is what replaced them.

**What runs now.** `demo/tests/test_expr_vectors.py` — four tests, named after
the fixture it reads, in the same `test_*.py` shape as its neighbours:

| test | needs a checkout? | what it does |
|---|---|---|
| `test_ac19_the_gate_over_every_fixture_case_reported_per_case` | yes — **loud skip** without one | parses every case with the demo's own vendored `expr.py`, runs `demo/gate.py`'s gate over each parsed tree, and writes a per-case report |
| `test_ac19_skips_loudly_when_the_checkout_is_absent` | no | proves the skip line names the path **and** `AUTOSQL_GIMS_TREE`, in-process against a forced-missing path, rather than trusting today's machine |
| `test_ac19_this_module_cannot_fail_on_the_number` | no | reads the module's own syntax tree and fails if any `assert` in it ever mentions the split or the numbers 68 / 62 |
| `test_ac19_the_report_path_is_where_a_person_can_read_it` | no | the artifact is a fixed, committed path under `demo/`, not a temporary file |

It resolves the checkout through `test_vendor.py`'s **own** `_resolve_tree` and
`_skip_reason` — imported, not copied — so there is exactly one place that
decides where a checkout is and what a skip line says, and no run can call a
tree present for one check and absent for another. Nothing is imported *from*
the checkout: the parser is `demo/vendor/expr.py` (R4), so no `__pycache__` is
ever written into a read-only tree, which is what AC-35 watches for. The tree is
opened for exactly one file — the fixture — and read.

**The measured split: 68 accepted / 62 refused of 130 — this matches AC-19's
expected reading exactly.** Nothing was adjusted to reach it; the number was
measured once and has been the same on every run since.

**Where the per-case report lives:** `demo/ac19-expr-vectors.md`, regenerated by
every `./run-demo test` that can see a checkout, overridable with
`AUTOSQL_AC19_REPORT`. It carries the fixture's path, sha256
`0091df64283d91cbcae75c814d56f9a5b759881044962b068544da8e10003552` and 15,499
bytes, the refusals grouped by construct, and then **all 130 cases one row
each** — case identifier, the expression, the verdict, and for a refusal the
construct the gate named and the rule it gave. The 62 refusals are 16 distinct
constructs: `days_between` 9, `string` 8, `%` 7, `date_add` 7, `contains` 5,
`round` 5, `sum` 4, `concat` 3, `number` 3, `avg`/`ceil`/`floor`/`lower` 2 each,
`now`/`today`/`upper` 1 each. Every one of them is a construct §4.2 excludes on
purpose — 15 of the 22 builtins, plus `%`.

**It cannot fail on the number, and that is enforced rather than promised.** The
criterion's own words: *"it never passes or fails on the number"*, because 68 of
130 is a **contract-surface** measure (§0) — how much of the *test file* is
inside the subset, never how much of real use is covered — and `FINDINGS.md`
§5.7(i) forbids quoting it at a gate. The module therefore asserts only that the
report could be produced: every case yields `accepted` or `refused` (a crash, an
unparsable expression or a case with no `expr` fails it), every refusal names a
construct **and** a rule (a bare "refused" fails it), and every case has its own
row with its own verdict in the written file (a missing per-case verdict fails
it). `test_ac19_this_module_cannot_fail_on_the_number` is the guard on that
promise, checked mechanically against the module's own syntax tree.

#### The finding worth writing down: there are two different 68s

The fixture carries **68 cases with a `record`** and the gate **accepts 68
cases**, and it is tempting to read one as the other. They are not the same 68:
**24 cases are in each set and not the other.** `arithmetic/add` (`1 + 2`) is
accepted and carries no record; `aggregates/sum_list` carries a record and is
refused, because `sum` is outside the subset. The equal size is a coincidence of
this fixture.

That is exactly the distinction §0 and AC-19 draw, now measured rather than
argued: the gate decides **from the AST alone**, so its 68 is contract-surface —
a property of which constructs the fixture's expressions use. A count of the
cases carrying rows would be *runtime-witnessed* — a property of the data the
fixture happens to ship. Anyone quoting "68" should say which one they mean.

#### One thing AC-19's wording does not settle, and the reading taken

AC-19 says the suite runs the gate over **"all 130 cases"**, and separately that
the criterion *"never passes or fails on the number"*. If GIMS ever grows or
trims the fixture, those two sentences point opposite ways: is a fixture of 131
cases a failure, or a finding?

**The reading taken: it is a finding.** The module reports the measured case
count against the 130 AC-19 names — on the terminal and at the top of the
artifact, prefixed `AC-19 FINDING:` — and does not fail. The reasoning is that
the build must not go red because a tree this ticket does not own changed
underneath it, and a loud finding is what stops that change passing unnoticed.
It is **one assertion away from the other reading** (`assert len(cases) ==
EXPECTED_CASE_COUNT`, in `demo/tests/test_expr_vectors.py`), and it is Evan's to
overturn. Today the count is 130, so the question is not live — only recorded.

#### Both legs of AC-19's own *Test:* clause, run

*With* the checkout — `AUTOSQL_GIMS_TREE="/home/corgea/Desktop/Coding
Projects/GIMS-Project"`, printed by the suite itself:

```
AC-19 (reported observation, no threshold): 68 accepted / 62 refused of 130 fixture cases.
AC-19's expected reading is 68 accepted / 62 refused — this run MATCHES it.
AC-19 per-case report written to /home/corgea/autoSQL-T-2-build/demo/ac19-expr-vectors.md
```

*With `AUTOSQL_GIMS_TREE` pointed at a path that does not exist* —
`AUTOSQL_GIMS_TREE=/nope/GIMS-Project`:

```
SKIPPED [1] demo/tests/test_expr_vectors.py:346: AC-19 (the 130 fixture cases at
tests/fixtures/expr_vectors.json): no GIMS checkout at /nope/GIMS-Project — set
AUTOSQL_GIMS_TREE to point at one
```

All four parts of §9.7's loud skip: `SKIPPED` rather than passed or omitted; the
path it looked for **and** the variable that moves it, plus which file inside the
checkout it wanted; counted separately in the summary (run C below); and the
three tests that need no checkout still ran and still passed in the same run.

#### AC-39(a) — checked, not assumed

AC-39(a) names **three** things that must report `SKIPPED` with both tree
variables pointed at nothing: AC-19, AC-34's tree half, and AC-35. Before this
work the run proved two of them and AC-19 was simply absent, so the claim was not
satisfiable however it was worded. Run D below is that criterion's literal test —
both variables pointed at paths that do not exist — and all three are now there,
each naming the path it looked for, counted separately from the passes, with
AC-34's manifest half among the passes as AC-39(b) requires.

---

## 7. What W17 asserted, criterion by criterion

Every row was run; the "where" column is the test that ran it.

| criterion | verdict | where |
|---|---|---|
| **AC-22** — Python `1e+300`, SQL `1`, flagged | **pass** | `test_walkthrough.py::test_ac22_step_11_python_says_1e300_where_sql_says_1_and_it_is_flagged`, `…_is_not_a_pane_that_failed_to_run`, `…_is_reproducible` |
| **AC-30** — all 14 steps performed, each producing its stated result | **14 of 14 pass** (was 13 of 14; step 13's Python-pane claim closed 2026-08-22 — §6.1) | `test_walkthrough.py::test_step_1_…` … `test_step_14_…`, plus `test_step_13_neither_side_can_read_edge_03s_huge_number` |
| **AC-31** — walkthrough = `expected-answers.json` = the app | **51 of 51 app-observable entries agree** (was 50 of 50; `steps[12].expect.python_pane` moved from the non-observable list to the sweep on 2026-08-22 — §6.1) | `test_ac31_all_three_producers_agree`; coverage proven by `test_ac31_the_sweep_covers_every_entry_in_the_file` (51 observed + 8 named non-observable = 59) |
| **AC-38(b)(c)** — zero statements, table survives, `AS "alive"` | **pass** | `test_step_14_the_hostile_column_name_never_reaches_sql`, `test_step_14_the_retyped_alias_is_accepted_and_emitted_quoted` |
| **AC-40(a)** — kept count 700–1,100 on **each pane separately** | **pass** — 861 on both | `test_step_9_only_the_rows_that_changed`; the ts-included negative control returns **8,400** in `test_step_9_negative_control_…` |
| **AC-40(e)** — the compared value is a builder constant; no picker | **pass** (pre-existing, verified running) | `test_builder_sql.py` (code half), `test_ui.py` (screen half) |
| **AC-41(b)** — five picks × 10 runs, identical sequence | **pass** | `test_order.py::test_ac41b_ten_runs_of_one_pick_return_one_sequence` (5 params) |
| **AC-41(c)** — Python's sequence = SQL's element for element | **pass** | `test_order.py::test_ac41c_the_two_panes_sequences_are_equal_element_for_element` (5 params) |
| **AC-41(d)** — step 5's ten *lowest* keys, each pane separately | **pass** | `test_walkthrough.py::test_step_5_the_tiebreak_runs_ascending_under_a_descending_sort` |
| **AC-41(e)** — three bands on `noun:Sample`, plus the `--locale=C` grep | **pass** | `test_order.py::test_ac41e_three_bands_in_spec_order_on_a_field_some_rows_omit`, `…_the_compose_file_pins_the_C_collation` |
| **AC-43(b)** — hostile inherited zone, 7 × 1,200 on each pane | **pass** | `test_walkthrough.py::test_ac43b_a_hostile_client_zone_does_not_move_the_day_boundary`, `…_a_hostile_database_default_does_not_move_it_either` |
| **AC-43(c)** — the labels are fixed-width UTC strings | **pass** | `test_walkthrough.py::test_ac43c_the_bucket_labels_are_fixed_width_utc_strings` |
| **AC-43(d)** — the zone is on the screen beside `extra_float_digits` | **pass** | `test_ui.py` (W14's) + `test_walkthrough.py::test_ac43_the_pinned_zone_is_on_the_screen` |
| **AC-44(a)(b)(c)** — the key formats, and text order = record order | **pass** | `test_order.py::test_ac44a_…` (3 params), `test_ac44b_key_order_is_record_order_on_the_heartbeat`, `test_ac44c_python_sorts_the_keys_exactly_as_postgres_does` (3 params), `test_ac44_the_hyphen_case_…` |
| **AC-45(a)(b)(c)** — the alias namespace is read from the data | **pass** | `test_alias.py::test_ac45a_…` (3), `test_ac45b_a_key_no_seeded_row_carries_is_refused_on_a_scratch_collection`, `test_ac45c_…` (17) |

### The measured numbers behind those rows

| step | what | SQL pane | Python pane | verdict |
|---|---|---|---|---|
| 2 | whole collection | 8,400 rows, `hb-01-0000` … `hb-50-0167` | 8,400, same first and last | agree |
| 3 | `alive` computed | 7,543 true / 857 false | 7,543 / 857 | agree |
| 4 | `$.status != "ok"` | 857, first `hb-01-0148` (`warn`) | 857, same | agree |
| 5 | `$.ts` desc, cap 10 | `hb-01-0167` … `hb-10-0167` | identical ten | agree |
| 6 | `sum($.payload.load)` | `400207.000000` | `400207.000000` | agree |
| 7 | day buckets | 7 × 1,200 | 7 × 1,200, same labels | agree |
| 8 | 3-point rolling avg | 8,400 cells, column sha256 `51198c3c…` | 8,400 cells, **same digest** | agree |
| 9 | changed rows | 861 (band 700–1,100) | 861 | agree |
| 10 | `round(…, 1)` | no SQL at all | not asked | refused, layer 1 |
| **11** | **`max($.l)`** | **`1`** | **`1e+300`** | **disagree** |
| 12 | `$.where == "alpha"` | abandoned, probe (b) on `edge-02` | 0 of 10 kept, reported fallback | no-compare |
| 13 | `$.huge * 1` | abandoned, probe (a) on `edge-03` | `raised` (see §6.1) | no-compare |
| 14 | hostile alias | no SQL at all | not asked | refused, layer 1; 10,410 rows still there |

Step 8's digest is the one to notice: `51198c3cf2903f0020ec3db926829bd9491e7993f0ce78d123cc464c28bef06b`
is sha256 over **all 8,400** rolling cells in key order, computed independently on
each pane and equal to `expected-answers.json`'s `steps[7].expect.column_sha256`,
which `demo/seed/expectations.py` derived without importing either pane. A pane
that divided by 3 at the first two rows of every sender — 100 wrong cells out of
8,400, all outside any five-row sample — changes that digest.

---

## 8. Rulings W17 recorded

**W17-1 — AC-43(b)'s container half is created at the database, not by restarting
the container.** The criterion says to start the app with the container's `TZ` set
to `America/New_York`. Restarting `autosql-demo-db` inside the suite would take
the stack down under every other test in the run, so the same condition is created
where it lands on a session: a `TimeZone` default attached to the demo's own
database (`ALTER DATABASE … SET TimeZone`, removed in a `finally`, with
`pg_db_role_setting` asserted empty afterwards). **Measured and stated rather than
assumed:** that half is the *weaker* of the two, because `-c timezone=UTC` in the
connection's startup packet already beats a database-level default. The `PGTZ`
half is the strong one — `PGTZ` **beats** the startup packet (B13-EXT-3 measured
it, and this test reproduces the measurement: after `RESET TimeZone` the session
reports `reset_val = 'America/New_York'`, source `client`, and buckets
`hb-01-0000` into `2026-08-13T00:00:00Z`, the previous day). Only the explicit
`SET TIME ZONE 'UTC'` saves the answer there. Both halves are asserted.

**W17-2 — six of the walkthrough's numbers are checked one layer below
`POST /api/pick`, and the layer is named.** The route renders a page of 50 rows
(B25) and offers no pager, so step 2's `last_key`, step 3's two counts over 8,400
rows and step 8's 8,400-cell digest cannot be read off a response. For those,
`_full_panes` calls the same functions `run_pick` calls — `normalised_pick` →
`legality.evaluate` → `collection_keys` → `builder.build` → `sql_pane` /
`python_pane` — and skips only the paging. It is the route with the fold removed,
not a second implementation, and it is used **only** where a page cannot answer.
The route's own `comparison.compared_rows` (8,400 for step 2) is what proves the
API itself compared the full result.

**W17-3 — AC-45(c)'s premise is measured before the criterion is asserted.** (c)
only proves the alias list is the *union over the collection* if a single row's
keys would be a wrong answer. Measured: `noun:Sample` rows carry between 5 and 15
of the fifteen `field_n` keys in 11 distinct subsets, 179 rows carry all fifteen,
and the first row in key order (`smp-0000`) carries 13 — so a build reading one
row would let `field_13` and `field_14` through as aliases. Those facts are
asserted first, so a reseed that made every row carry all fifteen would fail
loudly rather than let (c) pass by accident.

---

## Step 11's witness, and why it will have to move again — 2026-09-01, GA-11

**What step 11 shows today.** `max($.m)` over `noun:EdgeCase`. Row `edge-01` carries
`"m": ["１２３", 1]` — full-width digits. Python's coercion is Unicode-aware and reads **123**; the
vendored runtime's ASCII gate returns NULL, so SQL's `max()` answers **1**. Python **123** beside
SQL **1**, flagged, one row differing. Verified live on the running stack, not inferred.

**Why it is not `$.l` any more.** It was, and `$.l = [1e300, 1]` no longer diverges: the shipped
297-digit guard that silently nulled `1e300` was a *defect*, T-3 corrected it to 309 digits, and
Evan's q4 ruling adopted the corrected runtime. Both engines now read `1e300`, so `max($.l)` agrees.
**The original showcase divergence was an artifact of the bug the adopted fix removed.** Full note
against AC-22 in `.autodev/specs/T-2.md`.

**Why it will have to move a third time — read this before touching T-8.** T-6 (ruled 2026-09-01,
`kb/wiki/decision-t6-correctness-rerun.md`) adopted **variant C**: `xpr.num` maps the 670 non-ASCII
`Nd` code points onto ASCII, so `float("１２３")` and the compiled SQL **agree**. Measured: zero
divergences at the pinned float setting across 11,367 expressions.

**When T-8 lands variant C in `demo/vendor/`, `$.m` stops diverging exactly the way `$.l` did.**

That is not a regression to fix — it is T-6 passing. And on present evidence **there is no in-subset
value disagreement left after T-8**, which means step 11 cannot keep making the claim it makes now.
The honest successor is the magnitude refusal already demonstrated at step 13 (`edge-03`), and
step 11's claim changes from *"the two engines disagree"* to *"the tool refuses rather than
guessing"*.

**That changes what the demo argues, so it is Evan's call, not T-8's.** It is written down in three
places — here, against AC-22, and in `kb/CURRENT-WORK.md` — so T-8 cannot make it by accident.

## The differing column sits beside the marker — q8, GA-8

Evan, 2026-08-23: *"Fix it first — move the differing column beside the marker."* Implemented
2026-09-01.

The grid is `[SQL pane | coral spine | Python pane]`, so "beside the marker" is **mirrored about the
spine**: the differing columns move to the far **right** of the left pane and the far **left** of
the right pane, putting the two values either side of the `≠` and touching it. Verified live:

```
SQL order    : collection · key · data · biggest      value at the marker: 1
Python order : biggest · collection · key · data      value at the marker: 123
```

**The order is computed on the server** and published as `column_order`, a permutation of column
indices. `columns` and `kinds` are untouched, so every criterion asserting on them still holds and a
client ignoring the field renders what it always did. **An agreeing pick is not reordered at all** —
nine picks in ten must not move, or the screen becomes unpredictable for the sake of the tenth.

Six end-to-end tests in `demo/tests/test_ui.py::TestTheDifferingColumnSitsBesideTheMarker` pin it:
both orders are permutations of every column, agreeing picks stay natural, the differing block is
adjacent to the spine on both sides, the two orders mirror each other, untouched columns keep their
relative order, and the built bundle actually reads the published order (so a stale bundle fails).
