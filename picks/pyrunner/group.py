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

from .. import paths
from . import evaluate as ev
from .order import MISSING, compare_jsonb
from .rows import SourceRow, read_rows

__all__ = ["answer", "python_pane", "columns_of", "profile", "python_profile"]

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


def _match_key(value: Any, match: str):
    """A match value, as this engine compares it (T-76) — ``None`` matches
    nothing.  Its own rule, written from the one stated in demo/group.py's
    docstring, not from its code:

    * a missing value or a JSON null matches nothing;
    * ``"string"``: a str, compared exactly (case and spaces count);
    * ``"number"``: an int or Decimal from the exact parse, compared by value
      — ``Decimal`` equality and hashing make 2 and 2.0 one key, and keep
      9007199254740993 apart from 9007199254740992 (no float anywhere);
    * anything of another kind matches nothing: a number never matches text,
      and ``True`` is not the number 1 (Python's ``True == 1`` is kept out by
      the tag and the explicit bool test); lists and objects never match.

    The tag keeps the kinds apart even in one dict."""
    if value is MISSING or value is None:
        return None
    if match == "string":
        return ("s", value) if isinstance(value, str) else None
    if match == "number":
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            return None
        return ("n", Decimal(value))
    raise ValueError(f"unknown match type {match!r}")


def _matches(rows: Sequence[SourceRow], related_rows: Sequence[SourceRow], rel: dict):
    """For each parent row, the related rows it matches — a join done by
    hand, through a dict, with no database lookup."""
    child_steps = ev.dollar_path(paths.dollar(rel["key"]))
    parent_steps = ev.dollar_path(paths.dollar(rel["parent_key"]))
    by_key: Dict[Any, List[SourceRow]] = {}
    for c in related_rows:
        k = _match_key(ev.resolve(c.record_d, child_steps), rel["match"])
        if k is not None:
            by_key.setdefault(k, []).append(c)

    def matched(parent: SourceRow) -> List[SourceRow]:
        k = _match_key(ev.resolve(parent.record_d, parent_steps), rel["match"])
        return by_key.get(k, []) if k is not None else []
    return matched


def _kept(rows: Sequence[SourceRow], spec: dict) -> List[SourceRow]:
    if spec.get("filter"):
        flt = ev.expr.parse(spec["filter"])
        return [r for r in rows if ev.keep_by_filter(r, flt)]
    return list(rows)


def profile(rows: Sequence[SourceRow], spec: dict,
            related_rows: Sequence[SourceRow]) -> Dict[str, Any]:
    """The match profile (T-76) — what the chosen match does over the KEPT
    parents, computed here from the rows: the columns demo/group.py's
    ``build_profile`` documents, in its order."""
    parents = _kept(rows, spec)
    matched = _matches(parents, related_rows, spec["related"])
    per_parent = [len(matched(p)) for p in parents]
    hits: Dict[str, int] = {c.key: 0 for c in related_rows}
    for p in parents:
        for c in matched(p):
            hits[c.key] += 1
    some = [n for n in per_parent if n > 0]
    per_counted = list(hits.values())
    twice = [n for n in per_counted if n > 1]
    return {
        "parents": len(parents),
        "parents_none": sum(1 for n in per_parent if n == 0),
        "least": min(some) if some else None,
        "most": max(some) if some else None,
        "counted": len(per_counted),
        "counted_none": sum(1 for n in per_counted if n == 0),
        "counted_twice": len(twice),
        "most_parents": max((n for n in per_counted if n > 0), default=None),
    }


def answer(rows: Sequence[SourceRow], spec: dict,
           related_rows: Sequence[SourceRow] = ()) -> Dict[str, Any]:
    """The scoreboard for *spec* over one collection's source rows.

    With ``spec["related"]`` (T-74), *rows* are the PARENTS — the page
    filter keeps parents, and the groups come from them — and everything
    counted is the parents' related rows, found here by the match
    (:func:`_match_key`, a dict from tagged match value to rows; no
    database lookup).  A parent with no
    related rows is still a group, holding none: Rows 0, every count 0,
    every % 0, latest and measure blank — a LEFT JOIN, done by hand."""
    rows = _kept(rows, spec)

    rel = spec.get("related")
    if rel:
        counted = _matches(rows, related_rows, rel)
    else:
        def counted(parent: SourceRow) -> List[SourceRow]:
            return [parent]

    steps = ev.dollar_path(paths.dollar(spec["group"]))
    counts = [ev.expr.parse(c["expr"]) for c in spec.get("counts") or []]
    time = spec.get("time")
    time_steps = ev.dollar_path(paths.dollar(time["field"])) if time else None
    measure = spec.get("measure")
    msr_steps = ev.dollar_path(paths.dollar(measure["field"])) if measure else None

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


def python_pane(conn, spec: dict, records=None) -> Dict[str, Any]:
    """Read the source rows and answer the scoreboard — end to end.  With a
    relation, both collections' source rows are read, and joined here."""
    rel = spec.get("related")
    related = read_rows(conn, rel["source"], records) if rel else ()
    return answer(read_rows(conn, spec["source"], records), spec, related)


def python_profile(conn, spec: dict, records=None) -> Dict[str, Any]:
    """Read both collections' source rows and profile the match — end to end."""
    rel = spec["related"]
    return profile(read_rows(conn, spec["source"], records), spec, read_rows(conn, rel["source"], records))
