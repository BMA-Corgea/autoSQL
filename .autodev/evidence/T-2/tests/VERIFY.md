# T-2 — the verification record (stage: `verify`)

This is the record of the last check before Evan's own acceptance gate. It was
produced by driving the **running app** — the same stack `./run-demo up`
starts, app on `127.0.0.1:8787`, the demo's own database on `127.0.0.1:55440`
— over HTTP, through `POST /api/pick`, the same route the screen posts to.
Nothing here was produced by reading the code, and nothing here was produced
by the test suite except where a line says so explicitly.

| | |
|---|---|
| Produced by | the `tester` seat, stage `verify`, 2026-08-22 |
| Against | the stack brought up from `main` (app `127.0.0.1:8787`, database `127.0.0.1:55440`) |
| How | `./run-demo test` for regression (§1); raw HTTP `POST /api/pick` for every walkthrough step (§2–§4); `./run-demo down` + `./run-demo up` for the cold start (§5) |
| What was **not** verified | §6 — read it before accepting anything above it |

**All the data below is invented.** Nothing here describes a real sender, a
real customer, or anything that happened anywhere.

**What this demo never touches.** The demo owns ports `55440` and `8787` and
nothing else. No command run for this record dialled Evan's live database, on
any port, at any point. (That machine's port number is deliberately not
written here — AC-3 forbids it appearing anywhere in the demo tree, this file
included.)

---

## 1. Regression — the whole suite, against the running stack

Command: `./run-demo test` (it detected and used the stack already up — its
own first lines say `using the stack already up`). The suite collected
**1,143** tests. The real final lines, verbatim:

```
============= 2 failed, 1141 passed, 1 warning in 61.35s (0:01:01) =============
run-demo test: DISCLOSURE — plan §8.2's mutation pass HAS NOT RUN. './run-demo test --mutants' is not implemented — plan §8.2 has never run, here or anywhere under demo/.
run-demo test:   M1, M4, M8, M16 were hand-run once and killed. M6, M12, M13 have standing detector tests in this suite.
run-demo test:   The other nine of the sixteen have never been watched failing. The counts below are the ordinary suite and are not evidence for §8.2.
run-demo test: 1141 passed, 0 skipped, 0 xfailed, 0 xpassed, 2 failed, 0 errors — B10 checksum guard: verified
```

The B10 checksum guard line earlier in the run reads:
`B10 checksum guard: verified — demo.records unchanged across the session
(md5 c0929f731ebb499d2af269369da7faeb)` — the seeded table was byte-identical
before and after the whole suite ran.

### 1.1 The two failures, named and explained

Both failures are the two halves of **one** test —
`demo/tests/test_vendor.py::test_ac35_gims_tree_not_modified`, once for each
GIMS checkout:

```
FAILED demo/tests/test_vendor.py::test_ac35_gims_tree_not_modified[GIMS-Project-_gims_tree]
FAILED demo/tests/test_vendor.py::test_ac35_gims_tree_not_modified[GUTS spine copy-_guts_tree]
```

AC-35 asserts that neither GIMS checkout on this machine has been modified.
Both checkouts currently carry **uncommitted edits** (the failure output lists
them: files under `api/`, `nodes/`, `projects/RunlogTest/`, and an untracked
test file). Those edits are **Evan's own work in his own checkouts** — they
predate this ticket and nothing in this demo wrote them. The test cannot tell
whose edits they are; it can only see the trees are not clean, and it is right
to say so. This is a known standing item that is **Evan's decision** (commit,
stash, or discard his own edits), not a defect in the demo — but it is
reported here as the failure it literally is, because a verification record
that reclassified a red test as green would be worthless.

**Every one of the other 1,141 tests passed.** No test was skipped.

### 1.2 A disclosure the suite itself prints

The suite prints, on every run, that plan §8.2's sixteen-mutant mutation pass
**has never run** — four mutants were hand-run once, three have standing
detector tests, and nine have never been watched failing. That caveat travels
with the numbers above and is repeated in §6.

---

## 2. The fourteen walkthrough steps, driven through the live API

Every step of `demo/WALKTHROUGH.md` was sent to the running app as a raw HTTP
`POST http://127.0.0.1:8787/api/pick` — not through the test suite, not
through `fastapi.testclient`, but over the wire against the live process.
Every number below was then compared against `demo/expected-answers.json`
(the third, independent path — produced without importing any of the demo's
calculators). **Every comparison matched. No step returned a number that
differed from the expected answer.**

