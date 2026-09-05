# autoSQL — Evan's decisions · 21 Aug 2026

Every answer he has given, verbatim, with what each one caused. Two rounds:
the 46-question form (`QUESTIONS-FOR-EVAN.md`) and the 12-item follow-up (`WAITING-ON-EVAN.md`).

**All 46 answered. All 12 answered.** Go-aheads on the record: GA-1 (T-1), GA-2 (T-2), GA-3 (T-1 ruling).

---

# Round one — the 46

## The ruling

**Q1.** Do you accept "don't build it yet", take the restricted build, send the research back, or fund the full build anyway?

→ **Don't build yet; fund the two experiments**

> Re-confirmed 2026-08-21 (GA-3): "Stands — don't build yet. Continue. Do not ship the prototype as a universal replacement for Python. Build the bounded SQL path with explicit fallback, instrument which path ran, and run the dedicated subset acceptance tests before treating that subset as production-safe. Benchmark absolute user-facing latency rather than treating a 3.79×–7.15× relative slowdown as intrinsically fatal." NOTE: the tick and the note point at different options; acting on the tick, treating the note as (a) the shape any eventual build must take and (b) a re-specification of the speed run's bar. Flagged to him for correction.

**Q2.** Is that 130-case test file an adequate acceptance test for a third, SQL version of this expression language?

→ **Not good enough — build a real one**

**Q3.** Can GIMS itself change — can that function return extra fields saying what ran in the database and what fell back, and can the widget UI carry its own label for it?

→ **Yes, but only after the demo**

**Q4.** Do you want one run that proves the test rig can actually report a failure, before you rule?

→ **Yes — do that run before I rule**

> DONE 2026-08-21. The rig emits diverges / did-not-compile / SQL-error correctly when driven. Branches were dead, not broken.

**Q5.** Do you accept the evidence trail as it stands, or do you want the missing pieces reconstructed before you rule?

→ **Reconstruct the missing reports first**

> DONE 2026-08-21. Registers reconcile; every retained measurement re-derived exactly. Two undisclosed holes found. The reconstruction's own report was judged OVERSTATED in three places.

## The two experiments

**Q6.** Do you pay for both follow-up runs, and do you want the speed run first so a bad result can kill the project cheaply?

→ **Both, correctness run first**

> Confirmed again as item 6 of the second form, resolving the conflict with Q9.

**Q7.** Do you let the follow-up runs edit the throwaway code and test generators the research left behind, or must those tools be rebuilt from scratch?

→ **Let them edit the existing code in place**

**Q8.** Will you name a real widget or expression the SQL version could actually handle, or should the speed run use an invented one?

→ **I will name a real one I actually use**

> SUPERSEDED by item 7 of the second form — default taken, an invented widget labelled as invented.

**Q9.** How much do you want to spend on the two follow-up runs, and should cost logging be switched on before they start?

→ **Fund only the speed run, no cap**

> CONFLICTED with Q6 and Q10. Resolved by item 6 of the second form: Q6 governs, both runs, correctness first; "no cap" applies to the speed run's budget.

**Q10.** Do you accept, as a permanent rule, that every query autoSQL generates must pin that Postgres digit setting, and that none of these SQL helper functions may ever appear inside a database index?

→ **Make the correctness run test all three settings**

**Q11.** If you go with the limited version, do you accept the compiler writing tenant-supplied field names straight into the SQL text?

→ **Not acceptable — index work stays off**

> Consequence: generated queries can never use a database index. The measured 3.79×–7.15× gap is now a floor, not a starting point.

## What integration actually means

**Q12.** Which branch of the GIMS repo should autoSQL's changes be written against?

→ **main, where the newer checkout already sits**

> His words: "This addition is specifically for the one that isn't in the GUTS spine. I recognize that it will have to be reconciled expensively later, but the last thing the already fragile and ephemeral GUTS spine needs right now is more changes." The standalone checkout must be fetched first — its own main is still at ec1dd76 (2026-01-22).

**Q13.** Do we widen GIMS's storage layer so it can accept a filter, or is autoSQL only ever offered for the one source type that already has somewhere to attach one?

→ **All three, including a second verb integration**

**Q14.** Does autoSQL own moving noun records into GIMS's shared instances table, or does it offer the database path only for collections that are already there?

→ **autoSQL owns the migration as a prerequisite**

> His words: "This is the sort of thing that can happen later once we have a functional autoSQL mechanism. The more data transfer that happens in SQL instead of python the better."

**Q15.** Is autoSQL aimed at the high-volume data GIMS does not hold yet, or at the dashboard records GIMS holds today?

→ **High-volume data GIMS does not have yet**

**Q16.** Do you want the 20,000-row cap dealt with now, at roughly twice today's wait on a million-row widget, regardless of what you decide about the SQL work?

→ **Yes, but fix the badge wording first**

**Q17.** Do you want tickets opened for those four GIMS problems, and if so, in which repo?

→ **Open them in the GIMS repo directly**

> All four re-verified present on main by running GIMS's own code. Confirmed to file as item 4 of the second form.

## The demo you gated GIMS integration on

