# autosql — CURRENT WORK

Present tense only. Updated at EVERY handoff (see the handoff procedure).
Target size: ~2 pages. The live edge is never pruned; the recent past keeps
~15 items or ~30 days, one line each with the WHY; anything older is dropped
here and found via the reference table below.

## Live edge

<!-- What is in motion right now: one line per active ticket/effort —
     what, why, where it stands, what is next. Never pruned while live. -->
- **T-1** (spike) — Compile the GIMS dashboard expression AST to Postgres SQL — **sp-investigate**.
  sp-frame passed 2026-08-19 (`spikes/T-1/FRAMING.md` @ 562c4da, branch `spike/T-1-expr-sql`); it set
  the go/no-go bar in advance and corrected three of the ticket's own file references. Investigation
  is running as the STORM panel the stage prescribes: 5 recon researchers → throwaway AST→SQL compiler
  + 3-outcome conformance harness against live PG16 → conformance/index/measurement analysis → 3
  adversarial lenses on the harness itself → `spikes/T-1/FINDINGS.md`. Next: `sp-synth`, then it holds
  at `sp_decide` for Evan.


## Waiting on

<!-- Holds: "waiting at <gate> on <keyholder> since <date>, ping sent to
     <channel>" — no session should discover a hold by archaeology (ruling 24). -->

- Nothing at a gate yet. T-1 will hold at `sp_decide` for `human:evan` when its findings land.
- RESOLVED 2026-08-19 (was: no local GIMS checkout). Both trees are on this Linux machine and
  the Windows MAX_PATH concern is moot. **Two trees, and they are not interchangeable:**
  `GIMS-Project` @ 995cc59 has the expression stack; `GUTS/spine/L1-memory/gims-ledger` @ 7b7a049
  has the SAME expression stack byte-for-byte PLUS the Postgres layer (`migrations/pg/`,
  `list_records_where`, the RAG pushdown profile) that `GIMS-Project` lacks entirely. Every
  storage-layer file the T-1 spec names resolves only in gims-ledger. See `spikes/T-1/FRAMING.md` §2.

## Recent past (~15 items / ~30 days)

<!-- One line per completed item, WITH the why. Newest first. Prune from the
     bottom; the permanent record lives in tickets, events.jsonl, and wiki. -->

- (nothing completed yet)

## Reference table (where the past lives)

| Looking for... | Where |
| --- | --- |
| Any ticket's full journey | its ticket file (by id/slug) and its handoff in `.autodev/handoffs/` |
| The event-by-event record | `events.jsonl` (append-only, forever) |
| Durable lessons and decisions | `kb/wiki/` |
| What the code looks like now | `kb/CODE-MAP.md` |
