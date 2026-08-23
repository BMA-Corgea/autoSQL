"""demo/tests/conftest.py — shared fixtures for the demo suite.

W5 adds the database connection fixture the data tests need. The
connection comes from demo.seed.load.demo_connection(), which routes
through the demo's one connection factory (demo/server/db.py :: connect,
B13) as soon as that file exists — and can therefore only ever reach the
demo's own database on 127.0.0.1:55440.

The fixture pins the session READ ONLY: nothing that reads demo.records
through it can write, which is the cheap half of B10's protection. B10's
full session-start/session-end checksum guard is the second half, and it
landed with W16's suite wiring at the bottom of this file — together with
the run report `./run-demo test` prints its final summary line from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(scope="session")
def db():
    """A read-only session on the demo's own database."""
    from demo.seed.load import demo_connection

    try:
        conn = demo_connection()
    except Exception as exc:  # no stack up — say exactly what to do
        pytest.fail(
            "could not connect to the demo database on 127.0.0.1:55440 — "
            f"run './run-demo up' first ({exc})"
        )
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    yield conn
    conn.close()


# ═════════════════════════════════════════════════════════════════════════
# W16 — B10's checksum guard, and the suite's own report
# ═════════════════════════════════════════════════════════════════════════
#
# B10, in the plan's own words:
#
#   "demo/tests/conftest.py asserts AC-10's checksum — md5 over all rows
#    ordered by (collection, key) — at session start and again at session
#    end, and fails if they differ.  This is what turns 'we remembered to
#    clean up' into a checked fact.  A future test that writes and forgets
#    fails here rather than corrupting AC-38(b) two runs later."
#
# Three states, and all three are reported rather than inferred:
#
#   verified      the digest at session end equals the digest at session
#                 start.  Nothing leaked.
#   LEAKED        they differ.  The run is failed (exit status forced to 1)
#                 and the two digests are printed, because a suite that
#                 corrupted the seed and exited 0 is the exact failure this
#                 guard exists to stop.
#   unavailable   the demo database could not be reached.  Reported as a
#                 LOUD SKIP in §9.7's four-part sense — SKIPPED, naming what
#                 was looked for, counted separately in the final summary,
#                 and everything that does not need a database still runs.
#                 `./run-demo test` guarantees the stack (B23), so this state
#                 belongs to a bare `pytest demo/tests` with nothing up.
#
# A fourth is possible and is not a leak: the digest at session START may
# already disagree with demo/manifest.json.  That is a database which
# arrived corrupted rather than one this run corrupted, and the two are
# worth telling apart — so it is reported separately, and it also fails.
#
# THE REPORT.  When AUTOSQL_DEMO_TEST_REPORT names a path, this file writes
# the run's outcome counts, its skip reasons and the guard's state there as
# JSON.  `./run-demo test` reads it to print the final summary line, whose
# skip count is required to be separate from its pass count (§9.7 part 3,
# plan §6.4 item 6).  The counts come from pytest's own report objects
# rather than from parsing pytest's console output.

import json  # noqa: E402
import os  # noqa: E402

_MANIFEST_PATH = _REPO_ROOT / "demo" / "manifest.json"

#: Filled in by the hooks below; read by the report writer at session end.
_GUARD: dict = {
    "state": "unattempted",
    "start": None,
    "end": None,
    "manifest": None,
    "detail": "",
}

_COUNTS: dict = {
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "xfailed": 0,
    "xpassed": 0,
    "errors": 0,
}

#: Every skip reason seen, in order — the raw text the test itself wrote,
#: never a summary of it.
_SKIP_REASONS: list = []


def _records_digest_now() -> str:
    """AC-10's digest, read on a connection of this guard's own.

    Deliberately NOT the session-scoped `db` fixture: that fixture is
    created on first use and torn down before this guard's second reading,
    and a guard that shared a connection with the thing it is watching
    could be fooled by an open transaction.
    """
    from demo.seed.load import demo_connection, records_digest

    conn = demo_connection()
    try:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        return records_digest(conn)
    finally:
        conn.close()


def _manifest_digest() -> str | None:
    from demo.seed.load import MANIFEST_DIGEST_KEY

    try:
        return json.loads(_MANIFEST_PATH.read_text()).get(MANIFEST_DIGEST_KEY)
    except Exception:
        return None


