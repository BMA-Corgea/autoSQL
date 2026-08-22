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
- **T-2** (feature) — Demo the autoSQL UI end-to-end against a seeded fake-data database — build
  **`locate`**, **not blocked**, and **ready for `build`**. Evan gave the look sign-off on 2026-08-22
  under GA-6 (wrap-up item 3, *"Approve as drawn"*), which lifted the block the design stage had put
  where the missing checkpoint should have been. It now runs the **full** process — `.autodev/shop.json
  → settings.lean = false`, set the same day under item 5 (*"Run the rest full"*), so the build gets an
  isolated worktree and a worker per stage. The `locate` and `plan` stages ran as one combo on
  2026-08-22 and produced **`.autodev/specs/T-2-locate.md`** (457 lines — the exact file tree, this
  machine's verified dependency versions, and **eleven gaps neither the spec nor the design settles**)
  and **`.autodev/specs/T-2-plan.md`** (1,486 lines — **all sixteen punch-list items resolved**, the
  query builder's ellipsis-free contract, all 45 acceptance criteria mapped, and **32 rulings on
  delegated authority, B1–B32**). **The four punch-list items that described SQL which would not run
  are fixed before any code exists:** the aggregate re-emits the compiled expression instead of an
  alias (`42703`); operation 9's flag moves into a **CTE** so it can be filtered on (`42P20`);
  operations 7/8/9 are restricted to `noun:Heartbeat`, which is the approved design's own rule X1 (the
  one that ran, produced output and meant nothing); and a **three-shape legality matrix** replaces the
  two rules the design named (`42803`). **Nothing has been built — there is no `demo/` directory.**
  **Next:** the `build` stage, reading plan §1 then §4 then §6. Two places the build will exceed the
  approved drawing (one extra greyed control on the bucketed view; one extra invented-data label per
  answer pane) are named for Evan in the handoff, each one line to overturn. Handoff:
  `.autodev/handoffs/T-2.md`.
- **T-3** (spike) — Correctness run: does the restricted expression subset ever return a wrong numb… — sp-investigate
  number?* At `sp-frame`, **framed and NOT blocked**, and it can start whenever. `spikes/T-3/FRAMING.md`
  fixes the bar at **zero wrong answers of any kind, at each of `extra_float_digits` = 1, 0 and −3,
  reported separately** (pooling the three is forbidden). **Next:** `sp-investigate` — the run itself,
  which opens with a 24-character guard-literal fix at `proto/runtime.sql:33` and `:51`, then a
  negative control on `differ.py` that must pass **before any real number is quoted anywhere**.
  Ignore the ticket file's "BLOCKED ON EVAN" line: it was written 17 minutes before GA-4 answered it.
  Handoff: `.autodev/handoffs/T-3.md`.
- **T-4** (spike) — *Timing run: how long does a person actually wait, generated SQL vs today's
  Python?* At `sp-frame`, **framed**, `depends_on: ["T-1","T-3"]` — it waits for T-3 to **report**, not
  to pass. `spikes/T-4/FRAMING.md` sets the unit as **milliseconds a person waits, never a ratio**
  (Evan's own words under GA-3). **Two things gate it:** it needs **this machine to itself for 2–3
  hours**, and its three speed bars (350 ms at 20 000 rows, 1 000 ms at 100 000, 5 500 ms at
  1 000 000) are a **proposal he has not accepted** — the number is his. Its corpus must be rebuilt
  first, into its own throwaway container, from `spikes/T-1/proto/REGENERATE-CORPUS.md`. **Next:**
  Evan names a window; then `sp-investigate`. Handoff: `.autodev/handoffs/T-4.md`.

## Waiting on

<!-- Holds: "waiting at <gate> on <keyholder> since <date>, ping sent to
     <channel>" — no session should discover a hold by archaeology (ruling 24). -->

  his Q27 asked for *"a design stage and a look sign-off"*. The `design` modifier gave T-2 a design
  **stage**, and that stage ran — but `.autodev/data/gates-policy.json` defines seven gates and
  **none of them is `design`**, so there was no checkpoint for the sign-off to happen at and the
  ticket flowed straight to `queue` under GA-5 (his AFK note, *not* approval of the screen). **A block
  was put where the missing gate should have been**, so the next session told to keep going does not
  build a UI he has never seen. **What clears it**, from the ticket's own remedy field: *"Evan looks at
  the artifact and says go, or says what to change. Then: `tracker.mjs unblock T-2 --by <actor>`."*
  Do not clear it without him.
- **The wrap-up form is the single biggest thing waiting on him.** `WRAPUP-FOR-EVAN.md` at the repo
  root, and the same thing as a fillable form at
  `https://claude.ai/code/artifact/c883d912-d130-4e44-b156-e63e5d539754`. **38 items; 5 marked
  blocking.** Most are decisions taken on his behalf while he was away, each derived from something he
  already said and each one line to overturn. **Item 1 is the one to answer first: go-ahead GA-4 was
  logged against T-2 only, with `scope_confirmed: false`, and was then used as the authority for
  rulings on T-1 and T-3 as well — about twenty-one decisions rest on how far he meant one sentence to
  reach.** If he meant the T-2 spec only, three rulings revert to open: the tick-vs-note reading, the
  loud-refusal rule in T-3, and T-4's speed targets. Nothing would need re-running.
- **T-4 needs two things only he can give:** an exclusive quiet 2–3 hour window on this machine
  (wrap-up item 29), and either a real dashboard widget of his own or acceptance of the invented one,
  which is labelled invented everywhere it appears (item 30). Building T-2's demo is exactly the kind
  of work that voids T-4's measurements, so the two cannot share an afternoon here and nobody has
  decided the order (item 28).
- **Last night's work is uncommitted and exists on this Linux machine only** (wrap-up item 6): the
  spec folder move from `specs/` to `.autodev/specs/` — which changes the path other documents cite —
  the T-2 advance and cleared, the design receipt and brief edits, the punch list, and three record — unblocked 2026-08-22: Look sign-off GIVEN by Evan 2026-08-22 under GA-6: wrapup item 3 = 'Approve as drawn'. He opened the mock and approved the design as drawn; the build copies it exactly. This is the block's own stated remedy, satisfied.
  files. Nothing is lost, but it is invisible to the Windows machine and one reset from gone. **No
  session has committed it; that decision is his.**
- **Nothing else is a hold.** T-1's gate is cleared, T-3 is genuinely unblocked, and the two items
  this page used to list as open — re-fingerprinting `FINDINGS.md`, and Q31's corpus-regeneration
  notes — are both **done** (see below).

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