Three details of how the API answers, so the table reads right:

- The **comparison is computed server-side over every row** — `compared_rows`
  is the full result, not a sample. The 50-row page in each pane is display
  only.
- Because the page shows 50 rows, a few walkthrough numbers live off page 1
  (step 2's *last* key, step 3's true/false split, step 8's worked sender
  `hb-18`). Those were verified with **companion picks** through the same
  live route — each one labelled below — never by trusting the document.
- A refused pick answers HTTP **422** with `accepted: false` and a structured
  `refusal`; an accepted one answers HTTP **200**. Both are recorded.

### The headline table

| Step | Pick (the operative part) | Expected | The live app returned | Verdict |
|---|---|---|---|---|
| 1 | `./run-demo up` — infrastructure | db `55440`, app `8787`, 10,410 rows | verified in §5 (cold start) | — |
| 2 | source `noun:Heartbeat` | 8,400 rows, first `hb-01-0000`, last `hb-50-0167` | 8,400 / 8,400 rows, first `hb-01-0000`; last key via companion (below) | **agree** |
| 3 | computed `alive = $.status == "ok"` | 8,400 rows; split 7,543 true / 857 false | 8,400 / 8,400 rows, 0 differing; split verified by companion (below) | **agree** |
| 4 | filter `$.status != "ok"` | 857 rows, first `hb-01-0148` (`warn`) | 857 / 857 rows; first row `hb-01-0148`, status `warn` | **agree** |
| 5 | sort `$.ts` desc, cap 10 | the 10 **lowest** keys at the latest instant | `hb-01-0167` … `hb-10-0167`, identically in both panes; first row's `ts` `2026-08-20T23:00:00Z` | **agree** |
| 6 | aggregate `sum($.payload.load)` | `400207` | both panes `400207.000000` | **agree** |
| 7 | time bucket per day, count | 7 buckets × 1,200 | 7 buckets, `2026-08-14…2026-08-20T00:00:00Z`, every count `1200`, both panes | **agree** |
| 8 | rolling window `$.payload.load` | 8,400 cells; worked five on `hb-18` | 8,400 / 8,400 rows, 0 differing; worked five via companion (below) | **agree** |
| 9 | only rows that changed | 861 kept (band 700–1,100) | 861 / 861 rows; first five kept keys as expected | **agree** |
| 10 | computed `rounded = round($.payload.load, 1)` | refused, static gate, names `round` | HTTP 422, layer-1 refusal naming `round`; no SQL existed | **refused as specified** |
| 11 | on `noun:EdgeCase`, computed `biggest = max($.l)` | **disagree**: Python `1e+300`, SQL `1` | verdict `disagree`, exactly 1 differing row — §3 below | **disagree, as it must** |
| 12 | on `noun:EdgeCase`, filter `$.where == "alpha"` | refused at runtime, names `edge-02`; Python fallback keeps 0 | HTTP 422, layer-2 member (b) naming `edge-02`; Python pane `answered`, 0 of 10 kept | **refused as specified** |
| 13 | on `noun:EdgeCase`, computed `scaled = $.huge * 1` | refused at runtime, names `edge-03`; Python pane `raised` | HTTP 422, layer-2 member (a) naming `edge-03`; Python pane `raised`, `OverflowError` named | **refused as specified** |
| 14 | computed column **named** `alive"; DROP TABLE demo.records; --` | refused before SQL; table survives at 8,400 | HTTP 422, alias refusal naming the name and the rule; re-pick returned 8,400 rows | **refused as specified** |

Every accepted step reported `differing_rows: 0` — except step 11, which
reported exactly `1`, and is supposed to. Every response carried the pinned
session (`extra_float_digits = 1`, `TimeZone = UTC`).

### Step 2 — and its companion for the last key

