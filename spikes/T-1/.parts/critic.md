# T-1 sp-investigate — completeness critique of findings 1–4

Read: `.parts/f1.md`, `f2.md`, `f3.md`, `f4.md`, `f0-header.md`; `FRAMING.md` §§3,4,5,8; the ticket spec; `analysis/fuzz/*` (all 25 captured outputs + `differ.py`, `run_all.sh`); `proto/results.json` `meta`, `analysis/probes.json`, `analysis/measurements.json`, `analysis/index-shape.md` §1.2; `GIMS-Project/api/dashboard/sources.py`.

**What is complete and needs no further work:** f2 §2.9 (the `query`/`cascade_deep_search` bound — confirmed, bounded structurally, and the usage fraction explicitly refused as uncomputable); f3 §§3.1–3.4 (generated SQL, the three catalog causes, the required DDL and its four prerequisites, with a fair positive control at §3.2 showing the GIN index working); f1 §1.4 (per-case, all 130, never a summary count); f4 §4.7 (`MAX_SCAN` as a correctness boundary — counts, immune to the load caveat). **No stop-rule violation by chasing was found**: f2 §2.10 "Compliance", f1 §1.9 preamble and f3 §3.8/§12.2 all record defects un-fixed, as `FRAMING.md` §3 requires. The omissions below are the other stop-rule failure mode.

---

## 1. Thirteen of the 23 confirmed divergence classes have no fallback rule anywhere

(a) **Missing:** `FRAMING.md` §3 stop rule: "a divergence whose cause is identified → record cause **+ fallback rule**". f1 §1.9.2 records causes for D1–D23. f2 §2.7 is the only fallback table in the body and it holds C1–C4, R1–R7, S1–S3. Mapping the two together, R1↔`overflow_via_multiply`, R2↔D9-adjacent, R3↔D1–D5, R4↔D18, R5↔D16, R7↔D12. **Uncovered by any rule: D6, D7 (float8 *underflow* raises), D8 (`xpr.num` ASCII gate vs Unicode `_to_num`, 15/27), D10 (`btrim` vs `str.strip`, 22 in E2), D11 (raise→value), D13, D14 (sub-float8 jsonb numerics), D15 (`sum()` Neumaier, 21.84% on random lists), D16 at the pinned `efd=1`, D19 (int4 index), D20 (NUL byte), D22 (null→value), D23 (row loss and gain).** Thirteen classes, including **both** of FRAMING §5's named directions.

(b) **Belongs to:** `FRAMING.md` §4 finding #2 ("the explicit fallback rule for each"), §3 stop rule, §5; ticket FINDINGS REQUIRED #2.

(c) **Where the answer would be:** nowhere yet — the rules do not exist. The inputs to write them are `.parts/f1.md` §1.9.2 (cause + direction per class) and `analysis/fuzz/{B_overflow,C_numgate,E2_dates_ws,E_dates,K_sum_neumaier,L_misc,O_row_loss}.txt`. This is the single largest reason the gate cannot be answered: f2 §2.8's verdict ("five run-time divergences R2–R5/R7 are undetectable in principle") is scoped to f2's own list of seven, not to f1's list of twenty-three, so the body understates the undetectable set by roughly 2.5×.

## 2. Cross-section contradiction: is `expr` total? f2 says yes and confirms it 403 times; f1's evidence says no

(a) **Missing/wrong:** f2 §2.4 states "**0 `PYTHON_RAISED`** over 403 adversarial inputs is 403 independent confirmations of the totality premise the design rests on (`recon/semantics.md` §11: '`expr.py` never raises for data reasons')." f1 §1.9.3 states the opposite in a table cell: "`expr` itself raises, contradicting `expr.py:640` and `recon/semantics.md` §11." The raw data is unambiguous and larger than f1's four witnesses: `analysis/fuzz/E_dates.txt` has **4 `PY_RAISE`** (`days_between` on `'0001-01-01T00:00:00+14:00'` → `OverflowError: date value out of range`, SQL answers `738886.5833333334`); `analysis/fuzz/G2b_round_raises.txt` records **`BOTH_RAISE` 65/8000 = 0.81%** with witness `round(1.7976931348623157e+308, 3.0)` → `OverflowError`; `analysis/fuzz/B2_overflow.txt` line 13 has a third mechanism. No section reconciles these, and none counts the mechanisms by which `expr` raises.

