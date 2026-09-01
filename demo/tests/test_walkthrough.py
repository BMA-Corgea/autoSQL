"""demo/tests/test_walkthrough.py — the walkthrough's numbers.

W6 lands the FIRST half of this file: B8's structural guarantee that
demo/seed/expectations.py is genuinely a third independent path, plus the
checks on demo/expected-answers.json that W6's row in plan §6.2 names.

W17 adds the second half here — AC-30 and AC-31 driving all 14 steps
through the API and comparing what the app returns against this same
JSON. That work appends to this file; nothing below needs changing for it,
and none of it needs a database.

WHY THE AST TEST IS THE IMPORTANT ONE
-------------------------------------
The demo's whole checking story is that three producers answer every
walkthrough number — the SQL, the Python pane, and expectations.py — and
that agreement between them means something. It means nothing if the third
one is quietly computing its answer by calling one of the first two.

B8 puts it plainly: expectations.py "may import nothing from
demo/pyrunner/, demo/builder.py or demo/probes.py. A test walks
expectations.py's AST and fails on any such import. That is the assertion
that cannot be satisfied by good intentions."

Good intentions are exactly what this is protecting against. Nobody would
write that import today. Someone refactoring in six weeks, wanting the
rolling-average helper that already exists in pyrunner, would — and the
suite would stay green while AC-31 quietly became a tautology again. This
test is what makes that a failing build instead of a silent one.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_EXPECTATIONS_PY = _REPO_ROOT / "demo" / "seed" / "expectations.py"
_ANSWERS_JSON = _REPO_ROOT / "demo" / "expected-answers.json"

# B8.1's three names. Matched on the MODULE name, so demo.pyrunner,
# demo.pyrunner.order, .pyrunner and a bare `from demo import pyrunner` are
# all caught by the same rule.
FORBIDDEN_MODULES = {"pyrunner", "builder", "probes"}


def _forbidden_imports(tree: ast.AST) -> list:
    """Every import in `tree` that reaches one of B8.1's three modules."""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = set(alias.name.split("."))
                if parts & FORBIDDEN_MODULES:
                    hits.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module_parts = set((node.module or "").split("."))
            imported = {alias.name for alias in node.names}
            # `from demo.pyrunner import x` and `from demo import pyrunner`
            # are both forbidden, so both halves are checked.
            if (module_parts | imported) & FORBIDDEN_MODULES:
                dots = "." * node.level
                names = ", ".join(a.name for a in node.names)
                hits.append((node.lineno, f"from {dots}{node.module or ''} import {names}"))
    return hits


# ---------------------------------------------------------------------------
# B8.1 — the AST test. The one that cannot be satisfied by good intentions.
# ---------------------------------------------------------------------------

def test_b8_expectations_imports_no_pane():
    """expectations.py imports nothing from pyrunner, builder or probes."""
    assert _EXPECTATIONS_PY.exists(), f"missing {_EXPECTATIONS_PY}"
    tree = ast.parse(_EXPECTATIONS_PY.read_text(), filename=str(_EXPECTATIONS_PY))
    hits = _forbidden_imports(tree)
    assert not hits, (
        "B8.1 violated — demo/seed/expectations.py is supposed to be a THIRD "
        "independent path, and it is importing a pane it is meant to be checking:\n"
        + "\n".join(f"  line {line}: {text}" for line, text in hits)
        + "\nWith that import, AC-31 compares the pane against itself and proves nothing."
    )


def test_b8_ast_test_would_actually_catch_an_import():
    """The detector is exercised on source that DOES import the panes.

    A guard nobody has ever seen fire is a guard nobody knows works. Each of
    the six spellings below is a real way the forbidden import gets written,
    and the test above is only worth running if all six are caught.
    """
    samples = [
        "import demo.pyrunner",
        "from demo.pyrunner import order",
        "from demo import pyrunner",
        "import demo.builder as b",
        "from demo.probes import fire",
        "from ..pyrunner import decimals",
    ]
    for source in samples:
        hits = _forbidden_imports(ast.parse(source))
        assert hits, f"the AST detector MISSED a forbidden import: {source!r}"

    # And it does not fire on what B8.2 positively requires.
    allowed = [
        "from demo.seed import generate",
        "import json",
        "from decimal import Decimal, ROUND_HALF_UP",
    ]
    for source in allowed:
        hits = _forbidden_imports(ast.parse(source))
        assert not hits, f"the AST detector wrongly refused an allowed import: {source!r}"


def test_b8_expectations_uses_no_dynamic_import():
    """No importlib / __import__ back door around the AST check.

    The AST test reads static imports, which is what B8 specifies. A dynamic
    import would satisfy it while defeating it, so the door is shut here
    rather than left as a known gap.
    """
    tree = ast.parse(_EXPECTATIONS_PY.read_text(), filename=str(_EXPECTATIONS_PY))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                bad.append((node.lineno, "__import__(...)"))
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                bad.append((node.lineno, "importlib.import_module(...)"))
    assert not bad, (
        "demo/seed/expectations.py reaches for a dynamic import: "
        + ", ".join(f"line {line}: {text}" for line, text in bad)
    )


# ---------------------------------------------------------------------------
# The JSON itself — W6's other two "done means" clauses.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def answers():
    assert _ANSWERS_JSON.exists(), (
        f"missing {_ANSWERS_JSON} — regenerate with: python -m demo.seed.expectations"
    )
    return json.loads(_ANSWERS_JSON.read_text())


def _walk_entries(node, trail=""):
    """Yield (path, entry) for every {"value": ..., "derivation": ...} object."""
    if isinstance(node, dict):
        if "value" in node and "derivation" in node:
            yield trail, node
        for key, child in node.items():
            yield from _walk_entries(child, f"{trail}.{key}" if trail else str(key))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _walk_entries(child, f"{trail}[{index}]")


def test_b8_every_entry_has_a_nonempty_derivation(answers):
    """B8.3 — every number says how it was reached."""
    entries = list(_walk_entries(answers))
    assert entries, "no entries found in expected-answers.json"
    missing = [
        path for path, entry in entries
        if not isinstance(entry.get("derivation"), str) or not entry["derivation"].strip()
    ]
    assert not missing, (
        "B8.3 violated — these entries carry no derivation: " + ", ".join(missing)
    )
    # "Whatever the code returned" is not admissible (B8.3). A derivation that
    # is merely the value restated tells a reviewer nothing, so the floor is a
    # real sentence rather than a token.
    thin = [
        path for path, entry in entries
        if len(entry["derivation"].strip()) < 25
    ]
    assert not thin, (
        "B8.3 — these derivations are too thin to reconstruct the number from: "
        + ", ".join(thin)
    )


def test_every_step_has_a_derivation(answers):
    """The step-level derivations, which say what the step is FOR."""
    steps = answers["steps"]
    assert len(steps) == 14, f"§10 has 14 steps, the file has {len(steps)}"
    assert [s["step"] for s in steps] == list(range(1, 15)), "steps are not 1..14 in order"
    for step in steps:
        assert step.get("derivation", "").strip(), f"step {step['step']} has no derivation"
        assert step.get("expect"), f"step {step['step']} expects nothing"


def test_expectations_regenerate_byte_identically():
    """The third path is deterministic — it never reads the clock.

    Rebuilds the answers in-process and compares to the committed file. If
    this fails, either the seed changed (and the file needs regenerating) or
    something in the derivation is reading something it should not be.
    """
    from demo.seed import expectations

    rebuilt = json.dumps(expectations.build_answers(), indent=2, sort_keys=False) + "\n"
    assert rebuilt == _ANSWERS_JSON.read_text(), (
        "demo/expected-answers.json is stale or non-deterministic — "
        "regenerate with: python -m demo.seed.expectations"
    )


def test_the_numbers_agree_with_each_other(answers):
    """Internal cross-checks — the arithmetic has to close.

    Not a comparison against either pane (that is W17's). These are the
    identities the numbers must satisfy among THEMSELVES, and each one would
    catch a different slip in expectations.py's own arithmetic.
    """
    steps = {s["step"]: s["expect"] for s in answers["steps"]}
    total = steps[2]["row_count"]["value"]

    # step 3's two counts partition step 2's total.
    assert steps[3]["true_count"]["value"] + steps[3]["false_count"]["value"] == total

    # step 4 recounts step 3's false half by a different route.
    assert steps[4]["row_count"]["value"] == steps[3]["false_count"]["value"]

    # step 7's buckets account for every row, and each holds the same count.
    buckets = steps[7]["buckets"]["value"]
    assert len(buckets) == steps[7]["bucket_count"]["value"] == 7
    assert sum(b["count"] for b in buckets) == total
    assert {b["count"] for b in buckets} == {1200}
    assert [b["bucket"] for b in buckets] == sorted(b["bucket"] for b in buckets)

    # step 8 emits one cell per row, dropping and padding none.
    assert steps[8]["row_count"]["value"] == total

    # step 9's kept count sits inside AC-40's band, and the ts-included
    # negative control is the full table — the eight-fold miss B8 relies on.
    low, high = steps[9]["band"]["value"]
    kept = steps[9]["kept_count"]["value"]
    assert low <= kept <= high, f"kept count {kept} is outside AC-40's band {low}–{high}"
    assert steps[9]["kept_if_ts_included"]["value"] == total
    assert len(steps[9]["first_five_keys"]["value"]) == 5

    # step 5 returns exactly the row cap.
    assert len(steps[5]["keys"]["value"]) == steps[5]["row_count"]["value"] == 10
    assert len(set(steps[5]["keys"]["value"])) == 10, "step 5 returned a duplicate key"

    # step 6's sum cannot exceed 100 per row (R16 draws load 0–100).
    assert 0 <= int(steps[6]["sum"]["value"]) <= 100 * total
    assert steps[6]["row_count"]["value"] == total

    # step 14's table-survives count is step 2's count — that is the point.
    assert steps[14]["table_survives"]["value"] == total


