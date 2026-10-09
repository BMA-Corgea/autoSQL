"""demo/tests/test_t87.py — T-87 (M2): one compiler; no numbers when the engines disagree.

1. The statement, its display and its probes are written by ONE compiler — the
   shipping ``compiler/compile.py`` — so a probe asks about the operand exactly
   as the statement will compute it (the frozen T-1 spike compiles numbers
   differently since T-52 / T-61), and the display shows what runs.
2. When the two engines disagree on an answer, no number from it is shown —
   rows, a number, a chart, a board, a matched table.  Everyone reads one plain
   line; Admin keeps the verdict and how many rows differ.
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401
from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard  # noqa: E402
from picks import builder, env, probes  # noqa: E402
from picks.pyrunner import group as pygroup  # noqa: E402
from picks.pyrunner import lookup as pylookup  # noqa: E402
from picks.pyrunner import shape as pyshape  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


def ask(client, v, *, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    return r.status_code, r.json()


# ═════════════════════════════════════════════════════════════════════════
# 1 · One compiler
# ═════════════════════════════════════════════════════════════════════════

def test_the_statement_its_display_and_its_probes_share_one_compiler():
    ship = builder._compile
    assert ship.__file__ == str(_REPO_ROOT / "compiler" / "compile.py")
    assert server_app.compiler is ship, "the display renders with another compiler"
    assert probes._compile_module() is ship, "the probes compile with another compiler"
    assert not any(getattr(m, "__file__", None) == str(_REPO_ROOT / "spikes" / "T-1" / "proto" / "compile.py")
                   for m in list(sys.modules.values())), "the frozen spike compiler is still loaded"


@pytest.mark.parametrize("src", [
    "$.a * $.a > 1", "$.v + 1 == 2", "abs($.v) > 3", "round($.v, 2) >= 1", "number($.s) > 1",
    "$.a / $.b < 2", "-$.a > 0", "$.a % 2 == 1", "floor($.a) > 1", "sum($.l) > 1", "length($.l) > 1",
    "$.x != 3", '$.s == "x"',
])
def test_a_probe_asks_about_each_operand_exactly_as_the_statement_computes_it(src):
    ast = env.get("parser").parse(src)
    for probe in probes.build_probes([ast]):
        ops = (probes.numeric_context_operands(ast) if probe.member == "a"
               else probes.container_check_operands(ast))
        stem = "prbA" if probe.member == "a" else "prbB"
        want = []
        for i, op in enumerate(ops):
            frag = builder._compile.compile_ast(op, ctx_param=f"{stem}{i}_ctx")
            want.append(builder.namespace(frag, f"{stem}{i}")[0])
        assert list(probe.operands) == want, f"{src}: the probe's operand is not the statement's"


# ═════════════════════════════════════════════════════════════════════════
# 2 · No numbers when the engines disagree
# ═════════════════════════════════════════════════════════════════════════

_WORDS = re.compile(r"\b(?:sql|python|engine|statement|pane|query)\b", re.I)


def _nudge(row: dict) -> None:
    """Change one value of one row, the way a wrong second engine would."""
    for k in reversed(list(row)):
        v = row[k]
        if isinstance(v, bool) or k in ("collection", "key", "data"):
            continue
        if isinstance(v, (int, Decimal)):
            row[k] = v + 1
            return
        if isinstance(v, float):
            row[k] = v + 1.0
            return
        if isinstance(v, str):
            row[k] = v + "x"
            return
        if v is None:
            row[k] = Decimal(1)
            return
    raise AssertionError(f"nothing to nudge in {row}")


def _wrong_rows(module, monkeypatch):
    real = module.answer

    def wrong(*a, **k):
        out = real(*a, **k)
        if out["rows"]:
            out["rows"][0] = dict(out["rows"][0])
            _nudge(out["rows"][0])
            if "agg" in out and out["rows"][0].get("agg") is not None:
                out["agg"] = out["rows"][0]["agg"]
        return out

    monkeypatch.setattr(module, "answer", wrong)
    dashboard._CACHE.clear()


def _plain(ds="heartbeats", **kw):
    v = {"dataset": ds, "columns": ["sender_id", "status"], "conditions": [], "sort": None,
         "show": None, "summary": None}
    v.update(kw)
    return v


_CASES = [
    (pyshape, _plain()),                                                                   # rows
    (pyshape, _plain(columns=[], summary={"fn": "avg", "field": "payload.load", "per": "all"})),   # one number
    (pyshape, _plain(columns=[], summary={"fn": "count", "field": None, "per": "day"})),          # a chart
    (pygroup, _plain(columns=[], scoreboard={"by": "status", "counts": []})),             # a board
    (pylookup, _plain(matched={"dataset": "senders", "field": "id", "matches": "sender_id",
                               "columns": ["name"]})),                                    # a matched table
]


@pytest.mark.parametrize("module, view", _CASES, ids=["rows", "number", "chart", "board", "matched"])
def test_a_disagreement_shows_no_numbers(client, monkeypatch, module, view):
    _wrong_rows(module, monkeypatch)
    try:
        status, a = ask(client, view)
        status_e, e = ask(client, view, admin=False)
    finally:
        dashboard._CACHE.clear()
    assert status == 200 and a["kind"] == "refused", f"a disagreeing answer was drawn: {a.get('kind')}"
    assert a["message"] == dashboard.DISAGREED
    assert not {"rows", "number", "bars", "columns"} & set(a), "numbers were shown from a disagreement"
    assert a["admin"]["verdict"] == "disagree" and a["admin"]["differing_rows"] >= 1
    assert status_e == 200 and e["kind"] == "refused" and e["message"] == dashboard.DISAGREED and "admin" not in e
    assert not _WORDS.search(e["message"] + " " + e["sentence"]), e


@pytest.mark.parametrize("module, view", _CASES, ids=["rows", "number", "chart", "board", "matched"])
def test_agreeing_answers_are_drawn_as_before(client, module, view):
    dashboard._CACHE.clear()
    _, a = ask(client, view)
    assert a["kind"] != "refused" and a["admin"]["verdict"] == "agree"
