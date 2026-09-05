# T-1 — adversarial re-check of `.recheck/trail.md`

**Verdict: OVERSTATED.** Written 2026-08-21 by a second, adversarial seat instructed to assume the
trail is wrong. Everything below was re-run or re-read by me; nothing is taken on the trail's word.
Read-only against `spikes/T-1/`, both GIMS checkouts, `.autodev/events.jsonl` and the spike's
`autosql_spike` Postgres (`readonly=True`, catalog + scalar SELECTs only). I wrote no file except
this one.

> **Line-number note added 2026-08-21.** Every `FINDINGS.md:NNNN` in this file is a **pre-amendment**
> line number and is left as written, because several entries quote what a line used to say. Two
> later rounds inserted text into `FINDINGS.md` (5,389 → 5,528 lines). To convert: **+0** below line
> 929; **+16** for 929–1010; **+27** for 1011–1125; **+41** for 1126–1146; **+54** for 1147–~4849;
> **+58** for ~4850 and beyond. The full map, with worked examples, is the reading note at the top of
> `spikes/T-1/RECHECK-2026-08-21.md`. Three items recorded here — the C3 `or`/`and`/`not` sizes, the
> depth-64 sentence, and the unscoped 403 / 403 summary row — have since been **corrected in
> `FINDINGS.md`**, so entries calling them "still live" or "unapplied" are spent.

## Summary

The trail's **evidence layer reproduces exactly** — every number I re-derived from a retained
artifact came back to the digit, including the two it claimed as independent reproductions. Its
**framing layer overstates in two places and misreports three command outputs.** The trail's bottom
line (NO-GO stands; the record behind it is sound; the process account is the damaged part) survives,
but its single headline *weakening* finding is materially overstated.

## 1. What reproduced — exactly

