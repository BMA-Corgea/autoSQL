"""T-101: a zone is refused only for a row whose clock reading lies where the two clocks disagree.

Each clock reading (a time_of_day, T-100's zoned bucket) is checked against D(zone), the instants
this database's clock and Python's disagree on, worked out once per zone and database and re-checked
cheaply on every question (picks/zones.py). On this machine 109 of 484 zones have a non-empty D,
almost all of it before 1970 (Amsterdam: before 1937), so their questions about 2026 are answered.

The demo's Heartbeats are copied, read-only, from the shared demo database into a TEMPORARY table on
a throwaway Postgres carrying THIS tree's runtime (AUTOSQL_PARITY_DSN); rows the tests add go into
that temporary table only. SKIPS without a DSN.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "demo"), str(ROOT / "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DSN = os.environ.get("AUTOSQL_PARITY_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_PARITY_DSN to a throwaway Postgres with this tree's runtime")
TABLE = "t101_heartbeats"
AMS, EDM, DEN = "Europe/Amsterdam", "America/Edmonton", "America/Denver"


@pytest.fixture(scope="module")
def world():
    import psycopg

    import demo.picks_host  # noqa: F401  (registers the host's modules)
    import this_runtime
    from demo.server import db
    from picks.records import Records

    src = db.connect(application_name="autosql-t101-copy")
    try:
        rows = src.execute("SELECT key, data::text FROM demo.records WHERE collection = 'noun:Heartbeat'").fetchall()
    finally:
        src.rollback()
        src.close()
    with psycopg.connect(DSN, autocommit=True) as cx:
        this_runtime.install(cx)
    conn = psycopg.connect(DSN)
    conn.execute(f"CREATE TEMPORARY TABLE {TABLE} (collection text, key text, data jsonb, PRIMARY KEY (collection, key))")
    with conn.cursor() as cur:
        cur.executemany(f"INSERT INTO {TABLE} VALUES ('noun:Heartbeat', %s, %s::jsonb)", rows)
    conn.commit()
    keys = sorted({k for _, d in rows for k in json.loads(d)})
    records = Records(table=TABLE, sources={"noun:Heartbeat": ", ".join(keys)})
    yield conn, records, keys
    conn.rollback()
    conn.close()


def _pick(flt, **kw):
    p = {"source": "noun:Heartbeat", "computed": [], "filter": flt, "sort": None, "cap": None,
         "window": None, "changed": False, "bucket": "off"}
    p.update(kw)
    return p


def _ask(world, pick):
    """Both engines over the copied Heartbeats under the question's own zone check: ('rows', sql, py)
    or ('refused', message)."""
    import psycopg

    from picks import builder, env, zones
    from picks.pyrunner import shape as pyshape
    from picks.pyrunner.rows import read_rows
    conn, records, keys = world
    conn.execute("SAVEPOINT q")
    try:
        with env.checking_zones(zones.clock_check(conn)):
            built = builder.build(pick, keys, records=records)
        got = conn.execute(built.sql, built.params).fetchall()
    except psycopg.Error as e:
        conn.execute("ROLLBACK TO SAVEPOINT q")
        assert e.sqlstate == "XPR05", (e.sqlstate, str(e))
        return ("refused", str(e))
    conn.execute("RELEASE SAVEPOINT q")
    py = pyshape.answer(read_rows(conn, "noun:Heartbeat", records), pick, records)
    return ("rows", got, py)


def _keys(out):
    assert out[0] == "rows", out
    return sorted(r[1] for r in out[1]), sorted(r["key"] for r in out[2]["rows"])


def _hand(world, where):
    conn = world[0]
    return sorted(r[0] for r in conn.execute(
        f"SELECT key FROM {TABLE} WHERE collection = 'noun:Heartbeat' AND ({where})").fetchall())


def _with_row(world, key, ts, **data):
    conn = world[0]
    conn.execute(f"INSERT INTO {TABLE} VALUES ('noun:Heartbeat', %s, %s::jsonb)",
                 (key, json.dumps({"ts": ts, "status": "late", "sender_id": "hb-x", **data})))


def _without_row(world, key):
    world[0].execute(f"DELETE FROM {TABLE} WHERE key = %s", (key,))


#: 5:00 PM and later in Amsterdam in August (UTC+2) is 15:00Z to 21:59Z.
AMS_FROM_5 = "substr(data->>'ts', 12, 2) IN ('15', '16', '17', '18', '19', '20', '21')"
#: in Edmonton in August (UTC-6), 23:00Z to 05:59Z.
EDM_FROM_5 = "substr(data->>'ts', 12, 2) IN ('23', '00', '01', '02', '03', '04', '05')"


@needs_db
def test_amsterdam_and_edmonton_answer_a_question_about_august_equal_to_hand_written_sql(world):
    """Both zones have a D on this machine (Amsterdam before 1937, Edmonton from Nov 2026) and were
    refused outright before T-101. On the demo's August Heartbeats both are answered, the clock read
    through the check, both engines equal to hand-written SQL."""
    from picks import zones
    conn = world[0]
    for zone, where in ((AMS, AMS_FROM_5), (EDM, EDM_FROM_5)):
        assert zones.disagreements(conn, zone), f"{zone} has no D on this machine: the test proves nothing"
        out = _ask(world, _pick(f'time_of_day($.ts, "{zone}") >= 61200'))
        sql, py = _keys(out)
        hand = _hand(world, where)
        assert len(hand) == 2450 and sql == hand and py == hand, (zone, len(sql), len(py), len(hand))


@needs_db
def test_a_row_where_the_clocks_disagree_is_refused_naming_its_date(world):
    """A Heartbeat on 1916-04-30 read on Amsterdam's clock with no other condition: refused, by name."""
    from picks import zones
    _with_row(world, "t101-1916", "1916-04-30T12:00:00Z")
    try:
        out = _ask(world, _pick(f'time_of_day($.ts, "{AMS}") >= 61200'))
    finally:
        _without_row(world, "t101-1916")
    assert out[0] == "refused" and "Europe/Amsterdam" in out[1] and "1916-04-30" in out[1], out
    assert zones.refusal_words(out[1]) == (
        "Amsterdam time can't read these times: this computer and its database disagree about "
        "Amsterdam's clocks on Apr 30, 1916, and this question reads a time from then.")


