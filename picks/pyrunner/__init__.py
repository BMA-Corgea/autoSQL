"""demo.pyrunner — the second, independent calculator (T-2 spec §9.5, Q24).

W9's pair: ``decimals.py`` (the exact-decimal rule) and ``order.py``
(§7.4's comparator).  W12's trio: ``rows.py`` (B7's double parse),
``evaluate.py`` (the row-level runner — filter, windows, changed-rows,
aggregate, bucket) and ``shape.py`` (§4.1's pipeline order, B5a's three
answer shapes; ``shape.python_pane(conn, pick)`` is the pane end to end).

Independence is the point: nothing in this package imports from
``demo/builder.py`` or ``demo/probes.py``, or reuses their intermediate
results — when this calculator and the SQL disagree, the disagreement
means something.  ``demo/tests/test_pyrunner.py`` enforces that
structurally.
"""
