# T-1 · FINDINGS — compiling the GIMS dashboard expression AST to Postgres SQL

**Stage:** `sp-investigate` (spike@v2) · **ticket:** T-1 · **branch:** `spike/T-1-expr-sql`
**Decision authority:** `recommend-and-wait` — this document *recommends*; `human:owner` decides at
the `sp_decide` gate.
**Bar:** set in advance by [`FRAMING.md`](FRAMING.md) §4/§5, before any evidence was collected, so
the result could not be rationalised afterwards.

---

## The question

> Can the AST produced by `core/dashboard/expr.py` be compiled to Postgres SQL that agrees with the
> Python evaluator on **every** case in `tests/fixtures/expr_vectors.json` (within `float_epsilon`
> = 1e-9), well enough that `api/dashboard/sources.py` can push `derive` / `where` / `sort` /
> `limit` into the database instead of materialising up to `MAX_SCAN = 20_000` rows and filtering
> them in Python?

## Provenance — verified live on this machine, 2026-08-19

| | |
| --- | --- |
| Expression oracle | `GIMS-Project` @ `995cc59` (branch `refactor/foundation`) — `core/dashboard/expr.py`, `tests/fixtures/expr_vectors.json` |
| Storage reference | `GUTS/spine/L1-memory/gims-ledger` @ `7b7a049` — `migrations/pg/`, `list_records_where`, the RAG pushdown profile |
| Both trees | **read-only for this spike** (`FRAMING.md` §7). **No file in either tree was opened for writing by any seat of this spike**, and both HEADs are still the `FRAMING.md` §7 values. **[consistency]** The drafted form of this row — *"Nothing was written to either"* — claimed more than a read-only seat can observe: `xd` D.11 records a **concurrent non-spike writer** (AutoDev's own ingestion verb) creating `gims-ledger/projects/guts/verbs/ingestion/data_dumps/` **inside** the spike window, and moving `LedgerRecord` 17,145 → 17,148 during the sweep. Re-verified here: `git status --porcelain` shows 8 dirty entries in `GIMS-Project` and 9 in `gims-ledger`, HEADs `995cc59` / `7b7a049`. |
| Expression stack | **byte-identical across both trees** (`FRAMING.md` §2/C2) — one fixture, one meaning, no "which evaluator is canonical?" risk |
| Postgres | docker `glp-strong-db`, `pgvector/pgvector:pg16`, **PostgreSQL 16.14** (Debian 16.14-1.pgdg12+1), host port 55433 |
| Database | **`autosql_spike`** — the spike's own scratch db. `glp_strong`'s contents were not touched. |
| Python | `GIMS-Project/.venv`, CPython **3.12.3** — the reference runtime, imported directly |
| Fingerprints | fixture `sha256 0091df64…` · `expr.py` `90cbb56d…` · `compile.py` `b71b1538…` · `runtime.sql` `32628b45…` |

## How to read this document

Five findings, in the order `FRAMING.md` §4 requires them, **plus four cross-cutting sections** that
exist because the findings were written in parallel and some questions only became visible when they
were read together. Each finding is a **synthesis** — the full working lives in the artifact it
cites, and every number here is traceable to a file:

| § | Section | Full working |
| --- | --- | --- |
| §1 | Finding 1 · Conformance | [`proto/CONFORMANCE.md`](proto/CONFORMANCE.md), [`proto/results.json`](proto/results.json), [`analysis/fuzz/`](analysis/fuzz/) |
| §2 | Finding 2 · Coverage + fallback | [`analysis/coverage.md`](analysis/coverage.md), [`proto/coverage_probe_results.json`](proto/coverage_probe_results.json), [`recon/query-source.md`](recon/query-source.md) |
| §3 | Finding 3 · Index shape | [`analysis/index-shape.md`](analysis/index-shape.md), [`proto/idxshape_plans.json`](proto/idxshape_plans.json), [`recon/storage.md`](recon/storage.md) |
| §4 | Finding 4 · Measurement | [`analysis/measurement.md`](analysis/measurement.md), [`analysis/measurements.json`](analysis/measurements.json), [`recon/baseline.md`](recon/baseline.md) |
| §A | Cross-cutting · is `expr` total? | the premise `FRAMING.md` §5 rests on — and it is **false as a universal** |
| §B | Cross-cutting · `filters` / `sort` / `limit` | the half of the question with no conformance evidence |
| §C | Cross-cutting · the divergence → fallback register | every class, its direction, and whether anything can detect it |
| §D | Cross-cutting · reachability in real data | whether the breaches occur in the corpora actually on this machine |
| §5 | Finding 5 · Recommendation | this document |

**Read §A–§D before §5.** They are not appendices: three of the four changed the recommendation, and
§A revises what the non-negotiable in `FRAMING.md` §5 actually means.

Semantics reference for all of it: [`recon/semantics.md`](recon/semantics.md) (operational semantics
of `expr.py`) and [`recon/fixture.md`](recon/fixture.md) (complete 130-case inventory) — **with one
correction**: `recon/semantics.md` §11's totality claim ("`expr.py` never raises for data reasons")
is false as a universal, and §A gives the narrower form that is true.

**Conventions, kept from the source documents.** Numbers, not adjectives. Every claim carries a
citation. Anything that is an inference or a judgement rather than a measurement is labelled
**OPINION** or **INFERENCE** in place. A thing the evidence does not establish is written as
*not established*, with what would establish it — never rounded up to a conclusion.

**This document has been adversarially audited, and the audit is part of the record.** Each finding
was drafted, then re-derived from the raw machine data by a separate seat that did not trust the
prose (43 corrections, 2 load-bearing); a completeness critic checked the body against `FRAMING.md`
§4/§5/§8 (16 gaps, since closed or recorded as *not established*); three seats independently
adjudicated the go/no-go bar and **did not agree**; and a consistency read — not the last one,
see below **[punch]** — checked the assembled document against itself and found **24 defects in the
drafted prose**. Those records are kept beside this file in [`.parts/`](.parts/) —
`verifications.json`, `critic.md`, `panel.json`, `consistency.md`. **[consistency]** Those 24 items
were then worked by nine seats, one per section, each required to re-verify the repair against the
raw artifact before writing it — repairs were **refused** where the artifact disagreed with the consistency read, and the seats found further
defects it had missed.

**[punch] Then a third pass, over the repaired document.** Three adversarial lenses read the
assembled file independently. All three reported the same bottom line — the evidence is sound and
`f5`'s **NO-GO** still follows — and returned **21 items, every one classed *credibility* or *minor*
and none decision-blocking**. A punch-list round worked those items under the same verify-first
rule. It corrected citations and denominators, restated figures that mixed an id count with a class
count, withdrew claims the artifacts did not support — including two in the closure log's own
account of itself and the refusal count in this paragraph — and added the round's one new number:
`f5` §5.7's CONDITIONAL-GO subset covers **68 of 130 fixture cases (52.3%)**, where the figure had
stood as *not established*. **The lens reads are not retained as files**, unlike the four audit
records named above; the closure log is their only account.

**[punch] Refusals, counted the same way here as in the log: 5 refusals across 4 seats in the repair
pass — 3 of them refusing a prescribed repair outright, 2 applying the repair and refusing a
supporting claim** (a characterisation in one, an evidentiary premise in the other); **1 recorded in
the punch-list round**, whose refusal record the log itself flags as incomplete. The drafted form of
this paragraph said **three were refused**, which is the count of prescribed repairs refused
outright, not the number of refusals; the log's prose said four, which is the number of seats.
**Every repair, refusal and residual is logged, with its raw artifact, in the final section of this
document, [Closure log — what the audit passes changed](#closure-log--what-the-audit-passes-changed).**
Read it if you want to know what the audits changed rather than that they happened.

## Contents

| § | Section |
| --- | --- |
| §1 | [Finding 1 — Conformance](#finding-1--conformance) |
| §2 | [Finding 2 — Coverage and fallback](#finding-2--coverage-and-fallback) |
| §3 | [Finding 3 — Index shape](#finding-3--index-shape) |
| §4 | [Finding 4 — Measurement](#finding-4--measurement) |
| §A | [Cross-cutting A — is `expr` total? The premise FRAMING §5 rests on](#cross-cutting-a--is-expr-total-the-premise-framing-5-rests-on) |
| §B | [Cross-cutting B — `filters`, `sort` and `limit`: the half of the question with no evidence](#cross-cutting-b--filters-sort-and-limit-the-half-of-the-question-with-no-evidence) |
| §C | [Cross-cutting C — the complete divergence → fallback register, and what the machinery costs](#cross-cutting-c--the-complete-divergence--fallback-register-and-what-the-machinery-costs) |
| §D | [Cross-cutting D — is any of this reachable from real GIMS data?](#cross-cutting-d--is-any-of-this-reachable-from-real-gims-data) |
| §5 | [Finding 5 — Recommendation](#finding-5--recommendation) |
| — | [Closure log — what the audit passes changed](#closure-log--what-the-audit-passes-changed) **[punch]** |

## The bar, restated from `FRAMING.md` §4 — quoted, not paraphrased

> - **GO** requires: 100% of compiled cases agree within `float_epsilon`; every non-compiling
>   construct has a named fallback; and the fallback is **detectable and reported at query time**,
>   never silent.
> - **NO-GO** if any case diverges *silently* — i.e. produces a number rather than an error or an
>   explicit fallback. One silently-wrong number is disqualifying on its own.
> - **CONDITIONAL-GO** is a legitimate verdict: compile the subset that provably agrees, fall back
>   loudly for the rest, and name the subset.

And the non-negotiable, `FRAMING.md` §5:

> A fallback to in-memory evaluation must be **reported, never silent.**

## What the stop rules mean for what follows

`FRAMING.md` §3 bounded this investigation to one pass and forbade chasing what it found: a case
that cannot compile is *recorded as a coverage gap*, not designed around; a divergence whose cause
is identified is *recorded with its cause and fallback rule*, not fixed; the `query` source is
*bounded and confirmed* as non-pushdown, not made to work. **Several real defects appear below
un-fixed. That is the contract, not an oversight** — each is reported with its cause, its blast
radius, and its direction against `FRAMING.md` §5.

The prototype in `proto/` is **throwaway by contract** (`sp-investigate@v1`). It is not a library,
has no API, and nothing may import it later.

---
