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

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPILE_PY = _REPO_ROOT / "spikes" / "T-1" / "proto" / "compile.py"

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


# ---------------------------------------------------------------------------------
# The pinned compiler, loaded read-only from the spike (Q19: never edited;
# AC-33 checksums it; the manifest records its digest).
# ---------------------------------------------------------------------------------
def _compile_module():
    mod = sys.modules.get("t1_proto_compile")
    if mod is None:
        spec = importlib.util.spec_from_file_location("t1_proto_compile",
                                                      _COMPILE_PY)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise ImportError(f"cannot load {_COMPILE_PY}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["t1_proto_compile"] = mod
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------------
# B11's namespacing — demo/builder.py is its one home.  Until W10 lands that
# file, the verbatim fallback below implements the pinned rewrite; the moment
# demo.builder imports, the fallback is dead code (the same TEMPORARY shape
# W5's demo_connection() uses for demo/server/db.py).
# ---------------------------------------------------------------------------------
def _namespace(frag, prefix: str) -> Tuple[str, Dict[str, Any]]:
    try:
        from demo.builder import namespace  # B11: the one namespacing function
    except ImportError:
        sql = re.sub(r"%\((p\d+)\)s", rf"%({prefix}_\1)s", frag.sql)
        params = {f"{prefix}_{k}": v for k, v in frag.params.items()}
        return sql, params
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


def numeric_context_operands(ast, *, root_is_numeric: bool = False) -> List:
    """The sub-ASTs of *ast* that reach a guarded numeric read, in document
    order, deduplicated.  With root_is_numeric=True the whole AST is itself
    an operand as well — the shape for an aggregate or window FIELD
    expression, which the builder feeds to numeric_read() (ops 6, 7, 8)."""
    out: List = []
    seen: set = set()

    def add(node) -> None:
        key = repr(node)
        if key not in seen:
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
        if key not in seen:
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


def _build_probe(member: str, operand_asts: Sequence) -> Probe:
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
        frag = compile_ast(op_ast, ctx_param=ctx_name)
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
        "   WHERE r.collection = %(collection)s\n"
        "     AND ( " + body + " )"
    )
    sql = (
        "SELECT EXISTS (\n"
        "  SELECT 1 FROM demo.records AS r\n"
        + where + "\n"
        ");"
    )
    row_sql = (
        "SELECT r.key FROM demo.records AS r\n"
        + where + "\n"
        " ORDER BY r.key\n"
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


def build_probes(exprs: Sequence, *, numeric_roots: Sequence = ()) -> List[Probe]:
    """Build the (at most two) probes for one pick.

    exprs         -- every expression AST the pick carries: each computed
                     column's, and the filter's, in pick order
    numeric_roots -- expression ASTs that are THEMSELVES fed to the builder's
                     numeric_read() — the aggregate's field expression and
                     the window field's (ops 6, 7, 8)

    A member with no operands builds no probe: the returned list holds only
    probes with something to ask, member (a) first.
    """
    ops_a: List = []
    seen_a: set = set()
    ops_b: List = []
    seen_b: set = set()

    def extend(target: List, seen: set, nodes: Sequence) -> None:
        for n in nodes:
            key = repr(n)
            if key not in seen:
                seen.add(key)
                target.append(n)

    for e in exprs:
        extend(ops_a, seen_a, numeric_context_operands(e))
        extend(ops_b, seen_b, container_check_operands(e))
    for r in numeric_roots:
        extend(ops_a, seen_a, numeric_context_operands(r, root_is_numeric=True))
        extend(ops_b, seen_b, container_check_operands(r))

    probes: List[Probe] = []
    if ops_a:
        probes.append(_build_probe("a", ops_a))
    if ops_b:
        probes.append(_build_probe("b", ops_b))
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
        cur = conn.execute(p.sql, params)
        fired = bool(cur.fetchone()[0])
        row_key: Optional[str] = None
        if fired:
            cur = conn.execute(p.row_sql, params)
            row = cur.fetchone()
            row_key = row[0] if row is not None else None
        outcomes.append(ProbeOutcome(probe=p, fired=fired, row_key=row_key))
    return outcomes


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


def check(conn, collection: str, exprs: Sequence, *,
          numeric_roots: Sequence = (), ctx: str = "{}") -> List[ProbeOutcome]:
    """Layer 2, in one call: build both probes, run both, and raise the named
    RuntimeRefusal if either fired — member (a) taking precedence.  Returns
    every outcome (for the pane) when nothing fired.

    The caller catches RuntimeRefusal and reports the pick as the labelled
    fallback to the Python pane; it must never see a number from the SQL side
    once this has raised.
    """
    outcomes = run_probes(conn, collection,
                          build_probes(exprs, numeric_roots=numeric_roots),
                          ctx=ctx)
    for outcome in outcomes:  # member "a" precedes "b" by construction
        if outcome.fired:
            raise RuntimeRefusal(
                member=outcome.probe.member,
                cause=_cause(outcome.probe.member, outcome.row_key),
                row_key=outcome.row_key,
                probe=outcome.probe,
            )
    return outcomes
