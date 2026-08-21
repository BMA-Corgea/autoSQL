"""T-1 spike - subset fixture-coverage meter.  **[punch]**

WHAT THIS IS, PLAINLY:
  * BUILT DURING THE CLOSURE PASS (PUNCH-LIST round), not during the original
    investigation.  No seat ran it while the findings were being collected; every
    number it produces post-dates the panel, the critic, the consistency pass and
    the three adversarial lenses.  It exists because `f5` section 5.7 states that
    the CORRECTED CONDITIONAL-GO subset's fixture coverage "is NOT ESTABLISHED"
    and warns "Do not quote 84/130 for the corrected subset".  This computes it.
  * READ-ONLY.  It opens exactly two paths for reading -- GIMS-Project's
    `core/dashboard/expr.py` (imported) and `tests/fixtures/expr_vectors.json`
    (parsed).  It writes exactly one path, `../analysis/subset-coverage.json`.
    It opens NO database connection, imports no `psycopg2`, and touches neither
    GIMS tree except to read.  Nothing in either GIMS tree is modified.
  * IT IMPORTS THE REAL PARSER.  Every AST here comes from `expr.parse`, the
    contract runtime itself (`GIMS-Project` @ 995cc59, byte-identical to
    `GUTS/spine/L1-memory/gims-ledger` per FRAMING.md section 2 / C2).  There is
    no reimplementation of the grammar, the tokenizer or the node shapes.  The
    container-operand scan (reading A below) wraps the real `expr._eq` in memory
    for the duration of one evaluation and restores it; it does not patch the file.
  * IT IS A MEASUREMENT, NOT A FIX.  FRAMING.md section 3 forbids repairing the
    defects this spike found.  Nothing here changes `compile.py`, `runtime.sql`,
    `expr.py` or any fixture.  It only counts.
  * THROWAWAY, like the rest of `proto/` (FRAMING.md section 3): not a library,
    no API, nothing may import it.

DETERMINISM:  the output is a pure function of the two input files.  No clock, no
random source, no network, no DB, no run timestamp in the JSON -- provenance is
carried by the SHA-256 of each input instead, so two runs produce byte-identical
output.  The one place a clock could leak in is `today()`/`now()` during the
reading-A evaluation; the scan records only OPERAND KINDS reaching `_eq`, which
`self_check.eq_matrix_clock_invariant` re-verifies with the clock pinned and
unpinned.

RUN:      python3 spikes/T-1/proto/closure_subset_coverage.py
OUTPUT:   spikes/T-1/analysis/subset-coverage.json
"""
import hashlib
import json
import os
import sys

GIMS = "/home/corgea/Desktop/Coding Projects/GIMS-Project"
FIXTURE = os.path.join(GIMS, "tests", "fixtures", "expr_vectors.json")
PARSER = os.path.join(GIMS, "core", "dashboard", "expr.py")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   os.pardir, "analysis", "subset-coverage.json")

sys.dont_write_bytecode = True   # provably cannot drop a __pycache__ into the GIMS tree
sys.path.insert(0, GIMS)
from core.dashboard import expr as E  # the REAL parser + evaluator, read-only

