"""Runtime suite session hooks — the skip disclosure.

WHY THIS FILE EXISTS
    The digit tables in runtime/runtime.sql are derived from the running interpreter's
    Unicode data. `test_the_generated_runtime_is_not_stale` DETECTS a drift and needs no
    database. But the 39 cases that prove the mapping actually makes SQL agree with
    Python — `test_xpr_num_agrees_with_the_python_evaluator` over Arabic-Indic, Thai,
    Devanagari, fullwidth and mathematical digits — sit behind `@needs_db` and skip unless
    AUTOSQL_RUNTIME_DSN is set.

    So `pytest runtime/tests/` printed **"8 passed, 50 skipped"** and read as green, while
    the only thing that would catch a real divergence had not run. On a Unicode bump the
    staleness guard fires, you regenerate, the guard goes green — and nothing ever compared
    a single Unicode digit between the two engines.

    kb/wiki/lessons.md names the class: *never let "nothing happened" render as "everything
    passed"*. This is that rule, applied to the suite that most needs it.

    The skip is NOT removed: a machine without Postgres must still be able to run the
    pure-Python half. It is made LOUD instead, so the count and the caveat cannot be
    separated by a copy-paste.
"""
import os

_SKIPPED_FOR_DB = {"n": 0}
_DSN_ENV = "AUTOSQL_RUNTIME_DSN"


def pytest_runtest_logreport(report):
    if report.skipped and report.when == "setup":
        text = str(getattr(report, "longrepr", "") or "")
        if _DSN_ENV in text or "throwaway Postgres" in text:
            _SKIPPED_FOR_DB["n"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    n = _SKIPPED_FOR_DB["n"]
    w = terminalreporter.write_line
    if not n:
        if os.environ.get(_DSN_ENV):
            w("")
            w("runtime: the database half RAN — SQL was compared against the Python "
              "evaluator on every Unicode digit case.")
        return
    w("")
    w("=" * 78)
    w(f"runtime: DISCLOSURE — {n} tests DID NOT RUN. {_DSN_ENV} is not set.")
    w("runtime:   Those are the cases that compare xpr.num in SQL against the REAL Python")
    w("runtime:   evaluator on Arabic-Indic, Thai, Devanagari, fullwidth and mathematical")
    w("runtime:   digits. The staleness guard above only proves the committed bytes match")
    w("runtime:   THIS interpreter; it does not prove the two engines agree.")
    w("runtime:   A pass count that does not include them is NOT evidence that the digit")
    w("runtime:   mapping is correct — least of all after a regeneration.")
    w("runtime:   Run them:  ops/runtime-check.sh   (throwaway Postgres, torn down after)")
    w("=" * 78)
