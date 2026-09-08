---
name: lessons
description: Durable lessons this project has learned (seeded stub — fill me in)
type: reference
---

# lessons

Seeded stub (FAC-123): durable lessons land here as the project runs — one entry per lesson, newest first, each citing the ticket/incident it came from.

---

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
