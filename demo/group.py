"""demo/group.py — shape E, GROUP: one row per group, "count if" columns (T-73).

The scoreboard the owner asked for, in the sql-gauntlet's own shape
(``aggregation-9`` / ``aggregation-10``): one row per value of a field, and
beside it counts of the rows where a set of conditions holds, written the
way the gauntlet teaches it::

    sum(CASE WHEN <condition> THEN 1 ELSE 0 END)

This is a fifth statement shape beside builder.py's four, and it lives in
its own file on purpose: the nine-operation pick, legality.py's matrix and
the two-pane screen are untouched by it.  It is built from builder.py's own
pieces — parse → gate → compile for every expression (``_compile_expression``),
B11's prefixed bind names (``namespace`` / ``merge_params``), §7.2's numeric
read (``numeric_read``) — so nothing here is a second implementation of a rule
that already has one.

THE SPEC (built and validated by ``demo/server/dashboard.py :: to_spec``;
``group.check`` re-checks its shape and fails loudly on anything else)::

    source   str            one of legality.SOURCES
    group    str            a plain dotted field path — the group key
    filter   str | None     one expression: the rows kept BEFORE grouping
    counts   [{"expr": str, "pct": bool}]   at most MAX_COUNTS; each a
                            count-if column (and, if pct, its % of rows)
    time     {"fn": "max"|"min", "field": path} | None   latest / earliest
    measure  {"fn": "sum"|"avg"|"min"|"max", "field": path} | None
    sort     {"column": <an output column name>, "dir": "asc"|"desc"} | None
    cap      int | None     how many groups

THE COLUMNS, fixed names, never user text: ``grp``, ``rows``, ``c1``…``c6``,
``c1_pct``…, ``time``, ``measure``.  A label a person types for a count-if
column never reaches this file.

THE RULES IT WRITES DOWN
* The group key is ``nullif(data #> path, 'null')``: an absent key and a JSON
  null are one group, the blank one — as ``->>`` would read them.
* A count-if counts rows where ``xpr.truthy(<expr>)`` — the same truthiness
  the page's filter uses, so a row counts exactly when the filter would keep
  it.  A row WITHOUT the field fails ``is``, ``more than`` and the other
  comparisons, but HOLDS for ``is not`` (it is not equal to the value
  picked) — the page has always read ``is not`` that way, both engines
  agree, and the screen says so where ``is not`` is picked.  0, never NULL: every group has at least one row, and
  ``sum(CASE … ELSE 0 END)`` over at least one row is a number.
* The % of rows is ``round(100.0 * <count-if> / count(*), 1)``, half away
  from zero (Postgres ``round`` on numeric), and ``coalesce(…, 0.0)`` gives a
  group with nothing counted (a sender with no heartbeats) ``0.0``, the same
  text the second engine writes (T-77).
* Latest / earliest compare the field's TEXT (``#>>``) under the database's
  C collation; only fixed-width ISO time and date fields are offered, whose
  text order is time order.
* Every result is in a total order: the chosen column, NULLS LAST, then the
  group key ascending, NULLS LAST.  The group key is unique per row of the
  answer, so paging can never drop or double a group.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

_DEMO_DIR = str(Path(__file__).resolve().parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import builder  # noqa: E402
import legality  # noqa: E402

GROUP = "GROUP"
PROFILE = "PROFILE"

#: How a match compares (T-76): the jsonb type a counted row's match value
#: must have.  Text, dates and times are JSON strings; numbers are numbers.
#: With the type guard on one side, jsonb's own ``=`` does the rest: text
#: exactly, numbers by value (2 = 2.0, exact past 2^53, 1e400 intact), never
#: across types (1 is not "1") — and a JSON null, list or object, which the
#: guard keeps out, never matches anything.
MATCH_TYPES = ("string", "number")

#: The match profile's columns (T-76): what the preview says and what the
#: double-count check reads, in both engines.
PROFILE_COLUMNS = ("parents", "parents_none", "least", "most",
                   "counted", "counted_none", "counted_twice", "most_parents")

#: At most this many count-if columns (T-73 AC2).
MAX_COUNTS = 6

TIME_FNS = {"max": "max", "min": "min"}
MEASURE_FNS = ("sum", "avg", "min", "max")
SORT_DIRS = {"asc": "ASC", "desc": "DESC"}

_PLAIN_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z")


class Built(NamedTuple):
    sql: str
    params: dict
    shape: str
    columns: tuple


def columns_of(spec: dict) -> list:
    """The answer's column names, in SELECT order — one function, so the
    statement and the second engine cannot list them differently."""
    cols = ["grp", "rows"]
    for i, c in enumerate(spec.get("counts") or [], start=1):
        cols.append(f"c{i}")
        if c.get("pct"):
            cols.append(f"c{i}_pct")
    if spec.get("time"):
        cols.append("time")
    if spec.get("measure"):
        cols.append("measure")
    return cols


def _path(field: str, what: str) -> list:
    if not isinstance(field, str) or not _PLAIN_PATH.match(field):
        raise ValueError(f"{what} must be a plain field path, not {field!r}")
    return field.split(".")


def check(spec: dict) -> None:
    """The spec's own shape — loud on anything a caller let through."""
    if spec.get("source") not in legality.SOURCES:
        raise ValueError(f"unknown source {spec.get('source')!r}")
    _path(spec.get("group"), "the group")
    counts = spec.get("counts") or []
    if len(counts) > MAX_COUNTS:
        raise ValueError(f"at most {MAX_COUNTS} count-if columns")
    for c in counts:
        if not isinstance(c.get("expr"), str) or not c["expr"].strip():
            raise ValueError("a count-if column needs one expression")
    t = spec.get("time")
    if t is not None:
        if t.get("fn") not in TIME_FNS:
            raise ValueError(f"unknown time function {t.get('fn')!r}")
        _path(t.get("field"), "the time field")
    m = spec.get("measure")
    if m is not None:
        if m.get("fn") not in MEASURE_FNS:
            raise ValueError(f"unknown measure function {m.get('fn')!r}")
        _path(m.get("field"), "the measured field")
    s = spec.get("sort")
    if s is not None:
        if s.get("column") not in columns_of(spec) or s.get("dir") not in SORT_DIRS:
            raise ValueError(f"cannot sort by {s!r}")
    cap = spec.get("cap")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int)
                            or not legality.CAP_MIN <= cap <= legality.CAP_MAX):
        raise ValueError(f"the cap must be a whole number from 1 to {legality.CAP_MAX}")
    rel = spec.get("related")
    if rel is not None:
        if not isinstance(rel, dict) or rel.get("source") not in legality.SOURCES:
            raise ValueError(f"unknown related source {rel!r}")
        _path(rel.get("key"), "the related rows' key")
        _path(rel.get("parent_key"), "the parent's key")
        if rel.get("match") not in MATCH_TYPES:
            raise ValueError(f"unknown match type {rel.get('match')!r}")


