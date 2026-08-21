"""T-1 spike · THROWAWAY AST -> Postgres SQL compiler for the GIMS dashboard
expression language.

THIS IS NOT A LIBRARY.  Per spikes/T-1/FRAMING.md section 3 the prototype is throwaway
by contract; nothing may import it later.

Input  : the AST produced by the REAL parser, `core.dashboard.expr.parse()`
         (GIMS-Project@995cc59 core/dashboard/expr.py:264, byte-identical in
         gims-ledger@7b7a049 per FRAMING.md section 2).  Parsing is NEVER
         reimplemented here.
Output : `Compiled(sql, params)` where `sql` is a single Postgres scalar expression of
         type `jsonb` over a JSONB column (default name `data`), and `params` is the
         dict of named bind parameters it references (`%(name)s` placeholders).

REPRESENTATION CONTRACT
-----------------------
Every compiled subexpression has SQL type `jsonb`.  expr's Python `None` is carried as
SQL NULL, never as jsonb `'null'`.  This is faithful because `_resolve_field`
(expr.py:562-575) cannot distinguish an absent key from a JSON null -- both become
Python `None` -- so collapsing them is not a loss.  Nested JSON nulls *inside* an array
or object stay as jsonb `'null'`, which is also faithful (Python keeps them as `None`
inside the list/dict).

TOTALITY
--------
expr never raises for data reasons (expr.py:17-19).  Postgres does.  Every place the two
disagree is guarded here:
  * `/`  and `%` by zero        -> xpr.div / xpr.fmod return NULL  (expr.py:620-624)
  * bad numeric cast of a string-> xpr.num regex-gates before casting (expr.py:302-319)
  * unparseable / calendar-invalid date -> xpr.pdate_ms returns NULL (expr.py:409-431)
  * out-of-range date output    -> xpr.fmt_date_ms returns NULL      (expr.py:434-445)
  * index into a non-array      -> xpr.idx type-guards; Postgres alone would return the
                                   scalar itself ('5'::jsonb -> 0  ==  5)

Anything this compiler is NOT sure of raises `Uncompilable`.  Per FRAMING.md section 5,
an honest `Uncompilable` is a good outcome; a wrong number is disqualifying.

KNOWN_DIVERGENCES below lists every divergence this author identified but did NOT fix,
with whether the fixture exercises it.  It is emitted into results.json so the finding
cannot be lost.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, NamedTuple, Tuple

MS_PER_DAY_SQL = "86400000.0"

# Hard cap on generated SQL size.  Nothing in expr_vectors.json comes near it; the cap
# exists so a pathological AST produces an honest Uncompilable rather than a monster.
MAX_SQL_CHARS = 200_000


class Uncompilable(Exception):
    """This construct cannot be compiled to SQL the author is sure of."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Compiled(NamedTuple):
    sql: str
    params: Dict[str, Any]


