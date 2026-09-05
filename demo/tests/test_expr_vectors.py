"""demo/tests/test_expr_vectors.py — AC-19: the static gate over GIMS's 130
expression vectors, **reported, never scored**.

AC-19, in the signed spec's own words, is a *reported observation, not a pass
mark*: with the `GIMS-Project` checkout present, the suite runs
`demo/gate.py`'s gate over all 130 cases of `tests/fixtures/expr_vectors.json`
and **reports the accept/refuse split per case, with no threshold**; with the
checkout absent it **skips loudly** in §9.7's four-part sense. The criterion
passes on the report being produced and being per-case. It never passes or
fails on the number.

**Why it cannot be a pass mark**, restated here because it is the one thing a
future edit is likely to get wrong: 68 of 130 is a **contract-surface** measure
— §0's gloss — a count of how much of the *test file* falls inside the safe
subset, not of how much real use is covered, because no corpus of real use
exists in either checkout. `FINDINGS.md` §5.7(i), citing §5.2, rules that the
fixture is not the acceptance test and that none of these coverage figures may
be quoted at a gate. So this module reports the number and asserts nothing
about it. `test_ac19_this_module_cannot_fail_on_the_number` below is a
mechanical guard on that promise: it reads this file's own syntax tree and
fails if any `assert` here ever mentions the split or the numbers 68 / 62.

**What it does fail on** — the report not being produced:

  * a case that neither accepts nor refuses (a gate crash, an expression the
    parser cannot read, a case with no `expr`),
  * a refusal that does not name a construct **and** the rule it broke ("a
    bare 'refused' is not acceptable" — the gate already names both),
  * a fixture that cannot be parsed at all,
  * a per-case verdict missing from the written report.

**The 130 is reported, not asserted.** AC-19 names "all 130 cases"; if GIMS
ever grows or trims the fixture, this module reports the new count as a FINDING
— in the artifact and on the terminal — and still passes. That is a reading of
AC-19 rather than something its wording settles: the criterion forbids
passing/failing on *the split*, and says nothing about the case count. The
choice made here is that a build must not go red because a tree this ticket
does not own changed underneath it, and the loud finding is what stops the
change from passing unnoticed. One assertion away from the other reading, if
The owner wants it: assert `len(cases) == EXPECTED_CASE_COUNT`.

**§9.7's four-part loud skip, and how each part is met here** — the shape is
`test_vendor.py`'s, and deliberately so: this module imports that module's own
`_resolve_tree` and `_skip_reason` rather than growing a second skip idiom, so
there is exactly one place where "where is the checkout" and "what does a skip
line say" are decided.

  1. Reports SKIPPED, never PASSED and never nothing — `pytest.skip(...)`.
  2. The skip line names the path it looked for **and** `AUTOSQL_GIMS_TREE` as
     the way to point it somewhere else — `_skip_reason(...)` builds both in.
  3. `./run-demo test`'s final summary counts it separately and repeats its
     reason verbatim — `conftest.py` collects the reason text, `./run-demo`
     prints the breakdown; nothing to do here except not swallow the skip.
  4. Everything that does not need the tree still runs: the loud-skip proof and
     the no-threshold guard below are separate test functions that never touch
     a checkout, so the tree-dependent one skipping cannot hide them.

**Nothing here executes anything inside the checkout.** The tree is opened for
one file — the fixture JSON — and read. The parser used is the demo's *own*
vendored `demo/vendor/expr.py` (R4), never the tree's `core/dashboard/expr.py`:
importing from the tree would write `__pycache__` into a read-only checkout,
which is exactly what AC-35 watches for.

Plan §6.2 row 19 files AC-19 under `test_vendor.py`. It lives in its own module
instead, next to its subject and named after the fixture it reads, in the same
`test_*.py` shape as its neighbours; the skip idiom is shared rather than
copied, which is the part that mattered.
"""

from __future__ import annotations

import ast as python_ast
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_THIS_FILE = Path(__file__).resolve()
_TESTS_DIR = _THIS_FILE.parent
_REPO_ROOT = _THIS_FILE.parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from demo.gate import Refused, gate  # noqa: E402
from demo.vendor.expr import parse  # noqa: E402