def test_step_8_worked_example_demonstrates_all_three_window_widths(answers):
    """W6-R1 — the worked sender must actually exercise ÷1, ÷2 and ÷3.

    This is the check that would have failed on hb-01, whose five identical
    loads make all three divisors print the same number. If a reseed ever
    makes the chosen sender degenerate again, this fails rather than shipping
    a worked example that demonstrates nothing.
    """
    worked = {s["step"]: s["expect"] for s in answers["steps"]}[8]["worked_values"]["value"]
    assert len(worked) == 5
    assert [len(w["window"]) for w in worked] == [1, 2, 3, 3, 3], (
        "§7.1's window rule: the frame grows 1, 2, 3 and then stays at 3"
    )
    first_three = [w["value"] for w in worked[:3]]
    assert len(set(first_three)) == 3, (
        f"the worked example demonstrates nothing — ÷1, ÷2 and ÷3 all return {first_three}"
    )
    # Row 3 is the non-terminating division step 8 exists to exercise.
    third = worked[2]
    assert sum(third["window"]) % 3 != 0, (
        "row 3's window divides evenly by 3, so the step never exercises a "
        "non-terminating division and the 6-place round decides nothing"
    )
    # Every value carries exactly 6 decimal places, as a string.
    for cell in worked:
        assert isinstance(cell["value"], str), "rounded values are strings, never JSON floats"
        assert len(cell["value"].split(".")[1]) == 6, f"{cell['value']} is not at 6 places"


# ═════════════════════════════════════════════════════════════════════════
# W17 — THE WALKTHROUGH END TO END.  AC-30, AC-31, AC-22.
# ═════════════════════════════════════════════════════════════════════════
#
# Everything above this line needs no database: it is W6's structural half,
# checking demo/expected-answers.json against ITSELF and against the AST of
# the file that wrote it.  Everything below drives the running demo.
#
# THE THREE-WAY COMPARISON, WHICH IS THE WHOLE POINT OF AC-31
# -----------------------------------------------------------
# AC-31 names THREE producers and requires all three to agree:
#
#     demo/WALKTHROUGH.md   the prose a person reads
#     expected-answers.json the seed's independent arithmetic (B8)
#     the running app       what /api/pick actually returns
#
# demo/tests/test_walkthrough_doc.py already binds the first two together,
# annotation by annotation.  Nothing before W17 ever compared either of
# them to the third.  ``test_ac31_all_three_producers_agree`` below is that
# comparison, and it is written to collect EVERY mismatch rather than stop
# at the first — a reviewer needs to see "40 of 41 agree and here is the
# one that does not", not a single assertion error with no denominator.
#
# WHY SOME CHECKS GO ONE LAYER BELOW ``POST /api/pick``
# ----------------------------------------------------
# The route renders a PAGE of 50 rows (B25, settings.PAGE_SIZE) and offers
# no pager: there is no request that asks for row 8,399.  Its ``comparison``
# block is nevertheless computed over the WHOLE result — ``compared_rows``
# is 8,400 for step 2 — so the route itself proves the full-result
# comparison; what it cannot hand back is the full SEQUENCE.
#
# Six of the walkthrough's numbers live past row 50: step 2's ``last_key``,
# step 3's two counts over 8,400 rows, and step 8's 8,400-cell digest.  For
# those, ``_full_panes`` below calls the SAME functions ``run_pick`` calls
# — ``normalised_pick`` → ``legality.evaluate`` → ``collection_keys`` →
# ``builder.build`` → ``app.sql_pane`` / ``app.python_pane`` — and skips
# only the paging.  It is the route with the fold removed, not a second
# implementation, and it is used ONLY where a page cannot answer.

import hashlib  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from decimal import Decimal  # noqa: E402

_DEMO_DIR = _REPO_ROOT / "demo"
if str(_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(_DEMO_DIR))

import builder  # noqa: E402
import legality  # noqa: E402
from demo.server import app as server_app  # noqa: E402
from demo.server import db, settings  # noqa: E402

HEARTBEAT = "noun:Heartbeat"
EDGECASE = "noun:EdgeCase"

#: The hostile column NAME of step 14 — the attack is the name, not the
#: expression beneath it.
HOSTILE_ALIAS = 'alive"; DROP TABLE demo.records; --'


def _pick(**kw) -> dict:
    """One pick in the API's own shape, from the screen's initial state."""
    p = legality.default_pick()
    p.update(kw)
    return p


#: §10's fourteen steps as the API receives them.  Step 1 has no pick (it
#: is ``./run-demo up``), so the mapping starts at 2.  These are the picks
#: the screen's controls produce; ``expected-answers.json`` describes the
#: same fourteen in prose-shaped form ("operation", "alias", …), and
#: ``test_the_two_spellings_of_each_pick_describe_the_same_step`` below
#: holds the two spellings together so this table cannot drift from it.
STEP_PICKS = {
    2: _pick(),
    3: _pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}]),
    4: _pick(filter='$.status != "ok"'),
    5: _pick(sort={"field": "$.ts", "dir": "desc"}, cap=10),
    6: _pick(aggregate={"fn": "sum", "field": "$.payload.load"}),
    7: _pick(bucket="day", aggregate={"fn": "count", "field": None}),
    8: _pick(window={"field": "$.payload.load"}),
    9: _pick(changed=True),
    10: _pick(computed=[{"name": "rounded", "expr": "round($.payload.load, 1)"}]),
    11: _pick(source=EDGECASE, computed=[{"name": "biggest", "expr": "max($.m)"}]),
    12: _pick(source=EDGECASE, filter='$.where == "alpha"'),
    13: _pick(source=EDGECASE, computed=[{"name": "scaled", "expr": "$.huge * 1"}]),
    14: _pick(computed=[{"name": HOSTILE_ALIAS, "expr": '$.status == "ok"'}]),
}

#: Step 14's second half: the same column, its name retyped as a plain
#: identifier, which §10 says is accepted and emitted as ``AS "alive"``.
STEP_14_RETYPED = _pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}])


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def wconn():
    """A read-only session for the checks a 50-row page cannot answer."""
    c = db.connect(application_name="autosql-demo-walkthrough")
    c.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    yield c
    c.close()


def _post(client, pick: dict):
    """One pick through the route the screen posts to.  Returns (status, body)."""
    response = client.post("/api/pick", json=pick)
    return response.status_code, response.json()


@pytest.fixture(scope="module")
def ran(client):
    """Every step driven once, cached — the fourteen steps of §10.

    One dict: ``{step number: (http status, response body)}``.  Step 1 is
    absent because it is infrastructure rather than a pick.
    """
    out = {n: _post(client, p) for n, p in STEP_PICKS.items()}
    out["14-retyped"] = _post(client, STEP_14_RETYPED)
    return out


def _full_panes(conn, pick: dict):
    """``run_pick``'s own steps, with the 50-row page removed.  See above."""
    pick = server_app.normalised_pick(pick)
    verdict = legality.evaluate(pick)
    assert not verdict["violations"], verdict["violations"]
    keys = server_app.collection_keys(conn, verdict["source"])
    built = builder.build(pick, keys)
    sql = server_app.sql_pane(conn, built)
    kinds = dict(zip(sql["columns"], sql["kinds"]))
    python = server_app.python_pane(conn, pick, kinds)
    return built, sql, python


def _cells(pane: dict) -> list:
    """A pane's whole result as the screen's display text, row by row."""
    kinds = pane["kinds"]
    return [
        tuple(server_app.display_text(row[j], kinds[j]) for j in range(len(row)))
        for row in pane["canon"]
    ]


def _column(pane: dict, name: str) -> list:
    i = pane["columns"].index(name)
    return [row[i] for row in _cells(pane)]


def _keys_on_page(body: dict, pane: str) -> list:
    rows = body["panes"][pane]["rows"]
    i = body["panes"][pane]["columns"].index("key")
    return [r["c"][i] for r in rows]


def _value(answers: dict, step: int, name: str):
    return {s["step"]: s for s in answers["steps"]}[step]["expect"][name]["value"]


# ─────────────────────────────────────────────────────────────────────────
# AC-30 — every numbered step performed on the running demo, producing the
#         result §10 states.  One test per step; each asserts what the
#         WALKTHROUGH's own prose says, not merely that nothing crashed.
# ─────────────────────────────────────────────────────────────────────────

