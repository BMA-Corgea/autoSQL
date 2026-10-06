"""demo/tests/test_scoreboard.py — T-73 S6, the scoreboard engine (a SAFETY slice).

Every number here is checked against something that is neither engine:
* the seed generator's own rows (``demo/seed/generate.py``), and
* hand-written SQL — ``SUM(CASE WHEN … THEN 1 ELSE 0 END)``, the
  sql-gauntlet's own form — typed out in this file, not produced by
  ``demo/group.py``, run on the demo's read-only connection.

And the two engines are held to each other, cell by cell, with two mutants
that must be caught: one in the shared logic composition (caught by the
truth tables), one in the second engine (caught by the comparison).

What a scoreboard is: README.md, "The dashboard: SQL analysis, kept out of sight";
what it must do: the tests below, one class or group per promise.
"""

from __future__ import annotations

import itertools
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for _p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard, db, scoreboard  # noqa: E402
from seed import generate  # noqa: E402

import builder  # noqa: E402
import group  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402

_HB = [json.loads(d) for _c, _k, d in generate.heartbeat_rows()]
_SMP = [json.loads(d) for _c, _k, d in generate.sample_rows()]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    return client.get("/api/dashboard/setup").json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-scoreboard-test")
    server_app.refuse_writes(c)
    yield c
    c.close()


def board(setup, ds_id="heartbeats", **sb):
    v = {"dataset": ds_id, "columns": [], "conditions": [], "sort": None,
         "show": None, "summary": None, "scoreboard": sb}
    return v


def ask(client, v, page=0, *, admin=True):
    """One answer; as the Admin view asks for it unless ``admin=False``
    (only Admin's answers carry the statement and the engines' verdict)."""
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page, "admin": admin})
    return r.status_code, r.json()


def cond(field, op, **kw):
    return {"field": field, "op": op, **kw}


def count(label, *conditions, logic="all", pct=False):
    return {"label": label, "logic": logic, "conditions": list(conditions), "pct": pct}


