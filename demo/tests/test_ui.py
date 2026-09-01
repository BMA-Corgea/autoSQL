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

import json
import re
import pathlib
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
    # 2026-08-23, q4/GA-7: max($.l) agrees under the adopted runtime (the
    # corrected guard reads 1e300); the shown disagreement rides the
    # Unicode-digit gap in edge-01's `m` — see AC-22's dated note.
    "the disagreement": pick(
        source=EDGECASE, computed=[{"name": "biggest", "expr": "max($.m)"}]),
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
        assert py_row["c"][column] == "123"

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
        # The Python pane still answers — the reported fallback (§4.5).
        assert body["panes"]["python"]["state"] == "answered"
        # And its answer on THIS pick is zero rows, which is the right
        # answer rather than a missing one.  The filter is
        # `$.where == "alpha"`; on `noun:EdgeCase` exactly one row has a
        # `where` key and it holds an object, so expr.py's `==` is false
        # there and false (missing operand) on the other nine.  Asserted as
        # a number, not as truthiness: "the pane answered 0" and "the pane
        # did not answer" are different states and the difference is the
        # whole point of a reported fallback.
        assert body["panes"]["python"]["row_count"] == 0
        assert body["panes"]["python"]["rows"] == []
        assert body["page"]["total"] == 0

    def test_the_reported_fallback_really_does_render_pythons_rows(self, conn):
        """The same refusal with rows behind it, so §4.5's *"the Python pane
        shows Python's answer"* is watched producing some.

        Same probe, same member, same row — the container reaches `==`
        through a computed column instead of through the filter, so nothing
        is filtered away and all ten rows survive to the pane.
        """
        body = run(conn, pick(
            source=EDGECASE,
            computed=[{"name": "peek", "expr": '$.where == "alpha"'}]))
        assert body["refusal"]["layer"] == 2
        assert body["refusal"]["member"] == "b"
        assert body["refusal"]["row_key"] == "edge-02"
        assert body["panes"]["sql"]["state"] == "abandoned"
        assert body["panes"]["sql"]["rows"] == []
        py = body["panes"]["python"]
        assert py["state"] == "answered"
        assert py["row_count"] == 10
        assert len(py["rows"]) == 10
        assert "peek" in py["columns"]
        # No verdict is claimed: one pane has no answer to compare.
        assert body["verdict"] == "no-compare"


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


class _RecordingCursor:
    """The same spy, one level down, on the cursor the SQL pane executes on.

    Measured, and the reason this is a wrapper rather than a patched
    method: psycopg 3.3.4's ``Cursor`` refuses attribute assignment —
    ``AttributeError: 'Cursor' object attribute 'execute' is read-only`` —
    so ``cur.execute = spy`` cannot be done at all.  Wrapping is also the
    truer shape: the real cursor is untouched, and every call still reaches
    it, so what the spy records is what the driver was actually handed.
    """

    def __init__(self, real, log):
        self._real = real
        self._log = log

    def execute(self, statement, params=None, **kw):
        self._log.append(str(statement))
        self._real.execute(statement, params, **kw)
        return self

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __iter__(self):
        return iter(self._real)


