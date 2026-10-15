"""T-105 — an out-of-range number inside == / != answers in words on the two-pane screen, never a 500 (GA-72).

Edge cases hold a JSON number past the largest double (`huge`). Read through == or != it reaches the runtime's
named refusal (XPR01) either in a probe (`abs($.huge) == 1`: the container-equality probe computes the operand)
or in the statement itself (`$.huge == 1`: == is not a numeric-read place, so the magnitude probe never looks).
Both used to answer HTTP 500 (a-chk's LATER-verify, item 5a). Now each is a named layer-2 refusal, as the 22003
float8 overflow already was, with the Python pane still answering. Read-only on the demo database.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    return TestClient(server_app.app, raise_server_exceptions=False)


def _ask(client, flt):
    pick = {"source": "noun:EdgeCase", "computed": [], "filter": flt, "sort": None, "cap": None,
            "window": None, "changed": False, "bucket": "off", "aggregate": None}
    return client.post("/api/pick", json={"pick": pick})


#: the filter → where the refusal comes from (the probes, or the statement once sent)
REPRO = {
    "abs($.huge) == 1": False,          # a-chk's repro: raised in the container-equality probe
    "abs($.huge) != 1": False,
    'abs($.huge) == "x"': False,
    "$.huge * 1 == 1": False,           # the probe computes the product
    "$.huge == 1": True,                # raised by the statement itself (no probe computes a bare field)
}


@pytest.mark.parametrize("flt", list(REPRO))
def test_an_out_of_range_number_inside_equality_is_refused_in_words(client, flt):
    r = _ask(client, flt)
    assert r.status_code == 422, (r.status_code, r.text[:300])
    body = r.json()
    rf = body["refusal"]
    assert (rf["layer"], rf["kind"], rf["headline"], rf["construct"]) == (2, "runtime", "Refused while running",
                                                                         "number out of range")
    assert "larger than the largest double" in rf["body"] and "XPR01" in rf["why"]
    assert rf["sql_existed"] is True and rf["statement_sent"] is REPRO[flt]
    assert body["panes"]["sql"]["row_count"] == 0 and body["panes"]["python"]["state"] == "answered"


@pytest.mark.parametrize("flt, layer, construct", [("abs($.huge) > 1", 2, "probe (a)"),
                                                   ("floor($.huge) == 1", 1, "floor")])
def test_a_neighbour_that_already_answered_in_words_is_unchanged(client, flt, layer, construct):
    r = _ask(client, flt)
    rf = r.json()["refusal"]
    assert r.status_code == 422 and (rf["layer"], rf["construct"]) == (layer, construct)
