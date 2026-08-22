"""demo/tests/test_ui.py — AC-20, AC-26, AC-27, AC-28, AC-29 (B22, B25).

**W13 owns those five here.**  Locate §3.1 also lists AC-25, AC-40(e) and
AC-43(d) in this file; those are W14's and land beside this section.

Why these are contract tests and not browser tests — **B22**: the screen
renders from a server-supplied contract, and that contract is what the
always-on tests assert.  A browser test asserts what one rendered page
happened to contain; the contract test asserts what the screen *can*
contain, on every run, offline — and it removes the possibility that the
server's idea of a pick and the screen's idea of a control ever diverge.

Every test here drives the same function the route does, and several drive
the route itself, so nothing is asserted about a code path the screen does
not take.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for _p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import legality  # noqa: E402
from demo.server import app as server_app  # noqa: E402
from demo.server import db, settings  # noqa: E402

HEARTBEAT = "noun:Heartbeat"
EDGECASE = "noun:EdgeCase"


def pick(**kw) -> dict:
    p = legality.default_pick()
    p.update(kw)
    return p


@pytest.fixture(scope="module")
def conn():
    c = db.connect(application_name="autosql-demo-ui-test")
    c.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    yield c
    c.close()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


def run(conn, p) -> dict:
    return server_app.run_pick(conn, p)


#: One accepted pick of each of the three answer shapes, plus the two that
#: exercise the interesting halves.  Every AC-20 assertion runs over all of
#: them, because "for every accepted pick" is what the criterion says.
ACCEPTED_PICKS = {
    "rows, nothing set": pick(),
    "rows, computed column": pick(
        computed=[{"name": "alive", "expr": '$.status == "ok"'}]),
    "rows, filter + sort + cap": pick(
        filter='$.status != "ok"', sort={"field": "$.ts", "dir": "desc"}, cap=10),
    "rows, rolling window": pick(window={"field": "$.payload.load"}),
    "rows, only what changed": pick(changed=True),
    "scalar, sum": pick(aggregate={"fn": "sum", "field": "$.payload.load"}),
    "bucket, count per day": pick(
        bucket="day", aggregate={"fn": "count", "field": None}),
    "the disagreement": pick(
        source=EDGECASE, computed=[{"name": "biggest", "expr": "max($.l)"}]),
}


# ═════════════════════════════════════════════════════════════════════════
# AC-20 — both panes, always, and nothing that could suppress one
# ═════════════════════════════════════════════════════════════════════════

def _walk(node, trail=""):
    """Every (path, key, value) in a JSON body."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{trail}.{k}", k, v
            yield from _walk(v, f"{trail}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{trail}[{i}]")


#: Words a field would carry if it existed to turn a pane off.  AC-20:
#: *"Neither can be hidden, collapsed by default, or switched off in the
#: UI."*  A screen can only do that if the server hands it something to do
#: it with.
_SUPPRESSION = re.compile(
    r"hidden|hide|collaps|suppress|visible|show|only|primary|secondary"
    r"|disabled|off|minimi[sz]|fold",
    re.IGNORECASE,
)


