# autosql — CURRENT WORK

Present tense only. Updated at EVERY handoff (see the handoff procedure).
Target size: ~2 pages. The **live edge** — what is in motion right now — is never pruned; the recent
past keeps ~15 items or ~30 days, one line each with the WHY; anything older is dropped here and found
via the reference table below.

**Last rewritten at the 2026-08-21/22 wrap-up, from the ticket files, `.autodev/events.jsonl` and
the files on disk.** The previous version had drifted badly — it described T-2 as still writing its spec, called a
document that exists "not started", and its first bullet had lost its opening line. Every figure below
was re-read from the file it came from.

**Process words used below, in plain terms.** A ticket moves through *stages*. A spike (a
time-boxed investigation, not a build) runs `sp-frame` → `sp-investigate` → `sp-synth` → `sp-decide`
→ `sp-spawn`: frame the question, do the research, write it up, get the human ruling, then turn the
accepted option into build tickets. A feature runs `intake` (turn the request into a scoped ticket)
→ `refine` (write the spec) → `design` → `queue` → build and on. A *gate* is a checkpoint a ticket
cannot pass until a named person signs it — "uncleared" means nobody has signed yet. A *block* is a
deliberate stop recorded on a ticket, with a reason and a remedy. A *modifier* is an optional extra
stage bolted onto the standard pipeline (`design@v1` = add a design stage). A ticket's *passport* is
the running log inside its own ticket file of every move it made and why. A *go-ahead* (GA-*n*) is a
recorded line from Evan authorising a class of decisions, logged verbatim with a timestamp. A *ruling
on delegated authority* is a decision a session took **for** him under one of those — always labelled,
always showing its derivation, always overturnable by one line from him.

## Live edge

<!-- What is in motion right now: one line per active ticket/effort —
     what, why, where it stands, what is next. Never pruned while live. -->

