# autoSQL

autoSQL compiles the GIMS dashboard expression language into Postgres SQL, so a widget's numbers are
computed inside the database instead of being pulled into Python and reshaped there. It is three
things: a compiler (`compiler/`) that turns an expression AST into a parameterised Postgres
expression, a SQL runtime (`runtime/`) of 24 functions giving Postgres the same value semantics as
GIMS's Python evaluator (`kb/CURRENT-WORK.md`), and a harness that puts the same expression through
both engines and requires them to agree. The agreement is the deliverable — a compiler that is
usually right is worth nothing here.

## Why it exists

GIMS reads up to 20,000 records out of storage and then derives, filters, sorts and cuts them in
Python, so a big answer comes back capped and flagged `truncated` rather than complete
(`kb/wiki/autosql-architecture.md`). Pushing that work into the database is the obvious fix and it
is not the interesting part.

The interesting part is the failure mode. Two evaluators for the same expression language can
disagree about a value and both keep running — no exception, no error, no log line, just a
dashboard showing a number that is quietly wrong. Of 33 ways the Python evaluator and the SQL
translation can diverge, 18 cannot be detected at query time by any mechanism
(`kb/wiki/decision-expr-to-sql.md`). So most of what is in this repo is not the compiler. It is
the evidence that the compiler agrees with the thing it is replacing, and the record of every
place it did not.

GIMS is the information-management system this plugs into — nouns, verbs, dashboards, and the
small per-record expression language those widgets are built from:
https://github.com/BMA-Corgea/gims-oss

## What is in the tree

- **`compiler/`** — `compile.py`, the AST-to-Postgres compiler, and its tests. Float8 results are
  emitted through `xpr.j(...)` rather than bare `to_jsonb(...)`, so a value no longer changes with
  the session's `extra_float_digits`.
- **`runtime/`** — schema `xpr`, the SQL functions the compiled expressions call. `runtime.sql` is
  **generated**: edit `runtime.sql.in`, then run `python3 runtime/generate.py`. Three of its tables
  come from the running Python's `unicodedata` — freeze them as literals and a Python upgrade splits
  the two engines with nobody touching a line of code.
- **`demo/`** — a self-contained screen for driving the idea by hand: its own Postgres, 10,410
  invented rows, a server, and two answer panes side by side. Its test suite lives here too.
- **`spikes/`** — one folder per spike: a `FRAMING.md` (the bar, fixed in writing before any
  evidence was collected), a `FINDINGS.md`, and whatever recon, analysis and prototype code that
  spike needed. **Frozen evidence, not source** — digests of files in here are cited in the findings
  and battery outputs, and tests assert they have not moved. `compiler/` and `runtime/` are live.
- **`kb/`** — the knowledge base. Start at `kb/index.md`, which is a pointer table, not a wall of
  text. `kb/CURRENT-WORK.md` is the state of play; `kb/wiki/` holds the decisions of record and why
  each one was taken.
- **`design/`** — the demo's design brief and its HTML mock. **`ops/`** — small operational scripts.


## Running the demo

You need Docker and CPython 3.12 on x86-64 Linux, which is the only platform the committed
wheelhouse covers (`demo/vendor/wheels/README.md`). From the repository root:

```
./start.sh          # bring it up and open the dashboard
./start.sh stop     # tear it down (container and volume removed)
./start.sh status   # is it running?
```

`start.sh` is a wrapper over `./run-demo`, which does the real work and stays the thing the tests
and CI call. If something goes wrong, run `./run-demo up` directly — it prints everything
untrimmed. The other verbs are `./run-demo down`, `./run-demo test`, and `./run-demo build-ui`.

It brings up its own Postgres container on `127.0.0.1:55440` and serves the screen on
`127.0.0.1:8787` (`kb/CURRENT-WORK.md`), and it refuses to start if either port is already taken
rather than guessing. Python dependencies are installed from a committed wheelhouse (`pip install --no-index`), built
for CPython 3.12 on manylinux x86-64. On that platform, once the first `up` has pulled the Postgres
image (the one step that needs the network), `up` and `test` both run with the network switched off
and with Node removed from `PATH`. On macOS, Windows, or an ARM machine the offline install has no
matching wheel and fails outright rather than half-installing. `build-ui` is the only verb that
needs Node.

`./run-demo test` runs the demo's own suite (`demo/tests/`). The compiler and runtime suites are
pytest with setup of their own: `compiler/tests` wants `AUTOSQL_COMPILER_DSN` pointing at a Postgres
it may use, and `runtime/tests` wants a throwaway Postgres of its own with `runtime/runtime.sql`
loaded and `AUTOSQL_RUNTIME_DSN` set. Without those, `runtime/tests` skips most of its cases and
`compiler/tests` skips the ones that touch a database, rather than failing.
`compiler/README.md` and `runtime/README.md` give the exact steps.

`./start.sh` opens the dashboard at `http://127.0.0.1:8787/dashboard`, described in the next section.
The engineer's two-pane screen is at `http://127.0.0.1:8787/`.