class TestBothPanesAlways:
    @pytest.mark.parametrize("label", sorted(ACCEPTED_PICKS))
    def test_both_panes_are_populated_from_the_same_rows(self, conn, label):
        body = run(conn, ACCEPTED_PICKS[label])
        assert body["accepted"] is True
        panes = body["panes"]
        assert set(panes) == {"sql", "python"}
        for side in ("sql", "python"):
            assert panes[side]["state"] == "answered", side
            assert panes[side]["row_count"] > 0, side
            assert panes[side]["rows"], side
        # The same rows: same columns, same total, same page.
        assert panes["sql"]["columns"] == panes["python"]["columns"]
        assert panes["sql"]["row_count"] == panes["python"]["row_count"]
        assert len(panes["sql"]["rows"]) == len(panes["python"]["rows"])
        assert [r["i"] for r in panes["sql"]["rows"]] == \
               [r["i"] for r in panes["python"]["rows"]]

    @pytest.mark.parametrize("label", sorted(ACCEPTED_PICKS))
    def test_no_field_could_suppress_a_pane(self, conn, label):
        """The strong form: there is no boolean anywhere under ``panes``.

        A pane is switched off by a flag, and the response carries no flag
        to switch — not one named ``visible``, and not one named anything
        else either.  Asserting the *type* catches the field nobody thought
        to name.
        """
        panes = run(conn, ACCEPTED_PICKS[label])["panes"]
        booleans = [
            path for path, _k, v in _walk(panes, "panes")
            if isinstance(v, bool)
        ]
        assert booleans == []
        offenders = [
            path for path, k, _v in _walk(panes, "panes")
            if _SUPPRESSION.search(k)
        ]
        assert offenders == []

    def test_the_comparison_is_over_the_whole_result_not_the_page(self, conn):
        """B25.  The page is 50; the comparison is 8,400."""
        body = run(conn, pick())
        assert body["panes"]["sql"]["row_count"] == 8400
        assert body["comparison"]["compared_rows"] == 8400
        assert len(body["panes"]["sql"]["rows"]) == settings.PAGE_SIZE
        assert body["page"] == {
            "start": 0, "size": 50, "total": 8400, "ordered_by": "key",
        }

    def test_a_disagreement_carries_both_panes_the_count_and_the_index(
        self, conn
    ):
        """The pick response's four required parts, on the pick that has a
        real disagreement to report (walkthrough step 11)."""
        body = run(conn, ACCEPTED_PICKS["the disagreement"])
        c = body["comparison"]
        assert body["verdict"] == "disagree"
        assert c["differing_rows"] == 1
        assert c["first_differing_index"] == 1
        assert c["sql_row_count"] == c["python_row_count"] == 10

        column = body["panes"]["sql"]["columns"].index("biggest")
        sql_row = body["panes"]["sql"]["rows"][1]
        py_row = body["panes"]["python"]["rows"][1]
        assert sql_row["diff"] == [column]
        assert py_row["diff"] == [column]
        # §5's control, firing: the same row, read two ways.
        assert sql_row["c"][column] == "1"
        assert py_row["c"][column] == "1e+300"

    def test_a_disagreement_past_the_page_is_still_on_the_page(self, conn):
        """B25's D8: *a disagreement is never below the fold of a
        paginator.*  Driven with a synthetic pair rather than a real pick,
        because no seeded pick disagrees past row 50 — and the rule has to
        hold when one does."""
        sql = {"columns": ["key"], "kinds": ["text"], "row_count": 400,
               "rows": [], "canon": [(("string", f"k{i:04d}"),)
                                     for i in range(400)]}
        python = {"columns": ["key"], "kinds": ["text"], "row_count": 400,
                  "rows": [], "canon": list(sql["canon"])}
        python["canon"][317] = (("string", "different"),)
        comparison = server_app.compare_panes(sql, python)
        assert comparison["first_differing_index"] == 317
        start = server_app._page_start(317)
        assert start <= 317 < start + settings.PAGE_SIZE


# ═════════════════════════════════════════════════════════════════════════
# AC-26 — the SQL pane: the full statement, BOTH probes, both pinned values
# ═════════════════════════════════════════════════════════════════════════

