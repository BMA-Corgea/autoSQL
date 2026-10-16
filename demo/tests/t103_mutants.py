"""demo/tests/t103_mutants.py — T-103's mutants: the date parse without capture groups, one parse a row.

Three break BOTH engines the same way (the vendored evaluator AND the runtime), so the two still agree and only
the values worked out by hand in runtime/tests/test_t103_parse.py can catch them; five break the new SQL parser
alone. Run on ``t78_mutants.py``'s runner (each kill on the test's own assertion, bytecode off, files restored, the
digest checked). RUN ON A SCRATCH COPY OF THE TREE. The SQL half needs a THROWAWAY Postgres: set AUTOSQL_T98_DSN
(or AUTOSQL_RUNTIME_DSN); each test installs the scratch tree's own runtime/runtime.sql there first.

    AUTOSQL_T98_DSN="host=… …" demo/.venv/bin/python demo/tests/t103_mutants.py [--dry-run] [--only BH1]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_RT = "../runtime/runtime.sql"
_EV = "vendor/expr.py"
_T = "../runtime/tests/test_t103_parse.py::"
EDGES = _T + "test_every_null_rule_is_held_at_its_edge_in_both_engines"
INNER = "    IF s !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?)?$' THEN RETURN NULL; END IF;"

T103_MUTANTS = [
    dict(id="BH1", defect="BOTH engines read hour 24 as the next day's midnight (they agree)",
         edits=[(_EV, "    has_time = hh is not None\n",
                 "    has_time = hh is not None\n    _h24 = hh == \"24\"\n    if _h24:\n        hh = \"00\"\n"),
                (_EV, "    since_epoch = dt - _EPOCH\n",
                 "    since_epoch = dt - _EPOCH + (timedelta(days=1) if _h24 else timedelta(0))\n"),
                (_RT, "  IF hh > 23 OR mi > 59 OR ss > 59 THEN RETURN NULL; END IF;",
                 "  IF hh > 24 OR mi > 59 OR ss > 59 THEN RETURN NULL; END IF;"),
                (_RT, "  sec := extract(epoch from (make_timestamp(y, mo, d, hh, mi, ss::double precision) at time zone 'UTC'));",
                 "  sec := extract(epoch from (make_timestamp(y, mo, d, hh % 24, mi, ss::double precision) at time zone 'UTC')) + 86400 * (hh / 24);")],
         selector=EDGES, expect="by hand"),
    dict(id="BH2", defect="BOTH engines drop the fraction of a second",
         edits=[(_EV, '            int((frac or "0").ljust(6, "0")[:6]),', "            0,"),
                (_RT, "  us := rpad(coalesce(frac, '0'), 6, '0')::int;", "  us := 0;")],
         selector=EDGES, expect="by hand"),
    dict(id="BH3", defect="BOTH engines treat 1900 (any year) as a leap year: Feb 29 read as Mar 1",
         edits=[(_EV, "    except ValueError:\n        return None\n    since_epoch",
                 "    except ValueError:\n        if (int(mo), int(d)) != (2, 29):\n            return None\n"
                 "        dt = datetime(int(y), 3, 1, int(hh) if hh else 0, int(mm) if mm else 0, int(ss) if ss else 0,\n"
                 "                      int((frac or \"0\").ljust(6, \"0\")[:6]), tzinfo=timezone.utc)\n    since_epoch"),
                (_RT, "  IF d < 1 OR d > dim THEN RETURN NULL; END IF;",
                 "  IF mo = 2 AND d = 29 AND dim = 28 THEN mo := 3; d := 1; ELSIF d < 1 OR d > dim THEN RETURN NULL; END IF;")],
         selector=EDGES, expect="by hand"),
    dict(id="PM1", defect="the new parser reads the minutes one character off",
         edits=[(_RT, "    hh := substr(s, 12, 2)::int; mi := substr(s, 15, 2)::int;",
                 "    hh := substr(s, 12, 2)::int; mi := substr(s, 16, 2)::int;")],
         selector=EDGES, expect="SQL disagrees"),
    dict(id="PM2", defect="the new parser pads the fraction on the wrong side",
         edits=[(_RT, "  us := rpad(coalesce(frac, '0'), 6, '0')::int;", "  us := lpad(coalesce(frac, '0'), 6, '0')::int;")],
         selector=EDGES, expect="SQL disagrees"),
    dict(id="PM3", defect="the new parser flips the offset's sign (SQL alone)",
         edits=[(_RT, "    sgn := CASE WHEN substr(off, 1, 1) = '+' THEN 1 ELSE -1 END;",
                 "    sgn := CASE WHEN substr(off, 1, 1) = '+' THEN -1 ELSE 1 END;")],
         selector=EDGES, expect="SQL disagrees"),
    dict(id="PM4", defect="'has a time part' off by one: a bare date of exactly 10 characters counted as having a time",
         edits=[(_RT, "')) <= 10\n  END", "')) < 10\n  END")],
         selector=_T + "test_a_time_part_is_decided_after_pythons_trim", expect="xpr.pdate_only"),
    dict(id="PM5", defect="the new parser skips the Unicode path (Python's whitespace and Nd digits)",
         edits=[(_RT, INNER, "    RETURN NULL;")],
         selector=EDGES, expect="SQL disagrees"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    dsn = os.environ.get("AUTOSQL_T98_DSN")
    if dsn and not os.environ.get("AUTOSQL_RUNTIME_DSN"):
        os.environ["AUTOSQL_RUNTIME_DSN"] = dsn
    if not os.environ.get("AUTOSQL_RUNTIME_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t103 mutants: refusing to run — set AUTOSQL_T98_DSN (or AUTOSQL_RUNTIME_DSN) to a throwaway Postgres")
        return 2
    os.environ.setdefault("T103_DIFF_N", "20000")
    runner.T78_MUTANTS[:] = T103_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
