"""demo/server/dashboard.py — the dashboard's contract (T-71).

The dashboard at ``/dashboard`` is autoSQL in one screen: a dashboard from
which a person asks for different parts of a database, and the SQL writes
itself from the picks (README: "The dashboard: SQL analysis, kept out of
sight").  A person clicks; nothing is typed in any language.  This module is everything between those clicks and the engine:

* **the setup** — the data sets, their row counts, and each field's
  plain name, its kind, the conditions it can take and the values found in
  the data (``GET /api/dashboard/setup``);
* **the translation** — a *view* (the clicks) becomes one *pick* (the
  engine's own shape, ``legality.default_pick``).  Every picked value enters
  the filter as a correctly escaped literal of the expression language, which
  the pinned compiler then binds as a parameter (AC-11);
* **the answer** — the pick runs through ``app.run_pick``, the same function
  the two-pane screen calls, so the second engine, the probes and every
  refusal stay in one place.  What comes back is reshaped for a person: one
  sentence, formatted cells, a page of rows, plain reasons
  (``POST /api/dashboard/answer``).

The React side (``demo/frontend/dashboard*.jsx``) draws what this returns
and decides nothing.  That split is B22's, applied to a second screen: the
rules live where the suite can test them without a browser (AC-36).

WHAT THE EVERYONE VIEW NEVER SAYS (AC9).  The words a person sees come from
this file's templates, and none of them is a machinery word.  The statement
and the engine's own words travel in ``admin`` and are drawn only when the
page is switched to *View as: Admin*.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import math
import re
import sys
import threading
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

# demo/ is not a package; the same bootstrap as errors.py.
_DEMO_DIR = str(Path(__file__).resolve().parent.parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import group  # noqa: E402
import legality  # noqa: E402
import lookup  # noqa: E402

from . import db, settings  # noqa: E402

router = APIRouter()

_STATIC = Path(__file__).resolve().parent.parent / "static"

#: Rows per table page.  The engine's own page size, so the two screens
#: agree on what "a page" is.
PAGE_SIZE = settings.PAGE_SIZE

#: The "Show" choices.  ``None`` is "all rows" (no cap).
SHOW_CHOICES = (None, 25, 100, 500)

#: A text field with this many distinct values or fewer is offered as chips;
#: more than that, as a searchable list.
CHIP_LIMIT = 8

#: The most values a text field offers.  The largest field in the seed
#: (Samples' ID) has exactly 2,000.
VALUE_LIMIT = 2000


# ═════════════════════════════════════════════════════════════════════════
# 1 · The data sets and their fields, in plain words
# ═════════════════════════════════════════════════════════════════════════

DATASETS = (
    {
        "id": "heartbeats",
        "source": legality.HEARTBEAT,
        "name": "Heartbeats",
        "one": "heartbeat",
        "about": "Hourly check-ins from 50 senders over one week in August.",
        # Display order, and the columns a fresh view starts with.
        "order": ("sender_id", "ts", "status", "payload.load", "payload.note"),
        "default_columns": ("sender_id", "ts", "status", "payload.load",
                            "payload.note"),
    },
    {
        "id": "samples",
        "source": "noun:Sample",
        "name": "Samples",
        "one": "sample",
        "about": "Work items, each with a status, a due date and a priority.",
        "order": ("id", "status", "due_date", "priority"),
        "default_columns": ("id", "status", "due_date", "priority"),
    },
    {
        "id": "edge",
        "source": "noun:EdgeCase",
        "name": "Edge cases",
        "one": "edge case",
        "about": "Ten odd values kept on purpose: huge numbers, empty lists, blanks.",
        "order": ("label",),
        # Every field but Label, whose text was written for engineers
        # ("…SQL answers 1…", "XPR01"); a ticked box still shows it.
        "default_columns": None,
        "not_by_default": ("label",),
    },
    {
        "id": "senders",
        "source": "noun:Sender",
        "name": "Senders",
        "one": "sender",
        "about": "A profile per sender: its name, site, kind and the day it was installed.",
        "order": ("id", "name", "site", "kind", "installed"),
        "default_columns": ("id", "name", "site", "kind", "installed"),
        # Here a sender's id IS the sender: called that, not "ID".
        "labels": {"id": "Sender"},
    },
    {
        "id": "sites",
        "source": "noun:Site",
        "name": "Sites",
        "one": "site",
        "about": "A profile per site: its name, the day it opened and how many senders it was built for.",
        "order": ("name", "opened", "capacity"),
        "default_columns": ("name", "opened", "capacity"),
    },
)
_BY_ID = {d["id"]: d for d in DATASETS}

#: The relationships a scoreboard may count across — declared here, once,
#: never guessed from field names (T-74).  A Senders scoreboard can count
#: each sender's Heartbeats: Heartbeats.sender_id → Senders.id; a Sites
#: scoreboard each site's Senders: Senders.site → Sites.name (T-76).
RELATIONS = {
    "senders": [
        {"to": "heartbeats", "key": "sender_id", "parent_key": "id"},
    ],
    "sites": [
        {"to": "senders", "key": "site", "parent_key": "name"},
    ],
}

#: Plain names for the fields that have one.  Every other field is named by
#: :func:`_humanize` (``field_7`` → "Field 7").
_LABELS = {
    "sender_id": "Sender",
    "ts": "Time",
    "status": "Status",
    "payload.load": "Load",
    "payload.note": "Note",
    "id": "ID",
    "due_date": "Due date",
    "priority": "Priority",
    "label": "Label",
}

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


# ── reading the fields out of the data ───────────────────────────────────

_TYPES_SQL = """
SELECT e.k, jsonb_typeof(e.v) AS t, count(*)
  FROM demo.records r, LATERAL jsonb_each(r.data) AS e(k, v)
 WHERE r.collection = %(collection)s
 GROUP BY 1, 2
"""

_INNER_TYPES_SQL = """
SELECT e2.k, jsonb_typeof(e2.v) AS t, count(*)
  FROM demo.records r, LATERAL jsonb_each(r.data -> %(key)s) AS e2(k, v)
 WHERE r.collection = %(collection)s
   AND jsonb_typeof(r.data -> %(key)s) = 'object'
 GROUP BY 1, 2
