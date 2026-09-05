# T-3 · Synthesis — what the correctness run found, and the choices it leaves

Stage: `sp-synth` · seat: analyst · written 2026-08-22.
Built from `spikes/T-3/FINDINGS.md` (the investigation; verdict in its §10), the 29 raw output
files in `spikes/T-3/out/` (headline claims spot-checked against them for this document), and the
bar fixed in advance in `spikes/T-3/FRAMING.md` §3.

**This document recommends. It does not decide.** The decision is the owner's, at the next stage
(`sp-decide`). Nothing here clears that gate.

---

## 1. The answer

The question T-3 was funded to answer: if we keep only the safest third of the dashboard
expression language — 32 of its 48 building blocks, just seven functions, no dates, no text
operations, no rounding — does the SQL that autoSQL generates ever give a different answer than
the Python code GIMS runs today? The bar, set before any evidence was collected, was **zero wrong
answers**, tested at each of three Postgres output settings (explained in §2).

**The answer is: yes, it gives wrong answers — at all three settings, including the one production
would use. The run FAILED the bar.** And it failed it honestly: the test rig was first proven able
to report a failure at all (it was deliberately fed ten known-wrong cases and caught every one),
and the one bug we already knew about — a mistyped guard number, twelve digits too short — was
fixed *first* and is confirmed not to be the cause. These are new, different problems.

**The clearest single example.** The largest number any GIMS program on this machine has ever
stored is `1,787,169,706,037` — a timestamp, counted in milliseconds. Ask the SQL path for "that
timestamp plus zero" and, at the stingiest of the three output settings, it answers
**`1,787,169,706,040`** — three milliseconds late, with no error and no warning. Python answers
`...037`, correctly. That is real GIMS data, an in-subset expression, and a silently wrong number
(`out/timestamp_witness.txt`).

One honest qualifier on that example, up front: it only happens at that one setting, and
production would pin the setting that gets it right. The failures that survive even the *right*
setting are different — quieter — and they are what §2 explains.

**What it means for the plan, in one line:** under the rule the owner himself confirmed on 2026-08-22
— *nothing enters GIMS until T-3 and T-4 both pass* — the road into GIMS stays shut, now on
evidence rather than caution. What is on the table is whether to abandon that road, repair it and
re-test, or redraw the rule. §5 lays out those options; §6 recommends one.

---
## 2. What actually goes wrong, in plain terms

Two ideas make everything below readable.

**How the test works, and what "wrong" means.** Every test asks the same question two ways — once
through GIMS's Python evaluator (the thing running today) and once through the SQL translation —
and compares the answers. A disagreement is sorted into four kinds, called **classes**:
**class 1** — both sides answer, and the numbers differ; **class 2** — Python has a value, SQL
returns null (empty), so a dashboard cell goes blank or a filtered row silently disappears;
**class 3** — the reverse, null becomes a value; **class 4** — Python crashes with an error while
SQL confidently returns a number. Separately, there are **refusals**: cases where the SQL query
deliberately *dies with a named error* instead of answering. Under the ruling the owner delegated and
later confirmed, a refusal is allowed — it is loud, a caller can see it and fall back to Python —
so refusals are counted on their own line and are not wrong answers. Everything in this section is
a genuine wrong answer, not a refusal.

**The "float-digit setting".** Postgres has a session knob, `extra_float_digits` ("efd" for
short), that controls how many digits it writes out when turning a stored floating-point number
into text. That sounds cosmetic. Here it is not: the compiled SQL passes every intermediate number
through that text form — the **value channel**, the path the actual numbers travel on, not just
how they are displayed. So the knob changes the numbers themselves. Its three settings were all
tested, per the owner's own requirement (Q10): `1` (full precision, up to 17 digits), `0` (15 digits),
and `-3` (12 digits).

### Mechanism one — the Unicode-digit gap (fails at every setting, including the right one)

