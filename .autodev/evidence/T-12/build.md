# T-12 — build evidence

**Stage:** build · **Date:** 2026-09-04 · **Worktree:** `../autoSQL-T-12` · **Branch:** `t-12-readme-license`
Two files produced: `README.md`, `LICENSE`. Nothing else added, moved or deleted. Not pushed.

## Commit

| | |
|---|---|
| hash | `f25f4014cfa7df568d995dfbe4f97ad4e7c6d313` (`f25f401`) |
| subject | A front door for the repo: README and AGPL-3.0 |
| parent | `21d7f14` (A front door for the demo: start.sh, and a launcher page) |
| files | `README.md` (new), `LICENSE` (new) |
| trailers | `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` · `Claude-Session: https://claude.ai/code/session_01451SNRZD7uuFt2xckNhHvo` |

One commit, not two — the two files are one deliverable and neither is useful without the other.

**Not staged, left alone:** `.autodev/conformance-history.jsonl` was already modified in the worktree
when this stage started. It is untouched and uncommitted.

## Checks

```
$ wc -l README.md
139 README.md

$ wc -c LICENSE
34524 LICENSE

$ head -3 LICENSE
                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

$ grep -n -i -E "unlock|leverage|empower|transforming|cutting-edge|seamless|revolutioniz|next-generation|AI-powered" README.md
rc=1
```

Banned-word grep returns **no matches** (exit 1). README is **139 lines**, inside the ~140 budget.

**LICENSE integrity.** Fetched with `gh api /licenses/agpl-3.0 --jq .body > LICENSE`, unedited.
662 lines, 34,524 bytes (expected ~34,500). Line 1 is the title `GNU AFFERO GENERAL PUBLIC LICENSE`
— the leading whitespace is the canonical centred layout of the FSF text and was not stripped.
Line 2 is `Version 3, 19 November 2007`. Exactly one occurrence of each. Last line is
`<https://www.gnu.org/licenses/>.`

```
sha256  8d56b405468aad11f87ab5763f901e276e08d9646ff5c8481b1762b6b789e9ed  LICENSE
sha256  f08ae133036e3cff5094699ae7a076beb391151d36d25155964107f1ecfef6ca  README.md
```

## Where each number in the README came from

Every figure was read out of the KB page named beside it and cited inline in the README on first
appearance. Nothing was recalled, estimated or carried over from the ticket brief.

| Figure in README | Source |
|---|---|
| `xpr` runtime = **21 functions** | `kb/CURRENT-WORK.md` ("function count **21**"); `runtime/README.md` |
| GIMS reads up to **20,000** records, flags `truncated` | `kb/wiki/autosql-architecture.md` (`MAX_SCAN = 20_000`) |
| **18 of 33** divergence classes undetectable at query time | `kb/wiki/decision-expr-to-sql.md` §4 fact 3 |
| demo seeds **10,410** invented rows | `kb/CURRENT-WORK.md` (T-2 entry) |
| ports **55440** (Postgres) / **8787** (screen); offline `--no-index` wheelhouse | `kb/CURRENT-WORK.md` (T-2 entry); `demo/README.md`, `start.sh`, `run-demo` for the commands |
| **14** walkthrough steps | `kb/CURRENT-WORK.md` (T-2 entry); `demo/WALKTHROUGH.md` |
| step 11 reconciled — both engines read **123** on `["１２３", 1]` | `kb/CURRENT-WORK.md` "Three things a resuming session must not miss" #2; `demo/WALKTHROUGH.md` step 11; `demo/expected-answers.json` `steps[10].expect` |
| **0 wrong numbers over 11,367 expressions**, 3 batteries, 0 unexplained raises, 0 nullness violations | `kb/wiki/decision-t6-correctness-rerun.md` |
| contract fixture **130/130** | `kb/wiki/decision-t6-correctness-rerun.md` |
| harness driven with **six** deliberately wrong compilations, reported all six | `kb/wiki/decision-expr-to-sql.md` §5 |
| **62** and **66** wrong numbers at efd 0 and −3 | `kb/wiki/decision-t6-correctness-rerun.md` "What this does NOT settle" |
| `0.3333333333333333` at either setting on the shipping compiler (T-9/T-11) | `kb/CURRENT-WORK.md` (efd table); `compiler/README.md` |
| **0 of 144** coercible strings; eight databases read-only | `kb/wiki/nonascii-digits-in-real-data.md` |
| GIMS CSV import admits **8 of 10** non-ASCII digit forms | `kb/wiki/nonascii-digits-in-real-data.md`:56; also `kb/index.md`, `kb/wiki/decision-t5-homework.md` |
| **six of seven** GIMS write paths never check the schema | `kb/wiki/declared-types-are-not-a-guarantee.md`:8 |
| **3.79× to 7.15×** slower, six sizes 1,000–1,000,000, no crossover, gap is a floor | `kb/wiki/decision-expr-to-sql.md` §4 fact 2 and §7 (Q11 — index work off) |
| T-4 blocked: load avg **≤ 2.0** required, **2.30** measured, exclusive **2–3 hour** window | `kb/CURRENT-WORK.md` (START HERE) |
| **9 of 16** mutants never watched failing | `kb/CURRENT-WORK.md` |
| suites: demo **1155** · runtime **58** · compiler **34** | `kb/CURRENT-WORK.md`:46 |
| the ruling — do not build the compiler-plus-adapter as scoped, yet (Evan, 2026-08-21) | `kb/wiki/decision-expr-to-sql.md` §2 |

