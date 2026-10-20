"""demo/probes.py — LAYER 2, the runtime refusal (spec §4.5, plan §4.3).

The static gate (layer 1, demo/gate.py) answers every question that can be
answered from the expression alone.  Two questions cannot be — they are
properties of the ROWS, not of the AST — and they are this file's:

  member (a)  does any value this pick reads, at a place where it will be
              coerced through the guarded numeric read, have magnitude
              >= 1.7976931348623157e+308 (the real float8 limit, whose exact
              decimal expansion is 309 digits)?  Postgres's float8 genuinely
              cannot represent such a value.  The demo asks FIRST and
              refuses loudly, one question ahead of the statement — with a
              structured refusal that names the first offending ROW, which
              the runtime's own error cannot.  (Until 2026-08-23 there was a
              second reason: the pre-fix runtime answered NULL past its
              guard — the silent form FRAMING.md §5 forbids.  The adopted
              runtime — q4/GA-7 — instead RAISES a named XPR01 refusal at
              the same limit, so the probe is now the row-naming front door
              to a runtime that fails loudly behind it either way.)

  member (b)  does any row make an == / != operand resolve to an object or an
              array?  Container equality is outside the pinned subset at the
              row level (spec §4.6, reading A): the gate allows == by
              construct, and this layer refuses the specific picks where the
              data actually produces a container.

When either fires, the whole pick is abandoned — per-widget, not per-row —
and this module raises RuntimeRefusal, a NAMED, catchable error.  The caller
(demo/server, W13) reports that as the labelled fallback to the Python pane:
a reported refusal is not a wrong answer; a number would have been.

THE ONE WAY TO GET MEMBER (a) WRONG (spec §4.5, plan §4.3) — the probe reads
the RAW jsonb and casts through `numeric`, which holds 1e400 exactly.  It must
NEVER be routed through xpr.f8 or xpr.num.  Under the adopted runtime
(2026-08-23, q4/GA-7) those RAISE the named XPR01 refusal for exactly the
values the probe exists to pre-empt — so a probe built on them would die
mid-question instead of answering true, and the person would see the raw
runtime error instead of the probe's row-naming refusal.  (Under the pre-fix
runtime the failure was quieter still: a 297-digit guard answered NULL, and
`NULL >= anything` is null, never true — a quiet null instead of a refusal.)
Either way: raw jsonb, cast through numeric, never the runtime's readers.

THE SECOND WAY (plan §4.3) — the probe asks `jsonb_typeof(<op>) = 'number'`,
and an array is not a number.  `max($.l)` over `{"l": [1e300, 1]}` is NOT
refused: the operand `$.l` is an array, and walkthrough step 11 must show the
disagreement (Python `1e+300` beside SQL `1`), not a refusal.  The probe's
scope is the operands the expression touches, at the type they touch them —
it never looks inside containers.

The threshold literal is written `1.7976931348623157e+308` and compared with
`>=` — deliberately: as a `numeric` that literal is very slightly below the
true DBL_MAX, so a value of exactly DBL_MAX would be refused although it is
representable.  B15 rules that conservatism correct (a refusal is never a
wrong answer) and forbids "fixing" it into a `>`.

Both probes run BEFORE the pick's own statement, over the rows of the pick's
collection — `WHERE r.collection = %(collection)s` alone, exactly as plan
§4.3 writes the probe out.  The pick's filter is deliberately NOT applied to
the probe (W11 ruling, recorded in the build report): evaluating the filter
inside the probe would route the very guard-nulls the probe exists to
pre-empt — a filter like `$.huge > 0` silently DROPS the 1e400 row on the SQL
side (xpr.ord → xpr.f8 → NULL → not truthy), so a filtered probe would be
blinded by the poison it is looking for, and walkthrough step 12's own filter
operand could never be probed at all.

Fragment namespacing is B11's: every compiled operand is rewritten to its own
prefix — prbA0, prbA1, … for member (a); prbB0, … for member (b) — through
demo.builder.namespace() the moment that file exists (W10; a verbatim
fallback of B11's pinned rewrite is used until then, after which the fallback
is dead code to be deleted).
"""

from __future__ import annotations

import contextlib
import functools
import re
import unicodedata
import weakref
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import env, gate, paths

#: The real float8 limit, rendered at 17 significant digits (B15).  Since
#: the 2026-08-23 adoption (q4/GA-7) the vendored runtime's own guard sits
#: at this same value — its 309-digit positional expansion — where the
#: pre-fix guard sat twelve decades low at 1.7976931348623157e+296.
DBL_MAX_LITERAL = "1.7976931348623157e+308"

#: The comparison operators whose operands reach the guarded numeric read
#: when they hold numbers: xpr.ord routes number/number pairs through
#: xpr.f8.
_ORD_OPS = ("<", "<=", ">", ">=")
_EQ_OPS = ("==", "!=")


