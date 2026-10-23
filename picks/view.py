"""picks/view.py — what a person's clicks mean, as picks (T-86).

A screen sends a *view* — the clicks: a data set, columns, conditions and how
they join, a sort, Show, a summary, a scoreboard, fields from another data
set — and this turns it into what the engine runs: a pick (``to_pick``), a
scoreboard spec (``to_spec``), a match spec (``to_lookup``).  Every value a
person picked enters as a correctly escaped literal of the expression
language; anything this cannot honour is refused BY NAME (:class:`ViewError`),
never quietly dropped.  It also reads what the screen offers — each field's
kind, the conditions it can take, its values — out of the data
(``_read_fields``), and says how a value reads to a person (``fmt_*``).

Moved out of the demo's ``demo/server/dashboard.py``, which is its first host:
the demo keeps its own data sets, words for the answer, and routes.  What
the host says about its data sets is a :class:`Catalog`: which collection each
data set reads, the relations a board may count across, the name of the
time series, and the records description.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import json
import math
import re
from dataclasses import dataclass, field as _dc_field
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from . import doubles, env, group, legality, lookup, paths, times, zones
from .records import Records


@dataclass(frozen=True)
class Catalog:
    """What a host says about its data sets.

    * ``sources``   — data set id → the collection it reads;
    * ``relations`` — data set id → the relations a board may count across
      (``[{"to", "key", "parent_key"}]``), declared, never guessed;
    * ``series_name`` — what the time series is called on screen
      ("Heartbeats"), for the one reason that names it;
    * ``records``   — the records description (``None``: the process default).
    """
    sources: Mapping[str, str]
    relations: Mapping[str, list] = _dc_field(default_factory=dict)
    series_name: Optional[str] = None
    records: Optional[Records] = None


#: The "Show" choices.  ``None`` is "all rows" (no cap).
SHOW_CHOICES = (None, 25, 100, 500)


#: A text field with this many distinct values or fewer is offered as chips;
#: more than that, as a searchable list.
CHIP_LIMIT = 8


#: The most values a text field offers.  The largest field in the seed
#: (Samples' ID) has exactly 2,000.
VALUE_LIMIT = 2000


_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _humanize(path: str) -> str:
    words = " ".join(paths.steps(path)).replace("_", " ").split()
    text = " ".join(words) or path
    return text[:1].upper() + text[1:]


def _natural(key: str):
    """``field_2`` before ``field_10``."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", key)]


def _alias(label: str, taken: set) -> str:
    """The column name a field gets in the statement: its plain label, in
    the characters a column name may hold (``Due date`` → ``Due_date``).
    Every label starts with a capital, and every key in the seed is lower
    case, so an alias never collides with a field of the data set."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") or "Field"
    if not base[0].isalpha():
        base = "F_" + base
    base = base[:60]
    name, n = base, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    taken.add(name)
    return name


#: T-126: the setup reads a record type in two statements, however wide it is (it was one full scan per field per
#: fact: 385 statements for guts-ledger's 182 fields, 8.7 s of a widget's 9). The first: every key's JSON types and
#: counts, and in the same pass every key one level inside an object value (Python opens a key that always holds an
#: object, as before). In key order, so the field list has one fixed order (every caller orders it again: _ordered).
_SHAPE_SQL = """
SELECT x.k1, x.k2, x.t, count(*)
  FROM {table} r
 CROSS JOIN LATERAL jsonb_each(r.data) AS e(k, v)
 CROSS JOIN LATERAL (SELECT e.k AS k1, NULL::text AS k2, jsonb_typeof(e.v) AS t
                     UNION ALL
                     SELECT e.k, e2.k, jsonb_typeof(e2.v)
                       FROM jsonb_each(CASE WHEN jsonb_typeof(e.v) = 'object' THEN e.v END) AS e2(k, v)) AS x
 WHERE {scope}
 GROUP BY 1, 2, 3
 ORDER BY x.k1 COLLATE "C", x.k2 COLLATE "C" NULLS FIRST, x.t
