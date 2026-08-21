## Cross-cutting C — the complete divergence → fallback register, and what the machinery costs

Closes critic gap 1 (thirteen confirmed divergence classes with no fallback rule anywhere) and the
unmeasured half of critic gap 12 (the machinery, as distinct from the trigger). No new experiment:
every row is assembled from `f1` §1.9.1–§1.9.7 as corrected at closure, `f2` §2.6–§2.9, `f3`
§3.5(d)/§3.6, `f4` §4.9/§4.11 and the raw `analysis/fuzz/*.txt`. Per FRAMING §3 nothing is fixed.

### C.1 The two words the register keeps apart

FRAMING §5 requires a fallback to be **reported, never silent**. Two different mechanisms can satisfy
it, and every prior section conflates them:

- **DETECT** — at query time the adapter can tell that *this* query on *this* data actually diverged.
  Available only where the database raises (SQLSTATE) or the compiler refuses (`Uncompilable`).
- **AVOID** — the adapter cannot tell whether it diverged, but can decide **statically, from the AST
  or the source spec, before any SQL runs**, that this expression *could* reach the class, and refuse
  to push it down. An over-approximation: it fires on every expression containing the construct.

**AVOID satisfies FRAMING §5; it does not satisfy "detectable".** It is the only rule available for
every silent class, and its price is paid in pushdown coverage, not in wrong answers. The `detect`
column below is DETECT-only; the `fallback rule` column gives the AVOID rule where one exists. Codes:
**STATIC** (decidable from the spec/AST at `sources.py:345`, before `:347`) · **RAISE** (the query
aborts, SQLSTATE observable) · **NONE** (SQL succeeds and returns a different answer).

### C.2 Block A — compile-time classes (`f2` §2.6, §2.7)

| id | what diverges | cause | rate + witness | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| C1 | numeric literal overflows float8 | `compile.py:204-209`; `1e308` compiles, `1e309` does not, `$.a + 1e400` refuses the whole expression | boundary bisected, `f2` §2.6 | no answer produced | no | **STATIC** (`Uncompilable`) | catch `Uncompilable` → in-memory. Rule exists; **no reporting channel** (`f2` §2.8) |
| C2 | generated SQL > `MAX_SQL_CHARS` 200 000 | `compile.py:51,172-176`, checked **after** the string is built | first refusal `date_add` depth 11 = 294 795 chars | no answer | no | **STATIC** (`Uncompilable`) | as C1 |
| C3 | flat operator chain | ~3 Python frames/AST level vs `sys.getrecursionlimit()` 1000; parser `MAX_DEPTH=64` cannot see it (`expr.py:184-208`) | **first failure at 333 `+` operands, 665 chars** — one third of `MAX_SOURCE_LEN`; 332 compiles cleanly | no answer, **`RecursionError`** | no | **STATIC but off-contract** — `Uncompilable` never fires | catch `RecursionError` alongside `Uncompilable`. **Not in the contract today**; `except Uncompilable` catches nothing |
| C4 | nested `date_add` doubles SQL per level | `_f_date_add` emits its first argument twice (`compile.py:318-326`) | 2.00×/level; `Uncompilable` at depth 11; **`MemoryError` at ~depth 24 (~300-char source, ~2.4 GB)** under a 2 GiB `RLIMIT_AS` | no answer, or **process death** | no | **partial** | catch `MemoryError`. **INFERENCE:** with no `RLIMIT_AS` the allocation is an OOM event, not a catchable exception — then there is no fallback, there is an outage. Not established by this spike |

### C.3 Block B — run-time value classes (`f1` §1.9.1–§1.9.2 as corrected, plus `f2`'s R1/R2/R5/R6)

Numbering is `f1`'s, so the arithmetic is comparable with critic gap 1. `f2` §2.7's rule id is given
where one exists.

