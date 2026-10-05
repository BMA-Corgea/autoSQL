"""demo/tests/test_dashboard.py — T-71, the dashboard over the invented data.

The dashboard's rules live in ``demo/server/dashboard.py`` and are tested
here through its two routes and its pure functions, against the live demo
database — B22's reasoning, applied to a second screen: the contract is
what the screen *can* show, asserted offline on every run.  What only a
browser can show (the stale-answer guard, the phone layout) is driven
headless outside the suite, because the suite must pass with Node removed
from PATH (AC-36).

Criteria, by number (``.autodev/specs/T-71.md``): AC1 route, AC2 data
sets, AC3 columns in the statement, AC8 the sentence, AC9 plain words,
AC13 the page's fences, AC14 the bundle (``test_ui.py``'s digest covers
the dashboard's sources).
"""

from __future__ import annotations

import html.parser
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for _p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo.server import app as server_app  # noqa: E402
from demo.server import dashboard  # noqa: E402

_STATIC = _DEMO_DIR / "static"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    return TestClient(server_app.app)


@pytest.fixture(scope="module")
def setup(client):
    r = client.get("/api/dashboard/setup")
    assert r.status_code == 200
    return r.json()


def ds(setup, ds_id):
    return next(d for d in setup["datasets"] if d["id"] == ds_id)


def view(setup, ds_id="heartbeats", **kw):
    d = ds(setup, ds_id)
    v = {"dataset": ds_id, "columns": list(d["default_columns"]),
         "conditions": [], "sort": None, "show": None, "summary": None}
    v.update(kw)
    return v


def ask(client, v, page=0):
    r = client.post("/api/dashboard/answer", json={"view": v, "page": page})
    return r.status_code, r.json()


# ═════════════════════════════════════════════════════════════════════════
# AC1 — the page, and the screen at / left alone
# ═════════════════════════════════════════════════════════════════════════

class TestThePage:
    def test_dashboard_is_served(self, client):
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert 'src="/static/js/dashboard.js"' in r.text
        assert 'href="/static/dashboard.css"' in r.text

    def test_the_two_pane_screen_is_still_at_the_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert 'src="/static/js/app.js"' in r.text
        assert "dashboard.js" not in r.text

    def test_the_page_carries_the_same_policy_as_the_screen(self):
        def policy(name):
            text = (_STATIC / name).read_text()
            m = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', text)
            assert m, f"{name} carries no Content-Security-Policy"
            return m.group(1)
        assert policy("dashboard.html") == policy("index.html")

    def test_the_vendored_sheets_come_first_and_unedited(self):
        text = (_STATIC / "dashboard.html").read_text()
        order = [text.index(f"/vendor/styles/{n}.css")
                 for n in ("watery", "dashboard", "shell", "components")]
        assert order == sorted(order)
        assert max(order) < text.index("/static/skins/base.css") < text.index("/static/dashboard.css")

    def test_light_and_dark_follow_the_os(self):
        """AC13: no data-theme on the page and no skin switcher, so the base
        skin's prefers-color-scheme block decides."""
        text = (_STATIC / "dashboard.html").read_text()
        assert "data-theme" not in text.split("<!--")[0] + text.split("-->")[-1]
        assert "skin.js" not in text

    def test_its_own_sheet_declares_no_custom_property(self):
        """The same rule demo.css keeps (B18): only watery's token names."""
        css = (_STATIC / "dashboard.css").read_text()
        assert re.findall(r"^\s*--[A-Za-z]", css, re.M) == []

    def test_start_sh_opens_the_dashboard(self):
        text = (_REPO_ROOT / "start.sh").read_text()
        assert 'PAGE="http://127.0.0.1:${APP_PORT}/dashboard"' in text
        assert text.count('open_page "${PAGE}"') == 2


@pytest.fixture(scope="module")
def served(client):
    """Everything ``/dashboard`` pulls in, as this app serves it."""
    import test_isolation as iso

    def fetch(url):
        r = client.get(url)
        return r.status_code, r.headers.get("content-type", ""), r.content

    return iso, iso.what_the_page_loads(fetch, start="/dashboard")


class TestNothingLeavesThisHost:
    """AC13, by the same walk test_isolation.py runs from ``/``."""

    def test_the_walk_reaches_what_the_page_loads(self, served):
        _iso, pages = served
        for url in ("/dashboard", "/static/js/vendor.js", "/static/js/dashboard.js",
                    "/static/dashboard.css", "/static/skins/base.css",
                    "/vendor/styles/watery.css", "/static/fonts/inter-latin.woff2"):
            assert url in pages, f"the walk from /dashboard did not reach {url}"

    def test_nothing_it_loads_names_another_host(self, served):
        iso, pages = served
        findings = []
        for url, text in sorted(iso._text_assets(pages).items()):
            for found in iso._off_host_urls(text):
                if found not in iso._INERT_NOT_AN_ADDRESS:
                    findings.append(f"{url}: {found}")
        assert findings == []


# ═════════════════════════════════════════════════════════════════════════
# AC2 — the three data sets, in plain words, with their counts
# ═════════════════════════════════════════════════════════════════════════

