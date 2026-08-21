# T-4 · Framing — the timing run: how long does a person actually wait?

Stage: `sp-frame` (spike@v2) · lean: ON (`.autodev/shop.json` → `settings.lean: true`, verified)
Framed: 2026-08-21 · Every measured figure below was taken on this machine while writing this,
read-only, and is marked **[measured 2026-08-21]**.

Full specification: **`spikes/T-1/EXPERIMENTS.md` §2** (the run it calls **E2**). This document does
not restate that spec. It states, *before anything runs*, the bar the result is judged against, the
hygiene the measurement must meet, what makes a number unusable, what has to exist first, and when
to stop.

> **Vocabulary, since this document uses shop jargon.** A **spike** is a time-boxed investigation
> that answers a question rather than shipping a feature. **`sp-frame`** is its first stage: write
> down what would count as an answer *before* collecting evidence, so the result cannot be
> rationalised afterwards. **`sp-decide`** is the later stage where Evan rules go/no-go — spelled
> with a **hyphen**, because that is the stage's name in this ticket's own pipeline
> (`["sp-frame","sp-investigate","sp-synth","sp-decide","sp-spawn"]`, read out of the ticket file).
> Earlier drafts of this document wrote it `sp_decide`; the underscore form is only the *key* the
> gate carries inside `.autodev/data/gates-policy.json`, where it is set to `human`. This document
> says **`sp-decide`** throughout and means the stage. A **seat** is the agent working one stage of
> one ticket — the seat that writes this framing is not the seat that runs the benchmark, and
> neither of them is Evan. **Lean** is the shop's lightweight ceremony mode. An **arm** is one of the
> several ways the same dashboard widget is answered, timed side by side. A **corpus** is the pile of
> fake rows everything is measured over. **Recall** — the term the correctness column of §4.1's bar
> table turns on, and the one term here a reader most needs — means *of the rows that should have
> been in the answer, how many actually came back.* Recall 100% is the right rows; recall 4% at a
> million rows means 48 of the 50 rows on screen do not belong there.

---

## 1. The question

> **At realistic collection sizes, how many milliseconds does a person wait for one dashboard
> widget — on today's in-memory Python path, and on the compiled-SQL path — and is the compiled
> path's wait short enough to be worth building?**

Not "is it faster than Python". Not "by what multiple". **How many milliseconds.**

## 2. The correction this framing is built around

Evan re-specified this run himself. Verbatim, from his Q1 re-confirmation
(`ANSWERS-FROM-EVAN.md`, Q1; logged as **GA-3**):

> **"Benchmark absolute user-facing latency rather than treating a 3.79×–7.15× relative slowdown as
> intrinsically fatal."**

That sentence is the whole design of this run, and his own measured numbers make the case better
than any argument could. Both ends of that range, from `FINDINGS.md` §4.4 (line 2450 and 2453,
re-read):

| collection size | today's Python | compiled | the ratio | **the extra wait** |
|---:|---:|---:|---:|---:|
| 20,000 rows | 300.10 ms | 1,138.61 ms | 3.79× | **839 ms** — noticeable, survivable |
| 1,000,000 rows | 8,331.43 ms | 59,590.03 ms | 7.15× | **51 seconds** — everybody can feel this |

**The ratio moves by less than 2× across those rows. The wait moves by about sixty-fold.** A bar
written in ratios says roughly the same thing at both ends, which means it says almost nothing about
whether a person would mind. Evan is right, and this run is built on his unit.

**What the correction does *not* ban.** It bans ratios as the **bar**. It does not ban measuring
them. Ratios tell you where the time went. They just stop deciding anything. Restated as a rule the
write-up must obey: **a ratio may appear in the report; a ratio may never appear in the verdict.**

## 3. Timebox — scope, with stop rules

There is no clock in this factory, so the timebox is stated as **scope, with stop rules**.

**Scope:** one measurement pass over three required collection sizes, five arms, two widgets, on one
quiet host. `EXPERIMENTS.md` §2.6 budgets an **exclusive 2–3 hour window** for that, including
re-runs of voided cells. Nothing is added to the run that is not in §2.3.

**Stop rules — hit one and the result is written as-is, not chased:**

- **Pre-flight says the answer is closed.** Before the expensive 1,000,000-row pass, run the chosen
  widget's predicate alone over the 100,000-row table under `EXPLAIN (ANALYZE, BUFFERS)` and divide
  execution time by rows scanned (`EXPERIMENTS.md` §2.2, the method of `analysis/index-shape.md`
  §4.1). If that µs-per-row figure × 1,000,000 already exceeds 5,500 ms, **the 1M pass still runs and
  still reports its milliseconds** — but nobody books a second exclusive window believing the answer
  is open.
- **A cell voids on host load twice.** Re-run it once. If it voids again, record the host as
  unavailable for that cell and stop; do not keep re-rolling until a number looks good.
- **The 1,000,000-row load fails again on shared memory.** The known failure is
  `DiskFull: could not resize shared memory segment` at `VACUUM ANALYZE`. Apply the named fix **once**
  (`max_parallel_maintenance_workers = 0` for the load, or enlarge the container's `/dev/shm`),
  record which, and if it fails a second time **stop at 100,000 rows and report the 1M row as
  untested — never as an estimate.**
- **Disk runs low.** 19 GB free of 457 GB, 96% used **[measured 2026-08-21]**. Generate and drop the
  CSV for one size at a time. If free space falls below ~5 GB, stop and report the sizes completed.
- **Out of window = report the sizes that completed and mark the rest untested.** A partial latency
  table with honest gaps is a valid result. **Extrapolating a missing cell is not** — that is exactly
  the defect `EXPERIMENTS.md` §2.3 flags in the existing ≈16.7 s figure, which is arithmetic wearing
  a measurement's clothes.
- **The negative control fails — stop before any real timing at all.** §6.1. If the harness cannot be
  shown able to mark a cell **void**, nothing it later prints is evidence, and the correct move is to
  fix the harness rather than to spend the window.

**Every stop rule above produces a verdict, and for the first four that verdict is normally
`INCOMPLETE` — not "a pass with a gap".** A partial latency table with honest gaps is a valid
*result*; **§4.5 says what *verdict* it carries** and forbids the word "pass" appearing anywhere in
it.

## 4. What a decision needs — THE BAR, stated in advance

The bar below is **not mine and not invented here.** It is read out of `EXPERIMENTS.md` §2.2. Its
authority needs stating carefully, because the obvious citation — the one earlier drafts of this
section used — is the wrong one.

> **The basis for this bar, checked line by line in `.autodev/events.jsonl`.** A **go-ahead** is a
> recorded line from Evan authorising a class of decisions; each one is logged with the list of
> tickets it was recorded against.
>
> - **The unit — milliseconds, not ratios — is Evan's own**, verbatim, under **GA-3** (line 42,
>   2026-08-21T18:37:03Z), recorded against **T-1**, the investigation this ticket was spawned out
>   of. That is §2 above, and it is not delegated at all: he wrote the sentence.
> - **The 5,500 ms figure is older than any delegation.** It is the earlier panel's C-0 line, set
>   *before* the evidence was collected, converted into Evan's unit — §4.3.
> - **The authority for a seat ruling T-4's open questions while he is away is GA-5** (line 53,
>   2026-08-21T20:36:56Z): *"Be as autonomous as possible looping through what we still have to try
>   and get through all the tickets."* GA-5 is recorded against **`["T-2","T-3","T-4"]`** — this
>   ticket is named in it. **That is the go-ahead this framing runs under**, and §10 cites it.
> - **GA-4 is NOT the authority here.** GA-4 (line 52, 2026-08-21T19:43:01Z) is *"I feel like these
>   questions can be answered with your best judgement… I approve the spec for T-2"*. Two caveats
>   travel with it in this project's other documents and were dropped when it was quoted here: it is
>   recorded against **`["T-2"]` only**, and it carries **`scope_confirmed: false`** — nobody put the
>   scope of that delegation back to Evan and had him confirm it. It is where the *phrase* "ruled on
>   delegated authority" in this project comes from, and the T-1 seat was working under it when
>   `EXPERIMENTS.md` §2.2 was written, but **it does not name T-4 and it cannot be quoted as covering
>   this ticket.**
>
> **None of the numbers move because of this.** What changes is that the citation under them is now
> one that survives being checked.

The bar is reproduced here so the run cannot proceed without it in front of it.

### 4.1 Three bars, one per collection size

