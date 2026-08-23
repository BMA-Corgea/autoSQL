"""demo/builder.py — the query builder (W10; plan §4: B1, B2, B3, B5a, B11).

THE HEART OF THE DEMO.  Everything SQL-shaped the demo executes for a pick is
emitted here, and nowhere else.  The contract is T-2-plan.md §4 in full:

  §4.1  the pipeline order — source, computed columns, filter, window,
        keep-only-changed, aggregate/bucket, sort, cap LAST.
  §4.2  the four statement shapes (A rows · B rows+changed · C scalar ·
        D bucket), emitted by :func:`build`.
  §4.4  the alias — the only user text in the SQL text — validated and
        quoted by ``gate.emit_alias`` at EVERY emission site, never here.
  §4.5  one place per rule: this file owns exactly two of the table's
        rows — ``numeric_read(j_sql)`` (ops 6, 7, 8) and
        ``namespace(frag, prefix)`` (every ``compile_ast`` call site).

The four broken-SQL resolutions this file implements:

  B1   exactly ONE emitted column named ``bucket`` — the ``to_char`` text
       label; ``date_trunc`` is the inner expression and carries no alias
       of its own, so ``ORDER BY "bucket"`` cannot be ambiguous.
  B2   the aggregate NEVER references a SELECT-list alias (42703).  When
       operation 6's field names a computed column, that column's compiled
       expression is re-emitted INLINE, wrapped in the numeric read.  Under
       B5a the computed column is not even emitted in that shape, so no
       alias exists in the statement at all.
  B3   operation 9's flag lives in a CTE and is filtered in the outer
       query (``WHERE "changed"``) — a window function may not appear in
       WHERE (42P20).  The filter (op 3) is INSIDE the CTE; ``LIMIT`` is
       OUTSIDE, capping kept rows.  The CTE exists if and only if
       operation 9 is on.
  B11  ``compile.py`` restarts bind parameters at ``p0`` on every call, so
       every compiled fragment is namespaced before it may enter a
       statement — ``cc0``, ``cc1``, … for computed columns, ``flt`` for
       the filter, ``agg`` / ``win`` for the two numeric-read re-emissions
       (probes.py uses ``prbA0``…/``prbB0``… — W11).  Merging is checked,
       not assumed: :func:`merge_params` raises on ANY key collision.

The pick dict is legality.py's (its shape is pinned beside
``legality.evaluate``).  Field values on the wire (op 4's sort field, op
6's aggregate field, op 8's window field) are either

  * a JSON field path — dotted text such as ``ts`` or ``payload.load``
    (a leading ``$.`` is accepted and stripped) — which reaches the SQL
    only as a text[] bind parameter (``data #> %(sort_path)s``, AC-28); or
  * the NAME of a computed column defined in this pick — resolved per
    §4.4 row 6: as a quoted alias reference in ORDER BY (legal Postgres
    extension), and per B2 as the re-emitted compiled expression inside
    the numeric read.  Never as bare SQL text.

Operation 9's compared value is a CONSTANT of this module (AC-40(e)):
``COMPARED_EXPR`` below.  Nothing about it derives from the request.

This module never touches a database: it emits statements.  Executing
them is the server's (W13, through demo/server/db.py — B13).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

# ── path bootstrap: demo/ is not a package (same pattern as operations.py) ──
_DEMO_DIR = str(Path(__file__).resolve().parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import gate      # noqa: E402  (path bootstrap above)
import legality  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_from_path(name: str, path: Path):
    """Import a single file under a stable module name, cached."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover — install defect
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: The T-1 compiler, reused AS-IS (Q19; AC-33 checksums it).  Loaded from its
#: pinned location; never copied, never edited.
_compile = _load_from_path(
    "autosql_t1_compile", _REPO_ROOT / "spikes" / "T-1" / "proto" / "compile.py"
)
#: The vendored expression parser (AC-34) — the gate reads its trees.
_expr = _load_from_path(
    "autosql_demo_expr", Path(_DEMO_DIR) / "vendor" / "expr.py"
)

compile_ast = _compile.compile_ast
Compiled = _compile.Compiled


# ═════════════════════════════════════════════════════════════════════════
# The fixed texts.  Each is a constant so tests can grep the RULE, not an
# instance of it (AC-40(e), AC-43(a), B3b).
# ═════════════════════════════════════════════════════════════════════════