def _match_on(rel: dict, params: dict, counted: str, parent: str) -> str:
    """The one way a counted row matches a parent, in both statements: the
    type guard on the counted side, then jsonb ``=`` — never ``#>>`` text."""
    params["rel_key"] = _path(rel["key"], "the related rows' key")
    params["rel_parent_key"] = _path(rel["parent_key"], "the parent's key")
    params["rel_match"] = rel["match"]
    return (f"jsonb_typeof( {counted} #> %(rel_key)s ) = %(rel_match)s\n"
            f"   AND ( {counted} #> %(rel_key)s ) = ( {parent} #> %(rel_parent_key)s )")


def build(spec: dict) -> Built:
    """One scoreboard spec → one parameterised statement (shape E).

    With ``related`` (T-74; any chosen match since T-76), the groups come
    from the PARENT rows (``r``) and everything counted comes from their
    related rows (``c``), joined by the match (:func:`_match_on` — the type
    guard and jsonb ``=``) with a LEFT JOIN — so a parent with no related rows
    is still a group, with Rows = ``count(c.key)`` = 0 (never ``count(*)``,
    which would read 1 for it), every count-if 0 (a count-if also requires
    ``c.key IS NOT NULL``, so a condition that holds on a missing value —
    ``is not`` — cannot count the empty side of the join), its % 0, and
    its latest / measure blank.  The page filter reads the parent."""
    check(spec)
    params: dict = {"collection": spec["source"], "grp_path": _path(spec["group"], "the group")}
    rel = spec.get("related")
    col = "c.data" if rel else "r.data"          # what is counted
    rows_sql = "count(c.key)" if rel else "count(*)"
    present = "c.key IS NOT NULL AND " if rel else ""

    select = ['nullif( r.data #> %(grp_path)s, \'null\'::jsonb )  AS "grp"',
              f'{rows_sql}  AS "rows"']

    for i, c in enumerate(spec.get("counts") or [], start=1):
        frag = builder._compile_expression(c["expr"], ctx_param=f"k{i}_ctx", column=col)
        sql, prm = builder.namespace(frag, f"k{i}")
        builder.merge_params(params, prm)
        hit = f"sum( CASE WHEN {present}xpr.truthy( {sql} ) THEN 1 ELSE 0 END )"
        select.append(f'{hit}  AS "c{i}"')
        if c.get("pct"):
            # The count-if's own text again, with the same bind names: one
            # condition, one set of values, read twice.
            select.append(
                f"coalesce( round( 100.0 * {hit} / nullif( {rows_sql}, 0 ), 1 ), 0.0 )"
                f'  AS "c{i}_pct"')

    t = spec.get("time")
    if t:
        params["time_path"] = _path(t["field"], "the time field")
        select.append(f'{TIME_FNS[t["fn"]]}( {col} #>> %(time_path)s )  AS "time"')

    m = spec.get("measure")
    if m:
        params["msr_path"] = _path(m["field"], "the measured field")
        body = f'{m["fn"]}( {builder.numeric_read(col + " #> %(msr_path)s")} )'
        if m["fn"] in ("sum", "avg"):
            body = f"round( {body}, 6)"
        select.append(f'{body}  AS "measure"')

    source = "  FROM demo.records AS r\n"
    if rel:
        params["rel_source"] = rel["source"]
        source += ("  LEFT JOIN demo.records AS c\n"
                   "    ON c.collection = %(rel_source)s\n"
                   f"   AND {_match_on(rel, params, 'c.data', 'r.data')}\n")

    where = " WHERE r.collection = %(collection)s"
    if spec.get("filter"):
        frag = builder._compile_expression(spec["filter"], ctx_param="flt_ctx", column="r.data")
        sql, prm = builder.namespace(frag, builder.PREFIX_FILTER)
        builder.merge_params(params, prm)
        where += f"\n   AND xpr.truthy( {sql} )"

    s = spec.get("sort") or {"column": "grp", "dir": "asc"}
    order = f'"{s["column"]}" {SORT_DIRS[s["dir"]]} NULLS LAST'
    if s["column"] != "grp":
        order += ', "grp" ASC NULLS LAST'

    limit = ""
    if spec.get("cap") is not None:
        params["cap"] = spec["cap"]
        limit = "\n LIMIT %(cap)s"

    sql = (
        "SELECT " + ",\n       ".join(select) + "\n"
        + source
        + where + "\n"
        " GROUP BY 1\n"
        f" ORDER BY {order}"
        + limit + ";"
    )
    # Every compiled fragment's ctx bind gets the empty context, as
    # builder.build does for its own shapes.
    builder._bind_ctx_values(sql, params, builder._ctx_json(None))
    return Built(sql, params, GROUP, tuple(columns_of(spec)))


