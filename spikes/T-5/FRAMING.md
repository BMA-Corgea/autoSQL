# T-5 · Framing — do non-ASCII digit strings actually occur in the real data?

Stage: `sp-frame` (spike@v2) · **lean: OFF** (`.autodev/shop.json` → `settings.lean: false`, set
2026-08-22 under GA-6; T-5 carries no ticket-level lean flag, so the shop default decides — recorded
in `.autodev/lean-log.jsonl`) · Framed: **2026-09-01**

**Nothing in this document ran a query against any database.** Every figure marked
**[measured 2026-09-01]** was produced on this machine while writing this, from Python's own
standard library or from files already in this repository. Figures marked **[T-1 §D.x]** or
**[T-3 §x]** are quoted from the prior spikes' own records and were re-read, not remembered.

---

> ## Vocabulary, in plain terms
>
> This document uses shop jargon and Unicode jargon. Both are defined here so nothing below needs
> a second window.
>
> **Spike** — a time-boxed investigation that answers a question instead of shipping a feature.
> **`sp-frame`** is its first stage, and it exists for one reason: to write down *what would count
> as an answer* **before** any evidence exists, so the result cannot be reinterpreted afterwards to
> suit whichever way it lands. **`sp-investigate`** does the actual sweeping. **`sp-decide`** is
> where **Evan rules** — nobody else can, and no agent may sign it.
>
> **Coercion** — turning a value that is stored as *text* into a *number*. `"7"` → `7.0`. The
> dashboard does this constantly, because a lot of GIMS data is stored as strings that look like
> numbers.
>
> **Non-ASCII digit** — a character that means a digit but is not one of `0`–`9`. `１２３` is the
> full-width form; `١٢٣` is Arabic-Indic; `۱۲۳` is Persian. Unicode calls this character class
> **`Nd`** ("Number, decimal digit"). **Python's `float()` accepts all of them. Postgres does not.**
> That single sentence is the whole bug T-5 is measuring the reach of.
>
> **The gap (T-3's "M1")** — `float("１２３")` is `123.0` in Python and `NULL` in SQL. So the same
> dashboard cell reads **123** on today's path and **nothing** on the compiled-SQL path, with no
> error and no warning. A wrong number, silently.
>
> **Corpus** — the pile of real rows a sweep actually looks at. Which rows are in the corpus is the
> most important fact about any sweep, and §5 is entirely about a corpus nobody has swept yet.
>
> **Prevalence** — how often a thing occurs, as a *rate*: how many out of how many. A count with no
> denominator is not a prevalence, and §4.3 is about a denominator that was never computed.

---

## 1. The question

Two questions, and they are not the same size.

> **Q1 — Do strings that Python would silently coerce to a number, and that contain a non-ASCII
> decimal digit, occur in Evan's real data? At what rate, in which collections, and does any of it
> sit in a collection a dashboard actually reads?**

> **Q2 — Is anything other than the GIMS Python process ever going to write rows that autoSQL
> reads?**

Q1 is a measurement. Q2 is an inventory of code paths and an answer from Evan about intent — it
cannot be settled by sweeping, because it is a question about the future as much as the present.

**Neither question asks whether the compiled SQL is correct.** T-3 settled that: it is not, at all
three Postgres output settings. T-5 asks only **how much that matters here**.

## 2. The decision this feeds, stated exactly

T-3's ruling (`kb/wiki/decision-t3-correctness-run.md`, Evan, 2026-08-23, GA-7) is
**"homework first, then fix-and-re-run."** T-5 *is* the homework, and the ADR names its own weakest
point in the same breath:

> "if the sweep finds non-ASCII digits are *common* in real data, Option C turns those cases from
> silent wrong numbers into **frequent visible refusals** — correct by the bar, but potentially a
> worse product than either a properly narrowed language (B) or stopping (A). **That is the trigger
> to revisit this ruling**, and it is one line to overturn."

So T-5 does not merely add a fact. **It can overturn a standing ruling.** §9 fixes the thresholds
that would do it — now, before any counting, which is the entire point of this stage.

## 3. What is ALREADY measured — read this before planning any sweep

**A sweep for exactly this has already run.** T-1's Appendix D (`spikes/T-1/FINDINGS.md` §D.4)
swept the real data on this machine and reported:

| | | source |
| --- | ---: | --- |
| string values + object keys examined | **1,096,202** | [T-1 §D.4] |
| strings carrying a non-ASCII decimal digit (`Nd`) | **0** | [T-1 §D.4] |
| strings carrying non-ASCII whitespace | **0** | [T-1 §D.4] |
| …of those, at a string edge where `strip`/`btrim` differ | **0** | [T-1 §D.4] |

Three independent read-only instruments were run over the same bytes and agreed. And the zero is
**load-bearing rather than vacuous**, because the same corpus is demonstrably Unicode-tolerant:
**218 distinct non-ASCII code points, 206,567 occurrences, in 29,773 of 36,372 rows (81.86 %)** —
box-drawing, em-dashes, warning signs, arrows, smart quotes, emoji, Greek delta [T-1 §D.4]. An
ASCII-only corpus would make a zero worthless. This one is not ASCII-only. **GIMS writers put
plenty of non-ASCII in; what they have never once put in is a non-ASCII *digit*.**

**Therefore T-5 must not be planned as a blank-page sweep.** Re-running T-1's sweep over T-1's
corpus would burn a day to reproduce a zero that already has three witnesses. The value of T-5 is
entirely in the three things §4 and §5 identify that T-1 did **not** do.

**One citation to fix while passing.** T-3 cites "`FINDINGS.md` §D.6" three times in its FINDINGS
and twice in its FRAMING as the source for coercion reachability. T-3's own `FINDINGS.md` has no
§D.6 and no appendix D — **the reference is to *T-1's* `FINDINGS.md`**, a different file with the
same name. The claim is sound; only the pointer is ambiguous. Worth one clarifying edit, not a
finding.

## 4. The predicate, fixed before any counting

### 4.1 What Python actually accepts — measured, not assumed

**[measured 2026-09-01]**, by enumerating all 1,114,112 code points and testing `float()` directly:

| | |
| --- | ---: |
| non-ASCII code points `float()` accepts **as a digit** | **670** |
| …their Unicode category | **`Nd`, all 670 — no exceptions** |
| non-ASCII code points `float()` **strips as whitespace** before a digit | **19** |
| …how many satisfy Python's `str.isspace()` | **19 of 19** |

The 19: `U+0085`, `U+00A0`, `U+1680`, `U+2000`–`U+200A`, `U+2028`, `U+2029`, `U+202F`, `U+205F`,
`U+3000`. Note `U+0085` is category **`Cc`** (a control character), not `Zs`/`Zl`/`Zp` — a
category-only predicate would miss it, and `isspace()` catches it.

**Consequence: T-1's predicate was complete.** It tested `Nd` for digits and `Zs`/`Zl`/`Zp`/
`isspace()` for whitespace [T-1 §D.4]. `Nd` is exactly the 670; `isspace()` covers all 19. T-1's
zeros are not zeros of a too-narrow test. **T-5 reuses this predicate unchanged**, which is the
right outcome — the prior work holds up.

### 4.2 Containing a digit is NOT the same as triggering the gap

The Python side does not call `float()` on raw text. It gates first, at
`demo/vendor/expr.py:302-317`:

```python
_NUM_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
...
s = v.strip()
if _NUM_RE.match(s):
    return float(s)
```

Two things follow, both **[measured 2026-09-01]** against that exact regex:

- **`\d` in a Python `str` pattern is Unicode-aware.** `_NUM_RE` matches `'１２３'`, `'١٢٣'`,
  `'٣.٥'` and even `'۱۲۳e2'` → `12300.0`. This is *why* the gap exists, and it is one missing
  `re.ASCII` flag wide. (With `re.ASCII` the same pattern rejects both `'１２３'` and `'١٢٣'` —
  noted as an observation about the mechanism, **not** a fix recommendation; fixes are T-6's.)
- **A string containing a non-ASCII digit does not necessarily coerce.** `'Item ３'` contains an
  `Nd` digit and `_NUM_RE` rejects it, so `_to_num` returns `None` and **both engines agree on
  nothing-happened**. It is a false positive for the divergence.

So the sweep must count **two nested things**, not one:

| tier | predicate | what it means |
| --- | --- | --- |
| **A — contains** | any `Nd` character outside ASCII appears anywhere in the string | T-1's predicate; the safe superset |
| **B — coerces** | `strip()` then `_NUM_RE` matches, **and** at least one `Nd` char is non-ASCII | the strings that actually produce a wrong number |

**B is a strict subset of A**, so T-1's `A = 0` already implies `B = 0` on T-1's corpus — the prior
zero is not weakened by this refinement. It is stated so that a **non-zero** result on a new corpus
can be split into "noise" and "real divergence" rather than argued about afterwards.

### 4.3 The denominator T-1 never computed — the sharpest gap in the record

T-1 reported **0 of 1,096,202**. That denominator is *every string value and object key in the
corpus*. But the decision does not turn on how many strings exist; it turns on **how many strings a
dashboard would ever try to turn into a number** — tier-B's denominator, the count of
number-coercible strings.

Nobody has computed it, and T-1's own §D.6.3 suggests it may be **small**: the numeric-looking
string fields it found are counted in single and double digits — `Sample Weight (g)` 7, `Dilution
Weight (g)` 7, `sample_id` 20, `ID #` 4, `Submission.received_date` 5 [T-1 §D.6.3]. Meanwhile the
17,144 `"false"` strings that dominate §D.6.1 are **not** coercible (`_NUM_RE` rejects `'false'`,
**[measured 2026-09-01]**), so they inflate the 1,096,202 without contributing to the risk.

**If the true coercible population is ~300 strings, then "0 of 1,096,202" is really "0 of ~300"** —
still a zero, but a far weaker guarantee than the printed figure implies, and one that a single new
tenant could move. **Computing that denominator is the highest-value single output of T-5**, and it
is cheap: the same walk, one extra counter.

## 5. What T-1 never swept — where the real work is

T-1's corpus was, in its own words, "every `objects.db` / `archive.db` under `gims-ledger/projects/`
and `GIMS-Project/projects/`" [T-1 §D.2] — **SQLite files only**. Five things sit outside it:

1. **`glp_strong` — Evan's live Postgres, ~95 MB.** Docker container `glp-strong-db`
   (`pgvector/pgvector:pg16`, host port **55433**, up and healthy **[measured 2026-09-01]**,
   `docker ps` only — no connection opened). T-3 recorded it as "Evan's real data, ~95 MB … and is
   never touched" [T-3 §FRAMING]. **It is the largest real corpus on the machine and no sweep has
   ever looked inside it.** See §6 — reaching it is not T-5's decision to make.
2. **`guts-pg`** — a second Postgres container (`postgres:16`, port 55432), **exited 4 weeks ago**
   **[measured 2026-09-01]**. Contents unknown; unknown is not the same as empty.
3. **158 backup snapshot directories** — 91 under `gims-ledger/backups/`, 67 under
   `GIMS-Project/backups/` — explicitly excluded from T-1's sweep [T-1 §D.2].
4. **The un-checkpointed WAL.** T-1 opened every database `immutable=1`, which ignores the `-wal`
   file — 543,872 bytes unread for `guts-ledger` alone, "not zero and not measured" [T-1 §D.8].
5. **`archive.db`'s `noun_Sample` table** (28 rows) — skipped because it is column-per-field rather
   than a JSON blob, so T-1's walker had no path into it [T-1 §D.2].

**And the limit that no sweep on this machine can lift**, stated here so it is not discovered as a
disappointment later: *n* = **1 machine, 1 operator**. 60.2 % of T-1's rows were `LedgerRecord`
written by AutoDev itself and 36.5 % were code-embedding vectors; the only tenant-shaped project
contributed **222 rows across 18 collections**, and the one real dashboard's own source collection
holds **7 rows** [T-1 §D.8]. **Nothing here extrapolates to production.** T-5 can answer "does this
occur in the data Evan has"; it cannot answer "does this occur in the data a customer has."

## 6. The prerequisite only Evan can clear

Since commit `01e75b0` (21 Aug) **every spike script fails closed against port 55433**: no default
connection string, and an outright refusal if `AUTOSQL_SPIKE_DSN` names that port [T-3 §FRAMING].
That fence was put there deliberately, and it is the reason T-3's own instruments never saw
`glp_strong`.

**T-5 will not reach through it on its own authority.** The fence is a standing instruction, and
"the new sweep is read-only" is exactly the argument every unsafe read starts with.

> **The one question for Evan, and the only thing blocking the most valuable half of this spike:**
> **may `sp-investigate` open a read-only connection to `glp_strong` on port 55433 — `SELECT` only,
> one session, no schema installed, no writes, no `xpr` functions, no compiler — for the sole
> purpose of counting strings?**

Three honest options, in the order they cost:

- **(a) Yes, read-only.** Best answer available. A dedicated read-only role, or a plain `SELECT`
  session, and the sweep reports on the corpus that actually matters.
- **(b) Yes, but on a copy.** `pg_dump` to a throwaway container and sweep that. Strictly safer,
  and affordable: the volume is at **94 % full with 30 GB free [measured 2026-09-01]** against a
  ~95 MB database. (T-3 recorded 96 % / 21 GB on 2026-08-22; it has since loosened, not tightened.)
  Slower, and the copy is a snapshot rather than the live table.
- **(c) No.** Then T-5 sweeps items 2–5 of §5 only, and its answer carries a permanent, prominent
  caveat: *the largest real corpus was not examined.* **This is a legitimate answer** — but the
  spike should say plainly that it did not measure the thing it was chartered to measure, rather
  than report a zero that quietly excludes 95 MB.

**If no answer arrives, `sp-investigate` proceeds under (c) and says so loudly.** It does not wait,
and it does not assume (a).

## 7. Q2 — the writer inventory

Partly answered already, and the part that is answered is strong. T-1 §D.5 kept every number's
**raw literal text** across **5,236,427** numeric literals and found **0** that a
`json.dumps()` of a Python object could not have emitted; **0** with more than 17 significant
digits; and every stored row `\uXXXX`-escaped, the signature of `ensure_ascii=True`. Its inference:
*"No ETL, no `psql`, no restored dump, no second-language service has written these tables."*

Two things keep Q2 open, and both are named in T-1's own limits:

- **§D.10 item 2, verbatim:** *"Whether any non-Python writer exists anywhere in GIMS … Would
  establish it: an audit of every `INSERT`/`COPY` path into `instances` in both trees, plus
  deploy-time migration and restore tooling."* That audit is T-5's Q2 deliverable, and it is
  reading code, not sweeping rows.
- **A non-Python writer has existed before.** `storage_aws.py:326-335` carries a comment
  documenting this exact parity disagreement as a bug the team fixed once [T-1 §D.5] — so "there
  has never been one" is already false as history, and the question is really about the future.

**The future half is Evan's to answer, not the sweep's.** One sentence from him settles it: *is
anything other than the GIMS Python process ever going to write rows autoSQL reads — an ETL job, a
`psql` session, a restored dump, a second service, a customer import?* If the answer is "no, and
that is a rule we intend to keep", T-3's M4 class (raw-JSON rows from non-Python writers) is
contingent on something that will not happen and prices accordingly. If it is "yes, eventually",
M4 is a live risk and belongs in the re-run's bar.

## 8. Timebox

**One working day for `sp-investigate`, hard stop.** The ADR budgeted "hours of work, touches
nothing", and §3 has already removed the largest chunk of it by finding the sweep partly done.

| item | budget |
| --- | ---: |
| tier-A + tier-B walker, both tiers and the §4.3 denominator, over §5 items 2–5 | ~2 h |
| `glp_strong`, if §6 clears it | ~2 h |
| Q2 `INSERT`/`COPY` path audit across both trees + migration/restore tooling | ~2 h |
| writing `FINDINGS.md` | ~2 h |

**Overrun rule:** if the day ends with the sweep incomplete, `sp-investigate` reports **what it
swept and what it did not**, with the zeros and non-zeros it actually has. It does not take a second
day without Evan saying so. A partial sweep honestly bounded is a usable input; a spike that
quietly grows is not.

## 9. What a decision needs — the bands, fixed now

These are the numbers, written **before** any counting, that decide whether T-3's ruling stands.

**The denominator is tier-B's** — number-coercible strings (§4.2), **not** all strings. Every band
is quoted against that base, and the base itself is reported as a raw count (§4.3) so the reader can
see how strong the rate is.

| band | tier-B rate, over coercible strings | what it means for T-3's ruling |
| --- | --- | --- |
| **ZERO** | **0**, and 0 in tier A too | **Ruling stands, unqualified.** Proceed to fix-and-re-run. The refusal is a theoretical guard that fires on nothing this project has ever stored. |
| **RARE** | **>0 but <0.1 %**, none of it in a collection any dashboard reads | **Ruling stands.** A refusal that fires on <1 row in 1,000 is a good trade against a silent wrong number. Name the collections in the findings. |
| **PRESENT** | **0.1 %–1 %**, *or* any occurrence at all in a collection a dashboard reads | **Ruling stands, with a rider.** The fix needs a refusal that names the row and the JSON path, not a bare `XPR01` — a user who sees a refusal must be able to find the cell. Costs T-6 real work; say so. |
| **COMMON** | **>1 %**, *or* >0 in the one real dashboard's own source collection | **THE TRIGGER. Stop and put the ruling back to Evan.** The chosen fix would convert frequent silent errors into frequent visible refusals; narrowing the language (Option B) or stopping (Option A) becomes the honest choice. **`sp-investigate` does not proceed to T-6 on this result** — it reports and hands to `sp-decide`. |

**Three rules that make these bands mean something:**

1. **A zero is reported with its denominator and its Unicode-tolerance control, or it is not
   reported.** T-1 §D.4 set this standard and it is inherited: a zero over an ASCII-only corpus is
   worthless, so the sweep must show the corpus *could* have carried non-ASCII digits.
2. **"A collection a dashboard reads" is resolved from the live dashboards**, not assumed. T-1 §D.7
   found exactly one real dashboard (`nodes.db` table `dashboards`, 1 row, "Testy Test"), 3 widgets
   of which **2 are `csv` and never reach `resolve()`** — so **one** resolver-reaching widget, over
   source collection `Submission` (**7 rows**). That is the entire list until a bigger one is found,
   and it is small enough that a single hit inside it is decisive rather than statistical.
3. **Bands are computed per corpus and reported separately, never pooled.** A zero across 37,078
   SQLite rows and a non-zero in `glp_strong` are two different facts, and averaging them would hide
   the one that matters. Same discipline T-3 used for its three Postgres settings.

**Q2 has no bands — it has two answers**: *no non-Python writer, and none intended* (M4 is
contingent and prices low), or *one exists or is intended* (M4 is live and must be in the re-run's
bar). Anything vaguer than those two is not an answer, and `sp-investigate` should record it as
unresolved rather than round it into one.

## 10. What would make a result unusable

Fixed now, so no result can be rescued by argument later.

- **Any write, anywhere.** Read-only connections only (`mode=ro&immutable=1` for SQLite, a `SELECT`
  session for Postgres). One write invalidates the run — the ticket says READ-ONLY and that is the
  condition of touching Evan's live data at all.
- **A compiler run.** T-5 does not execute `runtime.sql`, does not install the `xpr` schema, does
  not compile an expression. It counts characters in stored strings. Anything more is T-6.
- **A pooled rate across corpora** (§9 rule 3).
- **A zero without its Unicode-tolerance control** (§9 rule 1).
- **A tier-A count reported as if it were tier B** (§4.2) — that overstates the risk, and this
  spike exists to price it accurately in *both* directions.
- **A single instrument.** T-1 ran three and they agreed; T-5 runs at least two independent ones
  over any corpus that returns a **non-zero**, because a first-ever non-zero is exactly where an
  instrument bug would be most expensive.
- **Silent scope reduction.** If §6 lands on (c), the findings say so in their first paragraph, not
  in a limits section at the end.

## 11. Out of scope — named, so they are not smuggled in

- **Fixing anything.** T-6 owns the fix and the re-run. T-5 produces a number and an inventory.
- **Re-running T-1's sweep over T-1's corpus** (§3) — unless a new instrument disagrees with the
  old zeros, in which case that disagreement *is* the finding.
- **The other T-3 mechanisms** — value-channel truncation (M3), container comparison rules (M2),
  raw-JSON rows (M4). Q2 informs M4's pricing; it does not measure it.
- **Speed.** T-4 is held until the correctness re-run reports, per Evan's own ordering.
- **Production data.** Not reachable and not in scope (§5).
- **The T-2 demo's disagreement-state question.** Separate decision, separate form, still open.

## 12. Stop conditions

`sp-investigate` stops early and hands back, without finishing, if any of these occur:

1. **A write is detected**, attempted or accidental, against any real database — stop immediately,
   report exactly what happened.
2. **The COMMON band is hit** (§9) — the ruling is in question; further sweeping cannot change that,
   and the decision belongs to Evan.
3. **Two instruments disagree** on any corpus — the instruments are the finding, and a number
   nobody can reproduce is worse than no number.
4. **The timebox expires** (§8) — report the partial sweep with its exact boundary.
5. **`glp_strong` cannot be reached read-only without a change to the fence** — fall to §6(c) and
   say so; do not modify the fail-closed guard.

---

## Attestation

Written at `sp-frame` on **2026-09-01**, on branch `spike/T-5-nonascii-digit-homework`. No database
connection was opened. `docker ps` was run to confirm container state and nothing else. The
`float()` and `_NUM_RE` figures were produced with Python's standard library against
`demo/vendor/expr.py:302` as it stands in this tree. T-1 and T-3 figures were re-read from
`spikes/T-1/FINDINGS.md` and `spikes/T-3/FRAMING.md` at the line numbers cited, not recalled.

**Open and blocking the most valuable half of this spike: §6 — Evan's ruling on read-only access to
`glp_strong`.**
