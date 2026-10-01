# `parity/` — autoSQL against GIMS's real dashboard pipeline (T-46)

Every earlier autoSQL battery compared the compiler with GIMS's expression evaluator on rows **as
stored**. A GIMS dashboard never evaluates a row as stored. Between `instances.data` and the screen,
GIMS copies keys, tags rows, looks fields up forgivingly, and sorts with its own total order. This
directory pins what each of those steps does, case by case, and what autoSQL's shipping compiler and
runtime do with the same case.

| file | what it is |
|---|---|
| `gims-pipeline-vectors.json` | the cases. **The source of truth**; GIMS pins a vendored copy |
| `check_gims_pipeline.py` | one command: GIMS confirms every expectation, then autoSQL is measured on every case |
| `tests/test_vectors.py` | the format, checked without GIMS or a database |

## Run it

```
demo/.venv/bin/python parity/check_gims_pipeline.py --gims <a GIMS source tree> \
    --dsn "host=127.0.0.1 port=<scratch> user=… password=… dbname=…"
demo/.venv/bin/python -m pytest parity/tests -q
```

- **The GIMS half needs no database.** It imports GIMS's own modules from the tree given by `--gims`
  (bytecode writing off, so nothing lands there), and drives GIMS's real
  `api.dashboard.sources.resolve()` end to end. Only the record store is replaced, by one that hands
  over the case's rows in jsonb key order (the order GIMS receives them in, in Postgres mode).
  `boto3`, which `api/i_o` imports at load and the pipeline never calls, is an inert stand-in.
- **The SQL half needs a scratch Postgres 16** (`--dsn` or `AUTOSQL_PARITY_DSN`). It installs the
  current `runtime/runtime.sql` fresh and runs `compiler/compile.py`'s output. Port 55433 is refused.
  Without a DSN the run says, loudly, that autoSQL was compared against nothing.
- **Exit codes:** 0 when GIMS confirms every expectation and every recorded `autosql` status and answer
  re-measures; 1 when anything does not; 2 for a malformed file; **3 when there was no DSN**: the GIMS
  half ran and the SQL half compared nothing, which is never a plain pass. `--gims-only` asks for the
  GIMS half alone, and exits 0 if it passes.
- The SQL half needs **Postgres 16 or later with UTF8** (the runtime and `COLLATE "C"` ordering assume
  both), and it **drops and reinstalls schema `xpr`** on the database it is given: use a scratch one.
  Port 55433 is refused by the port the connection actually reached, before any statement is sent.
- A recorded divergence is confirmed only by the **same answer** it recorded (`sql_gives`). An SQL error,
  or a different wrong answer, fails the run.
- **`--fold gims`** (T-48) also compiles every expression case (record, expr, a `where` filter) with
  `compile_ast(…, fold="gims", noun=…)` and requires each case's recorded `autosql.folded` to
  re-measure. That is the SQL a pushed-down `where` runs: see `compiler/README.md`.

## The format: `gims-pipeline-vectors/1`

It extends GIMS's `tests/fixtures/expr_vectors.json`: the same top keys (`version`, `note`, `float_epsilon`,
`cases`) and the same case keys (`group`, `name`, `expr`, `expect`, `record`, `context`). **A consumer must
dispatch on `kind`**: GIMS's existing expression loader, pointed at this whole file, fails on every case
that is not `kind: "expr"`. It adds:

- `format: "gims-pipeline-vectors/1"`, and an integer `version` bumped on any change to a case;
- `noun`: the noun every row is served under (the `_noun_type` tag), and `key_order: "jsonb"`: rows reach
  GIMS in jsonb key order (shorter keys first, then bytewise), as in Postgres mode. Both are things a
  consumer must reproduce to get GIMS's answers;
- `source`: `autosql` (the commit the statuses were measured at), `compiler_sha256` and
  `runtime_sha256` (the exact compiler and runtime measured), `gims` (the commit that confirmed the
  expectations);
- per case, `kind`:

| kind | keys | the GIMS answer it pins |
|---|---|---|
| `expr` | `expr`, `record`, `expect` | GIMS's existing shape, unchanged: `evaluate_str(expr, record, context)` |
| `record` | `stored`, `expr`, `expect` | the value of `expr` on the row **as the pipeline presents it** (after key copies and the `_noun_type` tag), via a `derive` column |
| `sort` | `rows` (each with `id`), `sort: {field, dir}`, `expect_ids` | the row order after `resolve`'s sort |
| `filter` | `rows`, `filter`, `expect_ids` | the rows kept, in order. A string `filter` is a `where` expression; an object is a `filters` map |

