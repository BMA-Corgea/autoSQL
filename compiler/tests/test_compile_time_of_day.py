"""T-98: compiling time_of_day(t, zone); T-101: each row's clock reading checked against D.

GIMS's time_of_day reads a wall clock in a NAMED zone (GA-68 Q6). The compiler emits it only for
a zone written in the expression as one of the evaluator's TIME_ZONES. Two clock databases on one
machine disagree (measured 2026-10-13: the host's tzdata and the demo container's differ on
Edmonton, Yellowknife, Casablanca and El Aaiun from this autumn, and on 105 other zones' history
before 1970). T-98 refused such a zone outright; T-101 checks each row instead: the host works out
D, the instants the two clocks disagree on (picks/zones.py, from Python's clock below), and the
compiler reads the clock plainly where D is empty and through xpr.clock otherwise, which refuses
(XPR05, the zone and the row's date) a row whose instant lies in D. A clock reading without D does
not compile.

Database tests: AUTOSQL_COMPILER_DSN, a throwaway Postgres with THIS tree's runtime installed.
They SKIP without it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_COMPILER_DSN")


def _connect():
    import psycopg
    cx = psycopg.connect(DSN, autocommit=True)
    if int(cx.info.port) in (55433, 55440):
        cx.close()
        raise SystemExit("refusing: 55433 is a live database and 55440 is the shared demo's")
    return cx


needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_COMPILER_DSN to a throwaway Postgres with this tree's runtime")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t98_expr", "demo/vendor/expr.py")
C = _load("t98_compile", "compiler/compile.py")
ZONES = EXPR.TIME_ZONES
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from picks import zones as Z  # noqa: E402  (D's arithmetic; stdlib only)

NONE = lambda z: ()  # noqa: E731  -- every zone's D empty: the plain reading


def _compile(src, zones=ZONES, gaps=NONE):
    return C.compile_predicate(EXPR.parse(src), column="data", time_zones=zones, zone_gaps=gaps)


def _d(db):
    """D on the throwaway, from THIS module's Python clock (so a test may move it)."""
    return Z.clock_check(db, transitions=lambda z: C.zone_transitions(z))


# ---- refusals, no database ----------------------------------------------------------------------

@pytest.mark.parametrize("src, why", [
    ('time_of_day($.t, $.z) >= 0', "written in the expression"),
    ('time_of_day($.t, "Mars/Olympus") >= 0', "Mars/Olympus"),
    ('time_of_day($.t, "america/denver") >= 0', "america/denver"),
    ('time_of_day($.t, 5) >= 0', "written in the expression"),
    ('time_of_day($.t, concat("America/", "Denver")) >= 0', "written in the expression"),
])
def test_a_zone_the_compiler_is_not_sure_of_is_uncompilable(src, why):
    with pytest.raises(C.Uncompilable) as e:
        _compile(src)
    assert why in e.value.reason


def test_without_the_evaluators_zone_list_nothing_compiles():
    with pytest.raises(C.Uncompilable) as e:
        C.compile_predicate(EXPR.parse('time_of_day($.t, "UTC") >= 0'), column="data")
    assert "zone list" in e.value.reason


def test_without_the_zones_disagreements_nothing_compiles():
    """T-101: a path that forgets to hand D over fails closed."""
    with pytest.raises(C.Uncompilable) as e:
        C.compile_predicate(EXPR.parse('time_of_day($.t, "UTC") >= 0'), column="data", time_zones=ZONES)
    assert "disagreements" in e.value.reason


def test_an_empty_D_is_the_plain_reading_and_any_other_is_checked():
    plain = _compile('time_of_day($.t, "America/Denver") >= 61200')
    assert "xpr.time_of_day(" in plain.sql and "float8[]" not in plain.sql and "SELECT" not in plain.sql
    d = ((-float("inf"), -1041379200.0), (1793520000.0, float("inf")))
    checked = _compile('time_of_day($.t, "America/Denver") >= 61200', gaps=lambda z: d)
    assert "xpr.time_of_day(" in checked.sql and checked.sql.count("::float8[]") == 1 and "SELECT" not in checked.sql
    assert [-1041379200.0, 1793520000.0] in checked.params.values()          # the bounds; open ends left out
    assert C.gap_bounds(d) == ([-1041379200.0, 1793520000.0], 0)