On the two-pane screen you get a picking panel and two answer panes: the SQL pane, which is what Postgres
computed, and the Python pane, a separate program that reads the same rows and works the answer out
again from scratch without asking the database. `demo/WALKTHROUGH.md` is the 14 steps in order
(`kb/CURRENT-WORK.md`) with the number each should produce, checked against
`demo/expected-answers.json` by a test rather than by eye.

Step 11 is the one to look at. It is the value that used to come back wrong — an array holding
`["１２３", 1]`, whose digits are the full-width kind rather than the ordinary `0`–`9`. Python's
`float()` reads digits from any writing system, Postgres's numeric gate does not, and the two
engines returned different numbers with nothing anywhere saying so. They now both report `123`,
because the runtime learned the same digits Python knows. If the panes ever disagree on any step,
the screen says so loudly instead of showing two quiet numbers side by side as though they
matched.

Every row behind the screen is invented, and there is no performance information anywhere in the
demo — that question is answered by the timing runs, below, not by the demo.

## The dashboard: SQL analysis, kept out of sight

The dashboard (`/dashboard`, titled "Data explorer") is **SQL analysis**. Someone picks a data
set, columns, conditions, a sort, a summary — by clicking — and every pick becomes **one
parameterised Postgres statement**, written by `demo/builder.py` through the same compiler as the
rest of the repo. Nothing typed by a person is spliced into the statement's text: the picked
values travel separately, as bind parameters. The statement runs on a **read-only** connection
(`demo/server/app.py :: refuse_writes`), and every answer is **double-checked by a second engine**
— a Python program that reads the same source rows and works the answer out again without asking
the database. "Auto" in the name means the SQL writes itself from the picks, not that anything is
generated by a model.

The everyday screen deliberately shows **none of that**. Its words are the data's words — "Heartbeats
where Status is warn, newest first — 588 rows" — and a test sweeps every state it can reach for
machinery words ("SQL", "query", "expression" and the like). The SQL is there for the people who
want it: switch **View as** to **Admin** and press **Show SQL** to see the statement for the
current picks rewrite itself as they change, with the second engine's verdict beside it. A
consumer of the dashboard never needs to know it is there.

Where it lives: `demo/server/dashboard.py` is the contract (the picks → the statement, the
sentence, the plain-word reasons), `demo/frontend/dashboard*.jsx` draws it, and
`demo/tests/test_dashboard.py` tests it against the live demo database.

## What is proven so far

- **Zero wrong numbers over 11,367 expressions — on `py`-mode data**, across three batteries, with
  zero unexplained raises and zero nullness violations; the 130-case contract fixture is **130/130**
  (`kb/wiki/decision-t6-correctness-rerun.md`). The harness was separately driven with six
  deliberately wrong compilations and reported all six, so its failure paths were dead rather than
  broken (`kb/wiki/decision-expr-to-sql.md`).

  **What that figure does not cover, stated because it leads this section.** Every one of those
  11,367 expressions ran in `py` mode: the record is a Python object, so *every number had already
  collapsed to an IEEE double before it reached the column*. The other ingestion mode, `raw` — a
  row written as JSON text by anything that is not this Python process (ETL, migration, `psql`,
  another service) — **can carry numbers a double cannot hold, and there the two engines
  disagree.** T-23 measured **7 divergences in 204 expressions**, all of them equality or
  inequality; for example `{"a": 0.1000000000000000000000001}` with `$.a == 0.1` is **True** in
  Python and **False** in SQL, because jsonb compares an exact `numeric` while Python compares
  after a `float` parse. Arithmetic does not diverge — it routes through `xpr.num`, which lands on
  the same `float8` Python uses.

  **This is a limit of the battery, not a regression in the compiler.** `py` mode cannot express
  those inputs, so a larger `py` run would never find them: the gap is domain, not sample size.
  It matters because T-7 found that **six of seven GIMS write paths never check the declared
  type**, so non-Python writers are the norm. Full result, mechanism and what is *not* claimed:
  `spikes/T-23/FINDINGS.md`.

  **A second gap, found 2026-10-01 and fixed by T-66.** The figure never covered strings with a
  leading or trailing letter `v`.
  - **The cause.** From the first runtime (T-1) until T-66, the whitespace trim was written
    `E' \t\n\r\f\v'`, and PostgreSQL has no `\v` escape, so the set held the *letter* v.
  - **The effect.** `"v2"`, `"12v"` and `"vv3.5v"` became 2, 12 and 3.5 where GIMS gives no
    number, and `"v2024-02-29"` became a date. A `number($.voltage) > 10` filter kept a `"12v"` row
    that GIMS drops.
  - **How it was found.** The batteries' 11,367 expressions did not catch it. An independent review
    did, by sweeping 6.9 million inputs against GIMS's own Python.
  - **The fix.** T-66 puts `\x0b`, the vertical tab, at the three sites. Its tests were watched
    failing on the old runtime. The parity vectors (v9) now carry eight letter-v cases, and a test
    guards every escape in the runtime template against ones PostgreSQL lacks.
