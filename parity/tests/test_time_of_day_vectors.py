"""T-98: parity/time-of-day-vectors.json through BOTH engines, each equal to the hand answer.

Needs a Postgres carrying THIS tree's runtime (AUTOSQL_PARITY_DSN; a throwaway: the shared demo
database carries whatever the last ./run-demo up installed). SKIPS without it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "parity")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres with this tree's runtime")
VECTORS = ROOT / "parity" / "time-of-day-vectors.json"


@needs_db
def test_every_case_equals_its_hand_answer_in_both_engines():
    import psycopg

    import demo.picks_host  # noqa: F401  (registers the host's modules)
    import check_picks

    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)       # the runtime under test, never what a database happens to hold
    with psycopg.connect(DSN) as conn:
        results = check_picks.run_vectors(conn, VECTORS)
        conn.rollback()
    bad = [(r.name, r.sql, r.python, r.expect) for r in results if not r.ok]
    assert len(results) == 15 and not bad, bad