**Q18.** Does your ruling on the first job release the demo — and either way, may the parts that write no SQL (the fake-data script, the screen itself, the one-command launcher) start now?

→ **Green light, but only the safe operations**

**Q19.** If the demo does get a piece that writes SQL, may it start from that throwaway program, or does the generator have to be written again from nothing?

→ **Reuse the throwaway program as-is**

> Safe only because of Q24 — the side-by-side comparison makes any divergence visible rather than silent. Q24 is therefore not droppable.

**Q20.** What is the smallest set of things the demo's screen has to let you do to the data?

→ **That, plus time buckets and rolling windows**

> His words: "I'd actually like both additions, so 2 & 3."

**Q21.** Should the demo only show that the SQL is correct and readable, or also show GIMS's current answer going wrong at size — and should it make any speed claim at all?

→ **Correct and readable only, small data**

**Q22.** What does one heartbeat record look like — which fields, how many things emitting them, how often, and over how long a span?

→ **TAKE THE DEFAULT — invented heartbeat shape, labelled as invented in the seed script: sender id, timestamp, status, payload; ~90% byte-identical consecutive repeats; ~50 senders over 7 days.**

**Q23.** Should the demo's screen be its own app built however is quickest, or built the same way GIMS's dashboard builder is so it can move into GIMS later?

→ **Its own app, but built GIMS's way**

**Q24.** How do you want to check the numbers — the fake-data script publishes the right answer for each step, or the screen shows the SQL answer beside a Python-computed answer for the same pick?

→ **Both answers side by side on screen**

> Load-bearing — see Q19.

**Q25.** Is autoSQL's picking screen for authors who set a view up once, with everyone else just consuming the saved result, or can the end viewer re-window and re-transform on the spot?

→ **Any viewer can re-slice live**

**Q26.** Does the one-command launch have to work on your Windows machine too, or is Linux plus Docker enough?

→ **Linux and Docker only**

**Q27.** Should the demo get a design stage where you approve the look before anything is built?

→ **Add a design stage and a look sign-off**

> APPLIED — design@v1 pinned on T-2.

## Nothing has left this machine

**Q28.** Do you want me to commit all of it to the side branch and push that branch to GitHub now?

→ **Commit and push to the side branch**

> Remote: https://github.com/BMA-Corgea/autoSQL. Sequenced after Q32 and after the findings amendment.

**Q29.** Does all 2.9 MB of the investigation's files go into git, or only part of it?

→ **Commit the whole spike folder**

**Q30.** Should the one-page summary and the updated project records go onto the main branch now, or does everything wait on the side branch until you rule?

→ **Merge the summary and records now**

**Q31.** Do you want those 1,000-to-1,000,000-row test tables left gone, reloaded and kept until you rule, or reloaded and reused as the database behind the fake-data demo?

→ **Leave it gone**

> His words: "leave notes for how to generate a corpus." OUTSTANDING — not yet written.

**Q32.** Do you want that script rewritten into the investigation's folder and the check re-run before the findings are committed, or does the document's written admission of the gap stand?

→ **Rebuild the script and re-check**

> DONE 2026-08-21 — rebuilt into proto/idxshape_jsonpath_130.py, reproduces exactly. CAVEAT the re-check attaches: neither named instrument contains an AST-to-jsonpath translator, which is where the semantic risk lives, so this is a substitute rather than a clean re-derivation.

## How this shop runs

**Q33.** Do you want the routine steps moved onto cheaper models, or is running everything on the top model deliberate?

→ **Use the shipped cheap/mid/top split**

> APPLIED. Top tier left on the shipped default per item 3 of the second form.

**Q34.** What has to pass before the demo ticket's code is allowed to land in the main branch?

→ **Leave both steps running unattended**

> No change made — now on the record as a decision rather than a leftover.

**Q35.** Do you want to be notified somewhere when a ticket stops and waits on your decision?

→ **Send it to Slack or Telegram**

> His words: "Check what's going on in the GUTS-bridge. I already get telegram messages when you have a question. You might be able to print it into the terminal." APPLIED — routed through the existing openclaw path; console printing on. Trigger set by item 5 of the second form.

**Q36.** Keep the lightweight mode on for the demo build, or run that one ticket with the full process?

→ **Lightweight by default, full for the demo**

**Q37.** Do you want to configure the time tracking properly, or switch it off?

→ **Configure it, keep the numbers local**

> APPLIED. Rate left null per item 8 of the second form.

**Q38.** Do you want that permanent warning cleared, or left in place with the note that explains it?

→ **Clear it**

> APPLIED — doctor now reads 19 pass, 0 warnings.

**Q39.** How do you want the monitoring fix handled when the plugin updates?

→ **Report it to the plugin's authors**

> Widened to all three path-with-a-space defects by item 9 of the second form.

**Q40.** Do you want both machines reporting under a single "evan" name?

→ **Unify under one evan identity**

> APPLIED on this machine. Windows still reports as evanb — queued in WINDOWS-CHECKLIST.md.

## About you — the last open goal

**Q41.** How much SQL and Postgres knowledge should these write-ups assume you already have?