# The one resolver and the one skip-reason format, borrowed rather than
# re-implemented (see the docstring). A second copy of either is how two
# checks end up looking for two different paths.
from test_vendor import _resolve_tree, _skip_reason  # noqa: E402

#: Where the fixture sits inside a checkout (§9.7's table).
FIXTURE_RELPATH = "tests/fixtures/expr_vectors.json"

#: The count AC-19 names. Reported against, never asserted — see the docstring.
EXPECTED_CASE_COUNT = 130

#: AC-19's "expected reading", quoted so the report can say whether the run
#: matched it. Never compared inside an `assert` — the guard below enforces
#: that mechanically.
EXPECTED_READING = "68 accepted / 62 refused"

#: Where the per-case report is written. A produced artifact at a fixed path
#: under `demo/`, the way `demo/expected-answers.json` is — `demo/EVIDENCE.md`
#: is assembled by hand from files like this one. `AUTOSQL_AC19_REPORT`
#: overrides it, the same way `AUTOSQL_DEMO_TEST_REPORT` overrides the suite's
#: own run report.
DEFAULT_REPORT_PATH = _REPO_ROOT / "demo" / "ac19-expr-vectors.md"

#: The two verdicts AC-19 asks for. Anything else is a report that could not
#: be produced for that case, and is a failure.
VERDICTS = ("accepted", "refused")


def _gims_tree() -> tuple[Path, bool]:
    return _resolve_tree("AUTOSQL_GIMS_TREE", "../GIMS-Project")


def _report_path() -> Path:
    override = os.environ.get("AUTOSQL_AC19_REPORT")
    return Path(override) if override else DEFAULT_REPORT_PATH


def _case_id(case: object, index: int) -> str:
    """`group/name`, the fixture's own two-part identifier.

    Falls back to the ordinal so a case missing either key still gets a
    per-case row rather than vanishing from the report.
    """
    if isinstance(case, dict):
        group = case.get("group")
        name = case.get("name")
        if isinstance(group, str) and isinstance(name, str):
            return f"{group}/{name}"
        if isinstance(name, str):
            return name
    return f"(case {index}, no group/name)"


def _gate_one(case: object, index: int) -> dict:
    """One case in, one per-case row out. Never raises.

    A row always carries a verdict; when that verdict is not `accepted` or
    `refused` it carries why not, and the caller fails the test on it.
    """
    row = {
        "n": index,
        "case": _case_id(case, index),
        "expr": "",
        "verdict": "",
        "construct": "",
        "rule": "",
    }

    if not isinstance(case, dict):
        row["verdict"] = "unreadable"
        row["rule"] = f"the fixture case is a {type(case).__name__}, not an object"
        return row

    source = case.get("expr")
    if not isinstance(source, str):
        row["verdict"] = "unreadable"
        row["rule"] = (
            f"the case carries no `expr` string (found {type(source).__name__})"
        )
        return row
    row["expr"] = source

    try:
        tree = parse(source)
    except Exception as exc:  # noqa: BLE001 — any parse failure is a finding
        row["verdict"] = "unparsed"
        row["construct"] = type(exc).__name__
        row["rule"] = str(exc)
        return row

    try:
        gate(tree)
    except Refused as refusal:
        row["verdict"] = "refused"
        row["construct"] = str(refusal.construct)
        row["rule"] = str(refusal.why)
    except Exception as exc:  # noqa: BLE001 — a gate that crashes is a finding
        row["verdict"] = "crashed"
        row["construct"] = type(exc).__name__
        row["rule"] = str(exc)
    else:
        row["verdict"] = "accepted"
    return row