| id | what diverges | cause | rate + witness | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| **D1** | `sum($.l)` on `[1e300,1]` → py `1e+300`, sql **`1`**; `max`,`avg` likewise | `xpr.f8` range-guard literal written to **297 digits** (`1.797693134862316e+296`) where DBL_MAX needs 309 (`runtime.sql:33`) | **16 of 16 f8-reachable paths** diverge (16/20 probed; the 4 that agree do not call `xpr.f8`) — `A_f8_guard.txt` §A2 | **different value** (silent) | not literally; **breaches §4 NO-GO** | **NONE** | =R3. `f2` §2.7 records "**none**". Only AVOID rule: refuse any expression whose operands can exceed 1.797693e+296 — **not decidable from the AST**, so in practice refuse arithmetic entirely; the alternative is to fix the guard (R3) and let R1′ catch the raises it unmasks (§C.12 item 3) |
| **D2** | `concat($.a)` → `''`, `string($.a)` → **SQL NULL** on `{a:1e300}` | same guard | in the same 16 (`A_f8_guard.txt` §A2) | different value; value→null | as D1 | **NONE** | as D1; AVOID by excluding `string`/`concat` |
| **D3** | `contains($.s,$.a)` → py `True`, sql `False` | same guard | ibid. | different value | as D1 | **NONE** | AVOID by excluding `contains` |
| **D4** | `$.a < 1e301`, `$.a > 1`, `$.a >= $.a` → SQL NULL | same guard, predicate path | **3 of 3** order comparisons | value→null → **rows dropped** | see D23 | **NONE** | as D1 |
| **D5** | boundary, bisected live: round-trips at `1.79769313486231551e+296`, corrupts at `…587e+296` | same guard | every finite double of magnitude ≥ 1.797693e+296 — **~12 of the float8 exponent's 632 decimal decades** (`A_f8_guard.txt` §A3) | — | — | **NONE** | bounds the blast radius of D1–D4; no independent rule |
| **D6** | float8 **underflow** raises: `$.a * $.a` on `1e-200` → py `0.0`, sql aborts | PG raises 22003 on underflow; `expr` returns `0.0` | **9 of 13** overflow/underflow probes raise (`B_overflow.txt`); witnesses at `1e150 × 1e160` and `1e-300 / 1e100` (`B2_overflow.txt`) | **value → raise** | no — this is the loud direction | **RAISE** 22003 | **R1′ (new here): catch SQLSTATE `22003` — overflow *and* underflow, any operator — and re-run the whole widget in memory.** `f2` R1 is scoped to "overflow in `+ - * /`" and misses this |
| **D7** | `round($.a,-2)` on a subnormal raises | `xpr.round` computes `x·10^nd` internally | `SQL_RAISE_ONLY` **94/8000 = 1.18%**; `BOTH_RAISE` **65/8000 = 0.81%** (`G2b_round_raises.txt`); 756/40 000 = 1.89% raises either side (`G_fmod_round.txt` §G2) | value → raise | no | **RAISE** 22003 | R1′ — **with a hole: on the 0.81% `BOTH_RAISE` subset the in-memory retry raises too** (`OverflowError: cannot convert float infinity to integer`). The fallback terminates in an error, not an answer |
| **D8** | `number('١٢٣')`, `'１２３'`, Devanagari, NKO, NBSP/thin/ideographic space → py `123.0`, sql NULL | `xpr.num`'s ASCII gate vs Python's Unicode-aware `_to_num` (`expr.py:305`) | **10 of 27** `C_numgate` probes (4 digit systems + 6 space code points) | **value → null**, silent | via D22 — **YES**, see C.6 | **NONE** | **none possible by detection.** AVOID: exclude `number` from pushdown |
| **D9** | `number('1e-400')` → py `0.0`, sql raises 22003 | same gate, unguarded underflow — while `xpr.f8` on `1e400` is *guarded* to NULL: the two guards are inconsistent (`M_encoding_guc.txt`) | **1 of 27**, distinct from D8's 10 | value → raise | no | **RAISE** | R1′ |
| **D10** | date strings padded with Unicode space → py `1.0`, sql NULL | `expr.py:413` `v.strip()` strips Unicode spaces; `runtime.sql:273` `btrim(E' \t\n\r\f\v')` does not; `expr.py:415` is a bare `return None` | **10 of 12** whitespace code points (only U+0020, U+000C agree) + 12 Unicode-digit cases = **22 divergences in E2** (`E2_dates_ws.txt`) | value → null, silent | via D22 — **YES** | **NONE** | none by detection. AVOID: exclude `days_between`/`date_add`/`today`/`now` |
| **D11** | `days_between($.d,"2024-01-02")` on `{d:'0001-01-01T00:00:00+14:00'}` → py **`OverflowError`**, sql `738886.5833333334` | offset pushes the year past `datetime.min`/`max`; SQL's timestamptz range is wider | **4 `PY_RAISE` of 45** date probes (`E_dates.txt:30-41`); one witness is inside a boolean a dashboard would write, where SQL answers `True` | **raise → value** — FRAMING §5 clause 2 | **YES** | **NONE** | **none possible — undetectable in principle, and the direction is inverted:** the reference runtime is the one that fails, so "fall back to in-memory" converts a wrong answer into a 500. AVOID: exclude the date functions |
| **D12** | `$.a == 1` on raw-JSON `{"a": 1.00000000000000001}` → py `True`, sql `False` | jsonb stores `numeric`, not IEEE double | **10 of 18** raw-JSON probes (`D_rawjson.txt`) | different value | no | **NONE** | =R7, `f2` records "none". **Partly bounded by reachability:** `gims-ledger/api/storage_aws.py:743-754` writes via `Jsonb(record)` from Python objects and cannot produce such a row; `:694` reads with `json.loads` and *will* mis-read one if anything else wrote it (`D_rawjson.py:12-17`). AVOID would mean refusing `==`/`!=` on paths — which deletes the only index-accelerated shape `f3` found |
| **D13** | `if($.a,1,2)`, `not $.a`, `$.a and true` on raw `{"a": 1e-400}` | `xpr.truthy` casts to `numeric`, where `1e-400` is non-zero; Python parses it to `0.0` | **4 of 18** | different value, silent | no | **NONE** | none by detection. **No AVOID rule exists**: the constructs are `if`/`not`/`and`, which any subset keeps. Bounded only by D12's reachability argument |
| **D14** | `number($.a)`, `$.a + 0`, `string($.a)` on raw `{"a": 1e-400}` | same | **3 of 18** | value → raise | no | **RAISE** | R1′ |
| **D15** | `sum($.l)` on `[1e16,1,-1e16]` → py `1.0`, sql **`0`** | CPython 3.12 `sum()` is Neumaier-compensated; `sum(float8)` is not (`runtime.sql:411` is exactly `sum(v ORDER BY ord)`) | **4368/20 000 random lists = 21.84%** by proxy; **99.73%** on the "big value ± small corrections" profile; max abs difference **35.39**; **6 of 10 end-to-end through the compiler** (`K_sum_neumaier.txt` §K2) | **different value**, silent | **breaches §4 NO-GO** | **NONE** | none by detection. AVOID: exclude `sum`/`avg` — **the single highest-yield exclusion in the register** |
| **D16** | `string()` of a double at the **pinned** `extra_float_digits = 1`: py `'52990648348713780'`, sql `'52990648348713776'` | `xpr.ecma_num` vs `_num_to_str` | **56 of 200 000 doubles = 0.0280%**, 1 in 3571; all round-trip to the same double (`F1b_ecma_rate.txt`) | different value (string) | no | **NONE** | **not covered by R5.** R5 says "pin the GUC"; D16 is what remains *after* pinning. AVOID: exclude `string`/`concat` |
| **D17** | 200 identical rows: `WHERE string($.a)='0.3333333333333333'` returns **0 rows via index scan, 200 via seq scan** | `xpr.ecma_num` declared `IMMUTABLE` while depending on `extra_float_digits`; index built at `efd=-3` (`F3_immutable_index.txt`) — `L5` shows **four** functions mis-declared (`ecma_num`, `f8`, `num`, `str`) | **1 of 2 configurations**; reproduced once, attempted twice | **silent wrong result set**, plan-dependent | **breaches §4 NO-GO** | **NONE** | none by detection — the planner's choice is invisible to the caller. **Avoidable by DDL policy, not by a query-time rule**: never build an index over an `xpr` function while the GUC dependency stands. **[consistency]** *Not* moot — the absolute this row carried is false. `proto/idxshape_preds.json` holds **11** compiled outputs and `to_jsonb` wraps exactly **10** of them: every compiled predicate W1–W9 and the compiled `derive` column D1, none of which can appear in an index. The compiled **sort key** S1 is `nullif((data -> (%(p0)s)::text), 'null'::jsonb)`, carries **no** wrapper, and `f3` §3.6 H4 measures it index-backed (`Index Scan using idxprobe_score_operand`, **0.065 ms**). A hand-written index over an `xpr` function is buildable too — `f3` §3.6 H1 built `idxprobe_ecma` over `xpr.ecma_num(xpr.f8(data -> 'score'))`, which is how D17 / §C.5 H1 was demonstrated at all. **The DDL policy is live, not moot.** |
| **D18** | `upper('İstanbul')`, `lower('ΣΊΣΥΦΟΣ')`, `upper('straße')` | PG follows DB collation; Python does full Unicode case mapping; Greek final sigma is context-dependent, so a per-code-point sweep is structurally blind to it | code points: `upper()` **102/286 718**, `lower()` **1/286 718**; **strings end-to-end: `upper()` 4 of 10, `lower()` 3 of 10** (`I_case_collate.txt` §I3) | different value, silent | no | **NONE** | =R4, "none". AVOID: exclude `upper`/`lower`. String-level *rate* not established |
| **D19** | `$.a[2147483648]` → py `None`, sql raises 22003 | jsonb array index is int4 | **3 of 5** (`L_misc.txt` §L2) | value → raise | no | **STATIC** *and* RAISE | **fully statically decidable** — the grammar's `[n]`/`[-n]` take an integer **literal** (`expr.py:240-243`), so a compile-time `abs(index) < 2^31` check refuses it before any SQL runs. Cheapest rule in the register |
| **D20** | `length($.s)` on `'a\x00b'` | a NUL byte cannot be stored as jsonb at all (22P05) | **1 of 1** (`L_misc.txt` §L3) | **unreachable row** | no | **RAISE**, at write time | not a read-side fallback: if the pushdown target is `instances.data jsonb` (`0001_instances.sql:13-18`), such a record can never have been written there. Lands on FRAMING §6's writes/invariants line, like `f3` H3 |
| **D21** | `extreme`-profile AST fuzz | — | **23 real divergences in 3880 that ran = 0.593%** after §1.9.6 removes 21 container-comparator artifacts; **23 of 23 carry a magnitude ≥ 1.797693e+296, 0 of 23 do not** | mixed (14 value→null, 9 different value) + 3 `SQL_RAISE` | as D1–D5 | **NONE** / RAISE | **subsumed: at closure D21 is D1–D5 seen 23 ways, not an independent class.** Its 3 raises are R1′ |
| **D22** | `if(number("１２３"), null, true)` → py `None`, sql **`True`** — 31 chars, record-independent | **named at closure: any `value → null` divergence sitting in an `if()` **condition** makes the two runtimes take different branches.** Verified live for three independent causes (D8 ASCII gate, D1–D5 f8 guard, D10 date trimming); control with no divergent sub-term agrees | 1 of 3867 in the `unicode` profile — but that measures **how often the generator emits the shape**, not reachability. 0 comparator artifacts | **null → value** — FRAMING §5 clause 1 | **YES** | **NONE** | **none possible — undetectable in principle.** Both branches agree in isolation; the breach is manufactured entirely by branch selection, so no sub-expression check can see it. AVOID: refuse any `if()` whose condition contains a construct that can yield value→null — i.e. `number`, the date functions, or unbounded arithmetic |
| **D23** | the same defects as a `WHERE` predicate: `$.amount > 100` over 8 rows keeps `[2,3,5]` in memory and `[2,5]` in SQL; `number($.amount) > 100` drops rows 3, 6, 7; **`not($.amount > 100)` silently ADDS row 3** | causes are D1–D5 (row 3, `amount=1e300`) and D8 (rows 6–7, non-ASCII numeric strings) — `O_row_loss.txt` | **4 of 4 predicates** lose or gain rows | **wrong row set**, silent | **breaches §4 NO-GO** | **NONE** | none by detection. **Negation is the sharp edge:** `not()` converts a value→null divergence from row *loss* into row *addition*, so "value→null is the conservative direction" is false at the query level |
| R1 | `$.a * $.b` on `{1e200,1e200}` → py `inf`, sql aborts 22003 | `expr.py:614-621` has no overflow guard | probe `overflow_via_multiply`; declared `float8_overflow_raises` | value → raise | no | **RAISE** | R1′. **Coupled to D1–D5:** `B2_overflow.txt` states in its own header that the 297-digit guard means `+`, `-` and `sum()` **cannot overflow today** — "an accident of defect #1, not a design". Fixing D1–D5 enlarges this class |
| R2 | `number('1e999')` → py `inf`, sql NULL | deliberate guard, `compile.py:84-93` | 3 of 27 `C_numgate` probes | value → null, **declared** | no | **NONE** | `f2` records "none". Declared in `KNOWN_DIVERGENCES`, which is a documentation fact, not a run-time signal |
| R5 | `extra_float_digits` ≠ 1 | `M_encoding_guc.txt` §M1: `to_jsonb(float8)` itself returns `0.3333333333333333` / `0.333333333333333` / `0.333333333333` at `efd = 1/0/-3` | 68 of 130 fixture cases carry a float8→jsonb or →text conversion (`f1` §1.2) | different value — **the returned value, not only `string()`'s rendering** | no | **NONE** at query time | pin the GUC on every pushdown session. **Necessary and not sufficient** — D16 is the residue at the pinned value, and D17 is the residue across index-build sessions |
| R6 | `today()`/`now()` with no `context.now`: Python re-reads the clock **per record** (`expr.py:456`), SQL `now()` is the transaction timestamp | one statement = one clock | measured 1.2 s apart in one transaction: SQL `18:02:20` twice, Python `18:02:20` then `18:02:22` (`analysis/coverage.md` §6.2) | different value | no | **STATIC** (the caller controls `context.now`) | **always inject `context.now`.** The one rule in the register that is both decidable and complete |