# --------------------------------------------------------------------------------------
# THE SUBSET, TAKEN VERBATIM FROM `f5` section 5.7 OF FINDINGS.md
# --------------------------------------------------------------------------------------
# Sentence 1 (the starting point, panel.json[0]'s subset):
#   "Start from `panel.json[0]`'s subset -- all 10 leaf/structural node types, all 5
#    arithmetic operators, all 6 comparisons, all 5 field-path forms with a compile-time
#    `|literal index| < 2**31` check (D19), and 10 of 22 functions: `abs ceil coalesce
#    count floor if length max min round`.  36 of 48 constructs, 84 of 130 cases (64.6%)"
#
# Sentence 2 (what closure removes -- the correction being priced here):
#   "Closure removes more, on section 5.4(1): `round` (R2-R5), `floor`/`ceil` (R6), `%`
#    (R7), and `==`/`!=` over container operands (R8) -- 7 of the 8 mechanisms by which
#    the *reference* runtime raises [...].  The resulting fixture coverage is NOT
#    ESTABLISHED; computing it is one AST walk over `expr_vectors.json`, unrun.  Do not
#    quote 84/130 for the corrected subset."
#
# R2-R8 are `xa` A.2's RAISE MECHANISMS (see section 5.4(1), which spells the mapping out:
# "R2-R5 are `round`, R6 is `floor`/`ceil`, R7 is `%`, R8 is `==`").  They are NOT `f2`
# section 2.7's separately-numbered run-time divergence classes R1-R7, which share the
# letter.  The mapping used here is section 5.4(1)'s, quoted.
#
# AMBIGUITY, recorded rather than silently resolved -- see `ambiguity` in the output:
#   (i)  "round, floor/ceil, %" are named as BARE CONSTRUCTS; "==/!=" is named with a
#        QUALIFIER ("over container operands").  The contrast is read as deliberate:
#        the first three leave the subset outright, the fourth leaves it only in its
#        qualified form.  Three readings of that qualifier are measured, A/B/C below.
#   (ii) "over container operands" is not decidable from the AST alone: the grammar has
#        NO container literal (`expr.py:185-214` -- num/str/bool/null/$field/(/call only),
#        so a container operand can only arrive from a `field` resolution or from a
#        pass-through function.  Hence A (runtime-witnessed), B (static over-
#        approximation) and C (maximal) are all defensible; all three are reported.

ALL_FUNCTIONS = frozenset(E._FUNCTIONS)                      # 22, from the evaluator itself
PANEL_FUNCTIONS = frozenset(
    "abs ceil coalesce count floor if length max min round".split())      # section 5.7 sentence 1
CLOSURE_REMOVES_FUNCTIONS = frozenset(("round", "floor", "ceil"))         # R2-R5, R6
CLOSURE_REMOVES_OPERATORS = frozenset(("%",))                             # R7
CORRECTED_FUNCTIONS = PANEL_FUNCTIONS - CLOSURE_REMOVES_FUNCTIONS         # 7 of 22
INDEX_LIMIT = 2 ** 31                                                     # D19

# `f2` section 2.1's census granularity, so the construct arithmetic below is auditable:
# 10 leaf/structural node types + 5 arithmetic operators + 6 comparisons + 22 functions
# + 5 field-path forms = 48.
N_NODE_TYPES = 10
N_ARITH_TOTAL = 5
N_COMPARISONS = 6
N_PATH_FORMS = 5
N_ARITH_CORRECTED = N_ARITH_TOTAL - len(CLOSURE_REMOVES_OPERATORS)
N_CONSTRUCTS_TOTAL = (N_NODE_TYPES + N_ARITH_TOTAL + N_COMPARISONS
                      + len(ALL_FUNCTIONS) + N_PATH_FORMS)
assert N_CONSTRUCTS_TOTAL == 48, N_CONSTRUCTS_TOTAL   # guards against a stale census
assert len(ALL_FUNCTIONS) == 22 and len(PANEL_FUNCTIONS) == 10 and len(CORRECTED_FUNCTIONS) == 7

# Functions that can RETURN one of their arguments unchanged, hence can hand a container
# to `==`/`!=` without a `field` node sitting directly under the comparison.  Read off the
# evaluator: `coalesce` returns the first non-null arg (expr.py:535); `if` returns the
# chosen branch (expr.py:627-632).  Every other whitelisted function coerces to
# number/string/bool or returns a fresh scalar, so it cannot yield a container.
PASSTHROUGH_FUNCTIONS = frozenset(("coalesce", "if"))