class TestTheSqlPane:
    KNOWN = pick(bucket="day", aggregate={"fn": "count", "field": None})

    def test_it_shows_the_full_statement(self, conn):
        body = run(conn, self.KNOWN)
        text = body["sql"]["pane_text"]
        assert body["sql"]["display"] in text
        # The bucket, in full, as §7.1's time-bucket rule pins it.
        assert "date_trunc('day'" in text
        assert "::timestamptz" in text
        assert 'AS "bucket"' in text

    def test_it_shows_both_probes_including_the_one_that_did_not_run(
        self, conn
    ):
        """B30: *the statement and both probes open, in full, with the probe
        that did not run stated in a comment rather than hidden.*"""
        text = run(conn, self.KNOWN)["sql"]["pane_text"]
        assert "-- probe (a)" in text
        assert "-- probe (b)" in text
        # This pick has neither a numeric-context operand nor an equality,
        # so neither probe was built — and the pane says so for each.
        assert text.count("nothing to ask") == 2

    def test_a_probe_that_ran_is_shown_with_its_answer(self, conn):
        text = run(
            conn, pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}])
        )["sql"]["pane_text"]
        assert "-- probe (b)" in text
        assert "SELECT EXISTS" in text
        assert "nothing found. the pick proceeds." in text

    def test_it_states_both_pinned_session_values(self, conn):
        """AC-26's second half, and the reason it exists: each of these
        changes the answer, and neither is visible anywhere else."""
        body = run(conn, self.KNOWN)
        assert body["pinned"] == {"extra_float_digits": "1", "time_zone": "UTC"}
        text = body["sql"]["pane_text"]
        assert "SET extra_float_digits = 1;" in text
        assert "SET TIME ZONE 'UTC';" in text

    def test_the_pinned_values_are_what_the_connection_actually_ran_at(
        self, conn
    ):
        """The pane's claim, checked against the database rather than
        against the constant it was rendered from."""
        body = run(conn, self.KNOWN)
        assert conn.execute("SHOW TimeZone").fetchone()[0] == \
            body["pinned"]["time_zone"]
        assert conn.execute("SHOW extra_float_digits").fetchone()[0] == \
            body["pinned"]["extra_float_digits"]

    def test_an_accepted_alias_is_shown_exactly_as_it_was_emitted(self, conn):
        """§9.3: the one piece of user-typed text in the statement that is
        not a bind parameter, double-quoted, visible."""
        body = run(
            conn, pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}])
        )
        assert 'AS "alive"' in body["sql"]["parameterised"]
        assert 'AS "alive"' in body["sql"]["pane_text"]
        assert "alive" in body["panes"]["python"]["columns"]

    def test_a_layer_1_refusal_says_there_is_no_sql_and_shows_none(self, conn):
        """§9.3's refusal half, and AC-16's *both panes empty*."""
        body = run(
            conn,
            pick(computed=[{"name": "rounded",
                            "expr": "round($.payload.load, 1)"}]),
        )
        assert body["accepted"] is False
        assert body["refusal"]["layer"] == 1
        assert body["refusal"]["kind"] == "expression"
        assert body["refusal"]["construct"] == "round"
        assert body["refusal"]["why"]
        assert body["refusal"]["sql_existed"] is False
        assert body["sql"]["parameterised"] is None
        assert "never built" in body["sql"]["pane_text"]
        for side in ("sql", "python"):
            assert body["panes"][side]["rows"] == []
            assert body["panes"][side]["state"] == "not-asked"

    def test_a_layer_2_refusal_names_the_probe_and_sends_nothing(self, conn):
        """§4.5: SQL existed, the probe fired, the statement never ran."""
        body = run(conn, pick(source=EDGECASE, filter='$.where == "alpha"'))
        assert body["refusal"]["layer"] == 2
        assert body["refusal"]["member"] == "b"
        assert body["refusal"]["row_key"] == "edge-02"
        assert body["refusal"]["sql_existed"] is True
        assert body["refusal"]["statement_sent"] is False
        assert body["sql"]["statement_sent"] is False
        assert body["panes"]["sql"]["state"] == "abandoned"
        # The Python pane still answers — the reported fallback.
        assert body["panes"]["python"]["state"] == "answered"
        assert body["panes"]["python"]["rows"]


# ═════════════════════════════════════════════════════════════════════════
# AC-27 — the parameterised form is what executes
# ═════════════════════════════════════════════════════════════════════════

