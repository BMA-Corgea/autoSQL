"""demo/tests/conftest.py — shared fixtures for the demo suite.

W5 adds the database connection fixture the data tests need. The
connection comes from demo.seed.load.demo_connection(), which routes
through the demo's one connection factory (demo/server/db.py :: connect,
B13) as soon as that file exists — and can therefore only ever reach the
demo's own database on 127.0.0.1:55440.

The fixture pins the session READ ONLY: nothing that reads demo.records
through it can write, which is the cheap half of B10's protection. B10's
full session-start/session-end checksum guard is W16's and lands here
with the suite wiring.
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