@needs_db
def test_edmonton_refuses_a_row_from_november_with_its_date(world):
    _with_row(world, "t101-nov", "2026-11-02T12:00:00Z")
    try:
        out = _ask(world, _pick(f'time_of_day($.ts, "{EDM}") >= 61200'))
    finally:
        _without_row(world, "t101-nov")
    assert out[0] == "refused" and "America/Edmonton" in out[1] and "2026-11-02" in out[1], out


@needs_db
def test_a_summary_per_day_reads_its_buckets_through_the_check_too(world):
    """T-100's zoned buckets: Amsterdam's days of August are answered (equal to hand-written SQL);
    with the 1916 row in the data set the cut is refused, never made two ways."""
    out = _ask(world, _pick(None, bucket="day", bucket_field="ts", bucket_zone=AMS, aggregate={"fn": "count", "field": None}))
    assert out[0] == "rows", out
    sql = [(r[0], int(r[1])) for r in out[1]]
    py = [(r["bucket"], int(r["agg"])) for r in out[2]["rows"]]
    hand = [(r[0], int(r[1])) for r in world[0].execute(
        f"SELECT to_char(date_trunc('day', (data->>'ts')::timestamptz AT TIME ZONE '{AMS}'), "
        f"'YYYY-MM-DD\"T\"HH24:MI:SS'), count(*) FROM {TABLE} GROUP BY 1 ORDER BY 1").fetchall()]
    assert sql == py == hand and hand[0] == ("2026-08-14T00:00:00", 1150), (sql[:2], py[:2], hand[:2])
    _with_row(world, "t101-1916", "1916-04-30T12:00:00Z")
    try:
        out = _ask(world, _pick(None, bucket="day", bucket_field="ts", bucket_zone=AMS, aggregate={"fn": "count", "field": None}))
    finally:
        _without_row(world, "t101-1916")
    assert out[0] == "refused" and "1916-04-30" in out[1], out


@needs_db
@pytest.mark.parametrize("off", ["enable_seqscan", "enable_indexscan", "enable_bitmapscan"])
def test_a_disagreeing_row_another_condition_drops_is_never_a_wrong_number(world, off):
    """Whether the 1916 row's clock is read depends on the plan (the other condition may drop it
    first). Under each forced plan the answer is the hand-written one or a refusal in words; never a
    third, wrong number."""
    conn = world[0]
    _with_row(world, "t101-1916", "1916-04-30T12:00:00Z", status="late")
    conn.execute(f"CREATE INDEX IF NOT EXISTS t101_status ON {TABLE} ((data->>'status'))")
    try:
        conn.execute(f"SET LOCAL {off} = off")
        out = _ask(world, _pick(f'$.status == "ok" and time_of_day($.ts, "{AMS}") >= 61200'))
        conn.execute(f"RESET {off}")
    finally:
        _without_row(world, "t101-1916")
    hand = _hand(world, f"data->>'status' = 'ok' AND {AMS_FROM_5}")
    if out[0] == "refused":
        assert "Europe/Amsterdam" in out[1] and "1916-04-30" in out[1], out
    else:
        sql, py = _keys(out)
        assert sql == hand and py == hand and len(hand) > 0, (off, len(sql), len(py), len(hand))


