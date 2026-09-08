---
name: lessons
description: Durable lessons this project has learned (seeded stub — fill me in)
type: reference
---

# lessons

Seeded stub (FAC-123): durable lessons land here as the project runs — one entry per lesson, newest first, each citing the ticket/incident it came from.

---

## A check that never ran reads exactly like a check that passed

*Four instances in this project, all four found on 2026-09-08 by someone re-driving a path
for an unrelated reason. None was found by reading the code, and none was found by the
check itself.*

**The class.** A verification step that does not execute is indistinguishable, in its
output, from one that executed and found nothing. Zero checks run renders as zero failures
found. Every instance below is the same sentence with different nouns, and in every one the
*detecting* half was present and correct — what was missing was any assurance that it ran.

### The four witnesses

| | the instrument | what did not run | how it read |
|---|---|---|---|
| **1** | `proto/conformance.py` | three of four outcome branches, **0 executions** across a full run | every conformance headline in the record, from a rig whose failure surface was dead. Found only because the owner asked for the check directly (**Q4**) |
| **2** | T-4's §6.1 negative control | the exclusion clause was asserted by calling `aggregate()` on a hand-built list — a **unit test of a helper**, which §6.1 rules out in as many words — while the real path in `run_cell` stayed dead | a passing control, over the very code it existed to prove |
| **3** | §8.2's mutation pass (`--only <typo>`) | the whole pass: an empty selection | `0 of 0`, then *"Every criterion was watched failing against its own mutant"*, **exit 0** |
| **4** | the digit mapping (T-21) | the **39** cases comparing `xpr.num` against the Python evaluator, behind `@needs_db` on a DSN nothing set | `8 passed, 50 skipped` — green. A Unicode bump would fire the staleness guard, you regenerate, the guard goes green, and **not one Unicode digit was ever compared between the two engines** |

### A fifth member, and it is a different one

