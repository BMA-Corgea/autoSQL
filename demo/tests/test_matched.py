"""demo/tests/test_matched.py — T-78 S19, matched fields in tables (a SAFETY slice).

Every number here is checked against something that is neither engine:
hand-written SQL typed out in this file — ``->>`` text compared as text with
both sides' JSON type checked, numbers cast to ``numeric`` — not produced by
``demo/lookup.py``, run on the demo's read-only connection; and fixture rows
whose answer is written down by the rule.

The rule (T-76's match, unchanged): one field of the table paired with one of
the other data set, same kind; text exactly, numbers by value, never across
kinds, a blank matches nothing.  A row with no match keeps its place with
blanks; a kept row matching MORE THAN ONE row is refused (it would repeat),
over the kept rows — conditions apply, Show and paging do not.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for _p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard, db, matched  # noqa: E402

import demo.legality as demo_legality  # noqa: E402
import legality  # noqa: E402
import lookup  # noqa: E402
from pyrunner import lookup as pylookup  # noqa: E402
from pyrunner.rows import read_rows  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    return client.get("/api/dashboard/setup?view=admin").json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-matched-test")
    server_app.refuse_writes(c)
    yield c
    c.close()


@pytest.fixture
def wconn():
    """A connection that may write — only ever inside a transaction this
    file rolls back."""
    c = db.connect(application_name="autosql-demo-matched-fixture")
    yield c
    c.rollback()
    c.close()


def ask(client, v, page=0, *, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page, "admin": admin})
    return r.status_code, r.json()


def table(ds_id="heartbeats", columns=("sender_id",), conditions=(), sort=None, show=None, matched=None):
    v = {"dataset": ds_id, "columns": list(columns), "conditions": list(conditions), "sort": sort,
         "show": show, "summary": None}
    if matched is not None:
        v["matched"] = matched
    return v


def cond(field, op, **kw):
    return {"field": field, "op": op, **kw}


SENDER = {"dataset": "senders", "field": "id", "matches": "sender_id", "columns": ["name", "site"]}
SITE_BY_LOAD = {"dataset": "sites", "field": "capacity", "matches": "payload.load", "columns": ["name"]}
NOT_18 = cond("payload.load", "ne", value=18)


# ═════════════════════════════════════════════════════════════════════════
# The hand-written SQL — neither engine
# ═════════════════════════════════════════════════════════════════════════

def hand_sql(conn, sql, params=None):
    return conn.execute(sql, params or {}).fetchall()


#: Each heartbeat → its sender's name and site, by text: both sides strings.
_HB_SENDER_SQL = """
SELECT h.key, s.data ->> 'name', s.data ->> 'site'
  FROM demo.records h
  LEFT JOIN demo.records s
    ON s.collection = 'noun:Sender'
   AND jsonb_typeof(s.data -> 'id') = 'string'
   AND jsonb_typeof(h.data -> 'sender_id') = 'string'
   AND s.data ->> 'id' = h.data ->> 'sender_id'
 WHERE h.collection = 'noun:Heartbeat'
