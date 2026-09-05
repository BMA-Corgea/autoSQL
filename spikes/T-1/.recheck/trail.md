# T-1 — reconstruction of the missing evidence trail

**Status: COMPLETE.** Written incrementally, 2026-08-21.
**Scope:** the two gaps the closure log admits about itself (GAP 1 refusal register, GAP 2 the three
producer-less `probes.json` blocks), plus the 130-case strict-jsonpath re-derivability claim at
`FINDINGS.md:2116`.
**Method:** read-only against `spikes/T-1/`, both GIMS checkouts read-only. Anything I ran is named
with its command and its actual output. Anything I could not establish is written as *not
established*, with what would settle it.
**This file does not modify `FINDINGS.md`.** It is a separate record.

> **Line-number note added 2026-08-21.** Every `FINDINGS.md:NNNN` in this file is a **pre-amendment**
> line number and is left as written, because several entries quote what a line used to say. Two
> later rounds inserted text into `FINDINGS.md` (5,389 → 5,528 lines). To convert: **+0** below line
> 929; **+16** for 929–1010; **+27** for 1011–1125; **+41** for 1126–1146; **+54** for 1147–~4849;
> **+58** for ~4850 and beyond. The full map, with worked examples, is the reading note at the top of
> `spikes/T-1/RECHECK-2026-08-21.md`. Three items recorded here — the C3 `or`/`and`/`not` sizes, the
> depth-64 sentence, and the unscoped 403 / 403 summary row — have since been **corrected in
> `FINDINGS.md`**, so entries calling them "still live" or "unapplied" are spent.

---

## 0. Pass structure — the frame the rest of this depends on

The document is the product of **six** distinct passes, not the "three passes" `f0`'s audit
paragraph names — and `f0` never mentions the sixth at all (§4). The three `f0` counts are the *audit* passes; two earlier passes produced the body
it audits. Established from the `.parts/` mtimes and the retained records themselves:

| # | pass | seats | retained record on disk | mtime |
| --- | --- | --- | --- | --- |
| 1 | investigation / draft | f1–f5 (+ f0) | the part files themselves | — |
| 2 | verification + critic + panel | verifier, critic, 3 panel seats | `.parts/verifications.json`, `.parts/critic.md`, `.parts/panel.json` | all `13:50:22` |
| 3 | closure pass (produced `xa`–`xd`, revised f1–f5) | **9** | **`.parts/closure-reports.md`** | `15:06:40` |
| 3b | consistency read (the "tenth seat") | 1 | `.parts/consistency.md` | `15:06:40` |
| 4 | consistency-repair pass | 9 (one per section) | **none** | — |
| 5 | punch-list round (3 lens reads + repair seats) | 3 lenses + 7 | **none** | — |
| 6 | **final-check round** — a 4th adversarial read, 4 edits applied | 1 + the dispatching session | **none** | — |

`ls --full-time spikes/T-1/.parts/` is the source for every mtime above.

---

## GAP 1 — the refusal register

### 1.1 First, a framing correction: the two numbers belong to different rounds

The brief pairs *"only ONE of six investigating seats' refusal reports reached it"* with *"five
refusals are cited elsewhere in the document"*, as if the five were the missing part of the six.
**They are not.** They are two different rounds with two different seat populations:

- **5 refusals · 4 seats** (`xb`, `f1`, `f3`, `f5`×2) belong to the **consistency-repair pass**
  (pass 4). That register is at `FINDINGS.md:5042–5046`, and it is **complete and reconciled** — see
  §1.3, where I re-checked all five against their raw artifacts.
- **1 refusal of 6 possible reporting seats** belongs to the **punch-list round** (pass 5), at
  `FINDINGS.md:5285`, table at `:5292`. Different seats, different work.

So the log is not missing four refusals from a set of five. It is missing an **unknown** number, from
five named punch-round seats. That is a worse-shaped gap than the brief implies, because it has no
denominator.

### 1.2 The seat roster — every seat, and what survives

| pass | seat | its report retained? | where | its in-place work verifiable? |
| --- | --- | --- | --- | --- |
| 3 closure | `f1` Conformance | **YES** | `.parts/closure-reports.md:3–10` | yes — 7 `[consistency]` marks in `f1.md` |
| 3 closure | `f2` Coverage/fallback | **YES, and it records the seat DIED** | `.parts/closure-reports.md:11–13` | **no work was done — see §1.6** |
| 3 closure | `f3` Index shape | **YES** | `:15–30` | yes |
| 3 closure | `f4` Measurement | **YES** | `:32–48` | yes |
| 3 closure | `xa` Totality | **YES** | `:50–61` | yes |
| 3 closure | `xb` filters/sort | **YES** | `:63–78` | yes |
| 3 closure | `xc` register | **YES** | `:80–96` | yes |
| 3 closure | `xd` reachability | **YES** | `:98–111` | yes |
| 3 closure | `f5` Recommendation | **YES** | `:113–130` | yes |
| 3b | consistency read | **YES** | `.parts/consistency.md` (24 items) | n/a |
| 4 repair | 9 repair seats (one per section) | **NO** | — | yes, via `[consistency]` / `[consistency N]` marks |
| 5 punch | 3 adversarial lens reads | **NO** | — | **no** — no artifact at all |
| 5 punch | `xc` | **YES (refusals intact)** | log only | yes, 3 `[punch]` marks |
| 5 punch | `xa` | truncated before refusals | log only | yes, 10 `[punch]` marks |
| 5 punch | `f5` | truncated after 4 items | log only | yes, 14 `[punch]` marks |
| 5 punch | `xb` | **did not reach the log** | — | yes, 4 `[punch]` marks |
| 5 punch | `xd` | **did not reach the log** | — | yes, 14 `[punch]` marks |
| 5 punch | measurement seat | **did not reach the log** | — | yes — `proto/closure_subset_coverage.py` + `analysis/subset-coverage.json` |
| 5 punch | `f0` + the log (bookkeeping) | it *is* the log | — | yes, 4 `[punch]` marks |
| **6 final-check** | a **fourth** adversarial read | **NO** | — | 4 edits, applied by the dispatching session |