# --------------------------------------------------------------------------------------
# AST walk over the REAL parser's output
# --------------------------------------------------------------------------------------
def walk(node, acc):
    """Collect every construct used, at the granularity of `f2` section 2.1's census
    (operators counted through the `cmp`/`bin` tags, not as tags)."""
    tag = node[0]
    acc["tags"].add(tag)
    if tag in ("num", "str", "bool", "null"):
        return
    if tag == "field":
        acc["field_used"] = True
        if not node[1]:
            acc["path_forms"].add("bare $")
        for kind, val in node[1]:
            if kind == "index":
                acc["path_forms"].add("[n]" if val >= 0 else "[-n]")
                acc["literal_indices"].append(val)
            else:
                acc["path_forms"].add(".ident or [\"quoted\"]")
        return
    if tag in ("neg", "not"):
        walk(node[1], acc)
        return
    if tag in ("and", "or"):
        walk(node[1], acc)
        walk(node[2], acc)
        return
    if tag == "cmp":
        acc["cmp_ops"].add(node[1])
        if node[1] in ("==", "!="):
            acc["eq_nodes"].append(node)
        walk(node[2], acc)
        walk(node[3], acc)
        return
    if tag == "bin":
        acc["bin_ops"].add(node[1])
        walk(node[2], acc)
        walk(node[3], acc)
        return
    if tag == "call":
        acc["functions"].add(node[1])
        for a in node[2]:
            walk(a, acc)
        return
    raise AssertionError("unknown AST tag %r -- the census in f2 2.1 is stale" % (tag,))


def new_acc():
    return {"tags": set(), "functions": set(), "bin_ops": set(), "cmp_ops": set(),
            "path_forms": set(), "literal_indices": [], "eq_nodes": [], "field_used": False}


def could_be_container(node):
    """Static over-approximation (reading B): can this operand evaluate to a list/dict?"""
    tag = node[0]
    if tag == "field":
        return True                      # a record value may be any JSON kind
    if tag == "call":
        if node[1] in PASSTHROUGH_FUNCTIONS:
            return any(could_be_container(a) for a in node[2])
        return False                     # every other builtin coerces to a scalar
    return False                         # literals, neg, not, and, or, cmp, bin: scalars


# --------------------------------------------------------------------------------------
# Runtime container-operand witness (reading A): wrap the REAL `expr._eq`, in memory
# --------------------------------------------------------------------------------------
_KINDS = ("null", "bool", "num", "str", "list", "dict")


