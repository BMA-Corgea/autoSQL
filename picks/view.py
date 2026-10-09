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

import datetime as _dt
import json
import math
import re
from dataclasses import dataclass, field as _dc_field
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from . import env, group, legality, lookup
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
    words = path.replace(".", " ").replace("_", " ").split()
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


_TYPES_SQL = """
SELECT e.k, jsonb_typeof(e.v) AS t, count(*)
  FROM {table} r, LATERAL jsonb_each(r.data) AS e(k, v)
 WHERE {scope}
 GROUP BY 1, 2
"""


_INNER_TYPES_SQL = """
SELECT e2.k, jsonb_typeof(e2.v) AS t, count(*)
  FROM {table} r, LATERAL jsonb_each(r.data -> %(key)s) AS e2(k, v)
 WHERE {scope}
   AND jsonb_typeof(r.data -> %(key)s) = 'object'
 GROUP BY 1, 2
"""


_VALUES_SQL = """
SELECT r.data #>> %(path)s AS v, count(*) AS n
  FROM {table} r
 WHERE {scope}
   AND jsonb_typeof(r.data #> %(path)s) = 'string'
 GROUP BY 1
 ORDER BY 1
 LIMIT %(limit)s
"""


_RANGE_SQL = """
SELECT min((r.data #>> %(path)s)::numeric), max((r.data #>> %(path)s)::numeric)
  FROM {table} r
 WHERE {scope}
   AND jsonb_typeof(r.data #> %(path)s) = 'number'
"""


def _kind(types: set, strings: list) -> str:
    """One field's kind, from the JSON types its values take.

    * ``number`` — every value is a number;
    * ``time`` / ``date`` — every value is text in the one fixed-width UTC
      form (``2026-08-20T23:00:00Z``) or a calendar date (``2026-09-03``);
    * ``text`` — every value is text;
    * ``yesno`` — every value is true or false;
    * ``mixed`` — anything else (different types in different rows).
    """
    if types == {"number"}:
        return "number"
    if types == {"string"}:
        if strings and all(_TIME_RE.match(s) for s in strings):
            return "time"
        if strings and all(_DATE_RE.match(s) for s in strings):
            return "date"
        return "text"
    if types == {"boolean"}:
        return "yesno"
    return "mixed"


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


def _read(conn, records, template: str, params: dict):
    """One of the setup reads above, for this description's table and owner."""
    params = dict(params)
    sql = template.replace("{table}", records.table).replace("{scope}", records.scope("r", params))
    return conn.execute(sql, params)


def _read_fields(conn, collection: str, labels=None, records=None) -> list:
    """Every field of one data set: its path, its JSON types, its kind,
    the conditions it can take and the values found in it."""
    records = env.records(records)
    labels = labels or {}
    rows = _read(conn, records, _TYPES_SQL, {"collection": collection}).fetchall()
    types: dict = {}
    for k, t, _n in rows:
        types.setdefault(k, set()).add(t)

    paths: dict = {}
    for key, ts in types.items():
        if not _PLAIN_KEY.match(key):
            continue   # a name the path grammar cannot reach (app._as_dollar_path)
        if ts == {"object"}:
            # A key that always holds an object (Heartbeats' payload) is
            # opened one level: its fields are what a person reads.
            inner = _read(
                conn, records, _INNER_TYPES_SQL, {"collection": collection, "key": key}
            ).fetchall()
            for k2, t2, _n in inner:
                if _PLAIN_KEY.match(k2):
                    paths.setdefault(f"{key}.{k2}", set()).add(t2)
        else:
            paths[key] = set(ts)

    fields = []
    for path, ts in paths.items():
        strings: list = []
        if "string" in ts:
            strings = [
                r[0] for r in _read(conn, records, _VALUES_SQL, {
                    "collection": collection, "path": path.split("."),
                    "limit": VALUE_LIMIT + 1,
                }).fetchall()
            ]
        scalar_types = ts - {"null"}
        kind = _kind(scalar_types, strings)
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
        field["group"] = _groupable(conn, collection, path, kind, ts, field["label"], strings, records)
        if kind == "text" and len(strings) <= VALUE_LIMIT:
            field["values"] = strings
            field["picker"] = "chips" if len(strings) <= CHIP_LIMIT else "list"
        if kind == "number":
            lo, hi = _read(
                conn, records, _RANGE_SQL, {"collection": collection, "path": path.split(".")}
            ).fetchone()
            if lo is not None:
                field["range"] = {"min": _number_text(lo), "max": _number_text(hi)}
        if kind in ("time", "date") and strings:
            field["range"] = {"min": strings[0], "max": strings[-1]}
        fields.append(field)
    return fields


#: One row per value works up to this many different values (T-73 AC1).
#: Chosen against the seed: the widest honest grouping is Heartbeats' 50
#: senders; the next field up is Samples' ID, 2,000 values, one row each —
#: a "scoreboard" of it is the table again.  500 is ten times the widest
#: real grouping, a quarter of the degenerate one, and ten pages of 50.
GROUP_LIMIT = 500