class TestTheDataSets:
    def test_three_data_sets_with_their_row_counts(self, setup):
        got = [(d["id"], d["name"], d["rows"]) for d in setup["datasets"]]
        assert got == [("heartbeats", "Heartbeats", 8400),
                       ("samples", "Samples", 2000),
                       ("edge", "Edge cases", 10)]

    def test_each_says_what_it_is_in_one_line(self, setup):
        for d in setup["datasets"]:
            assert d["about"] and "\n" not in d["about"] and len(d["about"]) < 90

    def test_fields_have_plain_names(self, setup):
        hb = [f["label"] for f in ds(setup, "heartbeats")["fields"]]
        assert hb == ["Sender", "Time", "Status", "Load", "Note"]
        smp = [f["label"] for f in ds(setup, "samples")["fields"]]
        assert smp[:4] == ["ID", "Status", "Due date", "Priority"]
        assert smp[4:] == [f"Field {n}" for n in range(15)]

    def test_the_kinds_are_read_from_the_data(self, setup):
        kinds = {f["path"]: f["kind"] for f in ds(setup, "heartbeats")["fields"]}
        assert kinds == {"sender_id": "text", "ts": "time", "status": "text",
                         "payload.load": "number", "payload.note": "text"}
        kinds = {f["path"]: f["kind"] for f in ds(setup, "samples")["fields"]}
        assert kinds["due_date"] == "date" and kinds["priority"] == "number"

    def test_text_values_come_from_the_data(self, setup):
        status = next(f for f in ds(setup, "heartbeats")["fields"] if f["path"] == "status")
        assert status["values"] == ["error", "ok", "warn"]
        assert status["picker"] == "chips"
        sender = next(f for f in ds(setup, "heartbeats")["fields"] if f["path"] == "sender_id")
        assert len(sender["values"]) == 50 and sender["picker"] == "list"

    def test_the_default_question(self, setup):
        assert setup["default_view"]["dataset"] == "heartbeats"
        assert setup["default_view"]["columns"] == [
            "sender_id", "ts", "status", "payload.load", "payload.note"]
        assert setup["default_view"]["sort"] == {"field": "ts", "dir": "desc"}
        assert setup["default_views"]["samples"]["sort"] is None


# ═════════════════════════════════════════════════════════════════════════
# The answer: the table, its pages, the sentence (AC8), the columns (AC3)
# ═════════════════════════════════════════════════════════════════════════

class TestTheAnswer:
    def test_samples_is_two_thousand_rows(self, client, setup):
        status, a = ask(client, view(setup, "samples"))
        assert status == 200
        assert a["kind"] == "table"
        assert a["total"] == 2000
        assert a["sentence"] == "Samples — 2,000 rows"
        assert [c["label"] for c in a["columns"]] == ["ID", "Status", "Due date", "Priority"]
        assert len(a["rows"]) == 50
        assert a["rows"][0][0] == "smp-0000"

    def test_pages_turn_through_the_whole_answer(self, client, setup):
        _, a = ask(client, view(setup, "samples"), page=1)
        assert a["page"]["start"] == 50 and a["rows"][0][0] == "smp-0050"
        _, a = ask(client, view(setup, "samples"), page=39)
        assert a["page"]["last"] == 39 and a["rows"][-1][0] == "smp-1999"

    def test_a_page_past_the_end_shows_the_last_page(self, client, setup):
        _, a = ask(client, view(setup, "samples"), page=400)
        assert a["page"]["index"] == 39

    def test_both_engines_were_asked(self, client, setup):
        _, a = ask(client, view(setup, "heartbeats"))
        assert a["total"] == 8400
        assert a["admin"]["verdict"] == "agree"
        assert a["admin"]["compared_rows"] == 8400

    def test_cells_read_like_a_person_writes_them(self, client, setup):
        _, a = ask(client, view(setup, "heartbeats"))
        assert a["rows"][0] == ["hb-01", "Aug 14, 00:00 UTC", "ok", "18", "lima"]
        _, a = ask(client, view(setup, "samples"), page=1)
        assert a["rows"][0][2] == "Jul 31, 2026"

    def test_the_chosen_columns_are_in_the_statement(self, client, setup):
        """AC3: the statement visibly changes with the pick."""
        _, a = ask(client, view(setup, "heartbeats"))
        sql = a["admin"]["statement"]
        for alias in ('AS "Sender"', 'AS "Time"', 'AS "Status"', 'AS "Load"', 'AS "Note"'):
            assert alias in sql
        _, b = ask(client, view(setup, "heartbeats", columns=["status"]))
        assert 'AS "Status"' in b["admin"]["statement"]
        assert 'AS "Note"' not in b["admin"]["statement"]
        assert [c["label"] for c in b["columns"]] == ["Status"]

    def test_columns_keep_the_order_they_were_asked_in(self, client, setup):
        _, a = ask(client, view(setup, "heartbeats", columns=["payload.note", "sender_id"]))
        assert [c["label"] for c in a["columns"]] == ["Note", "Sender"]

    def test_no_columns_still_counts_the_rows(self, client, setup):
        _, a = ask(client, view(setup, "samples", columns=[]))
        assert a["total"] == 2000 and a["columns"] == []

    def test_a_question_it_cannot_read_is_answered_plainly(self, client, setup):
        status, a = ask(client, view(setup, "samples", columns=["nope"]))
        assert status == 422 and a["kind"] == "invalid"
        assert "nope" in a["message"]
        status, a = ask(client, {"dataset": "elsewhere"})
        assert status == 422 and a["message"] == "Pick one of the three data sets."


class TestFormatting:
    @pytest.mark.parametrize("text, want", [
        ("2026-08-20T23:00:00Z", "Aug 20, 23:00 UTC"),
        ("2026-08-14T00:00:00Z", "Aug 14, 00:00 UTC"),
        ("not a time", "not a time"),
    ])
    def test_time(self, text, want):
        assert dashboard.fmt_time(text) == want

    def test_date(self):
        assert dashboard.fmt_date("2026-09-03") == "Sep 3, 2026"

    @pytest.mark.parametrize("text, want", [
        ("8400", "8,400"), ("-523.1234", "-523.1234"), ("0", "0"),
        ("1234567.5", "1,234,567.5"), ("1e+300", "1e+300"),
    ])
    def test_number(self, text, want):
        assert dashboard.fmt_number(text) == want

    def test_number_rounded_for_display(self):
        assert dashboard.fmt_number("48.074167", places=2) == "48.07"

    def test_cells_of_every_json_type(self):
        f = dashboard.fmt_cell
        assert f("null", "null", "text") is None
        assert f("true", "boolean", "mixed") == "Yes"
        assert f('{"code":"alpha","n":7}', "object", "mixed") == "code: alpha, n: 7"
        assert f("[]", "array", "mixed") == "(empty list)"
        assert f("[1e+300,1]", "array", "mixed") == "1e+300, 1"


