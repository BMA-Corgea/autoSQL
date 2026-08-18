# autosql — CURRENT WORK

Present tense only. Updated at EVERY handoff (see the handoff procedure).
Target size: ~2 pages. The live edge is never pruned; the recent past keeps
~15 items or ~30 days, one line each with the WHY; anything older is dropped
here and found via the reference table below.

## Live edge

<!-- What is in motion right now: one line per active ticket/effort —
     what, why, where it stands, what is next. Never pruned while live. -->
- **T-1** (spike) — Compile the GIMS dashboard expression AST to Postgres SQL — sp-frame


## Waiting on

<!-- Holds: "waiting at <gate> on <keyholder> since <date>, ping sent to
     <channel>" — no session should discover a hold by archaeology (ruling 24). -->

- Nothing at a gate yet. T-1 will hold at `sp_decide` for `human:evan` when its findings land.
- OPEN, not blocking: GIMS-Project and GUTS are readable over git but not cloned into this
  workspace (a sparse copy lives in the session scratchpad only). The spike needs a durable
  local GIMS checkout — `git config core.longpaths true` and a sparse-checkout excluding
  `/projects`, or the sample data blows past Windows MAX_PATH.

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