| trail claim | my check | result |
| --- | --- | --- |
| `FINDINGS.md` reassembles from the 11 parts | `cat` in the `:362` order; `diff` = 28 added lines | **exact** — 9 `---` + 19 blanks (see D1) |
| f2 closure seat died; sole record is `closure-reports.md:13` | `grep -in 'agent died\|API connection\|connection lost\|died' FINDINGS.md .parts/*.md` | **1 hit, that line** |
| `verifications.json` Finding 2 = 6 corrections; 43 total | parsed the JSON | **6 / 43** |
| **C1** first `RecursionError` at `or` 333, `and` 333, `not` 332 | re-bisected n=1..600 against real `expr.parse` + `proto/compile.py`, all four chain shapes | **exact**: `or` 333 (1661 ch), `and` 333 (1993), `not` 332 (1329), `+` 333 (665). Failure is monotone — no OK above first failure. Published 400/334/499 are the largest sizes under `MAX_SOURCE_LEN` |
| **C2** `out_of_fixture_probes` = 8 | parsed `proto/results.json` | `Counter({'DIVERGES':4,'agrees':3,'SQL_ERROR (totality violation)':1})`; `coverage_probe_results.json` = 403 |
| **C6** max parsing depth is 63, not 64 | read `expr.py` with line numbers | `:186 self.depth += 1`, `:187 if self.depth > MAX_DEPTH`, `:40 MAX_DEPTH = 64` → 63. `FINDINGS.md:1143` still says 64 |
| all 6 f2 corrections still live | read `:925`, `:947`, `:1121-1124`, `:1143`, `:1256`, `:1294`, `:1330` | **all six unaltered** |
| item 12 census — no `Repo` in `guts-ledger` | own `mode=ro&immutable=1` sweep of the three `objects.db` | **exact**: guts `{Vector 6835, LedgerRecord 5186, WorkOrder 83, Repo 5}` = 12 109; guts-code `{Vector 6705, Repo 5}`; guts-ledger `{LedgerRecord 17 430, WorkOrder 207}` = 17 637, **no Repo row** |
| item 11 — `xa` A.5(i) has 10 rows / 11 witnesses | read the table | **10 data rows**, R6 carries `floor`+`ceil` |
| item 23 — no `BEGIN`/`ROLLBACK` in the four `idxshape_*.sql` | per-file `grep -icE` | **0, 0, 0, 0**; `runtime.sql` 7 (plpgsql bodies). `hazard.sql:40` INSERT, `:49` DELETE |
| item 5 — 5 `worker.started` records | parsed `.autodev/events.jsonl` | **exact five timestamps**, incl. `2026-08-21T17:37:12.815Z` |
| `grep -i refus` = 0 in `xb`, `xd` | ran it | **0 and 0** |
| 4 `[consistency N]` marks, all in `xb` | `grep -o` over `.parts/` | **74 `[consistency]` + 3/12/18/23, all four in `xb`** |
| xc's refusal closed itself one round later | read `xc:237` / `FINDINGS.md:3876` / `:5378` | **"(19 ids)" present; final-check row present** |
| `f0:71-73` names 4 records, log `:5235-5236` names 5 | read both | **confirmed**; `grep -in 'fourth\|final-check\|4th' .parts/f0-header.md` = **0 hits** |
| `probe_extra.py` is the only writer, truncating | read the file | `out = {}` `:20`, `json.dump(..., "w")` `:100`, sets only `payload` `:36` and `poison` `:69-96` |
| corpus gone; `xpr` survives | read-only psycopg2 to `autosql_spike` | **`pg_tables` outside system schemas = 0 rows**; `xpr` = **21 functions** |
| B2÷A = 3.79×–7.15× | recomputed from `analysis/measurements.json` | **4.152 / 3.892 / 3.794 / 4.363 / 6.713 / 7.152** |
| +463% arithmetic, 11 citations | `grep -o '463%' \| wc -l`; recomputed | **11**; `(6916.85+1493.92)/1493.92 = +463.0%`; `(33.30+1493.92)/1493.92 = +2.2%`; `6916.85/40.76 = 169.7×` |
| **the 130-case jsonpath run** | **ran `proto/idxshape_jsonpath_130.py` myself** against `autosql_spike` | **exact, cell for cell** — 114/0, 10/10/9/1, 6/6/2/4, 130/16/11/5; all 16 case indices, jsonpaths, `expr`/`raw`/`sIS`/`lax` columns match `FINDINGS.md:1879-1901`, **including case 33 `$.x == null` → expr True, strict raw NULL, DIVERGES**. `idxshape_fixture_subset.py` standalone → 114/10/6/130 |
| 68/130 subset coverage | re-tallied `analysis/subset-coverage.json`'s 130 records | **panel 84 IN / A 68 / B 62 / C 56**; panel-IN→A-OUT = **16**, `{% 7, round 5, floor 2, ceil 2}` |
| `degenerate_baselines` | parsed `results.json` | `{true 20, null 19, false 15, zero 1, empty-string 0}` |
| nothing in the spike is under git | `git ls-files spikes/T-1/` | **1 file: `FRAMING.md`.** Everything else untracked, so the trail's "no baseline exists to diff" is right — and broader than it says |

Also independently confirmed: the trail's §3.4 caveat is correct and important. `idxshape_jsonpath_agree.py`
renders `$.score > 90` as the **filter** form `$."score" ? (@ > 90)`, while the published 130-case table and
the new instrument both use the **direct** form `$."n" < 7`. The AST→jsonpath convention is genuinely
supplied by the reconstruction, not by either named instrument.

Incidental, and it cuts the trail's way: verification correction **5**, which the trail lists as unapplied
but explicitly declines to endorse, is **itself wrong**. `expr.py`'s unary `+` really is at **180-182**, as
`FINDINGS.md:947` publishes; the verifier's "179-181" is off by one, and parentheses are at **205-209**, not
the verifier's "204-208". The trail was right to leave it in *not established*.

## 2. Defects

### A. MATERIAL — "an argument the document never concedes" is false

The trail's one headline *weakening* finding (§2.5, and the structured `bearing`) is that the +2.2%
fallback is an objection *"the document does not concede"* — *"`f4` §4.11 discloses the missing producer
but never states what the number falls back to."*

`FINDINGS.md:2875`, `f4` §4.10 item 10, states it verbatim:

> "`probes.json → poison` **still carries the superseded values** `time_to_raise_ms: 33.3`,
> `total_fallback_ms: 1527.22`, `overhead_pct: 2.2`. **A reader who opens the raw file first gets +2.2%,
> not +463%**" — Material? **"Yes, for anyone re-deriving"**

