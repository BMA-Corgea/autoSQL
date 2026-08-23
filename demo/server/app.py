"""demo/server/app.py — the four routes, the full comparison, the paged rows.

Routes (locate §3.1 plus B22's contract route):

* ``GET  /``                — the screen (W14's committed bundles).
* ``GET  /api/operations``  — B22's control contract, the single source of
  truth the screen renders from.  Optional ``pick`` query parameter so the
  screen can re-derive the enabled set as controls change, without running
  a pick.
* ``GET  /api/fields``      — §4.4 item 3's per-collection vocabulary: the
  top-level JSON field names the alias validator checks against, and the
  numeric paths operations 6 and 8 offer.
* ``POST /api/pick``        — one pick, both panes, the whole comparison.

──────────────────────────────────────────────────────────────────────────
WHAT ``/api/pick`` DOES, IN ORDER (plan §4.1, §4.5)
──────────────────────────────────────────────────────────────────────────
1.  **legality** — ``legality.evaluate``, the same one function the screen
    greys its controls from.  A violation is answered in the matrix's own
    words (DR-2: never silently ignored, never silently defaulted).
2.  **the vocabulary** — the collection's top-level field names, read from
    the data and handed to *both* panes, so the identical alias check runs
    on the identical string.
3.  **the alias check** — §4.10's allowlist, run in its own phase before
    the builder so a refusal can say *which* check refused (mock views
    `#gate` and `#alias` are two different checks in one layer).  The
    builder runs the same function again; the rule lives in one file.
4.  **build** — parse → gate → compile → the statement (§4.2's four
    shapes).  A layer-1 refusal happens here, before any SQL exists.
5.  **probe** — §4.3's two probes, over the same rows the pick will read,
    **before** the pick's own statement.  A firing abandons the pick.
6.  **run both panes** — the parameterised statement on one side; the same
    source rows walked from scratch in Python on the other.  Neither is
    handed the other's result.
7.  **compare in full** (B25) — every row, every column, ``==``, **no
    tolerance anywhere**.  The page of 50 is display only.

──────────────────────────────────────────────────────────────────────────
THE COMPARISON, AND WHY IT HAS NO TOLERANCE (plan §8.1 row 3)
──────────────────────────────────────────────────────────────────────────
Every compared cell is reduced to a ``(json type, exact value)`` pair and
compared with ``==``:

* numbers become ``Decimal`` — from the SQL side by reading jsonb and
  ``numeric`` exactly (``db.exact_json_cursor``), from the Python side by
  ``Decimal(repr(f))``, which is the shortest decimal that round-trips a
  double and is precisely what Postgres prints for the same double
  (measured on this database: ``18::float8 / 7`` renders
  ``2.5714285714285716`` on both sides).  Two doubles are equal if and
  only if those decimals are equal, so this is a faithful equality and not
  a rounding convenience;
* **the type is carried**, because Python's ``True == 1`` and a boolean
  that quietly matched a number would be a disagreement the control could
  not see — the one comparison bug that would make §5's whole control
  useless while every test stayed green;
* objects are compared by content with key order irrelevant, which is what
  jsonb means by equality;
* a non-finite float (``inf`` out of ``expr.py``) is tagged apart from
  every number, so it can never compare equal to one by accident.

A tolerance is not a testing convenience here.  It is the mechanism by
which the defect this demo exists to show would be hidden.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# demo/ is not a package; the flat imports below are what make the
# exceptions caught here the same objects builder.py and probes.py raise.
_DEMO_DIR = Path(__file__).resolve().parent.parent
if str(_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(_DEMO_DIR))
_REPO_ROOT = _DEMO_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import builder  # noqa: E402
import gate  # noqa: E402
import legality  # noqa: E402
import probes  # noqa: E402
from pyrunner import shape as pyshape  # noqa: E402

from . import db, errors, operations, settings  # noqa: E402

__all__ = ["app", "run_pick", "compare_panes", "canonical",
           "display_text", "normalised_pick", "refuse_writes"]


def _pinned(name: str, path: Path):
    """A single pinned file, under the one module name ``builder`` uses.

    Both files are loaded by ``builder.py`` under exactly these names, so
    this returns builder's own module object rather than a second copy of
    it: one parser, one compiler, one set of exception classes.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: The vendored parser (AC-34) and the pinned T-1 compiler (Q19, AC-33).
expr = _pinned("autosql_demo_expr", _DEMO_DIR / "vendor" / "expr.py")
compiler = _pinned(
    "autosql_t1_compile", _REPO_ROOT / "spikes" / "T-1" / "proto" / "compile.py"
)


# ═════════════════════════════════════════════════════════════════════════
# 1 · The canonical value — what a comparison actually compares
# ═════════════════════════════════════════════════════════════════════════

NULL, BOOLEAN, NUMBER, STRING, ARRAY, OBJECT = (
    "null", "boolean", "number", "string", "array", "object"
)
#: A float that is not a real number (``inf`` out of ``expr.py`` on a value
#: above the largest double).  Tagged apart so it cannot equal a number.
NOT_A_NUMBER = "number-nonfinite"


def _canon_json(v: Any) -> tuple:
    """One jsonb-shaped value → ``(type, exact value)``."""
    if v is None:
        return (NULL, None)
    if isinstance(v, bool):          # before int: bool subclasses int
        return (BOOLEAN, v)
    if isinstance(v, int):
        return (NUMBER, Decimal(v))
    if isinstance(v, Decimal):
        if not v.is_finite():
            return (NOT_A_NUMBER, str(v))
        return (NUMBER, v)
    if isinstance(v, float):
        # repr is the shortest decimal that round-trips the double, which
        # is what Postgres prints for that same double.
        text = repr(v)
        if text in ("inf", "-inf", "nan"):
            return (NOT_A_NUMBER, text)
        return (NUMBER, Decimal(text))
    if isinstance(v, str):
        return (STRING, v)
    if isinstance(v, (list, tuple)):
        return (ARRAY, tuple(_canon_json(x) for x in v))
    if isinstance(v, dict):
        return (OBJECT, tuple(sorted((k, _canon_json(x)) for k, x in v.items())))
    raise TypeError(
        f"no comparison rule for {type(v).__name__} — refusing to guess "
        "whether two values of an unknown type are the same value"
    )


def canonical(v: Any, kind: str) -> tuple:
    """One cell → ``(type, exact value)``, given its column's kind.

    ``kind`` comes from the executed statement's own cursor
    (``db.column_kinds``) and is applied to **both** panes, so a column is
    never compared under one rule on one side and another on the other.
    """
    if kind == "json":
        return _canon_json(v)
    if v is None:
        return (NULL, None)
    if kind == "text":
        return (STRING, v)
    if kind == "bool":
        return (BOOLEAN, bool(v))
    if kind in ("exact", "int"):
        if isinstance(v, bool):
            return (BOOLEAN, v)
        if isinstance(v, (int, Decimal)):
            d = Decimal(v)
            return (NUMBER, d) if d.is_finite() else (NOT_A_NUMBER, str(d))
        if isinstance(v, float):
            return _canon_json(v)
        if isinstance(v, str):
            return (STRING, v)
    raise TypeError(f"no comparison rule for {type(v).__name__} in a {kind} column")