# ---------------------------------------------------------------------------------
# Divergences identified but deliberately NOT fixed.  Each is either outside the
# fixture's coverage or a documented cost of the chosen representation.
# ---------------------------------------------------------------------------------
KNOWN_DIVERGENCES = [
    {
        "id": "float8_overflow_raises",
        "construct": "+ - * /  on float8",
        "expr_behaviour": "Python returns +-inf (expr.py:614-621 has no overflow guard)",
        "sql_behaviour": "Postgres RAISES 'value out of range: overflow' "
                         "(verified: select 1e308::float8 * 10::float8)",
        "guarded": False,
        "in_fixture": False,
        "note": "A real, unguarded totality violation. Arithmetic that overflows a "
                "double aborts the query instead of yielding a value.",
    },
    {
        "id": "num_out_of_float8_range",
        "construct": "xpr.num / xpr.f8 on a JSON number or numeric string beyond DBL_MAX",
        "expr_behaviour": "Python float('1e999') == inf, _to_num returns inf",
        "sql_behaviour": "guarded to NULL (a bare cast would RAISE: "
                         "select '1e999'::float8 -> out of range)",
        "guarded": True,
        "in_fixture": False,
        "note": "Chosen deliberately: NULL rather than an aborted query. Still a "
                "divergence (NULL vs inf) and it is reported here rather than hidden.",
    },
    {
        "id": "numeric_literal_inf",
        "construct": "a numeric literal that overflows, e.g. 1e400",
        "expr_behaviour": "parse() builds ('num', inf) (expr.py:193, float() on the token)",
        "sql_behaviour": "compiler raises Uncompilable; jsonb cannot hold inf "
                         "(to_jsonb('Infinity'::float8) yields the STRING \"Infinity\")",
        "guarded": True,
        "in_fixture": False,
    },
    {
        "id": "jsonb_numeric_is_not_ieee_double",
        "construct": "== / != / < <= > >= over JSON numbers with >17 significant digits",
        "expr_behaviour": "Python parses JSON numbers to IEEE doubles first, so "
                          "1.0000000000000001 and 1.0000000000000002 are EQUAL",
        "sql_behaviour": "jsonb stores `numeric`; the two are DISTINCT. "
                         "Ordering is routed through xpr.f8 (float8) so `<` matches, but "
                         "`==` uses jsonb IS NOT DISTINCT FROM and would not.",
        "guarded": False,
        "in_fixture": False,
    },
    {
        "id": "unicode_case_and_collation",
        "construct": "lower() / upper() / string ordering on non-ASCII text",
        "expr_behaviour": "Python str.lower()/upper() and codepoint ordering",
        "sql_behaviour": "Postgres lower()/upper() follow the database collation; "
                         "ordering is pinned to COLLATE \"C\" here, case mapping is not",
        "guarded": False,
        "in_fixture": False,
    },
    {
        "id": "extra_float_digits_guc",
        "construct": "string() / concat() of a number (xpr.ecma_num)",
        "expr_behaviour": "_num_to_str uses repr() == shortest round-trip (expr.py:334)",
        "sql_behaviour": "xpr.ecma_num reads float8's text output, which is the shortest "
                         "round-trip only while extra_float_digits >= 0 (PG12+ default 1)",
        "guarded": False,
        "in_fixture": True,
        "note": "The functions are declared IMMUTABLE despite depending on a GUC. "
                "A production deployment would have to pin it.",
    },
    {
        "id": "wall_clock_granularity",
        "construct": "today() / now() with no context clock",
        "expr_behaviour": "datetime.now(utc) evaluated once per evaluate() call, i.e. "
                          "once per record (expr.py:456)",
        "sql_behaviour": "xpr.now_ms falls back to now() == transaction timestamp, i.e. "
                         "once per query",
        "guarded": False,
        "in_fixture": False,
        "note": "Every fixture case that uses the clock injects context.now, so this "
                "path is NOT exercised by the conformance run.",
    },
]


