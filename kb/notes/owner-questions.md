# autoSQL — every open question · 21 Aug 2026

> **ANSWERED — 2026-08-21.** This is the blank form, kept as the record of what was asked.
> Every answer the owner gave, and what each one caused, is in [`kb/notes/owner-answers.md`](kb/notes/owner-answers.md).
> The checkboxes and ANSWER lines below are deliberately left empty.

For the owner. Second draft: written plainly, after you said the first one was full of jargon.

**46 questions · 7 of them blocking.**

## How to read this

- Each question opens with **what's going on** — the situation, in plain words — before it asks you anything.
- Then the question, then the answers, each saying what would actually happen if you picked it.
- Write your answer on the `ANSWER:` line. **Leave it blank and I take the stated default** — saying nothing is a real answer, not a gap.
- Short on time? Answer the 7 marked **BLOCKING** and stop.
- The technical version of each question, and the file it came from, sit in the indented block at the end.
- Unfamiliar word? There is a glossary of all 108 of them at the bottom.

When you are done, save the file and just say so — I read it from here.

**Blocking:** Q1, Q2, Q3, Q6, Q12, Q18, Q20

---

# The ruling

*Section A · T-1 · the gate*

This group is the actual decision on the research into turning GIMS dashboard expressions into SQL. The first question is that decision itself. The two after it are the two facts the decision rests on — answer those first if you want to reason it out rather than just take the recommendation. The last two are optional: they ask how much you want to trust the evidence before you rule.

### Q1. **[BLOCKING]** Do you accept "don't build it yet", take the restricted build, send the research back, or fund the full build anyway?

**What's going on:** A dashboard widget in GIMS today pulls up to 20,000 rows into Python and filters them there. The research asked whether the widget's expression language could be turned into SQL instead, so Postgres does that work. The answer came back mixed: the translation itself works — all 130 cases in GIMS's own test file agreed exactly — but the generated SQL ran 3.79x to 7.15x slower than today's Python path at every table size from 1,000 to 1,000,000 rows, with no crossover, and the gap widened as tables got bigger. There is also nowhere in GIMS's reply to a widget to say the database couldn't do the job and Python did it instead. Three independent reviewers read the same evidence and none of them could sign off on a plain "build it"; whatever you pick here becomes the build work, and nothing moves until you pick.

- [ ] **Don't build yet; fund the two experiments** — No build work starts; instead we run two measured experiments — one that hunts for wrong answers in the restricted feature set, one that times it head-to-head against today's code — and a "build it" has to be earned from their results (this is the recommendation).
- [ ] **Build only the restricted subset, refuse the rest** — We compile only the part of the expression language the research could vouch for — 32 of the 48 language constructs and 68 of the 130 test cases, keeping the functions abs, coalesce, count, if, length, max and min — refuse everything else with a loud, visible error, and land the five GIMS-side changes plus the wrong-answer experiment before any of it ships.
- [ ] **Send it back for more digging** — The research goes back for another pass and you name what is missing; nothing is built and nothing is decided until it returns.
- [ ] **Build it as originally scoped** — The full build goes ahead as first described, which overrules all three reviewers — every one of them found that option unavailable on this evidence.
- [ ] *Take your stated default* — Nothing moves. The research sits where it is, the fake-data UI demo stays unstarted, and the research branch stays unmerged.

**ANSWER:** 

> *Originally written as:* How do you rule at `sp_decide` — accept the NO-GO, take CONDITIONAL-GO on the corrected 32-construct / 68-of-130 subset, or send it back?
>
> *Why it matters:* This is the gate. `sp-spawn` turns whichever option you pick into build tickets, and T-2 is held behind it.
>
> `source:` .autodev/tickets/T-1-….json (gates.sp_decide:false, decision_authority: recommend-and-wait) · .autodev/handoffs/T-1.md:7-11 · kb/wiki/expr-ast-to-postgres-sql.md §3

---

### Q2. **[BLOCKING]** Is that 130-case test file an adequate acceptance test for a third, SQL version of this expression language?

**What's going on:** GIMS ships a test file of 130 cases that its expression language has to satisfy; the Python version and the JavaScript version in the frontend both pass it. The prototype SQL compiler was scored against that same file and passed all 130. Whether that file is good enough to accept a third, SQL implementation is the single point the three reviewers split on, and the whole ruling turns on it. If it is good enough, the problems found outside the file only price a rebuild of the throwaway prototype, and the restricted build stays on the table. If it is not, then the thing that would actually ship has no acceptance test at all, and "don't build" follows automatically.

- [ ] **Good enough — all 130 passing counts** — Passing 130 of 130 stands as the acceptance evidence, so the problems found outside that file price a prototype rebuild rather than block the build.
- [ ] **Not good enough — build a real one** — The wrong-answer experiment becomes the real acceptance test, and the "don't build yet" ruling follows from that.
- [ ] **Good enough for computed columns and row-conditions only** — The file counts as acceptance evidence for calculated columns and the row-condition expression, but never for sorting, key-based filters, or row limits.
- [ ] *Take your stated default* — I rule it not good enough: 6 of the 7 known SQL-vs-Python disagreements sit outside that file; the file holds zero sorting, key-filter or row-limit cases; 68 of the 130 cases carry a value through Postgres’s floating-point number type, and the entire run happened at one fixed setting for how many digits Postgres prints, with no other setting ever checked; and 0 of the 130 reach any of the 8 places where the Python evaluator throws an error instead of returning a value.

**ANSWER:** 

> *Originally written as:* Is the 130-case `expr_vectors.json` fixture an adequate acceptance test for a third (SQL) runtime of this language?
>
> *Why it matters:* FINDINGS §5.2 calls this "the one to hand the owner" — the panel's whole split turns on it. Adequate → the breaches only price a prototype rebuild and CONDITIONAL-GO stays live. Inadequate → the thing that would ship has no acceptance test at all, and NO-GO follows by construction.
>
> `source:` spikes/T-1/FINDINGS.md:4490 §5.2 ("That is the ruling this section asks for") · spikes/T-1/.parts/f5.md:67

---

### Q3. **[BLOCKING]** Can GIMS itself change — can that function return extra fields saying what ran in the database and what fell back, and can the widget UI carry its own label for it?

**What's going on:** When a dashboard widget asks GIMS for its rows it calls one function — resolve(), at api/dashboard/sources.py line 357 — and that function hands back exactly three things: the rows, a count, and a flag meaning "we stopped early". There is nowhere in that answer to say "I couldn't do this in the database, so I did it the old way in Python". The rule written before the research started said any such fallback must be reported and never silent, so meeting it needs new fields on that function plus a new label in the widget UI, separate from today's "Result capped for performance" badge. That one fact is why no reviewer could sign off, and why the "thin adapter" in the original plan is not thin — five separate GIMS-side changes hang off it. If GIMS can never change, no experiment result can ever produce a go, and funding those experiments is wasted money.

- [ ] **Yes — GIMS and its frontend are mine** — The GIMS function and the widget UI are in scope and you own them, so the five GIMS-side changes are buildable and the experiments can lead somewhere.
- [ ] **Yes, but only after the demo** — Same answer, but nothing in GIMS gets touched until you have seen the autoSQL UI working end to end over a fake-data database.
- [ ] **No — GIMS is frozen** — autoSQL has to work without changing that function, which means a fallback can never be reported and the non-negotiable rule can never be met.
- [ ] *Take your stated default* — Assumed to be yes in principle but never scheduled — which leaves the "report the fallback, never silently" rule unmet and puts any go permanently out of reach.

**ANSWER:** 

> *Originally written as:* Is GIMS's own API contract changeable — can `resolve()` grow `pushed_down` / `fallback:[{scope,reason}]`, and the UI a badge distinct from `capped`?
>
> *Why it matters:* This single fact is why GO is unavailable and why the "thin adapter" is not thin. If GIMS can never change, no E1 or E2 result can ever produce a GO, and funding them is wasted money.
>
> `source:` kb/wiki/expr-ast-to-postgres-sql.md §2 (sources.py:357 returns exactly {records,count,truncated}) · FINDINGS.md:4641 §5.5 (five-row GIMS change table incl. frontend/lib/dashboard/widgets.jsx:277)

---

### Q4. Do you want one run that proves the test rig can actually report a failure, before you rule?

**What's going on:** The 130-of-130 headline came from a test rig that sorts every case into one of three buckets: compiled and agreed, compiled and disagreed, or wouldn't compile. Only the first bucket has ever fired. The code that assigns the other two, at conformance.py lines 376 to 455, has never executed once — the rig’s 23 built-in self-checks each test one piece in isolation, and the three that feed a deliberately wrong answer hand it straight to the comparison function, so none of them ever runs the per-case path that would set a bucket. The instructions written before the research began warned about exactly this: a rig that scores "wouldn't compile" as a pass would reproduce, inside the research itself, the failure the research exists to rule out. One run would settle whether the number the whole decision quotes is real.

- [ ] **Yes — do that run before I rule** — The research goes back for that single run, and you rule after it lands.
- [ ] **No — skip it** — No run happens; the recommendation not to build does not rest on 130 of 130 being real, so the ruling is unaffected either way.
- [ ] **Make it a precondition of the first experiment** — The run does not happen now, but the wrong-answer experiment cannot start until the rig has been shown able to report a failure.
- [ ] *Take your stated default* — Never run. The 130-of-130 number stays an unaudited headline and gets inherited by whoever reuses that test file next.

**ANSWER:** 

> *Originally written as:* Before you rule — do you want the one run that proves the conformance harness can actually emit a failure?
>
> *Why it matters:* The 130/130 headline came from a harness whose "compiled and diverges" and "did not compile" branches have never once executed. That is precisely the failure mode FRAMING §8 exists to prevent, so one run is cheap insurance on the number the whole decision quotes.
>
> `source:` FINDINGS.md:4898 §5.9(6) (conformance.py:376-455, "exercised by nothing") · FINDINGS.md:447 §1.7 · FRAMING.md §8

---

### Q5. Do you accept the evidence trail as it stands, or do you want the missing pieces reconstructed before you rule?

**What's going on:** The research kept a log of what its four audit passes changed, including each time a reviewer refused to make a correction that had been prescribed to them. That log states its own refusal record is incomplete: only one of six reviewers' refusal sections reached it intact, so a refusal someone made but never wrote down would not appear anywhere. Separately, three blocks of raw measurement numbers have no surviving script that produced them — they can be read, but not re-derived or checked. So you would be ruling on a document whose own record admits it cannot list every refusal or reproduce every raw number.

- [ ] **Accept it as it stands** — The five refusals that were written down and the four audit passes that converged on the same conclusions stand as enough, and the missing reviewer reports are never recovered.
- [ ] **Reconstruct the missing reports first** — Someone spends a pass recovering the missing reviewer reports before you rule, paying that cost now instead of arguing about it later.
- [ ] *Take your stated default* — Accepted as it stands. The gap stays written down in the log and nobody revisits it.

**ANSWER:** 

> *Originally written as:* Do you accept the audit trail as-is, given its closure log records its own refusal register as incomplete — one of six seats' refusal reports reached it — and three raw `probes.json` blocks have no retained producer?
>
> *Why it matters:* You would be ruling on a document whose own record admits it cannot enumerate every refusal or re-derive every raw number. If that matters to you it costs a reconstruction pass now rather than an argument later.
>
> `source:` FINDINGS.md:5349 ("That is a gap in this log, not evidence that there were no others") · FINDINGS.md:4898 §5.9(6)

---

# The two experiments

*Section B · if NO-GO*

The recommended answer to the main decision was "not on this evidence" — not "never". Two further runs could turn it around: one that hunts for wrong numbers by throwing many thousands of generated expressions at both the existing Python code and the generated SQL, and one that times the generated SQL against what GIMS does today. These questions are about whether to pay for those two runs, in what order, and under what rules. They only matter if you went with the recommendation to hold off building.

### Q6. **[BLOCKING]** Do you pay for both follow-up runs, and do you want the speed run first so a bad result can kill the project cheaply?

**What's going on:** The research recommended holding off building, and it named two follow-up runs that could change that answer. The first is a correctness run: re-run 21 existing automated test runs plus three more, the 130-case test set and 403 extra probes, this time generating only expressions the limited version would allow, and with input values pushed hard enough to reach the error paths today's tests never touch. It passes only on zero wrong answers of any kind — no different value, no value turning into a null, no null turning into a value, and no case where Python raised an error but SQL quietly returned a number. The second is a speed run: time the generated SQL against GIMS's current in-memory code on the same table and the same data at 20,000, 100,000 and 1,000,000 rows. One of the three reviewers wrote the speed run as a kill switch — run it first, and if the SQL cannot get under 5.5 microseconds per row at 1 million rows, stop the project there.

