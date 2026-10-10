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


# ═════════════════════════════════════════════════════════════════════════
# 3 · Owner isolation, before any host with many owners uses picks/ (T-87,
#     widened after T-86's check): the reads, the keys, the row provider,
#     the default, two owners at once
# ═════════════════════════════════════════════════════════════════════════

import json as _json  # noqa: E402
import threading  # noqa: E402

from demo.server import db as _db  # noqa: E402
from picks import view as pview  # noqa: E402
from picks.pyrunner.rows import read_rows  # noqa: E402
from picks.records import Records  # noqa: E402

_T = "t87_owners"
_ROWS = [
    ("acme", "noun:Reading", "r1", {"who": "m1", "v": 2, "kind": "a", "at": "2026-01-05"}),
    ("acme", "noun:Reading", "r2", {"who": "m2", "v": 4, "kind": "b", "at": "2026-01-07"}),
    ("other", "noun:Reading", "r1", {"who": "m9", "v": 7000, "kind": "Elsewhere", "at": "2030-12-31",
                                     "secret": "x"}),
]


def _owner(owner, **kw):
    return Records(table=_T, sources={"noun:Reading": "who, v, kind, at"}, partition=("owner", owner), **kw)


@pytest.fixture
def owners():
    c = _db.connect(application_name="autosql-demo-t87-owners")
    try:
        c.execute(f"CREATE TEMPORARY TABLE {_T} (owner text, collection text, key text, data jsonb, "
                  "PRIMARY KEY (owner, collection, key))")
        for o, coll, k, d in _ROWS:
            c.execute(f"INSERT INTO {_T} VALUES (%s, %s, %s, %s::jsonb)", (o, coll, k, _json.dumps(d)))
        yield c
    finally:
        c.rollback()
        c.close()


def test_the_field_reads_offer_one_owners_values_ranges_and_groups(owners):
    fields = {f["path"]: f for f in pview._read_fields(owners, "noun:Reading", records=_owner("acme"))}
    assert set(fields) == {"who", "v", "kind", "at"}, "another owner's field names were offered"
    assert fields["kind"]["values"] == ["a", "b"], "another owner's values were offered as chips"
    assert fields["v"]["range"] == {"min": "2", "max": "4"}
    assert fields["at"]["range"] == {"min": "2026-01-05", "max": "2026-01-07"}
    assert fields["kind"]["group"]["groups"] == 2


def test_the_keys_a_pick_is_judged_against_are_one_owners(owners):
    assert pview.collection_keys(owners, "noun:Reading", records=_owner("acme")) == ["at", "kind", "v", "who"]
    assert "secret" in pview.collection_keys(owners, "noun:Reading", records=_owner("other"))


def test_the_row_provider_is_handed_the_owner():
    asked = []

    def rows(conn, collection, owner):
        asked.append((collection, owner))
        return [(k, _json.dumps(d)) for o, c, k, d in _ROWS if o == owner and c == collection]

    got = read_rows(None, "noun:Reading", _owner("acme", rows=rows))
    assert asked == [("noun:Reading", "acme")] and sorted(r.key for r in got) == ["r1", "r2"]


def test_a_default_with_an_owner_is_refused():
    with pytest.raises(ValueError, match="cannot carry an owner"):
        env.set_default_records(_owner("acme"))