(b) **Belongs to:** `FRAMING.md` §5, whose entire argument is "`expr` is *total* — it never throws, it returns `null`. SQL is not." If `expr` raises on data, then (i) §5's "raise → value" clause needs restating, and (ii) **the in-memory fallback can itself raise**, which no section considers.

(c) **Where the answer is:** `analysis/fuzz/E_dates.txt:29-40`, `analysis/fuzz/G2b_round_raises.txt` (totals block), `analysis/fuzz/B2_overflow.txt:11-14`, against `recon/semantics.md` §11 and `expr.py:640`. Resolvable now; it is a reading of evidence already collected. This is the highest-value cross-section find: neither drafter could see it alone, and it changes what the non-negotiable means.

## 3. The one `null → value` breach — the fact that decides GO vs NO-GO — has no named cause and no minimal reproducer

(a) **Missing:** f1 §1.9.3 rules "**YES** breaches §5" on the strength of D22, a single witness at 1/4000 in the `unicode` AST-fuzz profile. `analysis/fuzz/H_unicode.txt` shows the witness is an unreduced 200-character generated AST (`if(round(min(if($.t,$.b,"１２３"),$.e)), max(("🙂" * days_between(true,$.a))), …)`) with **no cause analysis and no reduction**. `FRAMING.md` §4 #1 requires "Every divergence named with its cause (NULL propagation · numeric coercion · date parsing)"; D22's cause column in f1 §1.9.2 is the direction label, not a cause.

(b) **Belongs to:** `FRAMING.md` §4 #1 and the §4 NO-GO bar; ticket FINDINGS REQUIRED #1 ("Any divergence named with its cause").

(c) **Where the answer would be found:** `analysis/fuzz/H_unicode.txt`, "DIVERGE: NULL → value (1)" block — the record and expression are both recorded, so reduction is a bounded read, not a redesign (recording the cause is what §3 requires; fixing it is what §3 forbids). INFERENCE, labelled: the other three unicode-profile divergences all carry Arabic-Indic (`١٢٣`) or fullwidth (`１２３`) digits, which is D8's ASCII gate — so D22 is plausibly D8 surfacing through a boolean, but **that is not established by this spike**.

## 4. Two of the four clauses the spike question names — `filters` and `sort` — have no conformance or coverage evidence at all

(a) **Missing:** the question is whether `derive`/`where`/`sort`/`limit` can be pushed down. `derive` and `where` reduce to `expr` evaluation and are covered. `sort` and `filters` do **not**: their semantics live outside `expr`, in `sources.py:67` `_field_value` (exact key → **tolerant case/space/underscore** match → dotted path), `sources.py:88` `_pass_filters` (Python `!=`, missing field fails unless the value is `None`) and `sources.py:99-115` `_sort_key` (`bool < number < string < other < None-last`, applied through stable `sorted()` at `:168-178`). f2's 48-construct census (§2.1) is an `expr` census and contains none of this; grep confirms `_field_value`, "tolerant" and "filters" appear in **f4 only** (f4: 7 hits; f1/f2/f3: 0). `limit` inherits the problem, since `LIMIT 50` is only well-defined under a matching total order.

The witnesses exist and were explicitly handed off and then dropped: f4 §4.11 records `measurements.json → tolerant_key_probe` — records keyed `"status"` / `"Status"` / `"status "`, `path_a_ids ["T-1","T-2","T-3"]` vs `path_b_ids ["T-1"]`, **2 of 3 rows silently dropped** — and says it "belong[s] to the conformance and coverage seats"; neither took it. f3 §3.6 H4 measured the sort mismatch (`_sort_key` ascending `[false, true, 2.5, 5, "Zebra", "apple", [1,2], {"a":1}, null]` vs jsonb B-tree `[null, "Zebra", "apple", 2.5, 5, false, true, [1,2], {"a":1}]`, "SAME ORDER? False") and left it in the index finding, where a reader looking for a fallback rule will not find it.