| | the instrument | what did not run | how it read |
|---|---|---|---|
| **5** | `ops/name-check.sh` (T-14's rule) | **nothing** — the check's failure path works perfectly; **no hook, no CI, no suite invoked it** | a sound guard, documented as `ops/name-check.sh && git push`, i.e. someone remembering to type it. The name reached `origin/main` anyway |

**The first four are checks whose failure path never executed. This one's failure path is
fine — the invocation was missing.** Same family, and worth separating, because a reader who
has only met the first four will look for a dead branch and find none.

**It has a precursor worth naming too:** the arrangement it replaced was an inline
`git grep … ; echo … && git add …`, where the grep *fired* and its exit status was never
consumed. So the sequence was: a check that ran and was discarded → replaced by a better
check that nothing called. **Both are the same failure at different distances from the code.**

**The test:** *what would have to break for this check to stop protecting me, and would I
notice?* If the answer is "someone stops typing it", it is not a guard yet.

**Its first catch was its own author, on the day it was written.** With the guard now invoked by
the suite, the next commit was refused — because `demo/tests/test_owner_name_absent.py` used the
owner's name **literally** as its probe fixture, so the check correctly flagged its own test file.
Two things made that a good outing rather than an embarrassing one: the commit was **chained with
`&&`**, so the refusal actually stopped it (the failure hours earlier was a `;` that let the push
through), and the fix was to **assemble** the probe (`"ev" + "an"`) so the file never contains the
token while the test still drives the real pattern. **A guard whose first catch is the person who
wrote it, minutes after writing it, is a guard that works** — and it is a reminder that the author
is inside the blast radius, not above it.

**Instance 2 is the sharpest and instance 4 is the most instructive.** Number 2 is a control
whose job was proving failure paths fire, and its own failure path could not. Number 4 shows
the class survives having a *correct, running* guard next door: detection worked perfectly,
and detection is not verification. **"The guard fired and I fixed it" is not evidence the fix
was right.**

### What to do about it, since naming a class is not a practice

- **Drive the empty case on purpose.** Ask the instrument for nothing — no matching id, an
  empty selection, a filter excluding everything — and require it to **refuse**. `--only M17`
  exits 2 now.
- **Make "nothing happened" and "everything passed" different outputs.** Different exit
  codes, different sentences. Where a skip is legitimate (no Postgres on this machine), keep
  the skip and print a **disclosure above the summary**, so the count and the caveat cannot
  be separated by a copy-paste — `runtime/tests/conftest.py`, and `run-demo`'s §8.2 line.
- **Prove green before you allow red.** A criterion that was already failing proves nothing
  by failing again. The mutation pass's KILLED / SURVIVED / **INVALID** triple is this, and it
  caught eight bad mutants of mine on its first run.
- **Watch it fail, and keep the exercise.** `.autodev/evidence/T-18/watched-failing.mjs`,
  `.autodev/evidence/T-21/watched-failing.sh`, `.autodev/evidence/T-17/watched-failing.sh` —
  each breaks the thing on purpose and asserts the guard reacts, re-runnably.
- **Put the invocation where it cannot be forgotten, and prefer the one that travels.**
  A `.git/hooks/` hook does not travel with the repo, so a fresh clone is unprotected —
  the case that matters for a public one. With no CI in this repo, the suite is the thing
  that both travels and always runs: `demo/tests/test_owner_name_absent.py` *runs the
  script* rather than reimplementing it, so one implementation is checked and the test also
  fails if the script itself breaks.
- **Give a known failure a name, a reason and a ticket, and give a NEW failure a different
  exit code.** Otherwise the known red masks the new one and the whole check becomes noise —
  `EXPECTED_SURVIVORS` in `demo/tests/mutation_pass.py`.

## The procedure transfers; the proof does not

*2026-09-08 · ruled while approving T-22's `.jsx` edit · the precedent is T-16*

**T-16 rebuilt digest-covered `.jsx` bundles and could say the rebuild was safe *because the
bundles came back byte-identical*.** That worked because T-14 had only reworded two comments:
any bundle change at all would have meant something unintended happened. It is a genuinely
strong proof — for that change.

**It is unavailable to the next change, and its absence proves nothing.** T-22 adds
`data-tour` attributes to about eight controls. That *legitimately* changes the bundles. A
session reaching for "byte-identical" out of habit gets a failure it cannot interpret: the
check fails, and it fails for a good reason, and nothing distinguishes that from the bad one.

**So: reuse the steps, re-derive the evidence.** The procedure carries over unchanged — edit
the `.jsx`, run `./run-demo build-ui`, re-baseline `manifest.json`. What has to be rebuilt for
each change is the *argument that the rebuild did only what was intended*:

| change | the proof that fits it |
|---|---|
| comments reworded (T-16) | bundles **byte-identical** — any diff is a defect |
| attributes added (T-22) | **diff the bundles** and show the change set contains only the added attributes |

**The general rule: a borrowed procedure comes with a borrowed proof, and the proof is the half
that expires.** When you inherit a runbook, ask what its evidence step was *establishing*, and
whether your change still makes that the right question. Ask it before running the check, not
after it goes red.

## A citation to "the plan" is not a citation to the spec

*2026-09-08 · found while starting plan §8.2's mutation pass · `.autodev/notes/plan-8-2-mutation-pass-citation.md`*

**This shop writes two documents per ticket and both have numbered sections.** For T-2 they
are `.autodev/specs/T-2.md` (the **spec**) and `.autodev/specs/T-2-plan.md` (the **plan**),
1,486 lines, a different document. Both have a `## 8`. The spec's §8.2 is *The table*; the
plan's §8.2 is *The mutation pass*. **Checking one is not checking the other.**

Six live files cite "plan §8.2" for a sixteen-mutant pass. A session read the **spec's** §8.2,
found a `CREATE TABLE`, checked several more places, and concluded the citation was broken and
the sixteen mutants had never been specified. Every individual check it ran was accurate. It
simply never opened the document the citation named. The proposed remedy — author sixteen
substitute mutants and "correct" six correct citations — would have replaced a real
specification with an invented one and then satisfied it.

**Before concluding a citation is broken, resolve the noun.** `spec`, `plan`, `locate` and
`handoff` are four different artifacts here, they live side by side in `.autodev/specs/` and
`.autodev/handoffs/`, and a section number means nothing without the document.

### Two search habits this exposed, both general

1. **Never conclude absence from a truncated search.** The grep that "proved" the mutants were
   undefined *did* glob the plan; `| head -10` discarded the hit. A `head` is fine for looking
   around and fatal for a negative conclusion — for absence use `-c`, or no limit, or name the
   file directly.
2. **In this repo, missing from `git log` is not missing from disk.** `adf23bf` shows as
   *deleting* `.autodev/**`; it untracked that directory from the public repo and left every
   file in the working tree. Around thirty `.autodev/` paths are cited by live files and all of
   them still exist. Reasoning from git history alone yields a confident story about a destroyed
   document — and, next, a fabricated reconstruction of it.

**The habit that saved it:** refusing to write a substitute for a specification that could not
be found, and saying so, rather than producing something shaped like the missing thing. A review
cannot catch a fabricated citation when it has been handed the same wrong document.
