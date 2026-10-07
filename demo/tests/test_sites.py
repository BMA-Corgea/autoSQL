"""demo/tests/test_sites.py — T-76 S15: Sites, a fifth invented data set.

Five sites: North, South, East and West, which the senders name, and Quarry,
which no sender names.  This file holds what S15 promises at the screen's
contract: Sites is browsable like the other data sets, and counting each
site's Senders across the declared relation (Senders.site → Sites.name)
equals SQL written by hand in this file — the sql-gauntlet's ``LEFT JOIN …
COUNT(s.key)`` — with Quarry kept at 0.  The seed's own proofs (counts, the
four old collections byte-identical, the loader's top-up) are in
test_data.py.  Choosing a match is T-76's engine slice, not this one.
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
from demo.server import db  # noqa: E402
from seed import generate  # noqa: E402

_SITES = [json.loads(d) for _c, _k, d in generate.site_rows()]
_SENDERS = [json.loads(d) for _c, _k, d in generate.sender_rows()]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    return client.get("/api/dashboard/setup").json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-sites-test")
    server_app.refuse_writes(c)
    yield c
    c.close()


def ask(client, v, page=0, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page, "admin": admin})
    return r.status_code, r.json()


def sites_view(**over):
    v = {"dataset": "sites", "columns": ["name", "opened", "capacity"], "conditions": [],
         "logic": "all", "sort": None, "show": None, "summary": None, "scoreboard": None}
    v.update(over)
    return v


def test_the_sites_data_set(setup):
    d = next(x for x in setup["datasets"] if x["id"] == "sites")
    assert d["rows"] == 5 and d["name"] == "Sites" and d["one"] == "site"
    assert [(f["label"], f["kind"]) for f in d["fields"]] == [
        ("Name", "text"), ("Opened", "date"), ("Capacity", "number")]
    assert d["default_columns"] == ["name", "opened", "capacity"]
    assert d["count_from"] == [{"id": "senders", "name": "Senders"}]
    assert d["own_keys"] == ["name"]


def test_sites_are_browsable_like_any_data_set(client):
    status, a = ask(client, sites_view(), admin=False)
    assert status == 200
    assert a["sentence"] == "Sites — 5 rows"
    assert [r[0] for r in a["rows"]] == ["North", "South", "East", "West", "Quarry"]
    assert a["rows"][4][2] == str(_SITES[4]["capacity"])


def test_a_total_over_sites_is_no_dead_end(client):
    status, a = ask(client, sites_view(columns=[], summary={"fn": "sum", "field": "capacity", "per": "all"}))
    assert status == 200 and a["admin"]["verdict"] == "agree"
    assert a["number"]["value"] == f"{sum(s['capacity'] for s in _SITES):,}"


#: Written by hand for this test; it shares no code with demo/group.py.
_HAND_WRITTEN = """
SELECT t.data ->> 'name'                                                    AS site,
       COUNT(s.key)                                                         AS senders,
       SUM(CASE WHEN s.data ->> 'kind' = 'pump' THEN 1 ELSE 0 END)          AS pumps,
       COALESCE(ROUND(100.0 * SUM(CASE WHEN s.data ->> 'kind' = 'pump' THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(s.key), 0), 1), 0.0)                   AS pct_pumps
  FROM demo.records t
  LEFT JOIN demo.records s
    ON s.collection = 'noun:Sender' AND s.data ->> 'site' = t.data ->> 'name'
 WHERE t.collection = 'noun:Site'
 GROUP BY t.data ->> 'name'
 ORDER BY site
"""

_BOARD = {"by": "name", "count_from": "senders",
          "counts": [{"id": 1, "label": "Pumps", "logic": "all", "pct": True,
                      "conditions": [{"field": "kind", "op": "eq", "value": "pump"}]}],
          "time": None, "measure": None, "sort": None}


def test_sites_counting_their_senders_equals_hand_written_left_join(client, conn):
    want = [[site, f"{n:,}", f"{k:,}", f"{pct}%"]
            for site, n, k, pct in conn.execute(_HAND_WRITTEN).fetchall()]
    status, a = ask(client, sites_view(columns=[], scoreboard=_BOARD))
    assert status == 200 and a["admin"]["verdict"] == "agree"
    assert a["sentence"] == "Sites, counting their Senders — 5 sites"
    assert [c["label"] for c in a["columns"]] == ["Name", "Senders", "Pumps", "% Pumps"]
    assert a["rows"] == want


def test_against_the_generator_quarry_at_zero(client):
    per_site = Counter(s["site"] for s in _SENDERS)
    pumps = Counter(s["site"] for s in _SENDERS if s["kind"] == "pump")
    _, a = ask(client, sites_view(columns=[], scoreboard=_BOARD))
    got = {r[0]: r[1:3] for r in a["rows"]}
    assert got == {name: [str(per_site[name]), str(pumps[name])] for name in generate.SITE_NAMES}
    assert got["Quarry"] == ["0", "0"] and {r[0]: r[3] for r in a["rows"]}["Quarry"] == "0.0%"
    assert sorted(per_site.values()) == [8, 13, 15, 19]


def test_a_sites_board_by_its_own_name_reads_one_row_each(client):
    v = sites_view(columns=[], scoreboard=dict(_BOARD, count_from=None, counts=[]))
    status, a = ask(client, v)
    assert status == 200 and a["sentence"] == "Sites, one row each — 5 sites"