class _Recorder:
    """A connection that answers exactly like the real one and remembers
    every statement text handed to the driver.

    The assertion below is made **at the driver boundary**, not by reading
    the code: what matters is what was executed, not what a function was
    named.
    """

    def __init__(self, real, log):
        self._real = real
        self._log = log

    def execute(self, statement, params=None, **kw):
        self._log.append(str(statement))
        return self._real.execute(statement, params, **kw) if params is not None \
            else self._real.execute(statement, **kw)

    def cursor(self, *a, **kw):
        return self._real.cursor(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def recorded(conn, monkeypatch):
    log: list = []
    real_cursor_factory = db.exact_json_cursor

    def spying_cursor(c):
        cur = real_cursor_factory(getattr(c, "_real", c))
        real_execute = cur.execute

        def execute(statement, params=None, **kw):
            log.append(str(statement))
            return real_execute(statement, params, **kw)

        cur.execute = execute
        return cur

    monkeypatch.setattr(server_app.db, "exact_json_cursor", spying_cursor)
    return _Recorder(conn, log), log


class TestWhatActuallyExecutes:
    def test_the_executed_text_still_carries_its_placeholders(self, conn):
        body = run(
            conn, pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}])
        )
        parameterised = body["sql"]["parameterised"]
        assert re.search(r"%\(\w+\)s", parameterised)
        assert "%(collection)s" in parameterised
        # The display rendering is the same statement with the values in.
        assert "%(" not in body["sql"]["display"]
        assert "'noun:Heartbeat'" in body["sql"]["display"]

    def test_the_display_rendering_never_reaches_the_driver(self, recorded):
        """AC-27, at the boundary.

        ``compile.py:445-449`` says it in its own words — *"NEVER execute
        this — the harness always executes the parameterised form."*  So:
        run a pick through a recording connection, then assert that no
        statement the driver was handed is the display rendering, and that
        none of them carries the substituted collection literal that only
        the display rendering has.
        """
        conn, log = recorded
        body = run(conn, pick(
            computed=[{"name": "alive", "expr": '$.status == "ok"'}], cap=5))
        assert log, "nothing was recorded — the spy is not on the path"
        display = body["sql"]["display"]
        assert display not in log
        for statement in log:
            assert "'noun:Heartbeat'" not in statement, statement
        # And the parameterised statement IS among them, verbatim.
        assert body["sql"]["parameterised"] in log

    def test_every_probe_also_executes_parameterised(self, recorded):
        conn, log = recorded
        body = run(conn, pick(
            computed=[{"name": "alive", "expr": '$.status == "ok"'}]))
        probe_sql = [p["sql"] for p in body["sql"]["probes"]]
        assert probe_sql
        for statement in probe_sql:
            assert "%(collection)s" in statement
            assert statement in log


# ═════════════════════════════════════════════════════════════════════════
# AC-28 — a typed JSON field name is a bind parameter, never SQL text
# ═════════════════════════════════════════════════════════════════════════

#: A field name carrying the two characters that would end a quoted
#: identifier and start a new statement.
HOSTILE_FIELD = 'a";b'


class TestFieldNamesAreBound:
    def test_a_hostile_field_name_in_a_computed_column_is_bound(self, conn):
        body = run(conn, pick(
            computed=[{"name": "peek", "expr": '$["a\\";b"]'}], cap=5))
        assert body["accepted"] is True
        parameterised = body["sql"]["parameterised"]
        assert HOSTILE_FIELD not in parameterised
        assert '";' not in parameterised
        values = [p["value"] for p in body["sql"]["params"]]
        assert HOSTILE_FIELD in values

    def test_a_hostile_field_name_in_the_sort_slot_is_bound(self, conn):
        body = run(conn, pick(
            sort={"field": HOSTILE_FIELD, "dir": "asc"}, cap=5))
        assert body["accepted"] is True
        parameterised = body["sql"]["parameterised"]
        assert HOSTILE_FIELD not in parameterised
        values = [p["value"] for p in body["sql"]["params"]]
        assert any(HOSTILE_FIELD in v for v in values)

    def test_the_row_count_is_unaffected(self, conn):
        """AC-28's second half.  The field does not exist on any row, so
        reading it changes nothing about which rows come back — which is
        what it means for the name to have stayed out of the SQL."""
        plain = run(conn, pick())
        hostile = run(conn, pick(
            computed=[{"name": "peek", "expr": '$["a\\";b"]'}]))
        assert hostile["comparison"]["sql_row_count"] == \
            plain["comparison"]["sql_row_count"] == 8400
        assert hostile["verdict"] == "agree"
        # And nothing was dropped: the demo's rows are all still there.
        assert conn.execute(
            "SELECT count(*) FROM demo.records"
        ).fetchone()[0] == 10410

    def test_the_alias_is_the_one_piece_of_typed_text_that_is_not_bound(
        self, conn
    ):
        """The criterion's own carve-out, stated as a test so it is not
        read as an oversight: a column name has no parameter position, so
        §4.10's allowlist governs it instead — and refuses this one."""
        body = run(conn, pick(
            computed=[{"name": 'alive"; DROP TABLE demo.records; --',
                       "expr": '$.status == "ok"'}]))
        assert body["accepted"] is False
        assert body["refusal"]["layer"] == 1
        assert body["refusal"]["kind"] == "alias"
        assert body["sql"]["parameterised"] is None
        assert conn.execute(
            "SELECT count(*) FROM demo.records"
        ).fetchone()[0] == 10410


