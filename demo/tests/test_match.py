"""demo/tests/test_match.py — T-76 S16: joins you choose.

A person picks another data set and the field pair that matches; the
board counts across that match.  This file holds the rule in both engines
(T-76 "What a match means"), the double-count refusal (AC4), the preview's
numbers (AC3), the boards against SQL written by hand (AC5), the gate's
refusals (AC8), the sentence (AC9), the probe split's killers (T-77 item 8)
and the S13 check's MEDIUM (names compared with whitespace collapsed).

Every number here is checked against something that is neither engine:
SQL written by hand in this file (LEFT JOIN … COUNT(c.key)), counted from the
generator's rows, or a fixture whose answer is written beside it.  The
fixtures go into scratch collections inside one transaction that is rolled
back (test_alias.py's pattern); B10's digest guard proves nothing stayed.

The mutants that must die are listed, each with the test here that kills it,
in demo/tests/t76_mutants.py.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
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

import group  # noqa: E402
import legality  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402
from pyrunner.rows import read_rows  # noqa: E402

_SENDERS = [json.loads(d) for _c, _k, d in generate.sender_rows()]
_HB = [json.loads(d) for _c, _k, d in generate.heartbeat_rows()]

SITES_SENDERS = {"dataset": "senders", "field": "site", "matches": "name"}
SENDERS_SITES = {"dataset": "sites", "field": "name", "matches": "site"}
SENDERS_HEARTBEATS = {"dataset": "heartbeats", "field": "sender_id", "matches": "id"}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    return client.get("/api/dashboard/setup").json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-match-test")
    server_app.refuse_writes(c)
    yield c
    c.close()


@pytest.fixture(scope="module")
def wconn():
    """A connection that may write — only ever inside a transaction this
    file rolls back."""
    c = db.connect(application_name="autosql-demo-match-fixture")
    yield c
    c.rollback()
    c.close()


def cond(field, op, **kw):
    return {"field": field, "op": op, **kw}


def count(label, *conditions, logic="all", pct=False, cid=None):
    out = {"label": label, "logic": logic, "conditions": list(conditions), "pct": pct}
    if cid is not None:
        out["id"] = cid
    return out


def board(dataset, by, count_from, conditions=(), **sb):
    sb = {"by": by, "count_from": count_from, "counts": [], "time": None, "measure": None,
          "sort": None, **sb}
    return {"dataset": dataset, "columns": [], "conditions": list(conditions), "logic": "all",
            "sort": None, "show": None, "summary": None, "scoreboard": sb}


def ask(client, v, page=0, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page, "admin": admin})
    return r.status_code, r.json()


def every_row(client, v, admin=True):
    rows, page = [], 0
    while True:
        status, a = ask(client, v, page, admin)
        assert status == 200, a
        rows += a["rows"]
        if page >= a["page"]["last"]:
            return a, rows
        page += 1


# ═════════════════════════════════════════════════════════════════════════
# AC5 — boards against SQL written by hand (LEFT JOIN, COUNT(c.key))
# ═════════════════════════════════════════════════════════════════════════

_SITES_BY_SITE = """
SELECT t.data ->> 'name', COUNT(s.key),
       SUM(CASE WHEN s.data ->> 'kind' = 'pump' THEN 1 ELSE 0 END),
       COALESCE(ROUND(100.0 * SUM(CASE WHEN s.data ->> 'kind' = 'pump' THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(s.key), 0), 1), 0.0),
       MIN(s.data ->> 'installed')
  FROM demo.records t
  LEFT JOIN demo.records s ON s.collection = 'noun:Sender' AND s.data ->> 'site' = t.data ->> 'name'
 WHERE t.collection = 'noun:Site' {where}
 GROUP BY 1 ORDER BY 1