# ---------------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------------
class _Compiler:
    def __init__(self, column: str, ctx_param: str):
        self.column = column
        self.ctx_param = ctx_param
        self.params: Dict[str, Any] = {}
        self._n = 0

    # -- bind parameters ----------------------------------------------------------
    def _bind(self, value: Any, cast: str) -> str:
        name = f"p{self._n}"
        self._n += 1
        self.params[name] = value
        return f"(%({name})s)::{cast}"

    def _ctx(self) -> str:
        return f"(%({self.ctx_param})s)::jsonb"

    # -- entry --------------------------------------------------------------------
    def compile(self, node: Tuple) -> str:
        sql = self._j(node)
        if len(sql) > MAX_SQL_CHARS:
            raise Uncompilable(
                f"generated SQL is {len(sql)} chars, over the {MAX_SQL_CHARS} cap"
            )
        return sql

    # -- helpers ------------------------------------------------------------------
    def _num(self, node: Tuple) -> str:
        """Compile a node and coerce it through _to_num (expr.py:305-319)."""
        return f"xpr.num({self._j(node)})"

    def _truthy(self, node: Tuple) -> str:
        """Compile a node and coerce it through _truthy (expr.py:282-293)."""
        return f"xpr.truthy({self._j(node)})"

    def _str(self, node: Tuple) -> str:
        """Compile a node and coerce it through _to_str (expr.py:351-360)."""
        return f"xpr.str({self._j(node)})"

    # -- the jsonb-valued dispatch ------------------------------------------------
    def _j(self, node: Tuple) -> str:
        if not isinstance(node, tuple) or not node:
            raise Uncompilable(f"not an AST node: {node!r}")
        tag = node[0]
        fn = getattr(self, f"_t_{tag}", None)
        if fn is None:
            # expr.py:636 says parse() guarantees the tag universe; anything else is a
            # construct this compiler has never seen and must not guess at.
            raise Uncompilable(f"unknown AST tag {tag!r}")
        return fn(node)

    # ---- literals ---------------------------------------------------------------
    def _t_num(self, node):                                   # expr.py:193, 580-581
        v = float(node[1])
        if v != v or math.isinf(v):
            raise Uncompilable(
                "numeric literal overflows to inf/nan; jsonb has no representation for it"
            )
        return f"to_jsonb({self._bind(v, 'float8')})"

    def _t_str(self, node):                                   # expr.py:196, 582-583
        return f"to_jsonb({self._bind(node[1], 'text')})"

    def _t_bool(self, node):                                  # expr.py:199, 584-585
        return "'true'::jsonb" if node[1] else "'false'::jsonb"

    def _t_null(self, node):                                  # expr.py:202, 586-587
        return "NULL::jsonb"

    # ---- field access -----------------------------------------------------------
    def _t_field(self, node):                                 # expr.py:247, 588-589
        path: List[Tuple[str, Any]] = node[1]
        sql = self.column
        for kind, key in path:
            if kind == "key":
                # Postgres `-> text` already returns NULL for every non-object jsonb
                # type (verified: '5'::jsonb->'a', '"abc"'::jsonb->'a', '[1,2]'::jsonb->'0',
                # 'null'::jsonb->'a' are all SQL NULL), matching _resolve_field:566-569.
                sql = f"({sql} -> {self._bind(key, 'text')})"
            elif kind == "index":
                # Postgres `-> int` does NOT match: it treats a jsonb SCALAR as a
                # one-element array ('5'::jsonb -> 0 == 5, -> -1 == 5), where
                # _resolve_field:570-574 requires an actual list.  xpr.idx type-guards it.
                sql = f"xpr.idx({sql}, {self._bind(int(key), 'int')})"
            else:
                raise Uncompilable(f"unknown field path step {kind!r}")
        # Collapse a resolved JSON null to SQL NULL: expr cannot tell it apart from
        # an absent key, so neither must we.
        return f"nullif({sql}, 'null'::jsonb)"

    # ---- unary ------------------------------------------------------------------
    def _t_neg(self, node):                                   # expr.py:179, 590-592
        return f"to_jsonb(- {self._num(node[1])})"

    def _t_not(self, node):                                   # expr.py:151, 593-594
        return f"to_jsonb(NOT {self._truthy(node[1])})"

    # ---- boolean ----------------------------------------------------------------
    # expr.py:595-598: `and`/`or` return a concrete bool, never null, and both sides go
    # through _truthy.  They are NOT value-preserving like Python's own and/or.
    def _t_and(self, node):
        return f"to_jsonb({self._truthy(node[1])} AND {self._truthy(node[2])})"

    def _t_or(self, node):
        return f"to_jsonb({self._truthy(node[1])} OR {self._truthy(node[2])})"

    # ---- comparison -------------------------------------------------------------
    def _t_cmp(self, node):                                   # expr.py:599-607
        op, left, right = node[1], node[2], node[3]
        l, r = self._j(left), self._j(right)
        if op == "==":
            # _eq (expr.py:363-378) is TWO-valued: null == null is true, null == x is
            # false.  IS NOT DISTINCT FROM is exactly that.  A bare `=` would be
            # three-valued and silently wrong.
            return f"to_jsonb({l} IS NOT DISTINCT FROM {r})"
        if op == "!=":
            return f"to_jsonb({l} IS DISTINCT FROM {r})"
        if op in ("<", "<=", ">", ">="):
            # _order_cmp (expr.py:381-396) is THREE-valued and type-homogeneous:
            # num-num or str-str only, everything else (including any bool operand and
            # any num/str mix) is None, NOT a coercion.
            return f"to_jsonb(xpr.ord({self._bind(op, 'text')}, {l}, {r}))"
        raise Uncompilable(f"unknown comparison operator {op!r}")

    # ---- arithmetic -------------------------------------------------------------
    def _t_bin(self, node):                                   # expr.py:608-624
        op, left, right = node[1], node[2], node[3]
        ln, rn = self._num(left), self._num(right)
        if op == "+":
            return f"to_jsonb({ln} + {rn})"
        if op == "-":
            return f"to_jsonb({ln} - {rn})"
        if op == "*":
            return f"to_jsonb({ln} * {rn})"
        if op == "/":
            # expr.py:620-621: zero divisor -> None. Postgres would RAISE division_by_zero.
            return f"to_jsonb(xpr.div({ln}, {rn}))"
        if op == "%":
            # expr.py:622-624 is math.fmod, not Python's %.  Postgres has NO % operator
            # and no mod() for double precision at all, so xpr.fmod computes the exact
            # IEEE truncated remainder.
            return f"to_jsonb(xpr.fmod({ln}, {rn}))"
        raise Uncompilable(f"unknown arithmetic operator {op!r}")

    # ---- calls ------------------------------------------------------------------
    def _t_call(self, node):                                  # expr.py:625-635
        name, args = node[1], node[2]
        fn = getattr(self, f"_f_{name}", None)
        if fn is None:
            raise Uncompilable(f"builtin {name!r} has no SQL compilation")
        return fn(args)

    # zero-arg clock builtins (expr.py:531-532); args are ignored by expr itself
    def _f_today(self, args):
        return f"to_jsonb(xpr.fmt_date_ms(xpr.now_ms({self._ctx()}), true))"

    def _f_now(self, args):
        return f"to_jsonb(xpr.fmt_date_ms(xpr.now_ms({self._ctx()}), false))"

    def _f_days_between(self, args):                          # expr.py:469-475
        if len(args) != 2:
            return "NULL::jsonb"                              # expr.py:470-471
        a, b = self._j(args[0]), self._j(args[1])
        return (f"to_jsonb((xpr.pdate_ms({b}) - xpr.pdate_ms({a})) "
                f"/ {MS_PER_DAY_SQL}::float8)")

    def _f_date_add(self, args):                              # expr.py:478-485
        if len(args) != 2:
            return "NULL::jsonb"
        base, n = self._j(args[0]), self._num(args[1])
        # The date_only flag comes from the INPUT (expr.py:485, base[1]) and cannot be
        # recovered from the timestamp, so it is parsed a second time.
        return (f"to_jsonb(xpr.fmt_date_ms("
                f"xpr.pdate_ms({base}) + ({n}) * {MS_PER_DAY_SQL}::float8, "
                f"xpr.pdate_only({base})))")

    def _f_coalesce(self, args):                              # expr.py:535
        if not args:
            return "NULL::jsonb"
        return "COALESCE(" + ", ".join(self._j(a) for a in args) + ")"

    def _f_if(self, args):                                    # expr.py:627-632
        if len(args) != 3:
            return "NULL::jsonb"                              # expr.py:629-630
        # MUST be a genuinely lazy CASE: expr evaluates only the taken branch, and SQL is
        # not total, so an eager form could raise on the untaken branch.
        return (f"CASE WHEN {self._truthy(args[0])} "
                f"THEN {self._j(args[1])} ELSE {self._j(args[2])} END")

    def _f_lower(self, args):                                 # expr.py:537
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(lower({self._str(args[0])}))"

    def _f_upper(self, args):                                 # expr.py:538
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(upper({self._str(args[0])}))"

    def _f_contains(self, args):                              # expr.py:488-499
        if len(args) != 2:
            return "NULL::jsonb"
        return f"to_jsonb(xpr.contains({self._j(args[0])}, {self._j(args[1])}))"

    def _f_number(self, args):                                # expr.py:540
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb({self._num(args[0])})"

    def _f_string(self, args):                                # expr.py:541
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb({self._str(args[0])})"

    def _f_concat(self, args):                                # expr.py:542
        # The one function where a null argument becomes '' instead of nulling the whole
        # result: "".join(_to_str(a) or "" for a in args).
        if not args:
            return "to_jsonb(''::text)"
        parts = " || ".join(f"coalesce({self._str(a)}, '')" for a in args)
        return f"to_jsonb({parts})"

    def _f_length(self, args):                                # expr.py:543
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(xpr.length({self._j(args[0])}))"

    def _f_abs(self, args):                                   # expr.py:544
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(abs({self._num(args[0])}))"

    def _f_floor(self, args):                                 # expr.py:545
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(floor({self._num(args[0])}))"

    def _f_ceil(self, args):                                  # expr.py:546
        if not args:
            return "NULL::jsonb"
        return f"to_jsonb(ceil({self._num(args[0])}))"

    def _f_round(self, args):                                 # expr.py:517-527
        if not args:
            return "NULL::jsonb"
        nd = self._num(args[1]) if len(args) > 1 else "NULL::float8"
        return f"to_jsonb(xpr.round({self._num(args[0])}, {nd}))"

    # count / sum / avg / min / max all route through _as_list (expr.py:462-466):
    # exactly ONE list argument is unwrapped; anything else is used as-is.
    def _f_count(self, args):                                 # expr.py:548
        if len(args) == 1:
            return f"to_jsonb(xpr.count_one({self._j(args[0])}))"
        return f"to_jsonb(xpr.count_arr({self._build_array(args)}))"

    def _reduce(self, op: str, args):                         # expr.py:502-514, 549-552
        if len(args) == 1:
            return (f"to_jsonb(xpr.reduce_one({self._bind(op, 'text')}, "
                    f"{self._j(args[0])}))")
        return (f"to_jsonb(xpr.reduce_arr({self._bind(op, 'text')}, "
                f"{self._build_array(args)}))")

    def _f_sum(self, args):
        return self._reduce("sum", args)

    def _f_avg(self, args):
        return self._reduce("avg", args)

    def _f_min(self, args):
        return self._reduce("min", args)

    def _f_max(self, args):
        return self._reduce("max", args)

    def _build_array(self, args) -> str:
        if not args:
            return "'[]'::jsonb"
        return "jsonb_build_array(" + ", ".join(self._j(a) for a in args) + ")"