# ---------------------------------------------------------------------------------
# The named, catchable error — what "refuses loudly" means in code.
# ---------------------------------------------------------------------------------
class RuntimeRefusal(Exception):
    """A layer-2 refusal: the gate accepted the expression, but the DATA made
    SQL unable to answer.  The pick is abandoned before its own statement
    runs; the caller reports this as the labelled fallback to the Python pane
    (spec §4.5: the SQL pane shows the probe that fired and no number; the
    Python pane shows Python's answer, labelled).

    member   -- "a" (out-of-range magnitude) or "b" (container operand)
    cause    -- the human sentence the screen shows, naming the cause
    row_key  -- the first offending row's key under ORDER BY key, or None
    probe    -- the Probe that fired, so the pane can render its SQL
    """

    def __init__(self, member: str, cause: str, row_key: Optional[str],
                 probe: "Probe"):
        self.member = member
        self.cause = cause
        self.row_key = row_key
        self.probe = probe
        super().__init__(cause)


@dataclass(frozen=True)
class Probe:
    """One runtime probe, ready to execute and to display.

    sql        -- the parameterised EXISTS statement, plan §4.3's shape
    row_sql    -- the follow-up that names the first offending row (only run
                  when the probe fires; AC-18: the refusal names the row)
    params     -- the merged, prefix-namespaced operand bind parameters.
                  Does NOT include %(collection)s (bound at run time) nor the
                  per-fragment ctx parameters (listed in ctx_params).
    ctx_params -- the *_ctx parameter names the operand fragments reference
                  (only fragments using now()/today() have any)
    operands   -- the namespaced operand fragments, for the SQL pane
    """

    member: str
    sql: str
    row_sql: str
    params: Mapping[str, Any]
    ctx_params: Tuple[str, ...]
    operands: Tuple[str, ...]


@dataclass(frozen=True)
class ProbeOutcome:
    """What one probe answered.  Both outcomes are reported to the pane —
    including the probe that did not fire, stated as a comment (plan §4.3)."""

    probe: Probe
    fired: bool
    row_key: Optional[str] = None
    detail: Optional[str] = None     # member d: the first row's kind (large, small, digits) -- T-112


# ---------------------------------------------------------------------------------
# The compiler the probes compile with: the statement's own (``picks.env.use``,
# ``compiler``), so each operand a probe asks about is written exactly as the
# statement will compute it (T-87).  Until T-87 the probes compiled with the
# frozen T-1 spike, which writes numbers differently since T-52 / T-61.
# ---------------------------------------------------------------------------------
def _compile_module():
    return env.get("compiler")


# ---------------------------------------------------------------------------------
# B11's namespacing — picks/builder.py is its one home.
# ---------------------------------------------------------------------------------
def _namespace(frag, prefix: str) -> Tuple[str, Dict[str, Any]]:
    from .builder import namespace  # B11: the one namespacing function
    return namespace(frag, prefix)


# ---------------------------------------------------------------------------------
# Operand collection.  Which positions count as "reaching a numeric context"
# is enumerated MECHANICALLY from where the compiled SQL coerces a jsonb
# number through the guarded read (xpr.f8 / xpr.num, runtime.sql):
#
#   _num call sites (compile.py):  neg; both operands of + - * / %;
#       number(x); abs(x); floor(x); ceil(x); round(x, nd); date_add(_, n)
#   xpr.ord (< <= > >=):           number operands go through xpr.f8
#   xpr.str (string/lower/upper/concat):  number operands go through
#       ecma_num(xpr.f8(j)) — SQL nulls where Python does something else
#       with an out-of-double value.  (That "something else" is a RAISE,
#       not an "inf", wherever the value reaches Python as a full-digit
#       INTEGER literal, which is how jsonb renders its numerics — see the
#       correction beside AC-17 in .autodev/specs/T-2.md.  Either way the
#       position is a numeric context and still needs the probe, which is
#       the only thing this enumeration decides.)
#   xpr.reduce_one/reduce_arr (sum/avg/min/max):  a SCALAR argument is
#       wrapped and xpr.num-ed.  A LIST argument is an array — the probe's
#       jsonb_typeof(<op>) = 'number' test keeps it out, which is exactly
#       §4.3's required scope: max($.l) over {"l":[1e300,1]} is not refused.
#
# count / length / contains / days_between / coalesce / if / and / or / not
# never route a number operand through the guard (verified against
# runtime.sql; count counts, length measures, the rest pass values through),
# so their argument positions are not numeric contexts — though their
# SUBTREES are still walked, because a numeric context may sit inside.
# ---------------------------------------------------------------------------------
def _numeric_call_args(name: str, args: Sequence) -> List:
    if name in ("abs", "floor", "ceil", "number", "string", "lower", "upper"):
        return list(args[:1])
    if name == "round":
        return list(args[:2])
    if name == "date_add":
        return list(args[1:2]) if len(args) == 2 else []
    if name == "concat":
        return list(args)
    if name in ("sum", "avg", "min", "max"):
        return list(args)
    return []


def _never_probed(node) -> bool:
    """T-98: a time_of_day(...) value is a whole number from 0 to 86399, or null, by
    construction in both engines -- never past DBL_MAX (member a) and never an object or an
    array (member b) -- so it is no operand either probe needs, and compiling one would only
    carry its zone guard into a query that cannot fire."""
    return isinstance(node, tuple) and len(node) == 3 and node[0] == "call" and node[1] == "time_of_day"


