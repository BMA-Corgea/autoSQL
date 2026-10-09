"""demo/lookup.py — shape F, MATCHED: a plain table with another data set's fields beside each row (T-78).

The plain table a person already has (builder.py's shape A: the same
computed columns, conditions, sort, row order and Show) with columns from ONE
other data set added, each row matched to at most one row of it by a field
pair the person picked::

    SELECT r.collection, r.key, r.data, <the table's columns>,
           <each matched field, read from m.data>
      FROM demo.records AS r
      LEFT JOIN demo.records AS m
        ON m.collection = <the other data set> AND <the match>
     WHERE r.collection = … AND <the conditions>
     ORDER BY <the sort>, r.key ASC, m.key ASC
     LIMIT …

It lives in its own file, as T-73's shape E does: the nine-operation pick,
legality.py's matrix and the two-pane screen are untouched.  It is built
from builder.py's own pieces (``_Pieces``: legality, the alias gate, every
compiled expression, the order and the cap) and from T-76's ONE match rule
(``group._match_on``: the type guard on the matched side, then jsonb ``=``).

THE RULES IT WRITES DOWN
* LEFT JOIN: a row with no match keeps its place, its matched columns blank.
* A matched field is read exactly as a table column is read: ``$.path``
  compiled against ``m.data`` (an absent row reads as a missing field: blank).
* The order is the table's own, then ``m.key``: one row per table row when
  every row matches at most one (``build_profile`` refuses anything else),
  and still a total order if that check were ever off.
* ``build_profile`` says what the match does over the KEPT rows (the
  conditions apply; Show and paging do not, so the verdict never depends on
  which rows are on screen): how many rows, how many match none, the fewest
  and most matches a matching row has, and how many rows match MORE THAN
  ONE (any is a refusal: a row would be repeated).

THE MATCH SPEC (built and checked by ``demo/server/dashboard.py``)::

    source      str     the other data set (one of legality.SOURCES)
    key         path    the other data set's field
    parent_key  path    this data set's field
    match       "string" | "number"   (group.MATCH_TYPES)
    columns     [{"name": alias, "path": path}]   at most MAX_COLUMNS
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

_DEMO_DIR = str(Path(__file__).resolve().parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import builder  # noqa: E402
import gate  # noqa: E402
import group  # noqa: E402
import legality  # noqa: E402

MATCHED = "MATCHED"
PROFILE = "MATCH_PROFILE"

#: The most fields one table may add from the other data set.
MAX_COLUMNS = 6

#: The profile's columns, in both engines.
PROFILE_COLUMNS = ("rows", "rows_none", "least", "most", "repeated", "others")


class Built(NamedTuple):
    sql: str
    params: dict
    shape: str
    columns: tuple


def check(pick: dict, lk: dict) -> None:
    """The match spec's own shape — loud on anything a caller let through."""
    if legality.evaluate(pick)["shape"] != legality.ROWS:
        raise ValueError("matched fields go beside a plain table's rows only")
    if pick.get("window") or pick.get("changed"):
        raise ValueError("matched fields go beside a plain table's rows only")
    if not isinstance(lk, dict) or lk.get("source") not in legality.SOURCES:
        raise ValueError(f"unknown matched source {lk!r}")
    group._path(lk.get("key"), "the matched rows' key")
    group._path(lk.get("parent_key"), "the table's key")
    if lk.get("match") not in group.MATCH_TYPES:
        raise ValueError(f"unknown match type {lk.get('match')!r}")
    cols = lk.get("columns")
    if not isinstance(cols, list) or not 1 <= len(cols) <= MAX_COLUMNS:
        raise ValueError(f"one to {MAX_COLUMNS} matched columns")
    for c in cols:
        group._path(c.get("path"), "a matched column")


def build(pick: dict, collection_keys, lk: dict) -> Built:
    """One plain-table pick + one match spec → one parameterised statement."""
    check(pick, lk)
    p = builder._Pieces(pick, collection_keys, None)
    select = ["r.collection", "r.key", "r.data"]
    columns = ["collection", "key", "data"]
    for name in p.cc_order:
        sql, prm = builder.namespace(p.cc_frag[name], f"cc{p.cc_index(name)}")
        builder.merge_params(p.params, prm)
        select.append(f"{sql}  AS {p.cc_quoted[name]}")
        columns.append(name)
    for i, c in enumerate(lk["columns"]):
        # One alias vocabulary for the whole SELECT list: the table's own
        # column names come first, and a matched column may repeat none.
        quoted = gate.emit_alias(c["name"], p.collection_keys, columns[3:])
        frag = builder._compile_expression("$." + c["path"], ctx_param=f"mc{i}_ctx", column="m.data")
        sql, prm = builder.namespace(frag, f"mc{i}")
        builder.merge_params(p.params, prm)
        select.append(f"{sql}  AS {quoted}")
        columns.append(c["name"])

    p.params["mt_source"] = lk["source"]
    on = group._match_on(lk, p.params, "m.data", "r.data")
    sql = (
        "SELECT " + ",\n       ".join(select) + "\n"
        "  FROM demo.records AS r\n"
        "  LEFT JOIN demo.records AS m\n"
        "    ON m.collection = %(mt_source)s\n"
        f"   AND {on}\n"
        + p.where_clause() + "\n"
        + p.order_by(pick, qualify="r.") + ", m.key ASC"
        + p.limit(pick) + ";"
    )
    builder._bind_ctx_values(sql, p.params, p.ctx_value)
    return Built(sql, p.params, MATCHED, tuple(columns))


def build_profile(pick: dict, lk: dict) -> Built:
    """What the match does over the KEPT rows, before anything is shown —
    read by the preview line and by the repeat check.

    * rows / rows_none — kept rows, and those matching no row;
    * least / most — the fewest and most rows a matching row matches (NULL
      when none matches);
    * repeated — kept rows matching MORE THAN ONE row (any is a refusal);
    * others — the rows of the other data set.

    Keys are unique per collection (demo.records' primary key), so counting
    keys counts rows."""
    check(pick, lk)
    params: dict = {"collection": pick["source"], "mt_source": lk["source"]}
    on = group._match_on(lk, params, "c.data", "p.data")
    where = "WHERE r.collection = %(collection)s"
    if pick.get("filter"):
        frag = builder._compile_expression(pick["filter"], ctx_param="flt_ctx", column="r.data")
        sql, prm = builder.namespace(frag, builder.PREFIX_FILTER)
        builder.merge_params(params, prm)
        where += f" AND xpr.truthy( {sql} )"
    sql = (
        "WITH p AS (SELECT r.key, r.data FROM demo.records AS r\n"
        f"            {where}),\n"
        "     c AS (SELECT c.key, c.data FROM demo.records AS c\n"
        "            WHERE c.collection = %(mt_source)s),\n"
        "     per_p AS (SELECT p.key, count(c.key) AS n FROM p LEFT JOIN c\n"
        f"                ON {on} GROUP BY p.key)\n"
        'SELECT count(*)                          AS "rows",\n'
        '       count(*) FILTER (WHERE n = 0)     AS "rows_none",\n'
        '       min(n) FILTER (WHERE n > 0)       AS "least",\n'
        '       max(n) FILTER (WHERE n > 0)       AS "most",\n'
        '       count(*) FILTER (WHERE n > 1)     AS "repeated",\n'
        '       (SELECT count(*) FROM c)          AS "others"\n'
        "  FROM per_p;"
    )
    builder._bind_ctx_values(sql, params, builder._ctx_json(None))
    return Built(sql, params, PROFILE, PROFILE_COLUMNS)