#: Operation 9's compared value — R13: the whole record minus its ordering
#: key, ``data - 'ts'`` (jsonb key removal, NOT arithmetic).  A constant of
#: the builder: no part of any request reaches it (AC-40(e)).
COMPARED_EXPR = "r.data - 'ts'"

#: Operation 9's flag, exactly as B3 writes it: ``lag()`` over the shared
#: frame ``w``, compared with IS DISTINCT FROM (never ``<>`` — NULL IS
#: DISTINCT FROM x is TRUE, which is how every sender's first beat is kept).
CHANGED_SQL = (
    f'( lag( {COMPARED_EXPR} ) OVER w\n'
    f'             IS DISTINCT FROM ( {COMPARED_EXPR} ) )     AS "changed"'
)

#: The one frame operations 8 and 9 share (§7.1's window rule, R9) — written
#: once, used twice, as B3 detail 6 demands.  Both components are read out of
#: the jsonb with ``->>`` (text; byte order under the C collation).
WINDOW_DEF = (
    "WINDOW w AS (PARTITION BY (r.data ->> 'sender_id')\n"
    "               ORDER BY     (r.data ->> 'ts'), r.key)"
)

#: Operation 8's frame extent (R14: width 3, trailing, a mean).
ROLLING_FRAME = "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW"

#: Shape D's bucket label — B1's ONE emitted ``bucket`` column: the
#: fixed-width UTC ISO-8601 text label (R15).  ``date_trunc`` is the inner
#: expression; it never carries an alias of its own.  ``{g}`` is filled from
#: :data:`_GRANULARITY_SQL`'s closed set, never from user text.
_BUCKET_LABEL_TEMPLATE = (
    "to_char( date_trunc({g}, (data ->> 'ts')::timestamptz) AT TIME ZONE 'UTC',\n"
    "                'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"' )"
)

#: §4.4 row 7's closed sets, mapped to the ONLY SQL keywords ever emitted
#: for them.  legality.evaluate has already refused anything else; these
#: dicts are the emission-side half of the same fence (a KeyError here is a
#: bug upstream, and it fails closed).
_GRANULARITY_SQL = {"hour": "'hour'", "day": "'day'"}
_DIRECTION_SQL = {"asc": "ASC", "desc": "DESC"}


# ═════════════════════════════════════════════════════════════════════════
# The two §4.5 rules this file owns.
# ═════════════════════════════════════════════════════════════════════════

def numeric_read(j_sql: str) -> str:
    """§7.2 item 5 — how a number gets out of the JSON, for ops 6, 7 and 8.

    ``j_sql`` is a scalar jsonb SQL expression: either ``data #> %(...)s``
    (a bound field path) or a compiled computed-column expression re-emitted
    inline (B2).  The guard turns a non-number into NULL — which Postgres's
    ``sum``/``avg``/``min``/``max`` ignore and ``count`` does not count —
    instead of raising 22P02 and killing the pick over one bad row.

    Never routed through ``xpr.f8``/``xpr.num``: those coerce to ``float8``
    (and, since the 2026-08-23 adoption of the corrected runtime, RAISE the
    named XPR01 refusal past DBL_MAX), while operations 6, 7 and 8 stay in
    ``numeric`` end to end (AC-24(c)).
    """
    return (
        f"CASE WHEN jsonb_typeof( {j_sql} ) = 'number'\n"
        f"                        THEN ( {j_sql} #>> '{{}}' )::numeric END"
    )


#: The fixed, mechanical fragment prefixes (B11) — so the SQL pane reads
#: predictably.  ``prbA%d``/``prbB%d`` are W11's; listed so the vocabulary
#: is in one place.
PREFIX_COMPUTED = "cc"    # cc0, cc1, … in the order they were entered
PREFIX_FILTER = "flt"
PREFIX_AGGREGATE = "agg"
PREFIX_WINDOW = "win"

_PREFIX_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")
_COMPILER_BIND_RE = re.compile(r"p\d+\Z")