_DISTINCT_SQL = """
SELECT count(DISTINCT nullif(r.data #> %(path)s, 'null'::jsonb))
     + max(CASE WHEN nullif(r.data #> %(path)s, 'null'::jsonb) IS NULL THEN 1 ELSE 0 END)
  FROM {table} r
 WHERE {scope}
"""


def _groupable(conn, collection, path, kind, types, label, strings, records=None) -> dict:
    """Can the page give one row per value of this field, and if not, why
    — in plain words.  The blank group counts as a value."""
    if kind not in ("text", "number", "yesno") or types & {"object", "array"}:
        why = ("Times and dates are grouped per hour or per day under Summarize."
               if kind in ("time", "date") else
               "Its rows hold different kinds of value, so there is no one value to group by.")
        return {"ok": False, "why": why, "groups": None}
    n = int(_read(conn, env.records(records), _DISTINCT_SQL, {"collection": collection,
                                         "path": path.split(".")}).fetchone()[0])
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
VIEW_KEYS = {"dataset", "columns", "conditions", "logic", "sort", "show", "summary",
             "scoreboard", "matched"}


CONDITION_KEYS = {"field", "op", "value", "value2", "values"}


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

    summary = _summary(view, fields, ds)
    if summary:
        if pick["computed"]:
            raise ViewError("Columns don't apply to a summary; untick them first.")
        pick["aggregate"] = {
            "fn": summary["fn"],
            "field": summary["field"],
        }
        pick["bucket"] = "off" if summary["per"] == "all" else summary["per"]

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


SUMMARY_KEYS = {"fn", "field", "per"}


PERS = ("all", "hour", "day")


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
    if per not in PERS:
        raise ViewError("Summarize over everything, per hour or per day.")
    path = summary.get("field")
    if fn == "count":
        if not _empty(path):
            raise ViewError("A count counts rows; it takes no field.")
        return {"fn": fn, "field": None, "per": per}
    if _name(path) not in fields or fields[path]["kind"] != "number":
        raise ViewError(f"{SUMMARY_FNS[fn]} of what? Pick a field that holds numbers.")
    return {"fn": fn, "field": path, "per": per}


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
    legality._WHY_BUCKET_SORT: "Per-hour and per-day summaries are always in time order.",
    legality._WHY_BUCKET_WINDOW: "Per-hour and per-day summaries are grouped already.",
    legality._WHY_BUCKET_CHANGED: "Per-hour and per-day summaries are grouped already.",
    legality.WHY_BUCKET_NEEDS_AGG: "Per hour and per day need something to count or total.",
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
    """A field path as the expression language spells it: ``$.payload.load``.
    Only paths read out of the data reach here, and every step of one is a
    plain identifier (:data:`_PLAIN_KEY`), so the dotted form is exact."""
    steps = path.split(".")
    if not all(_PLAIN_KEY.match(s) for s in steps):
        raise ViewError(f"{path!r} is not a field this page can reach.")
    return "$." + path


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


