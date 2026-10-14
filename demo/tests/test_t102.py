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
    from picks import builder, legality, probes
    C = _compiler()
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "filter": "($.payload.load + $.payload.load + $.payload.load) == 1"})
    statement = len(builder.build(p, ["sender_id", "ts", "status", "payload"]).sql)
    ops = probes.numeric_context_operands(env.get("parser").parse(p["filter"]))
    operand = max(len(C.compile_ast(o, time_zones=frozenset()).sql) for o in ops)
    assert operand > statement, (operand, statement)      # the probe's piece is the bigger one
    monkeypatch.setattr(C, "MAX_SQL_CHARS", statement)    # the statement fits exactly; the probe can't
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


# ═════════════════════════════════════════════════════════════════════════
# The fix round (a-chk on d9ee86c): the budget is for the whole STATEMENT, as it is assembled
# ═════════════════════════════════════════════════════════════════════════

#: In the caged child: psycopg refuses to SEND a statement over the budget, so a regression fails
#: the test there and never puts a 2-million-character statement on the shared database.
_NEVER_SEND_BIG = '''
import psycopg, time
_real = psycopg.Cursor.execute
def _guarded(self, query, *a, **k):
    if isinstance(query, str) and len(query) > 200_000:
        raise RuntimeError(f"a statement of {len(query):,} characters was about to be sent")
    return _real(self, query, *a, **k)
psycopg.Cursor.execute = _guarded
'''


def test_a_board_whose_pieces_each_fit_but_whose_statement_does_not_is_refused_before_it_is_sent():
    """a-chk: a page filter and 6 count columns, each piece just under the budget, made ONE statement
    of 2,038,322 characters (25 s and +504 MB in Postgres, as Everyone)."""
    got = _caged(_PRELUDE + _NEVER_SEND_BIG + '''
def one(d, k=0):
    t = card("ok")
    for i in range(d):
        t = {"join": "one", "items": [t, card(["warn", "error", "ok"][(i + k) % 3])]}
    return t
def towers(n):
    return {"version": 1, "join": "any", "items": [one(2, k) for k in range(n)]}
counts = [{"label": f"C{i}", "pct": bool(i % 2), "filter": towers(2)} for i in range(6)]
t0 = time.time()
ask("the board", view(columns=[], filter=towers(2), scoreboard={"by": "status", "counts": counts}))
ask("the board, Admin", view(columns=[], filter=towers(2), scoreboard={"by": "status", "counts": counts}), admin=True)
print(json.dumps({"seconds": round(time.time() - t0, 2)}), flush=True)
''', timeout=180)
    answers, timing = got[:-1], got[-1]
    for g in answers:
        assert g["status"] in (200, 422) and g["message"] == TOO_BIG, g
    assert timing["seconds"] < 30, timing


def test_ten_computed_columns_on_the_two_pane_screen_are_refused_before_they_are_sent():
    """a-chk: computed columns have no count limit; 10 made a 2,068,421-character statement (340 s and
    +2.6 GB in Postgres before a timeout cut it); 200 made 42M characters from a 49 KB request."""
    got = _caged(_PRELUDE + _NEVER_SEND_BIG + '''
from picks import legality
d1 = '(if($.status == "ok", 1, 0) + if($.status == "warn", 1, 0)) == 1'
d2 = f'(if({d1}, 1, 0) + if($.status == "error", 1, 0)) == 1'
for n in (10, 200):
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "computed": [{"name": f"k{i}", "expr": d2} for i in range(n)]})
    t0 = time.time()
    r = c.post("/api/pick", json=p)
    ref = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("refusal") or {}
    print(json.dumps({"n": n, "status": r.status_code, "kind": ref.get("kind"), "why": ref.get("why"),
                      "seconds": round(time.time() - t0, 2)}), flush=True)
''', timeout=180)
    assert [g["n"] for g in got] == [10, 200], got
    for g in got:
        assert g["status"] == 422 and g["kind"] == "size" and "too big to check" in (g["why"] or ""), g
        assert g["seconds"] < 20, g


def test_the_statements_budget_is_exact_at_its_edge(monkeypatch):
    """A statement of exactly the budget is built; one character over is refused -- the TOTAL, not a piece."""
    import gate
    from picks import builder, legality
    C = _compiler()
    d1 = '(if($.status == "ok", 1, 0) + if($.status == "warn", 1, 0)) == 1'
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "computed": [{"name": f"k{i}", "expr": d1} for i in range(3)],
              "filter": '$.status == "ok"'})
    keys = ["sender_id", "ts", "status", "payload"]
    size = len(builder.build(p, keys).sql)
    assert size > 3 * 20_000 // 10, size        # three pieces and a filter: well over any one piece
    monkeypatch.setattr(C, "MAX_SQL_CHARS", size)
    assert len(builder.build(p, keys).sql) == size
    monkeypatch.setattr(C, "MAX_SQL_CHARS", size - 1)
    with pytest.raises(gate.Refused) as e:
        builder.build(p, keys)
    assert "too big to check" in e.value.why


def test_every_compiler_method_that_returns_sql_is_measured():
    """a-chk's C1 (`_j` unmeasured) and C2 (`_eq_sql`, `_inline_coerce` unmeasured) survived: each was
    still bounded by another measured layer. Every one of them is measured itself."""
    C = _compiler()
    for name in ("_j", "_f8", "_num", "_truthy", "_str", "predicate", "_eq_sql", "_inline_coerce",
                 "_build_array", "_zone"):
        assert hasattr(getattr(C._Compiler, name), "__wrapped__"), f"_Compiler.{name} is not measured"


def test_the_total_stops_the_build_at_the_piece_that_passes_it(monkeypatch):
    """A running total, not only a final measurement: 200 computed columns, each a large piece,
    stop compiling once the total passes the budget -- not after all 200 exist."""
    import gate
    from picks import builder, legality
    calls = []
    real = builder.compile_ast
    monkeypatch.setattr(builder, "compile_ast", lambda *a, **k: calls.append(1) or real(*a, **k))
    d1 = '(if($.status == "ok", 1, 0) + if($.status == "warn", 1, 0)) == 1'
    d2 = f'(if({d1}, 1, 0) + if($.status == "error", 1, 0)) == 1'
    p = legality.default_pick()
    p.update({"source": "noun:Heartbeat", "computed": [{"name": f"k{i}", "expr": d2} for i in range(200)]})
    with pytest.raises(gate.Refused):
        builder.build(p, ["sender_id", "ts", "status", "payload"])
    assert len(calls) <= 3, f"{len(calls)} pieces were compiled before the total stopped the build"
