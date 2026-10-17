"""T-85 — the small cleanups from runs 6 and 8 (the owner's Q2: "build them this run"). Server-side items here; the
screen's (the pinned column, the ticks' stop, a blank number cell, the add-row label) are in the run folder's
dash-check-t85.mjs, and the shut group's brackets in ops/tests/test_t85_words.mjs. None changes a number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard  # noqa: E402

HB = {"id": "heartbeats", "one": "heartbeat", "many": "heartbeats", "name": "Heartbeats"}
EDGE = {"id": "edges", "one": "edge case", "many": "edge cases", "name": "Edge cases"}
SENDERS = {"id": "senders", "one": "sender", "many": "senders", "name": "Senders"}
SAMPLES = {"id": "samples", "one": "sample", "many": "samples", "name": "Samples"}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    return TestClient(server_app.app, raise_server_exceptions=False)


# ── 4 · "a" or "an" ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel, words", [(EDGE, "matches an edge case"), (SENDERS, "matches a sender")])
def test_the_preview_says_a_or_an_by_the_word(rel, words):
    line = dashboard.matched_preview(HB, rel, {"rows": 5, "rows_none": 5})
    assert line.startswith(f"No heartbeat here {words}, so "), line


# ── 9 · "all 2,000", not "2,000 of the 2,000" ──────────────────────────────────────────────────────

def test_a_refusal_where_every_row_is_affected_says_all():
    line = dashboard.repeat_line(SAMPLES, SENDERS, {"rows": 2000, "repeated": 2000, "most": 3})
    assert "for all 2,000 samples —" in line and "of the" not in line, line
    some = dashboard.repeat_line(SAMPLES, SENDERS, {"rows": 2000, "repeated": 7, "most": 3})
    assert "for 7 of the 2,000 samples —" in some, some
    line = dashboard.double_count_line(SENDERS, SAMPLES, {"counted": 2000, "counted_twice": 2000, "most_parents": 2})
    assert "for all 2,000 samples —" in line and "of the" not in line, line


# ── 8 · a body nested past the JSON reader: a sentence, not "There was an error parsing the body" ─────

def test_a_question_nested_too_deep_to_read_is_said_in_a_sentence(client):
    deep = '{"version": 1, "join": "all", "items": [' * 5000 + "]}" * 5000     # a-chk's 5,000 nested groups
    body = '{"view": {"dataset": "heartbeats", "columns": ["status"], "filter": ' + deep + '}, "page": 0}'
    r = client.post("/api/dashboard/answer", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 400
    a = r.json()
    assert a.get("kind") == "invalid" and a["message"] == dashboard.TOO_DEEP_WORDS, a
    assert "parsing" not in a["message"] and "error" not in a["message"].lower()


def test_any_other_bad_body_is_answered_as_before(client):
    r = client.post("/api/dashboard/answer", content="{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and "kind" not in r.json()


# ── 10 · the answer cache's key holds which matched columns are ticked ────────────────────────────

def _ask(client, matched):
    v = {"dataset": "heartbeats", "columns": ["sender_id"], "conditions": [], "sort": None, "show": None,
         "summary": None, "matched": matched}
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})
    assert r.status_code == 200, r.text[:200]
    return [c["label"] for c in r.json()["columns"]]


def test_the_same_question_with_another_matched_column_is_answered_again_not_from_the_cache(client):
    """M5 review MEDIUM 2: a key ignoring the matched columns passed every suite. Name, then Name and Site."""
    dashboard._CACHE.clear()
    m = {"dataset": "senders", "field": "id", "matches": "sender_id"}
    one = _ask(client, dict(m, columns=["name"]))
    two = _ask(client, dict(m, columns=["name", "site"]))
    assert len(two) == len(one) + 1 and two[:len(one)] == one, (one, two)
