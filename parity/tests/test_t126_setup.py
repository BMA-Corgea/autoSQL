"""T-126 — the setup reads a record type in a constant number of statements, its answer unchanged.

fm-gims on the owner's staging copy (guts-ledger, 22,304 LedgerRecords, about 182 fields): any widget took 8.2-10.1 s, 97%
of it the engine's setup -- ``picks.view._read_fields`` sent 385 statements, each a full scan (one per field per
fact: values, forms, distinct, range, span), 155 of them ``_groupable``'s. GIMS runs the setup for every preview,
answer and check. The class: the setup's cost grows with fields x records.

The bar here: the same number of statements on a 5-field type and a 200-field type, from both readers (Postgres,
and ``PythonReader``, GIMS's SQLite mode); and an answer identical, field by field and in ``_ordered``'s order, to
T-114's tip's (7f6c866) -- frozen below as the old side -- over every demo collection, GIMS's forms, a wide type with
every kind, and many random small ones; and ``PythonReader`` identical to Postgres on the same documents.

Needs AUTOSQL_PARITY_DSN: a throwaway Postgres (never 55433 or 55440); a scratch database is made and dropped there.
"""
from __future__ import annotations

import json
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401  (the engine, registered)
from picks import paths, view as pview  # noqa: E402
from picks.records import Records  # noqa: E402

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres")
SCRATCH = "t126_scratch"
TABLE = "demo.records"


# ── the old side: T-114's tip's field reader (7f6c866, picks/view.py), frozen; one full scan per field per fact ──

_OLD_TYPES_SQL = """
SELECT e.k, jsonb_typeof(e.v) AS t, count(*)
  FROM {table} r, LATERAL jsonb_each(r.data) AS e(k, v)
 WHERE {scope}
 GROUP BY 1, 2
"""
_OLD_INNER_TYPES_SQL = """
SELECT e2.k, jsonb_typeof(e2.v) AS t, count(*)
  FROM {table} r, LATERAL jsonb_each(r.data -> %(key)s) AS e2(k, v)
 WHERE {scope}
   AND jsonb_typeof(r.data -> %(key)s) = 'object'
 GROUP BY 1, 2
"""
_OLD_VALUES_SQL = """
SELECT r.data #>> %(path)s COLLATE "C" AS v, count(*) AS n
  FROM {table} r
 WHERE {scope}
   AND jsonb_typeof(r.data #> %(path)s) = 'string'
 GROUP BY 1
 ORDER BY 1
 LIMIT %(limit)s
"""
_OLD_FORMS_SQL = """
SELECT count(*),
       count(*) FILTER (WHERE v ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([Tt ][0-9]{2}:[0-9]{2}(:[0-9]{2}([.,][0-9]+)?)?([Zz]|[+-][0-9]{2}(:?[0-9]{2}(:?[0-9]{2})?)?)?)?$'),
       count(*) FILTER (WHERE length(v) > 10 AND xpr.time_at(v) IS NOT NULL),
       count(*) FILTER (WHERE v !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
  FROM (SELECT r.data #>> %(path)s AS v
          FROM {table} r
         WHERE {scope}
           AND jsonb_typeof(r.data #> %(path)s) = 'string') AS f
 WHERE v <> ''
"""
_OLD_SPAN_SQL = """
SELECT min(xpr.time_at(v)) FILTER (WHERE length(v) > 10), max(xpr.time_at(v)) FILTER (WHERE length(v) > 10),
       min(v) FILTER (WHERE length(v) = 10 AND xpr.time_at(v) IS NOT NULL),
       max(v) FILTER (WHERE length(v) = 10 AND xpr.time_at(v) IS NOT NULL)
  FROM (SELECT r.data #>> %(path)s AS v
          FROM {table} r
         WHERE {scope}
           AND jsonb_typeof(r.data #> %(path)s) = 'string') AS f
"""
_OLD_RANGE_SQL = """
SELECT min((r.data #>> %(path)s)::numeric), max((r.data #>> %(path)s)::numeric)
  FROM {table} r
 WHERE {scope}
   AND jsonb_typeof(r.data #> %(path)s) = 'number'
"""
_OLD_DISTINCT_SQL = """
SELECT count(DISTINCT nullif(r.data #> %(path)s, 'null'::jsonb))
     + max(CASE WHEN nullif(r.data #> %(path)s, 'null'::jsonb) IS NULL THEN 1 ELSE 0 END)
  FROM {table} r
 WHERE {scope}
"""


