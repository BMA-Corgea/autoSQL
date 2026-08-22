"""rows.py — how rows reach the Python pane: JSON text, parsed twice (B7).

THE RULING (plan B7): **the Python pane never sees a float where a number
matters.** ``Decimal(0.1)`` carries the binary value
0.1000000000000000055511151231257827021181583404541015625; ``Decimal(str)``
carries the decimal text.  So this module selects ``data::text`` alongside
``collection`` and ``key``, and for each row produces TWO parses of the same
string:

  ``record_f``  ``json.loads(raw)`` — ordinary floats.  Consumed by the
                vendored ``expr.py`` evaluator ONLY (operations 2 and 3).
                It must see exactly what GIMS's evaluator would see; §7.2
                keeps the compiler's expressions in ``float8`` for the same
                reason, and §5's defect has to stay visible.

  ``record_d``  ``json.loads(raw, parse_float=decimal.Decimal)`` — exact.
                Consumed by the numeric read for operations 6, 7 and 8,
                AND by operation 9's comparison (B7 rules the comparison
                onto the exact parse too: jsonb stores numbers as
                ``numeric``, exactly, so a lossy parse there is a
                divergence waiting for a different seed).

Where the input comes from matters more than anything else (spec §9.5): the
Python pane reads the SOURCE rows — the whole collection, before any filter,
sort, cap, aggregate, bucket or window — out of the same database, and then
applies the pick itself, in Python, from scratch.  It must not be handed the
SQL query's result (it would be checking the SQL against itself), and it
must not rebuild the data from the seed script's memory (the two panes would
describe different worlds).  Reading a whole collection is affordable
because Q21 kept the data small (10,410 rows).

Independence (W12's whole point): this module imports nothing from
``demo/builder.py`` or ``demo/probes.py``, and does NOT import the database
driver — plan §4.5 pins the connection factory as the only driver importer,
so the connection is an argument here.  ``demo/tests/test_pyrunner.py``
holds the package to both, structurally.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, List, NamedTuple

__all__ = ["SourceRow", "source_row", "read_rows"]


class SourceRow(NamedTuple):
    """One source row, with B7's two parses of the one ``data::text``."""

    collection: str
    key: str
    raw: str          # data::text, exactly as jsonb rendered it
    record_f: Any     # json.loads(raw) — the float world, for expr.py only
    record_d: Any     # json.loads(raw, parse_float=Decimal) — exact


def source_row(collection: str, key: str, raw: str) -> SourceRow:
    """Build one SourceRow from JSON text — THE double parse, in one place.

    Tests build synthetic rows through this same function so the
    text-parsed-twice contract (B7) holds for them too; a test that handed
    the runner a Python dict would be exercising a path production never
    takes.

    Note on huge numbers: jsonb renders its numerics in full digits, so
    edge-03's ``1e400`` arrives here as a 401-digit literal.  ``record_f``
    parses that to ``float('inf')`` (CPython's json returns inf rather than
    raising) — which is exactly what AC-17 requires the Python pane to end
    up showing as literal text — while ``record_d`` holds it exactly.
    """
    return SourceRow(
        collection=collection,
        key=key,
        raw=raw,
        record_f=json.loads(raw),
        record_d=json.loads(raw, parse_float=Decimal),
    )


def read_rows(conn, collection: str) -> List[SourceRow]:
    """Read one collection's source rows out of the demo database.

    ``conn`` is a connection from the demo's one connection factory
    (``demo/server/db.py :: connect()`` once W13 lands; until then
    ``demo/seed/load.py :: demo_connection()`` routes there) — this module
    never dials anything itself and never imports the driver.

    The statement carries no ORDER BY on purpose: arrival order must not
    matter, because every order the pane displays or compares is produced
    by the pipeline's own sorts (§7.4 via ``order.sort_key``, §7.1's frame
    order in ``evaluate``).  An implementation that leaned on arrival order
    would be borrowing an order from the SQL engine — the exact dependence
    this second calculator exists to not have — and AC-41(b)'s repeat-runs
    are the check that nothing does.
    """
    cur = conn.execute(
        "SELECT collection, key, data::text FROM demo.records"
        " WHERE collection = %(collection)s",
        {"collection": collection},
    )
    return [source_row(c, k, raw) for (c, k, raw) in cur.fetchall()]