def numeric_context_operands(ast, *, root_is_numeric: bool = False) -> List:
    """The sub-ASTs of *ast* that reach a guarded numeric read, in document
    order, deduplicated.  With root_is_numeric=True the whole AST is itself
    an operand as well — the shape for an aggregate or window FIELD
    expression, which the builder feeds to numeric_read() (ops 6, 7, 8)."""
    out: List = []
    seen: set = set()

    def add(node) -> None:
        key = repr(node)
        if key not in seen and not _never_probed(node):
            seen.add(key)
            out.append(node)

    def walk(node) -> None:
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag == "neg":
            add(node[1])
            walk(node[1])
        elif tag == "bin":
            add(node[2])
            add(node[3])
            walk(node[2])
            walk(node[3])
        elif tag == "cmp":
            if node[1] in _ORD_OPS:
                add(node[2])
                add(node[3])
            walk(node[2])
            walk(node[3])
        elif tag == "call":
            for a in _numeric_call_args(node[1], node[2]):
                add(a)
            for a in node[2]:
                walk(a)
        elif tag in ("and", "or"):
            walk(node[1])
            walk(node[2])
        elif tag == "not":
            walk(node[1])
        # field / num / str / bool / null are leaves: nothing beneath them.

    if root_is_numeric:
        add(ast)
    walk(ast)
    return out


def container_check_operands(ast) -> List:
    """Every == / != operand subexpression of *ast*, in document order,
    deduplicated (spec §4.6: the gate allows the construct; layer 2 gets the
    operand list — derived here from the same AST the gate accepted)."""
    out: List = []
    seen: set = set()

    def add(node) -> None:
        key = repr(node)
        if key not in seen and not _never_probed(node):
            seen.add(key)
            out.append(node)

    def walk(node) -> None:
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag == "cmp" and node[1] in _EQ_OPS:
            add(node[2])
            add(node[3])
        for child in node[1:]:
            if isinstance(child, tuple):
                walk(child)
            elif isinstance(child, list):  # ("call", name, [args...])
                for c in child:
                    walk(c)

    walk(ast)
    return out


# ---------------------------------------------------------------------------------
# Probe construction — plan §4.3's SQL, verbatim in shape.
# ---------------------------------------------------------------------------------
def _term_a(op_sql: str) -> str:
    return (
        "( jsonb_typeof( " + op_sql + " ) = 'number'\n"
        "             AND abs( ( " + op_sql + " #>> '{}' )::numeric ) >= "
        + DBL_MAX_LITERAL + "::numeric )"
    )


def _term_b(op_sql: str) -> str:
    return "( jsonb_typeof( " + op_sql + " ) IN ('object','array') )"


# ---------------------------------------------------------------------------------
# Member (d) -- T-112: a stored number this pick reads AS A DOUBLE, which no double holds.
#
# GIMS's language computes and compares in doubles on both engines; a stored number no double holds has no honest
# reading there (``picks/doubles.py`` states the rule: held when the double nearest to it, written as Postgres writes
# a double, is the same number). The statement rounds most such numbers silently, so this probe asks first, over the
# same scope as member (a), with the database's own printer (``xpr.j``: float8out at extra_float_digits = 1). The
# second engine asks the same question its own way (``picks/pyrunner/exact.py``).
#
# It fires on the two silent misreadings: a number a double holds only as 0 (small) and one with more digits than a
# double holds (digits). A number at or past the largest double is not its business: the statement already refuses
# one (member (a), or XPR01 while running), and the language declines one in arithmetic (the foreman's ruling (A)).
#
# Where a stored value is read as a double (this side's statement of the positions; pyrunner states them again):
#   NUMBER    a comparison operand (< <= > >= == !=), truthiness (a filter's root, not / and / or, if's condition):
#             a JSON number is read as a double; text compares as text and is never read
#   COERCED   unary minus, + - * /, abs, min / max of several: a JSON number, or a number written as text (as the
#             language reads one: inside Python's 29 spaces, in any script's digits -- xpr.num's reading since T-6
#             variant C), is read as a double
#   ELEMENTS  min / max of one argument: as COERCED, and a list's elements too (among several, a list is skipped)
# A field passed through (a computed column's value, coalesce's arguments, if's branches) takes the place of the
# call around it; count / length / time_of_day read no number.
# ---------------------------------------------------------------------------------
_D_SHOWN, _D_NUMBER, _D_COERCED, _D_ELEMENTS = "shown", "number", "coerced", "elements"
_TEXT_NUMBER_RE = r"^[+-]?([0-9]+[.]?[0-9]*|[.][0-9]+)([eE][+-]?[0-9]+)?$"
_ASCII_WS_SQL = r"E' \t\n\r\f\x0b'"
#: a number's text whose digits before the exponent are all zero: zero, whatever the exponent (a-chk's M3)
_ZERO_RE = r"^[+-]?[0.]*([eE]|$)"
_D_SMALL, _D_DIGITS = "small", "digits"


@functools.lru_cache(maxsize=1)
def _text_code_points() -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """What the runtime's ``xpr.num`` reads text with beyond ASCII (T-6 variant C), from this Python's Unicode data
    as ``runtime/generate.py`` derives it: the 29 code points ``str.strip()`` removes, and the zero of each script's
    decimal digits (every one of them a run of ten, 0 to 9: 67 runs, 670 digits)."""
    ws = tuple(cp for cp in range(0x110000) if chr(cp).isspace())
    zeros = tuple(cp for cp in range(0x80, 0x110000)
                  if unicodedata.category(chr(cp)) == "Nd" and unicodedata.decimal(chr(cp)) == 0)
    return ws, zeros


