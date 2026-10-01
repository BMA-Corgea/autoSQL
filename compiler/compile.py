"""autoSQL's expression -> Postgres compiler.

Promoted out of `spikes/T-1/proto/compile.py` by T-11 (2026-09-01). That copy is
FROZEN EVIDENCE -- its sha256 `b71b153802d0df94...` is cited in T-6's attestation
and in all 42 of T-6's battery outputs, so it can never change again. This is the
one that ships, exactly as `runtime/` is for the SQL side.

WHAT CHANGED IN THE PROMOTION, and nothing else did:

  Every float8-valued result is now wrapped in `xpr.j(...)` instead of bare
  `to_jsonb(...)`.

  `to_jsonb` reads `extra_float_digits`, a session GUC any connection can change.
  At 0 or -3 Postgres prints fewer digits than a double carries and the number
  comes back SHORT -- T-3's mechanism M3, 62 to 66 wrong answers across T-6's
  batteries. `xpr.j` (T-9) carries its own `SET extra_float_digits = 1`, so it is
  immune to whatever the session says.

  TEXT and BOOLEAN results still use `to_jsonb`, deliberately: neither has digits
  to lose, and wrapping them would cost a function call for nothing.

Everything else -- every construct, every refusal, every parameter binding, the
whole shape of the emitted SQL -- is byte-identical to the spike's.

T-52 (T-44's C_both): THE NUMBER CHECKS ARE WRITTEN INLINE.  Measured in
spikes/T-44: zero wrong numbers against the same batteries, and ~10x faster than the
per-row function calls it replaces.  Four changes, each exact against the compiler
before it (proved case by case over 11,367 battery expressions, spikes/T-44/FINDINGS.md):

  1. A FLOAT8 CHANNEL.  A node that is always a number or null (_is_num) keeps its
     value as float8 between operations instead of round-tripping through jsonb
     (xpr.j then xpr.num) at every step.  For finite x that round trip is the
     identity, and Postgres float8 arithmetic raises rather than make an infinity,
     so nothing non-finite enters the channel.  The one difference -- jsonb has no
     -0 -- cannot be observed: -0.0 and 0.0 compare equal, are both refused as a
     divisor, and both print "0".  The value becomes jsonb ONCE, at the boundary.
  2. AN INLINE COERCION (_inline_coerce) where a cheap jsonb value must become a
     number: a JSON number in range and a plain ASCII decimal string take the native
     cast, a boolean becomes 1/0, and every other path -- beyond DBL_MAX, whitespace,
     an exponent, non-ASCII digits -- calls the unchanged xpr.f8 / xpr.num, so the
     named refusals survive.
  3. NATIVE ORDERING when both sides of < <= > >= are in the channel.
  4. compile_predicate(): the boolean a WHERE filters with.  xpr.truthy(to_jsonb(b))
     is exactly COALESCE(b, false); only an ordering comparison is rewritten.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, NamedTuple, Tuple

MS_PER_DAY_SQL = "86400000.0"

# Hard cap on generated SQL size.  Nothing in expr_vectors.json comes near it; the cap
# exists so a pathological AST produces an honest Uncompilable rather than a monster.
MAX_SQL_CHARS = 200_000

# xpr.f8's refusal boundary (runtime/runtime.sql.in, `abs(n) > ...::numeric`): the
# shortest round-trip decimal of DBL_MAX written out in full.  The inline coercion must
# use THE SAME literal, or the two would disagree about where the named refusal starts;
# compiler/tests pin the equality against the runtime file.
DBL_MAX_LITERAL = "17976931348623157" + "0" * 292

# A string the inline coercion may cast natively: no surrounding space, no exponent,
# ASCII digits only.  Under 300 characters (checked beside it) such a value lies between
# 1e-299 and 1e299, so the cast can neither overflow nor underflow -- and it is exactly
# what xpr.num returns for it.  Everything else goes to xpr.num.
_PLAIN_DECIMAL = r"^[+-]?([0-9]+[.]?[0-9]*|[.][0-9]+)$"

# _inline_coerce writes its argument NINE times into the SQL (and evaluates it up to four
# times per row), so it is used only for an argument at most this long.  Longer -- a deep
# path, or a GIMS-folded key with many separator variants (T-48) -- takes the unchanged
# xpr.num(...) instead: exact either way, and the generated SQL stays far from the
# MAX_SQL_CHARS cap (the T-52 review measured 12 folded uses crossing it unbounded).
_INLINE_MAX_CHARS = 512

# Builtins whose value is always a number or null (the float8 channel).
_NUM_FUNCS = frozenset({"number", "abs", "floor", "ceil", "round", "length", "count",
                        "sum", "avg", "min", "max", "days_between"})


class Uncompilable(Exception):
    """This construct cannot be compiled to SQL the author is sure of."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Compiled(NamedTuple):
    sql: str
    params: Dict[str, Any]