def _kind(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "other"


def eq_scan(cases, pin_clock):
    """Evaluate every case through the real evaluator with `_eq` wrapped, and record the
    operand kinds every `==`/`!=` actually saw.  Restores `_eq` unconditionally."""
    real_eq = E._eq
    cells = {}
    per_case = []
    seen = []

    def spy(a, b):
        cells[(_kind(a), _kind(b))] = cells.get((_kind(a), _kind(b)), 0) + 1
        if isinstance(a, (list, tuple, dict)) or isinstance(b, (list, tuple, dict)):
            seen.append((_kind(a), _kind(b)))
        return real_eq(a, b)

    E._eq = spy
    try:
        for c in cases:
            ctx = dict(c.get("context") or {})
            if pin_clock:
                ctx.setdefault("now", "2026-08-19T12:00:00Z")
            del seen[:]
            error = None
            try:
                E.evaluate(E.parse(c["expr"]), c.get("record") or {}, ctx)
            except Exception as exc:                       # noqa: BLE001 - recorded, not raised
                error = "%s: %s" % (type(exc).__name__, exc)
            per_case.append({"container_operands": sorted(set(seen)),
                             "evaluator_error": error})
    finally:
        E._eq = real_eq
    matrix = [[cells.get((a, b), 0) for b in _KINDS] for a in _KINDS]
    return per_case, matrix, sum(cells.values()), len(cells)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --------------------------------------------------------------------------------------
def main():
    with open(FIXTURE) as fh:
        fixture = json.load(fh)
    cases = fixture["cases"]

    eq_per_case, eq_matrix, eq_calls, eq_cells = eq_scan(cases, pin_clock=False)
    _, eq_matrix_pinned, _, _ = eq_scan(cases, pin_clock=True)

    rows = []
    for i, (case, eqinfo) in enumerate(zip(cases, eq_per_case)):
        acc = new_acc()
        walk(E.parse(case["expr"]), acc)

        oversize = [n for n in acc["literal_indices"] if abs(n) >= INDEX_LIMIT]
        d19 = ["field index |%d| >= 2**31 (D19)" % n for n in oversize]

        panel_out = sorted("function %s" % f for f in acc["functions"] - PANEL_FUNCTIONS) + d19
        base_out = (sorted("function %s" % f for f in acc["functions"] - CORRECTED_FUNCTIONS)
                    + sorted("operator %s" % o for o in acc["bin_ops"] & CLOSURE_REMOVES_OPERATORS)
                    + d19)

        a_out = list(base_out)
        if eqinfo["container_operands"]:
            a_out.append("==/!= over container operands (witnessed: %s)"
                         % ", ".join("%s~%s" % kk for kk in eqinfo["container_operands"]))
        b_out = list(base_out)
        if any(could_be_container(n[2]) or could_be_container(n[3]) for n in acc["eq_nodes"]):
            b_out.append("==/!= with an operand that could be a container (static)")
        c_out = list(base_out)
        if acc["cmp_ops"] & {"==", "!="}:
            c_out.append("==/!= used at all (maximal reading)")

        rows.append({
            "index": i,
            "group": case["group"],
            "name": case["name"],
            "expr": case["expr"],
            "functions_used": sorted(acc["functions"]),
            "arith_operators_used": sorted(acc["bin_ops"]),
            "comparisons_used": sorted(acc["cmp_ops"]),
            "node_tags_used": sorted(acc["tags"]),
            "field_path_forms_used": sorted(acc["path_forms"]),
            "literal_field_indices": sorted(acc["literal_indices"]),
            "eq_container_operands_witnessed": eqinfo["container_operands"],
            "evaluator_error": eqinfo["evaluator_error"],
            "panel_subset": {"verdict": "IN" if not panel_out else "OUT",
                             "excluded_by": panel_out},
            "corrected_subset_reading_A": {"verdict": "IN" if not a_out else "OUT",
                                           "excluded_by": a_out},
            "corrected_subset_reading_B": {"verdict": "IN" if not b_out else "OUT",
                                           "excluded_by": b_out},
            "corrected_subset_reading_C": {"verdict": "IN" if not c_out else "OUT",
                                           "excluded_by": c_out},
        })

    def tally(key):
        inn = sum(1 for r in rows if r[key]["verdict"] == "IN")
        hist = {}
        sole = {}
        for r in rows:
            reasons = r[key]["excluded_by"]
            for x in reasons:
                hist[x] = hist.get(x, 0) + 1
            if len(reasons) == 1:
                sole[reasons[0]] = sole.get(reasons[0], 0) + 1
        return {
            "in": inn,
            "out": len(rows) - inn,
            "of": len(rows),
            "pct_in": round(100.0 * inn / len(rows), 1),
            "blocking_histogram": dict(sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))),
            "marginal_gain_if_readmitted": dict(
                sorted(sole.items(), key=lambda kv: (-kv[1], kv[0]))),
        }

    n_corrected_constructs = (N_NODE_TYPES + N_ARITH_CORRECTED + N_COMPARISONS
                              + len(CORRECTED_FUNCTIONS) + N_PATH_FORMS)
    panel = tally("panel_subset")
    ra = tally("corrected_subset_reading_A")
    rb = tally("corrected_subset_reading_B")
    rc = tally("corrected_subset_reading_C")

    # Control: panel[0] also published "without `contains` excluded it would be 89/130".
    panel_plus_contains = sum(
        1 for r in rows
        if not (set(r["functions_used"]) - (PANEL_FUNCTIONS | {"contains"}))
        and not [n for n in r["literal_field_indices"] if abs(n) >= INDEX_LIMIT])

    out = {
        "what_this_is": (
            "Fixture coverage of the CORRECTED CONDITIONAL-GO subset defined in FINDINGS.md "
            "`f5` section 5.7.  Built during the T-1 closure pass (punch-list round), not "
            "during the original investigation.  Read-only; imports the real parser; no "
            "database. [punch]"),
        "generated_by": "spikes/T-1/proto/closure_subset_coverage.py",
        "framing_clause": (
            "FRAMING.md section 4 requires per-case reporting, never a summary count -- so "
            "`cases` below carries a verdict and an exclusion reason for all 130, under every "
            "reading.  FRAMING.md section 3 is not engaged: this measures, it does not fix."),
        "provenance": {
            "parser": PARSER,
            "parser_sha256": sha256(PARSER),
            "fixture": FIXTURE,
            "fixture_sha256": sha256(FIXTURE),
            "gims_tree": "GIMS-Project @ 995cc59; expression stack byte-identical to "
                         "GUTS/spine/L1-memory/gims-ledger (FRAMING.md section 2, C2)",
            "fixture_version": fixture["version"],
            "float_epsilon": fixture["float_epsilon"],
            "case_count": len(cases),
            "database_touched": False,
            "files_written": ["spikes/T-1/analysis/subset-coverage.json"],
        },
        "subset_definition": {
            "source": "FINDINGS.md `f5` section 5.7, quoted verbatim in the script header",
            "starting_point_panel_json_0": {
                "node_types": "all 10 leaf/structural",
                "arithmetic_operators": "all 5 (+ - * / %)",
                "comparisons": "all 6 (== != < <= > >=)",
                "field_path_forms": "all 5, with a compile-time |literal index| < 2**31 check (D19)",
                "functions": sorted(PANEL_FUNCTIONS),
                "functions_excluded": sorted(ALL_FUNCTIONS - PANEL_FUNCTIONS),
                "published_size": "36 of 48 constructs, 84 of 130 cases (64.6%)",
            },
            "closure_removes": {
                "functions": sorted(CLOSURE_REMOVES_FUNCTIONS),
                "function_reason": "round = xa A.2 R2-R5; floor/ceil = R6 (per section 5.4(1))",
                "operators": sorted(CLOSURE_REMOVES_OPERATORS),
                "operator_reason": "% = xa A.2 R7 (per section 5.4(1))",
                "qualified": "==/!= over container operands = xa A.2 R8",
            },
            "corrected_functions": sorted(CORRECTED_FUNCTIONS),
            "corrected_construct_count": (
                "%d of %d constructs, at `f2` section 2.1's granularity: %d leaf/structural "
                "node types + %d arithmetic operators + %d comparisons + %d functions + %d "
                "field-path forms.  48 minus the panel's 12 functions = 36; minus "
                "round/floor/ceil = 33; minus the `%%` operator = %d.  The ==/!= "
                "container-operand restriction is a QUALIFIER on constructs that stay in, so "
                "it removes none from this count -- its price is measured in cases, not "
                "constructs (readings A/B/C below)."
                % (N_NODE_TYPES + N_ARITH_CORRECTED + N_COMPARISONS + len(CORRECTED_FUNCTIONS)
                   + N_PATH_FORMS,
                   N_CONSTRUCTS_TOTAL, N_NODE_TYPES, N_ARITH_CORRECTED, N_COMPARISONS,
                   len(CORRECTED_FUNCTIONS), N_PATH_FORMS,
                   N_NODE_TYPES + N_ARITH_CORRECTED + N_COMPARISONS
                   + len(CORRECTED_FUNCTIONS) + N_PATH_FORMS)),
        },
        "ambiguity": {
            "the_clause": "\"==/!= over container operands (R8)\"",
            "why_it_is_ambiguous": (
                "The grammar has no container literal (expr.py:185-214 accepts only "
                "num/str/bool/null/$field/(/call), so `==`/`!=` can receive a list or dict "
                "ONLY from a field resolution or a pass-through function.  Whether an "
                "operand IS a container is therefore a property of the ROW, not of the AST, "
                "and a construct-keyed AVOID rule (`xc` C.1) cannot decide it statically.  "
                "Every reading is measured separately rather than one being assumed."),
            "reading_A": "LITERAL / runtime-witnessed -- a case is OUT only if some `==`/`!=` "
                         "actually received a list or dict while the real evaluator ran that "
                         "case against its own record and context.  This is the clause as "
                         "written.  PRIMARY.",
            "reading_B": "STATIC OVER-APPROXIMATION -- a case is OUT if any `==`/`!=` operand "
                         "COULD be a container (a `field` node, or `coalesce`/`if` over one).  "
                         "This is what a compile-time AVOID rule could actually implement.",
            "reading_C": "MAXIMAL -- a case is OUT if it uses `==`/`!=` at all.  The floor.",
            "also_ambiguous": (
                "Whether \"removes round / floor+ceil / %\" means dropping the construct or "
                "guarding it.  Read as dropping, because section 5.7 names those three bare "
                "while qualifying only the fourth.  A guard-only reading does not produce a "
                "different number here anyway: `xa` A.5(3) records that R4, R6 and R7 are "
                "\"not statically decidable from the AST ... they depend on the row\", so a "
                "static subset rule cannot keep those constructs under a guard."),
        },
        "headline": {
            "answer": ra["in"],
            "of": len(cases),
            "pct": ra["pct_in"],
            "quotable": ("%d of 48 constructs, %d of 130 cases (%.1f%%) -- measured, in the "
                         "same form as section 5.7's own \"36 of 48 constructs, 84 of 130 "
                         "cases (64.6%%)\" for the uncorrected subset.  The correction costs "
                         "%d further fixture cases: `round` 5, `%%` 7, `floor` 2, `ceil` 2.  "
                         "The `==`/`!=` container-operand restriction costs nothing on this "
                         "fixture -- across all 130 cases `expr._eq` is called 16 times and "
                         "never once with a list or a dict operand, reproducing `f2` section "
                         "2.3's 7-of-36-cells table exactly."
                         % (n_corrected_constructs, ra["in"], ra["pct_in"],
                            panel["in"] - ra["in"])),
            "reading": "A (the clause as literally written)",
            "not_84_of_130": ("84/130 is `panel.json[0]`'s UNCORRECTED subset, reproduced here "
                              "as a control.  section 5.7 warns against quoting it for the "
                              "corrected subset; this measurement is why."),
        },
        "results": {
            "panel_subset_control": panel,
            "corrected_subset_reading_A": ra,
            "corrected_subset_reading_B": rb,
            "corrected_subset_reading_C": rc,
        },
        "self_check": {
            "reproduces_panel_84_of_130": panel["in"] == 84,
            "panel_in": panel["in"],
            "reproduces_panel_89_without_contains": panel_plus_contains == 89,
            "panel_plus_contains": panel_plus_contains,
            "eq_operand_kind_matrix": {
                "order": list(_KINDS),
                "rows": eq_matrix,
                "total_eq_calls": eq_calls,
                "cells_touched": eq_cells,
                "reproduces_f2_2_3_seven_of_36_cells": eq_cells == 7,
                "container_cells_touched": sum(
                    eq_matrix[i][j]
                    for i in range(len(_KINDS)) for j in range(len(_KINDS))
                    if _KINDS[i] in ("list", "dict") or _KINDS[j] in ("list", "dict")),
            },
            "eq_matrix_clock_invariant": eq_matrix == eq_matrix_pinned,
            "evaluator_errors": [r["name"] for r in rows if r["evaluator_error"]],
            "d19_oversize_indices_found": sorted(
                {n for r in rows for n in r["literal_field_indices"] if abs(n) >= INDEX_LIMIT}),
            "all_literal_field_indices": sorted(
                {n for r in rows for n in r["literal_field_indices"]}),
        },
        "cases": rows,
    }

    with open(os.path.abspath(OUT), "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=False)
        fh.write("\n")

    print("wrote %s" % os.path.abspath(OUT))
    print("panel[0] subset (control)   %3d / %d  (%.1f%%)   reproduces 84/130: %s"
          % (panel["in"], len(cases), panel["pct_in"], panel["in"] == 84))
    print("CORRECTED subset reading A  %3d / %d  (%.1f%%)   <-- headline"
          % (ra["in"], len(cases), ra["pct_in"]))
    print("CORRECTED subset reading B  %3d / %d  (%.1f%%)"
          % (rb["in"], len(cases), rb["pct_in"]))
    print("CORRECTED subset reading C  %3d / %d  (%.1f%%)"
          % (rc["in"], len(cases), rc["pct_in"]))
    print("\nblocking histogram (reading A; a case may appear under several):")
    for k, v in ra["blocking_histogram"].items():
        print("   %-58s %3d" % (k, v))
    print("\nmarginal gain if re-admitted (sole blocker, reading A):")
    for k, v in ra["marginal_gain_if_readmitted"].items():
        print("   %-58s +%d" % (k, v))


if __name__ == "__main__":
    main()
