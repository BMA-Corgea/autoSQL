# autosql — CURRENT WORK

Present tense only. Updated at EVERY handoff (see the handoff procedure).
Target size: ~2 pages. The **live edge** — what is in motion right now — is never pruned; the recent
past keeps ~15 items or ~30 days, one line each with the WHY; anything older is dropped here and found
via the reference table below.

**Process words used below, in plain terms.** A ticket moves through *stages*. A spike (a
time-boxed investigation, not a build) runs `sp-frame` → `sp-investigate` → `sp-synth` → `sp-decide`
→ `sp-spawn`: frame the question, do the research, write it up, get the human ruling, then turn the
accepted option into build tickets. A feature runs `intake` (turn the request into a scoped ticket)
→ `refine` (write the spec) → `design` → build and on. A *gate* is a checkpoint a ticket cannot pass
until a named person signs it — "uncleared" means nobody has signed yet. A *modifier* is an optional
extra stage bolted onto the standard pipeline (`design@v1` = add a design stage). A ticket's
*passport* is the running log inside its own ticket file of every move it made and why.

## Live edge

<!-- What is in motion right now: one line per active ticket/effort —
     what, why, where it stands, what is next. Never pruned while live. -->
  cleared 2026-08-21**
  **Ruled. Evan decided NO-GO: don't build yet, fund the two follow-up runs** — recorded as go-ahead
  **GA-3** in `.autodev/events.jsonl` with his words verbatim. It went backwards first: he ruled on
  2026-08-21 but made it conditional on two checks (Q4: prove the test rig can report a failure; Q5:
  reconstruct the missing reports), so the ruling was **stated, not signed** and the `sp_decide` gate
  stayed uncleared. T-1 returned to `sp-investigate` for exactly those two items, both came back done
  (`spikes/T-1/RECHECK-2026-08-21.md`), and he then signed. **The ruling:** NO-GO on the
  standalone-compiler-plus-thin-adapter architecture as scoped — not "impossible" (all 130 fixture
  cases agree exactly, with no case needing the 1e-9 tolerance) and not "discard the work", but "do
  not fund this on this evidence; run E1 and E2 first". It turns on three facts, none of which the
  re-check touched: `resolve()` has no field through which a fallback could be reported; the compiled
  path is 3.79×–7.15× slower with no crossover (and Q11 turns index use off permanently, removing the
  only route by which that could ever have closed); and 18 of 33 divergence classes are undetectable
  at query time, with the CONDITIONAL-GO subset covering only 68/130 (52.3%). What the re-check moved:
  the rig is **proven able to report a failure**, so 130/130 is a credible fact — which *removes* the
  stated ground for calling the fixture-adequacy leg "firmer"; and it found two holes `FINDINGS.md`
  did not disclose (a closure seat — one reviewing agent — died mid-pass, leaving 6 verification
  corrections unapplied, 2 of them wrong in the published text; and `+463%`, cited 11 times, rests
  on an unreproducible number that prices at +2.2% without it). **Both wrong numbers are now fixed**:
  Evan authorised the amendment (GA-3, "Fix them — re-fingerprint the document"), it ran on
  2026-08-21, and the three remaining corrections are cosmetic and named in the closure log.
  Evidence: `spikes/T-1/FINDINGS.md` (5,528 lines, sha256
  `bcda73d6…` — superseding `33c62975…` and, before that, `67fbe421…`; the `.parts/` fragment tree
  now rebuilds it byte-identically, so regenerating it can no longer silently revert the amendment)
  + `RECHECK-2026-08-21.md`; the decision page
  `kb/wiki/expr-ast-to-postgres-sql.md` carries all of it (~4,400 words, about ten printed pages, ~15
  minutes — not the "two-page summary" earlier handoffs called it). **Next:** `sp-spawn` turns the
  ruling into build tickets for **E1** (the subset acceptance battery) and **E2** (the like-for-like
  speed run), correctness run first per Q6.
