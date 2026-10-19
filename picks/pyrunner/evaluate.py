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
  * A non-finite float can still reach an aggregate: arithmetic inside
    expr.py's float world can overflow the double range and yield ``inf``
    even when every input row was finite.  ``Decimal`` has no honest home
    for it and ``q6`` refuses it, so any aggregate whose inputs include a
    non-finite float falls back to float arithmetic for that one answer and
    returns the non-finite float, unrounded, for the display layer to print
    literally.
    NOT edge-03, though (CORRECTION, 2026-08-22): this note used to cite
    edge-03's 1e400 as the example and say AC-17 wants the Python pane to
    SHOW ``inf``.  It does not arrive as a float at all — jsonb renders it
    as a bare 401-digit INTEGER literal, ``json.loads`` returns an exact
    ``int`` for that, and expr.py's ``float()`` of it RAISES
    ``OverflowError`` rather than producing an inf.  Step 13 therefore ends
    in a reported raise, not a printed inf; see W13-2 above
    ``_fallback_python_pane`` in ``demo/server/app.py`` and the correction
    note beside AC-17 in ``.autodev/specs/T-2.md``.  (T-98, 2026-10-13: with
    GIMS's current evaluator vendored, its T-36 leaves that product null,
    so step 13's Python pane answers with a blank instead of raising.)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .decimals import is_jsonb_number, q6
from .exact import exact_value
from .order import MISSING, sort_key
from .rows import SourceRow

# The evaluator (spec §9.5, R4): the HOST's expression module, registered
# once with ``picks.env.use(evaluator=...)`` (T-86) — GIMS's own evaluator,
# vendored in this repo at demo/vendor/expr.py.  Its own module object: the
# statement side's parser is registered separately.
from .. import env as _env  # noqa: E402
from .. import paths, times  # noqa: E402  (T-114: the rule, as the second engine reads it)

expr = _env.get("evaluator")

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

    T-112: a value the evaluator hands back untouched (a field, ``coalesce``,
    an ``if`` branch) is answered with its stored digits, as the statement
    answers jsonb's; a computed double in Postgres's digits (``exact.py``).
    """
    return {name: exact_value(expr.evaluate(ast, row.record_f, {})) for name, ast in parsed}


def keep_by_filter(row: SourceRow, filter_ast, instants: Optional[Sequence] = None) -> bool:
    """Operation 3 on one row: expr truthiness of the filter, on record_f -- with T-114's instant reading of the
    time fields ``instants`` names (expr.py path steps; :func:`instant_record`)."""
    record = instant_record(row.record_f, instants) if instants else row.record_f
    return expr.truthy(expr.evaluate(filter_ast, record, {}))


def reads_as_instant(field: str, named: Optional[Sequence[str]]) -> bool:
    """T-114: is ``field`` one of the time fields a pick names (``times``) -- by its path, in any spelling?"""
    if not named:
        return False
    try:
        steps = paths.steps(field)
    except ValueError:
        return False
    return any(paths.steps(t) == steps for t in named)


class InstantPath(list):
    """A sort's field path that names a time field read as an instant (T-114, ruling 2)."""


def instants_of(named: Optional[Sequence[str]]) -> list:
    """The time fields a pick or a board names (``times``), as expr.py path steps."""
    return [dollar_path(paths.dollar(t)) for t in named or ()]


def instant_record(record: Any, instants: Sequence) -> Any:
    """``record`` with each time field ``instants`` names handed to the filter as the statement hands it (runtime
    ``xpr.time_text``; T-114, the foreman's (A)): its UTC instant at one width, false when it is no readable time,
    a blank (JSON null, or no such field) as it is. A copy along each path; the record itself is never changed."""
    for steps in instants:
        record = _with_reading(record, list(steps))
    return record


def _with_reading(cur: Any, steps: List[Tuple[str, Any]]) -> Any:
    if not steps:
        return times.reading(cur)
    kind, key = steps[0]
    if kind == "key":
        if not isinstance(cur, dict) or key not in cur:
            return cur
        out = dict(cur)
    else:
        if not isinstance(cur, list) or not -len(cur) <= key < len(cur):
            return cur
        out = list(cur)
    out[key] = _with_reading(cur[key], steps[1:])
    return out


# ── the field an aggregate or window reads ──────────────────────────────

def field_reader(
    field: str, parsed_computed: Sequence[Tuple[str, Any]]
) -> Callable[[SourceRow], Any]:
    """One reader for op 6's and op 8's chosen field (§4.4 row 6's two forms).

    * a previously-defined computed column's NAME — the SQL side re-emits
      the compiled expression inline (B2) and that expression computes in
      float8, so the Python twin evaluates the same AST on ``record_f`` and
      classifies the result with the same jsonb_typeof test.  A finite
      computed float crosses into Decimal in the digits Postgres renders a
      float8 into jsonb with (T-112: Postgres's printer, not ``repr``, which
      differs on midpoints), and a value passed through untouched keeps its
      stored digits (``exact.py``).  A non-finite float is returned as itself
      (see the module docstring).
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
                return exact_value(v)  # int exact; a stored number exactly; a computed double in Postgres's digits
            return read_computed
    steps = dollar_path(field)
    return lambda row: numeric_value(row.record_d, steps)


# ── the frame operations 8 and 9 share (§7.1's window rule, R9) ─────────

def _frame_order_key(row: SourceRow, time: str = "ts") -> tuple:
    """``ORDER BY (data ->> 'ts'), key`` within one partition — text order,
    which for the seed's fixed-width UTC ISO-8601 is time order, with SQL
    NULL last (Postgres's ASC default) and ``key`` the tiebreak (§7.4)."""
    ts = text_of(resolve(row.record_d, [("key", time)]))
    if ts is None:
        return (1, b"", row.key.encode("utf-8"))
    return (0, ts.encode("utf-8"), row.key.encode("utf-8"))


def partition_walk(rows: Sequence[SourceRow], time: str = "ts",
                   member: str = "sender_id") -> List[List[int]]:
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
        sender = text_of(resolve(row.record_d, [("key", member)]))
        gkey = (1, b"") if sender is None else (0, sender.encode("utf-8"))
        groups.setdefault(gkey, []).append(i)
    out = []
    for gkey in sorted(groups):
        idxs = groups[gkey]
        idxs.sort(key=lambda i: _frame_order_key(rows[i], time))
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


def _compared_value(row: SourceRow, time: str = "ts") -> dict:
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
    return {k: v for k, v in record.items() if k != time}


_NO_PREDECESSOR = object()  # lag() before any row: SQL NULL


def changed_flags(
    rows: Sequence[SourceRow], partitions: Sequence[Sequence[int]], time: str = "ts"
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
            cur = _compared_value(rows[i], time)
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


def time_value(value: Any) -> Optional[datetime]:
    """A stored value as an AWARE UTC datetime when it is a readable time (T-114: every form the rule reads, at its
    UTC instant; ``picks.times``) or a date (its UTC midnight, T-88); ``None`` for anything else — missing, null, a
    number, a naive or another text form, a day the calendar lacks.  Such a record is in no bucket."""
    return times.instant(value)


def local_time(value: Any, zone: str) -> Optional[datetime]:
    """T-100: a stored time or date as a NAIVE wall-clock time on ``zone`` -- a time read on that
    clock, a calendar date as its own midnight (never shifted) -- or ``None`` when it is neither
    (the same values time_value refuses)."""
    at = time_value(value)
    if at is None:
        return None
    if len(value) == 10:
        return at.replace(tzinfo=None)
    try:
        return at.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
    except OverflowError:
        return None          # its clock reading leaves years 1..9999: in no bucket (a-chk's MEDIUM)


def truncate_wall(at: datetime, granularity: str) -> str:
    """A naive wall-clock time → its bucket's label on that clock: the bucket's local start,
    ``YYYY-MM-DDTHH:MM:SS`` with NO Z (T-100).  The same cut as truncate_label, on the wall clock:
    a repeated hour is one bucket, a skipped hour has none."""
    return truncate_label(at.replace(tzinfo=timezone.utc), granularity)[:-1]


def truncate_label(at: datetime, granularity: str) -> str:
    """One aware UTC datetime → its bucket's label, in the one fixed-width
    form: the hour, the day, the week (from its MONDAY, as Postgres's
    ``date_trunc('week')``), or the calendar month — all in UTC."""
    if granularity == "hour":
        trunc = at.replace(minute=0, second=0, microsecond=0)
    elif granularity == "day":
        trunc = at.replace(hour=0, minute=0, second=0, microsecond=0)
    elif granularity == "week":
        day = at.replace(hour=0, minute=0, second=0, microsecond=0)
        trunc = day - timedelta(days=day.weekday())          # Monday is 0
    elif granularity == "month":
        trunc = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"granularity must be hour, day, week or month, got {granularity!r}")
    return f"{trunc.year:04d}-{trunc.month:02d}-{trunc.day:02d}T{trunc.hour:02d}:{trunc.minute:02d}:{trunc.second:02d}Z"


def bucket_label(ts_text: str, granularity: str) -> str:
    """Operation 7's bucket for one row, as the label BOTH panes key by.

    §7.1's time-bucket rule, Python half: read ``ts`` as an AWARE UTC instant, truncate to the hour, day, week or
    month IN UTC, and write the same fixed-width string the SQL side's ``to_char`` pins — ``YYYY-MM-DDTHH:MM:SSZ``.
    The machine's local time zone is touched at no step and no naive datetime exists here (a naive datetime is the
    Python spelling of the ``::timestamp`` mistake).

    T-114: the series' time is read by the rule (``picks.times``: every readable form, with a time of day); anything
    else raises rather than landing in a quietly wrong bucket (T-109: the statement refuses the same rows, XPR06).
    """
    if granularity not in ("hour", "day", "week", "month"):
        raise ValueError(f"granularity must be hour, day, week or month, got {granularity!r}")
    at = times.instant(ts_text) if isinstance(ts_text, str) and len(ts_text) > 10 else None
    if at is None:
        raise ValueError(f"not a readable time: {ts_text!r}")
    return truncate_label(at, granularity)


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
        if isinstance(sort_steps, InstantPath) and value is not MISSING:
            # T-114 (ruling 2): a time field by its instant; a value that is no readable time sorts last either way,
            # with the rows that lack the field (the statement's NULLS LAST, then the key); JSON null keeps its place
            value = times.reading(value)
            if value is False:
                value = MISSING
    else:
        value = MISSING
    return sort_key(value, row.key, direction)
