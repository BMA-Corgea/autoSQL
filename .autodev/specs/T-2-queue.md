# T-2 · queue — ordering against all other work

**Decided 2026-08-22 by** `agent:claude(on-behalf:evan,GA-6)` · **authority:** Evan's wrap-up
item 28 answer, *"Correctness run alongside the demo, timing run alone later."*

## The ordering

| # | Ticket | Runs | Why here |
| --- | --- | --- | --- |
| 1 | **T-2** (this ticket) | **today, in parallel with T-3** | Evan approved the look (item 3, "Approve as drawn"), which lifted its block. It is the only ticket in a build pipeline and the only one that produces something he can look at tonight. |
| 1= | **T-3** correctness run | **today, in parallel with T-2** | Does not need an idle machine, so it costs T-2 nothing to run beside it. It is also the ticket T-1's ruling asked for first. |
| 3 | **T-4** timing run | **NOT today — waits for a window Evan names** | Its own rules require an otherwise-idle machine; building T-2 is exactly the heavy work that voids its numbers. Sequenced behind T-3 by the tracker regardless. Open item 29 is the window; open item 30 is the widget. |

## Ready-for-agent

T-2 is **ready**. Its inputs are all on disk and none are open questions:

- spec — `.autodev/specs/T-2.md` (signed at `spec_ready`, GA-4, scope now confirmed by GA-6)
- punch list — `.autodev/specs/T-2-punchlist.md` (16 items; the builder rules each and records how, per item 26's stated default)
- visual target — `design/t2-demo-mock.html` + `design/t2-demo.md` (**approved as drawn** by Evan, 2026-08-22, item 3)
- process — **FULL**, not lean: `.autodev/shop.json` `settings.lean` = false (item 5). Isolated worktree, deep locate/plan, a worker per stage.

## What this ticket must NOT do

Nothing here touches GIMS. Evan's item 2 answer fixes the reading: the "don't build yet" tick
governs GIMS, and nothing enters it until T-3 and T-4 pass. This ticket is the fake-data demo he
green-lit separately, and it runs against a seeded throwaway database only.
