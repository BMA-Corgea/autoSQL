"""AC-14 -- the static gate accepts exactly the 32 in-subset constructs and
refuses exactly the 16 excluded ones, tested construct by construct.

Three halves, all required (spec §12 AC-14):

  1. The 48-row census table (f2 §2.1 granularity, spec §4.2): 10 leaf/structural
     node types + 5 arithmetic operators + 6 comparisons + 5 field-path forms +
     all 22 functions.  32 accepted, 16 refused, every refusal naming the
     offending construct.
  2. The tag half: all TWELVE AST tags accepted at the tag, an invented
     thirteenth refused.  This is what catches a gate built against the
     ten-construct count (mutant M12): such a gate passes the leaf rows above
     and still refuses `$.status == "ok"`.
  3. The |index| < 2**31 boundary, both directions, exact.

Plus fails-closed checks the criterion does not ask for but the file's job does:
malformed nodes refuse rather than crash, deep trees exhaust nothing, and the
gate module imports neither the compiler nor the evaluator.

Every census row carries BOTH a source string and the hand-pinned AST the real
parser produces for it.  When the parser is importable the row first asserts
parse(src) == pinned_ast -- so the table can never drift from the language it
claims to gate -- and gates the parsed tree; without a parser the pinned trees
still drive all 48 verdicts.
"""

from __future__ import annotations

import ast as python_ast
import importlib.util
import os
import sys
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).resolve().parents[1]
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from gate import (  # noqa: E402
    ALLOWED_BIN_OPS,
    ALLOWED_CMP_OPS,
    ALLOWED_FUNCTIONS,
    ALLOWED_TAGS,
    MAX_INDEX_EXCLUSIVE,
    Refused,
    gate,
)

# ---------------------------------------------------------------------------------
# The parser.  The demo's own vendored copy is the one obligated source (R4);
# until W2 lands it, the sibling GIMS checkout (read-only, resolved exactly as
# spec §9.7 resolves it: AUTOSQL_GIMS_TREE, else <repo root>/../GIMS-Project)
# fills the same role.  AC-14 is NOT on the skippable list, so if neither source
# exists the parser-agreement assertions are the only thing lost -- the 48 rows
# still run on the pinned trees -- and test_parser_source_present fails loudly,
# naming both paths, so the diminished run cannot read as a full one.
# ---------------------------------------------------------------------------------

_VENDORED = DEMO_DIR / "vendor" / "expr.py"
_GIMS_ROOT = Path(
    os.environ.get("AUTOSQL_GIMS_TREE") or str(DEMO_DIR.parent.parent / "GIMS-Project")
)
_SIBLING = _GIMS_ROOT / "core" / "dashboard" / "expr.py"


def _find_expr_source():
    if _VENDORED.is_file():
        return _VENDORED
    if _SIBLING.is_file():
        return _SIBLING
    return None


_EXPR_PATH = _find_expr_source()