- per case, `autosql: {status: "agrees" | "diverges", why, fix_side}`. A divergence is **kept and
  explained**, never deleted. `sql_gives` records what autoSQL actually returns on it. `fix_side` says which side must change, seen from T-37's design (SQL runs
  the `where`; Python shapes the rows, then applies the `filters` map, the sort and the limit):
  `adapter-shaping`, `where-clause`, `filters-map`, `sort-pushdown`, `browser` or `accepted`.
- per expression case (record, expr, a `where` filter), `autosql.folded`: the status of the same case
  compiled with GIMS key folding (T-48). Required on those cases and absent on the rest; a folded divergence records `folded_gives`.

Expected values are **hand-authored** from GIMS's code and then confirmed by GIMS's own pipeline.
Never regenerate them from either side: a vector that encodes a misreading of GIMS would make GIMS's
parity gate pass or fail for the wrong reason.

**How GIMS will pin it** (gims-w2's vendoring, built tonight on a GIMS branch; nothing of it is on GIMS
`main`). GIMS vendors a copy beside the vendored compiler and runtime and records its sha256 and the autoSQL
commit in the same manifest. Its pin test can then also compare
`source.compiler_sha256` and `source.runtime_sha256` with the vendored compiler and runtime: if they
match, the recorded statuses describe exactly the autoSQL GIMS runs. GIMS never edits its copy;
changes come here first. T-39 (GIMS's three-way parity gate) loads the vendored copy.

## Findings (v4: 61 cases, 34 agree, 27 diverge; GIMS `9bf7b24`; the compiler and runtime by their `source` digests)

**With GIMS key folding (T-48), 32 of the 33 expression cases agree**, including the 5 copy and tag
where-clause cases and the 8 shaping cases that are expressions. The one that does not is a `where` over a
**derived column** (`where_over_a_derived_column`): GIMS runs derive before the where, a stored row has no
such key, and folding cannot invent it. **T-37 must not push down a where that names a derive output** (or
must inline the derive expression). What remains is not an
expression: the sort cases (T-42), the filters-map cases (Python, by T-37's design), and the one
sort by a copied key, which T-37's shaping fixes.

| fix side | cases | what must change |
|---|---|---|
| `adapter-shaping` | 9 | T-37 gives SQL-picked rows GIMS's key copies and the `_noun_type` tag before derive, filters and sort |
| `where-clause` | 6 | a pushed-down `where` must see the copies and the tag (**T-48**, compile-time key folding), and must not name a derived column (T-37) |
| `filters-map` | 3 | only if the `filters` map moves into SQL. T-37 keeps it in Python, after SQL's `where` |
| `sort-pushdown` | 9 | only if sort moves into SQL (T-42). T-37 sorts in Python |
| `browser`, `accepted` | 0 | none among these cases. The browser's own differences are listed at the end |

One difference T-37 accepts on purpose, outside the vectors: Python caps a noun at 20,000 rows BEFORE
filtering, and SQL's `where` runs before any cap. Above 20,000 raw rows the pushed-down answer includes
rows Python's cap was dropping.

### Where autoSQL diverges, and the side that must change

1. **Key copies (7 shaping cases and 4 where-clause cases).** `get_noun_items` (`api/iostore/nouns.py:41-50`, `_normalize_row`) adds,
   for every top-level key, a copy with underscores turned to spaces and one with spaces turned to
   underscores, through `setdefault`: a stored key always wins, and between two stored keys that
   produce the same copy, the first in key order wins. **In Postgres mode that is jsonb's key order**
   (shorter first, then bytewise). In SQLite mode it is insertion order, so the two modes can pick
   different winners. Nested keys, hyphens and case are left alone. Compiled SQL reads
   `instances.data` as stored, so `$.Sample_ID` over a stored `"Sample ID"` is blank there and
   `"S-1"` in GIMS. **The adapter (T-37) must give SQL-picked rows the same copies before derive,
   filter and sort.** A `where` pushed into SQL must see them too, either by copying in SQL first or
   by having the compiler resolve a key to its copies with the same precedence.
2. **The `_noun_type` tag (3 cases).** `_noun_records` tags every noun row with
   `_noun_type = <noun>` (setdefault: a stored `_noun_type` wins, and so does a stored `" noun type"`,
   because the key copies run first and copy it to `_noun_type`). Rows read straight from SQL lack
   it. **T-37 must add it**, and a pushed-down `where` must see it.
3. **The forgiving field lookup (7 cases).** Sort fields and the `filters` map go through
   `_field_value` (`api/dashboard/sources.py:67-85`): the exact key, then `find_actual_key`
   (`core/deep_search.py`: case-blind, and blind to spaces, underscores and hyphens; the **first**
   match in key order), then a dotted path through dicts only. A forgiving match beats the dotted
   path (`"a.b"` finds `"A.B"` before `a → b`). SQL reads the exact key. The `filters` map also
   compares with Python's `==`, so `{"flag": 1}` matches `true` and `1.0`, and `{"x": null}` matches
   a missing field. autoSQL has no translation for a `filters` map. **Whoever moves sort or filters
   into SQL (T-42) must translate `_field_value` with its precedence, and Python's equality with its
   quirks**; until then they stay in Python (T-37's design already does this).
4. **Lists and objects in a sort (3 cases).** `_sort_key` ranks them 3 and orders them by
   `str(value)`, Python's own text (`[1, 2] < [10] < [9] < {'k': 1}`). autoSQL's candidate SQL order
   (the rank/number/text triple from the T-1 and T-4 benches) ranks them equal and falls back to
   input order. **T-42.**

### Where autoSQL agrees (34 cases), which T-42 can rely on

Blanks (null and a missing key, as one class) sort **last ascending and first descending**. `""` is a
string, not a blank. Numeric strings sort as text (`"10" < "100" < "9"`), and a number sorts before
any string. Booleans sort before numbers. Text orders by code point, which `COLLATE "C"` reproduces
on UTF-8, astral characters included. **Ties keep input order in both directions**: Python's sort is
stable even with `reverse=True`, and SQL matches it only with an explicit `…, <input order>`
tiebreak. That tiebreak is this harness's `ord` column; `instances` has no such column, and GIMS's own
load order is unspecified (no `ORDER BY`), so T-42 must choose a tiebreak and accept that Python's tie
order is itself whatever the database returned. Extreme magnitudes order correctly through `xpr.f8`. In `where`, truthiness matches
(strings, numbers, lists, objects), so does `== null` against null **and** a missing key, `>`
between a string and a number is null rather than a coercion, and a boolean is never equal to a
number. The evaluator's own lookup is exact: no copies, no folding.

### Inside GIMS, not autoSQL's to fix (for T-39 and T-37)

From the read of GIMS at `9bf7b24`:

- **The browser never re-runs the server's `where`, `filters`, `sort` or `limit`.** It evaluates
  widget `conditions` (`frontend/lib/dashboard/logic.js:191-197`), a value widget's own
  `render.cfg.where` (`logic.js:44`), and a single-value condition against the aggregate
  (`widgets.jsx:55-58`). For three-way parity, the browser's side of a `filter` case is
  `frontend/lib/expr.js` running the same expression over the rows **as served** (copies and tag
  included). It is not a re-run of the server's filter.
- **The browser's field lookup is not the server's.** `getPath` (`logic.js:31-40`) does no case or
  separator folding, but does step into lists (`"tags.1"`). Table cells, value widgets and charts use
  it, so a sort field the server finds forgivingly can show blank in a cell.
- **The table's header-click sort** (`ui.jsx:122-138`) is a different comparator, and puts blanks
  **first** when ascending.
- **Unified-store reads have no `ORDER BY`**, so the order of tied rows, and which rows survive the
  20,000-row cap, is whatever the database returns.
- **A JSON integer too large for a float raises `OverflowError` in `_sort_key`**, an uncaught 500
  (T-36's class). The vector format cannot express an expected error, so no case pins it.
- **None of the above is tested in GIMS today**: no test reaches `_normalize_row` with a key that has
  a space or an underscore, and the descending-blank test checks ascending only.

### Known limits of this harness

- The sort cases run a local copy of the benches' rank SQL (`spikes/T-4/bench_t4.py` `_sort_sql_dir`),
  not shipping code: autoSQL has no sort compiler yet (T-42).
- `jsonb_order` reorders top-level keys only; a nested object's key order is not emulated. No case
  depends on it.
- The filters-map divergences are recorded as `uncompilable`: the shipping compiler has no
  translation. The benches built ad-hoc ones, which also diverge (measured by T-46's reviewer).