def test_the_two_spellings_of_each_pick_describe_the_same_step(answers):
    """STEP_PICKS above and expected-answers.json describe one walkthrough.

    The JSON writes a pick in prose shape (``operation``, ``alias``,
    ``expression``, ``source``…); the API takes the screen's shape.  If the
    two ever describe different picks, every number below would still agree
    with itself while testing something §10 never asks for.  So the fields
    they share are held together here, explicitly.
    """
    by_step = {s["step"]: s["pick"] for s in answers["steps"]}
    for n, api in STEP_PICKS.items():
        doc = by_step[n]
        assert api["source"] == doc["source"], f"step {n}: source differs"
        if "alias" in doc:
            names = [cc["name"] for cc in api["computed"]]
            assert doc["alias"] in names, f"step {n}: alias {doc['alias']!r} not in {names}"
        if "expression" in doc:
            exprs = [cc["expr"] for cc in api["computed"]]
            assert doc["expression"] in exprs, f"step {n}: expression differs"
        if "filter" in doc:
            assert api["filter"] == doc["filter"], f"step {n}: filter differs"
        if "limit" in doc:
            assert api["cap"] == doc["limit"], f"step {n}: row cap differs"
        if "granularity" in doc:
            assert api["bucket"] == doc["granularity"], f"step {n}: bucket differs"
        if "aggregate" in doc:
            assert api["aggregate"]["fn"] == doc["aggregate"], f"step {n}: aggregate differs"
        if "sort" in doc:
            assert api["sort"]["field"] == doc["sort"], f"step {n}: sort field differs"
            assert api["sort"]["dir"] == doc["direction"], f"step {n}: sort direction differs"


def test_step_1_the_two_ports_and_the_seeded_total(answers, wconn):
    """§10 step 1 — the demo's own ports, and 10,410 rows once seeded."""
    assert settings.DB_PORT == _value(answers, 1, "db_port") == 55440
    assert settings.APP_PORT == _value(answers, 1, "app_port") == 8787
    total = wconn.execute("SELECT count(*) FROM demo.records").fetchone()[0]
    assert total == _value(answers, 1, "rows_loaded") == 10410
    per = dict(wconn.execute(
        "SELECT collection, count(*) FROM demo.records GROUP BY collection"
    ).fetchall())
    assert per[HEARTBEAT] == answers["corpus"]["heartbeat_rows"]["value"] == 8400
    assert per["noun:Sample"] == answers["corpus"]["sample_rows"]["value"] == 2000
    assert per[EDGECASE] == answers["corpus"]["edge_case_rows"]["value"] == 10


def test_step_2_the_whole_collection_in_key_order(ran, answers, wconn):
    """§10 step 2 — 8,400 rows, first ``hb-01-0000``, last ``hb-50-0167``."""
    status, body = ran[2]
    assert status == 200 and body["accepted"] is True
    assert body["verdict"] == "agree"
    expected = _value(answers, 2, "row_count")
    # Each pane separately, before the two are compared with each other.
    assert body["panes"]["sql"]["row_count"] == expected == 8400
    assert body["panes"]["python"]["row_count"] == expected == 8400
    assert body["comparison"]["compared_rows"] == expected
    assert body["comparison"]["differing_rows"] == 0
    assert body["page"]["ordered_by"] == "key", "§7.4(2): the tiebreak is the only order here"
    assert _keys_on_page(body, "sql")[0] == _value(answers, 2, "first_key") == "hb-01-0000"
    assert _keys_on_page(body, "python")[0] == _value(answers, 2, "first_key")
    # The last key is past the page; the full result answers it.
    _, sql, python = _full_panes(wconn, STEP_PICKS[2])
    last = _value(answers, 2, "last_key")
    assert _column(sql, "key")[-1] == last == "hb-50-0167"
    assert _column(python, "key")[-1] == last


def test_step_3_the_computed_column_partitions_the_collection(ran, answers, wconn):
    """§10 step 3 — 7,543 true and 857 false, summing to step 2's total."""
    status, body = ran[3]
    assert status == 200 and body["verdict"] == "agree"
    assert "alive" in body["panes"]["sql"]["columns"]
    assert "alive" in body["panes"]["python"]["columns"]
    true_n = _value(answers, 3, "true_count")
    false_n = _value(answers, 3, "false_count")
    # Both counts run past the 50-row page, so they are counted on the
    # full result — on EACH pane separately, then compared.
    _, sql, python = _full_panes(wconn, STEP_PICKS[3])
    for name, pane in (("SQL", sql), ("Python", python)):
        alive = _column(pane, "alive")
        assert alive.count("true") == true_n == 7543, f"{name} pane's true count"
        assert alive.count("false") == false_n == 857, f"{name} pane's false count"
        assert len(alive) == true_n + false_n == 8400, (
            f"{name} pane: `status` is never missing, so there is no third bucket"
        )


def test_step_4_the_filter_reaches_857_by_a_different_route(ran, answers):
    """§10 step 4 — 857 rows, first ``hb-01-0148``, whose status is ``warn``."""
    status, body = ran[4]
    assert status == 200 and body["verdict"] == "agree"
    expected = _value(answers, 4, "row_count")
    assert body["panes"]["sql"]["row_count"] == expected == 857
    assert body["panes"]["python"]["row_count"] == expected == 857
    assert expected == _value(answers, 3, "false_count"), (
        "step 4's filter and step 3's computed column must reach one number"
    )
    for pane in ("sql", "python"):
        assert _keys_on_page(body, pane)[0] == _value(answers, 4, "first_key") == "hb-01-0148"
        row = body["panes"][pane]["rows"][0]
        data = json.loads(row["c"][body["panes"][pane]["columns"].index("data")])
        assert data["status"] == _value(answers, 4, "first_status") == "warn"


def test_step_5_the_tiebreak_runs_ascending_under_a_descending_sort(ran, answers):
    """§10 step 5 — the ten LOWEST keys inside the winning tie (AC-41(d)).

    Asserted against the hand-written list on each pane SEPARATELY before
    the panes are compared with each other.  A Python pane written as
    ``sorted(…, reverse=True)`` over a tuple containing ``key`` returns the
    ten HIGHEST keys and must fail here (§7.4(1a)).
    """
    status, body = ran[5]
    assert status == 200 and body["verdict"] == "agree"
    expected_keys = _value(answers, 5, "keys")
    assert expected_keys == [f"hb-{i:02d}-0167" for i in range(1, 11)]
    sql_keys = _keys_on_page(body, "sql")
    py_keys = _keys_on_page(body, "python")
    assert sql_keys == expected_keys, "the SQL pane's ten, against the hand-written list"
    assert py_keys == expected_keys, "the Python pane's ten, against the hand-written list"
    assert sql_keys == py_keys, "and only then, the two panes against each other"
    assert body["panes"]["sql"]["row_count"] == _value(answers, 5, "row_count") == 10
    assert body["panes"]["python"]["row_count"] == 10
    assert body["page"]["ordered_by"] == "$.ts DESC, then key"
    # Every one of the ten sits at the latest instant — the tie is real.
    di = body["panes"]["sql"]["columns"].index("data")
    latest = _value(answers, 5, "latest_ts")
    for row in body["panes"]["sql"]["rows"]:
        assert json.loads(row["c"][di])["ts"] == latest == "2026-08-20T23:00:00Z"


def test_step_6_the_sum_on_each_pane_separately(ran, answers):
    """§10 step 6 — 400,207, asserted per pane against B8's own number."""
    status, body = ran[6]
    assert status == 200 and body["verdict"] == "agree"
    expected = str(_value(answers, 6, "sum"))
    for pane in ("sql", "python"):
        cells = body["panes"][pane]["rows"][0]["c"]
        assert body["panes"][pane]["columns"] == ["agg"]
        # The display carries the exact-decimal rule's six places; the
        # number itself is what B8 derived independently of both panes.
        assert Decimal(cells[0]) == Decimal(expected) == Decimal(400207), (
            f"{pane} pane returned {cells[0]!r}, expected {expected}"
        )
    assert body["comparison"]["compared_rows"] == 1
    # The sanity band §10 states in words: 0 <= sum <= 8400 * 100.
    assert 0 <= int(Decimal(expected)) <= 100 * _value(answers, 6, "row_count")


def test_step_7_seven_buckets_of_twelve_hundred(ran, answers):
    """§10 step 7 — 7 UTC days, 1,200 rows each, labels compared as text."""
    status, body = ran[7]
    assert status == 200 and body["verdict"] == "agree"
    expected = [(b["bucket"], b["count"]) for b in _value(answers, 7, "buckets")]
    assert len(expected) == _value(answers, 7, "bucket_count") == 7
    for pane in ("sql", "python"):
        cols = body["panes"][pane]["columns"]
        assert cols == ["bucket", "agg"]
        got = [(r["c"][0], int(Decimal(r["c"][1]))) for r in body["panes"][pane]["rows"]]
        assert got == expected, f"{pane} pane's buckets"
        assert sum(c for _, c in got) == 8400, "7 x 1,200 accounts for every row"
        assert {c for _, c in got} == {1200}
    assert body["page"]["ordered_by"] == "bucket"


