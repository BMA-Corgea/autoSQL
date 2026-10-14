"""demo/tests/test_t96.py — T-96 S1: the filter as a tree of boxes, any depth (the engine slice).

The tree composes into ONE expression of the language both engines share, so a defect in the
recursion breaks the statement and the second engine the same way and they still agree.  What
catches it here is what neither engine computes:

* **truth tables** over four yes/no fields (all 16 combinations, a row without ``a``, a row
  without anything): every tree's kept rows from the statement, from the second engine, from
  hand-written SQL and from a hand-written Python predicate — all four equal;
* the outcome on the demo's own data against hand-written SQL, and the sentence with brackets;
* the old flat ``{conditions, logic}`` and its one-box tree give the same answer, word for word;
* every refusal in its own words, and the limits at their exact edges (the parser's length and
  depth, and the tree's own depth), never a parse error on screen;
* the Everyone view's hidden fields refused at any depth; a count column's tree.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "demo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import demo.picks_host  # noqa: E402,F401
from demo.server import app as server_app  # noqa: E402
from demo.server import db  # noqa: E402
from picks import builder, env  # noqa: E402
from picks import view as pview  # noqa: E402
from picks.pyrunner import shape as pyshape  # noqa: E402
from picks.pyrunner.rows import read_rows  # noqa: E402
from picks.records import Records  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    r = client.get("/api/dashboard/setup?view=admin")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-t96")
    server_app.refuse_writes(c)
    yield c
    c.close()


def ask(client, v, *, admin=True):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": admin})
    return r.status_code, r.json()


def card(field, op, value="", value2="", values=None):
    return {"field": field, "op": op, "value": value, "value2": value2, "values": values or []}


def box(join, *items):
    return {"join": join, "items": list(items)}


def tree(join, *items):
    return {"version": 1, "join": join, "items": list(items)}


def view(setup, ds_id="heartbeats", **kw):
    d = next(x for x in setup["datasets"] if x["id"] == ds_id)
    v = {"dataset": ds_id, "columns": list(d["default_columns"]), "sort": None, "show": None, "summary": None}
    v.update(kw)
    return v


# ═════════════════════════════════════════════════════════════════════════
# 1 · Truth tables, both engines, against hand-written SQL and Python
# ═════════════════════════════════════════════════════════════════════════

_RECORDS = {"r" + "".join("1" if b else "0" for b in bits): dict(zip("abcd", bits))
            for bits in itertools.product([False, True], repeat=4)}
_RECORDS["rx"] = {"b": True, "c": True, "d": True}       # no a
_RECORDS["rz"] = {}                                      # nothing


def Y(f):
    return card(f, "yes")


def N(f):
    return card(f, "no")


def _ys(f):
    return f"(data -> '{f}') = 'true'::jsonb"


def _ns(f):
    return f"(data -> '{f}') = 'false'::jsonb"


def _sum(*sqls):
    return "(" + " + ".join(f"CASE WHEN {s} THEN 1 ELSE 0 END" for s in sqls) + ")"


def y(r, f):
    return r.get(f) is True


def n(r, f):
    return r.get(f) is False


#: name → (tree, hand-written WHERE, hand-written predicate)
_TABLES = {
    "a AND (b OR c)": (
        tree("all", Y("a"), box("any", Y("b"), Y("c"))),
        f"{_ys('a')} AND ({_ys('b')} OR {_ys('c')})",
        lambda r: y(r, "a") and (y(r, "b") or y(r, "c"))),
    "(a OR b) AND (c OR d)": (
        tree("all", box("any", Y("a"), Y("b")), box("any", Y("c"), Y("d"))),
        f"({_ys('a')} OR {_ys('b')}) AND ({_ys('c')} OR {_ys('d')})",
        lambda r: (y(r, "a") or y(r, "b")) and (y(r, "c") or y(r, "d"))),
    "a OR (b AND (c OR d))": (
        tree("any", Y("a"), box("all", Y("b"), box("any", Y("c"), Y("d")))),
        f"{_ys('a')} OR ({_ys('b')} AND ({_ys('c')} OR {_ys('d')}))",
        lambda r: y(r, "a") or (y(r, "b") and (y(r, "c") or y(r, "d")))),
    "a AND exactly one of (b, c, d)": (
        tree("all", Y("a"), box("one", Y("b"), Y("c"), Y("d"))),
        f"{_ys('a')} AND {_sum(_ys('b'), _ys('c'), _ys('d'))} = 1",
        lambda r: y(r, "a") and sum([y(r, "b"), y(r, "c"), y(r, "d")]) == 1),
    "all or none of (a, b) OR d is no": (
        tree("any", box("allnone", Y("a"), Y("b")), N("d")),
        f"({_sum(_ys('a'), _ys('b'))} IN (0, 2)) OR {_ns('d')}",
        lambda r: sum([y(r, "a"), y(r, "b")]) in (0, 2) or n(r, "d")),
    "five boxes deep": (
        tree("all", Y("a"), box("any", N("b"), box("all", Y("c"), box("any", N("d"), box(
            "all", Y("b"), box("any", Y("d"), N("c"))))))),
        f"{_ys('a')} AND ({_ns('b')} OR ({_ys('c')} AND ({_ns('d')} OR ({_ys('b')} AND "
        f"({_ys('d')} OR {_ns('c')})))))",
        lambda r: y(r, "a") and (n(r, "b") or (y(r, "c") and (n(r, "d") or (y(r, "b") and (
            y(r, "d") or n(r, "c"))))))),
    "a group of one": (
        tree("all", Y("a"), box("any", Y("b"))),
        f"{_ys('a')} AND {_ys('b')}",
        lambda r: y(r, "a") and y(r, "b")),
    "an empty group beside a card": (
        tree("any", Y("a"), box("all")),
        _ys("a"),
        lambda r: y(r, "a")),
    # an empty group adds nothing: counted as false it would empty an AND (a-chk's VD) …
    "a AND an empty group": (
        tree("all", Y("a"), box("any")),
        _ys("a"),
        lambda r: y(r, "a")),
    # … and make "all or none" mean "none"
    "all or none of (a, b, an empty group)": (
        tree("allnone", Y("a"), Y("b"), box("all")),
        f"{_sum(_ys('a'), _ys('b'))} IN (0, 2)",
        lambda r: sum([y(r, "a"), y(r, "b")]) in (0, 2)),
    "exactly one of (a, b) OR (c AND d)": (
        tree("any", box("one", Y("a"), Y("b")), box("all", Y("c"), Y("d"))),
        f"{_sum(_ys('a'), _ys('b'))} = 1 OR ({_ys('c')} AND {_ys('d')})",
        lambda r: sum([y(r, "a"), y(r, "b")]) == 1 or (y(r, "c") and y(r, "d"))),
    "d AND all or none of (a, b, c)": (
        tree("all", Y("d"), box("allnone", Y("a"), Y("b"), Y("c"))),
        f"{_ys('d')} AND {_sum(_ys('a'), _ys('b'), _ys('c'))} IN (0, 3)",
        lambda r: y(r, "d") and sum([y(r, "a"), y(r, "b"), y(r, "c")]) in (0, 3)),
    "a is no AND (b OR exactly one of (c, d, b is no))": (
        tree("all", N("a"), box("any", Y("b"), box("one", Y("c"), Y("d"), N("b")))),
        f"{_ns('a')} AND ({_ys('b')} OR {_sum(_ys('c'), _ys('d'), _ns('b'))} = 1)",
        lambda r: n(r, "a") and (y(r, "b") or sum([y(r, "c"), y(r, "d"), n(r, "b")]) == 1)),
    "exactly one of (a, (b AND c), all or none of (b, d))": (
        tree("one", Y("a"), box("all", Y("b"), Y("c")), box("allnone", Y("b"), Y("d"))),
        f"{_sum(_ys('a'), f'({_ys(chr(98))} AND {_ys(chr(99))})', f'({_sum(_ys(chr(98)), _ys(chr(100)))} IN (0, 2))')} = 1",
        lambda r: sum([y(r, "a"), y(r, "b") and y(r, "c"),
                       sum([y(r, "b"), y(r, "d")]) in (0, 2)]) == 1),
}


@pytest.fixture(scope="module")
def truth():
    """A connection holding the 18 records in a TEMPORARY table (gone at the end)."""
    c = db.connect(application_name="autosql-demo-t96-truth")
    c.execute("CREATE TEMPORARY TABLE t96_truth (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    for k, d in _RECORDS.items():
        c.execute("INSERT INTO t96_truth VALUES ('noun:T', %s, %s::jsonb)", (k, json.dumps(d)))
    records = Records(table="t96_truth", sources={"noun:T": "a, b, c, d"})
    fields = {f["path"]: f for f in pview._read_fields(c, "noun:T", records=records)}
    yield c, records, fields
    c.rollback()
    c.close()


def _kept_by_both(c, records, expr):
    pick = {"source": "noun:T", "computed": [], "filter": expr, "sort": None, "cap": None, "window": None,
            "changed": False, "bucket": "off"}
    built = builder.build(pick, pview.collection_keys(c, "noun:T", records=records), records=records)
    sql = sorted(r[1] for r in c.execute(built.sql, built.params).fetchall())
    py = sorted(r["key"] for r in pyshape.answer(read_rows(c, "noun:T", records), pick, records)["rows"])
    return sql, py


@pytest.mark.parametrize("name", list(_TABLES))
def test_a_tree_keeps_what_its_truth_table_keeps_in_both_engines(truth, name):
    c, records, fields = truth
    t, where, holds = _TABLES[name]
    expr = pview.filter_expression({"filter": t}, fields)
    sql, py = _kept_by_both(c, records, expr)
    hand_sql = sorted(r[0] for r in c.execute(
        f"SELECT key FROM t96_truth WHERE collection = 'noun:T' AND ({where})").fetchall())
    hand = sorted(k for k, r in _RECORDS.items() if holds(r))
    assert 0 < len(hand) < len(_RECORDS), "this tree tells no rows apart"
    assert hand_sql == hand, "the hand-written SQL and the hand-written predicate disagree (the test is wrong)"
    assert (sql, py) == (hand, hand), f"{name}: kept {sql} (statement), {py} (second engine), want {hand}"


# ═════════════════════════════════════════════════════════════════════════
# 2 · The outcome, on the demo's own data
# ═════════════════════════════════════════════════════════════════════════

_AUG20 = card("ts", "on", "2026-08-20")
_WARN, _ERROR = card("status", "eq", "warn"), card("status", "eq", "error")


def test_time_on_aug_20_and_warn_or_error(client, setup, conn):
    want = conn.execute("""
        SELECT count(*) FROM demo.records WHERE collection = 'noun:Heartbeat'
           AND data->>'ts' >= '2026-08-20T00:00:00Z' AND data->>'ts' < '2026-08-21T00:00:00Z'
           AND (data->>'status' = 'warn' OR data->>'status' = 'error')""").fetchone()[0]
    st, a = ask(client, view(setup, filter=tree("all", _AUG20, box("any", _WARN, _ERROR))))
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    assert a["total"] == want == 147
    assert "where Time is on Aug 20 and (Status is warn or Status is error)" in a["sentence"], a["sentence"]


def test_a_nested_one_of_reads_in_brackets(client, setup):
    st, a = ask(client, view(setup, filter=tree("any", _AUG20, box("one", _WARN, _ERROR, card("payload.load", "gt", 50)))),
                admin=False)
    assert st == 200, a
    assert ("where Time is on Aug 20 or (exactly one of: Status is warn, Status is error and Load is more than 50)"
            in a["sentence"]), a["sentence"]


def test_a_group_of_one_reads_without_brackets(client, setup):
    st, a = ask(client, view(setup, filter=tree("all", _AUG20, box("any", _WARN))), admin=False)
    assert st == 200 and a["sentence"].startswith("Heartbeats where Time is on Aug 20 and Status is warn"), a


# ═════════════════════════════════════════════════════════════════════════
# 3 · The old flat form is a one-box tree: same answer, word for word
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("logic, conds", [
    ("all", [_WARN]),
    ("any", [_WARN, _ERROR]),
    ("all", [_AUG20, card("payload.load", "gt", 50)]),
    ("one", [_WARN, _AUG20, card("payload.load", "le", 20)]),
    ("allnone", [_ERROR, _AUG20]),
])
def test_the_old_flat_form_and_its_one_box_tree_answer_alike(client, setup, logic, conds):
    st_old, old = ask(client, view(setup, conditions=conds, logic=logic))
    st_new, new = ask(client, view(setup, filter=tree(logic, *conds)))
    assert st_old == st_new == 200, (old, new)
    for k in ("sentence", "total"):
        assert old[k] == new[k], k
    assert old["admin"]["statement"] == new["admin"]["statement"]


# ═════════════════════════════════════════════════════════════════════════
# 4 · Refusals, each in its own words
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("patch, says", [
    ({"filter": {"version": 2, "join": "all", "items": []}}, "This page reads filters of version 1."),
    ({"filter": {"version": True, "join": "all", "items": []}}, "This page reads filters of version 1."),
    ({"filter": {"join": "all", "items": []}}, "This page reads filters of version 1."),
    ({"filter": "status is warn"}, "A filter must be a set of choices."),
    ({"filter": {"version": 1, "join": "all", "items": [], "x": 1}}, "This page can't use 'x' in a filter yet."),
    ({"filter": {"version": 1, "join": "all", "items": {}}}, "A filter's items must be a list."),
    ({"filter": tree("all", _WARN, {"join": "any", "items": [_ERROR], "label": "G"})},
     "This page can't use 'label' in a group yet."),
    ({"filter": tree("all", _WARN, {"join": "any", "items": "x"})}, "A group's items must be a list."),
    ({"filter": tree("all", _WARN, box("one", _ERROR))}, "“Exactly one of these” needs two or more conditions."),
    ({"filter": tree("all", _WARN, box("allnone"))}, "“All of these, or none of them” needs two or more conditions."),
    ({"filter": tree("all", _WARN, box("most", _ERROR, _AUG20))},
     "A group joins its conditions by all, any, exactly one, or all or none."),
    ({"filter": tree("all", box("any", box("all", card("nowhere", "eq", "x"))))},
     "A condition names a field this data set doesn't have."),
    ({"filter": tree("all", box("any", "status is warn"))}, "A condition names a field this data set doesn't have."),
    ({"filter": tree("all", _WARN), "conditions": [_ERROR]}, "A question sends its filter once."),
    ({"filter": tree("all", _WARN), "logic": "any"}, "A question sends its filter once."),
])
def test_what_a_tree_cannot_be_is_refused_by_name(client, setup, patch, says):
    st, a = ask(client, view(setup, **patch))
    assert st == 422, a
    assert a["message"] == says, a["message"]


# ═════════════════════════════════════════════════════════════════════════
# 5 · The limits, at their exact edges, in words
# ═════════════════════════════════════════════════════════════════════════

def _depth(text: str) -> int:
    """The parser's depth of a text, counted by hand: an atom is 1 + the brackets and calls
    around it (a call's own bracket is one of them).  Quote-aware."""
    depth = best = 0
    i, quote = 0, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif not ch.isspace():
            best = max(best, depth + 1)
        i += 1
    return best


def _raw(t, fields):
    return pview._box({"join": t["join"], "items": t["items"]}, fields, "Only rows where")[0]


def _heartbeat_fields(setup):
    return {f["path"]: f for f in next(d for d in setup["datasets"] if d["id"] == "heartbeats")["fields"]}


def _long(setup, length):
    """An OR of Status cards whose composed text is exactly ``length`` characters."""
    fields = _heartbeat_fields(setup)
    cards = [card("status", "eq", "w" * 40) for _ in range(25)]
    base = len(_raw(tree("any", *cards), fields))
    pad = length - base
    assert pad > -40, "the base tree is already too long for this length"
    cards[-1] = card("status", "eq", "w" * (40 + min(pad, 2000 - base)))
    t = tree("any", *cards)
    assert len(_raw(t, fields)) == min(length, 2000)
    if length > 2000:
        # one more character in one value: the text is one longer (it can't be composed to measure it)
        t["items"][-1] = card("status", "eq", t["items"][-1]["value"] + "w" * (length - 2000))
    return t


def test_a_filter_of_2000_characters_is_answered_and_2001_refused_in_words(client, setup):
    st, a = ask(client, view(setup, filter=_long(setup, 2000)))
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    st, a = ask(client, view(setup, filter=_long(setup, 2001)))
    assert (st, a.get("message")) == (422, pview.TOO_LONG), a


def _nest(levels: int, inner):
    """``levels`` boxes, each holding a card and the next box: every level adds brackets."""
    t = inner
    for i in range(levels):
        t = box("any" if i % 2 else "all", _WARN, t)
    return t


def _at_depth(setup, want: int):
    """A tree whose composed text is exactly ``want`` deep, by the hand count."""
    fields = _heartbeat_fields(setup)
    for inner in (_WARN, _AUG20, card("status", "in", values=["warn", "error"])):
        for levels in range(1, 80):
            t = tree("all", _nest(levels, inner))
            d = _depth(_raw(t, fields))
            if d == want:
                return t
            if d > want:
                break
    raise AssertionError(f"no tree here is exactly {want} deep")


def test_the_parsers_depth_64_is_answered_and_65_refused_in_words(client, setup):
    fields = _heartbeat_fields(setup)
    parse = env.get("parser").parse
    t64, t65 = _at_depth(setup, 64), _at_depth(setup, 65)
    parse(_raw(t64, fields))                      # the parser takes 64 …
    with pytest.raises(Exception, match="nesting"):
        parse(_raw(t65, fields))                  # … and refuses 65: the hand count is the parser's
    st, a = ask(client, view(setup, filter=t64))
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    st, a = ask(client, view(setup, filter=t65))
    assert (st, a.get("message")) == (422, pview.TOO_DEEP), f"65 deep was not refused in words: {st} {a.get('message')}"


def _chain(levels: int):
    t = _WARN
    for _ in range(levels):
        t = box("all", t)
    return tree("all", t)


def test_a_tree_64_groups_deep_is_answered_and_65_refused_in_words(client, setup):
    """Groups of one add no brackets, so the text can't bound the tree: the tree's own depth is
    checked first, without recursion, so a hostile one is refused in words, never by a stack."""
    st, a = ask(client, view(setup, filter=_chain(64)))       # 64 groups inside groups
    assert st == 200 and a["total"] == ask(client, view(setup, conditions=[_WARN]))[1]["total"], a
    st, a = ask(client, view(setup, filter=_chain(65)))   # 65
    assert (st, a.get("message")) == (422, pview.TOO_DEEP), a
    st, a = ask(client, view(setup, filter=_chain(900)))
    assert (st, a.get("message")) == (422, pview.TOO_DEEP), a
    # deeper than any JSON reader goes: the body itself is turned away (400), never a 500
    deep = ('{"view": {"dataset": "heartbeats", "columns": [], "sort": null, "show": null, "summary": null, '
            '"filter": {"version": 1, "join": "all", "items": [' + '{"join": "all", "items": [' * 5000
            + json.dumps(_WARN) + ']}' * 5000 + ']}}, "page": 0, "admin": true}')
    r = client.post("/api/dashboard/answer", content=deep, headers={"content-type": "application/json"})
    assert r.status_code == 400, r.text[:200]


# ═════════════════════════════════════════════════════════════════════════
# 6 · Everyone: a hidden field is refused at any depth
# ═════════════════════════════════════════════════════════════════════════

def test_a_hidden_field_four_groups_deep_is_refused_for_everyone(client, setup):
    deep = tree("all", box("any", box("all", box("any", card("label", "eq", "x"), card("label", "eq", "y")))))
    v = view(setup, "edge", columns=[], filter=deep)
    st, a = ask(client, v, admin=False)
    assert (st, a.get("message")) == (422, "Label isn't offered in this view."), a
    st, a = ask(client, v)
    assert st == 200, a


# ═════════════════════════════════════════════════════════════════════════
# 7 · A scoreboard's count column takes the same tree
# ═════════════════════════════════════════════════════════════════════════

def test_a_count_columns_tree_equals_hand_sql(client, setup, conn):
    want = dict(conn.execute("""
        SELECT data->>'sender_id',
               count(*) FILTER (WHERE data->>'status' = 'warn'
                                 OR ((data #>> '{payload,load}')::numeric > 50 AND data->>'status' = 'error'))
          FROM demo.records WHERE collection = 'noun:Heartbeat' GROUP BY 1""").fetchall())
    count = {"label": "Hot", "pct": False,
             "filter": tree("any", _WARN, box("all", card("payload.load", "gt", 50), _ERROR))}
    v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": None, "summary": None,
         "scoreboard": {"by": "sender_id", "counts": [count]}}
    st, a = ask(client, v)
    assert st == 200 and a["admin"]["verdict"] == "agree", a
    ids = [c["id"] for c in a["columns"]]
    got = {r[ids.index("group")]: int(r[ids.index("count:1")]) for r in a["rows"]}
    assert got == want, "a count column's tree counted other rows than hand SQL"


