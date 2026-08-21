# T-1 · Final adversarial consistency read of the assembled FINDINGS body

Read as one document in assembly order (f0 · f1 · f2 · f3 · f4 · xa · xb · xc · xd · f5). Every item below was checked against the raw artifact, not against the prose.

---

## 1. f5 §5.3(b) states as an absolute exactly the sentence f3 wrote its opening paragraph to prevent — and f5 §5.9 states the correct form 230 lines later

**f5 §5.3(b), bolded, one of the four legs of the Gap-13 conjunction that carries the verdict:**
> **(b) No index containing compiled output can be created at all.**

**f3 §3 opening, verbatim:**
> "…so PostgreSQL **refuses to create any index whose expression or predicate contains a compiled WHERE predicate** (W1–W9) **or the compiled `derive` column** (D1). That absolute stops there: the compiled *sort key* S1 carries no wrapper and is both indexable and measured index-backed (§3.6 H4), and the bare compiled operand indexes fine (§3.3 T4a) — it is the `to_jsonb` wrapper, not "compiled output", that is refused."

**f5 §5.9 item 4, the same document:**
> "no compiled predicate can appear in **any** index today"

**Raw data supports f3.** I re-derived `proto/idxshape_preds.json`: 11 compiled outputs, `to_jsonb` in exactly 10; `S1` = `nullif((data -> (%(p0)s)::text), 'null'::jsonb)`, zero wrappers. f3 §3.6 H4 measures an index on precisely that expression being **created and used**: `Index Scan using idxprobe_score_operand`, **0.065 ms**, and f3 calls it "where the only working pushdown lives today". f3 §3.3 also creates `v_operand`, `v_t7d` and `H2a` live.

This is decision-blocking because leg (b) is what f5 uses to argue the fix for leg (a) is blocked, and because f5's own §5.9 contradicts it. **Repair:** restate (b) as "no compiled *predicate* or compiled *derive column*", and add the one measured counter-fact (S1 is index-backed at 0.065 ms) so the conjunction is stated at its true strength rather than above it.

---

## 2. Three sections disagree about whether the "the in-memory fallback can itself raise" question was answered — and it is the §5 non-negotiable

- **xa A.5(ii):** "**(ii) The in-memory fallback can itself raise. This is the finding.** No section considers it." — then measures it: poison row at index 0/5/9 → uncaught `OverflowError` in both `_apply_derive` and `_filter_rows`; HTTP 500 via `core/errors.py:115-119`; **40.9% (65/159)** of SQL raises also raise in the retry.
- **xc C.3 (D7 row) and C.11(a) (R1′ row):** "on the 0.81% `BOTH_RAISE` subset the in-memory retry raises too" / "on D7's `BOTH_RAISE` subset the retry raises too." — i.e. xc *does* consider it.
- **xc C.13, last bullet:** "**A fallback whose target can raise is not a fallback**, and no section of this spike adjudicates it."
- **f5 §5.4(2):** treats it as closed and quantified — "measured in `xa` A.5(ii)… `sources.py:335`'s contract… is false today".

**Raw data supports xa and f5.** The mtimes explain it (xa 14:22:47, xc 14:23:07 — neither could see the other), but concatenation does not care: a gate reader gets "no section considers it", then a section considering it, then "no section adjudicates it", then a verdict citing the adjudication. **Repair:** delete "No section considers it" from xa A.5(ii) and replace xc C.13's last bullet with a pointer to xa A.5(ii) plus what remains open (the production frequency of N1–N4).

---

## 3. xb B.10 attributes a CONDITIONAL-GO to f5, which recommends NO-GO

**xb B.10, verbatim:**
> "They do not touch f1's `expr` result, nor by themselves overturn **f5's CONDITIONAL-GO, which names a subset**; they do establish that **the named subset cannot include `filters` or `sort` on the present evidence**…"

**f5, verbatim:**
> "### Verdict: **NO-GO** on the architecture as scoped."