"""

#: The second: every fact of every chosen field (``k1``, ``k2``, ``lvl``: a top-level key, or a key one level inside
#: one), one row a field in the order asked, from ONE pass that groups each row's present values by key and value
#: (``pv``; JSON null is blank, as before), so each distinct value is read once -- grouped first, then matched with
#: the chosen fields once (matched inside the per-record loop, as the planner chose on a twin twice as wide, 3 s):
#:   present, distinct   the rows holding a non-null value, and the distinct non-null values under jsonb equality
#:                       (the blank group is the rows that hold none: ``total`` is every row of the collection);
#:   the four forms      over every non-blank text value -- how many, how many look like a time, how many are
#:                       readable times with a time of day, how many are NOT a date (spec §2.4, T-114; counted per
#:                       row, so a value counts as often as it is held) -- ``picks.times.kind_counts``'s four;
#:   the span            the first and last readable time with a time of day, and apart from them the first and last
#:                       real date (T-114);
#:   the range           a number field's least and greatest;
#:   the values          a text field's distinct values in C order, read only where there are at most VALUE_LIMIT of
#:                       them (the one use past that is "more than VALUE_LIMIT": ``strings_n``).
#: Each distinct string's facts are worked out once, in materialized steps (never copied into each aggregate), and
#: the costly patterns only where a cheap test can't settle them: a readable time always looks like a time
#: (READABLE is inside LOOKS), LOOKS begins YYYY-MM-DD, and a date is exactly 10 characters.
_FACTS_SQL = """
WITH p AS (
  SELECT k1, k2, lvl, i FROM unnest(%(k1)s::text[], %(k2)s::text[], %(lvl)s::int[]) WITH ORDINALITY AS p(k1, k2, lvl, i)
), pv AS MATERIALIZED (
  SELECT p.i, g.v, g.n
    FROM (SELECT x.k1, x.k2, x.lvl, x.v, count(*) AS n
            FROM {table} r
           CROSS JOIN LATERAL jsonb_each(r.data) AS e(k, v)
           CROSS JOIN LATERAL (SELECT e.k AS k1, '' AS k2, 0 AS lvl, e.v AS v
                               UNION ALL
                               SELECT e.k, e2.k, 1, e2.v
                                 FROM jsonb_each(CASE WHEN jsonb_typeof(e.v) = 'object' THEN e.v END) AS e2(k, v)) AS x
           WHERE {scope}
             AND x.v <> 'null'::jsonb
           GROUP BY 1, 2, 3, 4) AS g
    JOIN p ON p.k1 = g.k1 AND p.k2 = g.k2 AND p.lvl = g.lvl
), s AS MATERIALIZED (
  SELECT i, t, n, length(t) AS len,
         length(t) >= 10 AND substr(t, 5, 1) = '-' AND substr(t, 8, 1) = '-'
           AND t ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([Tt ][0-9]{2}:[0-9]{2}(:[0-9]{2}([.,][0-9]+)?)?([Zz]|[+-][0-9]{2}(:?[0-9]{2}(:?[0-9]{2})?)?)?)?$' AS looks
    FROM (SELECT i, v #>> '{}' AS t, n FROM pv WHERE jsonb_typeof(v) = 'string') AS q
), sf AS MATERIALIZED (
  SELECT i, n, looks, t <> '' AS filled,
         len <> 10 OR t !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AS not_date,
         CASE WHEN looks AND len > 10 THEN xpr.time_at(t) END AS at,
         CASE WHEN looks AND len = 10 AND xpr.time_at(t) IS NOT NULL THEN t END AS day
    FROM s
), sa AS (
  SELECT i, count(*) AS strings_n,
         coalesce(sum(n) FILTER (WHERE filled), 0)::bigint AS filled_n,
         coalesce(sum(n) FILTER (WHERE filled AND looks), 0)::bigint AS looks_n,
         coalesce(sum(n) FILTER (WHERE filled AND at IS NOT NULL), 0)::bigint AS readable_n,
         coalesce(sum(n) FILTER (WHERE filled AND not_date), 0)::bigint AS not_date_n,
         min(at) AS t_lo, max(at) AS t_hi, min(day) AS d_lo, max(day) AS d_hi
    FROM sf
   GROUP BY i
), firsts AS (
  SELECT s.i, array_agg(s.t ORDER BY s.t COLLATE "C") AS strings
    FROM s JOIN sa ON sa.i = s.i AND sa.strings_n <= %(limit)s
   GROUP BY s.i
), na AS (
  SELECT i, min((v #>> '{}')::numeric) AS lo, max((v #>> '{}')::numeric) AS hi
    FROM pv
   WHERE jsonb_typeof(v) = 'number'
   GROUP BY i
), a AS (
  SELECT i, sum(n)::bigint AS present, count(*) AS distinct_n FROM pv GROUP BY i
)
SELECT p.i, coalesce(a.present, 0), coalesce(a.distinct_n, 0), sa.strings_n,
       sa.filled_n, sa.looks_n, sa.readable_n, sa.not_date_n, sa.t_lo, sa.t_hi, sa.d_lo, sa.d_hi,
       firsts.strings, na.lo, na.hi, (SELECT count(*) FROM {table} r WHERE {scope}) AS total
  FROM p
  LEFT JOIN a ON a.i = p.i
  LEFT JOIN sa ON sa.i = p.i
  LEFT JOIN firsts ON firsts.i = p.i
  LEFT JOIN na ON na.i = p.i
 ORDER BY p.i
"""


def _kind(types: set, forms: tuple) -> str:
    """One field's kind, from the JSON types its values take and ``forms`` -- (text values, how many look like a
    time, how many are readable times with a time of day, how many are not a date), counted over EVERY non-blank
    value by ``_FACTS_SQL`` (``picks.times.kind_counts`` in Python).

    * ``number`` — every value is a number;
    * ``date`` — every value is text in the form ``2026-09-03``;
    * ``time`` — every value is text, at least one is a readable time and MORE than half look like a time (T-114,
      spec §2.4): an unreadable value never loses the field -- it is left out and counted -- and one time-looking
      value never makes free text a time; exactly half is text;
    * ``text`` — every value is text;
    * ``yesno`` — every value is true or false;
    * ``mixed`` — anything else (different types in different rows).
    """
    if types == {"number"}:
        return "number"
    if types == {"string"}:
        n, looks, readable, not_date = forms
        if n and not not_date:
            return "date"
        if readable and 2 * looks > n:
            return "time"
        return "text"
    if types == {"boolean"}:
        return "yesno"
    return "mixed"


def _span_text(at) -> str:
    """A span's end in the engine's one fixed form, to the second: an instant from _FACTS_SQL (a datetime) or the
    second engine's (picks.times)."""
    return times.fixed_text(at.astimezone(_dt.timezone.utc))


#: Why a field takes no conditions, in plain words.
WHY_GROUPED = (
    "Some rows hold a list or a group of values here, so it can't be "
    "matched against one value."
)


WHY_ONLY_BLANK = "Every row is blank here, so there is nothing to match."


def _ops_for(kind: str, types: set) -> list:
    """The conditions a field can take.  A field that holds a list or a
    group of values in any row takes none: the engine compares one value
    with one value, and refuses to compare a group (measured: ``==`` on
    Samples' ``field_3`` is refused at run time for exactly that)."""
    if types & {"object", "array"}:
        return []
    if not (types - {"null"}):
        return []
    blanks = ["present", "blank"]
    if kind == "number":
        return ["eq", "ne", "gt", "lt", "ge", "le", "between"] + blanks
    if kind in ("time", "date"):
        return ["on", "after", "before", "between"] + blanks
    if kind == "text":
        return ["eq", "ne", "in"] + blanks
    if kind == "yesno":
        return ["yes", "no"] + blanks
    return blanks


#: The keys a collection's records hold, for this owner only (T-87): which
#: column names a pick may not take (the alias gate) is decided by them, so
#: another owner's field names must never reach it.
_KEYS_SQL = """
SELECT DISTINCT k COLLATE "C" AS k FROM {table} r, LATERAL jsonb_object_keys(r.data) AS k
 WHERE {scope}
 ORDER BY k
"""


def collection_keys(conn, collection: str, records=None) -> list:
    """The top-level keys of one collection's records — this owner's."""
    return [r[0] for r in _read(conn, env.records(records), _KEYS_SQL, {"collection": collection}).fetchall()]


def _read(conn, records, template: str, params: dict):
    """One of the setup reads above, for this description's table and owner."""
    params = dict(params)
    sql = template.replace("{table}", records.table).replace("{scope}", records.scope("r", params))
    return conn.execute(sql, params)


class PythonReader:
    """The field reader (``_read_fields``'s statements), answered over one owner's stored documents in Python -- for
    a host whose records aren't in Postgres (GIMS's SQLite mode).  T-114 (the foreman's ruling) moved it here from
    GIMS's ``_RowsConn`` (``api/dashboard/picks_source.py``), so the kind rule and the span have one definition: the
    host hands its documents (parsed with ``parse_float=Decimal``) and the engine reads them.

    Each statement is recognised by its exact text, rendered as the engine renders it for this description, and
    answered as Postgres would answer it over these documents; any other statement is refused by name, so an engine
    that starts asking something new fails here rather than being half-answered."""

    def __init__(self, records: Records, docs: list):
        scope = records.scope("r", {})
        self._docs = docs
        self._known = {}
        for template, fn in ((_SHAPE_SQL, self._shape), (_FACTS_SQL, self._facts), (_KEYS_SQL, self._keys)):
            self._known[template.replace("{table}", records.table).replace("{scope}", scope)] = fn

    def execute(self, sql: str, params: Optional[dict] = None) -> "_Answer":
        fn = self._known.get(sql)
        if fn is None:
            raise RuntimeError("the field reader asked a statement its Python answer does not know")
        return _Answer(fn(params or {}))

    def _shape(self, p: dict) -> list:
        n: dict = {}
        for d in self._docs:
            for k, v in d.items():
                n[(k, None, _typeof(v))] = n.get((k, None, _typeof(v)), 0) + 1
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        n[(k, k2, _typeof(v2))] = n.get((k, k2, _typeof(v2)), 0) + 1
        # ORDER BY k1 COLLATE "C", k2 COLLATE "C" NULLS FIRST, t
        order = (lambda r: (r[0].encode("utf-8"), r[1] is not None, (r[1] or "").encode("utf-8"), r[2]))
        return sorted(((k1, k2, t, c) for (k1, k2, t), c in n.items()), key=order)

    def _facts(self, p: dict) -> list:
        rows = []
        for i, (k1, k2, lvl) in enumerate(zip(p["k1"], p["k2"], p["lvl"]), 1):
            held = []                                   # the non-null values at this field, one a document
            for d in self._docs:
                v = d.get(k1, _ABSENT)
                if lvl:
                    v = v.get(k2, _ABSENT) if isinstance(v, dict) else _ABSENT
                if v is not _ABSENT and v is not None:
                    held.append(v)
            strings = [v for v in held if isinstance(v, str)]
            distinct_strings = sorted(set(strings), key=lambda v: v.encode("utf-8"))
            filled, looks, readable, not_date = times.kind_counts(strings)
            ats = [a for a in (times.instant(v) for v in strings if len(v) > 10) if a is not None]
            days = [v for v in strings if len(v) == 10 and times.instant(v) is not None]
            nums = [Decimal(v) if not isinstance(v, float) else Decimal(repr(v)) for v in held if _typeof(v) == "number"]
            rows.append((
                i, len(held), len({_distinct_key(v) for v in held}),
                len(distinct_strings) if strings else None,
                filled if strings else None, looks if strings else None,
                readable if strings else None, not_date if strings else None,
                min(ats) if ats else None, max(ats) if ats else None,
                min(days, key=lambda v: v.encode("utf-8")) if days else None,
                max(days, key=lambda v: v.encode("utf-8")) if days else None,
                distinct_strings if strings and len(distinct_strings) <= p["limit"] else None,
                min(nums) if nums else None, max(nums) if nums else None,
                len(self._docs)))
        return rows

    def _keys(self, p: dict) -> list:
        return [(k,) for k in sorted({k for d in self._docs for k in d})]


class _Answer:
    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self) -> list:
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


_ABSENT = object()


def _typeof(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float, Decimal)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def _exact_dumps(doc: Any) -> str:
    """JSON text with every Decimal written exactly."""
    def enc(v):
        if isinstance(v, dict):
            return "{" + ",".join(json.dumps(str(k)) + ":" + enc(x) for k, x in v.items()) + "}"
        if isinstance(v, (list, tuple)):
            return "[" + ",".join(enc(x) for x in v) + "]"
        if isinstance(v, Decimal):
            return str(v) if v.is_finite() else json.dumps(float(v))
        return json.dumps(v, default=str)
    return enc(doc)


def _distinct_key(v: Any) -> tuple:
    t = _typeof(v)
    if t == "number":
        return (t, Decimal(v) if not isinstance(v, float) else Decimal(repr(v)))
    if t in ("array", "object"):
        return (t, _exact_dumps(v) if t == "array" else _exact_dumps(dict(sorted(v.items()))))
    return (t, v)


def _read_fields(conn, collection: str, labels=None, records=None) -> list:
    """Every field of one data set: its path, its JSON types, its kind,
    the conditions it can take and the values found in it -- in two
    statements however many fields it has (T-126): its shape, then every
    field's facts at once."""
    records = env.records(records)
    labels = labels or {}
    with _setup_settings(conn):
        found = _found(_read(conn, records, _SHAPE_SQL, {"collection": collection}).fetchall())
        if not found:
            return []
        steps = [st for st, _ts in found.values()]
        facts = _read(conn, records, _FACTS_SQL, {
            "collection": collection, "k1": [st[0] for st in steps],
            "k2": [st[1] if len(st) > 1 else "" for st in steps],
            "lvl": [len(st) - 1 for st in steps], "limit": VALUE_LIMIT}).fetchall()
    fields = []
    for (path, (_steps, ts)), row in zip(found.items(), facts):
        (_i, present, distinct, strings_n, filled, looks, readable, not_date,
         t_lo, t_hi, d_lo, d_hi, strings, lo, hi, total) = row
        forms = (filled, looks, readable, not_date) if strings_n else (0, 0, 0, 0)
        kind = _kind(ts - {"null"}, forms)
        ops = _ops_for(kind, ts)
        field = {
            "path": path,
            "label": labels.get(path) or _humanize(path),
            "kind": kind,
            "ops": ops,
            "why_no_ops": "" if ops else (
                WHY_GROUPED if ts & {"object", "array"} else WHY_ONLY_BLANK
            ),
            "values": None,
            "picker": None,
            "range": None,
        }
        # the blank group counts as a value: the rows that hold none (absent, or JSON null)
        field["group"] = _groupable(kind, ts, field["label"], distinct + (1 if present < total else 0))
        if kind == "text" and strings_n <= VALUE_LIMIT:
            field["values"] = list(strings or [])
            field["picker"] = "chips" if len(field["values"]) <= CHIP_LIMIT else "list"
        if kind == "number" and lo is not None:
            field["range"] = {"min": _number_text(lo), "max": _number_text(hi)}
        if kind == "time" and t_lo is not None:
            # T-114: over every value, by instant -- the times' span, and the bare dates' beside it: a date's
            # midnight is each question's clock's (spec §2.1), so the axis places it there (dashboard._span)
            field["range"] = {"min": _span_text(t_lo), "max": _span_text(t_hi)}
            if d_lo is not None:
                field["range"]["dates"] = {"min": d_lo, "max": d_hi}
        elif kind == "date" and d_lo is not None:
            field["range"] = {"min": d_lo, "max": d_hi}
        fields.append(field)
    return fields


@contextlib.contextmanager
def _setup_settings(conn):
    """The setup's two statements under their own savepoint (T-126, the foreman's decision on the time bar), with
    Postgres's JIT off -- it compiled the facts statement on every run, 780 ms of 2 s on guts-ledger's twin -- and the
    pairs grouped by hash, never by sort -- a sort of its 333k field-value pairs cost 370 ms; a hash aggregate spills
    to disk past work_mem, so memory stays bounded. The caller's settings are put back before the savepoint is
    released, as ``picks.probes`` does for a probe; a statement that raises rolls the savepoint back, and the settings
    with it. A reader with no transaction (``PythonReader``) answers as it always does."""
    if not hasattr(conn, "transaction"):
        yield
        return
    with conn.transaction():
        was = conn.execute("SELECT current_setting('jit'), current_setting('enable_sort')").fetchone()
        conn.execute("SET LOCAL jit = off")
        conn.execute("SET LOCAL enable_sort = off")
        yield
        conn.execute("SELECT set_config('jit', %s, true), set_config('enable_sort', %s, true)", tuple(was))


def _found(shape: list) -> dict:
    """The fields ``_SHAPE_SQL``'s rows name: path -> (its steps, its JSON types), in the rows' (key) order. A key that
    always holds an object (Heartbeats' payload) is opened one level: its fields are what a person reads. T-88: a key
    that is not an identifier ("Sample Weight (g)") is named in brackets (picks/paths.py), and one with no name both
    engines read back as exactly that key -- empty, NUL -- is skipped."""
    types: dict = {}
    inner: dict = {}
    for k1, k2, t, _n in shape:
        if k2 is None:
            types.setdefault(k1, set()).add(t)
        else:
            inner.setdefault(k1, {}).setdefault(k2, set()).add(t)
    found: dict = {}
    for key, ts in types.items():
        if ts == {"object"}:
            for k2, ts2 in inner.get(key, {}).items():
                name = paths.name([key, k2])
                if name is not None:
                    found.setdefault(name, ([key, k2], set()))[1].update(ts2)
        else:
            name = paths.name([key])
            if name is not None:
                found[name] = ([key], set(ts))
    return found


#: One row per value works up to this many different values (T-73 AC1).
#: Chosen against the seed: the widest honest grouping is Heartbeats' 50
#: senders; the next field up is Samples' ID, 2,000 values, one row each —
#: a "scoreboard" of it is the table again.  500 is ten times the widest
#: real grouping, a quarter of the degenerate one, and ten pages of 50.
GROUP_LIMIT = 500


def _groupable(kind, types, label, n) -> dict:
    """Can the page give one row per value of this field, and if not, why
    — in plain words.  ``n``: its different values, the blank group counted
    as one (``_FACTS_SQL``)."""
    if kind not in ("text", "number", "yesno") or types & {"object", "array"}:
        why = ("Times and dates are grouped per hour, day, week or month under Summarize."
               if kind in ("time", "date") else
               "Its rows hold different kinds of value, so there is no one value to group by.")
        return {"ok": False, "why": why, "groups": None}
    if n > GROUP_LIMIT:
        return {"ok": False, "groups": n, "why": (
            f"{label} has {n:,} different values — one row per value would be about as "
            f"long as the table itself. One row per value works up to {GROUP_LIMIT} different values.")}
    return {"ok": True, "why": "", "groups": n}


def _ordered(fields: list, order: tuple) -> list:
    first = {p: i for i, p in enumerate(order)}
    return sorted(
        fields,
        key=lambda f: (first.get(f["path"], len(first)), _natural(f["path"])),
    )


class ViewError(ValueError):
    """A view this contract cannot translate — said in plain words."""


def _name(value):
    """A name a view uses to look something up (a field, a function, a
    logic, a column): the text itself, or None for anything else — so a list
    or an object where a name belongs is refused by name as unknown, never
    met with a crash at the first lookup (T-75)."""
    return value if isinstance(value, str) else None


#: Every part of a view this contract honours, and the parts of each
#: condition and sort.  Anything else is REFUSED by name, never ignored: a
#: choice the page shows but the answer drops would be a pick silently
#: ignored, which is the one thing this page must never do.
VIEW_KEYS = {"dataset", "columns", "conditions", "logic", "filter", "zone", "sort", "show", "summary",
             "scoreboard", "matched"}


CONDITION_KEYS = {"field", "op", "value", "value2", "values", "part"}


SORT_KEYS = {"field", "dir"}


#: Which value slots each condition reads.  A slot it doesn't read must be
#: empty — "", [] or null — or the condition is refused.
_SLOTS = {
    "in": {"values"}, "between": {"value", "value2"},
    "present": set(), "blank": set(), "yes": set(), "no": set(),
}


def _empty(v) -> bool:
    return v is None or v == "" or v == []


def _refuse_extra(given: dict, allowed: set, what: str) -> None:
    extra = sorted(set(given) - allowed)
    if extra:
        raise ViewError(f"This page can't use {extra[0]!r} in {what} yet.")


def view_zone(view: dict):
    """The clock a question reads its times on (T-98, GA-68 Q7): one of the zones both engines
    read (the evaluator's TIME_ZONES), or ``None`` when the question names none — read as
    before T-98, in UTC, word for word.  Anything else is refused in plain words."""
    if "zone" not in view:
        return None
    zone = view["zone"]
    known = env.time_zones()
    if not isinstance(zone, str) or zone not in known:
        shown = zone if isinstance(zone, str) else "that"
        raise ViewError(f"This page doesn't know the time zone “{shown}”. Pick one from the list.")
    return zone


def _dataset(setup_payload: dict, view: dict) -> tuple[dict, dict]:
    if not isinstance(view, dict):
        raise ViewError("The question must be a set of choices.")
    _refuse_extra(view, VIEW_KEYS, "a question")

    ds_id = view.get("dataset")
    ds = next((d for d in setup_payload["datasets"] if d["id"] == ds_id), None)
    if ds is None:
        raise ViewError("Pick one of the data sets.")
    fields = {f["path"]: f for f in ds["fields"]}
    return ds, fields


def _columns(view: dict, fields: dict) -> list:
    cols = view.get("columns")
    if cols is None:
        return []
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        raise ViewError("Columns must be a list of field names.")
    unknown = [c for c in cols if c not in fields]
    if unknown:
        raise ViewError(f"This data set has no field called {unknown[0]!r}.")
    seen: list = []
    for c in cols:
        if c not in seen:
            seen.append(c)
    return seen


def _show(view: dict):
    show = view.get("show")
    if show not in SHOW_CHOICES or isinstance(show, bool):
        raise ViewError("Show must be all rows, 25, 100 or 500.")
    return show


def to_pick(catalog: "Catalog", setup_payload: dict, view: dict) -> dict:
    """One view → one pick, in the engine's own shape.

    The chosen columns become computed columns named by their plain labels
    (``$.sender_id AS "Sender"``), so the statement visibly changes with the
    pick (AC3).  The source is chosen from a closed set of three.
    """
    ds, fields = _dataset(setup_payload, view)
    if view.get("scoreboard") is not None:
        raise ViewError("A scoreboard is answered as a scoreboard, not as rows.")
    if view.get("matched") is not None:
        # answered by matched_answer, which asks for the table without it
        raise ViewError(MATCHED_NEEDS_TABLE)
    pick = legality.default_pick(catalog.records)
    pick["source"] = catalog.sources[ds["id"]]
    pick["computed"] = [
        {"name": fields[c]["alias"], "expr": field_ref(c)}
        for c in _columns(view, fields)
    ]
    flt = filter_expression(view, fields)
    if flt:
        pick["filter"] = flt
    sort = _sort(view, fields)
    if sort:
        pick["sort"] = sort
    pick["cap"] = _show(view)
    # T-114: the time fields the filter and the sort read as instants (both engines), named in the pick
    read = time_fields_read(view, fields)
    if sort and fields[sort["field"]]["kind"] == "time" and sort["field"] not in read:
        read.append(sort["field"])
    if read:
        pick["times"] = read
    if read and view_zone(view) is not None:
        pick["times_zone"] = view_zone(view)     # T-114: they are read on the question's clock (a bare date at its midnight)

    summary = _summary(view, fields, ds)
    if summary:
        if pick["computed"]:
            raise ViewError("Columns don't apply to a summary; untick them first.")
        pick["aggregate"] = {
            "fn": summary["fn"],
            "field": summary["field"],
        }
        if summary["per"] == "category":
            # one number per value of a field is a board's shape (to_category_spec)
            raise ViewError("One number per value of a field is answered as a board, not as one pick.")
        pick["bucket"] = "off" if summary["per"] == "all" else summary["per"]
        if summary["per"] in TIME_PERS and view_zone(view) is not None:
            pick["bucket_zone"] = view_zone(view)    # T-100: cut on the question's clock
        if summary["time"]:
            pick["bucket_field"] = summary["time"]
        elif summary["per"] in TIME_PERS and not _is_series(catalog, pick["source"]):
            # T-88: any data set can be read per time once its time is named
            if not any(f["kind"] in ("time", "date") for f in fields.values()):
                raise ViewError(f"{ds['name']} have no time or date field to group by.")
            raise ViewError("Pick the time or date field to group by.")

    # The engine's own rules decide what may be combined (legality.py, the
    # same function /api/operations greys its controls from).  A choice it
    # refuses is refused here in plain words, never quietly dropped.
    for v in legality.evaluate(pick, catalog.records)["violations"]:
        raise ViewError(plain_reason(v["why"], catalog.series_name))
    return pick


#: A summary's functions, as the page names them and as the sentence does.
SUMMARY_FNS = {
    "count": "Number", "sum": "Total", "avg": "Average",
    "min": "Smallest", "max": "Largest",
}


SUMMARY_KEYS = {"fn", "field", "per", "time", "by"}


PERS = ("all", "hour", "day", "week", "month", "category")
#: The time units a summary may read over a time or date field (T-88).
TIME_PERS = ("hour", "day", "week", "month")


def _summary(view: dict, fields: dict, ds: dict):
    """The summary a view asks for, checked: None when it asks for none."""
    summary = view.get("summary")
    if summary is None:
        return None
    if not isinstance(summary, dict):
        raise ViewError("A summary must be a set of choices.")
    _refuse_extra(summary, SUMMARY_KEYS, "a summary")
    fn = summary.get("fn")
    if _name(fn) not in SUMMARY_FNS:
        raise ViewError("Summarize by count, total, average, smallest or largest.")
    per = summary.get("per", "all")
    if _name(per) not in PERS:
        raise ViewError("Summarize over everything, per hour, day, week or month, or per value of a field.")
    # T-88: the time a per-time summary reads (any time or date field; none =
    # the time series' own), and the field a per-value summary groups by.
    time = summary.get("time")
    if not _empty(time):
        if per not in TIME_PERS:
            raise ViewError("A time to group by goes with per hour, day, week or month.")
        f = fields.get(_name(time))
        if f is None or f["kind"] not in ("time", "date"):
            raise ViewError("Group by a time or a date field.")
        if per == "hour" and f["kind"] != "time":
            raise ViewError(f"{f['label']} holds dates, so there is no hour to group by.")
        time = f["path"]
    else:
        time = None
    by = summary.get("by")
    if per == "category":
        f = fields.get(_name(by))
        if f is None:
            raise ViewError("Pick the field to give one number per value of.")
        if not f["group"]["ok"]:
            raise ViewError(f"{f['label']} can't be grouped by: {f['group']['why']}")
        by = f["path"]
    elif not _empty(by):
        raise ViewError("A field to group by goes with per value of a field.")
    else:
        by = None
    path = summary.get("field")
    if fn == "count":
        if not _empty(path):
            raise ViewError("A count counts rows; it takes no field.")
        return {"fn": fn, "field": None, "per": per, "time": time, "by": by}
    if _name(path) not in fields or fields[path]["kind"] != "number":
        raise ViewError(f"{SUMMARY_FNS[fn]} of what? Pick a field that holds numbers.")
    return {"fn": fn, "field": path, "per": per, "time": time, "by": by}


def _is_series(catalog: "Catalog", source: str) -> bool:
    series = env.records(catalog.records).series
    return bool(series) and series["source"] == source


def _why_only_series(series_name) -> str:
    # the X1 reason in plain words: the time series is named by the host
    return (f"Only {series_name} have a time to group by." if series_name
            else "Only one data set has a time to group by.")


#: legality.py's reasons (the text /api/operations greys a control with),
#: each said the way this page says things.  Matched on the engine's exact
#: words, so a reason that changes there fails test_dashboard.py by name
#: instead of reaching a person.
_PLAIN_REASONS = {
    legality._WHY_SCALAR_SORT: "A summary over everything is one number, so there is nothing to sort.",
    legality._WHY_SCALAR_CAP: "A summary over everything is one number, so there is only one row.",
    legality._WHY_SCALAR_WINDOW: "A summary over everything is one number.",
    legality._WHY_SCALAR_CHANGED: "A summary over everything is one number.",
    legality._WHY_BUCKET_SORT: "Summaries per hour, day, week or month are always in time order.",
    legality._WHY_BUCKET_WINDOW: "Summaries per hour, day, week or month are grouped already.",
    legality._WHY_BUCKET_CHANGED: "Summaries per hour, day, week or month are grouped already.",
    legality.WHY_BUCKET_NEEDS_AGG: "A summary per hour, day, week or month needs something to count or total.",
    legality.WHY_COUNT_TAKES_NO_FIELD: "A count counts rows; it takes no field.",
    legality.WHY_NO_FN_NO_FIELD: "Pick what to summarize first.",
}


_PLAIN_REASON_DEFAULT = "Not available with these choices."


def plain_reason(why: str, series_name: str | None = None) -> str:
    """One of the engine's reasons → the page's words."""
    if why in _PLAIN_REASONS:
        return _PLAIN_REASONS[why]
    if why.startswith("unavailable on this source (operation 1)"):
        return _why_only_series(series_name)
    return _PLAIN_REASON_DEFAULT


def field_ref(path: str) -> str:
    """A field path as the expression language spells it: ``$.payload.load``,
    ``$["Sample Weight (g)"]`` (``picks/paths.py``, T-88)."""
    try:
        return paths.dollar(path)
    except ValueError:
        raise ViewError(f"{path!r} is not a field this page can reach.") from None


def string_literal(value: str) -> str:
    """A string as a literal of the expression language, exactly.

    ``expr.py`` reads ``"…"`` with a backslash escaping the next character
    (``\\n``, ``\\t`` and ``\\r`` excepted), so a backslash and a double
    quote are the two characters that need escaping, and the only newline
    forms that would change meaning are written back as their escapes.
    Everything else — ``'``, ``%``, ``_``, any non-ASCII — is itself.  The
    pinned compiler then binds the decoded value as a parameter: nothing a
    person picks is ever spliced into the statement's text.
    """
    if not isinstance(value, str):
        raise ViewError("A text value must be text.")
    # The database's text cannot hold a NUL, and a lone surrogate is not a
    # character at all: both are refused here, by name, before any SQL.
    if "\x00" in value or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ViewError("That value holds a character the data can't store.")
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


#: A number typed as text (T-112, run 11's fold-in): the language's own number grammar in ASCII -- an optional sign,
#: digits with an optional point, an optional exponent. Nothing else is read as a number here.
_TYPED_NUMBER = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_JS_PLAIN = Decimal("1e21")         # below it JSON.stringify writes an integer's digits, as a JSON number reached here
_TYPED_WORDS = {doubles.LARGE: "That number is too large to compare with.",
                doubles.SMALL: "That number is too small to compare with.",
                doubles.DIGITS: "That number has more digits than can be compared exactly."}


def number_literal(value) -> str:
    """A number as a literal of the expression language: a finite JSON number, or the text a person typed (the
    number box sends what was typed, so the engine reads exactly that). Typed text is read by T-112's rule: held,
    it is written as the JSON number for it is (an integer below 1e21 in its digits, as ``JSON.stringify`` writes
    one; anything else as Postgres writes its double); not held, it is refused in words before any SQL. ``-5`` is
    the language's own unary minus."""
    if isinstance(value, str):
        if not _TYPED_NUMBER.fullmatch(value):
            raise ViewError("A number value must be a number.")
        exact = Decimal(value)
        kind = doubles.kind(exact)
        if kind is not None:
            raise ViewError(_TYPED_WORDS[kind])
        if exact == exact.to_integral_value() and exact.copy_abs() < _JS_PLAIN:
            return str(int(exact))
        return doubles.pg_shortest(float(exact))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ViewError("A number value must be a number.")
    try:
        as_double = float(value)
    except OverflowError:
        raise ViewError("That number is too large to compare with.") from None
    if not math.isfinite(as_double):
        raise ViewError("That number is too large to compare with.")
    if isinstance(value, int):
        # T-112: an integer with more digits than a double holds would be compared as a different number
        if doubles.kind(value) == doubles.DIGITS:
            raise ViewError("That number has more digits than can be compared exactly.")
        return str(value)
    # a float is already a double (the request's own reading): written as Postgres writes it, so the literal is
    # held and means exactly that double (``repr`` except on a midpoint, T-112)
    return doubles.pg_shortest(float(value))


_DAY_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\Z")


_MINUTE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?Z?\Z")


def _day(value) -> _dt.date:
    if not isinstance(value, str) or not _DAY_RE.match(value):
        raise ViewError("A day must be picked as a date.")
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise ViewError("A day must be picked as a date.") from None


def _instant(value, zone=None) -> str:
    """A picked time → its UTC instant in the data's fixed form (``2026-08-18T06:00:00Z``), with its fraction when
    it has one (T-114: GIMS's day end, the day's last microsecond, ``…23:59:59.999999Z``).  With a zone (T-98) the
    time is a wall time on that clock — the first of two on a day the clocks go back, a skipped one refused in
    words — unless it ends in ``Z``, which says UTC."""
    m = _MINUTE_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise ViewError("A time must be picked as a date and a time.")
    day = _day(m.group(1))
    hh, mm, ss = int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    if hh > 23 or mm > 59 or ss > 59:
        raise ViewError("A time must be picked as a date and a time.")
    if zone is not None and not value.endswith("Z"):
        try:
            t = zones.wall_instant(day, hh, mm, ss, zone)
        except zones.ZoneError as exc:
            raise ViewError(str(exc)) from None
    else:
        t = times.fixed_text(_dt.datetime(day.year, day.month, day.day, hh, mm, ss))
    if m.group(5):                      # an offset is whole minutes, so the fraction rides on the UTC instant
        t = f"{t[:-1]}.{m.group(5).ljust(6, '0')}Z"
    return t


def _marked(t: str) -> str:
    """An instant at the one width (``_wide``) as a bare date of that instant reads (``picks.times.reading_on``): its Z
    replaced by the date mark, which sorts it just ahead of a time at that very instant."""
    return _wide(t)[:-1] + times.DATE_MARK


def _day_start(day: _dt.date, zone=None) -> str:
    """A day's first instant on the question's clock (UTC's with none), as that day's bare date reads (marked)."""
    return times.utc_text(times.midnight(day.isoformat(), zone))[:-1] + times.DATE_MARK


def _day_end(day: _dt.date, zone=None):
    """Where a day on the question's clock ends, marked as ``_day_start``: the next day's first instant. The
    calendar's last day has no next and ends at the clock's last instant (t98-23): east of UTC an instant this reads
    (Dec 31, 9999 ends at 18:30Z on Kolkata), on UTC and west of it past them all (``None``: no end)."""
    if day < _dt.date.max:
        return _day_start(day + _dt.timedelta(days=1), zone)
    if zone is None:
        return None
    last = _dt.datetime.combine(day, _dt.time.max)
    try:
        end = last - zones.ZoneInfo(zone).utcoffset(last) + _dt.timedelta(microseconds=1)
    except OverflowError:
        return None
    return times.utc_text(end.replace(tzinfo=_dt.timezone.utc))[:-1] + times.DATE_MARK


def _time_condition(field: dict, ref: str, op: str, cond: dict, zone, said: str) -> tuple[str, str]:
    """after / before / between on a time field: one window over its reading (``picks.times.reading_on``, once a
    row), which puts a time at its instant and a bare date at the first instant of its day on the question's clock,
    just ahead of a time at that very instant (T-114: one reading for every reader; a-chk's cost MEDIUM: e00a5d8's
    own shape). After T: past T's own instant. Before T: ahead of T as a bare date there would read. Between A and
    B: from A as a bare date would read to B's own instant."""
    if op == "between":
        lo, hi = cond.get("value"), cond.get("value2")
        a, said_a = _value_for(field, lo, zone)
        b, said_b = _value_for(field, hi, zone)
        if _order_key(field, lo, zone) > _order_key(field, hi, zone):      # "between 5 PM and 9 AM", in order
            (a, said_a, lo), (b, said_b, hi) = (b, said_b, hi), (a, said_a, lo)
        return (f"{ref} >= {string_literal(_marked(_instant(lo, zone)))} and {ref} <= {b}",
                f"{said} {said_a} and {said_b}")
    lit, said_t = _value_for(field, cond.get("value"), zone)
    if op == "after":
        return f"{ref} > {lit}", f"{said} {said_t}"
    return f"{ref} < {string_literal(_marked(_instant(cond.get('value'), zone)))}", f"{said} {said_t}"


def _wide(t: str) -> str:
    """A UTC instant in the data's fixed form → the one width a time is compared at (T-114): to the microsecond,
    so text order is time order whatever form each stored time was written in (``picks.times.utc_text``)."""
    return t if "." in t else f"{t[:-1]}.000000Z"


_CLOCK_RE = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?\Z")


def _clock(value) -> int:
    """A picked time of day (``17:00`` or ``17:00:15``, 24-hour) → seconds since midnight."""
    m = _CLOCK_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise ViewError("A time of day is picked as hours and minutes, such as 17:00.")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)