# ═════════════════════════════════════════════════════════════════════════
# 8 · A filter's size is checked before it is built (the foreman's HIGH, availability)
# ═════════════════════════════════════════════════════════════════════════
#
# "All or none of" writes its sum twice, so one inside another doubles the text at every level: 40 of
# them would be ~2^40 characters. It must be refused in words the moment a box would pass 2,000
# characters — never built. Run in a subprocess with its memory and time capped, so a regression
# fails this test instead of the machine.

_DOUBLING = r"""
import json, resource, sys
resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
sys.path[:0] = [sys.argv[1], sys.argv[1] + "/demo"]
import demo.picks_host  # noqa
from fastapi.testclient import TestClient
from demo.server import app
c = TestClient(app.app)
warn = {"field": "status", "op": "eq", "value": "warn", "value2": "", "values": []}
t = {"join": "allnone", "items": [warn, warn]}
for _ in range(39):
    t = {"join": "allnone", "items": [t, warn]}
where = sys.argv[2]
v = {"dataset": "heartbeats", "columns": [], "sort": None, "show": None, "summary": None}
if where == "question":
    v["filter"] = {"version": 1, "join": "all", "items": [t]}
else:
    v["scoreboard"] = {"by": "sender_id", "counts": [
        {"label": "Odd", "pct": False, "filter": {"version": 1, "join": "all", "items": [t]}}]}
r = c.post("/api/dashboard/answer", json={"view": v, "page": 0, "admin": True})
print(json.dumps([r.status_code, r.json().get("message")]))
"""


