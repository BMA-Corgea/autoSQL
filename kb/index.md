# autosql KB Index
<!-- autodev-kb-index -->

Read this file first. Pick the smallest set of pages you need, then follow
links only as far as the task requires — don't load the whole `wiki/` tree.
How a KB works (wiki vs NOW vs operator, reference-table shape, history-
never-deleted) is plugin doctrine — see `skills/autodev/instructions/README.md`.

## Pointer table

| Looking for... | Page | Summary |
| --- | --- | --- |
| What is being worked RIGHT NOW | [CURRENT-WORK.md](CURRENT-WORK.md) | The live edge + recent past; updated at every handoff |
| What happened, day by day | [days/](days/) | Movements generated from the event log + session summaries |
| Why autoSQL exists and how it plugs into GIMS | [wiki/autosql-architecture.md](wiki/autosql-architecture.md) | The design: one spec, one compiler, two renderers; Postgres query plane; known risks |
| **What was DECIDED about compiling expressions to SQL, and why** | [wiki/decision-expr-to-sql.md](wiki/decision-expr-to-sql.md) | The signed ruling (Evan, 2026-08-21): don't build the compiler-plus-adapter as scoped yet; fund a correctness battery and a speed run first. The three facts it turns on, the argument it lost, and the one part still open |
| **What was DECIDED about the correctness run, and what happens next** | [wiki/decision-t3-correctness-run.md](wiki/decision-t3-correctness-run.md) | Evan's ruling (2026-08-23): *homework first, then fix-and-re-run*. The subset DOES return wrong numbers — the two mechanisms, why this option over the other three, what it does not settle, and the stated trigger to revisit it |
| **What was DECIDED once the homework reported, and what it released** | [wiki/decision-t5-homework.md](wiki/decision-t5-homework.md) | Evan's ruling (2026-09-01, GA-9): *proceed as ruled*. Band ZERO — the trigger that would have overturned T-3 did not fire — but the old denominator overstated it ~7,600x and GIMS's import path admits the trigger by design. All six answers, why C and D were rejected, and what it released |
| **Can autoSQL trust a declared field type? (T-7)** | [wiki/declared-types-are-not-a-guarantee.md](wiki/declared-types-are-not-a-guarantee.md) | No. Six of seven GIMS write paths never check the schema, and a `float` field holds "lmao im a changling" -- with the schema proven unchanged since three months before those rows. Makes T-1's H3 index hazard concrete with a second independent witness |
| **Did the re-run pass, and what the fix actually cost (T-6)** | [wiki/decision-t6-correctness-rerun.md](wiki/decision-t6-correctness-rerun.md) | PASS at the pinned setting -- 0 wrong numbers over 11,367 expressions, fixture 130/130. But the ruled refusal costs 60 correct answers to fix 26 wrong ones, and T-3's premise that SQL "cannot cheaply match Python" is false: one translate() does it, guarded, for no measurable cost. Variant C adopted under GA-10, flagged as a deviation |
| **Do non-ASCII digit strings actually occur in the real data? (T-5 homework)** | [wiki/nonascii-digits-in-real-data.md](wiki/nonascii-digits-in-real-data.md) | The homework T-3 ordered: options + recommendation, awaiting Evan at `sp-decide`. Stored data is clean (0 of 144 coercible strings, four agreeing instruments) — but the headline denominator was ~7,600x too big, and GIMS's own CSV import path admits 8 of 10 non-ASCII digit forms into number-declared fields |
| Can the GIMS expression AST compile to Postgres SQL? (T-1 spike) | [wiki/expr-ast-to-postgres-sql.md](wiki/expr-ast-to-postgres-sql.md) | The research behind that decision: options + recommendation — demonstrable but slower, and no fallback is reportable |
| The raw working material behind a spike | [../spikes/](../spikes/) | One folder per spike ticket: `FRAMING.md`, `recon/`, `analysis/`, `proto/`, `FINDINGS.md`. The wiki pages above are the distilled answers; this is what they were distilled from |

## Layout

- `kb/index.md` — this file, the pointer table (always read first)
- `kb/CURRENT-WORK.md` — the NOW layer: state of play, updated every handoff
- `kb/CODE-MAP.md` — the living code map (regenerated, never hand-edited)
- `kb/wiki/` — regenerable, LLM-maintained knowledge pages. kebab-case filenames, linked from this index.
- `kb/operator/` — the operator model: decision style, communication style, approval patterns, handoff phrasing.

## Where the past lives

Nothing is deleted; older knowledge is pointed at where it lies.

| Looking for... | Where |
| --- | --- |
| A ticket's full journey | its ticket file and `.autodev/handoffs/` |
| The event-by-event record | `events.jsonl` (append-only, forever) |
| Anything pruned from CURRENT-WORK's recent-past window | this table's other rows, plus git history |
| What has gone wrong before (and the rule each time taught) | [wiki/lessons.md](wiki/lessons.md) | Value-bearing lessons page; grown by retros, read by planners |
| The pre-flight discipline for risky changes | [wiki/hardening-checklist.md](wiki/hardening-checklist.md) | Hardening checklist; consulted before touching load-bearing paths |