"""

#: Each heartbeat → every site whose capacity equals its load, by numeric value.
_HB_SITE_SQL = """
SELECT h.key, (h.data #>> '{payload,load}')::numeric AS load, t.data ->> 'name' AS site
  FROM demo.records h
  LEFT JOIN demo.records t
    ON t.collection = 'noun:Site'
   AND jsonb_typeof(t.data -> 'capacity') = 'number'
   AND jsonb_typeof(h.data #> '{payload,load}') = 'number'
   AND (t.data ->> 'capacity')::numeric = (h.data #>> '{payload,load}')::numeric
 WHERE h.collection = 'noun:Heartbeat'
"""

#: The repeat edge, counted by hand: per heartbeat, how many sites match.
_HB_SITE_PER_ROW_SQL = """
SELECT n, count(*) FROM (
  SELECT h.key, count(t.key) AS n
    FROM demo.records h
    LEFT JOIN demo.records t
      ON t.collection = 'noun:Site'
     AND jsonb_typeof(t.data -> 'capacity') = 'number'
     AND jsonb_typeof(h.data #> '{payload,load}') = 'number'
     AND (t.data ->> 'capacity')::numeric = (h.data #>> '{payload,load}')::numeric
   WHERE h.collection = 'noun:Heartbeat' %(extra)s
   GROUP BY h.key) x
 GROUP BY n ORDER BY n
"""


def _per_row(conn, extra=""):
    return dict(conn.execute(_HB_SITE_PER_ROW_SQL % {"extra": extra}).fetchall())


def _whole(client, v, admin=True):
    """Every page of a table answer, as (columns, rows)."""
    status, a = ask(client, v, admin=admin)
    assert status == 200 and a["kind"] == "table", a
    rows = list(a["rows"])
    for p in range(1, a["page"]["last"] + 1):
        rows += ask(client, v, p, admin=admin)[1]["rows"]
    return a, rows


# ═════════════════════════════════════════════════════════════════════════
# 1 · The outcome check's pick: each heartbeat with its sender's name and site
# ═════════════════════════════════════════════════════════════════════════

def test_each_heartbeat_with_its_senders_name_and_site_equals_hand_written_sql(client, conn):
    want = {k: (name, site) for k, name, site in hand_sql(conn, _HB_SENDER_SQL)}
    assert len(want) == 8400 and all(n is not None for n, _ in want.values())
    pick = dashboard.to_pick(dashboard.setup(conn), table(columns=["sender_id", "ts"]))
    spec, _ = dashboard.to_lookup(dashboard.setup(conn), table(columns=["sender_id", "ts"], matched=SENDER))
    r = matched.run_lookup(conn, pick, spec)
    assert r["accepted"] and r["verdict"] == "agree", r.get("refusal")
    cols = r["panes"]["sql"]["columns"]
    got = {row["c"][cols.index("key")]: (row["c"][cols.index("Sender_s_Name")], row["c"][cols.index("Sender_s_Site")])
           for row in r["panes"]["sql"]["rows"]}
    assert got == want


def test_the_answer_on_screen_matches_too_every_page(client, conn):
    v = table(columns=["sender_id", "ts"], sort={"field": "ts", "dir": "desc"}, matched=SENDER)
    a, rows = _whole(client, v)
    assert a["sentence"] == "Heartbeats, newest first, with each one's Sender: Name and Site — 8,400 rows"
    assert [c["label"] for c in a["columns"]] == ["Sender", "Time", "Sender's Name", "Sender's Site"]
    assert a["match"] == {"preview": "Every heartbeat matches one sender.", "refused": False}
    names = {sid: (n, s) for sid, n, s in hand_sql(conn, "SELECT data->>'id', data->>'name', data->>'site' "
                                                     "FROM demo.records WHERE collection='noun:Sender'")}
    assert len(rows) == 8400 and all((r[2], r[3]) == names[r[0]] for r in rows)
    # and in the plain table's own order, row for row
    _, plain = _whole(client, table(columns=["sender_id", "ts"], sort={"field": "ts", "dir": "desc"}))
    assert [r[:2] for r in rows] == plain


def test_admin_sees_the_left_join_and_everyone_no_machinery(client):
    v = table(columns=["sender_id"], matched=SENDER)
    _, a = ask(client, v)
    st = a["admin"]["statement"]
    assert "LEFT JOIN demo.records AS m" in st and "m.collection = 'noun:Sender'" in st
    assert "( m.data #> '{\"id\"}'::text[] ) = ( r.data #> '{\"sender_id\"}'::text[] )" in st
    assert a["admin"]["verdict"] == "agree" and a["admin"]["sent"] is True
    assert "The match: Senders' Sender = Heartbeats' Sender." in a["admin"]["notes"]
    _, e = ask(client, v, admin=False)
    assert "admin" not in e
    text = json.dumps({k: e[k] for k in ("sentence", "columns", "match")})
    assert not re.search(r"\b(?:sql|join|engine|statement|python|query)\b", text, re.I), text


def test_senders_with_their_sites_fields(client, conn):
    v = table("senders", columns=["id", "site"], matched={"dataset": "sites", "field": "name", "matches": "site",
                                                         "columns": ["opened", "capacity"]})
    a, rows = _whole(client, v)
    assert a["sentence"] == "Senders, with each one's Site: Opened and Capacity — 55 rows"
    sites = {n: (o, c) for n, o, c in hand_sql(conn, "SELECT data->>'name', data->>'opened', data->>'capacity' "
                                                 "FROM demo.records WHERE collection='noun:Site'")}
    senders = dict(hand_sql(conn, "SELECT data->>'id', data->>'site' FROM demo.records WHERE collection='noun:Sender'"))
    assert len(rows) == 55
    for sid, site, opened, cap in rows:
        o, c = sites[senders[sid]]
        assert site == senders[sid] and opened == dashboard.fmt_date(o) and cap == c


def test_the_tables_open_on_the_declared_relation_read_backwards(setup):
    by = {d["id"]: d["lookups"] for d in setup["datasets"]}
    assert by["heartbeats"] == [{"id": "senders", "field": "id", "matches": "sender_id", "name": "Senders"}]
    assert by["senders"] == [{"id": "sites", "field": "name", "matches": "site", "name": "Sites"}]
    assert by["samples"] == by["edge"] == by["sites"] == []


# ═════════════════════════════════════════════════════════════════════════
# 2 · Never repeat a row: the refusal, at its exact edge, over the kept rows
# ═════════════════════════════════════════════════════════════════════════

def test_a_row_matching_exactly_two_is_refused_with_hand_written_numbers(client, conn):
    per = _per_row(conn)
    # the seed's own edge: East and West both hold capacity 18
    assert per == {0: 7892, 1: 388, 2: 120}
    status, a = ask(client, table(columns=["sender_id", "payload.load"], matched=SITE_BY_LOAD))
    assert status == 200 and a["kind"] == "refused"
    assert a["message"] == (f"Each heartbeat would be shown once for every site that matches it — up to "
                            f"{max(per)} times, for {per[2]} of the 8,400 heartbeats — and a row is shown only once.")
    assert a["match"] == {"preview": None, "refused": True}
    assert "rows" not in a and "columns" not in a
    assert a["admin"]["verdict"] == "no-compare" and a["admin"]["unchecked"] == _REPEAT_AGREED


def test_exactly_one_match_is_shown(client, conn):
    v = table(columns=["sender_id", "payload.load"], conditions=[cond("payload.load", "eq", value=18)],
              matched={"dataset": "sites", "field": "capacity", "matches": "payload.load", "columns": ["name"]})
    status, a = ask(client, v)
    assert a["kind"] == "refused", "every load-18 heartbeat matches two sites"
    v = dict(v, conditions=[cond("payload.load", "eq", value=10)])
    a, rows = _whole(client, v)
    assert a["total"] == 142 == _per_row(conn, "AND (h.data #>> '{payload,load}')::numeric = 10")[1]
    assert {r[2] for r in rows} == {"North"}
    assert a["match"]["preview"] == "Every heartbeat matches one site."


def test_a_condition_makes_the_refused_pick_legal_with_blanks_that_stay(client, conn):
    v = table(columns=["sender_id", "payload.load"], conditions=[NOT_18], matched=SITE_BY_LOAD)
    a, rows = _whole(client, v)
    # by hand: "is not 18" keeps a row without a load too (the page's reading of is not)
    want = {}
    for k, load, site in hand_sql(conn, _HB_SITE_SQL):
        if load is None or load != 18:
            want[k] = site
    assert a["total"] == len(want) == 8280 and len(rows) == 8280
    assert sum(1 for s in want.values() if s is None) == 7892
    assert a["match"]["preview"] == "388 heartbeats match one site; 7,892 match none, so their site fields are blank."
    assert sorted(r[2] for r in rows if r[2] is not None) == sorted(s for s in want.values() if s is not None)
    assert sum(1 for r in rows if r[2] is None) == 7892
    assert a["sentence"] == ("Heartbeats where Load is not 18, with each one's Site: Name "
                             "(matched by Load = Capacity) — 8,280 rows")


@pytest.mark.parametrize("show, page, sort", [
    (25, 0, None),
    (25, 3, None),
    (None, 7, None),
    (25, 0, {"field": "payload.load", "dir": "asc"}),     # the first 25 are load 0: none repeats
])
def test_a_repeat_anywhere_refuses_whatever_page_or_show(client, show, page, sort):
    v = table(columns=["sender_id", "payload.load"], sort=sort, show=show, matched=SITE_BY_LOAD)
    status, a = ask(client, v, page)
    assert status == 200 and a["kind"] == "refused" and "up to 2 times, for 120 of the 8,400" in a["message"]


def test_the_row_count_is_always_the_plain_tables(client):
    for v in (table(columns=["sender_id"], conditions=[cond("status", "eq", value="warn")], matched=SENDER),
              table(columns=["sender_id"], show=100, sort={"field": "payload.load", "dir": "desc"}, matched=SENDER),
              table(columns=["sender_id", "payload.load"], conditions=[NOT_18], show=500, matched=SITE_BY_LOAD)):
        _, a = ask(client, v)
        _, p = ask(client, dict(v, matched=None))
        assert a["kind"] == p["kind"] == "table" and a["total"] == p["total"], (a["sentence"], p["sentence"])
        assert a["sentence"].split(" — ")[1] == p["sentence"].split(" — ")[1]


# ═════════════════════════════════════════════════════════════════════════
# 3 · The match rule, on fixtures the seed has no case of
# ═════════════════════════════════════════════════════════════════════════

_P, _C = "scratch:LookupTable", "scratch:LookupOther"


class _fixture:
    def __init__(self, conn, monkeypatch, rows):
        self.conn, self.monkeypatch, self.rows = conn, monkeypatch, rows

    def __enter__(self):
        # demo/ is not a package: the closed set is read through two module
        # objects (``legality`` and ``demo.legality``, pyrunner's); both open.
        for mod in {id(legality): legality, id(demo_legality): demo_legality}.values():
            self.monkeypatch.setitem(mod.SOURCES, _P, "k, v")
            self.monkeypatch.setitem(mod.SOURCES, _C, "w, x")
        for coll, name in ((_P, "P"), (_C, "C")):
            for i, data in enumerate(self.rows[name]):
                text = data if isinstance(data, str) else json.dumps(data)
                self.conn.execute("INSERT INTO demo.records (collection, key, data) VALUES (%s, %s, %s::jsonb)",
                                  (coll, f"{name.lower()}{i + 1:02d}", text))
        return self

    def __exit__(self, *exc):
        self.conn.rollback()
        return False


def _fx_pick(filter_=None):
    p = dict(legality.default_pick(), source=_P, computed=[{"name": "K", "expr": "$.k"}])
    if filter_:
        p["filter"] = filter_
    return p


def _fx_spec(match):
    return {"source": _C, "key": "w", "parent_key": "v", "match": match, "columns": [{"name": "X", "path": "x"}]}


def _both(conn, pick, spec):
    """(statement rows, second-engine rows), each as [(k, x)] in order."""
    keys = server_app.collection_keys(conn, _P)
    sql = server_app.sql_pane(conn, lookup.build(server_app.normalised_pick(pick), keys, spec))
    s = [(r["K"], r["X"]) for r in sql["rows"]]          # the exact-JSON cursor decodes
    py = pylookup.answer(read_rows(conn, _P), pick, read_rows(conn, _C), spec)
    p = [(r["K"], r["X"]) for r in py["rows"]]
    return s, p


def _profiles(conn, pick, spec):
    sql = server_app.sql_pane(conn, lookup.build_profile(pick, spec))["rows"][0]
    return dict(sql), pylookup.profile(read_rows(conn, _P), pick, read_rows(conn, _C), spec)


_NUMBERS = {
    "P": ['{"k":"two","v":2}', '{"k":"text2","v":"2"}', '{"k":"null","v":null}', '{"k":"missing"}',
          '{"k":"true","v":true}', '{"k":"big","v":9007199254740993}', '{"k":"list","v":[2]}',
          '{"k":"huge","v":1e400}', '{"k":"one","v":1}'],
    "C": ['{"w":2.0,"x":"A"}', '{"w":"2","x":"B"}', '{"w":null,"x":"C"}', '{"x":"D"}', '{"w":true,"x":"E"}',
          '{"w":9007199254740992,"x":"F"}', '{"w":[2],"x":"G"}', '{"w":1E+400,"x":"H"}', '{"w":1.0,"x":"I"}'],
}
#: Written by the rule: 2 = 2.0, 1e400 = 1E+400, 1 = 1.0; "2" is text, a null,
#: a missing value and a list match nothing — not even each other — true is
#: not 1, and 9007199254740993 is not 9007199254740992.
_NUMBERS_WANT = [("big", None), ("huge", "H"), ("list", None), ("missing", None), ("null", None),
                 ("one", "I"), ("text2", None), ("true", None), ("two", "A")]


def test_numbers_match_by_value_exactly_and_a_blank_matches_nothing(wconn, monkeypatch):
    with _fixture(wconn, monkeypatch, _NUMBERS):
        s, p = _both(wconn, _fx_pick(), _fx_spec("number"))
        assert sorted(s) == sorted(p) == _NUMBERS_WANT
        for prof in _profiles(wconn, _fx_pick(), _fx_spec("number")):
            assert prof == {"rows": 9, "rows_none": 6, "least": 1, "most": 1, "repeated": 0, "others": 9}


_TEXT = {
    "P": [{"k": "a", "v": "North"}, {"k": "b", "v": "north"}, {"k": "c", "v": " North"}, {"k": "d", "v": 7},
          {"k": "e", "v": None}, {"k": "f", "v": ""}],
    "C": [{"w": "North", "x": 1}, {"w": "NORTH", "x": 2}, {"w": 7, "x": 3}, {"w": "7", "x": 4},
          {"w": None, "x": 5}, {"w": "", "x": 6}],
}


def test_text_matches_text_exactly(wconn, monkeypatch):
    with _fixture(wconn, monkeypatch, _TEXT):
        s, p = _both(wconn, _fx_pick(), _fx_spec("string"))
        # case and spaces count; 7 is not "7"; null matches nothing; "" is text and matches ""
        assert sorted(s) == sorted(p) == [("a", 1), ("b", None), ("c", None), ("d", None), ("e", None), ("f", 6)]


_REPEAT = {
    "P": [{"k": "one", "v": "x"}, {"k": "two", "v": "y"}, {"k": "three", "v": "z"}, {"k": "none", "v": "q"}],
    "C": [{"w": "x", "x": 1}, {"w": "y", "x": 2}, {"w": "y", "x": 3}, {"w": "z", "x": 4}, {"w": "z", "x": 5},
          {"w": "z", "x": 6}],
}


def test_the_profile_counts_each_edge_in_both_engines(wconn, monkeypatch):
    with _fixture(wconn, monkeypatch, _REPEAT):
        for prof in _profiles(wconn, _fx_pick(), _fx_spec("string")):
            assert prof == {"rows": 4, "rows_none": 1, "least": 1, "most": 3, "repeated": 2, "others": 6}
        # kept rows only: leaving out "three" leaves one row matching exactly two
        for prof in _profiles(wconn, _fx_pick('$.k != "three"'), _fx_spec("string")):
            assert prof == {"rows": 3, "rows_none": 1, "least": 1, "most": 2, "repeated": 1, "others": 6}
        # and leaving out "two" too: nothing repeats
        for prof in _profiles(wconn, _fx_pick('$.k == "one" or $.k == "none"'), _fx_spec("string")):
            assert prof == {"rows": 2, "rows_none": 1, "least": 1, "most": 1, "repeated": 0, "others": 6}


def test_a_refused_pick_is_never_drawn_even_by_the_engine_below_the_gate(wconn, monkeypatch):
    """Below the profile, both engines would REPEAT the row (a LEFT JOIN does):
    the row-count invariant is what the profile guards."""
    with _fixture(wconn, monkeypatch, _REPEAT):
        s, p = _both(wconn, _fx_pick(), _fx_spec("string"))
        assert len(s) == len(p) == 1 + 2 + 3 + 1     # 4 table rows, drawn as 7
        r = matched.run_lookup(wconn, _fx_pick(), _fx_spec("string"))
        assert not r["accepted"] and r["refusal"]["kind"] == "repeat" and r["panes"] == {}


# ═════════════════════════════════════════════════════════════════════════
# 4 · Fail closed: the second engine disagreeing or failing shows nothing
# ═════════════════════════════════════════════════════════════════════════

def _clear():
    dashboard._CACHE.clear()


@pytest.mark.parametrize("target, how, message, note, line", [
    ("python_profile", "raise", dashboard.MATCH_FIELDS_UNCHECKED,
     "second engine could not profile the match (RuntimeError: broke)", dashboard.UNCHECKED_PROFILE),
    ("python_profile", "off-by-one", dashboard.MATCH_FIELDS_UNCHECKED, "disagree on what the match does",
     dashboard.UNCHECKED_MATCH),
    ("python_pane", "raise", dashboard.ANSWER_UNCHECKED,
     "second engine could not compute this answer (RuntimeError: broke)", dashboard.UNCHECKED_SECOND_ENGINE),
])
def test_the_second_engine_failing_shows_nothing_in_words(client, monkeypatch, target, how, message, note, line):
    real = getattr(pylookup, target)

    def fake(*a, **k):
        if how == "raise":
            raise RuntimeError("broke")
        out = dict(real(*a, **k))
        out["rows_none"] += 1
        return out

    monkeypatch.setattr(pylookup, target, fake)
    _clear()
    try:
        status, a = ask(client, table(columns=["sender_id"], matched=SENDER))
        status_e, e = ask(client, table(columns=["sender_id"], matched=SENDER), admin=False)
    finally:
        _clear()
    assert status == 200 and a["kind"] == "refused" and a["message"] == message
    assert "rows" not in a and any(note in n for n in a["admin"]["notes"]), a["admin"]["notes"]
    assert a["admin"]["unchecked"] == line
    assert status_e == 200 and e["kind"] == "refused" and "admin" not in e


def test_a_disagreeing_table_is_flagged_for_admin(client, monkeypatch):
    """A cell the engines disagree on is the T-71 AC6 rule's: Admin sees the
    verdict.  Here the second engine is made to read one sender wrong."""
    real = pylookup.answer

    def wrong(rows, pick, related, lk):
        out = real(rows, pick, related, lk)
        out["rows"][0] = dict(out["rows"][0], **{lk["columns"][0]["name"]: "Not the name"})
        return out

    monkeypatch.setattr(pylookup, "answer", wrong)
    _clear()
    try:
        _, a = ask(client, table(columns=["sender_id"], matched=SENDER))
    finally:
        _clear()
    assert a["admin"]["verdict"] == "disagree" and a["admin"]["differing_rows"] == 1


# ═════════════════════════════════════════════════════════════════════════
# 5 · The gate: every pick the screen can't make, a plain 422 by name
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("v, admin, message", [
    (table(matched={"dataset": "nope", "field": "id", "matches": "sender_id", "columns": ["name"]}), True,
     "There's no data set called “nope” to take fields from."),
    (table(matched={"dataset": "heartbeats", "field": "sender_id", "matches": "sender_id", "columns": ["status"]}),
     True, "A data set can't be matched with itself."),
    (table(matched={"dataset": "senders", "field": "nope", "matches": "sender_id", "columns": ["name"]}), True,
     "Senders has no field “nope” to match on."),
    (table(matched={"dataset": "senders", "field": "id", "matches": "nope", "columns": ["name"]}), True,
     "Heartbeats has no field “nope” to match on."),
    (table(matched={"dataset": "sites", "field": "capacity", "matches": "sender_id", "columns": ["name"]}), True,
     "Sender holds text and Capacity holds numbers; a match pairs two fields of the same kind."),
    (table("samples", ["id"], matched={"dataset": "edge", "field": "arr", "matches": "id", "columns": ["a"]}), True,
     "Arr holds lists or mixed values, which can't be matched."),
    (table("senders", ["id"], matched={"dataset": "edge", "field": "label", "matches": "name", "columns": ["a"]}),
     False, "Label isn't offered in this view."),
    (table("senders", ["id"], matched={"dataset": "edge", "field": "txt", "matches": "name", "columns": ["label"]}),
     False, "Label isn't offered in this view."),
    (table(matched=dict(SENDER, columns=[])), True, "Pick at least one of Senders' fields to show."),
    (table(matched=dict(SENDER, columns="name")), True, "Pick at least one of Senders' fields to show."),
    (table(matched=dict(SENDER, columns=[["name"]])), True, "The fields to show must be a list of field names."),
    (table(matched=dict(SENDER, columns=["name", "nope"])), True, "Senders has no field “nope” to show."),
    (table(matched=dict(SENDER, columns=["id", "name", "site", "kind", "installed", "id", "name"])), True,
     "Show at most 6 fields from Senders."),
    (table(matched=dict(SENDER, extra=1)), True, "This page can't use 'extra' in fields from another data set yet."),
    (table(matched=["senders"]), True,
     "Fields from another data set must name a data set, the two fields that match, and the fields to show."),
    (dict(table(matched=SENDER), columns=[], summary={"fn": "count", "field": None, "per": "all"}), True,
     dashboard.MATCHED_NEEDS_TABLE),
    (dict(table(matched=SENDER), columns=[], scoreboard={"by": "status", "counts": []}), True,
     dashboard.MATCHED_NEEDS_TABLE),
])
def test_the_gate_refuses_by_name(client, v, admin, message):
    status, a = ask(client, v, admin=admin)
    assert status == 422 and a["kind"] == "invalid" and a["message"] == message, a


def test_admin_may_match_and_show_label(client):
    v = table("senders", ["id"], matched={"dataset": "edge", "field": "txt", "matches": "name", "columns": ["label"]})
    status, a = ask(client, v)
    assert status == 200 and a["kind"] == "table" and a["columns"][-1]["label"] == "Edge case's Label"


_JUNK = [None, True, 0, -1, 1.5, "", " ", "x", "senders", "id", "name", "label", "payload.load", "$.id",
         [], ["name"], [None], {}, {"a": 1}, "\u0000", "na me", "x" * 500]


def test_hand_built_matches_never_500(client):
    rnd = random.Random(78)
    for _ in range(300):
        m = {k: rnd.choice(_JUNK) for k in ("dataset", "field", "matches", "columns") if rnd.random() < 0.85}
        if rnd.random() < 0.5:
            m.update(dataset=rnd.choice(["senders", "sites", "edge", "samples", "heartbeats"]))
        v = table(rnd.choice(["heartbeats", "senders", "edge"]), [], matched=m)
        status, a = ask(client, v, admin=rnd.random() < 0.5)
        assert status in (200, 422), (m, status, a)
        assert a["kind"] in ("table", "refused", "invalid"), (m, a)


def test_everyone_never_sees_a_hidden_field_from_another_data_set(client):
    v = table("senders", ["id"], matched={"dataset": "edge", "field": "txt", "matches": "name", "columns": ["a", "label"]})
    status, a = ask(client, v, admin=False)
    assert (status, a.get("message")) == (422, "Label isn't offered in this view."), a


_EDGE_SITES = {"dataset": "sites", "field": "name", "matches": "txt", "columns": ["capacity"]}


@pytest.mark.parametrize("c, why", [
    (cond("huge", "gt", value=5), None),          # refused by the probe, before any statement
    (cond("huge", "eq", value=0), "XPR01: "),     # refused by the runtime while the statement runs
], ids=["probe", "mid-run"])
def test_a_refused_table_is_refused_with_its_fields_too(client, c, why):
    _clear()
    v = table("edge", ["a"], conditions=[c], matched=_EDGE_SITES)
    status, a = ask(client, v)
    assert status == 200 and a["kind"] == "refused" and "rows" not in a
    assert a["message"] == "One of these values is too large to compute with, so this can't be answered honestly."
    assert a["admin"]["unchecked"] == dashboard.UNCHECKED_REFUSED
    if why:
        assert a["admin"]["refusal"]["why"].startswith(why)
        assert "LEFT JOIN demo.records AS m" in (a["admin"]["statement"] or "")
    _, e = ask(client, v, admin=False)
    assert e["kind"] == "refused" and "admin" not in e


# ═════════════════════════════════════════════════════════════════════════
# S19 check (a-safe, HIGH-1): EXACTLY ONE kept row repeating is refused too
# ═════════════════════════════════════════════════════════════════════════

_MIKE = cond("payload.note", "eq", value="mike")
_REPEAT_AGREED = ("Double-checked — both engines found the same rows that would be shown twice, "
                  "so no table is drawn.")


@pytest.mark.parametrize("show, page, sort", [
    (None, 0, None),
    (25, 0, None),                                  # the repeating row is not among the first 25
    (None, 3, {"field": "ts", "dir": "desc"}),
    (None, 8, {"field": "ts", "dir": "desc"}),
])
def test_exactly_one_kept_row_repeating_is_refused(client, conn, show, page, sort):
    per = _per_row(conn, "AND h.data #>> '{payload,note}' = 'mike'")
    assert per == {0: 449, 2: 1}, per            # by hand: 450 kept, one (hb-23 at Aug 20 05:00) matches two
    v = table(columns=["sender_id", "payload.load"], conditions=[_MIKE], sort=sort, show=show, matched=SITE_BY_LOAD)
    status, a = ask(client, v, page)
    assert status == 200 and a["kind"] == "refused", f"one repeating row was drawn: {a.get('total')} rows"
    assert a["message"] == ("Each heartbeat would be shown once for every site that matches it — up to 2 times, "
                            f"for {per[2]} of the {sum(per.values())} heartbeats — and a row is shown only once.")
    assert "rows" not in a and a["admin"]["unchecked"] == _REPEAT_AGREED


def test_exactly_one_repeating_row_through_the_runner_on_a_fixture(wconn, monkeypatch):
    """Both engines' profile say one kept row repeats; the runner refuses it."""
    with _fixture(wconn, monkeypatch, _REPEAT):
        pick = _fx_pick('$.k != "three"')               # "two" matches two rows; nothing else repeats
        for prof in _profiles(wconn, pick, _fx_spec("string")):
            assert prof["repeated"] == 1 and prof["most"] == 2
        r = matched.run_lookup(wconn, pick, _fx_spec("string"))
        assert not r["accepted"] and r["refusal"]["kind"] == "repeat", "one repeating kept row was drawn"
        assert r["panes"] == {} and r["match"]["verdict"] == "agree"


def test_one_kept_row_reads_as_one(client):
    """S19 check, L2: never "for 1 of the 1 site"."""
    v = table("sites", ["name"], conditions=[cond("name", "eq", value="North")],
              matched={"dataset": "senders", "field": "site", "matches": "name", "columns": ["name"]})
    status, a = ask(client, v)
    assert status == 200 and a["kind"] == "refused"
    assert a["message"] == ("The site would be shown once for every sender that matches it — 8 times — "
                            "and a row is shown only once.")