def test_D_as_bounds_puts_every_instant_on_the_right_side():
    """width_bucket(x, bounds) % 2 == inside exactly when x lies in D, ends included as written."""
    import bisect
    cases = [((-float("inf"), 100.0),), ((100.0, float("inf")),), ((100.0, 200.0), (300.0, 400.0)),
             ((-float("inf"), 100.0), (200.0, 300.0), (400.0, float("inf"))), ((-float("inf"), float("inf")),)]
    for d in cases:
        bounds, inside = C.gap_bounds(d)
        for x in (-1e12, 99.0, 100.0, 150.0, 199.0, 200.0, 250.0, 300.0, 399.0, 400.0, 1e12):
            want = any(lo <= x < hi for lo, hi in d)
            assert (bisect.bisect_right(bounds, x) % 2 == inside) is want, (d, x)


def test_wrong_arity_is_the_evaluators_null():
    for src in ('time_of_day($.t)', 'time_of_day($.t, "UTC", "UTC")', 'time_of_day()'):
        assert C.compile_ast(EXPR.parse(src), column="data", time_zones=ZONES, zone_gaps=NONE).sql == "xpr.j(NULL::float8)"
        assert EXPR.evaluate(EXPR.parse(src), {"t": "2026-08-20T17:00:00Z"}) is None


# ---- Python's clock for a zone ------------------------------------------------------------------

def test_denvers_clock_in_2026():
    starts, offsets = C.zone_transitions("America/Denver")
    at = dict(zip(starts, offsets))
    assert at[1772960400] == -6 * 3600        # 2026-03-08T09:00:00Z: 2:00 MST becomes 3:00 MDT
    assert at[1793520000] == -7 * 3600        # 2026-11-01T08:00:00Z: 2:00 MDT becomes 1:00 MST
    assert starts[0] == C.ZONE_CHECK_FROM and offsets[0] == -(6 * 3600 + 59 * 60 + 56)  # local mean time
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_a_zone_without_changes_is_one_offset():
    assert C.zone_transitions("UTC") == ([C.ZONE_CHECK_FROM], [0])
    assert C.zone_transitions("Etc/GMT+12") == ([C.ZONE_CHECK_FROM], [-12 * 3600])


# ---- in the database ----------------------------------------------------------------------------

ROWS = ["2026-08-20T23:00:00Z", "2026-08-20T17:00:00Z", "2026-08-20T16:59:59Z",
        "2026-08-20T16:59:59.9Z", "2026-03-08T08:59:59Z", "2026-03-08T09:00:00Z",
        "2026-11-01T07:30:00Z", "2026-11-01T08:30:00Z", "2026-08-21T05:59:59Z",
        "2026-08-20T23:00:00+05:30", "2026-08-20", "teatime", None, 5, "1800-01-01T12:00:00Z",
        "0001-01-01T00:00:00Z", "9999-12-31T23:00:00Z"]

PREDICATES = ['time_of_day($.t, "{z}") >= 61200', 'time_of_day($.t, "{z}") < 61200',
              'time_of_day($.t, "{z}") == 5400', '(time_of_day($.t, "{z}") >= 79200) or (time_of_day($.t, "{z}") < 7200)',
              'not (time_of_day($.t, "{z}") >= 0)', 'time_of_day($.t, "{z}") == null']


@pytest.fixture(scope="module")
def db():
    cx = _connect()
    sys.path.insert(0, str(ROOT / "runtime"))
    import this_runtime
    this_runtime.install(cx)           # the runtime under test, never what a database happens to hold
    cx.execute("CREATE TEMP TABLE t98 (k int, data jsonb)")
    with cx.cursor() as cur:
        cur.executemany("INSERT INTO t98 VALUES (%s, %s::jsonb)",
                        [(i, json.dumps({} if t is None else {"t": t})) for i, t in enumerate(ROWS)])
    yield cx
    cx.close()


def _sql_keys(db, src, zones=ZONES, table="t98"):
    c = _compile(src, zones, _d(db))
    params = dict(c.params, ctx="{}")
    return sorted(r[0] for r in db.execute(f"SELECT k FROM {table} WHERE {c.sql}", params).fetchall())


def _py_keys(src):
    ast = EXPR.parse(src)
    return sorted(i for i, t in enumerate(ROWS)
                  if EXPR.truthy(EXPR.evaluate(ast, {} if t is None else {"t": t})))