**Seat counts, established:** the punch round had **7** working seats, **6** of which owed a report to
the bookkeeping seat — matching the log's "six". Across all six passes there were **9 + 1 + 9 + 3 + 7 + 1
= 30** seat-instances. **Reports survive on disk for 9 of them** (the nine closure-pass rows) plus the
consistency read. Everything else is self-attested in place or attested only by the log.

**Marker discipline holds.** I initially read `xb` as carrying zero `[consistency]` marks against three
logged repairs. It carries four, in a variant form the log does not describe —
`grep -oi '\[consistency[^]]*\]' .parts/*.md | sort | uniq -c` returns `74 [consistency]` plus one each
of `[consistency 3]`, `[consistency 12]`, `[consistency 18]`, `[consistency 23]`, all four in `xb`, and
those are exactly the four logged `xb` items. No unmarked edit found.

**`FINDINGS.md` is byte-reproducible from `.parts/`.** `cat` of the eleven parts in the documented order
differs from `FINDINGS.md` only by the ten `---` separators (`diff` = 28 added lines, all blank-or-`---`).
So every in-place claim above can be audited from either file.

### 1.3 The five repair-pass refusals, re-checked against the raw artifacts

All five reconcile. I re-derived each from the artifact the log names, not from the log.

| # | seat | what was refused | my independent check | verdict |
| --- | --- | --- | --- | --- |
| 12 | `xb` | the prescribed `17,148 + 197 + 5 = 17,350` — the `+5` invents a fifth collection | read-only census of all three stores, `mode=ro&immutable=1`: `guts` = `Vector` 6835 · `LedgerRecord` 5186 · `WorkOrder` 83 · **`Repo` 5**; `guts-code` = `Vector` 6705 · **`Repo` 5**; **`guts-ledger` = `LedgerRecord` + `WorkOrder` only, no `Repo` row at all** | **CONFIRMED.** Both `Repo` collections are outside `guts-ledger`, exactly as the refusal states |
| 11 | `f1` | the sub-clause "Of 11 re-verified witnesses, 4 / 3 / 3", which sums to 10 | counted `xa` A.5(i) directly: the table has **10 data rows**, and the R6 row reads `floor("1e400")` / `ceil("-1e400")` — two witnesses on one row. 4 raise→value (R1×2, R2, R8) · 3 both-raise (R3, R4@1.7e296, R5) · 3 raise→null (R4@DBL_MAX, R6, R7) | **CONFIRMED.** 4+3+3 counts rows; 11 counts witnesses. The refusal is the correct call |
| 23 | `f3` | the blanket attestation "f3's DDL probes **all** ran in rolled-back transactions" | `grep -inE '\bBEGIN\b\|\bROLLBACK\b\|\bCOMMIT\b' proto/*.sql` → **zero hits** in all four `idxshape_*.sql`; the only 7 `BEGIN`s are plpgsql function bodies in `runtime.sql`. `idxshape_hazard.sql:40` `INSERT`s and `:49` `DELETE`s | **CONFIRMED.** The blanket wording would have been an untrue attestation |
| 1 | `f5` | not the repair — the *characterisation* that §5.9(4) was false | `consistency.md` item 1 does quote §5.9(4) approvingly as "the correct form 230 lines later" while item 1's own headline calls it a defect | **CONFIRMED** on the document's own text |
| 5 | `f5` | the evidentiary premise that `events.jsonl`'s last event is `18:49:12.087Z` | `grep worker.started .autodev/events.jsonl` → **five** records: `2026-08-19T16:50:56.424Z`, `17:28:51.208Z`, **`18:49:12.087Z`**, **`21:32:32.536Z`**, and now **`2026-08-21T17:37:12.815Z`** | **CONFIRMED, and vindicated twice.** `consistency.md` cited #3 as "the last"; the log found #4; this verification session is #5. A claim about that file's last record does not stay true, which is exactly why `f5` refused to publish one |

**Nothing in the repair-pass refusal register is overstated.** The 5 / 4 / 3 reconciliation the punch
round performed (`f0:87–93`, log prose at `FINDINGS.md:5030–5038`, table at `:5042–5046`) is correct:
five rows, four distinct seats, three of them refusing a *prescribed repair* outright.

**One thing the register's own evidence has outrun.** `xb`'s published denominator was **17,345** at the
14:16:56 checkpoint, with a disclosed re-census of **17,398** at 16:21:55. My read today returns
`guts-ledger`/`instances` = `LedgerRecord` **17,430** + `WorkOrder` **207** = **17,637**, and `guts` =
**12,109** against `xb`'s 12,095. This does not contradict `xb` — it is precisely the "snapshot pinned to a
checkpoint, not a standing property" caveat `xb` B.4 added in the punch round, now demonstrated a third
time. *I did not re-derive the numerator 4,166; see §4.*

### 1.4 The punch round's six reporting seats — what each actually refused

The log's stated fallback method is: *"Those five entries are read off the seats' own in-place text,
and a refusal a seat made but did not write into its file would not appear here."* I applied that
method exhaustively to all five files, plus the one report that did arrive.

