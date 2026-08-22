"""legality.py — which operation combinations are legal, and why (W8).

THE ONE PLACE the legality matrix lives (T-2-plan.md §4.5): the
``/api/operations`` contract AND the pick handler both call
:func:`evaluate`, so the screen's idea of an enabled control and the
server's idea of a legal pick can never disagree.

The matrix is ruling B5a of ``.autodev/specs/T-2-plan.md``:

    A pick has exactly one of three SHAPES, and the shape decides every
    control.

      ROWS    op 6 = none, op 7 = off      -> a list of rows
      SCALAR  op 6 = a function, op 7 = off -> one number
      BUCKET  op 7 = hour or day            -> label + number per bucket

Rules folded in, each named where it is applied below:

  X1  (design part 3.1.2, ruled at B4) — operations 7, 8 and 9 read
      ``$.ts`` and ``$.sender_id``; only ``noun:Heartbeat`` carries them,
      so on any other source the three are disabled, with the
      collection's actual field list stated as the reason.
  X2  (design part 3.1.2) — op 8 is unavailable while op 6 has a
      function (one statement cannot emit both ``AS "agg"`` and a
      per-row ``AS "rolling_avg"``), and op 4 is unavailable while op 7
      is bucketing (a bucketed result is ordered by the bucket).
  B5a's extensions beyond the drawn pair — on SCALAR: ops 4, 5 and 9
      are also off; on BUCKET: ops 8 and 9 are also off (a window's
      PARTITION BY reads ungrouped ``data`` in a grouped query, which
      Postgres refuses with SQLSTATE 42803).  The bucketed view greys
      one MORE control (op 9) than the approved mock draws — that is
      B5a's stated, deliberate excess over the drawing.
  B5b — every disable is a DR-2 disable: the reason is non-empty, names
      the operation that caused it, and never says "invalid
      combination".
  B5c — BUCKET requires an aggregate.  The SCREEN honours this by
      visibly setting op 6 to ``count`` when op 7 turns on
      (operations.py carries that transition rule for W14); a pick
      that arrives with op 7 on and op 6 ``none`` anyway — i.e. not
      through the screen — is a violation here, refused, never
      silently defaulted.

Every combination walked, every disable's reason asserted non-empty:
``demo/tests/test_legality.py``.

Pure stdlib.  No database, no imports from the rest of the demo.
"""

from __future__ import annotations

# ── the closed sets (§4.4 row 7) ────────────────────────────────────────

HEARTBEAT = "noun:Heartbeat"

#: The three collections, and each one's top-level field vocabulary as a
#: display string — what X1's reason states.  The seed is deterministic
#: (plan §5), so these are constants of the build:
#:   noun:Heartbeat  plan §5.2's four fields
#:   noun:Sample     plan §5.3 / spec §4.10's list, as the approved mock
#:                   renders it
#:   noun:EdgeCase   the union of top-level keys over B24's ten pinned
#:                   rows, sorted as §4.4's key read sorts them.  The
#:                   mock drew five of these; B4 says the reason states
#:                   the collection's ACTUAL field list, so all sixteen
#:                   are stated (recorded in W8's report).
SOURCES: dict[str, str] = {
    "noun:Heartbeat": "sender_id, ts, status, payload",
    "noun:Sample": "id, status, due_date, priority, field_0 … field_14",
    "noun:EdgeCase": (
        "a, arr, d, g, huge, l, label, n, obj, present, "
        "s, t, tags, txt, where, z"
    ),
}

#: Operation 6's functions — "a closed set of five" plus ``none``.
AGG_FNS = ("none", "count", "sum", "avg", "min", "max")

#: The functions that read one numeric field.  ``count`` counts rows and
#: takes no field; ``none`` is no aggregate at all.
AGG_FNS_WITH_FIELD = ("sum", "avg", "min", "max")

#: Operation 7's granularities — Q20's own two, and nothing else.
BUCKETS = ("off", "hour", "day")

#: Operation 4's directions.
SORT_DIRS = ("asc", "desc")

#: Operation 5's range — §4.4 row 5, ``MAX_SCAN``.
CAP_MIN, CAP_MAX = 1, 20000

#: The three shapes of B5a.
ROWS, SCALAR, BUCKET = "ROWS", "SCALAR", "BUCKET"


# ── the reasons, written once ───────────────────────────────────────────
# B5b: each names the operation that caused the disable, and none says
# "invalid combination".

def _why_x1(source: str) -> str:
    fields = SOURCES.get(source)
    listed = (
        f"its top-level fields are {fields}"
        if fields
        else "it is not a known source"
    )
    return (
        "unavailable on this source (operation 1): reads $.ts and "
        f"$.sender_id, and {source} has neither — {listed}; only "
        "noun:Heartbeat carries both"
    )


