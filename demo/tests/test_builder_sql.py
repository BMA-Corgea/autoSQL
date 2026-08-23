"""demo/tests/test_builder_sql.py — W10: the query builder (plan §4).

What this file proves, per §6.2's W10 row:

  1. The four statement shapes ACTUALLY RUN against the seeded database
     and return the expected counts — 8,400 rows / the 700–1,100 kept
     band / 8,400 and the generator's own sum / 7 buckets of 1,200.
  2. B11's merge test passes: two computed columns and a filter with
     three DIFFERENT literals merge into one statement with three
     distinct prefixed binds, and every fragment's placeholders carry
     that fragment's prefix.  namespace() is also tested directly.
  3. AC-24(c) — the aggregate, bucket and window SQL the builder emits
     contains no float8 / double precision cast.
  4. AC-40(c), as B3b restates it — three positive facts and one
     negative about operation 9's fragment, not a character grep.
  5. AC-41(a) — every multi-row statement ends in an ORDER BY whose last
     component is `key` (rows) or the group key (bucket).
  6. AC-43(a) — the bucket is date_trunc(<granularity>,
     (data ->> 'ts')::timestamptz), granularity from a two-keyword closed
     set, and the cast is timestamptz, never bare ::timestamp.

Plus the emission halves of B1 (one `bucket` column), B2 (the aggregate
re-emits the compiled expression inline; the computed column is not
emitted at all in that shape) and B3 (the CTE exists iff op 9 is on; the
filter is inside it; LIMIT is outside; `changed` is not displayed).

Expected numbers are pinned by the plan (§5: AC-7's 8,400, AC-9's
7 × 1,200, AC-40(a)'s 700–1,100 band) or computed from the seed
generator's in-memory model — the third independent path B8 names —
never from the builder or the pyrunner.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import builder  # noqa: E402
import gate  # noqa: E402
import legality  # noqa: E402
from demo.seed import generate  # noqa: E402

HEARTBEAT = "noun:Heartbeat"

#: §4.4 item 3's key read — the pinned per-collection vocabulary query,
#: exactly as the plan writes it.  Computed on the server; the tests run
#: the same statement so the vocabulary is read from the data, never typed.
KEYS_SQL = (
    "SELECT DISTINCT k FROM demo.records, LATERAL jsonb_object_keys(data) AS k"
    " WHERE collection = %(collection)s ORDER BY k"
)


def pick(**kw) -> dict:
    p = legality.default_pick()
    p.update(kw)
    return p


@pytest.fixture(scope="module")
def hb_keys(db):
    rows = db.execute(KEYS_SQL, {"collection": HEARTBEAT}).fetchall()
    return [r[0] for r in rows]


def run(db, p, keys):
    built = builder.build(p, keys)
    return built, db.execute(built.sql, built.params).fetchall()


def q6(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@pytest.fixture(scope="module")
def hb_model():
    """The generator's in-memory heartbeat rows (B8's independent path)."""
    return [
        (key, json.loads(data))
        for _c, key, data in generate.heartbeat_rows()
    ]


# ═════════════════════════════════════════════════════════════════════════
# 1 · The four shapes run, and return the expected counts
# ═════════════════════════════════════════════════════════════════════════

class TestShapesRun:
    def test_shape_a_default_returns_all_8400(self, db, hb_keys):
        built, rows = run(db, pick(), hb_keys)
        assert built.shape == "ROWS"
        assert built.columns == ("collection", "key", "data")
        assert len(rows) == 8400  # AC-7's exact count for the heartbeat
        # §7.4: with no sort field, the order is key ASC — R19 makes text
        # order record order, so first/last are the corner keys.
        assert rows[0][1] == "hb-01-0000"
        assert rows[-1][1] == "hb-50-0167"

    def test_shape_a_full_pick_runs_and_caps_last(self, db, hb_keys, hb_model):
        p = pick(
            computed=[{"name": "busy", "expr": "$.payload.load > 80"}],
            filter='$.status == "ok"',
            sort={"field": "ts", "dir": "desc"},
            cap=10,
            window={"field": "payload.load"},
        )
        built, rows = run(db, p, hb_keys)
        assert built.columns == (
            "collection", "key", "data", "busy", "rolling_avg",
        )
        assert len(rows) == 10  # the cap, applied LAST (§4.1 step 8)
        for row in rows:
            record = row[2] if isinstance(row[2], dict) else json.loads(row[2])
            assert record["status"] == "ok"  # the filter really filtered

    def test_shape_a_filter_count_matches_generator(self, db, hb_keys, hb_model):
        """The filter's SQL keeps exactly the rows the generator's own
        in-memory model says carry status ok (B8's independent path)."""
        expected = sum(1 for _k, r in hb_model if r["status"] == "ok")
        built, rows = run(
            db,
            pick(filter='$.status == "ok"',
                 aggregate={"fn": "count", "field": None}),
            hb_keys,
        )
        assert rows == [(expected,)]
        assert 0 < expected < 8400  # the filter is not a no-op on this seed

    def test_shape_b_changed_kept_count_in_band(self, db, hb_keys):
        built, rows = run(db, pick(changed=True), hb_keys)
        kept = len(rows)
        # AC-40(a), SQL pane: 50 first beats + 8-12% of 8,350 pairs.
        assert 700 <= kept <= 1100, f"kept {kept}, band is 700–1,100 of 8,400"
        # AC-40(d)'s SQL half: every sender's first beat survives —
        # IS DISTINCT FROM is what buys this and <> would lose it.
        firsts = [r[1] for r in rows if r[1].endswith("-0000")]
        assert len(firsts) == 50

    def test_shape_b_changed_matches_generator_walk(self, db, hb_keys, hb_model):
        """The kept-key SET equals a plain-Python walk of the generator's
        rows — the identical comparison, on the independent path: group by
        sender, order by (ts, key), keep when the record minus `ts`
        differs from the predecessor's, first row always kept."""
        by_sender: dict[str, list] = {}
        for key, record in hb_model:
            by_sender.setdefault(record["sender_id"], []).append((key, record))
        expected_keys = set()
        for sender, beats in by_sender.items():
            beats.sort(key=lambda kr: (kr[1]["ts"], kr[0]))
            prev = None
            for key, record in beats:
                compared = {k: v for k, v in record.items() if k != "ts"}
                if prev is None or compared != prev:
                    expected_keys.add(key)
                prev = compared
        _built, rows = run(db, pick(changed=True), hb_keys)
        assert {r[1] for r in rows} == expected_keys

    def test_shape_c_count_is_8400(self, db, hb_keys):
        built, rows = run(
            db, pick(aggregate={"fn": "count", "field": None}), hb_keys
        )
        assert built.shape == "SCALAR"
        assert built.columns == ("agg",)
        assert rows == [(8400,)]

    def test_shape_c_sum_avg_min_max_match_generator(self, db, hb_keys, hb_model):
        # derivation: sum of payload.load over the generator's 8,400
        # in-memory rows — B8's third path, not the pyrunner, not this SQL.
        loads = [r["payload"]["load"] for _k, r in hb_model]
        expected_sum = sum(loads)
        cases = {
            "sum": q6(Decimal(expected_sum)),
            "avg": q6(Decimal(expected_sum) / Decimal(len(loads))),
            "min": Decimal(min(loads)),
            "max": Decimal(max(loads)),
        }
        for fn, expected in cases.items():
            _b, rows = run(
                db,
                pick(aggregate={"fn": fn, "field": "payload.load"}),
                hb_keys,
            )
            assert len(rows) == 1
            got = rows[0][0]
            assert got == expected, f"{fn}: SQL {got} != generator {expected}"

    def test_shape_d_day_is_7_buckets_of_1200(self, db, hb_keys):
        built, rows = run(
            db,
            pick(bucket="day", aggregate={"fn": "count", "field": None}),
            hb_keys,
        )
        assert built.shape == "BUCKET"
        assert built.columns == ("bucket", "agg")
        assert len(rows) == 7  # AC-9: R17's span is seven whole UTC days
        assert all(n == 1200 for _label, n in rows)  # 50 senders × 24 hours
        labels = [label for label, _n in rows]
        # R15: fixed-width UTC ISO-8601 — text order is time order.
        assert all(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", label)
            for label in labels
        )
        assert labels == sorted(labels)

    def test_shape_d_hour_is_168_buckets_of_50(self, db, hb_keys):
        _b, rows = run(
            db,
            pick(bucket="hour", aggregate={"fn": "count", "field": None}),
            hb_keys,
        )
        # R5: one beat per sender per hour, 7 × 24 hours → 168 buckets of 50.
        assert len(rows) == 168
        assert all(n == 50 for _label, n in rows)

    def test_shape_d_cap_caps_buckets(self, db, hb_keys):
        _b, rows = run(
            db,
            pick(bucket="day", aggregate={"fn": "count", "field": None}, cap=3),
            hb_keys,
        )
        assert len(rows) == 3  # B5a: on BUCKET the cap caps buckets


# ═════════════════════════════════════════════════════════════════════════
# 2 · B11 — namespacing, tested directly, and the pinned merge test
# ═════════════════════════════════════════════════════════════════════════

class _Frag:
    """A stand-in with compile.py's Compiled shape (sql, params)."""

    def __init__(self, sql, params):
        self.sql = sql
        self.params = params


class TestNamespace:
    def test_rewrites_sql_and_rekeys_params(self):
        frag = _Frag(
            "xpr.add((%(p0)s)::float8, (%(p1)s)::float8, (%(p0)s)::float8)",
            {"p0": 1.5, "p1": 2.5},
        )
        sql, params = builder.namespace(frag, "cc0")
        assert sql == (
            "xpr.add((%(cc0_p0)s)::float8, (%(cc0_p1)s)::float8, "
            "(%(cc0_p0)s)::float8)"
        )
        assert params == {"cc0_p0": 1.5, "cc0_p1": 2.5}
        assert "%(p0)s" not in sql  # every occurrence rewritten, not the first

    def test_prefix_vocabulary_is_closed(self):
        frag = _Frag("(%(p0)s)::float8", {"p0": 1})
        for bad in ("", "0cc", "cc_0", "flt-", "p rb"):
            with pytest.raises(ValueError):
                builder.namespace(frag, bad)

    def test_unexpected_bind_name_is_refused(self):
        # If compile.py ever names a bind anything but p<n>, a silent
        # partial rewrite would be B11's failure again — so it raises.
        with pytest.raises(ValueError):
            builder.namespace(_Frag("%(q0)s", {"q0": 1}), "cc0")

    def test_merge_params_refuses_any_collision(self):
        into = {}
        builder.merge_params(into, {"cc0_p0": 1})
        with pytest.raises(ValueError):
            builder.merge_params(into, {"cc0_p0": 1})  # same value: still a bug


class TestB11MergeTest:
    """The pinned merge test, exactly as B11 writes it: a pick with two
    computed columns and a filter whose literals are three DIFFERENT
    numbers."""

    PICK = dict(
        computed=[
            {"name": "cc_a", "expr": "$.payload.load + 111"},
            {"name": "cc_b", "expr": "$.payload.load + 222"},
        ],
        filter="$.payload.load > 333",
    )

    def test_merge(self, hb_keys):
        built = builder.build(pick(**self.PICK), hb_keys)

        # (i) the merged params dict has three distinct keys for the three
        # literals, one per fragment, each carrying that fragment's prefix.
        homes = {}
        for literal in (111, 222, 333):
            keys = [k for k, v in built.params.items() if v == literal]
            assert len(keys) == 1, f"literal {literal} bound {len(keys)} times"
            homes[literal] = keys[0]
        assert homes[111].startswith("cc0_")
        assert homes[222].startswith("cc1_")
        assert homes[333].startswith("flt_")

        # (ii) no key appears twice with different values — structurally
        # guaranteed by merge_params raising on ANY duplicate key; assert
        # the guarantee is the one in force.
        with pytest.raises(ValueError):
            builder.merge_params(dict(built.params), {homes[111]: 999})

        # (iii) each fragment's placeholders in the final SQL all carry
        # that fragment's prefix, and nothing un-namespaced remains.
        own = {"collection", "sort_path", "agg_path", "win_path", "cap"}
        for name in re.findall(r"%\((\w+)\)s", built.sql):
            assert name in own or re.fullmatch(
                r"(cc\d+|flt|agg|win|prb[AB]\d+)_(p\d+|ctx)", name
            ), f"un-namespaced bind {name!r} in the statement"
        assert "%(p0)s" not in built.sql  # the raw compiler spelling is gone
        # every bind the statement names has a value (executability half
        # is proven on the database below)
        for name in set(re.findall(r"%\((\w+)\)s", built.sql)):
            assert name in built.params

    def test_merged_statement_runs(self, db, hb_keys, hb_model):
        """The regression B11 names is a wrong number that runs clean —
        so the merged statement is also RUN and its answer checked against
        the generator's model."""
        built, rows = run(db, pick(**self.PICK), hb_keys)
        expected = sum(1 for _k, r in hb_model if r["payload"]["load"] > 333)
        assert len(rows) == expected  # load is 0–100: the filter keeps none
        assert expected == 0

        # The same two fragments with the filter loosened: counts match the
        # model, and cc_a/cc_b carry their OWN literals (111 vs 222) —
        # the exact value-swap namespacing exists to prevent.
        loose = dict(self.PICK, filter="$.payload.load > 90")
        built, rows = run(db, pick(**loose), hb_keys)
        expected_keys = {
            k for k, r in hb_model if r["payload"]["load"] > 90
        }
        assert {r[1] for r in rows} == expected_keys
        for row in rows:
            record = row[2] if isinstance(row[2], dict) else json.loads(row[2])
            load = record["payload"]["load"]
            assert row[3] == load + 111  # cc_a
            assert row[4] == load + 222  # cc_b


# ═════════════════════════════════════════════════════════════════════════
# 3 · AC-24(c) — no float8 / double precision in agg, bucket, window SQL
# ═════════════════════════════════════════════════════════════════════════

class TestAC24c:
    """Ops 6, 7 and 8 stay in numeric end to end.  Ops 2 and 3 are exempt
    by §7.2's last paragraph (the compiler's float8 world is where §5's
    defect deliberately lives), so the picks here carry no expression."""

    PICKS = [
        dict(aggregate={"fn": "sum", "field": "payload.load"}),
        dict(aggregate={"fn": "avg", "field": "payload.load"}),
        dict(aggregate={"fn": "min", "field": "payload.load"}),
        dict(aggregate={"fn": "max", "field": "payload.load"}),
        dict(aggregate={"fn": "count", "field": None}),
        dict(bucket="day", aggregate={"fn": "count", "field": None}),
        dict(bucket="hour", aggregate={"fn": "sum", "field": "payload.load"}),
        dict(window={"field": "payload.load"}),
        dict(window={"field": "payload.load"}, changed=True),
    ]

    @pytest.mark.parametrize("kw", PICKS)
    def test_no_float_cast(self, hb_keys, kw):
        built = builder.build(pick(**kw), hb_keys)
        assert "float8" not in built.sql
        assert "double precision" not in built.sql

    def test_numeric_read_itself_is_numeric(self):
        out = builder.numeric_read("data #> %(agg_path)s")
        assert "::numeric" in out
        assert "float8" not in out
        assert "xpr.f8" not in out and "xpr.num" not in out
        assert "jsonb_typeof" in out  # the 22P02 guard is present


# ═════════════════════════════════════════════════════════════════════════
# 4 · AC-40(c), as B3b restates it — and AC-40(e)'s code half
# ═════════════════════════════════════════════════════════════════════════

class TestAC40c:
    def fragment(self) -> str:
        return builder.CHANGED_SQL

    def test_compared_expression_appears_exactly_twice(self):
        frag = self.fragment()
        assert frag.count("data - 'ts'") == 2  # inside lag() and beside it

    def test_comparison_is_is_distinct_from_never_angle(self):
        frag = self.fragment()
        assert "IS DISTINCT FROM" in frag
        assert "<>" not in frag

    def test_no_arithmetic_outside_the_two_literals(self):
        # B3b's decidable grep: with the two literal occurrences removed,
        # no arithmetic remains in operation 9's fragment.
        residue = self.fragment().replace("data - 'ts'", "", 2)
        for forbidden in ("+", "-", "*", "/", "xpr.div", "xpr.num",
                          "xpr.f8", "sum(", "avg(", "::numeric"):
            assert forbidden not in residue, (
                f"operation 9's fragment does arithmetic: {forbidden!r} in "
                f"{residue!r}"
            )

    def test_fragment_is_emitted_verbatim_in_shape_b(self, hb_keys):
        built = builder.build(pick(changed=True), hb_keys)
        assert builder.CHANGED_SQL in built.sql
        # and the whole statement holds exactly the fragment's two
        # compared-value occurrences — nothing else compares it.
        assert built.sql.count("data - 'ts'") == 2

    def test_compared_value_is_a_builder_constant(self, hb_keys):
        # AC-40(e), the code half: the compared expression is a constant of
        # the query builder, and nothing about the request reaches it.
        assert builder.COMPARED_EXPR == "r.data - 'ts'"
        a = builder.build(pick(changed=True), hb_keys)
        b = builder.build(
            pick(changed=True, filter="$.payload.load > 50", cap=7,
                 sort={"field": "ts", "dir": "asc"}),
            hb_keys,
        )
        extract = lambda s: s[s.index("( lag("): s.index('AS "changed"')]
        assert extract(a.sql) == extract(b.sql)


# ═════════════════════════════════════════════════════════════════════════
# 5 · AC-41(a) — every multi-row statement ends in the total order
# ═════════════════════════════════════════════════════════════════════════

#: The trailing text of a statement: an ORDER BY whose LAST component is
#: `key ASC` (rows) or the group key `"bucket"`, then optionally the cap,
#: then the terminator — nothing after the order but the LIMIT (§4.1: cap
#: LAST).
_ROWS_TAIL = re.compile(
    r"ORDER BY [^;]*?\bkey ASC(\n LIMIT %\(cap\)s)?;\Z"
)
_BUCKET_TAIL = re.compile(
    r'ORDER BY "bucket"(\n LIMIT %\(cap\)s)?;\Z'
)


class TestAC41a:
    MULTI_ROW = [
        dict(),                                             # no sort at all
        dict(sort={"field": "ts", "dir": "asc"}),
        dict(sort={"field": "payload.load", "dir": "desc"}, cap=10),
        dict(computed=[{"name": "busy", "expr": "$.payload.load > 80"}],
             sort={"field": "busy", "dir": "desc"}),        # alias sort
        dict(window={"field": "payload.load"}),
        dict(changed=True),
        dict(changed=True, sort={"field": "ts", "dir": "desc"}, cap=5),
        dict(source="noun:Sample", sort={"field": "field_0", "dir": "asc"}),
    ]

    @pytest.mark.parametrize("kw", MULTI_ROW)
    def test_rows_statements_end_in_key_asc(self, hb_keys, db, kw):
        keys = hb_keys
        if kw.get("source") == "noun:Sample":
            keys = [r[0] for r in db.execute(
                KEYS_SQL, {"collection": "noun:Sample"}).fetchall()]
        built = builder.build(pick(**kw), keys)
        assert _ROWS_TAIL.search(built.sql), (
            f"multi-row statement does not end in the pinned order:\n"
            f"{built.sql}"
        )

    @pytest.mark.parametrize("kw", [
        dict(bucket="day", aggregate={"fn": "count", "field": None}),
        dict(bucket="hour", aggregate={"fn": "sum", "field": "payload.load"},
             cap=24),
    ])
    def test_bucket_statements_end_in_bucket(self, hb_keys, kw):
        built = builder.build(pick(**kw), hb_keys)
        assert _BUCKET_TAIL.search(built.sql)

    def test_scalar_is_the_stated_exemption(self, hb_keys):
        # §7.4(2): one aggregate returns a single row — nothing to order.
        built = builder.build(
            pick(aggregate={"fn": "count", "field": None}), hb_keys
        )
        assert "ORDER BY" not in built.sql


# ═════════════════════════════════════════════════════════════════════════
# 6 · AC-43(a) — the bucket expression, the closed set, the cast
# ═════════════════════════════════════════════════════════════════════════

class TestAC43a:
    def test_expression_and_cast(self, hb_keys):
        for granularity in ("day", "hour"):
            built = builder.build(
                pick(bucket=granularity,
                     aggregate={"fn": "count", "field": None}),
                hb_keys,
            )
            assert (
                f"date_trunc('{granularity}', (data ->> 'ts')::timestamptz)"
                in built.sql
            )
            # ::timestamp without the tz would return the right answer on
            # this seed by discarding the Z — it fails the criterion.
            assert not re.search(r"::timestamp(?!tz)", built.sql)

    def test_granularities_are_a_closed_set_of_two(self, hb_keys):
        assert set(builder._GRANULARITY_SQL) == {"hour", "day"}
        with pytest.raises(builder.IllegalPick):
            builder.build(
                pick(bucket="week",
                     aggregate={"fn": "count", "field": None}),
                hb_keys,
            )

    def test_label_is_the_fixed_width_utc_form(self, hb_keys):
        # R15: to_char(… AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
        built = builder.build(
            pick(bucket="day", aggregate={"fn": "count", "field": None}),
            hb_keys,
        )
        assert "AT TIME ZONE 'UTC'" in built.sql
        assert '\'YYYY-MM-DD"T"HH24:MI:SS"Z"\'' in built.sql


# ═════════════════════════════════════════════════════════════════════════
# 7 · The emission halves of B1, B2 and B3
# ═════════════════════════════════════════════════════════════════════════

class TestB1OneBucketColumn:
    def test_exactly_one_bucket_column(self, hb_keys):
        built = builder.build(
            pick(bucket="day", aggregate={"fn": "count", "field": None}),
            hb_keys,
        )
        assert built.sql.count('AS "bucket"') == 1  # the text label, only
        assert 'GROUP BY "bucket"' in built.sql
        # the inner date_trunc carries no alias of its own: the statement
        # emits exactly two names, "bucket" and "agg" (B1 writes shape D
        # without even a table alias).
        assert built.sql.count(" AS ") == 2
        assert 'AS "agg"' in built.sql
        assert " AS r" not in built.sql


class TestB2InlineReemission:
    def test_aggregate_never_references_the_alias(self, db, hb_keys, hb_model):
        p = pick(
            computed=[{"name": "loadx", "expr": "$.payload.load * 2"}],
            aggregate={"fn": "sum", "field": "loadx"},
        )
        built, rows = run(db, p, hb_keys)
        # the computed column is DEFINED, NOT EMITTED (B5a): no alias in
        # the statement at all — the 42703 is removed by construction.
        assert '"loadx"' not in built.sql
        assert built.columns == ("agg",)
        # the compiled expression appears twice, inside the numeric read
        # (jsonb_typeof guard + the cast), under the agg prefix.
        assert built.sql.count("%(agg_p0)s") == 2
        # and it RUNS, and the number is the generator's, doubled.
        expected = q6(Decimal(
            2 * sum(r["payload"]["load"] for _k, r in hb_model)
        ))
        assert rows == [(expected,)]

    def test_window_field_may_be_a_computed_column(self, db, hb_keys, hb_model):
        p = pick(
            computed=[{"name": "loadx", "expr": "$.payload.load * 2"}],
            window={"field": "loadx"},
            cap=3,
        )
        built, rows = run(db, p, hb_keys)
        # in ROWS the column IS emitted — and the window re-emits the
        # expression inline under its own prefix rather than naming it.
        assert built.sql.count('AS "loadx"') == 1
        assert "win_p0" in built.sql
        # hb-01's first three beats, rolling mean of 2×load, divisors 1/2/3
        first3 = [r["payload"]["load"] * 2
                  for k, r in hb_model if k.startswith("hb-01-")][:3]
        expected = [
            q6(Decimal(first3[0])),
            q6(Decimal(sum(first3[:2])) / 2),
            q6(Decimal(sum(first3[:3])) / 3),
        ]
        assert [r[4] for r in rows] == expected


class TestB3TheCTE:
    def test_cte_iff_operation_9(self, hb_keys):
        without = builder.build(pick(window={"field": "payload.load"}), hb_keys)
        assert "WITH picked" not in without.sql  # op 8 alone needs no CTE
        with_9 = builder.build(pick(changed=True), hb_keys)
        assert with_9.sql.startswith("WITH picked AS (")

    def test_filter_inside_limit_outside_changed_hidden(self, hb_keys):
        built = builder.build(
            pick(changed=True, filter="$.payload.load > 50", cap=5), hb_keys
        )
        cte_close = built.sql.index("\n)\n")
        inside, outside = built.sql[:cte_close], built.sql[cte_close:]
        assert "xpr.truthy(" in inside      # detail 4: filter in the CTE
        assert "xpr.truthy(" not in outside
        assert "LIMIT %(cap)s" in outside   # detail 5: LIMIT caps KEPT rows
        assert "LIMIT" not in inside
        assert 'WHERE "changed"' in outside  # detail 1
        # detail 3: changed is not displayed
        assert "changed" not in built.columns
        outer_select = outside[outside.index("SELECT"):outside.index("FROM")]
        assert "changed" not in outer_select
        # detail 6: one named window, used by the frame's two readers
        assert built.sql.count("WINDOW w AS") == 1

    def test_first_beat_convention_is_the_operator(self, db, hb_keys):
        # NULL IS DISTINCT FROM x is TRUE: hb-01-0000 is kept without any
        # special case.  (The band + 50-firsts counts are in TestShapesRun.)
        _b, rows = run(db, pick(changed=True, cap=1), hb_keys)
        assert rows[0][1] == "hb-01-0000"
