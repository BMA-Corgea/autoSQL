"""The shipping compiler's standing tests.

T-11 promoted `spikes/T-1/proto/compile.py` into `compiler/compile.py` and made
one change: float8-valued results are emitted through `xpr.j(...)` instead of
bare `to_jsonb(...)`, so they stop reading the session's `extra_float_digits`.

Three things have to stay true, and each has a test that would notice:

  * the promotion changed NOTHING ELSE -- asserted by compiling the same
    expressions with both modules and diffing, allowing only that one swap;
  * the shipping compiler's output is immune to the session setting, with the
    FROZEN one asserted to still move as the control;
  * the frozen spike copy is byte-identical to the digest its findings cite.

The database tests need the demo's Postgres (it has the runtime installed):

    ./run-demo up
    AUTOSQL_COMPILER_DSN='host=127.0.0.1 port=55440 user=autosql_demo ...' \\
        demo/.venv/bin/python -m pytest compiler/tests -q

They SKIP without it. Port 55433 is refused: it is a live database.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_COMPILER_DSN")
if DSN and "port=55433" in DSN:
    raise SystemExit("refusing to run against port 55433 — that is a live database")

needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_COMPILER_DSN to the demo's Postgres")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t11_expr", "demo/vendor/expr.py")
SHIPPING = _load("t11_shipping", "compiler/compile.py")
FROZEN = _load("t11_frozen", "spikes/T-1/proto/compile.py")

#: Expressions covering every emission family the compiler has: numeric literals,
#: arithmetic, the numeric builtins, the reducers, and — deliberately — the text
#: and boolean ones that must NOT have been touched.
EXPRESSIONS = [
    "1 / 3", "1787169706037 * 1", "$.a + 1", "$.a - $.b", "- $.a", "$.a * 2",
    "abs($.a)", "floor($.a)", "ceil($.a)", "length($.s)", "count($.l)",
    "min($.l)", "max($.l)", "number($.s)",
    "$.a == $.b", "$.a != $.b", "$.a > $.b", "not $.flag", "$.flag and $.c",
    "$.flag or $.c", "lower($.s)", "upper($.s)", "string($.a)", '"literal"',
]


def _sql(mod, src):
    return mod.compile_ast(EXPR.parse(src))[0]


# ── the promotion changed exactly one thing ───────────────────────────────

@pytest.mark.parametrize("src", EXPRESSIONS)
def test_the_promotion_changed_nothing_but_the_float8_wrapper(src):
    """Compile with both modules; the only permitted difference is to_jsonb -> xpr.j.

    This is the test that makes the promotion trustworthy. Copying a 464-line
    compiler and editing 18 call sites is exactly the kind of change where an
    unrelated edit rides along unnoticed.
    """
    frozen = _sql(FROZEN, src)
    shipping = _sql(SHIPPING, src)
    # Undo the one intended change, then the two must be identical.
    assert shipping.replace("xpr.j(", "to_jsonb(") == frozen, (
        "the shipping compiler differs from the frozen one by more than the "
        "to_jsonb -> xpr.j swap, for %r" % src)


def test_text_and_boolean_results_still_use_to_jsonb():
    """Wrapping them would cost a function call for nothing — neither has digits
    to lose. Asserted so a later 'consistency' pass does not wrap them anyway."""
    for src in ["lower($.s)", "upper($.s)", "string($.a)", '"literal"',
                "not $.flag", "$.a == $.b", "$.flag and $.c"]:
        sql = _sql(SHIPPING, src)
        assert "to_jsonb(" in sql, "%r stopped using to_jsonb" % src
        assert "xpr.j(" not in sql, "%r was wrapped in xpr.j and should not be" % src


def test_numeric_results_all_go_through_xpr_j():
    for src in ["1 / 3", "$.a + 1", "- $.a", "abs($.a)", "floor($.a)",
                "length($.s)", "count($.l)", "max($.l)", "number($.s)"]:
        assert "xpr.j(" in _sql(SHIPPING, src), "%r is not routed through xpr.j" % src


# ── the frozen copy is evidence ───────────────────────────────────────────

def test_the_spike_compiler_is_frozen():
    """Its sha is cited in T-6's attestation and in all 42 battery outputs."""
    got = hashlib.sha256((ROOT / "spikes/T-1/proto/compile.py").read_bytes()).hexdigest()
    assert got[:16] == "b71b153802d0df94", (
        "spikes/T-1/proto/compile.py has been modified — it is evidence, not source")


def test_the_demo_loads_the_shipping_compiler_not_the_spike():
    src = (ROOT / "demo/builder.py").read_text(encoding="utf-8")
    assert '"compiler" / "compile.py"' in src or "compiler/compile.py" in src
    assert '"spikes" / "T-1" / "proto" / "compile.py"' not in src


# ── immunity, with the frozen compiler as the control ─────────────────────

SETTINGS = ("1", "0", "-3")


def _at_each_setting(mod, src):
    """Compile, then run the SAME statement at each setting. The compiler binds
    every literal as a parameter, so the params ride along."""
    import psycopg
    sql, params = mod.compile_ast(EXPR.parse(src))
    out = {}
    for efd in SETTINGS:
        with psycopg.connect(DSN, autocommit=True) as cx:
            cx.execute("SET extra_float_digits = %s" % efd)
            out[efd] = str(cx.execute("select " + sql, params).fetchone()[0])
    return out


#: A non-terminating division: 16 digits at efd 1, 12 at efd -3.
PRECISE = "1 / 3"


@needs_db
def test_the_shipping_compilers_output_is_immune_to_the_setting():
    """The point of T-11. This is the assertion T-6's pass was resting on and
    could not make."""
    got = _at_each_setting(SHIPPING, PRECISE)
    assert len(set(got.values())) == 1, (
        "the compiled output still moves with extra_float_digits: %r" % got)
    assert got["-3"] == "0.3333333333333333"


@needs_db
def test_the_frozen_compilers_output_still_moves():
    """The control. If this ever passes, the test above proves nothing — it
    would mean the platform protects every path and xpr.j is redundant."""
    got = _at_each_setting(FROZEN, PRECISE)
    assert len(set(got.values())) > 1, (
        "the frozen compiler stopped moving with the setting (%r) — the immunity "
        "test above is now vacuous and this pair needs rethinking" % got)
    assert got["-3"] != got["1"]


@needs_db
#: Literal-only, so the statement stands alone with no row source. Field reads
#: are covered end-to-end by the demo's own suite, against real rows.
@pytest.mark.parametrize("src", ["1 / 3", "1787169706037 * 1", "2 / 7", "1 / 7 * 3"])
def test_precise_values_survive_every_setting(src):
    got = _at_each_setting(SHIPPING, src)
    assert len(set(got.values())) == 1, "%r moved: %r" % (src, got)
