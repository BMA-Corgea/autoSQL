# T-5 · Findings — do non-ASCII digit strings actually occur in the real data?

Stage: `sp-investigate` (spike@v2) · lean: OFF · Run: **2026-09-01** ·
Bar: **`spikes/T-5/FRAMING.md`**, fixed before any evidence, plus its 2026-09-01 amendment
recording the owner's two rulings.

**Read-only, and here is the guarantee.** Every SQLite database was opened
`file:<path>?mode=ro&immutable=1` — the form T-1 §D.1 used. **No Postgres connection was opened at
all**, by anything, at any point; `glp_strong` was never contacted, per the owner's ruling (FRAMING
amendment A1). No compiler was run, no `xpr` schema installed, no expression compiled. Nothing was
written anywhere outside `spikes/T-5/`.

Probes and their raw outputs: `probes/P1_csv_to_store.{py,txt}` · `probes/P2_tier_b_denominator.{py,txt}`
· `probes/P3_number_fields_on_disk.{py,txt}`. All three are re-runnable and print their own inputs.

---

## The answer, in one paragraph

**In the stored data: no. Not one, anywhere, and the zero is trustworthy.** A second independent
instrument, run eleven days after T-1's, reproduces both of T-1's zeros over a corpus that
demonstrably carries plenty of other non-ASCII. **But the published denominator was misleading by
four orders of magnitude** — the honest base is **144 strings, not 1,096,202** — and, far more
importantly, **the question was pointed at the wrong thing.** GIMS's own supported CSV/XLSX import
path admits **8 of 10** non-ASCII digit forms straight into fields the schema declares as numbers,
and the gate that lets them through is the very function meant to enforce "this field is a number".
**The trigger has not occurred, and nothing on the path prevents it from occurring.**

---

## 1. The stored data — T-1's zeros hold, independently

`probes/P2_tier_b_denominator.py`, 8 live SQLite stores, all `mode=ro&immutable=1`:

| corpus | rows | strings+keys | coercible | non-ASCII | **tier A** | **tier B** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GIMS-Project · LIMS-System | 249 | 2,597 | **137** | 0 | **0** | **0** |
| GIMS-Project · LIMS archive / DurationDemo / RunlogTest / Sterility | 0 | 0 | 0 | 0 | 0 | 0 |
| gims-ledger · guts-ledger | 18,823 | 564,703 | 4 | 24,914 | **0** | **0** |
| gims-ledger · guts | 12,479 | 371,446 | 3 | 15,188 | **0** | **0** |
| gims-ledger · guts-code | 6,906 | 203,183 | 0 | 8,195 | **0** | **0** |
| **shown, not pooled** (FRAMING §9 rule 3) | 38,457 | 1,141,929 | **144** | 48,297 | **0** | **0** |

Tier A = contains a non-ASCII `Nd` digit. Tier B = the Python gate coerces it and the SQL gate does
not — i.e. a string that actually produces a divergence (FRAMING §4.2). **Non-ASCII whitespace: 0.**

**The Unicode-tolerance control passes** (FRAMING §9 rule 1): **48,297 of 1,141,929 strings (4.23 %)
carry at least one non-ASCII character**. The corpus could have carried a non-ASCII digit. It does
not. The zero is load-bearing, not an artifact of an ASCII-only corpus.