The expression language does **coercion**: it quietly converts values from one type to another,
most importantly strings into numbers — the string `"123"` is treated as the number 123. The gap:
Python's converter accepts *any* characters the Unicode standard classifies as digits. That
includes full-width digits like `"１２３"` (as an East-Asian keyboard or form produces them) and
Arabic-Indic digits like `"١٢٣"`. The SQL runtime's converter accepts only the ASCII digits 0–9.
So on the same stored string, Python reads a number and SQL reads "not a number", which becomes
null.

A worked example from the run. A record holds `b = "１２３"`. The expression
`coalesce(min($.b), 0.1)` means "the smallest value of `b`, or 0.1 if there is nothing there".

- Python: converts `"１２３"` to 123, answers **123.0**.
- SQL: cannot convert it, gets null, falls through to the default, answers **0.1**.

A dashboard would display 0.1. No error is raised anywhere. The same gap also hits filters: a
comparison fed through it returns null instead of true/false, and the row **silently vanishes**
from the result. Every wrong answer the run found on ordinary-shaped and text-heavy data — at
every setting — traces to this one gap.

One more thing this mechanism did: it **broke a prediction**. The framing expected that
restricting to the 32 "safe" constructs would drive the broad test batteries to zero, because
every construct previously blamed for disagreements is outside the subset. It did not, because the
gap does not live in any construct — it lives in the shared string-to-number routine that
in-subset arithmetic, comparisons, `min`/`max`/`count` and `coalesce` all pass through. T-1's
per-construct blame analysis was too coarse. Cutting constructs cannot cut this out.

### Mechanism two — the value channel truncates numbers (fails at settings 0 and −3)

At setting 0 the value channel carries at most 15 significant digits; at −3, only 12. Any
intermediate number that needs more digits than that gets silently rounded to a **different
number**. The timestamp in §1 is this mechanism: `1,787,169,706,037` has 13 significant digits,
which fits in 15 (so setting 0 gets it right) but not in 12 — so setting −3 rounds it to
`...040`, three off. Bisection put the first wrong numbers at magnitudes as small as **about 4.16
billion** at setting 0 and **about 3.22 billion** at −3 (`out/A2_boundary_after.txt`) — those are
witnesses along one search path, not exact frontiers, because what fails depends on the digits a
value happens to have, not just its size. At setting 0 the same truncation also nudges values
*past* the safety guard mid-expression, producing 37 spurious refusals in one battery.

**This mechanism has a real fix**: pin the setting. At setting 1 the channel carries full
precision and the run confirmed the truncation disappears entirely. A production deployment would
have to force `extra_float_digits = 1` on every session and treat anything else as a
configuration defect.

### Two more, at the edges

**Containers compared exactly (fails even at setting 1).** When an expression returns a whole list
or object rather than a single number, the contract's own comparison rule allows no tolerance
inside it — and Postgres's `jsonb` storage keeps numbers as exact decimals where Python holds
floating-point approximations. Very large numbers (roughly 1e17 and up) inside a returned list
therefore compare as unequal even when both sides are "right" in their own arithmetic. 32 of the
36 wrong answers in the extreme-values battery at setting 1 are this shape. The investigation is
explicit that this is **as much a defect of the comparison rule as of the compiler** — but under
the definitions fixed in advance it counts as class 1, and it was counted, not explained away.

**Rows written by anything other than GIMS's Python ("raw mode").** If some other program — an
ETL job, a database script, another service — writes rows, those rows can hold values Python's own
writer never produces, and there the two sides split further: a number like 1e-400 is exactly
stored by Postgres but collapses to 0.0 in Python (so `if($.a, 1, 2)` disagrees); giant integers
near 2^53 collapse in Python but not in SQL; and one genuinely new discovery — a **ninth,
previously uncatalogued place the Python evaluator itself crashes** (`OverflowError` on a
400-digit JSON integer) while SQL answers cleanly. That last one is class 4, the kind the project
worried the instruments could not even see. These raw-mode findings come from directed single-case
probes, not broad random testing: the failures are real, but their *rates* are unmeasured.