"""

_PUMPS = count("Pumps", cond("kind", "eq", value="pump"), pct=True)


@pytest.mark.parametrize("where, conditions", [
    ("", []),
    ("AND (t.data ->> 'capacity')::numeric > 15", [cond("capacity", "gt", value=15)]),
])
def test_sites_counting_senders_by_site_equals_hand_written_sql(client, conn, where, conditions):
    want = [[n, f"{k:,}", f"{p:,}", f"{pct}%", None if first is None else first]
            for n, k, p, pct, first in conn.execute(_SITES_BY_SITE.format(where=where)).fetchall()]
    v = board("sites", "name", SITES_SENDERS, conditions, counts=[_PUMPS],
              time={"fn": "earliest", "field": "installed"})
    a, rows = every_row(client, v)
    assert a["admin"]["verdict"] == "agree"
    # the earliest Installed is a date: the screen writes it its own way, so
    # compare only that it is present exactly where the hand-written SQL has one
    assert [r[:4] for r in rows] == [w[:4] for w in want]
    assert [r[4] is None for r in rows] == [w[4] is None for w in want]
    if not conditions:
        assert {r[0]: r[1:4] for r in rows}["Quarry"] == ["0", "0", "0.0%"]


_SENDERS_BY_SITE_BEATS = """
SELECT s.data ->> 'site', COUNT(h.key),
       SUM(CASE WHEN h.data ->> 'status' = 'error' THEN 1 ELSE 0 END)
  FROM demo.records s
  LEFT JOIN demo.records h ON h.collection = 'noun:Heartbeat' AND h.data ->> 'sender_id' = s.data ->> 'id'
 WHERE s.collection = 'noun:Sender' AND s.data ->> 'kind' = 'pump'
 GROUP BY 1 ORDER BY 1