- **T-1** (spike) — *Can the GIMS dashboard expression AST compile to Postgres SQL?* **COMPLETE.**
  Pipeline finished at `sp-spawn`; the `sp_decide` gate was cleared 2026-08-21 under **GA-3** with
  Evan's words on the record. **The ruling: NO-GO on the standalone-compiler-plus-thin-adapter
  architecture as scoped** — not "impossible", not "discard the work", but *"do not fund this on this
  evidence; run the two follow-up experiments first"*. It turns on three facts: `resolve()` in GIMS
  has no field through which a fallback to in-memory evaluation could ever be reported; the compiled
  path is **3.79×–7.15× slower** with no crossover (and Q11 turns index use off permanently, removing
  the only route by which that gap could have closed, so it is a floor); and **18 of 33** ways the two
  engines can disagree cannot be detected at query time by any mechanism. **Next: nothing** — it
  spawned T-3 and T-4, which are the two runs it asked for. Evidence: `spikes/T-1/FINDINGS.md`
  (5,528 lines, sha256 `bcda73d6…`, **verified on disk today**, superseding `33c62975…` and
  `67fbe421…`); `spikes/T-1/.parts/` **re-assembles it byte-identically — re-verified today**, so
  regenerating from the fragments can no longer silently revert the amendment. Read
  `kb/wiki/decision-expr-to-sql.md` for the ruling and `kb/wiki/expr-ast-to-postgres-sql.md` for the
  research (~4,400 words, about ten printed pages, ~15 minutes — not the "two-page summary" older
  handoffs called it). Handoff: `.autodev/handoffs/T-1.md` — **its "What is still open"
  and "Downstream" sections were written before four of the things they describe changed** (the
  amendment, the latency bar, the corpus notes, and T-2's stage); this page and the ticket files are
  the current state.
- **T-2** (feature) — Demo the autoSQL UI end-to-end against a seeded fake-data database — **at
  `uat`, MERGED TO MAIN, WAITING ON EVAN.** The gate is `accept`, policy **`human:strict`** — hardened
  on this ticket 2026-08-22 under his items 35/36, so **on-behalf clearing is refused**; only his own
  `--i-am-human` hand clears it. Acceptance package, with the screen photographed:
  `https://claude.ai/code/artifact/79700309-4e45-45fa-9d4e-998a5f5c51fb`
  **It runs.** `./run-demo up` → own container on 55440 (`lc_collate=C`), offline install from a
  committed wheelhouse (`--no-index`, so AC-32 is proven by the command), **10,410 invented rows**
  (10 EdgeCase / 8,400 Heartbeat / 2,000 Sample), screen on 8787 with **no Node at run time**.
  **Suite on main: 1141 passed, 0 skipped, 2 failed** — both `AC-35`, which is Evan's own uncommitted
  GIMS edits and his call. All 14 walkthrough steps driven as **raw HTTP against the live app**, every
  number matching `expected-answers.json`; **step 11 disagrees exactly as asserted** (SQL `1`, Python
  `1e+300`, key `edge-01`, 1 differing row of 10, flagged), reproduced after a cold start that removed
  the container *and* its volume.
  **Three review rounds: 16 defects → 2 → 0.** Round 1's headline inverted the demo's own signal —
  Postgres sorts a top-level empty jsonb array below everything including null, the spec's ordering
  table omits that exception, so a reachable pick made the disagreement banner fire when the SQL was
  **right** and the Python control **wrong**. Round 2 found that round 1's fix had a guard test that
  **could not see six new instances of what it fixed** — a hand-maintained list of known-bad inputs,
  the same blindness round 1 had flagged in the AC-32 font guard. Both guards were rebuilt
  **generative**, and the sweep immediately found **four crashes the review never listed**. Round 3
  proved the sweeps load-bearing by monkeypatching the old code back in and watching 24 cases go red.
  **THE SCREEN HAS NOW BEEN RENDERED** — a Chromium already in the Playwright cache was used (AC-32
  forbids *fetching* browser automation, not using what is present; nothing was downloaded). Eight
  screenshots in `.autodev/evidence/T-2/`. **What looking found:** at **1440**, the design brief's own
  target width, the `biggest` column — the column the disagreement is *in* — is clipped at the pane
  edge in the SQL pane and off-screen in the Python pane; at 1920 the SQL side appears but the Python
  side is still clipped. The banner promises the disagreement is *"located, not merely announced"* and
  at the target width it is announced but not located. **No number is wrong** — a layout call for his
  acceptance, and exactly what Q27's look sign-off existed to catch.
  **Still open on this ticket, all his:** AC-35; whether the demo should **adopt** T-3's corrected
  runtime (it pins the older 427-line version, so it currently demonstrates behaviour T-3 has since
  proven wrong); and the clipped column. **Plan §8.2's mutation pass has still never run** — 4 of 16
  hand-run and killed, 3 with standing detectors, **9 never watched failing** — now printed as a
  DISCLOSURE above every suite summary. Handoff: `.autodev/handoffs/T-2.md`.
- **T-3** (spike) — *Correctness run: does the restricted expression subset ever return a wrong
  number?* — **at `sp-decide`, COMPLETE through synthesis, WAITING ON EVAN. The answer is NO: it does
  return wrong numbers.** The bar (zero wrong answers at each of `extra_float_digits` 1, 0 and −3,
  reported separately) is **FAILED at all three**, and not by the guard defect — step zero fixed that
  first (297→309 digits, plus a named `XPR01` refusal) and confirmed it was not the cause.
  **Two mechanisms.** (1) **The Unicode-digit gap**, which survives even the setting production would
  pin: `float("１２３")` is 123.0 in Python and `NULL` in SQL, so `coalesce(min($.b), 0.1)` returns
  **0.1** where Python says **123.0**. It **falsifies the framing's own prediction** that restricting
  constructs would drive the batteries to zero — the gap is not in any construct, it is in the shared
  string-to-number routine. (2) **Value-channel truncation** above ≈4.16e9, which at efd −3 makes
  `$.ts + 0` on GIMS's largest stored value return **1,787,169,706,040** instead of **…037**.
  Counts: 39+16 wrong at efd 1, 101+15 at efd 0, 105+16 at efd −3. Class 3 zero, unexplained raises
  zero, NULLNESS zero. Raw mode adds a **class-4**: a ninth, uncatalogued Python raise site.
  **The biggest qualifier, and it is not buried:** the headline mechanism only fires if non-ASCII digit
  strings occur in real data, and **the run did not measure whether they do**. "This can happen" is
  proven; "this will happen to you" is not.
  Evidence: `spikes/T-3/FINDINGS.md` (599 lines) + 29 raw outputs in `spikes/T-3/out/`; the decision
  document is **`spikes/T-3/SYNTHESIS.md`** (406 lines, four options A–D, a labelled recommendation
  with its own weakest point stated), published for him at
  `https://claude.ai/code/artifact/75bc45a2-7601-4334-aa2a-5dd6f7ef3351`.
  **`sp_decide` is UNCLEARED and stays that way** — GA-6 would permit clearing it on-behalf; a failing
  result with four live options is not what a go-ahead is for. Ping delivered to his phone.
  **Evidence integrity:** `spikes/T-1/FINDINGS.md` is untouched (sha256 `bcda73d6…`, matching its
  recorded digest), but T-1's numbers can no longer be reproduced byte-identically from the current
  instruments — that needs a checkout of `01e75b0`. Handoff: `.autodev/handoffs/T-3.md`.
- **T-4** (spike) — *Timing run: how long does a person actually wait, generated SQL vs today's
  Python?* — **at `sp-frame`, framed, and deliberately NOT started today.** `depends_on:
  ["T-1","T-3"]`. Evan's wrap-up item 28 put the correctness run and the demo build on today and left
  the timing run for a booked window, because building the demo is exactly the heavy work that voids
  its numbers. **Two things still gate it, both his:** it needs **this machine to itself for 2–3 hours**
  (item 29, unanswered), and a **real widget name** or the invented one (item 30, unanswered). Its
  three speed bars (350 ms / 1,000 ms / 5,500 ms) remain a proposal he has not accepted. Its corpus
  must be rebuilt into its own throwaway container first. **Worth noting after T-3:** a failed
  correctness run leaves the timing run with less to time — whether T-4 runs at all is now part of the
  `sp-decide` decision, not an automatic next step. Handoff: `.autodev/handoffs/T-4.md`.

## Waiting on

<!-- Holds: "waiting at <gate> on <keyholder> since <date>, ping sent to
     <channel>" — no session should discover a hold by archaeology (ruling 24). -->

**Rewritten 2026-08-22 evening.** Everything the previous version listed here has been answered or
lifted: T-2's design block was cleared by Evan's own look sign-off, and the 38-item wrap-up form is
fully answered — nine by him in session, the other 29 ruled under GA-6 and recorded where each lives.

- **T-3's `sp_decide` gate — the big one.** Waiting on `human:evan` since 2026-08-22, ping delivered
  to Telegram (via the outbox file seam; see the note below on why the automatic path did not fire).
  The correctness run **failed** and he has four options in `spikes/T-3/SYNTHESIS.md`, published at
  `https://claude.ai/code/artifact/75bc45a2-7601-4334-aa2a-5dd6f7ef3351`. **Do not clear this
  on-behalf.** GA-6 would technically permit it; a failing result that decides whether the SQL path is
  funded is his. He clears it with:
  `tracker.mjs approve T-3 sp_decide --by human:evan --i-am-human`
- **T-2's `accept` gate, when it gets there.** Hardened to **`human:strict`** on this ticket on
  2026-08-22 (wrap-up items 35/36, ruled under GA-6), so on-behalf clearing is **refused** — the demo
  physically cannot ship without him. Per-ticket, not shop-wide, because he was never asked 35 or 36.
  The recommendation to make it shop-wide is written in the form for whenever he agrees.
- **AC-35 needs a decision from him.** It asserts `git status --porcelain` is empty in two live GIMS
  checkouts; both carry **his own uncommitted edits from 2026-08-13**, in files T-2 never reads. Both
  trees are read-only to this ticket, so it cannot be resolved from here. Two ways out, both his:
  commit/stash those eight files (wrap-up item 33), or re-scope AC-35 to ignore modifications outside
  the seven files the ticket actually vendors. **A build worker refused to weaken the check to make it
  green, which was right.**
- **Should the demo adopt T-3's corrected runtime?** Open, and genuinely his. The demo currently pins
  `demo/vendor/runtime.sql` at the 427-line version its 45 criteria describe, while the spike tree
  carries T-3's 472-line fix. Adopting the fix would change B15's guard digits, B24's edge-04/edge-05
  pair, AC-13's fifth witness and AC-17's mechanism — four signed criteria — so it was not taken
  unilaterally. One line either way.
- **T-4 needs two things only he can give:** an exclusive quiet 2–3 hour window on this machine
  (item 29), and either a real dashboard widget of his own or acceptance of the invented one, which is
  labelled invented everywhere it appears (item 30). After T-3's failure, whether T-4 runs at all is
  part of the `sp-decide` decision rather than an automatic next step.
- **Two ten-minute jobs at the Windows machine** (item 32), and his stale GIMS checkout (item 33,
  which AC-35 above now depends on).

**A caution for any session that expects to be paged.** The automatic gate ping **does not work**, and
it is not a configuration mistake — see Defect 4 in `.autodev/notes/upstream-bugs.md`. `notify.mjs`
pages on `gate_waiting`; the only producer of that event fires when an advance is *refused* at a gate,
never when a ticket *arrives* at one. `grep -c gate_waiting .autodev/events.jsonl` over this repo's
entire history returns **0**. Worse, for a stage whose work IS the human's decision (`sp-decide`), the
gate check sits *after* the validator check, so it can never fire at all. **Until that is fixed, a
session that parks a ticket at a human gate must write the packet to `.autodev/outbox/` and run
`ops/notify-telegram.sh` by hand** — that is a documented seam, and it is how T-3's ping was delivered.

## Recent past (~15 items / ~30 days)

<!-- One line per completed item, WITH the why. Newest first. Prune from the
     bottom; the permanent record lives in tickets, events.jsonl, and wiki. -->

- **2026-08-22 — T-2 cleared at `queue`, on purpose.** The pipeline had no design gate to stop at, so a — unblocked 2026-08-22: Look sign-off GIVEN by Evan 2026-08-22 under GA-6: wrapup item 3 = 'Approve as drawn'. He opened the mock and approved the design as drawn; the build copies it exactly. This is the block's own stated remedy, satisfied.
  block was recorded in its place rather than inventing a gate or building past him.
- **2026-08-21 — the 38-item wrap-up swept and put to Evan.** Written because roughly 47 decisions had
  been taken on his behalf across seven documents, with no single place to review or reverse them from.
- **2026-08-21 — T-2's design stage ran.** Mock plus brief, seven states, verified in headless Chromium
  at 1440 and 390: no console errors, no horizontal page scroll, all thirteen picker controls reachable
  by Tab.
- **2026-08-21 — T-2's spec signed** against a defined bar (wrong number / won't run / unauthorised
  scope / undetectable) with zero findings — after four of six adversarial reviews refused earlier
  drafts over, among other things, a subset gate that would have refused every comparison in the demo.