### The counts

Per setting, summed across the three 4,000-draw batteries (~11,367 expressions actually ran per
setting; per-battery detail is in FINDINGS §5 — these sums exist only to make the row readable):

| setting | class 1 (different value) | class 2 (value→null) | class 3 | class 4 | named refusals |
|---|---:|---:|---:|---:|---:|
| efd 1 (production would pin this) | 39 | 16 | 0 | 0 in Python-written data; found in raw-mode probes | 9 |
| efd 0 | 101 | 15 | 0 | same | 45 |
| efd −3 | 105 | 16 | 0 | same | 9 |

Zero unexplained SQL errors anywhere. Zero null-representation leaks. The refusal machinery worked
exactly as ruled: every refusal named, identifiable, and counted.

---
## 3. How much does it matter?

This is the section to read slowly, because the honest answer is "it depends on facts about your
data that this run did not measure".

**The biggest qualifier first, stated plainly: the headline mechanism — the Unicode-digit gap —
only fires if strings containing non-ASCII digits (like `"１２３"` or `"١٢٣"`) actually occur in
your data, and this run did not measure whether they do.** No sweep on the record looks at the
*characters inside* stored strings. What T-1 did measure (its §D.6) is that string-to-number
coercion in general is exercised repeatedly by your real data — so the road to the gap is
travelled — but whether any traveller carries non-ASCII digits is unknown. So the run has proven
"**this can happen**". It has **not** proven "**this will happen to you**" — and it has not proven
the opposite either. Burying that distinction would make the rest of this document dishonest, so
it sits here, at the top of the section.

With that said, here is how each mechanism maps onto reality:

- **At the setting production would pin (efd 1), on data shaped like today's, the measured wrong
  rate was small and specific.** The ordinary-data battery: 2 wrong in 3,801 (~0.05%) — both
  requiring a full-width digit string in the record. The text-heavy battery: 17 in 3,799 (~0.45%)
  — all the same gap. Zero refusals on either. The 130-case contract fixture passed 130/130
  before and after the guard fix (and the owner has already ruled the fixture is not, by itself, an
  acceptance test).
- **The truncation mechanism is fully avoidable** by pinning the setting — but the run also
  priced what failing to pin costs: wrong numbers on values as small as a few billion, including
  a real timestamp. Not theoretical; a deployment checklist item with a measured penalty.
- **The container mechanism needs magnitudes around 1e17 inside a returned list.** The largest
  number any GIMS writer here has ever stored is about 1.8e12 — five orders of magnitude below.
  But the standing answer Q15 aims autoSQL at high-volume data GIMS *does not hold yet* — data
  nobody has sampled — and the framing itself ruled that "unreachable in today's corpus" is not
  safety. Both halves of that are true at once.
- **The raw-mode failures are live only if something other than GIMS's Python writes rows.**
  Today, on this machine, nothing does. The territory autoSQL is aimed at (Q15) is exactly where
  such writers would appear. Whether any are planned is a question about the roadmap, not about
  this run.

**And the flip side, so the picture is not one-sided:** the refusal design worked (loud, named,
distinguishable, 0.24% on adversarial data at the pinned setting, zero on ordinary data); the
known guard bug is fixed and completely closed (its 20-path test went from 16 failures to 0);
and no wrong answer of the "null becomes a value" kind, and no unexplained SQL error, appeared
anywhere. The failure is real, but it is narrow, and most of it is either pinnable away,
convertible to loud refusals, or contingent on data shapes not yet observed.

---

## 4. What this does to T-1's ruling

T-1's ruling (2026-08-21, signed by the owner) was: **don't build the compiler into GIMS yet; fund two
experiments and let a build be earned from their results** — this correctness run first, then T-4,
a speed run. On 2026-08-22 he confirmed the boundary in his own words: nothing enters GIMS until
T-3 **and** T-4 pass.

