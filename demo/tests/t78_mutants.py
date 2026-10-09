"""demo/tests/t78_mutants.py — T-78's mutants (AC7): wrong numbers that must fail the suite.

plan §8.2's pass (``mutation_pass.py``) is frozen machinery and edits ONE file per
mutant.  T-78's hardest mutants break BOTH engines the same way at once — the two
then agree, so only a check that is neither engine (hand-written SQL, a rule
written down, the row-count invariant) can catch them.  So this file has its own
small runner, built on that pass's own helpers, unchanged (``_pytest``,
``_write_atomic``, ``_digest``, ``_manifest_digest``):

* every anchor must appear exactly once, or nothing runs;
* every killing test must be GREEN on the clean tree first (red proves nothing
  otherwise);
* every file is restored and re-read after each mutant, on every exit path;
* a kill counts only if the test failed ON ITS OWN ASSERTION: the output must
  carry the mutant's ``expect`` text (run 5's lesson: a mutant can "die" of a
  crash or of a stale .pyc), and bytecode writes are off;
* the database's AC-10 digest is checked before the run and after every
  mutant; any drift stops the run (nothing is deleted).

    demo/.venv/bin/python demo/tests/t78_mutants.py              # all of them
    demo/.venv/bin/python demo/tests/t78_mutants.py --dry-run    # anchors only
    demo/.venv/bin/python demo/tests/t78_mutants.py --only F1,F3
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_pass as mp  # noqa: E402

_M = "tests/test_matched.py::"
EDGE = _M + "test_a_row_matching_exactly_two_is_refused_with_hand_written_numbers"
PROFILE = _M + "test_the_profile_counts_each_edge_in_both_engines"
LEGAL = _M + "test_a_condition_makes_the_refused_pick_legal_with_blanks_that_stay"
NUMBERS = _M + "test_numbers_match_by_value_exactly_and_a_blank_matches_nothing"
SENDER_SQL = _M + "test_each_heartbeat_with_its_senders_name_and_site_equals_hand_written_sql"

_SQL_REPEATED = 'count(*) FILTER (WHERE n > 1)     AS "repeated"'
_PY_REPEATED = '"repeated": sum(1 for n in per_row if n > 1),'

T78_MUTANTS = [
    dict(id="F1", defect="the repeat check is off in the runner: a row matching two is drawn twice",
         edits=[("server/matched.py", '    if prof["profile"]["repeated"] > 0:', "    if False:")],
         selector=EDGE, expect="'table' == 'refused'"),
    dict(id="F2", defect="BOTH engines count a row as repeated only past TWO matches (the threshold off by one, agreeing)",
         edits=[("lookup.py", _SQL_REPEATED, 'count(*) FILTER (WHERE n > 2)     AS "repeated"'),
                ("pyrunner/lookup.py", _PY_REPEATED, '"repeated": sum(1 for n in per_row if n > 2),')],
         selector=EDGE, expect="'table' == 'refused'"),
    dict(id="F3", defect="BOTH engines' repeat check is off (they agree on a repeated table)",
         edits=[("lookup.py", _SQL_REPEATED, '0                                 AS "repeated"'),
                ("pyrunner/lookup.py", _PY_REPEATED, '"repeated": 0,')],
         selector=[EDGE, PROFILE], expect="'table' == 'refused'"),
    dict(id="F4", defect="BOTH engines check repeats over ALL rows, not the kept rows (a condition can't make a pick legal)",
         edits=[("lookup.py", '        where += f" AND xpr.truthy( {sql} )"', '        where += ""'),
                ("pyrunner/lookup.py", "    per_row = [len(matched(r.record_d)) for r in _kept(rows, pick)]",
                 "    per_row = [len(matched(r.record_d)) for r in rows]")],
         selector=[LEGAL, PROFILE], expect="'refused' == 'table'"),
    dict(id="F5", defect="the statement joins INNER: a row with no match disappears",
         edits=[("lookup.py", '        "  LEFT JOIN demo.records AS m\\n"', '        "  JOIN demo.records AS m\\n"')],
         selector=[LEGAL, NUMBERS], expect="388 == 8280"),
    dict(id="F6", defect="the second engine joins INNER (source level): a row with no match disappears",
         edits=[("pyrunner/lookup.py", "        for m in hits or [None]:", "        for m in hits:")],
         selector=NUMBERS, expect="At index 0 diff: ('big', None) != ('huge', 'H')"),
    dict(id="F7", defect="BOTH engines join INNER (they agree on a table that lost its blank rows)",
         edits=[("lookup.py", '        "  LEFT JOIN demo.records AS m\\n"', '        "  JOIN demo.records AS m\\n"'),
                ("pyrunner/lookup.py", "        for m in hits or [None]:", "        for m in hits:")],
         selector=[LEGAL, NUMBERS], expect="388 == 8280"),
    dict(id="F8", defect="no type guard in the statement: a JSON null matches a null, a list a list",
         edits=[("group.py", 'f"jsonb_typeof( {counted} #> %(rel_key)s ) = %(rel_match)s\\n"',
                 'f"%(rel_match)s::text IS NOT NULL\\n"')],
         selector=NUMBERS, expect="('list', 'G')"),
    dict(id="F9", defect="BOTH engines let a JSON null match a JSON null (agreeing on it)",
         edits=[("group.py", 'f"jsonb_typeof( {counted} #> %(rel_key)s ) = %(rel_match)s\\n"',
                 'f"jsonb_typeof( {counted} #> %(rel_key)s ) IN (%(rel_match)s::text, \'null\')\\n"'),
                ("pyrunner/group.py", '    if value is MISSING or value is None:\n        return None\n    if match == "string":',
                 '    if value is MISSING:\n        return None\n    if value is None:\n        return ("blank",)\n    if match == "string":')],
         selector=NUMBERS, expect="('null', 'C')"),
    dict(id="F10", defect="BOTH engines match numbers as text: 2 no longer matches 2.0",
         edits=[("group.py", 'f"   AND ( {counted} #> %(rel_key)s ) = ( {parent} #> %(rel_parent_key)s )")',
                 'f"   AND ( {counted} #>> %(rel_key)s ) = ( {parent} #>> %(rel_parent_key)s )")'),
                ("pyrunner/group.py", '        return ("n", Decimal(value))', '        return ("n", str(value))')],
         selector=NUMBERS, expect="('one', None) != ('one', 'I')"),
    dict(id="F11", defect="BOTH engines read a matched field from the table's own row, not the matched row",
         edits=[("lookup.py", 'ctx_param=f"mc{i}_ctx", column="m.data")', 'ctx_param=f"mc{i}_ctx", column="r.data")'),
                ("pyrunner/lookup.py", "            cell.update(blank if m is None else ev.computed_values(m, parsed))",
                 "            cell.update(blank if m is None else ev.computed_values(by_key[row['key']], parsed))")],
         selector=SENDER_SQL, expect="assert {'hb-01-0000'"),
    dict(id="F12", defect="the gate lets Everyone show a field hidden from it (Edge cases' Label) from another data set",
         edits=[("server/dashboard.py", '        if f.get("hidden_by_default") and not admin:     # T-77\'s rule, for a shown field',
                 "        if False:")],
         selector=_M + "test_everyone_never_sees_a_hidden_field_from_another_data_set",
         expect="(422, \"Label isn't offered in this view.\")"),
    dict(id="F13", defect="the runner refuses only when MORE THAN ONE kept row repeats (a-safe's A11, S19 check HIGH-1)",
         edits=[("server/matched.py", '    if prof["profile"]["repeated"] > 0:', '    if prof["profile"]["repeated"] > 1:')],
         selector=[_M + "test_exactly_one_kept_row_repeating_is_refused",
                   _M + "test_exactly_one_repeating_row_through_the_runner_on_a_fixture"],
         expect="one repeating"),
]


def _check_anchors(chosen) -> list:
    bad = []
    for m in chosen:
        for f, anchor, _ in m["edits"]:
            n = (mp.DEMO / f).read_text().count(anchor)
            if n != 1:
                bad.append(f"{m['id']}: {f} holds its anchor {n} times")
    return bad


def run(dry_run: bool = False, only=None) -> int:
    chosen = [m for m in T78_MUTANTS if not only or m["id"] in only]
    bad = _check_anchors(chosen)
    if bad:
        print("t78 mutants: refusing to run —\n  " + "\n  ".join(bad))
        return 2
    if dry_run:
        print(f"t78 mutants: {len(chosen)} anchors ok")
        return 0
    want = mp._manifest_digest()
    if mp._digest() != want:
        print("t78 mutants: refusing to run — demo.records does not match the manifest")
        return 2
    results = []
    for m in chosen:
        sels = (m["selector"],) if isinstance(m["selector"], str) else tuple(m["selector"])
        t0 = time.time()
        print(f"\n--- {m['id']}: {m['defect']}", flush=True)
        not_green = [s for s in sels if mp._pytest(s).returncode != 0]
        if not_green:
            results.append((m["id"], "INVALID", f"not green on the clean tree: {not_green}"))
            print(f"    INVALID — not green on the clean tree: {not_green}", flush=True)
            continue
        originals = {f: (mp.DEMO / f).read_text() for f, _, _ in m["edits"]}
        try:
            texts = dict(originals)
            for f, anchor, repl in m["edits"]:
                texts[f] = texts[f].replace(anchor, repl, 1)
            for f, text in texts.items():
                mp._write_atomic(mp.DEMO / f, text)
            per = []
            for s in sels:
                got = mp._pytest(s)
                out = got.stdout + got.stderr
                per.append((s, got.returncode != 0, m["expect"] in out, out))
        finally:
            for f, text in originals.items():
                mp._write_atomic(mp.DEMO / f, text)
                if (mp.DEMO / f).read_text() != text:
                    raise RuntimeError(f"{f} was NOT restored after {m['id']}")
        killed = all(failed for _, failed, _, _ in per)
        own = any(failed and mine for _, failed, mine, _ in per)
        verdict = "KILLED" if killed and own else ("KILLED-ELSEWHERE" if killed else "SURVIVED")
        how = "; ".join(f"{s.split('::')[1]}: {'failed' if f else 'PASSED'}"
                        f"{' on its own assertion' if f and mine else ''}" for s, f, mine, _ in per)
        if verdict != "KILLED":
            for s, f, mine, out in per:
                tail = [ln for ln in out.splitlines() if ln.startswith("E ")][:3]
                how += f"\n      {s.split('::')[1]}: {tail}"
        results.append((m["id"], verdict, how))
        print(f"    {verdict} — {how} ({time.time() - t0:.0f}s)", flush=True)
        if mp._digest() != want:
            print("t78 mutants: STOPPED — demo.records drifted from the manifest after " + m["id"])
            return 2
    print("\nt78 mutants:")
    for mid, verdict, how in results:
        print(f"  {mid:4} {verdict:16} {how.splitlines()[0]}")
    ok = all(v == "KILLED" for _, v, _ in results)
    print(f"t78 mutants: {sum(v == 'KILLED' for _, v, _ in results)} killed on their own assertion, "
          f"{sum(v != 'KILLED' for _, v, _ in results)} not — {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T-78's mutants")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args(argv)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    return run(args.dry_run, [s.strip() for s in args.only.split(",")] if args.only else None)


if __name__ == "__main__":
    sys.exit(main())
