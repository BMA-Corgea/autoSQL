"""demo/tests/t76_mutants.py — T-76's mutants, run by the mutation pass's own runner.

plan §8.2's pass (demo/tests/mutation_pass.py) is frozen machinery: its sixteen are
pinned in run-demo's own text, and `./run-demo test --mutants` runs exactly those.
T-76's mutants live here instead, and reuse that runner WITHOUT changing it: the
same anchor check (each anchor exactly once, or the run fails), the same
green-before-red rule (a criterion not green on the clean tree is INVALID), the same
restore-and-verify of every edited file, the same B10 fixture check around each one.
Only the list differs.

    demo/.venv/bin/python demo/tests/t76_mutants.py            # all of them
    demo/.venv/bin/python demo/tests/t76_mutants.py --dry-run  # anchors only
    demo/.venv/bin/python demo/tests/t76_mutants.py --only T1,T4

Each mutant names its killing test (`selector`). AC7's seven are T1–T8 (the probe
split in two, T6 and T8, one per side); T9–T17 are the builder's own; T18–T20 are the
S16 check's survivors S1 and S6 (S6 in its two halves).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_pass  # noqa: E402

_M = "tests/test_match.py::"

T76_MUTANTS = [
    dict(id="T1",
         defect="the double-count check is off: a row matching two kept parents is drawn",
         criterion="AC4 / AC7: Senders counting Sites is refused with its numbers",
         file="server/scoreboard.py",
         anchor='        if prof["profile"]["counted_twice"] > 0:',
         replacement="        if False:",
         selector=_M + "test_senders_counting_sites_is_refused_with_its_numbers"),
    dict(id="T2",
         defect="the statement joins INNER: a parent with no match (Quarry) is dropped",
         criterion="AC5 / AC7: Sites counting Senders equals hand-written LEFT JOIN SQL",
         file="../picks/group.py",
         anchor='        source += (f"  LEFT JOIN {records.table} AS c\\n"',
         replacement='        source += (f"  JOIN {records.table} AS c\\n"',
         selector=_M + "test_sites_counting_senders_by_site_equals_hand_written_sql"),
    dict(id="T3",
         defect="Rows is count(*): a parent with no match reads 1",
         criterion="AC5 / AC7: Quarry reads 0 against hand-written COUNT(s.key)",
         file="../picks/group.py",
         anchor='rows_sql = "count(c.key)" if rel else "count(*)"',
         replacement='rows_sql = "count(*)"',
         selector=_M + "test_sites_counting_senders_by_site_equals_hand_written_sql"),
    dict(id="T4",
         defect="numbers matched as text (#>>): 2 no longer matches 2.0",
         criterion="AC7: the number fixture, 2 = 2.0 and 1 = 1.0",
         file="../picks/group.py",
         anchor='f"   AND ( {counted} #> %(rel_key)s ) = ( {parent} #> %(rel_parent_key)s )")',
         replacement='f"   AND ( {counted} #>> %(rel_key)s ) = ( {parent} #>> %(rel_parent_key)s )")',
         selector=_M + "test_numbers_match_by_value_exactly_and_never_across_kinds"),
    dict(id="T5",
         defect="matched across kinds: no type guard, compared as text, so \"2\" matches 2",
         criterion="AC7: the number fixture, a number never matches text",
         file="../picks/group.py",
         anchor=('    return (f"jsonb_typeof( {counted} #> %(rel_key)s ) = %(rel_match)s\\n"\n'
                 '            f"   AND ( {counted} #> %(rel_key)s ) = ( {parent} #> %(rel_parent_key)s )")'),
         replacement=('    return (f"%(rel_match)s::text IS NOT NULL\\n"\n'
                      '            f"   AND ( {counted} #>> %(rel_key)s ) = ( {parent} #>> %(rel_parent_key)s )")'),
         selector=_M + "test_numbers_match_by_value_exactly_and_never_across_kinds"),
    dict(id="T6",
         defect="probe split swapped: the count conditions are probed over the PARENT",
         criterion="AC7 / T-77 item 8: K1, a count over Edge cases is refused by its probe",
         file="server/scoreboard.py",
         anchor='outcomes = probes.check(conn, rel["source"], counted, numeric_roots=roots)',
         replacement='outcomes = probes.check(conn, spec["source"], counted, numeric_roots=roots)',
         selector=_M + "test_k1_a_count_over_edge_cases_is_probed_over_edge_cases"),
    dict(id="T7",
         defect="the second engine joins INNER in its own code (T-77 item 9, source-level)",
         criterion="AC7: the second engine keeps Quarry at 0",
         file="../picks/pyrunner/group.py",
         anchor="    for r in rows:\n        value = ev.resolve(r.record_d, steps)\n",
         replacement=("    for r in rows:\n        if rel and not counted(r):\n            continue\n"
                      "        value = ev.resolve(r.record_d, steps)\n"),
         selector=_M + "test_the_second_engine_keeps_a_parent_with_no_match"),
    dict(id="T8",
         defect="probe split swapped: the page filter is probed over the COUNTED data set",
         criterion="AC7 / T-77 item 8: K2, a filter on Edge cases is refused by its probe",
         file="server/scoreboard.py",
         anchor='outcomes = outcomes + probes.check(conn, spec["source"], page)',
         replacement='outcomes = outcomes + probes.check(conn, rel["source"], page)',
         selector=_M + "test_k2_a_page_filter_on_edge_cases_is_probed_over_edge_cases"),
    dict(id="T9",
         defect="the statement drops the type guard: null = null and [2] = [2] match",
         criterion="a blank or a list matches nothing (the number fixture)",
         file="../picks/group.py",
         anchor='    return (f"jsonb_typeof( {counted} #> %(rel_key)s ) = %(rel_match)s\\n"',
         replacement='    return (f"%(rel_match)s::text IS NOT NULL\\n"',
         selector=_M + "test_numbers_match_by_value_exactly_and_never_across_kinds"),
    dict(id="T10",
         defect="the statement's profile ignores the page's conditions (all parents, not the kept)",
         criterion="a page condition can make a refused match legal",
         file="../picks/group.py",
         anchor='        where += f" AND xpr.truthy( {sql} )"',
         replacement='        where += ""',
         selector=_M + "test_a_page_condition_can_make_a_refused_match_legal"),
    dict(id="T11",
         defect="the second engine's profile ignores the page's conditions",
         criterion="a page condition can make a refused match legal",
         file="../picks/pyrunner/group.py",
         anchor="    parents = _kept(rows, spec)",
         replacement="    parents = list(rows)",
         selector=_M + "test_a_page_condition_can_make_a_refused_match_legal"),
    dict(id="T12",
         defect="the preview drops the rows that match no kept parent",
         criterion="AC3: the preview says 47 senders aren't counted",
         file="server/dashboard.py",
         anchor='    k = prof["counted_none"]\n    if k == 0:',
         replacement='    k = 0\n    if k == 0:',
         selector=_M + "test_the_preview_says_what_the_match_does"),
    dict(id="T13",
         defect="the second engine matches numbers as floats: 9007199254740993 = 9007199254740992",
         criterion="numbers match exactly (the number fixture)",
         file="../picks/pyrunner/group.py",
         anchor='        return ("n", Decimal(value))',
         # floats wherever a float can hold the value (1e400 cannot), so the
         # mutant reaches the comparison instead of crashing on the conversion
         replacement='        return ("n", float(value) if abs(value) < Decimal("1e308") else Decimal(value))',
         selector=_M + "test_numbers_match_by_value_exactly_and_never_across_kinds"),
    dict(id="T14",
         defect="the second engine lets true match 1 (Python's True == 1)",
         criterion="true is not the number 1 (the number fixture)",
         file="../picks/pyrunner/group.py",
         anchor="        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):",
         replacement="        if not isinstance(value, (int, Decimal)):",
         selector=_M + "test_numbers_match_by_value_exactly_and_never_across_kinds"),
    dict(id="T15",
         defect="the gate lets fields of different kinds be matched",
         criterion="AC8: Capacity and Site, Name and Installed refused by name",
         file="../picks/view.py",          # demo/server/dashboard.py until T-86
         anchor='    if f_parent["kind"] != f_counted["kind"]:',
         replacement="    if False:",
         selector=_M + "test_the_gate_refuses_by_name"),
    dict(id="T16",
         defect="the gate lets Everyone match on a field hidden from it",
         criterion="AC8: Label isn't offered in this view",
         file="../picks/view.py",
         anchor='        if not admin and f.get("hidden_by_default"):',
         replacement="        if False:",
         selector=_M + "test_everyone_never_matches_on_a_hidden_field"),
    dict(id="T17",
         defect="names compared without collapsing whitespace (S13 check, MEDIUM)",
         criterion="\"Big hit\" and \"Big  hit\" are one name",
         file="../picks/view.py",
         anchor='    return re.sub(r"\\s+", " ", label).strip().casefold()',
         replacement="    return label.strip().casefold()",
         selector=_M + "test_two_counts_are_one_name_whatever_their_spaces"),
    # The S16 check's two survivors (checks/S16.md), on T-76's core rule: the
    # edge of "counted more than once" was right in the code but pinned by
    # no test.  S6 changes both engines; the runner edits one file per mutant,
    # so it runs here as its two halves (each alone is also caught, as a
    # disagreement), and the report shows the two together killed as well.
    dict(id="T18",
         defect="refused only when MORE THAN ONE row would be counted twice (S16 check, S1)",
         criterion="one site counted three times is refused, with its numbers",
         file="server/scoreboard.py",
         anchor='        if prof["profile"]["counted_twice"] > 0:',
         replacement='        if prof["profile"]["counted_twice"] > 1:',
         selector=_M + "test_one_row_counted_three_times_is_refused"),
    dict(id="T19",
         defect="the statement counts a row as doubled only past TWO parents (S16 check, S6, its SQL half)",
         criterion="a heartbeat matching two sites (Load = Capacity 18) is refused",
         file="../picks/group.py",
         anchor='per_c WHERE n > 1)   AS "counted_twice"',
         replacement='per_c WHERE n > 2)   AS "counted_twice"',
         selector=_M + "test_a_row_matching_exactly_two_parents_is_refused"),
    dict(id="T20",
         defect="the second engine counts a row as doubled only past TWO parents (S16 check, S6, its Python half)",
         criterion="a heartbeat matching two sites (Load = Capacity 18) is refused",
         file="../picks/pyrunner/group.py",
         anchor="    twice = [n for n in per_counted if n > 1]",
         replacement="    twice = [n for n in per_counted if n > 2]",
         selector=_M + "test_a_row_matching_exactly_two_parents_is_refused"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T-76's mutants, on the mutation pass's runner")
    ap.add_argument("--dry-run", action="store_true", help="check anchors; apply nothing")
    ap.add_argument("--only", help="comma-separated mutant ids, e.g. T1,T4")
    args = ap.parse_args(argv)
    # No bytecode is written by the pytest runs this starts: two mutants of one
    # file, applied within the same second and the same size apart, can otherwise
    # be served each other's cached .pyc (measured here: T9's bytecode ran for
    # T10).  An environment setting the forked runs inherit; the runner itself
    # is unchanged.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # The runner reads its module's MUTANTS when run() is called; this file's list
    # stands in for that call only.  The file mutation_pass.py is not touched.
    mutation_pass.MUTANTS = T76_MUTANTS
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    return mutation_pass.run(dry_run=args.dry_run, only=only)


if __name__ == "__main__":
    sys.exit(main())
