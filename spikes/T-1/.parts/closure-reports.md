# T-1 closure-pass agent reports

## Finding 1 — Conformance

CORRECTIONS APPLIED (all 11 from verifications.json, each re-checked against its named raw source): wall_clock_granularity IS exercised out-of-fixture (E_dates.txt:56-57, 2 probes, both AGREE) — my "not exercised" was wrong; the real gap is that a single-row single-query probe cannot separate per-record from per-query clock. Third prose-vs-raw disagreement added (CONFORMANCE.md:157 "every entry in_fixture:False" vs compile.py:124-133 in_fixture:True). D8 corrected 15/27 → 10/27, D9 no longer double-counted. §1.7 corrected: NC11/12/13 call matches() directly (conformance.py:1010-1031), never drive the per-case loop, so outcome-assignment at :376-455 is unexercised — "COMPILED_DIVERGES is reachable" downgraded to INFERENCE. D18 gains the string-level I3 rates (upper 4/10, lower 3/10, Greek final sigma). D15 split into K1 proxy (21.84%, not through compile.py) and K2 end-to-end (6/10). D1 "16 of 20 f8-reachable" → 16 of 20 probed = 16 of 16 f8-reachable. H denominators corrected to 3881/3880/3867 ran. Battery count → 19 scripts + differ.py, 21 run_all.sh runs. expr.py:415 → :413. D17 → 1 of 2 configurations. D5's "1.8987% of doubles" flagged as a decimal-decade share.
REJECTED: none. Every correction held against its raw source.
GAPS CLOSED: 3 — D22 reduced live via differ.py to `if(number("１２３"), null, true)` (31 chars); cause = D8's ASCII numeric gate in an if() CONDITION, both branches agree in isolation, Python takes then (None), SQL takes else (True); mechanism generalises — verified for D8, D1–D5 and D10, with a control that agrees (§1.9.5). 6 — read-only re-run of H_ast_fuzz.py (seed 99) reproduced its capture exactly, then re-scored each DIVERGE with conformance.py's existing deep_strict: 21 of 44 are container-comparator artifacts (all container-valued), 23 real (all scalar); real rate 0.593% not 1.100%; and 23 of 23 real cases carry a magnitude ≥1.7976931348623157e+296, so extreme found no cause D1–D5 does not explain (§1.9.6). 16a — numeric_literal_inf IS tested (coverage.md:133-142) and re-verified live. 16b — A_range/A2_boundary folded in as superseded by A_f8_guard §A2/§A3; M_encoding_guc §M1 now the stated GUC condition on the headline; B2_overflow records that the f8 guard MASKS + - sum() overflow, so fixing D1–D5 enlarges the 22003 class (§1.9.7). 16c — reproducibility boundary stated: A_range/A2_boundary/B2_overflow are not regenerable by run_all.sh, and differ.py was edited at 11:58 so earlier captures ran a different comparator. 16d — JS leg labelled an assumption; byte-identity is the partial mitigation. 16e — CLOSED by running conformance.run() twice in-process (SELECT-only, main() never called, proto/ byte-unchanged): both runs and the committed results.json cases array share sha256 9fc36644…, byte-identical three ways.
STILL OPEN, with the step named in §1.11: the 130 at other extra_float_digits values (68 of 130 exposed; conformance.py:341 hard-codes the GUC and instruments may not be edited here); reachability of the three non-pass outcome labels; the JS leg; wall_clock granularity; the string-level lower()/upper() rate; reachability of D1–D23 in real GIMS data; any loud-fallback mechanism.
EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/f1.md

## Finding 2 — Coverage and fallback

(agent died: API connection lost mid-response; file untouched)

## Finding 3 — Index shape

Section revised in place, database left as found (200 000 rows, `idxprobe_pkey` only, every DDL rolled back).

