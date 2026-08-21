# `spikes/T-1/.parts/` — source fragments for `FINDINGS.md`

## `FINDINGS.md` is the authoritative document. This directory is not.

`../FINDINGS.md` is the document of record for the T-1 spike — the one that was read at the gate, the one
that carries a sha256 in the event log, the one Evan's 2026-08-21 ruling (`GA-3`) was made against. This
directory holds the **fragments it was assembled from**: one Markdown file per finding or cross-cutting
section, concatenated in order to produce `FINDINGS.md`.

**If the two ever disagree, `FINDINGS.md` wins.** Fix the fragment to match it, never the other way round.

## Assembly

Order, top to bottom:

`f0-header` · `f1` · `f2` · `f3` · `f4` · `xa-totality` · `xb-filters-sort` · `xc-fallback-register` ·
`xd-reachability` · `f5` · `f6-closure-log`

Each fragment is stripped of trailing blank lines and of a trailing `---` rule, then the fragments are
joined with a blank line, `---`, and a blank line. Verified on 2026-08-21: assembling the eleven files that
way reproduces `FINDINGS.md` byte for byte, except for the one gap noted below.

The other files here — `critic.md`, `consistency.md`, `closure-reports.md`, `verifications.json`,
`panel.json` — are **working records of the review passes**, not fragments. They are not part of the
assembly and must not be concatenated into it.

## Reconciled 2026-08-21

Some vocabulary first, because it is this spike's own shorthand rather than ordinary English. A **closure
pass** is a round where one worker per finding takes an independent reviewer's list of objections, re-checks
each against the raw data file it names, and edits the finding in place. A **seat** is one such worker. The
seat for Finding 2 died mid-run, so its six corrections were never applied.

On 2026-08-21 three of those six were applied to `FINDINGS.md` — but only to `FINDINGS.md`, leaving `f2.md`
still carrying the wrong text. Re-assembling from the fragments would have silently wiped the amendment.
This pass closed that:

- **`f2.md`** now carries all three corrections, copied from `FINDINGS.md` so the wording matches exactly,
  amendment markers (`[amend-2026-08-21]`) included: the scoped out-of-fixture summary row; the
  or/and/not recursion row at **333 / 333 / 332** operands (it had published 400 / 334 / 499, which were the
  *largest* chains that fit, not the first that fail); and **depth 63**, not 64, as the deepest surviving
  nesting (the parser adds one to its depth counter and *then* tests it, so 64 is only ever reached by the
  expression it rejects).
- **`f2.md` and `FINDINGS.md`** additionally got the §2.4 **heading** scoped, which the amendment round had
  missed — it still read "403 out-of-fixture probes, 403 agree".
- **`f5.md` and `FINDINGS.md`** got the matching §5.9 synthesis line scoped, for the same reason.

The 403/403 figure means the **value-domain kind probes** in `proto/coverage_probe_results.json` and nothing
wider. The separate out-of-fixture set in `proto/results.json → out_of_fixture_probes` is 8 probes: 3 agree,
4 diverge, 1 SQL error. Both counts were re-derived from the raw JSON during this pass.

`FINDINGS.md` sha256 after this pass: `bcda73d652a7a7e5d513928601b5103e55e9dded11aef31ce085dc930c4a6273`
(5 528 lines). It supersedes `33c629…` from the amendment round, which superseded `67fbe4…` from the gate.

## Before you regenerate `FINDINGS.md` from these fragments — read the closure log

**Read `FINDINGS.md`'s closure log (its last section) first.** Amendments are recorded there, and the
fragments do not necessarily carry them yet.

One such gap is open right now, deliberately: the closure-log entry **"Amendment round — three corrections a
dead closure seat never applied"** exists only in `FINDINGS.md`. It is not in `f6-closure-log.md`.
Regenerating from these fragments today would delete it, taking the amendment's authority, its evidence
table and its fingerprint record with it. Port that entry into `f6-closure-log.md`, or append it back by
hand, before treating any regenerated file as the document of record.
