"""demo/tests/t96_mutants.py — T-96 S1's mutants: the filter tree.

The tree composes into ONE expression both engines read, so every one of these breaks the statement
and the second engine the SAME way — they still agree, and only the hand-written truth tables, the
hand-written SQL and the sentence's own words can catch it.  Run on ``t78_mutants.py``'s runner (each
kill on the test's own assertion, bytecode off, files restored, the digest checked).  RUN ON A SCRATCH
COPY OF THE TREE, never in a worktree anyone reads.

    demo/.venv/bin/python demo/tests/t96_mutants.py [--dry-run] [--only R1,R2]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_M = "tests/test_t96.py::"
TRUTH = _M + "test_a_tree_keeps_what_its_truth_table_keeps_in_both_engines"
V = "../picks/view.py"

T96_MUTANTS = [
    dict(id="R1", defect="a nested box joins by its parent's join (both engines)",
         edits=[(V, '            expr, words, n = _box(item, fields, "A group", zone)',
                 '            expr, words, n = _box(dict(item, join=box.get("join")), fields, "A group", zone)')],
         selector=TRUTH, expect="kept"),
    dict(id="R2", defect="a group of one reads in brackets",
         edits=[(V, '            parts.append((expr, f"({words})" if n >= 2 else words))',
                 '            parts.append((expr, f"({words})" if n >= 1 else words))')],
         selector=_M + "test_a_group_of_one_reads_without_brackets", expect="Heartbeats where Time is on Aug 20 and (Status is warn)"),
    dict(id="R3", defect="an empty group counts as every row (both engines)",
         edits=[(V, "            if expr is None:\n                continue\n",
                 '            if expr is None:\n                expr, words, n = "true", "every row", 1\n')],
         selector=TRUTH, expect="an empty group beside a card: kept"),
    dict(id="R4", defect="a nested 'exactly one of' / 'all or none of' of one item is taken, silently",
         edits=[(V, '    logic = _logic(box.get("join"), len(parts), where)',
                 '    logic = _logic(box.get("join"), max(len(parts), 2), where)')],
         selector=_M + "test_what_a_tree_cannot_be_is_refused_by_name", expect="needs two or more conditions"),
    dict(id="R5", defect="the filter is never measured by the parser (65 deep reaches the engines)",
         edits=[(V, "        parser.parse(expr)\n", "        pass\n")],
         selector=_M + "test_the_parsers_depth_64_is_answered_and_65_refused_in_words",
         expect="65 deep was not refused in words"),
    dict(id="R6", defect="too deep by brackets is said as too many in a row",
         edits=[(V, '        if "nesting" in said:', '        if "nesting" in said and False:')],
         selector=_M + "test_the_parsers_depth_64_is_answered_and_65_refused_in_words",
         expect="65 deep was not refused in words"),
    dict(id="R7", defect="the length limit off by one (2,000 characters refused)",
         edits=[(V, '    if len(expr) > _source_limit():', '    if len(expr) >= _source_limit():')],
         selector=_M + "test_a_filter_of_2000_characters_is_answered_and_2001_refused_in_words",
         expect="This filter is too long to check"),
    dict(id="R8", defect="the old flat form is read without its logic (any / exactly one / all or none → all)",
         edits=[(V, '    return {"join": logic, "items": conds}', '    return {"join": None, "items": conds}')],
         selector=_M + "test_the_old_flat_form_and_its_one_box_tree_answer_alike", expect="AssertionError: sentence"),
    dict(id="R9", defect="the Everyone view's hidden-field check stops at the top level",
         edits=[(V, '                    if isinstance(it["items"], list):\n                        stack.append(it["items"])',
                 '                    if isinstance(it["items"], list):\n                        pass')],
         selector=_M + "test_a_hidden_field_four_groups_deep_is_refused_for_everyone",
         expect="Label isn't offered in this view."),
    dict(id="R10", defect="a nested group of two or more loses its brackets in the sentence",
         edits=[(V, '            parts.append((expr, f"({words})" if n >= 2 else words))',
                 '            parts.append((expr, words))')],
         selector=[_M + "test_time_on_aug_20_and_warn_or_error", _M + "test_a_nested_one_of_reads_in_brackets"],
         expect="where Time is on Aug 20 and Status is warn or Status is error"),
    dict(id="R11", defect="a count column's nested groups are dropped (both engines)",
         edits=[(V, "    expr, words = filter_parts(c, fields, where, where, zone)",
                 "    expr, words = filter_parts(dict(c, filter=dict(c['filter'], items=[i for i in c['filter']['items'] "
                 "if 'items' not in i])) if c.get('filter') else c, fields, where, where, zone)")],
         selector=_M + "test_a_count_columns_tree_equals_hand_sql", expect="a count column's tree counted other rows"),
    dict(id="R12", defect="the tree's own depth limit off by one (64 groups refused)",
         edits=[(V, "        if depth > limit:", "        if depth >= limit:")],
         selector=_M + "test_a_tree_64_groups_deep_is_answered_and_65_refused_in_words", expect="assert (422 == 200"),
    dict(id="R13", defect="a box is built before it is measured (nested 'all or none' doubles at every level)",
         edits=[(V, "    if composed_length([len(e) for e, _ in parts], logic) > _source_limit():\n        raise ViewError(TOO_LONG)\n", "")],
         selector=_M + "test_forty_nested_all_or_none_groups_are_refused_in_words_without_building_them",
         expect="the request did not finish (memory capped at 1.5 GB)"),
    dict(id="R14", defect="'all or none of' measured as if its sum were written once",
         edits=[(V, "    return 2 * total + 17 + len(str(n))", "    return total + 17 + len(str(n))")],
         selector=_M + "test_a_filter_is_measured_exactly_as_it_would_be_built", expect="('allnone', 2)"),
    dict(id="VD", defect="an empty group counts as false (a-chk's mutant: it survived the suite)",
         edits=[(V, "            if expr is None:\n                continue\n",
                 '            if expr is None:\n                expr, words, n = "false", "nothing", 1\n')],
         selector=TRUTH, expect="a AND an empty group: kept"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    runner.T78_MUTANTS[:] = T96_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