"""

_VALUES_SQL = """
SELECT r.data #>> %(path)s AS v, count(*) AS n
  FROM demo.records r
 WHERE r.collection = %(collection)s
   AND jsonb_typeof(r.data #> %(path)s) = 'string'
 GROUP BY 1
 ORDER BY 1
 LIMIT %(limit)s
"""

_RANGE_SQL = """
SELECT min((r.data #>> %(path)s)::numeric), max((r.data #>> %(path)s)::numeric)
  FROM demo.records r
 WHERE r.collection = %(collection)s
   AND jsonb_typeof(r.data #> %(path)s) = 'number'
"""

_COUNTS_SQL = (
    "SELECT collection, count(*) FROM demo.records GROUP BY collection"
)


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


def _read_fields(conn, collection: str) -> list:
    """Every field of one data set: its path, its JSON types, its kind,
    the conditions it can take and the values found in it."""
    rows = conn.execute(_TYPES_SQL, {"collection": collection}).fetchall()
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
            inner = conn.execute(
                _INNER_TYPES_SQL, {"collection": collection, "key": key}
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
                r[0] for r in conn.execute(_VALUES_SQL, {
                    "collection": collection, "path": path.split("."),
                    "limit": VALUE_LIMIT + 1,
                }).fetchall()
            ]
        scalar_types = ts - {"null"}
        kind = _kind(scalar_types, strings)
        ops = _ops_for(kind, ts)
        field = {
            "path": path,
            "label": _LABELS.get(path) or _humanize(path),
            "kind": kind,
            "ops": ops,
            "why_no_ops": "" if ops else (
                WHY_GROUPED if ts & {"object", "array"} else WHY_ONLY_BLANK
            ),
            "values": None,
            "picker": None,
            "range": None,
        }
        field["group"] = _groupable(conn, collection, path, kind, ts, field["label"], strings)
        if kind == "text" and len(strings) <= VALUE_LIMIT:
            field["values"] = strings
            field["picker"] = "chips" if len(strings) <= CHIP_LIMIT else "list"
        if kind == "number":
            lo, hi = conn.execute(
                _RANGE_SQL, {"collection": collection, "path": path.split(".")}
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
  FROM demo.records r
 WHERE r.collection = %(collection)s
"""


def _groupable(conn, collection, path, kind, types, label, strings) -> dict:
    """Can the page give one row per value of this field, and if not, why
    — in plain words.  The blank group counts as a value."""
    if kind not in ("text", "number", "yesno") or types & {"object", "array"}:
        why = ("Times and dates are grouped per hour or per day under Summarize."
               if kind in ("time", "date") else
               "Its rows hold different kinds of value, so there is no one value to group by.")
        return {"ok": False, "why": why, "groups": None}
    n = int(conn.execute(_DISTINCT_SQL, {"collection": collection,
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


_SETUP_LOCK = threading.Lock()
_SETUP: dict | None = None


def setup(conn) -> dict:
    """The whole setup payload.  Read once per process: the data is the
    pinned, read-only seed (AC-10), so it cannot change underneath."""
    global _SETUP
    with _SETUP_LOCK:
        if _SETUP is not None:
            return _SETUP
        counts = dict(conn.execute(_COUNTS_SQL).fetchall())
        out = []
        for d in DATASETS:
            fields = _ordered(_read_fields(conn, d["source"]), d["order"])
            for f in fields:
                f["label"] = d.get("labels", {}).get(f["path"], f["label"])
            taken: set = set()
            for f in fields:
                f["alias"] = _alias(f["label"], taken)
                # Off by default in the Everyone view (Edge cases' Label):
                # a new condition does not open on it either.
                f["hidden_by_default"] = f["path"] in d.get("not_by_default", ())
            default = d["default_columns"] or tuple(
                f["path"] for f in fields
                if f["path"] not in d.get("not_by_default", ()))
            out.append({
                "id": d["id"],
                "name": d["name"],
                "about": d["about"],
                "rows": int(counts.get(d["source"], 0)),
                "fields": fields,
                "default_columns": [p for p in default
                                    if any(f["path"] == p for f in fields)],
                "has_time": d["source"] == legality.HEARTBEAT,
                "one": d["one"],
                "count_from": [{"id": r["to"], "name": _BY_ID[r["to"]]["name"],
                                "field": r["key"], "matches": r["parent_key"]}
                               for r in RELATIONS.get(d["id"], [])],
                # The fields that name one row each — a board by one of them
                # is "Senders", never "Senders per Sender" (the page's bar too).
                "own_keys": sorted({r["parent_key"] for r in RELATIONS.get(d["id"], [])}),
                # T-78: the matches a table opens on (a declared relation read
                # the other way): each heartbeat's sender, each sender's site.
                "lookups": [dict(x, name=_BY_ID[x["id"]]["name"]) for x in lookups(d["id"])],
            })
        _SETUP = {
            "datasets": out,
            "show": list(SHOW_CHOICES),
            "page_size": PAGE_SIZE,
            "default_view": default_view_from(out),
            "default_views": {d["id"]: default_view_from(out, d["id"]) for d in out},
            # Admin starts every data set with every field ticked — Edge
            # cases' Label included, whose text is written for engineers.
            "admin_default_views": {
                d["id"]: dict(default_view_from(out, d["id"]),
                              columns=[f["path"] for f in d["fields"]])
                if d["id"] == "edge" else default_view_from(out, d["id"])
                for d in out
            },
            "op_words": OP_WORDS,
            "sort_words": SORT_WORDS,
            "summary_fns": SUMMARY_FNS,
            "logics": LOGICS,
            # How the condition picker names each condition, where that needs
            # more than the sentence's word: a row WITHOUT the field is "not"
            # the value picked, so it is counted.
            "op_labels": dict(OP_WORDS, ne="is not (rows without a value count too)"),
            "logic_needs_two": WHY_LOGIC_NEEDS_TWO,
            "max_counts": group.MAX_COUNTS,
            # T-76: the field kinds a match may pair (two of the same kind);
            # the gate reads the same table.
            "match_kinds": list(MATCH_TYPE_OF_KIND),
            "label_max": LABEL_MAX,
            "max_matched_columns": lookup.MAX_COLUMNS,
            "unavailable": _reasons_table(out),
        }
        return _SETUP


def setup_for(payload: dict, admin: bool) -> dict:
    """The setup as one view may see it (T-79).  Admin gets all of it.  The
    Everyone view's copy names no field hidden from it — not its name, its
    values or its range (Edge cases' Label, whose text was written for
    engineers) — and no Admin starting view, which ticks that field.  The
    answers already go to each view this way (T-75); the server keeps the
    whole setup to check every request against."""
    if admin:
        return payload
    out = dict(payload)
    out.pop("admin_default_views", None)
    out["datasets"] = [
        dict(d, fields=[f for f in d["fields"] if not f.get("hidden_by_default")])
        for d in payload["datasets"]
    ]
    return out


def default_view_from(datasets: list, dataset_id: str = "heartbeats") -> dict:
    """A fresh question on one data set.  Heartbeats open newest first: the
    latest beats are what a person looks at a heartbeat log for."""
    ds = next(d for d in datasets if d["id"] == dataset_id)
    return {
        "dataset": ds["id"],
        "columns": list(ds["default_columns"]),
        "conditions": [],
        "sort": {"field": "ts", "dir": "desc"} if ds["has_time"] else None,
        "show": None,
        "summary": None,
    }


# ═════════════════════════════════════════════════════════════════════════
# 2 · The view → the pick
# ═════════════════════════════════════════════════════════════════════════

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


def to_pick(setup_payload: dict, view: dict) -> dict:
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
    pick = legality.default_pick()
    pick["source"] = next(d["source"] for d in DATASETS if d["id"] == ds["id"])
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
    for v in legality.evaluate(pick)["violations"]:
        raise ViewError(plain_reason(v["why"]))
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


# ── the engine's reasons, in plain words ───────────────────────────────

_WHY_ONLY_HEARTBEATS = "Only Heartbeats have a time to group by."

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


def plain_reason(why: str) -> str:
    """One of the engine's reasons → the page's words."""
    if why in _PLAIN_REASONS:
        return _PLAIN_REASONS[why]
    if why.startswith("unavailable on this source (operation 1)"):
        return _WHY_ONLY_HEARTBEATS
    return _PLAIN_REASON_DEFAULT


def unavailable(pick: dict) -> dict:
    """Which of the page's choices the engine can't do for this pick, and
    why, in plain words — read from the same contract /api/operations
    serves (operations.contract), never re-derived here."""
    from . import operations

    ops = {o["n"]: o for o in operations.contract(pick)["operations"]}
    out = {}
    for name, n in (("sort", 4), ("show", 5), ("per", 7)):
        if not ops[n]["enabled"]:
            out[name] = plain_reason(ops[n]["why"])
    return out


def _reasons_table(datasets: list) -> dict:
    """For each data set and each kind of answer (rows / one number / per
    hour or day), the choices that are off and why — what the page greys
    before it asks.  Each entry is the contract's own verdict."""
    out = {}
    for d in datasets:
        source = next(x["source"] for x in DATASETS if x["id"] == d["id"])
        base = legality.default_pick()
        base["source"] = source
        rows = dict(base)
        one = dict(base, aggregate={"fn": "count", "field": None})
        per = dict(base, aggregate={"fn": "count", "field": None}, bucket="day")
        out[d["id"]] = {"rows": unavailable(rows), "number": unavailable(one),
                        "per": unavailable(per)}
    return out


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


# ═════════════════════════════════════════════════════════════════════════
# 3 · Formatting a cell for a person
# ═════════════════════════════════════════════════════════════════════════

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


# ═════════════════════════════════════════════════════════════════════════
# 4 · The sentence (AC8) — by template, from the picks
# ═════════════════════════════════════════════════════════════════════════

def question_words(ds: dict, view: dict, fields: dict, *, sort: bool = True) -> str:
    """The question without its answer: ``Heartbeats where Status is warn,
    newest first``."""
    head = ds["name"]
    said = [words for _, words in _conditions(view, fields)]
    if said:
        head += " where " + joined_words(said, _logic(view.get("logic"), len(said), "Only rows where"))
    order = sort_words(view, fields) if sort else ""
    if order:
        head += ", " + order
    return head


def sentence(ds: dict, view: dict, fields: dict, total: int,
             of_total: int | None = None) -> str:
    """The question, restated in one line.  A template over the picks, never
    a model: ``Heartbeats where Status is warn, newest first — 412 rows``.

    ``of_total`` (T-72): how many rows the same choices match without
    the cap, when both engines agreed on it — ``the first 100 of 205 rows``.
    ``None`` keeps the capped wording that states no total."""
    show = view.get("show")
    head = question_words(ds, view, fields)
    if total == 0:
        tail = "no rows match"
    elif show is not None and total >= show:
        if of_total is not None and of_total <= show:
            tail = plural(of_total, "row")          # the cap cut nothing
        elif of_total is not None:
            tail = f"the first {fmt_number(str(show))} of {plural(of_total, 'row')}"
        else:
            tail = f"the first {plural(show, 'row')}"
    else:
        tail = plural(total, "row")
    return f"{head} — {tail}"


#: Notes for Admin about this one answer (T-75): set per request by the
#: route, appended to by any helper that had to leave something unsaid.
_NOTES: "contextvars.ContextVar[list | None]" = contextvars.ContextVar("dashboard_notes", default=None)


def _note(text: str) -> None:
    notes = _NOTES.get()
    if notes is not None and text not in notes:
        notes.append(text)


def _disagreed_total(what: str, a, b) -> str:
    """Admin's note when the engines disagree behind a total — worded for
    both ways that can happen (T-75)."""
    if a == b:
        return (f"The two engines found the same number of {what} ({a}) but disagreed on a "
                "value in them, so the sentence states no total.")
    return (f"The two engines disagreed on how many {what} these choices match "
            f"({a} against {b}), so the sentence states no total.")


def agreed_count(conn, pick: dict) -> int | None:
    """How many rows these choices match, counted through ``run_pick`` —
    both engines — and returned ONLY when the two agree.  ``None`` when
    they don't, or when the count is refused: the caller then says nothing
    it cannot stand behind (T-72 AC2)."""
    count_pick = dict(pick, aggregate={"fn": "count", "field": None},
                      bucket="off", computed=[], sort=None, cap=None)
    result = _run(conn, count_pick)
    if not result.get("accepted"):
        return None
    if result.get("verdict") != "agree":
        def first(pane):
            rows = (result.get("panes") or {}).get(pane, {}).get("rows") or []
            return rows[0]["c"][0] if rows and rows[0].get("c") else "none"
        _note(_disagreed_total("rows", first("sql"), first("python")))
        return None
    return int(Decimal(result["panes"]["sql"]["rows"][0]["c"][0]))


def agreed_rows(conn, pick: dict) -> int | None:
    """How many answer rows a pick returns without its cap — for a capped
    per-hour / per-day answer, the number of hours or days with rows —
    through both engines, ONLY when they agree."""
    result = _run(conn, dict(pick, cap=None))
    if not result.get("accepted"):
        return None
    if result.get("verdict") != "agree":
        cmp_ = result.get("comparison") or {}
        _note(_disagreed_total("hours or days", cmp_.get("sql_row_count"),
                               cmp_.get("python_row_count")))
        return None
    return int(result["panes"]["sql"]["row_count"])


# ═════════════════════════════════════════════════════════════════════════
# 5 · The answer
# ═════════════════════════════════════════════════════════════════════════

#: The runtime's named refusal (``xpr.f8``: a JSON number past the largest
#: double).  The one database error the dashboard answers instead of
#: raising; app.run_pick does not catch it on this path (the two-pane screen
#: answers HTTP 500 for the same pick; that screen is not changed here).
ENGINE_REFUSAL_SQLSTATE = "XPR01"

#: The headline of every refusal where the statement answered and the second
#: engine could not finish (scoreboard.py writes the same words).
SECOND_ENGINE_HEADLINE = "The second engine could not finish"

_CACHE_LOCK = threading.Lock()
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_SIZE = 8


def _second_engine_overflow(conn, exc, sql: dict) -> dict:
    """The second engine met a number Python cannot turn into a double
    (``OverflowError`` — a 401-digit integer, Edge cases' 1e400) on a row the
    statement itself never had to read: possible only when the statement
    stops early (a LIMIT).  No number is shown from a comparison that could
    not finish; the answer is a refusal, named (T-75)."""
    return {
        "accepted": False, "verdict": "no-compare", "comparison": {},
        "sql": sql,
        "refusal": {"headline": SECOND_ENGINE_HEADLINE,
                    "why": f"out-of-range magnitude in the second engine: {exc}"},
    }


def _statement_for_admin(conn, pick: dict, server_app) -> dict:
    """The statement that was sent and refused mid-run, rebuilt for the
    Admin panel — the engineer wants to read what the database refused.

    The failed statement left the transaction aborted: it is rolled back,
    the read-only guard is re-applied and read back (``refuse_writes``),
    and the same pick is built again by the same builder, exactly as
    ``run_pick`` built it.  If that cannot be done the panel says so; the
    answer itself is the refusal either way.
    """
    import builder

    # The same re-pinning the two-pane route does after its own mid-run
    # refusal (app.py, _float8_overflow_refusal): SET is transactional, so
    # the rollback reverted both db.py's pinned session values and the
    # read-only guard.  Outside the try on purpose: if the guard cannot be
    # re-applied, the request fails loudly rather than continuing on a
    # connection that might write.
    conn.rollback()
    for statement in settings.PINNED_SESSION_SQL:
        conn.execute(statement)
    server_app.refuse_writes(conn)
    try:
        norm = server_app.normalised_pick(pick)
        built = builder.build(norm, server_app.collection_keys(conn, norm["source"]))
        return {
            "display": server_app.render_display_sql(built),
            "parameterised": built.sql,
            "params": server_app._param_rows(built.params),
            "statement_sent": True,
        }
    except Exception:  # noqa: BLE001 — building the display only; the refusal stands
        return {"display": None, "statement_sent": True}


def _run(conn, pick: dict) -> dict:
    """``run_pick`` with every row of the answer, remembered per pick.

    A page turn re-asks the same pick; the seed is pinned and the session
    is read-only, so the answer to a pick cannot change while the process
    lives, and a page turn need not run both engines again.
    """
    from . import app as server_app   # the routes import this module

    key = json.dumps(pick, sort_keys=True)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    try:
        answer = server_app.run_pick(conn, pick, whole=True)
    except OverflowError as exc:
        return _second_engine_overflow(conn, exc, _statement_for_admin(conn, pick, server_app))
    except server_app.SecondEngineFailed as exc:
        # The statement answered and the second engine couldn't: nothing is
        # shown from an answer that couldn't be double-checked, never a 500
        # (T-79, as for a board).  Not cached: the next ask runs it again.
        return {
            "accepted": False, "verdict": "no-compare", "comparison": {},
            "sql": _statement_for_admin(conn, pick, server_app),
            "refusal": {"kind": "answer-unchecked",
                        "headline": SECOND_ENGINE_HEADLINE, "why": str(exc)},
        }
    except Exception as exc:  # noqa: BLE001 — one SQLSTATE, re-raised otherwise
        if getattr(exc, "sqlstate", None) != ENGINE_REFUSAL_SQLSTATE:
            raise
        # The runtime's own named refusal (a number past the largest double,
        # read by == or !=), raised mid-statement.  The engine is not
        # changed here; the page is told the truth in plain words instead
        # of "couldn't reach the data".  Nothing is cached: the connection
        # is closed after this request, and the next ask runs it again.
        return {
            "accepted": False,
            "verdict": "no-compare",
            "sql": _statement_for_admin(conn, pick, server_app),
            "comparison": {},
            "refusal": {
                "headline": "Refused while running",
                "why": f"{exc.sqlstate}: {str(exc).splitlines()[0]}",
            },
        }
    with _CACHE_LOCK:
        _CACHE[key] = answer
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return answer


#: What a refusal says to a person, by what the engine found.  The engine's
#: own words go to the admin panel unchanged.
_PLAIN_REFUSAL = (
    ("container operand", "Some rows hold a list or a group of values in a "
                          "field you're matching on, so it can't be compared "
                          "with one value."),
    ("out-of-range magnitude", "One of these values is too large to compute "
                               "with, so this can't be answered honestly."),
    ("exceeds float8 range", "One of these values is too large to compute "
                             "with, so this can't be answered honestly."),
    ("overflow", "A result here grows too large to compute, so this can't be "
                 "answered honestly."),
)
_PLAIN_REFUSAL_DEFAULT = "These choices can't be answered together. Try changing one."


def plain_refusal(refusal: dict | None) -> str:
    text = json.dumps(refusal or {}).lower()
    for needle, plain in _PLAIN_REFUSAL:
        if needle in text:
            return plain
    return _PLAIN_REFUSAL_DEFAULT


#: Why an answer was not double-checked, for Admin (T-79).  "Refused before
#: an answer existed" is true only when nothing answered.
UNCHECKED_REFUSED = "Not double-checked: this one was refused before an answer existed."
CHECKED_REFUSAL = {
    "repeat": "Double-checked — both engines found the same rows that would be shown twice, so no table is drawn.",
    "double-count": "Double-checked — both engines found the same rows that would be counted twice, so no board is drawn.",
}
UNCHECKED_SECOND_ENGINE = ("Not double-checked: the statement answered, but the second engine "
                           "could not finish, so nothing is shown.")
UNCHECKED_PROFILE = ("Not double-checked: the second engine could not work out what the match "
                     "does, so nothing is shown.")
UNCHECKED_MATCH = ("Not double-checked: the two engines disagree on what the match does, "
                   "so nothing is shown.")


def unchecked_line(answer: dict) -> str | None:
    """Admin's line when an answer was not compared: None when it was."""
    if answer.get("verdict") in ("agree", "disagree"):
        return None
    refusal = answer.get("refusal") or {}
    if refusal.get("kind") in ("repeat", "double-count") and (answer.get("match") or {}).get("verdict") == "agree":
        # the refusal's own numbers were worked out by both engines, and agreed
        # (S19 check, L1): it is not an unchecked answer
        return CHECKED_REFUSAL[refusal["kind"]]
    if refusal.get("kind") == "match-disagree":
        return UNCHECKED_PROFILE if (answer.get("match") or {}).get("python_error") else UNCHECKED_MATCH
    if refusal.get("headline") == SECOND_ENGINE_HEADLINE:
        return UNCHECKED_SECOND_ENGINE
    return UNCHECKED_REFUSED


def _admin_block(answer: dict) -> dict:
    sql = answer.get("sql") or {}
    comparison = answer.get("comparison") or {}
    refusal = answer.get("refusal")
    return {
        # What an admin reads: the statement with its values written in.
        "statement": sql.get("display"),
        # What the database actually receives: the statement with
        # placeholders, and the values beside it, sent separately.
        "parameterised": sql.get("parameterised"),
        "parameters": list(sql.get("params") or []),
        "sent": bool(sql.get("statement_sent")),
        "verdict": answer.get("verdict"),
        "differing_rows": comparison.get("differing_rows", 0),
        "compared_rows": comparison.get("compared_rows", 0),
        "refusal": None if refusal is None else {
            "headline": refusal.get("headline"),
            "why": refusal.get("why") or refusal.get("body"),
        },
        # Admin's "not double-checked" line, true to what happened (T-79):
        # the statement may have answered and the second engine not.
        "unchecked": unchecked_line(answer),
    }


def _refuse_hidden(view: dict, fields: dict) -> None:
    """The Everyone view names no field hidden from it (T-77's rule, held at
    the gate by T-76 AC8): not a column, a condition, the sort, a summary's
    field or a scoreboard's group.  A count's conditions and a match are
    checked in to_spec, which knows the counted data set."""
    named = list(view.get("columns") or []) if isinstance(view.get("columns"), list) else []
    conds = view.get("conditions")
    named += [c.get("field") for c in conds if isinstance(c, dict)] if isinstance(conds, list) else []
    for part, key in (("sort", "field"), ("summary", "field"), ("scoreboard", "by")):
        if isinstance(view.get(part), dict):
            named.append(view[part].get(key))
    for path in named:
        f = fields.get(_name(path))
        if f and f.get("hidden_by_default"):
            raise ViewError(f"{f['label']} isn't offered in this view.")


def answer(conn, setup_payload: dict, view: dict, page: int = 0, admin: bool = True) -> dict:
    """One view → what the dashboard draws.  ``admin`` False is the Everyone
    view, which may not name a field hidden from it."""
    ds, fields = _dataset(setup_payload, view)
    if not admin:
        _refuse_hidden(view, fields)
    if view.get("scoreboard") is not None:
        return scoreboard_answer(conn, setup_payload, view, page, admin)
    if view.get("matched") is not None:
        return matched_answer(conn, setup_payload, view, page, admin)
    pick = to_pick(setup_payload, view)
    result = _run(conn, pick)
    admin = _admin_block(result)

    if not result.get("accepted"):
        refusal = result.get("refusal") or {}
        if refusal.get("kind") == "answer-unchecked":
            _note(f"The second engine could not compute this answer ({refusal.get('why')}), "
                  "so it couldn't be double-checked and nothing is shown.")
            message = ANSWER_UNCHECKED
        else:
            message = plain_refusal(refusal)
        return {
            "kind": "refused",
            "sentence": question_words(ds, view, fields),
            "message": message,
            "admin": admin,
        }

    pane = result["panes"]["sql"]
    summary = _summary(view, fields, ds)
    if summary:
        return _summary_answer(conn, ds, view, fields, summary, pick, pane, page, admin)
    columns = pane["columns"]
    by_alias = {f["alias"]: f for f in fields.values()}
    shown = [i for i, c in enumerate(columns) if c in by_alias]
    total = pane["row_count"]

    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        page = 0
    last = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, last)
    start = page * PAGE_SIZE
    rows = []
    for row in pane["rows"][start:start + PAGE_SIZE]:
        rows.append([
            fmt_cell(row["c"][i], row["t"][i], by_alias[columns[i]]["kind"])
            for i in shown
        ])

    return {
        "kind": "table",
        "sentence": sentence(ds, view, fields, total, of_total=(
            agreed_count(conn, pick)
            if view.get("show") is not None and total >= view["show"] else None)),
        "total": total,
        "columns": [
            {"path": by_alias[columns[i]]["path"],
             "label": by_alias[columns[i]]["label"],
             "kind": by_alias[columns[i]]["kind"]}
            for i in shown
        ],
        "rows": rows,
        "page": {"index": page, "size": PAGE_SIZE, "start": start,
                 "count": len(rows), "last": last},
        "unavailable": unavailable(pick),
        "admin": admin,
    }


def _summary_value(text: str, tag: str, fn: str):
    """One summary value → (what a person reads, the exact value, a number
    for drawing).  An average is shown to two places, its exact value kept
    beside it; a total, a smallest and a largest are shown as they are."""
    if tag == "null":
        return None, None, None
    exact = text
    d = Decimal(text)
    if fn == "avg":
        shown = fmt_number(text, places=2)
    else:
        n = _normal(d)
        plain = n == 0 or _PLAIN_MIN_ADJUSTED <= n.adjusted() < _PLAIN_MAX_ADJUSTED
        shown = fmt_number(format(n, "f") if plain else text)
    drawn = float(d)
    return shown, exact, drawn if math.isfinite(drawn) else None


def _span(fields: dict) -> tuple[str, str]:
    """The data set's whole time span, read from the data at setup."""
    r = fields["ts"]["range"]
    return r["min"], r["max"]


def _slots(unit: str, lo: str, hi: str) -> list:
    """Every hour or day from ``lo`` to ``hi``, in the engine's own label
    form (``2026-08-14T00:00:00Z``)."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    t = _dt.datetime.strptime(lo, fmt)
    end = _dt.datetime.strptime(hi, fmt)
    if unit == "day":
        t, end = t.replace(hour=0, minute=0, second=0), end.replace(hour=0, minute=0, second=0)
    step = _dt.timedelta(days=1) if unit == "day" else _dt.timedelta(hours=1)
    out = []
    while t <= end:
        out.append(t.strftime(fmt))
        t += step
    return out


def summary_words(ds: dict, view: dict, fields: dict, summary: dict) -> str:
    """``Average Load of Heartbeats where Status is warn, per day``."""
    what = SUMMARY_FNS[summary["fn"]]
    if summary["field"]:
        what += " " + fields[summary["field"]]["label"]
    head = f"{what} of {question_words(ds, view, fields, sort=False)}"
    if summary["per"] != "all":
        head += f", per {summary['per']}"
    return head


def blank_reason(conn, pick: dict, field_label: str) -> str:
    """Why a summary over everything came back blank — in words that are
    true whether or not rows matched (test_dashboard.py ::
    TestABlankSummaryTellsTheTruth).

    A blank average, total, smallest or largest means either that no row
    matched, or that rows matched and none of them holds a number in the
    field.  "No rows match" is said only when the engine's own count over
    the same filter is 0; the count is asked through ``run_pick`` like any
    other pick, and used only when both engines agree on it (T-72).
    """
    n = agreed_count(conn, pick)
    if n is None:
        # The count was refused or the engines disagree on it: say only
        # what is true either way.
        return f"No value: no matching row has a value for {field_label}."
    if n == 0:
        return "No rows match"
    return (f"No value: {plural(n, 'row')} {'matches' if n == 1 else 'match'}, "
            f"and none has a value for {field_label}.")


def _summary_answer(conn, ds, view, fields, summary, pick, pane, page, admin) -> dict:
    fn = summary["fn"]
    head = summary_words(ds, view, fields, summary)
    label = SUMMARY_FNS[fn] + (" " + fields[summary["field"]]["label"] if summary["field"] else "")

    if summary["per"] == "all":
        row = pane["rows"][0]
        shown, exact, _ = _summary_value(row["c"][0], row["t"][0], fn)
        if fn == "count" and shown is not None:
            shown = fmt_number(row["c"][0])
        blank = None
        if shown is None:
            # count is never blank; every other function can be.
            blank = blank_reason(conn, pick, fields[summary["field"]]["label"])
        # A count of nothing IS 0 — and says why, in the same words the other
        # summaries use when no row matched (T-75).
        note = "No rows match" if fn == "count" and row["c"][0] == "0" else None
        return {
            "kind": "number",
            "sentence": head,
            "number": {"label": label, "value": shown, "exact": exact, "blank": blank,
                       "note": note},
            "unavailable": unavailable(pick),
            "admin": admin,
        }

    unit = summary["per"]
    label_of = (lambda w: fmt_day(w)) if unit == "day" else (lambda w: fmt_time(w).removesuffix(" UTC"))
    got = []
    for row in pane["rows"]:
        when = row["c"][0]
        shown, exact, num = _summary_value(row["c"][1], row["t"][1], fn)
        got.append({"label": label_of(when), "start": when, "value": num,
                    "text": shown, "exact": exact, "empty": False})

    # The engine returns only the hours or days that have rows.  The time
    # axis is kept whole — every hour or day of the data set's span gets a
    # slot, and one with no rows is an empty, marked slot — so two days
    # either side of an empty one never sit side by side as if adjacent
    # (test_dashboard.py :: TestTheTimeAxisIsWhole).  With a cap, the engine returned the first
    # N buckets that have rows; the axis is filled between those.
    show = view.get("show")
    capped = show is not None and len(got) >= show
    # A cap that cut nothing (exactly Show hours or days have rows) is no cap:
    # the axis is the whole span, as it is one step below Show (T-75).  Only
    # when both engines agree on the uncapped count.
    of = agreed_rows(conn, pick) if capped else None
    if capped and of is not None and of <= show:
        capped = False
    with_rows = len(got)
    by_start = {b["start"]: b for b in got}
    if not got:
        bars = []
    else:
        lo, hi = (got[0]["start"], got[-1]["start"]) if capped else _span(fields)
        bars = [by_start.get(t) or {"label": label_of(t), "start": t, "value": None,
                                    "text": None, "exact": None, "empty": True}
                for t in _slots(unit, lo, hi)]
        placed = {b["start"] for b in bars}
        if any(b["start"] not in placed for b in got):
            # A bucket with rows outside the axis would vanish from the
            # chart: fail loudly rather than draw a picture missing data.
            raise RuntimeError("a bucket with rows fell outside the time axis")
    total = len(bars)
    if with_rows == 0:
        tail = "no rows match"
    elif capped:
        if of is not None:
            tail = f"the first {fmt_number(str(show))} of {plural(of, unit)} with rows"
        else:
            tail = f"the first {plural(show, unit)} with rows"
    elif with_rows == total:
        tail = plural(total, unit)
    else:
        tail = f"{fmt_number(str(with_rows))} of {plural(total, unit)} have rows"

    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        page = 0
    last = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, last)
    start = page * PAGE_SIZE
    rows = [[b["label"], "no rows" if b["empty"] else b["text"]]
            for b in bars[start:start + PAGE_SIZE]]
    return {
        "kind": "chart",
        "sentence": f"{head} — {tail}",
        "total": total,
        "unit": unit,
        "measure": label,
        "bars": bars,
        "columns": [{"path": "bucket", "label": "Day" if unit == "day" else "Hour (UTC)", "kind": "text"},
                    {"path": "value", "label": label, "kind": "number"}],
        "rows": rows,
        "page": {"index": page, "size": PAGE_SIZE, "start": start,
                 "count": len(rows), "last": last},
        "unavailable": unavailable(pick),
        "admin": admin,
    }




# ═════════════════════════════════════════════════════════════════════════
# 5b · Scoreboards (T-73): one row per group, "count if" columns
# ═════════════════════════════════════════════════════════════════════════

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


#: The field names that read as a thing you can count ("3 statuses", "4
#: sites").  Declared, never guessed from the word: a name like Present,
#: Where code or Load is not a noun, and "2 presents" or "101 loads" reads
#: wrongly (T-79).  Every other field is counted as "2 values of Present".
COUNT_NOUNS = frozenset({"Sender", "Status", "Note", "Priority", "Name", "Site", "Kind"})


def _plural_noun(label: str, n: int, noun: bool = False) -> str:
    """``n`` groups of a board, in words: a data set's own word ("5 sites")
    or a declared noun ("3 statuses") is made plural; any other field name
    is said as "2 values of Present", which reads for every name."""
    if not (noun or label in COUNT_NOUNS):
        return f"1 value of {label}" if n == 1 else f"{fmt_number(str(n))} values of {label}"
    word = label.lower()
    if n == 1:
        return f"1 {word}"
    if word.endswith(("s", "x", "ch", "sh")):
        many = word + "es"
    elif word.endswith("y") and word[-2:-1] not in "aeiou":
        many = word[:-1] + "ies"
    else:
        many = word + "s"
    return f"{fmt_number(str(n))} {many}"


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


def _count_from(setup_payload: dict, ds: dict, fields: dict, count_from, admin: bool,
                verb: str = "count from"):
    """The match a scoreboard counts across (T-76), checked — or (None, None)
    for its own rows.  Returns ``({"to", "key", "parent_key", "match",
    "declared"}, the counted data set)``.  Every pick the screen can't make
    is refused by name (AC8)."""
    if count_from is None:
        return None, None
    if isinstance(count_from, str):
        # T-74's form: a declared relation, named by the data set it counts.
        relation = next((r for r in RELATIONS.get(ds["id"], []) if r["to"] == count_from), None)
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
                   and r["parent_key"] == f_parent["path"] for r in RELATIONS.get(ds["id"], []))
    return ({"to": rel_ds["id"], "key": f_counted["path"], "parent_key": f_parent["path"],
             "match": MATCH_TYPE_OF_KIND[f_parent["kind"]], "declared": declared,
             "field": f_counted, "matches": f_parent}, rel_ds)


def to_spec(setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
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
    relation, rel_ds = _count_from(setup_payload, ds, fields, sb.get("count_from"), admin)
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
        "source": next(d["source"] for d in DATASETS if d["id"] == ds["id"]),
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
            "source": next(d["source"] for d in DATASETS if d["id"] == relation["to"]),
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


def _run_group(conn, spec: dict) -> dict:
    """``run_group`` with the whole answer, remembered per spec — and the
    runtime's named refusal answered, as ``_run`` answers it."""
    from . import app as server_app
    from . import scoreboard

    key = "group:" + json.dumps(spec, sort_keys=True)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    try:
        result = scoreboard.run_group(conn, spec)
    except OverflowError as exc:
        built = group.build(spec)
        return _second_engine_overflow(conn, exc, {
            "display": server_app.render_display_sql(built), "parameterised": built.sql,
            "params": server_app._param_rows(built.params), "statement_sent": True})
    except Exception as exc:  # noqa: BLE001 — one SQLSTATE, re-raised otherwise
        if getattr(exc, "sqlstate", None) != ENGINE_REFUSAL_SQLSTATE:
            raise
        conn.rollback()
        for statement in settings.PINNED_SESSION_SQL:
            conn.execute(statement)
        server_app.refuse_writes(conn)
        built = group.build(spec)
        return {
            "accepted": False, "verdict": "no-compare", "comparison": {},
            "sql": {"display": server_app.render_display_sql(built),
                    "parameterised": built.sql,
                    "params": server_app._param_rows(built.params),
                    "statement_sent": True},
            "refusal": {"headline": "Refused while running",
                        "why": f"{exc.sqlstate}: {str(exc).splitlines()[0]}"},
        }
    with _CACHE_LOCK:
        _CACHE[key] = result
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return result


def _n(k: int, ds: dict) -> str:
    """"1 site", "19 senders" — a count in the data set's own words."""
    return f"{fmt_number(str(k))} {ds['one'] if k == 1 else ds['name'].lower()}"


def match_preview(ds: dict, rel_ds: dict, prof: dict, kept: bool) -> str:
    """T-76 AC3: what the chosen match does, in one plain line, from the
    agreed match profile — parents that match none, the spread of matches
    per parent, and counted rows that match no kept parent (not counted).
    ``kept`` says the page's conditions narrowed the parents."""
    if prof["parents"] == 0:
        return f"No {ds['name'].lower()} are kept here, so nothing is counted."
    if prof["most"] is None:
        return f"No {ds['one']} matches any {rel_ds['one']}, so every count is 0."
    matching = prof["parents"] - prof["parents_none"]
    least, most = prof["least"], prof["most"]
    spread = fmt_number(str(most)) if least == most else f"{fmt_number(str(least))} to {fmt_number(str(most))}"
    line = (f"{_n(matching, ds)} {'matches' if matching == 1 else 'match'} {spread} "
            f"{rel_ds['one'] if most == 1 else rel_ds['name'].lower()}{' each' if matching > 1 else ''}")
    if prof["parents_none"]:
        k = prof["parents_none"]
        line += f"; {_n(k, ds)} {'matches' if k == 1 else 'match'} none"
    line += "."
    k = prof["counted_none"]
    if k == 0:
        line += f" Every {rel_ds['one']} is counted."
    else:
        line += (f" {_n(k, rel_ds)} {'matches' if k == 1 else 'match'} no {ds['one']}"
                 f"{' kept here' if kept else ''} and {'isn' if k == 1 else 'aren'}'t counted.")
    return line


def double_count_line(ds: dict, rel_ds: dict, prof: dict) -> str:
    """T-76's refusal, in one line with its numbers: a counted row matching
    more than one kept parent would be counted once per parent."""
    line = (f"Each {rel_ds['one']} would be counted once for every {ds['one']} that matches it "
            f"— up to {fmt_number(str(prof['most_parents']))} times, for "
            f"{fmt_number(str(prof['counted_twice']))} of the {_n(prof['counted'], rel_ds)} "
            "— and a row is counted only once.")
    if any(r["to"] == ds["id"] for r in RELATIONS.get(rel_ds["id"], [])):
        line += f" Count it the other way round: {rel_ds['name']}, counting their {ds['name']}."
    return line


MATCH_UNCHECKED = "This match couldn't be double-checked, so it isn't counted."
BOARD_UNCHECKED = "This board couldn't be double-checked, so it isn't shown."
ANSWER_UNCHECKED = "This answer couldn't be double-checked, so it isn't shown."


def scoreboard_answer(conn, setup_payload: dict, view: dict, page: int = 0, admin: bool = True) -> dict:
    spec, about = to_spec(setup_payload, view, admin)
    ds, fields, by = about["ds"], about["fields"], about["by"]
    rel_ds, counted = about["rel_ds"], about["counted_fields"]
    # "Senders, counting their Heartbeats" when there is one row per parent
    # (grouped by its own key); "Senders per Site, counting their
    # Heartbeats" when grouped by another field.
    # Grouped by its own key (a sender's id) a board has one row per parent:
    # "Senders, counting their Heartbeats", or, counting its own rows,
    # "Senders, one row each" — never "Senders per Sender" (S11 check, LOW 3).
    own_key = by["path"] in {r["parent_key"] for r in RELATIONS.get(ds["id"], [])}
    head = ds["name"] if own_key else f"{ds['name']} per {by['label']}"
    said = [w for _, w in _conditions(view, fields)]
    if said:
        head += " where " + joined_words(said, _logic(view.get("logic"), len(said), "Only rows where"))
    relation = about["relation"]
    if rel_ds is not None:
        head += f", counting their {rel_ds['name']}"
        # A declared match reads as T-74's sentence, word for word; any other
        # match names the field it matches by (T-76 AC9).
        if not relation["declared"]:
            head += f" (by {relation['field']['label']})"
    elif own_key:
        head += ", one row each"
    what = rel_ds["name"] if rel_ds is not None else "rows"
    # What the tail counts: a board by the parent's own key has one row per
    # parent, so it counts those ("5 sites", not "5 names" — T-76: Sites'
    # own key is labelled Name); any other board counts its groups.
    noun = ds["one"] if own_key else by["label"]

    result = _run_group(conn, spec)
    admin_block = _admin_block(result)
    match = result.get("match")
    preview = None
    if relation is not None:
        f, m = relation["field"], relation["matches"]
        _note(f"The match: {rel_ds['name']}' {f['label']} = {ds['name']}' {m['label']}"
              + (f", over the {ds['name'].lower()} kept." if spec.get("filter") else "."))
        if match and match.get("verdict") == "agree" and match.get("profile"):
            preview = match_preview(ds, rel_ds, match["profile"], bool(spec.get("filter")))
    if not result.get("accepted"):
        kind = (result.get("refusal") or {}).get("kind")
        if kind == "double-count":
            message = double_count_line(ds, rel_ds, match["profile"])
        elif kind == "match-disagree":
            message = MATCH_UNCHECKED
            if match.get("python_error"):
                _note("The second engine could not profile the match "
                      f"({match['python_error']}), so it couldn't be double-checked and nothing is counted.")
            else:
                _note("The two engines disagree on what the match does — the statement's profile "
                      f"{json.dumps(match.get('profile'), default=str)} against the second engine's "
                      f"{json.dumps(match.get('python'), default=str)} — so nothing is counted.")
        elif kind == "board-unchecked":
            message = BOARD_UNCHECKED
            _note("The second engine could not compute this board "
                  f"({(result.get('refusal') or {}).get('why')}), so it couldn't be double-checked "
                  "and nothing is shown.")
        else:
            message = plain_refusal(result.get("refusal"))
        out = {"kind": "refused", "sentence": head, "message": message, "admin": admin_block}
        if relation is not None:
            out["match"] = {"preview": None if kind == "double-count" else preview,
                            "refused": kind in ("double-count", "match-disagree")}
        return out
    admin = admin_block

    pane = result["panes"]["sql"]
    names = pane["columns"]
    total = pane["row_count"]

    columns = [{"id": "group", "label": by["label"], "kind": by["kind"],
                "title": f"One row per {by['label']} found in the rows kept."},
               {"id": "rows", "label": rel_ds["name"] if rel_ds is not None else "Rows", "kind": "number",
                "title": f"How many {what} each group holds." if rel_ds is None
                         else f"How many {what} each group has (0 when it has none)."}]
    for i, c in enumerate(about["counts"], start=1):
        columns.append({"id": f"count:{c['id']}", "label": c["label"], "kind": "number",
                        "title": f"Counts the {what} in each group where {c['said']}."})
        if c["pct"]:
            columns.append({"id": f"pct:{c['id']}", "label": f"% {c['label']}", "kind": "number",
                            "title": f"“{c['label']}” as a share of the group's rows, to one decimal place."})
    if spec["time"]:
        word = TIME_WORDS[about["time"]["fn"]][1]
        f = counted[spec["time"]["field"]]
        columns.append({"id": "time", "label": f"{word} {f['label']}", "kind": f["kind"],
                        "title": f"The {word.lower()} {f['label']} in each group."})
    if spec["measure"]:
        f = counted[spec["measure"]["field"]]
        label = f"{SUMMARY_FNS[spec['measure']['fn']]} {f['label']}"
        columns.append({"id": "measure", "label": label, "kind": "number",
                        "title": f"The {label.lower()} over each group's rows."})

    def cell(name: str, text: str, tag: str):
        if name == "grp":
            return "(blank)" if tag == "null" else fmt_cell(text, tag, by["kind"])
        if tag == "null":
            return None
        if name.endswith("_pct"):
            return fmt_number(text, places=1) + "%"
        if name == "time":
            return fmt_cell(text, "string", counted[spec["time"]["field"]]["kind"])
        if name == "measure":
            return _summary_value(text, tag, spec["measure"]["fn"])[0]
        return fmt_number(text)

    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        page = 0
    last = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, last)
    start = page * PAGE_SIZE
    rows = [[cell(names[j], r["c"][j], r["t"][j]) for j in range(len(names))]
            for r in pane["rows"][start:start + PAGE_SIZE]]
    # An average is shown to two places; its six-place value rides beside
    # it for hover / tap, as it does for a single summary (T-75), so two
    # cells that read 3.02 and 3.02 are visibly not a tie.
    exact = []
    for r in pane["rows"][start:start + PAGE_SIZE]:
        exact.append([
            (f"To six places: {r['c'][j]}"
             if names[j] == "measure" and spec["measure"]["fn"] == "avg" and r["t"][j] != "null"
             else None)
            for j in range(len(names))])

    show = view.get("show")
    if total == 0:
        tail = "no rows match"
    elif show is not None and total >= show:
        full = _run_group(conn, dict(spec, cap=None))
        of = (full["panes"]["sql"]["row_count"]
              if full.get("accepted") and full.get("verdict") == "agree" else None)
        if full.get("accepted") and full.get("verdict") != "agree":
            cmp_ = full.get("comparison") or {}
            _note(_disagreed_total("groups", cmp_.get("sql_row_count"),
                                   cmp_.get("python_row_count")))
        if of is not None and of <= show:
            tail = _plural_noun(noun, of, own_key)
        elif of is not None:
            tail = f"the first {fmt_number(str(show))} of {_plural_noun(noun, of, own_key)}"
        else:
            tail = f"the first {_plural_noun(noun, show, own_key)}"
    else:
        tail = _plural_noun(noun, total, own_key)

    return {
        "kind": "scoreboard",
        "sentence": f"{head} — {tail}",
        "total": total,
        "columns": columns,
        "rows": rows,
        "titles": exact,
        "page": {"index": page, "size": PAGE_SIZE, "start": start,
                 "count": len(rows), "last": last},
        "unavailable": {"sort": "A scoreboard sorts by its own columns."},
        "match": None if relation is None else {"preview": preview, "refused": False},
        "admin": admin,
    }


# ═════════════════════════════════════════════════════════════════════════
# 5c · Matched fields in tables (T-78): another data set's fields beside
#      each row, by a field pair the person picks, never repeating a row
# ═════════════════════════════════════════════════════════════════════════

MATCHED_KEYS = {"dataset", "field", "matches", "columns"}
MATCHED_NEEDS_TABLE = ("Fields from another data set go beside a table's rows; "
                       "turn the summary or the scoreboard off first.")
MATCH_FIELDS_UNCHECKED = "This match couldn't be double-checked, so its fields aren't shown."


def lookups(ds_id: str) -> list:
    """The matches a table opens on: each declared relation read the other
    way (T-74's Senders → Heartbeats is each heartbeat's sender; T-76's
    Sites → Senders is each sender's site).  Never guessed from names."""
    return [{"id": parent, "field": r["parent_key"], "matches": r["key"]}
            for parent, rels in RELATIONS.items() for r in rels if r["to"] == ds_id]


def matched_label(rel_ds: dict, field: dict) -> str:
    """A matched column's name: the other data set's word and the field's
    — "Sender's Name", "Site's Capacity"."""
    one = rel_ds["one"]
    return f"{one[:1].upper()}{one[1:]}'s {field['label']}"


def to_lookup(setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
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
    relation, rel_ds = _count_from(setup_payload, ds, fields, pair, admin, verb="take fields from")
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
                   and x["matches"] == relation["parent_key"] for x in lookups(ds["id"]))
    spec = {
        "source": next(d["source"] for d in DATASETS if d["id"] == rel_ds["id"]),
        "key": relation["key"],
        "parent_key": relation["parent_key"],
        "match": relation["match"],
        "columns": [{"name": x["alias"], "path": x["field"]["path"]} for x in shown],
    }
    return spec, {"ds": ds, "rel_ds": rel_ds, "relation": relation, "shown": shown,
                  "declared": declared}


def _run_matched(conn, pick: dict, spec: dict) -> dict:
    """``run_lookup`` with the whole answer, remembered per pick — and the
    runtime's named refusals answered, as ``_run`` and ``_run_group`` do."""
    from . import app as server_app
    from . import matched

    key = "matched:" + json.dumps([pick, spec], sort_keys=True)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    try:
        result = matched.run_lookup(conn, pick, spec)
    except OverflowError as exc:
        return _second_engine_overflow(conn, exc, _matched_statement(conn, pick, spec, server_app))
    except Exception as exc:  # noqa: BLE001 — two SQLSTATEs, re-raised otherwise
        if getattr(exc, "sqlstate", None) not in (ENGINE_REFUSAL_SQLSTATE, "22003"):
            raise
        return {
            "accepted": False, "verdict": "no-compare", "comparison": {},
            "sql": _matched_statement(conn, pick, spec, server_app),
            "refusal": {"headline": "Refused while running",
                        "why": f"{exc.sqlstate}: {str(exc).splitlines()[0]}"},
        }
    if result.get("accepted") or (result.get("refusal") or {}).get("kind") == "repeat":
        with _CACHE_LOCK:
            _CACHE[key] = result
            _CACHE.move_to_end(key)
            while len(_CACHE) > _CACHE_SIZE:
                _CACHE.popitem(last=False)
    return result


def _matched_statement(conn, pick: dict, spec: dict, server_app) -> dict:
    """The statement that was sent and refused mid-run, rebuilt for Admin
    after the rollback (as ``_statement_for_admin`` does for a table)."""
    conn.rollback()
    for statement in settings.PINNED_SESSION_SQL:
        conn.execute(statement)
    server_app.refuse_writes(conn)
    try:
        norm = server_app.normalised_pick(pick)
        built = lookup.build(norm, server_app.collection_keys(conn, norm["source"]), spec)
        return {"display": server_app.render_display_sql(built), "parameterised": built.sql,
                "params": server_app._param_rows(built.params), "statement_sent": True}
    except Exception:  # noqa: BLE001 — building the display only; the refusal stands
        return {"display": None, "statement_sent": True}


def matched_words(about: dict, fields: dict) -> str:
    """What the sentence adds: ", with each one's Sender: Name and Site", and
    the pair when it isn't the declared one: "(matched by Load = Capacity)"."""
    labels = [x["field"]["label"] for x in about["shown"]]
    listed = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    rel_one = about["rel_ds"]["one"]
    out = f", with each one's {rel_one[:1].upper()}{rel_one[1:]}: {listed}"
    if not about["declared"]:
        out += (f" (matched by {about['relation']['matches']['label']} = "
                f"{about['relation']['field']['label']})")
    return out


def matched_preview(ds: dict, rel_ds: dict, prof: dict) -> str | None:
    """What the match does, in one plain line, from the agreed profile
    (every kept row matches at most one row here)."""
    rows, none = prof["rows"], prof["rows_none"]
    if rows == 0:
        return None
    some = rows - none
    blank = f"their {rel_ds['one']} fields are blank"
    if none == 0:
        return (f"Every {ds['one']} matches one {rel_ds['one']}." if rows > 1
                else f"The {ds['one']} matches one {rel_ds['one']}.")
    if some == 0:
        return f"No {ds['one']} here matches a {rel_ds['one']}, so {blank}."
    return (f"{_n(some, ds)} {'matches' if some == 1 else 'match'} one {rel_ds['one']}; "
            f"{fmt_number(str(none))} {'matches' if none == 1 else 'match'} none, so {blank}.")


def repeat_line(ds: dict, rel_ds: dict, prof: dict) -> str:
    """The refusal, in one line with its numbers: a row matching more than
    one row would be shown once per match."""
    if prof["rows"] == 1:
        # one kept row: never "for 1 of the 1 site" (S19 check, L2)
        return (f"The {ds['one']} would be shown once for every {rel_ds['one']} that matches it "
                f"— {fmt_number(str(prof['most']))} times — and a row is shown only once.")
    return (f"Each {ds['one']} would be shown once for every {rel_ds['one']} that matches it "
            f"— up to {fmt_number(str(prof['most']))} times, for "
            f"{fmt_number(str(prof['repeated']))} of the {_n(prof['rows'], ds)} "
            "— and a row is shown only once.")


def matched_answer(conn, setup_payload: dict, view: dict, page: int = 0, admin: bool = True) -> dict:
    spec, about = to_lookup(setup_payload, view, admin)
    ds, fields = _dataset(setup_payload, view)
    rel_ds, relation = about["rel_ds"], about["relation"]
    pick = to_pick(setup_payload, dict(view, matched=None))
    result = _run_matched(conn, pick, spec)
    admin_block = _admin_block(result)
    head = question_words(ds, view, fields) + matched_words(about, fields)
    _note(f"The match: {rel_ds['name']}' {relation['field']['label']} = "
          f"{ds['name']}' {relation['matches']['label']}"
          + (f", over the {ds['name'].lower()} kept." if pick.get("filter") else "."))
    match = result.get("match") or {}
    prof = match.get("profile") if match.get("verdict") == "agree" else None

    if not result.get("accepted"):
        refusal = result.get("refusal") or {}
        kind = refusal.get("kind")
        if kind == "repeat":
            message = repeat_line(ds, rel_ds, prof)
        elif kind == "match-disagree":
            message = MATCH_FIELDS_UNCHECKED
            if match.get("python_error"):
                _note("The second engine could not profile the match "
                      f"({match['python_error']}), so it couldn't be double-checked and nothing is shown.")
            else:
                _note("The two engines disagree on what the match does — the statement's profile "
                      f"{json.dumps(match.get('profile'), default=str)} against the second engine's "
                      f"{json.dumps(match.get('python'), default=str)} — so nothing is shown.")
        elif kind == "answer-unchecked":
            message = ANSWER_UNCHECKED
            _note(f"The second engine could not compute this answer ({refusal.get('why')}), "
                  "so it couldn't be double-checked and nothing is shown.")
        else:
            message = plain_refusal(refusal)
        return {"kind": "refused", "sentence": head, "message": message, "admin": admin_block,
                "match": {"preview": None if kind in ("repeat", "match-disagree") or prof is None
                          else matched_preview(ds, rel_ds, prof),
                          "refused": kind in ("repeat", "match-disagree")}}

    pane = result["panes"]["sql"]
    columns = pane["columns"]
    by_alias = {f["alias"]: {"path": f["path"], "label": f["label"], "kind": f["kind"]}
                for f in fields.values()}
    for x in about["shown"]:
        by_alias[x["alias"]] = {"path": "matched:" + x["field"]["path"], "label": x["label"],
                                "kind": x["field"]["kind"]}
    shown = [i for i, c in enumerate(columns) if c in by_alias]
    total = pane["row_count"]
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        page = 0
    last = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, last)
    start = page * PAGE_SIZE
    rows = [[fmt_cell(row["c"][i], row["t"][i], by_alias[columns[i]]["kind"]) for i in shown]
            for row in pane["rows"][start:start + PAGE_SIZE]]
    show = view.get("show")
    of_total = agreed_count(conn, pick) if show is not None and total >= show else None
    tail = sentence(ds, view, fields, total, of_total=of_total).rpartition(" — ")[2]
    return {
        "kind": "table",
        "sentence": f"{head} — {tail}",
        "total": total,
        "columns": [{"path": by_alias[columns[i]]["path"], "label": by_alias[columns[i]]["label"],
                     "kind": by_alias[columns[i]]["kind"]} for i in shown],
        "rows": rows,
        "page": {"index": page, "size": PAGE_SIZE, "start": start, "count": len(rows), "last": last},
        "unavailable": unavailable(pick),
        "match": {"preview": matched_preview(ds, rel_ds, prof) if prof else None, "refused": False},
        "admin": admin_block,
    }


# ═════════════════════════════════════════════════════════════════════════
# 6 · The routes
# ═════════════════════════════════════════════════════════════════════════

def _connect():
    from . import app as server_app

    conn = db.connect(application_name="autosql-demo-dashboard")
    server_app.refuse_writes(conn)
    return conn


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "dashboard.html").read_text())


@router.get("/api/dashboard/setup")
def api_setup(view: str = "everyone") -> JSONResponse:
    # ``?view=admin`` asks for the Admin view's setup; anything else is the
    # Everyone view's, which names no field hidden from it (T-79).
    conn = _connect()
    try:
        return JSONResponse(setup_for(setup(conn), view == "admin"))
    finally:
        conn.close()


@router.post("/api/dashboard/answer")
def api_answer(body: dict) -> JSONResponse:
    view = body.get("view") if isinstance(body, dict) else None
    page = body.get("page", 0) if isinstance(body, dict) else 0
    # The statement and the engines' verdict go only to a request that asks
    # for the Admin view (T-75): the Everyone view's response carries none
    # of it.  The demo has no login, so this is the shape GIMS must keep,
    # not a lock.
    wants_admin = isinstance(body, dict) and body.get("admin") is True
    conn = _connect()
    token = _NOTES.set([])
    try:
        payload = setup(conn)
        try:
            out = answer(conn, payload, view, page, admin=wants_admin)
        except ViewError as exc:
            return JSONResponse({"kind": "invalid", "sentence": "",
                                 "message": str(exc)}, status_code=422)
        if wants_admin:
            if "admin" in out:
                out["admin"] = dict(out["admin"], notes=list(_NOTES.get() or []))
        else:
            out.pop("admin", None)
        return JSONResponse(out)
    finally:
        _NOTES.reset(token)
        conn.close()