@needs_db
@pytest.mark.parametrize("zone", ["America/Denver", "UTC", "Asia/Kolkata", "Asia/Kathmandu",
                                  "Pacific/Kiritimati", "Etc/GMT+12", "Australia/Lord_Howe"])
def test_rows_equal_the_evaluators(db, zone):
    for p in PREDICATES:
        src = p.format(z=zone)
        assert _sql_keys(db, src) == _py_keys(src), src


@needs_db
def test_the_outcome_rows_in_denver(db):
    """5:00 PM in Denver on Aug 20 is 23:00Z; the row a second before 5 PM is not in it."""
    src = 'time_of_day($.t, "America/Denver") >= 61200'
    keys = _sql_keys(db, src)
    assert ROWS.index("2026-08-20T23:00:00Z") in keys
    assert ROWS.index("2026-08-20T16:59:59Z") not in keys     # 10:59:59 in Denver


@needs_db
def test_the_check_is_no_subquery_and_the_plan_scans_once(db, monkeypatch):
    """T-101: no per-statement guard any more (no InitPlan), with D empty or not: one scan."""
    for gaps in (NONE, lambda z: ((1793520000.0, float("inf")),)):
        c = _compile('time_of_day($.t, "America/Denver") >= 61200', gaps=gaps)
        plan = "\n".join(r[0] for r in db.execute(f"EXPLAIN SELECT k FROM t98 WHERE {c.sql}", dict(c.params, ctx="{}")))
        assert "InitPlan" not in plan and "SubPlan" not in plan and plan.count("Scan on t98") == 1, plan


def _moved(monkeypatch, fn):
    real = C.zone_transitions
    starts, offsets = real("America/Denver")
    s2, o2 = fn(list(starts), list(offsets))
    monkeypatch.setattr(C, "zone_transitions", lambda z: (s2, o2) if z == "America/Denver" else real(z))


def _edge_table(db, name, *instants):
    db.execute(f"DROP TABLE IF EXISTS {name}")
    db.execute(f"CREATE TEMP TABLE {name} (k int, data jsonb)")
    with db.cursor() as cur:
        cur.executemany(f"INSERT INTO {name} VALUES (%s, %s::jsonb)",
                        [(i, json.dumps({"t": t})) for i, t in enumerate(instants)])


def _refused(db, table, src='time_of_day($.t, "America/Denver") >= 0'):
    import psycopg
    try:
        _sql_keys(db, src, table=table)
    except psycopg.Error as e:
        assert e.sqlstate == "XPR05", (e.sqlstate, str(e))
        db.execute("SELECT 1")
        return str(e)
    return None


@needs_db
def test_a_row_at_the_first_differing_second_is_refused_and_the_second_before_is_not(db, monkeypatch):
    """Python's Denver clock moved an hour from 2026-11-01T08:00:00Z on: D = [that second, on)."""
    _moved(monkeypatch, lambda s, o: (s, [x + 3600 if t >= 1793520000 else x for t, x in zip(s, o)]))
    assert _d(db)("America/Denver") == ((1793520000.0, float("inf")),)
    _edge_table(db, "e1", "2026-11-01T07:59:59Z")
    assert _refused(db, "e1") is None
    _edge_table(db, "e2", "2026-11-01T08:00:00Z")
    assert "America/Denver" in _refused(db, "e2") and "2026-11-01" in _refused(db, "e2")


@needs_db
def test_a_difference_ends_at_the_first_second_the_clocks_agree_again(db, monkeypatch):
    """Moved only from Nov 1 2026 to Mar 14 2027 (09:00Z): D = [1793520000, 1805014800)."""
    _moved(monkeypatch, lambda s, o: (s, [x + 3600 if 1793520000 <= t < 1805014800 else x for t, x in zip(s, o)]))
    assert _d(db)("America/Denver") == ((1793520000.0, 1805014800.0),)
    _edge_table(db, "e3", "2027-03-14T08:59:59Z")
    assert "2027-03-14" in _refused(db, "e3")
    _edge_table(db, "e4", "2027-03-14T09:00:00Z", "2026-08-20T23:00:00Z")
    assert _refused(db, "e4") is None