def q1(k, n):
    return str((Decimal(100 * k) / Decimal(n)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


# ═════════════════════════════════════════════════════════════════════════
# AC3 — the four logics, as truth tables, through BOTH engines
# ═════════════════════════════════════════════════════════════════════════

#: One condition per variable: holds when the key is 1, fails when it is 0,
#: and the key may be MISSING — the third value a real field can take.
_VARS = ("a", "b", "c")
_STATES = ("T", "F", "missing")


def _record(states):
    rec = {}
    for name, st in zip(_VARS, states):
        if st == "T":
            rec[name] = 1
        elif st == "F":
            rec[name] = 0
    return rec


def _definition(logic, truths):
    n = sum(truths)
    return {"all": n == len(truths), "any": n >= 1,
            "one": n == 1, "allnone": n in (0, len(truths))}[logic]


@pytest.mark.parametrize("k", [2, 3])
@pytest.mark.parametrize("logic", ["all", "any", "one", "allnone"])
def test_truth_table_both_engines(conn, logic, k):
    """Every combination of holds / fails / missing, for 2 and 3 conditions:
    the composed expression, evaluated by GIMS's evaluator AND compiled and
    run by the database, against the definition written above."""
    expr = dashboard.compose([f"$.{v} == 1" for v in _VARS[:k]], logic)
    ast = server_app.expr.parse(expr)
    compiled = builder._compile_expression(expr, ctx_param="tt_ctx", column="t.data")
    for states in itertools.product(_STATES, repeat=k):
        rec = _record(states)
        want = _definition(logic, [s == "T" for s in states])
        py = server_app.expr.truthy(server_app.expr.evaluate(ast, rec, {}))
        params = dict(compiled.params, tt_ctx="{}", rec=json.dumps(rec))
        sql = conn.execute(
            f"SELECT xpr.truthy( {compiled.sql.replace('%(p', '%(p')} ) "
            "FROM (SELECT %(rec)s::jsonb AS data) AS t", params).fetchone()[0]
        assert py is want and sql is want, (logic, states, py, sql)


def test_for_two_conditions_they_are_the_standard_operators():
    for a, b in itertools.product([True, False], repeat=2):
        assert _definition("one", [a, b]) == (a ^ b)
        assert _definition("allnone", [a, b]) == (not (a ^ b))


@pytest.mark.parametrize("logic, test", [
    ("all", lambda w, h, a: w and h and a), ("any", lambda w, h, a: w or h or a),
    ("one", lambda w, h, a: (w + h + a) == 1), ("allnone", lambda w, h, a: (w + h + a) in (0, 3)),
])
def test_the_page_filter_takes_each_logic(client, setup, logic, test):
    conds = [cond("status", "eq", value="warn"), cond("payload.load", "gt", value=50),
             cond("payload.note", "eq", value="alpha")]
    want = sum(1 for r in _HB if test(r["status"] == "warn", r["payload"]["load"] > 50,
                                       r["payload"]["note"] == "alpha"))
    v = {"dataset": "heartbeats", "columns": ["status"], "conditions": conds, "logic": logic,
         "sort": None, "show": None, "summary": None}
    _, a = ask(client, v)
    assert a["total"] == want and a["admin"]["verdict"] == "agree", (logic, a.get("sentence"))


def test_the_sentence_says_the_logic(client, setup):
    v = {"dataset": "heartbeats", "columns": ["status"], "logic": "one", "sort": None,
         "show": None, "summary": None,
         "conditions": [cond("status", "eq", value="warn"), cond("payload.load", "gt", value=50)]}
    _, a = ask(client, v)
    assert a["sentence"].startswith("Heartbeats where exactly one of: Status is warn and Load is more than 50 — ")
    v["logic"] = "allnone"
    _, a = ask(client, v)
    assert "where all or none of: Status is warn and Load is more than 50" in a["sentence"]


@pytest.mark.parametrize("logic", ["one", "allnone"])
def test_exactly_one_needs_two_conditions(client, setup, logic):
    v = {"dataset": "heartbeats", "columns": ["status"], "logic": logic, "sort": None,
         "show": None, "summary": None, "conditions": [cond("status", "eq", value="warn")]}
    status, a = ask(client, v)
    assert status == 422 and a["message"].endswith("needs two or more conditions.")


def test_missing_values_count_as_not_holding(client, setup):
    """Samples' Due date is missing on some rows: "before" fails there, so
    XOR with Status is open counts those rows by Status alone."""
    def before(r):
        return "due_date" in r and r["due_date"] < "2026-10-01"
    want = sum(1 for r in _SMP if before(r) != (r["status"] == "open"))
    _, a = ask(client, board(setup, "samples", by="priority", counts=[count(
        "Either", cond("due_date", "before", value="2026-10-01"),
        cond("status", "eq", value="open"), logic="one")]))
    assert sum(int(r[2]) for r in a["rows"]) == want
    assert a["admin"]["verdict"] == "agree"


# ═════════════════════════════════════════════════════════════════════════
# AC8 — the gauntlet scoreboard, every cell against hand-written SQL
# ═════════════════════════════════════════════════════════════════════════

#: Written by hand for this test, in the gauntlet's own form; it shares no
#: code with demo/group.py.
_HAND_WRITTEN = """
SELECT data ->> 'sender_id'                                            AS sender,
       count(*)                                                        AS beats,
       SUM(CASE WHEN data ->> 'status' = 'ok' THEN 1 ELSE 0 END)       AS ok,
       ROUND(100.0 * SUM(CASE WHEN data ->> 'status' = 'ok' THEN 1 ELSE 0 END)
             / count(*), 1)                                            AS pct_ok,
       SUM(CASE WHEN data ->> 'status' IN ('warn', 'error') THEN 1 ELSE 0 END) AS trouble,
       SUM(CASE WHEN data ->> 'status' = 'warn'
                 AND (data -> 'payload' ->> 'load')::numeric > 50 THEN 1 ELSE 0 END) AS hot_warn,
       MAX(data ->> 'ts')                                              AS latest,
       ROUND(AVG((data -> 'payload' ->> 'load')::numeric), 6)          AS avg_load
  FROM demo.records
 WHERE collection = 'noun:Heartbeat'
 GROUP BY data ->> 'sender_id'
 ORDER BY sender
"""

_GAUNTLET = dict(
    by="sender_id",
    counts=[count("OK", cond("status", "eq", value="ok"), pct=True),
            count("Trouble", cond("status", "eq", value="warn"),
                  cond("status", "eq", value="error"), logic="any"),
            count("Hot warn", cond("status", "eq", value="warn"),
                  cond("payload.load", "gt", value=50))],
    time={"fn": "latest", "field": "ts"},
    measure={"fn": "avg", "field": "payload.load"},
)


def test_the_gauntlet_scoreboard_cell_by_cell(client, setup, conn):
    want = conn.execute(_HAND_WRITTEN).fetchall()
    assert len(want) == 50
    spec, _ = dashboard.to_spec(setup, board(setup, **_GAUNTLET))
    result = scoreboard.run_group(conn, spec)
    assert result["accepted"] and result["verdict"] == "agree"
    assert result["comparison"]["compared_rows"] == 50
    got = [r["c"] for r in result["panes"]["sql"]["rows"]]
    for row, (sender, beats, ok, pct, trouble, hot, latest, avg_load) in zip(got, want):
        assert row == [sender, str(beats), str(ok), str(pct), str(trouble), str(hot),
                       latest, str(avg_load)], sender

    # and the page's own rendering of the first sender
    _, a = ask(client, board(setup, **_GAUNTLET))
    sender, beats, ok, pct, trouble, hot, latest, avg_load = want[0]
    assert a["sentence"] == "Heartbeats per Sender — 50 senders"
    assert a["rows"][0][:6] == [sender, str(beats), str(ok), f"{pct}%", str(trouble), str(hot)]


def test_the_gauntlet_counts_against_the_generator(client, setup):
    _, a = ask(client, board(setup, **_GAUNTLET))
    by_sender = {}
    for r in _HB:
        g = by_sender.setdefault(r["sender_id"], [0, 0, 0, 0])
        g[0] += 1
        g[1] += r["status"] == "ok"
        g[2] += r["status"] in ("warn", "error")
        g[3] += r["status"] == "warn" and r["payload"]["load"] > 50
    for row in a["rows"]:
        n, ok, trouble, hot = by_sender[row[0]]
        assert row[1:6] == [str(n), str(ok), q1(ok, n) + "%", str(trouble), str(hot)], row[0]


@pytest.mark.parametrize("logic, test", [
    ("all", lambda w, h: w and h), ("any", lambda w, h: w or h),
    ("one", lambda w, h: w != h), ("allnone", lambda w, h: w == h),
])
def test_changing_a_columns_logic_changes_its_counts_correctly(client, setup, conn, logic, test):
    """The outcome check: AND → OR → XOR → XNOR on one count column, each
    against hand-written SQL and the generator."""
    sb = dict(by="sender_id", counts=[count(
        "Hot", cond("status", "eq", value="warn"), cond("payload.load", "gt", value=50), logic=logic)])
    _, a = ask(client, board(setup, **sb))
    sql_test = {"all": "{w} AND {h}", "any": "{w} OR {h}",
                "one": "({w}) <> ({h})", "allnone": "({w}) = ({h})"}[logic].format(
        w="data ->> 'status' = 'warn'", h="(data -> 'payload' ->> 'load')::numeric > 50")
    hand = dict(conn.execute(
        f"SELECT data ->> 'sender_id', SUM(CASE WHEN {sql_test} THEN 1 ELSE 0 END) "
        "FROM demo.records WHERE collection = 'noun:Heartbeat' GROUP BY 1").fetchall())
    gen: dict = {}
    for r in _HB:
        gen[r["sender_id"]] = gen.get(r["sender_id"], 0) + bool(
            test(r["status"] == "warn", r["payload"]["load"] > 50))
    for row in a["rows"]:
        assert int(row[2]) == hand[row[0]] == gen[row[0]], (logic, row[0])
    assert a["admin"]["verdict"] == "agree"


# ═════════════════════════════════════════════════════════════════════════
# AC1, AC2, AC4 — groups, count-if columns, the standard columns
# ═════════════════════════════════════════════════════════════════════════

def test_every_group_appears_even_when_a_count_is_zero(client, setup):
    _, a = ask(client, board(setup, by="status", counts=[count(
        "Overloaded", cond("payload.load", "gt", value=1000))]))
    assert [r[0] for r in a["rows"]] == ["error", "ok", "warn"]
    assert [r[2] for r in a["rows"]] == ["0", "0", "0"]


def test_the_page_filter_narrows_rows_before_grouping(client, setup):
    v = board(setup, by="status", counts=[count("Hot", cond("payload.load", "gt", value=50))])
    v["conditions"] = [cond("status", "ne", value="ok")]
    _, a = ask(client, v)
    assert [r[0] for r in a["rows"]] == ["error", "warn"]
    assert a["sentence"] == "Heartbeats per Status where Status is not ok — 2 statuses"


def test_a_blank_group_is_its_own_row(client, setup):
    _, a = ask(client, board(setup, "edge", by="s", counts=[count("Zero", cond("z", "eq", value=0))]))
    assert [r[0] for r in a["rows"]] == ["12.5", "(blank)"]
    assert [r[1] for r in a["rows"]] == ["1", "9"]


def test_samples_by_priority_with_earliest_and_a_total(client, setup, conn):
    hand = conn.execute("""
        SELECT (data ->> 'priority')::int, count(*),
               SUM(CASE WHEN data ->> 'status' = 'open' THEN 1 ELSE 0 END),
               MIN(data ->> 'due_date')
          FROM demo.records WHERE collection = 'noun:Sample' GROUP BY 1 ORDER BY 1""").fetchall()
    _, a = ask(client, board(setup, "samples", by="priority",
                             counts=[count("Open", cond("status", "eq", value="open"), pct=True)],
                             time={"fn": "earliest", "field": "due_date"}))
    assert [c["label"] for c in a["columns"]] == ["Priority", "Rows", "Open", "% Open", "Earliest Due date"]
    for row, (p, n, k, earliest) in zip(a["rows"], hand):
        assert row[:4] == [str(p), str(n), str(k), q1(k, n) + "%"]
        assert row[4] == dashboard.fmt_date(earliest)


@pytest.mark.parametrize("fn", ["sum", "avg", "min", "max"])
def test_the_measure_column(client, setup, conn, fn):
    sql_fn = {"sum": "ROUND(SUM({x}), 6)", "avg": "ROUND(AVG({x}), 6)",
              "min": "MIN({x})", "max": "MAX({x})"}[fn].format(x="(data -> 'payload' ->> 'load')::numeric")
    hand = dict(conn.execute(
        f"SELECT data ->> 'status', {sql_fn} FROM demo.records "
        "WHERE collection = 'noun:Heartbeat' GROUP BY 1").fetchall())
    spec, _ = dashboard.to_spec(setup, board(setup, by="status",
                                              measure={"fn": fn, "field": "payload.load"}))
    result = scoreboard.run_group(conn, spec)
    assert result["verdict"] == "agree"
    for r in result["panes"]["sql"]["rows"]:
        assert Decimal(r["c"][2]) == hand[r["c"][0]]


@pytest.mark.parametrize("label, says", [
    ("", "Give each count column a name."),
    ("   ", "Give each count column a name."),
    ("x" * 41, "A column's name can be at most 40 characters."),
    ("bad\x00name", "A column's name can't hold control or invisible characters."),
    ("tab\there", "A column's name can't hold control or invisible characters."),
    ("zero​width", "A column's name can't hold control or invisible characters."),
    (7, "A column's name must be text."),
])
def test_labels_are_checked(client, setup, label, says):
    status, a = ask(client, board(setup, by="status",
                                  counts=[count(label, cond("payload.load", "gt", value=50))]))
    assert status == 422 and a["message"] == says


def test_a_label_never_reaches_the_statement(client, setup):
    label = 'Hot "x"; DROP TABLE demo.records; --'
    _, a = ask(client, board(setup, by="status",
                             counts=[count(label, cond("payload.load", "gt", value=50))]))
    assert a["columns"][2]["label"] == label
    assert "DROP" not in a["admin"]["statement"] and "DROP" not in a["admin"]["parameterised"]
    assert all("DROP" not in str(p["value"]) for p in a["admin"]["parameters"])


def test_at_most_six_count_columns(client, setup):
    many = [count(f"C{i}", cond("payload.load", "gt", value=i)) for i in range(7)]
    status, a = ask(client, board(setup, by="status", counts=many))
    assert status == 422 and a["message"] == "A scoreboard has at most 6 count columns."
    _, a = ask(client, board(setup, by="status", counts=many[:6]))
    assert len(a["columns"]) == 8 and a["admin"]["verdict"] == "agree"


@pytest.mark.parametrize("patch, says", [
    ({"by": "id"}, "ID can't be grouped by: ID has 2,000 different values"),
    ({"by": "due_date"}, "Due date can't be grouped by: Times and dates are grouped per hour or per day"),
    ({"by": "field_3"}, "Field 3 can't be grouped by: Its rows hold different kinds of value"),
    ({"by": "status", "extra": 1}, "This page can't use 'extra' in a scoreboard yet."),
    ({"by": "status", "time": {"fn": "latest", "field": "priority"}},
     "Latest and earliest read a time or a date field."),
    ({"by": "status", "counts": [count("A", cond("status", "eq", value="open")),
                                 count("A", cond("status", "eq", value="hold"))]},
     "Two count columns are both called “A”."),
    ({"by": "status", "counts": [{"label": "A", "logic": "all", "conditions": [], "pct": False}]},
     "“A” needs at least one condition."),
    ({"by": "status", "sort": {"column": "pct:1", "dir": "asc"},
      "counts": [count("A", cond("status", "eq", value="open"))]},
     "Sort a scoreboard by one of its own columns."),
])
def test_what_a_scoreboard_cannot_honour_is_refused(client, setup, patch, says):
    status, a = ask(client, board(setup, "samples", **patch))
    assert status == 422 and a["message"].startswith(says), a["message"]


def test_a_scoreboard_refuses_rows_choices(client, setup):
    v = board(setup, by="status")
    v["columns"] = ["status"]
    assert ask(client, v)[1]["message"] == "Columns don't apply to a scoreboard; untick them first."
    v = board(setup, by="status")
    v["sort"] = {"field": "ts", "dir": "desc"}
    assert ask(client, v)[1]["message"] == "Sort a scoreboard by one of its own columns."


def test_the_group_cap_is_stated(setup):
    smp = {f["path"]: f["group"] for f in next(d for d in setup["datasets"] if d["id"] == "samples")["fields"]}
    assert smp["id"] == {"ok": False, "groups": 2000, "why": (
        "ID has 2,000 different values — one row per value would be about as long as the "
        "table itself. One row per value works up to 500 different values.")}
    hb = {f["path"]: f["group"] for f in next(d for d in setup["datasets"] if d["id"] == "heartbeats")["fields"]}
    assert hb["sender_id"] == {"ok": True, "why": "", "groups": 50}


# ═════════════════════════════════════════════════════════════════════════
# AC6 — sort by any column; ties by the group; paging never drops a row
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("column", ["group", "rows", "count:1", "pct:1", "time", "measure"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_any_column_in_a_total_order(client, setup, conn, column, direction):
    sb = dict(_GAUNTLET, sort={"column": column, "dir": direction})
    _, a = ask(client, board(setup, **sb), page=0)
    assert a["admin"]["verdict"] == "agree"
    spec, _ = dashboard.to_spec(setup, board(setup, **sb))
    rows = scoreboard.run_group(conn, spec)["panes"]["sql"]["rows"]
    idx = group.columns_of(spec).index(spec["sort"]["column"])

    def key(r):
        v = r["c"][idx]
        return Decimal(v) if spec["sort"]["column"] not in ("grp", "time") else v
    for x, y in zip(rows, rows[1:]):
        kx, ky = key(x), key(y)
        if kx == ky:
            assert x["c"][0] < y["c"][0]          # ties broken by the group, ascending
        else:
            assert (kx < ky) if direction == "asc" else (kx > ky)


def test_paging_never_drops_or_doubles_a_group(client, setup):
    """Load has 101 values (0–100): three pages, and many groups share a
    count, so the tie-break is what keeps each page's slice stable."""
    sb = dict(by="payload.load", counts=[count("Warn", cond("status", "eq", value="warn"))],
              sort={"column": "count:1", "dir": "desc"})
    _, first = ask(client, board(setup, **sb), page=0)
    assert first["total"] == 101 and first["page"]["last"] == 2
    seen = []
    for page in range(3):
        _, a = ask(client, board(setup, **sb), page=page)
        seen += [r[0] for r in a["rows"]]
    assert len(seen) == 101 and len(set(seen)) == 101
    assert sorted(seen, key=int) == [str(i) for i in range(101)]


# ═════════════════════════════════════════════════════════════════════════
# AC5 — both engines, cell by cell; the second engine's own computation
# ═════════════════════════════════════════════════════════════════════════

def test_the_engines_name_the_same_columns():
    spec = {"counts": [{"expr": "1", "pct": True}, {"expr": "1", "pct": False}],
            "time": {"fn": "max", "field": "ts"}, "measure": {"fn": "avg", "field": "x"}}
    assert group.columns_of(spec) == pygroup.columns_of(spec)


def test_the_second_engine_imports_nothing_from_the_first():
    text = (_DEMO_DIR / "pyrunner" / "group.py").read_text()
    for name in ("builder", "probes", "demo.group", "import group", "psycopg"):
        assert name not in text.split('"""', 2)[2], name


def test_mutant_in_the_second_engine_is_caught(conn, setup, monkeypatch):
    """A second engine that counts a condition whenever it is not null —
    instead of whenever it holds — must be caught by the comparison."""
    spec, _ = dashboard.to_spec(setup, board(setup, by="sender_id", counts=[count(
        "Hot", cond("status", "eq", value="warn"), cond("payload.load", "gt", value=50), logic="one")]))
    assert scoreboard.run_group(conn, spec)["verdict"] == "agree"

    real = pygroup.ev.expr.truthy
    monkeypatch.setattr(pygroup.ev.expr, "truthy", lambda v: v is not None)
    try:
        assert scoreboard.run_group(conn, spec)["verdict"] == "disagree"
    finally:
        monkeypatch.setattr(pygroup.ev.expr, "truthy", real)


def test_mutant_in_the_shared_logic_is_caught_by_the_truth_table(conn, monkeypatch):
    """Exactly one written as "at least one" fools both engines alike — so
    it is the truth table, not the comparison, that must catch it."""
    real = dashboard.compose

    def mutant(exprs, logic):
        out = real(exprs, logic)
        return out.replace(") == 1", ") >= 1") if logic == "one" else out

    monkeypatch.setattr(dashboard, "compose", mutant)
    with pytest.raises(AssertionError):
        test_truth_table_both_engines(conn, "one", 2)


def test_every_scoreboard_on_the_seed_agrees(conn, setup):
    """A matrix over the three data sets: every groupable field, a count
    column of each logic, both standard columns where they exist."""
    for d in setup["datasets"]:
        fields = {f["path"]: f for f in d["fields"]}
        groupable = [p for p, f in fields.items() if f["group"]["ok"]]
        matchable = [p for p, f in fields.items() if "present" in f["ops"]][:3]
        for by in groupable:
            counts = []
            for logic in ("all", "any", "one", "allnone"):
                if len(matchable) >= 2:
                    counts.append(count(f"L{logic}", cond(matchable[0], "present"),
                                        cond(matchable[1], "blank"), logic=logic, pct=True))
            sb = {"by": by, "counts": counts}
            times = [p for p, f in fields.items() if f["kind"] in ("time", "date")]
            if times:
                sb["time"] = {"fn": "latest", "field": times[0]}
            try:
                spec, _ = dashboard.to_spec(setup, board(setup, d["id"], **sb))
            except dashboard.ViewError:
                continue
            result = scoreboard.run_group(conn, spec)
            if result["accepted"]:
                assert result["verdict"] == "agree", (d["id"], by)


def test_near_duplicate_labels_are_refused(client, setup):
    status, a = ask(client, board(setup, "samples", by="status", counts=[
        count("Open", cond("status", "eq", value="open")),
        count(" open ", cond("priority", "ge", value=4))]))
    assert status == 422 and a["message"] == "Two count columns are both called “open”."


def test_is_not_counts_rows_without_the_field(client, setup):
    """A row WITHOUT the field is "not" the value picked, so it counts — the
    page filter's reading since S2, both engines agreeing; the picker says
    so in words.  Edge cases' S is on one row only."""
    edge = [json.loads(d) for _c, _k, d in generate.edge_case_rows()]
    want = sum(1 for r in edge if r.get("s") != "12.5")
    assert want == sum(1 for r in edge if "s" not in r) == 9
    _, a = ask(client, board(setup, "edge", by="label", counts=[
        count("Not 12.5", cond("s", "ne", value="12.5"))]))
    assert sum(int(r[2]) for r in a["rows"]) == want and a["admin"]["verdict"] == "agree"
    assert setup["op_labels"]["ne"] == "is not (rows without a value count too)"
    assert setup["op_words"]["ne"] == "is not"


class TestOneNumberingForCountColumns:
    """The S7 check's HIGH: a header and a sort must mean the same column.
    A count column carries its own id end to end — the answer's header ids
    and a sort both use it — so a column held back cannot shift numbering."""

    def _sb(self, sort=None):
        sb = dict(by="sender_id", counts=[
            dict(count("Warn", cond("status", "eq", value="warn")), id=7),
            dict(count("Errors", cond("status", "eq", value="error"), pct=True), id=3)])
        if sort:
            sb["sort"] = sort
        return sb

    def test_header_ids_are_the_columns_own(self, client, setup):
        _, a = ask(client, board(setup, **self._sb()))
        assert [c["id"] for c in a["columns"]] == ["group", "rows", "count:7", "count:3", "pct:3"]

    @pytest.mark.parametrize("column, idx", [("count:7", 2), ("count:3", 3), ("pct:3", 4)])
    def test_each_header_sorts_its_own_column(self, client, setup, column, idx):
        _, a = ask(client, board(setup, **self._sb({"column": column, "dir": "desc"})))
        values = [Decimal(r[idx].rstrip("%")) for r in a["rows"]]
        assert values == sorted(values, reverse=True), column
        others = [Decimal(r[j].rstrip("%")) for r in a["rows"] for j in (2, 3) if j != idx]
        assert others != sorted(others, reverse=True)   # it is not sorted by a neighbour

    @pytest.mark.parametrize("patch, says", [
        ({"column": "count:1", "dir": "desc"}, "Sort a scoreboard by one of its own columns."),
        ({"column": "pct:7", "dir": "desc"}, "Sort a scoreboard by one of its own columns."),
    ])
    def test_a_sort_naming_no_sent_column_is_refused(self, client, setup, patch, says):
        status, a = ask(client, board(setup, **self._sb(patch)))
        assert status == 422 and a["message"] == says

    @pytest.mark.parametrize("ids, says", [
        ((7, 7), "Two count columns share one id."),
        ((0, 3), "A count column's id must be a whole number."),
        (("7", 3), "A count column's id must be a whole number."),
        ((True, 3), "A count column's id must be a whole number."),
    ])
    def test_ids_are_checked(self, client, setup, ids, says):
        sb = self._sb()
        for c, i in zip(sb["counts"], ids):
            c["id"] = i
        status, a = ask(client, board(setup, **sb))
        assert status == 422 and a["message"] == says


def test_one_letter_group_names_read_plainly(client, setup):
    """T-75 item 13: "2 values of A", not "2 A values"."""
    _, a = ask(client, board(setup, "edge", by="a", counts=[count("Zero", cond("z", "eq", value=0))]))
    assert a["sentence"] == "Edge cases per A — 2 values of A"


def test_the_second_engine_overflowing_is_a_named_refusal(client, setup, monkeypatch):
    """T-75 item 12, for scoreboards."""
    dashboard._CACHE.clear()

    def overflow(*a, **k):
        raise OverflowError("int too large to convert to float")

    monkeypatch.setattr(pygroup, "python_pane", overflow)
    status, a = ask(client, board(setup, "edge", by="a", counts=[count("Zero", cond("z", "eq", value=0))]))
    assert status == 200 and a["kind"] == "refused"
    assert a["message"] == "One of these values is too large to compute with, so this can't be answered honestly."
    assert "GROUP BY 1" in a["admin"]["statement"]
    dashboard._CACHE.clear()


def test_scoreboard_averages_carry_their_exact_value(client, setup, conn):
    """T-75 item 18: an average reads to two places, with its six-place
    value beside it for hover / tap."""
    _, a = ask(client, board(setup, by="status", measure={"fn": "avg", "field": "payload.load"}))
    hand = dict(conn.execute(
        "SELECT data ->> 'status', ROUND(AVG((data -> 'payload' ->> 'load')::numeric), 6) "
        "FROM demo.records WHERE collection = 'noun:Heartbeat' GROUP BY 1").fetchall())
    for row, titles in zip(a["rows"], a["titles"]):
        assert titles[:2] == [None, None]
        assert titles[2] == f"To six places: {hand[row[0]]}"
        assert row[2] == f"{hand[row[0]]:.2f}"