# ═════════════════════════════════════════════════════════════════════════
# 2 · Display — a pure function of the canonical value
# ═════════════════════════════════════════════════════════════════════════
#
# Display is derived from the canonical value and from nothing else, so two
# cells that compare equal always print the same text.  A screen showing
# `6` beside `6.0` under a green "both panes agree" banner would teach a
# reader to distrust the banner.

#: Below this the plain form is written out; outside it the exponent form
#: is used, which is what both Postgres and Python print there.
_PLAIN_LOW, _PLAIN_HIGH = -5, 20


def _number_text(d: Decimal) -> str:
    """A jsonb number's text — one text per value, whatever produced it."""
    d = d.normalize()               # unique representation per value
    where = d.adjusted()            # exponent of the leading digit
    if _PLAIN_LOW <= where <= _PLAIN_HIGH:
        if d.as_tuple().exponent > 0:
            d = d.quantize(Decimal(1))   # 1E+2 → 100
        return format(d, "f")
    return str(d).replace("E", "e")


def _json_text(c: tuple) -> str:
    """A canonical value as compact JSON text — for a container cell."""
    kind, value = c
    if kind == NULL:
        return "null"
    if kind == BOOLEAN:
        return "true" if value else "false"
    if kind == NUMBER:
        return _number_text(value)
    if kind == NOT_A_NUMBER:
        return value
    if kind == STRING:
        return json.dumps(value)
    if kind == ARRAY:
        return "[" + ",".join(_json_text(x) for x in value) + "]"
    return "{" + ",".join(
        json.dumps(k) + ":" + _json_text(x) for k, x in value
    ) + "}"


def display_text(c: tuple, kind: str) -> str:
    """The one string both panes print for a canonical value.

    ``exact`` columns keep their scale — ``round(x, 6)`` and ``q6(x)`` both
    produce six decimal places, and ``41.000000`` printed as ``41`` would
    throw away the half of §7.2's rule a reader can actually see.
    """
    tag, value = c
    if tag == NULL:
        return "null"
    if tag == BOOLEAN:
        return "true" if value else "false"
    if tag == STRING:
        return value
    if tag == NOT_A_NUMBER:
        return value
    if tag == NUMBER:
        return str(value) if kind == "exact" else _number_text(value)
    return _json_text(c)


# ═════════════════════════════════════════════════════════════════════════
# 3 · The two panes, in the one shape the comparison reads
# ═════════════════════════════════════════════════════════════════════════

def _canon_rows(rows, columns, kinds) -> list:
    return [
        tuple(canonical(row[c], kinds[i]) for i, c in enumerate(columns))
        for row in rows
    ]


def sql_pane(conn, built) -> dict:
    """Execute the parameterised statement and read the whole result.

    What executes is ``built.sql`` — the text carrying its ``%(…)s``
    placeholders (AC-27).  The display rendering is produced separately,
    for the pane, and is never handed to the driver.
    """
    cur = db.exact_json_cursor(conn)
    cur.execute(built.sql, built.params)
    kinds = db.column_kinds(cur)
    columns = tuple(col.name for col in cur.description)
    raw = cur.fetchall()
    cur.close()
    rows = [dict(zip(columns, r)) for r in raw]
    return {
        "columns": list(columns),
        "kinds": list(kinds),
        "rows": rows,
        "row_count": len(rows),
        "canon": _canon_rows(rows, columns, kinds),
    }


def python_pane(conn, pick: dict, kinds_by_column: dict) -> dict:
    """The second calculator's answer, in the same shape.

    Its rows come from ``pyrunner``, which reads the **source** rows out of
    the same database and applies the pick from scratch (spec §9.5).  It is
    never handed the SQL query's result, and this function does not give it
    one: the only thing it borrows from the SQL side is the *kind* of each
    column, which is a type and not a value.
    """
    answer = pyshape.python_pane(conn, pick)
    columns = list(answer["columns"])
    kinds = [kinds_by_column.get(c, "json") for c in columns]
    return {
        "columns": columns,
        "kinds": kinds,
        "rows": answer["rows"],
        "row_count": answer["row_count"],
        "canon": _canon_rows(answer["rows"], columns, kinds),
    }


# ═════════════════════════════════════════════════════════════════════════
# 4 · The comparison — in full, over the whole result (B25)
# ═════════════════════════════════════════════════════════════════════════

AGREE, DISAGREE, NO_COMPARE = "agree", "disagree", "no-compare"


def compare_panes(sql: dict, python: dict) -> dict:
    """Compare the two answers **in full**.  No tolerance, anywhere.

    Returns the verdict, the number of differing rows, the index of the
    first of them, and — per differing row — which columns differ, so the
    screen can mark the value rather than only announce the row (D8).
    """
    columns_match = sql["columns"] == python["columns"]
    a, b = sql["canon"], python["canon"]
    width = len(sql["columns"])

    differing: dict = {}
    for i in range(max(len(a), len(b))):
        if i >= len(a) or i >= len(b):
            # One pane ran out of rows: every column of the row differs.
            differing[i] = list(range(width))
            continue
        cols = [j for j in range(min(len(a[i]), len(b[i]))) if a[i][j] != b[i][j]]
        if len(a[i]) != len(b[i]):
            cols += list(range(min(len(a[i]), len(b[i])), max(len(a[i]), len(b[i]))))
        if cols:
            differing[i] = cols

    first = min(differing) if differing else None
    verdict = AGREE if (not differing and columns_match) else DISAGREE
    return {
        "verdict": verdict,
        "columns_match": columns_match,
        "differing_rows": len(differing),
        "first_differing_index": first,
        "compared_rows": max(len(a), len(b)),
        "sql_row_count": sql["row_count"],
        "python_row_count": python["row_count"],
        "_per_row": differing,
    }


def _page_start(first: int | None) -> int:
    """B25's D8: a disagreement is never below the fold of a paginator.

    Rows 0–49 unless the first differing row is past them, in which case
    the page starts five rows before it — so the differing row is on the
    page with a little of what precedes it, and the screen has something to
    scroll to.
    """
    if first is None or first < settings.PAGE_SIZE:
        return 0
    return max(0, first - 5)


def _rendered_pane(pane: dict, differing: dict, start: int, state: str,
                   note: str) -> dict:
    """One pane, as the screen receives it: the true total, and a page."""
    stop = start + settings.PAGE_SIZE
    kinds = pane["kinds"]
    out = []
    for i in range(start, min(stop, len(pane["canon"]))):
        cells = pane["canon"][i]
        row = {
            "i": i,
            "c": [display_text(cells[j], kinds[j]) for j in range(len(cells))],
            "t": [cells[j][0] for j in range(len(cells))],
        }
        if i in differing:
            row["diff"] = differing[i]
        out.append(row)
    return {
        "state": state,
        "columns": pane["columns"],
        "kinds": kinds,
        "row_count": pane["row_count"],
        "rows": out,
        "note": note,
    }


