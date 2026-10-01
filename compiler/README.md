# `compiler/` — autoSQL's expression → Postgres compiler

`compile.py` turns a GIMS dashboard expression AST into a parameterised Postgres
statement whose value semantics match `core/dashboard/expr.py`. It runs against
schema `xpr`, which lives in [`../runtime/`](../runtime/README.md).

## Where it came from

Promoted out of `spikes/T-1/proto/compile.py` by **T-11** (2026-09-01) — the same
promotion `runtime.sql` got in T-8, and for the same reason.

**The spike copy is FROZEN EVIDENCE.** Its sha256 `b71b153802d0df94…` is cited in
T-6's attestation and in all 42 of T-6's battery outputs. Editing it would break the
chain that lets anyone re-derive those results, so it never changes again. A test
asserts it hasn't.

## The one thing the promotion changed

**Float8-valued results are emitted through `xpr.j(...)` instead of bare `to_jsonb(...)`.**

`to_jsonb` reads `extra_float_digits` — a session GUC any connection can change. At
`0` or `-3` Postgres prints fewer digits than a double carries and the number comes
back **short**: T-3's mechanism M3, **62–66 wrong answers** across T-6's batteries.
`xpr.j` carries its own `SET extra_float_digits = 1`, so it is immune to whatever the
session says.

Measured, both directions:

```
                        efd 1                  efd -3
frozen compiler         0.3333333333333333     0.333333333333      ← moves
shipping compiler       0.3333333333333333     0.3333333333333333  ← immune
```

**Text and boolean results still use `to_jsonb`, deliberately.** Neither has digits to
lose, and wrapping them would cost a function call for nothing. A test asserts they
stay unwrapped, so a later "consistency" pass doesn't wrap them anyway.

**Nothing else changed.** `test_the_promotion_changed_nothing_but_the_float8_wrapper`
compiles the same expressions with both modules and requires them byte-identical once
the one intended swap is undone — because copying a 464-line compiler and editing 18
call sites is exactly where an unrelated edit rides along unnoticed.

## Running the tests

```
./run-demo up
AUTOSQL_COMPILER_DSN="host=127.0.0.1 port=55440 user=autosql_demo password=autosql_demo_password dbname=autosql_demo" \
  demo/.venv/bin/python -m pytest compiler/tests -q
```

The pure-Python half runs anywhere; the database half skips without that DSN.
**Never point it at port 55433** — that is a live database, and the tests refuse it.

## Known, and not this directory's job

- **The magnitude guard still refuses** values beyond `float8` range by name (`XPR01`).
  That is correct and unchanged.
- **`xpr.assert_float_digits()`** (T-9) remains for callers that hand back `float8`
  directly. Nothing this compiler emits does, but the guard is there for code that does.

## GIMS key folding: `compile_ast(ast, fold="gims", noun=…)` (T-48)

A GIMS dashboard never evaluates a noun row as stored. `get_noun_items` serves every top-level key
**also** with its spaces and underscores swapped (`_normalize_row`: setdefault, stored keys taken in
jsonb order), and `_noun_records` then sets `_noun_type` to the noun if the row has none. A `where`
pushed into SQL runs over the **stored** row, so without help, `$.Sample_ID` over a stored
`"Sample ID"` is blank in SQL and `"S-1"` in GIMS, and the two pick different rows. T-46's vectors
(`parity/`) measure the class.

With `fold="gims"`, the first key step of every field path compiles to the key the served row would
answer with, statically, with no per-row function:

```
$.Sample_ID   →  COALESCE(data -> 'Sample_ID', data -> 'Sample ID')
$._noun_type  →  COALESCE(data -> '_noun_type', data -> ' noun type', data -> ' noun_type',
                          data -> '_noun type', to_jsonb(<noun>))
```

- **The stored key wins, JSON null included.** `->` gives SQL NULL only for an absent key, which is
  setdefault's rule.
- **Copy sources come next, in first-wins order** (`gims_copy_sources`). Only a key made entirely of
  one separator kind can be a copy. Its sources share its length, so jsonb's order among them is plain
  byte order, known at compile time.
- **Only the first step folds.** GIMS copies top-level keys only; nested and index steps stay exact.
- **What cannot be folded is refused**, never guessed: a bare `$` (the whole served row has no static
  form), and a key with more than `FOLD_MAX_SEPARATORS` (6) separators, which would have up to
  2⁶ − 1 = 63 copy sources. The adapter evaluates those in Python and says why.
- **Without `fold`, nothing moves.** The default output was diffed byte for byte against the
  compiler before T-48 over 154 expressions (the parity vectors, this suite's, GIMS's 130 shared
  vectors), and the promotion test still pins the default against the frozen spike copy.
- **Proof.** `tests/test_folding.py` holds an oracle: 600 generated stored rows and expressions,
  where the expected answer is `expr.py` over the row normalised exactly as GIMS does it, with key
  order read back from Postgres. It was watched catching three wrong folds (reversed order, no tag,
  no copies). `parity/check_gims_pipeline.py --fold gims` re-measures every expression vector folded.
- **Cost note.** A folded key costs one `->` lookup per copy source, but only until the first one
  present (COALESCE stops there). T-44's inline coercion repeats a field's SQL up to three times per
  row, folded or not (asql-w1, 2026-10-01).
