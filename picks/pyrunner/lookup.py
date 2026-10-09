"""lookup.py — shape F (MATCHED), the second engine's own way (T-78).

A plain table with another data set's fields beside each row, computed from
the source rows in Python, from scratch: never handed the statement, never
handed its result.  Like the rest of this package it imports nothing from
``demo/builder.py``, ``demo/group.py`` or ``demo/lookup.py`` and does not
touch the database driver; the rows arrive through ``read_rows``.

* The table is this package's own (``shape.answer``): its filter, computed
  columns, sort and order — computed WITHOUT the cap, which is applied last,
  after the join, as a LIMIT is.
* The join is a dict from match value to the other data set's rows
  (``group._match_key``: this package's one statement of T-76's rule — text
  exactly, numbers by value, never across kinds, a blank matches nothing).
* A row with no match keeps its place, its matched fields blank; a row with
  several matches would be repeated, once per match in key order — which the
  profile refuses before any table is drawn.
* A matched field is read as a computed column is (``$.path`` on the
  matched row's float parse, the evaluator GIMS uses).
* The profile: the columns ``demo/lookup.py :: build_profile`` documents,
  over the KEPT rows (the filter applies; the cap does not).
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from . import evaluate as ev
from . import shape
from .group import _match_key
from .rows import SourceRow, read_rows

__all__ = ["answer", "profile", "python_pane", "python_profile"]


def _matcher(related_rows: Sequence[SourceRow], lk: dict):
    """The other data set's rows by match value; and, for a row of the
    table, the rows it matches, in key order."""
    child = ev.dollar_path("$." + lk["key"])
    parent = ev.dollar_path("$." + lk["parent_key"])
    by_value: Dict[Any, List[SourceRow]] = {}
    for c in sorted(related_rows, key=lambda r: r.key.encode("utf-8")):
        k = _match_key(ev.resolve(c.record_d, child), lk["match"])
        if k is not None:
            by_value.setdefault(k, []).append(c)

    def matched(record_d) -> List[SourceRow]:
        k = _match_key(ev.resolve(record_d, parent), lk["match"])
        return by_value.get(k, []) if k is not None else []
    return matched


def _kept(rows: Sequence[SourceRow], pick: dict) -> List[SourceRow]:
    if pick.get("filter"):
        flt = ev.expr.parse(pick["filter"])
        return [r for r in rows if ev.keep_by_filter(r, flt)]
    return list(rows)


def profile(rows: Sequence[SourceRow], pick: dict, related_rows: Sequence[SourceRow],
            lk: dict) -> Dict[str, Any]:
    """What the match does over the kept rows, from the rows."""
    matched = _matcher(related_rows, lk)
    per_row = [len(matched(r.record_d)) for r in _kept(rows, pick)]
    some = [n for n in per_row if n > 0]
    return {
        "rows": len(per_row),
        "rows_none": sum(1 for n in per_row if n == 0),
        "least": min(some) if some else None,
        "most": max(some) if some else None,
        "repeated": sum(1 for n in per_row if n > 1),
        "others": len(related_rows),
    }


def answer(rows: Sequence[SourceRow], pick: dict, related_rows: Sequence[SourceRow],
           lk: dict, records=None) -> Dict[str, Any]:
    """The matched table for *pick* over the table's source rows."""
    base = shape.answer(rows, dict(pick, cap=None), records)
    by_key = {r.key: r for r in rows}
    matched = _matcher(related_rows, lk)
    parsed = ev.parse_computed([{"name": c["name"], "expr": "$." + c["path"]}
                                for c in lk["columns"]])
    blank = {name: None for name, _ in parsed}
    out: List[Dict[str, Any]] = []
    for row in base["rows"]:
        hits = matched(by_key[row["key"]].record_d)
        for m in hits or [None]:
            cell = dict(row)
            cell.update(blank if m is None else ev.computed_values(m, parsed))
            out.append(cell)
    if pick.get("cap") is not None:
        out = out[:pick["cap"]]
    return {
        "shape": "MATCHED",
        "columns": list(base["columns"]) + [name for name, _ in parsed],
        "rows": out,
        "row_count": len(out),
    }


def python_pane(conn, pick: dict, lk: dict, records=None) -> Dict[str, Any]:
    """Read both data sets' source rows and answer — end to end."""
    extra = {"records": records} if records is not None else {}
    return answer(read_rows(conn, pick["source"], records), pick, read_rows(conn, lk["source"], records), lk, **extra)


def python_profile(conn, pick: dict, lk: dict, records=None) -> Dict[str, Any]:
    return profile(read_rows(conn, pick["source"], records), pick, read_rows(conn, lk["source"], records), lk)