#: The words each condition reads as, by kind.  The screen shows these in
#: its condition picker; the sentence uses them too, so the two agree.
OP_WORDS = {
    "eq": "is", "ne": "is not", "in": "is one of",
    "gt": "is more than", "lt": "is less than",
    "ge": "is at least", "le": "is at most", "between": "is between",
    "on": "is on", "after": "is after", "before": "is before",
    "yes": "is yes", "no": "is no",
    "present": "has a value", "blank": "is blank",
    "from": "from", "until": "until",
}

#: A time field's time of day (T-98, GA-68 Q6): the conditions it takes and how they read.
#: "from" takes the time itself, "until" stops just before it, "between" wraps midnight.
TIME_OF_DAY_OPS = ("from", "until", "between")
TIME_OF_DAY_WORDS = {"from": "from", "until": "until", "between": "between"}


#: The most values one "is one of" may carry.
IN_LIMIT = 200


def _value_for(field: dict, value, zone=None):
    """One picked value → (its literal, how the sentence reads it)."""
    kind = field["kind"]
    if kind == "number":
        literal = number_literal(value)
        # typed text is said as it is compared ("12.50" as 12.5); a JSON number as it always was
        return literal, fmt_number(literal if isinstance(value, str) else str(value))
    if kind == "time":
        t = _instant(value, zone)
        return string_literal(_wide(t)), fmt_time(t, zone)
    if kind == "date":
        d = _day(value).isoformat()
        return string_literal(d), fmt_date(d)
    return string_literal(value), said_text(value)