def text_tables() -> Tuple[str, str, str]:
    """``xpr.num``'s three tables as probe d builds them: the spaces, every non-ASCII digit, the digit each is."""
    ws, zeros = _text_code_points()
    return ("".join(map(chr, ws)), "".join(chr(z + d) for z in zeros for d in range(10)), "0123456789" * len(zeros))


def _d_text_tables_sql() -> Tuple[str, str, str]:
    """:func:`text_tables` as SQL: built once a statement from the code points (an InitPlan), never shipped whole."""
    ws, zeros = _text_code_points()
    return (f"(SELECT string_agg(chr(c), '') FROM unnest('{{{','.join(map(str, ws))}}}'::int[]) AS s(c))",
            f"(SELECT string_agg(chr(z + d), '' ORDER BY z, d) FROM unnest('{{{','.join(map(str, zeros))}}}'::int[])"
            f" AS s(z), generate_series(0, 9) AS g(d))",
            f"repeat('0123456789', {len(zeros)})")


def _d_unicode_text(op: str, txt: str, test) -> str:
    """The condition *test* over a number written as text that isn't one in ASCII as it stands (a-chk's H2): read
    as ``xpr.num`` reads it, trimmed of the 29 spaces with every script's digits mapped onto 0-9. Plain ASCII is
    left out first (that reading can't change it), so ordinary text pays one pattern; the translate is nested, as
    in ``xpr.num``, and the reading made once, in a subquery."""
    ws, nd_from, nd_to = _d_text_tables_sql()
    x = "rd.x"
    fast = f"({x} !~ '[eE]' AND length({x}) <= 15)"
    return (f"(jsonb_typeof({op}) = 'string' AND {txt} !~ '{_TEXT_NUMBER_RE}'"
            f" AND ({op} #>> '{{}}') !~ '^[\\x01-\\x1b\\x20-\\x7f]*$'"
            f" AND EXISTS (SELECT 1 FROM (SELECT translate(btrim({op} #>> '{{}}', {ws}), {nd_from}, {nd_to}) AS x)"
            f" AS rd WHERE {x} ~ '{_TEXT_NUMBER_RE}' AND {test(x, fast)}))")


def exact_reading_operands(ast, root: str = _D_SHOWN) -> List[Tuple[Any, str]]:
    """``[(field AST, position)]``: every field *ast* reads as a double (member d's operands), deduplicated."""
    out: List[Tuple[Any, str]] = []
    seen: set = set()

    def walk(node, pos: str) -> None:
        if not isinstance(node, tuple) or not node:
            return
        tag = node[0]
        if tag == "field":
            key = (repr(node), pos)
            if pos != _D_SHOWN and key not in seen:
                seen.add(key)
                out.append((node, pos))
        elif tag == "neg":
            walk(node[1], _D_COERCED)
        elif tag == "bin":
            walk(node[2], _D_COERCED)
            walk(node[3], _D_COERCED)
        elif tag == "cmp":
            walk(node[2], _D_NUMBER)
            walk(node[3], _D_NUMBER)
        elif tag == "not":
            walk(node[1], _D_NUMBER)
        elif tag in ("and", "or"):
            walk(node[1], _D_NUMBER)
            walk(node[2], _D_NUMBER)
        elif tag == "call":
            name, args = node[1], node[2]
            if name == "coalesce":
                for a in args:
                    walk(a, pos)
            elif name == "if":
                for i, a in enumerate(args):
                    walk(a, _D_NUMBER if i == 0 else pos)
            elif name in ("min", "max") and len(args) == 1:      # among several, a list is skipped (M2)
                for a in args:
                    walk(a, _D_ELEMENTS)
            elif name in ("count", "length", "time_of_day"):
                for a in args:
                    walk(a, _D_SHOWN)
            else:
                for a in args:
                    walk(a, _D_COERCED)

    walk(ast, root)
    return out


def _held_sql(t: str, fast: str) -> str:
    """True when the text *t* (a number's digits) is held: the CASE guards every cast, so no input can raise."""
    return (f"(CASE WHEN {fast} THEN true"
            f" WHEN NOT pg_input_is_valid({t}, 'numeric') THEN ({t}) ~ '{_ZERO_RE}'"
            f" WHEN abs(({t})::numeric) >= {DBL_MAX_LITERAL}::numeric THEN false"
            f" WHEN NOT pg_input_is_valid({t}, 'float8') THEN false"
            f" ELSE ({t})::numeric = (xpr.j(({t})::float8) #>> '{{}}')::numeric END)")


def _fires_sql(t: str, fast: str) -> str:
    """True when the text *t* fires member d: not held, and not at or past the largest double (member (a)'s)."""
    return f"(NOT {_held_sql(t, fast)} AND NOT {_large_sql(t)})"


def _large_sql(t: str) -> str:
    return (f"(CASE WHEN NOT pg_input_is_valid({t}, 'numeric') THEN ({t}) !~ '[eE]-'"
            f" ELSE abs(({t})::numeric) >= {DBL_MAX_LITERAL}::numeric END)")