def test_two_owners_at_once_each_read_only_their_own(owners):
    """Two threads, two owners, one process, records= per call: each sees its own."""
    errors, seen = [], {}
    dsn_conns = {o: _db.connect(application_name=f"autosql-demo-t87-{o}") for o in ("acme", "other")}
    try:
        for c in dsn_conns.values():
            c.execute(f"CREATE TEMPORARY TABLE {_T} (owner text, collection text, key text, data jsonb, "
                      "PRIMARY KEY (owner, collection, key))")
            for o, coll, k, d in _ROWS:
                c.execute(f"INSERT INTO {_T} VALUES (%s, %s, %s, %s::jsonb)", (o, coll, k, _json.dumps(d)))

        def work(owner):
            try:
                r = _owner(owner)
                for _ in range(25):
                    p = dict(legality_default(), source="noun:Reading", aggregate={"fn": "sum", "field": "$.v"})
                    built = builder.build(p, ["who", "v", "kind", "at"], records=r)
                    total = dsn_conns[owner].execute(built.sql, built.params).fetchone()[0]
                    py = pyshape.answer(read_rows(dsn_conns[owner], "noun:Reading", r), p, r)["agg"]
                    seen.setdefault(owner, set()).add((str(Decimal(str(total)).normalize()), str(py.normalize())))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{owner}: {exc!r}")

        threads = [threading.Thread(target=work, args=(o,)) for o in ("acme", "other")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        for c in dsn_conns.values():
            c.rollback()
            c.close()
    assert not errors, errors
    assert seen == {"acme": {("6", "6")}, "other": {("7E+3", "7E+3")}}


def legality_default():
    from picks import legality as _lg
    return _lg.default_pick(_owner("acme"))


# ═════════════════════════════════════════════════════════════════════════
# 4 · The overflow probe never answers 500; number conditions, held directly
# ═════════════════════════════════════════════════════════════════════════

def _edge(**kw):
    from picks import legality as _lg
    return dict(_lg.default_pick(), source="noun:EdgeCase", **kw)


@pytest.mark.parametrize("pick", [
    _edge(filter="abs($.huge) > 1"),
    *[_edge(computed=[{"name": "x", "expr": "$.g * 3"}], aggregate={"fn": fn, "field": "x"})
      for fn in ("sum", "avg", "min", "max")],
], ids=["abs-huge", "sum-g3", "avg-g3", "min-g3", "max-g3"])
def test_a_probe_that_meets_an_out_of_range_number_refuses_by_name(client, pick):
    """The probe's own operand computes with a number past the largest double
    and the runtime refuses it: that IS the probe's answer (it fired).  Until
    T-87 these answered 500."""
    r = client.post("/api/pick", json=pick)
    assert r.status_code == 422, f"answered {r.status_code}"
    refusal = r.json()["refusal"]
    assert refusal["kind"] == "probe" and refusal["member"] == "a"
    assert refusal["why"].startswith("out-of-range magnitude")


@pytest.mark.parametrize("op, value, sql", [
    ("gt", 42, "(data #>> '{payload,load}')::numeric > 42"),
    ("ne", 42, "(data #>> '{payload,load}') IS NULL OR (data #>> '{payload,load}')::numeric <> 42"),
    ("ge", 42, "(data #>> '{payload,load}')::numeric >= 42"),
])
def test_a_number_condition_counts_what_hand_sql_counts(client, op, value, sql):
    """"is more than" excludes the value, "is not" counts the rows without
    one, "is at least" includes it — each against hand-written SQL (42 has
    rows, so a wrong edge shows)."""
    c = _db.connect(application_name="autosql-demo-t87-numbers")
    try:
        want = c.execute(f"SELECT count(*) FROM demo.records WHERE collection = 'noun:Heartbeat' AND ({sql})").fetchone()[0]
        has_42 = c.execute("SELECT count(*) FROM demo.records WHERE collection = 'noun:Heartbeat' "
                           "AND (data #>> '{payload,load}')::numeric = 42").fetchone()[0]
    finally:
        c.rollback()
        c.close()
    assert has_42 > 0
    v = {"dataset": "heartbeats", "columns": [], "conditions": [{"field": "payload.load", "op": op, "value": value}],
         "sort": None, "show": None, "summary": {"fn": "count", "field": None, "per": "all"}}
    dashboard._CACHE.clear()
    _, a = ask(client, v)
    assert a["kind"] == "number" and int(a["number"]["exact"]) == want
