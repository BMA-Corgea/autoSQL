"""demo/tests/t102_mutants.py — T-102's mutants: the compiler's running size budget.

Run on t78_mutants.py's runner (each kill on the test's own assertion, bytecode off, files
restored, the digest checked), ON A SCRATCH COPY OF THE TREE, under a memory cap and a timeout:

    prlimit --as=4000000000 timeout 3600 demo/.venv/bin/python demo/tests/t102_mutants.py [--dry-run] [--only M1]

M1 is the defect itself (the budget checked only once the statement is built): its tests run the
filter in a caged subprocess (1.5 GB), so the mutant dies there, not on the machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t102.py::"
_C = "../compiler/compile.py"

T102_MUTANTS = [
    dict(id="M1", defect="the budget is checked only once the whole statement is built",
         edits=[(_C, "    setattr(_Compiler, _name, _budgeted(getattr(_Compiler, _name)))\n", "    pass\n"),
                (_C, "    sql = c.predicate(ast)                   # measured as it is built (T-102)\n",
                 "    sql = c.predicate(ast)\n    if len(sql) > MAX_SQL_CHARS:\n        raise TooBig(len(sql))\n")],
         selector=[_T + "test_nested_exactly_one_of_is_refused_in_words_on_every_path",
                   _T + "test_the_budget_stops_the_build_before_it_grows"],
         expect="the caged process died"),
    dict(id="M2", defect="the budget is off by one (a statement of exactly the budget is refused)",
         edits=[(_C, "        if len(sql) > MAX_SQL_CHARS:\n            raise TooBig(len(sql))\n        return sql",
                 "        if len(sql) >= MAX_SQL_CHARS:\n            raise TooBig(len(sql))\n        return sql")],
         selector=_T + "test_the_budget_is_exact_at_its_edge", expect="TooBig"),
    dict(id="M3", defect="a probe's operand too big to check is not caught (a 500)",
         edits=[("../picks/probes.py", "        except _compile_module().TooBig as exc:", "        except ZeroDivisionError as exc:")],
         selector=_T + "test_a_probe_operand_too_big_to_check_refuses_the_pick_by_name", expect="assert 500 == 422"),
    dict(id="M4", defect="the page has no plain words for it",
         edits=[("server/dashboard.py", '    ("too big to check", "This filter is too big to check. Take out a group."),\n', "")],
         selector=_T + "test_nested_exactly_one_of_is_refused_in_words_on_every_path",
         expect="These choices can't be answered together"),
    dict(id="M5", defect="the two-pane screen says a construct is outside the safe subset",
         edits=[("server/errors.py", '        kind = "size"   # T-102', '        kind = "expression"   # T-102')],
         selector=_T + "test_a_typed_filter_on_the_two_pane_screen_is_refused_by_name", expect="'kind': 'expression'"),
    dict(id="M6", defect="a board whose probe is too big is a 500",
         edits=[("server/scoreboard.py", "    except gate.Refused as exc:\n        # T-102: a probe's operand too big to check refuses the board",
                 "    except ZeroDivisionError as exc:\n        # T-102: a probe's operand too big to check refuses the board")],
         selector=_T + "test_a_board_or_a_match_whose_probe_is_too_big_says_so_in_words", expect="Internal Server Error"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T102_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