| seat | report reached the log? | refusal discoverable in its in-place text? | what I found |
| --- | --- | --- | --- |
| `xc` | **yes, refusals intact** | **YES — 1** | Refused extending the unit repair into **§C.12 item 1**, on scope (the punch list named §C.8 and §C.11(b) only) and on merit (C.12 never performs the addition). Reported instead of editing, and **named the one-token fix**. See §1.4.1 — the fix landed one round later |
| `xa` | truncated before its refusals section | **no** | 10 `[punch]` marks; a punch-pass addendum at `xa-totality.md:261–271` that attests re-verification method only. `grep -i refus` returns 3 hits, all substantive ("the compiler must **refuse** them", "statically refusable") — **none about a repair** |
| `f5` | truncated after 4 of its items | **no** | 14 `[punch]` marks; a punch-pass compliance block at `f5.md:590–606`. `grep -i refus` returns 8 hits, all substantive (compile-time/run-time refusal, DDL refusal) — **none about a repair** |
| `xb` | **did not reach the log at all** | **no — and could not** | **`grep -i refus xb-filters-sort.md` returns ZERO hits.** The word does not occur in the file |
| `xd` | **did not reach the log at all** | **no — and could not** | **`grep -i refus xd-reachability.md` returns ZERO hits.** The word does not occur in the file |
| measurement seat | **did not reach the log at all** | **no** | It left instruments, not prose: `proto/closure_subset_coverage.py` + `analysis/subset-coverage.json`, both mtime `2026-08-19 16:27:39`. Nothing refusal-shaped exists to read |

**The sharpening the log does not make about itself.** Its fallback method — *read the refusal off the
seat's own in-place text* — has **zero recall on two of the five** seats it is applied to. `xb` and `xd`
do not contain the word "refuse" in any form, so no refusal by either could ever have been recovered
that way. For `xa` and `f5` the method had a chance and returned nothing. For the measurement seat there
is no prose at all. **The honest statement of the gap is therefore narrower and worse than the log's**:
not "we might have missed some", but "for `xb`, `xd` and the measurement seat we had no instrument that
could have found one."

**What `xb` and `xd` did do, which the log classifies correctly and I want to keep distinct from a
refusal:** each **withdrew one of its own already-published claims** as an over-claim — `xb` withdrew
*"a writer cannot move an `immutable=1` count in either direction"* and *"17 342 is superseded and
unexplained"* (`xb-filters-sort.md:130–134`); `xd` withdrew the *"not a new experiment"* half of its own
D.1 label (`xd-reachability.md:13`). Those are self-corrections, not refusals of a prescribed repair, and
the log books them under *What was repaired*. That is the right call.

#### 1.4.1 The one recorded refusal closed itself, one round later

`xc`'s refusal named its own fix: *"One-token fix if a later seat is authorised: insert '(19 ids)' after
'the **18 undetectable classes**'."* The **final-check round** (`FINDINGS.md:5378`) applied exactly that.
`xc-fallback-register.md:237` now reads: *"For the **18 undetectable classes (19 ids)** there is nothing
to trigger"*. I re-derived the underlying arithmetic off C.8's two id lists rather than its prose:
**15 detectable + 19 undetectable = 34 ids**; folding D21 into D1–D5 gives **15 + 18 = 33 classes**. Both
hold. **This refusal is fully closed and fully traceable.** It is the only one in the punch round that is.

### 1.5 Where the document UNDERSTATES its own trail — `f0` omits a fifth retained record

The brief asks which side the document errs on. On this point it **understates**.

`f0`'s inventory of retained audit records names four:

> "Those records are kept beside this file in [`.parts/`](.parts/) — `verifications.json`,
> `critic.md`, `panel.json`, `consistency.md`." — `FINDINGS.md:71–73`

The closure log's own punch-round preamble names **five**:

> "`.parts/` keeps `verifications.json`, `critic.md`, `panel.json`, `consistency.md` **and
> `closure-reports.md`** from the earlier passes, but there is no lens artifact"
> — `FINDINGS.md:5235–5236`

**`.parts/closure-reports.md` is real, 130 lines, and it is the single most valuable surviving seat
record in the spike** — nine per-seat reports, each with `CORRECTIONS APPLIED` / `REJECTED` / `GAPS
CLOSED` / `STILL OPEN` sections. It is the only place in the whole tree where a seat's *own* account of
what it applied and what it rejected survives as a file. `f0` — the part a gate reader reads first —
leaves it out of the list.

**The related sentence is literally true but reads wider than it is.** The punch log says:

> "The same holds one level down: **no repair seat's report is retained, in either round.** This log
> is their only record" — `FINDINGS.md:5236–5238`

"Either round" means the consistency-repair pass and the punch round, and for those two it is correct —
I found no such file. But a reader arrives at that sentence having just been told `closure-reports.md`
exists, and the two sentences together do not make clear that **nine seat reports from the pass that
produced `xa`–`xd` and revised `f1`–`f5` DO survive**, in full, on disk.

### 1.6 Where the document OMITS something material — a closure seat died and nothing says so

This is the one finding in this section that is not bookkeeping.

`.parts/closure-reports.md:11–13`, verbatim and complete:

> `## Finding 2 — Coverage and fallback`
>
> `(agent died: API connection lost mid-response; file untouched)`

**That fact appears nowhere in `FINDINGS.md` or in any of the eleven part files.**
`grep -in 'agent died\|API connection\|connection lost\|died' FINDINGS.md .parts/*.md` returns exactly
one hit, and it is the line above, inside `closure-reports.md` itself.

