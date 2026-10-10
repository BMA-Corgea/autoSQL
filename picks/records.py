"""picks/records.py — what "the records" are, for one host (T-86).

The pick engine reads one table of JSON records.  Everything it needs to know
about that table is in a :class:`Records` description, handed to every call
that touches SQL or rows:

* ``table`` — the table, ``schema.name`` or ``name``.  Every host's records
  table has the same three columns: ``collection`` (which collection a record
  is in), ``key`` (unique within the collection and the partition) and
  ``data`` (its JSON, ``jsonb``);
* ``partition`` — an optional ``(column, value)``: every statement also reads
  ``<column> = <value>`` (bound as a parameter), so a table shared by many
  owners is read for one owner only;
* ``sources`` — the closed set of collections a pick may read, each with a
  plain note of its fields (``legality`` refuses any other);
* ``fold`` / ``noun_of`` — how the compiler reads field paths (``None``, or
  ``"gims"`` with the collection's noun type, ``compiler/compile.py``);
* ``series`` — the one collection that is a per-member time series, if any:
  ``{"source", "time", "member"}``.  Operations 7-9 (per hour / per day,
  the rolling window, keep-only-changed) are offered on it alone;
* ``sources_note`` — a few words appended to the unknown-source refusal;
* ``rows`` — an optional row provider ``rows(conn, collection, owner) ->
  [(key, raw_json_text)]`` for the second engine, handed the description's
  owner (the partition value, or ``None``) and bound to read that owner's
  records only; without one the engine reads the table (T-87).

Identifiers are spliced into statement text, so each is checked against a
plain identifier pattern when the description is made; values never are
(they are bound).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Tuple

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_TABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?\Z")


def _check(value: Any, pattern, what: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(f"{what} must be a plain identifier, not {value!r}")
    return value


@dataclass(frozen=True)
class Records:
    table: str
    sources: Mapping[str, str]
    partition: Optional[Tuple[str, Any]] = None
    fold: Optional[str] = None
    noun_of: Optional[Callable[[str], str]] = None
    series: Optional[Mapping[str, str]] = None
    sources_note: str = ""
    rows: Optional[Callable[[Any, str], list]] = field(default=None, compare=False)

    def __post_init__(self):
        _check(self.table, _TABLE, "the table")
        if self.partition is not None:
            if not (isinstance(self.partition, tuple) and len(self.partition) == 2):
                raise ValueError("partition must be (column, value)")
            _check(self.partition[0], _IDENT, "the partition column")
        if self.fold not in (None, "gims"):
            raise ValueError(f"unknown fold {self.fold!r}")
        if self.fold and self.noun_of is None:
            raise ValueError("a fold needs noun_of(collection) -> the noun type")
        if self.series is not None:
            if set(self.series) != {"source", "time", "member"}:
                raise ValueError("series is {source, time, member}")
            if self.series["source"] not in self.sources:
                raise ValueError(f"the series {self.series['source']!r} is not one of the sources")
            for k in ("time", "member"):
                _check(self.series[k], _IDENT, f"the series {k} field")

    # ── the SQL pieces every statement shares ────────────────────────────

    def scope(self, alias: str, params: dict, *, collection_param: str = "collection") -> str:
        """``<alias>.collection = %(collection)s`` and, with a partition,
        ``AND <alias>.<partition> = %(partition)s`` — the WHERE for one
        collection of this owner.  ``alias`` "" reads the bare columns."""
        q = f"{alias}." if alias else ""
        out = f"{q}collection = %({collection_param})s"
        if self.partition is not None:
            params["partition"] = self.partition[1]
            out += f" AND {q}{self.partition[0]} = %(partition)s"
        return out

    def compile_kwargs(self, collection: str) -> dict:
        """What the compiler is told about field paths for this collection."""
        if not self.fold:
            return {}
        return {"fold": self.fold, "noun": self.noun_of(collection)}
