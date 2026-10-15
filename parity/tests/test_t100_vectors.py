"""T-100: parity/pick-vectors-in-zone.json through BOTH engines, each equal to its hand answer.

Needs a Postgres carrying THIS tree's runtime (AUTOSQL_PARITY_DSN; a throwaway). SKIPS without it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "parity"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres with this tree's runtime")
VECTORS = ROOT / "parity" / "pick-vectors-in-zone.json"


@needs_db
def test_every_bucket_case_equals_its_hand_answer_in_both_engines():
    import psycopg

    import demo.picks_host  # noqa: F401
    import check_picks
    import this_runtime

    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(DSN) as conn:
        results = check_picks.run_vectors(conn, VECTORS)
        conn.rollback()
    bad = [f"{r.name}: statement {r.sql}, second engine {r.python}, by hand {r.expect}" for r in results if not r.ok]
    assert len(results) == 15, f"{len(results)} cases ran, not 15"
    assert not bad, "\n".join(bad)


@needs_db
def test_a_summary_on_a_zone_the_clocks_disagree_on_is_refused_by_name(monkeypatch):
    """The zoned cut carries time_of_day's guard: Python's Denver clock moved an hour from 2026-11-01
    differs from the database's, so the statement is refused by name and date, never cut two ways."""
    import psycopg

    import demo.picks_host  # noqa: F401
    import check_picks
    import this_runtime
    from picks import builder

    C = builder._compile
    real = C.zone_transitions
    starts, offsets = real("America/Denver")
    moved = [o + 3600 if s >= 1793520000 else o for s, o in zip(starts, offsets)]
    monkeypatch.setattr(C, "zone_transitions", lambda z: (starts, moved) if z == "America/Denver" else real(z))
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.Error) as e:
            check_picks.run_vectors(conn, VECTORS)
        conn.rollback()
    assert e.value.sqlstate == "XPR05"
    assert "America/Denver" in str(e.value) and "2026-11-01" in str(e.value)