@needs_db
def test_a_second_question_reads_D_from_the_cache(world):
    """The full comparison runs once per zone and database; the next question only re-checks."""
    from picks import zones
    conn = world[0]
    zones._GAP_CACHE.clear()
    before = zones.full_comparisons
    for _ in range(2):
        out = _ask(world, _pick(f'time_of_day($.ts, "{AMS}") >= 61200'))
        assert out[0] == "rows"
    assert zones.full_comparisons - before == 1
    assert zones.disagreements(conn, AMS) and zones.full_comparisons - before == 1


_SHIFTED = """
CREATE OR REPLACE FUNCTION pg_temp.shifted_offset(z text, t bigint) RETURNS int LANGUAGE sql AS $$
  SELECT extract(epoch FROM ((to_timestamp(t) AT TIME ZONE z) - (to_timestamp(t) AT TIME ZONE 'UTC')))::int
         + CASE WHEN z = 'America/Denver' AND t >= 1903824000 AND t < 1911772800 THEN 3600 ELSE 0 END
$$
"""


@needs_db
def test_a_server_whose_zone_data_changed_without_a_restart_is_seen_by_the_next_question(world, monkeypatch):
    """A system-tzdata upgrade changes the server's rules with no restart (the start time doesn't
    move). Standing in for it: the server's Denver reading moved an hour from May 1 to Aug 1 2030,
    between two of Python's changes, so only the re-check's monthly noons can see it. D was cached
    empty; the next question re-checks, works D out again, and refuses a row from June 2030."""
    from picks import zones
    conn = world[0]
    zones._GAP_CACHE.clear()
    _with_row(world, "t101-2030", "2030-06-15T12:00:00Z")
    try:
        out = _ask(world, _pick(f'time_of_day($.ts, "{DEN}") >= 61200'))
        assert out[0] == "rows" and zones.disagreements(conn, DEN) == ()
        conn.execute(_SHIFTED)
        monkeypatch.setattr(zones, "_SERVER_OFFSET", "pg_temp.shifted_offset({z}, {t})")
        out = _ask(world, _pick(f'time_of_day($.ts, "{DEN}") >= 61200'))
    finally:
        _without_row(world, "t101-2030")
    assert out[0] == "refused" and "America/Denver" in out[1] and "2030-06-15" in out[1], out
    (lo, hi), = zones.disagreements(conn, DEN)
    assert lo <= 1903824000 < 1911772800 <= hi, (lo, hi)


@needs_db
def test_every_zone_this_machine_greyed_before_is_selectable_now(world):
    """The list (built-in SQL, 30-day noons): 109 zones had a mark under T-98, every one of them
    greyed; now a zone is greyed only when the database doesn't know it, and none is unknown here."""
    from picks import env, zones
    conn = world[0]
    names = env.time_zones()
    marks = zones.marks(conn, names, cache=False)
    greyed = [z for z, (why, _note) in marks.items() if why]
    noted = {z: note for z, (_why, note) in marks.items() if note}
    assert greyed == []
    assert len(noted) >= 100, len(noted)
    assert noted[AMS] == "Times before 1970 can't be read on this clock."
    assert noted[EDM] == "Times from November 2026 on can't be read on this clock."


@needs_db
def test_a_restarted_server_works_D_out_again(world):
    """The cache is keyed by the server's start time: an entry left from before a restart (here, a
    stale D planted under another start time, its other keys current) is never used."""
    from picks import zones
    conn = world[0]
    zones._GAP_CACHE.clear()
    assert zones.disagreements(conn, DEN) == ()
    key = (conn.info.host, conn.info.port, conn.info.dbname, DEN)
    zones._GAP_CACHE[key] = dict(zones._GAP_CACHE[key], started="1999-01-01 00:00:00+00", gaps=((0.0, float("inf")),))
    before = zones.full_comparisons
    assert zones.disagreements(conn, DEN) == () and zones.full_comparisons == before + 1
