"""exact.py — T-112: the second engine reads a stored number exactly, or refuses it in words.

Three things, each the statement's twin:

* SHOWN EXACTLY. ``record_f`` (the float parse GIMS's evaluator reads, B7) keeps each number's stored text beside its
  double (:class:`ExactFloat`). A value the evaluator hands back untouched -- a field, a ``coalesce`` argument, an
  ``if`` branch, a list or an object passed through -- is answered with its stored digits, as the statement answers
  jsonb's (``-0`` as ``0``: jsonb has none). A COMPUTED double is answered written as Postgres writes it
  (``picks.doubles.pg_shortest``), so ``1e22 * 10`` reads the same on both engines.

* HELD, OR REFUSED. Where the evaluator reads a stored number AS A DOUBLE -- a comparison, arithmetic, ``abs``,
  ``min``/``max`` (and a list's elements there), truthiness -- a number it would misread silently is refused: one a
  double holds only as 0 (small), one with more digits than a double holds (digits). A number stored as text is
  read as one only where arithmetic reads it, and text compared as text is never read. :func:`check` asks it of
  every source row BEFORE the filter (the statement's probe member d reads the same scope) and raises
  :class:`NumberRefused`, naming the first offending row in key order.

* PAST THE LARGEST DOUBLE. Beside the statement (the demo's two-pane screen) such a number is left as it was: the
  statement refuses it first (member (a), or XPR01 while running) and the language declines it in arithmetic (no
  value). When the host says this engine answers ALONE (``Records.alone``: GIMS's SQLite mode, nothing beside it
  to refuse), it is refused too ("large") wherever it is read as above, or sorted by: the language would compare
  two such numbers as the same infinity.

* ITS OWN WALK. The statement side states the rule in SQL (probe member d); this file states it again for this
  engine, importing nothing from ``builder``/``probes`` (W12's independence), so the two can disagree and be caught.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from .. import env
from ..doubles import DIGITS, LARGE, SMALL, kind, numeric_text, pg_shortest
from .order import MISSING

__all__ = ["ExactFloat", "exact_value", "NumberRefused", "readings", "check", "answers_alone", "SHOWN", "NUMBER",
           "COERCED", "ELEMENTS", "SORTED"]


class ExactFloat(float):
    """A JSON number literal as the float parse reads it -- a plain double to the evaluator -- with its stored text
    kept, so a value passed through untouched can be answered exactly. Arithmetic on it makes plain floats."""

    def __new__(cls, text: str):
        self = super().__new__(cls, text)
        self.text = text
        return self


def _exact(text: str) -> Decimal:
    d = Decimal(text)
    return d.copy_abs() if d.is_zero() else d


def exact_value(v: Any) -> Any:
    """A computed column's value as this engine answers it: a passed-through stored number exactly, a computed
    double in Postgres's digits, containers element by element; anything else as it is."""
    if isinstance(v, ExactFloat):
        return _exact(v.text)
    if isinstance(v, float):
        if not math.isfinite(v):
            return v
        return _exact(pg_shortest(v))
    if isinstance(v, list):
        return [exact_value(x) for x in v]
    if isinstance(v, dict):
        return {k: exact_value(x) for k, x in v.items()}
    return v


# ── where the evaluator reads a stored value as a double ────────────────
#: SHOWN: passed through untouched. NUMBER: read as a double if it is a number (a comparison, truthiness).
#: COERCED: read as a double if it is a number or a number written as text (arithmetic, ``abs``).
#: ELEMENTS: as COERCED, and a list's elements too (``min``/``max``).
#: SORTED: what a sort orders by (the column's passed-through fields, or the path). The sort reads the exact value,
#: so only a number past the largest double counts there, and only when the engine answers alone.
SHOWN, NUMBER, COERCED, ELEMENTS, SORTED = "shown", "number", "coerced", "elements", "sorted"

_WORDS = {
    LARGE: "out-of-range magnitude: this pick reads a number of magnitude >= 1.7976931348623157e+308, which a double "
           "cannot hold",
    SMALL: "number too small for a double: this pick reads a number a double holds only as 0",
    DIGITS: "number with more digits than a double holds: this pick reads a number no double holds exactly",
}


class NumberRefused(ValueError):
    """The second engine's refusal (T-112): a stored number this pick reads as a double, which no double holds.

    kind    -- LARGE, SMALL or DIGITS (``picks.doubles``)
    row_key -- the first offending row, in key order
    value   -- its stored value, as text
    cause   -- the sentence, naming both (the statement's probe member d says the same)
    """

    def __init__(self, kind_: str, row_key: str, value: str):
        self.kind = kind_
        self.row_key = row_key
        self.value = value
        self.cause = f'{_WORDS[kind_]} (first such row, by key: "{row_key}")'
        super().__init__(self.cause)