- **2026-08-21 — T-3 and T-4 framed**, each fixing its bar before any evidence exists and each
  correcting its own ticket text where the machine disagreed with it.
- **2026-08-21 — `spikes/T-1/proto/REGENERATE-CORPUS.md` written (814 lines)**, discharging Q31's
  outstanding note; T-4 cannot run without it.
- **2026-08-21 — `autosql_spike` dropped from the live container**, zero active connections, to execute
  Q31 as written and get benchmark work off `glp-strong-db` for good. The `xpr` runtime went with it and
  must be reinstalled (function count **21**); `glp_strong` was never touched.
- **2026-08-21 — `FINDINGS.md` amended and re-fingerprinted** on Evan's *"Fix them — re-fingerprint the
  document"*, after a closure seat died mid-pass leaving six corrections unapplied. The two material
  ones are fixed (recursion limits **333 / 333 / 332**, parse depth **63**, both §2.6); the new digest
  `bcda73d6…` is in the `sp-decide` receipt and matches the file today.
- **2026-08-21 — T-3 and T-4 created from T-1's ruling.** No build tickets: the ruling was
  do-not-build-yet, so a build has to be *earned* from these two results.
- **2026-08-21 — T-1's ruling signed (GA-3).** It went backwards first — he ruled, then made it
  conditional on two checks, so it was **stated, not signed** and the ticket returned to
  `sp-investigate` for exactly those two items (`spikes/T-1/RECHECK-2026-08-21.md`).