def said_text(value: str) -> str:
    """A text value as the sentence says it: bare when it is one word
    (``Status is warn``), in quotes when it is empty or holds a space, so
    ``S is not “not a number”`` cannot read as a double negative."""
    if value == "" or any(ch.isspace() for ch in value):
        return f"“{value}”"
    return value


def _order_key(field: dict, value, zone=None):
    if field["kind"] == "number":
        return value
    if field["kind"] == "time":
        return times.instant(_instant(value, zone))
    if field["kind"] == "date":
        return _day(value).isoformat()
    return value


def _time_of_day(field: dict, cond: dict, zone) -> tuple[str, str]:
    """A time field's time of day on the question's clock (T-98): ``time_of_day($.ts, "<zone>")``,
    whole seconds since that clock's midnight, the one name GA-68 Q6 added to the gate."""
    label = f"{field['label']} (time of day)"
    if field["kind"] != "time":
        raise ViewError(f"{field['label']} has no time of day.")
    op = cond.get("op")
    if op not in TIME_OF_DAY_OPS:
        raise ViewError(f"{label} can't be matched that way.")
    reads = {"value", "value2"} if op == "between" else {"value"}
    unread = [k for k in ("value", "value2", "values") if k not in reads and not _empty(cond.get(k))]
    if unread:
        slot = {"value": "value", "value2": "second value", "values": "list of values"}[unread[0]]
        raise ViewError(f"“{label} {TIME_OF_DAY_WORDS[op]}” takes no {slot}.")
    t = f"time_of_day({field_ref(field['path'])}, {string_literal(zone or 'UTC')})"
    a = _clock(cond.get("value"))
    if op == "from":
        return f"{t} >= {a}", f"{label} from {zones.clock_words(a)}"
    if op == "until":
        return f"{t} < {a}", f"{label} until {zones.clock_words(a)}"
    b = _clock(cond.get("value2"))
    if a == b:
        raise ViewError(f"Pick two different times for {label}.")
    # from a until b; when a is later than b the window wraps midnight
    joined = "and" if a < b else "or"
    return (f"({t} >= {a} {joined} {t} < {b})",
            f"{label} between {zones.clock_words(a)} and {zones.clock_words(b)}")