def test_step_8_the_rolling_window_and_its_whole_column(ran, answers, wconn):
    """§10 step 8 — one value per row, and the frame that grows 1, 2, 3.

    The five worked cells of sender ``hb-18`` are asserted per pane, and
    then the WHOLE 8,400-cell column is reduced to W6's sha256 so a pane
    that divides by 3 at rows 1 and 2 cannot hide outside the sample.
    """
    status, body = ran[8]
    assert status == 200 and body["verdict"] == "agree"
    assert body["panes"]["sql"]["row_count"] == _value(answers, 8, "row_count") == 8400
    assert body["panes"]["python"]["row_count"] == 8400
    assert "rolling_avg" in body["panes"]["sql"]["columns"]

    sender = _value(answers, 8, "worked_sender")
    worked = _value(answers, 8, "worked_values")
    digest = _value(answers, 8, "column_sha256")

    _, sql, python = _full_panes(wconn, STEP_PICKS[8])
    for name, pane in (("SQL", sql), ("Python", python)):
        keys = _column(pane, "key")
        values = _column(pane, "rolling_avg")
        got = [v for k, v in zip(keys, values) if k.startswith(sender + "-")][:5]
        assert got == [w["value"] for w in worked], (
            f"{name} pane's five worked cells for {sender}"
        )
        h = hashlib.sha256()
        for k, v in zip(keys, values):
            h.update(f"{k}\x1f{v}\n".encode())
        assert h.hexdigest() == digest, (
            f"{name} pane's whole rolling column differs from W6's digest"
        )
    assert body["page"]["ordered_by"] == "key"


def test_step_9_only_the_rows_that_changed(ran, answers, wconn):
    """§10 step 9 — 861 kept, inside AC-40's band, first five keys named."""
    status, body = ran[9]
    assert status == 200 and body["verdict"] == "agree"
    kept = _value(answers, 9, "kept_count")
    low, high = _value(answers, 9, "band")
    # AC-40(a): the band, on EACH pane separately, before the comparison.
    assert body["panes"]["sql"]["row_count"] == kept == 861
    assert body["panes"]["python"]["row_count"] == kept
    assert low <= body["panes"]["sql"]["row_count"] <= high == 1100
    assert low <= body["panes"]["python"]["row_count"] <= high
    first_five = _value(answers, 9, "first_five_keys")
    assert first_five == ["hb-01-0000", "hb-01-0006", "hb-01-0007",
                          "hb-01-0041", "hb-01-0056"]
    assert _keys_on_page(body, "sql")[:5] == first_five
    assert _keys_on_page(body, "python")[:5] == first_five
    assert body["comparison"]["compared_rows"] == kept


def test_step_9_negative_control_the_ts_included_comparison_keeps_everything(
    answers, wconn
):
    """§10 step 9's negative control — put ``ts`` back and 8,400 survive.

    Not a property of the demo (AC-40(e) makes the compared value a
    constant of the builder, so the app cannot be asked for this) — a
    property of the DATA, and the reason operation 9 is a demonstration at
    all.  The statement below is step 9's own generated SQL with
    ``r.data - 'ts'`` replaced by ``r.data``; everything else is identical.
    """
    ts_included = """
    WITH picked AS (
      SELECT r.key,
             ( lag( r.data ) OVER w IS DISTINCT FROM ( r.data ) ) AS "changed"
        FROM demo.records AS r
       WHERE r.collection = %(collection)s
      WINDOW w AS (PARTITION BY (r.data ->> 'sender_id')
                   ORDER BY     (r.data ->> 'ts'), r.key)
    )
    SELECT count(*) FROM picked WHERE "changed"
    """
    got = wconn.execute(ts_included, {"collection": HEARTBEAT}).fetchone()[0]
    assert got == _value(answers, 9, "kept_if_ts_included") == 8400, (
        "the ts-included comparison must keep every row — that eight-fold "
        "miss is what AC-40(a)'s band exists to catch"
    )
    assert got > _value(answers, 9, "band")[1], "and it must sit outside the band"


def test_step_10_the_static_gate_refuses_round_before_any_sql(ran, answers):
    """§10 step 10 — refused by layer 1; no SQL exists, both panes empty."""
    status, body = ran[10]
    assert status == 422 and body["accepted"] is False
    refusal = body["refusal"]
    assert refusal["layer"] == 1
    assert refusal["sql_existed"] is False
    assert refusal["statement_sent"] is False
    assert refusal["construct"] == _value(answers, 10, "names_construct") == "round"
    assert "round" in refusal["why"]
    assert body["sql"]["parameterised"] is None, (
        "a layer-1 refusal generates no SQL at all — that is what "
        "distinguishes it from steps 12 and 13"
    )
    assert body["sql"]["probes"] == []
    assert body["sql"]["statement_sent"] is False
    for pane in ("sql", "python"):
        assert body["panes"][pane]["state"] == "not-asked"
        assert body["panes"][pane]["rows"] == []
        assert body["panes"][pane]["row_count"] == 0
    assert _value(answers, 10, "sql_pane") is None
    assert _value(answers, 10, "python_pane") is None


# ─────────────────────────────────────────────────────────────────────────
# AC-22 — THE ASSERTED DISAGREEMENT.
#
# This is the single most important assertion in the build.  It is the
# demo's whole reason for existing: it proves the two engines CAN disagree,
# and that the disagreement is caught and shown rather than averaged away.
#
# Note what shape it is.  It does not assert that the panes agree and it
# does not tolerate them agreeing.  It asserts a SPECIFIC disagreement:
# Python `123`, SQL `1`, on row `edge-01`, in column `biggest`, with the
# response's verdict reading `disagree`.  Spec AC-22, in its own words:
# "If the two panes ever agree here, either the compiler has been edited
# (which Q19 forbids and AC-33 catches) or the control has stopped working
# — and in both cases the build is not accepted."
#
# CHANGED 2026-08-23 (q4/GA-7; the dated note beside AC-22 in T-2.md): the
# demo adopted T-3's corrected runtime.sql, whose 309-digit guard reads
# 1e300 correctly — measured: max($.l) over [1e300, 1] now answers 1e+300
# on BOTH panes.  The old vehicle agreeing is the FIX working, not the
# control failing, so the step moved to the divergence T-3 measured as
# surviving the corrected runtime: the Unicode-digit gap.  edge-01's `m`
# holds ["１２３", 1]; Python's float() reads any Unicode digit (123.0),
# the runtime's ASCII-only regex reads NULL, so Python says 123 and SQL
# says 1.  The disagreement is still asserted, not tolerated.
# ─────────────────────────────────────────────────────────────────────────

def test_ac22_step_11_both_engines_now_read_123_and_nothing_is_flagged(
    ran, answers
):
    """§10 step 11 — the value that used to be wrong, read from both sides.

    T-8, 2026-09-01. This test asserted a divergence for as long as one existed.
    T-6's variant C closed the last in-subset value disagreement, so every claim
    here is INVERTED rather than dropped: same pick, same row, same two panes,
    same three flag signals -- each now asserting the opposite outcome. Deleting
    it would have removed the only end-to-end check on the value this whole demo
    was built to talk about.
    """
    status, body = ran[11]
    assert status == 200, "step 11 is ACCEPTED — an agreement is a result, not a refusal"
    assert body["accepted"] is True
    assert body["refusal"] is None

    expected_row = _value(answers, 11, "row")
    expected_py = _value(answers, 11, "python_value")
    expected_sql = _value(answers, 11, "sql_value")
    assert (expected_row, expected_py, expected_sql) == ("edge-01", "123", "123")
    assert _value(answers, 11, "panes_agree") is True
    assert _value(answers, 11, "flagged") is False

    # ── the two numbers, read out of the response the screen renders ──
    sql_pane = body["panes"]["sql"]
    py_pane = body["panes"]["python"]
    assert sql_pane["columns"] == py_pane["columns"]
    ki = sql_pane["columns"].index("key")
    bi = sql_pane["columns"].index("biggest")
    sql_row = next(r for r in sql_pane["rows"] if r["c"][ki] == expected_row)
    py_row = next(r for r in py_pane["rows"] if r["c"][ki] == expected_row)

    assert py_row["c"][bi] == expected_py == "123", (
        "the Python pane must report 123: float() reads the FULLWIDTH "
        'digits of "１２３" as 123.0 — any Unicode decimal digit converts'
    )
    assert sql_row["c"][bi] == expected_sql == "123", (
        "the SQL pane must report 123: when the ASCII-only gate misses, the "
        'adopted runtime translates the 670 non-ASCII decimal digits onto 0-9 '
        'and re-tests, so "１２３" reads as 123 exactly as Python reads it '
        "(T-6 variant C, which closed T-3 finding 1 by matching rather than refusing)"
    )
    assert sql_row["c"][bi] == py_row["c"][bi], (
        "AC-22 NOW ASSERTS AN AGREEMENT. The two panes differing here means "
        "the runtime, the compiler or the comparison has changed — see AC-22 "
        "and its 2026-09-01 note."
    )

    # ── and the flag: three independent signals, not one ──────────────
    assert body["verdict"] == "agree"
    assert body["comparison"]["verdict"] == "agree"
    assert body["comparison"]["differing_rows"] == 0, (
        "no row differs — edge-01's `m` is the one that used to, and no longer does"
    )
    assert body["comparison"]["first_differing_index"] is None
    assert body["comparison"]["columns_match"] is True, (
        "the disagreement is about a VALUE, not about the shape of the result"
    )
    assert body["comparison"]["compared_rows"] == 10, (
        "all ten EdgeCase rows were compared, not just the page"
    )
    # The row itself carries the mark, so the screen can point at the cell
    # rather than only announcing the row (D8).
    assert not sql_row.get("diff")
    assert not py_row.get("diff")
    # All ten rows agree. The mark's ABSENCE is asserted, not merely unchecked.
    assert sum(1 for r in sql_pane["rows"] if r.get("diff")) == 0