- **T-2** (feature) — Demo the autoSQL UI end-to-end against a seeded fake-data database — `refine`
  **Unblocked and moving.** Out of `intake` since 2026-08-21 on Evan's scope answers, with a **design
  stage added** (modifier `design@v1`, his Q27: he approves the look before the demo UI is built rather
  than first seeing it at accept). Now at `refine` writing the spec; the `spec_ready` gate is uncleared
  — nobody has approved the spec yet — and **his approval of it is the next thing waiting on him**.
  Q3 puts this demo *before* any GIMS contract change, and now that T-1's gate is cleared it is no
  longer held behind that decision either — that is a consequence of the ruling, not a standing fact,
  and Q18 sets the limit it releases under: *"Green light, but only the safe operations."* Its
  SQL-generation layer is still what the T-1 ruling governs, so the ticket gets re-read against the
  ruling as the spec is written.
- **T-3** (spike) — Correctness run: does the restricted expression subset ever return a wrong numb… — sp-frame
- **T-4** (spike) — Timing run: how long does a person actually wait, generated SQL vs today's Pyth… — sp-frame

## Waiting on

<!-- Holds: "waiting at <gate> on <keyholder> since <date>, ping sent to
     <channel>" — no session should discover a hold by archaeology (ruling 24). -->

- **RESOLVED 2026-08-21** (was: T-1 waiting at `sp_decide` on `human:evan` since 2026-08-19). He
  ruled — GA-3, gate cleared. Four things it left genuinely open, none of them blocking `sp-spawn`
  from planning the two runs:
  - **CLOSED 2026-08-21 — the tick and the note point at different options.** He delegated the call
    (GA-4: *"I feel like these questions can be answered with your best judgement"*), so it is recorded
    as a **ruling on delegated authority**, not his decision: **the tick governs the GIMS integration**
    (nothing built against GIMS until the two runs earn it), **the note describes the demo**, which he
    already authorised himself under Q18/Q19/Q24. Derivation in `kb/wiki/decision-expr-to-sql.md` §6.
    He overturns it in one line.
  - **CLOSED 2026-08-21 — E2's absolute latency bar.** Also a **ruling on delegated authority**:
    **three bars, one per collection size**, because what a person will wait for depends on how big a
    question they asked — **350 ms at 20 000 rows, 1 000 ms at 100 000, 5 500 ms at 1 000 000** — plus a
    kill condition that the compiled path must beat the in-memory path measured in the same session
    (8 331 ms at 1M). Every number derived from a measurement, in `spikes/T-1/EXPERIMENTS.md` §2.2.
  - **NEW, and it belongs to the correctness run** — a third **ruling on delegated authority**
    (`EXPERIMENTS.md` §1.2): expressions that can exceed the largest representable double become a
    **reported runtime refusal** — the SQL refuses loudly instead of returning a number — so the pass
    bar stays at **zero wrong answers**. If that detection cannot be built, it is a named carve-out and
    the correctness run **FAILS**.
  - **Q31's corpus-regeneration notes are not written.** He said *"leave notes for how to generate a
    corpus"* when the 1 000-to-1 000 000-row test tables were deleted. Not started, and E2 needs them.
  - **DONE 2026-08-21 — the two material errors in `FINDINGS.md` are corrected.** He decided this one:
    follow-up item 2, *"Fix them — re-fingerprint the document."* Both were applied under go-ahead
    `GA-3` and are verified in the current file: recursion limits now **333 / 333 / 332**
    (`FINDINGS.md:1151`, §2.6; cited as `:1124` against the pre-amendment file) and parse depth now
    **63** (`FINDINGS.md:1184-1185`, §2.6; cited as `:1143-1144` before). **Re-fingerprinting is the
    open half.** Amending changed the file's sha256 — the fingerprint `.autodev/events.jsonl` recorded
    as the `sp-investigate` evidence — and it has since changed *again*: a parts-reconciliation pass
    added two further `[amend-2026-08-21]` scope notes on 2026-08-21, so the digest quoted in the
    amendment entry (`33c6297…`) no longer matches either. Whatever digest gets recorded has to be
    taken after the last writer stops. **Until then, treat every absolute `FINDINGS.md:NNNN` in the KB
    as provisional and confirm by section number.**
