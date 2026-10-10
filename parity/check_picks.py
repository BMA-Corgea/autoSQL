"""parity/check_picks.py — run pick-vectors/1 (parity/pick-vectors.json) through BOTH engines (T-88).

Each case is a pick (or a per-value board) over the file's invented records, with its answer worked
out by hand.  The records go into a TEMPORARY table on the connection given (made inside the caller's
transaction, gone at its end); each case runs through the statement (``picks.builder`` /
``picks.group``) and through the second engine (``picks.pyrunner``), and both must equal ``expect``
exactly, numbers compared as exact decimals.  A host (the demo, GIMS) supplies the connection and has
registered its modules with ``picks.env.use`` first.

    run_vectors(conn) -> [Result(name, sql, python, expect)]   # .ok when all three are equal
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, List, NamedTuple

VECTORS = Path(__file__).resolve().parent / "pick-vectors.json"
TABLE = "t88_pick_vectors"


class Result(NamedTuple):
    name: str
    sql: list
    python: list
    expect: list

    @property
    def ok(self) -> bool:
        return self.sql == self.expect and self.python == self.expect


def _canon(v: Any):
    """A cell as the vectors write it: text as text, a number as its exact
    decimal without trailing zeros, blank as None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        d = Decimal(str(v)).normalize()
        return format(d, "f")
    if isinstance(v, str):
        return v
    return v


def _expect(rows):
    return [[_canon(Decimal(c)) if isinstance(c, str) and _is_number(c) and i > 0 or (isinstance(c, str) and len(r) == 1 and _is_number(c)) else c
             for i, c in enumerate(r)] for r in rows]


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
        return True
    except Exception:  # noqa: BLE001
        return False


def run_vectors(conn, path: Path = VECTORS) -> List[Result]:
    from picks import builder, group
    from picks.pyrunner import group as pygroup
    from picks.pyrunner import shape as pyshape
    from picks.pyrunner.rows import read_rows
    from picks.records import Records

    v = json.loads(Path(path).read_text())
    if v.get("format") != "pick-vectors/1":
        raise ValueError(f"not pick-vectors/1: {v.get('format')!r}")
    coll = v["collection"]
    conn.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, "
                 "PRIMARY KEY (collection, key))")
    for r in v["records"]:
        conn.execute(f"INSERT INTO {TABLE} VALUES (%s, %s, %s::jsonb)", (coll, r["key"], json.dumps(r["data"])))
    keys = sorted({k for r in v["records"] for k in r["data"]})
    records = Records(table=TABLE, sources={coll: ", ".join(keys)})
    rows = read_rows(conn, coll, records)

    out = []
    for case in v["cases"]:
        if "pick" in case:
            pick = {"source": coll, "computed": [], "filter": None, "sort": None, "cap": None,
                    "window": None, "changed": False, "bucket": "off"}
            pick.update(case["pick"])
            built = builder.build(pick, keys, records=records)
            cur = conn.execute(built.sql, built.params)
            sql = [[_canon(c) for c in r] for r in cur.fetchall()]
            py = pyshape.answer(rows, pick, records)
            if py["shape"] == "SCALAR":
                python = [[_canon(py["agg"])]]
            else:
                python = [[r["bucket"], _canon(r["agg"])] for r in py["rows"]]
        else:
            b = case["board"]
            spec = {"source": coll, "group": b["group"], "filter": None, "counts": [], "time": None,
                    "measure": b["measure"], "sort": None, "cap": None}
            built = group.build(spec, records)
            cur = conn.execute(built.sql, built.params)
            names = [d.name for d in cur.description]
            col = names.index("rows" if b["measure"] is None else "measure")
            sql = [[_grp(r[0]), _canon(r[col])] for r in cur.fetchall()]
            py = pygroup.answer(rows, spec)
            pcol = "rows" if b["measure"] is None else "measure"
            python = [[r["grp"], _canon(r[pcol])] for r in py["rows"]]
        expect = [[_canon(Decimal(c)) if (isinstance(c, str) and _is_number(c) and (j > 0 or len(r) == 1)) else c
                   for j, c in enumerate(r)] for r in case["expect"]]
        out.append(Result(case["name"], sql, python, expect))
    return out


def _grp(v):
    # the statement returns a group's jsonb value; text arrives as text, a null as None
    return v