**What was lost.** `.parts/verifications.json` prescribed **6 corrections** to Finding 2 (2 material,
4 cosmetic). The sibling seats report `all 11` (f1), `all 13` (f3), `12 of 13` (f4) applied. Finding 2
applied **none** — and `f2.md`'s own compliance block confirms it in place:

> "The single §2.4 edit above is the **only change made to this file after it was first written**"
> — `FINDINGS.md:1330`

That single edit is the *consistency-repair* pass's item 11. The verification pass's six corrections
were never worked by anybody.

**All six are still live in `FINDINGS.md` today.** I checked each, and independently reproduced the two
material ones rather than taking the verifier on trust:

| # | severity | the claim still in `FINDINGS.md` | what I measured | status |
| --- | --- | --- | --- | --- |
| 1 | **material** | `:1121` column header **"first failing size"**, `:1124` row `1 or 1 or …` / `1 and 1 and …` / `not not …1` = **400 / 334 / 499** at **1996 / 1999 / 1997** chars | Re-bisected read-only against the real `expr.parse` + `proto/compile.py`: **first** `RecursionError` is `or` **n=333 (1661 chars)**, `and` **n=333 (1993)**, `not` **n=332 (1329)**. The published 400/334/499 are the **largest** sizes that still fit under `MAX_SOURCE_LEN=2000` (`or` overflows at n=401/2001 chars, `and` at n=335/2005, `not` at n=500/2001) | **WRONG AS LABELLED, and wrong in the direction that understates the defect** — `not` reaches C3 at 1329 chars, not 1997 |
| 2 | **material** | `:925` headline row "Out-of-fixture probes run / agreeing \| **403 / 403**", unscoped | `proto/coverage_probe_results.json` = **403 entries**, all agreeing ✓. But `proto/results.json → out_of_fixture_probes` is a **second** out-of-fixture set of **8**: `agrees` ×3, **`DIVERGES` ×4** (`f8_guard_1e300_arith`, `f8_guard_1e297_arith`, `num_of_1e999_string`, `unicode_upper_sharp_s`), **`SQL_ERROR (totality violation)` ×1** (`overflow_via_multiply`) | **TRUE BUT UNSCOPED.** The headline row reads as "out-of-fixture probing found nothing". §2.5/§2.7 do carry the divergences honestly, so nothing is hidden — but the summary row a gate reader scans does not say which probe set it counts |
| 3 | cosmetic | `:1256` a quotation spliced from two different docstrings, presented with one `file:line` cite | not re-checked in the GIMS tree beyond confirming the text still stands as written | unapplied |
| 4 | cosmetic | `:1294` "a read-only sweep of **every** SQLite database in the `gims-ledger` tree" | verifier found 2 of 33 files unopenable ("database disk image is malformed") and silently skipped; not re-run by me | unapplied |
| 5 | cosmetic | `:947` cites `expr.py:180-182` (unary `+`) and `expr.py:196-199` (parentheses) | verifier: correct sites are `:179-181` and `:204-208` | unapplied |
| 6 | cosmetic | `:1143–1144` "The parser permits depth **64**" | `GIMS-Project/core/dashboard/expr.py:186-187` reads `self.depth += 1` then `if self.depth > MAX_DEPTH: raise`, with `MAX_DEPTH = 64` at `:40` — so the deepest nesting that **parses** is **63** | **OFF BY ONE**, in the safe direction: the conclusion ("far past 24") is unaffected |

**Direction of the error, stated plainly.** Corrections 1 and 6 both err *against* the spike's own
conclusion — the real recursion boundary is **easier** to reach than published, and the real depth limit
is one lower. Correction 2 is the only one that flatters the document, and it flatters it in a summary
row rather than in a finding. **None of the six moves the NO-GO.** What they cost is the document's claim
about its own process: `f0:66` tells a gate reader the body was "re-derived from the raw machine data by
a separate seat that did not trust the prose (43 corrections, 2 load-bearing)", and **6 of those 43 were
never applied to the section they were written for, because the seat holding them died.**

---

## GAP 2 — the three raw `probes.json` blocks with no retained producer

### 2.1 The facts, established

`analysis/probes.json` has **five** top-level blocks. `proto/probe_extra.py` — the only retained script
in the tree that writes that path (`grep -rn 'probes.json' proto/ analysis/` → one hit,
`probe_extra.py:99`) — writes exactly **two** of them:

| block | producer retained? | evidence |
| --- | --- | --- |
| `payload` | **yes** | `probe_extra.py:36` `out["payload"] = pay` |
| `poison` | **yes** | `probe_extra.py:69–96` |
| `xpr_decomposition_100k_ms` | **NO** | no retained file mentions any of its 8 step names |
| `poison_syncscan` | **NO** | `grep -rn synchronize_seqscans proto/ analysis/` → **zero hits in any retained script** |
| `recheck` | **NO** | `grep -rn 'getloadavg\|loadavg' proto/` → **zero hits**; `bench.py` writes only `analysis/measurements.json` (`:581`, `:590`) and emits no block of this shape |

`f4` §4.11's statement of the gap (`FINDINGS.md:2891–2896`) is **accurate and, if anything, understated**.

### 2.2 A fragility the document does not record

`probe_extra.py:19` initialises `out = {}` and `:100` writes
`json.dump(out, open(p, "w"), indent=2, default=str)` — **truncating mode, no merge**.