# ═════════════════════════════════════════════════════════════════════════
# AC-29 — no session, no role, no saved view, no login
# ═════════════════════════════════════════════════════════════════════════
#
# Scope, stated rather than assumed.  The criterion is about **access
# control** — *"there is no login, no role and no saved-view mode"* — so
# the check runs over what a client is addressed by and keyed on: route
# paths, response headers, cookies, and response FIELD NAMES.  It is
# deliberately not a text search of the body, because §9.3 requires the SQL
# pane to print the words *session values* above the two SET statements and
# AC-26 above asserts they are there.  A check that forbade the word would
# forbid the thing AC-26 requires.

_ACCESS_CONTROL = re.compile(
    r"session|role|saved.?view|savedview|login|logout|auth|token|cookie"
    r"|permission|user|account|sign.?in|tenant",
    re.IGNORECASE,
)


class TestNoOneIsAskedWhoTheyAre:
    def test_no_route_mentions_one(self):
        paths = [getattr(r, "path", "") for r in server_app.app.routes]
        assert paths, "no routes registered"
        offenders = [p for p in paths if _ACCESS_CONTROL.search(p)]
        assert offenders == []

    def test_the_page_loads_with_no_login_and_sets_no_cookie(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "set-cookie" not in {k.lower() for k in response.headers}
        assert dict(response.cookies) == {}
        assert "www-authenticate" not in {k.lower() for k in response.headers}

    @pytest.mark.parametrize("route,method", [
        ("/api/operations", "get"),
        ("/api/fields?source=noun:Heartbeat", "get"),
    ])
    def test_the_api_routes_set_no_cookie_and_ask_for_no_identity(
        self, client, route, method
    ):
        response = getattr(client, method)(route)
        assert response.status_code == 200
        assert "set-cookie" not in {k.lower() for k in response.headers}
        offenders = [
            name for name in response.headers
            if _ACCESS_CONTROL.search(name)
        ]
        assert offenders == []

    def test_the_pick_route_answers_a_bare_request(self, client):
        response = client.post("/api/pick", json=legality.default_pick())
        assert response.status_code == 200
        assert "set-cookie" not in {k.lower() for k in response.headers}
        assert dict(response.cookies) == {}

    @pytest.mark.parametrize("label", sorted(ACCEPTED_PICKS))
    def test_no_response_field_is_named_for_one(self, conn, label):
        body = run(conn, ACCEPTED_PICKS[label])
        offenders = sorted({
            path for path, key, _v in _walk(body, "")
            if _ACCESS_CONTROL.search(key)
        })
        assert offenders == []

    def test_every_visitor_gets_the_same_nine_controls(self, client):
        """§9.4: no author/viewer split, no permission gate, no saved view.

        Two requests with nothing to tell them apart get the identical
        contract, because there is nothing the server could tell them
        apart by.
        """
        first = client.get("/api/operations").json()
        second = client.get("/api/operations").json()
        assert first == second
        assert len(first["operations"]) == 9