def condition(field: dict, cond: dict, zone=None) -> tuple[str, str]:
    """One clicked condition → (its expression, its words in the sentence).

    The expression is only ever comparisons, ``and``, ``or`` and ``null`` —
    every one inside the gate's subset — over one field read with ``$.``
    and values written by :func:`string_literal` / :func:`number_literal`;
    and, for a time field's time of day, the gate's ``time_of_day`` (T-98).

    ``zone`` (T-98): the question's clock.  A time field's day, its picked
    times and its time of day are read on it; ``None`` is UTC, as before.
    """
    _refuse_extra(cond, CONDITION_KEYS, "a condition")
    part = cond.get("part")
    if part is not None:
        if part != "time_of_day":
            raise ViewError("A condition reads a field, or a time field's time of day.")
        return _time_of_day(field, cond, zone)
    op = cond.get("op")
    if op not in field["ops"]:
        raise ViewError(f"{field['label']} can't be matched that way.")
    reads = _SLOTS.get(op, {"value"})
    unread = [k for k in ("value", "value2", "values")
              if k not in reads and not _empty(cond.get(k))]
    if unread:
        slot = {"value": "value", "value2": "second value",
                "values": "list of values"}[unread[0]]
        raise ViewError(f"“{field['label']} {OP_WORDS[op]}” takes no {slot}.")
    ref = field_ref(field["path"])
    label = field["label"]
    words = OP_WORDS[op]

    if op == "present":
        return f"{ref} != null", f"{label} {words}"
    if op == "blank":
        return f"{ref} == null", f"{label} {words}"
    if op in ("yes", "no"):
        return f"{ref} == {'true' if op == 'yes' else 'false'}", f"{label} {words}"

    if op == "in":
        values = cond.get("values")
        if not isinstance(values, list) or not values:
            raise ViewError(f"Pick at least one value for {label}.")
        if len(values) > IN_LIMIT:
            raise ViewError(f"Pick at most {IN_LIMIT} values for {label}.")
        if not all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in values):
            raise ViewError(f"Each value for {label} must be one value.")
        unique = list(dict.fromkeys(values))
        # one value however it was written (typed "12.50" and 12.5 are one number): one per literal
        pairs = list({lit: (lit, said) for lit, said in (_value_for(field, v, zone) for v in unique)}.values())
        if len(pairs) == 1:
            lit, said = pairs[0]
            return f"{ref} == {lit}", f"{label} is {said}"
        expr = " or ".join(f"{ref} == {lit}" for lit, _ in pairs)
        said = [s for _, s in pairs]
        return f"({expr})", f"{label} is {', '.join(said[:-1])} or {said[-1]}"

    if op == "on" and field["kind"] == "time":
        d = _day(cond.get("value"))
        # T-114: one window over the reading -- the day's first instant on the question's clock to the next day's,
        # each as that day's bare date reads, so the day's own bare date is in and the next one's out (DST-correct);
        # the calendar's last day has no next (a-chk's MEDIUM-2: never an OverflowError)
        start = f"{ref} >= {string_literal(_day_start(d, zone))}"
        end = _day_end(d, zone)
        if end is None:
            return start, f"{label} {words} {fmt_day(d.isoformat())}"
        return f"{start} and {ref} < {string_literal(end)}", f"{label} {words} {fmt_day(d.isoformat())}"

    if field["kind"] == "time" and op in ("after", "before", "between"):
        return _time_condition(field, ref, op, cond, zone, f"{label} {words}")

    if op == "between":
        lo, hi = cond.get("value"), cond.get("value2")
        a, said_a = _value_for(field, lo, zone)
        b, said_b = _value_for(field, hi, zone)
        # "between 50 and 10" means the same as "between 10 and 50" to a
        # person; the two ends are put in order rather than matching nothing.
        key = (lambda v: float(v)) if field["kind"] == "number" else (lambda v: v)
        if key(_order_key(field, lo, zone)) > key(_order_key(field, hi, zone)):
            (a, said_a), (b, said_b) = (b, said_b), (a, said_a)
        return (f"({ref} >= {a} and {ref} <= {b})",
                f"{label} {words} {said_a} and {said_b}")

    sym = {"eq": "==", "on": "==", "ne": "!=", "gt": ">", "lt": "<",
           "ge": ">=", "le": "<=", "after": ">", "before": "<"}[op]
    lit, said = _value_for(field, cond.get("value"), zone)
    return f"{ref} {sym} {lit}", f"{label} {words} {said}"


def _conditions(view: dict, fields: dict) -> list:
    conds = view.get("conditions") or []
    if not isinstance(conds, list):
        raise ViewError("Conditions must be a list.")
    out = []
    for c in conds:
        if not isinstance(c, dict) or _name(c.get("field")) not in fields:
            raise ViewError("A condition names a field this data set doesn't have.")
        out.append(condition(fields[c["field"]], c))
    return out


#: How a set of conditions joins (T-73 AC3), as the page names each.  For two
#: conditions "one" and "allnone" are XOR and XNOR; for three or more they
#: are their names — exactly one holds / all hold or none does.
LOGICS = {
    "all": "All of these",
    "any": "Any of these",
    "one": "Exactly one of these",
    "allnone": "All of these, or none of them",
}


WHY_LOGIC_NEEDS_TWO = "needs two or more conditions"


def _logic(value, n: int, where: str) -> str:
    logic = "all" if value is None else value
    if _name(logic) not in LOGICS:
        raise ViewError(f"{where} joins its conditions by all, any, exactly one, or all or none.")
    if logic in ("one", "allnone") and n < 2:
        raise ViewError(f"“{LOGICS[logic]}” {WHY_LOGIC_NEEDS_TWO}.")
    return logic


def compose(exprs: list, logic: str) -> str | None:
    """A set of condition expressions → ONE expression of the language both
    engines already share, so neither engine needs a new rule:

    * all     ``(a) and (b) and (c)``
    * any     ``(a) or (b) or (c)``
    * one     ``(if(a, 1, 0) + if(b, 1, 0) + if(c, 1, 0)) == 1``
    * allnone ``(S) == 0 or (S) == k`` with S that same sum, k the count

    ``if`` reads each condition by the language's truthiness, so each one
    holds on a row exactly when it would keep that row as a filter (a row
    without the field: ``is`` fails, ``is not`` holds).
    """
    if not exprs:
        return None
    if len(exprs) == 1 and logic in ("all", "any"):
        return exprs[0]
    if logic == "all":
        return " and ".join(f"({e})" for e in exprs)
    if logic == "any":
        return " or ".join(f"({e})" for e in exprs)
    total = "(" + " + ".join(f"if({e}, 1, 0)" for e in exprs) + ")"
    if logic == "one":
        return f"{total} == 1"
    return f"({total} == 0) or ({total} == {len(exprs)})"


def composed_length(lengths: list, logic: str) -> int:
    """How long :func:`compose` would make its text, from its parts' lengths
    alone — so a filter is measured before it is built (T-96: "all or none"
    writes its sum twice, and one inside another doubles at every level)."""
    n = len(lengths)
    if not n:
        return 0
    if n == 1 and logic in ("all", "any"):
        return lengths[0]
    if logic == "all":
        return sum(lengths) + 2 * n + 5 * (n - 1)
    if logic == "any":
        return sum(lengths) + 2 * n + 4 * (n - 1)
    total = sum(lengths) + 10 * n + 3 * (n - 1) + 2
    if logic == "one":
        return total + 5
    return 2 * total + 17 + len(str(n))


def joined_words(said: list, logic: str) -> str:
    """The conditions as the sentence says them, joined by their logic."""
    if len(said) == 1:
        return said[0]
    if logic == "all":
        return " and ".join(said)
    if logic == "any":
        return " or ".join(said)
    listed = ", ".join(said[:-1]) + " and " + said[-1]
    if logic == "one":
        return f"exactly one of: {listed}"
    return f"all or none of: {listed}"


# ── T-96: the filter is a tree of boxes, any depth ──────────────────────
#
# ``{"version": 1, "join": "all", "items": [card, {"join": "any", "items": [...]}, ...]}``:
# a box joins its items by one of LOGICS; an item with ``items`` is a box,
# any other item is a card (a condition).  Stored in the pick as it is sent,
# so a host (GIMS T-91) keeps it with no migration.  The old flat
# ``{conditions, logic}`` is read as a one-box tree.  The tree composes into
# ONE expression of the language both engines share (compose, recursively):
# neither engine has a rule of its own for it.

FILTER_VERSION = 1
FILTER_KEYS = {"version", "join", "items"}
BOX_KEYS = {"join", "items"}

#: How the screen's chip between two items names each join.
JOIN_CHIPS = {"all": "AND", "any": "OR", "one": "exactly one of", "allnone": "all or none of"}

#: A tree deeper than this is refused before it is walked (a box of one
#: adds no bracket, so the text's own depth can't bound the tree's).
MAX_GROUP_DEPTH = 64

TOO_LONG = "This filter is too long to check. Take out a condition or a group."
TOO_DEEP = "These groups go too deep to check. Take a group out of another."
TOO_MANY_IN_A_ROW = "This filter joins too many conditions in one row to check. Put some of them in groups."
CANT_CHECK = "This filter can't be checked as it is. Take out the last condition or group you added."


def filter_tree(holder: dict, what: str = "A question") -> dict:
    """The filter a question (or a count column) asks for, as its root box
    ``{"join", "items"}`` — the tree as sent, or the old flat form read as one box."""
    flt = holder.get("filter")
    conds, logic = holder.get("conditions"), holder.get("logic")
    if flt is not None:
        if not _empty(conds) or logic is not None:
            raise ViewError(f"{what} sends its filter once.")
        if not isinstance(flt, dict):
            raise ViewError("A filter must be a set of choices.")
        _refuse_extra(flt, FILTER_KEYS, "a filter")
        version = flt.get("version")
        if type(version) is not int or version != FILTER_VERSION:
            raise ViewError(f"This page reads filters of version {FILTER_VERSION}.")
        if not isinstance(flt.get("items"), list):
            raise ViewError("A filter's items must be a list.")
        return {"join": flt.get("join"), "items": flt["items"]}
    if conds is None:
        conds = []
    if not isinstance(conds, list):
        raise ViewError("Conditions must be a list.")
    return {"join": logic, "items": conds}


def _deeper_than(items: list, limit: int) -> bool:
    """Is any box more than ``limit`` levels below the root?  Walked without
    recursion, so a hostile tree is refused in words, never by a stack."""
    stack = [(items, 0)]
    while stack:
        its, depth = stack.pop()
        if depth > limit:
            return True
        for it in its if isinstance(its, list) else []:
            if isinstance(it, dict) and isinstance(it.get("items"), list):
                stack.append((it["items"], depth + 1))
    return False


def _box(box: dict, fields: dict, where: str, zone=None) -> tuple:
    """One box → (its expression, its words, how many live items).  A box
    that holds nothing adds nothing; a box of one is that one item.

    T-114 (the foreman's ruling 3): a time no reading can tell -- present, but no readable time -- holds no condition,
    negated ones included.  A condition reading a time's instant is then neither true nor definitely false, so a box
    that negates its items ("exactly one", "all or none") and holds such a condition asks each item both questions
    (:func:`_kleene`, :func:`_fails`); every other box is written exactly as before."""
    parts = []
    live = []
    for item in box["items"]:
        if isinstance(item, dict) and "items" in item:
            _refuse_extra(item, BOX_KEYS, "a group")
            if not isinstance(item["items"], list):
                raise ViewError("A group's items must be a list.")
            expr, words, n = _box(item, fields, "A group", zone)
            if expr is None:
                continue
            # a group of two or more reads in brackets in the sentence
            parts.append((expr, f"({words})" if n >= 2 else words))
        else:
            if not isinstance(item, dict) or _name(item.get("field")) not in fields:
                raise ViewError("A condition names a field this data set doesn't have.")
            parts.append(condition(fields[item["field"]], item, zone))
        live.append(item)
    logic = _logic(box.get("join"), len(parts), where)
    if not parts:
        return None, None, 0
    # Measured before it is built: every part is already within the limit,
    # so no box ever builds a text much longer than the limit allows.
    if composed_length([len(e) for e, _ in parts], logic) > _source_limit():
        raise ViewError(TOO_LONG)
    if logic in ("one", "allnone") and any(_reads_any_instant(it, fields) for it in live):
        holds = [e for e, _ in parts]
        expr = _kleene(holds, [_fails(it, e, fields, zone) for it, e in zip(live, holds)], logic)[0]
        if _source_limit() < len(expr):
            raise ViewError(TOO_LONG)
        return expr, joined_words([w for _, w in parts], logic), len(parts)
    return (compose([e for e, _ in parts], logic), joined_words([w for _, w in parts], logic), len(parts))