### C.4 Block C — source-level classes (`f2` §2.7, §2.9)

| id | what diverges | cause | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|
| S1 | `source.type == "query"` | `cascade_deep_search` is a pure in-memory scored cascade over three heterogeneous inputs (`core/deep_search.py:389-390`; `sources.py:256-308` loads every noun instance and every verb run with no limit) | no pushdown possible | no | **STATIC** | whole source falls back. Confirmed and bounded per FRAMING §3; **not reported** |
| S2 | `source.type == "verb"` | `load_verb_group_log` bypasses `core.storage`, so there is no seam to attach a predicate to | no pushdown possible | no | **STATIC** | whole source falls back; **not reported** |
| S3 | `sort.field` names a **derived** column | ordering depends on a column that only exists after `derive` ran | partial pushdown only | no | **STATIC** (`sort.field` vs `derive` keys) | pushable only if its `derive` was pushed too. **Not hypothetical — it is exactly what the one real tenant dashboard on this machine does** (`f2` §2.9) |

### C.5 Block D — storage-layer classes (`f3` §3.6) — these are FRAMING §5's failure mode relocated where the compiler cannot see it

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| H1 | index scan vs seq scan on the same row | `xpr.ecma_num` declared `IMMUTABLE` while reading GUC-dependent float text (`runtime.sql:15-18`) | **0 rows via `Index Scan using idxprobe_ecma`, 1 row via `Seq Scan`** | wrong row set, plan-dependent | breaches §4 NO-GO | **NONE** | = D17. No query-time rule; DDL policy only |
| H2 | `(data->>'score')::float8 > 90` vs compiled `$.score > 90` | `::float8` coerces across types; `xpr.ord` yields NULL on mixed types (pinned by fixture `$.n < "x"` on `{"n":5}` → null) | **5040 vs 4807 rows**; 2409 rows store `score` as a string, 233 of them exceed 90. Control `$.score * 2 > 180` returns 5040 — arithmetic *does* coerce | wrong row set | breaches §4 NO-GO | **NONE** | **the compiler is right and the index-friendly rewrite is wrong.** Rule: never emit the `::float8` rewrite. Price: it is the 89× (re-measured 19×) speedup |
| H3 | `CREATE INDEX … ((data->>'score')::float8)` then insert `{"score":"n/a"}` | `expr` is total; a `::float8` index is not | **write rejected**, and afterwards the index can no longer be built. A `safe_f8` wrapper fixes the write and **still returns 5040, not 4807** | rejected write | crosses FRAMING §6 | **RAISE**, at write time | do not create the index. Two defects; fixing one does not fix the other |
| H4 | `ORDER BY` the compiled sort key | `sources.py:99-115` `_sort_key` orders `bool < number < string < other < None-last`; jsonb's B-tree orders `Null < String < Number < Boolean < Array < Object` | `[false,true,2.5,5,"Zebra","apple",[1,2],{"a":1},null]` vs `[null,"Zebra","apple",2.5,5,false,true,[1,2],{"a":1}]` — **SAME ORDER? False** | wrong row **order**, and with `LIMIT` a wrong row **set** | breaches §4 NO-GO | **STATIC-able** (the column's type mix is a data property, not an AST property — so in practice **NONE**) | **no rule exists.** They agree only on a uniformly-numeric column and nothing in GIMS enforces that. This is where the only working pushdown lives (429× at 0.065 ms) |