def pytest_sessionstart(session) -> None:
    """B10, first reading."""
    _GUARD["manifest"] = _manifest_digest()
    try:
        _GUARD["start"] = _records_digest_now()
    except Exception as exc:
        _GUARD["state"] = "unavailable"
        _GUARD["detail"] = (
            "SKIPPED B10's checksum guard: no demo database at "
            "127.0.0.1:55440 — './run-demo test' brings one up (B23). "
            f"({type(exc).__name__}: {exc})"
        )
        return

    if _GUARD["manifest"] is not None and _GUARD["start"] != _GUARD["manifest"]:
        _GUARD["state"] = "start-mismatch"
        _GUARD["detail"] = (
            "the database did not match demo/manifest.json BEFORE this run "
            "started — it arrived corrupted rather than being corrupted here: "
            f"md5 {_GUARD['start']} against the recorded {_GUARD['manifest']}"
        )
    else:
        _GUARD["state"] = "armed"


def pytest_runtest_logreport(report) -> None:
    """Count the run from pytest's own report objects."""
    if report.when == "setup":
        if report.skipped:
            if hasattr(report, "wasxfail"):
                _COUNTS["xfailed"] += 1
            else:
                _COUNTS["skipped"] += 1
                _SKIP_REASONS.append(_skip_text(report))
        elif report.failed:
            _COUNTS["errors"] += 1
    elif report.when == "call":
        if hasattr(report, "wasxfail"):
            if report.skipped:
                _COUNTS["xfailed"] += 1
            elif report.passed:
                _COUNTS["xpassed"] += 1
            else:
                _COUNTS["failed"] += 1
        elif report.passed:
            _COUNTS["passed"] += 1
        elif report.failed:
            _COUNTS["failed"] += 1
        elif report.skipped:
            _COUNTS["skipped"] += 1
            _SKIP_REASONS.append(_skip_text(report))
    elif report.when == "teardown":
        if report.failed:
            _COUNTS["errors"] += 1


def _skip_text(report) -> str:
    """The reason the test itself gave, verbatim.

    §9.7 part 2 requires the skip line to name what it looked for; this
    keeps that text intact all the way to `./run-demo test`'s summary
    rather than replacing it with a category.
    """
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        reason = str(longrepr[2])
        return reason[len("Skipped: "):] if reason.startswith("Skipped: ") else reason
    return str(longrepr) if longrepr else "(no reason given)"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    """B10, second reading — and the report `./run-demo test` prints from.

    `trylast` so this prints AFTER pytest's own summary rather than into
    the middle of the progress line: the guard's verdict is the last thing
    the suite says, which is where a reader looks for it.
    """
    if _GUARD["state"] in ("armed", "start-mismatch"):
        try:
            _GUARD["end"] = _records_digest_now()
        except Exception as exc:
            _GUARD["state"] = "unreadable-at-end"
            _GUARD["detail"] = (
                "the demo database answered at session start and not at "
                f"session end ({type(exc).__name__}: {exc}) — B10's guard "
                "cannot say whether anything leaked, so this run fails"
            )
        else:
            if _GUARD["end"] != _GUARD["start"]:
                _GUARD["state"] = "LEAKED"
                _GUARD["detail"] = (
                    "a test wrote to demo.records and did not put it back: "
                    f"md5 was {_GUARD['start']} at session start and is "
                    f"{_GUARD['end']} now (B10)"
                )
            elif _GUARD["state"] == "armed":
                _GUARD["state"] = "verified"
                _GUARD["detail"] = (
                    f"demo.records unchanged across the session (md5 {_GUARD['end']})"
                )

    failing = _GUARD["state"] in ("LEAKED", "start-mismatch", "unreadable-at-end")

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line("")
        if failing:
            reporter.write_sep("=", "B10 CHECKSUM GUARD FAILED", red=True, bold=True)
            reporter.write_line(_GUARD["detail"])
        elif _GUARD["state"] == "unavailable":
            reporter.write_sep("=", "B10 checksum guard SKIPPED", yellow=True)
            reporter.write_line(_GUARD["detail"])
        elif _GUARD["state"] == "verified":
            reporter.write_line(f"B10 checksum guard: verified — {_GUARD['detail']}")

    if failing and session.exitstatus == 0:
        # A suite that corrupted the seed must not exit 0.
        session.exitstatus = 1

    report_path = os.environ.get("AUTOSQL_DEMO_TEST_REPORT")
    if report_path:
        payload = {
            "counts": dict(_COUNTS),
            "skip_reasons": list(_SKIP_REASONS),
            "guard": dict(_GUARD),
            "exitstatus": int(session.exitstatus),
        }
        try:
            Path(report_path).write_text(json.dumps(payload, indent=1))
        except Exception:
            # The report is an output, never a gate: a suite that ran must
            # not be failed by a path it could not write.
            pass