_EMPTY_PANE_NOT_ASKED = (
    "Not asked. Answering a pick the screen has just declared out of scope "
    "would be answering a question it refused to accept."
)
_EMPTY_PANE_ABANDONED = (
    "No number from this side. A probe found the condition below before the "
    "pick's own statement ran, so the statement was never sent."
)
_EMPTY_PANE_OVERFLOW = (
    "No number from this side. The statement was sent, and the database "
    "refused it mid-computation: float8 arithmetic overflowed (SQLSTATE "
    "22003, the pinned compiler's recorded divergence "
    "float8_overflow_raises). Nothing was written and nothing was committed "
    "— the session is read-only and the failed transaction was rolled back."
)
_SQL_NOTE = (
    "The parameterised statement above, run once against the demo's own "
    "database on 127.0.0.1:55440."
)
_PY_NOTE = (
    "The same source rows read out of the same database and walked in "
    "Python — decimal.Decimal, ROUND_HALF_UP, quantized to six places. "
    "Never handed the SQL query's result."
)


def _empty_pane(state: str, note: str) -> dict:
    return {
        "state": state, "columns": [], "kinds": [],
        "row_count": 0, "rows": [], "note": note,
    }


# ═════════════════════════════════════════════════════════════════════════
# 5 · The SQL pane's text (§9.3, AC-26, AC-27)
# ═════════════════════════════════════════════════════════════════════════

class _SqlLiteral:
    """A value ``render_for_display`` should print as SQL, not as Python.

    ``compile.py`` is pinned and never edited (Q19, AC-33), and its display
    helper prints anything that is not a string, bool or float with
    ``str()``.  A bound field path is a Python list, and ``['a', 'b']`` is
    not something a reader can paste into a client.  Wrapping it here gives
    the helper something whose ``str()`` is the array literal — without
    touching the pinned file, and without changing one bind value of what
    actually executes.
    """

    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text

    def __str__(self) -> str:
        return self.text


def _array_literal(parts) -> str:
    """A Python list of field-path parts → a Postgres ``text[]`` literal."""
    quoted = []
    for p in parts:
        s = str(p).replace("\\", "\\\\").replace('"', '\\"')
        quoted.append('"' + s + '"')
    inner = "{" + ",".join(quoted) + "}"
    return "'" + inner.replace("'", "''") + "'::text[]"


def _display_params(params: dict) -> dict:
    out = {}
    for name, value in params.items():
        out[name] = _SqlLiteral(_array_literal(value)) if isinstance(value, list) else value
    return out


def render_display_sql(built) -> str:
    """The pick's statement with its bind parameters substituted in (§9.3).

    Its own author's words, at ``compile.py:445-449``: *"NEVER execute this
    — the harness always executes the parameterised form."*  Nothing in
    this module passes the result to the driver, and ``test_ui.py`` asserts
    that at the driver boundary rather than by reading the code.
    """
    return compiler.render_for_display(built.sql, _display_params(built.params))


def _param_rows(params: dict) -> list:
    """The bind list the SQL pane prints — AC-28's *"only here"*."""
    rows = []
    for name in sorted(params):
        value = params[name]
        rows.append({
            "name": name,
            "value": json.dumps(value) if isinstance(value, (list, dict)) else str(value),
        })
    return rows


#: What each probe asks, in one sentence, so a reader of the pane does not
#: have to reverse-engineer the EXISTS (§4.3).
_PROBE_QUESTION = {
    "a": "is any operand of a numeric context at or above the largest double?",
    "b": "is either == operand actually a container on some row?",
}
#: B30 — a probe that was never built is STATED, not hidden.  A member with
#: no operands has nothing to ask; the pane says which and why, because the
#: demo's one claim is that the SQL on screen *is* the query.
_PROBE_NOT_BUILT = {
    "a": ("-- nothing to ask: no operand of this pick reaches a numeric "
          "context, so member (a) built no probe."),
    "b": ("-- nothing to ask: this pick has no == or != operand, so "
          "member (b) built no probe."),
}


def _probe_display_sql(probe, collection: str) -> str:
    """A probe with its bind parameters substituted in, like the pick's own
    statement — same helper, same rule, and just as never executed."""
    params = dict(probe.params)
    params["collection"] = collection
    for name in probe.ctx_params:
        params[name] = "{}"
    return compiler.render_for_display(probe.sql, _display_params(params))


def _probe_block(member: str, outcome, collection: str) -> str:
    head = f"-- probe ({member}) \u2014 {_PROBE_QUESTION[member]}"
    if outcome is None:
        return head + "\n" + _PROBE_NOT_BUILT[member]
    body = _probe_display_sql(outcome.probe, collection).rstrip().rstrip(";")
    tail = (
        f"-- fired. first offending row by key: {outcome.row_key!r}. "
        "the pick is abandoned here."
        if outcome.fired
        else "-- nothing found. the pick proceeds."
    )
    return head + "\n" + body + ";\n" + tail


def sql_pane_text(outcomes, display_sql, *, collection: str) -> str:
    """What §9.3 renders: the two pinned values, BOTH probes, the statement.

    B30, in full: the statement and both probes open, with the probe that
    did not run stated in a comment rather than hidden.  A collapsed probe
    is a question the demo asked the database and did not show — and a
    probe that was never built is a question it decided not to ask, which
    is worth exactly as much to a reader.
    """
    by_member = {o.probe.member: o for o in outcomes}
    parts = [
        "-- session values, SET on every connection the demo opens\n"
        + "\n".join(settings.PINNED_SESSION_SQL)
    ]
    for member in ("a", "b"):
        parts.append(_probe_block(member, by_member.get(member), collection))
    if display_sql is None:
        parts.append("-- the pick's own query was never built.")
    else:
        parts.append(
            "-- the pick's own query:\n"
            + display_sql.rstrip().rstrip(";") + ";"
        )
    return "\n\n".join(parts)


# ═════════════════════════════════════════════════════════════════════════
# 6 · The vocabulary reads (§4.4 item 3)
# ═════════════════════════════════════════════════════════════════════════

#: Numeric paths, one and two levels deep, read from the data.  Operations
#: 6 and 8 accept any dotted path; this is the list the screen OFFERS, and
#: two levels is what the seeded data has (``payload.load``).
_NUMERIC_FIELDS_SQL = """
SELECT k FROM (
    SELECT e.k AS k
      FROM demo.records r, LATERAL jsonb_each(r.data) AS e(k, v)
     WHERE r.collection = %(collection)s AND jsonb_typeof(e.v) = 'number'
    UNION
    SELECT e.k || '.' || e2.k AS k
      FROM demo.records r, LATERAL jsonb_each(r.data) AS e(k, v),
           LATERAL jsonb_each(e.v) AS e2(k, v)
     WHERE r.collection = %(collection)s
       AND jsonb_typeof(e.v) = 'object' AND jsonb_typeof(e2.v) = 'number'
) AS paths ORDER BY k
"""


def collection_keys(conn, collection: str) -> list:
    rows = conn.execute(
        settings.COLLECTION_KEYS_SQL, {"collection": collection}
    ).fetchall()
    return [r[0] for r in rows]


def numeric_fields(conn, collection: str) -> list:
    rows = conn.execute(
        _NUMERIC_FIELDS_SQL, {"collection": collection}
    ).fetchall()
    return [r[0] for r in rows]