The primary pick returned **8,400** rows in both panes, ordered by `key`,
first row `hb-01-0000`. The claimed last key, `hb-50-0167`, is 8,350 rows off
the display page, so it was reached through the same live route with a
companion pick — filter `$.sender_id == "hb-50"`, sort `$.ts` descending,
cap 1 — which returned exactly one row, key **`hb-50-0167`**, both panes
agreeing. (`hb-50-0167` is `hb-50`'s latest beat, which under fixed-width
keys is also the collection's highest key.)

### Step 3 — and its companion for the split

The primary pick returned 8,400 rows in both panes with the `alive` column,
0 differing. The 7,543 / 857 split was verified by two further live picks:
filter `$.status == "ok"` returned **7,543** rows (both panes), and step 4's
filter `$.status != "ok"` returned **857** — `7,543 + 857 = 8,400`, the
partition the walkthrough asserts, reached by filters rather than by counting
the computed column.

### Step 6 — the sum, on each pane separately

Shape `SCALAR`. The SQL pane answered `400207.000000` and the Python pane
answered `400207.000000` — each checked against the expected `400207` on its
own before being compared to the other, which is the whole point of the third
path (B8): two panes agreeing is no evidence if both share a mistake.

### Step 7 — the buckets, as text

Both panes returned the identical seven `(bucket, count)` pairs:
`2026-08-14T00:00:00Z` through `2026-08-20T00:00:00Z`, each with count
`1200`. Seven buckets and not eight is the pinned `UTC` session doing its job,
and `7 × 1,200 = 8,400` reconciles with step 2.

### Step 8 — and its companion for the worked five

The primary pick returned all **8,400** rolling cells with 0 differing rows.
The five worked cells belong to sender `hb-18`, off the display page, so a
companion pick — filter `$.sender_id == "hb-18"` plus the same window —
returned them through the same live route. Both panes, identically:

| Key | SQL pane | Python pane | Expected |
|---|---|---|---|
| `hb-18-0000` | `27.000000` | `27.000000` | `27.000000` |
| `hb-18-0001` | `57.500000` | `57.500000` | `57.500000` |
| `hb-18-0002` | `67.666667` | `67.666667` | `67.666667` |
| `hb-18-0003` | `88.000000` | `88.000000` | `88.000000` |
| `hb-18-0004` | `88.000000` | `88.000000` | `88.000000` |

Row 3 is the non-terminating division — the row where the 6-place rounding
rule actually decides the last digit. (One honesty note: filtering to one
sender changes nothing for a per-sender window, but it is still a *different
pick* from the walkthrough's; the walkthrough's own pick was also run, over
all 8,400 rows, and agreed with 0 differing. The whole-column digest over all
8,400 cells is asserted by the suite, not re-derived here — §6.)

### Step 9 — only what changed

**861** of 8,400 rows kept, both panes, inside AC-40's 700–1,100 band. The
first five kept keys, read off the live page: `hb-01-0000`, `hb-01-0006`,
`hb-01-0007`, `hb-01-0041`, `hb-01-0056` — exactly the expected five. The
negative control (8,400 kept if the timestamp were wrongly included) is not
reachable through the API — there is deliberately no toggle for it — so it
rests on the suite alone (§6).

### Steps 10, 12, 13, 14 — the four refusals

Quoted from the live responses:

- **Step 10** (static gate, layer 1): headline *"Refused before any SQL
  existed"*; `why`: *"`round` is outside the safe subset — the only functions
  this demo compiles are abs, coalesce, count, if, length, max, min"*;
  `sql_existed: false`, `statement_sent: false`; both panes `not-asked`.
- **Step 12** (runtime probe, layer 2 member (b)): headline *"Refused while
  running"*; `why` names *"container operand … (first such row, by key:
  \"edge-02\")"*; SQL **was** generated and the probe that fired is shown;
  `statement_sent: false` — the pick's own query never ran. SQL pane
  `abandoned`; Python pane `answered` as the labelled fallback, keeping
  **0** of the 10 rows.
- **Step 13** (runtime probe, layer 2 member (a)): `why` names the
  out-of-range magnitude and *"(first such row, by key: \"edge-03\")"*. SQL
  pane `abandoned`; Python pane `raised`, its note naming
  `OverflowError: int too large to convert to float` — **neither side prints
  a number**, which is the step's whole point (and matches the corrected
  AC-17, not the mock's original `inf` — see §4).
- **Step 14** (alias allowlist): the refusal names the offending name in
  full and the rule (*"letters, digits and underscore only, starting with a
  letter or underscore, at most 63 characters"*); `sql_existed: false`.
  Retyping the name as plain `alive` was **accepted** and the SQL pane's
  display shows `AS "alive"`, with the Python pane keying the same column.
  Picking `noun:Heartbeat` again afterwards returned **8,400** rows — the
  table survived, proven by count rather than by the refusal message.

---

## 3. Step 11 — the asserted disagreement, in full

This is the centrepiece: the one step where the two panes are **supposed** to
disagree, because it is the defect this whole screen exists to make visible.
A run where they agreed here would be a **failing** run (AC-22).

**The pick, as sent to the live app:** source `noun:EdgeCase`, one computed
column, `biggest = max($.l)`. (`max` is inside the safe subset — it is `sum`
and `avg` that are refused — which is why this runs where step 10 did not.)

**The SQL the app generated** (display rendering; the executed statement is
identical with bind parameters in place of the literals):

```sql
SELECT r.collection,
       r.key,
       r.data,
       to_jsonb(xpr.reduce_one(('max')::text, nullif((r.data -> ('l')::text), 'null'::jsonb)))  AS "biggest"
  FROM demo.records AS r
 WHERE r.collection = 'noun:EdgeCase'
 ORDER BY r.key ASC;
```

`statement_sent: true` — the layer-2 magnitude probe ran first and did
**not** fire (its threshold is the true `~1.798e+308` limit, deliberately
higher than the 297-digit display guard, so `1e300` passes the probe — the
defect has to stay visible), and the query itself executed.

**What actually came back, on the row that matters** — `edge-01`, whose
stored record is
`{"l":[1e+300,1],"label":"edge case: max of [1e300, 1] — SQL answers 1, Python answers 1e+300; the demo's asserted wrong number"}`:

| | value of `biggest` on `edge-01` |
|---|---|
| **SQL pane** | `1` |
| **Python pane** | `1e+300` |
| **Expected** (`expected-answers.json`, `#steps[10].expect`) | SQL `1`, Python `1e+300` |

**The comparison, verbatim from the response:**

```json
{"verdict": "disagree", "columns_match": true, "differing_rows": 1,
 "first_differing_index": 1, "compared_rows": 10,
 "sql_row_count": 10, "python_row_count": 10}
```

Exactly **one** differing row out of ten, at index 1 — `edge-01` — flagged as
`disagree` rather than silently averaged, hidden, or resolved in either
side's favour. The other nine rows agree (`biggest` is missing on all of
them, identically, in both panes).

**Why each side is right, for what it was asked.** Python reads `[1e300, 1]`
off the JSON and takes the larger — `1e+300` is an ordinary double. The SQL
side runs every number it reads out of the database through the shipped
297-digit guard (deliberately below the true `~1.798e+308` limit of the
float8 type); `1e300` comes back as *missing*, `max` ignores missing values,
and the only element left is `1`. Two defensible readings, one visible
disagreement — which is the product.

Verdict: **`disagree`, with the actual values `1` vs `1e+300`, exactly as
asserted.** This is the run's most important line.

---

## 4. The seven states of the approved mock, each reached on the running app

The mock Evan approved (`design/t2-demo-mock.html`) draws seven states. Each
one was reached on the live app through `POST /api/pick`; the pick that
reaches it and what came back:

| # | Mock state | The pick that reaches it | What the live app returned |
|---|---|---|---|
| 1 | **Agreement** | source `noun:Heartbeat`, computed `alive = $.status == "ok"` (step 3) | `accepted: true`, verdict **`agree`**, 8,400 rows in each pane, `differing_rows: 0`, per-row comparison over all 8,400 |
| 2 | **Time buckets** | bucket `day`, aggregate `count` (step 7) | shape **`BUCKET`**, seven `(bucket, count)` pairs, identical in both panes, labels compared as text |
| 3 | **Only what changed** | the `changed` toggle on `noun:Heartbeat` (step 9) | 861 of 8,400 rows kept, both panes, verdict `agree` |
| 4 | **Disagreement** | `noun:EdgeCase`, computed `biggest = max($.l)` (step 11) | verdict **`disagree`**, 1 differing row (`edge-01`: SQL `1`, Python `1e+300`), flagged |
| 5 | **Refused: the expression** | computed `rounded = round($.payload.load, 1)` (step 10) | HTTP 422, layer-**1** refusal, names `round`, `sql_existed: false`, both panes `not-asked` |
| 6 | **Refused: the column name** | a computed column named `alive"; DROP TABLE demo.records; --` (step 14) | HTTP 422, alias refusal naming the name and the allowlist rule, nothing sent to the database, table proven intact at 8,400 rows |
| 7 | **Refused while running** | `noun:EdgeCase`, filter `$.where == "alpha"` (step 12); also `scaled = $.huge * 1` (step 13) | HTTP 422, layer-**2** refusal; the probe that fired is shown with the offending row named (`edge-02` / `edge-03`); SQL pane `abandoned`; Python pane `answered` (fallback, 0 kept) / `raised` (`OverflowError` named) |

All seven states are reachable from the running app, and each response
carries what the mock draws for it: the verdict strip, both pane states, the
refusal card's headline/why/row, and the generated SQL where any existed.

**One known divergence from the mock, recorded rather than papered over.**
The mock's state 7 drew the Python pane answering **`inf`** for the `1e400`
case. The shipped app reports **`raised`** with `OverflowError` named — and
that is the corrected behaviour, not a defect: the signed AC-17 was amended
by a dated correction note (see `.autodev/specs/T-2.md`, the CORRECTION
beside AC-17, 2026-08-22) after two independent measurements showed the value
reaches Python as an exact 401-digit integer, never as a float literal, so
`inf` is never created. The walkthrough and `expected-answers.json` both
carry the corrected expectation; the live app matches them. The mock predates
the correction and still draws the old reading — worth one sentence when Evan
compares the screen against the mock. (Smaller, same kind: the mock's state 7
names the offending row `edge-04`, where the shipped seed puts `huge` on
`edge-03` — the row the live refusal names, and the one the signed spec's B24
assigns it to.)

**What "reachable" means here, honestly.** Each state was reached as the
screen's own data — the JSON the page renders from. Whether each state
*draws* correctly in a real browser is exactly the visual half nobody on this
machine can verify (§6).

---

## 5. The cold start — down to nothing, up again, clean

The strongest evidence this works for a person and not just for a warm
session: after all of §2–§4, the stack was torn all the way down and brought
back. Real output, verbatim (dependency lines elided where marked):

**`./run-demo down`** — exit 0:

```
run-demo down: stopping the app (pid 2110692)
run-demo down: stopping autosql-demo-db and removing its volume
 Container autosql-demo-db  Stopped
 Container autosql-demo-db  Removed
 Volume autosql-demo-db-data  Removed
 Network autosql-demo_default  Removed
run-demo down: autosql-demo-db container and volume removed.
```

The **volume** was removed, not just the container — so the reseed below
started from genuinely nothing, not from a database that survived.

**`./run-demo up`** — exit 0 (24 `Requirement already satisfied` lines from
the offline wheelhouse elided):

```
run-demo: installing pinned dependencies from the committed wheelhouse (--no-index, B20)
run-demo up: starting autosql-demo-db (docker compose, demo/compose.yaml)
run-demo: waiting for autosql-demo-db to accept connections (Python poll through demo/server/db.py — B21 for the poll, B13 for the fence, up to 60s)
run-demo: autosql-demo-db is ready (attempt 4)
run-demo up: demo/.venv ready, dependencies installed offline (W3).
run-demo up: autosql-demo-db is up on 127.0.0.1:55440, lc_collate=C (W4).
demo/seed: this database holds INVENTED data only — every row was fabricated by demo/seed/generate.py from fixed literal seeds; nothing in it is real.
demo/seed: wrote 10,410 invented rows into demo.records
demo/seed: AC-10 digest verified against demo/manifest.json (c0929f731ebb499d2af269369da7faeb)
demo/seed: demo.records holds 10 noun:EdgeCase / 8,400 noun:Heartbeat / 2,000 noun:Sample — all of it invented
run-demo up: starting the app on http://127.0.0.1:8787 (uvicorn, no Node)
run-demo up: the screen is up — http://127.0.0.1:8787/ (pid 2146541 holds the socket on 8787 and answers /api/operations)
```

Three things this proves, read against walkthrough step 1:

- The database came up on **`55440`** and the app on **`8787`** — the demo's
  own two ports, and no other.
- The seed loaded **10,410** rows — 8,400 + 2,000 + 10 — and the **AC-10
  digest verified** against `demo/manifest.json`
  (`c0929f731ebb499d2af269369da7faeb`, the same value §1's B10 checksum guard
  reported for the previous seeding — the reseed is byte-identical).
- The launcher confirmed the process it started is the one holding the
  socket before calling the screen up.

**And the fresh stack answers the same.** Two picks were re-driven against
the reseeded database: step 2 returned `agree`, 8,400 / 8,400 rows, first key
`hb-01-0000`; step 11 returned `disagree` with `edge-01` at SQL `1` /
Python `1e+300`, exactly 1 differing row — identical to §2 and §3.

The served page was also smoke-checked on the fresh stack: `GET /` answers
200, and every asset the page references — 4 vendored Watery stylesheets,
`demo.css`, the Inter font, `icons.svg`, `vendor.js` (142,177 bytes) and
`app.js` (47,571 bytes) — answers 200.

**And the whole suite was run a second time against the reseeded stack** —
with this very file in place under `demo/`, so the record itself is proven
not to trip any of the tree-wide sweeps (AC-3's forbidden-string grep,
AC-37's no-speed-claim sweep). The final line, verbatim:

```
================== 2 failed, 1141 passed, 1 warning in 59.96s ==================
run-demo test: 1141 passed, 0 skipped, 0 xfailed, 0 xpassed, 2 failed, 0 errors — B10 checksum guard: verified
```

— the same two AC-35 failures as §1, the same 1,141 passes, and the same
`demo.records` checksum (`c0929f731ebb499d2af269369da7faeb`) on the reseeded
data.

**The stack is left running**, as the verify stage found it.

One honest caveat on "cold": the checkout's `demo/.venv` already existed, so
the wheelhouse install was a no-op (`Requirement already satisfied` × 24).
This cold start proves *database-from-nothing and app-from-nothing*; it does
not re-prove *venv-from-nothing on a fresh clone* — that path is covered by
the wheelhouse's own offline-install tests (`test_wheelhouse.py`, all
passing), not by this run.

---

## 6. What was NOT verified — the honest list

Read this section as part of the evidence, not as an appendix.

1. **Nobody has looked at this screen in a real browser.** There is no
   browser on this machine, no browser automation installed, and AC-32
   forbids fetching one (a network dependency the suite must not carry —
   plan B22). Every claim in this record about "the screen" is a claim about
   the **JSON the page renders from** and the **assets the server serves** —
   the page's own JavaScript was served intact but never *executed* here.
   Whether the seven states draw at 1440px as the approved mock draws them —
   layout, the verdict strip, the refusal cards, the per-row marks — has been
   verified by **no one**. The plan's own risk register says this plainly
   (risk 13: "the browser layer is never actually run"). **The one check only
   Evan can do is open `http://127.0.0.1:8787/` and look — that is precisely
   what his acceptance gate is for, and this record does not pretend to have
   done it for him.**
2. **The two AC-35 failures stand.** The GIMS-Project checkout and the GUTS
   spine copy both carry uncommitted edits, so `test_ac35_gims_tree_not_modified`
   fails twice (§1.1). They are Evan's own edits in his own checkouts and
   only he can resolve them; until then, every `./run-demo test` will end
   `2 failed`, and a clean-suite claim cannot honestly be made.
3. **Plan §8.2's mutation pass has never run.** The suite discloses it on
   every run (§1.2): 4 of 16 mutants were hand-run once, 3 have standing
   detector tests, and **9 have never been watched failing**. The 1,141
   passes are the ordinary suite and are not evidence for §8.2.
4. **Two walkthrough numbers rest on the suite, not on this live drive:**
   step 9's negative control (8,400 rows kept if the timestamp were wrongly
   included — deliberately unreachable through the API, asserted by AC-40's
   test) and step 8's whole-column sha256 digest over all 8,400 rolling
   cells (asserted by the suite against the third path; this drive verified
   the worked five cells plus pane-against-pane agreement on all 8,400).
5. **Step 2's last key and step 3's split were verified by companion picks**
   through the same live route (§2), because the display page holds 50 rows —
   they were not read off the walkthrough pick's own page.
6. **Timing overlap, for scrupulousness:** the regression suite (§1) was
   still finishing while the first API steps of §2 ran, against the same
   read-only stack. Both only read; B10's checksum confirms `demo.records`
   was unchanged across the whole session, and steps 2 and 11 were re-driven
   after the cold start (§5) with identical results.
7. **This record verifies the demo, not the integration.** Nothing here says
   anything about GIMS itself — the demo runs on invented data, on its own
   database, behind its own fence, and that is all that was tested.