# ═════════════════════════════════════════════════════════════════════════
# AC9 — the Everyone view carries no machinery words
# ═════════════════════════════════════════════════════════════════════════

#: AC9's list.  Matched as words, case-insensitively, except the two
#: symbols, which are matched as written.
_MACHINERY = re.compile(
    r"\b(?:sql|python|pane|pushdown|compiler|expression|query)\b|noun:|\$\.", re.I)


class _VisibleText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def _everyone_strings(payload) -> list[str]:
    """Every string the Everyone view draws from a payload: all of it except
    the admin block and the data's own cell values."""
    out: list[str] = []

    def walk(node, key=""):
        if key in ("admin", "rows", "values", "path", "alias", "id", "range"):
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            out.append(node)

    walk(payload)
    return out


class TestPlainWords:
    def test_the_page_itself(self, client):
        p = _VisibleText()
        p.feed(client.get("/dashboard").text)
        text = " ".join(p.out)
        assert not _MACHINERY.search(text), _MACHINERY.search(text)

    def test_the_setup(self, setup):
        bad = [s for s in _everyone_strings(setup) if _MACHINERY.search(s)]
        assert bad == []

    @pytest.mark.parametrize("ds_id, columns", [
        ("heartbeats", None), ("samples", None), ("edge", None),
        ("samples", []), ("heartbeats", ["status"]),
    ])
    def test_every_answer(self, client, setup, ds_id, columns):
        v = view(setup, ds_id)
        if columns is not None:
            v["columns"] = columns
        _, a = ask(client, v)
        bad = [s for s in _everyone_strings(a) if _MACHINERY.search(s)]
        assert bad == []


# ═════════════════════════════════════════════════════════════════════════
# S2 — narrowing it down: conditions (AC4), sort and how many (AC5),
#      and the escaping of every picked value (AC11)
# ═════════════════════════════════════════════════════════════════════════

from seed import generate  # noqa: E402  — the third path: the generator's own rows

import builder  # noqa: E402

_HEARTBEATS = [__import__("json").loads(d) for _c, _k, d in generate.heartbeat_rows()]
_SAMPLES = [__import__("json").loads(d) for _c, _k, d in generate.sample_rows()]


def field(setup, ds_id, path):
    return next(f for f in ds(setup, ds_id)["fields"] if f["path"] == path)


def cond(field_path, op, **kw):
    return {"field": field_path, "op": op, **kw}


class TestConditions:
    """AC4: field → condition → value, every combination a click can make,
    each answer checked against a count made from the generator's rows."""

    def test_status_is_warn(self, client, setup):
        want = sum(1 for r in _HEARTBEATS if r["status"] == "warn")
        _, a = ask(client, view(setup, conditions=[cond("status", "eq", value="warn")],
                                sort={"field": "ts", "dir": "desc"}))
        assert a["total"] == want
        assert a["sentence"] == f"Heartbeats where Status is warn, newest first — {want:,} rows"
        assert a["admin"]["verdict"] == "agree"
        assert {r[2] for r in a["rows"]} == {"warn"}

    def test_one_of_several_values(self, client, setup):
        want = sum(1 for r in _HEARTBEATS if r["status"] in ("warn", "error"))
        _, a = ask(client, view(setup, conditions=[cond("status", "in", values=["warn", "error"])]))
        assert a["total"] == want
        assert "Status is warn or error" in a["sentence"]

    def test_all_conditions_must_match(self, client, setup):
        want = sum(1 for r in _HEARTBEATS
                   if r["status"] != "ok" and r["payload"]["load"] > 50)
        _, a = ask(client, view(setup, conditions=[
            cond("status", "ne", value="ok"), cond("payload.load", "gt", value=50)]))
        assert a["total"] == want
        assert "where Status is not ok and Load is more than 50" in a["sentence"]

    @pytest.mark.parametrize("op, lo, hi, test", [
        ("ge", 90, None, lambda x: x >= 90),
        ("le", 3, None, lambda x: x <= 3),
        ("lt", 10, None, lambda x: x < 10),
        ("eq", 42, None, lambda x: x == 42),
        ("between", 20, 30, lambda x: 20 <= x <= 30),
        ("between", 30, 20, lambda x: 20 <= x <= 30),   # the ends put in order
        ("between", 10.5, 11.5, lambda x: x == 11),
    ])
    def test_number_conditions(self, client, setup, op, lo, hi, test):
        want = sum(1 for r in _HEARTBEATS if test(r["payload"]["load"]))
        c = cond("payload.load", op, value=lo)
        if hi is not None:
            c["value2"] = hi
        _, a = ask(client, view(setup, conditions=[c]))
        assert a["total"] == want and a["admin"]["verdict"] == "agree"

    def test_a_time_on_one_day(self, client, setup):
        _, a = ask(client, view(setup, conditions=[cond("ts", "on", value="2026-08-18")]))
        assert a["total"] == 50 * 24
        assert "Time is on Aug 18" in a["sentence"]

    def test_times_after_before_and_between(self, client, setup):
        def count(test):
            return sum(1 for r in _HEARTBEATS if test(r["ts"]))
        _, a = ask(client, view(setup, conditions=[cond("ts", "after", value="2026-08-20T12:00")]))
        assert a["total"] == count(lambda t: t > "2026-08-20T12:00:00Z")
        assert "Time is after Aug 20, 12:00 UTC" in a["sentence"]
        _, a = ask(client, view(setup, conditions=[cond("ts", "before", value="2026-08-14T03:00")]))
        assert a["total"] == count(lambda t: t < "2026-08-14T03:00:00Z") == 150
        _, a = ask(client, view(setup, conditions=[
            cond("ts", "between", value="2026-08-15T00:00", value2="2026-08-15T05:00")]))
        assert a["total"] == 50 * 6

    def test_dates(self, client, setup):
        want = sum(1 for r in _SAMPLES if r.get("due_date") and r["due_date"] < "2026-08-01")
        _, a = ask(client, view(setup, "samples", conditions=[
            cond("due_date", "before", value="2026-08-01")]))
        assert a["total"] == want
        assert "Due date is before Aug 1, 2026" in a["sentence"]

    def test_blank_and_has_a_value(self, client, setup):
        missing = sum(1 for r in _SAMPLES if "due_date" not in r)
        _, a = ask(client, view(setup, "samples", conditions=[cond("due_date", "blank")]))
        assert a["total"] == missing and "Due date is blank" in a["sentence"]
        _, a = ask(client, view(setup, "samples", conditions=[cond("due_date", "present")]))
        assert a["total"] == 2000 - missing and "Due date has a value" in a["sentence"]

    def test_no_rows_match_is_said_plainly(self, client, setup):
        _, a = ask(client, view(setup, conditions=[cond("payload.load", "gt", value=1000)]))
        assert a["total"] == 0 and a["sentence"].endswith("— no rows match")

    def test_a_field_holding_groups_takes_no_conditions(self, client, setup):
        f = field(setup, "samples", "field_3")
        assert f["ops"] == [] and f["why_no_ops"] == dashboard.WHY_GROUPED
        status, a = ask(client, view(setup, "samples", conditions=[cond("field_3", "eq", value="x")]))
        assert status == 422 and a["message"] == "Field 3 can't be matched that way."

    def test_a_refusal_restates_the_question_in_plain_words(self, client, setup):
        _, a = ask(client, view(setup, "edge", columns=["label"],
                                conditions=[cond("huge", "gt", value=5)]))
        assert a["kind"] == "refused"
        assert a["sentence"] == "Edge cases where Huge is more than 5"
        assert a["message"] == "One of these values is too large to compute with, so this can't be answered honestly."

    @pytest.mark.parametrize("c, says", [
        (cond("status", "eq", value=7), "A text value must be text."),
        (cond("payload.load", "gt", value="50"), "A number value must be a number."),
        (cond("payload.load", "gt", value=True), "A number value must be a number."),
        (cond("ts", "on", value="Aug 18"), "A day must be picked as a date."),
        (cond("ts", "after", value="2026-08-18T25:00"), "A time must be picked as a date and a time."),
        (cond("status", "in", values=[]), "Pick at least one value for Status."),
        (cond("status", "gt", value="ok"), "Status can't be matched that way."),
        (cond("nope", "eq", value="ok"), "A condition names a field this data set doesn't have."),
    ])
    def test_a_condition_it_cannot_read_is_refused_plainly(self, client, setup, c, says):
        status, a = ask(client, view(setup, conditions=[c]))
        assert status == 422 and a["message"] == says