def test_ac22_the_agreement_is_not_a_pane_that_failed_to_run(ran):
    """Both panes ANSWERED. An agreement between two answers is a result; an
    agreement between one answer and an absence is a bug wearing a green mark —
    and that distinction matters MORE now than when this asserted a difference."""
    _, body = ran[11]
    for pane in ("sql", "python"):
        assert body["panes"][pane]["state"] == "answered"
        assert body["panes"][pane]["row_count"] == 10
        assert len(body["panes"][pane]["rows"]) == 10
    assert body["sql"]["statement_sent"] is True, (
        "the statement really ran — the SQL pane's `123` is a database answer"
    )


def test_ac22_the_agreement_is_reproducible(client):
    """Run step 11 five more times: the same agreement, every time.

    An agreement that appeared intermittently would be a flake dressed as a
    fix — the same failure the old divergence version of this test guarded
    against, pointed the other way.
    """
    seen = set()
    for _ in range(5):
        _, body = _post(client, STEP_PICKS[11])
        ki = body["panes"]["sql"]["columns"].index("key")
        bi = body["panes"]["sql"]["columns"].index("biggest")
        sql_row = next(r for r in body["panes"]["sql"]["rows"] if r["c"][ki] == "edge-01")
        py_row = next(r for r in body["panes"]["python"]["rows"] if r["c"][ki] == "edge-01")
        seen.add((body["verdict"], sql_row["c"][bi], py_row["c"][bi],
                  body["comparison"]["differing_rows"]))
    assert seen == {("agree", "123", "123", 0)}, f"step 11 was not stable: {seen}"


# ─────────────────────────────────────────────────────────────────────────
# Steps 12, 13, 14 — the two runtime refusals and the hostile column name.
# ─────────────────────────────────────────────────────────────────────────

def test_step_12_a_container_operand_is_refused_at_runtime_by_name(ran, answers):
    """§10 step 12 — layer 2 member (b), naming ``edge-02``; Python still answers."""
    status, body = ran[12]
    assert status == 422 and body["accepted"] is False
    refusal = body["refusal"]
    assert refusal["layer"] == 2
    assert refusal["member"] == "b", _value(answers, 12, "refused_by")
    assert refusal["row_key"] == _value(answers, 12, "offending_row") == "edge-02"
    assert "edge-02" in refusal["why"]
    assert refusal["statement_sent"] is False
    assert refusal["sql_existed"] is True, (
        "unlike step 10, SQL WAS generated here — that is the visible "
        "difference between a static refusal and a runtime one"
    )
    assert body["sql"]["parameterised"] is not None
    assert body["sql"]["statement_sent"] is False
    assert body["sql"]["probes"], "the probe that fired is shown"
    assert any(p["fired"] for p in body["sql"]["probes"])
    # The SQL pane shows no number; the Python pane still shows its own,
    # labelled as the reported fallback (§4.5).
    assert body["panes"]["sql"]["state"] == "abandoned"
    assert body["panes"]["sql"]["rows"] == []
    assert _value(answers, 12, "sql_pane") is None
    assert body["panes"]["python"]["state"] == "answered"
    assert body["panes"]["python"]["row_count"] == _value(
        answers, 12, "python_pane_rows_kept") == 0
    assert body["verdict"] == "no-compare", (
        "one side has no number, so there is nothing to compare — and the "
        "screen must not read `agree` off two empties"
    )


def test_step_13_an_out_of_range_magnitude_is_refused_at_runtime(ran, answers):
    """§10 step 13 — layer 2 member (a), naming ``edge-03``.

    The parts of the step that hold are asserted here.  The one part that
    does NOT — what the Python pane shows — has its own test below, so
    this one reports the refusal honestly instead of failing on a
    neighbouring claim.
    """
    status, body = ran[13]
    assert status == 422 and body["accepted"] is False
    refusal = body["refusal"]
    assert refusal["layer"] == 2
    assert refusal["member"] == "a", _value(answers, 13, "refused_by")
    assert refusal["row_key"] == _value(answers, 13, "offending_row") == "edge-03"
    assert "edge-03" in refusal["why"]
    assert refusal["sql_existed"] is True
    assert refusal["statement_sent"] is False
    assert body["sql"]["parameterised"] is not None, (
        "SQL was generated this time — §10's stated difference from step 10"
    )
    assert body["sql"]["statement_sent"] is False
    assert body["panes"]["sql"]["state"] == "abandoned"
    assert _value(answers, 13, "sql_pane") is None
    assert body["verdict"] == "no-compare"
    # AC-17's companion half: the refusal is not a blanket ban on large
    # numbers — step 11 (also on noun:EdgeCase, also reading real rows) ran
    # to an answer, and TestAC17 in test_probes.py pins 1e300-not-refused
    # directly.
    assert ran[11][0] == 200


def test_step_14_the_hostile_column_name_never_reaches_sql(ran, answers, client, wconn):
    """§10 step 14 — AC-38(b): refused before any SQL, zero statements sent.

    And the assertion the refusal message alone could not make: the table
    is still there afterwards, with every one of its rows.
    """
    status, body = ran[14]
    assert status == 422 and body["accepted"] is False
    refusal = body["refusal"]
    assert refusal["layer"] == 1
    assert refusal["kind"] == "alias"
    assert _value(answers, 14, "hostile_alias") == HOSTILE_ALIAS
    assert refusal["construct"] == HOSTILE_ALIAS, (
        "the refusal names the offending NAME, not a generic 'invalid input'"
    )
    assert HOSTILE_ALIAS in refusal["why"]
    assert "letters, digits and underscore" in refusal["why"], (
        "§4.10 requires the refusal to name the RULE as well as the name"
    )
    assert _value(answers, 14, "names_the_name_and_rule") is True
    # AC-38(b), first half: refused before any SQL, and nothing was sent.
    assert _value(answers, 14, "refused_before_sql") is True
    assert refusal["sql_existed"] is False
    assert refusal["statement_sent"] is False
    assert body["sql"]["parameterised"] is None
    assert body["sql"]["display"] is None
    assert body["sql"]["params"] == []
    assert body["sql"]["probes"] == [], "zero statements — not even a probe"
    assert body["sql"]["statement_sent"] is False
    for pane in ("sql", "python"):
        assert body["panes"][pane]["state"] == "not-asked"
        assert body["panes"][pane]["rows"] == []

    # AC-38(b), second half: the table survives, counted rather than assumed.
    assert wconn.execute("SELECT count(*) FROM demo.records").fetchone()[0] == 10410
    _, again = _post(client, STEP_PICKS[2])
    survives = _value(answers, 14, "table_survives")
    assert again["panes"]["sql"]["row_count"] == survives == 8400
    assert again["panes"]["python"]["row_count"] == survives
    assert survives == _value(answers, 2, "row_count"), (
        "step 14's survival count is step 2's count — that is the point"
    )


def test_step_14_the_retyped_alias_is_accepted_and_emitted_quoted(ran, answers):
    """§10 step 14's second half — AC-38(c): ``AS "alive"``, keyed the same."""
    status, body = ran["14-retyped"]
    assert status == 200 and body["accepted"] is True
    assert _value(answers, 14, "retyped_alias") == "alive"
    emitted = _value(answers, 14, "retyped_emitted_as")
    assert emitted == 'AS "alive"'
    assert emitted in body["sql"]["parameterised"], (
        "the alias is written into the SQL TEXT — it is the one piece of "
        "typed text that cannot be a bind parameter"
    )
    assert emitted in body["sql"]["display"]
    assert "alive" not in [p["value"] for p in body["sql"]["params"]]
    # And the Python pane keys its own answer by the same name.
    assert "alive" in body["panes"]["python"]["columns"]
    assert body["panes"]["sql"]["columns"] == body["panes"]["python"]["columns"]
    assert body["verdict"] == "agree"