**Re-running the only retained producer of `probes.json` would delete all three orphan blocks**, and
would also overwrite the `poison` block whose *superseded* values (`time_to_raise_ms: 33.3`,
`overhead_pct: 2.2`) `f4` §4.11 item 10 deliberately points at as a re-derivation hazard. The three
blocks are therefore not merely unreproducible — they are **one documented command away from being
destroyed**, and nothing in the tree warns a future seat of that. *(I did not run it. `proto/` is
writable to me under the owner's waiver; I made no change there — see §5.)*

### 2.3 Whether the corpus behind them still exists — it does not

Read-only against the spike's own scratch database (FRAMING §7's `autosql_spike`, `host=127.0.0.1
port=55433`, session set `readonly=True`, catalog `SELECT`s only):

- **`pg_tables` outside the system schemas returns ZERO rows.** Every `measure_instances_*` table, the
  `measure_instances_poison` table and `idxprobe` are gone.
- The `xpr` schema survives with **21 functions** installed, so `runtime.sql` is still applied.

So no probe of any kind can be re-run against the measured data today. The corpus **is** regenerable —
`proto/gen_data.py:15` fixes `SEED = 1729` and its docstring states *"rule 3: same seed => same per-row
shape"* — but regenerating it and re-measuring produces **new measurements, not a re-derivation**.

### 2.4 Which published numbers depend on each block, and whether each survives

#### Block 1 — `xpr_decomposition_100k_ms`: unreproducible, and **nothing rests on it**

Values: `0_count` 7.54 · `1_field` 27.16 · `2_pdate_x1` 3597.97 · `3_pdate_x2_derive` 13006.35 ·
`4_plus_to_jsonb` 13136.86 · `5_plus_xpr_ord` 25065.86 · `6_plus_xpr_truthy` 14072.30 ·
`7_full_compiled_filter` 8573.77.

Cited once, at `FINDINGS.md:2546–2551`, and cited **to disclose that the experiment failed**:

> "A direct per-function decomposition was attempted and **discarded, not reported** — it ran under host
> contention and returned self-contradictory results… The inference is therefore **unconfirmed**."

**Verdict: harmless.** The block supports a *negative*. If it vanished, "unconfirmed" would stand a
fortiori. No published claim rests on it. Not re-derivable, and it does not matter.

#### Block 2 — `recheck`: unreproducible, and the document has already demoted it

Values feeding the prose: `20000.path_a.median` 492.63 · `20000.path_B2.median` 1257.03 ·
`1000.path_a` 24.24 · `1000.path_B2` 87.79 · `20000.path_B4` 22.29 · `1000.path_B4` 1.70 · the two
load-average triples.

Dependent numbers: **2.55×** (9 occurrences), **3.62×**, **22.10×**, **14.26×**, the
"1 138.61 → 1 257.03 = +10.4%" band point, and the `13.79 / 17.92 / 15.16` load triple.

**Every one of them is already fenced in place.** The competing figure is re-derivable from retained
data, and I re-derived it: `analysis/measurements.json → sizes[*].path_B2.total_ms.median ÷
path_a.total_ms.median` = **4.152 / 3.892 / 3.794 / 4.363 / 6.713 / 7.152**, reproducing the binding
headline **3.79×–7.15×** exactly and reproducing closure-log item 7 exactly.

**Verdict: not re-derivable, and it does not need to be.** Demoting `recheck` *raises* the floor from
2.55× to 3.79× — the document says so itself at `:4684` and `:5192` (*"the performance leg — **firmer**"*).
**This block's unreproducibility strengthens the NO-GO.**

#### Block 3 — `poison_syncscan`: unreproducible, **and this one is load-bearing**

Values: `on.median_ms` **40.76** · `off.median_ms` **6916.85** · `b2_full_scan_same_table_ms` **6496.0**.

Dependent published numbers, all traced:

| number | where | rests on |
| --- | --- | --- |
| **170×** syncscan spread | `:2834`; disclosed as producer-less at `:2894` | `6916.85 ÷ 40.76 = 169.7` — **both legs inside the orphan block** |
| **6 917 + 1 494 = 8 411 ms** | `:2834`, `:3872`, `:4824` | `poison_syncscan.off` (orphan) **+** `poison.path_a_after_raise_ms` 1493.92 (**retained**) |
| **+463%** | **11 occurrences**, incl. `f4` §4.9, `xc` C.12, `f5` §5.8(a) | same composite |
| "the wasted scan is slower than a successful full B2 scan of that table (**6 496 ms**)" | `:2834` | `b2_full_scan_same_table_ms` — **orphan** |

I verified the arithmetic closes: `(6916.85 + 1493.92) / 1493.92 = +463.0%` exactly, and
`6916.85 / 40.76 = 169.7×`. The composite is internally sound. **What is unavailable is any way to check
the 6 916.85 itself.**

**This is the one number in the spike that is both unreproducible and cited eleven times.**

**How exposed is it? Quantified.** The retained fallback for the same event is `probes.json → poison`,
produced by the retained `probe_extra.py`: `time_to_raise_ms` **33.3**, `path_a_alone_ms` **1493.92**,
`overhead_pct` **2.2**. If `poison_syncscan` were struck entirely, the run-time-refusal price would fall
back to:

    with poison_syncscan (orphan):  6916.85 + 1493.92 = 8410.77 vs 1493.92  =  +463.0%
    retained fallback only:           33.30 + 1493.92 = 1527.22 vs 1493.92  =    +2.2%

**a 210-fold reduction in the priced worst case of a run-time refusal.**

**Is the instrument recoverable?** Nearly. `probe_extra.py:38–97` builds `measure_instances_poison`, runs
the identical compiled query and catches the `22003`. The only missing pieces are a
`SET synchronize_seqscans = off` and a repeat loop. But `synchronize_seqscans` appears in **no** retained
file, so the syncscan-controlled variant is a **new experiment**, not a re-derivation — and it would have
to run against a regenerated corpus on a different host at a different load.