@pytest.fixture
def recorded(conn, monkeypatch):
    log: list = []
    real_cursor_factory = db.exact_json_cursor

    def spying_cursor(c):
        return _RecordingCursor(real_cursor_factory(getattr(c, "_real", c)), log)

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

    def test_the_sort_slots_field_name_is_bound_and_not_written(self, conn):
        """The sort slot's half of AC-28, on a name the slot may hold.

        Operation 4 does not go through ``compile.py`` — the builder emits
        ``r.data #> %(sort_path)s`` directly — so the criterion has to be
        asserted here separately from the computed-column case above.
        """
        body = run(conn, pick(
            sort={"field": "payload.load", "dir": "desc"}, cap=5))
        assert body["accepted"] is True
        parameterised = body["sql"]["parameterised"]
        assert "%(sort_path)s" in parameterised
        assert "payload" not in parameterised and "load" not in parameterised
        values = [p["value"] for p in body["sql"]["params"]]
        assert '["payload", "load"]' in values

    def test_a_hostile_field_name_in_the_sort_slot_is_refused_by_name(
        self, conn
    ):
        """W13-2, and the reason the test above uses an ordinary name.

        A field slot is not an expression: operation 4's control is a
        ``select`` over the collection's own key names.  ``a";b`` is not a
        name any single spelling carries to both calculators — measured,
        twice, in ``demo/server/app.py :: _as_dollar_path`` — so the server
        refuses it at layer 1 instead of handing each pane its own reading.

        AC-28's requirement still holds, and holds more strongly: the name
        reaches neither the SQL text nor the parameter list, because no
        statement was built.
        """
        body = run(conn, pick(
            sort={"field": HOSTILE_FIELD, "dir": "asc"}, cap=5))
        assert body["accepted"] is False
        assert body["refusal"]["layer"] == 1
        assert body["refusal"]["kind"] == "field"
        assert body["refusal"]["construct"] == HOSTILE_FIELD
        assert body["refusal"]["why"]
        assert body["refusal"]["sql_existed"] is False
        assert body["refusal"]["statement_sent"] is False
        assert body["sql"]["parameterised"] is None
        assert body["sql"]["params"] == []
        for side in ("sql", "python"):
            assert body["panes"][side]["state"] == "not-asked"
        # And the rows are all still there.
        assert conn.execute(
            "SELECT count(*) FROM demo.records"
        ).fetchone()[0] == 10410

    @pytest.mark.parametrize("field", [
        '$["a\";b"]',   # the bracket spelling builder._field_path misreads
        "$.l[0]",        # an index step, same misreading
        "$",             # the whole record
    ])
    def test_every_slot_spelling_the_two_panes_would_split_on_is_refused(
        self, conn, field
    ):
        """The fence, over each slot that holds a field, not just the sort.

        Each of these parses cleanly on the Python side and is misread by
        the SQL side's ``_field_path``, which is exactly the shape plan
        §8.1's failure mode 1 takes: two readings, one comparison, and an
        agreement that means nothing.
        """
        for slot, extra in (
            ("sort", {"dir": "asc"}),
            ("window", {}),
        ):
            body = run(conn, pick(**{slot: {"field": field, **extra}}))
            assert body["accepted"] is False, (slot, field)
            assert body["refusal"]["kind"] == "field", (slot, field)
            assert field in body["refusal"]["why"], (slot, field)

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


# ═════════════════════════════════════════════════════════════════════════
# The routes' own edges — a bad request is answered, not crashed
# ═════════════════════════════════════════════════════════════════════════

class TestABadRequestIsAnswered:
    """DR-2's rule for the pick body, applied to the two routes that take
    a pick in the query string.

    Measured before it was fixed: ``?pick={not json`` came back as HTTP
    500 out of an unhandled ``JSONDecodeError``, which tells a screen and
    a reader nothing.  A refusal names the parameter and the reason.
    """

    @pytest.mark.parametrize("raw,expected", [
        ("{not json", "not JSON"),
        ("[1,2,3]", "must be a JSON object"),
        ('"a string"', "must be a JSON object"),
    ])
    def test_a_malformed_pick_parameter_is_a_422_that_says_why(
        self, client, raw, expected
    ):
        response = client.get("/api/operations", params={"pick": raw})
        assert response.status_code == 422
        assert expected in response.json()["detail"]

    def test_a_well_formed_pick_parameter_still_re_derives_the_contract(
        self, client
    ):
        response = client.get(
            "/api/operations",
            params={"pick": json.dumps(pick(bucket="day",
                                            aggregate={"fn": "count",
                                                       "field": None}))},
        )
        assert response.status_code == 200
        contract = response.json()
        assert contract["shape"] == legality.BUCKET
        disabled = {o["n"] for o in contract["operations"] if not o["enabled"]}
        assert disabled == {4, 8, 9}
        for o in contract["operations"]:
            if not o["enabled"]:
                assert o["why"], o["n"]

    def test_an_unknown_source_on_the_fields_route_is_a_422(self, client):
        response = client.get("/api/fields", params={"source": "noun:Nope"})
        assert response.status_code == 422
        assert "closed set" in response.json()["detail"]


# ═════════════════════════════════════════════════════════════════════════
# W14 — the screen.  AC-25, AC-40(e), AC-43(d), plus B17, B18, B19, B25,
# B28–B31 and the anti-stale-bundle guard of the plan's risk 7.
#
# Locate §3.1 puts AC-25, AC-40(e) and AC-43(d) in this file; W13 owns the
# five above and said so in the module docstring.  These are W14's.
#
# WHY THESE ARE CONTRACT AND ARTEFACT TESTS AND NOT BROWSER TESTS — B22.
# Playwright is not installed (locate §6.2) and AC-32 forbids fetching it.
# So the shape of a control is asserted where the shape is DECIDED — in
# `GET /api/operations`, which `pick.jsx` renders and invents nothing on
# top of — and the things that live only in the built page are asserted
# against the committed bundle and the committed stylesheet, which are the
# exact bytes a reviewer's browser will run.  A browser test would assert
# what one rendered page happened to contain; these assert what the screen
# CAN contain, on every run, offline.
# ═════════════════════════════════════════════════════════════════════════

import hashlib          # noqa: E402
import subprocess       # noqa: E402

