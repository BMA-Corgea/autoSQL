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
