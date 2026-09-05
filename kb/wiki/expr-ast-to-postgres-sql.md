# Compiling the GIMS dashboard expression AST to Postgres SQL — options and the ruling

The distilled result of the T-1 spike (2026-08-19), **re-checked 2026-08-21** on the two points
Evan made his ruling conditional on (§2a). Full working: `spikes/T-1/FINDINGS.md` (~80,000 words,
four adversarial audit passes) and `spikes/T-1/RECHECK-2026-08-21.md` (the re-check), judged against
a bar set before any evidence was collected (`spikes/T-1/FRAMING.md` §4/§5).

**The ruling is in.** On 2026-08-21 `human:evan` ruled **NO-GO — don't build yet, fund the two
follow-up runs** (recorded as go-ahead **GA-3** in `.autodev/events.jsonl`, his words verbatim). The
decision point in the process — the `sp_decide` gate, where the ruling is signed and the ticket moves
on — is **cleared**. This page is no longer asking for a decision; it records what was decided, on
what evidence, and what is still genuinely open (§6, §8). This is not a short page: about 4,400 words
— roughly ten printed pages, 15 minutes. §2 and §2a are the load-bearing parts; §6 and §8 are what is
still open.

**How to read the citations.** The research names its own parts in a shorthand this page keeps, so
every number walks back to its section and its raw artifact. `f1`–`f5` are the five **findings** of
`FINDINGS.md` — 1 conformance, 2 coverage and fallback, 3 index shape, 4 measurement, 5 the
recommendation. `xa`–`xd` are its four **cross-cutting sections** — a: is the Python evaluator total
(does it always return rather than crash)? b: the `filters`/`sort`/`limit` half of the question. c:
the register of every way the two engines can disagree. d: whether those disagreements are reachable
in the real data on this machine. A **seat** is one AI reviewer working a section alone and
deliberately not trusting the other seats' prose; `spikes/T-1/.parts/` holds what the seats wrote, and
`.parts/panel.json` holds the three seats that adjudicated the go/no-go bar. **Closure** is the final
pass that read all the sections against each other; the **punch round** is the adversarial pass after
it, which worked a punch list of defects and re-verified each repair against the raw data before
writing it.

**Evidence labels**, used below exactly as the research uses them: **INFERENCE** — arithmetic or
reasoning on top of measured numbers, not itself measured. **NOT ESTABLISHED** — the evidence does not
settle it, and the text says what would. **EXTRAPOLATION** — a number carried from the setting where
it was measured to a different one; the spike refuses these, and §7 says why.

## 1. The question