→ **Explain the SQL, skip the coding basics**

> Recorded as standing guidance across sessions.

**Q42.** Will anyone other than you ever review, maintain, or take over autoSQL?

→ **Just me**

**Q43.** Is autoSQL your own project, or does it belong to a company or client whose name should be on the record?

→ **Mine, but may be shown to an employer**

**Q44.** Do you want either of those two files written, or should both be dropped for good?

→ **Write both files**

> APPLIED — and the reviewer file renamed to auto-review.md so it actually resolves.

**Q45.** Should the spikes folder get its own row in the file every session reads first?

→ **List it on the front page**

> APPLIED.

**Q46.** Are you still working on autoSQL from the Windows machine, and if so, should that background watcher start itself there?

→ **Still on Windows — make it automatic**

> Script written; needs one path filled in and one run on that machine. Queued in WINDOWS-CHECKLIST.md.

---

# Round two — the 12 still waiting

**1.** → **Stands — don't build yet** — see Q1 — the note and the tick diverge; flagged

**2.** → **Fix them — re-fingerprint the document** — the two corrections a dead reviewing pass never applied

**3.** → **Leave the shipped default** — top tier stays claude-fable-5, falling back to Opus

**4.** → **File them** — four GIMS issues, all re-verified present on main

**5.** → **I send it when a ticket stops** — no hook installed

**6.** → **Right — both, correctness first** — resolves the Q6/Q9 conflict

**7.** → **TAKE THE DEFAULT** — invented widget, labelled as invented

**8.** → **TAKE THE DEFAULT** — hours tracked, no rate, billing column empty

**9.** → **Report all three** — one write-up covering all three path-with-a-space defects

**10.** → **Leave it — a rare duplicate is fine** — notification state stays per-machine, out of git

**11.** → **TAKE THE DEFAULT** — Windows script keeps its placeholder

**12.** → **Queue them — remind me when I'm there** — WINDOWS-CHECKLIST.md at the repo root

---

## Still outstanding

- **Q31's note** — write instructions for regenerating the 1,000-to-1,000,000-row test corpus. Not started.
- **Q1's ambiguity** — the tick says don't build, the note says build the bounded path. Acting on the tick; one line from him settles it.
- **The speed run's absolute latency bar** — he set the direction, not the number. A proposal is being drafted for him to accept or change.

---

# Round three — the wrap-up form · 22 Aug 2026

Asked and answered in session on 2026-08-22, before he went AFK for the day. Recorded as
**GA-6** on T-2, T-3 and T-4 with `scope_confirmed: true`. His framing, verbatim:

> "so I'm going to be AFK for most of the day. Open the form for me and let me answer the
> questions, but with those, I need you to take over and be as autonomous as possible, using
> your best judgement and previously answered questions for guidance for what I want, and
> getting through the available tickets"

**Nine of the 38 items answered — every item that gated today's work.** The remaining 29 fall to
best judgement under GA-6; each is recorded where it is taken and each stays one line to overturn.

**Item 1.** GA-4 approved one ticket; it was used to rule on three. How far did that sentence reach?

→ **It covered everything I was asked**

> The scope-confirm that was missing on GA-4 is now on the record as GA-6. All ~21 rulings stand,
> including those on T-1 and T-3. Nothing reverted, nothing re-run.

**Item 2.** Your tick said don't build; your note said build.

→ **Right — tick is GIMS, note is the demo**

**Item 3.** The demo screen's look — you have not seen it.

→ **Approve as drawn**

> APPLIED — T-2's block lifted on this answer; it was the block's own stated remedy. The build
> copies the mock exactly. The five open questions in the design brief's §9 fall to the builder.

**Item 4.** The design stage exists; the look sign-off has no stopping point.

→ **Make it a real checkpoint**

> APPLIED — repo-local `.autodev/data/gates.json` (survives plugin updates; tracker resolves
> repo-first) now carries a `design` gate, policy `human:strict` in `gates-policy.json`. Strict
> on purpose: plain `human` allows on-behalf clearing under a broad go-ahead, which is the exact
> route by which the look nearly got built unseen. Doctor: 19 pass.

**Item 5.** "Full process for the demo" was never switched on.

→ **Run the rest of T-2 full, starting tomorrow**

> APPLIED — `shop.json` `settings.lean` = false. Flip back once T-2 ships.

**Item 6.** Last night's work is not committed, and not on your other machine.

→ *Moot — already committed and pushed before he was asked.* HEAD `f274cd7` = `origin/main`.

**Item 27.** Nothing actually sends the Telegram ping when work stops.

→ **Install the automatic hook**

> APPLIED and PROVEN — `Stop` hook in `.claude/settings.json`; `notify-telegram.sh --test` sent a
> ping that reached his phone. Running commentary left off, as he chose.

**Item 28.** Three tickets are ready at once, and two of them cannot share this machine.

→ **Correctness run alongside the demo, timing run alone later**

**Item 31.** Three AutoDev bugs written up, never sent.

→ **File it**

> One issue, all three bugs, under his GitHub account; link returned to him.