def namespace(frag: Compiled, prefix: str) -> tuple[str, dict]:
    """Rewrite compile.py's p0,p1,… into <prefix>_p0,… in both the SQL and the params.

    B11: ``_Compiler.__init__`` restarts ``self._n`` at 0 on every
    ``compile_ast`` call (compile.py:159-164, :437), so two fragments merged
    into one statement would both name ``p0`` and silently overwrite each
    other's values — a wrong number that runs clean.  This transform is
    applied to EVERY fragment before it may enter a statement.  It rewrites
    the compiler's OUTPUT; compile.py itself is untouched (AC-33).

    The ``ctx`` parameter needs no rewrite here: each fragment is compiled
    with ``ctx_param=f"{prefix}_ctx"``, so that name is disjoint by
    construction (and ``compile_ast`` never puts it in ``params``).
    """
    if not _PREFIX_RE.match(prefix):
        raise ValueError(
            f"fragment prefix {prefix!r} is not usable: letters and digits "
            "only, starting with a letter (the prefixes are fixed and "
            "mechanical — B11)"
        )
    sql = re.sub(r"%\((p\d+)\)s", rf"%({prefix}_\1)s", frag.sql)
    params: dict = {}
    for name, value in frag.params.items():
        if not _COMPILER_BIND_RE.match(name):
            raise ValueError(
                f"unexpected bind name {name!r} from compile_ast — the "
                "compiler names its binds p0, p1, … (compile.py:159-164); "
                "anything else here means the contract moved and this "
                "rewrite would silently miss it"
            )
        params[f"{prefix}_{name}"] = value
    return sql, params


def merge_params(into: dict, add: dict) -> None:
    """Merge one fragment's params into the statement's, refusing ANY collision.

    Prefixed fragments are disjoint by construction; a collision therefore
    means two fragments were given one prefix — exactly the silent-overwrite
    class B11 exists to stop — so it raises rather than comparing values.
    """
    for name, value in add.items():
        if name in into:
            raise ValueError(
                f"bind parameter {name!r} is already set in this statement: "
                "two fragments were namespaced with the same prefix (B11)"
            )
        into[name] = value


# ═════════════════════════════════════════════════════════════════════════
# Errors
# ═════════════════════════════════════════════════════════════════════════

class IllegalPick(ValueError):
    """A pick legality.evaluate refuses — carried with legality's own words.

    Raised here as well as in the pick handler so no statement can be built
    for an illegal pick no matter who calls (§4.5: ONE function decides;
    this class only carries its verdict).
    """

    def __init__(self, violations: list[dict]):
        self.violations = violations
        detail = "; ".join(
            f"operation {v['operation']}: {v['why']}" for v in violations
        )
        super().__init__(f"the pick is not legal — {detail}")


# ═════════════════════════════════════════════════════════════════════════
# The built statement
# ═════════════════════════════════════════════════════════════════════════

class Built(NamedTuple):
    sql: str          # the parameterised statement (what executes — AC-27)
    params: dict      # every bind value, fragment binds prefixed per B11
    shape: str        # legality.ROWS | SCALAR | BUCKET
    columns: tuple    # output column names, in SELECT order


# ── internals ────────────────────────────────────────────────────────────

def _field_path(field: str, *, what: str) -> list[str]:
    """A dotted field path → the text[] value bound to ``#>`` (AC-28)."""
    if not isinstance(field, str) or not field:
        raise gate.Refused(
            repr(field), f"{what} needs a field, and none was given"
        )
    text = field[2:] if field.startswith("$.") else field
    parts = text.split(".")
    if any(p == "" for p in parts):
        raise gate.Refused(
            field, f"`{field}` is not a usable field path for {what}"
        )
    return parts


def _compile_expression(src: str, ctx_param: str, column: str) -> Compiled:
    """parse → gate → compile, in that order, always (§4.5: the gate runs
    before compile_ast, on the parsed tree, every time)."""
    if not isinstance(src, str) or not src.strip():
        raise gate.Refused(repr(src), "an empty expression is not usable")
    try:
        ast = _expr.parse(src)
    except _expr.ExprError as exc:
        raise gate.Refused(src, f"the expression does not parse: {exc}") from exc
    gate.gate(ast)  # Refused propagates with the construct named
    try:
        return compile_ast(ast, column=column, ctx_param=ctx_param)
    except _compile.Uncompilable as exc:
        # The gate's allowlist is supposed to make this branch unreachable:
        # every tree it approves is one the pinned compiler compiles.  If
        # the two ever disagree again (the non-finite literal did exactly
        # that before the gate grew its finiteness row), the person still
        # gets a NAMED layer-1 refusal — the doctrine of spec §4.3 / plan
        # §10.1 — never a bare 500 with an empty body.
        raise gate.Refused(
            src,
            f"the expression passed the gate but the pinned compiler cannot "
            f"compile it: {exc} — this is a gap between the gate's allowlist "
            f"and the compiler, worth reporting",
        ) from exc