### 2.5 The claim that rests on an unreproducible number, named exactly

Answering the brief's question in its own words:

> **`f4` §4.9's "run-time refusal" row (`FINDINGS.md:2834`) — and every downstream restatement of
> "+463%", including `xc` C.12's cost-of-the-machinery argument (`:3872`) and `f5` §5.8(a)'s
> (`:4824`) — rests on `poison_syncscan.off.median_ms = 6 916.85`, a number with no retained
> producer, no retained instrument that sets the GUC it depends on, and no surviving table to
> re-measure. Struck, the same claim prices at +2.2%.**

**Direction, stated honestly.** This cuts **against** the spike. +463% is a figure that makes pushdown
look expensive; it is the least-audited number in the document and it is 210× larger than the retained
alternative. A CONDITIONAL-GO advocate has a legitimate objection here that the document does not
concede — `f4` §4.11 discloses the missing producer but never states what the number falls back to.

**What limits the damage — and I want this stated as carefully as the objection.** `f4` §4.9
qualification 2 (`:2843–2846`) already says the figure bounds only the RAISE classes: *"For a silent
class there is nothing to trigger, so 0.0307 ms and +463% do not bound its cost."* `f5`'s NO-GO rests on
the **silent** classes — 18 of 33, undetectable in principle — which +463% never priced. So striking
6 916.85 removes an argument the verdict does not use.

---

## 3. The 130-case strict-jsonpath claim at `FINDINGS.md:2116` — TESTED, and it holds

### 3.1 The claim

> "**Grey area, disclosed rather than smoothed.** §3.5(d)(ii)'s 130-case strict-jsonpath run was driven
> by a script written to the session scratchpad, not to `proto/` (read-only for the closure pass): one
> read-only `SELECT` per case, no DDL, method taken unchanged from
> `proto/idxshape_fixture_subset.py` + `proto/idxshape_jsonpath_agree.py`. **It is re-derivable from
> those two committed instruments** but is not itself a committed artifact (§3.8 open item 9)."
> — `FINDINGS.md:2116–2121`

The brief asks whether that is genuine or an untested assertion. **Until today it was untested** —
`f3` §3.8 lists it as open item 9 and the punch round left it open. **I tested it. It is true.**

### 3.2 What I did

Read-only, against `autosql_spike` (scalar `SELECT`s only — no DDL, no table referenced, session
`readonly=True`). I built the run from the two named instruments and marked, line by line, what each
supplied:

- **`idxshape_fixture_subset.py` supplied the selection** — `LIT`, `is_path()`, `classify()` lifted
  verbatim. Re-running it standalone reproduces the consistency pass's figure exactly:
  `114 OTHER / 10 cmp(path, literal) / 6 bare path / 130 total`.
- **`idxshape_jsonpath_agree.py` supplied the comparison** — the
  `%s::jsonb @@ ('strict ' || %s)::jsonpath` shape and the `expr.truthy(expr.evaluate(...))` oracle,
  lifted verbatim.
- **The fixture supplied the records** — 68 of the 130 cases carry a `record` key, and all 16
  expressible ones do.

### 3.3 The result — an exact reproduction, all 16 rows

Every published cell reproduced: the case indices, names, `expr` texts, jsonpath strings, the `expr`
column, `strict raw`, `strict IS TRUE`, `lax IS TRUE`, and each verdict.

```
OTHER (no jsonpath equivalent)     cases= 114  expressible=  0  agrees=  0  diverges=  0
cmp(path, literal)                 cases=  10  expressible= 10  agrees=  9  diverges=  1
bare path                          cases=   6  expressible=  6  agrees=  2  diverges=  4
TOTAL                              cases= 130  expressible= 16  agrees= 11  diverges=  5
```

against the published table's `114 / 0 · 10 / 10 / 9 / 1 · 6 / 6 / 2 / 4 · 130 / 16 / 11 / 5`.

**LOAD-BEARING CORRECTION 2 reproduces.** Case 33, `missing_eq_null_true`, `$.x == null` on `{}`:
`expr` **True**, strict raw **NULL**, strict `IS TRUE` **False**, lax `IS TRUE` **False** →
**DIVERGES**. This is the silent row-drop `f3` calls disqualifying, and it is real. So are the four
bare-path divergences (cases 11, 12, 15, 19).

### 3.4 But the claim is overstated in one specific way — and the overstatement matters

**The two named instruments are necessary but not sufficient.** Neither contains an AST → jsonpath
translator, and one is required:

- `grep -rn 'jsonpath' proto/ --include='*.py'` finds the word only in a docstring, a return-string
  literal, and one `::jsonpath` cast. **`grep -rln 'def .*jsonpath\|to_jsonpath\|as_jsonpath'` over
  `proto/` and `analysis/` returns nothing.**
- `idxshape_fixture_subset.py` **classifies** shapes; it never emits a jsonpath and touches no database.
- `idxshape_jsonpath_agree.py`'s jsonpath strings are **hand-written literals in a hard-coded 11-case
  list**. It never reads the fixture. Its operator choice, `"@@" if "?" not in jp else "@?"`, is a
  heuristic over strings a human already wrote.

I had to write `jp_path()`, `jp_lit()` and `to_jsonpath()` myself — about twelve lines, and **exactly the
twelve lines where the semantic risk lives**: key quoting, literal rendering, and the `@@`-vs-`@?` and
strict-vs-lax choices that the whole §3.5(d) result turns on. A different seat could reasonably have
emitted `$."n" ? (@ < 7)` instead of `$."n" < 7` and got different numbers.

