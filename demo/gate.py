"""Layer 1 -- the static gate.  (spec §4.4, §4.10, ruling R10; plan §4.4, §4.5)

THE SAFETY-CRITICAL FILE.  `compile.py` is reused as-is (R3) and implements all 22
builtins and `%`; this file is the only thing standing between the demo and the
fifteen out-of-subset functions the compiler will otherwise happily compile.

Two jobs, one file, per plan §4.5 ("one place per rule"):

  * ``gate(ast)``           -- the 32-construct allowlist over the 12 AST tags.
                               Called on every expression the person types (op 2's
                               computed columns, op 3's filter), BEFORE compile_ast.
                               Returns quietly or raises ``Refused(construct, why)``.
  * ``validate_alias(...)`` -- §4.10's allowlist for the computed-column alias, the
                               one piece of user-typed text that reaches SQL text.
                               Run at every emission site, on the same string.

Both fail closed: anything not on an allowlist -- including any malformed or
never-seen node shape -- is refused, by name, before any SQL exists.  No refusal
message here ever reads "invalid input" (plan §10.1).

This module imports nothing but the standard library ``re``.  In particular it
does not import the compiler or the vendored ``expr.py``: the gate reads parsed
trees, it never parses and never compiles.
"""

from __future__ import annotations

import re

__all__ = [
    "Refused",
    "gate",
    "validate_alias",
    "emit_alias",
    "ALLOWED_TAGS",
    "ALLOWED_BIN_OPS",
    "ALLOWED_CMP_OPS",
    "ALLOWED_FUNCTIONS",
    "OUT_OF_SUBSET_FUNCTIONS",
    "MAX_INDEX_EXCLUSIVE",
    "ALIAS_RE",
    "TABLE_COLUMNS",
    "BUILDER_COLUMNS",
]


class Refused(Exception):
    """A layer-1 refusal: the pick is declined before any SQL exists.

    ``construct`` is the construct or name that was refused (e.g. ``"round"``,
    ``"%"``, an alias); ``why`` is the rule it broke, in words a person reads on
    screen (§9.3 renders it).  The message always names one or the other --
    a bare "invalid" is a defect (plan §10.1).
    """

    def __init__(self, construct: str, why: str):
        self.construct = construct
        self.why = why
        super().__init__(why)


# ---------------------------------------------------------------------------------
# The subset, exactly (spec §4.2) -- these five allowlists ARE the definition,
# executed.  Do not add a name here without a ruling: an accidental extra entry
# is invisible in review and is exactly how an unchecked construct ships
# (plan §9 risk 8).
# ---------------------------------------------------------------------------------

#: The twelve tags compile.py dispatches on (spec §4.4 -- twelve, NOT the ten
#: leaf/structural constructs; `cmp` and `bin` are accepted AS TAGS and then
#: confined by their operator rows below.  A ten-tag gate refuses every
#: comparison and every piece of arithmetic in the demo -- mutant M12).
ALLOWED_TAGS = frozenset(
    {"num", "str", "bool", "null", "field", "neg", "not", "and", "or", "cmp", "bin", "call"}
)

#: 4 of the 5 arithmetic operators.  This row, not the tag row, is what refuses `%`.
ALLOWED_BIN_OPS = frozenset({"+", "-", "*", "/"})

#: All 6 comparisons.  The ==/!= container qualifier is a ROW property and is
#: deliberately NOT decided here -- it is layer 2's (spec §4.3, §4.6).
ALLOWED_CMP_OPS = frozenset({"==", "!=", "<", "<=", ">", ">="})

#: 7 of the 22 builtins.
ALLOWED_FUNCTIONS = frozenset({"abs", "coalesce", "count", "if", "length", "max", "min"})