# ─────────────────────────────────────────────────────────────────────────
# AC-31 — ALL THREE PRODUCERS, COMPARED.
#
#   demo/WALKTHROUGH.md   <->  demo/expected-answers.json   <->  the app
#        (test_walkthrough_doc.py binds the first two)   (this binds the third)
#
# Every entry of expected-answers.json is either OBSERVED from the running
# demo below, or named in NOT_APP_OBSERVABLE with the reason it cannot be.
# The two sets are asserted to cover the file exactly, so a number added
# later cannot slip through the sweep by being in neither.
# ─────────────────────────────────────────────────────────────────────────

#: Entries no pick can produce, each with why.  A short list, checked.
NOT_APP_OBSERVABLE = {
    "steps[7].expect.worked_sender":
        "W6's SELECTION RULE, not a result — which sender the worked example "
        "uses. The app is asked about hb-18 because this says so.",
    "steps[8].expect.band":
        "AC-40(a)'s band is a property of the seed's repeat rate, not an "
        "answer the app returns. The kept count is checked INSIDE it.",
    "steps[8].expect.kept_if_ts_included":
        "The negative control. AC-40(e) makes the compared value a constant "
        "of the builder, so the app cannot be asked to include ts — the "
        "number is checked against hand-written SQL instead "
        "(test_step_9_negative_control_...).",
    "steps[9].expect.refused_by":
        "Prose naming the LAYER. The layer number itself is asserted in the "
        "step-10 test; this string is not a value the API returns.",
    "steps[9].expect.why_it_proves_something":
        "A pointer to compile.py:394 — evidence that the step tests "
        "something reachable, not a number the app produces.",
    "steps[11].expect.refused_by":
        "Prose naming layer 2 member (b); the member letter itself is "
        "asserted in the step-12 test.",
    "steps[12].expect.refused_by":
        "Prose naming layer 2 member (a); the member letter itself is "
        "asserted in the step-13 test.",
    "steps[13].expect.names_the_name_and_rule":
        "A property of the refusal TEXT, asserted directly in the step-14 "
        "test (the name appears, and so does §4.10's rule).",
}


def _agrees(want, got) -> bool:
    """Equal, or the same number written two ways.  NOT a tolerance.

    The SQL pane renders step 6's sum as ``400207.000000`` and the file
    records it as ``400207``.  Both are parsed as EXACT ``Decimal``s and
    compared with ``==``, which is the same comparison the panes themselves
    use (§8.1 forbids a tolerance anywhere, and this is not one:
    ``Decimal("400207.000001")`` still differs).  Anything that is not a
    decimal on both sides falls back to plain equality, so ``True`` never
    equals ``1`` here.
    """
    if want == got and type(want) is type(got):
        return True
    if isinstance(want, bool) or isinstance(got, bool):
        return want is got
    try:
        return Decimal(str(want)) == Decimal(str(got))
    except (ArithmeticError, ValueError, TypeError):
        return want == got


@pytest.fixture(scope="module")
def observed(ran, wconn, client):
    """What the running demo returns, keyed by expected-answers.json path."""
    o = {}

    o["corpus.heartbeat_rows"] = ran[2][1]["panes"]["sql"]["row_count"]
    per = dict(wconn.execute(
        "SELECT collection, count(*) FROM demo.records GROUP BY collection"
    ).fetchall())
    o["corpus.sample_rows"] = per["noun:Sample"]
    o["corpus.edge_case_rows"] = per[EDGECASE]

    o["steps[0].expect.db_port"] = settings.DB_PORT
    o["steps[0].expect.app_port"] = settings.APP_PORT
    o["steps[0].expect.rows_loaded"] = sum(per.values())

    b2 = ran[2][1]
    o["steps[1].expect.row_count"] = b2["panes"]["sql"]["row_count"]
    o["steps[1].expect.first_key"] = _keys_on_page(b2, "sql")[0]
    _, sql2, _py2 = _full_panes(wconn, STEP_PICKS[2])
    o["steps[1].expect.last_key"] = _column(sql2, "key")[-1]

    _, sql3, _py3 = _full_panes(wconn, STEP_PICKS[3])
    alive = _column(sql3, "alive")
    o["steps[2].expect.true_count"] = alive.count("true")
    o["steps[2].expect.false_count"] = alive.count("false")

    b4 = ran[4][1]
    o["steps[3].expect.row_count"] = b4["panes"]["sql"]["row_count"]
    o["steps[3].expect.first_key"] = _keys_on_page(b4, "sql")[0]
    di = b4["panes"]["sql"]["columns"].index("data")
    o["steps[3].expect.first_status"] = json.loads(
        b4["panes"]["sql"]["rows"][0]["c"][di])["status"]

    b5 = ran[5][1]
    di = b5["panes"]["sql"]["columns"].index("data")
    o["steps[4].expect.latest_ts"] = json.loads(
        b5["panes"]["sql"]["rows"][0]["c"][di])["ts"]
    o["steps[4].expect.keys"] = _keys_on_page(b5, "sql")
    o["steps[4].expect.row_count"] = b5["panes"]["sql"]["row_count"]

    b6 = ran[6][1]
    # Verbatim as the pane renders it — `400207.000000`, the exact-decimal
    # rule's six places.  _agrees() below parses both sides as exact
    # Decimals; the file records the same number as `400207`.
    o["steps[5].expect.sum"] = b6["panes"]["sql"]["rows"][0]["c"][0]
    # Step 6's OWN contributing-row count.  The file's claim is "all 8400
    # rows contribute … none drops out of the sum", which the sum alone
    # cannot police (74 seeded loads are 0, so a read that silently dropped
    # zero-valued rows would leave 400207 untouched).  So: count the rows
    # whose §7.2 item 5 numeric read is non-null, through the IDENTICAL
    # read fragment step 6's emitted statement sums — asserted to appear in
    # that statement so the two cannot drift apart.  (This entry used to be
    # filled from ran[2], step 2's plain-select row count: an observation
    # of a different pick, unable to fail against this claim.)
    built6, _sql6, _py6 = _full_panes(wconn, STEP_PICKS[6])
    read6 = builder.numeric_read("r.data #> %(agg_path)s")
    assert read6 in built6.sql, (
        "step 6's emitted SQL no longer contains the numeric read this "
        "count observes — rebind them before trusting either"
    )
    (contributing,) = wconn.execute(
        "SELECT count( " + read6 + " ) FROM demo.records AS r"
        " WHERE r.collection = %(collection)s",
        built6.params,
    ).fetchone()
    o["steps[5].expect.row_count"] = contributing

    b7 = ran[7][1]
    buckets = [{"bucket": r["c"][0], "count": int(Decimal(r["c"][1]))}
               for r in b7["panes"]["sql"]["rows"]]
    o["steps[6].expect.bucket_count"] = len(buckets)
    o["steps[6].expect.rows_per_bucket"] = sorted({b["count"] for b in buckets})
    o["steps[6].expect.buckets"] = buckets

    _, sql8, _py8 = _full_panes(wconn, STEP_PICKS[8])
    keys8 = _column(sql8, "key")
    vals8 = _column(sql8, "rolling_avg")
    datas8 = _column(sql8, "data")
    loads, values, window = [], [], []
    for k, v, d in zip(keys8, vals8, datas8):
        if k.startswith("hb-18-") and len(values) < 5:
            load = json.loads(d)["payload"]["load"]
            loads.append(load)
            window = (window + [load])[-3:]
            values.append({"key": k, "window": list(window), "value": v})
    o["steps[7].expect.worked_loads"] = loads
    o["steps[7].expect.worked_values"] = values
    h = hashlib.sha256()
    for k, v in zip(keys8, vals8):
        h.update(f"{k}\x1f{v}\n".encode())
    o["steps[7].expect.column_sha256"] = h.hexdigest()
    o["steps[7].expect.row_count"] = ran[8][1]["panes"]["sql"]["row_count"]

    b9 = ran[9][1]
    o["steps[8].expect.kept_count"] = b9["panes"]["sql"]["row_count"]
    o["steps[8].expect.first_five_keys"] = _keys_on_page(b9, "sql")[:5]

    b10 = ran[10][1]
    o["steps[9].expect.verdict"] = "refused" if not b10["accepted"] else "accepted"
    o["steps[9].expect.names_construct"] = b10["refusal"]["construct"]
    o["steps[9].expect.sql_pane"] = b10["sql"]["parameterised"]
    o["steps[9].expect.python_pane"] = (
        None if b10["panes"]["python"]["row_count"] == 0
        and b10["panes"]["python"]["state"] == "not-asked" else "populated"
    )

    b11 = ran[11][1]
    ki = b11["panes"]["sql"]["columns"].index("key")
    bi = b11["panes"]["sql"]["columns"].index("biggest")
    # T-8, 2026-09-01: this used to find the row by its diff mark. Nothing is
    # marked any more (T-6 closed the last value divergence), so the row is
    # selected by the key it always was -- edge-01, the only EdgeCase row with
    # an `m`. Selecting by diff would silently pick nothing and this sweep
    # would stop reporting on step 11 at all.
    sql_row = next(r for r in b11["panes"]["sql"]["rows"] if r["c"][ki] == "edge-01")
    py_row = b11["panes"]["python"]["rows"][sql_row["i"]]
    o["steps[10].expect.row"] = sql_row["c"][ki]
    o["steps[10].expect.python_value"] = py_row["c"][bi]
    o["steps[10].expect.sql_value"] = sql_row["c"][bi]
    o["steps[10].expect.panes_agree"] = b11["verdict"] == "agree"
    o["steps[10].expect.flagged"] = b11["verdict"] == "disagree"

    b12 = ran[12][1]
    o["steps[11].expect.verdict"] = "refused" if not b12["accepted"] else "accepted"
    o["steps[11].expect.offending_row"] = b12["refusal"]["row_key"]
    o["steps[11].expect.sql_pane"] = (
        None if b12["panes"]["sql"]["state"] == "abandoned" else "populated")
    o["steps[11].expect.python_pane_rows_kept"] = b12["panes"]["python"]["row_count"]

    b13 = ran[13][1]
    o["steps[12].expect.verdict"] = "refused" if not b13["accepted"] else "accepted"
    o["steps[12].expect.offending_row"] = b13["refusal"]["row_key"]
    o["steps[12].expect.sql_pane"] = (
        None if b13["panes"]["sql"]["state"] == "abandoned" else "populated")
    # Was on NOT_APP_OBSERVABLE while the file claimed `inf` — a value the
    # API genuinely cannot publish, since step 13 never returns a number.
    # The corrected entry is the pane's own published STATE, which the API
    # does return, so the third leg of AC-31 is a real comparison here
    # rather than a carve-out. The mechanism behind the state (jsonb's
    # 401-digit integer literal → an exact int → OverflowError) is checked
    # at its source in test_step_13_neither_side_can_read_edge_03s_huge_number.
    o["steps[12].expect.python_pane"] = b13["panes"]["python"]["state"]

    b14 = ran[14][1]
    o["steps[13].expect.hostile_alias"] = b14["refusal"]["construct"]
    o["steps[13].expect.verdict"] = "refused" if not b14["accepted"] else "accepted"
    o["steps[13].expect.refused_before_sql"] = (
        b14["refusal"]["sql_existed"] is False
        and b14["sql"]["parameterised"] is None
        and b14["sql"]["probes"] == []
    )
    o["steps[13].expect.table_survives"] = (
        ran["14-retyped"][1]["panes"]["sql"]["row_count"])
    retyped = ran["14-retyped"][1]
    o["steps[13].expect.retyped_alias"] = next(
        c for c in retyped["panes"]["sql"]["columns"]
        if c not in ("collection", "key", "data"))
    o["steps[13].expect.retyped_emitted_as"] = next(
        m.group(0) for m in re.finditer(r'AS "[^"]+"', retyped["sql"]["parameterised"])
        if m.group(0) == 'AS "alive"')
    return o