def _old_groupable(conn, collection, path, kind, types, label, records) -> dict:
    if kind not in ("text", "number", "yesno") or types & {"object", "array"}:
        why = ("Times and dates are grouped per hour, day, week or month under Summarize."
               if kind in ("time", "date") else
               "Its rows hold different kinds of value, so there is no one value to group by.")
        return {"ok": False, "why": why, "groups": None}
    n = int(pview._read(conn, records, _OLD_DISTINCT_SQL, {"collection": collection,
                                                         "path": paths.steps(path)}).fetchone()[0])
    if n > pview.GROUP_LIMIT:
        return {"ok": False, "groups": n, "why": (
            f"{label} has {n:,} different values — one row per value would be about as "
            f"long as the table itself. One row per value works up to {pview.GROUP_LIMIT} different values.")}
    return {"ok": True, "why": "", "groups": n}


def _old_read_fields(conn, collection, labels=None, records=None) -> list:
    labels = labels or {}
    rows = pview._read(conn, records, _OLD_TYPES_SQL, {"collection": collection}).fetchall()
    types: dict = {}
    for k, t, _n in rows:
        types.setdefault(k, set()).add(t)
    found: dict = {}
    for key, ts in types.items():
        if ts == {"object"}:
            inner = pview._read(conn, records, _OLD_INNER_TYPES_SQL, {"collection": collection, "key": key}).fetchall()
            for k2, t2, _n in inner:
                name = paths.name([key, k2])
                if name is not None:
                    found.setdefault(name, set()).add(t2)
        else:
            name = paths.name([key])
            if name is not None:
                found[name] = set(ts)
    fields = []
    for path, ts in found.items():
        strings: list = []
        if "string" in ts:
            strings = [r[0] for r in pview._read(conn, records, _OLD_VALUES_SQL, {
                "collection": collection, "path": paths.steps(path), "limit": pview.VALUE_LIMIT + 1}).fetchall()]
        forms = (0, 0, 0, 0)
        if "string" in ts:
            forms = tuple(pview._read(conn, records, _OLD_FORMS_SQL, {
                "collection": collection, "path": paths.steps(path)}).fetchone())
        kind = pview._kind(ts - {"null"}, forms)
        ops = pview._ops_for(kind, ts)
        field = {"path": path, "label": labels.get(path) or pview._humanize(path), "kind": kind, "ops": ops,
                 "why_no_ops": "" if ops else (pview.WHY_GROUPED if ts & {"object", "array"} else pview.WHY_ONLY_BLANK),
                 "values": None, "picker": None, "range": None}
        field["group"] = _old_groupable(conn, collection, path, kind, ts, field["label"], records)
        if kind == "text" and len(strings) <= pview.VALUE_LIMIT:
            field["values"] = strings
            field["picker"] = "chips" if len(strings) <= pview.CHIP_LIMIT else "list"
        if kind == "number":
            lo, hi = pview._read(conn, records, _OLD_RANGE_SQL,
                                 {"collection": collection, "path": paths.steps(path)}).fetchone()
            if lo is not None:
                field["range"] = {"min": pview._number_text(lo), "max": pview._number_text(hi)}
        if kind in ("time", "date"):
            t_lo, t_hi, d_lo, d_hi = pview._read(conn, records, _OLD_SPAN_SQL, {
                "collection": collection, "path": paths.steps(path)}).fetchone()
            if kind == "time" and t_lo is not None:
                field["range"] = {"min": pview._span_text(t_lo), "max": pview._span_text(t_hi)}
                if d_lo is not None:
                    field["range"]["dates"] = {"min": d_lo, "max": d_hi}
            elif kind == "date" and d_lo is not None:
                field["range"] = {"min": d_lo, "max": d_hi}
        fields.append(field)
    return fields