def _reads_any_instant(item, fields: dict) -> bool:
    """Does this card, or any card in this group, read a time field's instant (T-114)?"""
    if isinstance(item, dict) and "items" in item:
        return any(_reads_any_instant(it, fields) for it in item["items"] if isinstance(it, dict))
    return isinstance(item, dict) and item.get("field") in fields and _reads_instant(fields[item["field"]], item)


def _fails(item, holds: str, fields: dict, zone) -> str:
    """When an item (whose expression is ``holds``) definitely fails (T-114): a condition reading a time's instant
    fails when it doesn't hold AND its field is not a present time no reading can tell (the engines hand such a value
    to the filter as false; a blank stays null, and fails as it always did); a group by Kleene's rules over its own
    items; anything else simply when it doesn't hold."""
    if not _reads_any_instant(item, fields):
        return f"not ({holds})"
    if "items" not in item:
        return f"not ({holds}) and {field_ref(fields[item['field']]['path'])} != false"
    sub_live, sub_holds = [], []
    for it in item["items"]:
        if isinstance(it, dict) and "items" in it:
            e, _w, _n = _box(it, fields, "A group", zone)
            if e is None:
                continue
        else:
            e, _w = condition(fields[it["field"]], it, zone)
        sub_live.append(it)
        sub_holds.append(e)
    logic = _logic(item.get("join"), len(sub_holds), "A group")
    return _kleene(sub_holds, [_fails(it, e, fields, zone) for it, e in zip(sub_live, sub_holds)], logic)[1]


#: the conditions that read a time field's instant (T-114, spec §4); present and blank read none
_INSTANT_OPS = ("on", "after", "before", "between")


def _reads_instant(field: dict, card: dict) -> bool:
    return field["kind"] == "time" and (card.get("part") == "time_of_day" or card.get("op") in _INSTANT_OPS)


def _kleene(holds: list, fails: list, logic: str) -> tuple:
    """(the box holds, the box definitely fails), from each item's two answers -- both can be false: Kleene's AND,
    OR, exactly one, and all or none, in the language both engines share (``if`` reads each by truthiness).
    Exactly one and all or none each have two exact forms, the counts and and / or alone (an item never both holds
    and fails, so they agree), and each is written in the shorter: the language's == reads a count three times over,
    in the statement and its probes (a-chk's cost on 506e4b2), and the shorter is never longer than the counts."""
    if len(holds) == 1 and logic in ("all", "any"):
        return holds[0], fails[0]
    if logic == "all":
        return " and ".join(f"({h})" for h in holds), " or ".join(f"({f})" for f in fails)
    if logic == "any":
        return " or ".join(f"({h})" for h in holds), " and ".join(f"({f})" for f in fails)
    n = len(holds)
    nh = "(" + " + ".join(f"if({h}, 1, 0)" for h in holds) + ")"
    nf = "(" + " + ".join(f"if({f}, 1, 0)" for f in fails) + ")"
    both = (lambda xs, join: f" {join} ".join(f"({x})" for x in xs))
    if logic == "one":
        counts = f"({nh} == 1) and ({nf} == {n - 1})", f"({nh} >= 2) or ({nf} == {n})"
        # one holds and every other fails; two hold, or all fail
        plain = (both([both([holds[i]] + fails[:i] + fails[i + 1:], "and") for i in range(n)], "or"),
                 both([both([holds[i], holds[j]], "and") for i in range(n) for j in range(i + 1, n)]
                      + [both(fails, "and")], "or"))
    else:
        counts = f"({nh} == {n}) or ({nf} == {n})", f"({nh} >= 1) and ({nf} >= 1)"
        plain = (f"({both(holds, 'and')}) or ({both(fails, 'and')})",
                 f"({both(holds, 'or')}) and ({both(fails, 'or')})")
    return tuple(min(p, c, key=len) for p, c in zip(plain, counts))


def _source_limit() -> int:
    """The longest text the parser both engines use will read."""
    return getattr(env.get("parser"), "MAX_SOURCE_LEN", 2000)


def checked_filter(expr: str | None) -> str | None:
    """A composed filter, measured as the engines will measure it — by the
    parser both use — and refused in words past any of its limits: its
    length, its brackets' depth, its syntax tree's depth.  Never a parse
    error on screen."""
    if expr is None:
        return None
    parser = env.get("parser")
    if len(expr) > _source_limit():
        raise ViewError(TOO_LONG)
    try:
        parser.parse(expr)
    except Exception as exc:  # noqa: BLE001 — every parser refusal is said in words
        said = str(exc).lower()
        if "nesting" in said:
            raise ViewError(TOO_DEEP) from None
        if "deep" in said or "depth" in said:
            raise ViewError(TOO_MANY_IN_A_ROW) from None
        raise ViewError(CANT_CHECK) from None
    return expr


def filter_parts(holder: dict, fields: dict, what: str = "A question", where: str = "Only rows where",
                 zone=None) -> tuple:
    """(expression, words) of the filter a question or a count column asks
    for — (None, None) when it asks for none.  Every limit is checked.
    ``zone``: the question's clock (a count column reads its question's)."""
    tree = filter_tree(holder, what)
    if _deeper_than(tree["items"], MAX_GROUP_DEPTH):
        raise ViewError(TOO_DEEP)
    expr, words, _n = _box(tree, fields, where, zone)
    return checked_filter(expr), words


def filter_expression(view: dict, fields: dict) -> str | None:
    """The page's filter as one expression: ``(a) and ((b) or (c))``."""
    return filter_parts(view, fields, zone=view_zone(view))[0]


def filter_words(view: dict, fields: dict) -> str | None:
    """The page's filter as the sentence says it: ``Time is on Aug 20 and
    (Status is warn or Status is error)``."""
    return filter_parts(view, fields, zone=view_zone(view))[1]


def filter_reads_clock(holder: dict, fields: dict) -> bool:
    """Does any card read a time on the question's clock — a time field's day, a picked time or
    its time of day (T-98)?  The sentence then names the clock once."""
    for c in _cards(holder):
        f = fields.get(c.get("field")) if isinstance(c.get("field"), str) else None
        if f and f["kind"] == "time" and (c.get("part") == "time_of_day"
                                           or c.get("op") not in ("present", "blank")):
            return True
    return False


def time_fields_read(holder: dict, fields: dict) -> list:
    """The time fields a filter's conditions read as instants (T-114, the foreman's (A)): the pick names them
    (``times``), and both engines hand each to the filter as its UTC instant at one width -- false for a value that
    is no readable time, null for a blank."""
    out = []
    for c in _cards(holder):
        f = fields.get(c.get("field")) if isinstance(c.get("field"), str) else None
        if f and _reads_instant(f, c) and f["path"] not in out:
            out.append(f["path"])
    return out


def _cards(holder: dict) -> list:
    """Every card of a filter, at any depth (the tree as sent, or the old flat form)."""
    out, stack = [], []
    flt = holder.get("filter")
    for items in ((flt.get("items") if isinstance(flt, dict) else None), holder.get("conditions")):
        if isinstance(items, list):
            stack.append(items)
    while stack:
        for it in stack.pop():
            if isinstance(it, dict):
                if "items" in it:
                    if isinstance(it["items"], list):
                        stack.append(it["items"])
                else:
                    out.append(it)
    return out


def filter_fields(holder: dict) -> list:
    """Every field a filter's cards name, at any depth, the tree as sent or
    the old flat form — for the Everyone view's hidden-field rule.  Lenient:
    what is malformed is refused where the filter is read."""
    return [c.get("field") for c in _cards(holder)]


#: How each kind reads a sort direction.
SORT_WORDS = {
    "time": {"desc": "newest first", "asc": "oldest first"},
    "date": {"desc": "latest first", "asc": "earliest first"},
    "number": {"desc": "largest first", "asc": "smallest first"},
    "text": {"asc": "A to Z", "desc": "Z to A"},
    "yesno": {"desc": "yes first", "asc": "no first"},
}


def _sort(view: dict, fields: dict):
    sort = view.get("sort")
    if sort is None:
        return None
    if not isinstance(sort, dict) or _name(sort.get("field")) not in fields:
        raise ViewError("Sort by a field of this data set.")
    _refuse_extra(sort, SORT_KEYS, "a sort")
    field = fields[sort["field"]]
    if field["kind"] not in SORT_WORDS:
        raise ViewError(f"{field['label']} can't be sorted: its rows hold different kinds of value.")
    if sort.get("dir") not in ("asc", "desc"):
        raise ViewError("Sort one way or the other.")
    return {"field": field["path"], "dir": sort["dir"]}


def sort_words(view: dict, fields: dict) -> str:
    sort = _sort(view, fields)
    if not sort:
        return ""
    field = fields[sort["field"]]
    words = SORT_WORDS[field["kind"]][sort["dir"]]
    if field["path"] == "ts":
        return words
    return f"by {field['label']}, {words}"


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_time(text: str, zone=None) -> str:
    """``2026-08-20T23:00:00Z`` → ``Aug 20, 23:00 UTC``; ``…23:00:15Z`` →
    ``Aug 20, 23:00:15 UTC``.  On a question's clock (T-98) the time reads as
    that clock shows it, ``Aug 20, 5:00 PM`` in Denver: the screen names the
    clock once, not in every cell."""
    at = times.instant(text) if isinstance(text, str) and len(text) > 10 else None
    if at is None:
        return text                         # T-114: any readable form reads as its instant; anything else as it is
    t = at.replace(tzinfo=None)
    seconds = f":{t.second:02d}" if t.second else ""      # shown when not zero (T-75)
    if zone is not None:
        try:
            local = at.astimezone(zones.ZoneInfo(zone))
        except OverflowError:
            # t98-23: a time this clock can't show (read on it, it leaves the calendar) says what's stored, in UTC
            # words with its year -- never a made-up local time, never a 500
            return f"{_MONTHS[t.month - 1]} {t.day}, {t.year}, {t.hour:02d}:{t.minute:02d}{seconds} UTC"
        return (f"{_MONTHS[local.month - 1]} {local.day}, "
                f"{zones.clock_words(local.hour * 3600 + local.minute * 60 + local.second)}")
    return f"{_MONTHS[t.month - 1]} {t.day}, {t.hour:02d}:{t.minute:02d}{seconds} UTC"


def fmt_date(text: str) -> str:
    """``2026-09-03`` → ``Sep 3, 2026``."""
    try:
        d = _dt.date.fromisoformat(text)
    except ValueError:
        return text
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def fmt_day(text: str) -> str:
    """``2026-08-14…`` → ``Aug 14``."""
    try:
        d = _dt.date.fromisoformat(text[:10])
    except ValueError:
        return text
    return f"{_MONTHS[d.month - 1]} {d.day}"


