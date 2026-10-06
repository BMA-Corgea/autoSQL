"""demo/tests/test_joins.py — T-74 S11: scoreboards that count across a declared relation.

Senders are grouped; their Heartbeats are counted (Heartbeats.sender_id →
Senders.id, declared once in ``demo/server/dashboard.py :: RELATIONS``).
Every number is checked against something that is neither engine: SQL
written by hand in this file — the sql-gauntlet's own ``LEFT JOIN …
COUNT(h.key) … SUM(CASE WHEN … THEN 1 ELSE 0 END)`` — and the seed
generator's rows.  Two mutants must be caught: the statement counting
``count(*)`` (a sender with no heartbeats would read 1), and the second
engine joining INNER (the five silent senders would vanish).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
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

import group  # noqa: E402
from pyrunner import group as pygroup  # noqa: E402

_HB = [json.loads(d) for _c, _k, d in generate.heartbeat_rows()]
_SENDERS = [json.loads(d) for _c, _k, d in generate.sender_rows()]
_SILENT = [f"hb-{i:02d}" for i in range(51, 56)]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    return client.get("/api/dashboard/setup").json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-joins-test")
    server_app.refuse_writes(c)
    yield c
    c.close()


def cond(field, op, **kw):
    return {"field": field, "op": op, **kw}


def count(label, *conditions, logic="all", pct=False, cid=None):
    out = {"label": label, "logic": logic, "conditions": list(conditions), "pct": pct}
    if cid is not None:
        out["id"] = cid
    return out


def senders_board(by="id", conditions=(), **sb):
    sb = {"by": by, "count_from": "heartbeats", **sb}
    return {"dataset": "senders", "columns": [], "conditions": list(conditions), "sort": None,
            "show": None, "summary": None, "scoreboard": sb}


def ask(client, v, page=0):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page, "admin": True})
    return r.status_code, r.json()


def q1(k, n):
    if n == 0:
        return "0"
    return str((Decimal(100 * k) / Decimal(n)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


_BOARD = dict(counts=[count("OK", cond("status", "eq", value="ok"), pct=True),
                      count("Trouble", cond("status", "eq", value="warn"),
                            cond("status", "eq", value="error"), logic="any")],
              time={"fn": "latest", "field": "ts"})

#: Written by hand for this test; it shares no code with demo/group.py.
_HAND_WRITTEN = """
SELECT s.data ->> 'id'                                                       AS sender,
       COUNT(h.key)                                                          AS beats,
       SUM(CASE WHEN h.data ->> 'status' = 'ok' THEN 1 ELSE 0 END)           AS ok,
       COALESCE(ROUND(100.0 * SUM(CASE WHEN h.data ->> 'status' = 'ok' THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(h.key), 0), 1), 0)                       AS pct_ok,
       SUM(CASE WHEN h.data ->> 'status' IN ('warn', 'error') THEN 1 ELSE 0 END) AS trouble,
       MAX(h.data ->> 'ts')                                                  AS latest
  FROM demo.records s
  LEFT JOIN demo.records h
    ON h.collection = 'noun:Heartbeat' AND h.data ->> 'sender_id' = s.data ->> 'id'
 WHERE s.collection = 'noun:Sender'
 GROUP BY s.data ->> 'id'
 ORDER BY sender
