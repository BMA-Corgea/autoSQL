"""demo/tests/t111_mutants.py — T-111's mutants: a bare JSON array thousands deep answers its 422, and FastAPI's
every other reply is its own. Run on ``t78_mutants.py``'s runner (each kill on the test's own assertion).

    demo/.venv/bin/python demo/tests/t111_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t111.py::"
_A = "server/app.py"

T111_MUTANTS = [
    dict(id="D1", defect="the reply that can't echo its input raises again: HTTP 500",
         edits=[(_A, '        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]\n',
                 "        raise\n")],
         selector=_T + "test_a_bare_array_thousands_deep_answers_its_422_in_words[3000-/api/pick]",
         expect="(500, 'Internal Server Error')"),
    dict(id="D2", defect="every 422 loses its input, not only the one that can't echo it",
         edits=[(_A, "        return await request_validation_exception_handler(request, exc)\n",
                 "        raise RecursionError\n")],
         selector=_T + "test_a_shallow_bare_array_keeps_fastapis_own_reply_with_its_input[/api/dashboard/answer]",
         expect="'input'"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T111_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