(b) **Belongs to:** ticket spec QUESTION and FINDINGS REQUIRED #2; `FRAMING.md` §4 #2.

(c) **Where the answer could be found:** `measurements.json → tolerant_key_probe` (raw, complete); `proto/idxshape_sort_semantics.py` + f3 §3.6 H4; `sources.py:67-115`. The consequence — that pushing `filters` or `sort` requires reproducing tolerant key resolution and a 3-key type-rank ordering in SQL, and that neither is compiled, tested or fallback-ruled — is **stated nowhere**.

## 5. Reachability in production data was never attempted, although real GIMS data was open on this machine during the spike

(a) **Missing:** f1 §1.11 ("Whether any of D1–D23 is reachable from **real GIMS dashboard data**… every witness is a constructed record… **not established**… would need a scan of the live `instances` table"), f2 §2.9 (no `DataSource` corpus; usage distribution uncomputable), and f4 §4.1/§4.11 (no telemetry, one synthetic corpus) each declare the same gap independently. **None of them attempted the check that was available:** `analysis/index-shape.md` §1.2 records that the real **17,087-row `LedgerRecord` collection** in `gims-ledger/projects/guts-ledger/objects.db` was opened read-only (`mode=ro&immutable=1`) *during this spike* purely to measure key frequencies — and found, e.g., that `human_required` is the **string** `"false"` in real data.

(b) **Belongs to:** `FRAMING.md` §4's GO/NO-GO bar — whether a silently-wrong number is *reachable* is what converts f1 §1.9.3's "breaches the bar outside the fixture" into a priced decision; ticket NON-NEGOTIABLE.

(c) **Where it could be found:** the same read-only sweep of `gims-ledger/projects/*/objects.db`, asking whether any stored value falls in D1–D5's range (|v| ≥ 1.797693e+296), carries non-ASCII digits (D8/D10), exceeds 17 significant digits (D12), or was written by a non-Python path (D13/D14 — `fuzz/D_rawjson.py:12-17` already records that `gims-ledger/api/storage_aws.py:743-754` writes via `Jsonb(record)` and so cannot produce them, while `:694` will mis-read them). Honest to report as **not established**; not honest to leave unattempted when the corpus was in hand.

## 6. D21's 44/4000 headline is uncomposed, and its two published witnesses look like comparator artifacts

