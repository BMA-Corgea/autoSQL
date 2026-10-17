"""demo/tests/t85_mutants.py — T-85's server-side mutants (the screen's are driven by the run folder's
dash-check-t85.mjs and ops/tests/test_t85_words.mjs). Run on ``t78_mutants.py``'s runner (each kill on the test's own
assertion, bytecode off, files restored, the digest checked). RUN ON A SCRATCH COPY. Read-only on the demo database.

    demo/.venv/bin/python demo/tests/t85_mutants.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_T = "tests/test_t85.py::"
_D = "server/dashboard.py"

T85_MUTANTS = [
    dict(id="Q4", defect="the preview's article is always \"a\" (\"matches a edge case\")",
         edits=[(_D, '    return ("an " if word[:1].lower() in "aeiou" else "a ") + word', '    return "a " + word')],
         selector=_T + "test_the_preview_says_a_or_an_by_the_word", expect="matches a edge case"),
    dict(id="Q8", defect="the too-deep question gets the bare \"There was an error parsing the body\" again",
         edits=[("server/app.py", "    if (exc.status_code == 400 and isinstance(exc.__cause__, RecursionError)",
                 "    if (exc.status_code == 400 and False")],
         selector=_T + "test_a_question_nested_too_deep_to_read_is_said_in_a_sentence", expect="assert"),
    dict(id="Q9", defect="\"2,000 of the 2,000 samples\" again, where every one is meant",
         edits=[(_D, "    if part == whole:\n        return f\"all {_n(whole, ds)}\"", "    if False:\n        return f\"all {_n(whole, ds)}\"")],
         selector=_T + "test_a_refusal_where_every_row_is_affected_says_all", expect="of the 2,000"),
    dict(id="Q10", defect="the answer cache's key ignores which matched columns are ticked (run 6's R3)",
         edits=[(_D, '    key = "matched:" + json.dumps([pick, spec], sort_keys=True)',
                 '    key = "matched:" + json.dumps([pick, {k: v for k, v in spec.items() if k != "columns"}], sort_keys=True)')],
         selector=_T + "test_the_same_question_with_another_matched_column_is_answered_again_not_from_the_cache",
         expect="assert"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T85_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
