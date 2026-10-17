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


def test_a_float8_overflow_met_by_a_probe_is_refused_in_its_own_words(client):
    """$.a * $.a == 1: the container-equality probe computes the product before the statement runs; the
    database refuses the arithmetic (22003). It was a 500 too; now the overflow refusal, said as such."""
    r = _ask(client, "$.a * $.a == 1")
    assert r.status_code == 422, (r.status_code, r.text[:200])
    rf = r.json()["refusal"]
    assert (rf["layer"], rf["construct"], rf["statement_sent"]) == (2, "float8 overflow", False)
    assert "before the statement was sent" in rf["body"] and "22003" in rf["why"]


class _Refused(Exception):
    def __init__(self, sqlstate, message, detail=None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = type("Diag", (), {"message_detail": detail})()


#: T-109: a series row whose time the statement can't read (xpr.series_time_refused), its key and value in DETAIL
_SERIES_MSG = "row hb-zz-t109: its series time is not one this reads, so it can't be put in a bucket"
_SERIES_DETAIL = '{"key" : "hb-zz-t109", "value" : "2026-08-20t10:00:00z"}'

_ZONE_MSG = ("time zone America/Edmonton: this database's clock differs from the evaluator's on 2026-11-02, "
             "a time this question reads")


@pytest.mark.parametrize("sqlstate, message, construct", [
    ("XPR01", "xpr.f8 refusal: JSON number magnitude exceeds float8 range (DBL_MAX)", "number out of range"),
    ("XPR05", _ZONE_MSG, "time zone"),
    ("22003", "value out of range: overflow", "float8 overflow"),
    ("XPR06", _SERIES_MSG, "series time"),
    ("XX000", "some other failure of the database", None),
])
def test_each_refusal_the_statement_meets_is_told_in_its_own_words(client, monkeypatch, sqlstate, message, construct):
    """a-chk's MEDIUM (MQ1 survived): only XPR01 gets the out-of-range number's words; the zone refusal gets the
    dashboard's sentence; the float8 overflow keeps its own; any other database error is not reworded (it is
    still the error it is). The statement is made to raise each in turn on a pick the probes pass. T-109's round
    (a-chk's MEDIUM): a series time the statement can't read (XPR06) gets the dashboard's sentence too."""
    from demo.server import app as server_app
    from picks import zones

    def refuse(conn, built):
        raise _Refused(sqlstate, message, _SERIES_DETAIL if sqlstate == "XPR06" else None)
    monkeypatch.setattr(server_app, "sql_pane", refuse)
    pick = {"source": "noun:Heartbeat", "computed": [], "filter": '$.status == "ok"', "sort": None, "cap": None,
            "window": None, "changed": False, "bucket": "off", "aggregate": None}
    if sqlstate == "XPR06":      # only a summary per hour, day, week or month buckets the series time
        pick.update(bucket="day", aggregate={"fn": "count", "field": None})
    r = client.post("/api/pick", json={"pick": pick})
    if construct is None:
        assert r.status_code == 500
        return
    assert r.status_code == 422, (r.status_code, r.text[:200])
    rf = r.json()["refusal"]
    assert (rf["construct"], rf["statement_sent"]) == (construct, True) and sqlstate in rf["why"]
    if sqlstate == "XPR05":
        assert rf["body"] == zones.refusal_words(_ZONE_MSG) == (
            "Edmonton time can't read these times: this computer and its database disagree about Edmonton's "
            "clocks on Nov 2, 2026, and this question reads a time from then.")
    if sqlstate == "XPR06":
        assert rf["body"] == ("Heartbeat hb-zz-t109 has a time this can't read (\u201c2026-08-20t10:00:00z\u201d), "
                              "so these can't be counted per day.")