# ═════════════════════════════════════════════════════════════════════════
# 7 · One pick, end to end
# ═════════════════════════════════════════════════════════════════════════

#: The field slots (operations 4, 6, 8) hold a field path.  ``builder.py``
#: accepts it with or without the leading ``$.``; ``pyrunner`` requires the
#: ``$.`` form — ``evaluate.dollar_path`` parses the slot with the vendored
#: parser and refuses anything that is not a bare field reference, and
#: ``payload.load`` is not one.  Measured, not assumed: a pick carrying
#: ``payload.load`` builds and runs on the SQL side and raises
#: ``ExprError: Expected '(' but found '.'`` on the Python side.
#:
#: NEW RULING (W13-1) — **the server normalises the field slots to the
#: ``$.`` spelling and hands the SAME pick to both panes.**  §4.5's
#: principle already says the vocabulary is computed on the server and
#: handed to both panes so the identical check runs on the identical
#: string; a field path is the same kind of thing.  Normalising in one
#: place beats teaching one pane a second spelling, because a pane that
#: accepts two spellings is a pane that can be handed a different field
#: from the other one and still answer.
_FIELD_SLOTS = (("sort", "field"), ("aggregate", "field"), ("window", "field"))

#: One step of a field path: an ordinary JSON identifier.
_PLAIN_STEP = r"[A-Za-z_][A-Za-z0-9_]*"
#: The whole of what a field slot may hold, once its ``$.`` is off: a
#: dotted run of those and nothing else.  See :func:`_as_dollar_path`.
_PLAIN_PATH = re.compile(rf"{_PLAIN_STEP}(?:\.{_PLAIN_STEP})*\Z")

#: The refusal a field slot gets when it holds something the two panes
#: would read differently.  Written once so the sort, aggregate and window
#: slots all say the same thing.
_FIELD_PATH_WHY = (
    "a field slot holds a plain field name, or a dotted run of them "
    "(`ts`, `payload.load`) — not an expression. The two calculators read a "
    "field slot with two different readers: the SQL side splits it on the "
    "dot and binds the pieces as the `#>` path, and the Python side parses "
    "it with the vendored expr.py. They agree on a plain dotted name and "
    "only on a plain dotted name, so anything else is refused here rather "
    "than sent to both of them to be read two different ways"
)


def _as_dollar_path(field: str) -> str:
    r"""A field slot in the one spelling both panes read — or a refusal.

    NEW RULING (W13-2) — **a field slot that is not a plain dotted run of
    identifiers is refused, by name, before any SQL exists.**

    W13-1 above normalises the field slots so both panes read one string,
    with ``"$." + field``.  That is only sound while the name is spellable
    after a dot, and a field slot's value does not have to be: it comes
    from ``/api/fields``, which serves **key names read out of the rows**
    (§4.4 item 3), and a JSON key is an arbitrary string.  Two measurements
    on this machine, both on the seam between the two panes:

    1. **A name the dot form cannot hold raises rather than answers.**  The
       sort slot carrying ``a";b`` — AC-28's own hostile name — became
       ``$.a";b`` and came back as
       ``ExprError: Unexpected character '"' at position 3`` out of
       ``demo/pyrunner/evaluate.py :: dollar_path``.  Loud, but a 500.

    2. **The bracket spelling that fixes (1) makes the two panes read two
       different fields.**  ``$["a\";b"]`` is what §4.4 item 3 names as
       the third form of a field path, and ``dollar_path`` reads it
       correctly as the single key ``a";b``.  ``demo/builder.py ::
       _field_path`` does not: it strips a leading ``$.``, splits the rest
       on ``.``, and binds the pieces — so it bound the **whole source
       text** as one key name, ``["$[\"a\\\";b\"]"]``, and the SQL
       pane ordered by a key no row has.  Both panes then agreed — on
       nothing, by accident, because a missing key sorts as NULL on one
       side and MISSING on the other and the tiebreak carried the result.

    (2) is plan §8.1's failure mode 1 in miniature: two calculators reading
    one pick two ways and agreeing anyway — here on a key no row has, so
    both sides sorted on nothing and the tiebreak made it look right.

    What this rule does **not** claim to fix: the dotted spelling means
    *nesting*, on both sides, so a key whose own name contains a dot is not
    addressable through a field slot at all.  Both panes read ``user.name``
    as ``['user','name']``, which is at least the **same** reading — it is a
    limit of the path grammar, not a divergence between the panes, and it
    is left exactly where §4.4 left it.

    So the slot is fenced instead: a plain dotted run of identifiers is
    normalised to the ``$.`` spelling exactly as before, and everything
    else is a named layer-1 refusal.  **Nothing the demo can show changes.**
    Every top-level key of all three seeded collections is a plain
    identifier — checked, 4 + 19 + 16 of them — and operation 4's field
    control is a ``select`` over that closed set (``operations.py``), so
    the screen cannot produce a refused slot.  What this closes is the API
    path and any future collection.

    **The narrower fix is in someone else's file.**  Teaching
    ``builder._field_path`` the bracket form would let the demo *sort by*
    such a key rather than refuse it.  That is W10's file and this item
    does not edit it; the refusal is the honest thing this item can do on
    its own, and it fails closed rather than open.
    """
    if field.startswith("$."):
        bare = field[2:]
    elif field.startswith("$"):
        bare = None          # bare `$`, or `$[...]` — never a plain path
    else:
        bare = field
    if bare is None or not _PLAIN_PATH.match(bare):
        raise gate.Refused(field, f"`{field}` is not a usable field path: "
                                  + _FIELD_PATH_WHY)
    return "$." + bare


def normalised_pick(pick: dict) -> dict:
    """One pick, with every field slot in the one spelling both panes read.

    A slot naming a **computed column** is left alone: that is an alias,
    not a path, and both panes look it up by name before treating it as
    one.

    Raises :class:`gate.Refused` — a layer-1 refusal, before any SQL —
    for a field slot no single spelling can carry to both panes.  See
    :func:`_as_dollar_path` (W13-2) for the two measurements behind that.
    """
    if not isinstance(pick, dict):
        raise TypeError("a pick is a JSON object")
    # A malformed computed slot (42, "notalist") is legality's to refuse by
    # name (shape_violations); this pass must merely not crash before the
    # refusal can happen.
    computed = pick.get("computed")
    aliases = ({cc.get("name") for cc in computed if isinstance(cc, dict)}
               if isinstance(computed, list) else set())
    out = dict(pick)
    for slot, key in _FIELD_SLOTS:
        holder = out.get(slot)
        if not isinstance(holder, dict):
            continue
        field = holder.get(key)
        if not isinstance(field, str) or not field or field in aliases:
            continue
        spelled = _as_dollar_path(field)
        if spelled != field:
            holder = dict(holder)
            holder[key] = spelled
            out[slot] = holder
    return out


def _field_ast(field: str, cc_asts: dict):
    """The AST a numeric read is fed — a computed column's, or a path's."""
    if field in cc_asts:
        return cc_asts[field]
    src = field if field.startswith("$") else "$." + field
    return expr.parse(src)