def _ctx_json(ctx: dict | None) -> str:
    return json.dumps(ctx or {}, separators=(",", ":"))


def _bind_ctx_values(sql: str, params: dict, ctx_value: str) -> None:
    """Supply a value for every ``<prefix>_ctx`` bind the statement uses."""
    for name in set(re.findall(r"%\((\w+_ctx)\)s", sql)):
        params.setdefault(name, ctx_value)


class _Pieces:
    """The shared prep every shape starts from."""

    def __init__(self, pick: dict, collection_keys, ctx: dict | None):
        lg = legality.evaluate(pick)
        if lg["violations"]:
            raise IllegalPick(lg["violations"])
        self.shape = lg["shape"]
        self.source = lg["source"]
        self.collection_keys = list(collection_keys)
        self.ctx_value = _ctx_json(ctx)
        self.params: dict = {"collection": self.source}
        # Shape D (B1) is written without a table alias; every other shape
        # aliases ``demo.records AS r``.  Every fragment and every emitted
        # column reference agrees with that choice FROM COMPILATION ON —
        # nothing rewrites SQL text after the fact.
        self.q = "" if self.shape == legality.BUCKET else "r."
        self.col = self.q + "data"

        # Op 2 — parse+gate+compile each computed column ONCE; validate and
        # quote each alias against the vocabulary that existed before it.
        self.cc_order: list[str] = []       # names, entry order
        self.cc_frag: dict[str, Compiled] = {}
        self.cc_quoted: dict[str, str] = {}  # name -> emit_alias() output
        for i, cc in enumerate(pick.get("computed") or []):
            name = cc.get("name")
            quoted = gate.emit_alias(name, self.collection_keys, self.cc_order)
            frag = _compile_expression(
                cc.get("expr"), ctx_param=f"cc{i}_ctx", column=self.col
            )
            self.cc_order.append(name)
            self.cc_frag[name] = frag
            self.cc_quoted[name] = quoted

        # Op 3 — the filter, namespaced flt (B11).
        self.filter_sql: str | None = None
        flt_src = pick.get("filter")
        if flt_src:
            frag = _compile_expression(
                flt_src, ctx_param="flt_ctx", column=self.col
            )
            sql, prm = namespace(frag, PREFIX_FILTER)
            merge_params(self.params, prm)
            self.filter_sql = sql

    def cc_index(self, name: str) -> int:
        return self.cc_order.index(name)

    def numeric_source(self, field: str, prefix: str, path_param: str,
                       *, what: str) -> str:
        """§7.2 item 5's `<j>`: a bound path, or a computed column's compiled
        expression re-emitted inline (B2) — never an alias, never SQL text."""
        if field in self.cc_frag:
            sql, prm = namespace(self.cc_frag[field], prefix)
            merge_params(self.params, prm)
            return sql
        path = _field_path(field, what=what)
        self.params[path_param] = path
        return f"{self.col} #> %({path_param})s"

    def where_clause(self) -> str:
        out = f" WHERE {self.q}collection = %(collection)s"
        if self.filter_sql is not None:
            out += f"\n   AND xpr.truthy( {self.filter_sql} )"
        return out

    def rolling_column(self, pick: dict, *, named_window: bool) -> str:
        """Op 8's SELECT-list entry (R14: width 3, trailing, a mean).

        The ``round(…, 6)`` around the window ``avg`` is §7.2 item 2 —
        every division is followed immediately by a half-up round to 6
        places — applied through §4.5's rule table, whose exact-decimal row
        covers ops 6, 7 AND 8 on both panes.  Plan §4.2's shape-A fence
        (and B3's) write the ``avg`` bare, which contradicts the plan's own
        §4.5 row and would make AC-24(a)'s digit-for-digit agreement
        unsatisfiable (``avg`` of ``numeric`` returns scale-16 text beside
        the Python pane's q6).  Recorded as a W10 ruling in the build
        report."""
        field = (pick.get("window") or {}).get("field")
        j = self.numeric_source(
            field, PREFIX_WINDOW, "win_path", what="the rolling window"
        )
        if named_window:
            over = f"OVER (w {ROLLING_FRAME})"
        else:
            over = (
                "OVER (PARTITION BY (r.data ->> 'sender_id')\n"
                "               ORDER BY     (r.data ->> 'ts'), r.key\n"
                f"               {ROLLING_FRAME})"
            )
        return (
            f'round( avg( {numeric_read(j)} )\n'
            f'         {over}, 6)  AS "rolling_avg"'
        )

    def order_by(self, pick: dict, *, qualify: str) -> str:
        """§7.4 — the total order every multi-row result carries; the last
        component is always ``key ASC`` (AC-41(a)), the tiebreak ascending
        whichever way the sort field runs (§7.4(1a))."""
        q = qualify  # "r." inside single-level statements, "" over the CTE
        sort = pick.get("sort") or None
        if not (sort and sort.get("field")):
            return f" ORDER BY {q}key ASC"
        direction = _DIRECTION_SQL[sort["dir"]]  # closed set; refused upstream
        field = sort["field"]
        if field in self.cc_order:
            # §4.4 row 6: an ORDER BY alias reference is legal and stays.
            lead = f"{self.cc_quoted[field]} {direction} NULLS LAST"
        else:
            self.params["sort_path"] = _field_path(field, what="the sort")
            lead = f"( {q}data #> %(sort_path)s ) {direction} NULLS LAST"
        return f" ORDER BY {lead}, {q}key ASC"

    def limit(self, pick: dict) -> str:
        if pick.get("cap") is None:
            return ""
        self.params["cap"] = pick["cap"]
        return "\n LIMIT %(cap)s"

    def aggregate_call(self, pick: dict) -> str:
        """Op 6's one emitted value (shapes C and D): the chosen function
        over the numeric read, in ``numeric`` end to end (§7.2, AC-24(c)).
        ``sum``/``avg`` are rounded half-up to 6 places; ``min``/``max``
        take no round; ``count`` is the exception — it counts rows and
        takes no field (legality refuses a count that carries one)."""
        fn = (pick.get("aggregate") or {}).get("fn")
        if fn == "count":
            return "count(*)"
        field = (pick.get("aggregate") or {}).get("field")
        j = self.numeric_source(
            field, PREFIX_AGGREGATE, "agg_path", what="the aggregate"
        )
        body = f"{fn}( {numeric_read(j)} )"
        if fn in ("sum", "avg"):
            return f"round( {body}, 6)"
        return body  # min / max


