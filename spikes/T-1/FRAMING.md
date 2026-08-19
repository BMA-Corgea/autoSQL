# T-1 · Framing — compile the GIMS dashboard expression AST to Postgres SQL

Stage: `sp-frame` (spike@v2) · risk: medium · lean: ON (shop default, no veto)
Framed: 2026-08-19 · Reference trees verified on this machine, read-only.

---

## 1. The question

> Can the AST produced by `core/dashboard/expr.py` be compiled to Postgres SQL that
> agrees with the Python evaluator on **every** case in `tests/fixtures/expr_vectors.json`
> (within `float_epsilon` = 1e-9), well enough that `api/dashboard/sources.py` can push
> `derive` / `where` / `sort` / `limit` into the database instead of materialising up to
> `MAX_SCAN = 20_000` rows and filtering them in Python?

Unchanged from the ticket. What changed is *where we point it* — see §2.

## 2. Three corrections to the ticket as written

The ticket's file references were checked against the machine. All five resolve — but
**not all of them in the tree we assumed.** There are two GIMS checkouts here:

| | `GIMS-Project` | `GUTS/spine/L1-memory/gims-ledger` |
| --- | --- | --- |
| commit | `995cc59` (branch `refactor/foundation`) | `7b7a049` |
| `core/dashboard/expr.py` | ✅ 646 lines | ✅ **byte-identical** |
| `tests/fixtures/expr_vectors.json` | ✅ | ✅ **byte-identical** |
| `api/dashboard/sources.py` | ✅ `MAX_SCAN=20_000` | ✅ **byte-identical**, same cap |
| `frontend/lib/expr.js` | ✅ | ✅ **byte-identical** |
| `design/dashboard_expr_grammar.md` | ✅ | ✅ **byte-identical** |
| `core/storage/sql.py` | 163 lines, SQLite only | **500+ lines**, has `list_records_where` |
| `migrations/pg/` | ❌ **absent** | ✅ `0001_instances.sql`, `0002_instances_data_gin.sql` |
| the pgvector/RAG pushdown profile | ❌ absent | ✅ `core/storage/sql.py:242-250` |

**C1 — the storage reference is `gims-ledger`, not `GIMS-Project`.** Every storage-layer
artifact the ticket names (the GIN migration, `list_records_where`, the RAG pushdown
profile) exists only in `gims-ledger`. `GIMS-Project` is behind on storage.

**C2 — the expression oracle is unambiguous.** All five expression-stack files are
byte-identical across both trees, so there is no "which evaluator is canonical?" risk.
The conformance target is one fixture with one meaning. This was the biggest latent
threat to the spike and it is closed before we start.

