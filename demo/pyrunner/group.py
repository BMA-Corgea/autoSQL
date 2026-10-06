"""group.py — shape E (GROUP), the second engine's own way (T-73).

The scoreboard computed from the source rows in Python, from scratch: never
handed the statement, never handed its result.  Like the rest of this
package it imports nothing from ``demo/builder.py``, ``demo/group.py`` or
``demo/probes.py`` and does not touch the database driver; the rows arrive
through ``read_rows`` and every rule below is this package's own.

What it computes, per the spec ``demo/group.py`` documents:

* the rows kept by the filter — GIMS's evaluator, its truthiness, on the
  float parse, exactly as ``keep_by_filter`` keeps rows today;
* one group per value of the group field — an absent key and a JSON null
  are the same, blank, group (``->>``'s reading); values are the exact
  parse, so ``1`` and ``1.0`` are one group, as they are in jsonb;
* ``rows`` — how many kept rows the group holds;
* each count-if — how many of them the condition holds for, by the same
  truthiness; and its % of rows, 100·k/n rounded half-up to one place
  (Postgres rounds numeric half away from zero; every value here is ≥ 0);
* latest / earliest — the largest / smallest TEXT of the field, by code
  point (the database's C collation compares UTF-8 bytes, the same order);
* the measure — ``evaluate.aggregate``, the exact-decimal rule shape C uses;
* the order — the chosen column with blanks last, then the group value
  ascending (jsonb's own ordering, ``order.compare_jsonb``), blanks last.
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_UP
from functools import cmp_to_key
from typing import Any, Dict, List, Sequence

from . import evaluate as ev
from .order import MISSING, compare_jsonb
from .rows import SourceRow, read_rows

__all__ = ["answer", "python_pane", "columns_of"]

_PCT_CONTEXT = Context(prec=60, rounding=ROUND_HALF_UP)
_ONE_PLACE = Decimal("0.1")


def columns_of(spec: dict) -> List[str]:
    """The column names, in order — written here independently of
    demo/group.py's list; a test holds the two equal."""
    out = ["grp", "rows"]
    for i, c in enumerate(spec.get("counts") or [], start=1):
        out.append(f"c{i}")
        if c.get("pct"):
            out.append(f"c{i}_pct")
    if spec.get("time"):
        out.append("time")
    if spec.get("measure"):
        out.append("measure")
    return out


def _group_key(value: Any):
    """A hashable stand-in for one group value, equal exactly when jsonb
    would call the two values equal (numbers by value, text by content)."""
    if value is MISSING or value is None:
        return ("blank",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, Decimal)):
        return ("num", Decimal(value))
    if isinstance(value, str):
        return ("str", value)
    raise TypeError(f"cannot group by a {type(value).__name__} value")


def _pct(k: int, n: int) -> Decimal:
    if n == 0:
        return Decimal(0).quantize(_ONE_PLACE)
    return (_PCT_CONTEXT.divide(Decimal(100 * k), Decimal(n))
            .quantize(_ONE_PLACE, rounding=ROUND_HALF_UP))


def _text(value: Any):
    if value is MISSING or value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("latest / earliest read a time or date field, which is text")


def _order(rows: List[dict], spec: dict) -> List[dict]:
    s = spec.get("sort") or {"column": "grp", "dir": "asc"}
    column, desc = s["column"], s["dir"] == "desc"

    def compare_values(a, b, *, descending: bool) -> int:
        # blanks last whichever way the column runs
        if a is None and b is None:
            return 0
        if a is None:
            return 1
        if b is None:
            return -1
        if isinstance(a, str) and isinstance(b, str):
            ka, kb = a.encode("utf-8"), b.encode("utf-8")
            c = (ka > kb) - (ka < kb)
        elif column == "grp":
            c = compare_jsonb(a, b)
        else:
            c = (a > b) - (a < b)
        return -c if descending else c

    def compare(x, y) -> int:
        c = compare_values(x[column], y[column], descending=desc)
        if c or column == "grp":
            return c
        return compare_values(x["grp"], y["grp"], descending=False)

    return sorted(rows, key=cmp_to_key(compare))