def _number_text(value) -> str:
    """A number read from the database, as plain text: ``100``, ``-523.1234``,
    and an exponent only past fifteen digits (``1e+300``)."""
    d = Decimal(value) if not isinstance(value, Decimal) else value
    if d.copy_abs() >= Decimal("1e15"):              # exact: abs() rounds to the default context's 28 digits
        return format(_normal(d), "e").replace("E", "e")
    return format(_normal(d), "f")


#: Past these, a number reads as an exponent (``1e+300``): grouping 301
#: digits, or rounding them to two places, makes nothing easier to read.
_PLAIN_MAX_ADJUSTED = 15     # 1,000,000,000,000,000 and up


_PLAIN_MIN_ADJUSTED = -6     # below 0.000001


def _normal(d: Decimal) -> Decimal:
    """``d`` without trailing zeros, EXACTLY: ``Decimal.normalize`` rounds to
    the default context's 28 digits, which would lose digits of a long
    number."""
    return d.normalize(Context(prec=max(28, len(d.as_tuple().digits))))


def fmt_number(text: str, *, places: int | None = None) -> str:
    """Thousands separators, the digits otherwise as stored.

    ``places`` rounds half-up for display only (an average); the exact
    value stays in the payload beside it.  A number outside the plain range
    is written as an exponent with every one of its digits
    (``1e+300``, ``1.7976931348623157e+308``), never rounded.  Total: a
    value it cannot read comes back as the text it was given, so formatting
    can never turn an answer into an error (test_dashboard.py ::
    TestHugeNumbersAreShownNotFatal).
    """
    raw = str(text)
    try:
        d = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        return raw
    if not d.is_finite() or "e" in raw.lower():
        return raw
    try:
        if d and not (_PLAIN_MIN_ADJUSTED <= d.adjusted() < _PLAIN_MAX_ADJUSTED):
            return format(_normal(d), "e").replace("E", "e")
        if places is not None:
            q = d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
            return f"{q:,.{places}f}"
        sign = "-" if d < 0 else ""
        whole, _, frac = format(d.copy_abs(), "f").partition(".")
        return sign + f"{int(whole):,}" + ("." + frac if frac else "")
    except (ArithmeticError, ValueError):
        return raw


def _plain_json(value: Any, *, inside: bool = False) -> str:
    """A list or group value, readably.  Text INSIDE a list or group is
    quoted, so ``["a, b"]`` (one item) and ``["a", "b"]`` (two) never read
    the same: “a, b” against “a”, “b” (T-75)."""
    if value is None:
        return "blank"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, Decimal)):
        return fmt_number(str(value).replace("E", "e"))
    if isinstance(value, str):
        return f"“{value}”" if inside else value
    if isinstance(value, list):
        if not value:
            return "[ ]" if inside else "(empty list)"
        body = ", ".join(_plain_json(v, inside=True) for v in value)
        # a list inside a list keeps its brackets, so [["a","b"],["c"]]
        # never reads like ["a","b","c"] (T-75)
        return f"[{body}]" if inside else body
    if isinstance(value, dict):
        if not value:
            return "{ }" if inside else "(empty group)"
        body = ", ".join(f"{k}: {_plain_json(v, inside=True)}" for k, v in value.items())
        return f"{{{body}}}" if inside else body
    return str(value)


def fmt_cell(text: str, tag: str, kind: str, zone=None):
    """One answer cell → what a person reads.  ``None`` is a blank cell.
    A time reads on the question's clock (``zone``, T-98)."""
    if tag == "null":
        return None
    if tag == "boolean":
        return "Yes" if text == "true" else "No"
    if tag == "number":
        return fmt_number(text)
    if tag == "string":
        if kind == "time":
            return fmt_time(text, zone)
        if kind == "date":
            return fmt_date(text)
        return text
    if tag in ("array", "object"):
        try:
            return _plain_json(json.loads(text, parse_float=Decimal, parse_int=Decimal))
        except ValueError:
            return text
    return text


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{fmt_number(str(n))} {one if n == 1 else (many or one + 's')}"


SCOREBOARD_KEYS = {"by", "count_from", "counts", "time", "measure", "sort"}


COUNT_KEYS = {"id", "label", "logic", "conditions", "filter", "pct"}


#: A count column's id: the handle the screen keeps for it, echoed back in
#: the answer's column ids ("count:<id>", "pct:<id>") and used by a sort —
#: ONE numbering end to end, so a column the screen holds back (not ready)
#: cannot shift which column a sort or a header means.  Without ids, the
#: columns are numbered 1, 2, … in order.
COUNT_ID_MAX = 10 ** 9


TIME_KEYS = {"fn", "field"}


MEASURE_KEYS = {"fn", "field"}


#: A chosen match (T-76): count the rows of ``dataset`` whose ``field``
#: equals this row's ``matches``.
COUNT_FROM_KEYS = {"dataset", "field", "matches"}


#: Which field kinds can be matched, and how the engines compare them
#: (demo/group.py :: MATCH_TYPES).  Dates and times are ISO text, so they
#: compare as text — but only date with date and time with time: a match
#: pairs two fields of the SAME kind.  Mixed fields (lists, groups, values of
#: more than one kind) are never matched.
MATCH_TYPE_OF_KIND = {"text": "string", "date": "string", "time": "string", "number": "number"}


_KIND_WORDS = {"text": "text", "date": "dates", "time": "times", "number": "numbers"}


SB_SORT_KEYS = {"column", "dir"}


TIME_WORDS = {"latest": ("max", "Latest"), "earliest": ("min", "Earliest")}


#: A count-if column's label: what the person typed, shown in the answer
#: and nowhere else — it never reaches the statement (the column is c1…c6).
LABEL_MAX = 40


def check_label(label) -> str:
    """A label a person typed, checked: plain text, 1 to LABEL_MAX
    characters once trimmed, no control or invisible formatting
    characters."""
    import unicodedata

    if not isinstance(label, str):
        raise ViewError("A column's name must be text.")
    text = label.strip()
    if not text:
        raise ViewError("Give each count column a name.")
    if len(text) > LABEL_MAX:
        raise ViewError(f"A column's name can be at most {LABEL_MAX} characters.")
    if any(unicodedata.category(ch).startswith("C") for ch in text):
        raise ViewError("A column's name can't hold control or invisible characters.")
    return text


def _same_name(label: str) -> str:
    """A column name as a person reads it: case folded and every run of
    Unicode whitespace — two spaces, a no-break space, an em-space — one
    space (S13 check, MEDIUM).  "Latest  Time" and "Latest Time" are one
    name; so are "Big hit" and "Big\u00a0hit"."""
    return re.sub(r"\s+", " ", label).strip().casefold()


def _count_conditions(c: dict, fields: dict, where: str, zone=None) -> tuple[str, str]:
    # T-96: a count column's filter is a tree too (``filter``), or the old
    # flat ``{conditions, logic}``; either way it needs a condition.
    if c.get("filter") is None and not isinstance(c.get("conditions"), list):
        raise ViewError(f"{where} needs at least one condition.")
    expr, words = filter_parts(c, fields, where, where, zone)
    if expr is None:
        raise ViewError(f"{where} needs at least one condition.")
    return expr, words


def _count_from(catalog: "Catalog", setup_payload: dict, ds: dict, fields: dict, count_from, admin: bool,
                verb: str = "count from"):
    """The match a scoreboard counts across (T-76), checked — or (None, None)
    for its own rows.  Returns ``({"to", "key", "parent_key", "match",
    "declared"}, the counted data set)``.  Every pick the screen can't make
    is refused by name (AC8)."""
    if count_from is None:
        return None, None
    if isinstance(count_from, str):
        # T-74's form: a declared relation, named by the data set it counts.
        relation = next((r for r in catalog.relations.get(ds["id"], []) if r["to"] == count_from), None)
        if relation is None:
            raise ViewError(f"{ds['name']} has no related data set to count from by that name.")
        count_from = {"dataset": relation["to"], "field": relation["key"], "matches": relation["parent_key"]}
    if not isinstance(count_from, dict):
        raise ViewError(f"{verb[:1].upper() + verb[1:]} must name a data set and the two fields that match.")
    _refuse_extra(count_from, COUNT_FROM_KEYS, verb)
    other = _name(count_from.get("dataset"))
    rel_ds = next((d for d in setup_payload["datasets"] if d["id"] == other), None)
    if rel_ds is None:
        raise ViewError(f"There's no data set called “{other}” to {verb}." if other
                        else f"There's no data set by that name to {verb}.")
    if rel_ds["id"] == ds["id"]:
        raise ViewError("A data set can't be matched with itself.")
    theirs = {f["path"]: f for f in rel_ds["fields"]}
    def no_field(owner: dict, name) -> ViewError:
        # A name that isn't text (or is empty) is said plainly, never as “”.
        return ViewError(f"{owner['name']} has no field “{name}” to match on." if name
                         else f"{owner['name']} has no field by that name to match on.")

    f_counted = theirs.get(_name(count_from.get("field")))
    if f_counted is None:
        raise no_field(rel_ds, _name(count_from.get("field")))
    f_parent = fields.get(_name(count_from.get("matches")))
    if f_parent is None:
        raise no_field(ds, _name(count_from.get("matches")))
    for f in (f_parent, f_counted):
        if not admin and f.get("hidden_by_default"):
            raise ViewError(f"{f['label']} isn't offered in this view.")
        if f["kind"] not in MATCH_TYPE_OF_KIND:
            raise ViewError(f"{f['label']} holds lists or mixed values, which can't be matched.")
    if f_parent["kind"] != f_counted["kind"]:
        raise ViewError(f"{f_parent['label']} holds {_KIND_WORDS[f_parent['kind']]} and "
                        f"{f_counted['label']} holds {_KIND_WORDS[f_counted['kind']]}; "
                        "a match pairs two fields of the same kind.")
    declared = any(r["to"] == rel_ds["id"] and r["key"] == f_counted["path"]
                   and r["parent_key"] == f_parent["path"] for r in catalog.relations.get(ds["id"], []))
    return ({"to": rel_ds["id"], "key": f_counted["path"], "parent_key": f_parent["path"],
             "match": MATCH_TYPE_OF_KIND[f_parent["kind"]], "declared": declared,
             "field": f_counted, "matches": f_parent}, rel_ds)