def _cell(text: str) -> str:
    """One Markdown table cell: no pipes, no line breaks, nothing swallowed."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _headline(rows: list[dict], case_count: int, report_path: Path) -> list[str]:
    """The lines a person reads first — terminal and artifact say the same."""
    accepted = sum(1 for row in rows if row["verdict"] == "accepted")
    refused = sum(1 for row in rows if row["verdict"] == "refused")
    measured = f"{accepted} accepted / {refused} refused"
    lines = [
        f"AC-19 (reported observation, no threshold): {measured} "
        f"of {case_count} fixture cases.",
        f"AC-19's expected reading is {EXPECTED_READING} — this run "
        + ("MATCHES it." if measured == EXPECTED_READING else f"DIFFERS: {measured}."),
    ]
    if case_count != EXPECTED_CASE_COUNT:
        lines.append(
            f"AC-19 FINDING: the fixture carries {case_count} cases, not the "
            f"{EXPECTED_CASE_COUNT} AC-19 names. Reported, not failed — the "
            "checkout is not this ticket's to change."
        )
    lines.append(f"AC-19 per-case report written to {report_path}")
    return lines


def _render_report(
    rows: list[dict],
    fixture: Path,
    payload: dict,
    case_count: int,
    report_path: Path,
) -> str:
    accepted = sum(1 for row in rows if row["verdict"] == "accepted")
    refused = sum(1 for row in rows if row["verdict"] == "refused")
    other = [row for row in rows if row["verdict"] not in VERDICTS]

    by_construct: dict[str, int] = {}
    for row in rows:
        if row["verdict"] == "refused":
            by_construct[row["construct"]] = by_construct.get(row["construct"], 0) + 1

    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()

    out: list[str] = []
    out.append("# AC-19 — the static gate over GIMS's expression vectors")
    out.append("")
    out.append(
        "**A reported observation, not a pass mark.** Produced by "
        "`demo/tests/test_expr_vectors.py` on every `./run-demo test` that can "
        "see a `GIMS-Project` checkout; the run that cannot see one skips "
        "loudly instead and leaves this file as it stood. Nothing in the suite "
        "passes or fails on the split below — see the criterion, and the module "
        "docstring, for why it cannot."
    )
    out.append("")
    out.append("## What was read, and with what")
    out.append("")
    out.append("| | |")
    out.append("|---|---|")
    out.append(f"| fixture | `{_cell(str(fixture))}` |")
    out.append(f"| fixture sha256 | `{digest}` |")
    out.append(f"| fixture bytes | {fixture.stat().st_size:,} |")
    out.append(f"| fixture `version` | `{_cell(repr(payload.get('version')))}` |")
    out.append(
        f"| fixture `float_epsilon` | `{_cell(repr(payload.get('float_epsilon')))}` |"
    )
    out.append(f"| cases | {case_count} (AC-19 names {EXPECTED_CASE_COUNT}) |")
    out.append("| gate | `demo/gate.py` — the 32-construct allowlist over the 12 AST tags |")
    out.append(
        "| parser | `demo/vendor/expr.py` — the demo's own vendored copy (R4), "
        "never the checkout's, so nothing is executed inside a read-only tree |"
    )
    out.append("")
    out.append("## The split")
    out.append("")
    for line in _headline(rows, case_count, report_path):
        out.append(f"- {line}")
    out.append("")
    out.append(
        "Read it as §0 defines it: a **contract-surface** count — how much of "
        "*this test file* falls inside the safe subset — and never as how much "
        "of real use is covered. No corpus of real use exists in either "
        "checkout, and `FINDINGS.md` §5.7(i) rules that this figure may not be "
        "quoted at a gate."
    )
    out.append("")
    if other:
        out.append("### Cases that produced no verdict")
        out.append("")
        out.append(
            "These are what AC-19 *does* fail on: a case that neither accepts "
            "nor refuses means the report could not be produced."
        )
        out.append("")
        for row in other:
            out.append(
                f"- `{_cell(row['case'])}` — **{_cell(row['verdict'])}** — "
                f"{_cell(row['construct'])}: {_cell(row['rule'])}"
            )
        out.append("")
    out.append("## Refusals by construct")
    out.append("")
    out.append("| construct | cases refused |")
    out.append("|---|---|")
    for construct, count in sorted(by_construct.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"| `{_cell(construct)}` | {count} |")
    out.append("")
    out.append(
        f"{accepted} cases were accepted and are not listed here; every one of "
        f"them appears in the per-case table below, and {refused} refusals name "
        "the construct that stopped them."
    )
    out.append("")
    out.append("## Every case, one row each")
    out.append("")
    out.append(
        "`construct` and `rule` are the gate's own words for a refusal — the "
        "two things AC-19 requires instead of a bare \"refused\"."
    )
    out.append("")
    out.append("| # | case | expression | verdict | construct | rule |")
    out.append("|---:|---|---|---|---|---|")
    for row in rows:
        out.append(
            f"| {row['n']} | `{_cell(row['case'])}` | `{_cell(row['expr'])}` | "
            f"{_cell(row['verdict'])} | "
            f"{('`' + _cell(row['construct']) + '`') if row['construct'] else '—'} | "
            f"{_cell(row['rule']) if row['rule'] else '—'} |"
        )
    out.append("")
    return "\n".join(out)


# =====================================================================
# AC-19 — the tree-dependent half: one report, per case, no threshold
# =====================================================================


def test_ac19_the_gate_over_every_fixture_case_reported_per_case(pytestconfig) -> None:
    """Run the gate over every case the fixture carries and report each one.

    The report is written **before** any assertion below, so a run that fails
    on a case that produced no verdict still leaves the evidence of which case
    it was.
    """
    tree_path, present = _gims_tree()
    if not present:
        pytest.skip(
            _skip_reason(
                "AC-19",
                f"the {EXPECTED_CASE_COUNT} fixture cases at {FIXTURE_RELPATH}",
                "AUTOSQL_GIMS_TREE",
                tree_path,
            )
        )

    fixture = tree_path / FIXTURE_RELPATH
    if not fixture.is_file():
        # A checkout that is present but carries no fixture: the same loud
        # shape (what was looked for, and the variable that moves it), because
        # the cases still do not exist here and a silent pass would be worse.
        pytest.skip(
            f"AC-19 (fixture half): the GIMS checkout at {tree_path} carries no "
            f"{FIXTURE_RELPATH} — set AUTOSQL_GIMS_TREE to point at one that does"
        )

    # A fixture that will not parse is AC-19's "malformed fixture": it fails
    # here, loudly, with the path in the message rather than a bare traceback.
    try:
        payload = json.loads(fixture.read_text())
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"AC-19: {fixture} is not readable JSON ({type(exc).__name__}: {exc})")

    cases = payload.get("cases") if isinstance(payload, dict) else None
    assert isinstance(cases, list) and cases, (
        f"AC-19: {fixture} has no non-empty `cases` list — the report cannot be "
        "produced from it"
    )

    rows = [_gate_one(case, index) for index, case in enumerate(cases, start=1)]
    case_count = len(cases)
    report_path = _report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report(rows, fixture, payload, case_count, report_path)
    )

    reporter = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line("")
        for line in _headline(rows, case_count, report_path):
            reporter.write_line(line)

    # ---- what the criterion actually fails on -----------------------------
    no_verdict = [row for row in rows if row["verdict"] not in VERDICTS]
    assert not no_verdict, (
        "AC-19: these cases neither accepted nor refused, so the report could "
        "not be produced for them:\n"
        + "\n".join(
            f"  {row['case']}: {row['verdict']} — {row['construct']}: {row['rule']}"
            for row in no_verdict
        )
    )

    unnamed = [
        row
        for row in rows
        if row["verdict"] == "refused" and not (row["construct"] and row["rule"])
    ]
    assert not unnamed, (
        "AC-19: these refusals name neither the construct nor the rule; a bare "
        "'refused' is not a per-case verdict:\n"
        + "\n".join(f"  {row['case']}" for row in unnamed)
    )

    # ---- the report really is per case, read back off disk -----------------
    # Per case means per case: every one of the fixture's cases must have its
    # own row in the written file, carrying its own verdict — not a total at
    # the top and a count at the bottom.
    assert len(rows) == case_count
    written_lines = _report_path().read_text().splitlines()
    missing: list[str] = []
    for row in rows:
        own_row = [line for line in written_lines if f"| `{_cell(row['case'])}` |" in line]
        if not own_row:
            missing.append(f"{row['case']}: no row in the report")
        elif not any(f"| {_cell(row['verdict'])} |" in line for line in own_row):
            missing.append(f"{row['case']}: a row, but no verdict on it")
    assert not missing, (
        f"AC-19: {len(missing)} of {case_count} cases have no per-case verdict "
        f"in {report_path}:\n  " + "\n  ".join(missing[:10])
    )


# =====================================================================
# The halves that need no checkout, and must never skip (AC-39(a)/(b))
# =====================================================================


def test_ac19_skips_loudly_when_the_checkout_is_absent() -> None:
    """AC-19's second leg, proven in-process rather than by today's machine.

    `./run-demo test` with `AUTOSQL_GIMS_TREE` pointed at a path that does not
    exist must report SKIPPED for AC-19 and name the path. pytest supplies the
    SKIPPED verdict (part 1); this asserts the rest of §9.7 — that the resolver
    calls a non-existent path absent, and that the reason text names both the
    path it looked for and the variable that moves it.
    """
    nowhere = Path("/nope/GIMS-Project")
    reason = _skip_reason(
        "AC-19",
        f"the {EXPECTED_CASE_COUNT} fixture cases at {FIXTURE_RELPATH}",
        "AUTOSQL_GIMS_TREE",
        nowhere,
    )
    assert "AC-19" in reason
    assert str(nowhere) in reason, "§9.7 part 2: the skip line must name the path"
    assert "AUTOSQL_GIMS_TREE" in reason, "§9.7 part 2: and the override variable"
    assert FIXTURE_RELPATH in reason, "and what inside the checkout it wanted"

    # The resolver itself, on a path that does not exist, calls it absent —
    # the precondition the tree-dependent test above skips on.
    _, present = _resolve_tree(
        "AUTOSQL_GIMS_TREE_TEST_ONLY_DOES_NOT_EXIST", "does/not/exist"
    )
    assert present is False

    # And this module shares test_vendor.py's resolver rather than carrying a
    # second one, so a checkout can never be "present" for one check and
    # "absent" for another in the same run.
    assert _gims_tree()[0] == _resolve_tree("AUTOSQL_GIMS_TREE", "../GIMS-Project")[0]


def test_ac19_this_module_cannot_fail_on_the_number() -> None:
    """The mechanical guard on AC-19's hardest sentence.

    "It never passes or fails on the number." Read this file's own syntax tree
    and fail if any `assert` in it mentions the split counts or the expected
    reading's numbers. A future edit that quietly turns the report into a
    threshold trips this rather than shipping.
    """
    tree = python_ast.parse(_THIS_FILE.read_text())
    forbidden_numbers = {68, 62}
    forbidden_names = {"accepted", "refused", "split", "EXPECTED_READING"}
    offenders: list[str] = []

    for node in python_ast.walk(tree):
        if not isinstance(node, python_ast.Assert):
            continue
        for inner in python_ast.walk(node.test):
            if (
                isinstance(inner, python_ast.Constant)
                and isinstance(inner.value, int)
                and not isinstance(inner.value, bool)
                and inner.value in forbidden_numbers
            ):
                offenders.append(
                    f"line {node.lineno}: an assert compares against {inner.value}"
                )
            if isinstance(inner, python_ast.Name) and inner.id in forbidden_names:
                offenders.append(
                    f"line {node.lineno}: an assert reads `{inner.id}`, one of the "
                    "split's own names"
                )

    assert not offenders, (
        "AC-19 says the criterion 'never passes or fails on the number', and "
        "this module has grown an assertion that does exactly that:\n  "
        + "\n  ".join(offenders)
    )


def test_ac19_the_report_path_is_where_a_person_can_read_it() -> None:
    """The artifact is a committed, human-readable file under `demo/`, at a
    fixed path, the way `demo/expected-answers.json` is — not a temporary file
    that vanishes with the run. Checked without needing a checkout, so a
    skipped run still proves where the report would land."""
    assert DEFAULT_REPORT_PATH.parent == _REPO_ROOT / "demo"
    assert DEFAULT_REPORT_PATH.suffix == ".md"
    assert not str(DEFAULT_REPORT_PATH).startswith("/tmp")