**Because "what a person actually waits" is not one thing.** A 20,000-row widget is a page load; a
million-row widget is a report someone asked for knowing it was big. Same person, different patience.

**Measured as:** the **median** wall clock of one complete widget resolve, on the shippable compiled
path (**arm C**), on a quiet host, over the repetitions ruled in §5.2.

| collection size | **PASS if median ≤** | **and the tail statistic ≤** | repetitions (§5.2) | today's Python, measured | is today's answer correct? |
|---:|---:|---:|---:|---:|:--|
| **20,000** | **350 ms** | 95th percentile 700 ms | n = 25 | 300.10 ms | **yes** — top-50 recall 100% |
| **100,000** | **1,000 ms** | 95th percentile 2,000 ms | n = 25 | 899.26 ms | **no** — recall 38%, 31 of 50 displayed rows do not belong |
| **1,000,000** | **5,500 ms** | **worst of 9 — max ≤ 8,331 ms** | n = 9 | 8,331.43 ms | **no** — recall 4%, 48 of 50 rows wrong, top row wrong |

> **"Recall", since the last column turns on it and it is never explained anywhere else in this
> project's documents:** *of the rows that should have been in the answer, how many actually came
> back.* The widget asks for the top 50 rows. At 20,000 rows today's Python path returns all 50 of
> the right ones — recall 100%, nothing to fix. At 1,000,000 rows it returns **4%** of them: 2 rows
> right, **48 of the 50 rows on screen do not belong there, and neither does the one at the top.**
> That is the correctness problem the compiled path exists to fix. This run is about what fixing it
> costs in milliseconds.

**Every size that gets measured must pass. A size that does not get measured is neither a pass nor a
fail — §4.5 says what it is instead.** Python figures are `FINDINGS.md` §4.4; the recall figures are
§4.7. The per-row budgets those bars imply are **17.5 → 10.0 → 5.5 µs/row** — it tightens with size
because a person's patience does not scale with the row count. **The 1,000,000-row bar is the binding
one.**

The two tail numbers at 20,000 and 100,000 are a **2× convention, not a measurement**, and
`EXPERIMENTS.md` §2.2 flags them as such. The 1M tail number is not a convention — it is the kill
floor below.

> ### CORRECTED HERE — the 1M tail bar asked for a percentile that nine samples cannot produce
>
> **The contradiction.** As first drafted this table demanded a **95th percentile at every size**,
> while §5.2 rules **9 repetitions at 1,000,000 rows** — and the two lines met at exactly the size
> that decides the run. **The 95th percentile of 9 samples is the maximum**, under every
> interpolation rule in common use (nearest-rank, linear, all of them: 0.95 × 9 lands above the 8th
> point). So the binding size's tail bar would have been decided by **one reading — the single
> slowest of nine — while wearing the name of a percentile.** That is precisely the defect this
> project has shipped before: a number whose name described something other than what was measured.
>
> **Two repairs were available. The cost figures already in this document choose between them.**
>
> 1. **Raise the repetitions at 1M until a p95 is real.** §5.2's own threshold for a p95 to be an
>    interior order statistic is **n ≥ 20**. §5.2 measures the cost: one round of the five arms at
>    1,000,000 rows is roughly **145 s**, 9 repetitions land at **45–70 minutes**, and
>    `EXPERIMENTS.md` §2.6 budgets an exclusive window of **2–3 hours** for the whole run. Scaling
>    off those same figures: **n = 20 costs 100–156 minutes; n = 25 costs 125–195 minutes.** At the
>    top of either range the 1,000,000-row size *alone* eats the entire window — leaving nothing for
>    20,000, nothing for 100,000, nothing for the second widget, and in particular nothing for the
>    re-run that §3's void rule assumes is affordable. **Even the cheapest n that buys a real p95
>    costs the rest of the run.**
> 2. **State the 1M bar as a statistic 9 samples can support.** Costs nothing.
>
> **Repair 2 is the one taken, and this is the change:** at 1,000,000 rows the tail bar now reads
> **"worst of 9 — max ≤ 8,331 ms"** instead of "95th percentile ≤ 8,331 ms". **The number did not
> move and its meaning did not move**: no single one of the nine resolves may take as long as today's
> Python path already takes at that size. It is now labelled as the order statistic it always was.
> At 20,000 and 100,000 rows n = 25, where the 95th percentile *is* a real interior order statistic,
> so those two rows keep it — and §5.2's "no column called p95 below n = 20" rule now agrees with
> this table instead of contradicting it.
>
> **Note this is STRICTER than the p95 it replaces, not looser.** A max bar is failed by one bad
> reading, where a p95 over 20+ samples would absorb it. That is only safe because of **§6 item 1**:
> a cell taken outside §5.1's load band is **void** and re-run, so an outlier surviving into the
> reported nine is a property of the query rather than of the machine. **If the void rule is ever
> relaxed, this bar has to be relaxed with it** — otherwise it stops measuring latency and starts
> measuring host noise.
>
> **One line from Evan overturns this** in either direction. Wanting a genuine p95 at a million rows
> is a perfectly reasonable preference; what he would be buying it with is a **second exclusive
> quiet-host window**, and that is the trade, stated so he does not have to derive it.

### 4.2 The hard kill condition — it must beat what already exists

**At 100,000 and 1,000,000 rows, the compiled path's median must be strictly below the Python path's
median measured in the same session.** At a million rows that is **8,331.43 ms**. **Failing to beat
what exists is a kill whatever the absolute number** — there would be no reason to build it.

**At 20,000 rows the ruling took a different form**, and this is the one place it interprets rather
than applies, so it is flagged here as `EXPERIMENTS.md` §2.2 flags it. Today's answer at 20,000 rows
is *already exactly right* — row-for-row identical to the compiled arm (§4.7) — so the compiled path
buys no correctness there and cannot be justified by winning a race it does not need to win. The test
at that size is **no perceptible regression: within +100 ms of the same-session Python median.**
(An absolute increment, not a smuggled-back ratio.)

> **One line from Evan overturns this.** If he wants the strict form everywhere, the 20,000-row
> clause simply becomes "< the same-session Python median" and nothing else in this document changes.
> Worth knowing what he would be choosing: the compiled arm measured **1,138.61 ms** at 20,000 rows
> against Python's 300.10 ms, so strict-beat-at-every-size is close to a decision taken in advance.

**Use the same-session number, not the recorded one.** If the same-session Python median lands far
from 8,331.43 ms, that is itself evidence the host was not quiet, and §6 item 1 voids the cell.

### 4.3 The three candidate lines, side by side, so the choice stays visible

| line at 1M | per-row budget | what it means for a person | status |
|---:|---:|---|---|
| 2,500 ms | 2.5 µs | correct *and* feels fast — but **below every compiled predicate ever measured** | proposed earlier, **not taken** |
| **5,500 ms** | **5.5 µs** | correct, 1.5× faster than today, ~3× faster than the approved cap lift; a spinner, not a coffee break | **THE BAR** |
| 8,331 ms | 8.3 µs | correct instead of 96% wrong, but no faster than today | **the kill line** |