### C.6 Block E — route-conditional classes (`f3` §3.5(d)) — only live if the jsonpath route is adopted

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| J1 | `$.x == null` on `{}` | `expr`'s `==` is **total** and never yields null (`expr.py:363-367`, `:603-606`): absent key → `null`, `null == null` → `True`. `'{}'::jsonb @@ '$."x" == null'` is `False` in lax and SQL NULL in strict | **fixture case 33** — inside the 130, and reachable through the exact subset the jsonpath route recommends | **a row `expr` keeps is silently dropped** | **YES** (`f3`'s own reading) | **NONE** | exclude `== null` from the jsonpath route. Note it is one of the two shapes that *are* index-accelerated |
| J2 | bare path as `where`, e.g. `"where": "$.flag"` | `@@` yields the item only when it is a JSON **boolean**, SQL NULL otherwise; `expr._truthy` keeps any non-zero number, non-empty string/array/object | **4 of 6** bare-path fixture cases diverge; the 2 "agreements" are coincidental (both sides falsy on a missing key) | silently drops every row whose value is truthy-but-not-boolean | breaches §4 NO-GO | **STATIC** (the AST shape is visible) | refuse the jsonpath route for bare paths. Whole route: expressible 16/130, agreeing 11/130, index-accelerated **and** agreeing 3/130, routable **1.5% — one distinct expression shape** |