(a) **Wrong as it reads:** f1 §1.9.2 D21 reports "`extreme` profile: **44 / 4000 diverge (1.100%)** — 30 'different value', 14 'value → NULL'". Those are auto-clustered *direction* labels, not causes. `analysis/fuzz/H_extreme.txt` publishes two "different value" witnesses and **both are field reads of arrays containing `1e300`** (`expr : $.s`, py `[{...}, 1e+300, 0.5]` vs sql `[{...}, 10^300, 0.5]`): the mirrored rule compares containers with bare `==` while comparing scalars with the epsilon, so a jsonb `numeric` inside a list fails where the identical scalar passes (f1's own probe `f8_readback_1e300_no_arith` agrees on the scalar). f2 §2.4 already names this hole (NC6a/NC6b, "the known hole in the mirrored rule"). So an unknown share of the 1.100% may be comparator artifact rather than compiler divergence — and an unknown share may be worse than labelled.

(b) **Belongs to:** `FRAMING.md` §4 #1 ("every divergence named with its cause"), §8 (a harness whose comparator has a known hole must have that hole's contribution measured, not just acknowledged).

(c) **Where the answer could be found:** `analysis/fuzz/H_extreme.txt` (the 44 are clustered but only 4 printed) and `differ.py:44-50` + `:145-152` (the `compare_error → agree=False` path). The per-case breakdown was computed by `H_ast_fuzz.py` and not captured.

## 7. `FRAMING.md` §8's harness proof covers two harnesses and not the two that carry the decision

(a) **Missing:** §8 demands three distinguishable outcomes, demonstrated. **Demonstrated:** `conformance.py` — f1 §1.7, 23 negative controls, exit 2 on any failure, `NC13` ("`python=None sql=0`" caught) as §5 written as a test. `coverage_probe.py` — f2 §2.4, eight-outcome ladder plus 11 negative controls. **Asserted, not demonstrated:** `analysis/fuzz/differ.py` — the harness that produced **every** decision-relevant divergence (D1–D23) — has seven verdicts including `UNCOMPILABLE`, `SQL_RAISE`, `PY_RAISE` and `NULLNESS` by construction (`differ.py` `run_case` docstring), but **no section cites a single negative control for it**, and the relevant risk is the mirror of §8's: false *positives* inflating the divergence inventory (see gap 6). **Absent entirely:** `proto/bench.py` — grep for `NC`/`negative_control` returns nothing; every answer-quality claim in f4 §4.7 (recall 100/88/38/4%, `rank1_correct`, "IDENTICAL") rests on comparison code never shown able to fail. Partial mitigation, which f4 does not claim: the monotonic recall decay is itself evidence the comparator discriminates.

(b) **Belongs to:** `FRAMING.md` §8.

(c) **Where the answer would be:** it does not exist. Establishing it: inject a known-wrong SQL string into `differ.run_case` and into `bench.py`'s identity path and confirm `DIVERGE` / non-identity, exactly as `conformance.py` NC11–NC13 do.

## 8. The "one-line" `xpr.f8` fix is mispriced — the correction unmasks a class of query-aborting raises

(a) **Wrong:** f2 §2.8 lists "**R3** — fix the `xpr.f8` range-guard literal to 309 digits (**one line** in `runtime.sql`)". `analysis/fuzz/B2_overflow.txt` — **cited by no section** — states in its own header: *"The f8 guard clamps operands to <=1.7976931348623157e296, so `+` `-` and `sum()` **CANNOT overflow TODAY**. That is an accident of defect #1, not a design."* Fixing R3 therefore converts D1–D5 (silent value→null / value→wrong-value) into a new population of SQLSTATE `22003` aborts on ordinary `+`, `-` and `sum()`. f4 §4.9 prices exactly that failure mode as unbounded: **40.76 ms with `synchronize_seqscans=on` vs 6 916.85 ms with it off, worst case 6 917 + 1 494 = 8 411 ms, +463%**.

(b) **Belongs to:** `FRAMING.md` §4 #5 ("the cost of the fallback machinery") and §3 (record, don't chase — the *interaction* is a recorded fact, not a fix).

(c) **Where the answer is:** `analysis/fuzz/B2_overflow.txt` (whole file), read against f2 §2.8 and f4 §4.9 / `probes.json → poison_syncscan`.

## 9. The 130/130 is a result at `extra_float_digits = 1` only, and one uncited battery shows the GUC changes the *value*, not the rendering

(a) **Missing/understated:** `proto/results.json` `meta.extra_float_digits = "1"`; the fixture was never re-run at another value. f1 §1.9.2 D16 characterises the GUC effect as "a TEXT divergence"; f2 §2.7 R5 as "changes float **text**". `analysis/fuzz/M_encoding_guc.txt` — **cited by no section** — measures `to_jsonb(float8)` directly at `efd = 1 / 0 / -3` and returns `0.3333333333333333` / `0.333333333333333` / `0.333333333333`, with its own note: *"if these rows differ, the compiled expression's **RETURNED VALUE** is GUC-dependent, not merely its `string()` rendering."* They differ. That makes every compiled numeric result, not just `string()`, a function of a session GUC — which is the mechanism behind f3 §3.6 H1 and f1 D17's index/seq-scan split brain, and it makes "pin the GUC per session" (f2 R5) a correctness requirement rather than a formatting one.

(b) **Belongs to:** `FRAMING.md` §4 #1 (the conformance result's stated conditions) and §5.

(c) **Where the answer would be:** `analysis/fuzz/M_encoding_guc.txt` §M1 for the mechanism; re-running `conformance.py` with `SET extra_float_digits = 0` and `= -3` would establish how many of the 130 survive. Currently **not established**.

## 10. The jsonpath route — the only no-per-key-DDL option f3 found — has no conformance evidence, and the agreement measurement that exists was not reported

(a) **Missing:** f3 §3.5 measures `data @@ 'strict $."status" == "open"'` at **12.504 ms vs 139.9 ms compiled (11.2×)**, on the production index, with **no DDL per key** — the most attractive result in the whole index finding. Its correctness rests on **11 hand-chosen adversarial records** (lax 9/11, strict 11/11), which f3 itself labels "a hypothesis for the conformance harness, not an equivalence proof", and on which "2 of those 4 [index-accelerated] cases are `$.x == null`, whose jsonpath-vs-`expr` agreement is **not established**". f1's harness — the instrument built for exactly this — never ran against the jsonpath forms. Separately, f3 §3.7 item 5 records that `proto/idxshape_jsonpath.sql` **J5 already measured row-count agreement between the jsonpath forms and the compiled predicates — four counts, unquoted.**

(b) **Belongs to:** `FRAMING.md` §4 #3 (the index autoSQL requires) feeding #5; ticket FINDINGS REQUIRED #3.

(c) **Where the answer could be found:** run `proto/idxshape_jsonpath.sql` J5 and report the four counts (measurement already exists, unreported); running the 130 fixture cases through the strict-jsonpath form would establish the equivalence, and is the single cheapest experiment left in the spike.

## 11. Cross-reading f3 and f4 localises the 260× prize to the date path — no section does the cross-read, and a recommendation turns on it

(a) **Missing:** f4 §4.8's profile block generalises: "**~99.6% of the compiled arm's time is plpgsql call overhead**", supported by `xpr.pdate_ms` at 10.97–12.28 µs/row (§4.6). f3 §3.2 measures nine *other* compiled predicates on 50 000–150 000-row collections. Dividing f3's own published columns (`act` + `Rows Removed by filter` = rows scanned; `exec ms`): W1 `$.status == "open"` 134.4 ms / 50 000 = **≈2.7 µs/row**; W6 `$.actor == "goms"` 406.2 ms / 150 000 = **≈2.7 µs/row**; W2 `$.score > 90` 362.5 ms / 50 000 = **≈7.3 µs/row**; W4 `days_between(today(), $.due_date) < 7` 3 285.0 ms / 50 000 = **≈65.7 µs/row** — consistent with f4's B2 at 59.6 µs/row for the same shape. (Arithmetic is mine, from f3 §3.2's table; the two rigs ran on different tables under acknowledged contention, so treat as order-of-magnitude.) The composite says the runtime penalty is **~24× worse on the date path than on an equality predicate**, i.e. concentrated in `xpr.pdate_ms`/`xpr.now_ms`, not in plpgsql as a category.

(b) **Belongs to:** `FRAMING.md` §4 #4 feeding #5 — "go/no-go on *standalone compiler + thin GIMS adapter*, with the reasoning". "Replace the runtime" and "fix the date path and fold the clock" are different recommendations with different costs.

(c) **Where the answer is:** f3 §3.2 table (est/act/removed/exec) + f4 §4.6 (`runtime_microcost_ms`) + f4 §4.6's own named-but-unrun experiment ("a quiet-host decomposition plus one run with `xpr.now_ms` hoisted to a scalar subquery would settle it"). Currently **not established**; f4's §4.6 inference is explicitly labelled unconfirmed after `probes.json → xpr_decomposition_100k_ms` returned self-contradictory values (`5_plus_xpr_ord` 25 065.86 ms > `7_full_compiled_filter` 8 573.77 ms).

## 12. The cost of the fallback machinery is not sized — the one thing FRAMING §4 #5 names by hand

(a) **Missing:** `FRAMING.md` §4 #5 requires the recommendation to carry "**the cost of the fallback machinery**". What exists: f2 §2.8's "what closing the gap would take — named, not built" (a `pushed_down`/`fallback` return-contract change, C3 stack conversion, C4 CTE binding, catching `RecursionError`/`MemoryError`, R1 SQLSTATE retry, R3 literal, R5 GUC pin) with **no effort, blast-radius or risk figure attached**; and f4 §4.9's *runtime* trigger cost (compile-time refusal **0.0266 ms**, 0.0003–0.19% of Path A; run-time refusal unbounded, +463% worst case). Neither is the machinery's cost. Nothing prices the standing cost of a **third runtime** kept in lockstep with `expr.py` and `frontend/lib/expr.js` against a 130-case contract fixture — the maintenance obligation the "standalone compiler + thin adapter" architecture creates. And per gap 1, a run-time fallback can only ever trigger on the *raise* classes; for the 13 uncovered silent classes there is nothing to trigger, so the measured 0.0266 ms / +463% figures do not bound the real cost.

(b) **Belongs to:** `FRAMING.md` §4 #5; ticket FINDINGS REQUIRED #5.

(c) **Where the answer could be found:** partially derivable from f2 §2.8's change list and f4 §4.9 / `measurements.json → fallback`; the third-runtime maintenance cost is **not established by this spike** and would need a scoping estimate, not a measurement.

## 13. The four sections never state the conjunction, and a reader can assemble a story the evidence does not support

(a) **Missing:** read separately, each section ends survivably. Read together, three facts that no section places side by side: f4 §4.9(2) — the compiled arm is **3.79×–7.15× slower than today at every size measured, with the gap widening**; f3 §3.3 cause 2 — **no index containing compiled output can be created at all** while `to_jsonb` wraps every subexpression, so the fix for (1) is blocked behind four compiler changes (§3.4); f2 §2.8 — **nothing reports a fallback today**, and part of the divergence set is undetectable in principle. The sentence a decision needs — *there is no measured configuration in which pushdown as prototyped is simultaneously faster than today's path and no less correct* — appears in none of the four. f4 §4.9 comes closest ("B4 bounds the size of the prize; it does not show the prize is collectable") and is explicitly labelled OPINION.

(b) **Belongs to:** `FRAMING.md` §4 #5 and the §4 bar ("stated in advance so the result cannot be rationalised afterwards").

(c) **Where it could be found:** f2 §2.8, f3 §3.3/§3.4, f4 §4.9, all already written — this is a synthesis omission, not a measurement gap. It is the thing finding #5 must not paper over.

## 14. The spike's only real tenant widget sits in f2 and is never connected to f4's representativeness gap

(a) **Missing:** f4 §4.1 states "there is **no** telemetry and no corpus of tenant-authored `DataSource` JSON in either tree… that it is the **most common** widget in production is **not established**." f2 §2.9 reports a read-only sweep that found **one real dashboard** (row `143c987947874e36b728bb66f5a9125c`, two `LIMS-System` backups) whose single `noun` widget is `derive: {days_left: "round(days_between(today(), $.due_date), 1)"}`, `where: "$.status == \"in progress\""`, `sort: {field: "days_left", dir: "asc"}` — the same shape f4 measured, and it was compiled and run: **12 checks, 12 agree, 0 diverge** (`analysis/coverage.md` §8.3). Neither section cites the other. The result: the one piece of real tenant evidence in the spike is conformance-checked but never measured, and the measured widget is documented-but-never-observed, while both sections independently report "no real data".

(b) **Belongs to:** `FRAMING.md` §4 #4 (representativeness of the measured widget); ticket FINDINGS REQUIRED #4.

(c) **Where the answer is:** f2 §2.9 (n = 1, correctly labelled as bounding nothing statistically) ↔ f4 §4.1. Connecting them raises f4's warrant from "the codebase documents it" to "the codebase documents it **and** the one real widget found matches it, n = 1"; that is a weak but real strengthening the body currently discards. Note the real widget's `where` reads a **stored** field, not the derived one — so it is *easier* to push down than f4's, which no section observes.

## 15. `derive` chaining is a documented `sources.py` behaviour that nothing compiles, measures, or fallback-rules

(a) **Missing:** `sources.py:133-148` `_apply_derive` writes each result back into the row (`row[name] = evaluate(...)`) and its docstring states "**later derives can reference earlier ones**". Every arm in f4 §4.3 (B1 faithful, B2 inlined, B3, B4) handles **one** derive; f2's construct census is per-expression and has no notion of inter-derive dependency or of the mapping's ordering; f3's compiled predicates are single-expression. A multi-derive widget where `derive2` reads `$.derive1` — and a derive that shadows a stored key — is uncompiled, unmeasured, and has no fallback rule.

(b) **Belongs to:** ticket QUESTION (push `derive` into the database) and FINDINGS REQUIRED #2.

(c) **Where the answer could be found:** **not established by this spike.** `sources.py:133-148` defines the semantics; establishing it needs a two-derive widget through `compile.py` (B1's `data || jsonb_build_object(...)` shape composes in principle, but that is INFERENCE, not measurement).

## 16. Smaller items, each concrete

- **16a — a stale "not established" that a sibling section closed.** f1 §1.9.4 records `KNOWN_DIVERGENCES/numeric_literal_inf` as "**not tested** by any artifact read here. Would be established by compiling `1e400` and asserting `Uncompilable`." f2 §2.6 C1 did exactly that: "`1e308` compiles, `1e309` does not; `$.a + 1e400` refuses the whole expression" (`compile.py:204-209`). Read together the body both asserts and denies the same fact. (`FRAMING.md` §4 #1.)
- **16b — three captured fuzz outputs are cited by no section**: `analysis/fuzz/A_range.txt` (the fullest form of the D1–D4 blast radius, 16/20, including `concat($.a)` → `''`), `B2_overflow.txt` (gap 8) and `M_encoding_guc.txt` (gap 9). Two of them carry facts that change conclusions.
- **16c — `run_all.sh` does not reproduce the whole evidence set.** It runs 21 batteries; `A_range.txt`, `A2_boundary.txt` and `B2_overflow.txt` are not among them. f1 §1.9.2 cites `fuzz/A2_boundary.txt` for D5, an output `run_all.sh` cannot regenerate and which `A_f8_guard.txt` §A3 supersedes with the same numbers. f1 §1.9.2 also says "**Twenty** batteries, `fuzz/run_all.sh`"; the script has 21 `run` lines. (`FRAMING.md` §8 — reproducibility of the harness.)
- **16d — the "third runtime" premise is unverified on its second leg.** `FRAMING.md` §4 #1: "run as a *third runtime* against the same fixture the Python **and JS** runtimes already satisfy." f1 §1.2 supplies a Python control (`control_python_vs_fixture_expect` = 130/130 against the hand-authored `expect`); `frontend/lib/expr.js` was never executed. Low severity — `FRAMING.md` §2/C2 establishes byte-identity across trees, and the UI is out of scope per §6 — but the claim as written is an assumption, not a measurement.
- **16e — f1's §1.5 byte-identity gap is correctly flagged and still open.** "Two consecutive runs produce byte-identical `cases`" is a hard-coded string at `conformance.py:681`, not a computed check; f1 says so and names the fix (run twice, diff `cases`). It was not run. Cheap, and it is the reproducibility claim every other number leans on.

---

**Summary of the criteria table.** `FRAMING.md` §4 #1 is met on its first clause (per-case, all 130) and **not** on its second (every divergence named with its cause — D21 and D22 fail, gaps 3 and 6). §4 #2 is met on "which constructs compile / which cannot" and on the `query` bound, and **not** on "the explicit fallback rule for each" (gap 1), with `filters`/`sort` outside its census entirely (gap 4). §4 #3 is fully met for the question as asked, with one unclosed follow-on it raised itself (gap 10). §4 #4 is met, with its own limits honestly stated, and its headline attribution is contradicted by a cross-read nobody performed (gap 11). §8 is demonstrated for two harnesses of four (gap 7). §5 is engaged directly and honestly by f1 §1.9.3 — and the premise §5 rests on is contradicted between sections (gap 2).