_STATIC = _DEMO_DIR / "static"
_FRONTEND = _DEMO_DIR / "frontend"
_BUNDLE = _STATIC / "js" / "app.js"
_VENDOR_BUNDLE = _STATIC / "js" / "vendor.js"
_DEMO_CSS = _STATIC / "demo.css"
_DEMO_SPRITE = _STATIC / "icons-demo.svg"
_GIMS_SPRITE = _DEMO_DIR / "vendor" / "icons.svg"

#: The order build.mjs hashes in.  Kept here rather than parsed out of
#: build.mjs so that a build script quietly dropping a file from the list
#: fails this test instead of hiding inside it.
_UI_SOURCES = [
    "demo/vendor/ui.jsx",
    "demo/frontend/icons.jsx",
    "demo/frontend/pick.jsx",
    "demo/frontend/verdict.jsx",
    "demo/frontend/rail.jsx",
    "demo/frontend/panes.jsx",
    "demo/frontend/sqlpane.jsx",
    "demo/frontend/app.jsx",
]


def _sprite_ids(path: Path) -> set:
    return set(re.findall(r'<symbol id="([^"]+)"', path.read_text()))


def _bundle_text() -> str:
    return _BUNDLE.read_text()


# ─────────────────────────────────────────────────────────────────────────
# AC-25 — every operation reachable, and the shape of the three that are
#         ruled rather than left open
# ─────────────────────────────────────────────────────────────────────────

class TestAllNineOperationsAreReachable:
    """AC-25, in the one place the nine controls are decided (B22).

    ``operations.py`` is the single source of truth and ``pick.jsx``
    renders it; a control the contract does not carry cannot appear on
    the screen, and a control it does carry cannot be missing from it.
    """

    def test_all_nine_operations_are_present_and_named(self, client):
        contract = client.get("/api/operations").json()
        ops = contract["operations"]
        assert [o["n"] for o in ops] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
        for o in ops:
            assert o["label"], o["n"]
            assert o["controls"], f"operation {o['n']} has no control at all"

    def test_every_operation_is_reachable_from_the_initial_pick(self, client):
        """Reachable means: enabled on the screen's own opening state, or
        enabled by a pick a person can make from it.  Nothing is reachable
        only by editing JSON."""
        contract = client.get("/api/operations").json()
        assert all(o["enabled"] for o in contract["operations"]), (
            "the opening state greys an operation; a reader would have to "
            "guess what un-greys it"
        )

    def test_operation_7_offers_exactly_two_granularities(self, client):
        """Q20's own option text, and no week, month or free-text unit."""
        op7 = next(o for o in client.get("/api/operations").json()["operations"]
                   if o["n"] == 7)
        assert len(op7["controls"]) == 1
        values = [o["value"] for o in op7["controls"][0]["options"]]
        assert values == ["off", "hour", "day"]
        assert op7["ctl_fixed"], "the absence has to be stated on the screen"

    def test_operation_8_offers_a_field_and_nothing_else(self, client):
        """R14: width 3, trailing, arithmetic mean are all FIXED — so there
        is deliberately no width box, no direction switch and no second
        aggregate.  AC-25 tests exactly this absence."""
        op8 = next(o for o in client.get("/api/operations").json()["operations"]
                   if o["n"] == 8)
        assert len(op8["controls"]) == 1
        assert op8["controls"][0]["name"] == "field"
        assert op8["controls"][0]["kind"] == "select"
        names = {c["name"] for c in op8["controls"]}
        assert not (names & {"width", "direction", "aggregate", "fn", "size"})
        assert op8["ctl_fixed"]

    def test_operation_9_offers_a_toggle_and_no_picker(self, client):
        """R13 and AC-40(e): an on/off toggle is the only control, and
        there must be no picker for what it compares."""
        op9 = next(o for o in client.get("/api/operations").json()["operations"]
                   if o["n"] == 9)
        assert len(op9["controls"]) == 1
        assert op9["controls"][0]["kind"] == "toggle"
        assert op9["kind"] == "toggle"
        assert op9["ctl_fixed"]

    def test_the_screen_renders_no_control_the_contract_did_not_serve(self):
        """B22 point 2, asserted structurally against ``pick.jsx``.

        Operations 8 and 9 are the two whose SHAPE IS AN ABSENCE, so the
        assertion is a count of the form controls each one renders: one
        select for operation 8 (R14 — no width box, no direction switch,
        no second aggregate) and one checkbox for operation 9 (R13 — no
        picker for what it compares).
        """
        source = (_FRONTEND / "pick.jsx").read_text()

        def case_block(n):
            start = source.index("      case %d:" % n)
            nxt = source.find("      case %d:" % (n + 1), start)
            end = nxt if nxt >= 0 else source.index("      default:", start)
            return source[start:end]

        eight = case_block(8)
        assert eight.count("<Select") == 1, "operation 8 renders more than one select"
        assert "<input" not in eight, "operation 8 renders a text or number input"
        assert '"width"' not in eight and '"aggregate"' not in eight

        nine = case_block(9)
        assert nine.count('type="checkbox"') == 1
        assert "<Select" not in nine, "operation 9 renders a picker"
        assert nine.count("<input") == 1