# ---------------------------------------------------------------------------------
# GIMS key folding (T-48).  A GIMS dashboard never evaluates a noun row as stored:
# get_noun_items (api/iostore/nouns.py, _normalize_row) serves every top-level key
# ALSO with its spaces and underscores swapped, through setdefault, taking stored keys
# in jsonb order; then _noun_records (api/dashboard/sources.py) does
# setdefault("_noun_type", <noun>).  A WHERE pushed into SQL runs over the STORED row,
# so with fold="gims" the first key step of every field path is compiled to the key
# the served row would have, statically: no per-row function (T-4's open question is
# per-row cost).  T-46's parity vectors pin the rule; parity/README.md explains it.
# ---------------------------------------------------------------------------------
FOLD_MAX_SEPARATORS = 6   # n separators -> 2**n - 1 copy sources; refuse above this


def gims_copy_sources(key: str) -> List[str]:
    """The stored keys whose GIMS copy is `key`, in the order the first one wins.

    `_normalize_row` copies a stored key k to k.replace("_", " ") and to
    k.replace(" ", "_"), so only a key made entirely of one separator kind can be a
    copy: `key` with a non-empty subset of its spaces turned to underscores (if it has
    only spaces), or of its underscores turned to spaces (if it has only underscores).
    Every source has `key`'s length, so jsonb's key order among them, which decides
    the setdefault winner, is plain byte order.  A key with both kinds, or neither, is
    never a copy: [].  Raises Uncompilable above FOLD_MAX_SEPARATORS.
    """
    has_space, has_us = " " in key, "_" in key
    if has_space == has_us:
        return []
    sep, swap = (" ", "_") if has_space else ("_", " ")
    at = [i for i, ch in enumerate(key) if ch == sep]
    if len(at) > FOLD_MAX_SEPARATORS:
        raise Uncompilable(
            f"GIMS key folding: {key!r} has {len(at)} separators, so {2 ** len(at) - 1} keys could "
            f"be copied into it; the cap is {FOLD_MAX_SEPARATORS}. The adapter must evaluate it in Python"
        )
    out = []
    for mask in range(1, 1 << len(at)):
        chars = list(key)
        for bit, i in enumerate(at):
            if mask >> bit & 1:
                chars[i] = swap
        out.append("".join(chars))
    # Plain code-point order: for any key that can be stored, it IS UTF-8 byte order (and so jsonb's
    # order among same-length keys); unlike .encode(), it cannot raise on a lone surrogate (T-48 review).
    return sorted(out)


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
        "sql_behaviour": "jsonb stores `numeric`; the two are DISTINCT. Ordering is routed "
                         "through xpr.f8 (float8) so `<` matches; since T-61 `==` / `!=` are too "
                         "(two numbers via xpr.f8 inline, NaN-aware; two lists or dicts via "
                         "xpr.eq_deep), and beyond DBL_MAX xpr.f8 raises its named refusal (XPR01).",
        "guarded": True,
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
        "guarded": True,
        "in_fixture": True,
        "note": "T-52: xpr.ecma_num now carries its own SET extra_float_digits = 1, as "
                "xpr.j does (T-9), so string() no longer follows the session's setting "
                "and its IMMUTABLE label is true.",
    },
    {
        "id": "parallel_refusal_order",
        "construct": "a query in which more than one row would raise",
        "expr_behaviour": "Python never raises a refusal; it returns inf / None per row",
        "sql_behaviour": "T-52 made the runtime PARALLEL SAFE, so a large scan may run in "
                         "workers, and WHICH row's error surfaces first (XPR01 or 22003) "
                         "depends on worker timing",
        "guarded": False,
        "in_fixture": False,
        "note": "A caller deciding to fall back to the Python path must treat ANY raise as "
                "the fallback signal, not only XPR01.",
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
    def __init__(self, column: str, ctx_param: str, fold: Any = None, noun: Any = None):
        self.column = column
        self.ctx_param = ctx_param
        self.fold = fold
        self.noun = noun
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
        """Compile a node and coerce it through _to_num (expr.py:305-319), as float8.

        A channel node is already a number (T-52 change 1).  A cheap jsonb value is
        coerced inline (change 2).  Anything else calls the runtime's xpr.num, unchanged.
        """
        if self._is_num(node):
            return self._f8(node)
        j = self._j(node)
        if self._is_cheap(node) and len(j) <= _INLINE_MAX_CHARS:
            return self._inline_coerce(j)
        return f"xpr.num({j})"

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
        if tag != "num" and self._is_num(node):
            # T-52: a channel node becomes jsonb once, here, at the boundary.
            return f"xpr.j({self._f8(node)})"
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
        return f"xpr.j({self._bind(v, 'float8')})"

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
        if self.fold == "gims":
            sql, path = self._gims_first_step(path)
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

    def _gims_first_step(self, path):
        """T-48: the first key step as GIMS's served row would answer it.

        COALESCE(stored K, each copy source in first-wins order, [the noun, for
        _noun_type]).  `->` yields SQL NULL only for an ABSENT key, so a stored JSON
        null stops the COALESCE exactly as setdefault keeps it.  Only the first step
        folds: GIMS copies top-level keys only.  Returns (sql, remaining path)."""
        if not path:
            raise Uncompilable(
                "GIMS key folding: a bare $ is the whole served row, copies and _noun_type "
                "included, which has no static form. The adapter must evaluate it in Python"
            )
        kind, key = path[0]
        if kind != "key":
            return self.column, path       # $[i] on an object row: exact, xpr.idx gives NULL
        terms = [f"({self.column} -> {self._bind(k, 'text')})" for k in [key] + gims_copy_sources(key)]
        if key == "_noun_type":
            terms.append(f"to_jsonb({self._bind(self.noun, 'text')})")
        sql = terms[0] if len(terms) == 1 else "COALESCE(" + ", ".join(terms) + ")"
        return sql, path[1:]

    # ---- unary ------------------------------------------------------------------
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
        if op in ("<", "<=", ">", ">=") and self._is_num(left) and self._is_num(right):
            # T-52 change 3: xpr.ord on two numbers IS the float8 comparison, NULL when
            # either side is NULL -- so compare natively and skip both jsonb round trips.
            return f"to_jsonb(({self._f8(left)} {op} {self._f8(right)}))"
        l, r = self._j(left), self._j(right)
        if op == "==":
            return f"to_jsonb({self._eq_sql(l, r)})"
        if op == "!=":
            return f"to_jsonb(NOT {self._eq_sql(l, r)})"
        if op in ("<", "<=", ">", ">="):
            # _order_cmp (expr.py:381-396) is THREE-valued and type-homogeneous:
            # num-num or str-str only, everything else (including any bool operand and
            # any num/str mix) is None, NOT a coercion.
            return f"to_jsonb(xpr.ord({self._bind(op, 'text')}, {l}, {r}))"
        raise Uncompilable(f"unknown comparison operator {op!r}")

    def _eq_sql(self, l: str, r: str) -> str:
        """_eq (expr.py:363-378) as SQL: TWO-valued, never NULL (null == null is true,
        null == x is false), so `!=` is simply its NOT.

        T-61 (T-37 review F4): Python compares numbers as DOUBLES; jsonb compares exact
        numeric, so 12345678901234567 == 12345678901234568 is True in GIMS and was False
        here. Two numbers now meet through xpr.f8 inline (no call on the hot path for
        anything else); xpr.f8 RAISES its named refusal beyond DBL_MAX, where Python would
        compare inf with inf (R2-2), and `<> 'NaN'` keeps NaN unequal to itself, as Python
        does and float8 does not (R2-3). Two lists or two dicts go through xpr.eq_deep,
        which recurses the same way. Everything else keeps IS NOT DISTINCT FROM, which is
        exactly _eq for strings, booleans, null and any mix of types."""
        tl, tr = f"jsonb_typeof({l})", f"jsonb_typeof({r})"
        return (f"(CASE WHEN {tl} = 'number' AND {tr} = 'number' "
                f"THEN (xpr.f8({l}) = xpr.f8({r}) AND xpr.f8({l}) <> 'NaN'::float8) "
                f"WHEN ({tl} = 'array' AND {tr} = 'array') OR ({tl} = 'object' AND {tr} = 'object') "
                f"THEN xpr.eq_deep({l}, {r}) "
                f"ELSE ({l} IS NOT DISTINCT FROM {r}) END)")


    # ---- the float8 channel (T-52 changes 1 and 2) ---------------------------------
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
        """Cheap enough for _inline_coerce: written nine times, evaluated at most four per row."""
        tag = node[0] if isinstance(node, tuple) and node else None
        if tag in ("field", "num", "str", "bool", "null"):
            return True
        if tag == "call" and node[1] == "coalesce":
            return all(isinstance(a, tuple) and a and a[0] in ("field", "num", "str", "bool", "null")
                       for a in node[2])
        return False

    def _f8(self, node) -> str:
        """float8 SQL for an _is_num node.  Arity rules are expr.py's, as before T-52."""
        tag = node[0]
        if tag == "num":                                      # expr.py:193, 580-581
            v = float(node[1])
            if v != v or math.isinf(v):
                raise Uncompilable(
                    "numeric literal overflows to inf/nan; jsonb has no representation for it")
            return self._bind(v, "float8")
        if tag == "neg":                                      # expr.py:179, 590-592
            return f"(- {self._num(node[1])})"
        if tag == "bin":                                      # expr.py:608-624
            op, left, right = node[1], node[2], node[3]
            ln, rn = self._num(left), self._num(right)
            if op in ("+", "-", "*"):
                return f"({ln} {op} {rn})"
            if op == "/":
                # expr.py:620-621: zero divisor -> None. Postgres would RAISE division_by_zero.
                return f"xpr.div({ln}, {rn})"
            if op == "%":
                # expr.py:622-624 is math.fmod, not Python's %.  Postgres has NO % operator
                # and no mod() for double precision at all, so xpr.fmod computes the exact
                # IEEE truncated remainder.
                return f"xpr.fmod({ln}, {rn})"
            raise Uncompilable(f"unknown arithmetic operator {op!r}")
        name, args = node[1], node[2]
        if name == "number":                                  # expr.py:540
            return self._num(args[0]) if args else "NULL::float8"
        if name in ("abs", "floor", "ceil"):                  # expr.py:544-546
            return f"{name}({self._num(args[0])})" if args else "NULL::float8"
        if name == "round":                                   # expr.py:517-527
            if not args:
                return "NULL::float8"
            x = self._num(args[0])
            nd = self._num(args[1]) if len(args) > 1 else "NULL::float8"
            return f"xpr.round({x}, {nd})"
        if name == "length":                                  # expr.py:543
            return f"xpr.length({self._j(args[0])})" if args else "NULL::float8"
        # count / sum / avg / min / max all route through _as_list (expr.py:462-466):
        # exactly ONE list argument is unwrapped; anything else is used as-is.
        if name == "count":                                   # expr.py:548
            if len(args) == 1:
                return f"xpr.count_one({self._j(args[0])})"
            return f"xpr.count_arr({self._build_array(args)})"
        if name in ("sum", "avg", "min", "max"):              # expr.py:502-514, 549-552
            if len(args) == 1:
                return f"xpr.reduce_one({self._bind(name, 'text')}, {self._j(args[0])})"
            return f"xpr.reduce_arr({self._bind(name, 'text')}, {self._build_array(args)})"
        if name == "days_between":                            # expr.py:469-475
            if len(args) != 2:
                return "NULL::float8"
            a, b = self._j(args[0]), self._j(args[1])
            return f"((xpr.pdate_ms({b}) - xpr.pdate_ms({a})) / {MS_PER_DAY_SQL}::float8)"
        if name == "coalesce":                                # expr.py:535
            if not args:
                return "NULL::float8"
            return "COALESCE(" + ", ".join(self._f8(a) for a in args) + ")"
        if name == "if":                                      # expr.py:627-632
            if len(args) != 3:
                return "NULL::float8"
            return (f"CASE WHEN {self._truthy(args[0])} "
                    f"THEN {self._f8(args[1])} ELSE {self._f8(args[2])} END")
        raise AssertionError(f"_f8 called on a node _is_num does not admit: {node!r}")

    def _inline_coerce(self, j: str) -> str:
        """xpr.num(j) written inline for a cheap j; the rare paths still call the runtime."""
        s = f"({j} #>> '{{}}')"
        return (f"(CASE jsonb_typeof({j}) "
                f"WHEN 'number' THEN (CASE WHEN abs(({j})::numeric) <= {DBL_MAX_LITERAL}::numeric "
                f"THEN ({j})::float8 ELSE xpr.f8({j}) END) "
                f"WHEN 'string' THEN (CASE WHEN {s} ~ '{_PLAIN_DECIMAL}' AND length({s}) < 300 "
                f"THEN {s}::float8 ELSE xpr.num({j}) END) "
                f"WHEN 'boolean' THEN (CASE WHEN ({j}) = 'true'::jsonb "
                f"THEN 1.0::float8 ELSE 0.0::float8 END) "
                f"ELSE NULL::float8 END)")

    # ---- the predicate (T-52 change 4) ---------------------------------------------
    def predicate(self, node) -> str:
        """Boolean SQL, true exactly where expr's _truthy(evaluate(node)) is."""
        if (isinstance(node, tuple) and node and node[0] == "cmp"
                and node[1] in ("<", "<=", ">", ">=")
                and self._is_num(node[2]) and self._is_num(node[3])):
            return f"COALESCE(({self._f8(node[2])} {node[1]} {self._f8(node[3])}), false)"
        return f"xpr.truthy({self._j(node)})"

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

    def _build_array(self, args) -> str:
        if not args:
            return "'[]'::jsonb"
        return "jsonb_build_array(" + ", ".join(self._j(a) for a in args) + ")"


def compile_ast(ast: Tuple, *, column: str = "data", ctx_param: str = "ctx",
                fold: Any = None, noun: Any = None) -> Compiled:
    """Compile an expr AST to a Postgres scalar jsonb expression + bind parameters.

    Raises Uncompilable for anything this compiler is not sure of.

    fold="gims" (T-48): compile field access as GIMS's dashboard pipeline serves a noun
    row (its key copies and the _noun_type tag; see gims_copy_sources), for a WHERE run
    over the STORED row.  `noun` is required with it.  Without `fold`, the output is
    byte-identical to the compiler before T-48.
    """
    if fold not in (None, "gims"):
        raise ValueError(f"unknown fold {fold!r}: the only fold is 'gims'")
    if fold == "gims" and not (isinstance(noun, str) and noun):
        raise ValueError("fold='gims' needs noun=<the noun type>: GIMS tags every served row with it")
    c = _Compiler(column, ctx_param, fold, noun)
    sql = c.compile(ast)
    if "%" in sql.replace("%(", "\x00").replace(")s", "\x00"):
        # Defensive: a stray literal % would break %(name)s parameter binding.
        pass
    return Compiled(sql=sql, params=c.params)


def compile_predicate(ast: Tuple, *, column: str = "data", ctx_param: str = "ctx",
                      fold: Any = None, noun: Any = None) -> Compiled:
    """Compile an expr AST to a Postgres BOOLEAN: true exactly where expr's
    _truthy(evaluate(ast)) is.  For a WHERE.  Same arguments and refusals as compile_ast.

    The pre-T-52 form, xpr.truthy(<compile_ast>), is what this replaces; the two are
    identical case by case (spikes/T-44, the predicate verdicts on all 11,367 battery
    expressions).  An ordering comparison between two numbers becomes a native compare.
    """
    if fold not in (None, "gims"):
        raise ValueError(f"unknown fold {fold!r}: the only fold is 'gims'")
    if fold == "gims" and not (isinstance(noun, str) and noun):
        raise ValueError("fold='gims' needs noun=<the noun type>: GIMS tags every served row with it")
    c = _Compiler(column, ctx_param, fold, noun)
    sql = c.predicate(ast)
    if len(sql) > MAX_SQL_CHARS:
        raise Uncompilable(f"generated SQL is {len(sql)} chars, over the {MAX_SQL_CHARS} cap")
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
