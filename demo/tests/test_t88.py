"""demo/tests/test_t88.py — T-88 (M3): time summaries over any date field, one number per value of a field.

* ``parity/pick-vectors.json`` through BOTH engines — every answer worked out by hand from the
  rules written in the file (time values, Monday weeks, UTC, blanks, exact averages);
* the demo's own data against hand-written SQL: Samples per week and per month of Due date,
  Heartbeats per week of their time, Samples per Status (a count, an average);
* what the view refuses, and what legality now allows.
"""

from __future__ import annotations

import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "demo"), str(_REPO_ROOT / "parity")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401
import check_picks  # noqa: E402
from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard, db  # noqa: E402
from picks import legality  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-t88")
    server_app.refuse_writes(c)
    yield c
    c.close()


def ask(client, v, *, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    return r.status_code, r.json()


def summary(ds, **s):
    return {"dataset": ds, "columns": [], "conditions": [], "sort": None, "show": None, "summary": s}


# ═════════════════════════════════════════════════════════════════════════
# 1 · The pick vectors, both engines, against answers worked out by hand
# ═════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def vector_results():
    c = db.connect(application_name="autosql-demo-t88-vectors")
    try:
        return {r.name: r for r in check_picks.run_vectors(c)}
    finally:
        c.rollback()
        c.close()


_NAMES = [c["name"] for c in __import__("json").loads(check_picks.VECTORS.read_text())["cases"]]


@pytest.mark.parametrize("name", _NAMES)
def test_a_pick_vector_equals_its_hand_worked_answer_in_both_engines(vector_results, name):
    r = vector_results[name]
    assert r.sql == r.expect, f"the statement: {r.sql} != {r.expect}"
    assert r.python == r.expect, f"the second engine: {r.python} != {r.expect}"


# ═════════════════════════════════════════════════════════════════════════
# 2 · The demo's own data, against hand-written SQL
# ═════════════════════════════════════════════════════════════════════════

#: Monday-start weeks by date arithmetic (not date_trunc), as GIMS's own oracle writes them.
_SAMPLES_PER_WEEK = """
SELECT to_char(d - (extract(isodow FROM d)::int - 1), 'YYYY-MM-DD') AS week, count(*)
  FROM (SELECT (data->>'due_date')::date AS d FROM demo.records
         WHERE collection = 'noun:Sample' AND jsonb_typeof(data->'due_date') = 'string') s
 GROUP BY 1 ORDER BY 1
"""
_SAMPLES_PER_MONTH = """
SELECT to_char(d, 'YYYY-MM') AS month, count(*)
  FROM (SELECT (data->>'due_date')::date AS d FROM demo.records
         WHERE collection = 'noun:Sample' AND jsonb_typeof(data->'due_date') = 'string') s
 GROUP BY 1 ORDER BY 1
"""


def _weeks(a):
    """(Monday's date, count) for each slot of a chart answer that has rows."""
    return [(b["start"][:10], int(b["exact"])) for b in a["bars"] if not b["empty"]]


def test_samples_per_week_of_due_date_equals_hand_sql(client, conn):
    want = [(w, int(n)) for w, n in conn.execute(_SAMPLES_PER_WEEK).fetchall()]
    st, a = ask(client, summary("samples", fn="count", field=None, per="week", time="due_date"))
    assert st == 200 and a["kind"] == "chart" and a["admin"]["verdict"] == "agree"
    assert _weeks(a) == want and len(want) > 40
    assert a["sentence"].startswith("Number of Samples, per week of Due date — ")
    assert all(b["start"][:10] == b["start"][:10] and
               __import__("datetime").date.fromisoformat(b["start"][:10]).weekday() == 0 for b in a["bars"])


def test_samples_per_month_of_due_date_equals_hand_sql(client, conn):
    want = [(m, int(n)) for m, n in conn.execute(_SAMPLES_PER_MONTH).fetchall()]
    st, a = ask(client, summary("samples", fn="count", field=None, per="month", time="due_date"))
    assert a["admin"]["verdict"] == "agree"
    assert [(b["start"][:7], int(b["exact"])) for b in a["bars"] if not b["empty"]] == want


def test_heartbeats_average_load_per_week_equals_hand_sql(client, conn):
    want = conn.execute("""
        SELECT to_char(date_trunc('week', (data->>'ts')::timestamptz) AT TIME ZONE 'UTC', 'YYYY-MM-DD'),
               avg((data #>> '{payload,load}')::numeric)
          FROM demo.records WHERE collection = 'noun:Heartbeat'
           AND jsonb_typeof(data #> '{payload,load}') = 'number'
         GROUP BY 1 ORDER BY 1""").fetchall()
    st, a = ask(client, summary("heartbeats", fn="avg", field="payload.load", per="week"))
    assert a["admin"]["verdict"] == "agree"
    got = [(b["start"][:10], Decimal(b["exact"])) for b in a["bars"] if not b["empty"]]
    assert got == [(w, v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) for w, v in want]


@pytest.mark.parametrize("fn, field, sql", [
    ("count", None, "count(*)"),
    ("avg", "priority", "round(avg((data->>'priority')::numeric) FILTER (WHERE jsonb_typeof(data->'priority') = 'number'), 6)"),
    ("max", "priority", "max((data->>'priority')::numeric) FILTER (WHERE jsonb_typeof(data->'priority') = 'number')"),
])
def test_samples_per_status_equals_hand_sql(client, conn, fn, field, sql):
    want = conn.execute(f"""
        SELECT CASE WHEN jsonb_typeof(data->'status') IN ('string', 'number', 'boolean') THEN data->>'status' END, {sql}
          FROM demo.records WHERE collection = 'noun:Sample' GROUP BY 1 ORDER BY 1 NULLS LAST""").fetchall()
    st, a = ask(client, summary("samples", fn=fn, field=field, per="category", by="status"))
    assert st == 200 and a["kind"] == "categories" and a["admin"]["verdict"] == "agree"
    got = [(c["label"], Decimal(c["exact"]) if c["exact"] is not None else None) for c in a["categories"]]
    assert got == [(k, Decimal(v) if v is not None else None) for k, v in want]


def test_one_number_per_value_reads_in_words(client):
    _, a = ask(client, summary("samples", fn="count", field=None, per="category", by="status"), admin=False)
    assert a["sentence"] == "Number of Samples, per Status — 4 statuses" and "admin" not in a
    assert [c["label"] for c in a["columns"]] == ["Status", "Number"]


# ═════════════════════════════════════════════════════════════════════════
# 3 · What the view refuses, by name
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("s, message", [
    ({"fn": "count", "field": None, "per": "hour", "time": "due_date"},
     "Due date holds dates, so there is no hour to group by."),
    ({"fn": "count", "field": None, "per": "week", "time": "status"}, "Group by a time or a date field."),
    ({"fn": "count", "field": None, "per": "all", "time": "due_date"},
     "A time to group by goes with per hour, day, week or month."),
    ({"fn": "count", "field": None, "per": "week", "by": "status"},
     "A field to group by goes with per value of a field."),
    ({"fn": "count", "field": None, "per": "category"}, "Pick the field to give one number per value of."),
    ({"fn": "count", "field": None, "per": "category", "by": "id"},
     "ID can't be grouped by: ID has 2,000 different values — one row per value would be about as long as the "
     "table itself. One row per value works up to 500 different values."),
    ({"fn": "count", "field": None, "per": "fortnight"},
     "Summarize over everything, per hour, day, week or month, or per value of a field."),
])
def test_the_view_refuses_by_name(client, s, message):
    st, a = ask(client, summary("samples", **s))
    assert (st, a.get("message")) == (422, message), a


# ═════════════════════════════════════════════════════════════════════════
# 4 · Legality: week and month; a time to group by, on any data set
# ═════════════════════════════════════════════════════════════════════════

def test_week_and_month_are_granularities_and_nothing_else_is():
    assert legality.BUCKETS == ("off", "hour", "day", "week", "month")
    for unit in ("week", "month"):
        p = dict(legality.default_pick(), aggregate={"fn": "count", "field": None}, bucket=unit)
        assert legality.evaluate(p)["violations"] == []
    p = dict(legality.default_pick(), aggregate={"fn": "count", "field": None}, bucket="fortnight")
    assert 7 in [v["operation"] for v in legality.evaluate(p)["violations"]]


def test_a_named_time_field_opens_operation_7_on_any_data_set():
    p = dict(legality.default_pick(), source="noun:Sample", aggregate={"fn": "count", "field": None}, bucket="week")
    assert 7 in [v["operation"] for v in legality.evaluate(p)["violations"]]       # no time: refused
    p["bucket_field"] = "due_date"
    v = legality.evaluate(p)
    assert v["violations"] == [] and v["ops"][7]["enabled"]
    assert not v["ops"][8]["enabled"] and not v["ops"][9]["enabled"]     # the window and keep-changed stay the series'
    p["bucket_field"] = ["due_date"]
    assert 7 in [x["operation"] for x in legality.evaluate(p)["violations"]]


@pytest.mark.parametrize("per", ["hour", "day", "week", "month"])
def test_the_view_asks_for_exactly_the_unit_and_the_field_picked(conn, per):
    """The view is shared by both engines: a unit it got wrong, both would
    get wrong alike.  Held directly."""
    setup = dashboard.setup_for(dashboard.setup(conn), True)
    ds, field = ("heartbeats", None) if per == "hour" else ("samples", "due_date")
    s = {"fn": "count", "field": None, "per": per}
    if field:
        s["time"] = field
    pick = dashboard.to_pick(setup, summary(ds, **s))
    assert (pick["bucket"], pick.get("bucket_field")) == (per, field)


def test_a_field_named_with_spaces_and_brackets_is_offered_and_read():
    """GIMS's field names hold spaces and brackets ("Sample Weight (g)"):
    offered by their bracketed path and their own words, and a condition on
    one reads exactly that key (picks/paths.py)."""
    import json as _json
    from picks import view as pview
    from picks.records import Records

    c = db.connect(application_name="autosql-demo-t88-names")
    try:
        c.execute("CREATE TEMPORARY TABLE t88_names (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
        for k, d in (("s1", {"Sample Type": "flower", "Sample Weight (g)": 1.5}),
                     ("s2", {"Sample Type": "oil", "Sample Weight (g)": 3})):
            c.execute("INSERT INTO t88_names VALUES ('noun:S', %s, %s::jsonb)", (k, _json.dumps(d)))
        r = Records(table="t88_names", sources={"noun:S": "Sample Type, Sample Weight (g)"})
        fields = {f["path"]: f for f in pview._read_fields(c, "noun:S", records=r)}
        assert set(fields) == {'["Sample Type"]', '["Sample Weight (g)"]'}, sorted(fields)
        w = fields['["Sample Weight (g)"]']
        assert (w["label"], w["kind"], w["range"]) == ("Sample Weight (g)", "number", {"min": "1.5", "max": "3"})
        assert fields['["Sample Type"]']["values"] == ["flower", "oil"]
        expr, words = pview.condition(w, {"field": w["path"], "op": "gt", "value": 2})
        assert (expr, words) == ('$["Sample Weight (g)"] > 2', "Sample Weight (g) is more than 2")
    finally:
        c.rollback()
        c.close()


# ═════════════════════════════════════════════════════════════════════════
# 5 · T-88 check: a name reads its own key; buckets in UTC; the owner kept
# ═════════════════════════════════════════════════════════════════════════

import json as _json  # noqa: E402

from picks import builder as _builder  # noqa: E402
from picks import paths as _paths  # noqa: E402
from picks import view as _pview  # noqa: E402
from picks.pyrunner import shape as _pyshape  # noqa: E402
from picks.pyrunner.rows import read_rows as _read_rows  # noqa: E402
from picks.records import Records as _Records  # noqa: E402

#: every control character Postgres can store (0x00 it cannot), DEL, and
#: the characters a name is spelled with
_ODD = [chr(i) for i in range(0x01, 0x20)] + ["\x7f", '"', "\\", "[", "]", ".", "'", " ", "$", "\\b", '\\"']
_KEYS = {f"a{c}c": 100 + i for i, c in enumerate(_ODD)}
#: what a name read the wrong way would land on instead (JSON's \b, \f, \u0001 …
#: read as bare letters; a dot inside brackets read as a path)
_DECOYS = {"abc": 1, "afc": 2, "anc": 3, "arc": 4, "atc": 5, "au0001c": 6, "au007fc": 7,
           "a": {"c": 9}}


def _one_record_table(c, table, coll, data):
    c.execute(f"CREATE TEMPORARY TABLE {table} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    c.execute(f"INSERT INTO {table} VALUES (%s, 'k1', %s::jsonb)", (coll, _json.dumps(data)))
    return _Records(table=table, sources={coll: "odd keys"})


def _both(c, records, coll, pick):
    pick = dict({"source": coll, "computed": [], "filter": None, "sort": None, "cap": None, "window": None,
                 "changed": False, "bucket": "off"}, **pick)
    built = _builder.build(pick, _pview.collection_keys(c, coll, records=records), records=records)
    sql = [list(r) for r in c.execute(built.sql, built.params).fetchall()]
    py = _pyshape.answer(_read_rows(c, coll, records), pick, records)
    python = [[py["agg"]]] if py["shape"] == "SCALAR" else [[r["bucket"], r["agg"]] for r in py["rows"]]
    return sql, python


def test_every_offered_name_reads_its_own_key_in_both_engines():
    """The check's HIGH: a key holding a control character was named the JSON way (``["a\\bc"]``) and the
    expression language read ``abc``.  Every name the page offers must read back exactly its own key — in
    the statement and in the second engine, as a summary's field and as a condition."""
    c = db.connect(application_name="autosql-demo-t88-keys")
    try:
        records = _one_record_table(c, "t88_keys", "noun:K", {**_KEYS, **_DECOYS})
        fields = [f for f in _pview._read_fields(c, "noun:K", records=records) if f["kind"] == "number"]
        read, wrong = {}, {}
        for f in fields:
            try:
                sql, python = _both(c, records, "noun:K", {"aggregate": {"fn": "max", "field": _pview.field_ref(f["path"])}})
                if sql != python:
                    wrong[f["path"]] = ("the engines differ", sql, python)
                    continue
                read[f["path"]] = n = int(sql[0][0]) if sql[0][0] is not None else None
                sql, python = _both(c, records, "noun:K", {"aggregate": {"fn": "count", "field": None},
                                                           "filter": f"{_pview.field_ref(f['path'])} == {n or 0}"})
                if not sql == python == [[1]]:
                    wrong[f["path"]] = ("its condition reads another key", sql, python)
            except Exception as e:  # noqa: BLE001 — a name an engine can't read is a wrong name
                wrong[f["path"]] = ("an engine could not read it", repr(e)[:80])
        want = sorted(list(_KEYS.values()) + [v for v in _DECOYS.values() if isinstance(v, int)] + [9])
        twice = {p: v for p, v in read.items() if v is None or list(read.values()).count(v) > 1}
        assert not wrong and not twice and sorted(read.values()) == want, (
            f"names that read another key or nothing: {twice}; names an engine got wrong: {wrong}; "
            f"keys never offered: {sorted(set(want) - set(read.values()))}")
    finally:
        c.rollback()
        c.close()


@pytest.mark.parametrize("hand_sent", ['["a\\bc"]', '["a\\u0008c"]', '["abc"]', '["a"].c', 'a["c"]x', '[""]'])
def test_a_name_spelled_any_other_way_is_refused(hand_sent):
    """Only the one spelling the page offers is a name: a hand-sent JSON escape, a needless bracket or
    anything that would read another key is refused, never read."""
    with pytest.raises(ValueError):
        _paths.steps(hand_sent)
    from picks.gate import Refused
    with pytest.raises((ValueError, _builder.IllegalPick, _pview.ViewError, Refused)):
        _builder.build({"source": "noun:K", "computed": [], "filter": None, "sort": None, "cap": None,
                        "window": None, "changed": False, "bucket": "off",
                        "aggregate": {"fn": "max", "field": hand_sent}}, ["a", "abc"],
                       records=_Records(table="t88_keys", sources={"noun:K": "odd keys"}))


def test_a_record_with_an_empty_key_does_not_break_its_data_sets_fields():
    c = db.connect(application_name="autosql-demo-t88-empty-key")
    try:
        records = _one_record_table(c, "t88_empty", "noun:E", {"": 1, "a": 2})
        assert [f["path"] for f in _pview._read_fields(c, "noun:E", records=records)] == ["a"]
    finally:
        c.rollback()
        c.close()


_ZONES = ["America/Denver", "Asia/Kolkata", "Pacific/Kiritimati"]


@pytest.mark.parametrize("zone", _ZONES)
def test_the_pick_vectors_hold_whatever_the_sessions_time_zone(zone):
    """GIMS's connection may not be UTC: buckets are cut in UTC by the statement itself."""
    c = db.connect(application_name="autosql-demo-t88-zone")
    try:
        c.execute(f"SET LOCAL TimeZone = '{zone}'")
        bad = [(r.name, r.sql, r.python, r.expect) for r in check_picks.run_vectors(c) if not r.ok]
        assert not bad, bad
    finally:
        c.rollback()
        c.close()


@pytest.mark.parametrize("zone", _ZONES)
def test_a_series_buckets_in_utc_whatever_the_sessions_time_zone(zone):
    """Another host's time series (not the demo's own, whose sessions are pinned to UTC)."""
    c = db.connect(application_name="autosql-demo-t88-zone-series")
    try:
        c.execute("CREATE TEMPORARY TABLE t88_series (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
        for k, at in (("r1", "2026-01-05T00:30:00Z"), ("r2", "2026-01-05T23:30:00Z"), ("r3", "2026-01-31T23:30:00Z")):
            c.execute("INSERT INTO t88_series VALUES ('noun:P', %s, %s::jsonb)", (k, _json.dumps({"at": at, "m": "x"})))
        records = _Records(table="t88_series", sources={"noun:P": "at, m"},
                           series={"source": "noun:P", "time": "at", "member": "m"})
        c.execute(f"SET LOCAL TimeZone = '{zone}'")
        for bucket, want in (("day", [["2026-01-05T00:00:00Z", 2], ["2026-01-31T00:00:00Z", 1]]),
                             ("month", [["2026-01-01T00:00:00Z", 3]])):
            sql, python = _both(c, records, "noun:P", {"bucket": bucket, "aggregate": {"fn": "count", "field": None}})
            assert sql == python == want, (bucket, sql, python)
    finally:
        c.rollback()
        c.close()


def test_a_summary_over_a_named_time_field_reads_one_owner():
    """Tenancy (the check's O1): a per-week summary over a named date field counts its owner's records only."""
    c = db.connect(application_name="autosql-demo-t88-owner")
    try:
        c.execute("CREATE TEMPORARY TABLE t88_owners (owner text, collection text, key text, data jsonb, "
                  "PRIMARY KEY (owner, collection, key))")
        for o, k, at in (("acme", "r1", "2026-01-05"), ("acme", "r2", "2026-01-07"), ("other", "r1", "2026-01-06")):
            c.execute("INSERT INTO t88_owners VALUES (%s, 'noun:R', %s, %s::jsonb)", (o, k, _json.dumps({"at": at})))
        acme = _Records(table="t88_owners", sources={"noun:R": "at"}, partition=("owner", "acme"))
        sql, python = _both(c, acme, "noun:R", {"bucket": "week", "bucket_field": "at",
                                                "aggregate": {"fn": "count", "field": None}})
        assert sql == python == [["2026-01-05T00:00:00Z", 2]], "another owner's record was counted"
    finally:
        c.rollback()
        c.close()


_PRIORITY = {"field": "priority", "op": "gt", "value": 2, "value2": None, "values": []}


def test_one_number_per_value_keeps_the_pages_conditions(client, conn):
    """The check's VW1: the conditions narrow a per-value summary, as hand-written SQL does."""
    want = conn.execute("""
        SELECT CASE WHEN jsonb_typeof(data->'status') IN ('string', 'number', 'boolean') THEN data->>'status' END, count(*)
          FROM demo.records WHERE collection = 'noun:Sample'
           AND jsonb_typeof(data->'priority') = 'number' AND (data->>'priority')::numeric > 2
         GROUP BY 1 ORDER BY 1 NULLS LAST""").fetchall()
    v = summary("samples", fn="count", field=None, per="category", by="status")
    v["conditions"] = [_PRIORITY]
    st, a = ask(client, v)
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    assert [(c["label"], int(c["exact"])) for c in a["categories"]] == [(k, int(n)) for k, n in want]


def test_a_total_per_value_is_a_total(client, conn):
    """The check's VW2: a total per value equals hand-written SQL's sum (not its average)."""
    want = conn.execute("""
        SELECT CASE WHEN jsonb_typeof(data->'status') IN ('string', 'number', 'boolean') THEN data->>'status' END,
               sum((data->>'priority')::numeric) FILTER (WHERE jsonb_typeof(data->'priority') = 'number')
          FROM demo.records WHERE collection = 'noun:Sample' GROUP BY 1 ORDER BY 1 NULLS LAST""").fetchall()
    st, a = ask(client, summary("samples", fn="sum", field="priority", per="category", by="status"))
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    got = [(c["label"], Decimal(c["exact"]) if c["exact"] is not None else None) for c in a["categories"]]
    assert got == [(k, Decimal(v) if v is not None else None) for k, v in want]


def test_a_board_measures_a_field_named_in_brackets(conn):
    """The demo's board probes its measure by the field's own name, not ``"$." + name``
    (``$.["Sample Weight (g)"]`` is no name)."""
    from demo.server import scoreboard

    spec = {"source": "noun:Sample", "group": "status", "filter": None, "counts": [], "time": None,
            "measure": {"fn": "avg", "field": '["Sample Weight (g)"]'}, "sort": None, "cap": None}
    out = scoreboard.run_group(conn, spec)
    conn.rollback()
    assert out.get("verdict") == "agree", out
