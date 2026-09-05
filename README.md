# autoSQL

autoSQL compiles the GIMS dashboard expression language into Postgres SQL, so a widget's numbers are
computed inside the database instead of being pulled into Python and reshaped there. It is three
things: a compiler (`compiler/`) that turns an expression AST into a parameterised Postgres
statement, a SQL runtime (`runtime/`) of 21 functions giving Postgres the same value semantics as
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
- **`runtime/`** — schema `xpr`, the SQL functions the compiled statements call. `runtime.sql` is
  **generated**: edit `runtime.sql.in`, then run `python3 runtime/generate.py`. Three of its tables
  come from the running Python's `unicodedata` — freeze them as literals and a Python upgrade splits
  the two engines with nobody touching a line of code.
- **`demo/`** — a self-contained screen for driving the idea by hand: its own Postgres, 10,410
  invented rows, a server, and two answer panes side by side. Its test suite lives here too.
- **`spikes/`** — one folder per spike ticket: a `FRAMING.md` (the bar, fixed in writing before any
  evidence was collected), a `FINDINGS.md`, and whatever recon, analysis and prototype code that
  spike needed. **Frozen evidence, not source** — digests of files in here are cited in the findings
  and battery outputs, and tests assert they have not moved. `compiler/` and `runtime/` are live.
- **`kb/`** — the knowledge base. Start at `kb/index.md`, which is a pointer table, not a wall of
  text. `kb/CURRENT-WORK.md` is the state of play; `kb/wiki/` holds the decisions of record and why
  each one was taken.
- **`design/`** — the demo's design brief and its HTML mock. **`ops/`** — small operational scripts.

`.autodev/` is the AutoDev factory's ledger for this repo — tickets, events, handoffs, evidence.
Also at the root: `SETUP.md` (setting this repo up on a new machine, plugin included),
`WINDOWS-CHECKLIST.md`, and the `QUESTIONS-FOR-EVAN.md` / `ANSWERS-FROM-EVAN.md` /
`WAITING-ON-EVAN.md` / `WRAPUP-FOR-EVAN.md` set: the factory's questions to the owner and his answers,
kept because the decisions in `kb/` cite them.

## Running the demo

You need Docker and CPython 3.12 on x86-64 Linux, which is the only platform the committed
wheelhouse covers (`demo/vendor/wheels/README.md`). From the repository root:

```
./start.sh          # bring it up and open the screen
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
loaded and `AUTOSQL_RUNTIME_DSN` set. Without those, most of their tests skip rather than run.
`compiler/README.md` and `runtime/README.md` give the exact steps.

What you get is a picking panel and two answer panes: the SQL pane, which is what Postgres
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
matched. Note that `demo/README.md` still describes step 11 as a live disagreement; that text
predates the fix and `demo/WALKTHROUGH.md` is the current account.

Every row behind the screen is invented, and there is no performance information anywhere in the
demo — that question belongs to work that has not run yet (see below).

## What is proven so far

- **Zero wrong numbers over 11,367 expressions**, across three batteries, with zero unexplained
  raises and zero nullness violations; the 130-case contract fixture is **130/130**
  (`kb/wiki/decision-t6-correctness-rerun.md`). The harness was separately driven with six
  deliberately wrong compilations and reported all six, so its failure paths were dead rather than
  broken (`kb/wiki/decision-expr-to-sql.md`).
- **The numbers no longer depend on a session setting.** The pass above holds at
  `extra_float_digits = 1`; at 0 and −3 there were still 62 and 66 wrong numbers, from a
  value-channel truncation the pin cures (`kb/wiki/decision-t6-correctness-rerun.md`). T-9 and T-11
  closed that: the shipping compiler routes float8 through `xpr.j`, which carries its own setting,
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

- **Speed.** The one like-for-like timing run has never happened. The T-1 spike measured the
  compiled path at **3.79× to 7.15× slower** than today's Python across six table sizes from 1,000
  to 1,000,000 rows, with no crossover — it never won at any size — and because index work is ruled
  out, that gap is a floor rather than a starting point (`kb/wiki/decision-expr-to-sql.md`), and it
  has never been refined. The run that would refine it, T-4, is blocked on a measured condition: it
  reports absolute milliseconds, so it needs a 1-minute load average of 2.0 or below and an
  exclusive two-to-three-hour window, and the load when it came up was 2.30
  (`kb/CURRENT-WORK.md`). Numbers taken under load are not weaker, they are void, so it waits.
- The digit mapping is generated but **nothing regenerates it** on a Unicode bump, `raw`-mode data
  was never re-run, and the planned mutation pass has never run — 9 of 16 mutants have never been
  watched failing (`kb/wiki/decision-t6-correctness-rerun.md`, `kb/CURRENT-WORK.md`).

## Status

Research-grade. The demo works end to end and the correctness thread is closed; suites stand at
demo 1155, runtime 58, compiler 34, all green (`kb/CURRENT-WORK.md`). None of it is wired into
GIMS, and nothing here should be called production-safe.

That is deliberate. The standing ruling (Evan, 2026-08-21) is **do not build the
standalone-compiler-plus-thin-adapter architecture as scoped, yet** — not "impossible" and not
"throw the work away", but *this evidence does not fund this build* — with two follow-up runs
funded to earn it (`kb/wiki/decision-expr-to-sql.md`). The correctness run is the one that has
reported. The speed run has not. Until it does, the GIMS gate stays shut.

## License

GNU AGPL-3.0. The full text is in [`LICENSE`](./LICENSE).