**One of the two experiments has now reported, and it failed.** What that settles, and what it
does not:

**Settled:**
- The restricted subset, as scoped, is **not production-safe** — the zero-wrong-answers bar is
  failed at every setting. The GIMS gate stays shut, and it now stays shut on evidence, not
  caution.
- The guard defect T-1 found was real, was exactly the mistyped literal, and is now fixed —
  nothing else was hiding under it.
- The "loud refusal" ruling was implementable, and is implemented and proven.
- One piece of T-1's *analysis* was wrong in an instructive way: it assigned blame per construct,
  and predicted the subset would test clean. The blame actually lives in shared conversion
  plumbing that every construct uses. That corrects the research; it does not weaken the ruling
  (which was "don't build yet" — now reinforced).

**Not settled:**
- **Speed. T-4 has not run at all.** Nothing new is known about how slow the SQL path is; T-1's
  3.8×–7.2× measurement stands, unrefined.
- **The demo (T-2) is untouched** — it runs on invented data with both answers on screen, was
  authorised independently, and nothing here changes that.
- **Whether the translation is impossible.** No. 130/130 fixture agreement still stands, and the
  failures found have identified causes, several with identified fixes. What failed is *this
  subset under this bar today*, not the idea.
- **Whether a repaired runtime would pass.** Unknown until re-run — and this run found mechanisms
  T-1 never predicted, which recommends humility about what a next run would find.

The standing default in the T-3 handoff is that T-4 waits for T-3's *report*, and that a failed
T-3 leaves the timing run with nothing to time. Whether T-4 runs at all is therefore part of the
decision in front of the owner, not an automatic next step.

---
## 5. The options

Four roads, plus one cheap piece of homework that changes how good two of them look. Each option
gets its honest case — none of these is a straw man.

### Option A — abandon the SQL path

**Costs:** GIMS keeps its 20,000-row cap; dashboards over big collections stay truncated — the
completeness problem autoSQL exists to solve stays unsolved. The prototype work is written off
(T-1 already priced it as spent, so this is not new money).
**Buys:** certainty and zero further spend. No wrong-number risk, ever, because no generated SQL
ever runs.
**The honest case for it:** the bar was zero, it was set twice before any evidence existed, and
the subset failed it at every setting. The other experiment's territory already looks bad — T-1
measured the SQL path 3.8×–7.2× slower with the one classical cure (indexes) ruled out by the owner
himself. When both experiments point downhill, "let a build be earned" was designed to produce
exactly this outcome, cheaply. Stopping here is the system working.

### Option B — narrow the subset further and re-run

**Costs:** design work plus another bounded run (machine time is small — about 3 seconds per
4,000-expression battery; the whole run fit in a day). And one catch that must not be skipped:
**the headline mechanism is not a construct, so cutting more constructs does not remove it.** To
kill the Unicode-digit gap by narrowing, you would have to narrow the *data contract* — for
example, rule strings-as-numbers out of the language entirely, and/or rule out whole-container
returns. That is a visibly smaller language, and existing widget expressions that rely on
coercion would fall outside it.
**Buys:** possibly a subset that genuinely passes the unchanged zero bar, with no runtime
engineering at all.
**The honest case for it:** the failures cluster entirely in coercion and containers. A subset
with no string-to-number coercion and no container returns has no observed failure mechanism left
at the pinned setting, and T-3's instruments — already built, already proven able to fail — would
confirm or refute that cheaply.

### Option C — fix the two mechanisms and re-run