CORRECTIONS APPLIED — all 13, none rejected; each re-checked against the source it names:
- LOAD-BEARING 1 (§3.5(a)): reproduced live in a rolled-back txn — bare lax 10.498 ms / bare strict 9.709 ms both get `Bitmap Index Scan` on the GIN (7 index buffers); `IS TRUE` → `Parallel Seq Scan` 29.800 ms, and with `enable_seqscan=off` a pkey bitmap + Filter (21.685 ms, `Rows Removed 40015`), compiled W1 same session 177.344 ms. **Extension the verifier did not have:** lax `IS TRUE` loses the index identically (21.850 ms) — the cause is `IS TRUE`, not `strict`. Headline withdrawn; requirement narrowed to top-level-WHERE-conjunct and justified by measurement: `NOT (bare)` keeps 40 015 rows vs `NOT (IS TRUE)` 190 015, and `expr` keeps 190 015 (`_eq` total, expr.py:363-367) — bare under negation silently drops 150 000/200 000.
- LOAD-BEARING 2 (§3.5(d)): case 33 written as a MEASURED SILENT DIVERGENCE (expr True / lax False / strict NULL), disqualifying per FRAMING §5 + §4 NO-GO. Also measured: `== null` is one of only two shapes that *are* index-accelerated.
- Material/cosmetic: Answer absolute rescoped (v_operand + v_t7d created live); 4 root types = 9 of 11 (D1/S1 roots quoted); inlining corrected (native `>` in W2's filter, `xpr.truthy` inlined for W1/W6); 0.5-vs-0.3333 re-attributed to inlining (W7 falsifies the old rule); write-cost B-trees shown all-NULL (regenerated TSV: 20 000/20 000 LedgerRecord, `score` absent on all); 152 not 150 field names (Sterility list-form); buffers column relabelled hit+read; J2/J3 labels + all citation drift fixed (0002:36-37, 0001:13-18, sql.py:252-262, writecost:18-21); "on any key" relabelled INFERENCE; §3.6 heading de-overclaimed.

GAP 10 CLOSED — (i) J5 re-run read-only: 4807 / 4807 / 9985 / 9985, reported with its denominator (0 `Submission` rows lack `score` or `status`, so its corpus cannot contain the divergent shape). (ii) All 130 fixture cases through strict `@@ … IS TRUE`: 16 expressible, **11 agree, 5 diverge**, 114 not expressible; per-class and per-case tables in §3.5(d). New divergence class found and recorded: bare path 4/6 diverge (`@@` yields the item only when it is a JSON boolean). New measurement of which operators earn an index condition: `==` and `== null` only; `!=`, `<`, `>=` are filters even with `enable_seqscan=off`. Honest fraction: expressible 12.3% · agreeing 8.5% · index-accelerated 3.1% · **index-accelerated and agreeing 2.3% · routable 1.5% (one distinct shape)**.

ALSO FOLDED IN from the verification notes: BRIN tested-and-rejected (24 kB, unused); the §10.2 emission rule, rewritten as new §3.9 with FRAMING §5's storage-layer clause; the recon 11-vs-6 opclass contradiction reconciled live (btree 5 / gin 6 / gin path_ops 3 / hash 1); distinct-expression denominator (113); the synthetic-`score` provenance caveat.

OPEN, each with its one closing step (§3.8 table): index-accelerated form of the value-position predicate; cause of the 4 416 kB vs 6.5 MB size lineage; write cost on representative rows; the 0.585/24.9 ms prose-only figures; H2's 19×; second-key generalisation; array divergence on real GIMS data; the 17 087→17 110 ledger snapshot; and the 130-case script's lack of a committed artifact (`proto/` read-only this pass).

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/f3.md

## Finding 4 — Measurement

Applied 12 of 13 verification corrections; rejected 1; closed gaps 11, 14, and 12's measurement half.

**Applied (verified against the named raw source first):** (1,2) the widget is an assembly of three attested fragments, not a quotation — docstring `where` is `"$.days_left < 7"` (`sources.py:25`), the full-pipeline test is `"$.days_left != null"`/`limit:1` (`test_dashboard_sources.py:85-95`); clause-by-clause table added. (3) split under-reports Path A at 5 of 6 sizes, not all. (4) B2-vs-B3 is a *predicted* null result — re-measured live myself at 100 k: 6 137.7/6 144.8 ms vs 3 723.8/3 887.8 ms with the equality first, ratio 0.607–0.633 against the expected 0.601. (5) the 99.6% is the combined effect of five simultaneous changes; §4.8's comment block rewritten. (6) EXPLAIN pair restated (+36.8%/+7.9%, B3 21% *faster* under EXPLAIN — cause not established). (7) the 20 001 onset was never measured. (8) error band split — my own re-check at load 29: `xpr.pdate_ms` +246…+282%, `plus_field_read` +31…+34%, native −17…+10%. (9) `B2÷A` 3.79×→2.55× stated in the headline's own units. (10,12,13) all citation/size fixes confirmed and applied.

**Rejected:** correction 12's claim that the RAG profile block runs to `sql.py:252`. Line 251 is `# profiling proving the scan is the bottleneck, and it is not.`; **252 is code** (`_INDEXABLE_FIELDS = frozenset({...`). The original `240-251` stands.

**Gap 11 (closed):** re-derived from `idxshape_plans.json` myself — W1 2.69, W6 2.71, W2 7.25, W3 22.98, W4 65.70 µs/row; date predicate **24.4×** an equality, and W4's 65.7 matches this rig's B2 at 59.6. Localised further: plpgsql `xpr.contains` costs 3.1 µs/call while plpgsql `xpr.pdate_ms` costs 21–30 — so "plpgsql" is the wrong category. Stated as order-of-magnitude (two rigs, two tables), and "replace the runtime" vs "fix the date path" named as different recommendations.

**Gap 14 (closed):** LIMS-System widget connected in §4.1 with a clause table; warrant raised to "documented **and** matched in shape, n = 1"; its `where` reads a **stored** field, making it easier to push down (INFERENCE, never timed).

**Gap 12 measurement half (closed as far as evidence reaches):** trigger cost stated as trigger cost — and corrected to **0.0307 ms** (`plan_ms` 0.026605 excludes `detect_uncompilable_ms` 0.004079, my finding); +463% labelled a two-probe composite; explicitly does not bound the silent classes; machinery's standing cost marked not established with the step that would establish it.

**Open, recorded:** MAX_SCAN onset between 20 k and 25 k; LIMS-System widget timing; expression index on the derive; the quiet-host decomposition + clock-hoist run; `probes.json`'s three producer-less blocks; the two asserted provenance claims.

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/f4.md

## Cross-cutting A — is `expr` total? The premise FRAMING §5 rests on

ESTABLISHED:
1. The premise is FALSE as stated. `expr.evaluate()` raises on data through **8 mechanisms across 9 source lines and 4 exception types** (`OverflowError`, `ZeroDivisionError`, `ValueError`, `RecursionError`) — `expr.py:430` (date-offset arithmetic outside its `try`), `:521/:525/:526/:527` (four independent `_fn_round` sites), `:545/:546` (`floor`/`ceil` of ±inf), `:624` (`math.fmod` infinite dividend), `:375` (`_eq` structural recursion). Every witness re-run by me in the GIMS venv through the public `evaluate()`, with measured thresholds (ndig ≥ 309 / ≤ −324; nesting 497 ok / 498 raises; 9 of 3 652 059 calendar dates = 2.464e-06).
2. Root cause common to 4 of 8: `_to_num` (`expr.py:306`) promises "never returns NaN" and keeps that promise, but returns ±inf freely; nothing re-checks finiteness downstream. R2–R5 are reachable from tenant-written expression text alone, with no unusual stored data.
3. RECONCILED. f2's count is right, its inference is wrong: the 403-probe domain (max |value| **2026.0**, max nesting **4**, `round` ndigits ∈ {−1,2}, **0** occurrences of `%`, **0** offset-bearing dates) cannot reach any raise site. Same structural explanation covers 0/130 fixture and 0/12 000 H-fuzz. E_dates (4/45) and G2b (65/8000 = 0.8125%, re-derived exactly at seed 13, 100% at `expr.py:526`) are the only two instruments whose generators reach one.
4. CONSEQUENCE. Of 11 witnesses run through the existing `differ.py`: 4 are **raise → value** (§5's own disqualifying direction, arriving from the Python side), 3 raise → null, 3 both-raise. `sources.py:147` and `:162` call `evaluate()` **unguarded**; one poison row in any position of a 10-row list produces an uncaught exception → `core/errors.py:115-119` → **HTTP 500**, entire widget lost. So the in-memory fallback can itself raise: on G2b's domain Postgres raised 159 times and Python raised on 65 of the same 159 — **the fallback rescues 59.1%, 40.9% die in the fallback too**. `sources.py:335`'s "never crash" contract is false today, independent of this spike.
5. NARROW TRUE FORM given in §A.4 (N1–N4). N2/N3 are statically refusable only when `round`'s 2nd arg is literal; N1/N4 and most of N2 are row-dependent, so the compiler cannot fix this — the in-memory path must be made total in GIMS first.

NOT ESTABLISHED: production frequency of N1–N4 inputs (would need a read-only value-domain sweep of the record stores); whether R6/R7 are reachable under H's generator given more draws (0/12 000 bounds ≲0.025%); and the JS mirror's behaviour on the 8 sites — JS has no `OverflowError`, so `frontend/lib/expr.js` very likely diverges from Python there, which the fixture does not bind. Establishing it: run the 8 witnesses through `frontend/lib/expr.js` under node.

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/xa-totality.md

## Cross-cutting B — `filters`, `sort`, `limit`: the half of the question with no evidence

Section written: `/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/xb-filters-sort.md` (250 lines, §B.1–B.11).

**Established (all measured, cited in place):**
1. Semantics of `_field_value` (`sources.py:67-85`), `_pass_filters` (`:88-96`), `_sort_key` (`:99-115`), `_apply_sort` (`:168-177`, stable both directions), `_apply_limit` (`:180-187`, `"abc"`/`-1`→unlimited) — with `find_actual_key`/`_norm_key` (`core/deep_search.py:19-39`) as the tolerant-match cause.
2. `tolerant_key_probe` verified and re-derived: Python keeps `T-1,T-2,T-3`, compiled `(data->'status')=…::jsonb` keeps `T-1` only. Blast radius = **any ASCII case/space/`_`/`-` difference** (measured against 14 spellings); tab/newline/accents/fullwidth do **not** match. GIMS locks the behaviour in `tests/test_dashboard_sources.py:169-177`.
3. **New, and the strongest item:** tolerant matching is *ambiguous* and the ambiguity is in real data — read-only census of `gims-ledger/projects/*/objects.db` finds `run_id` + `_runID` (both → `runid`, different values) co-occurring on **4 166/17 342 (24.0%)** rows of `guts-ledger/instances` and **1 966/12 095 (16.3%)** of `guts/instances`. Because `jsonb` does not preserve key order, the *same* Python call resolves to `run_id=""` off SQLite and `_runID="one-body-phase-1"` off Postgres — a store migration changes the answer with no pushdown involved.
4. `filters` value comparison also diverges: `1 == True` (Python) vs `false` (jsonb); missing-key vs `filters {"k": null}` (Python keeps, SQL drops).
5. Sort mismatch re-run and confirmed: **9 of 9 positions differ**; rank-3 (container) keys use Python `repr` and depend on document key order — **uncompilable**, not merely uncompiled.
6. Obligation table: **10 substantive obligations, 0 compiled, 0 tested, 0 fallback-ruled**; `find_actual_key`/`_pass_filters` have **0 mentions across all five findings**.
7. Gap 15 recorded with five measured cases: chaining works two levels; reversed mapping order yields `urgent=None` **silently**; shadowing overwrites stored keys and later derives read the shadowed value; rows mutated in place.

**Could not establish (named in §B.11):** production `DataSource` usage of `filters`/`sort`; whether tolerant matching is compilable at all; whether `bench.py`'s rank-triple agrees with `_sort_key` over mixed types; derive chaining for n ≥ 2 (needs new machinery — FRAMING §3 forbids it here); the magnitude of SQL-vs-Python sort instability (prose-only, absent from raw).

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/xb-filters-sort.md

## Cross-cutting C — the complete divergence → fallback register, and what the machinery costs

Only my file was written (sibling seats wrote `xa-`/`xb-` concurrently; the `__pycache__` byte is another seat's read-only re-run).

ESTABLISHED: one register of **43 divergence ids** — Block A compile-time C1–C4, Block B run-time D1–D23 + R1/R2/R5/R6, Block C source S1–S3, Block D storage H1–H4, Block E jsonpath J1–J2, Block F clause-level K1–K3 — each with cause, measured rate + witness, direction, §5 verdict, detectability and a fallback rule or a stated reason none is possible.

THE COUNT (34 `expr`-layer ids in Blocks A–C; 33 distinct classes once D21 folds into D1–D5): **15 DETECTABLE at query time, 19 ids = 18 classes UNDETECTABLE in principle** — half the register. **13 had no rule anywhere** (critic gap 1's list reproduced exactly), and **both FRAMING §5 breaches, D22 null→value and D11 raise→value, are inside that 13**. **9 breach the §4 NO-GO bar** in Blocks A–C, +7 outside.

CORRECTED: `f2` §2.8's "five run-time divergences undetectable in principle" is **18 of 33 — 3.6×**, confirming the critic's ~2.5× estimate as low.

NEW CLOSURE, from existing evidence only: **R1′** (catch SQLSTATE 22003 for overflow *and* underflow, any operator, plus `xpr.round`'s internal overflow) covers 6 ids, 4 of them in the unruled 13; D19 additionally admits a compile-time `abs(index) < 2^31` check; D20 is write-side. **Eight remain with no possible detection rule** — D8, D10, D11, D13, D15, D16, D22, D23. For those the only §5-compliant answer is AVOID (static construct-keyed refusal), priced at 36/48 constructs and 84/130 cases, with D13 a known hole.

MACHINERY (OPINION, reasoning shown): sized `f2` §2.8's seven items by blast radius — R3's "one line" is mispriced (it unmasks a raise population), C3/C4 rewrite the compiler's traversal, and the return-contract field is load-bearing. Standing obligation: **3 runtimes / 4 artifacts / 3 languages** (expr.py 646 + expr.js 373 + compile.py 464 + runtime.sql 427 with 21 `xpr` functions) against a 130-case fixture that provably does not detect 18 of the classes. Labelled a permanent unbounded coupling; not measurable here.

COULD NOT ESTABLISH: reachability of any class in real GIMS data; completeness of the AVOID subset (never run); D18's string-level rate; K3 `derive` chaining; and whether the in-memory fallback itself always succeeds (three mechanisms by which `expr` raises).

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/xc-fallback-register.md

## Cross-cutting D — is any of this reachable from real GIMS data?

Established, all from a strictly read-only sweep of every real corpus in both trees (37,078 rows · 5,236,427 numeric nodes · 495,115 strings), cross-checked by two independent instruments that agree to the row:

1. **D1–D5 (297-digit `f8` guard): 0 hits.** Largest `|v|` anywhere is 1,787,169,706,037 — 284 decimal decades below the guard. Query published.
2. **D8/D10 (non-ASCII digits/whitespace): 0 hits** — and the zero is load-bearing because the corpus carries 218 distinct non-ASCII code points, 206,567 occurrences, in 81.86 % of rows. It is not an ASCII-only corpus.
3. **D12–D14: 0 hits, and no writer here that could make one.** All 5,236,427 numeric literals equal `repr(float)`/`str(int)` exactly, and all 36,372 rows are `\uXXXX`-escaped — a single `json.dumps` writer signature matching `core/storage/sql.py:362,563`.
4. **The tolerant/coercion class IS reached, at scale:** `$.human_required` = 17,144 bool-strings vs 4 real bools; `$.payload.blocked_since` = 315 numbers vs 9 ISO strings in one key (a **real** witness for `f3` H3, previously only constructed); LIMS weight fields 100 % strings; `'0002'`; `'60824'`.
5. **Null propagation is live in the one real dashboard's own data** — `due_date` absent on 42.9 % of `Submission` (the generator modelled 8 %). The widget's filter happens to remove exactly those rows: an n = 7 coincidence, labelled as such.
6. **MAX_SCAN:** largest real collection 17,148 = 85.7 % of 20,000; 0.8 / 3.5 / 7.4 / 49.4 days to cross on four growth bases.

Could not establish: whether the compiled SQL diverges on these real witnesses (that is a new experiment); whether a non-Python writer exists elsewhere in GIMS; whether production resembles this (n = 1 machine, 60.2 % of rows are AutoDev's own ledger, tenant data is 222 rows); WAL contents (543,872 bytes invisible to `immutable=1`); dashboard usage (still n = 1, now confirmed live rather than only in backups). Each names what would answer it. No extrapolation to production.

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/xd-reachability.md

## Finding 5 — Recommendation

Finding 5 is written to `/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/f5.md` (344 lines, within the 150–350 band).

**VERDICT: NO-GO on the architecture as scoped** — *a standalone AST→Postgres-SQL compiler plus a thin GIMS adapter*. I side with the panel minority (`panel.json[1]`), on evidence two of the three seats did not have. The section states each of the three verdicts, who held it and the one fact it turns on; it does not average them. It is explicit that `decision_authority` is `recommend-and-wait` and that `human:owner` rules at `sp_decide`, and §5.7 supplies the corrected subset and its conditions in case he rules the other way.

**THE CONTESTED POINT, as I put it to the decision-maker:** does a FRAMING §5 breach found *outside* the nominated fixture disqualify the ARCHITECTURE, or only this THROWAWAY PROTOTYPE? I reduce it to one decidable sub-question — **is the 130-case fixture an adequate acceptance test for a third runtime of this language?** — and the evidence answers no: 130/130 was achieved while both §5 directions were breached; 6 of 7 `KNOWN_DIVERGENCES` entries are `in_fixture:false`; the fixture holds zero `sort`/`filters`/`limit` cases; 68 of 130 exist at `extra_float_digits=1` only; 0 of 130 reach any of the eight sites where the *reference* evaluator raises.

**THE FACTS IT TURNS ON**

1. **The only named subset in the record still contains two of the four measured §5 raise→value breaches.** `panel[0]`'s subset keeps `round`, `floor`/`ceil`, `%` and `==` — 7 of the 8 mechanisms by which `expr` itself raises (`xa` A.2). Re-verified live this pass through the existing `analysis/fuzz/differ.py`: `round($.a,$.n)` on `{a:1.0,n:"1e400"}` → Python `OverflowError` at `expr.py:521`, **SQL returns the number `1`**; `$.a == $.b` on containers nested 498 deep → Python `RecursionError` at `expr.py:375`, **SQL returns `true`**. So the residual divergence rate of that subset is not low, it is **unmeasured** — and the assumption behind it is demonstrably false, not merely unproven. (`differ.py` buckets both as `PY_RAISE`, so a reader counting `DIVERGE` lines never sees them.)
2. **Gap 13's conjunction, which no section stated and which I state plainly: there is no measured configuration in which pushdown as prototyped is simultaneously faster than today's path and no less correct** — (a) 2.55×–7.15× slower at every size, gap widening; (b) no index containing compiled output can be *created* at all (`to_jsonb` is `STABLE`; 0 of 36 plans; four compiler changes gate it); (c) 0 fallbacks reported and **18 of 33** classes undetectable in principle, 3.6× the body's figure, both §5 directions inside it; (d) two of the four clauses in the question have zero evidence, with **ten obligations, zero compiled/tested/ruled** and two uncompilable in principle. And they are coupled: (b) blocks the fix for (a), the fixes for (c) cost (a), and (d) removes the win (a) was to be traded against.
3. **A new number that falls out of (d):** the headline **19 667.5×** payload win is produced by `ORDER BY … LIMIT 50`. With `sort` outside any subset, `LIMIT` goes with it, and a `where`-only pushdown returns the qualifying set — measured at 5.00–5.35% across all six sizes — i.e. **16.59 MB, 19.1×**, not 19 667.5×. The sort+limit half is the other 1 029×. (INFERENCE; arithmetic mine, inputs re-derived from `analysis/measurements.json`.)
4. **The adapter cannot be thin**, which falsifies the architecture by name: five required changes live in the GIMS tree, not the compiler — the `pushed_down`/`fallback` contract + UI badge, a per-row `try/except` (today one poison row 500s the whole widget and the in-memory retry itself raises on 40.9% of the one measured domain), tolerant key resolution, `_sort_key`, and `derive` ordering/shadowing.

Strongest argument against my verdict is quoted at full strength in §5.6 (130/130 by a harness with 23/23 negative controls; `xd`'s **zero** production witnesses across 5 236 427 numeric literals and 1 096 202 strings; a status quo already wrong at 4% recall with the largest real collection 0.8–7.4 days from crossing the cap), with my three-part answer. §5.8 sizes the fallback machinery, §5.9/§5.10 state what the spike delivered and cost (token/currency cost **not established** — `.autodev/metrics.jsonl` has no cost fields), §5.11 names the two experiments (E1 subset acceptance battery, E2 like-for-like performance run) that would convert the verdict.

EVIDENCE: /home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.parts/f5.md