def _join_key(value: Any, side: str):
    """A relation key, as the join compares it: text.  A missing key or a
    JSON null joins to nothing (SQL: NULL never equals).  Any other value
    is refused loudly — the statement compares keys as text, and a number
    quietly turned into text here could join differently there."""
    if value is MISSING or value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError(f"the {side} key holds a {type(value).__name__}, not text")


def answer(rows: Sequence[SourceRow], spec: dict,
           related_rows: Sequence[SourceRow] = ()) -> Dict[str, Any]:
    """The scoreboard for *spec* over one collection's source rows.

    With ``spec["related"]`` (T-74), *rows* are the PARENTS — the page
    filter keeps parents, and the groups come from them — and everything
    counted is the parents' related rows, found here by the declared keys
    (a dict from key text to rows; no database lookup).  A parent with no
    related rows is still a group, holding none: Rows 0, every count 0,
    every % 0, latest and measure blank — a LEFT JOIN, done by hand."""
    if spec.get("filter"):
        flt = ev.expr.parse(spec["filter"])
        rows = [r for r in rows if ev.keep_by_filter(r, flt)]

    rel = spec.get("related")
    if rel:
        child_steps = ev.dollar_path("$." + rel["key"])
        parent_steps = ev.dollar_path("$." + rel["parent_key"])
        by_key: Dict[str, List[SourceRow]] = {}
        for c in related_rows:
            k = _join_key(ev.resolve(c.record_d, child_steps), "related rows'")
            if k is not None:
                by_key.setdefault(k, []).append(c)

        def counted(parent: SourceRow) -> List[SourceRow]:
            k = _join_key(ev.resolve(parent.record_d, parent_steps), "parent's")
            return by_key.get(k, []) if k is not None else []
    else:
        def counted(parent: SourceRow) -> List[SourceRow]:
            return [parent]

    steps = ev.dollar_path("$." + spec["group"])
    counts = [ev.expr.parse(c["expr"]) for c in spec.get("counts") or []]
    time = spec.get("time")
    time_steps = ev.dollar_path("$." + time["field"]) if time else None
    measure = spec.get("measure")
    msr_steps = ev.dollar_path("$." + measure["field"]) if measure else None

    groups: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        value = ev.resolve(r.record_d, steps)
        g = groups.setdefault(_group_key(value), {
            "value": None if value is MISSING else value,
            "rows": [],
        })
        g["rows"].extend(counted(r))

    out = []
    for g in groups.values():
        members = g["rows"]
        n = len(members)
        row: Dict[str, Any] = {"grp": g["value"], "rows": n}
        for i, ast in enumerate(counts, start=1):
            k = sum(1 for r in members
                    if ev.expr.truthy(ev.expr.evaluate(ast, r.record_f, {})))
            row[f"c{i}"] = k
            if (spec["counts"][i - 1]).get("pct"):
                row[f"c{i}_pct"] = _pct(k, n)
        if time:
            texts = [t for t in (_text(ev.resolve(r.record_d, time_steps)) for r in members)
                     if t is not None]
            if not texts:
                row["time"] = None
            else:
                pick = max if time["fn"] == "max" else min
                row["time"] = pick(texts, key=lambda t: t.encode("utf-8"))
        if measure:
            values = [ev.numeric_value(r.record_d, msr_steps) for r in members]
            row["measure"] = ev.aggregate(measure["fn"], values, n)
        out.append(row)

    out = _order(out, spec)
    if spec.get("cap") is not None:
        out = out[:spec["cap"]]
    return {
        "shape": "GROUP",
        "columns": columns_of(spec),
        "rows": out,
        "row_count": len(out),
    }


def python_pane(conn, spec: dict) -> Dict[str, Any]:
    """Read the source rows and answer the scoreboard — end to end.  With a
    relation, both collections' source rows are read, and joined here."""
    rel = spec.get("related")
    related = read_rows(conn, rel["source"]) if rel else ()
    return answer(read_rows(conn, spec["source"]), spec, related)