What "fix" concretely means, mechanism by mechanism:
- **Unicode-digit gap:** it cannot cheaply be made to *match* Python (Postgres's regular
  expressions have no equivalent of Python's any-Unicode-digit class), but it can be converted to
  a **loud refusal** — raise a named error whenever a rejected string contains non-ASCII digits.
  Under the standing ruling, a refusal is an allowed outcome.
- **Truncation:** pin `extra_float_digits = 1` per session/query. Cheap, proven effective by this
  run's own data.
- **Containers:** needs the compiled SQL to normalise numbers inside returned containers — a
  redesign the investigation priced but did not do. Alternatively, the owner can rule on the
  comparison-rule question (§2) — if tolerance inside containers is the contract's defect, the
  fix may belong there instead.
- **Raw mode:** the Python evaluator's own crashes are GIMS contract gaps; they need their own
  ruling about whether Python or SQL is the reference on non-Python-written data.

**Costs:** runtime engineering plus a full re-run; a higher refusal rate (every converted case
becomes a query that dies and falls back — on text-heavy data that could be visible, and its
frequency depends on the same unmeasured prevalence as everything else); and the risk that a
re-run finds a next layer — this run found mechanisms nobody predicted, twice.
**Buys:** the strongest correctness story available short of abandoning: *everything either
agrees or refuses loudly*, on the same zero bar, unchanged.
**The honest case for it:** the failure decomposes cleanly, every mechanism has an identified
cause, and three of the four have identified, bounded treatments. This is the "earn the build"
path continued, not restarted.

### Option D — accept the failures, with a documented carve-out

**Costs:** a written exception under the zero — "wrong answers are possible when non-ASCII digit
strings, or container values around 1e17+, occur" — which is precisely what the framing calls an
admission of silent wrongness. The failures stay undetectable at query time: no error fires, a
wrong number just appears. The project's founding purpose was preventing exactly this.
**Buys:** the fastest route to T-4 and, if T-4 passes, to the build. Zero engineering now.
**The honest case for it:** an operator can rationally accept a measured risk, and these triggers
may genuinely never occur in his data — nothing observed on this machine has ever contained one.
But today the trigger prevalence is *unmeasured*, so choosing D now means accepting an unmeasured
risk. The homework below turns D from a blind bet into a priced one.

### The homework that sharpens B, C and D — a small measurement first

A read-only sweep of the real data for strings containing non-ASCII digits (the same kind of
sweep T-1 already ran for magnitudes, extended to look inside strings), plus a one-question
inventory: *is anything other than the GIMS Python process ever going to write rows autoSQL
reads?* Hours of work, touches nothing, and it converts the single biggest unknown in this
document into a number. It is compatible with every option above and is cheapest before choosing
between them.

---

## 6. Recommendation

**This is a recommendation, not a decision. The decision is the owner's at `sp-decide`.**

**Recommended: do the small measurement first, then take Option C in its cheap form — pin the
float-digit setting, convert the Unicode-digit gap into a loud refusal, put the container
comparison-rule question back to the owner explicitly as its own one-line ruling, and re-run the same
batteries on the unchanged zero bar. Do not abandon yet; do not accept a carve-out yet. Hold T-4
until the re-run reports** (his own ordering — correctness first — and a failed correctness path
leaves nothing worth timing).

Reasoning:
1. The failure is real but **narrow and structured**: one mechanism that survives the pinned
   setting on ordinary data, one cured by a configuration pin, one that is partly a defect of the
   comparison rule, one contingent on writers that do not exist yet. That is a very different
   shape from "the translation is wrong all over", and it is a shape with treatments.
2. The treatments are mostly **conversions to loudness, not silent patches** — which is exactly
   the design philosophy the owner already ruled for. A re-run then re-tests the same bar with the
   same instruments; nothing about the target moves.
3. **The alternatives currently rest on the same missing fact.** Abandoning because of a
   mechanism whose trigger may never occur in this data, or accepting a carve-out for a trigger
   that may be common, are both bets on the unmeasured prevalence of non-ASCII digits. Hours of
   read-only sweeping buys that fact before any bigger money moves.
4. The instruments are built, proven able to fail, and cheap to re-run. The marginal cost of
   another honest answer is one day; the cost of a wrong go/no-go is the project.

**The weakest point of this recommendation, stated rather than hidden:** if the sweep finds
non-ASCII digits are *common* in real data, Option C turns those cases from silent wrong numbers
into frequent visible refusals — correct by the bar, but potentially a worse product than either
a properly narrowed language (B) or stopping (A). And even a fully passed re-run buys admission
to T-4, the speed run — not to GIMS. The speed question is untouched and T-1's measured 3.8×–7.2×
slowdown still stands on the other side of this decision. If the owner's appetite for the whole road
is gone on speed grounds alone, Option A is cheaper honesty than a passing re-run followed by a
failed T-4.

---
## 7. What is still unknown

The run's own named limits (FINDINGS §9), plus what this synthesis adds:

- **Non-ASCII digit prevalence in real data: unmeasured.** The biggest single qualifier on the
  result (§3). No sweep on the record examines the characters inside stored strings.
- **Raw-mode failure *rates*: unmeasured.** The raw-mode findings (including the ninth Python
  crash site) come from directed single-case probes, not a broad random battery. The witnesses
  are real; how often they would fire is unknown.
- **The truncation boundaries (~4.16e9 at setting 0, ~3.22e9 at −3) are bisect-path witnesses,
  not exact frontiers.** The first wrong value depends on a number's digit pattern, not only its
  magnitude.
- **Whether a repaired runtime passes: unknown until re-run.** This run twice found mechanisms
  nobody had predicted; a re-run could find a third layer.
- **Speed: entirely unknown beyond T-1's coarse measurement.** T-4 has not run. T-3 recorded its
  own wall clocks (~3 s per battery) only so T-4 can be planned from a measurement; no
  performance claim is made.
- **The refusal-rate line: deliberately not drawn.** The rates are produced (0.24% adversarial /
  0% ordinary at the pinned setting); where "too many refusals" sits is the owner's line to draw,
  per the framing.
- **The fixture's 130/130 says nothing beyond the fixture** (the owner's own Q2 ruling stands).