"""


def test_senders_per_site_counting_heartbeats_with_a_page_condition(client, conn):
    want = [[site, f"{n:,}", f"{e:,}"] for site, n, e in conn.execute(_SENDERS_BY_SITE_BEATS).fetchall()]
    v = board("senders", "site", SENDERS_HEARTBEATS, [cond("kind", "eq", value="pump")],
              counts=[count("Errors", cond("status", "eq", value="error"))])
    a, rows = every_row(client, v)
    assert a["admin"]["verdict"] == "agree" and rows == want
    assert a["sentence"] == "Senders per Site where Kind is pump, counting their Heartbeats — 4 sites"


def test_t74s_board_built_by_choosing_the_match_is_t74s_board(client):
    """Outcome step 3: Senders counting Heartbeats, matched by Heartbeats'
    Sender = this Sender — the same numbers and sentence as T-74's
    declared relation (all 55 senders, hb-51 … hb-55 at 0 / 0.0%)."""
    ok = count("OK", cond("status", "eq", value="ok"), pct=True)
    by_hand = board("senders", "id", SENDERS_HEARTBEATS, counts=[ok])
    declared = board("senders", "id", "heartbeats", counts=[ok])
    a1, r1 = every_row(client, by_hand)
    a2, r2 = every_row(client, declared)
    assert r1 == r2 and len(r1) == 55
    assert a1["sentence"] == a2["sentence"] == "Senders, counting their Heartbeats — 55 senders"
    assert [r[1:4] for r in r1 if r[0] >= "hb-51"] == [["0", "0", "0.0%"]] * 5


def test_the_second_engine_keeps_a_parent_with_no_match(conn, setup):
    """T-77 item 9's trigger: the second engine's OWN join must keep Quarry —
    a source-level inner join there is killed here, before any comparison."""
    spec, _ = dashboard.to_spec(setup, board("sites", "name", SITES_SENDERS))
    got = {r["grp"]: r["rows"] for r in pygroup.python_pane(conn, spec)["rows"]}
    assert got == {"East": 15, "North": 8, "Quarry": 0, "South": 19, "West": 13}


def test_admin_sees_the_join_and_the_match(client):
    _, a = ask(client, board("sites", "name", SITES_SENDERS))
    sql = a["admin"]["statement"]
    assert "LEFT JOIN demo.records AS c" in sql
    assert """jsonb_typeof( c.data #> '{"site"}'::text[] ) = 'string'""" in sql
    assert """( c.data #> '{"site"}'::text[] ) = ( r.data #> '{"name"}'::text[] )""" in sql
    assert "The match: Senders' Site = Sites' Name." in a["admin"]["notes"]


# ═════════════════════════════════════════════════════════════════════════
# AC3 — the preview, and its numbers against hand-written SQL
# ═════════════════════════════════════════════════════════════════════════

_PROFILE_BY_HAND = """
WITH p AS (SELECT key, data -> {pk} AS v FROM demo.records WHERE collection = %(p)s {where}),
     c AS (SELECT key, data -> {ck} AS v FROM demo.records WHERE collection = %(c)s),
     m AS (SELECT p.key AS pk, c.key AS ck FROM p JOIN c
             ON jsonb_typeof(c.v) IN ('string', 'number') AND c.v = p.v),
     np AS (SELECT p.key, (SELECT count(*) FROM m WHERE m.pk = p.key) AS n FROM p),
     nc AS (SELECT c.key, (SELECT count(*) FROM m WHERE m.ck = c.key) AS n FROM c)
SELECT (SELECT count(*) FROM np), (SELECT count(*) FROM np WHERE n = 0),
       (SELECT min(n) FROM np WHERE n > 0), (SELECT max(n) FROM np WHERE n > 0),
       (SELECT count(*) FROM nc), (SELECT count(*) FROM nc WHERE n = 0),
       (SELECT count(*) FROM nc WHERE n > 1), (SELECT max(n) FROM nc WHERE n > 0)
"""


@pytest.mark.parametrize("parent, pk, counted, ck, where, view", [
    ("noun:Site", "'name'", "noun:Sender", "'site'", "",
     board("sites", "name", SITES_SENDERS)),
    ("noun:Sender", "'site'", "noun:Site", "'name'", "",
     board("senders", "id", SENDERS_SITES)),
    ("noun:Sender", "'id'", "noun:Heartbeat", "'sender_id'", "AND data ->> 'kind' = 'meter'",
     board("senders", "id", SENDERS_HEARTBEATS, [cond("kind", "eq", value="meter")])),
    ("noun:Sample", "'priority'", "noun:Heartbeat", "'payload'", "",
     board("samples", "status", {"dataset": "heartbeats", "field": "payload.load", "matches": "priority"})),
])
def test_the_profile_equals_hand_written_sql_in_both_engines(conn, setup, parent, pk, counted, ck, where, view):
    sql = _PROFILE_BY_HAND.format(pk=pk, ck=ck, where=where)
    if ck == "'payload'":   # a dotted path: payload.load
        sql = sql.replace("data -> 'payload'", "data #> '{payload,load}'")
    want = list(conn.execute(sql, {"p": parent, "c": counted}).fetchone())
    spec, _ = dashboard.to_spec(setup, view)
    sql_row = server_app.sql_pane(conn, group.build_profile(spec))["rows"][0]
    py_row = pygroup.python_profile(conn, spec)
    assert [sql_row[c] for c in group.PROFILE_COLUMNS] == want
    assert [py_row[c] for c in group.PROFILE_COLUMNS] == want


@pytest.mark.parametrize("view, line", [
    (board("sites", "name", SITES_SENDERS),
     "4 sites match 8 to 19 senders each; 1 site matches none. Every sender is counted."),
    (board("senders", "id", SENDERS_HEARTBEATS),
     "50 senders match 168 heartbeats each; 5 senders match none. Every heartbeat is counted."),
    (board("sites", "name", SITES_SENDERS, [cond("name", "eq", value="North")]),
     "1 site matches 8 senders. 47 senders match no site kept here and aren't counted."),
    (board("sites", "name", {"dataset": "senders", "field": "name", "matches": "name"}),
     "No site matches any sender, so every count is 0."),
])
def test_the_preview_says_what_the_match_does(client, view, line):
    status, a = ask(client, view)
    assert status == 200 and a["kind"] == "scoreboard"
    assert a["match"] == {"preview": line, "refused": False}


# ═════════════════════════════════════════════════════════════════════════
# AC4 — never count a row twice
# ═════════════════════════════════════════════════════════════════════════

def test_senders_counting_sites_is_refused_with_its_numbers(client):
    """Outcome step 2: each site would be counted under every sender at it."""
    status, a = ask(client, board("senders", "id", SENDERS_SITES))
    assert status == 200 and a["kind"] == "refused" and "rows" not in a
    assert a["message"] == (
        "Each site would be counted once for every sender that matches it — up to 19 times, "
        "for 4 of the 5 sites — and a row is counted only once. "
        "Count it the other way round: Sites, counting their Senders.")
    assert a["match"] == {"preview": None, "refused": True}
    # Admin reads the profile statement that was sent, not a board
    assert a["admin"]["sent"] is True and "per_c" in a["admin"]["statement"]


def test_one_row_counted_three_times_is_refused(client):
    """The edge, from below (S16 check, mutant S1): ONE counted row matching
    more than one kept parent is already a refusal — here three North
    senders kept, and the North site would be counted under each."""
    v = board("senders", "id", SENDERS_SITES, [cond("id", "in", values=["hb-07", "hb-11", "hb-27"])])
    status, a = ask(client, v)
    assert status == 200 and a["kind"] == "refused" and "rows" not in a
    assert a["message"] == (
        "Each site would be counted once for every sender that matches it — up to 3 times, "
        "for 1 of the 5 sites — and a row is counted only once. "
        "Count it the other way round: Sites, counting their Senders.")


def test_a_row_matching_exactly_two_parents_is_refused(client, conn, setup):
    """The edge, from the side (S16 check, mutant S6): a row matching TWO kept
    parents is counted twice — East and West both have Capacity 18, so each
    heartbeat with Load 18 would be counted under both. Both engines' profiles
    say so, and the pick is refused with the numbers, never drawn."""
    load = {"dataset": "heartbeats", "field": "payload.load", "matches": "capacity"}
    status, a = ask(client, board("sites", "name", load))
    assert status == 200 and a["kind"] == "refused" and "rows" not in a
    assert a["message"] == (
        "Each heartbeat would be counted once for every site that matches it — up to 2 times, "
        "for 120 of the 8,400 heartbeats — and a row is counted only once.")
    spec, _ = dashboard.to_spec(setup, board("sites", "name", load))
    sql = server_app.sql_pane(conn, group.build_profile(spec))["rows"][0]
    py = pygroup.python_profile(conn, spec)
    for prof in (sql, py):
        assert (prof["counted_twice"], prof["most_parents"]) == (120, 2)


def test_heartbeats_counting_senders_is_refused_too(client):
    status, a = ask(client, board("heartbeats", "status",
                                  {"dataset": "senders", "field": "id", "matches": "sender_id"}))
    assert a["kind"] == "refused" and a["message"].startswith(
        "Each sender would be counted once for every heartbeat that matches it — up to 168 times, "
        "for 50 of the 55 senders —")


def test_a_page_condition_can_make_a_refused_match_legal(client):
    """The check reads the KEPT parents: one sender per site kept, and each
    site matches at most one of them — legal, and correct."""
    one_each = [_SENDERS[i]["id"] for i in range(len(_SENDERS))
                if _SENDERS[i]["site"] not in {s["site"] for s in _SENDERS[:i]}]
    assert len(one_each) == 4
    v = board("senders", "id", SENDERS_SITES, [cond("id", "in", values=one_each)])
    status, a = ask(client, v)
    assert status == 200 and a["kind"] == "scoreboard", a.get("message")
    assert {r[0]: r[1] for r in a["rows"]} == {k: "1" for k in one_each}
    assert a["match"]["preview"] == "4 senders match 1 site each. 1 site matches no sender kept here and isn't counted."


def test_blank_parents_never_trigger_the_check(wconn, monkeypatch):
    """Two parents whose match value is blank (null, missing) must not count
    as both matching a blank counted row."""
    rows = {"P": [{"k": "p1", "s": None}, {"k": "p2"}, {"k": "p3", "s": "x"}],
            "C": [{"t": None}, {}, {"t": "x"}]}
    with _fixture(wconn, monkeypatch, rows):
        spec = _fixture_spec("string")
        for prof in _profiles(wconn, spec):
            assert prof["counted_twice"] == 0 and prof["parents_none"] == 2 and prof["counted_none"] == 2


def test_a_second_engine_that_fails_counts_nothing_in_words(client, monkeypatch):
    """S16 check, LOW: the second engine's profile throwing is "couldn't be
    double-checked", like a disagreement — never a 500."""
    def broken(rows, spec, related_rows):
        raise RuntimeError("profile broke")

    monkeypatch.setattr(pygroup, "profile", broken)
    dashboard._CACHE.clear()
    try:
        status, a = ask(client, board("sites", "name", {"dataset": "senders", "field": "kind", "matches": "name"}))
    finally:
        dashboard._CACHE.clear()
    assert status == 200 and a["kind"] == "refused" and a["message"] == dashboard.MATCH_UNCHECKED
    assert any("second engine could not profile the match (RuntimeError: profile broke)" in n
               for n in a["admin"]["notes"])


def test_engines_that_disagree_on_the_match_count_nothing(client, monkeypatch):
    real = pygroup.profile

    def off_by_one(rows, spec, related_rows):
        out = dict(real(rows, spec, related_rows))
        out["counted_none"] += 1
        return out

    monkeypatch.setattr(pygroup, "profile", off_by_one)
    dashboard._CACHE.clear()
    try:
        status, a = ask(client, board("sites", "name", {"dataset": "senders", "field": "kind", "matches": "name"}))
    finally:
        dashboard._CACHE.clear()
    assert status == 200 and a["kind"] == "refused" and a["message"] == dashboard.MATCH_UNCHECKED
    assert any("disagree on what the match does" in n for n in a["admin"]["notes"])


# ═════════════════════════════════════════════════════════════════════════
# The match rule, in both engines, on fixtures the seed has no case of
# ═════════════════════════════════════════════════════════════════════════

_P, _C = "scratch:MatchParent", "scratch:MatchCounted"


class _fixture:
    def __init__(self, conn, monkeypatch, rows):
        self.conn, self.monkeypatch, self.rows = conn, monkeypatch, rows

    def __enter__(self):
        self.monkeypatch.setitem(legality.SOURCES, _P, "k, v, s")
        self.monkeypatch.setitem(legality.SOURCES, _C, "w, t")
        for coll, name in ((_P, "P"), (_C, "C")):
            for i, data in enumerate(self.rows[name]):
                # raw JSON text, so 1e400 and 2.0 reach jsonb exactly as written
                text = data if isinstance(data, str) else json.dumps(data)
                self.conn.execute("INSERT INTO demo.records (collection, key, data) VALUES (%s, %s, %s::jsonb)",
                                  (coll, f"{name.lower()}{i + 1:02d}", text))
        return self

    def __exit__(self, *exc):
        self.conn.rollback()
        return False


def _fixture_spec(match):
    key, parent_key = ("t", "s") if match == "string" else ("w", "v")
    return {"source": _P, "group": "k", "filter": None, "counts": [], "time": None, "measure": None,
            "sort": None, "cap": None,
            "related": {"source": _C, "key": key if match == "string" else "w",
                        "parent_key": parent_key if match == "string" else "v", "match": match}}


def _profiles(conn, spec):
    sql = server_app.sql_pane(conn, group.build_profile(spec))["rows"][0]
    py = pygroup.profile(read_rows(conn, _P), spec, read_rows(conn, _C))
    return [dict(sql), py]


def _boards(conn, spec):
    sql = {json.loads(r["grp"]) if isinstance(r["grp"], str) and r["grp"].startswith('"') else r["grp"]: r["rows"]
           for r in server_app.sql_pane(conn, group.build(spec))["rows"]}
    py = {r["grp"]: r["rows"] for r in pygroup.answer(read_rows(conn, _P), spec, read_rows(conn, _C))["rows"]}
    return [sql, py]


# Each parent names itself (k) and holds one value (v); each counted row one (w).
_NUMBERS = {
    "P": ['{"k":"two","v":2}', '{"k":"text2","v":"2"}', '{"k":"null","v":null}', '{"k":"missing"}',
          '{"k":"true","v":true}', '{"k":"big","v":9007199254740993}', '{"k":"list","v":[2]}',
          '{"k":"huge","v":1e400}', '{"k":"one","v":1}'],
    "C": ['{"w":2.0}', '{"w":"2"}', '{"w":null}', '{}', '{"w":true}', '{"w":9007199254740992}',
          '{"w":[2]}', '{"w":1E+400}', '{"w":1.0}'],
}
#: Written by the rule, not by either engine: 2 = 2.0, 1e400 = 1E+400, 1 = 1.0;
#: "2" is text, null / missing / a list match nothing, true is not 1, and
#: 9007199254740993 is not 9007199254740992.
_NUMBERS_WANT = {"two": 1, "text2": 0, "null": 0, "missing": 0, "true": 0, "big": 0, "list": 0,
                 "huge": 1, "one": 1}


def test_numbers_match_by_value_exactly_and_never_across_kinds(wconn, monkeypatch):
    with _fixture(wconn, monkeypatch, _NUMBERS):
        spec = _fixture_spec("number")
        sql, py = _boards(wconn, spec)
        assert sql == py == _NUMBERS_WANT
        for prof in _profiles(wconn, spec):
            assert (prof["counted_none"], prof["counted_twice"]) == (6, 0)


_TEXT = {
    "P": [{"k": "a", "s": "North"}, {"k": "b", "s": "north"}, {"k": "c", "s": " North"}, {"k": "d", "s": 7},
          {"k": "e", "s": None}],
    "C": [{"t": "North"}, {"t": "North"}, {"t": "NORTH"}, {"t": 7}, {"t": "7"}, {"t": None}],
}


def test_text_matches_text_exactly(wconn, monkeypatch):
    with _fixture(wconn, monkeypatch, _TEXT):
        spec = _fixture_spec("string")
        sql, py = _boards(wconn, spec)
        assert sql == py == {"a": 2, "b": 0, "c": 0, "d": 0, "e": 0}


# ═════════════════════════════════════════════════════════════════════════
# The probe split (T-77 item 8): counts probed over the COUNTED data set,
# the page filter over the PARENT — killed by Edge cases' huge numbers
# ═════════════════════════════════════════════════════════════════════════

_HUGE = count("Big", cond("huge", "gt", value=5))


def test_k1_a_count_over_edge_cases_is_probed_over_edge_cases(client):
    status, a = ask(client, board("sites", "name", {"dataset": "edge", "field": "txt", "matches": "name"},
                                  counts=[_HUGE]))
    assert status == 200 and a["kind"] == "refused"
    assert a["message"].startswith("One of these values is too large to compute with")
    assert a["admin"]["sent"] is False and 'by key: "edge-03"' in a["admin"]["refusal"]["why"]


def test_k2_a_page_filter_on_edge_cases_is_probed_over_edge_cases(client):
    status, a = ask(client, board("edge", "a", {"dataset": "sites", "field": "name", "matches": "txt"},
                                  [cond("huge", "gt", value=5)]))
    assert status == 200 and a["kind"] == "refused"
    assert a["admin"]["sent"] is False and 'by key: "edge-03"' in a["admin"]["refusal"]["why"]


# ═════════════════════════════════════════════════════════════════════════
# AC8 — the gate refuses every pick the screen can't make, by name
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("count_from, says", [
    ({"dataset": "nowhere", "field": "site", "matches": "name"}, "There's no data set called “nowhere” to count from."),
    ({"dataset": ["senders"], "field": "site", "matches": "name"}, "There's no data set by that name to count from."),
    ({"dataset": "senders", "field": 7, "matches": "name"}, "Senders has no field by that name to match on."),
    ({"dataset": "senders", "field": "site", "matches": ""}, "Sites has no field by that name to match on."),
    ({"dataset": "sites", "field": "name", "matches": "name"}, "A data set can't be matched with itself."),
    ({"dataset": "senders", "field": "postcode", "matches": "name"}, "Senders has no field “postcode” to match on."),
    ({"dataset": "senders", "field": "site", "matches": "town"}, "Sites has no field “town” to match on."),
    ({"dataset": "senders", "field": "site", "matches": "capacity"},
     "Capacity holds numbers and Site holds text; a match pairs two fields of the same kind."),
    ({"dataset": "senders", "field": "installed", "matches": "name"},
     "Name holds text and Installed holds dates; a match pairs two fields of the same kind."),
    ({"dataset": "edge", "field": "tags", "matches": "name"}, "Tags holds lists or mixed values, which can't be matched."),
    ({"dataset": "senders", "field": "site"}, None),
    ({"dataset": "senders", "field": "site", "matches": "name", "how": "loosely"}, None),
    (["senders"], "Count from must name a data set and the two fields that match."),
    (7, "Count from must name a data set and the two fields that match."),
    ("samples", "Sites has no related data set to count from by that name."),
])
def test_the_gate_refuses_by_name(client, count_from, says):
    status, a = ask(client, board("sites", "name", count_from))
    assert status == 422, a
    if says is not None:
        assert a["message"] == says
    else:
        assert a["message"]


def test_the_setup_says_which_kinds_a_match_may_pair(setup):
    """S17: the page offers only pairs of one kind, from the gate's own table."""
    assert setup["match_kinds"] == ["text", "date", "time", "number"]
    sites = next(d for d in setup["datasets"] if d["id"] == "sites")
    assert sites["count_from"] == [{"id": "senders", "name": "Senders", "field": "site", "matches": "name"}]


def test_everyone_never_matches_on_a_hidden_field(client):
    v = board("sites", "name", {"dataset": "edge", "field": "label", "matches": "name"})
    status, a = ask(client, v, admin=False)
    assert status == 422 and a["message"] == "Label isn't offered in this view."
    status, a = ask(client, v, admin=True)
    assert status == 200


@pytest.mark.parametrize("patch", [
    {"columns": ["label"]},
    {"conditions": [cond("label", "present")]},
    {"sort": {"field": "label", "dir": "asc"}},
    {"scoreboard": {"by": "label", "count_from": None, "counts": [], "time": None, "measure": None, "sort": None},
     "columns": []},
])
def test_everyone_never_names_a_hidden_field_anywhere(client, patch):
    v = {"dataset": "edge", "columns": ["a"], "conditions": [], "logic": "all", "sort": None, "show": None,
         "summary": None, "scoreboard": None, **patch}
    assert ask(client, v, admin=False)[0] == 422
    assert ask(client, v, admin=False)[1]["message"] == "Label isn't offered in this view."
    assert ask(client, v, admin=True)[0] == 200


def test_everyone_never_counts_on_a_hidden_field(client):
    v = board("sites", "name", {"dataset": "edge", "field": "txt", "matches": "name"},
              counts=[count("Lab", cond("label", "present"))])
    assert ask(client, v, admin=False)[1]["message"] == "Label isn't offered in this view."


def test_no_hand_built_match_is_a_500(client):
    odd = [None, 0, True, "", [], {}, {"dataset": None}, {"dataset": "senders"},
           {"dataset": "senders", "field": None, "matches": None},
           {"dataset": "senders", "field": ["site"], "matches": {"a": 1}},
           {"dataset": "senders", "field": "site\x00", "matches": "name"},
           {"dataset": "heartbeats", "field": "payload", "matches": "capacity"},
           {"dataset": "heartbeats", "field": "ts", "matches": "opened"},
           {"dataset": "senders", "field": "site", "matches": "name", "dataset2": 1}]
    for cf in odd:
        status, a = ask(client, board("sites", "name", cf))
        assert status in (200, 422), (cf, status, a)


# ═════════════════════════════════════════════════════════════════════════
# AC9 — the sentence names the match unless it is the declared one
# ═════════════════════════════════════════════════════════════════════════

def test_a_chosen_match_names_its_field(client):
    _, a = ask(client, board("sites", "name", {"dataset": "senders", "field": "name", "matches": "name"}))
    assert a["sentence"] == "Sites, counting their Senders (by Name) — 5 sites"
    _, a = ask(client, board("sites", "name", SITES_SENDERS))
    assert a["sentence"] == "Sites, counting their Senders — 5 sites"


# ═════════════════════════════════════════════════════════════════════════
# The S13 check's MEDIUM: names compared with whitespace collapsed
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name", ["Latest  Time", "Latest Time", "Latest Time", "latest \u2002 time"])
def test_a_derived_header_name_is_refused_whatever_its_spaces(client, name):
    v = board("senders", "id", "heartbeats", counts=[count(name, cond("status", "eq", value="ok"))],
              time={"fn": "latest", "field": "ts"})
    status, a = ask(client, v)
    assert status == 422 and "is already a column on this board" in a["message"]


def test_a_percent_header_is_refused_with_a_no_break_space(client):
    v = board("senders", "id", "heartbeats", counts=[count("OK", cond("status", "eq", value="ok"), pct=True),
                                                     count("% OK", cond("status", "eq", value="warn"))])
    status, a = ask(client, v)
    assert status == 422 and "is already a column on this board" in a["message"]


def test_two_counts_are_one_name_whatever_their_spaces(client):
    v = board("senders", "id", "heartbeats", counts=[count("Big hit", cond("status", "eq", value="ok")),
                                                     count("Big  hit", cond("status", "eq", value="warn"))])
    status, a = ask(client, v)
    assert status == 422 and a["message"] == "Two count columns are both called “Big  hit”."