**Rounding note.** The brief quoted the slowdown as 3.8×–7.2×. The README uses the KB's own figure,
**3.79×–7.15×**, which is how it is written everywhere in the record and in Evan's own quoted words.

## One deliberate departure from the brief, on a matter of fact

The brief asked the demo section to say that **step 11 deliberately disagrees between SQL and Python
and is flagged**. That is no longer true of this repo, so it is not what the README says.

- `kb/CURRENT-WORK.md` lists it as one of three things a resuming session must not miss: *"The demo
  shows no disagreement, and that is not a regression. Step 11's artboard is `reconciled`."*
- `demo/WALKTHROUGH.md` (last touched by `9da3a51`, "T-8 build: variant C vendored, and step 11
  asserts the opposite") states both panes now report `123`.
- `demo/expected-answers.json` `steps[10].expect` carries `python_value: 123` and `sql_value: 123`.

`demo/README.md` still describes the disagreement as live; its step-11 paragraph predates T-8. The
README therefore describes step 11 as the value that **used to** come back wrong and now reconciles,
says the screen flags any disagreement loudly, and adds one sentence pointing out that
`demo/README.md` is stale on this point. Writing the brief's version would have put a claim on the
repo's front page that the demo disproves on first run — the day before it goes public.

**Not fixed here:** `demo/README.md` itself. It is outside this ticket's two paths.

## Rework after review (2026-09-05, agent:pm inline)
Review finding (BLOCKING, .autodev/reviews/T-12.md): offline-install claim overstated. Fixed in README.md on branch t-12-readme-license, commit 3d27731: states CPython 3.12 / manylinux x86-64 as the only covered platform, names the one network step (first Postgres image pull), says what happens elsewhere. Advisories A1–A3 also applied: 'by design' dropped; `./run-demo test` + `python3 -m pytest compiler/tests runtime/tests` named; root-level documents listed. Banned-word grep still empty. LICENSE untouched.

## Rework 2 after re-review (2026-09-05, agent:pm inline)
Re-review FINDING: the pytest one-liner introduced in rework 1 skipped most compiler/runtime tests (missing DSNs and a separate Postgres for runtime/tests). Replaced with a paragraph that names the setup each suite needs and points at compiler/README.md and runtime/README.md. Commit d90cb5e. LICENSE untouched; banned-word grep empty.
rework 2 build receipt: commit d90cb5e on t-12-readme-license; see evidence sections above.