# ─────────────────────────────────────────────────────────────────────────
# AC-40(e) — no picker for what operation 9 compares, anywhere
# ─────────────────────────────────────────────────────────────────────────

class TestOperationNineHasNoPicker:
    def test_the_contract_carries_one_control_for_operation_9(self, client):
        for source in ("noun:Heartbeat",):
            contract = client.get(
                "/api/operations",
                params={"pick": json.dumps(pick(source=source, changed=True))},
            ).json()
            op9 = next(o for o in contract["operations"] if o["n"] == 9)
            assert [c["kind"] for c in op9["controls"]] == ["toggle"]

    def test_the_ctl_fixed_note_states_the_absence_in_words(self, client):
        op9 = next(o for o in client.get("/api/operations").json()["operations"]
                   if o["n"] == 9)
        note = op9["ctl_fixed"].lower()
        assert "toggle" in note
        assert "no picker" in note

    def test_the_built_bundle_renders_that_note(self):
        """The absence leaves no trace unless it is drawn, so the note has
        to survive into the page a person actually loads."""
        assert "ctl-fixed" in _bundle_text()


# ─────────────────────────────────────────────────────────────────────────
# AC-43(d) — the session time zone is on the screen, beside the other one
# ─────────────────────────────────────────────────────────────────────────

class TestTheSessionValuesAreOnTheScreen:
    def test_the_pick_response_carries_both_pinned_values(self, conn):
        answer = run(conn, pick(bucket="day",
                                aggregate={"fn": "count", "field": None}))
        assert answer["pinned"]["time_zone"] == settings.TIME_ZONE
        assert answer["pinned"]["extra_float_digits"] == settings.EXTRA_FLOAT_DIGITS

    def test_the_built_bundle_prints_both_of_them_side_by_side(self):
        """They live NOWHERE else on the screen (§9.3), which is the whole
        reason AC-43(d) is a separate part: the time zone is what makes a
        day's bucket seven and not eight, and nothing else on the page
        would tell a reader what it was."""
        text = _bundle_text()
        assert "extra_float_digits = " in text
        assert "TimeZone = " in text


# ─────────────────────────────────────────────────────────────────────────
# B17 — two sprites, one resolver, and no id in common
# ─────────────────────────────────────────────────────────────────────────

class TestTheTwoSprites:
    """The day GIMS adds an ``i-sort`` of its own, this fails — rather
    than the demo silently shadowing it."""

    def test_the_two_sprites_share_no_id(self):
        shared = _sprite_ids(_GIMS_SPRITE) & _sprite_ids(_DEMO_SPRITE)
        assert shared == set(), (
            f"{sorted(shared)} exist in BOTH sprites: the resolver would "
            "silently shadow GIMS's shapes"
        )

    def test_the_demo_sprite_carries_exactly_the_eighteen(self):
        assert len(_sprite_ids(_DEMO_SPRITE)) == 18

    def test_the_vendored_sprite_is_still_fifty_four_symbols(self):
        assert len(_sprite_ids(_GIMS_SPRITE)) == 54

    def test_the_resolvers_two_lists_match_the_two_sprite_files(self):
        """The resolver decides from a literal list, so the list has to be
        the file.  Parsed rather than imported: there is no JavaScript
        runtime in this suite, and there must not need to be (AC-36)."""
        source = (_FRONTEND / "icons.jsx").read_text()

        def listed(name):
            body = re.search(name + r" = \[(.*?)\];", source, re.S).group(1)
            return {m for m in re.findall(r'"([^"]+)"', body)}

        assert listed("VENDORED") == {i[2:] for i in _sprite_ids(_GIMS_SPRITE)}
        assert listed("DEMO_ONLY") == {i[2:] for i in _sprite_ids(_DEMO_SPRITE)}

    def test_the_vendored_sprite_is_checked_first(self):
        """B17: i-play, i-plus and i-search exist in both drawings with
        different path data, and GIMS's shapes are the ones that render."""
        source = (_FRONTEND / "icons.jsx").read_text()
        assert "VENDORED_SET.has(name)" in source
        assert source.index("VENDORED_SET.has(name)") < source.index("DEMO_SPRITE +")


# ─────────────────────────────────────────────────────────────────────────
# B18 — demo.css declares no token, so it cannot fork watery.css
# ─────────────────────────────────────────────────────────────────────────