def test_ac31_the_sweep_covers_every_entry_in_the_file(answers, observed):
    """No number escapes AC-31 by being in neither list."""
    every = {path for path, _ in _walk_entries(answers)}
    covered = set(observed) | set(NOT_APP_OBSERVABLE)
    missed = every - covered
    assert not missed, (
        "these expected-answers.json entries are compared against nothing "
        "the app returns and are not on the NOT_APP_OBSERVABLE list: "
        + ", ".join(sorted(missed))
    )
    stray = covered - every
    assert not stray, (
        "the sweep names entries the file does not have: " + ", ".join(sorted(stray))
    )
    assert len(every) == 59, f"the file grew or shrank: {len(every)} entries"


def test_ac31_all_three_producers_agree(answers, observed):
    """THE three-way comparison. Every mismatch is reported, not just the first.

    ``demo/tests/test_walkthrough_doc.py`` already proves WALKTHROUGH.md's
    printed numbers equal expected-answers.json's, annotation by
    annotation.  This test adds the third leg: expected-answers.json
    against what ``POST /api/pick`` actually returns on the running demo.
    Together the two are AC-31.
    """
    entries = dict(_walk_entries(answers))
    mismatches = []
    for path in sorted(observed):
        want = entries[path]["value"]
        got = observed[path]
        if not _agrees(want, got):
            mismatches.append((path, want, got, entries[path]["derivation"]))
    assert not mismatches, (
        f"AC-31: {len(observed) - len(mismatches)} of {len(observed)} "
        f"app-observable numbers agree; {len(mismatches)} do NOT:\n"
        + "\n".join(
            f"  {path}\n"
            f"      WALKTHROUGH.md / expected-answers.json says: {want!r}\n"
            f"      the running app returns:                     {got!r}\n"
            f"      the file's derivation: {why}"
            for path, want, got, why in mismatches
        )
    )


def test_step_13_neither_side_can_read_edge_03s_huge_number():
    """§10 step 13's Python-side claim, checked where it is made.

    ``expected-answers.json`` says ``steps[12].expect.python_pane ==
    "raised"`` and derives it — without running anything — from two facts
    about representations rather than from IEEE-754 arithmetic:

      1. jsonb renders its numerics in FULL POSITIONAL DIGITS, so
         ``edge-03``'s ``huge`` reaches Python as a bare 401-digit INTEGER
         literal: no ``.``, no ``e``.
      2. JSON's grammar calls that an integer, so ``json.loads`` routes it
         through ``parse_int`` and returns an EXACT arbitrary-precision
         ``int``.  ``parse_float`` never fires, so the ``float('inf')``
         an exponent literal would have produced never comes into
         existence — and the overflow surfaces later, at the arithmetic,
         as a raise.

    Both facts are asserted below over the real row and the real
    evaluator, so a change to either — a different jsonb rendering, a
    different parse, or a pyrunner that started manufacturing an ``inf``
    for an integer literal above ``DBL_MAX`` — fails here by name.

    W13-2 (above ``_fallback_python_pane`` in ``demo/server/app.py``) rules
    that raise CORRECT: *neither* side can read this value, which is a
    stronger statement of the demo's point than an ``inf`` on one side
    would be.  Corroborated independently by T-3's correctness run, which
    recorded ``float(int)`` overflow on a 10^400 JSON integer as a ninth,
    uncatalogued Python raise site.

    (This test replaced ``test_step_13_the_documented_inf_is_what_python_
    really_produces``, which asserted the ``inf`` AC-17 was signed on.  The
    documents were corrected to the measured behaviour rather than the code
    changed to manufacture an ``inf`` — see the correction note beside
    AC-17 in ``.autodev/specs/T-2.md``.)
    """
    from demo.pyrunner.rows import read_rows, source_row
    from demo.pyrunner.shape import answer

    conn = db.connect(application_name="autosql-demo-step13")
    try:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        raw = conn.execute(
            "SELECT data::text FROM demo.records"
            " WHERE collection = %(c)s AND key = %(k)s",
            {"c": EDGECASE, "k": "edge-03"},
        ).fetchone()[0]
        rows = read_rows(conn, EDGECASE)
    finally:
        conn.close()

    # ── fact 1 · what jsonb actually handed back ──────────────────────────
    literal = raw.split('"huge":')[1].split(",")[0].strip("} ")
    assert re.fullmatch(r"\d+", literal), (
        "STEP 13's PREMISE MOVED: edge-03's `huge` no longer arrives as a "
        f"bare integer literal — jsonb rendered it as {literal!r}. Every "
        "claim below (and expected-answers.json's derivation for "
        "steps[12].expect.python_pane) rests on jsonb writing its numerics "
        "in full positional digits."
    )
    assert len(literal) == 401, (
        f"edge-03's `huge` is {len(literal)} digits, not the 401 the "
        "walkthrough and expected-answers.json both state for 1e400"
    )

    # ── fact 2 · what json.loads makes of it, in BOTH of B7's parses ──────
    row = source_row(EDGECASE, "edge-03", raw)
    huge = row.record_f["huge"]
    assert isinstance(huge, int) and not isinstance(huge, bool), (
        "STEP 13: `record_f['huge']` is no longer an exact int but a "
        f"{type(huge).__name__}. json.loads returns an int for an integer "
        "literal whatever parse_float says; if that changed, the Python "
        "pane's behaviour on this row changed with it."
    )
    assert not isinstance(huge, float), (
        "STEP 13: `record_f['huge']` came back as a float. If something now "
        "manufactures a float — inf or otherwise — for a 401-digit INTEGER "
        "literal, the demo has started reporting a number Python does not "
        "really produce. W13-2 rules that the wrong fix; correct the "
        "documents, not rows.py."
    )
    assert isinstance(row.record_d["huge"], int), (
        "STEP 13: the exact parse should reach the same int — a Decimal "
        "hook is a parse_float hook and an integer literal never reaches it"
    )
    assert len(str(huge)) == 401, (
        f"STEP 13: the parsed int is {len(str(huge))} digits, not 401 — it "
        "is no longer the value the literal carries"
    )

    # ── fact 3 · the overflow is a RAISE, at the arithmetic, not an inf ───
    with pytest.raises(OverflowError) as raised:
        float(huge)
    assert "too large" in str(raised.value)

    pick = _pick(source=EDGECASE,
                 computed=[{"name": "scaled", "expr": "$.huge * 1"}])
    with pytest.raises(OverflowError) as from_evaluator:
        answer(rows, pick)
    assert "int too large to convert to float" in str(from_evaluator.value), (
        "STEP 13: GIMS's vendored expr.py no longer raises OverflowError on "
        f"this pick — it raised {from_evaluator.value!r} instead. The "
        "Python pane's `raised` state, the note it prints, and "
        "expected-answers.json's steps[12].expect.python_pane all describe "
        "that specific raise."
    )

    # ── and the documents say exactly that, in the same words ─────────────
    documented = json.loads(_ANSWERS_JSON.read_text())[
        "steps"][12]["expect"]["python_pane"]["value"]
    assert documented == "raised", (
        "STEP 13's DOCUMENTED PYTHON ANSWER IS NOT WHAT PYTHON PRODUCES.\n"
        f"  expected-answers.json says steps[12].expect.python_pane == "
        f"{documented!r}.\n"
        "  Measured above: edge-03's `huge` arrives as a bare 401-digit\n"
        "  INTEGER literal, json.loads returns an exact int for it, and\n"
        "  GIMS's own expr.py raises OverflowError converting that int to a\n"
        "  double. No inf is ever created, so the pane's state is `raised`.\n"
        "  W13-2 (demo/server/app.py, above _fallback_python_pane) rules\n"
        "  that raise CORRECT: 'neither side can read it' is a stronger and\n"
        "  truer statement than an inf would be. If this value is being\n"
        "  changed back, the code would have to start manufacturing an inf\n"
        "  for an integer literal — which would make the demo lie about\n"
        "  what Python really does."
    )