class TestSortAndShow:
    """AC5: the field and the direction, and how many rows."""

    def test_newest_first(self, client, setup):
        _, a = ask(client, view(setup, sort={"field": "ts", "dir": "desc"}))
        assert a["rows"][0][:2] == ["hb-01", "Aug 20, 23:00 UTC"]
        assert a["sentence"] == "Heartbeats, newest first — 8,400 rows"

    def test_largest_first_and_the_words_follow_the_kind(self, client, setup):
        _, a = ask(client, view(setup, sort={"field": "payload.load", "dir": "desc"}))
        assert a["rows"][0][3] == "100"
        assert a["sentence"] == "Heartbeats, by Load, largest first — 8,400 rows"
        _, a = ask(client, view(setup, "samples", sort={"field": "id", "dir": "desc"}))
        assert a["rows"][0][0] == "smp-1999" and "by ID, Z to A" in a["sentence"]
        _, a = ask(client, view(setup, "samples", sort={"field": "due_date", "dir": "asc"}))
        assert a["rows"][0][2] == "Jul 20, 2026" and "by Due date, earliest first" in a["sentence"]

    def test_show_caps_the_rows_and_says_so(self, client, setup):
        _, a = ask(client, view(setup, show=25, sort={"field": "ts", "dir": "desc"}))
        assert a["total"] == 25 and len(a["rows"]) == 25
        assert a["sentence"] == "Heartbeats, newest first — the first 25 rows"
        _, a = ask(client, view(setup, show=500, conditions=[cond("status", "eq", value="error")]))
        want = sum(1 for r in _HEARTBEATS if r["status"] == "error")
        assert want < 500 and a["total"] == want   # fewer than asked: the real count

    @pytest.mark.parametrize("bad, says", [
        ({"show": 30}, "Show must be all rows, 25, 100 or 500."),
        ({"sort": {"field": "field_3", "dir": "asc"}},
         "Field 3 can't be sorted: its rows hold different kinds of value."),
        ({"sort": {"field": "ts", "dir": "up"}}, "Sort one way or the other."),
    ])
    def test_a_sort_or_show_it_cannot_read(self, client, setup, bad, says):
        v = view(setup, "samples" if "field_3" in str(bad) else "heartbeats", **bad)
        status, a = ask(client, v)
        assert status == 422 and a["message"] == says


#: AC11's characters, alone and in company, plus the kind of text an
#: injection attempt carries.  No row holds any of these, so each must
#: return exactly zero rows — and in particular ``%`` and ``_`` must not act
#: as wildcards (``o_`` would match ``ok`` under LIKE).
_HOSTILE = ['"', "'", "\\", "%", "_", "o_", "ok%", "%ok%", "é", "１２３",
            'ok"', "ok'", "ok\\", 'a"b\'c\\d%e_f',
            "'; DROP TABLE demo.records; --", '" or 1 == 1 or "', "\\\"", "line\nbreak", "tab\there"]