### C.7 Block F — clause-level classes outside `expr` (critic gaps 4 and 15; listed so the register is complete, counted separately)

| id | what diverges | cause | measured | direction | §5? | detect | fallback rule |
|---|---|---|---|---|---|---|---|
| K1 | tolerant key resolution | `sources.py:67` resolves exact key → **case/space/underscore-tolerant** → dotted path; SQL `data->'status'` is exact-only | records keyed `"status"`/`"Status"`/`"status "`: Path A returns `["T-1","T-2","T-3"]`, Path B returns `["T-1"]` — **2 of 3 rows silently dropped** (`measurements.json → tolerant_key_probe`) | wrong row set | breaches §4 NO-GO | **NONE** | **no rule exists anywhere in the spike.** Pushing `where` or `filters` requires reproducing tolerant key resolution in SQL; nothing compiles it |
| K2 | `sort` semantics | `_sort_key`'s 3-key type-rank tuple (`sources.py:99-115`) has no SQL equivalent | = H4 | wrong order → wrong `LIMIT` set | breaches §4 NO-GO | **NONE** | none; `limit` inherits it, since `LIMIT 50` is only well-defined under a matching total order |
| K3 | `derive` chaining | `_apply_derive` writes each result back into the row and "later derives can reference earlier ones" (`sources.py:133-148`) | **nothing compiles, measures or fallback-rules it** | not established | — | **STATIC** (dependency between `derive` keys is visible in the spec) | **not established by this spike.** What would establish it: one two-derive widget where `derive2` reads `$.derive1`, through `compile.py` |

### C.8 The count — the answer the gate actually needs

Counted over the **34 `expr`-layer ids** in Blocks A–C (C1–C4, D1–D23, R1/R2/R5/R6, S1–S3) — the
population critic gap 1 is about. Folding D21 into D1–D5 (`f1` §1.9.6: "one defect seen 23 ways")
gives **33 distinct classes**. Blocks D, E and F add **9 more** ids (4 storage, 2 route-conditional,
3 clause-level) and are counted separately, because D and E are conditional on a storage decision and
F is outside `expr` entirely.

| | count | ids |
|---|---:|---|
| **DETECTABLE at query time** | **15** | C1, C2 (`Uncompilable`) · C3, C4 (off-contract `RecursionError`/`MemoryError`) · D6, D7, D9, D14, D19, R1 (SQLSTATE `22003`) · D20 (write-time `22P05`) · S1, S2, S3 (static, from the source spec) · R6 (caller-controlled) |
| **UNDETECTABLE in principle** | **19 ids = 18 classes** | D1, D2, D3, D4, D5, D8, D10, D11, D12, D13, D15, D16, D17, D18, D21, D22, D23, R2, R5 — **18 once D21 folds into D1–D5** |
| carried a rule in `f2` §2.7, directly or by the critic's mapping | 21 | C1–C4 · R1, R2, R5, R6 · D1–D5 (R3), D18 (R4), D12 (R7), D9, D17, D21 (loosely) · S1–S3 |
| **had no fallback rule anywhere** | **13** | D6, D7, D8, D10, D11, D13, D14, D15, D16 (at `efd`=1), D19, D20, D22, D23 — critic gap 1's list, reproduced exactly |
| **breach FRAMING §5 as literally written** | **2** | **D22** (null → value) · **D11** (raise → value) — **and both are in the unruled 13** |
| **breach the §4 NO-GO bar** (silent wrong number or wrong row set) | **9** in Blocks A–C | D1, D12, D13, D15, D16, D17, D18, D21, D23 · **+7 outside**: H1, H2, H4, J1, J2, K1, K2 |

**15 detectable ids, 19 undetectable ids — and 15 + 19 = 34, the whole register. Folding D21 into
D1–D5 restates the identical split in classes: 15 detectable, 18 undetectable, 15 + 18 = 33. In
either unit more than half the register cannot be seen at query time by any mechanism — 19 of 34
ids (55.9%), 18 of 33 classes (54.5%).** **[punch]** *Units: an id count and a class count are
different denominators and may not be added. This headline previously read "15 detectable, 18
undetectable", which sums to 33 while naming the 34-id register. The arithmetic was mixed, not the
claim — the "half the register" force survives in both units, as the two percentages show.*

**What this section changes in that count.** One rule that already half-existed closes six ids:
**R1′ — catch SQLSTATE `22003`, overflow *and* underflow, on any operator, including `xpr.round`'s
internal overflow, and re-run the whole widget in memory.** It covers D6, D7, D9, D14, D19 and R1;
**four of those (D6, D7, D14, D19) are among the unruled 13.** `f2` R1's condition ("float8 overflow
in `+ - * /`") was too narrow by inspection, not by measurement. D19 additionally admits a
**compile-time** check (`abs(index) < 2^31`), decidable because the grammar accepts only integer literals
in `[n]`/`[-n]` (`expr.py:240-243`). D20 is a write-side fact, not a read-side fallback.
**That leaves eight of the thirteen — D8, D10, D11, D13, D15, D16, D22, D23 — with no possible
detection rule at all**, and for those the only FRAMING §5-compliant answer is AVOID (§C.10).

### C.9 The correction to `f2` §2.8, stated plainly

