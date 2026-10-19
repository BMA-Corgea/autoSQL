"""demo/tests/t112_mutants.py — T-112's mutants: a stored number read as a double that no double holds.

BE1–BE5 break the second engine's check and the statement's probe member d ALIKE, so the engines agree and only a
hand-truth vector (a refusal the rule demands, a value the exact answer demands) catches them. E1–E16 break one
engine at one edge each. The parity tests run on an alpine throwaway (AUTOSQL_PARITY_DSN). Run on
``t78_mutants.py``'s runner. RUN ON A SCRATCH COPY.

E2 and E16 are the foreman's ruling (A): a number past the largest double is left as it was beside the statement
(E2 refuses it anyway, and the demo's step 13 would move), and refused when the engine answers alone (E16, the
option ignored). E15 breaks the printer's midpoint rule (an edge of the interval counted as inside); the spec's "a
tie to the odd digit" was an equivalent mutant: no double reaches a tie in that search (``pg_shortest``).

    AUTOSQL_PARITY_DSN=… demo/.venv/bin/python demo/tests/t112_mutants.py [--dry-run] [--only E1,E2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_P = "../parity/tests/test_t112_float_readings.py::"
_PR = "../picks/probes.py"
_D = "../picks/doubles.py"
_X = "../picks/pyrunner/exact.py"
_EV = "../picks/pyrunner/evaluate.py"
_SH = "../picks/pyrunner/shape.py"
_V = "../picks/view.py"

_BY_NAME = _P + "test_a_stored_number_no_double_holds_read_as_a_double_is_refused_by_name"
_PY_2_53 = _BY_NAME + "[filter == 1-9007199254740993]"
_SQL_2_53 = _P + "test_the_statement_alone_refuses_what_the_second_engine_refuses[9007199254740993]"
_AGREE = _P + "test_the_probes_held_test_and_the_second_engines_agree_on_every_value"
_PRINTED = _P + "test_a_computed_double_is_written_as_postgres_writes_it"
_TEXT = _P + "test_numbers_stored_as_text"
_TWO_PANE_SMALL = (_P + "test_the_two_pane_screen_refuses_on_both_panes_in_its_own_words[1e-400-One of these values "
                        "is too small to compute with, so this can't be answered honestly.]")

_HELD_ELSE = """f" ELSE ({t})::numeric = (xpr.j(({t})::float8) #>> '{{}}')::numeric END)")"""
_FLOAT8_VALID = """f" WHEN NOT pg_input_is_valid({t}, 'float8') THEN false\""""
_TEXT_FORM = """        parts.append(f"(jsonb_typeof({op}) = 'string' AND {txt} ~ '{_TEXT_NUMBER_RE}' AND {test(txt, fast_txt)})")\n"""
_TEXT_POS = "    if pos in (COERCED, ELEMENTS) and isinstance(v, str):\n"
_INT_FAST = "        if -_TWO_53 <= v <= _TWO_53:\n"