class TestDemoCssIsNotAForkOfWatery:
    """The one assertion that keeps a silent copy of GIMS's stylesheet out
    of the demo.  The approved mock inlines a near-copy of watery's
    ``:root`` because a mock has to be a single file; copying that block
    into demo.css would defeat D1's drift check completely, because a
    fragment cannot be checksummed against its source."""

    def test_demo_css_declares_no_custom_property_on_root(self):
        css = _DEMO_CSS.read_text()
        blocks = re.findall(r":root\s*\{([^}]*)\}", css)
        declared = [line for b in blocks
                    for line in re.findall(r"^\s*--", b, re.M)]
        assert declared == [], f"demo.css declares {len(declared)} :root tokens"

    def test_demo_css_declares_no_custom_property_at_all(self):
        """Stronger than B18's own grep, and for the same reason: moving
        the fork off ``:root`` would still be a fork."""
        assert re.findall(r"^\s*--[A-Za-z]", _DEMO_CSS.read_text(), re.M) == []

    def test_demo_css_does_not_redefine_waterys_own_primitives(self):
        """Part 5.1's reused-unchanged list.  A rule for any of these here
        would be a restyle of GIMS's components under another name."""
        css = _DEMO_CSS.read_text()
        for primitive in (".panel", ".panel-head", ".panel-body", ".panel-title",
                          ".icon-chip", ".count-pill", ".btn-primary", ".field",
                          ".field-label", ".toggle"):
            assert not re.search(r"^\s*\%s\s*\{" % re.escape(primitive), css, re.M), (
                f"demo.css restyles {primitive}, which is watery.css's"
            )

    def test_the_page_links_the_vendored_sheets_before_its_own(self):
        html = (_STATIC / "index.html").read_text()
        order = [html.index(f'/vendor/styles/{n}.css')
                 for n in ("watery", "dashboard", "shell", "components")]
        assert order == sorted(order)
        assert max(order) < html.index("/static/demo.css")

    def test_these_two_files_alone_are_off_host_clean(self):
        """A NARROW check, and it says so — it is NOT the AC-32 guard.

        This test used to be named
        ``test_nothing_on_the_page_is_fetched_from_another_host``, which was
        a promise it could not keep.  It reads exactly two files, so it was
        structurally unable to see the one real off-host fetch this build
        shipped with: ``watery.css:8`` imported Inter from Google on every
        page load, and this test passed the whole time.  A reviewer later
        demonstrated the same blind spot by planting a telemetry beacon in
        ``app.js`` and watching this test report ``1 passed``.

        A test that cannot fail for the reason it was written is worse than
        no test, because it is *read* as coverage.  So it is renamed to what
        it actually does, and the real guard — a sweep over every asset the
        page actually loads, bundles and vendored sheets included — lives in
        ``test_isolation.py`` and runs in this same suite.

        The last assertion below is the one that matters: it fails if that
        real sweep is ever deleted, so this narrow check can never quietly
        become the only thing standing."""
        html = (_STATIC / "index.html").read_text()
        css = _DEMO_CSS.read_text()
        for text, name in ((html, "index.html"), (css, "demo.css")):
            assert "//fonts.googleapis.com" not in text, name
            assert "//fonts.gstatic.com" not in text, name
            assert "http://" not in text.replace("http://127.0.0.1", ""), name
            assert "https://" not in text, name

        # The real AC-32 sweep must exist. If someone deletes it, this fails
        # rather than leaving the two-file check above as the only guard.
        isolation = (pathlib.Path(__file__).parent / "test_isolation.py").read_text()
        assert "AC-32" in isolation and "ac32" in isolation.lower(), (
            "test_isolation.py no longer carries the AC-32 off-host sweep. "
            "This two-file check is NOT a substitute for it — it is the check "
            "that failed to notice watery.css:8 fetching Inter from Google."
        )

    def test_inter_is_committed_and_declared(self):
        fonts = sorted(p.name for p in (_STATIC / "fonts").glob("*.woff2"))
        assert fonts, "D11 requires the woff2 files to be committed"
        css = _DEMO_CSS.read_text()
        assert "@font-face" in css
        for f in fonts:
            assert f in css, f"{f} is committed but nothing declares it"


# ─────────────────────────────────────────────────────────────────────────
# B19 — the committed bundles survive a clone
#
# B19 names ``demo/tests/test_isolation.py`` for this.  It is here because
# that file belongs to another work item and was being edited alongside
# this one; the assertion is identical wherever it lives, and moving it is
# a cut and paste.
# ─────────────────────────────────────────────────────────────────────────