**The accurate form of the claim** would be: *"re-derivable from those two committed instruments plus an
AST→jsonpath translator that neither of them contains."* As written, `FINDINGS.md:2119–2120` **overstates
the completeness of its trail**.

### 3.5 What I changed, to close the document's own open item

`f3` §3.8 open item 9 (`FINDINGS.md:2037`) prescribes the remedy: *"copy the scratchpad script into
`proto/` when the tree is writable again"*. Under the owner's written waiver I did the equivalent, and wrote
the instrument I built:

**`spikes/T-1/proto/idxshape_jsonpath_130.py`** — new file. Its header states in the first paragraph that
it was written by this reconstruction pass on 2026-08-21, **not** by the investigation, and that it is
**not** the original scratchpad script. Its blocks are marked `[FROM INSTRUMENT 1]`, `[FROM INSTRUMENT 2]`
and `[NOT IN EITHER INSTRUMENT]` so the gap in §3.4 stays visible in the code itself.

**Open item 9 is now closed** — the result has a committed, runnable artifact that reproduces it. What
does **not** change is the surrounding caveat: this instrument was written two days after the
investigation, by a different seat, and reproducing a number is not the same as the original run having
been correct. It is, however, considerably better than an untested assertion, which is what it was.

---

## 4. Master table — every seat, what survives, what does not, what the missing piece would have told us

| pass | seat | survives | missing | what the missing piece would have told us |
| --- | --- | --- | --- | --- |
| 2 verify | verifier | `verifications.json` — 43 corrections, 19 unverifiable, across Findings 1–4 | nothing | — |
| 2 critic | completeness critic | `critic.md` — 16 gaps | nothing | — |
| 2 panel | 3 go/no-go seats | `panel.json` — the non-convergence | nothing | — |
| 3 closure | `f1` | full report (`closure-reports.md:3–10`); 11/11 applied, 0 rejected | — | — |
| 3 closure | **`f2`** | **a one-line death notice** | **the entire seat** — 6 verification corrections, all critic gaps for §2 | **§1.6.** Whether §2.6's C3 boundary, the 403/403 headline scope, the depth-64 limit and three citations were right. Two were material and are still wrong in the document today |
| 3 closure | `f3` | full report (`:15–30`); 13/13 applied, 2 load-bearing | — | — |
| 3 closure | `f4` | full report (`:32–48`); 12/13 applied, **1 rejected with its reasoning** | — | — |
| 3 closure | `xa` `xb` `xc` `xd` `f5` | full reports (`:50–130`) | — | — |
| 3b | consistency read | `consistency.md` — 24 items | nothing | — |
| 4 repair | `xb` `f1` `f3` `f5`×2 | **all five refusals logged with raw evidence**; I re-checked all five and all five hold (§1.3) | the seats' report files | little — the log's register is complete and reconciles against the artifacts |
| 4 repair | the other 5 repair seats | their `[consistency]` marks in place | their report files | whether any of them also refused. **Unknowable, and the log does not claim otherwise** |
| 5 punch | 3 adversarial lenses | **nothing at all** | all three reads | **the biggest single hole.** "21 items, all credibility or minor, none decision-blocking" is a dispatch summary no reader can audit. If a lens raised something decision-blocking that the dispatch downgraded, nothing on disk would show it |
| 5 punch | `xc` | report **with refusals intact**; 3 `[punch]` marks | — | — |
| 5 punch | `xa` | 10 `[punch]` marks + a method addendum | report truncated before its refusals | whether `xa` refused any punch item. Its in-place text records none |
| 5 punch | `f5` | 14 `[punch]` marks + a compliance block | report truncated after 4 items | same, for `f5`'s remaining ~7 items |
| 5 punch | `xb` | 4 `[punch]` marks; two self-withdrawals | **report never arrived; the word "refuse" does not occur in the file** | the log's fallback method has **zero recall** here (§1.4) |
| 5 punch | `xd` | 14 `[punch]` marks + a compliance block | **report never arrived; "refuse" does not occur in the file** | same |
| 5 punch | measurement seat | **`proto/closure_subset_coverage.py` + `analysis/subset-coverage.json`** — the round's only retained instrument | no prose report | I re-tallied all 130 per-case verdicts: `panel` 84 · A 68 · B 62 · C 56, and the 16-case loss decomposes `% 7 / round 5 / floor 2 / ceil 2`. **Reproduces exactly.** Nothing is missing that matters |
| 5 punch | `f0` + the log | the log itself | — | — |
| 6 final | a 4th adversarial read | **nothing** | the whole read | 4 edits it prompted are in place and all four **strengthen** the NO-GO; its "5 defects" list survives only as the log's summary. **`f0` never mentions this round exists** |
| — | measurement seat (`probes.json`) | `payload`, `poison` — `probe_extra.py` retained | **`xpr_decomposition_100k_ms`, `poison_syncscan`, `recheck`** | **§2.** Block 1: nothing rests on it. Block 3 (`recheck`): its loss *strengthens* NO-GO. **Block 2 (`poison_syncscan`) is the one that matters — it alone carries the +463% cited 11 times, and without it the same claim prices at +2.2%** |
| — | `f3` scratchpad seat | the **result**, in `f3` §3.5(d)(ii) | the script | **§3. Now closed** — I re-derived all 16 rows exactly and committed `proto/idxshape_jsonpath_130.py` |

---

## 5. Not established by this pass — with what would settle each