def readings(ast, root: str = SHOWN) -> List[Tuple[list, str]]:
    """``[(field path steps, position)]``: every field ``ast`` reads as a double, and how (SHOWN fields omitted).
    ``root`` is how the whole expression is used: SHOWN for a computed column, NUMBER for a filter or a count,
    SORTED for what a sort orders by."""
    out: List[Tuple[list, str]] = []

    def walk(node, pos: str) -> None:
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag == "field":
            if pos != SHOWN:
                out.append((list(node[1]), pos))
        elif tag == "neg":
            walk(node[1], COERCED)
        elif tag == "bin":
            walk(node[2], COERCED)
            walk(node[3], COERCED)
        elif tag == "cmp":
            walk(node[2], NUMBER)
            walk(node[3], NUMBER)
        elif tag == "not":
            walk(node[1], NUMBER)
        elif tag in ("and", "or"):
            walk(node[1], NUMBER)
            walk(node[2], NUMBER)
        elif tag == "call":
            name, args = node[1], node[2]
            if name == "coalesce":
                for a in args:
                    walk(a, pos)                       # each argument may be the value: it takes the call's place
            elif name == "if":
                for i, a in enumerate(args):
                    walk(a, NUMBER if i == 0 else pos)
            elif name in ("min", "max"):
                for a in args:
                    walk(a, ELEMENTS)
            elif name in ("count", "length", "time_of_day"):
                for a in args:
                    walk(a, SHOWN)                     # counts, measures, reads a time: never a double
            else:                                      # abs, and anything else: its arguments read as numbers
                for a in args:
                    walk(a, COERCED)
        # num / str / bool / null: literals (the gate and the builder judge those)

    walk(ast, root)
    seen, unique = set(), []
    for steps, pos in out:
        key = (repr(steps), pos)
        if key not in seen:
            seen.add(key)
            unique.append((steps, pos))
    return unique


def _number(v: Any) -> Optional[Decimal]:
    if isinstance(v, bool) or not isinstance(v, (int, Decimal)):
        return None
    return v


def _refused(k: Optional[str], text: str, pos: str, alone: bool) -> Optional[Tuple[str, str]]:
    if k is None:
        return None
    if k == LARGE:
        return (k, text) if alone else None
    return None if pos == SORTED else (k, text)


def _value_kind(v: Any, pos: str, alone: bool = False) -> Optional[Tuple[str, str]]:
    """(kind, value text) when ``v``, read at ``pos``, is refused (see the module docstring); else None."""
    n = _number(v)
    if n is not None:
        return _refused(kind(n), str(n), pos, alone)
    if pos in (COERCED, ELEMENTS) and isinstance(v, str):
        d = numeric_text(v)
        if d is not None:
            return _refused(kind(d), v, pos, alone)
    if pos == ELEMENTS and isinstance(v, list):
        for x in v:
            found = _value_kind(x, COERCED, alone)
            if found:
                return found
    return None


def _resolve(record: Any, steps: Sequence[Tuple[str, Any]]) -> Any:
    cur = record
    for k, key in steps:
        if k == "key":
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return MISSING
        else:
            if isinstance(cur, (list, tuple)) and -len(cur) <= key < len(cur):
                cur = cur[key]
            else:
                return MISSING
    return cur


def answers_alone(records=None) -> bool:
    """Whether the host says this engine answers by itself (``Records.alone``): the records handed in, else the
    process default's; off when there is no description at all."""
    if records is None:
        try:
            records = env.records()
        except RuntimeError:
            return False
    return bool(records.alone)


def check(rows: Iterable, asts: Sequence[Tuple[Any, str]], *, alone: bool = False) -> None:
    """Raise :class:`NumberRefused` if any row holds, where one of ``asts`` (``(ast, root)`` pairs) reads it as a
    double, a number it would misread (``alone``: or one past the largest double). Every row is read (the
    statement's probe reads the whole collection), and the refusal names the first such row in key order
    (``record_d``, the exact parse)."""
    wanted: List[Tuple[list, str]] = []
    for ast, root in asts:
        wanted.extend(w for w in readings(ast, root) if alone or w[1] != SORTED)
    if not wanted:
        return
    first = None
    for r in rows:
        if first is not None and r.key.encode("utf-8") >= first[0].encode("utf-8"):
            continue
        found = [f for f in (_value_kind(_resolve(r.record_d, steps), pos, alone) for steps, pos in wanted) if f]
        if found:
            # one row, several numbers: the same precedence as the probe's words (large, small, digits)
            first = (r.key, min(found, key=lambda f: _PRECEDENCE[f[0]]))
    if first is not None:
        key, (k, value) = first
        raise NumberRefused(k, key, value)


_PRECEDENCE = {LARGE: 0, SMALL: 1, DIGITS: 2}
