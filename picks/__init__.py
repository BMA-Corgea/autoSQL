"""picks — autoSQL's pick engine (T-86).

A person picks parts of a table of JSON records (a data set, columns,
conditions, a sort, a summary, a board, a match) and the engine writes the
statement for those picks — parameterised Postgres through the expression
compiler — and works the same answer out again, independently, in Python.

* ``records``  — the records description: the table, an owner's partition,
                 the closed set of collections, the time series, a fold.
* ``env``      — what the host supplies once: the compiler, the expression
                 parser and evaluator, the probes' compiler; a default
                 records description for a single-owner host.
* ``legality`` — which combinations of picks are legal, and why not.
* ``gate``     — the allowlist every expression passes before it compiles.
* ``builder``  — one pick → one statement (rows, one number, per time).
* ``group``    — a scoreboard: one row per value, "count if" columns.
* ``lookup``   — a table with another data set's fields beside each row.
* ``probes``   — the data questions asked before a statement runs.
* ``pyrunner`` — the second engine: the same answers from the rows.

The demo (``demo/``) is the first host.  Nothing here knows its data.
"""
