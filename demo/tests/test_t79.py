"""demo/tests/test_t79.py — T-79, run 5's later list (LATER.md, "Run 5").

The server's share of the list; the screen's share is driven in a browser
(the builder's dash-check, §24).  One block per item:

* the Everyone view's setup names no field hidden from it (S13 check, M4);
* a board's groups are counted in words that read ("2 values of Present",
  never "2 presents") (S17 check);
* a second engine that throws on a board itself fails closed in words,
  never a 500 (S16 re-check);
* the loader, driven for real on the real table — inside one transaction
  that is always rolled back (S15 check: its tests ran on a stand-in).
"""

from __future__ import annotations

import json
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
from demo.server import dashboard  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402

_MANIFEST = json.loads((_DEMO_DIR / "manifest.json").read_text())


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


def ask(client, v, *, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    return r.status_code, r.json()


def board(ds_id, by, count_from=None, *, show=None, conditions=()):
    sb = {"by": by, "counts": []}
    if count_from is not None:
        sb["count_from"] = count_from
    return {"dataset": ds_id, "columns": [], "conditions": list(conditions), "sort": None,
            "show": show, "summary": None, "scoreboard": sb}


# ═════════════════════════════════════════════════════════════════════════
# 1 · The Everyone view's setup names no field hidden from it
# ═════════════════════════════════════════════════════════════════════════

def _label_values(client):
    admin = client.get("/api/dashboard/setup?view=admin").json()
    edge = next(d for d in admin["datasets"] if d["id"] == "edge")
    label = next(f for f in edge["fields"] if f["path"] == "label")
    assert label["hidden_by_default"] and len(label["values"]) == 10
    return label["values"]


def test_everyone_setup_carries_no_hidden_field(client):
    values = _label_values(client)
    r = client.get("/api/dashboard/setup")
    assert r.status_code == 200
    s = r.json()
    edge = next(d for d in s["datasets"] if d["id"] == "edge")
    assert "label" not in {f["path"] for f in edge["fields"]}, "Everyone's setup names Label"
    assert not any(f.get("hidden_by_default") for d in s["datasets"] for f in d["fields"])
    assert "admin_default_views" not in s, "Everyone's setup carries Admin's starting views"
    # not one of Label's values, anywhere in the response's text
    text = r.text
    leaked = [v for v in values if json.dumps(v)[1:-1] in text]
    assert not leaked, f"Everyone's setup still carries Label's values: {leaked[:3]}"
    # the explicit word is the same answer, and anything but "admin" is Everyone
    assert client.get("/api/dashboard/setup?view=everyone").json() == s
    assert client.get("/api/dashboard/setup?view=Admin").json() == s


def test_admin_setup_is_the_whole_setup(client):
    s = client.get("/api/dashboard/setup?view=admin").json()
    edge = next(d for d in s["datasets"] if d["id"] == "edge")
    assert "label" in {f["path"] for f in edge["fields"]}
    assert "label" in s["admin_default_views"]["edge"]["columns"]
    assert "label" not in s["default_views"]["edge"]["columns"]


def test_everyone_setup_differs_from_admin_only_by_the_hidden_field(client):
    admin = client.get("/api/dashboard/setup?view=admin").json()
    everyone = client.get("/api/dashboard/setup").json()
    stripped = dict(admin)
    stripped.pop("admin_default_views")
    stripped["datasets"] = [dict(d, fields=[f for f in d["fields"] if not f["hidden_by_default"]])
                            for d in admin["datasets"]]
    assert everyone == stripped
    # every other field keeps the alias it had: the statement doesn't change
    for d_a, d_e in zip(admin["datasets"], everyone["datasets"]):
        aliases = {f["path"]: f["alias"] for f in d_a["fields"]}
        assert all(aliases[f["path"]] == f["alias"] for f in d_e["fields"])


def test_everyone_still_cannot_ask_for_the_hidden_field(client):
    v = {"dataset": "edge", "columns": ["label"], "conditions": [], "sort": None,
         "show": None, "summary": None}
    status, a = ask(client, v, admin=False)
    assert status == 422 and a["message"] == "Label isn't offered in this view."


# ═════════════════════════════════════════════════════════════════════════
# 2 · A board's groups, counted in words that read
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ds_id, by, tail", [
    ("edge", "present", "2 values of Present"),
    ("edge", "where.code", "2 values of Where code"),
    ("edge", "txt", "2 values of Txt"),
    ("edge", "a", "2 values of A"),
    ("heartbeats", "payload.load", "101 values of Load"),
    ("sites", "capacity", "4 values of Capacity"),
    # the declared nouns are still made plural
    ("heartbeats", "status", "3 statuses"),
    ("heartbeats", "payload.note", "16 notes"),
    ("samples", "priority", "5 priorities"),
    ("senders", "site", "4 sites"),
    ("senders", "kind", "4 kinds"),
    # a board by the data set's own key counts the data set's own word
    ("sites", "name", "5 sites"),
    ("senders", "id", "55 senders"),
])
def test_a_boards_groups_read_as_words(client, ds_id, by, tail):
    status, a = ask(client, board(ds_id, by), admin=False)
    assert status == 200, a
    assert a["sentence"].endswith(f" — {tail}"), a["sentence"]