> `f2` §2.8 concludes: "Five run-time divergences (R2, R3, R4, R5, R7) are **undetectable in
> principle** under this design."

That verdict is scoped to `f2`'s own list of seven run-time rules, not to `f1`'s twenty-three
confirmed classes. Mapped across the whole register the undetectable set is **18 of 33 distinct
classes — 3.6× `f2`'s figure**, and it contains **both** of FRAMING §5's named directions, which
`f2`'s five do not. The critic's estimate of "roughly 2.5×" is confirmed and is if anything low.
Every one of the 13 extra undetectable classes was measured by the same spike, in the same batteries,
on the same database and in the same pass; none of it is new evidence. **The body understates the
undetectable set because it never mapped `f1`'s inventory onto `f2`'s rule table.**

### C.10 The only rule that reaches the silent classes, and its measured price

For all 18 undetectable classes the sole FRAMING §5-compliant rule is AVOID: a **static,
construct-keyed refusal**, evaluated at `sources.py:345` before any SQL runs, reported through a
return-contract field that does not exist yet.

The one place in the record where that rule is written down is `panel.json` verdict [0], which names
the subset: all 10 leaf/structural node types, all 5 arithmetic operators, all 6 comparisons, all 5
field-path forms (with the D19 compile-time index check) and **10 of 22 functions** — `abs ceil
coalesce count floor if length max min round`. Excluded: `days_between date_add today now` (D10, D11),
`sum avg` (D15), `string concat contains` (D16, D2, D3), `lower upper` (D18), `number` (D8, D9).

**Its price, computed by that adjudicator by walking the real `expr.parse` AST over the fixture and
not re-derived by this seat: 36 of 48 constructs** and **84 of 130 cases (64.6%)** — so the rule
refuses **46 of 130 cases, 35.4% of the contract fixture**, including the canonical widget `f4`
measured end-to-end, which is a date widget. **Its coverage of this register has at least two holes, and the larger one is
measured rather than inferred** **[punch]**. **First, D1–D5 — the highest-rate silent class in this
register — survives the subset.** The corrected subset (`f5` §5.7) retains `+ - * /`, all six
comparisons and `abs`/`max`/`min`, and `analysis/fuzz/A_f8_guard.txt` §A2 measures **8 of the 16 paths
that diverge at `a = 1e300`** as composed entirely of constructs the subset keeps: `$.a + 0`, `$.a * 1`,
`- $.a`, `abs($.a)`, `$.a < 1e301`, `$.a > 1`, `$.a >= $.a` and `max($.l)`. Three of the eight are order
comparisons, which that file labels *"the pushdown-predicate path"*. And `max($.l)` returns SQL **`1`**
where Python returns **`1e+300`** — a silently wrong *number*, FRAMING §4's disqualifying clause verbatim,
**inside the subset the AVOID rule exists to make safe**. §C.8's own D1 row concedes the mechanism: its
only AVOID rule is *"refuse any expression whose operands can exceed 1.797693e+296 — not decidable from
the AST, so in practice refuse arithmetic entirely"*, and the subset keeps arithmetic. **Second**, D13
(`xpr.truthy` on a sub-float8 raw-JSON numeric) reaches
through `if`/`not`/`and`, which every subset keeps, and is bounded only by the reachability argument
that `Jsonb(record)` cannot write such a row (`D_rawjson.py:12-17`) — an argument about GIMS's
*current* writer, not an invariant. **OPINION, labelled:** a rule whose completeness rests on no other
process ever writing raw JSON into `instances.data` is a deployment assumption, not a compiler
property, and it is the kind of assumption that fails silently.

### C.11 Sizing the machinery — OPINION, with the reasoning shown

`FRAMING` §4 #5 requires "the cost of the fallback machinery". `f2` §2.8 lists seven changes with no
effort attached; `f4` §4.9 prices the *trigger*. Neither prices the machinery. This spike cannot
measure it, so what follows is a **scoping estimate, labelled OPINION**, every input a counted artifact.

**(a) The one-time build — `f2` §2.8's list, sized by what each touches.**

| item | what it touches | scope, OPINION |
|---|---|---|
| `pushed_down: bool` + `fallback: [{scope,reason}]` on `resolve()`'s dict | `sources.py:357` (one return), its three call sites `:353-356`, plus every UI consumer of the widget contract | **the load-bearing item — everything else is inert without it.** One return shape, but it is a public contract change: `frontend/lib/dashboard/widgets.jsx` already renders a "Result capped for performance" badge for `truncated`, so a precedent exists; a second badge and its copy do not |
| C3 — recursion → explicit stack, or a depth budget checked before recursing | `compile.py`'s whole `_j`/`_t_*` dispatch | rewriting the traversal of a 464-line compiler, not a guard |
| C4 — bind `date_add`'s argument through a CTE/`LATERAL`; accumulate `MAX_SQL_CHARS` during construction | `compile.py:318-326` + `:171-176` | changes the emitted SQL's *shape*, so every conformance number is re-earned |
| C3/C4 belt-and-braces — catch `RecursionError`/`MemoryError` as fallback | the adapter | genuinely small; the only cheap item on this list |
| R1′ — catch SQLSTATE 22003 and re-run in memory | the adapter | small, **but the transaction is already aborted: it is a full retry, not a resume**, and on D7's `BOTH_RAISE` subset the retry raises too |
| R3 — widen the `xpr.f8` guard literal 297 → 309 digits | one line of `runtime.sql` | **mispriced as "one line".** `B2_overflow.txt` states the 297-digit guard is why `+`, `-` and `sum()` cannot overflow today; correcting it converts D1–D5's silent population into a new population of query-aborting 22003 raises, which R1′ must then absorb |
| R5 — pin `extra_float_digits` on every pushdown session | session setup | small, and **incomplete** (D16, D17) |