def build_profile(spec: dict) -> Built:
    """The match profile (T-76): one row saying what the chosen match does
    over the KEPT parents (the page filter applies), before anything is
    counted — read by the preview and by the double-count check.

    * parents / parents_none — kept parents, and those matching no row;
    * least / most — the fewest and most rows a parent matches, among the
      parents that match any (NULL when none does);
    * counted / counted_none — rows of the counted data set, and those
      matching no kept parent (they are not counted);
    * counted_twice / most_parents — rows matching MORE THAN ONE kept parent
      (any is a refusal: a row is counted at most once), and the most parents
      any one row matches.

    Keys are unique per collection (demo.records' primary key), so counting
    keys counts rows."""
    check(spec)
    rel = spec.get("related")
    if not rel:
        raise ValueError("a match profile needs a related data set")
    params: dict = {"collection": spec["source"], "rel_source": rel["source"]}
    on = _match_on(rel, params, "c.data", "p.data")
    where = "WHERE r.collection = %(collection)s"
    if spec.get("filter"):
        frag = builder._compile_expression(spec["filter"], ctx_param="flt_ctx", column="r.data")
        sql, prm = builder.namespace(frag, builder.PREFIX_FILTER)
        builder.merge_params(params, prm)
        where += f" AND xpr.truthy( {sql} )"
    sql = (
        "WITH p AS (SELECT r.key, r.data FROM demo.records AS r\n"
        f"            {where}),\n"
        "     c AS (SELECT c.key, c.data FROM demo.records AS c\n"
        "            WHERE c.collection = %(rel_source)s),\n"
        "     m AS (SELECT p.key AS pk, c.key AS ck FROM p JOIN c\n"
        f"             ON {on}),\n"
        "     per_p AS (SELECT p.key, count(m.ck) AS n FROM p LEFT JOIN m ON m.pk = p.key GROUP BY p.key),\n"
        "     per_c AS (SELECT c.key, count(m.pk) AS n FROM c LEFT JOIN m ON m.ck = c.key GROUP BY c.key)\n"
        'SELECT (SELECT count(*) FROM per_p)               AS "parents",\n'
        '       (SELECT count(*) FROM per_p WHERE n = 0)   AS "parents_none",\n'
        '       (SELECT min(n) FROM per_p WHERE n > 0)     AS "least",\n'
        '       (SELECT max(n) FROM per_p WHERE n > 0)     AS "most",\n'
        '       (SELECT count(*) FROM per_c)               AS "counted",\n'
        '       (SELECT count(*) FROM per_c WHERE n = 0)   AS "counted_none",\n'
        '       (SELECT count(*) FROM per_c WHERE n > 1)   AS "counted_twice",\n'
        '       (SELECT max(n) FROM per_c WHERE n > 0)     AS "most_parents";'
    )
    builder._bind_ctx_values(sql, params, builder._ctx_json(None))
    return Built(sql, params, PROFILE, PROFILE_COLUMNS)