class TestEveryValueIsEscaped:
    """AC11.  A picked value reaches the database as a bound parameter, and
    a value holding a quote, a backslash, a wildcard or non-ASCII returns
    exactly the rows it should."""

    @pytest.mark.parametrize("value", _HOSTILE)
    def test_the_literal_reads_back_as_the_same_value(self, value):
        expr = sys.modules["autosql_demo_expr"]
        tree = expr.parse("$.status == " + dashboard.string_literal(value))
        assert tree[0] == "cmp" and tree[3] == ("str", value)

    @pytest.mark.parametrize("value", _HOSTILE)
    def test_the_value_is_bound_never_spliced(self, setup, value):
        pick = dashboard.to_pick(setup, view(setup, conditions=[cond("status", "eq", value=value)]))
        built = builder.build(pick, ["payload", "sender_id", "status", "ts"])
        assert value in built.params.values()
        if len(value) > 2:
            assert value not in built.sql

    @pytest.mark.parametrize("value", _HOSTILE)
    def test_it_matches_exactly_nothing(self, client, setup, value):
        _, a = ask(client, view(setup, conditions=[cond("status", "eq", value=value)]))
        assert a["kind"] == "table" and a["total"] == 0
        assert a["admin"]["verdict"] == "agree"

    def test_hostile_values_beside_a_real_one_match_only_the_real_one(self, client, setup):
        want = sum(1 for r in _HEARTBEATS if r["status"] == "warn")
        _, a = ask(client, view(setup, conditions=[
            cond("status", "in", values=_HOSTILE + ["warn"])]))
        assert a["total"] == want

    def test_every_real_value_with_quotes_and_non_ascii_finds_its_own_row(self, client, setup):
        """The Edge cases' labels hold ``"``, ``'``, ``—`` and full-width
        digits: each, picked from the list, finds exactly its own row."""
        labels = field(setup, "edge", "label")["values"]
        assert any('"' in v for v in labels) and any("'" in v for v in labels)
        assert any(not v.isascii() for v in labels)
        for label in labels:
            _, a = ask(client, view(setup, "edge", columns=["label"],
                                    conditions=[cond("label", "eq", value=label)]))
            assert a["total"] == 1 and a["rows"][0][0] == label, label


class TestNothingIsSilentlyIgnored:
    """A choice the answer cannot honour is refused by name, never dropped
    (the S1 check's second finding): a later gap must not become a pick
    that quietly does nothing while the screen shows it as chosen."""

    @pytest.mark.parametrize("patch, says", [
        ({"summary": {"fn": "count", "per": "all", "by": "status"}},
         "This page can't use 'by' in a summary yet."),
        ({"group_by": "status"}, "This page can't use 'group_by' in a question yet."),
        ({"conditions": [{"field": "status", "op": "eq", "value": "ok", "_k": 1}]},
         "This page can't use '_k' in a condition yet."),
        ({"conditions": [{"field": "status", "op": "eq", "value": "ok", "values": ["warn"]}]},
         "“Status is” takes no list of values."),
        ({"conditions": [{"field": "status", "op": "in", "values": ["ok"], "value": "warn"}]},
         "“Status is one of” takes no value."),
        ({"conditions": [{"field": "payload.load", "op": "gt", "value": 5, "value2": 9}]},
         "“Load is more than” takes no second value."),
        ({"conditions": [{"field": "status", "op": "blank", "value": "ok"}]},
         "“Status is blank” takes no value."),
        ({"sort": {"field": "ts", "dir": "desc", "nulls": "first"}},
         "This page can't use 'nulls' in a sort yet."),
    ])
    def test_refused_by_name(self, client, setup, patch, says):
        status, a = ask(client, view(setup, **patch))
        assert status == 422 and a["kind"] == "invalid" and a["message"] == says

    def test_empty_slots_the_screen_always_sends_are_fine(self, client, setup):
        status, a = ask(client, view(setup, conditions=[
            {"field": "status", "op": "eq", "value": "warn", "value2": "", "values": []},
            {"field": "payload.note", "op": "blank", "value": "", "value2": None, "values": []}]))
        assert status == 200 and a["kind"] == "table"


class TestEdgeCasesLabelIsOffByDefault:
    """The foreman's call on the S1 check's first finding: Label's text was
    written for engineers, so a fresh Edge cases question leaves it off; a
    ticked box (or the Admin view) still shows it."""

    def test_off_by_default(self, setup):
        assert "label" not in setup["default_views"]["edge"]["columns"]
        assert len(setup["default_views"]["edge"]["columns"]) == len(ds(setup, "edge")["fields"]) - 1

    def test_a_ticked_box_still_shows_it(self, client, setup):
        _, a = ask(client, view(setup, "edge", columns=["label"]))
        assert a["total"] == 10 and [c["label"] for c in a["columns"]] == ["Label"]


# ═════════════════════════════════════════════════════════════════════════
# S3 — summaries (AC6), and the engine's reasons in plain words (AC7)
# ═════════════════════════════════════════════════════════════════════════

from decimal import ROUND_HALF_UP, Decimal  # noqa: E402

import legality  # noqa: E402
from demo.server import operations  # noqa: E402

_Q6 = Decimal("0.000001")


def q6(x) -> str:
    return str(Decimal(x).quantize(_Q6, rounding=ROUND_HALF_UP))


def summed(setup, ds_id="heartbeats", **kw):
    """A summary view: no columns, no sort (the page sends neither)."""
    kw = {"columns": [], "sort": None, **kw}
    return view(setup, ds_id, **kw)