_WHY_SCALAR_SORT = (
    "unavailable while the aggregate (operation 6) is set: an aggregate "
    "returns one row; there is nothing to sort"
)
_WHY_SCALAR_CAP = (
    "unavailable while the aggregate (operation 6) is set: an aggregate "
    "returns one row"
)
_WHY_SCALAR_WINDOW = (
    "unavailable while the aggregate (operation 6) is set: one statement "
    "cannot return both a total and a per-row value"
)
_WHY_SCALAR_CHANGED = (
    "unavailable while the aggregate (operation 6) is set: one row has "
    "no predecessor"
)
_WHY_BUCKET_SORT = (
    "unavailable while time buckets (operation 7) are on: bucketed "
    "results are ordered by the bucket, fixed by operation 7 rather "
    "than chosen here"
)
_WHY_BUCKET_WINDOW = (
    "unavailable while time buckets (operation 7) are on: a rolling "
    "window is computed row by row, a bucketed query has grouped its "
    "rows away, and Postgres refuses the combination (42803)"
)
_WHY_BUCKET_CHANGED = (
    "unavailable while time buckets (operation 7) are on: a bucket has "
    "no predecessor to compare against, and Postgres refuses the "
    "row-by-row comparison inside a grouped query (42803)"
)

#: The rule that lives INSIDE operation 6 (B5a's last paragraph, drawn
#: in the mock): with ``count`` chosen the field picker is off.
WHY_COUNT_TAKES_NO_FIELD = "count counts rows and takes no field"
WHY_NO_FN_NO_FIELD = "no function is chosen; there is no field to read"

#: B5c, as the screen speaks it when op 7 turns on over op 6 = none.
WHY_BUCKET_NEEDS_AGG = "a bucket has to count or total something; set to count"


# ── the pick ────────────────────────────────────────────────────────────
# The pick is a plain dict; this is its shape, pinned here because
# evaluate(pick) is the one function both the contract and the pick
# handler call (§4.5).  Absent keys mean "not set".
#
#   source    str   one of SOURCES                       (op 1)
#   computed  list  [{"name": str, "expr": str}, ...]     (op 2)
#   filter    str | None                                  (op 3)
#   sort      {"field": str, "dir": "asc"|"desc"} | None  (op 4)
#   cap       int | None                                  (op 5)
#   aggregate {"fn": str, "field": str | None} | None     (op 6)
#   bucket    "off" | "hour" | "day"                      (op 7)
#   window    {"field": str} | None                       (op 8)
#   changed   bool                                        (op 9)


def default_pick() -> dict:
    """The screen's initial state: the heartbeat, nothing set."""
    return {
        "source": HEARTBEAT,
        "computed": [],
        "filter": None,
        "sort": None,
        "cap": None,
        "aggregate": {"fn": "none", "field": None},
        "bucket": "off",
        "window": None,
        "changed": False,
    }


def shape_of(pick: dict) -> str:
    """B5a: the pick's one shape.  Op 7 decides first, then op 6."""
    if _bucket(pick) != "off":
        return BUCKET
    if _agg_fn(pick) != "none":
        return SCALAR
    return ROWS


# ── small readers, tolerant of absent keys ──────────────────────────────

def _bucket(pick: dict) -> str:
    return pick.get("bucket") or "off"


def _agg(pick: dict) -> dict:
    return pick.get("aggregate") or {}


def _agg_fn(pick: dict) -> str:
    return _agg(pick).get("fn") or "none"


def _agg_field(pick: dict):
    return _agg(pick).get("field") or None


def _sort(pick: dict):
    return pick.get("sort") or None


def _window(pick: dict):
    return pick.get("window") or None


def _carries_value(pick: dict, n: int) -> bool:
    """Does operation *n* carry a value in this pick?  Mirrors the
    mock's ``isOn`` — derived from the controls, not stored beside
    them."""
    if n == 4:
        s = _sort(pick)
        return bool(s and s.get("field"))
    if n == 5:
        return pick.get("cap") is not None
    if n == 7:
        return _bucket(pick) != "off"
    if n == 8:
        w = _window(pick)
        return bool(w and w.get("field"))
    if n == 9:
        return bool(pick.get("changed"))
    raise ValueError(f"operation {n} is never disabled; no value check for it")


# ── THE function (§4.5) ─────────────────────────────────────────────────