- **The numbers no longer depend on a session setting.** The pass above holds at
  `extra_float_digits = 1`; at 0 and −3 there were still 62 and 66 wrong numbers, from a
  value-channel truncation the pin cures (`kb/wiki/decision-t6-correctness-rerun.md`). Later work closed that: the shipping compiler routes float8 through `xpr.j`, which carries its own setting,
  so the same expression returns `0.3333333333333333` at either setting where the frozen spike
  compiler returned a short number (`kb/CURRENT-WORK.md`).
- **The trigger for the worst divergence has not been seen in real data, and nothing prevents it.**
  Eight databases read-only: zero non-ASCII digits — but the honest denominator is **144** strings a
  dashboard would actually try to turn into a number, not the million-odd an earlier sweep counted,
  and GIMS's own CSV import lets 8 of 10 such forms into a number-declared field without complaint
  (`kb/wiki/nonascii-digits-in-real-data.md`). It has not happened. Nothing stops it.
- **A declared field type is not a guarantee about stored content.** Six of seven GIMS write paths
  never check the schema (`kb/wiki/declared-types-are-not-a-guarantee.md`).

What is **not** settled, stated plainly:

- **Speed: the first like-for-like run failed its bar, and a faster design has since passed it.**
  The first spike measured the compiled
  path at **3.79× to 7.15× slower** than today's Python, with no crossover at any size
  (`kb/wiki/decision-expr-to-sql.md`). The like-for-like timing run, **T-4**, ran on 2026-09-08
  under its pre-written bar and **failed**: **413.76 ms against a 350 ms bar** at 20,000 rows, and
  **2,004.61 ms against 1,000 ms** at 100,000, about 2.1× to 2.6× slower than same-session Python
  and flat across sizes (`spikes/T-4/FINDINGS-T4.md`,
  `kb/wiki/decision-t4-timing-verdict.md`). The owner's ruling (2026-09-27) was to **test a faster
  design first**: a child spike, **T-44**, is timing a compiled path built to cut the per-row cost
  against the same bar, including "must beat Python". **T-44, re-timed on a quiet host
  (2026-10-01): PASS.** For the same invented widget, the faster path (number checks written
  inline, plus a parallel-safe runtime) gave **zero wrong numbers** and answered in **108.69 ms at
  100,000 rows, against Python's 829.46 ms** in the same session (136.71 ms with numbers stored as
  text), inside its 300 ms target. An earlier run on a busy machine (load 27–40 on 20 cores)
  missed the target (`spikes/T-44/FINDINGS.md`). It was ruled passed the same morning
  (`kb/wiki/decision-t44-faster-path.md`). **The change that ships it, T-52, is on `main`**
  (2026-10-01): `compiler/compile.py` writes the number checks inline, and every runtime function
  is labelled parallel safe, with a test that proves it inside a forced worker. Against the
  compiler before it, an independent review found 0 differences in 209,594 per-row comparisons.
  None of the owner's own widgets has been timed yet.
- The digit mapping is **regenerated by hand** (`python3 runtime/generate.py`) on a Unicode bump.
  A test detects a stale mapping, and `ops/runtime-check.sh` compares every Unicode-digit case
  between the two engines on a throwaway Postgres (`kb/wiki/decision-t6-correctness-rerun.md`).
- The planned mutation pass **now runs**: `./run-demo test --mutants` applies plan §8.2's sixteen
  one-line defects, runs only the criterion each must break, and asserts it fails
  (2026-09-08). **15 killed, 1 known survivor, 0 new** — and the survivor is the pass doing
  its job. §8.2 names two halves for M15; `AC-41(a)`'s grep kills it, `AC-41(b)`'s ten runs do
  not, and that is a real discovery about `AC-41(b)` rather than a defect in the demo: the
  reordering it watches for needs a synchronised sequential scan, a plan change or parallel
  workers, and none of those occurs on a 2.8 MB table where `LIMIT 10` stops the scan first.
  It is a repeatability test, not an `ORDER BY` detector. Tracked in **T-20**, and the
  criterion was deliberately **not** edited to make the mutant die (`.autodev/specs/T-19.md`,
  Out of scope). Known survivors are listed with a reason and a ticket each, and a **new**
  survivor exits 3 — so a tracked red can never mask a fresh one.

## Status

Research-grade. The demo works end to end and the correctness thread is closed. The suites stand at
demo 1182, runtime 58, compiler 34 and ops 14, all green (measured 2026-09-26 at `6c628ae`; runtime
and compiler re-run green on 2026-10-01). None of it is wired into GIMS's live path, and nothing here
should be called production-safe.

That is deliberate. The standing ruling (2026-08-21) is **do not build the
standalone-compiler-plus-thin-adapter architecture as scoped, yet** — not "impossible" and not
"throw the work away", but *this evidence does not fund this build* — with two follow-up runs
funded to earn it (`kb/wiki/decision-expr-to-sql.md`). The correctness run is the one that has
reported, and the speed run has too: it failed (above). The ruling on that result (2026-09-27) was
to test a faster design before deciding. That test, T-44, has reported: it PASSED on a quiet host (above).

## License

GNU AGPL-3.0. The full text is in [`LICENSE`](./LICENSE).