# ── the four shapes ──────────────────────────────────────────────────────

def _shape_rows(p: _Pieces, pick: dict) -> Built:
    """Shape A — ROWS, no operation 9 (plan §4.2).  No CTE: a window
    function in the SELECT list needs no wrapping."""
    select = ["r.collection", "r.key", "r.data"]
    columns = ["collection", "key", "data"]
    for name in p.cc_order:
        sql, prm = namespace(p.cc_frag[name], f"cc{p.cc_index(name)}")
        merge_params(p.params, prm)
        select.append(f"{sql}  AS {p.cc_quoted[name]}")
        columns.append(name)
    if pick.get("window"):
        select.append(p.rolling_column(pick, named_window=False))
        columns.append("rolling_avg")

    sql = (
        "SELECT " + ",\n       ".join(select) + "\n"
        "  FROM demo.records AS r\n"
        + p.where_clause() + "\n"
        + p.order_by(pick, qualify="r.")
        + p.limit(pick) + ";"
    )
    return Built(sql, p.params, legality.ROWS, tuple(columns))


def _shape_rows_changed(p: _Pieces, pick: dict) -> Built:
    """Shape B — ROWS with operation 9: B3's CTE, written out in full there.

    The six pinned details: (1) ``WHERE "changed"`` is legal because the CTE
    made it a column; (2) never NULL, so no IS TRUE; (3) ``changed`` is NOT
    emitted by the outer SELECT; (4) the filter is INSIDE the CTE, so the
    window sees only surviving rows; (5) LIMIT is OUTSIDE, capping kept
    rows; (6) ``WINDOW w`` is written once and used by ops 8 and 9 alike.
    """
    inner = ["r.collection", "r.key", "r.data"]
    outer = ["collection", "key", "data"]
    for name in p.cc_order:
        sql, prm = namespace(p.cc_frag[name], f"cc{p.cc_index(name)}")
        merge_params(p.params, prm)
        inner.append(f"{sql}  AS {p.cc_quoted[name]}")
        outer.append(p.cc_quoted[name])
    if pick.get("window"):
        inner.append(p.rolling_column(pick, named_window=True))
        outer.append('"rolling_avg"')
    inner.append(CHANGED_SQL)

    columns = [c.strip('"') for c in outer]
    sql = (
        "WITH picked AS (\n"
        "  SELECT " + ",\n         ".join(inner) + "\n"
        "    FROM demo.records AS r\n"
        "  " + p.where_clause().replace("\n   ", "\n     ") + "\n"
        "  " + WINDOW_DEF + "\n"
        ")\n"
        "SELECT " + ", ".join(outer) + "\n"
        "  FROM picked\n"
        ' WHERE "changed"\n'
        + p.order_by(pick, qualify="")
        + p.limit(pick) + ";"
    )
    return Built(sql, p.params, legality.ROWS, tuple(columns))