xb landed 14:26, f5 at 14:51. **f5 is the operative recommendation.** In the assembled document the reader is told the verdict is CONDITIONAL-GO twelve pages before being told it is NO-GO. **Repair:** rewrite xb B.10's clause to "nor by themselves decide the verdict f5 reaches; they do establish that any named subset cannot include `filters` or `sort`."

---

## 4. Two sections declare the reachability question open and prescribe the exact sweep that the next section performs and reports

**f1 §1.11 item 6:** "Whether any of D1–D23 is reachable from real GIMS dashboard data… Rate of occurrence in production data is **not established**. *Step:* a read-only scan of the live `instances` table (and of `gims-ledger/projects/*/objects.db`…) for values with |v| ≥ 1.797693e+296, non-ASCII digits, or >17 significant digits."

**xc C.13 bullet 1:** "whether any of the 34 ids fires on production data is **not established**. *Step:* the read-only sweep of `gims-ledger/projects/*/objects.db`… screening for magnitudes ≥ 1.797693e+296, non-ASCII digits, >17 significant digits, or values written by a non-Python path."

**xd D.3/D.4/D.5:** runs precisely those four predicates and reports **0 / 5,235,942**, **0 / 1,096,202**, **0 / 5,236,427**, plus the writer-signature test.

**Raw data supports xd.** Both stale "not established" lines should be converted to forward pointers ("closed for this corpus by `xd` D.3–D.5; production-scale reachability remains open — `xd` D.8"). Left as-is, the body's own headline caveat on its §5 witnesses reads as unanswered when it was answered, which biases the gate against the CONDITIONAL-GO reading.

---

## 5. f5 §5.10's cost figures are cited to a file that does not contain them, and the elapsed number excludes f5 itself

**f5 §5.10:** "`sp-investigate` opened **2026-08-19T16:50:18Z**; the last section landed **20:33:32Z** — **3 h 43 min** of wall clock across 3 `worker.started` events… (`.autodev/events.jsonl`, read here)."

**Checked:** `.autodev/events.jsonl` contains `stage.advanced` at `16:50:18.060Z` ✓ and exactly 3 `worker.started` ✓ — but its **last event of any kind is `18:49:12.087Z`**. `20:33:32Z` is not in the file; it is `xd-reachability.md`'s mtime (`14:33:32 -0600`). And **f5 itself landed at `20:51:51Z`**, so "the last section" is not the last section and the true span is **4 h 01 min**, not 3 h 43.

Small in itself; it is listed high because §5.10 is the one place f5 asks the gate to trust a provenance claim, and it is the one that does not check out. Everything else in f5 I opened *did* check out (see item 16).

---

## 6. The same fuzz denominator appears two ways; f5 used the AGREE count as the "ran" count

**f1 §1.9.2 (D22):** "**4 diverge of 3867 that ran = 0.103%** (133 `PARSE_ERROR` of 4000)"
**f5 §5.7 (E1 "State to beat"):** "`H_ordinary` 0/3 881 · `H_unicode` **4/3 863** · `H_extreme` 23/3 880 real"

**Raw file `analysis/fuzz/H_unicode.txt`:** `AGREE 3863 · DIVERGE 4 · PARSE_ERROR 133`. Ran = 3863 + 4 = **3867**. **f1 is right; f5's 3 863 is the AGREE count.** f5's other two entries (3 881, 3 880) *are* ran-counts, so the list is internally inconsistent as well. This matters because E1's bar is stated against these three numbers.

---

## 7. The headline slowdown multiplier is published as two different ranges

**f4 §4.9(2):** "B2 is **3.79×–7.15× slower** than Path A" (and f4 §4.1 re-uses "3.79×–7.15×").
**f5 §5.3(a) and §5.5 point 3:** "the honest range is **2.55×–7.15× slower**" / "The compiled arm is **2.55×–7.15×** slower".

Both are defensible — 3.79× is the sweep minimum, 2.55× is the one load-controlled re-run at N=20 000 (`probes.json → recheck`), and f4 states the collapse in its own §4.9(2). But the assembled document gives a gate reader two headline ranges for the one multiplier they will quote. **Raw data:** `measurements.json` medians give 4.152 / 3.892 / 3.794 / 4.363 / 6.713 / 7.152; the 2.55× exists only in the un-audited `recheck` block that f4 §4.11 itself flags as having **no retained producer**. **Repair:** one range, stated once, with the recheck's provenance caveat attached wherever it appears.