def to_spec(catalog: "Catalog", setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
    """A scoreboard view → (the engine's spec, what the screen needs to
    label it).  Everything the view carries is honoured or refused by name.
    ``admin`` False is the Everyone view: a field hidden from it is refused."""
    ds, fields = _dataset(setup_payload, view)
    sb = view.get("scoreboard")
    if not isinstance(sb, dict):
        raise ViewError("A scoreboard must be a set of choices.")
    _refuse_extra(sb, SCOREBOARD_KEYS, "a scoreboard")
    if view.get("summary") is not None:
        raise ViewError("A scoreboard and a summary can't be asked at once.")
    if view.get("matched") is not None:
        raise ViewError(MATCHED_NEEDS_TABLE)
    if _columns(view, fields):
        raise ViewError("Columns don't apply to a scoreboard; untick them first.")
    if view.get("sort") is not None:
        raise ViewError("Sort a scoreboard by one of its own columns.")

    by = sb.get("by")
    if _name(by) not in fields:
        raise ViewError("Pick the field to give one row per value of.")
    if not fields[by]["group"]["ok"]:
        raise ViewError(f"{fields[by]['label']} can't be grouped by: {fields[by]['group']['why']}")

    # T-74: count each group's OWN rows (the default), or the rows of
    # another data set — the parents are grouped, the other rows are
    # counted.  Count columns, latest and the measure then read the counted
    # data set's fields; the page's conditions still read the parent.
    # T-76: the match is the person's to choose (see _count_from); T-74's
    # string form names a declared relation and is its shorthand.
    relation, rel_ds = _count_from(catalog, setup_payload, ds, fields, sb.get("count_from"), admin)
    counted_fields = {f["path"]: f for f in rel_ds["fields"]} if rel_ds else fields
    if not admin:
        # Everyone never picks a field hidden from it, here either (T-77).
        for c in sb.get("counts") or []:
            for name in (filter_fields(c) if isinstance(c, dict) else []):
                f = counted_fields.get(_name(name))
                if f and f.get("hidden_by_default"):
                    raise ViewError(f"{f['label']} isn't offered in this view.")

    counts_in = sb.get("counts") or []
    if not isinstance(counts_in, list):
        raise ViewError("Count columns must be a list.")
    if len(counts_in) > group.MAX_COUNTS:
        raise ViewError(f"A scoreboard has at most {group.MAX_COUNTS} count columns.")
    counts, labels, count_times = [], [], []
    for i, c in enumerate(counts_in, start=1):
        if not isinstance(c, dict):
            raise ViewError("A count column must be a set of choices.")
        _refuse_extra(c, COUNT_KEYS, "a count column")
        label = check_label(c.get("label"))
        # "A" and "a " read as the same name to a person: trimmed and
        # case-folded, they are refused as duplicates.
        if _same_name(label) in [_same_name(x["label"]) for x in labels]:
            raise ViewError(f"Two count columns are both called “{label}”.")
        if not isinstance(c.get("pct", False), bool):
            raise ViewError("“% of rows” is on or off.")
        cid = c.get("id", i)
        if isinstance(cid, bool) or not isinstance(cid, int) or not 1 <= cid <= COUNT_ID_MAX:
            raise ViewError("A count column's id must be a whole number.")
        if cid in [x["id"] for x in labels]:
            raise ViewError("Two count columns share one id.")
        expr, said = _count_conditions(c, counted_fields, f"“{label}”", view_zone(view))
        counts.append({"expr": expr, "pct": bool(c.get("pct"))})
        count_times += [t for t in time_fields_read(c, counted_fields) if t not in count_times]
        labels.append({"id": cid, "label": label, "said": said, "pct": bool(c.get("pct"))})

    time = sb.get("time")
    time_spec = None
    if time is not None:
        if not isinstance(time, dict):
            raise ViewError("Latest or earliest must be a set of choices.")
        _refuse_extra(time, TIME_KEYS, "latest or earliest")
        if _name(time.get("fn")) not in TIME_WORDS:
            raise ViewError("Pick latest or earliest.")
        f = counted_fields.get(_name(time.get("field")))
        if not f or f["kind"] not in ("time", "date"):
            raise ViewError("Latest and earliest read a time or a date field.")
        time_spec = {"fn": TIME_WORDS[time["fn"]][0], "field": f["path"]}
        if f["kind"] == "time" and f["path"] not in count_times:
            count_times.append(f["path"])       # T-114: latest / earliest by instant

    measure = sb.get("measure")
    measure_spec = None
    if measure is not None:
        if not isinstance(measure, dict):
            raise ViewError("A total or average must be a set of choices.")
        _refuse_extra(measure, MEASURE_KEYS, "a total or average")
        if measure.get("fn") not in group.MEASURE_FNS:
            raise ViewError("Summarize by total, average, smallest or largest.")
        f = counted_fields.get(_name(measure.get("field")))
        if not f or f["kind"] != "number":
            raise ViewError(f"{SUMMARY_FNS[measure['fn']]} of what? Pick a field that holds numbers.")
        measure_spec = {"fn": measure["fn"], "field": f["path"]}

    # Nor the name of any other column on the board — its own two ("Heartbeats"
    # beside "Heartbeats", M3 review LOW-2), a count's "% …", "Latest …" or a
    # total's header (T-77): one name, one column.
    headers = [fields[by]["label"], rel_ds["name"] if rel_ds is not None else "Rows"]
    headers += [f"% {x['label']}" for x in labels if x["pct"]]
    if time_spec:
        headers.append(f"{TIME_WORDS[time['fn']][1]} {counted_fields[time_spec['field']]['label']}")
    if measure_spec:
        headers.append(f"{SUMMARY_FNS[measure_spec['fn']]} {counted_fields[measure_spec['field']]['label']}")
    taken = {_same_name(h) for h in headers}
    for x in labels:
        if _same_name(x["label"]) in taken:
            raise ViewError(f"“{x['label']}” is already a column on this board; call this count something else.")

    spec = {
        "source": catalog.sources[ds["id"]],
        "group": by,
        "filter": filter_expression(view, fields),
        "counts": counts,
        "time": time_spec,
        "measure": measure_spec,
        "sort": None,
        "cap": _show(view),
    }
    # T-114: the time fields read as instants -- the page filter's (the parents'), and the counts' and latest /
    # earliest's (the counted rows')
    if time_fields_read(view, fields):
        spec["times"] = time_fields_read(view, fields)
    if count_times:
        spec["count_times"] = count_times
    if (spec.get("times") or count_times) and view_zone(view) is not None:
        spec["times_zone"] = view_zone(view)     # T-114: they are read on the question's clock
    if relation:
        spec["related"] = {
            "source": catalog.sources[relation["to"]],
            "key": relation["key"],
            "parent_key": relation["parent_key"],
            "match": relation["match"],
        }

    sort = sb.get("sort")
    if sort is not None:
        if not isinstance(sort, dict):
            raise ViewError("Sort a scoreboard by one of its own columns.")
        _refuse_extra(sort, SB_SORT_KEYS, "a sort")
        names = {"group": "grp", "rows": "rows", "time": "time", "measure": "measure"}
        for i, c in enumerate(labels, start=1):
            names[f"count:{c['id']}"] = f"c{i}"
            if c["pct"]:
                names[f"pct:{c['id']}"] = f"c{i}_pct"
        column = names.get(_name(sort.get("column")))
        if column is None or column not in group.columns_of(spec):
            raise ViewError("Sort a scoreboard by one of its own columns.")
        if sort.get("dir") not in ("asc", "desc"):
            raise ViewError("Sort one way or the other.")
        spec["sort"] = {"column": column, "dir": sort["dir"]}

    return spec, {"ds": ds, "fields": fields, "by": fields[by], "counts": labels,
                  "time": time, "measure": measure, "rel_ds": rel_ds,
                  "counted_fields": counted_fields, "relation": relation}


MATCHED_KEYS = {"dataset", "field", "matches", "columns"}


MATCHED_NEEDS_TABLE = ("Fields from another data set go beside a table's rows; "
                       "turn the summary or the scoreboard off first.")


def lookups(catalog: "Catalog", ds_id: str) -> list:
    """The matches a table opens on: each declared relation read the other
    way (T-74's Senders → Heartbeats is each heartbeat's sender; T-76's
    Sites → Senders is each sender's site).  Never guessed from names."""
    return [{"id": parent, "field": r["parent_key"], "matches": r["key"]}
            for parent, rels in catalog.relations.items() for r in rels if r["to"] == ds_id]


def matched_label(rel_ds: dict, field: dict) -> str:
    """A matched column's name: the other data set's word and the field's
    — "Sender's Name", "Site's Capacity"."""
    one = rel_ds["one"]
    return f"{one[:1].upper()}{one[1:]}'s {field['label']}"


def to_lookup(catalog: "Catalog", setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
    """A view's ``matched`` → (the engine's match spec, what the screen needs
    to label it).  Every pick the screen can't make is refused by name
    (AC8): T-76's checks on the pair, then the columns."""
    ds, fields = _dataset(setup_payload, view)
    m = view.get("matched")
    if view.get("summary") is not None or view.get("scoreboard") is not None:
        raise ViewError(MATCHED_NEEDS_TABLE)
    if not isinstance(m, dict):
        raise ViewError("Fields from another data set must name a data set, the two fields that "
                        "match, and the fields to show.")
    _refuse_extra(m, MATCHED_KEYS, "fields from another data set")
    pair = {k: m.get(k) for k in ("dataset", "field", "matches")}
    relation, rel_ds = _count_from(catalog, setup_payload, ds, fields, pair, admin, verb="take fields from")
    theirs = {f["path"]: f for f in rel_ds["fields"]}
    cols = m.get("columns")
    if not isinstance(cols, list) or not cols:
        raise ViewError(f"Pick at least one of {rel_ds['name']}' fields to show.")
    if not all(isinstance(c, str) for c in cols):
        raise ViewError("The fields to show must be a list of field names.")
    if len(cols) > lookup.MAX_COLUMNS:
        raise ViewError(f"Show at most {lookup.MAX_COLUMNS} fields from {rel_ds['name']}.")
    picked: list = []
    for c in cols:
        f = theirs.get(c)
        if f is None:
            raise ViewError(f"{rel_ds['name']} has no field “{c}” to show." if c
                            else f"{rel_ds['name']} has no field by that name to show.")
        if f.get("hidden_by_default") and not admin:     # T-77's rule, for a shown field
            raise ViewError(f"{f['label']} isn't offered in this view.")
        if f not in picked:
            picked.append(f)
    # The statement's names: the table's own column names come first, and a
    # matched column takes the next free one ("Sender_s_Name").
    taken = {fields[c]["alias"] for c in _columns(view, fields)}
    shown = [{"field": f, "label": matched_label(rel_ds, f),
              "alias": _alias(matched_label(rel_ds, f), taken)} for f in picked]
    declared = any(x["id"] == rel_ds["id"] and x["field"] == relation["key"]
                   and x["matches"] == relation["parent_key"] for x in lookups(catalog, ds["id"]))
    spec = {
        "source": catalog.sources[rel_ds["id"]],
        "key": relation["key"],
        "parent_key": relation["parent_key"],
        "match": relation["match"],
        "columns": [{"name": x["alias"], "path": x["field"]["path"]} for x in shown],
    }
    return spec, {"ds": ds, "rel_ds": rel_ds, "relation": relation, "shown": shown,
                  "declared": declared}


def to_category_spec(catalog: "Catalog", setup_payload: dict, view: dict) -> tuple[dict, dict]:
    """A summary ``per: "category"`` → (the engine's board spec, what the
    screen needs).  One number per value of a field (T-88): a count is the
    board's own Rows; a total, average, smallest or largest is its measure.
    Both engines compute it as they compute any board (``group``,
    ``pyrunner.group``).  The blank group (missing or JSON null) is its own;
    an empty text ``""`` is a value like any other."""
    ds, fields = _dataset(setup_payload, view)
    summary = _summary(view, fields, ds)
    if not summary or summary["per"] != "category":
        raise ViewError("This is not one number per value of a field.")
    if _columns(view, fields):
        raise ViewError("Columns don't apply to a summary; untick them first.")
    if view.get("sort") is not None:
        raise ViewError("One number per value of a field is in the order of its values.")
    spec = {
        "source": catalog.sources[ds["id"]],
        "group": summary["by"],
        "filter": filter_expression(view, fields),
        "counts": [],
        "time": None,
        "measure": None if summary["fn"] == "count" else {"fn": summary["fn"], "field": summary["field"]},
        "sort": None,
        "cap": _show(view),
    }
    if time_fields_read(view, fields):
        spec["times"] = time_fields_read(view, fields)       # T-114
        if view_zone(view) is not None:
            spec["times_zone"] = view_zone(view)
    return spec, {"ds": ds, "fields": fields, "summary": summary, "by": fields[summary["by"]]}
