"""T-44 LEVER (b): the shipping compiler with its number checks written inline.

A SUBCLASS of compiler/compile.py's _Compiler. It is loaded by path, never copied, so
everything not overridden here is the shipping compiler byte for byte. T-44 FRAMING section
3.2 is the specification. Four changes, each claimed EXACT against the shipping compiler. The
claim is proved by the batteries (K1-K3), and by identity at scale (K5), not by this
docstring:

1. THE FLOAT8 CHANNEL. A node whose value is always a number or null (_is_num) keeps its
   value as float8 between operations. The shipping compiler turns every intermediate number
   into jsonb (xpr.j) and back again (xpr.num). For finite x that round trip is the identity:
   float8 -> shortest round-trip text -> numeric -> the same text -> float8. Postgres float8
   arithmetic raises rather than produce an infinity, so no non-finite value ever enters the
   channel. The one difference is the sign of zero (jsonb has no -0). It cannot be observed in
   any result: -0.0 and 0.0 compare equal, both are rejected as divisors, and both print "0".

2. THE INLINE COERCION, wherever a jsonb value must become a number and the jsonb expression
   is cheap enough to repeat (a field path, a constant, or a coalesce of those):
      number   in range  -> the native cast; beyond DBL_MAX -> the unchanged xpr.f8, so the
                            named refusal XPR01 survives. The range literal is READ from the
                            shipping runtime, never retyped here.
      string   plain ASCII decimal, no surrounding space, no exponent, under 300 characters
                            -> the native cast. Such a string has magnitude below 1e299 and
                            above 1e-299, so the cast can neither overflow nor underflow. It
                            is exactly what xpr.num returns: btrim is the identity, the regex
                            accepts it, numeric cannot overflow, the DBL_MAX check passes,
                            and the result is t::float8.
               anything else (whitespace, exponent, non-ASCII digits, long) -> xpr.num.
      boolean  -> 1.0 / 0.0, as xpr.num does.
      other    -> NULL, as xpr.num does (SQL NULL has a NULL jsonb_typeof).
   An expensive jsonb expression goes to the unchanged xpr.num instead. That keeps the
   generated SQL linear in the size of the AST.

3. NATIVE ORDERING when both sides of < <= > >= are in the float8 channel. xpr.ord on two
   numbers is exactly the float8 comparison, with NULL when either side is NULL.

4. compile_predicate(): the boolean the timed arms filter with. The shipping harness wraps the
   value as xpr.truthy(<jsonb>), and truthy(to_jsonb(b)) is exactly COALESCE(b, false). Only an
   ORDERING comparison is rewritten. Everything else falls back to xpr.truthy(<jsonb>), so the
   evaluation order of AND/OR is never exposed to the planner's qual reordering.
"""
from __future__ import annotations

import importlib.util
import math
import os
import re
from typing import Any, Tuple

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_SHIP_PATH = os.path.join(_ROOT, "compiler", "compile.py")
_spec = importlib.util.spec_from_file_location("autosql_shipping_compile", _SHIP_PATH)
ship = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ship)

# Re-exported so callers (differ.py, the fixture, the timing harness) see the shipping types.
Uncompilable = ship.Uncompilable
Compiled = ship.Compiled
KNOWN_DIVERGENCES = ship.KNOWN_DIVERGENCES
render_for_display = ship.render_for_display
MAX_SQL_CHARS = ship.MAX_SQL_CHARS

# The DBL_MAX guard literal, read from the shipping runtime so the inline range check and
# xpr.f8's refusal can never disagree about where the boundary is.
_RT = open(os.path.join(_ROOT, "runtime", "runtime.sql"), encoding="utf-8").read()
_lits = set(re.findall(r"abs\(n\) > (\d+)::numeric", _RT))
assert len(_lits) == 1, f"expected one DBL_MAX literal in runtime.sql, found {len(_lits)}"
DBL_MAX_LIT = _lits.pop()
assert len(DBL_MAX_LIT) == 309 and DBL_MAX_LIT.startswith("17976931348623157"), DBL_MAX_LIT

_PLAIN_DECIMAL = r"^[+-]?([0-9]+[.]?[0-9]*|[.][0-9]+)$"

_NUM_FUNCS = {"number", "abs", "floor", "ceil", "round", "length", "count",
              "sum", "avg", "min", "max", "days_between"}