**C3 — `kb/wiki/autosql-architecture.md` is accurate but under-specified.** Its claims
("`migrations/pg/0002_instances_data_gin.sql` exists", "`core/storage/sql.py` records a
measured profile") are **true of `gims-ledger`** and false of `GIMS-Project`. The page
does not say which tree it means. Fixing that wording is a `sp-synth` output, not a
finding — it is a documentation defect, not a design one.

**Consequence for finding #3:** the ticket said "compare against
`migrations/pg/0002_instances_data_gin.sql`". That index is `GIN (data jsonb_path_ops)`
on `instances`/`instances_archive`, built for the ledger's **exact-match containment**
filters (`data @> '{"actor":"goms"}'`). `jsonb_path_ops` deliberately does **not** support
key-existence (`?`/`?|`/`?&`). Dashboard pushdown is range, comparison, arithmetic and
computed predicates over arbitrary keys — a different access pattern. So finding #3 is
restated: *does the existing index serve dashboard pushdown at all, and if not, what
index does autoSQL actually require?* Answering "it doesn't help" is a real finding, not
a failure.

## 3. Timebox

There is no clock in this factory, so the timebox is stated as **scope, with stop rules**:
one investigation pass, the five findings below, and no more. Specifically:

- **Compile only what `expr_vectors.json` exercises.** No grammar the fixture does not test.
- **The prototype is throwaway by contract** (`sp-investigate@v1`). It lands in
  `spikes/T-1/proto/` in *this* repo. It is not a library, has no API, and nothing may
  import it later. Neither GIMS tree is written to — both are read-only for this spike.
- **Stop rules — hit one and the finding is written as-is, not chased:**
  - a fixture case that cannot compile → record it as a **coverage gap**, do not redesign
    the grammar to reach it;
  - a divergence whose cause is identified → record cause + fallback rule, do not fix it;
  - the `query` source (`cascade_deep_search`) → **bound and confirm it does not push
    down**, do not attempt to make it.
- **Out of time = write findings and go to `sp-synth` anyway.** A partial conformance
  matrix with honest gaps is a valid spike result; a stalled spike is not.

## 4. What a decision needs (the `sp_decide` criteria)

`decision_authority` is `recommend-and-wait` — this spike **recommends**, Evan decides at
the `sp_decide` gate. For that gate to be answerable, the findings must supply:

| # | Finding | What makes it decision-grade |
| --- | --- | --- |
| 1 | **Conformance** | Pass/fail **per case**, all cases, never a summary count. Every divergence named with its cause (NULL propagation · numeric coercion · date parsing). Run as a *third runtime* against the same fixture the Python and JS runtimes already satisfy. |
| 2 | **Coverage** | Which constructs compile, which cannot, and the explicit fallback rule for each. `query`/`cascade_deep_search` confirmed as non-pushdown and bounded. |
| 3 | **Index shape** | The actual generated SQL over JSONB arbitrary-key records, and the index it needs — measured against `0002_instances_data_gin.sql`'s `jsonb_path_ops` GIN, including the honest answer if that index is the wrong shape. |
| 4 | **Measurement** | End-to-end numbers vs. the current in-memory path on a representative widget, in the style of the existing RAG pushdown profile (`gims-ledger/core/storage/sql.py:242`). Numbers, not adjectives. |
| 5 | **Recommendation** | Go / no-go on *standalone compiler + thin GIMS adapter*, with the reasoning and the cost of the fallback machinery. |

**The go/no-go bar, stated in advance so the result cannot be rationalised afterwards:**

- **GO** requires: 100% of compiled cases agree within `float_epsilon`; every
  non-compiling construct has a named fallback; and the fallback is **detectable and
  reported at query time**, never silent.
- **NO-GO** if any case diverges *silently* — i.e. produces a number rather than an error
  or an explicit fallback. One silently-wrong number is disqualifying on its own.
- **CONDITIONAL-GO** is a legitimate verdict: compile the subset that provably agrees,
  fall back loudly for the rest, and name the subset.

## 5. Non-negotiable

> A fallback to in-memory evaluation must be **reported, never silent**.

This is the reason the project exists. `expr` is *total* — it never throws, it returns
`null`. SQL is not: Postgres raises where SQLite would silently coerce
(`CAST('abc' AS REAL)` → `0.0`). Postgres was chosen precisely because it fails loudly.
Any compiler output that turns a `null` into a number, or a raise into a value, is a
defect of the highest severity in this spike regardless of its performance.

## 6. Out of scope (restated from the ticket, unchanged)

The UI · window/aggregate functions (the tier above `expr`) · the prepositional-phrase
adapter · any GIMS storage migration · anything touching writes, locks or invariants
(**D12c: locks never move**).

## 7. Environment — verified on this machine

- **Postgres for the conformance harness:** docker container `glp-strong-db`,
  `pgvector/pgvector:pg16`, PostgreSQL **16.14**, healthy, host port **55433**,
  role `glp_owner`, db `glp_strong`. The spike creates its **own scratch database**;
  it does not touch `glp_strong`'s contents.
- **Python:** `GIMS-Project/.venv`, Python 3.12.3 — used to import `core.dashboard.expr`
  as the reference runtime.
- **Both GIMS trees are read-only for this spike.** Nothing is written to either.

## 8. Risky part, for the next seat

The conformance harness is the whole spike. If it is wrong, every finding downstream is
wrong and looks green. Build it so that **a case that fails to compile is visibly
distinct from a case that compiles and disagrees** — three outcomes (compiled+agrees,
compiled+diverges, did-not-compile), never two. A harness that silently scores
"did-not-compile" as a pass would reproduce, inside the spike itself, exactly the failure
mode the spike exists to rule out.