class TestTheBundlesAreCommitted:
    """A bundle that exists on the build machine and not in a fresh clone
    is the worst shape a criterion can have: AC-36 would pass here and
    fail for everyone else.  ``.gitignore`` ignores ``dist/`` and
    ``build/`` at any depth, which is exactly why the bundles are written
    to ``demo/static/js/``."""

    @pytest.mark.parametrize("name", ["app.js", "vendor.js"])
    def test_the_bundle_is_not_git_ignored(self, name):
        path = _STATIC / "js" / name
        assert path.is_file(), f"{path} is missing"
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "check-ignore", "-q", str(path)],
            capture_output=True, text=True,
        )
        # exit 0 = ignored, 1 = NOT ignored, >1 = the command itself failed
        assert result.returncode != 0, f"demo/static/js/{name} is git-ignored"
        assert result.returncode == 1, (
            f"git check-ignore errored on {name}: {result.stderr}"
        )

    def test_no_bundle_lives_under_a_dist_or_build_directory(self):
        strays = [p for p in _DEMO_DIR.rglob("*.js")
                  if "dist" in p.parts or "build" in p.parts]
        assert strays == [], f"bundles under an ignored directory: {strays}"

    def test_index_html_and_the_static_assets_are_present(self):
        for rel in ("index.html", "demo.css", "icons-demo.svg",
                    "js/app.js", "js/vendor.js"):
            assert (_STATIC / rel).is_file(), rel


# ─────────────────────────────────────────────────────────────────────────
# The plan's risk 7 — a stale bundle is worse than a missing one
# ─────────────────────────────────────────────────────────────────────────