def _small_sql(t: str) -> str:
    return (f"(CASE WHEN NOT pg_input_is_valid({t}, 'numeric') THEN ({t}) ~ '[eE]-' AND ({t}) !~ '{_ZERO_RE}'"
            f" WHEN abs(({t})::numeric) >= {DBL_MAX_LITERAL}::numeric THEN false"
            f" WHEN ({t})::numeric = 0 THEN false"
            f" ELSE NOT pg_input_is_valid({t}, 'float8') END)")


def _d_forms(op: str, pos: str, test) -> str:
    """The condition *test* (a function of a text SQL expression and its fast-path SQL) over the value *op* (jsonb)
    takes at *pos*: a JSON number; at COERCED/ELEMENTS a number written as text; at ELEMENTS a list's elements."""
    num_t = f"({op} #>> '{{}}')"
    parts = [f"(jsonb_typeof({op}) = 'number' AND {test(num_t, f'length({num_t}) <= 15')})"]
    if pos in (_D_COERCED, _D_ELEMENTS):
        txt = f"btrim({op} #>> '{{}}', {_ASCII_WS_SQL})"
        fast_txt = f"({txt} !~ '[eE]' AND length({txt}) <= 15)"
        parts.append(f"(jsonb_typeof({op}) = 'string' AND {txt} ~ '{_TEXT_NUMBER_RE}' AND {test(txt, fast_txt)})")
        parts.append(_d_unicode_text(op, txt, test))
    if pos == _D_ELEMENTS:
        inner = _d_forms("e.v", _D_COERCED, test)
        parts.append(f"(jsonb_typeof({op}) = 'array' AND EXISTS (SELECT 1 FROM jsonb_array_elements({op}) AS e(v)"
                     f" WHERE {inner}))")
    return "(" + " OR ".join(parts) + ")"


def _build_probe_d(operands: Sequence[Tuple[Any, str]], records, compile_kw: dict) -> Probe:
    from .builder import build_statement   # T-102: a probe is a statement too
    return build_statement(_build_probe_d_unbudgeted)(operands, records, compile_kw)


def _build_probe_d_unbudgeted(operands: Sequence[Tuple[Any, str]], records, compile_kw: dict) -> Probe:
    compile_ast = _compile_module().compile_ast
    merged: Dict[str, Any] = {}
    ctx_names: List[str] = []
    fires, small, operand_sqls = [], [], []
    for i, (op_ast, pos) in enumerate(operands):
        prefix = f"prbD{i}"
        ctx_name = f"{prefix}_ctx"
        frag = compile_ast(op_ast, ctx_param=ctx_name, **compile_kw)
        sql, params = _namespace(frag, prefix)
        merged.update(params)
        if f"%({ctx_name})s" in sql:
            ctx_names.append(ctx_name)
        operand_sqls.append(sql)
        fires.append(_d_forms(sql, pos, _fires_sql))
        small.append(_d_forms(sql, pos, lambda t, fast: _small_sql(t)))
    where = ("   WHERE " + records.scope("r", merged) + "\n"
             "     AND ( " + "\n        OR ".join(fires) + " )")
    sql = "SELECT EXISTS (\n" f"  SELECT 1 FROM {records.table} AS r\n" + where + "\n);"
    row_sql = (f"SELECT r.key, CASE WHEN ({' OR '.join(small)}) THEN '{_D_SMALL}' ELSE '{_D_DIGITS}' END\n"
               f"  FROM {records.table} AS r\n" + where + "\n"
               ' ORDER BY r.key COLLATE "C"\n LIMIT 1;')
    return Probe(member="d", sql=sql, row_sql=row_sql, params=merged, ctx_params=tuple(ctx_names),
                 operands=tuple(operand_sqls))


def _build_probe(member: str, operand_asts: Sequence, records, compile_kw: dict) -> Probe:
    from .builder import build_statement   # T-102: a probe is a statement too
    return build_statement(_build_probe_unbudgeted)(member, operand_asts, records, compile_kw)


def _build_probe_unbudgeted(member: str, operand_asts: Sequence, records, compile_kw: dict) -> Probe:
    compile_ast = _compile_module().compile_ast
    prefix_stem = "prbA" if member == "a" else "prbB"
    term_fn = _term_a if member == "a" else _term_b

    operand_sqls: List[str] = []
    merged: Dict[str, Any] = {}
    ctx_names: List[str] = []
    terms: List[str] = []

    for i, op_ast in enumerate(operand_asts):
        prefix = f"{prefix_stem}{i}"
        ctx_name = f"{prefix}_ctx"
        try:
            frag = compile_ast(op_ast, ctx_param=ctx_name, **compile_kw)
        except _compile_module().TooBig as exc:
            # T-102: an operand compiled on its own (as a probe reads it) can pass the budget
            # even when the whole statement did not; the pick is refused, never half-checked.
            from .builder import too_big_words
            raise gate.Refused(repr(op_ast)[:80], too_big_words()) from exc
        sql, params = _namespace(frag, prefix)
        for k, v in params.items():
            if k in merged and merged[k] != v:  # cannot happen: prefixes disjoint
                raise AssertionError(f"bind parameter collision on {k!r}")
            merged[k] = v
        if f"%({ctx_name})s" in sql:
            ctx_names.append(ctx_name)
        operand_sqls.append(sql)
        terms.append(term_fn(sql))

    body = "\n        OR ".join(terms)
    where = (
        "   WHERE " + records.scope("r", merged) + "\n"
        "     AND ( " + body + " )"
    )
    sql = (
        "SELECT EXISTS (\n"
        f"  SELECT 1 FROM {records.table} AS r\n"
        + where + "\n"
        ");"
    )
    row_sql = (
        f"SELECT r.key FROM {records.table} AS r\n"
        + where + "\n"
        ' ORDER BY r.key COLLATE "C"\n'
        " LIMIT 1;"
    )
    return Probe(
        member=member,
        sql=sql,
        row_sql=row_sql,
        params=merged,
        ctx_params=tuple(ctx_names),
        operands=tuple(operand_sqls),
    )