def _ordered_by(pick: dict, shape: str) -> str:
    if shape == legality.BUCKET:
        return "bucket"
    if shape == legality.SCALAR:
        return ""
    sort = pick.get("sort") or {}
    if sort.get("field"):
        return f"{sort['field']} {(sort.get('dir') or 'asc').upper()}, then key"
    return "key"


def _refused(payload: dict, *, pick: dict, panes: dict, sql_block: dict) -> dict:
    return {
        "accepted": False,
        "shape": legality.shape_of(pick),
        "source": pick.get("source"),
        "verdict": NO_COMPARE,
        "comparison": {
            "verdict": NO_COMPARE,
            "columns_match": True,
            "differing_rows": 0,
            "first_differing_index": None,
            "compared_rows": 0,
            "sql_row_count": 0,
            "python_row_count": panes["python"]["row_count"],
        },
        "panes": panes,
        "page": {"start": 0, "size": settings.PAGE_SIZE, "total": 0,
                 "ordered_by": ""},
        "sql": sql_block,
        "pinned": {"extra_float_digits": settings.EXTRA_FLOAT_DIGITS,
                   "time_zone": settings.TIME_ZONE},
        # The contract beside a refusal is rendered from the nearest
        # well-formed pick: ``contract`` reads raw slots, and a slot whose
        # TYPE is malformed (the thing being refused) must not crash the
        # refusal naming it.  ``pick`` itself is echoed back untouched.
        "operations": operations.contract(_contract_safe_pick(pick)),
        "pick": pick,
        "refusal": payload,
    }


def _sql_block(*, parameterised, display, params, outcomes, sent, collection):
    return {
        "parameterised": parameterised,
        "display": display,
        "params": _param_rows(params or {}),
        "probes": [
            {"member": o.probe.member, "fired": o.fired,
             "row_key": o.row_key, "sql": o.probe.sql}
            for o in outcomes
        ],
        "pane_text": sql_pane_text(outcomes, display, collection=collection),
        "statement_sent": sent,
    }


#: The reported-fallback pane, and the one place an exception from the
#: second calculator is caught.
#:
#: NEW RULING (W13-2) — **on the layer-2 path, and ONLY there, a second
#: calculator that cannot read the value says so instead of taking the
#: request down.**  Measured on this seed: walkthrough step 13 refuses at
#: layer 2 because ``edge-03`` holds a number above the largest double —
#: and the Python fallback then raises ``OverflowError: int too large to
#: convert to float`` inside GIMS's own ``expr.py`` (``_to_num``, line
#: 310).  ``demo/pyrunner/rows.py``'s docstring expects ``record_f`` to
#: hold ``float('inf')`` for that row; it does not, because jsonb renders
#: ``1e400`` as a plain 401-digit INTEGER and ``json.loads`` returns an
#: exact ``int`` for an integer literal whatever ``parse_float`` says.
#: ``float(that int)`` overflows.
#:
#: The raise is not a defect to hide: it is what GIMS's evaluator really
#: does with this value, and saying so is a stronger statement of the
#: demo's point than an ``inf`` would be — *neither* side can read it.  So
#: the pane reports the refusal by name.
#:
#: This catch is deliberately confined to the already-refused path.  On the
#: accepted path an exception from either pane propagates: a pick that
#: produces a number must never be able to produce it by swallowing
#: something.
def _fallback_python_pane(conn, pick: dict):
    try:
        py = python_pane(conn, pick, {})
    except Exception as exc:  # noqa: BLE001 — reported by name, see above
        return _empty_pane(
            "raised",
            "This side could not read the value either. The second "
            "calculator is GIMS's own expr.py, vendored byte-identically, "
            f"and evaluating this pick over these rows raised "
            f"{type(exc).__name__}: {exc}. The SQL side had already "
            "refused the same value at layer 2; neither engine can "
            "represent it.",
        ), 0
    return _rendered_pane(py, {}, 0, "answered", _PY_NOTE), py["row_count"]


def refuse_writes(conn) -> None:
    """The read-only guard, on the transaction the pick ACTUALLY runs in.

    ``db.connect()`` verifies the session (``db.py :: _verify``) before the
    caller ever sees the connection, and with autocommit off those reads
    have already opened the transaction everything after them runs in.
    ``SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`` alone sets
    ``default_transaction_read_only`` — the default for *later*
    transactions — and leaves the one already in progress read-write.
    Measured on this database before the fix: after that statement alone,
    ``SHOW transaction_read_only`` read ``off`` and an UPDATE was accepted.

    So both statements are issued: ``SET TRANSACTION READ ONLY`` pins the
    transaction already open, and the session characteristic pins any later
    one on the same connection (a rollback after a failed statement starts
    one).  The setting is then read back, in the same transaction, so the
    guard is a checked fact rather than a wish — the same
    set-then-read-back discipline ``db.py`` applies to the two pinned
    session values.
    """
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    conn.execute("SET TRANSACTION READ ONLY")
    got = conn.execute("SHOW transaction_read_only").fetchone()[0]
    if got != "on":
        raise RuntimeError(
            f"transaction_read_only reads {got!r} after the read-only guard "
            "— refusing to run on a transaction that can write to the "
            "seeded rows AC-10's digest is taken over"
        )


def _contract_safe_pick(pick: dict) -> dict:
    """The nearest well-formed pick, for rendering the control contract
    BESIDE a refusal — never for judging the pick.

    ``_refused`` puts ``operations.contract(pick)`` in every refusal body
    so the screen keeps rendering its controls, and ``contract`` reads the
    raw pick's slots.  A slot of the wrong JSON type has already been
    refused by name (``legality.shape_violations``) by the time this runs;
    dropping it HERE affects only the contract shown beside that refusal,
    so the display cannot crash the refusal that is trying to name the
    defect.  The pick itself is never repaired: what was judged, and what
    the refusal echoes back, is the pick as it arrived.
    """
    out = dict(pick)
    for slot in ("aggregate", "sort", "window"):
        if out.get(slot) is not None and not isinstance(out[slot], dict):
            del out[slot]
    computed = out.get("computed")
    if computed is not None and not isinstance(computed, list):
        del out["computed"]
    elif isinstance(computed, list):
        out["computed"] = [cc for cc in computed if isinstance(cc, dict)]
    for slot in ("source", "filter", "bucket"):
        if out.get(slot) is not None and not isinstance(out[slot], str):
            del out[slot]
    if out.get("changed") is not None and not isinstance(out["changed"], bool):
        del out["changed"]
    return out


#: Postgres's class-22 code for "value out of range: overflow" — what
#: float8 ``+ - * /`` raises when a finite double's square (say) is not a
#: double.  The pinned compiler RECORDS this divergence
#: (``KNOWN_DIVERGENCES.float8_overflow_raises``: Postgres raises where
#: Python returns ``inf``) and the demo left it unhandled — reachable from
#: the screen, since seeded ``edge-04`` holds ``g`` just below the range
#: guard, so ``$.g * $.g`` overflows.  It is caught by SQLSTATE, not by
#: exception class, because nothing in this file may import the driver
#: (plan §4.5: only ``db.py`` does).
_FLOAT8_OVERFLOW_SQLSTATE = "22003"