def test_one_group_reads_as_one_value(client):
    cond = {"field": "present", "op": "eq", "value": 1}
    status, a = ask(client, board("edge", "present", conditions=[cond]), admin=False)
    assert status == 200 and a["sentence"].endswith(" — 1 value of Present"), a["sentence"]


def test_a_capped_board_reads_the_same_way(client):
    status, a = ask(client, board("heartbeats", "payload.load", show=25), admin=False)
    assert status == 200 and a["sentence"].endswith(" — the first 25 of 101 values of Load"), a["sentence"]


# ═════════════════════════════════════════════════════════════════════════
# 3 · The second engine throwing on a board itself: refused in words
# ═════════════════════════════════════════════════════════════════════════

_MACHINERY = re.compile(r"\b(?:sql|python|engine|pane|pushdown|statement|join)\b", re.I)


def _broken(monkeypatch):
    def broken(rows, spec, related_rows=()):
        raise RuntimeError("board broke")

    monkeypatch.setattr(pygroup, "answer", broken)
    dashboard._CACHE.clear()


@pytest.mark.parametrize("view", [
    board("heartbeats", "status"),                                                     # its own rows
    board("sites", "name", {"dataset": "senders", "field": "site", "matches": "name"}),  # a match
    board("senders", "id", "heartbeats"),                                              # T-74's relation
    board("heartbeats", "sender_id", show=25),                                         # capped: two boards
], ids=["own-rows", "a-match", "declared", "capped"])
def test_a_board_the_second_engine_cannot_compute_is_refused_in_words(client, monkeypatch, view):
    _broken(monkeypatch)
    try:
        status, a = ask(client, view)
        status_e, e = ask(client, view, admin=False)
    finally:
        dashboard._CACHE.clear()
    assert status == 200, f"answered {status}, not a refusal in words"
    assert a["kind"] == "refused" and a["message"] == dashboard.BOARD_UNCHECKED
    assert "rows" not in a and "columns" not in a, "a number was shown from a board not double-checked"
    assert any("second engine could not compute this board (RuntimeError: board broke)" in n
               for n in a["admin"]["notes"])
    assert a["admin"]["verdict"] == "no-compare" and a["admin"]["sent"] is True
    assert status_e == 200 and e["kind"] == "refused" and "admin" not in e
    assert not _MACHINERY.search(e["message"] + " " + e["sentence"]), e


def test_after_the_failure_the_board_is_answered_again(client):
    """Nothing about the refusal is remembered as the answer."""
    dashboard._CACHE.clear()
    status, a = ask(client, board("heartbeats", "status"))
    assert status == 200 and a["kind"] == "scoreboard" and a["admin"]["verdict"] == "agree"


# ═════════════════════════════════════════════════════════════════════════
# 4 · The loader, for real, on the real table — and always rolled back
# ═════════════════════════════════════════════════════════════════════════
#
# The demo has ONE connection factory, to ONE database (db.py, B13), so a
# throwaway database is not reachable from here, by design.  Instead each
# case opens one transaction on the demo's own table, changes what the case
# needs (DELETE, never TRUNCATE: readers keep reading the committed rows
# under MVCC and are never blocked), runs the REAL ``load.run`` — its
# schema check, runtime install, COPY, counts and AC-10 digest on real
# Postgres — and ROLLS BACK.  ``load.run`` commits at its end; the one
# thing replaced is that ``commit``, which is recorded instead of sent.

class _NoCommit:
    """The real connection, with ``commit`` recorded and not sent."""

    def __init__(self, conn):
        self._conn = conn
        self.committed = 0

    def commit(self):
        self.committed += 1

    def __getattr__(self, name):
        return getattr(self._conn, name)


_DIGEST = _MANIFEST["seed:demo.records:md5"]


@pytest.fixture
def txn():
    from demo.seed.load import demo_connection, records_digest

    conn = demo_connection()
    assert conn.autocommit is False
    conn.execute("SET LOCAL lock_timeout = '5s'")
    conn.execute("SET LOCAL statement_timeout = '60s'")
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
        # the committed table is exactly the pinned seed, every time
        with demo_connection() as after:
            assert records_digest(after) == _DIGEST


def _written_here(conn) -> dict:
    """Rows this transaction wrote, by collection."""
    rows = conn.execute(
        "SELECT collection, count(*) FROM demo.records"
        " WHERE xmin::text = (pg_current_xact_id()::xid)::text GROUP BY 1").fetchall()
    return {c: int(n) for c, n in rows}


def _run(conn):
    from demo.seed import load

    wrapped = _NoCommit(conn)
    return load, wrapped, load.run(wrapped)


def test_the_loader_seeds_an_empty_table_for_real(txn):
    txn.execute("DELETE FROM demo.records")
    _load, wrapped, digest = _run(txn)
    assert digest == _DIGEST and wrapped.committed == 1
    assert _written_here(txn) == {"noun:EdgeCase": 10, "noun:Heartbeat": 8400, "noun:Sample": 2000,
                                  "noun:Sender": 55, "noun:Site": 5}