**(b) The standing obligation — the part nothing in the spike prices.** "Standalone compiler + thin
GIMS adapter" creates a **third runtime** of the expression language, and the contract fixture's own
note makes the obligation explicit: *"Both the Python evaluator … and the JS evaluator … MUST produce
`expect` for each case … Hand-authored expected values — do NOT regenerate from either evaluator"*
(`expr_vectors.json`, `note`). Counted inputs: `expr.py` **646** lines · `frontend/lib/expr.js`
**373** lines · the third runtime is **two artifacts in two languages** — `compile.py` **464** lines
plus `runtime.sql` **427** lines defining **21** `xpr.*` SQL functions · **48** constructs ·
**130** contract cases · **6** JSON value kinds per construct, of which the fixture exercises
`_eq` **7 of 36** cells and `_order_cmp` **4 of 36** (`f2` §2.3).

**OPINION, and the reasoning:** the maintenance cost is not proportional to the 891 lines. It is
proportional to (i) the number of places a language change must land — **three runtimes, four
artifacts, three languages (Python, JS, PL/pgSQL)**, up from two and two; (ii) the number of
*semantic* surfaces re-verified per change — this register is **33 distinct classes** (34 ids, D21 folded into D1–D5), of which **18 classes are invisible** to any test that only checks the 130 cases, because that is exactly how 130/130 was
achieved while both §5 directions were breached **[punch]**; and (iii) the fact that the SQL runtime's behaviour
depends on things the other two runtimes have no analogue for — a session GUC (R5, D16, D17), a
collation (D18), a planner choice (D17, H1), an `IMMUTABLE` declaration the server does not verify,
and the target server's version. **Any future edit to `expr.py` must be mirrored into two
artifacts, one of which is SQL whose correctness is deployment-conditional.** No measurement in this
spike bounds that; the honest statement is that it is a **permanent, unbounded coupling**, and the
130-case fixture demonstrably does not detect its violation.

**(c) What would establish it, since this spike cannot:** size `f2` §2.8's change list against the
three call sites at `sources.py:353-356` and the widget contract in
`frontend/lib/dashboard/widgets.jsx`; then run this register as an acceptance battery against the
proposed subset and count how many of the 34 ids it actually closes. **The batteries already exist**
(`analysis/fuzz/run_all.sh`, 21 of them, plus `O_row_loss.py` as a ready-made regression test) — but
**no run of them against any subset exists**, so the subset's completeness is asserted, not measured.
A `sp-synth` design task; FRAMING §3 forbids this pass from producing it.

### C.12 Why the measured trigger figures do not bound the cost

`f4` §4.9 measures compile-time refusal at **0.0307 ms** (0.0004%–0.22% of Path A) and run-time
refusal at a constructed worst case of **6 917 + 1 494 = 8 411 ms vs 1 494 ms, +463%**. Both are
correct and both are **out of scope for most of this register**:

