"""shape.py — one pick, applied §4.1's way, shaped B5a's way.

The Python pane's front door.  ``answer(rows, pick)`` applies the pick to
the source rows in EXACTLY the pipeline order plan §4.1 pins — a pane that
reorders any two steps produces a different number while looking entirely
correct — and returns the pick's whole answer in its one B5a shape:

  ROWS    {"shape": "ROWS",   "columns": [...], "rows": [...], "row_count": n}
  SCALAR  {"shape": "SCALAR", "columns": ["agg"], "rows": [{"agg": v}],
           "row_count": 1, "agg": v}
  BUCKET  {"shape": "BUCKET", "columns": ["bucket", "agg"], "rows":
           [{"bucket": label, "agg": v}, ...], "row_count": n}

The order, and the two instincts it corrects (§4.1):

  1 source            (the caller read one collection — rows.read_rows)
  2 computed columns  emitted on ROWS; defined-not-emitted on SCALAR/BUCKET
  3 filter            BEFORE the windows: the frame sees only survivors —
                      the only order SQL permits (B3 detail 4)
  4 windows (8, 9)    over the filtered rows, in the frame's order
  5 keep changed (9)  drop rows whose compared value equals the predecessor's
  6 aggregate/bucket  accumulate in Decimal, then round
  7 sort              §7.4's comparator — every result, sorted or not
  8 cap               LAST: it caps kept rows, after windows and the
                      changed filter, never scanned rows

Row cells carry the values the pipeline computed: ``data`` is the exact
parse (B7), ``rolling_avg`` a 6-place Decimal (or None), computed columns
whatever expr.py's float world returned.  Rendering them is the display
layer's job; comparing them against the SQL pane is the server's (B25 — in
full, on the server).

The whole answer is a pure function of (source rows, pick).  There is no
parameter through which a SQL result could arrive, which is AC-23(b)'s
independence stated as an interface: perturb the SQL side however you like
— this pane cannot follow, because it cannot see.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import evaluate as ev
from .rows import SourceRow, read_rows

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import demo.legality as legality  # noqa: E402  (path bootstrap above)

__all__ = ["answer", "python_pane"]

#: The four column names the builder emits, fixed at §7.3 — both panes key
#: their output by these same names, so neither may rename one.
AGG, BUCKET_COL, ROLLING_AVG = "agg", "bucket", "rolling_avg"
# ("changed" is the fourth; it is computed and filtered on, never emitted —
# B3 detail 3.)


def answer(rows: Sequence[SourceRow], pick: dict) -> Dict[str, Any]:
    """Apply *pick* to *rows* (one collection's source rows), §4.1's way."""
    # The legality matrix is consulted, not re-implemented (§4.5: one
    # function, so nothing can disagree with it).  The pick handler refuses
    # illegal picks before either pane runs; a violation reaching this far
    # is a caller bug, and B4's silent degradations (PARTITION BY NULL, the
    # one-bucket bucket) must never produce a number, so: loud.
    verdict = legality.evaluate(pick)
    if verdict["violations"]:
        why = "; ".join(v["why"] for v in verdict["violations"])
        raise ValueError(f"illegal pick reached the Python pane: {why}")
    shape = verdict["shape"]

    # step 2 (parse once) — evaluation happens per shape below
    parsed = ev.parse_computed(pick.get("computed") or [])

    # step 3 — filter, before anything windowed (B3 detail 4)
    if pick.get("filter"):
        filter_ast = ev.expr.parse(pick["filter"])
        rows = [r for r in rows if ev.keep_by_filter(r, filter_ast)]

    if shape == "SCALAR":
        return _scalar(rows, pick, parsed)
    if shape == "BUCKET":
        return _bucket(rows, pick, parsed)
    return _rows(rows, pick, parsed)


def python_pane(conn, pick: dict) -> Dict[str, Any]:
    """Read the pick's source rows and answer it — the pane, end to end.

    The rows come out of the same database the SQL pane reads (spec §9.5:
    not the SQL query's result, not the seed script's memory), and the
    pick is applied from scratch by ``answer``.
    """
    return answer(read_rows(conn, pick["source"]), pick)


# ── ROWS (shapes A and B) ───────────────────────────────────────────────

def _rows(
    rows: Sequence[SourceRow], pick: dict, parsed: Sequence[tuple]
) -> Dict[str, Any]:
    windowed = bool(pick.get("window") and pick["window"].get("field"))
    changed_on = bool(pick.get("changed"))

    # step 2 — computed columns, emitted (ROWS is the one shape that shows
    # them, B5a); the float world, expr.py only (B7)
    cells = [ev.computed_values(r, parsed) for r in rows]

    # step 4 — the shared frame, over the filtered rows only
    rolling: Dict[int, Any] = {}
    kept_flags: Optional[Dict[int, bool]] = None
    if windowed or changed_on:
        partitions = ev.partition_walk(rows)
        if windowed:
            read = ev.field_reader(pick["window"]["field"], parsed)
            rolling = ev.rolling_averages(rows, partitions, read)
        if changed_on:
            kept_flags = ev.changed_flags(rows, partitions)

    # step 5 — keep only changed (op 9): WHERE "changed" in the outer query
    indices = [
        i for i in range(len(rows)) if kept_flags is None or kept_flags[i]
    ]

    # step 7 — sort: §7.4, every result, sorted or not
    sort = pick.get("sort") or None
    sort_steps = None
    sort_alias = None
    direction = "asc"
    if sort and sort.get("field"):
        direction = sort.get("dir") or "asc"
        field = sort["field"]
        if any(name == field for name, _ in parsed):
            sort_alias = field
        else:
            sort_steps = ev.dollar_path(field)
    indices.sort(
        key=lambda i: ev.row_sort_key(
            rows[i], sort_steps, cells[i], sort_alias, direction
        )
    )

    # step 8 — cap, LAST
    cap = pick.get("cap")
    if cap is not None:
        indices = indices[:cap]

    columns = ["collection", "key", "data"] + [name for name, _ in parsed]
    if windowed:
        columns.append(ROLLING_AVG)
    out_rows: List[Dict[str, Any]] = []
    for i in indices:
        r = rows[i]
        cell: Dict[str, Any] = {
            "collection": r.collection,
            "key": r.key,
            "data": r.record_d,
        }
        cell.update(cells[i])
        if windowed:
            cell[ROLLING_AVG] = rolling[i]
        out_rows.append(cell)
    return {
        "shape": "ROWS",
        "columns": columns,
        "rows": out_rows,
        "row_count": len(out_rows),
    }


# ── SCALAR (shape C) ────────────────────────────────────────────────────

def _agg_values(
    rows: Sequence[SourceRow], fn: str, field: Optional[str], parsed: Sequence[tuple]
) -> Optional[List[Any]]:
    """The numeric read per row for op 6, or None for count-with-no-field
    (``count(*)``).  The field is §4.4 row 6's either: a computed column
    (B2 — the same AST, re-evaluated, never an alias reference) or a path."""
    if field is None:
        if fn != "count":
            raise ValueError(f"aggregate {fn!r} needs a field")
        return None
    read = ev.field_reader(field, parsed)
    return [read(r) for r in rows]


def _scalar(
    rows: Sequence[SourceRow], pick: dict, parsed: Sequence[tuple]
) -> Dict[str, Any]:
    agg = pick.get("aggregate") or {}
    fn = agg.get("fn")
    values = _agg_values(rows, fn, agg.get("field") or None, parsed)
    value = ev.aggregate(fn, values, len(rows))
    return {
        "shape": "SCALAR",
        "columns": [AGG],
        "rows": [{AGG: value}],
        "row_count": 1,
        AGG: value,
    }


# ── BUCKET (shape D) ────────────────────────────────────────────────────

_TS_STEPS = [("key", "ts")]


def _bucket(
    rows: Sequence[SourceRow], pick: dict, parsed: Sequence[tuple]
) -> Dict[str, Any]:
    granularity = pick.get("bucket")
    agg = pick.get("aggregate") or {}
    fn = agg.get("fn")  # never "none" here — B5c, enforced by the matrix
    field = agg.get("field") or None

    groups: Dict[str, List[SourceRow]] = {}
    for r in rows:
        ts = ev.text_of(ev.resolve(r.record_d, _TS_STEPS))
        if ts is None:
            # date_trunc(NULL) would be a silent NULL bucket; B4 restricts
            # bucketing to noun:Heartbeat, where ts is on every row — loud.
            raise ValueError(f"row {r.key!r} has no ts to bucket")
        groups.setdefault(ev.bucket_label(ts, granularity), []).append(r)

    # §7.1's time-bucket rule: bucketed results are ordered by the bucket —
    # text order over the fixed-width label IS time order.  Cap caps
    # buckets (B5a: op 5 on BUCKET), and it stays last.
    labels = sorted(groups, key=lambda s: s.encode("utf-8"))
    cap = pick.get("cap")
    if cap is not None:
        labels = labels[:cap]

    out_rows = []
    for label in labels:
        grp = groups[label]
        values = _agg_values(grp, fn, field, parsed)
        out_rows.append({BUCKET_COL: label, AGG: ev.aggregate(fn, values, len(grp))})
    return {
        "shape": "BUCKET",
        "columns": [BUCKET_COL, AGG],
        "rows": out_rows,
        "row_count": len(out_rows),
    }
