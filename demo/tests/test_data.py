"""demo/tests/test_data.py — AC-7 … AC-13: the seeded data (W5).

Every assertion here runs against the really-seeded database (the `db`
fixture, read-only) or against the seed's own source. The numbers are the
plan's, exactly — no tolerances beyond the two bands the criteria
themselves state (AC-8's 88–92%; nothing else has one).

Covers, per T-2-plan.md §7 "Data":
  AC-7  — three count(*): 8,400 / 2,000 / 10.
  AC-8  — adjacent same-sender pairs matching on status AND payload in
          88–92% of cases, over the whole span (B27's mechanism).
  AC-9  — GROUP BY date_trunc('day', (data ->> 'ts')::timestamptz) in a
          UTC session → exactly 7 buckets of 1,200.
  AC-10 — the md5 over all rows ordered by (collection, key) equals the
          digest recorded in demo/manifest.json, and the generator is
          byte-identical across runs.
  AC-11 — the seed's header and console line say the data is invented
          (B31's third place; the screen's labels are W14's half).
  AC-12 — pg_indexes for schema demo holds exactly one row, the PK.
  AC-13 — five witnesses, not four (B12), including the guard-boundary
          pair edge-04/edge-05 through xpr.f8.
Plus the seed-side constraints the plan pins:
  B24  — all ten edge rows, labelled, and none carries a `status` key.
  B26  — every noun:Sample record's `id` equals its row key.
  R16/R17 — the heartbeat's shape and span, literal.
  R19  — the three key formats, fixed-width, so text order is record order.
  §5.5 — the seed never reads the clock (a grep, exactly as the plan says).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.seed import generate, load  # noqa: E402

_SEED_DIR = _REPO_ROOT / "demo" / "seed"
_MANIFEST = _REPO_ROOT / "demo" / "manifest.json"


# ---------------------------------------------------------------------------
# AC-7 — the three counts.
# ---------------------------------------------------------------------------

def test_ac7_counts(db):
    for collection, expected in [
        ("noun:Heartbeat", 8400),
        ("noun:Sample", 2000),
        ("noun:EdgeCase", 10),
    ]:
        n = db.execute(
            "SELECT count(*) FROM demo.records WHERE collection = %s", (collection,)
        ).fetchone()[0]
        assert n == expected, f"{collection}: count(*) = {n}, expected exactly {expected}"


# ---------------------------------------------------------------------------
# AC-8 — the repeat band, measured the way the criterion says: adjacent
# pairs per sender, status AND payload both matching, over the whole span.
# ---------------------------------------------------------------------------

def test_ac8_adjacent_repeat_band(db):
    matched, total = db.execute(
        """
        WITH beats AS (
          SELECT data ->> 'sender_id' AS sender,
                 data -> 'status'  AS status,
                 data -> 'payload' AS payload,
                 key
          FROM demo.records
          WHERE collection = 'noun:Heartbeat'
        ), pairs AS (
          SELECT (status = lag(status) OVER w) AND (payload = lag(payload) OVER w) AS same
          FROM beats
          WINDOW w AS (PARTITION BY sender ORDER BY key)
        )
        SELECT count(*) FILTER (WHERE same), count(same) FROM pairs
        """
    ).fetchone()
    # 50 senders × 167 adjacent pairs — R19 makes ORDER BY key time order.
    assert total == 8350, f"adjacent pair count is {total}, expected 50 × 167 = 8350"
    rate = matched / total
    assert 0.88 <= rate <= 0.92, (
        f"consecutive same-sender beats match on status+payload in {rate:.5f} "
        f"of cases ({matched}/{total}) — outside AC-8's 88–92% band"
    )


# ---------------------------------------------------------------------------
# AC-9 — §7.1's time-bucket expression, written out, in a UTC session.
# ---------------------------------------------------------------------------

def test_ac9_seven_buckets_of_1200(db):
    db.execute("SET TIME ZONE 'UTC'")
    buckets = db.execute(
        """
        SELECT date_trunc('day', (data ->> 'ts')::timestamptz) AS bucket, count(*)
        FROM demo.records
        WHERE collection = 'noun:Heartbeat'
        GROUP BY date_trunc('day', (data ->> 'ts')::timestamptz)
        ORDER BY bucket
        """
    ).fetchall()
    assert len(buckets) == 7, f"expected exactly 7 day buckets, got {len(buckets)}"
    for bucket, n in buckets:
        assert n == 1200, f"bucket {bucket} holds {n} rows, expected exactly 1200"


# ---------------------------------------------------------------------------
# AC-10 — the digest, against the manifest; and the generator against itself.
# ---------------------------------------------------------------------------

def test_ac10_database_digest_matches_manifest(db):
    manifest = json.loads(_MANIFEST.read_text())
    assert load.MANIFEST_DIGEST_KEY in manifest, (
        f"demo/manifest.json has no {load.MANIFEST_DIGEST_KEY} entry — "
        "the seed records it once with `python demo/seed/load.py --record-digest`"
    )
    digest = load.records_digest(db)
    assert digest == manifest[load.MANIFEST_DIGEST_KEY], (
        f"md5 over all rows ordered by (collection, key) is {digest}, but "
        f"demo/manifest.json records {manifest[load.MANIFEST_DIGEST_KEY]} — "
        "the seeded rows are not the rows the manifest promises"
    )


def test_ac10_generator_is_byte_identical_across_runs():
    first = generate.corpus_sha256()
    second = generate.corpus_sha256()
    assert first == second, (
        "two runs of demo/seed/generate.py produced different bytes — "
        "the seed is not deterministic"
    )


# ---------------------------------------------------------------------------
# AC-11 — the seed says its data is invented (B31's third place).
# The screen's three labels are asserted by the UI-contract tests (W14).
# ---------------------------------------------------------------------------

def test_ac11_seed_header_and_console_line_say_invented():
    header = (generate.__doc__ or "").splitlines()[0]
    assert "INVENTED" in header, (
        "demo/seed/generate.py's header must state the data is invented; "
        f"first docstring line is: {header!r}"
    )
    line = load.INVENTED_DATA_LINE
    assert "INVENTED" in line and "fabricated" in line, (
        f"the seed's console line must say the data is invented; got: {line!r}"
    )
    # The line is really printed, not merely defined.
    source = (_SEED_DIR / "load.py").read_text()
    assert "print(INVENTED_DATA_LINE)" in source, (
        "demo/seed/load.py defines INVENTED_DATA_LINE but never prints it"
    )


# ---------------------------------------------------------------------------
# AC-12 — no index but the primary key, ever.
# ---------------------------------------------------------------------------

def test_ac12_the_only_index_is_the_primary_key(db):
    rows = db.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'demo'"
    ).fetchall()
    assert [r[0] for r in rows] == ["records_pkey"], (
        f"schema demo must hold exactly one index (the PK); pg_indexes says: {rows}"
    )


# ---------------------------------------------------------------------------
# AC-13 — five witnesses (B12), each asserted on its named row (B24).
# ---------------------------------------------------------------------------

def _edge(db, key, sql):
    return db.execute(
        sql, {"key": key}
    ).fetchone()


def test_ac13_witness_1_value_1e300(db):
    typeof, exact = _edge(
        db, "edge-00",
        "SELECT jsonb_typeof(data -> 'a'), (data ->> 'a')::numeric = 1e300 "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' AND key = %(key)s",
    )
    assert typeof == "number" and exact is True, (
        f"edge-00 must carry a = 1e300 as a JSON number, exactly; got typeof={typeof}, equal={exact}"
    )


def test_ac13_witness_2_list_1e300_1(db):
    (equal,) = _edge(
        db, "edge-01",
        "SELECT data -> 'l' = '[1e300, 1]'::jsonb "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' AND key = %(key)s",
    )
    assert equal is True, "edge-01 must carry l = [1e300, 1], exactly"


def test_ac13_witness_3_container_valued_keys(db):
    where_t, tags_t = _edge(
        db, "edge-02",
        "SELECT jsonb_typeof(data -> 'where'), jsonb_typeof(data -> 'tags') "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' AND key = %(key)s",
    )
    assert (where_t, tags_t) == ("object", "array"), (
        f"edge-02 must carry one object-valued and one array-valued key; got {where_t}/{tags_t}"
    )


def test_ac13_witness_4_huge_is_a_json_number(db):
    typeof, exact = _edge(
        db, "edge-03",
        "SELECT jsonb_typeof(data -> 'huge'), (data ->> 'huge')::numeric = '1e400'::numeric "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' AND key = %(key)s",
    )
    # The last clause of AC-13: the value survived the seed as a JSON number,
    # not a string and not a null — which is why generate.py writes this row
    # as raw JSON text rather than through a Python float.
    assert typeof == "number", f"edge-03's huge must be a JSON number; jsonb_typeof says {typeof}"
    assert exact is True, "edge-03's huge must equal 1e400 exactly"


def test_ac13_witness_5_guard_boundary_pair(db):
    # B12's fifth witness: just below the shipped 297-digit guard xpr.f8
    # returns a number; just above it, NULL. This is what proves the guard's
    # edge is where the file says it is (B15: 1.7976931348623157e+296).
    rows = db.execute(
        "SELECT key, xpr.f8(data -> 'g') IS NULL "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' "
        "AND key IN ('edge-04', 'edge-05') ORDER BY key"
    ).fetchall()
    assert rows == [("edge-04", False), ("edge-05", True)], (
        "the guard-boundary pair is wrong: expected xpr.f8 to return a number "
        f"for edge-04 and NULL for edge-05; got {rows}"
    )


# ---------------------------------------------------------------------------
# B24's two constraints, and the ten rows themselves.
# ---------------------------------------------------------------------------

def test_b24_all_ten_edge_rows_labelled_and_status_free(db):
    rows = db.execute(
        "SELECT key, data ? 'label', coalesce(data ->> 'label', '') <> '', data ? 'status' "
        "FROM demo.records WHERE collection = 'noun:EdgeCase' ORDER BY key"
    ).fetchall()
    assert [r[0] for r in rows] == [f"edge-{i:02d}" for i in range(10)], (
        f"noun:EdgeCase must hold exactly edge-00 … edge-09; got {[r[0] for r in rows]}"
    )
    for key, has_label, label_nonempty, has_status in rows:
        assert has_label and label_nonempty, f"{key} must carry a non-empty label (R11, B24)"
        # AC-45(a) needs `status` accepted as an alias on this collection —
        # so no row here may carry a status key (B24 constraint 1).
        assert not has_status, f"{key} carries a status key, which B24 forbids"


# ---------------------------------------------------------------------------
# B26 — one identifier per Sample row, not two.
# ---------------------------------------------------------------------------

def test_b26_sample_id_equals_key(db):
    n = db.execute(
        "SELECT count(*) FROM demo.records "
        "WHERE collection = 'noun:Sample' AND data ->> 'id' IS DISTINCT FROM key"
    ).fetchone()[0]
    assert n == 0, f"{n} noun:Sample rows carry an id that differs from their key (B26)"


# ---------------------------------------------------------------------------
# R16 / R17 — the heartbeat's shape and span, in every single row.
# ---------------------------------------------------------------------------

def test_r16_heartbeat_shape_holds_in_every_row(db):
    n = db.execute(
        """
        SELECT count(*) FROM demo.records
        WHERE collection = 'noun:Heartbeat'
          AND NOT (
            data ->> 'status' IN ('ok', 'warn', 'error')
            AND jsonb_typeof(data -> 'payload') = 'object'
            AND (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(data -> 'payload') k)
                = ARRAY['load', 'note']
            AND jsonb_typeof(data -> 'payload' -> 'load') = 'number'
            AND (data -> 'payload' ->> 'load')::numeric = floor((data -> 'payload' ->> 'load')::numeric)
            AND (data -> 'payload' ->> 'load')::numeric BETWEEN 0 AND 100
          )
        """
    ).fetchone()[0]
    assert n == 0, (
        f"{n} heartbeat rows break R16's shape (closed status set; payload of "
        "exactly load+note; load a whole JSON number in 0–100 in every row)"
    )


def test_r17_span_is_the_pinned_seven_utc_days(db):
    lo, hi, distinct_ts, bad_form = db.execute(
        r"""
        SELECT min(data ->> 'ts'), max(data ->> 'ts'),
               count(DISTINCT data ->> 'ts'),
               count(*) FILTER (WHERE data ->> 'ts' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        FROM demo.records WHERE collection = 'noun:Heartbeat'
        """
    ).fetchone()
    assert lo == "2026-08-14T00:00:00Z", f"span must start at R17's literal; min ts is {lo}"
    assert hi == "2026-08-20T23:00:00Z", f"span must end at R17's literal; max ts is {hi}"
    assert distinct_ts == 168, f"all senders share 168 instants; got {distinct_ts} distinct ts"
    assert bad_form == 0, f"{bad_form} heartbeat ts values are not fixed-width UTC ISO-8601"


# ---------------------------------------------------------------------------
# R19 — fixed-width keys: text order is record order.
# ---------------------------------------------------------------------------

def test_r19_key_formats(db):
    for collection, pattern in [
        ("noun:Heartbeat", r"^hb-\d{2}-\d{4}$"),
        ("noun:Sample", r"^smp-\d{4}$"),
        ("noun:EdgeCase", r"^edge-\d{2}$"),
    ]:
        n = db.execute(
            "SELECT count(*) FROM demo.records WHERE collection = %s AND key !~ %s",
            (collection, pattern),
        ).fetchone()[0]
        assert n == 0, f"{n} {collection} keys do not match R19's format {pattern}"


# ---------------------------------------------------------------------------
# §5.5's grep — the seed never reads the clock, and never re-seeds the
# module-level RNG. Exactly the four strings the plan names, over demo/seed/.
# ---------------------------------------------------------------------------

def test_seed_never_reads_the_clock():
    forbidden = ["datetime.now", "date.today", "time.time", "random.seed()"]
    hits = []
    for path in sorted(_SEED_DIR.glob("*.py")):
        text = path.read_text()
        for needle in forbidden:
            if needle in text:
                hits.append(f"{path.name}: {needle}")
    assert not hits, (
        "the seed must be deterministic — plan §5.5 forbids these in demo/seed/: "
        + ", ".join(hits)
    )