def _load_parse():
    spec = importlib.util.spec_from_file_location("autosql_test_expr", _EXPR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse


parse = _load_parse() if _EXPR_PATH is not None else None


def test_parser_source_present():
    """A run without any parser is a diminished run and must say so, loudly."""
    assert _EXPR_PATH is not None, (
        "no expression parser found: neither the vendored copy at "
        f"{_VENDORED} nor a GIMS checkout at {_SIBLING} "
        "(point AUTOSQL_GIMS_TREE at one). The 48 census rows above still ran "
        "on the pinned ASTs, but nothing has confirmed those trees against the "
        "real parser in this run."
    )


# ---------------------------------------------------------------------------------
# Half 1 -- the 48-row census.  (construct, source, pinned AST, verdict)
# ---------------------------------------------------------------------------------

A = "accept"
R = "refuse"

ROWS = [
    # -- the 10 leaf / structural node types (spec §4.2) -- all accepted --------
    ("num-literal", "1.5", ("num", 1.5), A),
    ("str-literal", '"ok"', ("str", "ok"), A),
    ("bool-literal", "true", ("bool", True), A),
    ("null-literal", "null", ("null",), A),
    ("field-access", "$.status", ("field", [("key", "status")]), A),
    ("neg", "-$.payload.load", ("neg", ("field", [("key", "payload"), ("key", "load")])), A),
    ("not", "not $.ok", ("not", ("field", [("key", "ok")])), A),
    ("and", "true and $.ok", ("and", ("bool", True), ("field", [("key", "ok")])), A),
    ("or", "false or $.ok", ("or", ("bool", False), ("field", [("key", "ok")])), A),
    ("call", "length($.name)", ("call", "length", [("field", [("key", "name")])]), A),
    # -- the 5 arithmetic operators: 4 accepted, `%` refused --------------------
    ("+", "$.a + 1", ("bin", "+", ("field", [("key", "a")]), ("num", 1.0)), A),
    ("-", "$.a - 1", ("bin", "-", ("field", [("key", "a")]), ("num", 1.0)), A),
    ("*", "$.a * 2", ("bin", "*", ("field", [("key", "a")]), ("num", 2.0)), A),
    ("/", "$.a / 2", ("bin", "/", ("field", [("key", "a")]), ("num", 2.0)), A),
    ("%", "$.a % 2", ("bin", "%", ("field", [("key", "a")]), ("num", 2.0)), R),
    # -- all 6 comparisons -- accepted (the ==/!= container qualifier is
    #    layer 2's, spec §4.3/§4.6; a gate that guessed would over- or under-refuse)
    ("==", '$.status == "ok"', ("cmp", "==", ("field", [("key", "status")]), ("str", "ok")), A),
    ("!=", '$.status != "ok"', ("cmp", "!=", ("field", [("key", "status")]), ("str", "ok")), A),
    ("<", "$.payload.load < 10",
     ("cmp", "<", ("field", [("key", "payload"), ("key", "load")]), ("num", 10.0)), A),
    ("<=", "$.payload.load <= 10",
     ("cmp", "<=", ("field", [("key", "payload"), ("key", "load")]), ("num", 10.0)), A),
    (">", "$.payload.load > 80",
     ("cmp", ">", ("field", [("key", "payload"), ("key", "load")]), ("num", 80.0)), A),
    (">=", "$.payload.load >= 80",
     ("cmp", ">=", ("field", [("key", "payload"), ("key", "load")]), ("num", 80.0)), A),
    # -- the 5 field-path forms (expr.py:215-246) -- all accepted ---------------
    ("bare-$", "$", ("field", []), A),
    (".ident", "$.sender_id", ("field", [("key", "sender_id")]), A),
    ('["quoted"]', '$["a b"]', ("field", [("key", "a b")]), A),
    ("[n]", "$.l[0]", ("field", [("key", "l"), ("index", 0)]), A),
    ("[-n]", "$.l[-1]", ("field", [("key", "l"), ("index", -1)]), A),
    # -- all 22 functions: the 7 in-subset accepted -----------------------------
    ("abs", "abs(-3)", ("call", "abs", [("neg", ("num", 3.0))]), A),
    ("coalesce", "coalesce($.a, 0)",
     ("call", "coalesce", [("field", [("key", "a")]), ("num", 0.0)]), A),
    ("count", "count($.a)", ("call", "count", [("field", [("key", "a")])]), A),
    ("if", "if($.ok, 1, 0)",
     ("call", "if", [("field", [("key", "ok")]), ("num", 1.0), ("num", 0.0)]), A),
    ("length", 'length("abc")', ("call", "length", [("str", "abc")]), A),
    ("max", "max($.a, $.b)",
     ("call", "max", [("field", [("key", "a")]), ("field", [("key", "b")])]), A),
    ("min", "min($.a, $.b)",
     ("call", "min", [("field", [("key", "a")]), ("field", [("key", "b")])]), A),
    # -- ... and the 15 out-of-subset ones refused, each by name ----------------
    # walkthrough step 10 types exactly this row's expression:
    ("round", "round($.payload.load, 1)",
     ("call", "round", [("field", [("key", "payload"), ("key", "load")]), ("num", 1.0)]), R),
    ("floor", "floor($.a)", ("call", "floor", [("field", [("key", "a")])]), R),
    ("ceil", "ceil($.a)", ("call", "ceil", [("field", [("key", "a")])]), R),
    ("sum", "sum($.a)", ("call", "sum", [("field", [("key", "a")])]), R),
    ("avg", "avg($.a)", ("call", "avg", [("field", [("key", "a")])]), R),
    ("string", "string($.a)", ("call", "string", [("field", [("key", "a")])]), R),
    ("number", 'number("3")', ("call", "number", [("str", "3")]), R),
    ("concat", 'concat($.a, "x")',
     ("call", "concat", [("field", [("key", "a")]), ("str", "x")]), R),
    ("contains", 'contains($.a, "x")',
     ("call", "contains", [("field", [("key", "a")]), ("str", "x")]), R),
    ("lower", "lower($.a)", ("call", "lower", [("field", [("key", "a")])]), R),
    ("upper", "upper($.a)", ("call", "upper", [("field", [("key", "a")])]), R),
    ("today", "today()", ("call", "today", []), R),
    ("now", "now()", ("call", "now", []), R),
    ("days_between", "days_between($.a, $.b)",
     ("call", "days_between", [("field", [("key", "a")]), ("field", [("key", "b")])]), R),
    ("date_add", "date_add($.a, 1)",
     ("call", "date_add", [("field", [("key", "a")]), ("num", 1.0)]), R),
]

_ROW_IDS = [f"{i + 1:02d}-{row[0]}" for i, row in enumerate(ROWS)]


def test_census_is_exactly_48_rows_32_accepted_16_refused():
    """The arithmetic of spec §4.2, asserted on the table itself so a dropped or
    duplicated row is a loud failure rather than a quietly smaller census."""
    assert len(ROWS) == 48
    assert len({row[0] for row in ROWS}) == 48  # 48 DISTINCT constructs
    accepted = [row[0] for row in ROWS if row[3] == A]
    refused = [row[0] for row in ROWS if row[3] == R]
    assert len(accepted) == 32
    assert len(refused) == 16
    # the 16 refused constructs, by name (spec §4.2's table)
    assert set(refused) == {
        "%",
        "round", "floor", "ceil",
        "sum", "avg",
        "string", "number",
        "concat", "contains", "lower", "upper",
        "today", "now", "days_between", "date_add",
    }


@pytest.mark.parametrize("construct,src,pinned,verdict", ROWS, ids=_ROW_IDS)
def test_census_row(construct, src, pinned, verdict):
    tree = pinned
    if parse is not None:
        parsed = parse(src)
        assert parsed == pinned, (
            f"the pinned AST for {src!r} does not match what the real parser "
            f"produces -- the census would be gating a different language"
        )
        tree = parsed
    if verdict == A:
        assert gate(tree) is None
    else:
        with pytest.raises(Refused) as exc:
            gate(tree)
        # every refusal names the offending construct -- a bare "invalid" fails
        assert exc.value.construct == construct
        assert construct in str(exc.value)
        assert "invalid input" not in str(exc.value).lower()
        assert "invalid expression" not in str(exc.value).lower()


def test_walkthrough_step_10_reads_the_construct_name():
    """Step 10's refusal must be readable as '`round` is outside the safe
    subset', never 'invalid expression' (spec §4.4)."""
    tree = ("call", "round", [("field", [("key", "payload"), ("key", "load")]), ("num", 1.0)])
    if parse is not None:
        tree = parse("round($.payload.load, 1)")
    with pytest.raises(Refused) as exc:
        gate(tree)
    assert "`round` is outside the safe subset" in str(exc.value)


# ---------------------------------------------------------------------------------
# Half 2 -- the tag check, over all twelve tags, plus a thirteenth.
# ---------------------------------------------------------------------------------

TAG_NODES = [
    ("num", ("num", 1.0)),
    ("str", ("str", "x")),
    ("bool", ("bool", True)),
    ("null", ("null",)),
    ("field", ("field", [("key", "a")])),
    ("neg", ("neg", ("num", 1.0))),
    ("not", ("not", ("bool", True))),
    ("and", ("and", ("bool", True), ("bool", False))),
    ("or", ("or", ("bool", True), ("bool", False))),
    ("cmp", ("cmp", "==", ("num", 1.0), ("num", 2.0))),
    ("bin", ("bin", "+", ("num", 1.0), ("num", 2.0))),
    ("call", ("call", "abs", [("num", 1.0)])),
]


def test_the_tag_universe_is_exactly_twelve():
    tags = [tag for tag, _ in TAG_NODES]
    assert len(tags) == 12
    # pinned literally here, NOT read from the module under test
    assert set(tags) == {
        "num", "str", "bool", "null", "field", "neg", "not",
        "and", "or", "cmp", "bin", "call",
    }
    assert set(tags) == ALLOWED_TAGS


@pytest.mark.parametrize("tag,node", TAG_NODES, ids=[t for t, _ in TAG_NODES])
def test_each_of_the_twelve_tags_is_accepted_at_the_tag(tag, node):
    """The M12 mutant -- a gate accepting only the ten leaf/structural tags --
    fails here on `cmp` and `bin`, exactly as AC-14's tag half intends."""
    assert gate(node) is None


@pytest.mark.parametrize(
    "node",
    [
        ("frob",),
        ("frob", ("num", 1.0)),
        ("sum", [("num", 1.0)]),  # a FUNCTION name smuggled in as a tag
        ("select", "x"),
    ],
    ids=["frob-bare", "frob-child", "sum-as-tag", "select-as-tag"],
)
def test_a_thirteenth_tag_is_refused_by_name(node):
    with pytest.raises(Refused) as exc:
        gate(node)
    assert exc.value.construct == node[0]
    assert node[0] in str(exc.value)
    assert "invalid input" not in str(exc.value).lower()


def test_bin_is_refused_at_the_operator_not_at_the_tag():
    """`%` inside a `bin` node: the tag row is permissive on purpose (spec §4.4);
    the refusal must name `%`, never call `bin` an unknown construct."""
    with pytest.raises(Refused) as exc:
        gate(("bin", "%", ("num", 1.0), ("num", 2.0)))
    assert exc.value.construct == "%"
    assert "`%` is outside the safe subset" in str(exc.value)


def test_cmp_unknown_operator_is_refused_by_operator_name():
    with pytest.raises(Refused) as exc:
        gate(("cmp", "~", ("num", 1.0), ("num", 2.0)))
    assert exc.value.construct == "~"


def test_bin_unknown_operator_is_refused_by_operator_name():
    with pytest.raises(Refused) as exc:
        gate(("bin", "**", ("num", 1.0), ("num", 2.0)))
    assert exc.value.construct == "**"


# ---------------------------------------------------------------------------------
# Half 3 -- |index| < 2**31, at the boundary, both directions, exact.
# ---------------------------------------------------------------------------------

BOUNDARY = [
    ("$.l[2147483647]", 2147483647, A),    # 2**31 - 1: the largest allowed
    ("$.l[2147483648]", 2147483648, R),    # 2**31 exactly: refused
    ("$.l[-2147483647]", -2147483647, A),  # -(2**31 - 1): the most negative allowed
    ("$.l[-2147483648]", -2147483648, R),  # |-2**31| = 2**31: refused -- the rule
                                           # is |index| < 2**31, exact, even though
                                           # int4 itself could hold this one value
]


@pytest.mark.parametrize("src,index,verdict", BOUNDARY, ids=[b[0] for b in BOUNDARY])
def test_index_boundary(src, index, verdict):
    pinned = ("field", [("key", "l"), ("index", index)])
    tree = pinned
    if parse is not None:
        parsed = parse(src)
        assert parsed == pinned
        tree = parsed
    if verdict == A:
        assert gate(tree) is None
    else:
        with pytest.raises(Refused) as exc:
            gate(tree)
        assert exc.value.construct == f"[{index}]"
        assert str(index) in str(exc.value)
        assert "2**31" in str(exc.value)


def test_max_index_constant_is_exact():
    assert MAX_INDEX_EXCLUSIVE == 2147483648


# ---------------------------------------------------------------------------------
# The refusal is the FIRST offender in reading order, wherever it hides.
# ---------------------------------------------------------------------------------

def test_offender_nested_in_accepted_arithmetic_is_named():
    tree = ("bin", "+", ("num", 1.0),
            ("call", "round", [("field", [("key", "a")]), ("num", 0.0)]))
    if parse is not None:
        tree = parse("1 + round($.a, 0)")
    with pytest.raises(Refused) as exc:
        gate(tree)
    assert exc.value.construct == "round"


def test_offender_nested_in_accepted_call_is_named():
    tree = ("call", "abs", [("call", "sum", [("field", [("key", "a")])])])
    if parse is not None:
        tree = parse("abs(sum($.a))")
    with pytest.raises(Refused) as exc:
        gate(tree)
    assert exc.value.construct == "sum"


def test_two_offenders_name_the_left_one():
    tree = ("bin", "+",
            ("call", "round", [("field", [("key", "a")]), ("num", 0.0)]),
            ("call", "sum", [("field", [("key", "b")])]))
    if parse is not None:
        tree = parse("round($.a, 0) + sum($.b)")
    with pytest.raises(Refused) as exc:
        gate(tree)
    assert exc.value.construct == "round"


# ---------------------------------------------------------------------------------
# Fails closed: shapes the parser can never produce refuse -- they never crash
# and are never quietly accepted.
# ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "junk",
    [
        None,
        42,
        "x == 1",          # a source STRING is not a parsed tree
        (),
        ("num",),
        ("num", "1"),
        ("num", True),     # bool masquerading as a number
        ("str", 3),
        ("bool", 1),
        ("null", None),
        ("field", "nope"),
        ("field", [("key", 3)]),
        ("field", [("index", True)]),   # bool masquerading as an index
        ("field", [("index", "0")]),
        ("neg",),
        ("and", ("bool", True)),        # arity 2, needs 3
        ("cmp", "==", ("num", 1.0)),    # arity 3, needs 4
        ("bin", "+", ("num", 1.0)),
        ("call", "abs"),                # no args element
        ("call", 42, []),
        ("call", "abs", ("num", 1.0)),  # args not a list
        (3, "x"),                       # tag not a string
    ],
    ids=lambda j: repr(j)[:40],
)
def test_malformed_nodes_are_refused_not_crashed(junk):
    with pytest.raises(Refused) as exc:
        gate(junk)
    assert "invalid input" not in str(exc.value).lower()