def _float8_overflow_refusal(conn, pick, exc, *, built, display_sql,
                             outcomes, source, shape) -> dict:
    """The float8-overflow refusal, named (spec §4.3's doctrine: whichever
    layer refuses, the person sees it, and it names what caused it).

    Shaped like a layer-2 refusal because that is what it is: SQL existed,
    the statement ran, and the database itself is the layer that refused —
    mid-computation rather than one question ahead of it.  The Python pane
    still answers, labelled, exactly as on the probe path.
    """
    # The failed statement aborted the transaction.  Nothing committed —
    # the session is read-only besides — but the Python pane still has to
    # read, so roll back and re-pin what the rollback reverts: SET is
    # transactional, and both db.py's two pinned session values and the
    # read-only guard ran inside the transaction that just died.
    conn.rollback()
    for statement in settings.PINNED_SESSION_SQL:
        conn.execute(statement)
    refuse_writes(conn)

    detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "value out of range: overflow"
    payload = {
        "layer": 2,
        "kind": "runtime",
        "headline": errors.LAYER_2_HEADLINE,
        "body": (
            "The expression was inside the subset, SQL was compiled and "
            "the statement was sent — and the database refused it "
            "mid-computation: float8 arithmetic overflowed. This is the "
            "pinned compiler's own recorded divergence "
            "(KNOWN_DIVERGENCES.float8_overflow_raises): Postgres raises "
            "where Python's float quietly becomes inf. No number came "
            "back from the SQL side, and refusing by name is the honest "
            "answer."
        ),
        "construct": "float8 overflow",
        "why": (
            f"the database refused the arithmetic: {detail} (SQLSTATE "
            f"{_FLOAT8_OVERFLOW_SQLSTATE}) — a float8 value in this "
            "expression exceeded the largest double, about "
            "1.7976931348623157e+308, while the statement ran"
        ),
        "row_key": None,
        "sql_existed": True,
        "statement_sent": True,
    }
    py_pane, py_total = _fallback_python_pane(conn, pick)
    body = _refused(
        payload, pick=pick,
        panes={"sql": _empty_pane("raised", _EMPTY_PANE_OVERFLOW),
               "python": py_pane},
        sql_block=_sql_block(parameterised=built.sql, display=display_sql,
                             params=built.params, outcomes=outcomes,
                             sent=True, collection=source),
    )
    body["page"]["total"] = py_total
    body["page"]["ordered_by"] = _ordered_by(pick, shape)
    return body


def run_pick(conn, pick: dict) -> dict:
    """One pick → the whole response body.  Separated from the route so the
    suite drives the same code the screen does, with no HTTP in the way."""
    # ── 0 · one spelling for the field slots, handed to both panes ──────
    #        A slot no single spelling reaches both panes with is refused
    #        here, at layer 1, before anything is built (W13-2).
    try:
        pick = normalised_pick(pick)
    except gate.Refused as exc:
        return _refused(
            errors.layer_1(exc, kind="field"),
            pick=pick,
            panes={"sql": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED),
                   "python": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED)},
            sql_block=_sql_block(parameterised=None, display=None,
                                 params={}, outcomes=[], sent=False,
                                 collection=pick.get("source") or ""),
        )

    # ── 1 · legality, from the one function the screen greys from ───────
    verdict = legality.evaluate(pick)
    if verdict["violations"]:
        return _refused(
            errors.illegal_pick(verdict["violations"]),
            pick=pick,
            panes={"sql": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED),
                   "python": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED)},
            sql_block=_sql_block(parameterised=None, display=None,
                                 params={}, outcomes=[], sent=False,
                                 collection=pick.get("source") or ""),
        )

    source = verdict["source"]
    keys = collection_keys(conn, source)

    # ── 2 · the alias check, in its own phase so a refusal can say which
    #        check refused.  gate.validate_alias is the one rule; the
    #        builder calls it again on the same strings.
    seen: list = []
    for cc in (pick.get("computed") or []):
        try:
            gate.validate_alias(cc.get("name"), keys, seen)
        except gate.Refused as exc:
            return _refused(
                errors.layer_1(exc, kind="alias"),
                pick=pick,
                panes={"sql": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED),
                       "python": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED)},
                sql_block=_sql_block(parameterised=None, display=None,
                                     params={}, outcomes=[], sent=False,
                                 collection=pick.get("source") or ""),
            )
        seen.append(cc.get("name"))

    # ── 3 · build: parse → gate → compile → the statement ───────────────
    try:
        built = builder.build(pick, keys)
    except gate.Refused as exc:
        return _refused(
            errors.layer_1(exc, kind="expression"),
            pick=pick,
            panes={"sql": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED),
                   "python": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED)},
            sql_block=_sql_block(parameterised=None, display=None,
                                 params={}, outcomes=[], sent=False,
                                 collection=pick.get("source") or ""),
        )
    except builder.IllegalPick as exc:
        return _refused(
            errors.illegal_pick(exc.violations),
            pick=pick,
            panes={"sql": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED),
                   "python": _empty_pane("not-asked", _EMPTY_PANE_NOT_ASKED)},
            sql_block=_sql_block(parameterised=None, display=None,
                                 params={}, outcomes=[], sent=False,
                                 collection=pick.get("source") or ""),
        )

    display_sql = render_display_sql(built)

    # ── 4 · the probes, before the pick's own statement ─────────────────
    cc_asts = {cc["name"]: expr.parse(cc["expr"])
               for cc in (pick.get("computed") or [])}
    exprs = list(cc_asts.values())
    if pick.get("filter"):
        exprs.append(expr.parse(pick["filter"]))
    roots = []
    agg_field = (pick.get("aggregate") or {}).get("field")
    if agg_field:
        roots.append(_field_ast(agg_field, cc_asts))
    win_field = (pick.get("window") or {}).get("field")
    if win_field:
        roots.append(_field_ast(win_field, cc_asts))

    try:
        outcomes = probes.check(conn, source, exprs, numeric_roots=roots)
    except probes.RuntimeRefusal as exc:
        # §4.5: no number from the SQL side; the Python pane still answers,
        # labelled as the reported fallback (AC-17, AC-18, mock view #probe).
        #
        # The probes are run once more here, on this path only, so §9.3 can
        # show BOTH of them — including the one that did not fire, stated
        # as a comment rather than hidden (§4.3).  check() raises on the
        # first firing and so cannot hand back the other outcome; the
        # decision stays its, and this is display.
        outcomes = probes.run_probes(
            conn, source,
            probes.build_probes(exprs, numeric_roots=roots),
        )
        py_pane, py_total = _fallback_python_pane(conn, pick)
        panes = {
            "sql": _empty_pane("abandoned", _EMPTY_PANE_ABANDONED),
            "python": py_pane,
        }
        body = _refused(
            errors.layer_2(exc), pick=pick, panes=panes,
            sql_block=_sql_block(
                parameterised=built.sql, display=display_sql,
                params=built.params, outcomes=outcomes, sent=False,
                collection=source),
        )
        body["page"]["total"] = py_total
        body["page"]["ordered_by"] = _ordered_by(pick, verdict["shape"])
        return body

    # ── 5 · both panes, then the whole comparison ───────────────────────
    # One database error, and only that one, is a refusal rather than a
    # defect: the float8 overflow the pinned compiler records as a known
    # divergence.  Anything else from either pane propagates — a pick that
    # produces a number must never produce it by swallowing something.
    try:
        sql = sql_pane(conn, built)
    except Exception as exc:  # noqa: BLE001 — one SQLSTATE, re-raised otherwise
        if getattr(exc, "sqlstate", None) != _FLOAT8_OVERFLOW_SQLSTATE:
            raise
        return _float8_overflow_refusal(
            conn, pick, exc, built=built, display_sql=display_sql,
            outcomes=outcomes, source=source, shape=verdict["shape"],
        )
    kinds_by_column = dict(zip(sql["columns"], sql["kinds"]))
    python = python_pane(conn, pick, kinds_by_column)
    comparison = compare_panes(sql, python)
    per_row = comparison.pop("_per_row")
    start = _page_start(comparison["first_differing_index"])

    return {
        "accepted": True,
        "shape": verdict["shape"],
        "source": source,
        "verdict": comparison["verdict"],
        "comparison": comparison,
        "panes": {
            "sql": _rendered_pane(sql, per_row, start, "answered", _SQL_NOTE),
            "python": _rendered_pane(python, per_row, start, "answered", _PY_NOTE),
        },
        "page": {
            "start": start,
            "size": settings.PAGE_SIZE,
            "total": comparison["compared_rows"],
            "ordered_by": _ordered_by(pick, verdict["shape"]),
        },
        "sql": _sql_block(parameterised=built.sql, display=display_sql,
                          params=built.params, outcomes=outcomes, sent=True,
                          collection=source),
        "pinned": {"extra_float_digits": settings.EXTRA_FLOAT_DIGITS,
                   "time_zone": settings.TIME_ZONE},
        "operations": operations.contract(pick),
        "pick": pick,
        "refusal": None,
    }