def evaluate(pick: dict) -> dict:
    """The legality of one pick — B5a's whole matrix, in one place.

    Returns::

        {
          "shape":  "ROWS" | "SCALAR" | "BUCKET",
          "source": the pick's source,
          "ops":    {n: {"enabled": bool, "why": str}}  for n in 1..9 —
                    ``why`` is "" when enabled, NON-EMPTY when not (B5b),
          "aggregate_field": {"enabled": bool, "why": str} — op 6's
                    field picker, the rule inside the operation,
          "violations": [{"operation": n, "why": str}, ...] — every way
                    this pick, arriving other than through the screen,
                    sets a value the matrix forbids.  Empty means the
                    pick is legal.  The pick handler refuses on any
                    entry, with these words (DR-2: never silently
                    ignored, never silently defaulted).
        }
    """
    source = pick.get("source") or ""
    on_heartbeat = source == HEARTBEAT
    shape = shape_of(pick)
    fn = _agg_fn(pick)

    ops: dict[int, dict] = {n: {"enabled": True, "why": ""} for n in range(1, 10)}

    def disable(n: int, why: str) -> None:
        # First reason wins, as in the approved mock: X1 (applied first,
        # below) outranks a shape reason for the same control.
        if ops[n]["enabled"]:
            ops[n] = {"enabled": False, "why": why}

    # X1 — before everything, exactly as the mock's locksFor() orders it.
    if not on_heartbeat:
        why = _why_x1(source)
        disable(7, why)
        disable(8, why)
        disable(9, why)

    # The shape's own column of the B5a matrix.
    if shape == SCALAR:
        disable(4, _WHY_SCALAR_SORT)
        disable(5, _WHY_SCALAR_CAP)
        disable(8, _WHY_SCALAR_WINDOW)   # X2, first half
        disable(9, _WHY_SCALAR_CHANGED)
    elif shape == BUCKET:
        disable(4, _WHY_BUCKET_SORT)     # X2, second half
        disable(8, _WHY_BUCKET_WINDOW)   # B5a's extension: 42803
        disable(9, _WHY_BUCKET_CHANGED)  # B5a extension: the one past the mock

    # The rule inside operation 6.
    if fn == "count":
        aggregate_field = {"enabled": False, "why": WHY_COUNT_TAKES_NO_FIELD}
    elif fn == "none":
        aggregate_field = {"enabled": False, "why": WHY_NO_FN_NO_FIELD}
    else:
        aggregate_field = {"enabled": True, "why": ""}

    # ── violations: values the matrix forbids, present anyway ───────────
    violations: list[dict] = []

    def violate(n: int, why: str) -> None:
        violations.append({"operation": n, "why": why})

    # Closed sets first (§4.4 row 7) — fail closed on anything unknown.
    if source not in SOURCES:
        violate(1, f"unknown source {source!r}: the sources are a closed set of three")
    if fn not in AGG_FNS:
        violate(6, f"unknown aggregate {fn!r}: the functions are a closed set")
    if _bucket(pick) not in BUCKETS:
        violate(
            7,
            f"unknown granularity {_bucket(pick)!r}: hour and day are the "
            "closed set, and there is no other unit",
        )
    s = _sort(pick)
    if s and s.get("field") and s.get("dir") not in SORT_DIRS:
        violate(4, f"unknown sort direction {s.get('dir')!r}: ascending or descending")

    # A value on a disabled operation is refused with the SAME words the
    # screen shows beside the greyed control (§4.5: one function).
    for n in (4, 5, 7, 8, 9):
        if not ops[n]["enabled"] and _carries_value(pick, n):
            violate(n, ops[n]["why"])

    # B5c — BUCKET with no aggregate never runs.
    if shape == BUCKET and fn == "none":
        violate(6, WHY_BUCKET_NEEDS_AGG)

    # An aggregate that reads a field needs one; count must not carry one.
    if fn in AGG_FNS_WITH_FIELD and not _agg_field(pick):
        violate(6, f"the aggregate {fn} reads one numeric field, and none is chosen")
    if fn in ("none", "count") and _agg_field(pick):
        violate(
            6,
            WHY_COUNT_TAKES_NO_FIELD if fn == "count" else WHY_NO_FN_NO_FIELD,
        )

    # Operation 5's range — a positive integer no greater than MAX_SCAN.
    cap = pick.get("cap")
    if cap is not None and ops[5]["enabled"]:
        if not isinstance(cap, int) or isinstance(cap, bool) or not (
            CAP_MIN <= cap <= CAP_MAX
        ):
            violate(
                5,
                "the row cap must be a whole number between 1 and 20,000",
            )

    return {
        "shape": shape,
        "source": source,
        "ops": ops,
        "aggregate_field": aggregate_field,
        "violations": violations,
    }