- [ ] **Speed run first as a kill switch** — The timing run happens first and alone; if the generated SQL cannot get under 5.5 microseconds per row at 1 million rows the project stops there and the much larger correctness run is never paid for — and only if it clears that bar does the correctness run get funded.
- [ ] **Both, correctness run first** — Both get funded in the order the findings list them, so you pay for the large correctness battery before knowing whether the speed can ever be won.
- [ ] **Both at once** — Both runs are funded and go in parallel; you get both answers sooner and pay for both whatever either one says.
- [ ] **Neither — park the work** — Neither run happens and the whole line of work stops here.
- [ ] *Take your stated default* — Neither run gets paid for, and "not yet" hardens into a permanent no.

**ANSWER:** 

> *Originally written as:* Do you fund E1 and E2 — and do you want E2 first as a cheap kill-switch, or both together?
>
> *Why it matters:* E2 alone can kill the project on its own bar (panel seat 2's C-0 is written as "run FIRST, can still kill the project"), so the ordering decides whether E1's much larger correctness battery is ever paid for.
>
> `source:` FINDINGS.md:4968 §5.11 · FINDINGS.md:4788 §5.7 · spikes/T-1/.parts/panel.json seat[2] C-0 (bar ≤ 5.5 µs/row at 1M)

---

### Q7. Do you let the follow-up runs edit the throwaway code and test generators the research left behind, or must those tools be rebuilt from scratch?

**What's going on:** The research ran under a written rule of its own: the throwaway compiler it built is not a library, nothing else may ever import it, and nothing it found was allowed to be fixed while it was still running. The findings claim the two follow-up runs use tools that already exist, but that is not quite true. The correctness run needs the random-expression generators rewritten so they produce only expressions the limited version allows, and so their values get large and strange enough to reach the error paths — today's generators top out at numbers around 2026 and four levels of nesting, which is a large part of why every clean result so far is clean. It also needs two defects in the throwaway SQL fixed first: a range check written with 297 digits where it should be 309, and a number-parsing function that accepts only ASCII digits where the Python side also accepts Unicode digits. So the rule either gets an explicit exception or those tools get built again from nothing.

- [ ] **Let them edit the existing code in place** — The follow-up runs modify the existing throwaway compiler and the expression generators directly — the cheapest path — and the throwaway code stops being a frozen record of exactly what the research measured.
- [ ] **No exception — build fresh tools** — New generators and a new throwaway compiler get written from scratch with the old ones cited only as reference, roughly doubling what the correctness run costs.
- [ ] **Edit the generators only; freeze the compiler** — The expression generators may be changed in place, but the throwaway compiler stays untouched as the audit record, so the two SQL defects have to be fixed somewhere other than the frozen copy.
- [ ] *Take your stated default* — Whoever runs the correctness battery hits the rule and either stalls or quietly breaks it. Assume a rebuild, roughly doubling that run's cost.

**ANSWER:** 

> *Originally written as:* E1 cannot literally "re-run existing instruments" — it needs the fuzz generators rewritten and two runtime defects fixed (`xpr.f8`'s range guard 297→309 digits, a Unicode-aware `xpr.num`). Do you waive FRAMING §3's throwaway-prototype and no-fix contract for that work?
>
> *Why it matters:* FRAMING §3 says the prototype "is not a library, has no API, and nothing may import it later" and forbids fixing anything the spike found. So E1 either gets an explicit waiver or gets rebuilt from scratch at much higher cost.
>
> `source:` FRAMING.md §3 · FINDINGS.md:4968 §5.11 · .parts/panel.json seat[0] conditions 5-6

---

### Q8. Will you name a real widget or expression the SQL version could actually handle, or should the speed run use an invented one?

**What's going on:** The speed run has to time a real dashboard widget. The only widget anyone has ever timed end to end is one that computes how many days are left until a due date — and date functions are excluded from every version of the limited feature list, so that widget could never be compiled to SQL under any of them. There is nothing else to reach for: this machine holds exactly one dashboard, three widgets, and 7 rows of the kind of data a tenant would have. So the speed run either measures something you name from your own use, or something invented for the occasion.

- [ ] **I will name a real one I actually use** — You supply a filter or derived-column expression you genuinely use, and the speed run's pass or fail is binding because it measured real work.
- [ ] **Invent one and label it invented** — Whoever runs the timing makes up a representative widget inside the limited feature list and says so plainly in the write-up, which leaves the result arguable if anyone disputes that it represents real usage.
- [ ] **Both — real date widget plus an invented one** — The run times the existing date widget as a comparison point even though no version allows it, alongside an invented in-scope one, costing two measurements instead of one.
- [ ] *Take your stated default* — Someone invents an in-scope widget while running the timing, and the result can be challenged on whether it represents real usage.

**ANSWER:** 

> *Originally written as:* E2 needs a subset-legal widget and none exists — the only widget measured end to end is a date widget, outside every proposed subset. Name a real one, or synthesize?
>
> *Why it matters:* A synthesized widget makes E2's pass/fail arguable; a real one makes it binding. The spike has n = 1 dashboard, 3 widgets and 7 rows of tenant-shaped data to draw from.
>
> `source:` FINDINGS.md:4788 §5.7(iii) and condition 4 · FINDINGS.md:4968 §5.11

---

### Q9. How much do you want to spend on the two follow-up runs, and should cost logging be switched on before they start?

**What's going on:** Nobody knows what the research cost. The tool wrote three lines about it, one for each stage it moved through, and none of them carry a token count or a dollar figure; getting one needs per-run usage logging that the tool does not currently do. What is known is that the investigation ran 4 hours 1 minute of wall clock and produced about 117,000 words of documents. Any budget you set for the two follow-up runs would rest on that and nothing else.

- [ ] **Turn cost logging on first, then fund them** — Per-run token and money tracking gets wired up before either run starts, so you finally learn what these things cost, at the price of doing that setup first.
- [ ] **Fixed timebox each, no cost tracking** — Each run gets one pass and then stops, and you still have no idea what it cost.
- [ ] **Fund only the speed run, no cap** — Only the timing run happens, with no spending limit, on the grounds that it is a single benchmark.
- [ ] *Take your stated default* — Both runs get funded (or not) with no cost estimate, and afterwards their cost stays as unmeasurable as the research’s is now.

**ANSWER:** 

> *Originally written as:* What budget or timebox do E1 and E2 get — and do you want per-worker cost logging turned on first?
>
> *Why it matters:* T-1's own token and currency cost is NOT ESTABLISHED — the metrics file holds three stage rows with no cost fields — so there is no basis for estimating E1/E2 beyond T-1's 4 h 01 min span and ~117,000 words of output.
>
> `source:` FINDINGS.md:4938 §5.10 · .autodev/metrics.jsonl (3 stage.advanced rows, no cost fields)

---

### Q10. Do you accept, as a permanent rule, that every query autoSQL generates must pin that Postgres digit setting, and that none of these SQL helper functions may ever appear inside a database index?

**What's going on:** Postgres has a session setting that controls how many digits it prints when it turns a floating-point number into text. The research’s headline result — all 130 test cases matched — was only ever run at one value of that setting, and 68 of the 130 carry a number that passes through that conversion, so nobody knows whether those 68 still match at the other two values. Separately, four of the SQL helper functions the compiler calls are declared to Postgres as IMMUTABLE — a promise that they always return the same answer for the same input — while actually reading that setting. Postgres believes the promise and will store their results inside an index, and the research measured what follows: the same query over the same 200 rows returned 0 rows when Postgres used an index and 200 rows when it read the table directly.

- [ ] **Accept the pinned setting and the index ban** — Both become permanent deployment rules in the design, and nothing further gets tested about what happens at the other two settings.
- [ ] **Make the correctness run test all three settings** — The correctness battery runs the 130 cases at all three values of the setting and reports each separately, so you find out whether the 68 exposed cases actually break — at the cost of running that part three times.
- [ ] **Correct the four wrong declarations first** — The four helper functions get re-declared as depending on session settings before anything else, which removes the 0-rows-versus-200-rows split by making Postgres refuse to put them in an index at all.
- [ ] *Take your stated default* — The pinned setting is assumed fine and carried forward silently — which is exactly how the 0-rows-versus-200-rows failure reaches production.

**ANSWER:** 

> *Originally written as:* Do you accept pinning `extra_float_digits = 1` on every pushdown session, and banning all `xpr.*` functions from index expressions, as a permanent deployment constraint?
>
> *Why it matters:* The whole 130/130 headline exists only at that one GUC value, with 68 of 130 cases passing through float8 — and four xpr functions are declared IMMUTABLE while depending on it, which has already produced a measured index-vs-seqscan split brain (0 rows vs 200 on identical data).
>
> `source:` FINDINGS.md:227-254 §1.2 (conformance.py:341) · FINDINGS.md:558 D17 · FINDINGS.md:622 · panel.json seat[0] cond 9, seat[2] S-e

---

### Q11. If you go with the limited version, do you accept the compiler writing tenant-supplied field names straight into the SQL text?

**What's going on:** This one only bites if you chose to build the limited version. For a generated query to ever use a database index — the thing that makes a lookup fast instead of a full table read — the compiler has to write the JSON field name straight into the SQL text, rather than handing it to Postgres separately as a value. Those field names come from dashboards that tenants write. User-written text pasted directly into SQL text is the classic shape of a SQL injection hole. The research flags this as its author’s opinion rather than a measurement, and says its cost is priced nowhere in the entire record.

- [ ] **Not acceptable — and index work stays off** — The compiler never writes field names into SQL text, so generated queries can never use an index, and index work comes off the table entirely.
- [ ] **Acceptable with a strict field-name check specified up front** — It is permitted, but the design must state in advance exactly what a field name may contain and reject anything else before it reaches SQL, moving that work to spec time rather than build time.
- [ ] **Decide later, only if index work happens** — Nothing is decided now, and the question comes back the first time somebody tries to make an index work.
- [ ] *Take your stated default* — Deferred and unremarked. The first attempt at index work reintroduces this under build pressure.

**ANSWER:** 

> *Originally written as:* If you rule CONDITIONAL-GO: do you accept tenant-authored JSON key text being emitted into SQL literal position — a new injection surface the spike labels OPINION and says is "costed nowhere in the evidence"?
>
> *Why it matters:* It is a prerequisite for any index work, and it is the only security-shaped cost in the whole record that nobody priced. It either gets a design constraint now or gets discovered during build.
>
> `source:` FINDINGS.md:4641 §5.5 point 2 · f3 §3.4 prerequisite 4

---

# What integration actually means

*Section C · GIMS*

These questions are about GIMS itself, not about autoSQL's SQL generator. Going back through the GIMS code a second time turned up things the first research pass missed, and they make the integration job a different size than it looked. The first question corrects something your project notes currently record as settled fact.

### Q12. **[BLOCKING]** Which branch of the GIMS repo should autoSQL's changes be written against?

**What's going on:** Your project notes record that there are two GIMS code trees on this machine and that they are "not interchangeable" — written down as a permanent structural fact. They are actually one GitHub repo checked out twice: the folder called GIMS-Project sits on the branch refactor/foundation at 995cc59, and the copy inside GUTS sits on main. That refactor branch has already been merged into main and is now 44 commits behind it, and the GIMS-Project folder was last pulled from GitHub on 27 June 2026. Every GIMS-side change the research names has to be written against one branch or the other, and the tool creates those follow-on work tickets the moment you answer, so a wrong answer gets baked in straight away.

- [ ] **main, where the newer checkout already sits** — All GIMS-side work targets main, the stale GIMS-Project folder gets pulled up to main, and the note about two permanently different trees gets corrected.
- [ ] **refactor/foundation, to finish that line first** — Work targets a branch that is already merged into main and 44 commits behind it, so every change would later have to be carried forward onto main anyway.
- [ ] **Both, behind a compatibility layer** — Every change has to work on both branches, which means writing a translation layer and testing against both for as long as the integration lives.
- [ ] *Take your stated default* — main. I pull the stale GIMS-Project checkout up to main, and correct your notes to say "one repo, two branches, one of them 44 commits behind" instead of "two trees that are not interchangeable".

**ANSWER:** 

> *Originally written as:* Which GIMS branch is autoSQL's integration target? The "two trees" are one GitHub repo — and `GIMS-Project` sits on `refactor/foundation` @ 995cc59, already merged into `main` and 44 commits behind it.
>
> *Why it matters:* kb/CURRENT-WORK.md records these as "two trees, and they are not interchangeable" — a permanent structural fact — when they are one repo on two branches, one stale and last fetched 27 Jun 2026. Every GIMS-side change the spike names has to be authored against a branch, and sp-spawn mints those tickets the moment you rule, so a wrong answer bakes in immediately.
>
> `source:` git remote -v in both checkouts (identical) · rev-list --left-right --count origin/main...origin/refactor/foundation = 44 0, merge-base says MERGED · GIMS-Project/.git/FETCH_HEAD dated 2026-06-27 · kb/CURRENT-WORK.md:41-46

---

### Q13. Do we widen GIMS's storage layer so it can accept a filter, or is autoSQL only ever offered for the one source type that already has somewhere to attach one?

**What's going on:** A dashboard widget gets its rows from one of three kinds of source: a noun source (every record of one type, like all "tickets"), a verb source (logs of runs), or a query source (a saved keyword search). For the database to do the filtering instead of Python, there has to be somewhere to hand it a filter — and only the noun source has such a place, which today cannot actually take a filter. GIMS’s shared storage read method takes only the name of a collection and hands back the whole collection every time; a filtered version exists only on the GUTS ledger’s own stores, and it accepts a fixed list of eight ledger field names (proposal_slug, ticket_id, actor and the like), none of them a dashboard field like "due_date". Verb sources never touch that shared storage layer at all — they run their own hand-written SQL against a table whose name is assembled from the project name. So far the GIMS work has been priced as "change what the read hands back"; the incoming half — giving the read somewhere to accept a filter — is the bigger piece, and for verb sources it is a second, separate integration rather than an extension of the first.

- [ ] **noun sources only** — autoSQL is offered only for widgets that read one record type; GIMS's storage layer is left untouched, and verb and query widgets keep doing all their work in Python.
- [ ] **noun now, plus a new filtered read method** — You add a filter-accepting read method to GIMS's shared storage interface and to every store that implements it, and come back to verb sources as a separate job later.
- [ ] **All three, including a second verb integration** — On top of the storage change you also build a separate SQL path into the hand-written verb-log query, which has no shared storage layer to attach to at all.
- [ ] *Take your stated default* — noun sources only. Verb and query widgets keep running entirely in Python, and every widget’s answer says so out loud through the new field that reports whether the database did the work — one source type wired up, honest about the other two.

**ANSWER:** 

> *Originally written as:* Is changing GIMS's storage port in scope, or is autoSQL only ever offered for `noun` sources — because there is no inbound seam for 2 of the 3 dashboard source types?
>
> *Why it matters:* The GIMS change has been priced as an output-contract change, but the inbound half is bigger: RecordStore.list_records(collection) takes no filter argument at all, list_records_where exists only on gims-ledger's stores behind a whitelist with no dashboard noun field, and verb bypasses core.storage entirely with hand-rolled SQL. That is the difference between a thin adapter and a storage-layer change plus a second integration.
>
> `source:` spikes/T-1/recon/query-source.md §4, §6 · GIMS-Project/core/storage/ports.py:37 · GIMS-Project/api/iostore/verb_logs.py:82

---

### Q14. Does autoSQL own moving noun records into GIMS's shared instances table, or does it offer the database path only for collections that are already there?

**What's going on:** When a widget asks GIMS for a noun's rows, one function tries four places in order: first a single shared table called instances (whose own code comment calls it "the SQL-only target"), then a per-noun Postgres table, then SQLite, then a JSON-lines file on disk. Only the first of those four is something generated SQL could ever filter — the other three get read whole into Python no matter what. So if a real project's records still sit in the last three, the speed win is unavailable in production however good the SQL generator is. Moving that data into the shared instances table is exactly the "GIMS storage migration" that the T-1 ticket declared out of scope.

- [ ] **Only collections already in the shared table** — The database path is offered where the data already sits in the shared instances table, and every other case is reported back with a named reason for staying in Python.
- [ ] **autoSQL owns the migration as a prerequisite** — Moving existing noun data into the shared table becomes autoSQL's work and has to land before the database path is useful anywhere, which pulls this project into GIMS's storage layer.
- [ ] **Someone else owns it; autoSQL waits** — The database path gets built but stays unusable on any collection that has not been moved, on whatever schedule its owner sets.
- [ ] *Take your stated default* — Only collections already in the shared table — and "this collection is not in the shared instances table" becomes one of the named reasons reported back with the answer, never a silent switch to the Python path.

**ANSWER:** 

> *Originally written as:* Does autoSQL own migrating noun collections into GIMS's unified `instances` store, or does it offer pushdown only for collections already there?
>
> *Why it matters:* get_noun_items is a four-tier read cascade and only tier 0 is reachable by compiled SQL. If a real project's noun data still sits in tiers 1-3, the pushdown win is unavailable in production no matter what the compiler does — and getting it there is exactly the "GIMS storage migration" T-1's scope excluded.
>
> `source:` GIMS-Project/api/iostore/nouns.py:52-121 (comment at :52 "the SQL-only target") · FRAMING.md:113-115 §6

---

### Q15. Is autoSQL aimed at the high-volume data GIMS does not hold yet, or at the dashboard records GIMS holds today?

**What's going on:** The reason on record for starting autoSQL is that GIMS is "too slow for heartbeat data". But the word "heartbeat" appears in zero files in either GIMS checkout — it is a GUTS idea, where GUTS's own enterprise proposal puts heartbeats in a high-volume tier alongside ledger records and logs. Meanwhile the largest real collection the research found anywhere on this machine is 17,148 rows, which is under GIMS's 20,000-row scan cap; nothing here reaches that cap at all. Your answer sets what data the demo gets seeded with, what the follow-up speed test is measured against, and whether the project aims at a problem someone has observed or one you expect to have.

- [ ] **High-volume data GIMS does not have yet** — The demo and every performance number get built around a data shape nothing on this machine currently produces, and today's dashboards are not the target.
- [ ] **GIMS dashboard records as they are today** — The demo and the tests run on real dashboard collections, the largest 17,148 rows and under the cap, so what is being fixed is the right answer rather than a faster one.
- [ ] **Both — high volume target, dashboards ship first** — The high-volume shape stays the design target while GIMS dashboards are where it first ships, so the demo and the tests have to cover both.
- [ ] *Take your stated default* — Aim at the high-volume shape, seed the demo with it, and write plainly in your project notes that no GIMS collection seen today exceeds the 20,000-row cap — so the near-term win is getting the right answer, not getting it faster.

**ANSWER:** 

> *Originally written as:* What workload is autoSQL actually for — the heartbeat/firehose data that motivated it, or GIMS dashboard noun records?
>
> *Why it matters:* The problem statement on record is "too slow for heartbeat data", but "heartbeat" appears in zero files in either GIMS checkout — it is a GUTS spine concept — and the largest real collection the spike found is 17,148 rows, under the 20,000 cap. Nothing on this machine even reaches MAX_SCAN. This decides the demo's headline dataset, what E2 is measured against, and whether the project aims at an observed problem or an anticipated one.
>
> `source:` grep -ril heartbeat = 0 hits in both GIMS checkouts · GUTS/proposals/guts_enterprise.md:315,321 · FINDINGS.md §5.11

---

### Q16. Do you want the 20,000-row cap dealt with now, at roughly twice today's wait on a million-row widget, regardless of what you decide about the SQL work?

**What's going on:** GIMS pulls at most 20,000 rows into memory per widget, then filters and sorts them in Python. Past that point the widget's answer is not just incomplete, it is wrong: the research measured how many of the true top 50 rows come back, and got all 50 at 20,000 rows, 88% at 25,000, 38% at 100,000, and 4% at 1,000,000 — where 98% of the records that qualify are never looked at. The badge the UI shows in that state reads "Result capped for performance", which describes a slow answer, not a different one. Lifting the cap is essentially one constant in one file: the research estimates a 1,000,000-row widget would go from today's measured 8,331 ms to about 16.7 s — roughly 2.0x slower — and give back the correct answer. The research recommends not funding the SQL generator on today's evidence, which leaves this wrongness in place, so whether to trade that wait for a correct answer now is a product call only you can make.

- [ ] **Yes — lift the cap, accept the wait** — A ticket gets opened to raise or remove the cap; widgets past 20,000 rows return the correct answer and a million-row widget takes about 16.7 s instead of 8,331 ms.
- [ ] **Yes, but fix the badge wording first** — The same cap change, preceded by rewording the badge so it says the answer is different rather than late.
- [ ] **Just fix the badge wording; leave the cap** — Widgets stay wrong past 20,000 rows, but the UI stops describing a wrong answer as a slow one.
- [ ] **No — leave the cap in place** — Nothing changes now: the cap and the misleading badge both stay until the database-side filtering is built.
- [ ] *Take your stated default* — The cap stays, the badge keeps calling a wrong answer a slow one, and at 1,000,000 rows 98% of qualifying records stay unexamined.

**ANSWER:** 

> *Originally written as:* The dashboard is silently wrong today — top-50 recall 100 / 88 / 38 / 4 % at 20k / 25k / 100k / 1M, under a badge reading "Result capped for performance". Ship the cheap fix now, independent of this decision?
>
> *Why it matters:* NO-GO leaves that wrongness in place. The alternative is one line: lifting MAX_SCAN costs about 2.0× today's 8,331 ms at 1M and buys back correctness. That is a product judgement only you can make.
>
> `source:` FINDINGS.md:4641 §5.5 point 3 (≈16.7 s uncapped vs 8,331 ms measured at 1M; sources.py:61's own comment) · kb/wiki/expr-ast-to-postgres-sql.md §3

---

### Q17. Do you want tickets opened for those four GIMS problems, and if so, in which repo?

**What's going on:** The research turned up four problems in GIMS that are real whether or not any SQL work happens, and no ticket exists for any of them — the ledger holds only T-1 and T-2. Two are live production hazards. One bad row takes a whole widget down: a date value like "0001-01-01T00:00:00+14:00" makes the expression evaluator throw, and neither of the two places that call it wraps the call, so the catch-all error handler turns the widget into an HTTP 500. And if GIMS ever moves the shared instances table to Postgres's jsonb type, today's Python answer changes on 4,166 of 17,345 real rows already on this machine — those rows each carry both a run_id and a _runID key, GIMS's tolerant field lookup takes whichever comes first in key order, and jsonb does not preserve key order. The other two: the expression evaluator is documented as never throwing but actually throws 8 different ways across 9 lines and 4 exception types, and the 20,000-row cap silently changes answers.

- [ ] **Open them here, hand findings to GIMS** — Four tickets get tracked in autoSQL where the evidence sits and the findings go over to GIMS, but the fixes still have to be made in GIMS by whoever owns it.
- [ ] **Open them in the GIMS repo directly** — The four go into GIMS's own tracker, next to the code that has to change, and autoSQL stops carrying them.
- [ ] **Only the widget crash and the cap** — Two tickets get opened — the one bad row that crashes a widget, and the 20,000-row cap — leaving the other two untracked, including the jsonb key-order change that is itself one of the two live production hazards.
- [ ] **None — leave them in the findings** — Nothing gets tracked anywhere; all four stay inside the write-up.
- [ ] *Take your stated default* — They stay recorded only inside a 5,389-line document on a branch that has never been merged, and get rediscovered later by accident.

**ANSWER:** 

> *Originally written as:* The spike found four GIMS defects that exist with or without pushdown — open tickets for them, and in which repo?
>
> *Why it matters:* Two are live production hazards: one poison row takes a whole widget to HTTP 500, and migrating instances to jsonb would change today's Python answer on 4,166 of 17,345 real rows. No ticket exists for any of them — the ledger holds only T-1 and T-2.
>
> `source:` FINDINGS.md:4898 §5.9(3) · FINDINGS.md:3946 §C.13 (uncaught OverflowError at sources.py:147/:162 → HTTP 500) · ls .autodev/tickets/ = T-1, T-2 only

---

# The demo you gated GIMS integration on

*Section D · T-2*

The second job on the list is the demo you asked for: the picking screen running over a database full of made-up records, so you can watch the tool write SQL before any of this goes near GIMS. It has not been started, because its own write-up says to wait for your ruling on the first job — the investigation into whether GIMS's expression language can be turned into SQL. Before anyone can write a build plan for the demo, ten things have to be settled that nothing in the repo answers: what the screen offers, how big the fake database is, what a heartbeat record looks like, how you check the numbers. Those are product calls, so they are yours rather than mine to guess.

### Q18. **[BLOCKING]** Does your ruling on the first job release the demo — and either way, may the parts that write no SQL (the fake-data script, the screen itself, the one-command launcher) start now?

**What's going on:** The demo's write-up lists five must-haves: a database of fake records built by a committed script, the screen where you pick data and pick how to view it, the generated SQL shown next to the result, a do-this-expect-that walkthrough so you can drive it yourself and check the numbers, and one command that launches the whole thing from a fresh clone. Only the SQL-writing part depends on the ruling you owe on the first job. But the write-up also says do not start building until that ruling is in, which currently freezes all five, and nothing else is on the board to work on. So the question is whether the freeze comes off everything, off the parts that never touch SQL, or stays on.

- [ ] **Full green light, SQL written fresh** — All five parts start now, and the demo builds its SQL straight from what you click on the screen rather than by translating GIMS's existing expression language, which sidesteps everything the investigation found.
- [ ] **Green light, but only the safe operations** — The demo starts, but everything it generates is confined to the slice of GIMS’s expression language the investigation checked and corrected — 32 of 48 building blocks, covering 68 of the 130 test cases, with the other 62 refused out loud — and that slice is not clean either: the one defect measured inside it makes 8 of the 16 expression paths it can reach give wrong answers, one of them returning 1 where Python returns 1e+300.
- [ ] **Start the fake data and the screen only** — The fake-data script, the screen and the one-command launcher get built now, and the piece that actually writes SQL waits until you rule.
- [ ] **Keep everything frozen until the two experiments finish** — Nothing on the demo starts until the two follow-up experiments the investigation asked for are run and reported — one re-testing the safe slice for wrong answers, one measuring the SQL path head-to-head against today's path — and the board stays idle in the meantime.
- [ ] *Take your stated default* — Nothing on the demo starts. It stays exactly where its write-up puts it, and nothing else moves either, because you are the only one who can clear the ruling on the first job.

**ANSWER:** 

> *Originally written as:* Does your ruling unblock T-2 — and either way, may its non-SQL half (seed script, UI shell, one-command launcher) start now?
>
> *Why it matters:* Only one of T-2's five must-includes actually depends on what you rule at T-1. The other four do not, and with T-1 parked at a human gate this is the only work on the board that could move at all.
>
> `source:` .autodev/tickets/T-2-….json ("Do not start building until sp_decide is cleared") vs its own MUST INCLUDE 1/2/4/5 · kb/CURRENT-WORK.md:38

---

### Q19. If the demo does get a piece that writes SQL, may it start from that throwaway program, or does the generator have to be written again from nothing?

**What's going on:** During the investigation a throwaway program was written that turns GIMS expressions into SQL. It got all 130 test cases right, with the SQL answer matching the Python answer exactly. But the investigation's own ground rules said the program was disposable and nothing may ever import it, and all three independent reviewers agreed the thing as built must never ship, because outside the test set it quietly turns errors into numbers and nulls into values. It is also the only code anywhere in this repo that generates SQL from these expressions, and it carries a written list of 7 differences it knowingly does not fix.

- [ ] **Reuse the throwaway program as-is** — The demo imports and builds on the existing program, which means lifting the rule the investigation set for itself that nothing may ever import it, and carrying its known quiet wrong answers straight into the demo.
- [ ] **Write it again, with the old one open** — A new generator gets written from scratch with the old one beside it as reference, and the 7 differences the old one wrote down but never fixed become the first tests the new one has to pass.
- [ ] **No SQL piece in the demo yet** — The demo gets no SQL-writing piece at all until the two follow-up experiments have been run and reported.
- [ ] *Take your stated default* — Read it, do not import it. A fresh generator gets written with the old one as reference, and its list of 7 known differences becomes the starting test set.

**ANSWER:** 

> *Originally written as:* If T-2 gets a SQL layer, may it start from `spikes/T-1/proto/compile.py`, or must its generator be written from scratch?
>
> *Why it matters:* This is the concrete bridge between "the spike says NO-GO" and "the demo must still happen". FRAMING §3 says nothing may import the prototype and all three panel seats hold it must never ship — yet it is the only thing in the repo that generates SQL from this AST, and it scored 130/130.
>
> `source:` FRAMING.md:66-68 §3 · kb/wiki/expr-ast-to-postgres-sql.md:72 ("the prototype as built must never ship")

---

### Q20. **[BLOCKING]** What is the smallest set of things the demo's screen has to let you do to the data?

**What's going on:** GIMS's dashboard builder already lets an author add computed columns, set one filter, choose a sort field, cap the number of rows, and reduce rows to a single number with count, sum, avg, min or max. The tier above that does not exist anywhere in GIMS: grouping rows into time buckets, or judging a row against its neighbours — a rolling average, or whether a value changed from the row before it. The investigation deliberately left that whole tier out of scope, and nothing in this repo says which of it the demo's screen has to offer. That list is the product's feature set, so if you do not name it, I invent it.

- [ ] **Only what GIMS already does** — The screen offers exactly what your builder offers today — computed columns, a filter, sort, a row cap, and count/sum/avg/min/max — so the demo proves the SQL is right on ground you already know and shows nothing new.
- [ ] **That, plus time buckets and rolling windows** — Adds grouping rows into time buckets (per hour, per day) and a rolling calculation across neighbouring rows — the tier that does not exist in GIMS today, so it has to be designed and built from nothing.
- [ ] **That, plus show only rows that changed** — Adds the heartbeat case the project was pitched on: out of a stream of mostly identical repeats, show only the rows whose value differs from the one before it — one line of SQL in Postgres, but still another new operation to design, build and test.
- [ ] *Take your stated default* — GIMS's existing set, plus one time-bucket and one show-only-what-changed operation, with you reviewing the final list before the build starts.

**ANSWER:** 

> *Originally written as:* What is the minimum set of view / window / transform operations the demo's UI must actually offer?
>
> *Why it matters:* Windowing and aggregation are named as the tier that does not exist yet, and were explicitly out of T-1's scope. Nothing in the repo says what the UI's controls are — this is the product's feature list, and I would otherwise be inventing it.
>
> `source:` kb/wiki/autosql-architecture.md:63-68 · FRAMING.md §6 (window/aggregate out of scope) · GIMS-Project/frontend/lib/dashboard/builder.jsx:225-240

---

### Q21. Should the demo only show that the SQL is correct and readable, or also show GIMS's current answer going wrong at size — and should it make any speed claim at all?

**What's going on:** The investigation measured the SQL path at 3.79 to 7.15 times slower than what GIMS does today, at every table size from 1,000 up to 1,000,000 rows, with the gap widening and no size at which SQL wins. So a demo asked to prove speed loses on today's evidence. What a demo can prove instead is that GIMS's current answer goes wrong at size: GIMS stops after examining 20,000 rows and flags the widget "Result capped for performance", and of the top 50 rows it then displays, 100% are right at 20,000 rows, 88% at 25,000, 38% at 100,000 and 4% at 1,000,000 — at a million rows, 98% of the rows that qualify are never looked at. Showing that side by side needs a fake database big enough to cross the 20,000-row cap, and a small readable one will never show it.

- [ ] **Correct and readable only, small data** — The fake database holds 5,000 to 20,000 rows, small enough that you can read it and check by hand, and the demo shows the SQL and its result but never crosses the cap, so GIMS's truncation never appears.
- [ ] **Also show the truncation, big data** — The fake database holds 100,000 to 1,000,000 rows so GIMS's capped answer sits beside autoSQL's complete one and you can see how many of the 50 displayed rows are wrong, at the cost of data too big to eyeball, which makes checking depend on the walkthrough's written-down answers.
- [ ] **Also claim it is faster** — The demo also times both paths and makes a speed claim, knowing the only measurements taken so far put the SQL path 3.79 to 7.15 times slower with no crossover.
- [ ] *Take your stated default* — Correct answers plus the truncation. The fake database gets about 100,000 rows so GIMS's capped answer sits visibly beside autoSQL's complete one, and the demo makes no speed claim.

**ANSWER:** 

> *Originally written as:* Must the demo prove only that the generated SQL is correct and inspectable, or also show a measured win over GIMS's current in-memory path — and at what row count?
>
> *Why it matters:* T-1 measured the compiled path 3.79×–7.15× SLOWER with no crossover, so a demo asked to prove speed loses today. A correctness demo needs at least ~100k rows before MAX_SCAN's recall loss is visible at all.
>
> `source:` kb/wiki/expr-ast-to-postgres-sql.md §2, §6 · ticket T-2 MUST INCLUDE 3

---

### Q22. What does one heartbeat record look like — which fields, how many things emitting them, how often, and over how long a span?

**What's going on:** The demo's write-up says the fake data has to be shaped like the data autoSQL is meant for — GIMS-style records with arbitrary keys — including the heartbeat/firehose shape that motivated the whole project. Searching both GIMS checkouts for "heartbeat" returns nothing: no schema, no example record, no table. The only place it is defined at all is one line in the GUTS enterprise proposal, and there it is a volume class (heartbeats, ledger records, logs — high volume, mostly byte-identical repeats), not a record layout. So either you say what one heartbeat record looks like, or the demo's headline data shape gets made up.

- [ ] *Take your stated default* — I make one up and label it as invented inside the fake-data script: each record carries a sender id, a timestamp, a status and a payload; about 90% of consecutive records are byte-identical repeats of the one before; about 50 senders over 7 days. It sits alongside the GIMS-shaped records the investigation's data generator already produces (an id, a status, a due date, a priority, plus 5 to 15 arbitrary extra keys of mixed types).

**ANSWER:** 

> *Originally written as:* What should one "heartbeat" record look like in the seeded database — which fields, how many distinct emitters, at what rate, over what span?
>
> *Why it matters:* The ticket requires the seed to carry the heartbeat/firehose shape, but no heartbeat schema exists anywhere in either GIMS tree. Without an answer, the demo's headline data shape gets invented.
>
> `source:` Ticket T-2 MUST INCLUDE 1 · grep -rn heartbeat over GIMS-Project = 0 hits · GUTS/proposals/guts_enterprise.md:315 (the only definition, a volume class)

---

### Q23. Should the demo's screen be its own app built however is quickest, or built the same way GIMS's dashboard builder is so it can move into GIMS later?

**What's going on:** autoSQL has no source code at all yet — 27 files tracked in git, and every one of them is notes, settings, or the single framing document the investigation wrote before it started. GIMS already has a builder screen doing exactly the picking part: choose a source, add computed columns, a filter, a sort, a row cap, an aggregate, with a live preview. That screen is React 18, bundled ahead of time by esbuild into committed files, served by FastAPI with no Node needed at serve time. Whether the demo's screen copies that setup decides whether it is scaffolding you throw away or the first real piece of autoSQL's front end.

- [ ] **Whatever is quickest, thrown away later** — The screen gets built with whatever puts it on screen fastest, and is expected to be discarded and rewritten when autoSQL actually goes into GIMS.
- [ ] **Its own app, but built GIMS's way** — The screen lives in this repo but uses React 18, esbuild-bundled committed files and a small FastAPI server, so the same code drops into GIMS later without a rewrite.
- [ ] **Copy GIMS's builder, add a SQL panel** — The demo starts from a copy of GIMS's existing builder screen with a generated-SQL panel bolted on, which is the fastest route to a familiar-looking demo but means the copy and the original start drifting apart immediately.
- [ ] *Take your stated default* — Its own app in this repo, built on GIMS's shape — React 18, esbuild bundles served by a small FastAPI server — so it ports later without a rewrite.

**ANSWER:** 

> *Originally written as:* Is the demo UI a standalone app in this repo with a free tech choice, or built the way GIMS's dashboard builder is (React 18 + esbuild, served by FastAPI, no node at serve time) so it drops back into GIMS later?
>
> *Why it matters:* GIMS already has a builder doing source / derive / filter / sort / limit / aggregate with a live preview. This decides whether T-2's UI is throwaway scaffolding or the first real autoSQL frontend.
>
> `source:` GIMS-Project/frontend/lib/dashboard/builder.jsx · GIMS-Project/build.mjs:3 ("FastAPI serves them, no node at serve time") · autoSQL has zero source files per git ls-files

---

### Q24. How do you want to check the numbers — the fake-data script publishes the right answer for each step, or the screen shows the SQL answer beside a Python-computed answer for the same pick?

**What's going on:** The demo's write-up requires a do-this-expect-that walkthrough so you can drive the thing yourself and check the numbers rather than watch a recording. The reason is on the record in this repo: a SQL generator fails quietly, giving subtly wrong numbers rather than an error, which is why you look at it before anything ships. There are two ways to give you something to check against. Either the script that builds the fake data also writes down the right answer for each step, or the screen runs today's Python calculation alongside the SQL and shows both — and the second means building a second full calculator inside the demo, a materially bigger job.

- [ ] **Expected answers written down up front** — The script that builds the fake data also computes and prints the correct answer for each walkthrough step, and you compare what the screen shows against that list.
- [ ] **Both answers side by side on screen** — The demo carries a second, in-memory calculator that works out the same pick the way GIMS does today and shows both results together — stronger evidence, but a materially bigger build.
- [ ] **Both** — Both get built: the written-down expected answers and the live side-by-side comparison.
- [ ] *Take your stated default* — The fake-data script computes and writes the expected answer for each walkthrough step into the walkthrough document, and no second calculator is built into the screen.

**ANSWER:** 

> *Originally written as:* How do you check the numbers in the walkthrough — does the seed script publish known expected answers, or does the UI show the current Python in-memory answer beside the SQL answer for the same pick?
>
> *Why it matters:* "Check the numbers" is the demo's whole defence against the silent-wrong-number failure mode, and embedding a reference evaluator in the UI is a materially bigger build than shipping a fixture of expected answers.
>
> `source:` Ticket T-2 MUST INCLUDE 4 · kb/notes/setup.md "This shop" ("a SQL generator fails quietly — subtly wrong numbers rather than an error")

---

### Q25. Is autoSQL's picking screen for authors who set a view up once, with everyone else just consuming the saved result, or can the end viewer re-window and re-transform on the spot?

**What's going on:** GIMS already splits this in two: /dashboard is the read-only viewer, /dashboard_admin is the builder, and the builder sits behind a permission. autoSQL's picking screen has no such split decided. The answer settles whether the generated-SQL panel is in front of every viewer or only in front of authors, and whether every viewer's pick fires a fresh query. It shapes the demo now and the eventual GIMS integration later.

- [ ] **Authors set it up, viewers just look** — Only authors get the picking controls; viewers open a saved view and cannot change the shape of the data, which matches how GIMS separates its viewer from its builder today.
- [ ] **Any viewer can re-slice live** — Every viewer gets the picking controls and can re-window and re-transform whenever they want, which puts the generated SQL in front of everyone and fires a fresh query on every pick.
- [ ] **Both screens, only authors see the SQL** — Viewers get picking controls too, but the generated SQL is hidden from them and shown only to authors.
- [ ] *Take your stated default* — Authors only, with the generated SQL visible throughout the demo.

**ANSWER:** 

> *Originally written as:* Is autoSQL's picking UI an author/admin surface — configured once, viewers just consume the result — or does the end viewer re-window and re-transform live?
>
> *Why it matters:* GIMS splits these into two separately-gated pages. The answer decides whether the generated-SQL panel is shown to every viewer or only to authors, which shapes both the demo and the eventual integration.
>
> `source:` GIMS-Project/frontend/pages/dashboard.jsx:1-3 (viewer) vs dashboard_admin.jsx:1-3 (builder, gated by module:dashboards-admin) · kb/wiki/autosql-architecture.md:9-11

---

### Q26. Does the one-command launch have to work on your Windows machine too, or is Linux plus Docker enough?

**What's going on:** The demo's write-up says one command has to launch it from a clean checkout, and you work from two machines — this Linux box and a Windows one. Making that one command work on both means the demo ships its own database via docker compose plus a fake-data script that runs on either operating system. The investigation took a shortcut here: it borrowed a Postgres container already running on this Linux box, called glp-strong-db on port 55433, which belongs to a different project entirely. The demo should not inherit that shortcut, but how far it has to go instead is your call.

- [ ] **Linux and Docker only** — The demo is only ever expected to launch on this Linux box, and nobody tests or fixes it for Windows.
- [ ] **Must work on Windows too** — The launcher and the fake-data script have to be written and tested to run on both machines, which is more work up front and more that can break.
- [ ] **Either, but no borrowed container** — Which machine it runs on is left open, but the demo must bring its own database rather than lean on the Postgres container that happens to already be running here for another project.
- [ ] *Take your stated default* — Linux and Docker only. The demo ships its own Postgres via docker compose on a port of its own, and never touches the other project's container.

**ANSWER:** 

> *Originally written as:* Does "one command to launch it from a clean checkout" have to work on your Windows box too, or is Linux + Docker enough?
>
> *Why it matters:* It decides whether the demo ships its own Postgres via docker compose plus a cross-platform seed script, or can lean on this Linux machine's existing container.
>
> `source:` kb/notes/setup.md "Working across two machines" · FRAMING.md §7 (the spike borrowed glp-strong-db on host port 55433, which belongs to another project)

---

### Q27. Should the demo get a design stage where you approve the look before anything is built?

**What's going on:** The process can insert an extra stage before the build, where the look of the screen gets worked out and you approve it before any of it is coded. The demo is currently set up without one, so it would go straight from the written plan to a finished screen, and the first time you see how it looks is at the final sign-off — the point where changing the look means rework. There is also a middle path: no extra stage, but you name the visual style up front so the build is not guessing.

- [ ] **Add a design stage and a look sign-off** — An extra stage runs before the build: the screen's look is worked out and you approve it, which costs time up front but stops you first seeing the look when changing it is expensive.
- [ ] **No design stage, it is a throwaway demo** — The build goes straight from the written plan to a working screen, and you first see how it looks at the final sign-off.
- [ ] **No extra stage, just pick the style first** — No design stage is added, but you name the visual style before the build starts so the look is not invented on the spot.
- [ ] *Take your stated default* — No design stage. The demo gets built straight from the plan, and you see the screen for the first time at the final sign-off.

**ANSWER:** 

> *Originally written as:* Should T-2 get `--modifiers design` — a design pass plus a design gate — before build?
>
> *Why it matters:* Without it the UI is built straight from the spec and you first see the look at the accept gate, when changing it is expensive.
>
> `source:` .autodev/tickets/T-2-….json (modifiers: []) · the plugin's modifier table lists design as "Adds a design pass/gate"

---

# Nothing has left this machine

*Section E · git, disk, the record*

None of this work has left the laptop. Everything the investigation produced — an 80,000-word findings document, the throwaway compiler and its test scripts, a one-page summary, the updated project records, and a new ticket for the fake-data UI demo — is sitting uncommitted on a side branch. GitHub and your Windows machine still show this work at its first step, with no demo ticket at all. These five questions decide what gets written into git, what gets thrown away, and what stays on the disk and on the database server.

### Q28. Do you want me to commit all of it to the side branch and push that branch to GitHub now?

**What's going on:** Everything from the investigation is uncommitted files on this laptop, on a side branch named spike/T-1-expr-sql — a branch being a parallel line of history that leaves the main line untouched. Two commits already on that branch have also never been uploaded to GitHub. So GitHub and your Windows machine both still show this work at its first step: no findings, no summary page, no demo ticket. AutoDev's record of what happened is an append-only log — every session adds lines to the end of the same file — so if you start a session on the Windows machine from its two-day-stale copy, both copies grow different endings and the merge has to be untangled by hand.

- [ ] **Commit and push to the side branch** — Everything — records, summary page, findings, scripts, the demo ticket — goes into git on the side branch and up to GitHub, so your other machine can pull it, and the main line stays untouched.
- [ ] **Commit locally, don't push yet** — It is recorded in git on this laptop so nothing can be lost by accident, but GitHub and your other machine still cannot see any of it.
- [ ] **Leave it uncommitted until you decide** — Nothing is recorded anywhere until you make the build-or-not call; the files stay as loose uncommitted changes on this laptop only.
- [ ] *Take your stated default* — I commit everything — records, handoff, notes pages, and all the investigation's files — to the side branch and push it to GitHub. The main line of history is left alone.

**ANSWER:** 

> *Originally written as:* Do I commit and push it all to `spike/T-1-expr-sql` now?
>
> *Why it matters:* A session started on your other machine would work from a two-day-stale board and then conflict the append-only ledger. Right now that machine cannot see the findings, the T-2 ticket, or any ledger movement.
>
> `source:` git status --short (7 modified, 6 untracked) · git log origin/main..spike/T-1-expr-sql = 2 unpushed · git show 181be80:.autodev/tickets/T-1-….json still says sp-frame · kb/notes/setup.md:114

---

### Q29. Does all 2.9 MB of the investigation's files go into git, or only part of it?

**What's going on:** The investigation left 2.9 MB of files under spikes/T-1. Some of it is plainly worth keeping: the findings document (508 KB) and the document that set the pass/fail bar before any evidence was collected. The rest is working material — proto/ (828 KB), the throwaway compiler plus every script that produced a number; analysis/ (660 KB), the measurements and 21 test batteries that hunt for cases where SQL and Python disagree; .parts/ (764 KB), the raw notes each parallel sub-investigation wrote, including the three independent verdict write-ups the summary page quotes; and recon/ (180 KB), notes on your existing code. The recommended follow-up experiment is literally "run analysis/fuzz/run_all.sh again with a narrower set of expressions", so throwing out the throwaway prototype throws out the instruments that experiment needs.

- [ ] **Commit the whole spike folder** — Every file is committed, so every reference in the summary page opens from a fresh copy of the project, at the cost of 2.9 MB living in the project's history forever.
- [ ] **Commit everything except the drafting notes** — Everything but the 764 KB of raw sub-investigation notes goes in, which leaves the summary page's citations to the three verdict write-ups pointing at files nobody else can open.
- [ ] **Keep the write-ups, delete the code** — Only the findings document, the bar-setting document and the summary page survive; the 828 KB prototype compiler and the 660 KB of measurement and divergence-test scripts are deleted, so the recommended follow-up experiment would have to be rebuilt from scratch.
- [ ] *Take your stated default* — I commit all of spikes/T-1 exactly as it is (Python's cache folders are already excluded), so every reference in the summary page opens from a fresh copy of the project.

**ANSWER:** 

> *Originally written as:* Does the whole 2.9 MB spike tree go into git history — including `.parts/` (764 KB of drafting parts) and `proto/` (the throwaway compiler) — or only a curated subset?
>
> *Why it matters:* The KB page cites .parts/panel.json and analysis/fuzz/ as its evidence, and E1 is literally defined as re-running analysis/fuzz/run_all.sh — so deleting the "throwaway" prototype would delete the instruments the recommended next experiments need.
>
> `source:` du -sh spikes/T-1/* → FINDINGS 508K, proto/ 828K, analysis/ 660K, .parts/ 764K, recon/ 180K · kb/wiki/expr-ast-to-postgres-sql.md:92 and §7

---

### Q30. Should the one-page summary and the updated project records go onto the main branch now, or does everything wait on the side branch until you rule?

**What's going on:** Alongside the 80,000-word findings there is a one-page summary of what the investigation found and what it recommends — the version anyone would actually read. It exists only on the side branch, as does the new row in the project's index that points at it, so the copy on GitHub carries no sign the investigation ever ran, and if that index row ever lands without the page the link is dead. AutoDev's process for this kind of investigation has no step that says when to merge back to the main line, so nothing decides this except you. The other natural moment is right after your ruling, when the ruling gets turned into build tickets.

- [ ] **Merge the summary and records now** — The summary page and the updated records land on the main line immediately, so a fresh copy of the project shows the investigation happened and what it found, even though you have not ruled yet.
- [ ] **Keep it all on the branch** — The main line stays exactly as it is, and every trace of the investigation lives on the side branch until you make the call.
- [ ] **Merge later, with your ruling** — The merge happens as part of turning your ruling into build tickets, so the main line changes once and in line with whatever you decide.
- [ ] *Take your stated default* — Everything stays on the side branch. The summary page and the records merge to the main line after you rule, as part of turning that ruling into build tickets.

**ANSWER:** 

> *Originally written as:* Should the durable KB page merge to `main` now, or does the whole spike branch stay parked until you rule?
>
> *Why it matters:* kb/index.md already advertises wiki/expr-ast-to-postgres-sql.md in its pointer table, but that file exists only in this branch's working tree — so a fresh clone of main has a dead KB link and no record the spike ever ran. The spike@v2 pipeline has no merge stage, so nothing in the process decides this for you.
>
> `source:` git branch -a: local main == origin/main == 181be80 · kb/index.md pointer table · git status --short (file untracked)

---

### Q31. Do you want those 1,000-to-1,000,000-row test tables left gone, reloaded and kept until you rule, or reloaded and reused as the database behind the fake-data demo?

**What's going on:** To run its tests, the investigation built its own scratch database — autosql_spike — on the same Postgres container that hosts your glp_strong database, and loaded it with tables from 1,000 up to 1,000,000 rows: 1,060 MB against glp_strong’s 131 MB. I checked that container just now and the scratch database is gone. It was restarted 41 minutes ago and only glp_strong remains, at 71 MB. So this is no longer "drop it or keep it" — it is "reload it or not". Two things still want a loaded database: the head-to-head speed run the findings recommend, and the fake-data demo; reloading those tables from the committed scripts costs real time.

- [ ] **Leave it gone** — Nothing gets reloaded, and any later speed run or demo rebuilds the 1,000-to-1,000,000-row tables from the committed scripts.
- [ ] **Reload it and keep it until you decide** — The 1,060 MB goes back onto the shared container now, so nothing has to be loaded later if you fund the speed re-run.
- [ ] **Reload it and reuse it for the demo** — The same tables come back and become the demo’s database, so the UI demo needs no loading step of its own and the gigabyte stays.
- [ ] *Take your stated default* — Nothing gets reloaded until you rule; if you accept the recommendation not to build and do not fund the speed re-run, it stays gone.

**ANSWER:** 

> *Originally written as:* The spike's scratch database `autosql_spike` is still on the shared `glp-strong-db` container at 1,060 MB — drop it, or keep it seeded?
>
> *Why it matters:* E2 and T-2's seeded demo both want a loaded Postgres, and re-seeding the 1k→1M measurement tables costs real time. But keeping it costs a gigabyte on the same container that hosts glp_strong (131 MB).
>
> `source:` docker exec glp-strong-db psql -l → autosql_spike 1060 MB, glp_strong 131 MB · FINDINGS.md:28 · FRAMING.md §7

---

### Q32. Do you want that script rewritten into the investigation's folder and the check re-run before the findings are committed, or does the document's written admission of the gap stand?

**What's going on:** One measurement in the findings was produced by a one-off script that got written into a temporary session folder instead of the investigation's own script folder, and was never saved. It is the check of all 130 test cases through Postgres's own JSON-path matching — the built-in way Postgres asks whether a JSON document satisfies a path expression: 16 of the 130 cases could be written that way, 11 agreed with Python and 5 disagreed. The document says this openly, and notes the result can still be re-derived from two scripts that were saved. AutoDev's record of the investigation pins the findings document by a sha256 fingerprint — a checksum of its exact bytes — so once it is committed this gap is frozen in as it stands.

- [ ] **Rebuild the script and re-check** — I rewrite the script into the investigation's script folder, re-run all 130 cases and commit it beside the findings, so every number in the document can be reproduced from this repo alone; it costs the re-run, and if the result disagrees with 16 expressible / 11 agreeing / 5 diverging that has to be settled before the document is committed.
- [ ] **Leave the gap disclosed** — Nothing changes; the document's written admission that this one number cannot be reproduced from the repo alone becomes permanent once it is committed.
- [ ] *Take your stated default* — I leave it. The admission stays in the document, and the result can still be re-derived from two scripts that are committed.

**ANSWER:** 

> *Originally written as:* FINDINGS cites a 130-case strict-jsonpath result produced by a script written to the session scratchpad and never saved into `proto/`. Regenerate and commit it, or let the record stand with the gap disclosed?
>
> *Why it matters:* It is the one number in the spike that cannot be reproduced from this repo alone, and the sp-investigate receipt pins FINDINGS.md by sha256. If that file is about to be frozen into git as the evidence, this is the moment to close the gap or accept it permanently.
>
> `source:` FINDINGS.md:2170-2175 ("not itself a committed artifact", §3.8 open item 9) · the receipt in the T-1 ticket cites a sha256, not a commit

---

# How this shop runs

*Section F · the factory*

These are settings that came bundled with the starting template you picked when you set this up, not choices you actually made. None of them stop any work from happening. A few of them quietly spend money, and a few hide problems instead of showing them to you. Each one below is a small decision you can make once and forget.

### Q33. Do you want the routine steps moved onto cheaper models, or is running everything on the top model deliberate?

**What's going on:** When a step of a ticket runs, the tool starts a background worker to do it, and each kind of step carries a job label — the only one used so far is "coder". The tool ships a table saying which strength of model each job label should get: a cheap fast one for light work, a mid-strength one (Sonnet) for ordinary work, and the top one for building, reviewing and QA. That table has never taken effect here — all four workers that have run so far ran on Opus, the top and most expensive model, because a spawned worker inherits whatever model your session is on and nothing in this repo overrides it. So routine steps like taking in a ticket, queueing it and finding the right files cost exactly what the hard steps cost, and on a long build that is most of the spend.

- [ ] **Use the shipped cheap/mid/top split** — Light steps run on cheap or mid-strength models and only building, reviewing and QA get the top model, which cuts most of the spend on a long build.
- [ ] **Keep everything on Opus** — Nothing changes; every step, however routine, keeps running on the most expensive model.
- [ ] **Use the split, but force top tier to Opus** — Light steps get cheaper models, and the heavy steps are pinned to Opus instead of the tool's default top model, claude-fable-5, which you may not have access to.
- [ ] *Take your stated default* — Nothing changes. No model settings file is written, and every background worker keeps inheriting your session's Opus.

**ANSWER:** 

> *Originally written as:* Every worker so far has run on `claude-opus-5[1m]` even though the `coder` seat resolves to the standard (Sonnet) tier — honour tier routing to cut cost, or is top-model-for-everything deliberate?
>
> *Why it matters:* It decides whether routine stages — intake, queue, locate — burn top-tier tokens. On a long build like T-2 that is most of the spend.
>
> `source:` .autodev/events.jsonl — all 4 worker.started events carry seat "coder" with model claude-opus-5[1m] · roster seatModel('coder') returns "standard" · .autodev/roster/autosql/ holds only .gitkeep

---

### Q34. What has to pass before the demo ticket's code is allowed to land in the main branch?

**What's going on:** This repo has no tests, no dependency lockfile and no automated build service — there is nothing here that can be run to prove code works. Your process has a step called verify that is meant to run the test suite and report it green, and a merge step that folds finished work into the main branch; both merge and the ship step are currently set to run with no human involved. T-2, the ticket for demoing the SQL UI over a database of fake data, is the first ticket that will actually reach those steps. As things stand it would arrive at verify, find nothing to run, pass on whatever the worker wrote up by hand, and then merge itself.

- [ ] **Decide now what counts as tested** — You pick the language and framework and the exact commands — tests, lint, type checks — that must come back clean, and code cannot land until they do.
- [ ] **Require your approval before merging** — Merging stops and waits for you every time, until a real test suite exists to check instead.
- [ ] **Leave both steps running unattended** — Code lands with no automated check at all, and you catch problems yourself when you are asked to accept the finished work.
- [ ] *Take your stated default* — The demo ticket reaches the check step, finds nothing to run, passes on whatever the worker writes up by hand, and merges itself.

**ANSWER:** 

> *Originally written as:* The repo has no test runner, lockfile or CI, yet `merge` and `deploy` both clear unattended — what counts as "green" before T-2's code lands?
>
> *Why it matters:* T-2 is the first ticket that will reach verify and merge, and today those stages would pass and land code with no automated evidence at all.
>
> `source:` .autodev/data/gates-policy.json:5,7 (merge/deploy unattended) against a repo with no package.json and no .github/workflows · verify@v1 validator requires suites GREEN

---

### Q35. Do you want to be notified somewhere when a ticket stops and waits on your decision?

**What's going on:** T-1 — the research spike into whether GIMS dashboard expressions can be compiled into Postgres SQL — finished its research and has been sitting waiting on your decision since 2026-08-19. The watcher's own log now reads 40.4 hours in that state, longer than it expects. Nothing told you, and nothing will: a stopped ticket is discoverable only by opening a session in this specific repo, and you work from two machines. The same silence applies to the two check points you deliberately asked for — approving a spec before build starts, and accepting finished work before it ships.

- [ ] **No alerts, I'll find out in a session** — Nothing changes; a stopped ticket stays invisible until you happen to open a session in this repo.
- [ ] **Drop a note file into the repo** — Each hold writes a small note file into a folder in this repo, which needs no accounts or passwords and can be picked up by you or by anything you point at it later.
- [ ] **Print it to the terminal** — The hold prints to whatever terminal is running at the time, which only helps if you are already sitting there.
- [ ] **Send it to Slack or Telegram** — You get a real message on your phone, but it needs an account and access token set up first.
- [ ] *Take your stated default* — No notifications are set up. Holds keep surfacing only when a session happens to run in this repo.

**ANSWER:** 

> *Originally written as:* T-1 has sat at `sp_decide` for two days with no way to tell you. Do you want gate holds pinged somewhere?
>
> *Why it matters:* You work from two machines, so a decision that stops the entire factory is currently discoverable only by opening a session in this specific repo. The same silence will apply to spec_ready and accept — the two gates this preset exists to enforce.
>
> `source:` .autodev/connect.json = {"channels":[]} · kb/CURRENT-WORK.md:36 · watcher log: "autoSQL · T-1 in sp-decide for 40.4h — over expected"

---

### Q36. Keep the lightweight mode on for the demo build, or run that one ticket with the full process?

**What's going on:** The tool has a lightweight mode that trims ceremony on every ticket: short write-ups at the find-the-files and planning steps, trivial steps folded in without starting a worker, and the build done on a branch in your working copy instead of in a separate isolated checkout. It is on for everything in this repo because the starting template you picked turned it on — it was never a separate decision, and the log records the reason as the template’s default. T-1, a research spike, ran that way, which suited it. T-2 — the UI demo over fake data — is the first ticket that will write real code across several files, and lightweight is thinner than you may want for that.

- [ ] **Keep it lightweight everywhere** — Every ticket including the multi-file demo build keeps short planning notes and builds on a branch in your working copy.
- [ ] **Lightweight by default, full for the demo** — Routine tickets stay light, but the demo build gets full planning documents, its own isolated checkout, and each step run by its own worker.
- [ ] **Turn lightweight off everywhere** — Every ticket, however small, pays for full planning documents and an isolated checkout.
- [ ] *Take your stated default* — Lightweight stays on for everything, so the demo ticket is built on a branch in your working copy with short planning notes.

**ANSWER:** 

> *Originally written as:* Lean ceremony is on shop-wide because it came with the preset, never as a separate decision — keep it for T-2's build, or run that ticket `--full`?
>
> *Why it matters:* Lean gives terse locate/plan, inlines trivial stages and drops the worktree. Right-sized for a research spike; thinner than you may want for the first real multi-file build.
>
> `source:` .autodev/shop.json:8 ("lean": true) · .autodev/lean-log.jsonl (T-1 ran lean, source shop-default, worktree dropped) · no lean decision in the onboarding transcript

---

### Q37. Do you want to configure the time tracking properly, or switch it off?

**What's going on:** Time tracking is on by default and has never been configured, so it is running on stock settings. It works out hours by taking the moments you typed something plus the moments the system wrote a record, then cutting them into work blocks wherever the gap between two marks is longer than 15 minutes. Long stretches inside a single background worker run leave no marks in between, so those hours simply vanish. For everything done on T-1 it reports 25 minutes tracked, 30 minutes billed and 1.00 hour total — while one research step alone ran from 16:50 to 23:26, an undercount of roughly ten times.

- [ ] **Configure it, keep the numbers local** — You set a client name, an hourly rate and how long a gap ends a work block, and the hours stay in this repo.
- [ ] **Configure it and connect a Google Sheet** — Same setup, plus hours and work descriptions get written into a spreadsheet you connect.
- [ ] **Switch it off** — It stops recording and no hours are kept at all.
- [ ] *Take your stated default* — It keeps quietly building up a large undercount that nobody uses.

**ANSWER:** 

> *Originally written as:* Time tracking is on by default and currently reports 1.00 billable hour for everything done on T-1 — configure it properly, or switch it off?
>
> *Why it matters:* Blocks are derived from session turns plus ledger events, so hours spent inside long worker runs vanish. The totals understate the real work by roughly an order of magnitude.
>
> `source:` no .autodev/time.json exists (defaults to enabled) · time-track report → T-1 tracked 0h25m / billed 0h30m / TOTAL 1.00h, while sp-investigate alone spanned 16:50→23:26

---

### Q38. Do you want that permanent warning cleared, or left in place with the note that explains it?

**What's going on:** There is a command that checks this setup's wiring and prints a pass or a warn for each thing it checks. It reads 18 pass and 1 warn, every single time. The warning is about a stricter built-in process template meant for compliance-heavy work — one this repo never runs — whose compliance-review step names a "compliance officer" role that has no definition behind it. kb/notes/setup.md already tells anyone who reads it that this warning is expected and harmless. The cost is habit: a check that always warns trains you to skim it, so the day a real warning appears it gets skipped.

- [ ] **Clear it** — Either define the missing role here or drop that regulated template from this repo, so the check reads all-clear and any warning you see later is a real one.
- [ ] **Leave it as documented noise** — The check keeps reading 18 pass and 1 warn, and kb/notes/setup.md keeps explaining why.
- [ ] *Take your stated default* — The check keeps reading 18 pass and 1 warn indefinitely, and kb/notes/setup.md keeps explaining why.

**ANSWER:** 

> *Originally written as:* Doctor's one standing warning is an unresolved `compliance-officer` role in the `feature-regulated` pipeline this shop never runs — silence it, or keep it as documented noise?
>
> *Why it matters:* A doctor that always warns trains you to skim it, so the day a real warning appears it gets skipped.
>
> `source:` doctor.mjs --verbose · kb/notes/setup.md pre-documents it as "expected and harmless" · .autodev/data/gates-policy.json:10 still carries compliance: human for that unused pipeline

---

### Q39. How do you want the monitoring fix handled when the plugin updates?

**What's going on:** This repo's path contains a space, in "Coding Projects". The background service that watches your repos did not handle that: it split the path at the space, watched a folder that does not exist, saw zero repos, and reported no error at all. You patched the plugin's own files on this machine to fix it, but that patch lives only inside the installed copy of version 0.53.0. Any plugin update writes a fresh copy and the fix is gone — at which point monitoring goes dark silently, with nothing to tell you.

- [ ] **Report it to the plugin's authors** — You send the fix upstream so a future version ships it and you stop re-applying it, though nothing changes until they take it.
- [ ] **Add a check that catches the revert** — Something detects when the fix has been wiped and tells you, instead of monitoring failing silently.
- [ ] **Re-apply it by hand each time** — Nothing is added; you notice when the health check reports the watcher is not covering this repo, and patch it again.
- [ ] *Take your stated default* — Nothing proactive happens. You re-apply the fix by hand whenever the health check reports the watcher is not covering this repo.

**ANSWER:** 

> *Originally written as:* The sidecar `--roots` quoting patch exists only inside the 0.53.0 plugin cache — report it upstream, guard it with a check, or accept re-applying it after each plugin update?
>
> *Why it matters:* On the next plugin update the watcher silently re-points at a nonexistent "/home/corgea/Desktop/Coding" and monitoring goes dark with no error. The failure mode is invisible, not loud.
>
> `source:` memory/autodev-sidecar-quoting-patch.md · the plugin cache holds only 0.53.0

---

### Q40. Do you want both machines reporting under a single "the owner" name?

**What's going on:** The monitoring service files its reports tagged with an id for each machine. Your Windows box reports as <telemetry-id>; this Linux box reports as corgea-corgea-ms-7c79-da02f2, because on its first run it fell back to the Linux account name "corgea". Your own recorded rule for this project is that the person doing the work is the owner and never the Corgea git identity, yet this machine attributes everything to corgea. The id was written to a cache file the first time it ran, so renaming now starts a fresh id rather than relabelling what is already filed.

- [ ] **Unify under one the owner identity** — This machine starts reporting as the owner, while the reports already filed under corgea keep that label, so the history is split at the changeover point.
- [ ] **Leave both as they are** — Two machine names stay in the reports, one saying owner and one saying corgea.
- [ ] *Take your stated default* — Both stay as they are. It only affects labels on reports, and because the id is cached, changing it would split the history anyway.

**ANSWER:** 

> *Originally written as:* Fleet reports arrive under two identities — `<telemetry-id>` from Windows and `corgea-corgea-ms-7c79-da02f2` from here, where the operator resolved to "corgea" rather than "the owner". Unify them?
>
> *Why it matters:* Your own recorded rule is that the true actor is human:owner and never the Corgea git identity, yet this machine's telemetry attributes everything to "corgea".
>
> `source:` ~/autodev-reports/install.json ({"operator":"corgea"}) vs the Windows install id in onboarding.json:94 · install-id.mjs:46 falls back to the OS username

---

# About you — the last open goal

*Section G · onboarding*

Setup asked a short list of questions three days ago, and all but one got answered. The one still open is about you — your background, whether anyone else will ever touch autoSQL, and who the project belongs to. None of it blocks work; the answers change how future write-ups are worded, whose name goes on decisions, and a few leftover setup details. The first question is the one with real effect: it sets how much a report explains before it hands you numbers to check by eye.

### Q41. How much SQL and Postgres knowledge should these write-ups assume you already have?

**What's going on:** The way this project is set up, work stops twice and waits for you: once on the plan, before any code is written, and once on the finished result, before it ships. Each stop hands you a written summary to read. Nothing on record says how much database background you have, so right now those summaries are written as if you have none. That matters more here than usual, because a tool that writes SQL for you does not crash when it gets something wrong — it hands back a number that looks fine and is quietly incorrect, and you are the person reading the summary who has to catch it.

- [ ] **Assume none — explain everything** — Every database term gets defined where it first appears and nothing is cut for length, so the write-ups stay long but nothing goes past you unexplained.
- [ ] **Explain the SQL, skip the coding basics** — Write-ups spell out the database reasoning but assume you follow the programming side, which makes them noticeably shorter.
- [ ] **Assume I know Postgres; write tight** — Database terms get used without definition and summaries get much shorter — quicker to read, with less explanation sitting in front of the numbers you are checking.
- [ ] *Take your stated default* — You stay recorded as a solo builder who knows the Python side of GIMS and GUTS well but who has said outright that you are shaky on ad-hoc SQL — that came from the job-interview SQL challenge. So write-ups keep explaining everything and cut nothing.

**ANSWER:** 

> *Originally written as:* What's your role, and how much SQL/Postgres depth should the factory assume you bring to a review — beginner, comfortable, or expert?
>
> *Why it matters:* It sets how much a spike write-up explains versus assumes at your two gates, and this shop's whole premise is that you catch a silently-wrong number by eye.
>
> `source:` procedures/onboarding.md:179 (goal 7 — role, experience) · .autodev/onboarding.json:36-43 (about step still pending)

---

### Q42. Will anyone other than you ever review, maintain, or take over autoSQL?

**What's going on:** The setup you picked names you personally as the person who approves the plan and accepts the finished work. There is also a list of people allowed to hold those approvals, and it is empty apart from a placeholder file. Everything written so far assumes one human with one name. If someone else is ever going to review this code or take it over, that person needs a real entry on that list and an approval step of their own, plus a handoff document written for another human — which does not exist today.

- [ ] **Just me** — Nothing changes: you stay the only name on every approval, no list of people gets created, and no handoff is written for anyone else.
- [ ] **Someone else will review it** — That person gets a real entry on the list and the review approval gets assigned to them instead of you — say who in the notes.
- [ ] **A team later, but not yet** — You hold every approval for now, but the record notes that more people are expected, so the process is shaped for an eventual handoff rather than a one-name project.
- [ ] *Take your stated default* — You are treated as working alone: you hold every approval, nobody else is listed, and no handoff gets written for another person.

**ANSWER:** 

> *Originally written as:* Is anyone else ever going to touch autoSQL — a reviewer, a teammate, a future maintainer — or is it just you?
>
> *Why it matters:* The roster is empty and solo-builder-review names you at both gates. A second person means real gate roles and a roster entry rather than a one-name shop.
>
> `source:` procedures/onboarding.md:181 (goal 8 — team) · .autodev/roster/autosql/ holds only .gitkeep

---

### Q43. Is autoSQL your own project, or does it belong to a company or client whose name should be on the record?

**What's going on:** Nothing on record says who autoSQL is for. What is on record is why it exists: you failed a surprise SQL challenge in a job interview, and that pushed you to harden GIMS into something enterprise-ready. No employer or client is named anywhere. Whether an outsider ever reads this code changes how strict review has to be, and whether folding autoSQL into GIMS has a real deadline behind it.

- [ ] **Mine — personal or portfolio** — No outside owner is recorded, review stays as strict as you choose to make it, and the GIMS integration has no deadline attached.
- [ ] **Company or client work** — The owner's name goes on the record, review gets tightened for an outside reader, and the GIMS integration is treated as having a real deadline — say whose in the notes.
- [ ] **Mine, but may be shown to an employer** — No outside owner is recorded, but the work is kept in a state you would be willing to put in front of someone judging it.
- [ ] *Take your stated default* — It is recorded as your own personal or portfolio work under the BMA-Corgea account, with no outside stakeholder and no deadline.

**ANSWER:** 

> *Originally written as:* Is autoSQL personal/portfolio work, or does it belong to a company or client whose name should be on the record?
>
> *Why it matters:* Whether an outside reviewer or employer ever sees this changes how strict review has to be, and whether the GIMS integration has a real deadline behind it.
>
> `source:` .autodev/onboarding.json:38 (ABOUT step) · onboarding.json:73 (motivation recorded as a failed job-interview SQL challenge, no employer named)

---

### Q44. Do you want either of those two files written, or should both be dropped for good?

**What's going on:** During setup, a helper read your onboarding answers, drafted two optional extra files for the project, and then never showed them to you. One would tell every reviewing session to behave like the reviewer for a regulated client; it was triggered by nothing more than the word "compliance" appearing in your own notes about GIMS's audit trail. The other is a standing note telling build sessions what the surrounding stack is — greenfield repo, GUTS and GIMS-Project alongside it, folded back into GIMS later. Both drafts are, as written, your onboarding answers quoted back verbatim plus two generic sentences. Neither file exists on disk, and because no yes-or-no was ever recorded, both get re-offered every time setup is resumed.

- [ ] **Write both files** — Both get created: reviewing sessions take on the regulated-client tone and build sessions read the stack note, each file carrying your onboarding answers pasted in.
- [ ] **Write only the stack note** — Only autodev/instructions/build.md is created, so build sessions know GUTS and GIMS are the surrounding context; the regulated-reviewer file is dropped.
- [ ] **Drop both, stop asking** — Neither file is created, and the refusal is written down so no future setup session offers them again.
- [ ] *Take your stated default* — Both are dropped for good. The regulated-reviewer draft only appeared because the word "compliance" showed up in your GIMS notes, and both drafts are raw quote-dumps of your own onboarding answers.

**ANSWER:** 

> *Originally written as:* shop-tailor drafted two profile files that were never offered to you — a compliance-minded reviewer and a stack-context build instruction. Write either, or record a permanent skip?
>
> *Why it matters:* The procedure requires a recorded per-file yes/edit/skip. With nothing recorded, these get re-pitched on every resumed onboarding session.
>
> `source:` shop-tailor.mjs --json returns 2 drafts (agents/review.md, instructions/build.md) · no autodev/ directory exists in the repo

---

### Q45. Should the spikes folder get its own row in the file every session reads first?

**What's going on:** Every session that starts work on this project reads one file first — kb/index.md — a short table that says "looking for X, read this page." A scan noticed that the spikes folder holds a lot of written knowledge that table never mentions: 105 files, 25 of them markdown, 2.8 MB. That folder is where the whole first investigation lives, including its 5,389-line findings document and every raw measurement behind it. It is not lost — the short summary page in the wiki and the current-work note both link into it — but nothing on the front page points there directly.

- [ ] **List it on the front page** — A row is added pointing at the spikes folder, so any session can reach the raw investigation output straight from the front page.
- [ ] **Leave it off** — The front page keeps only the summary pages, and the raw investigation output stays reachable only by following a link from the summary page or the current-work note.
- [ ] *Take your stated default* — It stays off. The summary page and the notes from the first piece of work already link into that folder, and raw investigation output is not treated as front-page knowledge.

**ANSWER:** 

> *Originally written as:* brain-scan flags `spikes/` (105 files, 25 markdown, 2.8 MB) as knowledge the KB index doesn't point at — add an index row, or leave it out?
>
> *Why it matters:* kb/index.md is what every future session reads first. Unindexed, T-1's 5,389-line FINDINGS.md is only reachable by following the wiki page or CURRENT-WORK.
>
> `source:` brain-scan.mjs --json → {"path":"spikes","kind":"docs-like","files":105,"linked":false} · kb/index.md has no spikes row

---

### Q46. Are you still working on autoSQL from the Windows machine, and if so, should that background watcher start itself there?

**What's going on:** Setup was done on your Windows machine; everything since has run on this Linux one. A small background process watches this project's log files and writes status reports — read-only, no AI, no cost. On Linux it is installed as a proper background service and is running right now. On Windows it cannot be: the installer has no Windows support, so it has to be started by hand every session or wired into Windows Task Scheduler. The Windows setup details on record are only worth keeping accurate if that machine is still in play.

- [ ] **Linux only from now on** — Windows drops off the list of machines being watched, and its setup notes stop being kept up to date.
- [ ] **Still on Windows — make it automatic** — A Windows Task Scheduler entry gets set up so the watcher starts on its own there, and the Windows setup notes stay maintained.
- [ ] **Still on Windows — I'll start it myself** — No autostart gets built; you run the watcher by hand on Windows each session, and it stops when that session ends.
- [ ] *Take your stated default* — Linux is treated as the only machine in use for autoSQL. No Windows monitoring work gets done, and the Windows setup notes stop being maintained.

**ANSWER:** 

> *Originally written as:* Are you still driving autoSQL from the Windows box — and if so, do you want monitoring persistent there?
>
> *Why it matters:* The sidecar has no win32 service support, so persistence means a Task Scheduler entry or a hand-started watcher every session. The alternative is dropping that machine from the monitored fleet.
>
> `source:` .autodev/onboarding.json:94 ("install REFUSED on win32 … no autostart on Windows") · sidecar-service.mjs:100 returns "no service manager" for anything but darwin/linux

---

# Glossary

Every word in this document that is jargon somewhere — the process tool's, this project's, or a database's.

## The process tool

**AutoDev** — The process tool you set up three days ago; it runs inside Claude Code and turns each piece of work into a tracked file that moves step by step, stopping wherever a human has to decide. It is where almost all of the unfamiliar vocabulary in these questions comes from.
**ticket** — One unit of work, kept as a file with its own history, spec and stage; nothing gets worked on unless it is a ticket. This project has exactly two so far, T-1 and T-2.
**stage** — One step in a ticket's route — researching, planning, building, verifying. A ticket sits in exactly one stage at a time, and the stage it is in is what decides what happens next.
**pipeline** — The fixed sequence of stages a ticket walks through, chosen by its type. A research ticket's pipeline is a different, shorter sequence than a build ticket's.
**spike** — A ticket type whose job is to answer a question, not to ship code: research it, write it up, recommend, then wait for a human ruling. T-1 is one.
**gate** — A named stopping point where a ticket cannot move on until it is cleared. Each gate is configured either as "a person must clear this" or "clears itself".
**gate policy** — The per-gate setting deciding who clears it — a human, or unattended (it clears itself with nobody looking). In this repo the spec and the final sign-off need you; merge and deploy clear themselves.
**final sign-off** — The last of the two points in this repo where you personally must approve before work counts as done. The other is approving the written spec before the build starts.
**spec_ready** — The gate where you approve a ticket's written spec — the statement of what "done" means — before anything is built against it.
**intake** — The first stage of a ticket's route: created, but not yet worked. T-2 is parked there.
**sp-investigate** — The stage of a research ticket where the actual investigation happens. "Send it back to sp-investigate" means ordering more research before you rule.
**sp-decide** — The stage where a research ticket waits for your ruling. T-1 has been sitting there for two days, and nothing else in the project moves until you rule.
**sp-spawn** — The step immediately after your ruling, where whatever you decided gets turned into the actual build tickets.
**recommend-and-wait** — The setting on T-1 saying the research may recommend but may not decide. That is why a finished investigation is still sitting still.
**evidence** — The proof that a stage's work actually happened, recorded as a location — a file path, a commit, test output — never as a claim like "looks good". A stage is only allowed to advance on evidence.
**validator** — A mechanical check that a stage produced what it was supposed to: does the file exist, did the tests run. It deliberately judges nothing about quality.
**handoff** — The working note one stage leaves for the next — what was done, what was touched, what surprised it, what comes next. It is how a fresh session resumes a ticket without you re-explaining anything.
**passport** — A short summary kept inside the ticket file of everywhere the ticket has been and what each stage decided.
**ledger** — The ticket files plus the running event log — the tool's record of everything it has done. It is append-only, which is why two machines writing to it separately collide.
**append-only log** — A file the tool only ever adds new lines to the end of, never edits or reorders. Two machines each appending their own lines produce a conflict rather than a merge.
**board** — The generated status view of every ticket and the stage it is in. It is regenerated from the ticket files, never hand-edited.
**shop** — This repo's whole process setup: which gates need a human, which models get used, whether lean is on, and who the operator is. One repo, one shop.
**preset** — A ready-made bundle of shop settings picked once at setup; this repo took the "solo-builder-review" one. Everything it chose for you can be changed afterwards.
**operator** — The human the tool records as the real decision-maker behind every approval. Here that is you — recorded as human:owner, not as the "Corgea" git identity.
**worker** — A separate background AI session the tool starts to carry out one stage of one ticket. Each one costs money and runs on whichever model it is given.
**seat** — The role a stage's work gets done by — coder, reviewer, QA — each carrying a default model tier. The T-1 research also used "seat" for each separate investigating session it ran.
**roster** — The mapping from seats to the agents and models that actually staff them. This repo's roster folder is empty, so every worker just inherits whatever model the session was already running.
**modifier** — An optional tag on a ticket that inserts extra stages into its route. Adding the "design" modifier, for example, puts a design pass and a design review in front of the build.
**lean** — A shop setting that trims process ceremony for small work: short planning notes, no separate copy of the repo, trivial steps done inline instead of by a separate worker. It is on here because the preset turned it on, not because anyone chose it.
**isolated checkout** — A second copy of the repo on disk that a build works inside, so half-finished changes cannot disturb the files you are looking at. Lean drops it for small changes and builds in place.
**verify** — The stage meant to install the project cleanly and run its whole test suite before code is accepted. This repo has no test runner, so today there is nothing for it to run.
**merge** — Folding a finished branch of work into the repo's main line. In this shop the merge gate clears itself, with no human looking at it.
**deploy** — The final gate of a build route, also set here to clear itself. In a repo with nothing to deploy it is currently a formality.
**branch** — A parallel line of the project's history in git; work on a branch leaves the main line untouched until someone merges it. All of the T-1 research sits on one.
**sha256 fingerprint** — A checksum of a file's exact bytes, recorded as evidence that a specific version of it was what a stage produced. Change one character and the fingerprint no longer matches.
**token** — The unit AI usage and billing is counted in — roughly a fragment of a word.
**Opus** — The most capable and most expensive Claude model. Every worker on this project so far has run on it.
**Sonnet** — The cheaper mid-strength Claude model — what the lighter stages are meant to use.
**claude-fable-5** — The model the tool reaches for by default when a stage is marked as needing the top tier. You may not have access to it, in which case Opus is the fallback.
**doctor** — The setup checker you can run against this repo to confirm it is safe to leave running unattended. It currently reports 18 passes and one warning.
**regulated process template** — A stricter built-in route meant for compliance-heavy work, which this repo never uses. It is the source of the one warning the setup checker always reports.
**plugin** — The AutoDev add-on installed on this machine that holds the actual process machinery. The repo itself only holds your settings, your tickets and your notes.
**watcher** — A background service on this machine that keeps an eye on your enrolled repos and logs when work stalls. It is what noticed T-1 had been waiting 40 hours.
**monitoring** — The activity reports written out per machine by that background service. Yours currently arrive under two different machine identities, one from the Windows box and one from here.
**install id** — The per-machine name stamped on those reports, worked out once at setup and then cached. On this machine it resolved to "corgea" rather than "the owner".
**.autodev/outbox/** — A folder inside this repo the tool can drop plain notification files into, one per event. It is the notification route that needs no accounts, tokens or secrets.
**work block** — One continuous stretch of tracked activity, ended as soon as there is a gap longer than the idle setting. Time spent inside a long background worker run falls outside them, which is why the recorded hours are far too low.
**lockfile** — A file pinning the exact version of every dependency, so a fresh install rebuilds the same thing every time. This repo has none.
**kb/** — This project's durable written notes — what is happening now, plus one page per subject — kept in the repo so any session starts with the same context you have.
**kb/index.md** — The one-page pointer table at the front of those notes, saying which page covers what. Every session reads it before anything else.
**spikes/** — The folder holding throwaway investigation work: code written only to answer a question, plus the findings and measurements it produced. It is 2.9 MB and currently uncommitted.
**autodev/instructions/build.md** — An optional plain-text file of standing notes that any session doing build work would read before it starts. It does not exist in this repo yet.
**autodev/agents/review.md** — An optional plain-text file that sets the tone and priorities of any session doing review work. It does not exist in this repo yet.
**kb/notes/setup.md** — The file in this repo that explains how to set this project up on another machine.

## This project

**autoSQL** — This repo: a tool where you pick data and how to view or transform it, and it generates the SQL underneath — built standalone first, meant to move into GIMS later. It currently contains no source code at all, only research and process files.
**GIMS** — Your existing system that stores records and shows dashboards over them. It is the eventual home for autoSQL, and the system the research measured.
**GUTS** — Your other, larger project. One folder inside it holds a second copy of GIMS, and that copy is the only one with the Postgres layer.
**the two trees** — The two copies of GIMS on this machine. The expression code is byte-identical in both, but only the copy inside GUTS has the Postgres migrations, indexes and query code — so anything about the database has to be read there.
**T-1** — The first job: the finished investigation into whether GIMS's dashboard formula language can be turned into Postgres SQL. It is written up and waiting only on your ruling.
**T-2** — The second job: a runnable demo of the picking screen over a database of made-up records, which you said must happen before autoSQL goes into GIMS. It has not started.
**the expression language** — The small formula language GIMS dashboards use to define a derived column, a filter or a sort — adding two fields, comparing one to a number, calling a function like max or length.
**expression AST** — The parsed, tree-shaped form of one of those formulas, which GIMS builds before evaluating it in Python. "Compiling" it means walking that tree and writing out equivalent SQL.
**the compiler** — The throwaway program the research wrote to turn those formula trees into SQL. It was built to answer a question, not to ship, and all three reviewers said it must never ship as it stands.
**pushdown** — Making the database do the filtering, sorting and limiting, instead of pulling rows into Python and doing it there. That is the whole idea the first job was testing.
**MAX_SCAN** — The 20,000-row limit in GIMS's dashboard code: it pulls at most that many rows into Python, filters them there, and flags the widget "Result capped for performance".
**the fixture** — The 130 saved test cases already in GIMS that pin down what each formula should evaluate to. The prototype's SQL matched all 130 of them exactly.
**conformance harness** — The script that ran each of those 130 cases through both Python and SQL and compared the two answers. Its "they disagreed" and "it would not compile" branches have never once actually run.
**divergence** — A case where the SQL answer and the Python answer differ. The dangerous kind is the silent one: a wrong number with no error attached.
**KNOWN_DIVERGENCES** — The list inside the prototype naming the places its SQL is known to disagree with Python. Six of its seven entries describe cases the 130-case fixture never tests.
**construct** — One piece of the expression language — an operator, a function, or a way of naming a field.
**the limited version** — The middle option at your ruling, also called CONDITIONAL-GO: compile only the part of the formula language the research could vouch for, and refuse everything else out loud rather than quietly guessing.
**the limited feature list** — The set of features that limited version would compile — 32 of 48 language features and 7 of 22 functions, covering 68 of the 130 test cases — with the other 62 refused. It is also called the subset.
**NO-GO** — The recommendation on record: do not fund this build on the evidence as it stands. It does not say the translation is impossible, and it does not throw the work away.
**GO** — Build it exactly as originally scoped. All three reviewers found this option unavailable on the evidence.
**the panel** — The three independent reviewers who judged the same evidence against the same bar at the end of the research. They split two-to-one, and the split was reported rather than averaged away.
**E1** — The proposed correctness experiment: re-run every test battery with the formulas restricted to the limited feature list, at a pass bar of zero wrong answers of any kind.
**E2** — The proposed speed experiment that nobody has run yet: today's Python path against the compiled path, on the same data, at 20,000 / 100,000 / 1,000,000 rows.
**fallback** — When the database cannot do a piece of the work and the code quietly does it the old way in Python instead. The research's one non-negotiable was that this must always be reported, never silent.
**resolve()** — The single function a dashboard widget calls to get its rows. It can only hand back the rows, a count and a "we stopped early" flag — there is nowhere in its answer to say "I had to fall back".
**widget** — One panel on a GIMS dashboard: a data source, an optional derived column, a filter, a sort and a limit.
**noun source** — A dashboard widget fed by every record of one type, such as all "tickets".
**verb source** — A dashboard widget fed by the logged history of runs of some action.
**query source** — A dashboard widget fed by a saved keyword search that sweeps several kinds of data at once.
**collection** — A named group of records inside GIMS's storage — roughly one noun type, such as all proposals or all ledger records.
**shared instances table** — The one table in GIMS that holds records from many collections together. It is the only one of GIMS's four read paths that generated SQL could actually filter.
**heartbeat / firehose** — The high-rate machine-generated data this project was originally pitched at. No such data exists in either copy of GIMS today, and the largest real collection found was 17,148 rows — under the 20,000 cap.
**acceptance test** — The test something has to pass before anyone is allowed to ship it. The open question is whether the 130 saved cases count as one for a SQL version of this language.
**audit pass** — A review round in which someone re-read the research against its own raw files and corrected whatever did not hold up. The first job had four of them, and the last one cut the limited version's coverage from 84 cases to 68.
**test battery** — One self-contained script that hammers a single area — dates, number overflow, Unicode text — looking for cases where the SQL answer and the Python answer differ.
**docker compose** — A single config file that starts a database inside a container, so the demo would bring its own Postgres rather than needing one already installed on the machine.
**HTTP 500** — The server's generic "something crashed" reply. For a dashboard it means the widget shows an error instead of any data at all.

## Databases and SQL

**Postgres** — The database engine GIMS's records live in, and the one autoSQL would be generating queries for.
**jsonb** — Postgres's binary format for storing JSON documents. It is faster to query than plain text, but it does not keep a record's keys in their original order.
**JSON-path matching** — Postgres's built-in way of asking whether a JSON document satisfies a path expression such as `$.score < 7`, without unpacking the document in application code.
**index** — A separate lookup structure Postgres keeps beside a table so it can find matching rows without reading every row.
**index expression** — An index built over a computed value rather than a plain column — over "field a plus field b", say. Postgres only allows one if every function involved is declared IMMUTABLE.
**GIN index** — The kind of index GIMS already has on its JSON column. It went unused in all 36 query plans the research measured, because that index type does not support the comparison operators the generated SQL needs.
**B-tree** — The ordinary sorted index type, and the shape autoSQL would actually need — one per combination of collection, field and extractor.
**seqscan** — Postgres reading every row of a table in order instead of using an index. Forcing Postgres to avoid it changed none of the 36 query plans the research measured.
**query plan** — Postgres's own printout of how it intends to run a query — which indexes it will use, or whether it will read the whole table.
**IMMUTABLE / STABLE** — Labels on a SQL function telling Postgres how far it can trust the result. IMMUTABLE means "the same input always gives the same answer", which lets Postgres pre-store results inside an index; STABLE is weaker and blocks that.
**GUC** — Postgres's name for a setting you can change per connection at runtime, rather than one fixed when the server starts.
**extra_float_digits** — One of those settings, controlling how many digits Postgres prints when it turns a floating-point number into text. The whole 130-of-130 result was measured with it pinned to 1, and 68 of the 130 cases pass through a floating-point value on the way.
**float8** — Postgres's 64-bit floating-point number type, the same shape as a Python float. It carries about 15 to 17 significant digits and cannot represent every decimal exactly.
**xpr.f8 / xpr.num** — Helper functions the prototype installed inside the database to imitate Python's number handling. Both have defects: f8's overflow guard is set at 297 digits where it needs 309, and num rejects non-ASCII digits that Python accepts.
**window** — A calculation that looks at a row together with its neighbours — a rolling average, or whether the value changed from the previous row — instead of at that row on its own.
**top 50 recall** — Of the 50 rows that should have been in an answer, how many actually came back. Under GIMS's 20,000-row cap that is 100 / 88 / 38 / 4 percent at 20k / 25k / 100k / 1M rows.
**SQL injection** — A bug where text someone supplied ends up read by the database as part of the query itself, rather than as a plain value.