# ═════════════════════════════════════════════════════════════════════════
# 8 · The routes
# ═════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="autoSQL demo",
    docs_url=None, redoc_url=None, openapi_url=None,
)

_STATIC = _DEMO_DIR / "static"
_VENDOR = _DEMO_DIR / "vendor"


# W14 — the screen's two asset roots, and the ONE line of this file W14
# added.  The picking screen links the four vendored Watery stylesheets,
# and ``demo/vendor/ui.jsx``'s ``Icon`` resolves ``/static/icons.svg#i-…``
# with that URL hardcoded.  D1/D2 forbid copying ``demo/vendor/icons.svg``
# into ``demo/static/``, so the vendored tree is SERVED rather than
# duplicated:
#
#   /vendor/…            the vendored assets, read-only, byte-identical
#   /static/icons.svg    GIMS's 54-symbol sprite, from demo/vendor/
#   /static/…            the demo's own — demo.css, icons-demo.svg (the
#                        18 of B17), fonts/, and the committed bundles
#
# The sprite route is declared BEFORE the ``/static`` mount because
# Starlette matches routes in the order they were added, and a Mount at
# ``/static`` would otherwise answer 404 for it first.
# ── AC-32 · the vendored sheets are SERVED with their off-host
#            references removed ────────────────────────────────────────
#
# `demo/vendor/styles/watery.css`:8 is a live `@import url(…)` pointing at
# Google's font service.  `index.html` links that sheet, a browser fetches
# an applied stylesheet's `@import` unconditionally, and nothing here sets
# a Content-Security-Policy — so serving the file verbatim made every page
# load of a demo presented as fully offline go out to another host.  Found
# by the round-1 review; AC-32 is the criterion it breaks.
#
# THE FILE ITSELF MAY NOT BE EDITED.  D1 vendors it byte-identical from
# GIMS and `demo/manifest.json` pins its digest — that fidelity is its own
# acceptance criterion, checked by `test_vendor.py`.  So the removal
# happens HERE, in the layer that composes what goes out: the bytes on
# disk stay identical, and the bytes on the wire carry nothing that leaves
# this machine.
#
# NOTHING IS LOST BY REMOVING IT.  D11 already self-hosts the same face —
# `demo/static/demo.css` declares Inter from `demo/static/fonts/*.woff2`,
# and offline that has always been the only Inter the screen actually got.
# What changes is that it is now the only one the screen ever ASKS for.
#
# AND IT IS NOT A SILENT REWRITE.  Every removal is recorded in
# `STRIPPED_FROM_VENDORED_CSS` and asserted by name in
# `demo/tests/test_isolation.py`, so a re-vendored sheet that grows a new
# off-host reference is a visible, tested event rather than a quiet fix.
# The demo's OWN stylesheets are deliberately NOT put through this: a
# remote URL in a file this project can edit is a mistake to fail on, not
# one to paper over, and the same test fails on it.

#: A URL with an authority component — `scheme://host…` or `//host…` —
#: i.e. one that names a host to go to.  `data:`, `about:blank` and every
#: relative path have no authority and are left alone.
_URL_WITH_A_HOST = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:)?//", re.I)

#: `@import url(…)` / `@import "…"`, whole at-rule.  The quoted forms are
#: matched as whole strings so a semicolon INSIDE the URL cannot end the
#: at-rule early — the Google Fonts one has four, in `wght@300;400;…`, and
#: a looser pattern leaves half an address behind.
_CSS_AT_IMPORT = re.compile(
    r"""@import\s+
        (?: url\(\s* (?: '(?P<a>[^']*)' | "(?P<b>[^"]*)" | (?P<c>[^)\s]*) ) \s*\)
          | '(?P<d>[^']*)' | "(?P<e>[^"]*)" )
        [^;]*;?""",
    re.I | re.X,
)

#: Every other `url(…)` — a background, a mask, a font file.
_CSS_URL = re.compile(
    r"""url\(\s* (?: '(?P<a>[^']*)' | "(?P<b>[^"]*)" | (?P<c>[^)\s]*) ) \s*\)""",
    re.I | re.X,
)

#: Left where an off-host reference was.  It names no address on purpose:
#: these bytes are themselves swept for off-host URLs, and a sheet that
#: quoted the address it had just removed would fail that sweep for the
#: wrong reason.
_STRIP_NOTE = (
    "/* autoSQL, AC-32: an off-host reference was removed here when this "
    "vendored sheet was served. The file on disk is untouched and still "
    "byte-identical to GIMS's own (D1). Inter is self-hosted -- see "
    "/static/demo.css. */"
)

#: name → the off-host URLs removed from it, filled in as each sheet is
#: composed.  Read by the AC-32 test, which is what makes the removal a
#: checked fact rather than a comment.
STRIPPED_FROM_VENDORED_CSS: dict[str, list[str]] = {}

#: The vendored stylesheets, by name, read once.  The route below resolves
#: against THIS mapping and never against the path it was handed, so no
#: request can name a file outside `demo/vendor/styles/`.
_VENDORED_STYLESHEETS = {
    p.stem: p for p in sorted((_VENDOR / "styles").glob("*.css"))
}


def _points_at_another_host(target: str) -> bool:
    return bool(_URL_WITH_A_HOST.match(target.strip()))