@pytest.mark.parametrize("gone, added", [
    (("noun:Site",), {"noun:Site": 5}),                                  # seeded at T-74
    (("noun:Sender", "noun:Site"), {"noun:Sender": 55, "noun:Site": 5}),  # seeded before T-74
])
def test_the_loader_tops_up_only_what_an_older_seed_lacks(txn, gone, added):
    txn.execute("DELETE FROM demo.records WHERE collection = ANY(%(c)s)", {"c": list(gone)})
    _load, wrapped, digest = _run(txn)
    assert digest == _DIGEST and wrapped.committed == 1
    # only the missing collections were written; every older row is untouched
    assert _written_here(txn) == added


def test_the_loader_refuses_a_lost_old_collection_and_writes_nothing(txn):
    from demo.seed import load

    txn.execute("DELETE FROM demo.records WHERE collection = 'noun:Heartbeat'")
    wrapped = _NoCommit(txn)
    with pytest.raises(load.SeedError, match=r"no rows of noun:Heartbeat .* its absence is damage"):
        load.run(wrapped)
    assert wrapped.committed == 0 and _written_here(txn) == {}


def test_the_loader_never_tops_up_a_partial_collection(txn):
    from demo.seed import load

    txn.execute("DELETE FROM demo.records WHERE collection = 'noun:Site' AND key = 'site-05'")
    wrapped = _NoCommit(txn)
    with pytest.raises(load.SeedError, match="collection counts are wrong"):
        load.run(wrapped)
    assert wrapped.committed == 0 and _written_here(txn) == {}


def test_the_loader_refuses_a_changed_row_by_its_digest(txn):
    from demo.seed import load

    txn.execute("UPDATE demo.records SET data = jsonb_set(data, '{capacity}', '99')"
                " WHERE collection = 'noun:Site' AND key = 'site-01'")
    wrapped = _NoCommit(txn)
    with pytest.raises(load.SeedError, match="AC-10 digest mismatch"):
        load.run(wrapped)
    assert wrapped.committed == 0


# ═════════════════════════════════════════════════════════════════════════
# 3b · The same for every answer that isn't a board: a plain table, a
#      number, a chart (the foreman, on S18: item 9's class, everywhere)
# ═════════════════════════════════════════════════════════════════════════

def _plain(ds_id="heartbeats", **kw):
    v = {"dataset": ds_id, "columns": ["sender_id", "status"], "conditions": [], "sort": None,
         "show": None, "summary": None}
    v.update(kw)
    return v


def _broken_table(monkeypatch):
    def broken(conn, pick, kinds_by_column):
        raise RuntimeError("table broke")

    monkeypatch.setattr(server_app, "python_pane", broken)
    dashboard._CACHE.clear()


@pytest.mark.parametrize("view", [
    _plain(),                                                                    # rows
    _plain(show=25),                                                             # capped rows (a count beside)
    _plain(columns=[], summary={"fn": "avg", "field": "payload.load", "per": "all"}),   # one number
    _plain(columns=[], summary={"fn": "count", "field": None, "per": "day"}),          # a chart
    _plain("sites", columns=["name", "capacity"]),                               # another data set
], ids=["rows", "capped", "number", "chart", "sites"])
def test_an_answer_the_second_engine_cannot_compute_is_refused_in_words(client, monkeypatch, view):
    _broken_table(monkeypatch)
    try:
        status, a = ask(client, view)
        status_e, e = ask(client, view, admin=False)
    finally:
        dashboard._CACHE.clear()
    assert status == 200, f"answered {status}, not a refusal in words"
    assert a["kind"] == "refused" and a["message"] == dashboard.ANSWER_UNCHECKED
    assert not {"rows", "number", "bars", "columns"} & set(a), "a number was shown from an answer not double-checked"
    assert any("second engine could not compute this answer (RuntimeError: table broke)" in n
               for n in a["admin"]["notes"])
    assert a["admin"]["statement"].startswith("SELECT"), "Admin can still read the statement that was sent"
    assert status_e == 200 and e["kind"] == "refused" and "admin" not in e
    assert not _MACHINERY.search(e["message"] + " " + e["sentence"]), e


def test_after_the_table_failure_the_table_is_answered_again(client):
    dashboard._CACHE.clear()
    status, a = ask(client, _plain())
    assert status == 200 and a["kind"] == "table" and a["total"] == 8400 and a["admin"]["verdict"] == "agree"


def test_the_two_pane_screen_still_answers_its_own_way(client, monkeypatch):
    """run_pick's own rule stands for the two-pane screen: anything but the
    float8 refusal propagates there (now under a name the dashboard reads)."""
    _broken_table(monkeypatch)
    from demo import legality

    pick = dict(legality.default_pick(), source="noun:Heartbeat", cap=5)
    with pytest.raises(server_app.SecondEngineFailed, match="RuntimeError: table broke"):
        client.post("/api/pick", json=pick)
    dashboard._CACHE.clear()