**This is an independent reproduction, not a re-quote.** T-1 swept on 2026-08-21 and reported
0 / 1,096,202; this walker ran 2026-09-01, over a corpus that has grown by ~1,379 rows since
(AutoDev's own ledger kept writing), with its own predicate implementation, and returns the same two
zeros. That is now **four** instruments agreeing (T-1 ran three).

## 2. The denominator — the published figure overstates the guarantee ~7,600×

FRAMING §4.3 predicted this and it is worse than predicted:

| | |
| --- | ---: |
| T-1 §D.4's published denominator (every string value + object key) | **1,096,202** |
| the decision-relevant denominator (strings a dashboard would coerce) | **144** |
| the honest base, as a fraction of the published one | **0.01 %** |

**"Zero out of 1,096,202" reads as an overwhelming guarantee. The true statement is "zero out of
144."** Both are true; only one is informative. The 1,096,202 is dominated by object keys and by
the 17,144-plus `"false"` strings T-1 §D.6.1 found — none of which `_NUM_RE` will coerce, so none of
which could ever have carried this failure. **137 of the 144 coercible strings are in the LIMS
tenant project**; the three ledger databases contribute **7 between them**.

A zero over 144 strings on one machine, from one operator, in a sandbox project is a **weak** prior
about a product's future. That is not a criticism of T-1 — its §D.8 said plainly that nothing there
extrapolates — it is what happens when the number is quoted without its base.

## 3. The door — GIMS's import path admits the trigger by design

This is the finding, and it is not a row count.

The owner's ruling A2: *"In the GIMS there's a method of adding rows and data for a run or noun via CSV.
That gets digested by a python process."* Following that path through the code:

**The chain, link by link, every link read in the source:**

| # | what happens | where |
| --- | --- | --- |
| 1 | CSV read as UTF-8; `csv.DictReader` yields **every cell as a `str`, verbatim** — no numeric parsing anywhere | `GIMS-Project/api/routers/noun_workbench/uploads.py:43-49` |
| 2 | XLSX likewise: `rec[h] = "" if cell.value is None else str(cell.value)` — **stringified, verbatim** | `uploads.py:51-65` |
| 3 | rows validated against the noun schema | `api/routers/noun_workbench/routes_bulk.py:127` |
| 4 | a field declared `number`/`int`/`float` is checked with `is_number(val)` | `core/words/validation.py:143-146` |
| 5 | **`is_number` is bare `float(str(value))`** — and `float()` accepts all 670 non-ASCII `Nd` digits | `core/words/validation.py:88-97` |
| 6 | `_clean` maps only `"" → None`. **No coercion, no normalization, no ASCII check** | `routes_bulk.py:118-119` |
| 7 | the **original string** is written to the store | `routes_bulk.py:141/144/163` |
| 8 | today's dashboard reads it: `_NUM_RE` uses Unicode-aware `\d`, so it coerces → **correct number** | `autoSQL/demo/vendor/expr.py:302-317` |
| 9 | autoSQL's compiled SQL reads it: `btrim` on ASCII whitespace, then a literal `[0-9]` class → **NULL** | `autoSQL/demo/vendor/runtime.sql:73-77` |

**Driven end to end against the real GIMS validator** (`probes/P1_csv_to_store.py` imports
`core.words.validation.is_number` itself — the same object the API calls):

| CSV cell | GIMS validator | today's dashboard | autoSQL compiled | |
| --- | --- | ---: | ---: | --- |
| `123` | ACCEPTS | 123.0 | 123.0 | agree |
| `１２３` full-width | **ACCEPTS** | 123.0 | **NULL** | **silent wrong number** |
| `١٢٣` Arabic-Indic | **ACCEPTS** | 123.0 | **NULL** | **silent wrong number** |
| `۱۲۳` Persian | **ACCEPTS** | 123.0 | **NULL** | **silent wrong number** |
| `๑๒๓` Thai | **ACCEPTS** | 123.0 | **NULL** | **silent wrong number** |
| `१२३` Devanagari | **ACCEPTS** | 123.0 | **NULL** | **silent wrong number** |
| `１.５` full-width decimal | **ACCEPTS** | 1.5 | **NULL** | **silent wrong number** |
| `٣.٥` Arabic-Indic decimal | **ACCEPTS** | 3.5 | **NULL** | **silent wrong number** |
| `\xa07\xa0` NBSP-wrapped `7` | **ACCEPTS** | 7.0 | **NULL** | **silent wrong number** |
| `n/a` | rejects | — | — | stopped at import |

**8 of 10.** The NBSP row is the T-3 "D10" whitespace gap arriving by the same door: Python's
`str.strip()` removes all 19 non-ASCII whitespace code points, and SQL's `btrim(E' \t\n\r\f\v')`
removes none of them. A trailing non-breaking space is an ordinary artifact of an Excel export or a
web copy-paste — **no unusual locale is required for that one.**

**The gate is one missing flag wide.** `_NUM_RE`'s `\d` is Unicode-aware because the pattern is a
`str`; with `re.ASCII` the same pattern rejects `'１２３'` and `'١٢٣'` (measured). Stated as a fact
about the mechanism — **the fix is T-6's to choose, not this spike's.**

## 4. Where it would land — real fields, on the real schema

Not hypothetical fields. `probes/P3_number_fields_on_disk.py`, read-only against the live LIMS
store, with the schema read from `projects/LIMS-System/noun_types.json`:

| noun | field | required | rows | what is physically stored |
| --- | --- | --- | ---: | --- |
| Potency Sample | **`Sample Weight (g)`** | **yes** | 17 | `null` ×7, **`str` ×10** — `'1'`, `'1'`, … |
| Potency Sample | **`Dilution Weight (g)`** | **yes** | 17 | `null` ×7, **`str` ×10** — `'24'`, … |
| Terpene Sample | `Sample Weight (g)` | yes | 17 | `null` ×7, **`str` ×10** |
| Terpene Sample | `Dilution Weight (g)` | yes | 17 | `null` ×7, **`str` ×10** |
| Elbows | `Force` | yes | 1 | **`str` ×1** — `'12'` |
| Glove | `size` | no | 9 | **`str` ×9** — see §5 |

**14 number-typed fields are declared across 10 nouns; 6 carry any rows; and all 6 hold strings —
none holds a JSON number, on any row.** So the coercion path is not an edge case reached by unusual
data: **it is how every number in this project is read.** A `Sample Weight (g)` of `１.５` would be
accepted at import, stored as text, read as **1.5** by the dashboard today and as **nothing** by
autoSQL, on a **required** field of the project's flagship noun.

## 5. Unplanned finding — the number type is not enforced on every write path

`Glove.size` is declared `type: float`, and the rows stored in it are:

```
'lmao im a changling'   '3 more boss'   'oh okay'   'ok I pull up'
```

`is_number()` rejects all four. **They are in the store anyway**, so at least one write path reaches
`put_record` without the schema check that `bulk_commit` applies — or these rows predate it. Either
way: **a `float` declaration in `noun_types.json` is not a guarantee about what is stored under it.**

This is out of T-5's charter and is reported rather than pursued. It matters here for one reason:
any autoSQL design that plans to trust declared types to decide what to compile — an expression
index per assumed scalar type, say — cannot trust them on this evidence.

## 6. Verdict against the bar

**FRAMING §9 bands, computed on tier B over coercible strings, per corpus, unpooled:**

> **Band: ZERO.** 0 of 144, tier A also 0, with a passing Unicode-tolerance control.
> By the bar as written: **T-3's ruling stands, unqualified. Proceed to fix-and-re-run.**

**And the bar's own premise did not survive the run.** The bands price the risk by *prevalence in
stored data*. §3 shows prevalence in stored data is a fact about what one operator has typed on one
machine, while the import path is a fact about **what the product accepts from anybody**. The
amendment anticipated exactly this and instructed that it be said plainly, so:

- **Nothing observed argues against T-3's fix.** A loud refusal on a value that occurs zero times
  regresses nothing that exists today. The ZERO band's practical conclusion holds.
- **The COMMON trigger is not fired, but it is not *bounded* either.** The band that would overturn
  the ruling depends on a rate that today is zero and that **one CSV from a lab using Thai, Persian,
  Arabic-Indic or full-width numerals — or one Excel export with a trailing non-breaking space —
  moves off zero**, with no code change and no misuse. How often that happens is a question about
  customers, and this machine cannot answer it.
- **A third treatment site exists that neither T-3 nor this framing named:** the gap can be closed
  **at the door** (`is_number`, one function, one flag) rather than **at every query** (a refusal
  in the compiled runtime). The two are not exclusive. **Weighing them is `sp-synth`'s job, and the
  ruling is the owner's** — noted here only because a finding that names a treatment site nobody had on
  the table should not be left in a probe file. Note it is **GIMS's** code, not autoSQL's, which is
  a real cost given the owner's ruling that autoSQL stands as its own project.

## 7. Q2 — the writer inventory

**Answered, and it splits.**

- **Storage writer: Python, confirmed.** the owner: *"That gets digested by a python process."* Corroborated
  in code — the bulk path writes through `store.put_record` (`routes_bulk.py:141/144/163`), and T-1
  §D.5 found **0 of 5,236,427** stored numeric literals that a `json.dumps()` of a Python object
  could not have emitted. **T-3's M4 class — raw-JSON rows a Python float cannot represent — stays
  contingent on a writer that does not exist, and prices low.** This is the direct answer to the
  ticket's second question.
- **Content author: not Python, and not the system.** CSV and XLSX cells are authored by people,
  instruments and spreadsheets, and enter as text the system did not generate (§3, links 1–2).
  **The row format is trustworthy; the row content is arbitrary.**

One historical note, from T-1 §D.5: `storage_aws.py:326-335` carries a comment documenting this
exact Python/non-Python parity disagreement as a bug the team fixed once — so a non-Python writer
**has** existed in this system's history.

## 8. Limits — what this run does NOT establish

1. **`glp_strong` was not examined.** By the owner's ruling (A1), on relevance grounds. Stated here in
   the findings, not buried, per FRAMING §10.
2. **`guts-pg`** (exited container, port 55432), **158 backup snapshots**, the **un-checkpointed
   WAL**, and `archive.db`'s column-per-field `noun_Sample` table were **not swept**. A1 removed most
   of their point — they are the same tooling data — but they are un-swept and that is a fact, not
   an argument.
3. ***n* = 1 machine, 1 operator, and the tenant project is a sandbox.** Noun names in the LIMS
   schema include `Sand`, `LL Cool J`, `Soup Ladel` and `t55t5t5t5t5`. `Potency Sample` and
   `Terpene Sample` are a real cannabis-testing domain shape, but **these are test rows.** Nothing
   here extrapolates to production, and §2's denominator of 144 is a sandbox's denominator.
4. **No divergence was executed against a database.** §3's SQL column is `xpr.num`'s string branch
   **transcribed from `runtime.sql:73-77`**, not run — deliberate, since running the compiler is
   outside this stage (FRAMING §10). T-3 already demonstrated the same divergence live; this run
   shows the **route in**, not the failure itself.
5. **The `Glove.size` bypass (§5) was found, not investigated.** Which write path skips validation
   is unknown.
6. **Rate of CSV import in practice: unmeasured.** That the door is open says nothing about how
   often anyone walks through it, or with what locale.

## 9. Attestation

Run 2026-09-01 on branch `spike/T-5-nonascii-digit-homework`. 8 SQLite databases opened read-only
and immutable; **zero Postgres connections**; zero writes outside `spikes/T-5/`. `is_number` was
imported from `GIMS-Project/core/words/validation.py` and executed as the real object. T-1 and T-3
figures were re-read from their own files at the cited sections. Every table above is reproducible
by re-running the three probes, which print their inputs.