def _instant_fields(times: Sequence) -> set:
    """T-114: the fields a pick's truths read as instants (its ``times``, as field ASTs). Read so, a field is text,
    null or false in both engines -- never a number past a double, an object or a list, or a number a double
    misreads -- so no member could fire on it (T-98's reason for a time_of_day): a truth's such field is not
    probed. A computed column or a measure reads the field raw, and is probed as before."""
    if not times:
        return set()
    parse = env.get("parser").parse
    return {repr(parse(paths.dollar(t))) for t in times}


def build_probes(exprs: Sequence, *, numeric_roots: Sequence = (), truth_roots: Sequence = (), records=None,
                 collection: Optional[str] = None, times: Sequence = ()) -> List[Probe]:
    """Build the (at most two) probes for one pick.

    exprs         -- every expression AST the pick carries: each computed
                     column's, and the filter's, in pick order
    numeric_roots -- expression ASTs that are THEMSELVES fed to the builder's
                     numeric_read() — the aggregate's field expression and
                     the window field's (ops 6, 7, 8)

    truth_roots   -- expression ASTs whose truth is taken: the filter, a board's counts (T-112: their root is read
                     as a double, where a computed column's root is only shown). Probed as ``exprs`` are by (a)
                     and (b).

    A member with no operands builds no probe: the returned list holds only
    probes with something to ask, member (a) first, then (b), then (d).

    times         -- T-114: the fields the truths read as instants (the pick's ``times``, a board's
                     ``count_times`` / ``times``): a truth's such field is never probed (``_instant_fields``)

    records       -- the records description (default: the process's); its
                     table and partition scope each probe, and with a fold
                     the compiler needs ``collection``
    """
    records = env.records(records)
    compile_kw = records.compile_kwargs(collection) if records.fold else {}
    # T-98: a probed operand may hold a time_of_day; it compiles exactly as the statement does
    compile_kw = dict(compile_kw, time_zones=env.time_zones(), zone_gaps=env.zone_gaps())
    ops_a: List = []
    seen_a: set = set()
    ops_b: List = []
    seen_b: set = set()
    skip: set = set()                  # T-114: filled while the truths are walked (_instant_fields)

    def extend(target: List, seen: set, nodes: Sequence) -> None:
        for n in nodes:
            key = repr(n)
            if key not in seen and key not in skip:
                seen.add(key)
                target.append(n)

    ops_d: List[Tuple[Any, str]] = []
    seen_d: set = set()

    def extend_d(nodes: Sequence[Tuple[Any, str]]) -> None:
        for n, pos in nodes:
            key = (repr(n), pos)
            if key not in seen_d and repr(n) not in skip:
                seen_d.add(key)
                ops_d.append((n, pos))

    instant = _instant_fields(times)
    for e in exprs:
        extend(ops_a, seen_a, numeric_context_operands(e))
        extend(ops_b, seen_b, container_check_operands(e))
    skip.update(instant)
    for e in truth_roots:
        extend(ops_a, seen_a, numeric_context_operands(e))
        extend(ops_b, seen_b, container_check_operands(e))
    skip.clear()
    for r in numeric_roots:
        extend(ops_a, seen_a, numeric_context_operands(r, root_is_numeric=True))
        extend(ops_b, seen_b, container_check_operands(r))
    for e in exprs:
        extend_d(exact_reading_operands(e, _D_SHOWN))
    skip.update(instant)
    for e in truth_roots:
        extend_d(exact_reading_operands(e, _D_NUMBER))
    skip.clear()
    for r in numeric_roots:
        extend_d(exact_reading_operands(r, _D_SHOWN))   # an aggregate's field is read as numeric, exactly

    probes: List[Probe] = []
    if ops_a:
        probes.append(_build_probe("a", ops_a, records, compile_kw))
    if ops_b:
        probes.append(_build_probe("b", ops_b, records, compile_kw))
    if ops_d:
        probes.append(_build_probe_d(ops_d, records, compile_kw))
    return probes


# ---------------------------------------------------------------------------------
# Execution.
# ---------------------------------------------------------------------------------
def run_probes(conn, collection: str, probes: Sequence[Probe], *,
               ctx: str = "{}") -> List[ProbeOutcome]:
    """Execute every probe over *collection* and report each outcome.

    Both probes always run — the pane shows the one that did not fire as a
    comment (plan §4.3), and that claim needs a real answer behind it.  When
    a probe fires, the follow-up names the first offending row under
    ORDER BY key.  Nothing here raises on a firing; check() does.
    """
    outcomes: List[ProbeOutcome] = []
    for p in probes:
        params: Dict[str, Any] = dict(p.params)
        params["collection"] = collection
        for name in p.ctx_params:
            params[name] = ctx
        fired, row_key, detail = _ask(conn, p, params)
        outcomes.append(ProbeOutcome(probe=p, fired=fired, row_key=row_key, detail=detail))
    return outcomes


