"""evaluate.py — the Python pane's row-level runner (spec §9.5, plan §4.1).

The second, independent calculator: filter, sort, cap, aggregate, bucket,
window and changed-rows-only, in Python, from scratch, over the source rows
``rows.py`` read.  GIMS has no equivalent for buckets, windows or change
detection to copy, so this file is new code — and the thing that checks the
SQL side's ops 7, 8 and 9 (spec §7.3), which is why it must not peek at the
SQL side: it imports nothing from ``demo/builder.py`` or ``demo/probes.py``
and receives nothing computed by them.  When the two panes disagree, the
disagreement has to mean something.

What implements what:

  §4.1's pipeline order      ``shape.py`` drives it; the steps live here
  §7.1's window rule (R9)    ``rolling_averages`` — divisor = the number of
                             non-null values actually in the frame, never 3
  §7.1's comparison rule     ``changed_flags`` — the record minus its
      (R13)                  ordering key, first row of a partition always
                             kept (lag() is NULL ↔ previous is _NO_PREDECESSOR)
  §7.1's time-bucket rule    ``bucket_label`` — aware UTC datetimes only,
      (R15)                  fixed-width label, the machine's zone untouched
  §7.2 item 5's numeric read ``numeric_value`` / ``field_reader`` — the
                             jsonb_typeof guard, Python half, via W9's
                             ``is_jsonb_number`` (the bool trap lives there)
  §7.2 item 2's rounding     W9's ``q6`` — every division, immediately
  §7.4's total order         W9's ``sort_key`` — every sort in this file

Arithmetic notes, because this project's failure mode is a subtly wrong
number that runs clean:

  * Sums and divisions for ops 6, 7 and 8 run inside an explicit
    ``decimal`` context — prec 1000, ROUND_HALF_UP — not the ambient one.
    The default 28-digit context would silently truncate a sum the moment a
    value like edge-00's 1e300 met a small addend (Postgres's ``numeric``
    addition is exact), and §7.2 item 4 forbids relying on anything ambient.
    1000 digits covers every magnitude the runtime probes admit (< DBL_MAX)
    with room to round to 6 places exactly.
  * A non-finite float can still reach an aggregate: a computed column over
    edge-03's 1e400 evaluates (in expr.py's float world) to ``inf``, and
    AC-17 wants the Python pane to SHOW ``inf`` while the SQL side refuses.
    ``Decimal`` has no honest home for it and ``q6`` refuses it, so any
    aggregate whose inputs include a non-finite float falls back to float
    arithmetic for that one answer and returns the non-finite float,
    unrounded, for the display layer to print literally.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .decimals import is_jsonb_number, q6
from .order import MISSING, sort_key
from .rows import SourceRow

# The vendored evaluator (spec §9.5, R4).  demo/ is a namespace package off
# the repo root; make the import hold regardless of cwd, the same way
# demo/server/operations.py does for its own imports.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from demo.vendor import expr  # noqa: E402  (path bootstrap above)

__all__ = [
    "dollar_path",
    "resolve",
    "text_of",
    "numeric_value",
    "parse_computed",
    "computed_values",
    "keep_by_filter",
    "field_reader",
    "partition_walk",
    "rolling_averages",
    "changed_flags",
    "aggregate",
    "bucket_label",
    "row_sort_key",
]

# §7.2's arithmetic context — explicit, never ambient (item 4).  prec=1000
# matches decimals.py's own quantize context: far beyond any admitted
# magnitude, so addition is exact and division carries every digit q6 needs.
_ARITH = Context(prec=1000, rounding=ROUND_HALF_UP)


# ── field paths ─────────────────────────────────────────────────────────

def dollar_path(field: str) -> List[Tuple[str, Any]]:
    """Parse a ``$.a.b`` / ``$.l[0]`` field string into expr.py path steps.

    The vendored parser is the demo's one AST supplier (spec §9.5: it feeds
    the gate and the compiler too), so the pane resolves the same spelling
    of a path the same way the rest of the demo does.  Anything that parses
    to more than a bare field reference is refused — a pick's field slots
    hold fields, never expressions.
    """
    ast = expr.parse(field)
    if not (isinstance(ast, tuple) and ast[0] == "field"):
        raise ValueError(f"not a field path: {field!r}")
    return list(ast[1])


def resolve(record: Any, steps: Sequence[Tuple[str, Any]]) -> Any:
    """``data #> path`` with the two nulls kept apart (§7.4(1b)).

    Returns ``MISSING`` where SQL gets NULL (absent key, index out of
    range, or a step into a non-container) and ``None`` where the value is
    present and holds JSON null.  expr.py's own ``_resolve_field`` merges
    the two — right for the evaluator, fatal for the sort — hence this
    resolver exists.
    """
    cur = record
    for kind, key in steps:
        if kind == "key":
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return MISSING
        else:  # index
            if isinstance(cur, (list, tuple)) and -len(cur) <= key < len(cur):
                cur = cur[key]
            else:
                return MISSING
    return cur


def text_of(value: Any) -> Optional[str]:
    """``->>`` for the values the frame actually orders on: text or null.

    ``sender_id`` and ``ts`` are text on every row of the one collection
    operations 8 and 9 are allowed to touch (B4).  A non-text value here
    means the pick handler let something through that the legality matrix
    forbids, and a loud raise beats the silent degradation B4 documents
    (``PARTITION BY NULL``, one bucket, whole-record comparisons) — the
    demo must never show a number produced by a control doing nothing.
    """
    if value is MISSING or value is None:
        return None  # SQL NULL either way under ->> (absent key / JSON null)
    if isinstance(value, str):
        return value
    raise TypeError(
        f"frame key is {type(value).__name__}, not text — operations 7, 8 "
        "and 9 are restricted to noun:Heartbeat (plan B4), whose sender_id "
        "and ts are always strings"
    )


def numeric_value(record_d: Any, steps: Sequence[Tuple[str, Any]]):
    """§7.2 item 5's numeric read, Python half, over the exact parse (B7).

    ``CASE WHEN jsonb_typeof(<j>) = 'number' THEN (<j> #>> '{}')::numeric END``
    — a non-number (string, bool, null, object, array, absent) becomes
    None, which drops out of every sum AND every divisor, matching what
    Postgres's aggregates do with NULL.  The bool trap is W9's
    ``is_jsonb_number`` (§7.2 item 5's one-character difference).

    Values arrive as ``int`` or ``Decimal`` — never a float — because the
    record is the ``parse_float=Decimal`` parse (B7).
    """
    v = resolve(record_d, steps)
    if v is MISSING or not is_jsonb_number(v):
        return None
    return v


# ── operations 2 and 3 — the float world (B7: expr.py only) ─────────────

def parse_computed(computed: Sequence[dict]) -> List[Tuple[str, Any]]:
    """Parse each computed column's expression once. [(name, ast), …] in
    entry order.  The gate has already accepted these (§4.5: the server
    gates before either pane runs); a parse error here propagates loudly.
    """
    return [(cc["name"], expr.parse(cc["expr"])) for cc in computed]


def computed_values(row: SourceRow, parsed: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    """Operation 2 on one row: evaluate each AST on ``record_f``.

    ``record_f`` — the ordinary-float parse — on purpose and by ruling
    (B7): the evaluator must see exactly what GIMS's evaluator would see,
    the compiled SQL stays in float8 for the same reason (R7), and §5's
    defect has to stay visible.  The exact-decimal rule does NOT extend to
    these values (§7.2, last paragraph).
    """
    return {name: expr.evaluate(ast, row.record_f, {}) for name, ast in parsed}


def keep_by_filter(row: SourceRow, filter_ast) -> bool:
    """Operation 3 on one row: expr truthiness of the filter, on record_f."""
    return expr.truthy(expr.evaluate(filter_ast, row.record_f, {}))


# ── the field an aggregate or window reads ──────────────────────────────

def field_reader(
    field: str, parsed_computed: Sequence[Tuple[str, Any]]
) -> Callable[[SourceRow], Any]:
    """One reader for op 6's and op 8's chosen field (§4.4 row 6's two forms).

    * a previously-defined computed column's NAME — the SQL side re-emits
      the compiled expression inline (B2) and that expression computes in
      float8, so the Python twin evaluates the same AST on ``record_f`` and
      classifies the result with the same jsonb_typeof test.  A finite
      float crosses into Decimal via ``repr`` — the shortest round-trip
      digits, which are exactly the text Postgres renders a float8 into
      jsonb with and then casts to numeric.  A non-finite float is returned
      as itself (see the module docstring).
    * otherwise a ``$.path`` — §7.2 item 5's numeric read over the exact
      parse (B7).

    Returns a callable row -> int | Decimal | float('inf'/nan) | None.
    """
    for name, ast in parsed_computed:
        if name == field:
            def read_computed(row: SourceRow, _ast=ast):
                v = expr.evaluate(_ast, row.record_f, {})
                if not is_jsonb_number(v):
                    return None
                if isinstance(v, float):
                    if v != v or v in (float("inf"), float("-inf")):
                        return v  # non-finite: carried as-is for display
                    return Decimal(repr(v))
                return v  # int — exact
            return read_computed
    steps = dollar_path(field)
    return lambda row: numeric_value(row.record_d, steps)


# ── the frame operations 8 and 9 share (§7.1's window rule, R9) ─────────

def _frame_order_key(row: SourceRow) -> tuple:
    """``ORDER BY (data ->> 'ts'), key`` within one partition — text order,
    which for the seed's fixed-width UTC ISO-8601 is time order, with SQL
    NULL last (Postgres's ASC default) and ``key`` the tiebreak (§7.4)."""
    ts = text_of(resolve(row.record_d, [("key", "ts")]))
    if ts is None:
        return (1, b"", row.key.encode("utf-8"))
    return (0, ts.encode("utf-8"), row.key.encode("utf-8"))


def partition_walk(rows: Sequence[SourceRow]) -> List[List[int]]:
    """``PARTITION BY (data ->> 'sender_id') ORDER BY (data ->> 'ts'), key``.

    Returns each partition as a list of indices into ``rows``, each list in
    frame order; partitions themselves in partition-key order (their order
    never reaches the screen — the pipeline's later sort decides that).
    Rows with no ``sender_id`` (SQL NULL) form one partition together,
    exactly as ``PARTITION BY`` groups NULLs — unreachable under B4, but
    the frame must not invent behaviour the SQL side doesn't have.
    """
    groups: Dict[tuple, List[int]] = {}
    for i, row in enumerate(rows):
        sender = text_of(resolve(row.record_d, [("key", "sender_id")]))
        gkey = (1, b"") if sender is None else (0, sender.encode("utf-8"))
        groups.setdefault(gkey, []).append(i)
    out = []
    for gkey in sorted(groups):
        idxs = groups[gkey]
        idxs.sort(key=lambda i: _frame_order_key(rows[i]))
        out.append(idxs)
    return out


def rolling_averages(
    rows: Sequence[SourceRow],
    partitions: Sequence[Sequence[int]],
    read: Callable[[SourceRow], Any],
) -> Dict[int, Any]:
    """Operation 8: ``avg(<numeric read>) OVER (w ROWS BETWEEN 2 PRECEDING
    AND CURRENT ROW)`` — {row index: value}.

    THE RULE both sides implement (§7.1's window rule, verbatim): *the
    divisor is the number of rows actually in the frame whose value is
    non-null, recounted for every row — never the constant 3.*  At a
    sender's first beat the frame holds 1 row, at its second 2 — the
    average is over the rows that exist, never over a phantom three, and
    never None there (mutants M1 and M2 are exactly those two wrong
    readings; AC-24(d) is the test that kills them).  If every value in
    the frame is null the cell is null, matching Postgres's ``avg`` over
    NULLs.  §7.2: accumulate in Decimal, round half-up to 6 immediately
    after the division.
    """
    out: Dict[int, Any] = {}
    for part in partitions:
        vals = [read(rows[i]) for i in part]
        for pos, i in enumerate(part):
            frame = vals[max(0, pos - 2): pos + 1]
            present = [v for v in frame if v is not None]
            if not present:
                out[i] = None
            elif any(isinstance(v, float) for v in present):
                # a non-finite float reached the frame (module docstring):
                # float fallback, unrounded, so inf can be shown as inf.
                out[i] = sum(float(v) for v in present) / len(present)
            else:
                with localcontext(_ARITH):
                    total = Decimal(0)
                    for v in present:
                        total += v if isinstance(v, Decimal) else Decimal(v)
                    out[i] = q6(total / Decimal(len(present)))
    return out


def _compared_value(row: SourceRow) -> dict:
    """§7.1's comparison rule: the record minus its ordering key — the
    spec's own spelling, over the EXACT parse (B7 rules op 9's comparison
    onto ``record_d``: jsonb compares numbers as numerics, exactly, and so
    does a dict of int/Decimal).  Content equality, key order irrelevant —
    never serialised text."""
    record = row.record_d
    if not isinstance(record, dict):
        # data - 'ts' on a non-object jsonb raises in Postgres; unreachable
        # on the seeded collections (every record is an object), and loud
        # here rather than silently comparing scalars.
        raise TypeError(f"record of {row.key!r} is not an object")
    return {k: v for k, v in record.items() if k != "ts"}


_NO_PREDECESSOR = object()  # lag() before any row: SQL NULL


def changed_flags(
    rows: Sequence[SourceRow], partitions: Sequence[Sequence[int]]
) -> Dict[int, bool]:
    """Operation 9: ``lag(data - 'ts') OVER w IS DISTINCT FROM (data - 'ts')``
    — {row index: kept?}.

    ``IS DISTINCT FROM``, never ``<>``: at a partition's first row lag() is
    NULL and NULL IS DISTINCT FROM x is TRUE, so every sender's first beat
    is kept by the operator itself, no special case (B3 detail 2; ``<>``
    is mutant M5, and AC-40(d)'s fifty first beats are what it loses).
    """
    out: Dict[int, bool] = {}
    for part in partitions:
        prev: Any = _NO_PREDECESSOR
        for i in part:
            cur = _compared_value(rows[i])
            out[i] = prev is _NO_PREDECESSOR or cur != prev
            prev = cur
    return out


# ── operations 6 and 7 — aggregate and bucket ───────────────────────────

def aggregate(fn: str, values: Optional[Sequence[Any]], row_count: int) -> Any:
    """Operation 6 over one group of rows (the whole pick for SCALAR, one
    bucket for BUCKET).

    ``values`` is the numeric read of the chosen field per row (None for
    ``count`` with no field, which counts rows — ``count(*)``).  Matches
    plan §4.2 shape C exactly: sum and avg accumulate in Decimal and are
    rounded to 6 places (the SQL is ``round(sum(…), 6)`` / ``round(avg(…),
    6)``); min and max take no round; every fn ignores nulls; sum/avg/min/
    max of no values is None (SQL NULL), count of no rows is 0.
    """
    if fn == "count":
        if values is None:
            return row_count  # count(*)
        return sum(1 for v in values if v is not None)  # count(CASE …)
    if values is None:
        raise ValueError(f"aggregate {fn!r} needs a field")
    present = [v for v in values if v is not None]
    if not present:
        return None
    if any(isinstance(v, float) for v in present):
        # non-finite floats in play (module docstring): float fallback.
        floats = [float(v) for v in present]
        if fn == "sum":
            return sum(floats)
        if fn == "avg":
            return sum(floats) / len(floats)
        if fn == "min":
            return min(floats)
        if fn == "max":
            return max(floats)
        raise ValueError(f"unknown aggregate {fn!r}")
    with localcontext(_ARITH):
        if fn in ("sum", "avg"):
            total = Decimal(0)
            for v in present:
                total += v if isinstance(v, Decimal) else Decimal(v)
            if fn == "sum":
                return q6(total)
            return q6(total / Decimal(len(present)))
        if fn == "min":
            return min(present)
        if fn == "max":
            return max(present)
    raise ValueError(f"unknown aggregate {fn!r}")


_TS_WIDTH = len("2026-08-14T00:00:00Z")


def bucket_label(ts_text: str, granularity: str) -> str:
    """Operation 7's bucket for one row, as the label BOTH panes key by.

    §7.1's time-bucket rule, Python half, verbatim: parse ``ts`` as an
    AWARE UTC datetime, truncate to the hour or the day IN UTC, format
    with the same fixed-width string the SQL side's ``to_char`` pins —
    ``YYYY-MM-DDTHH:MM:SSZ``.  The machine's local time zone is touched at
    no step and no naive datetime exists here (a naive datetime is the
    Python spelling of the ``::timestamp`` mistake).

    The seed writes ``ts`` in exactly this fixed-width form (R17); anything
    else raises rather than landing in a quietly wrong bucket.
    """
    if granularity not in ("hour", "day"):
        raise ValueError(f"granularity must be 'hour' or 'day', got {granularity!r}")
    if len(ts_text) != _TS_WIDTH:
        raise ValueError(f"not fixed-width UTC ISO-8601: {ts_text!r}")
    parsed = datetime.strptime(ts_text, "%Y-%m-%dT%H:%M:%SZ")
    aware = parsed.replace(tzinfo=timezone.utc)  # aware, UTC, immediately
    if granularity == "hour":
        trunc = aware.replace(minute=0, second=0, microsecond=0)
    else:
        trunc = aware.replace(hour=0, minute=0, second=0, microsecond=0)
    return f"{trunc.year:04d}-{trunc.month:02d}-{trunc.day:02d}T{trunc.hour:02d}:{trunc.minute:02d}:{trunc.second:02d}Z"


# ── operation 4 (and the order every result carries) ────────────────────

def row_sort_key(
    row: SourceRow,
    sort_steps: Optional[Sequence[Tuple[str, Any]]],
    computed: Optional[Dict[str, Any]],
    sort_alias: Optional[str],
    direction: str,
) -> tuple:
    """§7.4's total order for one row, routed through W9's ``sort_key``.

    Three cases for the sort value:
      * no sort picked — MISSING for every row, collapsing the order to
        ``key ASC`` (§7.4(2): every result carries the order, sorted or not);
      * a ``$.path`` — resolved on the exact parse, MISSING/None kept apart;
      * a computed alias — the row's evaluated column (SQL sorts the emitted
        column by alias reference, which is legal in ORDER BY); expr.py's
        None means the compiled float8 expression was SQL NULL, i.e. the
        NULLS LAST band, so it maps to MISSING here.
    """
    if sort_alias is not None:
        v = (computed or {}).get(sort_alias)
        value = MISSING if v is None else v
    elif sort_steps is not None:
        value = resolve(row.record_d, sort_steps)
    else:
        value = MISSING
    return sort_key(value, row.key, direction)