class TestSummaries:
    def test_average_load_per_day_is_seven_bars(self, client, setup):
        _, a = ask(client, summed(setup, summary={"fn": "avg", "field": "payload.load", "per": "day"}))
        assert a["kind"] == "chart" and a["total"] == 7 and len(a["bars"]) == 7
        assert a["sentence"] == "Average Load of Heartbeats, per day — 7 days"
        by_day: dict = {}
        for r in _HEARTBEATS:
            by_day.setdefault(r["ts"][:10], []).append(r["payload"]["load"])
        want = [q6(Decimal(sum(v)) / len(v)) for _d, v in sorted(by_day.items())]
        assert [b["exact"] for b in a["bars"]] == want
        assert [b["label"] for b in a["bars"]] == [f"Aug {d}" for d in range(14, 21)]
        assert a["rows"][0] == ["Aug 14", f"{Decimal(want[0]):.2f}"]
        assert a["admin"]["verdict"] == "agree"

    def test_count_per_hour(self, client, setup):
        _, a = ask(client, summed(setup, summary={"fn": "count", "field": None, "per": "hour"}))
        assert a["total"] == 168 and {b["value"] for b in a["bars"]} == {50.0}
        assert a["bars"][5]["label"] == "Aug 14, 05:00"
        assert a["sentence"] == "Number of Heartbeats, per hour — 168 hours"
        assert a["page"]["last"] == 3 and len(a["rows"]) == 50

    def test_per_hour_with_a_condition_and_a_cap(self, client, setup):
        _, a = ask(client, summed(setup, show=25,
                                  conditions=[cond("status", "eq", value="error")],
                                  summary={"fn": "count", "field": None, "per": "hour"}))
        assert a["sentence"] == ("Number of Heartbeats where Status is error, per hour"
                                 " — the first 25 hours with rows")
        hours: dict = {}
        for r in _HEARTBEATS:
            if r["status"] == "error":
                hours[r["ts"]] = hours.get(r["ts"], 0) + 1
        first = sorted(hours.items())[:25]
        assert [(b["start"], int(b["value"])) for b in a["bars"] if not b["empty"]] == first
        # the axis between them is whole: every hour from the first to the 25th
        assert a["bars"][0]["start"] == first[0][0] and a["bars"][-1]["start"] == first[-1][0]
        assert a["total"] == len(dashboard._slots("hour", first[0][0], first[-1][0]))

    @pytest.mark.parametrize("fn, want", [
        ("sum", lambda v: str(sum(v))), ("min", lambda v: str(min(v))), ("max", lambda v: str(max(v))),
        ("avg", lambda v: f"{Decimal(sum(v)) / len(v):,.2f}"),
    ])
    def test_one_number_over_everything(self, client, setup, fn, want):
        loads = [r["payload"]["load"] for r in _HEARTBEATS if r["status"] == "warn"]
        _, a = ask(client, summed(setup, conditions=[cond("status", "eq", value="warn")],
                                  summary={"fn": fn, "field": "payload.load", "per": "all"}))
        assert a["kind"] == "number"
        assert a["number"]["value"] == f"{int(want(loads)):,}" if fn != "avg" else want(loads)
        assert a["sentence"] == f"{dashboard.SUMMARY_FNS[fn]} Load of Heartbeats where Status is warn"

    def test_count_and_an_exact_average_on_samples(self, client, setup):
        _, a = ask(client, summed(setup, "samples", summary={"fn": "count", "field": None, "per": "all"}))
        assert a["number"] == {"label": "Number", "value": "2,000", "exact": "2000"}
        _, a = ask(client, summed(setup, "samples", summary={"fn": "avg", "field": "priority", "per": "all"}))
        pr = [r["priority"] for r in _SAMPLES]
        assert a["number"]["exact"] == q6(Decimal(sum(pr)) / len(pr))

    def test_a_summary_with_no_rows(self, client, setup):
        _, a = ask(client, summed(setup, conditions=[cond("payload.load", "gt", value=1000)],
                                  summary={"fn": "avg", "field": "payload.load", "per": "all"}))
        assert a["kind"] == "number" and a["number"]["value"] is None
        _, a = ask(client, summed(setup, conditions=[cond("payload.load", "gt", value=1000)],
                                  summary={"fn": "count", "field": None, "per": "day"}))
        assert a["total"] == 0 and a["sentence"].endswith("— no rows match")

    @pytest.mark.parametrize("ds_id, patch, says", [
        ("samples", {"summary": {"fn": "count", "field": None, "per": "day"}},
         "Only Heartbeats have a time to group by."),
        ("heartbeats", {"summary": {"fn": "avg", "field": "payload.load", "per": "all"},
                        "sort": {"field": "ts", "dir": "desc"}},
         "A summary over everything is one number, so there is nothing to sort."),
        ("heartbeats", {"summary": {"fn": "avg", "field": "payload.load", "per": "day"},
                        "sort": {"field": "ts", "dir": "desc"}},
         "Per-hour and per-day summaries are always in time order."),
        ("heartbeats", {"summary": {"fn": "avg", "field": "payload.load", "per": "all"}, "show": 25},
         "A summary over everything is one number, so there is only one row."),
        ("heartbeats", {"summary": {"fn": "count", "field": "payload.load", "per": "all"}},
         "A count counts rows; it takes no field."),
        ("heartbeats", {"summary": {"fn": "avg", "field": "status", "per": "all"}},
         "Average of what? Pick a field that holds numbers."),
        ("heartbeats", {"summary": {"fn": "median", "field": "payload.load", "per": "all"}},
         "Summarize by count, total, average, smallest or largest."),
        ("heartbeats", {"summary": {"fn": "count", "field": None, "per": "week"}},
         "Summarize over everything, per hour or per day."),
    ])
    def test_what_cannot_be_combined_is_refused_in_plain_words(self, client, setup, ds_id, patch, says):
        status, a = ask(client, summed(setup, ds_id, **patch))
        assert status == 422 and a["message"] == says

    def test_columns_are_refused_not_dropped(self, client, setup):
        status, a = ask(client, view(setup, sort=None,
                                     summary={"fn": "count", "field": None, "per": "all"}))
        assert status == 422 and a["message"] == "Columns don't apply to a summary; untick them first."