#: The runtime's own out-of-range refusals: ``XPR01`` (a number past the
#: largest double, read by the runtime) and ``22003`` (float8 overflow).
_OUT_OF_RANGE = ("XPR01", "22003")


@contextlib.contextmanager
def _without_jit(conn):
    """One probe query under its own savepoint, with Postgres's JIT off (run 11, a-chk's pre-check of the round: probe
    d's text reading made its statement big enough for the LLVM JIT to compile it on every run, about 1.5 s, for a
    scan that answers in milliseconds). The setting is the transaction's own and is put back as it was before the
    savepoint is released, so the pick's statement after the probes plans exactly as it did; a probe that raises
    rolls the savepoint back, and the setting with it."""
    with conn.transaction():
        was = conn.execute("SELECT current_setting('jit')").fetchone()[0]
        conn.execute("SET LOCAL jit = off")
        yield
        conn.execute("SELECT set_config('jit', %s, true)", (was,))


def _ask(conn, p: Probe, params: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """One probe's answer — fired, the first offending key, and (member d) that row's kind.

    The magnitude probe reads its operands; an operand that itself computes
    with an out-of-range number (``abs($.huge)``, ``$.g * 3``) makes the PROBE
    raise the runtime's out-of-range refusal before it can answer — which is
    the answer: the data holds a number the statement could not use.  So
    that refusal counts as FIRED, the first offending key unknown (T-87;
    until then the pick answered 500).  Each query runs under a savepoint, so
    the caller's transaction stays usable, and with the JIT off (``_without_jit``); any other error still raises."""
    try:
        with _without_jit(conn):
            fired = bool(conn.execute(p.sql, params).fetchone()[0])
    except Exception as exc:  # noqa: BLE001 — two SQLSTATEs, re-raised otherwise
        if getattr(exc, "sqlstate", None) not in _OUT_OF_RANGE or p.member != "a":
            raise
        return True, None, None
    if not fired:
        return False, None, None
    try:
        with _without_jit(conn):
            row = conn.execute(p.row_sql, params).fetchone()
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "sqlstate", None) not in _OUT_OF_RANGE or p.member != "a":
            raise
        return True, None, None
    if row is None:
        return True, None, None
    return True, row[0], (row[1] if len(row) > 1 else None)


def _cause(member: str, row_key: Optional[str]) -> str:
    where = f' (first such row, by key: "{row_key}")' if row_key else ""
    if member == "a":
        return (
            "out-of-range magnitude: this pick reads a number of magnitude >= "
            + DBL_MAX_LITERAL
            + ", which the database's float8 cannot represent"
            + where
        )
    return (
        "container operand: an == or != operand resolved to an object or an "
        "array, which the safe subset does not compare"
        + where
    )


# ---------------------------------------------------------------------------------
# T-110: a sort over text nested in jsonb, on a database that orders that text its own way
# ---------------------------------------------------------------------------------
#: How many order checks and sort probes have run (the tests read them: once per database; none on C).
ORDER_CHECKS_RUN = 0
SORT_PROBES_RUN = 0
#: The order check's answer, cached by the server (host, port, pg_postmaster_start_time()) and the database itself
#: (name, OID and its collation facts: a database dropped and recreated with another collation is asked again; a-chk,
#: T-110's round), as zones caches D; and remembered per connection, so a pick asks nothing twice.
_ORDER_CACHE: Dict[tuple, bool] = {}
_ORDER_SEEN: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_DATABASE_FACTS_SQL = ("SELECT to_jsonb(d), pg_postmaster_start_time()::text FROM pg_database d "
                       "WHERE d.datname = current_database()")
#: The battery a database must pass before nested text is read as code points (a-chk, T-110's round: one tailoring
#: rule passed the B/a pair alone): each (x, y) is x < y in code points, as list elements and, at equal UTF-8 lengths
#: so no length rule decides them, as object keys -- case, an accent, a decomposed letter, digits as text,
#: punctuation, a space, CJK against astral.
_CODE_POINT_PAIRS = (
    ("B", "a", "B", "a"),
    ("f", "\u00e9", "ez", "\u00e9"),
    ("ea", "e\u0301", "eaa", "e\u0301"),
    ("10", "9", "10", "9a"),
    ("-b", "a", "-b", "ab"),
    (" b", "a", " b", "ab"),
    ("\u4e2d", "\U0001F600", "\u4e2da", "\U0001F600"),
)
_BATTERY_SQL = ("SELECT bool_and(to_jsonb(ARRAY[x]) < to_jsonb(ARRAY[y]) "
                "AND jsonb_build_object(kx, 1) < jsonb_build_object(ky, 1)) "
                "FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[]) AS t(x, y, kx, ky)")