#: The other 15 builtins compile.py implements.  Listed ONLY so their refusal can
#: say "outside the safe subset" rather than "unknown"; membership here grants
#: nothing.  A 23rd function GIMS grows later is on neither list and is refused
#: all the same -- the allowlist fails closed.
OUT_OF_SUBSET_FUNCTIONS = frozenset(
    {
        "round", "floor", "ceil",            # rounding
        "sum", "avg",                        # aggregates
        "string", "number",                  # conversion
        "concat", "contains", "lower", "upper",  # string
        "today", "now", "days_between", "date_add",  # date
    }
)

#: A literal array index must satisfy |index| < 2**31 (spec §4.2, §4.4).  Exact,
#: both directions, no tolerance: 2147483647 passes, 2147483648 is refused;
#: -2147483647 passes, -2147483648 is refused.
MAX_INDEX_EXCLUSIVE = 2 ** 31

_ALLOWED_FN_WORDS = "abs, coalesce, count, if, length, max, min"


def _refuse_malformed(found: object) -> Refused:
    """A node shape the parser can never produce.  Fails closed, naming what was found."""
    return Refused(
        repr(found),
        f"not a well-formed expression node: {found!r} -- the demo gates only trees "
        f"produced by the expression parser, and this is not one",
    )


def gate(ast: object) -> None:
    """Walk the parsed expression tree; return quietly or raise ``Refused``.

    The walk is iterative (an explicit stack, left-to-right depth-first), so a
    hostile or absurdly deep tree exhausts nothing and the first offending
    construct in reading order is the one named.
    """
    stack = [ast]
    while stack:
        node = stack.pop()

        # -- shape: every node is a non-empty tuple whose tag is a string -------
        if not isinstance(node, tuple) or not node:
            raise _refuse_malformed(node)
        tag = node[0]
        if not isinstance(tag, str):
            raise _refuse_malformed(node)

        # -- the tag row: one of the twelve, else refused by name ---------------
        if tag not in ALLOWED_TAGS:
            raise Refused(
                tag,
                f"`{tag}` is not a construct this demo's expression language has: "
                f"the twelve compilable kinds of node are num, str, bool, null, "
                f"field, neg, not, and, or, cmp, bin, call",
            )

        # -- per-tag structure and the confining rows ---------------------------
        if tag == "num":
            if len(node) != 2 or isinstance(node[1], bool) or not isinstance(node[1], (int, float)):
                raise _refuse_malformed(node)
            # Finiteness is part of the allowlist.  The parser reads "1e400"
            # as float('inf') (expr.py:193), which passes the type row above
            # but which the pinned compiler cannot compile (_t_num raises
            # Uncompilable: jsonb has no representation for inf/nan) — and a
            # refusal that happens at compile time instead of here escapes
            # as a bare 500 with no construct named, which plan §10.1 calls
            # worse than a bare "invalid".  The field row already pre-empts
            # its compile-time failure (|index| < 2**31); this row does the
            # same for its own.  An int is checked through float() because
            # that is literally what _t_num will do to it, and an int above
            # the largest double raises OverflowError there rather than
            # Uncompilable — same escape, same fence.
            # (No ``math`` here — the gate imports nothing but ``re``, and
            # test_gate.py pins that.  ``nan != nan`` and the two infinities
            # are the only non-finite doubles there are.)
            value = node[1]
            try:
                as_double = float(value)
                finite = (as_double == as_double
                          and as_double != float("inf")
                          and as_double != float("-inf"))
            except OverflowError:
                finite = False
            if not finite:
                raise Refused(
                    repr(value),
                    f"the numeric literal reads as {value!r}, which is not a "
                    f"finite number this demo can compile: a JSON number "
                    f"becomes a double, the largest double is about "
                    f"1.7976931348623157e+308, and anything past that has no "
                    f"honest value to compute with",
                )

        elif tag == "str":
            if len(node) != 2 or not isinstance(node[1], str):
                raise _refuse_malformed(node)

        elif tag == "bool":
            if len(node) != 2 or not isinstance(node[1], bool):
                raise _refuse_malformed(node)

        elif tag == "null":
            if len(node) != 1:
                raise _refuse_malformed(node)

        elif tag == "field":
            if len(node) != 2 or not isinstance(node[1], list):
                raise _refuse_malformed(node)
            for step in node[1]:
                if not isinstance(step, tuple) or len(step) != 2:
                    raise _refuse_malformed(step)
                kind, key = step
                if kind == "key":
                    if not isinstance(key, str):
                        raise _refuse_malformed(step)
                elif kind == "index":
                    if isinstance(key, bool) or not isinstance(key, int):
                        raise _refuse_malformed(step)
                    if not (abs(key) < MAX_INDEX_EXCLUSIVE):
                        raise Refused(
                            f"[{key}]",
                            f"the array index {key} is outside the compilable range: "
                            f"a literal array index must satisfy |index| < 2**31",
                        )
                else:
                    raise Refused(
                        str(kind),
                        f"`{kind}` is not a field-path step this demo's expression "
                        f"language has: the five forms are the bare $, .name, "
                        f'["quoted"], [n] and [-n]',
                    )

        elif tag in ("neg", "not"):
            if len(node) != 2:
                raise _refuse_malformed(node)
            stack.append(node[1])

        elif tag in ("and", "or"):
            if len(node) != 3:
                raise _refuse_malformed(node)
            stack.append(node[2])  # pushed right-then-left so the LEFT operand
            stack.append(node[1])  # is examined first (first offender in reading order)

        elif tag == "cmp":
            if len(node) != 4 or not isinstance(node[1], str):
                raise _refuse_malformed(node)
            op = node[1]
            if op not in ALLOWED_CMP_OPS:
                raise Refused(
                    op,
                    f"`{op}` is not a comparison this demo compiles: "
                    f"the six are == != < <= > >=",
                )
            stack.append(node[3])
            stack.append(node[2])

        elif tag == "bin":
            if len(node) != 4 or not isinstance(node[1], str):
                raise _refuse_malformed(node)
            op = node[1]
            if op not in ALLOWED_BIN_OPS:
                if op == "%":
                    # A construct the language HAS, excluded by Q18's subset.
                    raise Refused(
                        "%",
                        "`%` is outside the safe subset -- the only arithmetic "
                        "this demo compiles is + - * /",
                    )
                raise Refused(
                    op,
                    f"`{op}` is not an arithmetic operator this demo compiles: "
                    f"the four are + - * /",
                )
            stack.append(node[3])
            stack.append(node[2])

        else:  # tag == "call" -- the only tag left; ALLOWED_TAGS is exhausted above
            if len(node) != 3 or not isinstance(node[1], str) or not isinstance(node[2], list):
                raise _refuse_malformed(node)
            name = node[1]
            if name not in ALLOWED_FUNCTIONS:
                if name in OUT_OF_SUBSET_FUNCTIONS:
                    # Walkthrough step 10 reads exactly this shape:
                    # "`round` is outside the safe subset ...", never "invalid expression".
                    raise Refused(
                        name,
                        f"`{name}` is outside the safe subset -- the only functions "
                        f"this demo compiles are {_ALLOWED_FN_WORDS}",
                    )
                raise Refused(
                    name,
                    f"`{name}` is not a function this demo compiles: "
                    f"the only functions it compiles are {_ALLOWED_FN_WORDS}",
                )
            for arg in reversed(node[2]):
                stack.append(arg)

    return None