def test_unknown_field_path_step_is_refused_by_name():
    with pytest.raises(Refused) as exc:
        gate(("field", [("slice", "0:2")]))
    assert exc.value.construct == "slice"


def test_a_deep_tree_exhausts_nothing():
    """The walk is iterative: 50,000 levels neither crash nor mask a verdict."""
    node = ("num", 1.0)
    for _ in range(50_000):
        node = ("neg", node)
    assert gate(node) is None

    offender = ("call", "round", [("num", 1.0)])
    node = offender
    for _ in range(50_000):
        node = ("not", node)
    with pytest.raises(Refused) as exc:
        gate(node)
    assert exc.value.construct == "round"


# ---------------------------------------------------------------------------------
# The gate is freestanding and its allowlists are the pinned literals.
# ---------------------------------------------------------------------------------

def test_gate_module_imports_only_the_stdlib_re():
    """The gate reads trees; it must not import the compiler it stands in front
    of (R3), the evaluator, or anything else that could widen quietly."""
    import gate as gate_module

    source = Path(gate_module.__file__).read_text(encoding="utf-8")
    imported = set()
    for stmt in python_ast.walk(python_ast.parse(source)):
        if isinstance(stmt, python_ast.Import):
            imported.update(alias.name for alias in stmt.names)
        elif isinstance(stmt, python_ast.ImportFrom):
            imported.add(stmt.module or "")
    assert imported <= {"re", "__future__"}, f"unexpected imports: {imported}"


def test_allowlists_are_exactly_the_subset_definition():
    """Pinned literally HERE, so the test's expectation cannot be read out of
    the code under test."""
    assert ALLOWED_FUNCTIONS == {"abs", "coalesce", "count", "if", "length", "max", "min"}
    assert ALLOWED_BIN_OPS == {"+", "-", "*", "/"}
    assert ALLOWED_CMP_OPS == {"==", "!=", "<", "<=", ">", ">="}
    assert len(ALLOWED_TAGS) == 12