"""


def _spec(setup, v):
    spec, _ = dashboard.to_spec(setup, v)
    return spec


class TestEverySenderCountingTheirHeartbeats:
    def test_cell_by_cell_against_hand_written_left_join(self, setup, conn):
        want = conn.execute(_HAND_WRITTEN).fetchall()
        assert len(want) == 55
        result = scoreboard.run_group(conn, _spec(setup, senders_board(**_BOARD)))
        assert result["accepted"] and result["verdict"] == "agree"
        assert result["comparison"]["compared_rows"] == 55
        got = [r["c"] for r in result["panes"]["sql"]["rows"]]
        for row, (sender, beats, ok, pct, trouble, latest) in zip(got, want):
            assert row == [sender, str(beats), str(ok), str(pct), str(trouble),
                           "null" if latest is None else latest], sender

    def test_against_the_generator(self, client, setup):
        per = defaultdict(lambda: [0, 0, 0])
        for r in _HB:
            p = per[r["sender_id"]]
            p[0] += 1
            p[1] += r["status"] == "ok"
            p[2] += r["status"] in ("warn", "error")
        rows = []
        for page in (0, 1):
            _, a = ask(client, senders_board(**_BOARD), page=page)
            rows += a["rows"]
        assert [r[0] for r in rows] == [s["id"] for s in _SENDERS]
        for r in rows:
            n, ok, trouble = per[r[0]]
            assert r[1:5] == [f"{n:,}", f"{ok:,}", (q1(ok, n) if n else "0.0") + "%", f"{trouble:,}"], r[0]

    def test_the_five_silent_senders_read_zero_not_blank(self, client, setup):
        _, a = ask(client, senders_board(**_BOARD), page=1)
        silent = [r for r in a["rows"] if r[0] in _SILENT]
        assert [r[0] for r in silent] == _SILENT
        for r in silent:
            assert r[1:5] == ["0", "0", "0.0%", "0"] and r[5] is None, r
        assert a["sentence"] == "Senders, counting their Heartbeats — 55 senders"

    def test_is_not_cannot_count_the_empty_side_of_the_join(self, client, setup):
        """"is not warn" holds on a missing value — so a sender with no
        heartbeats must still read 0, not 1 (the statement's c.key IS NOT
        NULL guard; the second engine has no rows to test)."""
        _, a = ask(client, senders_board(counts=[count("Not warn", cond("status", "ne", value="warn"))]), page=1)
        assert {r[0]: r[2] for r in a["rows"] if r[0] in _SILENT} == {s: "0" for s in _SILENT}
        assert a["admin"]["verdict"] == "agree"

    def test_admin_sees_the_join(self, client, setup):
        _, a = ask(client, senders_board(**_BOARD))
        sql = a["admin"]["statement"]
        assert "LEFT JOIN demo.records AS c" in sql and "count(c.key)" in sql
        assert "count(*)" not in sql


class TestPerSiteAndParentConditions:
    """AC3 (Heartbeats per Site, read as Senders per Site counting their
    Heartbeats) and AC5 (page conditions narrow the senders; conditions in
    a count column look at the heartbeats)."""

    def test_per_site(self, client, setup, conn):
        hand = {site: (n, ok) for site, n, ok in conn.execute("""
            SELECT s.data ->> 'site', COUNT(h.key),
                   SUM(CASE WHEN h.data ->> 'status' = 'ok' THEN 1 ELSE 0 END)
              FROM demo.records s
              LEFT JOIN demo.records h
                ON h.collection = 'noun:Heartbeat' AND h.data ->> 'sender_id' = s.data ->> 'id'
             WHERE s.collection = 'noun:Sender' GROUP BY 1""").fetchall()}
        _, a = ask(client, senders_board(by="site", counts=[count("OK", cond("status", "eq", value="ok"))]))
        assert a["admin"]["verdict"] == "agree"
        assert {r[0]: (int(r[1].replace(",", "")), int(r[2].replace(",", ""))) for r in a["rows"]} == hand
        assert a["sentence"] == "Senders per Site, counting their Heartbeats — 4 sites"

    def test_a_page_condition_narrows_the_senders(self, client, setup):
        north = {s["id"] for s in _SENDERS if s["site"] == "North"}
        rows = []
        for page in (0, 1):
            _, a = ask(client, senders_board(conditions=[cond("site", "eq", value="North")], **_BOARD), page=page)
            rows += a["rows"]
        assert {r[0] for r in rows} == north
        assert a["sentence"] == f"Senders where Site is North, counting their Heartbeats — {len(north)} senders"

    def test_count_conditions_read_the_heartbeats(self, client, setup):
        status, a = ask(client, senders_board(counts=[count("North?", cond("site", "eq", value="North"))]))
        assert status == 422 and a["message"] == "A condition names a field this data set doesn't have."


class TestWhatAJoinCannotHonour:
    @pytest.mark.parametrize("patch, says", [
        ({"count_from": "samples"}, "Senders has no related data set to count from by that name."),
        ({"count_from": ["heartbeats"]}, "Senders has no related data set to count from by that name."),
        ({"time": {"fn": "latest", "field": "installed"}}, "Latest and earliest read a time or a date field."),
    ])
    def test_refused_by_name(self, client, setup, patch, says):
        v = senders_board(**_BOARD)
        v["scoreboard"].update(patch)
        status, a = ask(client, v)
        assert status == 422 and a["message"] == says

    def test_only_declared_relations(self, client, setup):
        v = senders_board(**_BOARD)
        v["dataset"] = "heartbeats"
        v["scoreboard"]["by"] = "status"
        status, a = ask(client, v)
        assert status == 422 and a["message"] == "Heartbeats has no related data set to count from by that name."


class TestTheJoinMutants:
    def test_count_star_in_the_statement_is_caught_by_the_hand_written_sql(self, setup, conn, monkeypatch):
        """A statement that counts count(*) reads 1 for a sender with none —
        the hand-written LEFT JOIN … COUNT(h.key) catches it."""
        real = group.build

        def mutant(spec):
            b = real(spec)
            return b._replace(sql=b.sql.replace("count(c.key)", "count(*)"))

        monkeypatch.setattr(group, "build", mutant)
        spec = _spec(setup, senders_board(**_BOARD))
        rows = scoreboard.run_group(conn, spec)["panes"]["sql"]["rows"]
        want = {r[0]: str(r[1]) for r in conn.execute(_HAND_WRITTEN).fetchall()}
        got = {r["c"][0]: r["c"][1] for r in rows}
        assert got != want and all(got[s] == "1" for s in _SILENT)

    def test_an_inner_join_in_the_second_engine_is_caught_by_the_comparison(self, setup, conn, monkeypatch):
        real = pygroup.answer

        def inner(rows, spec, related_rows=()):
            out = real(rows, spec, related_rows)
            kept = [r for r in out["rows"] if r["rows"] > 0]
            return dict(out, rows=kept, row_count=len(kept))

        spec = _spec(setup, senders_board(**_BOARD))
        assert scoreboard.run_group(conn, spec)["verdict"] == "agree"
        monkeypatch.setattr(pygroup, "answer", inner)
        assert scoreboard.run_group(conn, spec)["verdict"] == "disagree"


def test_the_senders_data_set(setup):
    d = next(x for x in setup["datasets"] if x["id"] == "senders")
    assert d["rows"] == 55 and d["name"] == "Senders"
    assert [f["label"] for f in d["fields"]] == ["Sender", "Name", "Site", "Kind", "Installed"]
    assert d["count_from"] == [{"id": "heartbeats", "name": "Heartbeats"}]
    assert all(x["count_from"] == [] for x in setup["datasets"] if x["id"] != "senders")
    assert d["own_keys"] == ["id"]
    assert all(x["own_keys"] == [] for x in setup["datasets"] if x["id"] != "senders")


def test_every_join_scoreboard_in_a_matrix_agrees(setup, conn):
    """AC4: both engines, cell by cell, over join scoreboards — every logic,
    measures, earliest, page filters on the parents, each grouping, and
    sorts that put the silent senders first and last."""
    counts = [count(f"Warn hot {lg}", cond("status", "eq", value="warn"),
                    cond("payload.load", "gt", value=50), logic=lg, pct=True, cid=i + 1)
              for i, lg in enumerate(("all", "any", "one", "allnone"))]
    # Eight scoreboards that between them cover each axis: both groupings,
    # a measure and none, a page filter and none, silent-first and
    # largest-first sorts (the full 72-way product agreed too, measured
    # once at 152 s — too slow to keep in the suite).
    combos = [
        ("id", None, [], {"column": "rows", "dir": "asc"}),
        ("id", {"fn": "avg", "field": "payload.load"}, [cond("site", "ne", value="North")], None),
        ("id", {"fn": "max", "field": "payload.load"}, [], {"column": "count:3", "dir": "desc"}),
        ("id", None, [cond("site", "ne", value="North")], {"column": "pct:4", "dir": "desc"}),
        ("site", {"fn": "avg", "field": "payload.load"}, [], {"column": "rows", "dir": "asc"}),
        ("site", None, [cond("site", "ne", value="North")], None),
        ("kind", {"fn": "sum", "field": "payload.load"}, [], {"column": "measure", "dir": "desc"}),
        ("name", None, [], {"column": "time", "dir": "asc"}),
    ]
    for by, measure, page_conds, sort in combos:
        sb = {"counts": counts, "time": {"fn": "earliest", "field": "ts"}, "sort": sort}
        if measure:
            sb["measure"] = measure
        spec = _spec(setup, senders_board(by=by, conditions=page_conds, **sb))
        result = scoreboard.run_group(conn, spec)
        assert result["accepted"] and result["verdict"] == "agree", (by, measure, page_conds, sort)


def test_the_first_column_is_named_after_what_it_counts(client, setup):
    """S12: on a join the first count column reads "Heartbeats" (each
    sender's beats), not "Rows"; counting a data set's own rows it stays
    "Rows"."""
    _, a = ask(client, senders_board(**_BOARD))
    assert [c["label"] for c in a["columns"]][:2] == ["Sender", "Heartbeats"]
    own = senders_board(by="site", counts=[])
    own["scoreboard"].pop("count_from")
    _, b = ask(client, own)
    assert [c["label"] for c in b["columns"]][:2] == ["Site", "Rows"]
    assert next(d for d in setup["datasets"] if d["id"] == "senders")["one"] == "sender"


def test_a_board_by_its_own_key_reads_one_row_each(client, setup):
    """S11 check, LOW 3: not "Senders per Sender"."""
    own = senders_board(by="id", counts=[])
    own["scoreboard"].pop("count_from")
    _, a = ask(client, own)
    assert a["sentence"] == "Senders, one row each — 55 senders"
    _, b = ask(client, senders_board(by="id", counts=[]))
    assert b["sentence"] == "Senders, counting their Heartbeats — 55 senders"
