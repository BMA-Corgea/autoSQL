"""demo/server/matched.py — a matched table, both engines, compared in full (T-78).

``run_lookup`` is to shape F what ``scoreboard.run_group`` is to shape E, and
it is built from ``app.run_pick``'s own parts:

1. **gate + build** — the pick's spelling (``normalised_pick``), the alias
   gate and every compiled expression, through ``demo/lookup.py`` (built on
   builder.py's pieces); a refusal there is layer 1, named.
2. **probe** — ``probes.check`` asks the table's data its two questions
   over the table's own expressions (its columns and conditions), as
   ``run_pick`` does.  A matched field is a plain read: nothing to probe.
3. **the match profile, in both engines, compared** — what the match does
   over the KEPT rows (Show and paging don't apply).  Disagree, or the
   second engine can't profile it: refused, nothing shown (fail closed).
   Any kept row matching more than one row: refused — a row would repeat —
   and no table statement runs.
4. **both engines** — the statement, and the second engine's own table and
   join (``demo/pyrunner/lookup.py``), neither handed the other's answer; a
   second-engine failure is refused in words, never a 500 (T-79).
5. **compare in full** — ``app.compare_panes``: every row, every cell.
"""

from __future__ import annotations

from . import app as server_app
from . import errors

import builder  # noqa: E402  (app.py bootstraps demo/ onto sys.path)
import gate  # noqa: E402
import legality  # noqa: E402
import lookup  # noqa: E402
import probes  # noqa: E402
from pyrunner import lookup as pylookup  # noqa: E402

__all__ = ["run_lookup"]


def _refused(payload: dict, pick: dict, lk: dict, *, built=None, display=None,
             sent: bool = False, match=None) -> dict:
    return {
        "accepted": False,
        "shape": lookup.MATCHED,
        "verdict": server_app.NO_COMPARE,
        "comparison": {},
        "panes": {},
        "sql": {
            "parameterised": built.sql if built else None,
            "display": display,
            "params": server_app._param_rows(built.params) if built else [],
            "statement_sent": sent,
        },
        "pick": pick,
        "lookup": lk,
        "refusal": payload,
        "match": match,
    }


def _profile(conn, pick: dict, lk: dict) -> dict:
    """The match profile, from both engines, compared in full."""
    built = lookup.build_profile(pick, lk)
    sql = server_app.sql_pane(conn, built)
    columns = list(lookup.PROFILE_COLUMNS)
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    kinds = [kinds_by_column.get(c, "json") for c in columns]
    out = {"profile": dict(sql["rows"][0]) if sql["rows"] else None, "built": built,
           "display": server_app.render_display_sql(built), "python_error": None}
    try:
        row = pylookup.python_profile(conn, pick, lk)
    except Exception as exc:  # noqa: BLE001 — any failure is "not double-checked"
        return dict(out, verdict="disagree", python=None,
                    python_error=f"{type(exc).__name__}: {exc}")
    python = {"columns": columns, "kinds": kinds, "rows": [row], "row_count": 1,
              "canon": server_app._canon_rows([row], columns, kinds)}
    comparison = server_app.compare_panes(sql, python)
    comparison.pop("_per_row", None)
    return dict(out, verdict=comparison["verdict"], python=row)


def run_lookup(conn, pick: dict, lk: dict) -> dict:
    """One plain-table pick + one match → the whole answer, both engines."""
    try:
        pick = server_app.normalised_pick(pick)
    except gate.Refused as exc:
        return _refused(errors.layer_1(exc, kind="field"), pick, lk)
    source = legality.evaluate(pick)["source"]
    keys = server_app.collection_keys(conn, source)
    try:
        built = lookup.build(pick, keys, lk)
    except gate.Refused as exc:
        return _refused(errors.layer_1(exc, kind="expression"), pick, lk)
    except builder.IllegalPick as exc:
        return _refused(errors.illegal_pick(exc.violations), pick, lk)
    display = server_app.render_display_sql(built)

    exprs = [server_app.expr.parse(cc["expr"]) for cc in pick.get("computed") or []]
    if pick.get("filter"):
        exprs.append(server_app.expr.parse(pick["filter"]))
    try:
        outcomes = probes.check(conn, source, exprs)
    except probes.RuntimeRefusal as exc:
        return _refused(errors.layer_2(exc), pick, lk, built=built, display=display)

    prof = _profile(conn, pick, lk)
    match = {"verdict": prof["verdict"], "profile": prof["profile"], "python": prof["python"],
             "python_error": prof["python_error"], "statement": prof["display"]}
    if prof["verdict"] != "agree":
        return _refused({"kind": "match-disagree",
                         "headline": "The two engines disagree on what the match does",
                         "why": "The statement and the second engine profiled the match "
                                "differently, so nothing is shown."},
                        pick, lk, built=prof["built"], display=prof["display"], sent=True, match=match)
    if prof["profile"]["repeated"] > 0:
        return _refused({"kind": "repeat",
                         "headline": "A row would be shown more than once",
                         "why": f"{prof['profile']['repeated']} kept rows match more than one row."},
                        pick, lk, built=prof["built"], display=prof["display"], sent=True, match=match)

    sql = server_app.sql_pane(conn, built)
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    try:
        answer = pylookup.python_pane(conn, pick, lk)
    except OverflowError:
        raise        # a number past a double: the dashboard names it (T-75)
    except Exception as exc:  # noqa: BLE001 — "not double-checked", never a 500
        return _refused({"kind": "answer-unchecked",
                         "headline": "The second engine could not finish",
                         "why": f"{type(exc).__name__}: {exc}"},
                        pick, lk, built=built, display=display, sent=True, match=match)
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
    size = len(sql["canon"])
    return {
        "accepted": True,
        "shape": lookup.MATCHED,
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
                                     sent=True, collection=source),
        "pick": pick,
        "lookup": lk,
        "refusal": None,
        "match": match,
    }