class TestTheEnginesReasonsInPlainWords:
    """AC7: a choice the engine can't do right now is disabled with a plain
    reason taken from /api/operations — every reason it can give for the
    three controls this page greys, on every source and every shape."""

    def _picks(self):
        for source in legality.SOURCES:
            base = dict(legality.default_pick(), source=source)
            yield dict(base)
            yield dict(base, aggregate={"fn": "count", "field": None})
            yield dict(base, aggregate={"fn": "avg", "field": "x"})
            yield dict(base, aggregate={"fn": "count", "field": None}, bucket="hour")
            yield dict(base, aggregate={"fn": "sum", "field": "x"}, bucket="day")

    def test_every_reason_has_its_own_plain_words(self):
        seen = set()
        for pick in self._picks():
            for o in operations.contract(pick)["operations"]:
                if o["n"] in (4, 5, 7) and not o["enabled"]:
                    plain = dashboard.plain_reason(o["why"])
                    assert plain != dashboard._PLAIN_REASON_DEFAULT, o["why"]
                    assert not _MACHINERY.search(plain), plain
                    seen.add(plain)
        assert len(seen) == 4

    def test_the_setup_carries_the_contracts_verdicts(self, setup):
        u = setup["unavailable"]
        assert u["heartbeats"]["rows"] == {}
        assert u["heartbeats"]["per"] == {"sort": "Per-hour and per-day summaries are always in time order."}
        assert u["samples"]["rows"] == {"per": "Only Heartbeats have a time to group by."}
        assert set(u["edge"]["number"]) == {"sort", "show", "per"}

    def test_every_answer_says_what_is_off(self, client, setup):
        _, a = ask(client, view(setup, "samples"))
        assert a["unavailable"] == {"per": "Only Heartbeats have a time to group by."}
        _, a = ask(client, summed(setup, summary={"fn": "count", "field": None, "per": "all"}))
        assert set(a["unavailable"]) == {"sort", "show"}

    @pytest.mark.parametrize("summary", [
        {"fn": "avg", "field": "payload.load", "per": "day"},
        {"fn": "count", "field": None, "per": "hour"},
        {"fn": "max", "field": "payload.load", "per": "all"},
    ])
    def test_summary_answers_carry_no_machinery_words(self, client, setup, summary):
        _, a = ask(client, summed(setup, summary=summary))
        bad = [x for x in _everyone_strings(a) if _MACHINERY.search(x)]
        assert bad == []


class TestTheEnginesOwnRefusalIsSaidPlainly:
    """The S2 check's MEDIUM: ``==`` / ``!=`` on a number past the largest
    double raises the runtime's named refusal (SQLSTATE XPR01) mid-statement.
    The engine is not changed; the dashboard answers it in plain words
    rather than failing as though the demo were down."""

    @pytest.mark.parametrize("c", [
        cond("huge", "eq", value=0), cond("g", "eq", value=1), cond("g", "ne", value=1),
    ])
    def test_refused_in_plain_words(self, client, setup, c):
        status, a = ask(client, view(setup, "edge", columns=["a"], conditions=[c]))
        assert status == 200 and a["kind"] == "refused"
        assert a["message"] == "One of these values is too large to compute with, so this can't be answered honestly."
        assert a["admin"]["refusal"]["why"].startswith("XPR01: ")
        assert a["sentence"].startswith("Edge cases where ")
        # Admin still reads the statement the database refused (S4 check, 2)
        assert a["admin"]["statement"].startswith("SELECT ") and a["admin"]["sent"] is True
        assert '"A"' in a["admin"]["statement"] and a["admin"]["parameters"]

    def test_after_the_refusal_the_connection_is_read_only_and_pinned_again(self, setup):
        """The rollback after XPR01 reverts SET; the guard and the two pinned
        session values are re-applied before anything else reads."""
        from demo.server import db, settings

        dashboard._CACHE.clear()
        pick = dashboard.to_pick(setup, view(setup, "edge", columns=["a"],
                                             conditions=[cond("huge", "eq", value=0)]))
        conn = db.connect(application_name="autosql-demo-dashboard-test")
        try:
            server_app.refuse_writes(conn)
            out = dashboard._run(conn, pick)
            assert out["accepted"] is False and out["sql"]["display"].startswith("SELECT ")
            assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
            assert conn.execute("SHOW TimeZone").fetchone()[0] == settings.TIME_ZONE
            assert conn.execute("SHOW extra_float_digits").fetchone()[0] == settings.EXTRA_FLOAT_DIGITS
        finally:
            conn.close()

    def test_a_guard_that_cannot_be_reapplied_is_not_swallowed(self, monkeypatch, setup):
        from demo.server import db

        def broken(conn):
            raise RuntimeError("transaction_read_only reads 'off'")

        dashboard._CACHE.clear()
        pick = dashboard.to_pick(setup, view(setup, "edge", columns=["a"],
                                             conditions=[cond("huge", "eq", value=0)]))
        conn = db.connect(application_name="autosql-demo-dashboard-test")
        try:
            server_app.refuse_writes(conn)
            monkeypatch.setattr(server_app, "refuse_writes", broken)
            with pytest.raises(RuntimeError, match="transaction_read_only"):
                dashboard._run(conn, pick)
        finally:
            conn.close()

    def test_only_that_refusal_is_caught(self, monkeypatch, setup):
        """Any other database error still propagates: a pick must never
        produce an answer by swallowing something."""
        class Other(Exception):
            sqlstate = "22003"

        def boom(*a, **k):
            raise Other("something else")

        monkeypatch.setattr(server_app, "run_pick", boom)
        pick = dashboard.to_pick(setup, view(setup, "edge", columns=["a"],
                                             conditions=[cond("z", "eq", value=12345)]))
        with pytest.raises(Other):
            dashboard._run(None, pick)


class TestSentenceWording:
    def test_values_with_spaces_or_nothing_are_quoted(self, client, setup):
        _, a = ask(client, view(setup, "edge", columns=["s"],
                                conditions=[cond("t", "ne", value="not a number")]))
        assert "T is not “not a number”" in a["sentence"]
        _, a = ask(client, view(setup, "edge", columns=["s"],
                                conditions=[cond("txt", "eq", value="")]))
        assert "Txt is “”" in a["sentence"] and a["total"] == 1
        _, a = ask(client, view(setup, conditions=[cond("status", "eq", value="warn")]))
        assert "Status is warn" in a["sentence"]