- **2026-08-21 — the test rig was proven able to report a failure.** Every failure branch in
  `proto/conformance.py` had run **zero** times; fed six deliberately wrong compilations it reported all
  six. **Dead, not broken** — so 130/130 is a real result, and the ruling lost the leg that rested on
  the doubt.
- **2026-08-21 — the evidence trail reconstructed, and two undisclosed holes found.** Everything
  reconciles, but a `+463%` figure cited 11 times rests on an unreproducible measurement and prices at
  **+2.2%** without it — the one thing arguing for CONDITIONAL-GO rather than NO-GO.
- **2026-08-21 — the GIMS checkout question settled with git.** **One repo on two branches**, not two
  repos: `../GIMS-Project` is on `refactor/foundation` @ 995cc59, already merged into `main` and 44
  commits behind, last fetched 2026-06-27. Evan ruled (Q12) that work is authored against `main` in that
  standalone checkout, leaving the GUTS spine alone. **It needs a fetch and a branch change first; it is
  his working copy and no session has touched it.**

## Reference table (where the past lives)

| Looking for... | Where |
| --- | --- |
| Any ticket's full journey | its ticket file (by id/slug) and its handoff in `.autodev/handoffs/` |
| The event-by-event record | `events.jsonl` (append-only, forever) |
| Durable lessons and decisions | `kb/wiki/` |
| What the code looks like now | `kb/CODE-MAP.md` |
| Every question Evan answered, and what each answer caused | `ANSWERS-FROM-EVAN.md` (its "Still outstanding" list is stale: one of the three is done, the other two were ruled on his behalf and are wrap-up items 2 and 8) |
| The open items put to him at the wrap-up | `WRAPUP-FOR-EVAN.md` |