def compile_ast(ast: Tuple, *, column: str = "data", ctx_param: str = "ctx") -> Compiled:
    """Compile an expr AST to a Postgres scalar jsonb expression + bind parameters.

    Raises Uncompilable for anything this compiler is not sure of.
    """
    c = _Compiler(column, ctx_param)
    sql = c.compile(ast)
    if "%" in sql.replace("%(", "\x00").replace(")s", "\x00"):
        # Defensive: a stray literal % would break %(name)s parameter binding.
        pass
    return Compiled(sql=sql, params=c.params)


# ---------------------------------------------------------------------------------
# Display-only helper.  Substitutes bind parameters into the SQL so a human (and the
# index-shape finding) can read the real generated predicate.  NEVER execute this --
# the harness always executes the parameterised form.
# ---------------------------------------------------------------------------------
def render_for_display(sql: str, params: Dict[str, Any], ctx_param: str = "ctx",
                       ctx_value: str = "'{}'") -> str:
    out = sql
    for name, value in sorted(params.items(), key=lambda kv: -len(kv[0])):
        if isinstance(value, str):
            lit = "'" + value.replace("'", "''") + "'"
        elif isinstance(value, bool):
            lit = "true" if value else "false"
        elif isinstance(value, float):
            lit = repr(value)
        else:
            lit = str(value)
        out = out.replace(f"%({name})s", lit)
    out = out.replace(f"%({ctx_param})s", ctx_value)
    return out
