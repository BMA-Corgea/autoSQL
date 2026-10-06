"""demo/server/scoreboard.py — one scoreboard, both engines, compared in full (T-73).

``run_group`` is to shape E what ``app.run_pick`` is to the four shapes of
the nine-operation pick, and it is built from run_pick's own parts:

1. **gate + build** — ``demo/group.py`` parses, gates and compiles every
   expression the spec carries (the filter and each count-if) before any
   SQL exists; a refusal there is layer 1, named.
2. **probe** — ``probes.check`` asks the data its two questions over the
   same expressions (a container compared with ``==``, a number past the
   largest double) before the statement runs; a firing is layer 2, named,
   and no number is shown.
3. **both engines** — the statement on one side (``app.sql_pane``), the
   second engine's own computation on the other
   (``demo/pyrunner/group.py``), neither handed the other's answer.
4. **compare in full** — ``app.compare_panes``: every row, every cell, no
   tolerance, the same comparison every other answer in the demo gets.
"""

from __future__ import annotations

from . import app as server_app
from . import errors

import gate  # noqa: E402  (app.py bootstraps demo/ onto sys.path)
import group  # noqa: E402
import probes  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402

__all__ = ["run_group"]


def _refused(payload: dict, spec: dict, *, built=None, display=None) -> dict:
    return {
        "accepted": False,
        "shape": group.GROUP,
        "verdict": server_app.NO_COMPARE,
        "comparison": {},
        "panes": {},
        "sql": {
            "parameterised": built.sql if built else None,
            "display": display,
            "params": server_app._param_rows(built.params) if built else [],
            "statement_sent": False,
        },
        "spec": spec,
        "refusal": payload,
    }


def run_group(conn, spec: dict, *, whole: bool = True) -> dict:
    """One scoreboard spec → the whole answer, both engines, compared."""
    try:
        built = group.build(spec)
    except gate.Refused as exc:
        return _refused(errors.layer_1(exc, kind="expression"), spec)
    display = server_app.render_display_sql(built)

    counted = [server_app.expr.parse(c["expr"]) for c in spec.get("counts") or []]
    roots = []
    if spec.get("measure"):
        roots.append(server_app.expr.parse("$." + spec["measure"]["field"]))
    page = [server_app.expr.parse(spec["filter"])] if spec.get("filter") else []
    rel = spec.get("related")
    try:
        if rel:
            # T-74: what is counted is the related rows, so their
            # expressions are probed over THAT collection; the page filter
            # reads the parents and is probed over them.
            outcomes = probes.check(conn, rel["source"], counted, numeric_roots=roots)
            if page:
                outcomes = outcomes + probes.check(conn, spec["source"], page)
        else:
            outcomes = probes.check(conn, spec["source"], counted + page, numeric_roots=roots)
    except probes.RuntimeRefusal as exc:
        return _refused(errors.layer_2(exc), spec, built=built, display=display)

    sql = server_app.sql_pane(conn, built)
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    answer = pygroup.python_pane(conn, spec)
    columns = list(answer["columns"])
    kinds = [kinds_by_column.get(c, "json") for c in columns]
    python = {
        "columns": columns,
        "kinds": kinds,
        "rows": answer["rows"],
        "row_count": answer["row_count"],
        "canon": server_app._canon_rows(answer["rows"], columns, kinds),
    }
    comparison = server_app.compare_panes(sql, python)
    per_row = comparison.pop("_per_row")
    size = len(sql["canon"]) if whole else None
    return {
        "accepted": True,
        "shape": group.GROUP,
        "verdict": comparison["verdict"],
        "comparison": comparison,
        "panes": {
            "sql": server_app._rendered_pane(sql, per_row, 0, "answered",
                                             server_app._SQL_NOTE, size=size),
            "python": server_app._rendered_pane(python, per_row, 0, "answered",
                                                server_app._PY_NOTE, size=size),
        },
        "sql": server_app._sql_block(parameterised=built.sql, display=display,
                                     params=built.params, outcomes=outcomes,
                                     sent=True, collection=spec["source"]),
        "spec": spec,
        "refusal": None,
    }