Can the AST produced by `core/dashboard/expr.py` be compiled to Postgres SQL that agrees with
the Python evaluator on every case in `tests/fixtures/expr_vectors.json` (within
`float_epsilon` = 1e-9), well enough that `api/dashboard/sources.py` can push
`derive`/`where`/`sort`/`limit` into the database instead of materialising up to
`MAX_SCAN = 20 000` rows and filtering them in Python? Go/no-go was asked on one architecture:
**a standalone compiler plus a thin GIMS adapter** (`FRAMING` §4 #5).

`tests/fixtures/expr_vectors.json` is **the fixture**, and the word appears throughout below: it is
the 130-case test file GIMS already ships beside the Python evaluator, each case being one
expression, one input record, and the answer Python is expected to give. `float_epsilon` = 1e-9 is
the tolerance the comparison was allowed to use — two numbers count as agreeing if they differ by
less than that.

## 2. What was established

**The translation is demonstrable — say this first.** A throwaway compiler and a three-outcome
conformance harness scored **130 of 130 fixture cases `COMPILED_AGREES`**: 0 diverging, 0 failed
to compile, 0 SQL errors; **max |SQL − Python| = 0.0**; **0 of 54 numeric cases consumed the 1e-9
epsilon** — that is, the tolerance was available and no case needed it; **22 of 22 strings
character-exact**; and **23 of 23 negative controls** pass — deliberately wrong answers fed to the
comparison first, to prove it says *no* when it should, including one that is the spike's own
non-negotiable written as an executable test (`f1` §1.2, §1.5, §1.7). The literal question is
answered yes — **under one condition that is not a formatting detail**: the run pinned
`extra_float_digits = 1`, a Postgres **GUC** (a setting you can change per connection) that controls
how many digits Postgres prints when it turns a number into text. **68 of the 130** cases carry a
value through a **float8** conversion — `float8` is Postgres's double-precision number type, the same
64-bit format a Python `float` uses — and whether those cases still agree at any other value of that
setting is **NOT ESTABLISHED** (`f1` §1.2, `f5` §5.2/§5.11).

**The fixture is not the acceptance test — and the spike measures that rather than asserting
it.** **6 of 7** `KNOWN_DIVERGENCES` entries are `in_fixture: false` (`compile.py:71-146`,
`f5` §5.2); the fixture holds **zero** `sort`/`filters`/`limit` cases, two of the question's
four clauses (`xb` B.10); and **0 of 130** fixture cases make the Python evaluator raise at all,
measured by re-running it over the fixture — the reason being simply that the fixture contains no
boundary case (`xa` A.3, second table). *Citation corrected:* the stronger, by-construction result —
that the input domain **cannot reach** any of the eight sites where the reference evaluator raises —
is about the 403 coverage probes, not about the 130 fixture cases; `FINDINGS.md:4489` (§5.2) attaches it to
the 130 and this page inherited the slip. (A fourth item once sat here — that the harness's own
failure branches had never been exercised. It has since been retested and no longer holds; see §2a.)

**The spike's own non-negotiable was breached.** `FRAMING` §5 required that a fallback to
in-memory evaluation be *reported, never silent*. Outside the fixture, breaches were measured in
**both** of §5's named directions — `NULL` → value and raise → value — and all three panel seats
recorded `framing_s5_breached: true` (`f5` §5.1, `xc` C.8). This, not the performance number, is
what makes the prototype unshippable as it stands.

**Performance is negative.** The compiled arm is **3.79× to 7.15× slower** than the current
in-memory path across six table sizes (1 k → 1 M) — **no crossover, gap widening with N**; at
1 M, 59 590 ms against Path A's 8 331 ms (`f4` §4.4, `f5` §5.3a).

**The existing index is the wrong shape, and is not the blocker.** *An index is a side structure that
lets Postgres jump straight to the rows that match instead of reading every row in the table; without
a usable one, every query the compiler generates is a full scan by construction — so this paragraph
is about the only lever that could ever have made the compiled path fast.* GIMS ships one index over
the JSON column: `GIN (data jsonb_path_ops)`, in `migrations/pg/0002_instances_data_gin.sql`. **GIN**
is the index kind Postgres uses for "look *inside* this JSON value"; `jsonb_path_ops` is the flavour
of it built for **jsonpath**, Postgres's small query language for reaching into a JSON document
(`$.score > 90` and the like). Across **36 measured query plans** — a plan being Postgres's own
printed account of how it intends to answer a query — that index was chosen **0 times**, and forcing
its hand with `enable_seqscan = off` (the per-connection setting that tells Postgres to avoid reading
the whole table) changed **0 of 36** (`f3` §3.2). **Two distinct causes, and conflating them flatters
a GO.** The GIN goes unused because neither `jsonb` GIN *opclass* — the set of operators an index kind
knows how to answer — offers the comparison operators the generated predicates need; that is a
property of Postgres, not of our compiler, and no compiler change reaches it. Separately, a
*purpose-built* expression index cannot be created today because `compile.py`'s `STABLE` `to_jsonb()`
wrapper makes Postgres refuse any index whose expression contains a compiled **predicate** (W1–W9) or
the compiled **`derive`** column (D1) — so **four compiler changes** must land before one could even
be attempted (`f3` §3.3–§3.4). Not an absolute: the compiled **sort key** carries no wrapper, indexes
today, and was measured index-backed at **0.065 ms** (`f3` §3.6 H4). The shape autoSQL needs is a
per-`(collection, key, extractor)` **B-tree** — Postgres's ordinary sorted index, the kind that
answers `=`, `<` and `>` on one extracted value (`f5` §5.9(4)).

**Half the divergence register is invisible: 18 of 33 distinct `expr`-layer classes are
undetectable at query time by any mechanism** (`xc` C.8–C.9; 3.6× the body's own earlier figure).

**The decisive fact is in GIMS, not in the compiler.** `resolve()` in
`GIMS-Project/api/dashboard/sources.py:357` returns exactly `{records, count, truncated}` — **no
`pushed_down` field, no `fallback` field** — and fallbacks reported today = **0** (`f2` §2.8,
re-verified live). `FRAMING` §4's *"detectable and reported at query time"* clause fails on a live
read, not on an argument.

## 2a. What the 2026-08-21 re-check changed

Evan made his ruling conditional on two checks running first (`.autodev/notes/ANSWERS-FROM-EVAN.md` Q4 and Q5).
Both were done, and he then signed (§6). The working — including what each check's own adversarial
re-check found — is in `spikes/T-1/RECHECK-2026-08-21.md`; this is the short version.

**The test rig was proven able to report a failure — so 130 of 130 is a credible fact.** The harness
runs each fixture case twice, once through Python and once through Postgres, and compares. Nobody had
ever seen it say *fail*: a line tracer over a full run measured **0 executions** of every branch that
reports one. Driven with six deliberately wrong compilations it emitted `COMPILED_DIVERGES`,
`DID_NOT_COMPILE` and `SQL_ERROR` correctly through the real per-case loop — and the case that failed
to compile landed in the **denominator** (`Pass rate = 125/130 = 96.2%`) rather than quietly scoring
130/130 again. **The branches were dead, not broken.**

**That removes a stated ground for the NO-GO, and this page leaned on it.** `FINDINGS.md:5251` books
the fixture-adequacy leg as *firmer* on exactly that basis — 130/130 "scored by a harness whose
branches have never been emitted, only inferred". **That ground is spent.** The leg falls back on the
68-of-130 coverage argument in §3, always the stronger half, re-derived exactly here. The honest
reading: **130/130 got stronger, not the NO-GO weaker** — 130/130 was never what the NO-GO rested on,
it is the pro-GO fact the NO-GO has to account for.

**The evidence trail was reconstructed, and it holds — but its own report overstated the case.**
Every refusal register reconciles against the raw artifact it cites; every retained measurement
re-derived to the digit — the 3.79×–7.15× headline, the 68/130 subset coverage, all 16 jsonpath rows.
The 130-case strict-jsonpath claim, which had **never been tested**, now reproduces cell for cell —
**with a caveat the adversarial reader called "correct and important", and which belongs beside the
result**: neither instrument, the original or the rebuild, contains an AST→jsonpath *translator*, and
translation is exactly where the semantic risk lives. The original hand-writes its jsonpath strings as
a fixed 11-case list that never reads the fixture, and writes them in a different form
(`$."score" ? (@ > 90)`) than the published table uses (`$."n" < 7`); the rebuild supplies the
translation convention itself. So this is the best available **substitute**, not a clean
re-derivation (`RECHECK` §3.5). And the reconstruction's own report was then judged **OVERSTATED in
three places** by a second adversarial reader — including its single headline finding, that
`FINDINGS.md` "never concedes" the `+463%` fallback below. It does concede it, verbatim, at `:2929` (§4.10 item 10);
only the strike arithmetic was new (`RECHECK`, answer-up-front and §3.4). Everything reported here is
the re-check's reading, not the reconstruction's own.

**Two real holes `FINDINGS.md` does not disclose.** Neither touches a decision fact; both mean
reading it with a correction sheet beside it.

- **A closure seat died mid-pass** — `.parts/closure-reports.md:13` (`agent died: API connection lost
  mid-response`) is the only mention anywhere. So all **6** of Finding 2's verification corrections
  went unapplied at the time. **The 2 material ones were applied on 2026-08-21** under go-ahead
  `GA-3`, and are verified corrected in the current file: the recursion limits now read **333 / 333 /
  332** (`FINDINGS.md:1151`, §2.6 — published 400 / 334 / 499, cited as `:1124` before the amendment)
  and "the parser permits depth" now reads **63** (`FINDINGS.md:1184-1185`, §2.6 — cited as
  `:1143-1144` before the amendment; `expr.py:186-187` increments *then* tests). The other **4**,
  all cosmetic, are still unapplied and `FINDINGS.md`'s own amendment entry lists them.
- **The `+463%` figure rests on an unreproducible number.** Cited **11 times**, it depends entirely on
  one measurement (`poison_syncscan.off.median_ms = 6916.85`) whose producer script did not survive.
  Struck, the identical claim prices at **+2.2%** from retained numbers. `FINDINGS.md:2929` (§4.10 item 10) concedes
  that fallback and flags it Material — but only there, not at the other ten citation sites. **This is
  the one thing the re-check found that argued for CONDITIONAL-GO instead.**

**And this pass repeated, once, the failure it was auditing.** The adversarial check that declared
item 1 sound reached the document as a spoken result with **no file on disk** — which is precisely the
property item 2 was sent to investigate. Item 1's own working (`.recheck/harness.md`) and every
command output it cites *are* on disk, and the load-bearing hashes were re-verified; the check *of* it
is not (`RECHECK` §5.10). Re-running it with its report written to `.recheck/adversarial-harness.md`
closes the gap cheaply.

**The recommendation stood** — nothing found touched the three facts it turns on; §4 says which, and
why. The one result that *would* have overturned it — the harness scoring `DID_NOT_COMPILE` as a
pass, voiding every conformance number downstream — is precisely the result this pass did not get.
**Still open:** Q4 asked about "the test rig", and only the conformance harness was tested;
`differ.py` — *"the instrument that produced every decision-relevant divergence"* — and `bench.py`
still have no negative controls of their own (`RECHECK` §5.1).

## 3. The options

| Option | What it would take | What it costs | What the evidence says |
| --- | --- | --- | --- |
| **GO** — build it as scoped | fund the build | — | **Unavailable, unanimously:** all three panel seats hold that §4's third GO clause fails outright and that the prototype as built must never ship (`f5` §5.1) |
| **CONDITIONAL-GO** — compile a statically-decidable subset, refuse the rest loudly | the corrected subset (32 of 48 constructs; functions `abs coalesce count if length max min`), the five GIMS-side changes of `f5` §5.5 pt 2, and E1 before anything ships | **68 of 130 fixture cases (52.3%)** — measured at closure (`analysis/subset-coverage.json`), independently re-derived; **not** the 84/130 (64.6%) the panel argued from. The AVOID rule — refuse to push an expression into SQL whenever it merely *could* reach a known divergence, decided from the expression itself before any SQL runs — refuses the other **62 of 130 (47.7%)** (`f5` §5.7) | Legitimate, and weaker than it looks. Its residual is **partly measured and non-empty**: **8 of the 16 paths diverging at `a = 1e300` are in-subset**, one (`max($.l)`) returning SQL `1` for Python `1e+300` — a silently wrong **number**, §4's stated disqualifier (`analysis/fuzz/A_f8_guard.txt` §A2, `xc` C.10). The *rate* is unmeasured, and the only widget measured end to end is a date widget outside every proposed subset — **no existing measurement is subset-legal** |
| **NO-GO** — don't fund it on this evidence; run E1 and E2 first | two experiments, on instruments that exist | the status quo stays wrong in a bounded, signalled way: under `MAX_SCAN`, **top-50 recall** — of the 50 rows that truly belong at the top of the widget's sort, how many the capped path actually returns — is **100 / 88 / 38 / 4 %** at 20 k / 25 k / 100 k / 1 M (`f4` §4.7) | **this is what Evan ruled** (§6) |

## 4. The recommendation, and what it rests on

**NO-GO on the architecture as scoped** — recommended by the research, and ruled by Evan on
2026-08-21 (§6). `f5` §5.5 point 5 and §5.11 give it this shape (condensed here; the verbatim wording
is in `FINDINGS.md`):

> **NO-GO does not mean "the translation is impossible"** — §5.9 records that it was
> demonstrated — **nor "discard the work"**. It means: do not fund a standalone compiler plus
> thin adapter on this evidence; run E1 and E2 first, and let a GO be earned.

The sentence no single finding contains, which `f5` §5.3 assembles: *there is no measured
configuration in which pushdown as prototyped is simultaneously faster than today's path and no
less correct* — and the legs are coupled, the speed fix blocked behind the index, the silence
fixes costing speed, and the 19 667× **payload win** (the bytes shipped from Postgres to Python:
16.1 kB for 50 rows instead of 317.02 MB for a million) collapsing to 19.1× once `sort`/`limit` leave
a subset (**INFERENCE** — arithmetic derived, inputs measured; `f5` §5.3(d)).

**E1 — the subset acceptance battery** (`f5` §5.7): re-run the 21 batteries of
`analysis/fuzz/run_all.sh` plus the three it does not regenerate, the 130 conformance cases and
the 403 coverage probes, with AST generation **restricted to the corrected
subset** and the value domain widened to reach the eight raise sites. **Bar: zero outcomes in the
classes "different value", "value → NULL" and "NULL → value", and zero cases bucketed `PY_RAISE`
in which SQL returned a value.**

**E2 — the like-for-like performance run** (`f5` §5.7 cond. 4), which no seat performed: Path A
against a compiled **subset-legal** widget, same table and corpus, at 20 k / 100 k / 1 M. **Bar:
below Path A's measured 13.3–15.0 µs/row under the cap** (`f4` §4.5, 1 k–25 k) **and the ≈16.7 µs/row
uncapped alternative** (the latter an **INFERENCE**, `f5` §5.5 pt 3); `panel.json[2]`'s C-0 states it
as ≤ 5.5 µs/row. Evan's ruling adds a requirement to this run: benchmark **absolute user-facing
latency**, not just the relative slowdown. **The absolute number itself is not yet set** — see §8.

**Why it survived the re-check.** It rests on three facts and the re-check touched none of
them: **(1)** `resolve()` at `sources.py:357` returns `{records, count, truncated}`, so a fallback has
no channel to be reported through; **(2)** the compiled arm is 3.79×–7.15× slower with no crossover —
re-derived exactly on 2026-08-21, and Evan's Q11 ruling (§6) makes it a floor; **(3)** 18 of 33
divergence classes cannot be detected at query time by any mechanism. What the re-check did move is in
§2a, in both directions, and it is small by comparison.

## 5. Where the panel disagreed

Disagreements surface; they are not averaged. Three **seats** — three AI reviewers, each adjudicating
alone — read the same bar on the same evidence (`.parts/panel.json`, 13:50) and **did not converge**:

| seat | verdict | the one fact it turns on |
| --- | --- | --- |
| `panel.json[0]` | **CONDITIONAL-GO** | every silent divergence traces to a named construct; excluding 12 of 22 functions removes all of them — 36 of 48 constructs, 84 of 130 cases |
| `panel.json[1]` | **NO-GO** | the divergences are keyed on runtime **values**, not constructs, so §4's CONDITIONAL-GO template cannot be instantiated |
| `panel.json[2]` | **CONDITIONAL-GO** | the economic case reduces to one unmeasured proposition — that a total *and* fast SQL runtime exists — so the only defensible go buys that experiment first (C-0) |

**What moved the synthesis to NO-GO at closure** — closure being the final pass that read all the
sections against each other (`f5` §5.4): four cross-cutting sections landed *after* `panel.json`.
`expr` is **not total** (it can crash rather than return), and **7 of its 8 raise mechanisms sit
inside the only named subset**, 2 of the 4 measured raise→value witnesses among them (`xa` A.2, A.5);
the in-memory fallback target itself raises uncaught, taking a whole widget to HTTP 500
(`sources.py:147`, `:162`); `filters`/`sort` carry two **uncompilable** obligations (`xb` B.8);
and reachability cut **both** ways — 0 production witnesses for the float and Unicode classes,
weakening seat [1]'s sharpest witnesses, but the classes reached *at scale* are the coercion and
tolerant ones no compiler, test or rule covers, weakening both subsets (`xd` D.3–D.6). One item
cut **for** CONDITIONAL-GO: `xc` C.1's DETECT/AVOID split — DETECT being "we can tell at query time
that this query diverged", AVOID being "we cannot tell, so we refuse the expression in advance". Closure also corrected the subset from
84/130 to **68/130**.

## 6. The ruling, and Evan's scope decisions

**The ruling (Q1, re-confirmed as GA-3 on 2026-08-21).** *"Don't build yet; fund the two
experiments."* His note attached to it, verbatim: *"Stands — don't build yet. Continue. Do not ship
the prototype as a universal replacement for Python. Build the bounded SQL path with explicit
fallback, instrument which path ran, and run the dedicated subset acceptance tests before treating
that subset as production-safe. Benchmark absolute user-facing latency rather than treating a
3.79×–7.15× relative slowdown as intrinsically fatal."* **The ambiguity that was on the record — the
tick says *don't build*, the note describes a bounded build — was resolved on 2026-08-21 as a ruling
on delegated authority** (GA-4), not by him personally: the tick governs the **GIMS integration**, the
note describes the **demo** he had already authorised under Q18/Q19/Q24, and "acceptance tests before
production-safe" gates the integration rather than the demo. Full derivation, and the one line that
overturns it, in [`decision-expr-to-sql.md`](decision-expr-to-sql.md) §6.

His other answers rule on **scope**. Five change the shape of whatever gets built. All 46 questions
and all 12 follow-ups are answered and written down in `.autodev/notes/ANSWERS-FROM-EVAN.md`.

- **Index use is permanently off (Q11).** He rejected writing tenant-supplied field names straight
  into SQL text, and index work goes with it. Without an index Postgres has no way to jump to the
  matching rows, so every generated query is a full scan by construction. **This removes the only
  route by which the compiled path could ever have got faster** — §2's 3.79×–7.15× becomes a floor,
  so the performance leg gets harder, not softer.
- **All three widget source types are in scope (Q13)** — the largest option offered: a
  filter-accepting read method across the shared storage interface and every store implementing it,
  **plus** a separate SQL path into the hand-written verb-log query, which has no shared storage layer
  to attach to at all.
- **autoSQL owns the storage migration, as a prerequisite (Q14).** Moving noun records into the shared
  `instances` table is autoSQL's job and comes first. Weigh it against §7's measured figure: migrating
  `instances` to `jsonb` changes today's Python answer on **4 166 of 17 345 real rows**.
- **The target is high-volume data GIMS does not hold yet (Q15).** Near-term value is **correctness —
  completeness of answers — not speed**; no GIMS collection observed today reaches the 20 000-row cap.
  That reframes the performance leg rather than dissolving it.
- **GIMS contract changes come after the demo (Q3).** `resolve()` may grow the fallback-reporting
  field §2 says it lacks — but only once T-2's fake-data UI demo has been seen working. Nothing that
  depends on that field can be scheduled ahead of it.

## 7. What this means for autoSQL

autoSQL is a greenfield repo whose premise is generating SQL underneath an interactive UI, for
eventual integration into GIMS. **The spike studied one expression layer — the `derive`/`where`
half of one dashboard source module — not the whole idea.** It does not say SQL generation for
autoSQL is wrong; it says this architecture is not funded by this evidence, which is itself narrow:
*n* = 1 machine, 1 dashboard, 3 widgets, no `DataSource` corpus in either tree, so **no fraction of
production traffic may be quoted at the gate** — no EXTRAPOLATION from this bench to production is
allowed (`f2` §2.9, `xd` D.8 — *"Nothing here extrapolates to production."*).

- **The bottleneck thesis in [`autosql-architecture.md`](autosql-architecture.md) survives as a
  correctness argument, not yet a performance one.** `MAX_SCAN` is a *correctness* cap — 98% of
  qualifying records never examined at 1 M, under a badge reading "Result capped for performance" —
  and pushdown fixes it; but the compiled path measured 3.79×–7.15× slower (`f4` §4.4; the recall figures are `f4` §4.7).
- **Four GIMS defects exist with or without pushdown** (`f5` §5.9(3)) — among them that `expr` is
  not total, and that migrating `instances` to `jsonb` would change today's Python answer on
  **4 166 of 17 345 real rows** (production relevance labelled an INFERENCE by `xb` B.4 itself).
- **Documentation defect C3 — fixed by this stage.** `autosql-architecture.md`'s storage-layer
  claims hold for `GUTS/spine/L1-memory/gims-ledger`, not `GIMS-Project`, and the page did not say
  which tree it meant. `FRAMING` §2 C3 assigns that wording fix to `sp-synth`; both claims now name
  their tree, and the GIN claim carries this spike's finding that the index is the wrong shape.

**T-2** (the fake-data UI demo) is moving: it is out of intake, at `refine` writing its spec with a
design stage added, and Evan's approval of that spec is the next thing waiting on him. **Because the
gate is now cleared, T-2 is no longer held behind this decision** — that is a consequence of the
ruling, not a standing fact, and Q18 sets its limit: *"Green light, but only the safe operations."*
Its SQL-generation layer is still what this decision governs, and Q3 puts the demo *before* any GIMS
contract change.

## 8. Status and pointers

T-1 is at `sp-decide` with the gate **cleared** (GA-3, 2026-08-21). The ticket's authority is
`recommend-and-wait` — the research recommends and Evan decides — and he has decided. Next in the
pipeline is `sp-spawn`, which turns the accepted option into build tickets: **E1, the subset
acceptance battery, and E2, the like-for-like speed run, correctness run first (Q6).**

**What is still genuinely open**, and none of it blocks the follow-up runs from being planned:

1. ~~The tick-vs-note ambiguity in the ruling~~ — **ruled 2026-08-21 on delegated authority** (§6):
   the tick governs GIMS integration, the note describes the already-authorised demo. Overturnable by
   Evan in one line.
2. ~~E2's absolute latency bar~~ — **ruled 2026-08-21 on delegated authority**: three bars, one per
   collection size (350 ms / 1 000 ms / 5 500 ms at 20 k / 100 k / 1M), plus a kill condition that the
   compiled path must beat the in-memory path at the same row count. `spikes/T-1/EXPERIMENTS.md` §2.2.
3. **Q31's corpus-regeneration notes.** He asked for written instructions for regenerating the
   1 000-to-1 000 000-row test tables, which were deleted. Not started, and E2 needs them.
4. **The two material errors still published in `FINDINGS.md`** (§2a). He answered *"fix them —
   re-fingerprint the document"* (follow-up item 2); the amendment has not been made yet.

| Looking for | Where |
| --- | --- |
| The full working — 5 findings, 4 cross-cutting sections, closure log | `spikes/T-1/FINDINGS.md` |
| §2a's working — both verifications, both adversarial re-checks, what is still open | `spikes/T-1/RECHECK-2026-08-21.md` |
| Every answer Evan has given — all 46 from the first round and all 12 follow-ups, verbatim, each with what it caused, plus the three items still outstanding | `.autodev/notes/ANSWERS-FROM-EVAN.md` |
| The ruling as an event, with his words verbatim | `.autodev/events.jsonl` (GA-3) |
| The bar, set before any evidence | `spikes/T-1/FRAMING.md` §4/§5 |
| The 130-case run, per case | `spikes/T-1/proto/results.json` |
| Every performance number above | `spikes/T-1/analysis/measurements.json` |
| The corrected subset's 68/130, per case | `spikes/T-1/analysis/subset-coverage.json` |
| Divergence witnesses, and E1's batteries | `spikes/T-1/analysis/fuzz/` |
| The three panel seats, verbatim | `spikes/T-1/.parts/panel.json` |