1. **A run-time fallback can only ever fire on the RAISE classes.** That is 6 of 34 (D6, D7, D9, D14,
   R1, and D19's run-time half). For the **18 undetectable classes (19 ids) there is nothing to
   trigger** —
   the SQL succeeds, the number is wrong, and no timer starts. The +463% figure prices the loud
   failure mode and says nothing about the silent one, whose cost is a wrong number on a tenant's
   dashboard and which this rig cannot price at all.
2. **The 0.0307 ms prices deciding not to push down — which is the AVOID rule, and it is cheap.**
   That is the good news in this section: the only rule that reaches the silent classes costs
   essentially nothing per request. **Its cost is not latency, it is coverage: 46 of 130 fixture
   cases, 12 of 22 functions, and the canonical measured widget.**
3. **Fixing the loudest silent class makes the loud class larger.** R3 (widen the `xpr.f8` guard)
   moves D1–D5 out of "undetectable" and into "RAISE" — which is FRAMING §5's own logic, Postgres
   having been chosen because it fails loudly — but it does so by converting silently-wrong answers on
   `+`, `-` and `sum()` into aborted queries priced at up to +463%. **The register's undetectable
   count and its run-time trigger cost move in opposite directions.** That trade is the decision, and
   no number in this spike prices which side of it a tenant prefers.

### C.13 What this register does not establish

- **Reachability in real GIMS data — closed for this corpus, open at production scale. [consistency]**
  Every witness in Blocks A–C is a constructed record. The read-only sweep this bullet originally
  prescribed was performed and reported by `xd` D.3–D.5, which ran those four predicates over every
  `objects.db`/`archive.db` in both trees: magnitude ≥ 1.797693e+296 → **0 of 5,235,942 numeric nodes**
  (D.3, largest observed `|v|` = 1.787e+12, 284 decades short); non-ASCII decimal digit or non-ASCII
  whitespace → **0 of 1,096,202 string values *plus object keys*** (D.4, in a corpus carrying 206,567
  non-ASCII code points, so the zero is not an artifact of an ASCII-only corpus); >17 significant
  digits **and** the writer-signature test (literal ≠ `repr(float(lit))` / `str(int(lit))`) → **0 of
  5,236,427 numeric literals** on both (D.5). D1–D5, D8, D10 and D12–D14 therefore have **no witness
  in this corpus, and D12–D14 no writer here that could make one**. What remains open is
  **production-scale reachability — `xd` D.8**, which states its own limits against itself: n = 1
  machine, 1 operator, 60.2% of the 37,078 swept rows written by AutoDev itself, and the one
  tenant-shaped project contributing 222 rows. **Scope of this closure, stated so it is not
  over-read:** it covers the exotic-numeric and Unicode classes only. `xd` D.6/D.9 finds the
  tolerant/coercion classes — §C.7's K1, and the string-where-a-number-belongs shape §C.5's H2 is
  about — **reached at scale** in the same corpus (17,144 bool-strings on one key; weight fields 100%
  string; `'60824'` as a `received_date`), and §C.7's K1 still has no rule anywhere in the spike.
- **That the AVOID subset is complete.** It is asserted from cause attribution, never run against the
  register. D13 is already a known hole in it.
- **A rate for D18 at string level, or for D22 in reachable-shape terms**; and **K3 (`derive`
  chaining) in any respect** — uncompiled, unmeasured, unruled.
- **Whether an in-memory fallback always succeeds — mechanism adjudicated in `xa` A.5(ii); what
  remains open is a frequency, not a mechanism. [consistency]** D7's `BOTH_RAISE` (0.81%), D11's four
  `PY_RAISE` witnesses and `B2_overflow.txt`'s `round($.a,20)` on `1.7e296` are three mechanisms by
  which `expr` itself raises, against `expr.py:640` and `recon/semantics.md` §11 — and §C.3's D7 row
  and §C.11(a)'s R1′ row already carry the consequence into the register. **A fallback whose target
  can raise is not a fallback.** `xa` A.5(ii) measures exactly that: one poison row
  `{"d":"0001-01-01T00:00:00+14:00"}` placed at index **0, 5 or 9** of a 10-row list produces an
  **uncaught `OverflowError` in both `_apply_derive` (`sources.py:147`) and `_filter_rows`
  (`sources.py:162`)** — neither `evaluate()` call is inside a `try` — which
  `core/errors.py:115-119`'s `@app.exception_handler(Exception)` returns as **HTTP 500
  `INTERNAL_ERROR`**, i.e. loud but not a *report*: no `pushed_down: false`, no reason, no partial
  result. On the one battery that quantifies the overlap (`G2b_round_raises.txt`, n = 8000) Postgres
  raised on 94 + 65 = 159 probes and Python raised on 65 of those same 159, so **40.9% (65/159) of SQL
  raises also raise in the retry** and R1′ rescues ~59% of that domain, not 100%. **What genuinely
  remains open is the production frequency of `xa`'s N1–N4 raise conditions**, which `xa` A.5 records
  as not established and does not chase, per FRAMING §3. Note the bound from `xd` does not extend to
  it: `xd` D.3–D.5 screens magnitudes, non-ASCII digits/whitespace and writer signature, and runs **no
  predicate for offset-bearing or out-of-`datetime`-range date strings**, which is the shape carrying
  D11 and `xa`'s R1. The D11 half of this frequency is therefore unbounded by any sweep in this spike.

**Net effect of the two closures above on this section's argument — labelled, because it cuts both
ways. [consistency]** The first weakens a leg this register leaned on: "no witness in production data"
is no longer an open unknown for D1–D5, D8, D10 and D12–D14 on this machine, so the exotic-numeric
half of the undetectable set is, for this corpus, a hazard with **zero observed instances** rather than
an unquantified one. The second strengthens the opposite leg: the fallback of last resort is not
merely unruled, it is **measured to fail 40.9% of the time on the only domain that quantifies it** and
to surface as a 500 rather than a report. Neither closure changes the counts in §C.8 — detectability is
a property of the mechanism, not of its rate — and this section still recommends nothing. **OPINION,
this seat:** on the register as a whole the second closure is the heavier of the two, because the
classes `xd` finds *reached at scale* (tolerant keys, string-typed numbers, null propagation through
`derive`) are the ones with no rule at all, and R1′ does not touch them.

### C.14 Compliance attestation **[consistency]**

**Compliance.** Read-only throughout, and **no new experiment**: every row in Blocks A–F is assembled
from `f1` §1.9.1–§1.9.7 as corrected at closure, `f2` §2.6–§2.9, `f3` §3.5(d)/§3.6, `f4` §4.9/§4.11
and the already-captured `analysis/fuzz/*.txt`. No figure in this section originates in a run made for
this section: every cell carries a citation to a prior section or to a committed capture, so no fuzz
battery was re-run, no capture was regenerated, and no database object was required, created, altered
or dropped. Both GIMS trees, `FRAMING.md`, `recon/`, `proto/`, `analysis/`, `.autodev/` and `kb/` were
read and not written; the only file this seat wrote is `spikes/T-1/.parts/xc-fallback-register.md`.

**Nothing is fixed, per FRAMING §3.** C1–C4, R3, R5 and the absent reporting channel are **recorded,
not repaired**. In particular **R1′ — the one new rule this section proposes (§C.3, §C.8, §C.11(a)) —
is proposed as a *rule* and is not implemented**: `compile.py`, `runtime.sql` and `sources.py` are
byte-unchanged by this seat. FRAMING §3's stop rule ("a divergence whose cause is identified → record
cause + fallback rule, do not fix it") requires that form rather than merely permitting it. §C.11 is
labelled **OPINION** and is a scoping estimate, not a measurement; §C.11(c) records that the existing
batteries have **never been run against any proposed subset**, so the AVOID subset's completeness is
asserted, not measured, and this section says so rather than closing it.

**What is not independently attestable from the artifacts, stated rather than glossed:** this section
produced no run log, script or capture of its own — by design, since it ran nothing — so its read-only
status rests on the citation audit above rather than on a recorded transcript. The closure edits marked
**[consistency]** in §C.13 were made in this document only, against `xa` A.5(ii), `xd` D.3–D.5/D.8 and
`analysis/fuzz/G2b_round_raises.txt` as read; no artifact outside this file was modified to make them
true.