def _shape_scalar(p: _Pieces, pick: dict) -> Built:
    """Shape C — SCALAR (plan §4.2).  One row: no ORDER BY, no LIMIT
    (legality disables ops 4 and 5).  Computed columns are defined, not
    emitted — B2 removed the 42703 by construction."""
    sql = (
        f'SELECT {p.aggregate_call(pick)}  AS "agg"\n'
        "  FROM demo.records AS r\n"
        + p.where_clause() + ";"
    )
    return Built(sql, p.params, legality.SCALAR, ("agg",))


def _shape_bucket(p: _Pieces, pick: dict) -> Built:
    """Shape D — BUCKET: B1's statement, exactly.  ONE emitted ``bucket``
    column — the text label — so ``ORDER BY "bucket"`` cannot be ambiguous;
    text order on the fixed-width UTC label IS time order (R15, C collation).
    B1 writes this shape without a table alias; the shared pieces compiled
    every fragment unqualified for it (``_Pieces.col``)."""
    label = _BUCKET_LABEL_TEMPLATE.format(g=_GRANULARITY_SQL[pick["bucket"]])
    agg = p.aggregate_call(pick)
    where = p.where_clause()
    sql = (
        f'SELECT {label}                      AS "bucket",\n'
        f'       {agg}             AS "agg"\n'
        "  FROM demo.records\n"
        + where + "\n"
        ' GROUP BY "bucket"\n'
        ' ORDER BY "bucket"'
        + p.limit(pick) + ";"
    )
    return Built(sql, p.params, legality.BUCKET, ("bucket", "agg"))


# ── THE entry point ──────────────────────────────────────────────────────

def build(pick: dict, collection_keys, *, ctx: dict | None = None) -> Built:
    """One pick → one parameterised statement (plan §4.2's four shapes).

    ``collection_keys`` is the chosen collection's top-level JSON field
    names, computed ON THE SERVER at operation 1 (§4.4) — required, never
    defaulted, so an emission site cannot validate an alias against nothing.

    ``ctx`` is the expression context handed to ``xpr``-compiled fragments
    that read it (``now()``/``today()``); defaults to ``{}``.

    Raises :class:`gate.Refused` (a construct, an alias, an expression) or
    :class:`IllegalPick` (a combination legality.evaluate refuses).  A
    refusal always happens BEFORE any SQL exists for the offending part.
    """
    p = _Pieces(pick, collection_keys, ctx)
    if p.shape == legality.BUCKET:
        built = _shape_bucket(p, pick)
    elif p.shape == legality.SCALAR:
        built = _shape_scalar(p, pick)
    elif pick.get("changed"):
        built = _shape_rows_changed(p, pick)
    else:
        built = _shape_rows(p, pick)
    _bind_ctx_values(built.sql, built.params, p.ctx_value)
    return built