class _InlineCompiler(ship._Compiler):

    # ---- classification --------------------------------------------------------------
    def _is_num(self, node) -> bool:
        """Always a number or null, whatever the record holds."""
        if not isinstance(node, tuple) or not node:
            return False
        tag = node[0]
        if tag in ("num", "neg", "bin"):
            return True
        if tag == "call":
            name, args = node[1], node[2]
            if name in _NUM_FUNCS:
                return True
            if name == "coalesce":
                return all(self._is_num(a) for a in args)
            if name == "if":
                return len(args) != 3 or (self._is_num(args[1]) and self._is_num(args[2]))
        return False

    def _is_cheap(self, node) -> bool:
        """Cheap enough to evaluate up to three times per row in the inline coercion."""
        tag = node[0] if isinstance(node, tuple) and node else None
        if tag in ("field", "num", "str", "bool", "null"):
            return True
        if tag == "call" and node[1] == "coalesce":
            return all(isinstance(a, tuple) and a and a[0] in ("field", "num", "str", "bool", "null")
                       for a in node[2])
        return False

    # ---- the float8 channel ------------------------------------------------------------
    def _f8(self, node) -> str:
        """float8 SQL for an _is_num node.  Mirrors the parent's arity rules exactly."""
        tag = node[0]
        if tag == "num":
            v = float(node[1])
            if v != v or math.isinf(v):
                raise Uncompilable(
                    "numeric literal overflows to inf/nan; jsonb has no representation for it")
            return self._bind(v, "float8")
        if tag == "neg":
            return f"(- {self._num(node[1])})"
        if tag == "bin":
            op, left, right = node[1], node[2], node[3]
            ln, rn = self._num(left), self._num(right)
            if op in ("+", "-", "*"):
                return f"({ln} {op} {rn})"
            if op == "/":
                return f"xpr.div({ln}, {rn})"
            if op == "%":
                return f"xpr.fmod({ln}, {rn})"
            raise Uncompilable(f"unknown arithmetic operator {op!r}")
        name, args = node[1], node[2]
        if name == "number":
            return self._num(args[0]) if args else "NULL::float8"
        if name in ("abs", "floor", "ceil"):
            return f"{name}({self._num(args[0])})" if args else "NULL::float8"
        if name == "round":
            if not args:
                return "NULL::float8"
            x = self._num(args[0])
            nd = self._num(args[1]) if len(args) > 1 else "NULL::float8"
            return f"xpr.round({x}, {nd})"
        if name == "length":
            return f"xpr.length({self._j(args[0])})" if args else "NULL::float8"
        if name == "count":
            if len(args) == 1:
                return f"xpr.count_one({self._j(args[0])})"
            return f"xpr.count_arr({self._build_array(args)})"
        if name in ("sum", "avg", "min", "max"):
            if len(args) == 1:
                return f"xpr.reduce_one({self._bind(name, 'text')}, {self._j(args[0])})"
            return f"xpr.reduce_arr({self._bind(name, 'text')}, {self._build_array(args)})"
        if name == "days_between":
            if len(args) != 2:
                return "NULL::float8"
            a, b = self._j(args[0]), self._j(args[1])
            return f"((xpr.pdate_ms({b}) - xpr.pdate_ms({a})) / {ship.MS_PER_DAY_SQL}::float8)"
        if name == "coalesce":
            if not args:
                return "NULL::float8"
            return "COALESCE(" + ", ".join(self._f8(a) for a in args) + ")"
        if name == "if":
            if len(args) != 3:
                return "NULL::float8"
            return (f"CASE WHEN {self._truthy(args[0])} "
                    f"THEN {self._f8(args[1])} ELSE {self._f8(args[2])} END")
        raise AssertionError(f"_f8 called on a node _is_num does not admit: {node!r}")

    # ---- the coercion every consumer of a number goes through ---------------------------
    def _num(self, node) -> str:
        if self._is_num(node):
            return self._f8(node)
        j = self._j(node)
        if self._is_cheap(node):
            return self._inline_coerce(j)
        return f"xpr.num({j})"

    def _inline_coerce(self, j: str) -> str:
        s = f"({j} #>> '{{}}')"
        return (f"(CASE jsonb_typeof({j}) "
                f"WHEN 'number' THEN (CASE WHEN abs(({j})::numeric) <= {DBL_MAX_LIT}::numeric "
                f"THEN ({j})::float8 ELSE xpr.f8({j}) END) "
                f"WHEN 'string' THEN (CASE WHEN {s} ~ '{_PLAIN_DECIMAL}' AND length({s}) < 300 "
                f"THEN {s}::float8 ELSE xpr.num({j}) END) "
                f"WHEN 'boolean' THEN (CASE WHEN ({j}) = 'true'::jsonb "
                f"THEN 1.0::float8 ELSE 0.0::float8 END) "
                f"ELSE NULL::float8 END)")

    # ---- jsonb results: a channel node is converted ONCE, at the boundary ----------------
    def _j(self, node) -> str:
        if self._is_num(node) and node[0] != "num":
            return f"xpr.j({self._f8(node)})"
        return super()._j(node)        # literals and every non-numeric construct: unchanged

    def _t_cmp(self, node):
        op, left, right = node[1], node[2], node[3]
        if op in ("<", "<=", ">", ">=") and self._is_num(left) and self._is_num(right):
            return f"to_jsonb(({self._f8(left)} {op} {self._f8(right)}))"
        return super()._t_cmp(node)

    # ---- the predicate -----------------------------------------------------------------
    def predicate(self, node) -> str:
        if (isinstance(node, tuple) and node and node[0] == "cmp"
                and node[1] in ("<", "<=", ">", ">=")
                and self._is_num(node[2]) and self._is_num(node[3])):
            return f"COALESCE(({self._f8(node[2])} {node[1]} {self._f8(node[3])}), false)"
        return f"xpr.truthy({self._j(node)})"


def compile_ast(ast: Tuple, *, column: str = "data", ctx_param: str = "ctx") -> Compiled:
    c = _InlineCompiler(column, ctx_param)
    return Compiled(sql=c.compile(ast), params=c.params)


def compile_predicate(ast: Tuple, *, column: str = "data", ctx_param: str = "ctx") -> Compiled:
    """A boolean SQL expression: true exactly where Python's _truthy(evaluate(ast)) is."""
    c = _InlineCompiler(column, ctx_param)
    sql = c.predicate(ast)
    if len(sql) > MAX_SQL_CHARS:
        raise Uncompilable(f"generated SQL is {len(sql)} chars, over the {MAX_SQL_CHARS} cap")
    return Compiled(sql=sql, params=c.params)