@pytest.mark.parametrize("where", ["question", "count column"])
def test_forty_nested_all_or_none_groups_are_refused_in_words_without_building_them(where):
    import subprocess
    try:
        out = subprocess.run([sys.executable, "-c", _DOUBLING, str(_REPO_ROOT), where], capture_output=True,
                             text=True, timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail("the filter was still being built after 60 s: its size is not checked before it is built")
    assert out.returncode == 0, f"the request did not finish (memory capped at 1.5 GB): {out.stderr[-400:]}"
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [422, pview.TOO_LONG], out.stdout[-300:]


@pytest.mark.parametrize("logic", ["all", "any", "one", "allnone"])
def test_a_filter_is_measured_exactly_as_it_would_be_built(logic):
    """The length a box is refused on is the length compose would write, to the character."""
    import random
    rnd = random.Random(96)
    for n in range(1, 8):
        if logic in ("one", "allnone") and n < 2:
            continue
        for _ in range(20):
            parts = ["x" * rnd.randint(1, 120) for _ in range(n)]
            assert pview.composed_length([len(p) for p in parts], logic) == len(pview.compose(parts, logic)), (logic, n)


def test_the_parsers_syntax_tree_depth_256_passes_and_257_is_refused_in_words():
    """T-36's limit, which the re-vendored parser brings into both engines: a syntax tree deeper than 256 is
    a syntax error. Measured by the parser's own count; past it, the page's words, never a parse error."""
    parser = env.get("parser")

    def text(n):
        return "$.status == " + "-" * n + "1"

    n = next(k for k in range(200, 300) if parser._ast_depth(parser.parse(text(k))) == 256)
    assert pview.checked_filter(text(n)) == text(n)
    with pytest.raises(pview.ViewError) as refused:
        pview.checked_filter(text(n + 1))
    assert str(refused.value) == pview.TOO_DEEP


def test_no_tree_the_page_can_send_reaches_that_depth(setup):
    """The deepest syntax tree a filter can compose inside 2,000 characters and 64 brackets (searched under a
    memory cap: nested "exactly one of" groups, two items a level, 27 levels) is 109 deep — far from 256."""
    fields = _heartbeat_fields(setup)
    t = None
    for _ in range(27):
        t = box("one", *([t] if t else []), card("status", "eq", "a"), *([] if t else [card("status", "eq", "a")]))
    text = _raw(tree("all", t), fields)
    depth = env.get("parser")._ast_depth(env.get("parser").parse(text))
    assert len(text) <= 2000 and depth < 256, (len(text), depth)