- **T-2 is waiting on Evan's spec approval** (`spec_ready`, uncleared) once `refine` produces the spec.
  Q20 is answered — *"That, plus time buckets and rolling windows"* — so the spec has what it needs.
  Note a record gap now closed: T-2's intake receipt cites "scope decisions Q18–Q27 recorded in
  `ANSWERS-FROM-EVAN.md`" and that file was, at the time, twenty minutes stale and still listed Q18 as
  open. It has since been rewritten and now holds all 46 first-round answers and all 12 follow-ups,
  each with what it caused, so the receipt resolves correctly today.
- **RESOLVED 2026-08-19** (was: no local GIMS checkout). Both working trees are on this Linux machine and
  the Windows MAX_PATH concern is moot. **Correction, verified with git on 2026-08-21: they are not two
  repos. They are ONE repo on two branches of the same remote**
  (`https://github.com/BMA-Corgea/GIMS-Project.git` — the standalone tree calls that remote
  `gims-project-upstream`, the ledger tree calls it `origin`).
  - `../GIMS-Project` sits on **`refactor/foundation` @ 995cc59** (committed 2026-07-03). That commit is
    **already merged into `main` and 44 commits behind it** — `git rev-list --left-right --count
    995cc59...main` returns `0  44`, run in the up-to-date tree, whose `main` is 7b7a049 (2026-08-10).
  - The standalone checkout cannot see that itself: it **last fetched 2026-06-27 10:28**, its own `main` is
    still ec1dd76 (2026-01-22), and from inside it `refactor/foundation` looks 311 commits *ahead* and
    unmerged. That is a stale fetch, not a disagreement about history.
  - The content difference that made the two trees look non-interchangeable is that staleness: the
    Postgres layer (`migrations/pg/0001_instances.sql`, `0002_instances_data_gin.sql`, `list_records_where`,
    the RAG pushdown profile) is on `main`, so it is present in `GUTS/spine/L1-memory/gims-ledger` @ 7b7a049
    and absent from `../GIMS-Project`'s working tree at 995cc59. Every storage-layer file the T-1 spec names
    resolves only in the ledger tree today. See `spikes/T-1/FRAMING.md` §2.
  - **Evan ruled (Q12): work is authored against `main`, in the standalone `GIMS-Project` checkout, leaving
    the GUTS spine untouched** — verbatim, *"the last thing the already fragile and ephemeral GUTS spine
    needs right now is more changes"*. So that checkout needs a fetch and a branch change before anything is
    written against it. **Not done — it is his working copy and no session has touched it.**

## Recent past (~15 items / ~30 days)

<!-- One line per completed item, WITH the why. Newest first. Prune from the
     bottom; the permanent record lives in tickets, events.jsonl, and wiki. -->

- 2026-08-21 **T-1 COMPLETE** — Compile the GIMS dashboard expression AST to Postgres SQL
- **2026-08-21 — T-1's ruling signed (GA-3).** NO-GO on the compiler-plus-adapter architecture; fund
  E1 and E2 instead. The `sp_decide` gate is cleared and T-1's research phase is finished.

## Reference table (where the past lives)

| Looking for... | Where |
| --- | --- |
| Any ticket's full journey | its ticket file (by id/slug) and its handoff in `.autodev/handoffs/` |
| The event-by-event record | `events.jsonl` (append-only, forever) |
| Durable lessons and decisions | `kb/wiki/` |
| What the code looks like now | `kb/CODE-MAP.md` |
