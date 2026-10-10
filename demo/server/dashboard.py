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

from picks import view as _pv  # noqa: E402
from picks.view import (  # noqa: E402  (T-86: the view layer moved to picks/view.py)
    _TIME_RE, _DATE_RE, _PLAIN_KEY, _humanize, _natural, _alias, _TYPES_SQL, _INNER_TYPES_SQL,
    _VALUES_SQL, _RANGE_SQL, _kind, WHY_GROUPED, WHY_ONLY_BLANK, _ops_for, GROUP_LIMIT,
    _DISTINCT_SQL, _groupable, _ordered, CHIP_LIMIT, VALUE_LIMIT, SHOW_CHOICES, ViewError, _name,
    VIEW_KEYS, CONDITION_KEYS, SORT_KEYS, _SLOTS, _empty, _refuse_extra, _dataset, _columns, _show,
    SUMMARY_FNS, SUMMARY_KEYS, PERS, _summary, _PLAIN_REASONS, _PLAIN_REASON_DEFAULT, field_ref,
    string_literal, number_literal, _DAY_RE, _MINUTE_RE, _day, _instant, OP_WORDS, IN_LIMIT,
    _value_for, said_text, _order_key, condition, _conditions, LOGICS, WHY_LOGIC_NEEDS_TWO, _logic,
    compose, joined_words, filter_expression, SORT_WORDS, _sort, sort_words, _MONTHS, fmt_time,
    fmt_date, fmt_day, _number_text, _PLAIN_MAX_ADJUSTED, _PLAIN_MIN_ADJUSTED, _normal, fmt_number,
    _plain_json, fmt_cell, plural, SCOREBOARD_KEYS, COUNT_KEYS, COUNT_ID_MAX, TIME_KEYS,
    MEASURE_KEYS, COUNT_FROM_KEYS, MATCH_TYPE_OF_KIND, _KIND_WORDS, SB_SORT_KEYS, TIME_WORDS,
    LABEL_MAX, check_label, _same_name, _count_conditions, _count_from, MATCHED_KEYS,
    MATCHED_NEEDS_TABLE, matched_label,
)

router = APIRouter()

_STATIC = Path(__file__).resolve().parent.parent / "static"

#: Rows per table page.  The engine's own page size, so the two screens
#: agree on what "a page" is.
PAGE_SIZE = settings.PAGE_SIZE





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

#: What the demo says about its data sets, for the view layer (T-86): each data
#: set's collection, the relations above, and the time series' name on screen.
CATALOG = _pv.Catalog(
    sources={d["id"]: d["source"] for d in DATASETS},
    relations=RELATIONS,
    series_name="Heartbeats",
)


def to_pick(setup_payload: dict, view: dict) -> dict:
    """One view → one pick, in the engine's own shape (``picks.view.to_pick``,
    over the demo's catalog)."""
    return _pv.to_pick(CATALOG, setup_payload, view)


