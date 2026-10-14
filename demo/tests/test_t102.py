"""T-102 — the compiler keeps a running size budget: nested comparisons can't build gigabytes of SQL.

Found by asql-a-chk checking T-96 S1 (GA-69): nested "exactly one of" boxes pass every page limit,
but the compiler wrote each operand of an ``==`` several times over and checked its 200,000-character
cap only once the whole statement was built. Depth 6 (a 257-character filter) became 216M characters
of SQL; depth 7, 1.5 billion; depth 8 ran out of memory -- a 500 for Everyone through
/api/dashboard/answer, and the same for a typed filter on the two-pane screen.

The dangerous cases run in a SUBPROCESS capped at 1.5 GB of address space and a timeout, so a
regression fails this test, not the machine.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401
from picks import env  # noqa: E402

TOO_BIG = "This filter is too big to check. Take out a group."
CAGE_BYTES = 1_500_000_000


def _caged(code: str, timeout: int = 240) -> list:
    """Run ``code`` in a fresh interpreter capped at 1.5 GB and ``timeout`` seconds; it prints one
    JSON line per answer.  A crash, a kill or a hang fails here, by name."""
    def cap():
        resource.setrlimit(resource.RLIMIT_AS, (CAGE_BYTES, CAGE_BYTES))
    try:
        r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout, preexec_fn=cap,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        pytest.fail(f"still compiling after {timeout} s: the budget did not stop it")
    assert r.returncode == 0, (f"the caged process died (exit {r.returncode}) — it ran past 1.5 GB or "
                               f"crashed:\n{r.stderr[-1500:]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]


_PRELUDE = '''
import json, sys
sys.path[:0] = [".", "demo"]
import demo.picks_host
from fastapi.testclient import TestClient
from demo.server import app as server_app
c = TestClient(server_app.app, raise_server_exceptions=False)

def card(v):
    return {"field": "status", "op": "eq", "value": v, "value2": "", "values": []}

def nested(depth, join="one"):
    t = card("ok")
    for i in range(depth):
        t = {"join": join, "items": [t, card(["warn", "error", "ok"][i % 3])]}
    return {"version": 1, "join": "all", "items": [t]}

def view(**kw):
    v = {"dataset": "heartbeats", "columns": ["sender_id", "ts"], "sort": None, "show": None, "summary": None}
    v.update(kw)
    return v

def ask(name, v, admin=False):
    r = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    print(json.dumps({"name": name, "status": r.status_code, "kind": body.get("kind"),
                      "message": body.get("message")}), flush=True)
'''


@pytest.mark.parametrize("depth", [7, 8])
def test_nested_exactly_one_of_is_refused_in_words_on_every_path(depth):
    got = _caged(_PRELUDE + f'''
f = nested({depth})
ask("rows", view(filter=f))
ask("rows, Admin", view(filter=f), admin=True)
ask("a count column", view(columns=[], scoreboard={{"by": "sender_id", "counts": [{{"label": "Odd", "pct": False, "filter": f}}]}}))
ask("a summary per hour", view(columns=[], filter=f, summary={{"fn": "count", "field": None, "per": "hour"}}))
ask("columns from another data set", view(filter=f, matched={{"dataset": "senders", "field": "id", "matches": "sender_id", "columns": ["name"]}}))
''')
    assert [g["name"] for g in got] == ["rows", "rows, Admin", "a count column", "a summary per hour",
                                        "columns from another data set"], got
    for g in got:
        assert g["status"] in (200, 422) and g["message"] == TOO_BIG, g


def test_a_typed_filter_on_the_two_pane_screen_is_refused_by_name():
    got = _caged(_PRELUDE + '''
from picks import legality
x = '$.status == "ok"'
for i in range(8):
    x = f'(if({x}, 1, 0) + if($.status == "warn", 1, 0)) == 1'
p = legality.default_pick(); p.update({"source": "noun:Heartbeat", "filter": x})
r = c.post("/api/pick", json=p)
ref = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("refusal") or {}
print(json.dumps({"status": r.status_code, "kind": ref.get("kind"), "why": ref.get("why"),
                  "body": ref.get("body"), "chars": len(x)}), flush=True)
''')
    (g,) = got
    assert g["chars"] < 2000 and g["status"] == 422, g
    assert g["kind"] == "size" and "too big to check" in (g["why"] or ""), g
    assert "outside the safe subset" not in (g["body"] or ""), g


# ── the edge, exactly ────────────────────────────────────────────────────────

def _compiler():
    return env.get("compiler")


def test_the_budget_is_exact_at_its_edge(monkeypatch):
    """A statement of exactly the budget compiles; one character over is refused, by size, mid-build."""
    C = _compiler()
    ast = env.get("parser").parse('(if($.a == 1, 1, 0) + if($.b == "x", 1, 0)) == 1')
    size = len(C.compile_predicate(ast).sql)
    monkeypatch.setattr(C, "MAX_SQL_CHARS", size)
    assert len(C.compile_predicate(ast).sql) == size
    monkeypatch.setattr(C, "MAX_SQL_CHARS", size - 1)
    with pytest.raises(C.TooBig):
        C.compile_predicate(ast)


def test_the_budget_stops_the_build_before_it_grows():
    """Depth 12 would be terabytes: refused while each part is still small."""
    got = _caged('''
import json, resource, sys, time
sys.path[:0] = [".", "demo"]
import demo.picks_host
from picks import env
C, P = env.get("compiler"), env.get("parser")
x = '$.a == 1'
out = []
for d in range(1, 13):
    x = f'(if({x}, 1, 0) + if($.b == 2, 1, 0)) == 1'
    t0 = time.time()
    try:
        n = len(C.compile_predicate(P.parse(x)).sql); verdict = "compiled"
    except C.TooBig:
        n, verdict = 0, "too big"
    out.append({"depth": d, "verdict": verdict, "chars": n, "seconds": round(time.time() - t0, 3),
                "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024})
print(json.dumps({"ladder": out}), flush=True)
''')
    ladder = got[0]["ladder"]
    assert any(s["verdict"] == "too big" for s in ladder), ladder
    for s in ladder:
        assert s["chars"] <= 200_000 and s["seconds"] < 5, s
    assert max(s["rss_mb"] for s in ladder) < 400, ladder


# ── a probe's operand, compiled on its own, can pass the budget the statement fit ──

def _client():
    from fastapi.testclient import TestClient
    from demo.server import app as server_app
    return TestClient(server_app.app, raise_server_exceptions=False)


def test_a_probe_operand_too_big_to_check_refuses_the_pick_by_name(monkeypatch):
    """Inside an `==` an operand is compiled compactly; a probe compiles it on its own, inline, and
    it comes out larger (measured: 3,905 characters against the whole filter's 2,176). With the
    budget between the two the statement is built and the probe is not: refused, never a 500."""
    from picks import legality
    C = _compiler()
    monkeypatch.setattr(C, "MAX_SQL_CHARS", 3000)
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "filter": "($.payload.load + $.payload.load + $.payload.load) == 1"})
    r = _client().post("/api/pick", json=p)
    assert r.status_code == 422, r.text[:300]
    ref = r.json()["refusal"]
    assert ref["kind"] == "size" and "too big to check" in ref["why"], ref


@pytest.mark.parametrize("which", ["a count column", "columns from another data set"])
def test_a_board_or_a_match_whose_probe_is_too_big_says_so_in_words(monkeypatch, which):
    import gate
    from picks import builder, probes

    def too_big(*a, **k):
        raise gate.Refused("x", builder.too_big_words())
    monkeypatch.setattr(probes, "check", too_big)
    c = _client()
    card = {"field": "payload.load", "op": "gt", "value": 50, "value2": "", "values": []}
    tree = {"version": 1, "join": "all", "items": [card]}
    v = {"dataset": "heartbeats", "columns": ["sender_id"], "sort": None, "show": None, "summary": None}
    if which == "a count column":
        v.update(columns=[], scoreboard={"by": "sender_id", "counts": [{"label": "Hot", "pct": False, "filter": tree}]})
    else:
        v.update(filter=tree, matched={"dataset": "senders", "field": "id", "matches": "sender_id", "columns": ["name"]})
    r = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": False})
    assert r.status_code in (200, 422) and r.json().get("message") == TOO_BIG, r.text[:300]