| what | why not | what would settle it |
| --- | --- | --- |
| Whether `xa`, `f5`, `xb`, `xd` or the measurement seat refused anything in the punch round | Their reports do not exist and their files record no refusal. For `xb` and `xd` the word does not appear at all | Nothing on disk can. Only the transcripts of those five seats, if the driving session retained them |
| What the three adversarial lens reads and the fourth final-check read actually said | No artifact was written | Their transcripts. This is unrecoverable from the repo |
| Whether the three orphan `probes.json` blocks were produced by the code the prose describes | No producer, and the measured tables no longer exist in `autosql_spike` | Only a fresh experiment: regenerate the corpus (`gen_data.py`, `SEED=1729`) and write a new syncscan-controlled probe. That produces **new** numbers, not a re-derivation |
| Whether `f2`'s 4 cosmetic verification corrections (3, 4, 5) are right | I reproduced corrections 1 and 6 and confirmed 2 against the raw JSON; I did not re-run the `gims-ledger` SQLite sweep or re-check the two GIMS docstring cites | Re-run the verifier's sweep read-only; open `core/deep_search.py:168` and `:381–391` |
| Whether `xb`'s numerator **4 166** still holds | I re-censused the denominators (now 17,637 / 12,109) but did not recompute the `_norm_key` collision count | Re-run `xb`'s collision probe read-only against `guts-ledger/instances` |
| Whether the original scratchpad 130-case script produced its result the same way mine does | It was never retained | Nothing can settle this. My run reproduces the **result**; it cannot certify the **original run** |

---

## 6. What I changed

Under the owner's written waiver of `FRAMING.md` §3's no-edit rule (2026-08-21, *"Let them edit the existing
code in place"*):

| file | change |
| --- | --- |
| `spikes/T-1/proto/idxshape_jsonpath_130.py` | **NEW.** The 130-case strict-jsonpath instrument, closing `f3` §3.8 open item 9. Header states unambiguously that it is a 2026-08-21 reconstruction, not the original script |
| `spikes/T-1/.recheck/trail.md` | **NEW.** This record |

**Nothing else was written.** `FINDINGS.md` and every file in `.parts/` are unmodified — I verified
`FINDINGS.md` still reassembles byte-identically from the parts. No existing file in `proto/` or
`analysis/` was edited; in particular **I did not run `probe_extra.py`**, which would have destroyed the
three orphan blocks (§2.2). Both GIMS checkouts were read-only throughout: SQLite opened only as
`mode=ro&immutable=1`, Python imports run with `sys.dont_write_bytecode` or against the existing venv,
`git status` clean in both. Postgres work was scalar `SELECT`s on a `readonly=True` session against the
spike's own `autosql_spike`; **no DDL, no writes, and `glp_strong` was never opened.**

**Concurrency note, disclosed because it affects my own reads.** A parallel session wrote
`proto/results.json` and `proto/CONFORMANCE.md` at **11:45:47** today and created
`proto/conformance_injection_test.py` at **11:49:21** — after this pass began (11:38) and before my
reads. Neither file is under git, so no baseline exists to diff. I re-read `results.json` after
noticing, and both figures I rely on still match the **2026-08-19** records exactly:
`out_of_fixture_probes` = 3 agrees / 4 `DIVERGES` / 1 `SQL_ERROR`, as `verifications.json` recorded on
08-19; and `degenerate_baselines` = `{true 20, null 19, false 15, zero 1, empty-string 0}`, reproducing
closure-log item 10's `130 − 20 = 110` and `130 − 55 = 75`. Both GIMS trees' dirty files carry mtimes of
**2026-08-13 and earlier** — pre-existing, not this pass.

---

## 7. Bearing on the NO-GO ruling

**Net: the reconstruction leaves the NO-GO standing, and on balance slightly strengthens the record
behind it — but it hands a CONDITIONAL-GO advocate one legitimate new argument, and it damages the
document's account of its own process more than it damages its findings.**

**Strengthens:**
- The five repair-pass refusals all reconcile against raw artifacts (§1.3) — the register is honest.
- The punch round's one refusal closed itself a round later, traceably (§1.4.1).
- The 130-case jsonpath result — including the disqualifying case-33 silent row drop — **reproduces
  exactly** and now has a committed instrument (§3).
- The corrected-subset measurement (68/130) re-tallies exactly from the raw per-case verdicts.
- The unreproducible `recheck` block, demoted, **raises** the B2÷A floor from 2.55× to 3.79×.
- `f2`'s two unapplied material corrections both err *against* the spike: C3 is reachable at 1329
  characters, not 1997.

**Weakens:**
- **+463% rests on `poison_syncscan.off = 6 916.85`, which has no producer, no retained instrument that
  sets the GUC, and no surviving table.** Struck, the same claim prices at **+2.2%** — 210× smaller. It
  is cited 11 times. The document discloses the missing producer but never states the fallback.
- Six verification corrections were never applied because a seat died, and **nothing in `FINDINGS.md`
  says so** — while `f0:66` tells a gate reader all 43 were found by a seat that "did not trust the
  prose".

**Neither:** the verdict rests on the **18 undetectable-in-principle classes**, and nothing in this pass
touched them. `f4` §4.9 itself says +463% never priced them.

**One thing the owner should weigh before ruling.** The un-auditable parts of this record are concentrated in
the *audit* layer, not the evidence layer: three lens reads, a fourth final-check read, and eighteen seat
reports exist only as summaries written by the seat being summarised. Every **measurement** I tried to
re-derive from a retained artifact came back exact. That is the right way round — but it means "three
adversarial reads found nothing decision-blocking" is the one load-bearing claim in the document that no
reader can check, and it is the claim doing the most work in the closure log's confidence.