class SortRefusal(RuntimeRefusal):
    """Member "c": the pick sorts by a value whose nested text this database orders by its own collation, which
    the second engine (code points) would not; ``field`` is the sort field as the pick names it."""

    def __init__(self, field: str, row_key: Optional[str], probe: Probe):
        self.field = field
        where = f' (first such row, by key: "{row_key}")' if row_key else ""
        super().__init__(member="c", row_key=row_key, probe=probe, cause=(
            f"nested text order: two or more rows hold text inside a list or an object at the sort value {field}, "
            "and this database orders text inside a jsonb value by its own collation, not in code points" + where))


def nested_text_in_code_points(conn) -> bool:
    """T-110 (a-chk's proposal): does this database compare text INSIDE a jsonb value in code points, as the second
    engine does? Trusted by name only for a libc C or POSIX database; anything else must pass the whole battery
    (glibc's C.UTF-8 and musl's locales do; glibc's en_US, ICU, and ICU with one tailoring rule don't). Asked once
    per database (its OID and collation in the key), and once per connection."""
    global ORDER_CHECKS_RUN
    hit = _ORDER_SEEN.get(conn)
    if hit is not None:
        return hit
    info = conn.info
    with conn.transaction():
        facts, started = conn.execute(_DATABASE_FACTS_SQL).fetchone()
        key = (info.host, info.port, started, facts.get("datname"), facts.get("oid"), facts.get("datlocprovider"),
               facts.get("datcollate"), facts.get("daticulocale", facts.get("datlocale")), facts.get("daticurules"))
        hit = _ORDER_CACHE.get(key)
        if hit is None:
            if facts.get("datlocprovider") == "c" and facts.get("datcollate") in ("C", "POSIX"):
                hit = True
            else:
                hit = bool(conn.execute(_BATTERY_SQL, [list(p) for p in zip(*_CODE_POINT_PAIRS)]).fetchone()[0])
            ORDER_CHECKS_RUN += 1
            _ORDER_CACHE[key] = hit
    _ORDER_SEEN[conn] = hit
    return hit


def check_sort(conn, pick: dict, collection_keys, *, records=None, ctx: Optional[dict] = None):
    """T-110, layer 2 for a sort: on a database that orders nested text its own way, a rows pick sorted by a value
    holding text inside a list or an object, in two or more rows, is refused (:class:`SortRefusal`) before its
    statement runs, where its two engines could order the rows two ways. On C nothing is asked. Returns the
    outcome when the probe ran and did not fire, else None."""
    global SORT_PROBES_RUN
    if not ((pick.get("sort") or {}).get("field")):
        return None                       # nothing sorted: nothing to ask (a-chk's LOW 2)
    if nested_text_in_code_points(conn):
        return None
    from .builder import sort_probe  # the statement's own pieces (scope, filter, sort value)
    built = sort_probe(pick, collection_keys, ctx=ctx, records=records)
    if built is None:
        return None
    probe = Probe(member="c", sql=built.sql, row_sql=built.sql, params=dict(built.params), ctx_params=(),
                  operands=())
    with _without_jit(conn):
        fired, first_key = conn.execute(built.sql, built.params).fetchone()
    SORT_PROBES_RUN += 1
    if fired:
        raise SortRefusal(pick["sort"]["field"], first_key, probe)
    return ProbeOutcome(probe=probe, fired=False)


class NumberRefusal(RuntimeRefusal):
    """Member "d" (T-112): a stored number this pick reads as a double, which no double holds. ``kind`` is
    ``small`` or ``digits`` (``picks.doubles``), the first offending row's."""

    def __init__(self, kind: str, row_key: Optional[str], probe: "Probe"):
        self.kind = kind
        super().__init__(member="d", cause=_cause_d(kind, row_key), row_key=row_key, probe=probe)


_D_WORDS = {
    _D_SMALL: "number too small for a double: this pick reads a number a double holds only as 0",
    _D_DIGITS: "number with more digits than a double holds: this pick reads a number no double holds exactly",
}


def _cause_d(kind: str, row_key: Optional[str]) -> str:
    where = f' (first such row, by key: "{row_key}")' if row_key else ""
    return _D_WORDS.get(kind, _D_WORDS[_D_DIGITS]) + where


def check(conn, collection: str, exprs: Sequence, *,
          numeric_roots: Sequence = (), truth_roots: Sequence = (), ctx: str = "{}",
          records=None, times: Sequence = ()) -> List[ProbeOutcome]:
    """Layer 2, in one call: build both probes, run both, and raise the named
    RuntimeRefusal if either fired — member (a) taking precedence.  Returns
    every outcome (for the pane) when nothing fired.

    The caller catches RuntimeRefusal and reports the pick as the labelled
    fallback to the Python pane; it must never see a number from the SQL side
    once this has raised.
    """
    outcomes = run_probes(conn, collection,
                          build_probes(exprs, numeric_roots=numeric_roots, truth_roots=truth_roots,
                                       records=records, collection=collection, times=times),
                          ctx=ctx)
    for outcome in outcomes:  # member "a" precedes "b", and "b" precedes "d", by construction
        if outcome.fired and outcome.probe.member == "d":
            raise NumberRefusal(outcome.detail or _D_DIGITS, outcome.row_key, outcome.probe)
        if outcome.fired:
            raise RuntimeRefusal(
                member=outcome.probe.member,
                cause=_cause(outcome.probe.member, outcome.row_key),
                row_key=outcome.row_key,
                probe=outcome.probe,
            )
    return outcomes