@needs_db
def test_a_change_pythons_clock_does_not_have_is_found_by_the_daily_noons(db, monkeypatch):
    """Edmonton's shape: Python's Denver keeps MDT through Nov 2026 - Mar 2027. No change of Python's
    is near the database's Nov 1, so D's ends are the noons either side the clocks agree on."""
    gone = {1793520000, 1805014800}
    _moved(monkeypatch, lambda s, o: ([t for t in s if t not in gone], [x for t, x in zip(s, o) if t not in gone]))
    assert _d(db)("America/Denver") == ((1793448001.0, 1805025600.0),)   # 2026-10-31T12:00:01Z .. 2027-03-14T12:00Z
    _edge_table(db, "e5", "2026-12-25T12:00:00Z")
    assert "2026-12-25" in _refused(db, "e5")
    _edge_table(db, "e6", "2026-10-31T12:00:00Z", "2027-03-14T12:00:00Z")
    assert _refused(db, "e6") is None


@needs_db
def test_a_change_an_hour_out_on_the_same_day_is_found_at_the_change(db, monkeypatch):
    """Python's Nov 1 2026 change at 09:00Z instead of 08:00Z: every noon agrees; the second before
    Python's change does not."""
    _moved(monkeypatch, lambda s, o: ([t + 3600 if t == 1793520000 else t for t in s], o))
    (lo, hi), = _d(db)("America/Denver")
    assert lo <= 1793520000 and hi == 1793523600.0
    _edge_table(db, "e7", "2026-11-01T08:30:00Z")
    assert "2026-11-01" in _refused(db, "e7")


@needs_db
def test_a_zone_the_database_does_not_know_is_refused_in_words(db, monkeypatch):
    zones = set(ZONES) | {"Mars/Olympus"}
    monkeypatch.setattr(C, "zone_transitions", lambda z: ([C.ZONE_CHECK_FROM], [0]))
    with pytest.raises(Z.ZoneUnknown) as e:
        _sql_keys(db, 'time_of_day($.t, "Mars/Olympus") >= 0', zones=zones)
    assert str(e.value) == "Olympus time can't be used yet: this computer's database doesn't know it."


@needs_db
def test_every_listed_zone_reads_alike_outside_D_and_refuses_inside_it(db):
    """Every zone the evaluator lists, at a spread of instants: outside its D the database's clock
    equals Python's; inside it the row is refused by name. Never a third outcome."""
    import psycopg
    instants = ["1800-01-01T12:00:00Z", "1900-01-01T00:00:00Z", "1950-06-15T12:00:00Z",
                "1970-01-01T00:00:00Z", "2026-01-15T03:17:41Z", "2026-07-15T21:44:09Z",
                "2026-12-15T09:00:00Z", "2040-07-01T12:00:00Z", "2100-12-31T12:00:00Z"]
    from datetime import datetime
    sec = [datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() for t in instants]
    resolve = _d(db)
    wrong, with_d = [], []
    unknown = []
    for zone in sorted(ZONES):
        try:
            d = resolve(zone)
        except Z.ZoneUnknown:
            unknown.append(zone)          # refused in words: this database doesn't know the zone (a Debian image lacks some)
            continue
        if d:
            with_d.append(zone)
        src = f'time_of_day($.t, "{zone}")'
        c = C.compile_ast(EXPR.parse(src), column="x", time_zones=ZONES, zone_gaps=resolve)
        for t, s in zip(instants, sec):
            inside = any(lo <= s < hi for lo, hi in d)
            try:
                g = db.execute(f"SELECT {c.sql} FROM (SELECT jsonb_build_object('t', %(t)s::text) AS x) b",
                               dict(c.params, ctx="{}", t=t)).fetchone()[0]
            except psycopg.Error as e:
                if not (inside and e.sqlstate == "XPR05" and zone in str(e)):
                    wrong.append((zone, t, "refused", str(e)[:80]))
                continue
            want = EXPR.evaluate(EXPR.parse(src), {"t": t})
            g = None if g is None else json.loads(g) if isinstance(g, str) else g
            if inside or g != want:
                wrong.append((zone, t, g, want))
    assert not wrong, wrong[:5]
    assert len(with_d) < len(ZONES) // 2, f"{len(with_d)} zones have a D: {with_d[:10]}"
    print(f"\n{len(with_d)} of {len(ZONES)} zones have a non-empty D on this machine: {with_d}")