# ═════════════════════════════════════════════════════════════════════════
# S4 — the Admin view's data (AC10).  What the page does with it is driven
#      headless in dash-check.mjs; here, what the contract hands it.
# ═════════════════════════════════════════════════════════════════════════

class TestTheAdminBlock:
    def test_the_readable_statement_and_what_is_actually_sent(self, client, setup):
        _, a = ask(client, view(setup, conditions=[cond("status", "eq", value="warn")]))
        adm = a["admin"]
        assert adm["sent"] is True
        assert "'warn'" in adm["statement"]                 # written in, for reading
        assert "warn" not in adm["parameterised"]           # never in what is sent
        warn = [p for p in adm["parameters"] if p["value"] == "warn"]
        assert len(warn) == 1 and warn[0]["name"].startswith("flt_")
        assert f"%({warn[0]['name']})s" in adm["parameterised"]

    def test_the_statement_changes_with_every_kind_of_pick(self, client, setup):
        seen = set()
        for v in (view(setup), view(setup, columns=["status"]),
                  view(setup, conditions=[cond("payload.load", "gt", value=50)]),
                  view(setup, sort={"field": "payload.load", "dir": "asc"}),
                  view(setup, show=25),
                  summed(setup, summary={"fn": "avg", "field": "payload.load", "per": "day"})):
            _, a = ask(client, v)
            seen.add(a["admin"]["statement"])
        assert len(seen) == 6

    def test_agreement_is_reported(self, client, setup):
        _, a = ask(client, view(setup, "samples"))
        assert a["admin"]["verdict"] == "agree" and a["admin"]["differing_rows"] == 0
        assert a["admin"]["compared_rows"] == 2000

    def test_a_refusal_carries_the_engines_own_words(self, client, setup):
        _, a = ask(client, view(setup, "edge", columns=["a"], conditions=[cond("huge", "gt", value=5)]))
        assert "out-of-range magnitude" in a["admin"]["refusal"]["why"]

    def test_admin_starts_edge_cases_with_label(self, setup):
        assert "label" in setup["admin_default_views"]["edge"]["columns"]
        assert "label" not in setup["default_views"]["edge"]["columns"]
        assert setup["admin_default_views"]["heartbeats"] == setup["default_views"]["heartbeats"]



class TestTheTimeAxisIsWhole:
    """The S3 check's MEDIUM: an hour or day with no rows keeps its place on
    the axis, marked, and the sentence says so."""

    def test_an_empty_day_keeps_its_slot(self, client, setup):
        days = {r["ts"][:10] for r in _HEARTBEATS if r["payload"]["load"] > 99}
        assert 0 < len(days) < 7      # the seed has a day with no load above 99
        _, a = ask(client, summed(setup, conditions=[cond("payload.load", "gt", value=99)],
                                  summary={"fn": "count", "field": None, "per": "day"}))
        assert a["total"] == 7 and [b["label"] for b in a["bars"]] == [f"Aug {d}" for d in range(14, 21)]
        assert {b["start"][:10] for b in a["bars"] if not b["empty"]} == days
        empty = [b for b in a["bars"] if b["empty"]]
        assert empty and all(b["value"] is None and b["text"] is None for b in empty)
        assert a["sentence"].endswith(f"per day — {len(days)} of 7 days have rows")
        assert ["Aug " + empty[0]["start"][8:10].lstrip("0"), "no rows"] in a["rows"]

    def test_every_hour_is_on_the_axis(self, client, setup):
        _, a = ask(client, summed(setup, conditions=[cond("status", "eq", value="error")],
                                  summary={"fn": "count", "field": None, "per": "hour"}))
        assert a["total"] == 168
        have = len({r["ts"] for r in _HEARTBEATS if r["status"] == "error"})
        assert sum(1 for b in a["bars"] if not b["empty"]) == have
        if have < 168:
            assert a["sentence"].endswith(f"— {have} of 168 hours have rows")

    def test_no_rows_at_all_draws_nothing(self, client, setup):
        _, a = ask(client, summed(setup, conditions=[cond("payload.load", "gt", value=1000)],
                                  summary={"fn": "count", "field": None, "per": "day"}))
        assert a["total"] == 0 and a["bars"] == [] and a["sentence"].endswith("— no rows match")


class TestHugeNumbersAreShownNotFatal:
    """The S3 check's MEDIUM: an average over Edge cases' 1e300 crashed the
    two-place rounding.  Numbers outside the plain range read as exponents,
    every digit kept, and a formatting problem never becomes an error."""

    def test_the_average_of_a_huge_number(self, client, setup):
        status, a = ask(client, summed(setup, "edge", summary={"fn": "avg", "field": "a", "per": "all"}))
        assert status == 200 and a["kind"] == "number"
        assert a["number"]["value"] == "1e+300"

    @pytest.mark.parametrize("fn", ["sum", "min", "max"])
    def test_other_summaries_of_it(self, client, setup, fn):
        status, a = ask(client, summed(setup, "edge", summary={"fn": fn, "field": "a", "per": "all"}))
        assert status == 200 and a["number"]["value"] == "1e+300"

    @pytest.mark.parametrize("text, places, want", [
        ("1" + "0" * 300 + ".000000", 2, "1e+300"),
        ("1" + "0" * 300, None, "1e+300"),
        (str(int(Decimal("1.7976931348623157e308"))), None, "1.7976931348623157e+308"),
        ("1234567890123456789012345678901234", None, "1.234567890123456789012345678901234e+33"),
        ("0.0000001", None, "1e-7"),
        ("999999999999999", None, "999,999,999,999,999"),
        ("-0.125", 2, "-0.13"),
        ("2.675", 2, "2.68"),                      # half-up, as the engine rounds
        ("not a number", 2, "not a number"),
    ])
    def test_fmt_number_is_total(self, text, places, want):
        assert dashboard.fmt_number(text, places=places) == want
