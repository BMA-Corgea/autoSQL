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