T112_MUTANTS = [
    # ── both engines broken alike: only the hand-truth vectors can catch these ──
    dict(id="BE1", defect="'digits' dropped on both engines (range only): 2^53+1 kept by == as 2^53",
         edits=[(_D, "    return None if Decimal(pg_shortest(f)) == d else DIGITS\n", "    return None\n"),
                (_PR, _HELD_ELSE, """f" ELSE true END)")""")],
         selector=[_PY_2_53, _SQL_2_53], expect="AssertionError: ('9007199254740993', "),
    dict(id="BE2", defect="a number that reads as 0 counted as held, on both engines: 1e-400 > 0",
         edits=[(_D, "    if f == 0.0:\n        return SMALL\n", "    if f == 0.0:\n        return None\n"),
                (_PR, _FLOAT8_VALID, _FLOAT8_VALID.replace("THEN false", "THEN true"))],
         selector=_BY_NAME + "[filter > 0-1e-400]", expect="AssertionError: ('1e-400', 'filter > 0'"),
    dict(id="BE3", defect="truthiness skipped on both engines: 1e-400 as a bare filter",
         edits=[(_SH, "+ ([(filter_ast, exact.NUMBER)] if filter_ast is not None else [])",
                 "+ ([(filter_ast, exact.SHOWN)] if filter_ast is not None else [])"),
                (_PR, "        extend_d(exact_reading_operands(e, _D_NUMBER))\n",
                 "        extend_d(exact_reading_operands(e, _D_SHOWN))\n")],
         selector=_BY_NAME + "[filter truthy-1e-400]", expect="AssertionError: ('1e-400', 'filter truthy'"),
    dict(id="BE4", defect="text positions skipped on both engines: \"9007199254740993\" * 1 answers ...992",
         edits=[(_X, _TEXT_POS, "    if False:\n"), (_PR, _TEXT_FORM, "        pass\n")],
         selector=_TEXT, expect="assert None == 'digits'"),
    dict(id="BE5", defect="the fast path widened to 16 digits on both engines: 2^53+1 passes",
         edits=[(_D, _INT_FAST, "        if abs(v) < 10 ** 16:\n"),
                (_D, "        if significant <= 15 and -307 <= d.adjusted() <= 14:\n",
                 "        if significant <= 16 and -307 <= d.adjusted() <= 15:\n"),
                (_PR, "f'length({num_t}) <= 15'", "f'length({num_t}) <= 16'"),
                (_PR, 'length({txt}) <= 15)"', 'length({txt}) <= 16)"')],
         selector=[_PY_2_53, _SQL_2_53], expect="AssertionError: ('9007199254740993', "),
    # ── one per edge, one engine each ──
    dict(id="E1", defect="2^53 +/- 1: the second engine's fast path off by one (< 2**54)",
         edits=[(_D, _INT_FAST, "        if -_TWO_53 <= v < 2 ** 54:\n")],
         selector=_PY_2_53, expect="AssertionError: ('9007199254740993', 'filter == 1'"),
    dict(id="E2", defect="1e309 beside the statement: refused without the option, so the demo's step 13 would move",
         edits=[(_X, "        return (k, text) if alone else None\n", "        return (k, text)\n")],
         selector=_P + "test_beside_the_statement_a_number_past_the_largest_double_is_left_to_the_language[1e309]",
         expect="AssertionError: ('1e309', {'source'"),
    dict(id="E3", defect="1e-400: the probe's float8 guard dropped, so the probe dies of 22003 instead of naming the row",
         edits=[(_PR, "            " + _FLOAT8_VALID + "\n", "")],
         selector=_TWO_PANE_SMALL, expect="AssertionError: ('float8 overflow', "),
    dict(id="E4", defect="17 vs 18 digits: Python's repr for the printer that decides 'held'",
         edits=[(_D, "    if m_lo < Fraction(Decimal(r)) < m_hi:\n        return sign + r\n",
                 "    if True:\n        return sign + r\n")],
         selector=[_AGREE, _PRINTED], expect="('number', '44319635693286576', False, True)"),
    dict(id="E5", defect="-0: a shown -0.0 kept as -0",
         edits=[(_X, "    return d.copy_abs() if d.is_zero() else d\n", "    return d\n")],
         selector=_P + "test_a_stored_number_only_shown_is_shown_exactly[-0.0]",
         expect="AssertionError: ('-0.0', Decimal('-0.0'))"),
    dict(id="E6", defect="text: the probe's text form dropped",
         edits=[(_PR, _TEXT_FORM, "        pass\n")],
         selector=_AGREE, expect="('text', '9007199254740993', False, True)"),
    dict(id="E7", defect="nested: min/max's list elements skipped by the second engine",
         edits=[(_X, "    if pos == ELEMENTS and isinstance(v, list):\n", "    if False:\n")],
         selector=_P + "test_numbers_nested_in_lists_and_objects", expect="assert None == 'digits'"),
    dict(id="E8", defect="printer: a computed cell written with repr",
         edits=[(_X, "        return _exact(pg_shortest(v))\n", "        return _exact(repr(v))\n")],
         selector=_PRINTED, expect="Decimal('1E+23') == Decimal('99999999999999990000000')"),
    dict(id="E9", defect="pass-through: a value passed through untouched answered as its double",
         edits=[(_X, "    if isinstance(v, ExactFloat):\n        return _exact(v.text)\n", "")],
         selector=_P + "test_a_stored_number_only_shown_is_shown_exactly[0.12345678901234567]",
         expect="AssertionError: ('0.12345678901234567', Decimal("),
    dict(id="E10", defect="sort by the column: cells converted after the sort, so the sort reads the doubles",
         edits=[(_EV, "    return {name: exact_value(expr.evaluate(ast, row.record_f, {})) for name, ast in parsed}\n",
                 "    return {name: expr.evaluate(ast, row.record_f, {}) for name, ast in parsed}\n"),
                (_SH, "        cell.update(cells[i])\n", "        cell.update(exact.exact_value(cells[i]))\n")],
         selector=_P + "test_a_sort_and_a_summary_by_the_column_read_the_exact_value",
         expect="assert ['c', 'a', 'b'] == ['c', 'b', 'a']"),
    dict(id="E11", defect="literal: number_literal's check removed",
         edits=[(_V, "        if doubles.kind(value) == doubles.DIGITS:\n"
                     "            raise ViewError(\"That number has more digits than can be compared exactly.\")\n", "")],
         selector=_P + "test_a_condition_value_no_double_holds_is_refused_in_words", expect="DID NOT RAISE"),
    dict(id="E12", defect="scope: the second engine's check run after the filter",
         edits=[(_SH, "    exact.check(rows, [(ast, exact.SHOWN) for _n, ast in parsed]\n",
                 "    (lambda *_, **__: None)(rows, [(ast, exact.SHOWN) for _n, ast in parsed]\n"),
                (_SH, "        rows = [r for r in rows if ev.keep_by_filter(r, filter_ast)]\n",
                 "        rows = [r for r in rows if ev.keep_by_filter(r, filter_ast)]\n"
                 "    exact.check(rows, [(ast, exact.SHOWN) for _n, ast in parsed]\n"
                 "                + ([(filter_ast, exact.NUMBER)] if filter_ast is not None else []))\n")],
         selector=_P + "test_the_refusal_reads_every_row_not_only_the_filters", expect="None == 'small'"),
    dict(id="E13", defect="over-refusal guard: text compared as text checked as a reading",
         edits=[(_X, _TEXT_POS, "    if pos in (NUMBER, COERCED, ELEMENTS) and isinstance(v, str):\n")],
         selector=_TEXT, expect="AssertionError: NumberRefused("),
    dict(id="E14", defect="words: member d given the container's words",
         edits=[("server/errors.py", '    if exc.member == "d":\n'
                 "        # T-112: a stored number no double holds, by its kind, with the builder's hint on this screen\n"
                 '        out["body"] = number_words(exc.kind, hint=True)\n', "")],
         selector=_TWO_PANE_SMALL, expect="The expression was inside the subset"),
    dict(id="E15", defect="printer midpoint: an edge of the double's interval counted as inside (Python's choice)",
         edits=[(_D, "        candidates = [n for n in (n_down, n_down + 1) if m_lo < n * q < m_hi]\n",
                 "        candidates = [n for n in (n_down, n_down + 1) if m_lo <= n * q <= m_hi]\n")],
         selector=_P + "test_the_printer_emulation_is_postgres_own", expect="AssertionError: [("),
    dict(id="E16", defect="1e309 == 1e310 alone: the host's option ignored, so two such numbers compare as one infinity",
         edits=[(_X, "            f = _value_kind(v, pos, alone)\n", "            f = _value_kind(v, pos, False)\n")],
         selector=_P + "test_alone_a_number_past_the_largest_double_is_never_a_wrong_answer[1e309 == 1e310]",
         expect="AssertionError: ('1e309 == 1e310', ['a'])"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t112 mutants: refusing to run — set AUTOSQL_PARITY_DSN to a throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T112_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