---

## 8. Evidence integrity — what this run changed under T-1's feet

T-3 was permitted (the owner's Q7) to edit T-1's instruments in place rather than fork them, and it
did: the guard literal in `spikes/T-1/proto/runtime.sql` was extended from 297 to 309 digits at
both sites and its out-of-range branch now raises the named error `XPR01` instead of returning
null; `spikes/T-1/analysis/fuzz/differ.py` now splits named refusals from unexplained errors and
parameterises the float-digit setting; `spikes/T-1/proto/conformance.py` likewise; the fuzz
generator gained the three subset profiles; and three battery scripts that had outputs but no
producing code were written. All committed in `5b91973`.

**T-1's written evidence stands untouched.** `spikes/T-1/FINDINGS.md` was verified for this
synthesis: sha256 `bcda73d652a7a7e5d513928601b5103e55e9dded11aef31ce085dc930c4a6273`, matching
the digest recorded at `spikes/T-1/.parts/README.md:52`. Nothing under `spikes/T-3/out/` was
edited after the run.

**But — stated plainly, because softening it would be a disservice — T-1's numbers can no longer
be reproduced byte-identically from the current instruments.** They now carry a bug fix and a
reporting split that T-1 ran without. Anyone re-running today's tools over T-1's cases gets
different numbers than T-1 published: the twenty-path guard battery T-1 recorded as 16-of-20
diverging now records 0-of-20, because the bug it was measuring is fixed. T-1's record remains
true *as a record of what the instruments did then*; reproducing it exactly requires checking out
the tree as of commit `01e75b0` (the last commit before T-3's edits). The before/after states this
run preserved (`out/A_range_before.txt` / `_after.txt`, `out/fixture_before_*` / `_after_*` at all
three settings) are the bridge between the two eras.

One clerical note on the source document: `spikes/T-3/FINDINGS.md` contains its §6 twice — an
editing slip; the two copies are verbatim identical (checked by diff for this synthesis), so no
number is affected.

---

*End of synthesis. Next stage: `sp-decide` — the owner's gate.*