def _url_target(m: "re.Match[str]") -> str:
    for name in ("a", "b", "c", "d", "e"):
        try:
            value = m.group(name)
        except IndexError:
            continue
        if value is not None:
            return value.strip()
    return ""


def offline_css(text: str) -> tuple[str, list[str]]:
    """`text` with every reference that would leave this host removed.

    Returns the rewritten sheet and the list of what was removed.  An
    `@import` goes entirely; any other `url(…)` is pointed at
    ``about:blank``, which is inert — a browser never puts a request on
    the wire for it — and which keeps the declaration syntactically whole
    so the rest of the rule still parses.
    """
    removed: list[str] = []

    def _drop_import(m: "re.Match[str]") -> str:
        target = _url_target(m)
        if not _points_at_another_host(target):
            return m.group(0)
        removed.append(target)
        return _STRIP_NOTE

    def _neutralise_url(m: "re.Match[str]") -> str:
        target = _url_target(m)
        if not _points_at_another_host(target):
            return m.group(0)
        removed.append(target)
        return "url(about:blank)"

    # `@import` first: it contains a `url(…)` of its own, and removing the
    # whole at-rule must not leave half of one behind.
    out = _CSS_AT_IMPORT.sub(_drop_import, text)
    out = _CSS_URL.sub(_neutralise_url, out)
    return out, removed


def vendored_css_as_served(name: str) -> tuple[str, list[str]]:
    """One vendored sheet, exactly as the route below sends it."""
    served, removed = offline_css(
        _VENDORED_STYLESHEETS[name].read_text(encoding="utf-8")
    )
    STRIPPED_FROM_VENDORED_CSS[name + ".css"] = removed
    return served, removed


if (_STATIC / "js").is_dir():

    @app.get("/static/icons.svg", include_in_schema=False)
    def vendored_sprite():
        """GIMS's sprite, at the URL its own Icon component asks for."""
        return FileResponse(_VENDOR / "icons.svg", media_type="image/svg+xml")

    # Declared BEFORE the ``/vendor`` mount, for the same reason the sprite
    # route is declared before ``/static``: Starlette matches routes in the
    # order they were added, and the Mount would otherwise answer first —
    # with the file verbatim, which is the defect.
    @app.get("/vendor/styles/{name}.css", include_in_schema=False)
    def vendored_stylesheet(name: str) -> Response:
        """A vendored Watery sheet, carrying nothing that leaves this host."""
        if name not in _VENDORED_STYLESHEETS:
            return Response(status_code=404)
        served, _removed = vendored_css_as_served(name)
        return Response(served, media_type="text/css; charset=utf-8")

    app.mount("/vendor", StaticFiles(directory=str(_VENDOR)), name="vendor")
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_NO_SCREEN_YET = (
    "<h1>autoSQL demo — the API is up</h1>"
    "<p>The picking screen is built from <code>GET /api/operations</code> "
    "and lands with the front-end bundles under "
    "<code>demo/static/js/</code>. The API answers now: "
    "<code>GET /api/operations</code>, <code>GET /api/fields</code>, "
    "<code>POST /api/pick</code>.</p>"
)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """The screen.  Says so plainly when the bundles are not built yet,
    rather than answering 404 as though the route were wrong."""
    page = _STATIC / "index.html"
    if page.is_file():
        return HTMLResponse(page.read_text())
    return HTMLResponse(_NO_SCREEN_YET, status_code=200)


class _BadQueryPick(ValueError):
    """The ``pick`` query parameter is not a JSON object."""


def _pick_from_query(raw: str | None) -> dict:
    """The ``?pick=`` parameter, or the initial state.

    Measured: ``json.loads`` on a malformed value came back through the
    route as an unhandled ``JSONDecodeError`` — HTTP 500, with nothing a
    screen or a reader could act on.  A refusal here says which parameter
    and why, in the same 422 shape ``/api/fields`` already uses for its
    closed set, so a client defect reads as a client defect (DR-2's rule
    for the pick body, applied to the one other route that takes a pick).
    """
    if not raw:
        return operations.default_pick()
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise _BadQueryPick(f"the `pick` parameter is not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise _BadQueryPick(
            "the `pick` parameter must be a JSON object describing a pick, "
            f"not a {type(parsed).__name__}"
        )
    return parsed


@app.get("/api/operations")
def api_operations(pick: str | None = None) -> JSONResponse:
    """B22's contract — the nine controls, and which are enabled right now.

    With no ``pick`` the initial state; with one, the same contract
    re-derived for it, which is how the screen greys a control the instant
    a pick makes it illegal rather than after a round trip through a run.
    """
    try:
        current = _pick_from_query(pick)
    except _BadQueryPick as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    # A slot of the wrong JSON TYPE cannot drive the controls — refused by
    # name (DR-2, legality.shape_violations), in the same 422 shape this
    # route already uses for a pick that is not JSON.  Measured before the
    # fix: ``?pick={"source":"noun:Heartbeat","sort":"ts"}`` answered a
    # bare HTTP 500 out of legality's readers.
    malformed = legality.shape_violations(current)
    if malformed:
        return JSONResponse(
            {"detail": "; ".join(
                f"operation {v['operation']}: {v['why']}" for v in malformed
            )},
            status_code=422,
        )
    return JSONResponse(operations.contract(current))


@app.get("/api/fields")
def api_fields(source: str | None = None) -> JSONResponse:
    """§4.4 item 3's vocabulary, read from the data, per collection.

    ``fields`` is the list the alias validator refuses against — the same
    list, from the same statement, that the server hands the builder — so
    the screen cannot offer a name the server will refuse.
    """
    collection = source or legality.HEARTBEAT
    if collection not in legality.SOURCES:
        return JSONResponse(
            {"detail": f"unknown source {collection!r}: the sources are a "
                       "closed set of three"},
            status_code=422,
        )
    conn = db.connect(application_name="autosql-demo-fields")
    try:
        refuse_writes(conn)
        return JSONResponse({
            "source": collection,
            "fields": collection_keys(conn, collection),
            "numeric_fields": numeric_fields(conn, collection),
        })
    finally:
        conn.close()


@app.post("/api/pick")
def api_pick(body: dict) -> JSONResponse:
    """One pick: both panes, the verdict, and the whole comparison."""
    pick = body.get("pick", body) if isinstance(body, dict) else body
    if not isinstance(pick, dict):
        # DR-2's rule, one level up: a `pick` key holding something other
        # than an object used to crash normalised_pick as a bare 500.
        return JSONResponse(
            {"detail": "the pick must be a JSON object describing a pick, "
                       f"not a {type(pick).__name__}"},
            status_code=422,
        )
    conn = db.connect(application_name="autosql-demo-pick")
    try:
        # The app reads; it never writes.  A pick cannot alter the seeded
        # rows AC-10's digest is taken over, whatever it asks for.
        # `refuse_writes` pins the transaction ALREADY OPENED by
        # db.connect()'s verification reads — the one this pick actually
        # runs in — and reads the setting back; the session-characteristics
        # statement alone provably did not (see its docstring).
        refuse_writes(conn)
        answer = run_pick(conn, pick)
    finally:
        conn.close()
    return JSONResponse(answer, status_code=200 if answer["accepted"] else 422)