---

## 8. f5's cheaper-alternative argument leans on a code comment that says the opposite, and never states the alternative's own cost

**f5 §5.5 point 3:** "Pushdown fixes that — **so does raising one constant whose own comment anticipates the change** (`sources.py:61`)."

**The comment, read live:**
> `# Safety cap: v1 materialises every candidate row in memory before filtering… "truncated" is surfaced so the UI can warn. (Pushdown filtering removes this.)`

The comment anticipates **pushdown** as the fix — i.e. this project — not raising `MAX_SCAN`. The citation is used to support the opposite of what it says.

Second, the alternative's cost is stated only against the prototype: "≈ **16.7 s uncapped and correct vs B2's measured 59 590 ms** — ≈3.6× faster than the prototype, same answer." It is never stated against **today**: Path A at 1 M measures **8 331 ms** (`measurements.json`), so the "one-line change" is **≈2.0× slower than today's latency** while leaving the 98%-of-time acquisition and the 2.4 GB per-request heap untouched — the two things §5.3 and §5.9(1) call the actual prize. f5 §5.11 names concurrency as "the axis on which the 2.4 GB-per-request memory win would matter most" and does not apply it to its own recommended alternative. This is unearned optimism about the alternative inside an otherwise pessimistic verdict, and point 3 is one of five load-bearing reasons for NO-GO.

---

## 9. f5 §5.6 calls the conformance harness "proven able to fail"; f1 §1.7 explicitly corrected that claim

**f5 §5.6:** "…by a **harness proven able to fail**: **23/23** negative controls `ok`, including **NC13**…"

**f1 §1.7, verbatim correction:**
> "**Correction applied… My earlier wording — "`COMPILED_DIVERGES` is reachable from a real case", "injected end-to-end failures" — overstated what the code does…** None constructs a case entry; none asserts `outcome == "COMPILED_DIVERGES"`… the **outcome-assignment branches at `conformance.py:376-455` are exercised by nothing.** …That the three non-pass outcome **labels** are reachable is an **INFERENCE**."