The trail **quotes this same line in its own §2.2** and then writes the opposite two sections later. The
document also already labels +463% *"a construction, not one observed event"* (`:2838`), states that every
claim resting on the orphan blocks *"inherits that"* un-auditability (`:2894`), and books the whole thing in
a table headed *where the raw data disagrees*. What is genuinely new in the trail is only the **strike
arithmetic** — that removing the orphan block leaves +2.2% as the sole retained price. That is a real
contribution. *"Never concedes"* is not supportable.

### B. MATERIAL — the seat-count contradicts the trail's own table

`trail.md:78-80`: *"Across all six passes there were **9 + 1 + 9 + 3 + 7 + 1 = 30** seat-instances. **Reports
survive on disk for 9 of them.**"*

The sum covers passes 3, 3b, 4, 5 and 6 only. The trail's **own** pass table (`trail.md:22-23`) lists
pass 1 = `f1–f5 (+f0)` = **6 seats** and pass 2 = verifier + critic + **3 panel seats** = **5 seats** —
eleven seats it counts as passes and then omits from the total. `panel.json` is a 3-element list
(CONDITIONAL-GO / NO-GO / CONDITIONAL-GO), so the 5 is right.

Corrected: ~**41** seat-instances, with records surviving for **all eleven** omitted ones (the part files
themselves, `verifications.json`, `critic.md`, `panel.json`). The published fraction — 9 of 30, 30% —
understates surviving coverage by about half (≈20 of 41, ≈49%) in the direction that makes the trail
gap look larger. The structured result repeats "30 seat-instances total" as established.

### C. MATERIAL — three reported command outputs do not reproduce

The trail's stated method is *"Anything I ran is named with its command and its actual output."*

1. `grep -rn 'probes.json' proto/ analysis/` → **4 hits**, not "one hit": `proto/probe_extra.py:99`
   **plus** `analysis/measurement.md:306, 468, 810`. (`trail.md:236`; repeated in the structured proof.)
2. `grep -rn synchronize_seqscans proto/ analysis/` → **3 hits**, not zero:
   `analysis/measurement.md:639, 643, 644`. `trail.md:244` qualifies this as *"zero hits in any retained
   script"*, which is true; the **structured result drops the qualifier** and asserts zero. This matters
   beyond pedantry: `measurement.md:639-644` is a **retained prose account of the syncscan experiment's
   method** — *"`synchronize_seqscans = on` (the default) | 40.8 ms | the scan happened to start 7 pages
   before the poison row"* — so the orphan block is not quite as method-less as "no retained instrument
   anywhere" implies. No script; but a described method.
3. `grep -i refus .parts/f5.md` → **12 hits**, not the reported 8 (12 by line and by occurrence;
   `grep -icw refuse` = 2). `trail.md:125`. The substantive conclusion — none concerns refusing a punch
   repair — holds; I read all twelve.

### D. COSMETIC — cite drift

- `out = {}` is `probe_extra.py:20`, not `:19`.
- The *"performance leg — firmer"* sentence is `FINDINGS.md:4682`, not `:4684` (`:5192` is exact).
- The reassembly delta is **9** `---` lines + 19 blanks, not *"the ten `---` separators"* —
  `f0-header.md` already ends with one.
- `xpr_decomposition_100k_ms` is named **twice** in `FINDINGS.md` (`:2547` and `:2892`), not "cited once".
  The second is the disclosure bullet, so the conclusion (nothing rests on it) is unaffected.

### E. COSMETIC — "210-fold reduction in the priced worst case"

`trail.md:335`. 210× is the ratio of **overhead percentages** (463.0 / 2.2). The priced worst case in
milliseconds falls **8 410.77 → 1 527.22, a 5.5× reduction**. The structured result's phrasing ("prices at
+2.2% — 210× smaller") is fine; `trail.md`'s reads as though the absolute cost estimate collapses 210-fold.

## 3. Bearing

Unchanged from the trail's, with one correction. The NO-GO stands. The trail's re-derivations are sound —
I reproduced the two it offered as independent work (the C3 re-bisect and the 130-case jsonpath run) to the
digit, and every retained-artifact measurement I touched came back exact. Its account of the **process
gaps** is where it overreaches: the +463% exposure is real and worth the owner's attention, but the document
**does** disclose the +2.2% fallback and does label the composite a construction, so this is a *sharpening*
of a disclosed weakness, not an undisclosed one. And the trail's own coverage statistic understates how
much of the audit trail survives.
