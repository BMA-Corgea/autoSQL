---
name: lessons
description: Durable lessons this project has learned (seeded stub — fill me in)
type: reference
---

# lessons

Seeded stub (FAC-123): durable lessons land here as the project runs — one entry per lesson, newest first, each citing the ticket/incident it came from.

---

## The instrument that checks for dead failure paths is a program with failure paths, and nothing checks its

*2026-09-08 · found implementing plan §8.2's mutation pass (T-19) · third instance in this project*

**`./run-demo test --mutants --only M17` printed this, and exited 0:**

```
mutation pass: all 0 anchors resolve, exactly once each.
mutation pass: 0 killed, 0 SURVIVED, 0 INVALID, of 0
Every criterion was watched failing against its own mutant.
```

A typo in a mutant id selected nothing, and the tool built specifically to catch vacuous
greens reported a vacuous green — with a sentence claiming the opposite of what happened.

**This is the third time this project has met the same shape, and that is why it is here
rather than in a commit message.**

| | the instrument | its own dead path |
|---|---|---|
| 1 | `proto/conformance.py` | three of four outcome branches had **0 executions** across a full run — every conformance headline came from a rig whose failure surface was dead. Found only because the owner asked for the check directly (**Q4**) |
| 2 | T-4's §6.1 negative control | the exclusion clause was asserted by calling `aggregate()` on a hand-built list — a **unit test of a helper**, which §6.1 rules out in as many words — while the real exclusion path in `run_cell` stayed as dead as conformance.py's branches |
| 3 | §8.2's mutation pass | `--only <typo>` → empty selection → "0 of 0" → *"Every criterion was watched failing"* → **exit 0** |

**The class:** *a checking instrument is a program, its failure and empty paths are code, and
being the thing that checks does not exempt it from being checked.* Instance 2 is the sharpest:
the control that exists to prove failure paths fire had a failure path that could not fire.

### What to actually do, since naming a class is not a practice

- **Drive the instrument's empty case on purpose.** Ask it for nothing — no matching id, an
  empty selection, a filter that excludes everything — and require it to **refuse**, not to
  report success over an empty set. `--only M17` now exits 2.
- **Never let "nothing happened" render as "everything passed".** The two must be different
  exit codes and different sentences. Zero checks run is not zero failures found.
- **Watch the instrument fail before believing it.** `.autodev/evidence/T-18/watched-failing.mjs`
  and the KILLED/SURVIVED/**INVALID** triple in the mutation pass are both this: a criterion is
  proved green *before* it is allowed to go red, so a test that was already broken cannot be
  counted as a catch.
- **A permanently-red check is a check on its way to being deleted.** Give known failures a
  named list with a reason and a ticket each, and a *distinct* exit code for a NEW failure —
  otherwise the known red masks the new one and the whole thing becomes noise.
  (`EXPECTED_SURVIVORS` in `demo/tests/mutation_pass.py`.)

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