5,500 ms is not invented for the ruling: it is the gate an earlier panel set *before* the evidence
was collected (`panel.json[2]`'s C-0, restated in `FINDINGS.md` §5.7 condition 4), converted out of
µs/row and into the unit Evan asked for.

### 4.4 The bar cannot decide on its own which widget it is applied to

Compiled predicates measured on the same rig differ by **8.5×** (`analysis/index-shape.md` §4.1, via
`EXPERIMENTS.md` §2.1):

| compiled predicate | per row | fits 350 ms @20k? | fits 1,000 ms @100k? | fits 5,500 ms @1M? |
|---|---:|---|---|---|
| `$.status == "open"` | 2.73 µs | fits | fits | fits |
| `$.score > 90` | 7.43 µs | fits | fits | **does not fit** |
| `$.score * 2 > 180` | 23.2 µs | **does not fit** | **does not fit** | **does not fit** |
| `days_between(today(), $.due_date) < 7` | 66.0 µs | **does not fit** | **does not fit** | **does not fit** |

The widget this run uses is the arithmetic shape — the third row. Those figures were taken as
standalone predicate scans on a 50,000-row table, not as arm C over the corpus, so they do not settle
it. **They are why the pre-flight in §3 is mandatory rather than optional.**

### 4.5 What verdict a run produces when a size was never measured — a THIRD outcome

**Reconciling §4.1 with §3, which as written pointed opposite ways.** §4.1 requires every size to
pass. §3 explicitly permits a size to go unmeasured — the 1,000,000-row load can fail twice on shared
memory, the window can run out, the disk can fall below 5 GB — and in each case §3 says to report the
sizes that completed, mark the rest **untested**, and calls a partial table with honest gaps a valid
result. Both rules are right, and together they left a seat holding two green rows and one blank with
no stated verdict, to be invented at the worst possible moment.

**So the run produces exactly one of three verdicts. They are not interchangeable and the readout
must name one of them:**

| verdict | when it applies | what it tells Evan |
|---|---|---|
| **PASS** | all three required sizes measured; every contributing cell admissible under §6; every size at or under **both** its median bar and its tail bar (§4.1); **and** the kill condition met at every size (§4.2) | The compiled path is worth building on latency grounds. **This is the only verdict that says so.** |
| **FAIL** | any measured, admissible size misses its median bar, misses its tail bar, or fails §4.2's kill condition | Decisive on its own — **and it stays a FAIL even if another size went untested.** A miss is evidence; a gap elsewhere cannot cancel it. |
| **INCOMPLETE** | any required size is untested, or all of its repetitions voided — and no measured size failed | **Not a pass.** The run answered a smaller question than the one it was booked to answer. |

**INCOMPLETE is the verdict this framing most needs to be unmistakable, because it is the one that
most resembles a pass**: two green rows and a blank one reads, at a glance, as success. Three rules
keep it distinct.

1. **The word "pass" may not appear anywhere in a readout whose verdict is INCOMPLETE** — not in the
   headline, not in a summary sentence, not in a subject line. Per-**size** cells read `pass`,
   `fail`, `untested` or `void`; the **run-level** verdict reads `INCOMPLETE` and names which size is
   missing and why.
2. **An INCOMPLETE at 1,000,000 rows is worth strictly less than a FAIL at 1,000,000 rows, and must
   say so in those words.** 1M is the binding size (§4.1). A fail there closes the question. A gap
   there leaves it exactly as open as it was before an exclusive quiet-host window was spent on it,
   and the honest sentence — which the readout must actually contain — is *"this run did not answer
   the question it was booked to answer."*
3. **INCOMPLETE never clears `sp-decide` on its own.** What gets handed up is *"no answer at size N,
   and here is what an answer would cost"* — which, per §3, is a second exclusive window, never an
   estimate. **Extrapolating the missing cell turns INCOMPLETE into a fabricated PASS**, and is
   already inadmissible under §3's last stop rule and §6.

**Why an untested size is not simply scored as a fail.** Because a fail is a claim *about the
compiled path*, and at an untested size no evidence about the compiled path exists. Scoring a gap as
a fail would be exactly as much a fabrication as scoring it as a pass — merely a pessimistic one —
and it would kill a design on a measurement nobody took.

**Two sizes passing is still worth reporting.** INCOMPLETE is not a wasted run: "≤ 350 ms at 20,000
and ≤ 1,000 ms at 100,000, nothing at 1,000,000" is genuinely useful, and it is what §3's stop rules
are designed to preserve. It is just not an answer to §1's question, and it must not be dressed as
one.

---

## 5. MEASUREMENT HYGIENE — the most important section in this document

**A benchmark run on a loaded machine is not evidence.** Everything else here can be corrected after
the fact by redrawing a line. A number taken on a dirty host cannot be corrected at all; it can only
be thrown away and re-taken. This section is therefore the run's real acceptance criterion.

The evidence that this is not paranoia is in the project's own record:

- `FINDINGS.md` §4.6 re-ran four of the original sweep's queries at a measured 1-minute load average
  of 29 and the per-row date cost moved **+246% to +282%** (line 2560).
- The headline multiplier itself moved by a third — 3.79× down to 2.55× — between the sweep and the
  one load-controlled re-run in the record.
- One Postgres session setting, `synchronize_seqscans`, produced **"a 170× spread on the identical
  query and table"** — 40.76 ms against 6,916.85 ms (`FINDINGS.md` line 2888).
- **The original sweep never recorded its host load at all.** That is the single largest known error
  source in every number this project has.

A bar in absolute milliseconds is unusable against numbers taken at an unknown load. So:

### 5.1 What must not be running

**Required: the 1-minute load average is ≤ 2.0 when a size starts and ≤ 4.0 when it ends**, on this
20-core host, recorded both times (`EXPERIMENTS.md` §2.5 item 1). Outside that band the cell is void
and re-run.

> **Load average, since it decides everything here:** roughly the number of processes wanting a CPU
> at that instant. On a 20-core box a load of 2 means about a tenth of the machine is busy; a load of
> 20 means it is fully committed and your benchmark is queueing behind other work.

**This machine, right now, as the worked example [measured 2026-08-21T20:38:49Z]:**

```
/proc/loadavg   2.71  2.95  2.86        (1-min / 5-min / 15-min)
nproc           20
free -g         46 GB total, 32 GB available
df -h /         457 G, 19 G avail, 96% used
```

**That fails the start ceiling.** 2.71 > 2.0. And the same host read **16.18** earlier today, per
`EXPERIMENTS.md` §2.1 — a factor of six apart on one machine on one day, which is precisely why the
number has to be read and written down rather than assumed.

The named consumers, `ps -eo pcpu,pmem,comm --sort=-pcpu` **[measured 2026-08-21]**:

| %CPU | process | must it be stopped before the run? |
|---:|---|---|
| 200 | `node` | **yes** |
| 87.0 | `python` | **yes** |
| 75.0 | `chrome-headless` | **yes** |
| 17.8 | `chrome-headless` | **yes** |
| 16.8 | `firefox` | **yes** |
| 9.9 | `next-server` | **yes** |
| 7.0 | `claude` | the driving session itself — see below |

**The checklist, then:**

1. **No other AutoDev work on this machine**, in any repo. `EXPERIMENTS.md` §2.6 makes the host
   exclusive, and that includes the factory's own background workers and the `watch` sidecar.
2. **No browser, no headless Chrome, no dev server.** The three biggest consumers above are a
   development front end, not this project.
3. **The run goes nowhere near `glp-strong-db` — and the contention that container used to create
   has moved from the database server to the host.** This is the sharpest edge here, it changed
   shape after this framing was first drafted, and it is therefore stated in full.

   **What was true, and is no longer.** The spike originally measured against a scratch database
   `autosql_spike` sitting on **`glp-strong-db`** — the same Postgres server, the same container and
   the same 128 MB of `shared_buffers` as Evan's live `glp_strong`. Under that arrangement any GIMS
   process reading `glp_strong` competed directly with the benchmark, invisibly to any check of
   *host* load.

   **What is true now [verified 2026-08-21].** `autosql_spike` was recreated on `glp-strong-db`
   earlier today by a worker of this same session, and then **dropped at about 20:55** — §7.1 records
   exactly what it held and why it went. **The run must not put it back there.**
   `spikes/T-1/proto/REGENERATE-CORPUS.md` §3 opens with *"Do not load this into `glp-strong-db`"*
   and specifies a **throwaway container** instead: `autosql-corpus`, image `pgvector/pgvector:pg16`,
   **`--shm-size=1g`**, bound to **`127.0.0.1:55434`** so nothing off this machine can reach it, and
   destroyed with its anonymous volume when the run ends (§9 of that file). Two independent reasons,
   both already ruled: **Q31** ordered the scratch tables gone, and the role `glp_owner` owns the
   live database as well as the scratch one, so its password is a working credential for real data
   (`proto/README-db.md`).

   **The edge that remains: a separate container is not a separate machine.** `glp-strong-db` is
   still up on this host — `docker ps`: **up 5 hours, healthy, port 55433 [verified 2026-08-21]** —
   and it is not alone; `autosql-doccheck` on port 55436 was running while this paragraph was
   written. Every container here shares the host's **20 cores, its RAM, and the one filesystem that
   is already 96% full**. A GIMS job hammering `glp_strong` no longer competes for the benchmark's
   buffer cache; it competes for its **CPU and its disk** — quieter, but not smaller. And a busy
   neighbour container surfaces in host `ps` as an anonymous `postgres` process that nobody would
   connect to another project. **So check the containers, not only the processes.** §5.4 items 15–18
   say exactly what to record.
4. **The driving session is unavoidable and must be declared.** The `claude` process running the
   benchmark is itself on the list at 7.0% CPU. It cannot be stopped, so it is recorded as part of
   the host state rather than pretended away — and it must not be doing anything else (no parallel
   file reads, no other lane) while a cell is being timed.

### 5.2 How many repetitions, and which statistic — RULED

**Current state, verified:** `spikes/T-1/proto/bench.py:508` uses
`nreps = {1000: 9, 10000: 9, 20000: 9, 25000: 9, 100000: 7, 1000000: 3}`, and `reps()` at
`bench.py:297-311` reports **median, min, max, stdev, n** — no percentile, no load reading anywhere
in the file.

`EXPERIMENTS.md` §2.5 item 5 sets a floor of **5** repetitions and voids anything below it. But §2.2's
bar table asks for a **95th percentile**, and five samples cannot produce one — the 95th percentile of
5 points is just the maximum under any interpolation rule. Those two requirements are in tension, and
nothing in Evan's answers resolves it. So:

> **RULING (mine, not Evan's) — repetition counts and reported statistics.**
>
> - **25 repetitions at 20,000 and 100,000 rows.** Summing the per-arm medians in `FINDINGS.md` §4.4
>   (line 2450 and 2452), one round of the five arms costs roughly **3 s at 20,000** (A 300 ms,
>   B2 1,139 ms, B4 13 ms, plus A-uncapped and arm C estimated at their neighbours' cost) and roughly
>   **15 s at 100,000** (A 899 ms, B2 6,036 ms, B4 34 ms, same estimate for the two new arms). That
>   is about **2.5 minutes and 12 minutes** for both widgets together — affordable inside the window,
>   and at n = 25 the 95th percentile is a real order statistic, so §2.2's tail bars mean something.
>   *(Arm C and arm A-uncapped do not exist yet, so their cost is an estimate, flagged as one.)*
> - **9 repetitions at 1,000,000 rows.** One round of the date widget there costs roughly **145 s**
>   (A 8.33 s, B2 59.59 s, B4 0.23 s, plus arm C at about B2's cost and A-uncapped at the inferred
>   ≈16.7 s); the invented widget's round should be cheaper, having no date function. `EXPERIMENTS.md`
>   §2.6 budgets 25–40 minutes for a complete pass at **five** repetitions; 9 pushes that to roughly
>   45–70 minutes, which the 2–3 hour window absorbs with room for a re-run. **25 reps at 1M would
>   not fit** — it would consume the entire exclusive window before a single voided cell could be
>   re-taken. 9 is also the count the project's own script already uses at four of its six sizes, so
>   it is this shop's established number rather than a new one.
> - **Where n < 20, the run reports `max` labelled "worst of n" and does NOT print a column called
>   "p95".** A p95 computed from 9 samples is the maximum with a misleading name on it, and this
>   project has already been burned once by a number that was really a measurement of its own
>   instrument. **§4.1's bar table has now been restated to match**: at 1,000,000 rows the tail bar
>   reads *"worst of 9 — max ≤ 8,331 ms"*, not *"95th percentile ≤ 8,331 ms"*. Until that correction
>   this ruling and the bar it serves **contradicted each other at the one size that decides the
>   run** — the bar demanded a percentile, this ruling refused to print one, and nothing said what
>   the bar was then supposed to be. §4.1 resolves it, and shows the cost arithmetic that chose
>   restating the bar over buying more repetitions.
>
> **Derivation.** §2.5 item 5 sets the floor; §2.2 asks for a percentile; §2.6 makes the exclusive
> window the binding cost, not money — Evan's **Q9** put "no cap" on this run's budget, which removes
> the only other reason to skimp. Raising 1M from 3 → 9 is the smallest change that clears the floor
> and triples the worst-case coverage at the size that decides the run.
>
> **One line from Evan overturns this**, in either direction, and **nothing about what the run
> measures changes** — it is a dict literal at `bench.py:508` and a column in the output.

**The headline statistic is the MEDIAN. Never the mean.** Two reasons, and the first is measured:

1. **The known error source here is outliers, not spread.** §4.6's +246%–+282% and §4.9's 170× are
   not gentle noise; they are single readings landing far away. One 60-second outlier moves the mean
   of 9 readings by nearly 7 seconds. It moves the median by nothing. A mean would import exactly the
   contamination this section exists to keep out.
2. **A mean is not a wait anybody experiences.** The median is the wait a person usually gets; the
   95th percentile is the bad day they remember. The arithmetic average of a latency distribution
   corresponds to no actual page load.

**Report, per cell: n, min, median, 95th percentile (only where n ≥ 20), max, stdev.** Dispersion is
not optional — `EXPERIMENTS.md` §2.4 item 8 records that medians alone hid the load sensitivity last
time. A median printed without its spread is an assertion, not a measurement.

### 5.3 Warm-up — and why "warm cache" cannot simply be claimed at 1M

**Current state, verified:** `bench.py:544` warms both paths once and discards the result.
`EXPERIMENTS.md` §2.5 item 7 records that the original document "claimed everything was warm-cache at
every size; that was false at 100,000 and 1,000,000 rows."

**This framing can now say *why*, arithmetically, from a measurement taken today.** The Postgres
**buffer cache** — the server's in-memory copy of recently read pages — is sized by `shared_buffers`,
and the value measured **[2026-08-21]** was `shared_buffers = 128MB`. *(Measured on `glp-strong-db`,
which is **not** the server this run uses — re-read it from `autosql-corpus` per §5.4 item 18. The
arithmetic below does not change: 128MB is the `pgvector/pgvector:pg16` image's default, so the same
number is expected, but "expected" is not "measured" and this section is about exactly that
distinction.)* The 1,000,000-row table is **700 MB** — 419 MB of heap plus 281 MB of GIN index,
predicted by `EXPERIMENTS.md` §2.6 and since **reproduced byte-for-byte on a cold rebuild**
(`REGENERATE-CORPUS.md` §5). **The 1M table is roughly 5.5× larger than the entire buffer cache.**
It is not possible for that table to be warm.
Declaring it warm is not an oversight to be corrected by warming harder; it is arithmetically false
on this server.

> **RULING (mine, not Evan's) — the warm-up policy.**
>
> 1. **Keep one discarded warm-up per arm per size**, as `bench.py:544` already does. It removes
>    first-call effects (connection setup, plan caching, Python import) that nobody is trying to
>    measure.
> 2. **Record the warm-up's own timing instead of throwing it away.** It is the closest thing to a
>    cold reading available and it costs nothing to keep. Label it `warmup_ms`, exclude it from the
>    median.
> 3. **Never claim a cache state. Measure it.** Every cell reports `shared hit` and `read` counts
>    lifted from `EXPLAIN (ANALYZE, BUFFERS)` — §2.5 item 7 requires the numbers; this ruling requires
>    that the *word* "warm" never appear in the write-up unless those numbers support it.
> 4. **State the buffer-cache-to-table-size ratio next to every size**, so a reader can see at a
>    glance that 20,000 rows fits in cache and 1,000,000 rows cannot.
>
> **Derivation.** §2.5 item 7 requires cache state to be *stated*; it does not say how. The measured
> `shared_buffers = 128MB` against a 700 MB table makes "stated" mean "measured per cell", because
> the honest answer differs by size. Cheapest possible reversal: it is reporting, not method — no
> re-run is needed if Evan wants it presented differently.

### 5.4 What the run must record about the host, so a reader can judge the numbers

**Every one of these, in the output JSON, per size, or the cell is not admissible.** The list is
built from what would have been needed to rescue the original sweep and was not there.

| # | recorded | why | value on this host **[measured 2026-08-21]** |
|---|---|---|---|
| 1 | `/proc/loadavg` **before and after each size** | §2.4 item 1 — the largest known error source | `2.71 2.95 2.86` |
| 2 | `nproc`, total and available RAM, free disk | load means nothing without the core count | 20 cores · 46 GB / 32 GB avail · 19 GB free (96% used) |
| 3 | top 3 processes by CPU, at start and end | proves what "quiet" meant, and catches a stray dev server | `node` 200%, `python` 87%, `chrome-headless` 75% |
| 4 | Postgres `server_version` | version-dependent planner behaviour | **16.14** (Debian 16.14-1.pgdg12+1) |
| 5 | **`synchronize_seqscans`** | §2.4 item 9 — the 170× setting | **`on`** |
| 6 | `shared_buffers`, `work_mem`, `max_parallel_workers_per_gather` | decides caching and parallelism | **128MB · 4MB · 2** |
| 7 | `max_parallel_maintenance_workers` | the known 1M-load failure turns on it | **2** — i.e. *reverted*, exactly as §2.6 warned |
| 8 | `extra_float_digits` | the value channel, per Run 1 (T-3) | **1** |
| 9 | container `/dev/shm` size | the `DiskFull` failure mode | **64 MB** — the Docker default, unchanged |
| 10 | wall-clock timestamps, UTC, per cell | lets a later reader line cells up against anything else on the box | — |
| 11 | sha256 of `compile.py`, `runtime.sql`, `gen_data.py`, `bench.py` | so the run can be re-derived; the conformance harness already does this | — |
| 12 | corpus row count, **measured selectivity**, mean stored JSON bytes per row | §2.5 item 6 — both silently move every number | — |
| 13 | `shared hit` / `read` per plan | §2.5 item 7, and §5.3 above | — |
| 14 | the full `EXPLAIN (ANALYZE, BUFFERS)` plan for every compiled arm at every size | §2.5 item 2 — the Q11 index check | — |

**Items 15–18 were missing and are added here.** §5.1 item 3 names the machine the Postgres server
sits on as *the sharpest edge in this run*, and items 1–14 then recorded **nothing whatsoever about
it** — a reader could not have judged contention from this list. The run's database is a **throwaway
container on a host it shares with other containers** (§5.1 item 3), so what has to be recorded is
the state of that **host**, and of everything competing with the run for the same CPU and the same
disk:

| # | recorded | why | value at framing time **[verified 2026-08-21]** |
|---|---|---|---|
| 15 | **Every other container on this Docker host** — `docker ps` plus `docker stats --no-stream` (CPU%, mem) at the **start and end of every size** | the run's Postgres is one tenant among several on one kernel. A neighbour container appears in host `ps` as an anonymous `postgres`/`node` process, so the container list is the only place its identity is legible. Items 1–3 record host totals; this records *who* | `glp-strong-db` (up 5 h, healthy, 55433) and `autosql-doccheck` (55436) were both up |
| 16 | **Whether `glp_strong` was actually being worked during the window** — `numbackends` and `xact_commit` for that database from `pg_stat_database`, read **once before and once after each size**, and nothing else | it is the one neighbour known to carry Evan's real work. Two readings and a delta is the entire record; **a delta of zero commits is the only thing that turns "GIMS was idle" from an assumption into a measurement.** **Read-only, two statements, no load, no write, no `CREATE`** — the run's hard rule is that no procedure points at that container, and this is the single narrow exception, stated so nobody widens it | — |
| 17 | **Disk contention** — free space **and** I/O activity on the filesystem holding the container's volume, before and after each size, plus whether a CSV was being generated onto the same device while a cell was being timed | the corpus, its CSVs, `glp_strong`'s data and the OS all sit on **one 457 GB filesystem at 96% used**. `EXPERIMENTS.md` §2.6 already forces CSVs to be made and dropped one at a time; this is what records whether that was honoured, and it is the contention host `loadavg` is worst at showing | 19 GB free of 457 GB, 96% used |
| 18 | **The run's own container**: name, image digest, published port, `--shm-size`, and the literal `docker run` line used | items 4–9 are settings **of a specific server**, and the server that produced the values in this table is not the server the run will use. Without this a reader cannot tell which cluster any setting belongs to | expected `autosql-corpus` · `pgvector/pgvector:pg16` · `127.0.0.1:55434` · `--shm-size=1g` (`REGENERATE-CORPUS.md` §3) |

> ### Read the "value on this host" column with care — items 4–9 are from the WRONG SERVER
>
> They were measured on **`glp-strong-db`**, because that is where the spike's scratch database lived
> when this framing was drafted. **The run does not use that container** (§5.1 item 3, §7.1) — it
> brings up a fresh `autosql-corpus`. **Every one of items 4–9 must be re-read from that container
> after it comes up and before anything is timed.** Inheriting a server setting from a server you are
> not measuring on is the same class of error as inheriting a load average.
>
> Two of them are already known to differ, and both differences run in the run's favour:
>
> - **Item 9, `/dev/shm`.** `glp-strong-db` still reads **64 MB**, the Docker default — the exact
>   cause of the `DiskFull` abort at the 1M `VACUUM ANALYZE`. The throwaway container is created with
>   **`--shm-size=1g`**, and `REGENERATE-CORPUS.md` §8 records that the full 1,000,000-row load then
>   **completes end to end: `COPY` 11.49 s, GIN 19.91 s, `VACUUM ANALYZE` included, 32.0 s wall, no
>   error.** The failure §3's third stop rule plans around has been fixed at its source. **That stop
>   rule stays anyway** — it costs nothing, and a fix verified once on one container is not a fix
>   verified today on this one.
> - **Item 7, `max_parallel_maintenance_workers`.** On `glp-strong-db` it is back at **2**; it was set
>   to 0 for the original load and reverted afterwards. On a fresh container it is whatever the image
>   ships, and **with 1 GB of `/dev/shm` it does not need touching at all.** Do **not** run the
>   `ALTER SYSTEM` workaround: `REGENERATE-CORPUS.md` §8 flags it as **cluster-wide and persistent**,
>   which is exactly why it is the worse of the two fixes.
>
> **Item 5, `synchronize_seqscans`, carries over unchanged as a requirement.** It reads `on` by
> default and it is the setting that produced a **170× spread on an identical query and table**. Pin
> it and record it — **from the run's own container** — or the run is void under §6 item 9.

### 5.5 One measurement bug to fix before trusting the memory column

`bench.py:547-553` reads `resource.getrusage(RUSAGE_SELF).ru_maxrss` — a **whole-process high-water
mark**, read once. Sizes run in one process in ascending order, so the 1,000,000-row figure carries
the residue of every smaller arm before it. Per `EXPERIMENTS.md` §2.4 item 10: **either one process
per size, or measure per call, or do not report memory at all.** A wrong number is worse than a
missing one; if the fix is not made, delete the column.

---

## 6. What makes the result INADMISSIBLE

> **Inadmissible** means: the run produced a number, but something about how it was produced means
> the number cannot be used to decide anything. It is not "a failing result" — it is *no result*.

Any one of these voids the run, or the affected cell. The four the ticket calls out first:

1. **A LOADED HOST.** Load not recorded, or outside ≤ 2.0 at start / ≤ 4.0 at end (§5.1). *This
   machine reads 2.71 right now and would already void the first cell.* This is the condition
   `FINDINGS.md` §5.7 condition 4 asks for as "quiet host, load recorded", and it is the one the
   original sweep did not meet.
2. **A PARTIALLY-LOADED CORPUS.** Every size must be fully generated, fully loaded, `VACUUM ANALYZE`d
   and **row-counted after loading**. The 1M load has aborted mid-way before (§3), so a table can
   exist and be short. Additionally: **measured selectivity outside 4.5%–6.0%** at any size voids the
   corpus, and the fix is to tune the generator's literal and **regenerate before timing anything —
   never after, and never by tuning until a timing looks good** (`EXPERIMENTS.md` §2.3). Mean stored
   JSON bytes per row must be reported; two new keys move it, and every payload and scan number moves
   with it.
3. **AN INVENTED WIDGET PRESENTED AS A REAL ONE.** See §7.2. The widget is invented and must carry
   that label everywhere it appears, including every table header and chart caption in the readout.
   A latency figure attributed to a widget Evan actually uses, when no such widget was measured, is a
   fabricated result — the most serious failure available to this run.
4. **INDEX HELP SNEAKING IN.** Evan ruled indexes permanently off (**Q11**: *"Not acceptable — index
   work stays off"*), which means the generated query is a **sequential scan** — Postgres reading
   every row in order — every single time. Capture `EXPLAIN (ANALYZE, BUFFERS)` for every compiled arm
   at every size and **assert no index-scan node appears** other than the primary key doing the
   `collection = …` lookup. If a generated query turns out to benefit from an index, its timing is
   inadmissible as evidence about the world Q11 creates. Note the corpus **keeps** the production GIN
   index, because the real `instances` table has one — Q11 does not delete the index from production,
   it means the generated query can never use it, and **the run must demonstrate that rather than
   assume it.**

And, from `EXPERIMENTS.md` §2.5, equally binding:

5. **The widget not verified subset-legal, mechanically, before timing.** Use
   `proto/closure_subset_coverage.py`. If it uses a construct outside the 32-construct subset, the run
   has measured something nobody proposes to build — which is exactly what happened to the *entire*
   existing sweep, whose widget turned on a date function every candidate subset excludes.
6. **The arms not returning the same answer.** Row-for-row identity between arms where Python is
   correct (≤ 20,000 rows), and identity against ground truth computed by an uncapped query above the
   cap. If the arms disagree, the timing comparison is between two different questions.
7. **Fewer repetitions than §5.2 rules, or dispersion not reported.**
8. **Cache state claimed rather than measured** (§5.3).
9. **`synchronize_seqscans` unrecorded** (§5.4 item 5).
10. **A ratio quoted as the verdict.** Ratios are reported; the bar is milliseconds. This is Evan's
    correction and it applies to the write-up as much as to the design.
11. **Anything written into either GIMS checkout.** Both are read-only. `bench.py:20` inserts
    `/home/corgea/Desktop/Coding Projects/GIMS-Project` onto `sys.path` and imports from it, so run it
    with bytecode writing disabled (`PYTHONDONTWRITEBYTECODE=1`) or a `__pycache__` lands in Evan's
    tree.
12. **The void path never shown able to fire.** A harness that has only ever printed "measured" has
    not been shown capable of printing anything else — see the negative control, §6.1 below.
13. **Any real millisecond quoted before the negative control has passed.** Ordering rule, §6.1.
14. **The run's database being `glp-strong-db`, or any table of this run's being created on it.** Not
    a hygiene preference — Q31, and a live database sharing the server (§5.1 item 3, §7.1).

### 6.1 The negative control — required, and required FIRST

> **A negative control is a deliberately broken input, used to prove the rig can report a failure at
> all.** It is not a test of the thing being measured. It is a test of the *instrument*, run before
> the instrument is believed.

**This project has already shipped exactly this mistake, and it stood for four passes.**
`proto/conformance.py` assigns outcomes at four sites. A full normal run under a line tracer showed
**`DID_NOT_COMPILE` hits=0, `SQL_ERROR` hits=0, `COMPILED_DIVERGES` hits=0, `COMPILED_AGREES`
hits=130** (`spikes/T-1/RECHECK-2026-08-21.md` §2.3, lines 141–144 — measured, not inferred). Three of
the four failure branches had **never executed**. Every conformance headline in this project's record
had been produced by a rig whose failure branches were dead surface, and nobody caught it until Evan
asked for the check himself (**Q4**: *"Yes — do that run before I rule"*). When it was finally driven
the branches worked — **dead, not broken** — but that was luck, and nobody could have known which it
was.

**T-4 is open to the same failure in a worse place.** Everything this run reports is a number of
milliseconds. The one thing standing between a dirty-host reading and a quoted headline is the **void
path** — the code that reads `/proc/loadavg`, compares it to §5.1's band, checks the row count,
inspects the plan, and marks the cell **void** rather than **measured**. **If that path never fires,
the run emits a complete, plausible, internally consistent table of timings with no indication
whatsoever that anything was wrong** — which is a description of the original sweep. §11 asks a later
seat to make a void cell *visibly distinct* from a passing one; that is a **display** requirement, and
a display requirement cannot fail. **This is the requirement that can.**

**So, binding:**

- **Before any real millisecond is quoted, the void path is driven deliberately, through the real
  harness** — not a copy of it, not a unit test of a helper function. `proto/conformance_injection_test.py`
  is a working template for this shape: it swaps a handle and asserts on the emitted outcome string
  without modifying the harness. **One injection per admissibility gate, each declaring in advance
  which outcome it must produce:**

  | # | injection | must produce |
  |---|---|---|
  | 1 | a `/proc/loadavg` reading above §5.1's ceiling, **injected — do not load the machine** | **void**, reason `host_load` (§6 item 1) |
  | 2 | a table whose row count is deliberately short of N | **void**, reason `corpus_incomplete` (§6 item 2) |
  | 3 | a plan containing an index-scan node other than the primary-key lookup | **void**, reason `index_help` (§6 item 4) |
  | 4 | one arm's result perturbed by a single row | **void**, reason `arms_disagree` (§6 item 6) |
  | 5 | a size never attempted at all | the **third** outcome, `not-attempted` — distinguishable from both of the others (§4.5, §11) |

- **Each injection must also be shown to be excluded from the statistics.** A cell that prints `void`
  and still contributes to the median is *worse* than one that never voided, because it looks
  handled. Assert that a median computed over a set containing one voided cell is computed from the
  others.
- **If any injection comes back scored as admissible, the run reports nothing.** Not a caveat in the
  write-up, not a footnote under the table. **No output** — and the control failure is what gets
  handed up instead.
- **Ordering rule: no real millisecond may be quoted, in any document, until the control has passed.**
  A control run afterwards is a control that already knows which answer it needs.
- **Cost is not an argument against it.** Five injections on the 1,000-row table, seconds of work,
  against a 2–3 hour exclusive window — and against the alternative, which is a headline nobody can
  stand behind.

**One line from Evan overturns this**, but it is worth being explicit about what he would be
choosing: the project's one previous encounter with an unproven rig cost it every conformance
headline in the record and took a separate dedicated run to uncover.

## 7. Prerequisites — what must exist before the run starts

### 7.1 The corpus must be rebuilt first — and the regeneration notes now EXIST

Evan ruled the scratch tables gone (**Q31**: *"Leave it gone"*, with the note *"leave notes for how to
generate a corpus"*). Both halves of that ruling have since been executed, and the state of the
scratch database changed **after** this section was first drafted. Since three documents in this repo
now tell three different stories about it, here is what actually happened, in order:

1. The spike's original scratch database `autosql_spike` lived on **`glp-strong-db`** — the same
   container as Evan's live `glp_strong`. Q31 ruled it gone.
2. **It was recreated on that same live container earlier today**, by a worker of this session, while
   the regeneration procedure was being verified. So when this framing was first drafted it did
   exist — **7,567 kB, zero tables in `public`, and only the 21 `xpr` runtime functions** — and this
   section called it *"confirmed still gone"*, which it plainly was not.
3. **It was dropped at about 20:55 today.** The driving session confirmed it held no tables and had
   **zero active connections**, then dropped it — to execute Q31 as written, and to get this
   project's benchmark runs off Evan's live container for good.
4. **`glp_strong` was never touched, at any point.** It is **95 MB** and untouched.

**Two consequences, and the second one corrects a claim this section used to make:**

- **This run must rebuild everything** — the database, the `xpr` runtime, and every corpus table —
  into a **new throwaway container**, never onto `glp-strong-db` (§5.1 item 3, §6 item 14).
- **Run 1 (T-3) is not exempt.** This section previously said T-3 *"needs no rebuild at all"* on the
  grounds that the `xpr` functions had survived. **They did not survive** — they went with the
  database. T-3 needs the same container brought up and `runtime.sql` installed; the check is a
  function count of **21** (`REGENERATE-CORPUS.md` §4), and anything else means the install did not
  complete.

> **And for the avoidance of a wrong story: the database is gone because it was deliberately dropped
> to honour Q31 — not because any container was rebuilt or lost.** `glp-strong-db` has been up
> continuously and still is (`docker ps`: **up 5 hours, healthy [verified 2026-08-21]**). Any
> document in this repo explaining the absence by a container rebuild is **wrong about the reason**;
> any document still saying the database exists is **wrong about the fact**.

> ### PREREQUISITE — and it exists: `spikes/T-1/proto/REGENERATE-CORPUS.md`
>
> 35 KB, written 2026-08-21 in the sibling lane to discharge Q31's outstanding note. **Verified on
> disk 2026-08-21.**
>
> **This corrects a hard blocker in the run's very first step.** Every earlier draft of this section
> named the prerequisite **`spikes/T-1/proto/CORPUS-REGEN.md`**. **No file of that name has ever
> existed in this repo** — the notes were still unwritten when this framing guessed at the name, and
> the guess was wrong. A run that opens by checking for its own stated prerequisite would have failed
> that check on a path that never existed, and the natural reading of the failure — *"the notes were
> never written"* — would have been false at the moment it was read. **The file is
> `REGENERATE-CORPUS.md`.** `spikes/T-1/proto/README-db.md` remains the anchor: it is the file that
> points at wherever these notes live.
>
> **The six-point content test, now checked against the document that actually shipped:**
>
> | # | required | present? |
> |---|---|---|
> | 1 | recreate the database and install `runtime.sql` (the 21 `xpr` functions) | **yes** — §3 brings the container up, §4 installs the runtime and verifies the count is **21** |
> | 2 | the generator invocation per size, **seed 1729 preserved** | **yes** — §4, with §1 explaining why the fixed seed is the whole game |
> | 3 | **the two new fields** `queue_depth` and `retest_count` | **yes — as a documented gap, which is the honest answer.** §0 states outright that the scripts do *not* produce them; §7 gives the four-line patch, the selectivity it actually yields (**5.31%** at 100,000 rows, inside the required 4.5–6.0% band), and the warning that **every checksum in the file goes stale the moment it is applied** |
> | 4 | the loader invocation including the **GIN index** flag | **yes** — §4 |
> | 5 | the `/dev/shm` workaround for the 1M `VACUUM ANALYZE` | **yes, and better than a workaround** — §8 replaces it with `--shm-size=1g` at container creation, verified to carry the 1M load end to end, and explains why the `ALTER SYSTEM` route is the worse fix (cluster-wide and persistent) |
> | 6 | post-load verification: row count, measured selectivity, mean stored JSON bytes per row | **yes** — §5 gives per-size row counts, `content_md5`, `xor_sum` and sizes; §7 gives selectivity and **303.2 bytes/row** for the extended corpus, up from 283.0 |
>
> **All six are covered, so the dependency is discharged and this run is not blocked on it.** Three
> things the notes hand the run that the six-point test never asked for, and that change how this
> run's numbers must be read:
>
> 1. **A cold rebuild reproduces the original corpus byte-for-byte.** Heap+index at every size
>    matches `analysis/measurement.md` §3 exactly, **700 MB (419 MB heap + 281 MB GIN)** at 1M
>    included. That is the reproducibility property the investigation's evidence layer was confirmed
>    to have — *"the rig reproduced byte-identically from a cold rebuild after the scratch database
>    had been deleted"* (`.autodev/handoffs/T-1.md`) — re-established after the deletion above.
> 2. **But the corpus THIS run needs is not row-identical to the one the old numbers came from.**
>    Adding the two fields shifts the random stream: measured over 1,000 rows, **only row 0 keeps its
>    old values — 999 of 1,000 rows change.** Same shape, same generator, same distributions,
>    different rows. **So no old absolute number may be quoted as though it had been measured on
>    these exact rows** — including the date-widget control in §7.2, whose entire value is that it is
>    re-measured in-session under a recorded host load.
> 3. **The rebuild is cheap, and its cost is measured rather than guessed:** all six sizes in **under
>    two minutes**, ~824 MiB of database, peak ~1.2 GiB with one CSV on disk at a time.
>
> **If the §7 patch is applied and any of §5's checks then fails, that is this run's problem to close
> before timing anything, and it must be recorded as a deviation.** A corpus nobody can rebuild
> identically makes every number here unreproducible.

Budget — no longer an estimate. `EXPERIMENTS.md` §2.6 predicted roughly **823 MB** of database across
the six sizes; the verified rebuild measured **823.9 MiB**, of which **700 MB** is the 1,000,000-row
table, plus the largest CSV held on disk at once — **342 MiB** (358,818,019 bytes) at 1M. **Peak about
1.2 GiB.** Against **19 GB free of 457 GB, 96% used [measured 2026-08-21]** it fits, but not
comfortably: generate and drop CSVs one size at a time, as `REGENERATE-CORPUS.md` §4 already does.

### 7.2 The widget is INVENTED, and must be labelled invented in the readout

Evan's **Q8** answer was *"I will name a real one I actually use"*. That was **superseded by item 7 of
the second form: "TAKE THE DEFAULT"** — an invented widget, labelled as invented. So:

```json
{ "type": "noun", "noun_type": "Sample",
  "derive": { "load_score": "coalesce($.queue_depth, 0) + coalesce($.retest_count, 0) * 25" },
  "where":  "$.load_score > 195",
  "sort":   { "field": "load_score", "dir": "desc" },
  "limit":  50 }
```

**This is an invented widget. It is not one of Evan's. Every table, chart and sentence in the readout
that reports a number for it must say so.** The rule is not cosmetic: §6 item 3 makes an unlabelled
invented widget an inadmissible result, because a latency figure silently attributed to real usage is
a fabrication regardless of how carefully it was measured.

**If Evan names a real widget before the run starts, it substitutes directly and nothing else in this
framing changes** (`EXPERIMENTS.md` §2.3). The old date widget also runs, as a control — **same
corpus, same session, same recorded host load** — which re-establishes the entire existing sweep
under a *recorded* load for the first time.

**One precision about "same corpus", because it is the control's whole value.** Same *shape*, same
generator, same seed, same distributions — **not the same rows.** Adding `queue_depth` and
`retest_count` shifts the random stream; measured over 1,000 rows, **999 of 1,000 rows change**
(§7.1). The control is therefore a comparison **within this run's session**, against this run's own
Python arm, on this run's rows. **It is not a licence to quote an old absolute figure — 300.10 ms,
8,331.43 ms, ≈16.7 s — as if it had been measured on these rows.** Those older numbers appear in §4.1
as the bar's provenance and as §4.2's kill line; the control exists precisely because they were taken
at an unrecorded host load and need re-taking.

### 7.3 Ticket dependencies

`T-4.depends_on = ["T-1", "T-3"]` (verified in the ticket file). T-1 is the investigation this spec
came out of. T-3 is the correctness run, which Evan put **first** (**Q6**: *"Both, correctness run
first"*) so that a bad correctness result kills the project cheaply before anyone books an exclusive
quiet host. **T-4 does not wait for T-3 to *pass*** — it waits for T-3 to *report*. If T-3 fails, the
timing run has nothing to time and this framing's answer is "do not run".

## 8. Out of scope

- **Correctness.** T-3 owns it. T-4 checks arm identity **only as an admissibility check** (§6 item
  6) — to prove the arms are answering the same question — never as a conformance result.
- **Sort and limit pushdown.** `FINDINGS.md` §5.7 condition 3 keeps them out of the compiled path
  until ten ordering obligations are compiled and tested. Arm **B2** (fully compiled) is **reported,
  not gated**; the bar applies to **arm C**, whose Python sort/limit tail is a real part of what a
  person waits — at 1M with ~5% selectivity roughly 52,000 rows come back to be decoded in Python.
  *A ratio hides that tail; an absolute bar cannot.* That is a concrete reason Evan's correction
  improves the experiment.
- **Index design.** Q11 closed it permanently. Arm **B3** (query rewritten so the GIN index becomes
  usable) is dropped for that reason; its answer was known anyway — across 36 measured query plans
  the production index was used **zero times**.
- **Arm B1** (faithful translation rebuilding the JSON document per row) — 30–36 µs/row of pure
  overhead at every size and slower than B2 everywhere. Question closed.
- **Arm B4** (native Postgres operators) is measured as the physics ceiling — 229.99 ms at 1M — and is
  **not a candidate**: it raises where the language must return null.
- **Anything in GIMS.** No storage migration, no fallback-reporting machinery, no adapter. Both GIMS
  checkouts are read-only. The fallback plumbing is what `FINDINGS.md` calls the hard half, and
  nothing in this run touches it.
- **The UI.** That is T-2.
- **Memory behaviour under concurrency.** Concurrency is measured at 100,000 rows only (1, 3 and 8
  simultaneous resolves), **reported, not gated** — there is no baseline to set a bar against. It is
  confined to 100k on purpose: three concurrent 1M Python resolves would want ~7 GB of heap and become
  a memory experiment rather than a latency one.
- **Deciding whether to build.** This run produces milliseconds. The verdict is Evan's at `sp-decide`.

## 9. Environment — verified on this machine [measured 2026-08-21]

| | |
|---|---|
| **Host** | 20 cores · 46 GB RAM (32 GB available) · 457 GB disk, **19 GB free, 96% used** |
| **Load at framing time** | `2.71 2.95 2.86` at 20:38:49 UTC — **above the run's start ceiling** |
| **The Postgres this run uses** | **does not exist yet — the run creates it.** Throwaway container `autosql-corpus`, `pgvector/pgvector:pg16` (**PostgreSQL 16.14**; image cached locally, 438 MB), **`--shm-size=1g`**, bound to **`127.0.0.1:55434`**, brought up by `REGENERATE-CORPUS.md` §3 and destroyed with its volume by §9 |
| **`glp-strong-db`** | Evan's live container — **up 5 hours, healthy, port 55433 [verified 2026-08-21]**. **The run does not load into it, does not benchmark against it, and creates nothing on it.** One narrow read-only exception: §5.4 item 16's two `pg_stat_database` reads |
| **`autosql_spike`** | **gone.** It was recreated on `glp-strong-db` earlier today by a worker of this session — 7,567 kB, zero tables, 21 `xpr` functions — and **dropped at ~20:55**, with zero active connections, to execute Q31. It is gone because it was dropped, **not** because a container was rebuilt. §7.1 |
| **`glp_strong`** | **95 MB — never touched** at any point today |
| **`xpr` runtime schema** | **gone with the database. It must be reinstalled** from `runtime.sql` and the function count checked to be **21**. This table previously said it survived; it did not |
| **Server settings — measured on `glp-strong-db`, i.e. the WRONG SERVER** | `synchronize_seqscans=on` · `shared_buffers=128MB` · `work_mem=4MB` · `max_parallel_workers_per_gather=2` · `max_parallel_maintenance_workers=2` · `extra_float_digits=1`. **Re-read every one from `autosql-corpus` before timing** — §5.4 |
| **`/dev/shm`** | **64 MB on `glp-strong-db`** — the 1M-load failure mode. The run's own container gets **1 GB**, and the 1M load is verified to complete with it (`REGENERATE-CORPUS.md` §8) |
| **Other containers on this host** | `autosql-doccheck` (55436) was up while this was written. **The host is shared even though the database no longer is** — §5.1 item 3, §5.4 items 15–18 |
| **Credentials** | never in the repo for a real database — `AUTOSQL_SPIKE_DSN` / `PGPASSWORD`, per `proto/README-db.md`. The throwaway container uses a throwaway password on loopback (`REGENERATE-CORPUS.md` §3), which guards nothing and is designed not to |
| **GIMS checkouts** | **read-only.** `bench.py` imports from `GIMS-Project`; run with bytecode writing off |

## 10. Rulings made in this framing, and how to overturn them

Evan is AFK under **GA-5** (`.autodev/events.jsonl` line 53, 2026-08-21T20:36:56Z, covering T-2, T-3,
T-4): *"I'm about to be AFK for a long time. Be as autonomous as possible looping through what we
still have to try and get through all the tickets."* Open questions are therefore **ruled**, from his
recorded answers, rather than handed back. **Each is his to overturn in one line, and none of them
changes what the run measures.**

| # | question | ruling | derived from | reverse cost |
|---|---|---|---|---|
| **R1** | repetitions vs. the p95 the bar asks for (§5.2) | 25 at 20k/100k, 9 at 1M; no column called "p95" below n = 20 | §2.5 item 5's floor of 5 · §2.2's percentile · §2.6's exclusive window as the binding cost · **Q9** "no cap" removing the money objection · `bench.py:508`'s own 9 | one dict literal; re-run only the affected sizes |
| **R1a** | which side of the p95-vs-9-reps contradiction gives way (§4.1) | **the bar gives way, not the repetition count.** At 1M the tail bar is restated as **"worst of 9 — max ≤ 8,331 ms"**; 20k/100k keep a real p95 at n = 25 | §5.2's own measured costs: 145 s per 1M round → 45–70 min at n = 9, but **100–156 min at n = 20** (the minimum n that makes a p95 an interior statistic) against a **2–3 h** total window. Buying the p95 costs the rest of the run | reporting label only, **no re-run** — unless he wants the real p95, which costs a second exclusive window |
| **R2** | how "state the cache state" is satisfied (§5.3) | measure buffer hits/reads per cell; keep the warm-up but record its timing; never write "warm" unmeasured | §2.5 item 7 · the arithmetic of measured `shared_buffers=128MB` vs a 700 MB table | reporting only — no re-run |
| **R2a** | what verdict a run with an untested size produces (§4.5) | a **third** verdict, `INCOMPLETE` — never "pass with a gap", never scored as a fail; and `FAIL` outranks it | §4.1's "every measured size must pass" against §3's explicit permission for a size to go untested; the two were contradictory as written | wording only — no re-run |
| **R3** | the prerequisite file's name (§7.1) | **RESOLVED, not ruled.** The file exists and is `spikes/T-1/proto/REGENERATE-CORPUS.md`; the guessed name `CORPUS-REGEN.md` never existed and every reference to it is corrected. The six-point content test was applied to the real file and **all six points pass** | direct inspection of `spikes/T-1/proto/` **[verified 2026-08-21]** | nothing to reverse — this was a wrong path, not a preference |
| **R5** | whether the void path must be *proved* to fire before real numbers are quoted (§6.1) | **yes — a negative control, run first, five injections, no output at all if any is scored admissible** | the conformance rig shipped four headline passes from a harness whose three failure branches had `hits=0` (`RECHECK-2026-08-21.md` §2.3) · **Q4** *"do that run before I rule"* is Evan's own standing requirement · §11's display rule cannot fail, so it is not a control | one line; the control costs seconds on the 1,000-row table |
| **R4** | T-4's decision authority | assume **`recommend-and-wait`**, as T-1 carries | T-1's ticket has `"decision_authority": "recommend-and-wait"`; **T-4's ticket has no such field** (verified) · GA-5 authorises progress, not deciding for him | one field |

**Where there was genuinely nothing to derive from, this document says so** rather than inventing a
preference: R4 has no recorded answer of Evan's behind it at all, so it takes the option that is
cheapest to reverse — recommending and waiting, which cannot pre-commit him to anything.

**Everything in §4 is Evan's own, or predates this framing.** The unit is his under **GA-3**; the
5,500 ms line is the earlier panel's C-0, set before the evidence existed; the authority for ruling
anything on T-4 while he is away is **GA-5**, which names this ticket. **What was ruled here is R1a
and R2a** — the *shape* of two bars that contradicted other parts of this document, with the numbers
left where they were. And note what §4 no longer claims: earlier drafts cited **GA-4** as §4's
authority, which does not hold — GA-4 is recorded against **T-2 only**, with **`scope_confirmed:
false`**. See the box at the top of §4.

## 11. The risky part, for the next seat

> **"Seat", since it is in the heading and used unglossed below:** the agent working one stage of one
> ticket. The seat that wrote this framing is not the seat that will run the benchmark, and neither
> of them is Evan — which is exactly why everything that matters has to be written down here rather
> than remembered.

**The whole run turns on the host being quiet, and quiet is a state nobody can verify after the
fact.** Every other defect in this design is recoverable: a bar can be redrawn, a widget substituted,
a statistic recomputed, a ratio deleted from a sentence. A cell measured on a busy machine is simply
gone, and — this is the trap — **it does not look gone.** It looks like a number. The original sweep
produced a complete, plausible, internally consistent table of timings whose largest error source was
never written down, and it took a separate re-run at a measured load of 29 to discover that the
numbers moved by +246% to +282%.

So build the harness so that **a cell that was measured on a dirty host is visibly distinct from a
cell that passed** — three outcomes (**measured-and-admissible, measured-and-void, not-attempted**),
never two. Write the load reading into the same JSON object as the milliseconds, so the two cannot be
separated by anyone quoting one of them later. **A harness that records a timing without its host
state reproduces, inside this run, exactly the failure this run exists to correct.**

**And then prove the void outcome can actually be produced. That is §6.1, it is a precondition, and
it is not the same request as the paragraph above.** The paragraph above is a *display* requirement,
and a display requirement cannot fail: a harness with beautifully distinct `void` styling and a void
path that never fires looks, from the outside, exactly like a harness that works. **That is not
hypothetical — it is what this project shipped in its conformance rig, where three of four failure
branches had `hits=0` and four passes went by before anyone checked.** So: **no millisecond from this
run may be quoted, anywhere, until the void path has been driven deliberately and seen to fire.**

**Second risk, and it changed shape while this framing was being written: the host is shared, even
though the database no longer is.** The original arrangement put the spike's scratch database on
`glp-strong-db` beside Evan's live `glp_strong`, competing for the same 128 MB of buffer cache — and
that particular risk is now closed at its source: `autosql_spike` was dropped (§7.1) and the run
brings up its own throwaway container on port **55434** (§5.1 item 3). **What is not closed is the
machine underneath.** `glp-strong-db` is still running, other project containers come and go
(`autosql-doccheck` was up while this was written), and every one of them shares this host's 20
cores, its RAM and its single **96%-full** filesystem. Everything in §5.1's checklist is about
*processes*, and it is natural to run `top`, see a quiet machine, and start — but a busy neighbour
container surfaces there as an anonymous `postgres` process that nobody connects to another project.
**So check the containers, not only the processes** (§5.4 items 15–18), and read `glp_strong`'s
commit count before and after each size, so that "GIMS was idle during the window" is a measurement
rather than an assumption.