class TestTheBundleIsNotStale:
    """Someone edits a .jsx and forgets ``./run-demo build-ui``, so the
    screen a reviewer sees is not the screen the source describes.
    ``build-ui`` records a sha256 over the concatenated sources in
    ``demo/manifest.json``; this recomputes it."""

    def test_the_manifest_records_the_source_digest(self):
        manifest = json.loads((_DEMO_DIR / "manifest.json").read_text())
        assert "ui:frontend-sources:sha256" in manifest, (
            "run ./run-demo build-ui — it writes this key"
        )

    def test_the_bundle_was_built_from_these_exact_sources(self):
        digest = hashlib.sha256()
        for rel in _UI_SOURCES:
            path = _REPO_ROOT / rel
            assert path.is_file(), rel
            digest.update(rel.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        manifest = json.loads((_DEMO_DIR / "manifest.json").read_text())
        assert digest.hexdigest() == manifest["ui:frontend-sources:sha256"], (
            "demo/static/js/ is stale — a front-end source changed since the "
            "last ./run-demo build-ui, so the committed bundle is not this code"
        )


# ─────────────────────────────────────────────────────────────────────────
# B25 / D5 / B28–B31 — what the built screen is not allowed to let a
# person do, and the three places it says the data is invented
# ─────────────────────────────────────────────────────────────────────────

class TestTheScreenCannotHideEitherPane:
    """AC-20 read as a property of the built page rather than of the API:
    ``.pane-pair`` carries no collapse affordance, and there is nothing on
    the screen that could suppress one side."""

    def test_the_bundle_contains_no_collapse_affordance(self):
        text = _bundle_text()
        for token in ("<details", "aria-expanded", "collapsed", "toggleP" "ane"):
            assert token not in text, f"the built screen carries {token!r}"

    def test_the_pane_pair_is_one_grid_and_not_two_frames(self):
        css = _DEMO_CSS.read_text()
        assert ".pane-pair" in css
        assert ".cmp-grid" in css
        # D5: side by side above the one breakpoint B29 allows
        assert "grid-template-columns: minmax(0,1fr) 48px minmax(0,1fr)" in css

    def test_the_frame_goes_coral_only_when_they_differ(self):
        """DR-1's second of three independent signals, and D3's one named
        exception to Watery's role table."""
        css = _DEMO_CSS.read_text()
        assert ".cmp.is-diff" in css
        assert "is-diff" in _bundle_text()

    def test_the_verdict_carries_words_and_an_icon_and_not_only_colour(self):
        """DR-1.3: AGREE and DISAGREE differ in WORDS and ICONS, so the
        banner is legible in greyscale and to a red/green-confused reader."""
        source = (_FRONTEND / "verdict.jsx").read_text()
        assert "Both panes agree" in source
        assert "panes disagree" in source
        assert '"check"' in source and '"neq"' in source


class TestTheDataSaysItIsInventedInThreePlaces:
    """B31.  (1) the masthead chip and the standing banner, as drawn;
    (2) one ``.chip.warn`` reading ``invented`` in EACH answer pane's head
    — the one addition this build makes to the approved drawing, because a
    screenshot of the panes alone carries neither of the other two;
    (3) the seed script's own header and console line, which
    ``test_data.py`` asserts."""

    def test_the_masthead_chip_and_the_standing_banner(self):
        text = _bundle_text()
        assert "invented data" in text
        assert "Every record on this screen is invented" in text

    def test_each_answer_pane_head_carries_its_own_chip(self):
        assert "pane-invented" in (_FRONTEND / "panes.jsx").read_text()
        assert "pane-invented" in _bundle_text()
        assert ".pane-invented" in _DEMO_CSS.read_text()


# ─────────────────────────────────────────────────────────────────────────
# The seven states of the approved mock are REACHABLE — driven, not drawn
# ─────────────────────────────────────────────────────────────────────────

#: The mock's seven views, as the picks the built screen loads for them.
#: Kept in step with ``demo/frontend/app.jsx``'s STATES by the test below.
SEVEN_STATES = {
    "agree": (pick(computed=[{"name": "alive", "expr": '$.status == "ok"'}],
                   cap=8, window={"field": "$.payload.load"}), "agree", None),
    "buckets": (pick(bucket="day", aggregate={"fn": "count", "field": None}),
                "agree", None),
    "changed": (pick(changed=True), "agree", None),
    # 2026-09-01 (GA-11): was max($.l).  Under the adopted corrected runtime the
    # guard reads 1e300 properly, so [1e300, 1] AGREES on both engines and this
    # state stopped being a disagreement at all -- the two failing tests were
    # telling the truth.  ACCEPTED_PICKS above had already been moved to $.m on
    # 2026-08-23; this second definition was missed.  $.m is ["\uff11\uff12\uff13", 1]:
    # Python coerces the full-width digits to 123, the ASCII gate in the vendored
    # runtime returns NULL, so max() answers 123 against 1.  That divergence is
    # real, in-subset, and survives the corrected guard.
    #
    # IT DOES NOT SURVIVE T-8.  T-6 adopted variant C, which maps non-ASCII digits
    # onto ASCII and makes both engines agree here too.  When T-8 lands variant C
    # in demo/vendor/, this state needs a new witness -- see the note in
    # demo/EVIDENCE.md.
    "disagree": (pick(source=EDGECASE,
                      computed=[{"name": "biggest", "expr": "max($.m)"}]),
                 "disagree", None),
    "gate": (pick(computed=[{"name": "hot",
                             "expr": "round($.payload.load, 1)"}]),
             "no-compare", ("expression", 1)),
    "alias": (pick(computed=[{"name": 'alive"; DROP TABLE demo.records; --',
                              "expr": '$.status == "ok"'}]),
              "no-compare", ("alias", 1)),
    "probe": (pick(source=EDGECASE,
                   computed=[{"name": "scaled", "expr": "$.huge * 1"}]),
              "no-compare", ("probe", 2)),
}


class TestTheSevenStatesAreReachable:
    """The approved mock draws seven artboards.  The built screen keeps
    the mock's own tab strip and makes it real: a tab loads that state's
    pick INTO the nine controls and runs it against the database.  So
    "reachable" is not a claim about a drawing — every one of the seven is
    a pick this suite runs, and what comes back is what the mock's view
    says comes back.
    """

    def test_the_bundle_offers_all_seven_by_id(self):
        text = _bundle_text()
        for state in SEVEN_STATES:
            assert '"' + state + '"' in text, state

    def test_the_seven_ids_in_the_source_are_exactly_these_seven(self):
        source = (_FRONTEND / "app.jsx").read_text()
        ids = re.findall(r'id: "([a-z]+)", n: \d', source)
        assert ids == ["agree", "buckets", "changed", "disagree", "gate",
                       "alias", "probe"]

    @pytest.mark.parametrize("state", sorted(SEVEN_STATES))
    def test_each_state_reaches_the_outcome_its_view_describes(self, conn, state):
        p, verdict, refusal = SEVEN_STATES[state]
        answer = run(conn, p)
        assert answer["verdict"] == verdict, state
        if refusal is None:
            assert answer["accepted"] is True
            assert answer["refusal"] is None
            assert answer["panes"]["sql"]["state"] == "answered"
            assert answer["panes"]["python"]["state"] == "answered"
        else:
            kind, layer = refusal
            assert answer["accepted"] is False
            assert answer["refusal"]["kind"] == kind
            assert answer["refusal"]["layer"] == layer

    def test_the_disagreement_state_is_located_and_not_merely_announced(self, conn):
        """D8, and the one view the whole design is arranged around."""
        p, _, _ = SEVEN_STATES["disagree"]
        answer = run(conn, p)
        c = answer["comparison"]
        assert c["differing_rows"] >= 1
        assert c["first_differing_index"] is not None
        row = next(r for r in answer["panes"]["sql"]["rows"]
                   if r["i"] == c["first_differing_index"])
        assert row["diff"], "the differing COLUMN is not marked, only the row"

    def test_the_bucketed_state_disables_more_than_the_mock_drew(self, client):
        """B5a greys one more control on the bucketed view than the drawing
        does — operation 9 as well as 4 and 8.  It is one of exactly two
        places this build exceeds the approved drawing, it comes from the
        legality matrix rather than from the screen, and it is named here
        so it cannot become a surprise."""
        p, _, _ = SEVEN_STATES["buckets"]
        contract = client.get("/api/operations",
                              params={"pick": json.dumps(p)}).json()
        assert {o["n"] for o in contract["operations"] if not o["enabled"]} == {4, 8, 9}


# ═════════════════════════════════════════════════════════════════════════
# q8 (GA-8) — the differing column sits BESIDE the marker
#
# Evan, 2026-08-23, resolving his own Q1/Q2 contradiction: *"Fix it first -
# move the differing column beside the marker"* — so that a row shows its own
# disagreement instead of the reader scrolling sideways to find the values the
# banner already named.
#
# The grid is  [SQL pane | coral spine | Python pane].  "Beside the marker"
# therefore means MIRRORED about the spine: on the left pane the differing
# column moves to the far RIGHT, on the right pane to the far LEFT, so the two
# differing values end up either side of the ≠ and touching it.
#
# The order is computed on the SERVER and published as `column_order`, which is
# why these are real end-to-end assertions rather than a grep over the bundle.
# `columns` itself is untouched, so every criterion asserting on it still holds.
# ═════════════════════════════════════════════════════════════════════════

class TestTheDifferingColumnSitsBesideTheMarker:

    def _order(self, answer):
        o = answer["column_order"]
        return o["sql"], o["python"]

    def test_both_orders_are_permutations_of_every_column(self, conn):
        """Reordering may not drop, duplicate or invent a column."""
        for name, p in ACCEPTED_PICKS.items():
            answer = run(conn, p)
            width = len(answer["panes"]["sql"]["columns"]) or \
                    len(answer["panes"]["python"]["columns"])
            if not width:
                continue
            s, y = self._order(answer)
            assert sorted(s) == list(range(width)), name
            assert sorted(y) == list(range(width)), name

    def test_an_agreeing_pick_is_left_in_its_natural_order(self, conn):
        """The reorder is for disagreement only. Nine picks in ten must not move."""
        for state in ("agree", "buckets", "changed"):
            p, _, _ = SEVEN_STATES[state]
            answer = run(conn, p)
            width = len(answer["panes"]["sql"]["columns"])
            s, y = self._order(answer)
            assert s == list(range(width)), state
            assert y == list(range(width)), state

    def test_the_differing_column_is_adjacent_to_the_spine_on_both_sides(self, conn):
        """The whole of q8, stated once."""
        p, _, _ = SEVEN_STATES["disagree"]
        answer = run(conn, p)
        rows = answer["panes"]["sql"]["rows"]
        diffs = sorted({j for r in rows if r.get("diff") for j in r["diff"]})
        assert diffs, "this state must actually differ, or the test proves nothing"

        s, y = self._order(answer)
        # SQL is LEFT of the spine: its differing columns are the last ones.
        assert s[-len(diffs):] == diffs
        # Python is RIGHT of the spine: its differing columns are the first ones.
        assert y[:len(diffs)] == diffs

    def test_the_two_orders_mirror_each_other_about_the_spine(self, conn):
        """Not merely 'both moved' — the same block, flipped across the marker,
        so the eye travels the shortest distance between the two values."""
        p, _, _ = SEVEN_STATES["disagree"]
        answer = run(conn, p)
        s, y = self._order(answer)
        rows = answer["panes"]["sql"]["rows"]
        diffs = sorted({j for r in rows if r.get("diff") for j in r["diff"]})
        k = len(diffs)
        assert s[-k:] == y[:k], "the differing block is not mirrored"
        assert s[:-k] == y[k:], "the untouched columns are not in the same relative order"

    def test_the_untouched_columns_keep_their_relative_order(self, conn):
        """Moving the differing column must not shuffle everything else."""
        p, _, _ = SEVEN_STATES["disagree"]
        answer = run(conn, p)
        s, _ = self._order(answer)
        rows = answer["panes"]["sql"]["rows"]
        diffs = {j for r in rows if r.get("diff") for j in r["diff"]}
        rest = [j for j in s if j not in diffs]
        assert rest == sorted(rest)

    def test_the_screen_actually_follows_the_published_order(self):
        """A server-side order nothing renders is not a layout fix."""
        src = (_REPO_ROOT / "demo" / "frontend" / "panes.jsx").read_text(encoding="utf-8")
        assert "column_order" in src, "the view never reads the published order"
        bundle = (_REPO_ROOT / "demo" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "column_order" in bundle, "the built bundle is stale — run ./run-demo build-ui"
