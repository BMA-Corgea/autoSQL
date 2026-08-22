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