# ---------------------------------------------------------------------------------
# §4.10 -- the computed-column alias, the one place user-typed text reaches SQL
# text (SQL has no bind-parameter position for a column name).  Ruling R10.
# ---------------------------------------------------------------------------------

#: The pattern, exactly as R10 pins it.  ASCII letters, digits, underscore;
#: starts with a letter or underscore; 1 to 63 characters (Postgres's own
#: NAMEDATALEN - 1 -- anything longer the server silently TRUNCATES, collapsing
#: two aliases into one column, so refusing is the honest answer).
ALIAS_RE = r"[A-Za-z_][A-Za-z0-9_]{0,62}"

_ALIAS_RULE = (
    "letters, digits and underscore only, starting with a letter or underscore, "
    "at most 63 characters"
)

#: Collision group 1 -- the demo table's own columns (spec §8.2).
TABLE_COLUMNS = frozenset({"collection", "key", "data"})

#: Collision group 2 -- the four column names the demo's own query builder emits,
#: pinned by exactly these names in spec §7.3 / R8 (including `changed`, which
#: under B3 lives inside the CTE and collides just as fatally there).
BUILDER_COLUMNS = frozenset({"agg", "bucket", "rolling_avg", "changed"})


def validate_alias(name, collection_keys, pick_aliases) -> str:
    """§4.10's allowlist.  Returns ``name`` unchanged, or raises ``Refused``.

    ``collection_keys``: the chosen collection's top-level JSON field names --
    computed ON THE SERVER at operation 1 (``SELECT DISTINCT k FROM demo.records,
    LATERAL jsonb_object_keys(data) AS k WHERE collection = %(collection)s``) and
    handed to both panes, so the identical check runs on the identical string.
    ``pick_aliases``: the aliases already defined in this pick.

    Both are required, not defaulted: an emission site that forgets a vocabulary
    must fail loudly, not validate against nothing.  Every emission site --
    SELECT, ORDER BY, GROUP BY, the aggregate -- calls this same function on the
    same string; none re-implements the rule (plan §4.5).
    """
    if not isinstance(name, str):
        raise Refused(
            repr(name),
            f"{name!r} is not a usable column name: a column name is text -- {_ALIAS_RULE}",
        )

    # The pattern first: keys that could never be aliases (a quote, 64+ chars)
    # are refused here before any list is consulted (§4.10).
    # fullmatch, NOT match -- match anchors only the start, and
    # `alive"; DROP TABLE demo.records; --` would pass it (mutant M13).
    if re.fullmatch(ALIAS_RE, name) is None:
        if name == "":
            raise Refused(
                name,
                f"an empty column name is not usable: a name needs at least one "
                f"character -- {_ALIAS_RULE}",
            )
        raise Refused(name, f"`{name}` is not a usable column name: {_ALIAS_RULE}")

    # Collision group 1 -- the table's own columns.
    if name in TABLE_COLUMNS:
        raise Refused(
            name,
            f"`{name}` is already a column of the demo's own table "
            f"(collection, key, data) -- pick a different name",
        )

    # Collision group 2 -- the names the query builder itself emits.
    if name in BUILDER_COLUMNS:
        raise Refused(
            name,
            f"`{name}` is a column name the demo's query builder emits itself "
            f"(agg, bucket, rolling_avg, changed) -- pick a different name",
        )

    # Collision group 3 -- the source collection's own top-level field names,
    # read from the data (spec §4.10; AC-45 tests that they really come from it).
    if name in set(collection_keys):
        raise Refused(
            name,
            f"`{name}` is already a top-level field name of the chosen collection "
            f"-- pick a different name",
        )

    # Collision group 4 -- an alias already defined in this pick.
    if name in set(pick_aliases):
        raise Refused(
            name,
            f"`{name}` is already defined as a computed column in this pick "
            f"-- pick a different name",
        )

    return name


def emit_alias(name, collection_keys, pick_aliases) -> str:
    """Validate, then double-quote for emission: ``alive`` -> ``"alive"``.

    The quoting is applied AFTER the check, never instead of it (§4.10).  No
    escaping is performed and none is needed: the pattern admits no quote, no
    space, no `%`, nothing outside ASCII word characters.
    """
    validate_alias(name, collection_keys, pick_aliases)
    return '"' + name + '"'