def to_spec(setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
    """A scoreboard view → (the engine's spec, what the screen needs)."""
    return _pv.to_spec(CATALOG, setup_payload, view, admin)


def to_lookup(setup_payload: dict, view: dict, admin: bool = True) -> tuple[dict, dict]:
    """A view's ``matched`` → (the engine's match spec, what the screen needs)."""
    return _pv.to_lookup(CATALOG, setup_payload, view, admin)


def to_category_spec(setup_payload: dict, view: dict) -> tuple[dict, dict]:
    """A summary per value of a field → (the engine's board spec, what the
    screen needs) (``picks.view.to_category_spec``, T-88)."""
    return _pv.to_category_spec(CATALOG, setup_payload, view)


def lookups(ds_id: str) -> list:
    """The matches a table opens on (a declared relation read the other way)."""
    return _pv.lookups(CATALOG, ds_id)


def plain_reason(why: str) -> str:
    """One of the engine's reasons → the page's words."""
    return _pv.plain_reason(why, CATALOG.series_name)


def _read_fields(conn, collection: str) -> list:
    """Every field of one data set, read out of the data, labelled the
    demo's way."""
    return _pv._read_fields(conn, collection, _LABELS)









# ── reading the fields out of the data ───────────────────────────────────





_COUNTS_SQL = (
    "SELECT collection, count(*) FROM demo.records GROUP BY collection"
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
























# ── the engine's reasons, in plain words ───────────────────────────────






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











































# ═════════════════════════════════════════════════════════════════════════
# 3 · Formatting a cell for a person
# ═════════════════════════════════════════════════════════════════════════























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
    # the engines compare the refusal's NUMBERS (how many rows, how many times), not which rows (S19 re-check, LOW)
    "repeat": "Double-checked — both engines found the same numbers: a row would be shown twice, so no table is drawn.",
    "double-count": "Double-checked — both engines found the same numbers: a row would be counted twice, so no board is drawn.",
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
    if isinstance(view.get("summary"), dict) and view["summary"].get("per") == "category":
        return category_answer(conn, setup_payload, view, page, admin)
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

    summary = _summary(view, fields, ds)
    if result.get("verdict") == "disagree":
        # T-87: an answer the two engines disagree on shows no number at all.
        return _disagreement(result, summary_words(ds, view, fields, summary) if summary
                             else question_words(ds, view, fields), admin)

    pane = result["panes"]["sql"]
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


def _span(fields: dict, time: str = "ts") -> tuple[str, str]:
    """The data set's whole span over one time or date field, read from the
    data at setup — a date as its UTC midnight (T-88)."""
    r = fields[time]["range"]
    as_time = (lambda v: v + "T00:00:00Z" if len(v) == 10 else v)
    return as_time(r["min"]), as_time(r["max"])


def _slots(unit: str, lo: str, hi: str) -> list:
    """Every hour, day, week (from its Monday) or calendar month from ``lo``
    to ``hi``, in the engine's own label form (``2026-08-14T00:00:00Z``)."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    t = _dt.datetime.strptime(lo, fmt)
    end = _dt.datetime.strptime(hi, fmt)

    def start(d):
        if unit == "hour":
            return d.replace(minute=0, second=0)
        d = d.replace(hour=0, minute=0, second=0)
        if unit == "week":
            return d - _dt.timedelta(days=d.weekday())
        if unit == "month":
            return d.replace(day=1)
        return d

    def step(d):
        if unit == "month":
            return d.replace(year=d.year + (d.month == 12), month=d.month % 12 + 1)
        return d + {"hour": _dt.timedelta(hours=1), "day": _dt.timedelta(days=1),
                    "week": _dt.timedelta(days=7)}[unit]

    t, end = start(t), start(end)
    out = []
    while t <= end:
        out.append(t.strftime(fmt))
        t = step(t)
    return out


#: How a per-time slot reads, and its column's name (T-88: weeks, months).
_UNIT_COLUMN = {"hour": "Hour (UTC)", "day": "Day", "week": "Week (from Monday)", "month": "Month"}


def _slot_label(unit: str, when: str) -> str:
    if unit == "day":
        return fmt_day(when)
    if unit == "week":
        return f"Week of {fmt_day(when)}"
    if unit == "month":
        return f"{_MONTHS[int(when[5:7]) - 1]} {when[:4]}"
    return fmt_time(when).removesuffix(" UTC")


def summary_words(ds: dict, view: dict, fields: dict, summary: dict) -> str:
    """``Average Load of Heartbeats where Status is warn, per day``."""
    what = SUMMARY_FNS[summary["fn"]]
    if summary["field"]:
        what += " " + fields[summary["field"]]["label"]
    head = f"{what} of {question_words(ds, view, fields, sort=False)}"
    if summary["per"] == "category":
        head += f", per {fields[summary['by']]['label']}"
    elif summary["per"] != "all":
        head += f", per {summary['per']}"
        if summary.get("time"):
            head += f" of {fields[summary['time']]['label']}"
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
    label_of = (lambda w: _slot_label(unit, w))
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
        lo, hi = (got[0]["start"], got[-1]["start"]) if capped else _span(fields, summary.get("time") or "ts")
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
        "columns": [{"path": "bucket", "label": _UNIT_COLUMN[unit], "kind": "text"},
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
#: T-87: what Everyone reads when the two engines worked an answer out and got
#: different numbers.  No number from it is shown.
DISAGREED = "These numbers didn't come out the same when they were double-checked, so they aren't shown."


def _disagreement(result: dict, sentence: str, admin_block: dict) -> dict:
    """An answer the two engines disagree on: refused in one plain line, no
    number from either side; Admin keeps the verdict and how many rows differ
    (T-87, the fix for the draw-on-disagree caveat — until then the statement's
    answer was drawn and only Admin saw the disagreement)."""
    cmp_ = result.get("comparison") or {}
    _note(f"The two engines disagree on {cmp_.get('differing_rows', '?')} of "
          f"{cmp_.get('compared_rows', '?')} rows, so no number is shown.")
    return {"kind": "refused", "sentence": sentence, "message": DISAGREED, "admin": admin_block}


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
    if result.get("verdict") == "disagree":
        out = _disagreement(result, head, admin_block)
        if relation is not None:
            out["match"] = {"preview": preview, "refused": False}
        return out

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

MATCH_FIELDS_UNCHECKED = "This match couldn't be double-checked, so its fields aren't shown."








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
    if result.get("verdict") == "disagree":
        out = _disagreement(result, head, admin_block)
        out["match"] = {"preview": matched_preview(ds, rel_ds, prof) if prof else None, "refused": False}
        return out

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


# ═════════════════════════════════════════════════════════════════════════
# 5d · One number per value of a field (T-88)
# ═════════════════════════════════════════════════════════════════════════

def category_answer(conn, setup_payload: dict, view: dict, page: int = 0, admin: bool = True) -> dict:
    """A summary per value of a field: one row per value — its count, or the
    total, average, smallest or largest of a number field over its rows —
    worked out by both engines as a board.  The blank group (missing or
    null) reads "(blank)"; an empty text value reads “”."""
    spec, about = to_category_spec(setup_payload, view)
    ds, fields, summary, by = about["ds"], about["fields"], about["summary"], about["by"]
    head = summary_words(ds, view, fields, summary)
    result = _run_group(conn, spec)
    admin_block = _admin_block(result)
    if not result.get("accepted"):
        refusal = result.get("refusal") or {}
        if refusal.get("kind") == "board-unchecked":
            _note(f"The second engine could not compute this answer ({refusal.get('why')}), "
                  "so it couldn't be double-checked and nothing is shown.")
            message = ANSWER_UNCHECKED
        else:
            message = plain_refusal(refusal)
        return {"kind": "refused", "sentence": head, "message": message, "admin": admin_block}
    if result.get("verdict") == "disagree":
        return _disagreement(result, head, admin_block)

    pane = result["panes"]["sql"]
    names = pane["columns"]
    fn = summary["fn"]
    label = SUMMARY_FNS[fn] + (" " + fields[summary["field"]]["label"] if summary["field"] else "")
    col = names.index("rows" if fn == "count" else "measure")
    items = []
    for r in pane["rows"]:
        g_text, g_tag = r["c"][0], r["t"][0]
        name = "(blank)" if g_tag == "null" else ("“”" if g_tag == "string" and g_text == "" else fmt_cell(g_text, g_tag, by["kind"]))
        text, tag = r["c"][col], r["t"][col]
        if fn == "count":
            shown, exact = fmt_number(text), text
        else:
            shown, exact, _ = _summary_value(text, tag, fn)
        items.append({"label": name, "value": shown, "exact": exact})
    total = pane["row_count"]
    show = view.get("show")
    if total == 0:
        tail = "no rows match"
    elif show is not None and total >= show:
        full = _run_group(conn, dict(spec, cap=None))
        of = (full["panes"]["sql"]["row_count"]
              if full.get("accepted") and full.get("verdict") == "agree" else None)
        tail = (_plural_noun(by["label"], of) if of is not None and of <= show
                else f"the first {fmt_number(str(show))} of {_plural_noun(by['label'], of)}" if of is not None
                else f"the first {_plural_noun(by['label'], show)}")
    else:
        tail = _plural_noun(by["label"], total)
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        page = 0
    last = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, last)
    start = page * PAGE_SIZE
    rows = [[i["label"], i["value"]] for i in items[start:start + PAGE_SIZE]]
    return {
        "kind": "categories",
        "sentence": f"{head} — {tail}",
        "total": total,
        "measure": label,
        "categories": items,
        "columns": [{"path": "category", "label": by["label"], "kind": "text"},
                    {"path": "value", "label": label, "kind": "number"}],
        "rows": rows,
        "page": {"index": page, "size": PAGE_SIZE, "start": start, "count": len(rows), "last": last},
        "unavailable": {"sort": "One number per value of a field is in the order of its values."},
        "admin": admin_block,
    }
