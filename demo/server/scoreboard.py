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

With a related data set (T-76: any match a person picks), one step comes
between 2 and 3: **the match profile**, in both engines and compared the same
way — what the match does over the kept parents.  It is the preview's
numbers, and the double-count check: if any counted row matches more than
one kept parent, the pick is refused and no board statement runs.  If the
two engines disagree on the profile, the pick is refused too: a match that
could not be double-checked is not counted (fail closed).
"""

from __future__ import annotations

from . import app as server_app
from . import errors

import gate  # noqa: E402  (app.py bootstraps demo/ onto sys.path)
import group  # noqa: E402
from picks import paths  # noqa: E402
import probes  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402

__all__ = ["run_group"]


def _refused(payload: dict, spec: dict, *, built=None, display=None,
             sent: bool = False, match=None) -> dict:
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
            "statement_sent": sent,
        },
        "spec": spec,
        "refusal": payload,
        "match": match,
    }


def _profile(conn, spec: dict) -> dict:
    """The match profile, from both engines, compared in full."""
    built = group.build_profile(spec)
    sql = server_app.sql_pane(conn, built)
    columns = list(group.PROFILE_COLUMNS)
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    kinds = [kinds_by_column.get(c, "json") for c in columns]
    out = {"profile": dict(sql["rows"][0]) if sql["rows"] else None, "built": built,
           "display": server_app.render_display_sql(built), "python_error": None}
    try:
        row = pygroup.python_profile(conn, spec)
    except Exception as exc:  # noqa: BLE001 — any failure is "not double-checked"
        # The second engine couldn't profile the match: the same answer as a
        # disagreement — nothing is counted (fail closed), never a 500.
        return dict(out, verdict="disagree", python=None,
                    python_error=f"{type(exc).__name__}: {exc}")
    python = {"columns": columns, "kinds": kinds, "rows": [row], "row_count": 1,
              "canon": server_app._canon_rows([row], columns, kinds)}
    comparison = server_app.compare_panes(sql, python)
    comparison.pop("_per_row", None)
    return dict(out, verdict=comparison["verdict"], python=row)


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
        roots.append(server_app.expr.parse(paths.dollar(spec["measure"]["field"])))
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

    match = None
    if rel:
        prof = _profile(conn, spec)
        match = {"verdict": prof["verdict"], "profile": prof["profile"], "python": prof["python"],
                 "python_error": prof["python_error"], "statement": prof["display"]}
        if prof["verdict"] != "agree":
            return _refused({"kind": "match-disagree",
                             "headline": "The two engines disagree on what the match does",
                             "why": "The statement and the second engine profiled the match "
                                    "differently, so nothing is counted."},
                            spec, built=prof["built"], display=prof["display"], sent=True, match=match)
        if prof["profile"]["counted_twice"] > 0:
            return _refused({"kind": "double-count",
                             "headline": "A row would be counted more than once",
                             "why": f"{prof['profile']['counted_twice']} counted rows match more than "
                                    "one kept parent."},
                            spec, built=prof["built"], display=prof["display"], sent=True, match=match)

    sql = server_app.sql_pane(conn, built)
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    try:
        answer = pygroup.python_pane(conn, spec)
    except OverflowError:
        raise        # a number past a double: dashboard._run_group names it (T-75)
    except Exception as exc:  # noqa: BLE001 — any other failure is "not double-checked"
        # The second engine couldn't compute the board: nothing is shown,
        # as for a match it couldn't profile (fail closed) — never a 500
        # with no words (T-79; the S16 re-check's last LATER item).
        return _refused({"kind": "board-unchecked",
                         "headline": "The second engine could not finish",
                         "why": f"{type(exc).__name__}: {exc}"},
                        spec, built=built, display=display, sent=True, match=match)
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
        "match": match,
    }