**f1 is right** (I read the controls' construction as f1 describes). f5's §5.6 is the steel-man, so the overstatement runs *against* f5's own verdict — but it is still a claim the findings do not support, and it is the single most FRAMING §8-relevant residual on the 130/130 headline. f5 §5.9's "stated against the spike" list names `differ.py` and `bench.py` having no negative controls but **omits** this one.

---

## 10. f5 §5.6 derives "75 of 130" from a premise that yields 110

**f5 §5.6:** "…best single constant **20/130**, so **75 of 130 agreements are unreachable by any constant** (`f1` §1.6)."

**f1 §1.6, correctly:** best single constant 20/130 → "**110 of the 130** agreements are agreement no single constant could fake"; the **union of all five** constants covers 55/130 → "**75 of 130** cases are unreachable by *any* of the five".

**Raw `results.json` `degenerate_baselines`:** `{true:20, null:19, false:15, zero:1, empty-string:0}` — 130−20 = 110; 130−55 = 75. f1 is right; f5's "so" is a non-sequitur that silently switches denominators mid-sentence. (It picks the conservative number, so the direction is safe; the derivation is not.)

---

## 11. Two corrections xa ordered onto f1 and f2 were never applied in place, and both sections come first in reading order

**xa A.6 orders:**
- on **f2 §2.4** — "'0 `PYTHON_RAISED` over 403 adversarial inputs is **403 independent confirmations of the totality premise**' → **Delete the inference, keep the count.**"
- on **f1 §1.9.3** — "'4 witnesses of 45 date probes' → **Understated. 8 mechanisms across 9 source lines and 4 exception types.**"

**f2 §2.4 still reads, unannotated:** "Separately, `0 PYTHON_RAISED` over 403 adversarial inputs is 403 independent confirmations of the totality premise the design rests on."
**f1 §1.9.3 still reads:** "D11 (Python `OverflowError`, SQL returns `738886.58…`), 4 witnesses of 45 date probes".

**Raw data supports xa** — its A.3 table shows the 403-probe domain tops out at |value| 2026.0, nesting depth 4, ndigits ∈ {−1, 2}, zero `%`, zero offset-bearing dates, so it cannot reach a single one of the eight raise sites. xa adjudicates the contradiction ("f1 §1.9.3 is right and f2 §2.4's inference is wrong"), which makes this survivable — but a reader meets the false inference on page ~15 and its retraction on page ~60. **Repair:** two in-place footnotes in f1 and f2 pointing forward to xa.

---

## 12. Four different row counts for "the live ledger", none reconciled, two of them quoted by f5 seventy lines apart

| section | figure | what it is |
|---|---|---|
| f3 §1.2 | "the real **17 087**-row ledger" | generator's frequency snapshot |
| f3 §3.8 item 8 | "the live file now holds **17 110** rows" | ~14:07 |
| xd D.2 / D.8 | "**17,148** = 85.7 % of MAX_SCAN" | ~14:20 |
| xb B.4 | "`guts-ledger/instances` … **17 342** dict rows" | whole table, all collections, ~14:26 |

**f5 §5.4(3):** "**4 166 of 17 342 rows (24.0%)** of the live `guts-ledger` `instances` table" · **f5 §5.6/§5.11:** "largest real collection is **17 148 rows**".

All four are reconcilable — xd D.1 documents an active writer (17,145 → 17,148 in six minutes) and xb's 17,342 is the *table* while xd's 17,148 is the `LedgerRecord` *collection* (17,148 + 197 + 5 = 17,350, minus six minutes of drift). **Nothing in the document says so.** One sentence in xb B.4 ("table-wide, not `LedgerRecord`-only; cf. `xd` D.2") removes the appearance of a contradiction in the two numbers f5 quotes.

---

## 13. f5 §5.1 leaves seat [1]'s decisive argument standing unrebutted while f5 §5.7 performs the thing it says is impossible

**f5 §5.1, seat [1] row:** "…the divergences are keyed on runtime **values**, not constructs (`f2` §2.7: all thirteen rules are shape-, magnitude-, value- or source-keyed, **none** construct-keyed), so §4's CONDITIONAL-GO template **cannot be instantiated**."
**f5 §5.2:** "…and Reading B governs."
**f5 §5.7:** "**Start from `panel.json[0]`'s subset** — all 10 leaf/structural node types… and 10 of 22 functions: `abs ceil coalesce count floor if length max min round`." — a construct-keyed instantiation.
**f5 §5.8(b):** "The only rule reaching the silent classes is **AVOID**…"

**xc C.1 is the rebuttal and f5 never places it there:** "**DETECT** … **AVOID** — the adapter cannot tell whether it diverged, but can decide **statically, from the AST or the source spec** … **AVOID satisfies FRAMING §5; it does not satisfy 'detectable'.**" Note also that f5 §5.4 ("What closure added that the panel did not have") lists four items, all of which cut against or across CONDITIONAL-GO, and omits the one closure item that answers seat [1] directly. That omission is the only place in f5 where the synthesis is one-sided in the direction of its own verdict.

---

## 14. f3 §3.9 contains a second, unlabelled recommendation that f5 never engages

**f3 §3.9, OPINION:** "…rule 1's measured-agreeing shape set is **one distinct expression shape** — which is **an argument for shipping rule 3 and rule 4 first**, and treating rules 1 and 2 as optimisations that must earn their way in case by case."

f5's §5 never mentions f3's emission rule, the jsonpath route, or rule 3. It also never closes f3 rule 3's own open question — f3 defers it ("whether it beats the in-memory path is finding #4's question") and f4 answers *no* (3.79×–7.15× slower), but no section joins the two. A gate reader reaches the recommendation having just been told to ship rules 3 and 4, and is then told NO-GO on the architecture, with no reconciliation. **Repair:** one paragraph in f5 §5.5 or §5.9 that either adopts f3 §3.9's routing as the shape a future GO would take, or records that f4 §4.4 removes rule 3's premise.

---

## 15. Denominator drift: "34 ids · 15 detectable / 18 undetectable" does not add up

**f5 §5.9 item 2:** "A complete divergence register — **34 ids** with cause, direction, rate, blast radius and detectability, **15 detectable / 18 undetectable** (`xc` C.8)."
**xc C.8:** 34 `expr`-layer **ids** → **15 detectable ids** · "**19 ids = 18 classes**" undetectable → "**33 distinct classes**" after folding D21.

15 + 18 = 33 ids, not 34. f5 §5.3(c) states it correctly ("**18 of 33 distinct `expr`-layer classes**"). **xc is right;** f5 §5.9 mixes the id count with the class count in one line. Same class of slip: f5 §5.4(4)/§5.6 quote "**1 096 202** real strings" where xd D.4's own row label is "string values **+ object keys**" and xd D.2 reports **495,115 string values**.

---

## 16. What I checked in f5 that *does* hold (so the repairs above are not read as a general indictment)

Opened and confirmed against source: `sources.py:357` returns exactly `{"records","count","truncated"}`; `sources.py:61`'s `MAX_SCAN = 20_000` and its comment; `sources.py:335`'s "never crash" docstring; `widgets.jsx:277`'s `title="Result capped for performance"` / `capped`; `compile.py`'s `KNOWN_DIVERGENCES` = 7 entries, exactly one `in_fixture: True`; `results.json` totals 130/130, `agreement_strength` 54/0.0/0/22/22/19/6/0, `control_python_vs_fixture_expect` `{130, []}`, 23/23 controls `ok`; `degenerate_baselines` 20/19/15/1/0; `measurements.json` B2÷A = 4.152/3.892/3.794/4.363/6.713/7.152, `qualifying_rows_total ÷ N` = 5.00/5.10/5.27/5.35/5.20/5.23 %, payload 317 019 897 B → 16.59 MB → **19.1×**, and 19 667.5 ÷ 19.1 = **1 029×**; `fallback.plan_ms` 0.026605 + `detect_uncompilable_ms` 0.004079 = **0.0307 ms**; the §5.5 point-3 arithmetic (7.27 + 1.23 µs/row × 1 M + 8 161 ms ≈ 16.7 s; 59 590 ÷ 16 660 ≈ 3.6×); `proto/` 14 Python + 5 SQL = 2 912 + 427 lines, `compile.py` 464, `runtime.sql` 427; `analysis/fuzz/` 20 `.py` / 25 `.txt` / 1 990 lines; `run_all.sh` = 21 `run` lines; all four `panel.json` quotations verbatim, including C-0's ≤ 5.5 µs/row bar; 2.1 MB of output, ~119 k words. **f5's citation discipline is real. Items 5, 6, 8, 9, 10 are the exceptions, not the pattern.**

---

## Minor tail (each a one-line repair, none decision-blocking)

17. **f1 §1.1 names three non-regenerable captures** ("`A_range.txt`, `A2_boundary.txt` and `B2_overflow.txt`"), but its own table (25 outputs, 21 runs) requires **four**; the fourth is `H_parse_errors.txt`, which f1 §1.10 identifies separately as a superseded capture. f5's "regenerates **21 of 25** outputs" is arithmetically right and inconsistent with f1's named list. Confirmed: those four `.txt` have no `.py`.
18. **xb B.8 bolds "Ten substantive obligations. Zero compiled, zero tested, zero fallback-ruled"** while row 6 of its own table reads "**partial** — `bench.py:94-101`, ranks 0/1/2/4, one widget" and row 1 reads "no (hand-written in `bench.py:226` only)". f5 §5.3(d) repeats "zero compiled". Defensible if "compiled" means "by `compile.py`" — say so.
19. **f5 §5.4(3)/§5.9(3)** state flatly that "migrating this store to Postgres **changes the answer** of the existing Python path on **4 166 real rows**". xb B.4's own scope note is dropped: the answer changes only for a query that resolves a `runid`-normalising key, and xb labels the production relevance an **INFERENCE** ("whether a production `DataSource` targets a collection holding this pair is **not established**").
20. **f0's map does not match the document.** "Five findings, in the order `FRAMING.md` §4 requires them" with a five-row table — the four cross-cutting sections xa–xd, which f5 §5.4 says changed the verdict, appear nowhere in the reader's map. f0 also calls `recon/semantics.md` "Semantics ground truth for all five" when xa A.6 rules its §11 "**False as a universal**".
21. **f3's own summary line** ("Index-accelerated *and* measured to agree with `expr`: **3 of 130 fixture cases (2.3%)**, one routable shape") reads against §3.5(c)/§3.9's operative figure, "**routable… 2/130 = 1.5%**". Lead with 1.5%.
22. **The measurement corpus's missing-key rate is 5%** (`gen_data.py:30`, f4 §4.2); **the one real collection's is 42.9%** (xd D.7). xd compares itself only to f3's 8% generator. Nobody says what an 8.6× difference in `due_date` absence does to f4's selectivity, derive cost or recall figures. f4 §4.11 flags selectivity as untested generically; the specific number now exists and is not applied.
23. **Compliance attestations are present in f2, xb, xd and f5 and absent from f1, f3, f4, xa and xc.** Given rules 2 and 3 (read-only; roll back anything that creates an object), uniform attestation is cheap and its absence reads as uneven diligence.
24. **Stop rules — no violation found.** No defect is fixed anywhere: C3/C4/R3 recorded not fixed (f2 §2.8), f3's DDL probes all in rolled-back transactions with post-rollback verification, f1's re-run calls `conformance.run()` without `main()` and leaves `proto/` byte-unchanged, xc proposes R1′ as a *rule* (explicitly permitted by FRAMING §3) and does not implement it. Two grey areas, both disclosed: **f3 §3.5(d)(ii)** ran all 130 fixture cases through a strict-jsonpath comparison via a scratchpad script (f3 flags it as "re-derivable from two committed instruments but not itself a committed artifact"), and **xd D.1** built a genuinely new instrument, `xd_sweep.py`, while calling the pass "a **read-only sweep, not a new experiment**". Neither fixes anything; xd's label is a stretch and should say "a new read-only instrument, built this pass, cross-checked against `json_tree`".

---

## Verdict

**Yes, with named repairs — and the repairs are small relative to the body.**

This is an unusually honest evidence set. The three things a gate most needs are all present and correctly scoped: the literal question is answered and audited (130/130, bit-exact, non-degenerate, with the fixture's own inadequacy as an acceptance test measured rather than asserted); the FRAMING §5 breaches are named with causes, reproducers and directions and are *not* rounded away; and the things the spike could not reach — the JS runtime, the GUC sensitivity of 68 of 130 cases, the machinery's standing cost, production reachability, `derive` chaining — are recorded as **not established** with the one step that would establish each, which is the contract-compliant answer rather than a hole. Numbers reproduce: I re-derived roughly forty of them from `results.json`, `measurements.json`, `idxshape_preds.json`, the fuzz captures and the GIMS tree, and all but the five in items 5–10 came back exact.

What must be fixed before a human reads it: **items 1, 2, 3 and 4.** Item 1 is a false absolute in the section that carries the verdict, contradicted verbatim by the finding it cites and by f5's own §5.9 — leave it and the NO-GO rests on a leg the evidence does not hold. Items 2, 3 and 4 are the assembly artifacts of parallel authorship: a section calling a gap open that its neighbour closed (twice), and a section naming a verdict the document does not reach. Each is a one-to-three-sentence edit. Items 5–10 are citation and arithmetic slips in f5 that a careful reader will find and that will cost the document credibility it has otherwise earned; fix them too. Everything from 11 down can ship as-is if time is short.

One structural note that is not a defect but should be said out loud at the gate: **f5 argues honestly against itself in §5.6 and then over-argues in §5.3(b) and §5.5(3).** The pessimism in this document is better evidenced than the optimism, but it is not uniformly evidenced, and the two places it outruns the findings both sit inside the five reasons for NO-GO. Repair those and the recommendation is one a decision-maker can act on without re-doing the work.