# ─────────────────────────────────────────────────────────────────────────
# AC-43(b)(c) — the time bucket under a HOSTILE inherited zone.
#
# "A build that lets the session inherit its zone returns 8 uneven buckets
# here and passes every other criterion in this document." (plan §7)
# ─────────────────────────────────────────────────────────────────────────

HOSTILE_ZONE = "America/New_York"
BUCKET_LABEL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _step_7_on_both_panes(conn):
    """Step 7's seven (label, count) pairs, from each pane's full result."""
    _, sql, python = _full_panes(conn, STEP_PICKS[7])
    out = {}
    for name, pane in (("sql", sql), ("python", python)):
        rows = _cells(pane)
        bi = pane["columns"].index("bucket")
        ai = pane["columns"].index("agg")
        out[name] = [(r[bi], int(Decimal(r[ai]))) for r in rows]
    return out


def test_ac43c_the_bucket_labels_are_fixed_width_utc_strings(ran):
    """AC-43(c) — the label is text, and both panes key their rows by it."""
    _, body = ran[7]
    for pane in ("sql", "python"):
        assert body["panes"][pane]["kinds"][0] == "text", (
            "the bucket is compared as a STRING, not as an instant — two "
            "engines need not spell one moment the same way"
        )
        for row in body["panes"][pane]["rows"]:
            assert BUCKET_LABEL.match(row["c"][0]), f"{row['c'][0]!r} is not the UTC form"
            assert row["c"][0].endswith("T00:00:00Z"), "a `day` bucket starts at UTC midnight"


def test_ac43b_a_hostile_client_zone_does_not_move_the_day_boundary(monkeypatch):
    """AC-43(b), the client half — ``PGTZ`` and ``TZ`` set to New York.

    This is the hostility that actually wins on this machine.  B13-EXT-3
    measured that ``PGTZ`` BEATS the ``options`` string on the connection,
    so the ``-c timezone=UTC`` in ``connection_parameters`` is not what
    saves the answer here — the explicit ``SET TIME ZONE 'UTC'`` is.  Both
    halves are shown: what the session WOULD have run at, and what it does.
    """
    monkeypatch.setenv("PGTZ", HOSTILE_ZONE)
    monkeypatch.setenv("TZ", HOSTILE_ZONE)

    # (i) The hostility is real, and it is shown rather than described.
    #     RESET drops the demo's own SET and restores what the session
    #     opened at — which is the inherited zone, and the day boundary
    #     moves with it.  Done through db.connect(), because AC-2(c)
    #     allows exactly one importer of the driver and this file is
    #     not it.
    probe = db.connect(application_name="autosql-demo-tz-probe")
    try:
        probe.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        assert probe.execute("SHOW TimeZone").fetchone()[0] == "UTC"
        probe.execute("RESET TimeZone")
        inherited, reset_val, source = probe.execute(
            "SELECT setting, reset_val, source FROM pg_settings"
            " WHERE name = 'TimeZone'"
        ).fetchone()
        assert inherited == reset_val == HOSTILE_ZONE, (
            "PGTZ did not reach the session, so this test is not exercising "
            f"the hostility it names (setting={inherited!r})"
        )
        assert source == "client"
        drifted = probe.execute(
            "SELECT to_char(date_trunc('day', (data ->> 'ts')::timestamptz),"
            " 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
            " FROM demo.records WHERE key = 'hb-01-0000'"
        ).fetchone()[0]
        assert drifted == "2026-08-13T00:00:00Z", (
            "an inheriting session should bucket the first beat into the "
            f"PREVIOUS day — that is the 8-uneven-buckets failure; got {drifted!r}"
        )
    finally:
        probe.close()

    # (ii) And the demo survives it, on each pane separately.
    conn = db.connect(application_name="autosql-demo-tz-client")
    try:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        assert conn.execute("SHOW TimeZone").fetchone()[0] == "UTC", (
            "the session inherited the hostile zone"
        )
        panes = _step_7_on_both_panes(conn)
    finally:
        conn.close()
    expected_labels = [f"2026-08-{d}T00:00:00Z" for d in range(14, 21)]
    for name in ("sql", "python"):
        assert [b for b, _ in panes[name]] == expected_labels, f"{name} pane's labels"
        assert [c for _, c in panes[name]] == [1200] * 7, f"{name} pane's counts"
        assert sum(c for _, c in panes[name]) == 8400
    assert panes["sql"] == panes["python"], "the same seven labels on both panes"


def test_ac43b_a_hostile_database_default_does_not_move_it_either(wconn):
    """AC-43(b), the inherited-default half — the container's ``TZ`` analogue.

    NEW RULING (W17-1). The criterion says "start the app with the
    container's ``TZ`` … set to ``America/New_York``".  Restarting
    ``autosql-demo-db`` inside the suite would take the stack down under
    every other test in the run, so the same condition is created where it
    lands: a ``TimeZone`` default attached to the demo's own database,
    which is what a container ``TZ`` ends up being for a session.

    MEASURED, and stated rather than hidden: this half is the WEAKER of the
    two.  With the default in place a fresh ``db.connect()`` session
    reports ``reset_val = 'UTC'`` — the ``-c timezone=UTC`` in the startup
    packet already beats a database-level default, so the explicit ``SET``
    is the second of two protections here.  Under ``PGTZ`` (the test above)
    it is the only one.  Both are asserted; neither is assumed.
    """
    dbname = settings.compose_config()["dbname"]
    admin = db.connect(application_name="autosql-demo-tz-admin", autocommit=True)
    try:
        admin.execute(f'ALTER DATABASE "{dbname}" SET TimeZone TO \'{HOSTILE_ZONE}\'')
        configured = admin.execute(
            "SELECT setconfig FROM pg_db_role_setting s"
            " JOIN pg_database d ON d.oid = s.setdatabase"
            " WHERE d.datname = current_database()"
        ).fetchall()
        assert configured == [([f"TimeZone={HOSTILE_ZONE}"],)], (
            f"the hostile default was not attached to {dbname}: {configured}"
        )
        conn = db.connect(application_name="autosql-demo-tz-server")
        try:
            conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            assert conn.execute("SHOW TimeZone").fetchone()[0] == "UTC"
            panes = _step_7_on_both_panes(conn)
        finally:
            conn.close()
    finally:
        admin.execute(f'ALTER DATABASE "{dbname}" RESET TimeZone')
        left = admin.execute("SELECT count(*) FROM pg_db_role_setting").fetchone()[0]
        admin.close()
        assert left == 0, "the hostile default was not removed"

    expected_labels = [f"2026-08-{d}T00:00:00Z" for d in range(14, 21)]
    for name in ("sql", "python"):
        assert [b for b, _ in panes[name]] == expected_labels, f"{name} pane's labels"
        assert [c for _, c in panes[name]] == [1200] * 7, f"{name} pane's counts"
    assert panes["sql"] == panes["python"]


def test_ac43_the_pinned_zone_is_on_the_screen(ran):
    """AC-43(d)'s walkthrough half — the zone the answer depends on is shown."""
    _, body = ran[7]
    assert body["pinned"]["time_zone"] == settings.TIME_ZONE == "UTC"
    assert body["pinned"]["extra_float_digits"] == settings.EXTRA_FLOAT_DIGITS == "1"
    assert "SET TIME ZONE 'UTC';" in body["sql"]["pane_text"]
    assert "SET extra_float_digits = 1;" in body["sql"]["pane_text"]