# ── the data: every demo collection, and these added to a scratch copy ──

def _gims_forms(n, seed=126):
    """Times as GIMS writes them (a-chk's cost generator): +00:00 whole and with 6 digits, .ffffffZ, -0600, a few
    naive and bare dates."""
    from datetime import datetime, timedelta, timezone
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        at = datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(seconds=rnd.randrange(0, 120 * 86400),
                                                                   microseconds=rnd.randrange(0, 10 ** 6))
        k = rnd.random()
        when = (at.replace(microsecond=0).isoformat() if k < 0.4 else at.isoformat() if k < 0.75 else
                at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if k < 0.9 else
                (at - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S-0600") if k < 0.97 else
                at.strftime("%Y-%m-%dT%H:%M") if k < 0.99 else at.strftime("%Y-%m-%d"))
        out.append({"label": f"g{i:05d}", "note": rnd.choice(["fine", "check", "redo", ""]), "created_at": when,
                    "weight": rnd.choice([1, 2.5, 10, 0.001, 1.0, 12345678901234567890]), "ok": rnd.random() < 0.5})
    return out


def _wide(n=2100, seed=127):
    """One type with every kind the reader tells apart, and its edges: text with at most and more than VALUE_LIMIT
    values (2,000 and 2,001), numbers with long digits, yes/no, GIMS's times, bare dates (one the calendar lacks),
    mixed types, nulls and blanks, an object opened one level and one that is sometimes not, arrays, keys that need
    brackets, a key with no name, and a sparse key."""
    rnd = random.Random(seed)
    times = _gims_forms(n, seed)
    docs = []
    for i in range(n):
        d = {
            "t_few": rnd.choice(["alpha", "beta", "gamma"]),
            "t_at_limit": f"v{i % pview.VALUE_LIMIT:05d}",
            "t_past_limit": f"w{i % (pview.VALUE_LIMIT + 1):05d}",
            "n_long": rnd.choice([0, -5, 0.1, 1.0, 1, 123456789012345678901234567890, Decimal("1E+30"), 7.25]),
            "yn": rnd.random() < 0.3,
            "when": times[i]["created_at"],
            "day": rnd.choice(["2026-07-09", "2026-07-10", "2026-02-30", "0999-06-15", "9999-12-31"]),
            "mix": rnd.choice([1, "one", 2, "two"]),
            "nul": None,
            "blank": rnd.choice(["", "x", ""]),
            "obj": {"a": rnd.randrange(5), "b": rnd.choice(["x", "y"]), "c d": rnd.choice([True, False])},
            "objs": {"a": 1} if rnd.random() < 0.9 else "flat",
            "arr": [rnd.randrange(3), rnd.randrange(3)],
            "Sample Weight (g)": rnd.choice([1.5, 2.5]),
            "": "no name",
        }
        if rnd.random() < 0.1:
            d["sparse"] = rnd.choice(["s1", "s2", None])
        if rnd.random() < 0.05:
            del d["t_few"]
        docs.append(d)
    return docs


_STRINGS = ["", "a", "b", "B", "lunch", "2026-07-09", "2026-07-10", "2026-02-30", "0001-01-01", "9999-12-31",
            "2026-07-09T05:03:48Z", "2026-07-09T05:03:48+00:00", "2026-07-09T05:03:48.123456+00:00",
            "2026-07-09T23:30:00-06:00", "2026-07-09 05:03:48Z", "2026-07-09T05:03", "2026-07-09T05:03:48",
            "2026-07-09t05:03:48z", "2026-07-09T24:00:00Z", "2026-07-09T05:03:48.1234567Z", "0001-01-01T00:00:00Z",
            "9999-12-31T23:59:59.999999+00:00", "Sample (x)", "x y", "é", "日本"]
_NUMBERS = [0, 1, -1, 1.0, 2.5, -0.25, 10 ** 20, Decimal("1E+30"), Decimal("123456789012345678901234567890.5")]


def _random_types(count=48, seed=126):
    """Many small types, each a few keys, each key of one kind or several, sometimes absent, null, or an object."""
    rnd = random.Random(seed)
    out = {}
    for t in range(count):
        keys = rnd.sample(["k1", "k2", "k3", "when", "n", "Key Two", "o", "flag", "deep"], rnd.randint(1, 6))
        kind = {k: rnd.choice(["str", "time", "num", "bool", "mix", "obj", "arr", "null"]) for k in keys}
        docs = []
        for _ in range(rnd.randint(3, 40)):
            d = {}
            for k in keys:
                if rnd.random() < 0.15:
                    continue
                kd = kind[k]
                v = (rnd.choice(_STRINGS) if kd == "str" else rnd.choice(_STRINGS[5:22]) if kd == "time" else
                     rnd.choice(_NUMBERS) if kd == "num" else rnd.random() < 0.5 if kd == "bool" else
                     rnd.choice(_STRINGS + _NUMBERS + [True, None]) if kd == "mix" else
                     {"x": rnd.choice(_NUMBERS[:4]), "y": rnd.choice(_STRINGS[:6])} if kd == "obj" else
                     [rnd.randrange(3)] if kd == "arr" else None)
                d[k] = v
            docs.append(d)
        out[f"noun:R{t:02d}"] = docs
    return out


def _fields(n_fields, n_rows=12, seed=128):
    """A type of exactly ``n_fields`` fields, every one in every row: text, numbers and times by turns."""
    rnd = random.Random(seed)
    return [{f"f{j:03d}": (rnd.choice(["a", "b", "c"]) if j % 3 == 0 else rnd.choice(_NUMBERS[:6]) if j % 3 == 1
                           else rnd.choice(_STRINGS[10:14])) for j in range(n_fields)} for _ in range(n_rows)]


ADDED = dict({"noun:Wide": _wide(), "noun:Gims": _gims_forms(3000), "noun:Five": _fields(5),
              "noun:TwoHundred": _fields(200)}, **_random_types())


def _dumps(doc) -> str:
    return pview._exact_dumps(doc)


@pytest.fixture(scope="module")
def world():
    if not DSN:
        pytest.skip("set AUTOSQL_PARITY_DSN to a throwaway Postgres")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    import this_runtime
    from demo.seed import load
    with psycopg.connect(DSN, autocommit=True) as cx:
        if int(cx.info.port) in (55433, 55440):
            raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        cx.execute(f"CREATE DATABASE {SCRATCH} TEMPLATE template0 LOCALE 'C' ENCODING 'UTF8'")
    dsn = make_conninfo(**{**conninfo_to_dict(DSN), "dbname": SCRATCH})
    with psycopg.connect(dsn, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(dsn) as cx:
        load.install_schema(cx)
        load.copy_rows(cx)
        with cx.cursor().copy("COPY demo.records (collection, key, data) FROM STDIN") as cp:
            for collection, docs in ADDED.items():
                for i, d in enumerate(docs):
                    cp.write_row((collection, f"t126-{i:05d}", _dumps(d)))
        cx.commit()
        collections = [r[0] for r in cx.execute("SELECT DISTINCT collection FROM demo.records ORDER BY 1")]
    conn = psycopg.connect(dsn)
    records = Records(table=TABLE, sources={c: "data" for c in collections})
    yield {"conn": conn, "records": records, "collections": collections, "dsn": dsn}
    conn.close()
    with psycopg.connect(DSN, autocommit=True) as cx:
        cx.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


class _Counted:
    """A connection (or PythonReader) that counts the statements sent to it."""

    def __init__(self, conn):
        self.conn, self.sent = conn, 0

    def execute(self, sql, params=None):
        self.sent += 1
        return self.conn.execute(sql, params)


def _docs(world, collection) -> list:
    rows = world["conn"].execute("SELECT data::text FROM demo.records WHERE collection = %s ORDER BY key",
                                 (collection,)).fetchall()
    world["conn"].rollback()
    return [json.loads(r[0], parse_float=Decimal) for r in rows]


def _by_path(fields) -> dict:
    return {f["path"]: f for f in fields}


# ── the bar's tests ──

@needs_db
def test_the_setup_sends_as_many_statements_for_200_fields_as_for_5(world):
    counts = {}
    for collection in ("noun:Five", "noun:TwoHundred"):
        counted = _Counted(world["conn"])
        fields = pview._read_fields(counted, collection, records=world["records"])
        world["conn"].rollback()
        counts[collection] = (counted.sent, len(fields))
    assert counts["noun:Five"][1] == 5 and counts["noun:TwoHundred"][1] == 200, counts
    assert counts["noun:Five"][0] == counts["noun:TwoHundred"][0] == 2, counts


@needs_db
def test_the_python_reader_sends_as_many_statements_for_200_fields_as_for_5(world):
    counts = {}
    for collection in ("noun:Five", "noun:TwoHundred"):
        reader = _Counted(pview.PythonReader(world["records"], _docs(world, collection)))
        fields = pview._read_fields(reader, collection, records=world["records"])
        counts[collection] = (reader.sent, len(fields))
    assert counts["noun:Five"][0] == counts["noun:TwoHundred"][0] == 2, counts


@needs_db
def test_every_collection_reads_as_t114s_tip_read_it(world):
    """Field by field, and in _ordered's order (the order every caller shows: the demo's dashboard, GIMS's _prepare)."""
    differ = []
    for collection in world["collections"]:
        new = pview._read_fields(world["conn"], collection, records=world["records"])
        world["conn"].rollback()
        old = _old_read_fields(world["conn"], collection, records=world["records"])
        world["conn"].rollback()
        if _by_path(new) != _by_path(old) or pview._ordered(new, ()) != pview._ordered(old, ()):
            differ.append((collection, sorted(p for p in set(_by_path(new)) | set(_by_path(old))
                                              if _by_path(new).get(p) != _by_path(old).get(p))[:5]))
    assert not differ, differ
    assert len(world["collections"]) > 50, len(world["collections"])


@needs_db
def test_the_python_reader_reads_every_added_type_as_postgres_does(world):
    differ = []
    for collection in ADDED:
        in_sql = pview._read_fields(world["conn"], collection, records=world["records"])
        world["conn"].rollback()
        reader = pview.PythonReader(world["records"], _docs(world, collection))
        in_python = pview._read_fields(reader, collection, records=world["records"])
        if _by_path(in_python) != _by_path(in_sql) or pview._ordered(in_python, ()) != pview._ordered(in_sql, ()):
            differ.append((collection, sorted(p for p in set(_by_path(in_sql)) | set(_by_path(in_python))
                                              if _by_path(in_sql).get(p) != _by_path(in_python).get(p))[:5]))
    assert not differ, differ


@needs_db
def test_the_setup_hands_python_one_row_a_field_and_at_most_value_limit_and_one_strings(world):
    """Memory stays bounded: what crosses into Python is one row a field (and a text field's first VALUE_LIMIT + 1
    values, as before), never every value."""
    fetched = []

    class Watched(_Counted):
        def execute(self, sql, params=None):
            cur = super().execute(sql, params)
            rows = cur.fetchall()
            fetched.append(rows)
            return _Rows(rows)
    fields = pview._read_fields(Watched(world["conn"]), "noun:Wide", records=world["records"])
    world["conn"].rollback()
    facts = fetched[-1]
    longest = max((len(c) for row in facts for c in row if isinstance(c, list)), default=0)
    assert len(facts) == len(fields) and longest <= pview.VALUE_LIMIT + 1, (len(facts), len(fields), longest)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None