def number_literal(value) -> str:
    """A number as a literal of the expression language.  Only a finite
    JSON number is accepted; ``-5`` is the language's own unary minus."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ViewError("A number value must be a number.")
    try:
        as_double = float(value)
    except OverflowError:
        raise ViewError("That number is too large to compare with.") from None
    if not math.isfinite(as_double):
        raise ViewError("That number is too large to compare with.")
    text = str(value) if isinstance(value, int) else repr(float(value))
    return text


_DAY_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\Z")


_MINUTE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?Z?\Z")


def _day(value) -> _dt.date:
    if not isinstance(value, str) or not _DAY_RE.match(value):
        raise ViewError("A day must be picked as a date.")
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise ViewError("A day must be picked as a date.") from None


def _instant(value) -> str:
    """A picked time → the data's own fixed-width UTC text, which orders as
    time orders (``2026-08-18T06:00:00Z``)."""
    m = _MINUTE_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise ViewError("A time must be picked as a date and a time.")
    day = _day(m.group(1))
    hh, mm, ss = int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    if hh > 23 or mm > 59 or ss > 59:
        raise ViewError("A time must be picked as a date and a time.")
    return f"{day.isoformat()}T{hh:02d}:{mm:02d}:{ss:02d}Z"


#: The words each condition reads as, by kind.  The screen shows these in
#: its condition picker; the sentence uses them too, so the two agree.
OP_WORDS = {
    "eq": "is", "ne": "is not", "in": "is one of",
    "gt": "is more than", "lt": "is less than",
    "ge": "is at least", "le": "is at most", "between": "is between",
    "on": "is on", "after": "is after", "before": "is before",
    "yes": "is yes", "no": "is no",
    "present": "has a value", "blank": "is blank",
}


#: The most values one "is one of" may carry.
IN_LIMIT = 200


def _value_for(field: dict, value):
    """One picked value → (its literal, how the sentence reads it)."""
    kind = field["kind"]
    if kind == "number":
        return number_literal(value), fmt_number(str(value))
    if kind == "time":
        t = _instant(value)
        return string_literal(t), fmt_time(t)
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


def _order_key(field: dict, value):
    if field["kind"] == "number":
        return value
    if field["kind"] == "time":
        return _instant(value)
    if field["kind"] == "date":
        return _day(value).isoformat()
    return value


def condition(field: dict, cond: dict) -> tuple[str, str]:
    """One clicked condition → (its expression, its words in the sentence).

    The expression is only ever comparisons, ``and``, ``or`` and ``null`` —
    every one inside the gate's subset — over one field read with ``$.``
    and values written by :func:`string_literal` / :func:`number_literal`.
    """
    _refuse_extra(cond, CONDITION_KEYS, "a condition")
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
        pairs = [_value_for(field, v) for v in unique]
        if len(pairs) == 1:
            lit, said = pairs[0]
            return f"{ref} == {lit}", f"{label} is {said}"
        expr = " or ".join(f"{ref} == {lit}" for lit, _ in pairs)
        said = [s for _, s in pairs]
        return f"({expr})", f"{label} is {', '.join(said[:-1])} or {said[-1]}"

    if op == "on" and field["kind"] == "time":
        d = _day(cond.get("value"))
        start = string_literal(f"{d.isoformat()}T00:00:00Z")
        end = string_literal(f"{(d + _dt.timedelta(days=1)).isoformat()}T00:00:00Z")
        return (f"({ref} >= {start} and {ref} < {end})",
                f"{label} {words} {fmt_day(d.isoformat())}")

    if op == "between":
        lo, hi = cond.get("value"), cond.get("value2")
        a, said_a = _value_for(field, lo)
        b, said_b = _value_for(field, hi)
        # "between 50 and 10" means the same as "between 10 and 50" to a
        # person; the two ends are put in order rather than matching nothing.
        key = (lambda v: float(v)) if field["kind"] == "number" else (lambda v: v)
        if key(_order_key(field, lo)) > key(_order_key(field, hi)):
            (a, said_a), (b, said_b) = (b, said_b), (a, said_a)
        return (f"({ref} >= {a} and {ref} <= {b})",
                f"{label} {words} {said_a} and {said_b}")

    sym = {"eq": "==", "on": "==", "ne": "!=", "gt": ">", "lt": "<",
           "ge": ">=", "le": "<=", "after": ">", "before": "<"}[op]
    lit, said = _value_for(field, cond.get("value"))
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


def filter_expression(view: dict, fields: dict) -> str | None:
    """Every condition on the page, joined by the page's logic (default
    all): ``(a) and (b)``."""
    conds = _conditions(view, fields)
    parts = [expr for expr, _ in conds]
    if not parts:
        if view.get("logic") not in (None, "all"):
            _logic(view.get("logic"), 0, "Only rows where")
        return None
    return compose(parts, _logic(view.get("logic"), len(parts), "Only rows where"))


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


def fmt_time(text: str) -> str:
    """``2026-08-20T23:00:00Z`` → ``Aug 20, 23:00 UTC``; ``…23:00:15Z`` →
    ``Aug 20, 23:00:15 UTC``."""
    try:
        t = _dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return text
    seconds = f":{t.second:02d}" if t.second else ""      # shown when not zero (T-75)
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
    if abs(d) >= Decimal("1e15"):
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


def fmt_cell(text: str, tag: str, kind: str):
    """One answer cell → what a person reads.  ``None`` is a blank cell."""
    if tag == "null":
        return None
    if tag == "boolean":
        return "Yes" if text == "true" else "No"
    if tag == "number":
        return fmt_number(text)
    if tag == "string":
        if kind == "time":
            return fmt_time(text)
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


COUNT_KEYS = {"id", "label", "logic", "conditions", "pct"}


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


def _count_conditions(c: dict, fields: dict, where: str) -> tuple[str, str]:
    conds = c.get("conditions")
    if not isinstance(conds, list) or not conds:
        raise ViewError(f"{where} needs at least one condition.")
    parsed = []
    for cond in conds:
        if not isinstance(cond, dict) or _name(cond.get("field")) not in fields:
            raise ViewError("A condition names a field this data set doesn't have.")
        parsed.append(condition(fields[cond["field"]], cond))
    logic = _logic(c.get("logic"), len(parsed), where)
    return compose([e for e, _ in parsed], logic), joined_words([w for _, w in parsed], logic)


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
            for x in (c.get("conditions") if isinstance(c, dict) and isinstance(c.get("conditions"), list) else []):
                f = counted_fields.get(_name(x.get("field")) if isinstance(x, dict) else None)
                if f and f.get("hidden_by_default"):
                    raise ViewError(f"{f['label']} isn't offered in this view.")

    counts_in = sb.get("counts") or []
    if not isinstance(counts_in, list):
        raise ViewError("Count columns must be a list.")
    if len(counts_in) > group.MAX_COUNTS:
        raise ViewError(f"A scoreboard has at most {group.MAX_COUNTS} count columns.")
    counts, labels = [], []
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
        expr, said = _count_conditions(c, counted_fields, f"“{label}”")
        counts.append({"expr": expr, "pct": bool(c.get("pct"))})
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
