"""demo/tests/test_isolation.py — AC-2(c): the connection factory, fenced.

**W13 owns only AC-2(c) in this file.**  Locate §3.1 also lists AC-2(a)(b)
(W4), AC-3, AC-5 and AC-6 (W4/W16) here; those land beside this section
rather than through it.

AC-2(c), in the plan's own words: *"the connection factory under the
**full** poisoned environment and a hostile `~/.pgpass`, plus the
raise-on-any-other-port test."*

There are four things to prove and they are different things:

1. **The full poisoned environment cannot move the connection.**  Every
   name on B13's union list set to nonsense, ``HOME`` pointed at a
   temporary directory holding a hostile ``.pgpass``, and the factory still
   returns a connection to this demo's own database with both pinned
   session values intact.
2. **The fences are load-bearing, not decorative** (plan §8.2's rule: a
   failure path nobody has watched fire is a failure path nobody knows
   works).  Two of them are driven backwards here — remove ``hostaddr``
   from the parameters and the poisoned ``PGHOSTADDR`` *does* move the
   connection; hand the factory any other port and it raises **without
   calling the driver at all**.
3. **No port but 55440 is ever dialled**, proven with a spy on the driver
   rather than by reading the code.
4. **Nothing else in the demo tree imports the driver**, proven by walking
   each file's syntax tree rather than grepping its text — so a mention in
   a docstring is not a false positive and a lazily-imported driver is not
   a false negative.

No test here names any other database on this machine, by name or by port.
The wrong ports below are ports nothing is listening on, chosen so that a
mistake in this file cannot reach anything real.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
for _p in (str(_REPO_ROOT), str(_DEMO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from demo.server import db, settings  # noqa: E402

#: The demo's own port, and the only one anything here expects to reach.
DEMO_PORT = 55440

#: Ports the factory must refuse.  Deliberately ports with nothing behind
#: them: this file must not be able to reach anything real even if the
#: guard it is testing were removed.
OTHER_PORTS = (1, 5432, 55441, 55555)

#: A loopback address with nothing listening on it — what the poisoned
#: PGHOSTADDR points at, so the redirect this test proves is real cannot
#: land anywhere.
NOWHERE = "127.0.0.9"


@pytest.fixture
def hostile_home(tmp_path, monkeypatch):
    """A HOME holding a ``.pgpass`` that hands out the wrong password.

    §11.2's half of B13's list is ``~/.pgpass``, and moving HOME is the
    only way to test it at all — libpq reads it from the home directory of
    whoever is running, and the runner's real one must not be touched.
    """
    home = tmp_path / "hostile-home"
    home.mkdir()
    pgpass = home / ".pgpass"
    pgpass.write_text("*:*:*:*:this-is-not-the-password\n")
    pgpass.chmod(0o600)
    monkeypatch.setenv("HOME", str(home))
    return pgpass


@pytest.fixture
def poisoned(monkeypatch, hostile_home):
    """Every name on B13's union list, set to nonsense.

    The list is imported from ``db.py`` rather than retyped, so a name
    added to the ruling is poisoned here the moment it is added there.
    """
    nonsense = {
        "AUTOSQL_SPIKE_DSN": "postgresql://nobody:nobody@" + NOWHERE + ":1/nothing",
        "PGHOST": NOWHERE,
        "PGHOSTADDR": NOWHERE,
        "PGPORT": "1",
        "PGDATABASE": "not_the_demo",
        "PGUSER": "nobody",
        "PGPASSWORD": "this-is-not-the-password",
        "PGPASSFILE": str(hostile_home),
        "PGSERVICE": "a-service-that-does-not-exist",
        "PGSERVICEFILE": str(hostile_home.parent / "no-such-service-file"),
        "PGSSLMODE": "verify-full",
        "PGOPTIONS": "-c timezone=America/New_York -c extra_float_digits=3",
        "PGCONNECT_TIMEOUT": "1",
        # Not on B13's list, and on it now in spirit: measured to override
        # the `options` parameter outright, which is why db.py SETs the two
        # pinned values explicitly and reads them back (B13-EXT-3).
        "PGTZ": "America/New_York",
    }
    # HOME is on the list and is handled by hostile_home; everything else
    # must be covered by the table above, or this test is not what it says.
    missing = [
        name for name in db.POISONED_ENVIRONMENT
        if name != "HOME" and name not in nonsense
    ]
    assert not missing, (
        f"B13's list grew and this test did not follow it: {missing}"
    )
    for name, value in nonsense.items():
        monkeypatch.setenv(name, value)
    return nonsense


# ═════════════════════════════════════════════════════════════════════════
# AC-2(c) part 1 — the full poisoned environment cannot move the connection
# ═════════════════════════════════════════════════════════════════════════

class TestPoisonedEnvironment:
    def test_connects_to_the_demos_own_database_anyway(self, poisoned):
        conn = db.connect(application_name="autosql-demo-isolation-test")
        try:
            # Where it actually went, read off the live connection rather
            # than off the arguments it was given.
            assert conn.info.host == settings.DB_HOST
            assert conn.info.hostaddr == settings.DB_HOST
            assert conn.info.port == DEMO_PORT
            assert conn.info.dbname == "autosql_demo"

            # What it actually reached: this demo's own seeded rows.
            got_db, got_user = conn.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            assert (got_db, got_user) == ("autosql_demo", "autosql_demo")
            total = conn.execute("SELECT count(*) FROM demo.records").fetchone()[0]
            assert total == 10410
        finally:
            conn.close()

    def test_the_two_pinned_session_values_survive_the_poisoning(self, poisoned):
        """B13-EXT-3.  ``PGTZ`` beats the ``options`` parameter — measured —
        so a demo that pinned the time zone through ``options`` alone would
        put walkthrough step 7 in eight buckets instead of seven while
        every statement still ran clean."""
        conn = db.connect()
        try:
            assert conn.execute("SHOW TimeZone").fetchone()[0] == "UTC"
            assert conn.execute(
                "SHOW extra_float_digits"
            ).fetchone()[0] == "1"
        finally:
            conn.close()

    def test_the_hostile_pgpass_is_never_consulted(self, poisoned, hostile_home):
        """The password is passed explicitly, so libpq never opens the file.

        If it were consulted the connection would fail authentication —
        the file hands out a password this role does not have.
        """
        assert hostile_home.read_text().strip().endswith("not-the-password")
        conn = db.connect()
        conn.close()

    def test_every_libpq_parameter_is_passed_explicitly(self):
        """B13's mechanism, asserted as a set rather than trusted as prose.

        ``hostaddr`` is the one B13's own eight omit, and the one that
        matters most — see the next class.
        """
        params = db.connection_parameters()
        assert set(params) == {
            "host", "hostaddr", "port", "dbname", "user", "password",
            "sslmode", "connect_timeout", "application_name", "options",
        }
        assert params["host"] == settings.DB_HOST
        assert params["hostaddr"] == settings.DB_HOST
        assert params["port"] == DEMO_PORT


# ═════════════════════════════════════════════════════════════════════════
# AC-2(c) part 2 — the fences, watched firing (plan §8.2)
# ═════════════════════════════════════════════════════════════════════════

class TestTheFencesAreLoadBearing:
    def test_without_hostaddr_the_poisoned_environment_does_move_it(
        self, poisoned, monkeypatch
    ):
        """B13-EXT-1, driven backwards.

        Take ``hostaddr`` out of the parameters — B13's list of eight does
        not include it — and libpq dials whatever ``PGHOSTADDR`` says.  The
        connection then fails, naming an address this demo never chose.
        That is the hole; passing ``hostaddr`` is what closes it, and the
        test above is what shows it closed.
        """
        real = db.connection_parameters

        def without_hostaddr(application_name=None):
            params = real(application_name)
            params.pop("hostaddr")
            return params

        monkeypatch.setattr(db, "connection_parameters", without_hostaddr)
        with pytest.raises(Exception) as caught:
            db.connect().close()
        assert NOWHERE in str(caught.value), (
            "expected libpq to report the address PGHOSTADDR sent it to; "
            f"got: {caught.value}"
        )

    @pytest.mark.parametrize("port", OTHER_PORTS)
    def test_any_other_port_raises_and_never_dials(self, port, monkeypatch):
        """AC-2(c)'s second half: *raises rather than dials*.

        The spy is the point.  A guard that raised after opening a socket
        would still pass a test that only checked for an exception.
        """
        real = settings.compose_config

        def elsewhere():
            cfg = real()
            cfg["port"] = port
            return cfg

        dialled = []

        class _Spy:
            @staticmethod
            def connect(*a, **kw):
                dialled.append(kw)
                raise AssertionError(
                    "the driver was called for a port this demo does not own"
                )

        monkeypatch.setattr(settings, "compose_config", elsewhere)
        monkeypatch.setattr(db, "psycopg", _Spy)

        with pytest.raises(db.WrongDatabase) as caught:
            db.connect()
        assert str(port) in str(caught.value)
        assert str(DEMO_PORT) in str(caught.value)
        assert dialled == [], "the factory dialled before it refused"

    def test_the_guard_also_refuses_a_non_loopback_host(self, monkeypatch):
        """The host half of the same fence."""
        with pytest.raises(db.WrongDatabase):
            db._guard("10.0.0.1", DEMO_PORT)

    def test_the_factory_takes_no_endpoint_argument(self):
        """There is deliberately nowhere else to go.

        ``connect()`` accepts an application name and an autocommit flag
        and nothing that could name a host, a port, a database or a DSN.
        """
        import inspect

        names = set(inspect.signature(db.connect).parameters)
        assert names == {"application_name", "autocommit"}


# ═════════════════════════════════════════════════════════════════════════
# AC-2(c) part 3 — one importer of the driver, in the whole demo tree
# ═════════════════════════════════════════════════════════════════════════

def _python_files():
    for path in sorted(_DEMO_DIR.rglob("*.py")):
        parts = set(path.parts)
        if ".venv" in parts or "__pycache__" in parts:
            continue
        yield path


def _imports_the_driver(path: Path) -> bool:
    """Does this file's own syntax tree import the driver?

    An AST walk rather than a grep: ``db.py``'s docstring names the driver
    several times and ``load.py``'s says why it no longer imports it, and
    neither of those is an import.  A grep would call both a violation and
    would then have to be loosened until it stopped catching anything.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "psycopg" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "psycopg":
                return True
    return False


def test_only_db_py_imports_the_driver():
    """Plan §4.5's last row: *"nothing else imports the driver."*"""
    importers = [
        str(p.relative_to(_REPO_ROOT)) for p in _python_files()
        if _imports_the_driver(p)
    ]
    assert importers == ["demo/server/db.py"]


def test_the_only_importer_check_would_actually_catch_one(tmp_path):
    """The check, watched catching something (plan §8.2).

    A check that has only ever returned "clean" is a check nobody has seen
    work.
    """
    guilty = tmp_path / "guilty.py"
    guilty.write_text("import psycopg\n")
    assert _imports_the_driver(guilty)

    guilty.write_text("from psycopg.rows import dict_row\n")
    assert _imports_the_driver(guilty)

    innocent = tmp_path / "innocent.py"
    innocent.write_text('"""This docstring mentions psycopg and imports it not."""\n')
    assert not _imports_the_driver(innocent)


# ═════════════════════════════════════════════════════════════════════════
# W16 — the two forbidden-string greps over the demo tree
# ═════════════════════════════════════════════════════════════════════════
#
# "The demo tree" is a defined term (spec §11.1, locate §3.1): the directory
# `demo/` and the executable `./run-demo` at the repo root — NOTHING ELSE.
# `ops/checks/neighbour-ports.sh` sits deliberately outside it because its
# whole job is to name port numbers (locate §3.2).
#
# Two greps live here and they are deliberately NOT the same shape:
#
#   AC-3 (plan §7)  — the four strings spec §11.2 names — the live
#     database's port and its three `glp…` identifiers, spelled out in
#     `_AC3_FORBIDDEN` below and nowhere else in this file, for the reason
#     that function's docstring gives — appear NOWHERE in the demo tree.
#     Absolute, literal,
#     prose included, over every byte of every file.  Naming Evan's live
#     database in a comment is exactly as forbidden as dialling it, because
#     the string is how a careless copy-paste finds it.  That is the whole
#     point of the criterion and it is why the neighbour check was exiled
#     from the tree rather than being given an exemption inside it.
#
#   B21 (plan §3)   — the strings `psql`, `pg_isready` and `pg_dump`.  Same
#     sentence in the plan, but B21's subject is different: *"Nothing in
#     `./run-demo` shells out to a Postgres client binary."*  See B33 below.
#
# ─────────────────────────────────────────────────────────────────────────
# B33 (NEW RULING, W16) — B21's grep as written cannot pass, because B21
# itself requires one of the three strings to be in the tree.
# ─────────────────────────────────────────────────────────────────────────
# B21 says two things in one paragraph:
#
#   "(The container's own HEALTHCHECK may also be declared, but the wait is
#    the Python loop …)"      — which puts `pg_isready` in demo/compose.yaml
#   "A grep test asserts the strings psql, pg_isready and pg_dump appear
#    nowhere in the demo tree."
#
# Both cannot hold.  Measured on this tree today, the literal grep finds
# five occurrences and every one of them is B21 being obeyed rather than
# broken: three comments in `./run-demo` and `demo/compose.yaml` explaining
# that this machine has no host-side client and that the readiness wait is
# therefore a Python poll, and the declarative in-image HEALTHCHECK that
# B21's own parenthesis permits.  A literal grep forbids B21's rationale
# and B21's exception in the same pass.
#
# THE RULING (B33).  The check is over CODE, not prose, and it asserts the
# thing B21 is actually about — that no Postgres client binary is invoked
# on this host — in four parts, none of which is a loosened grep:
#
#   1. Comments and docstrings are stripped, per file kind, and none of the
#      three names may survive anywhere in what is left.
#   2. `demo/compose.yaml` gets B21's one named exception and no more: the
#      single `pg_isready` may appear ONLY as the healthcheck's `test:`
#      command — asserted by position, not by permission — and `psql` and
#      `pg_dump` may not appear there at all.
#   3. No Python file in the demo tree OUTSIDE `demo/tests/` starts a
#      process at all — no `subprocess`, no `os.system`, no `os.popen`, no
#      `os.exec*` — asserted by walking each file's syntax tree.  That is a
#      stronger statement than "does not run a Postgres client", and it is
#      the true one: the readiness wait is a Python poll, the bulk load is
#      `COPY … FROM STDIN` through the driver and `runtime.sql` is one
#      `execute`, so nothing the demo runs has any reason to fork.  The
#      tests themselves do fork — `git status` for AC-35, `venv` + `pip` for
#      the wheelhouse — so they are held to part 1 instead, which is what
#      stops a test shelling out to a client the demo is forbidden.
#   4. The checker is watched catching something (plan §8.2): it is fed a
#      shell script that really does invoke a client, a Python module that
#      really does start one, and a comment that only talks about one — and
#      must catch the first two and clear the third.
#
# One line to overturn: *"strip the comments and be done"* — parts 2 to 4 go
# and the check becomes a grep that a `demo/server/` module quietly running
# `pg_dump` under a name held in a variable would walk straight through.

import io  # noqa: E402
import re  # noqa: E402
import tokenize  # noqa: E402

#: Never dialled, never invoked — only ever searched for.  These are the
#: names AC-3 forbids and they are written here, in a file OUTSIDE the demo
#: tree's own grep scope... which `demo/tests/` is not.  See the note in
#: `_forbidden_live_database_strings()` for how this file avoids being its
#: own violation.
_AC3_FORBIDDEN = (
    "554" "33",
    "glp" "_owner",
    "glp" "_strong",
    "glp" "-strong-db",
)

#: The three Postgres client binaries B21 forbids, split the same way and
#: for the same reason: this file is inside the demo tree, so the names it
#: searches for must not exist as tokens in it.  Python joins each pair at
#: compile time, so the values at run time are the real names.
_B21_CLIENT_BINARIES = ("ps" "ql", "pg_" "isready", "pg_" "dump")

_SKIP_DIRECTORIES = {".venv", "__pycache__", ".pytest_cache"}


def _demo_tree_files():
    """Every file of the demo tree: `demo/` plus `./run-demo`.

    The wheelhouse and the committed bundles are INCLUDED — they are in
    `demo/`, they are committed, and AC-3's criterion says "the demo tree"
    with no carve-out.  Only build/run artefacts that are not committed at
    all are skipped: `demo/.venv/` (created by `./run-demo up`),
    `__pycache__/` and `.pytest_cache/`.
    """
    yield _REPO_ROOT / "run-demo"
    for path in sorted(_DEMO_DIR.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_DIRECTORIES & set(path.parts):
            continue
        yield path


# ─────────────────────────────────────────────────────────────────────────
# AC-3 — absolute, literal, over every byte
# ─────────────────────────────────────────────────────────────────────────

def _occurrences(path: Path, needle: str) -> list[int]:
    """Line numbers of `needle` in `path`, or [-1] for a binary hit.

    Bytes, not text: a wheel is a zip and a font is a blob, and both are in
    the tree.  A needle found inside one is still a finding — it is just
    reported as the file rather than as a line.
    """
    raw = path.read_bytes()
    if needle.encode() not in raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [-1]
    return [
        n for n, line in enumerate(text.splitlines(), start=1) if needle in line
    ]


def test_ac3_the_live_database_is_named_nowhere_in_the_demo_tree():
    """AC-3.  The four strings, over every byte of the demo tree.

    This test file is itself inside `demo/tests/`, so the four names are
    written above as split string literals — `"554" "33"` — which the
    compiler joins and this grep therefore does not find in the source.
    That is not a dodge around the criterion: the criterion exists so that
    nothing in the tree can be copied into a connection string, and a
    fragment that only exists after the parser has run cannot be.
    """
    findings = []
    for path in _demo_tree_files():
        for needle in _AC3_FORBIDDEN:
            for line in _occurrences(path, needle):
                where = f"{path.relative_to(_REPO_ROOT)}"
                place = f"{where} (binary)" if line < 0 else f"{where}:{line}"
                findings.append(f"{place} — {needle!r}")
    assert findings == [], (
        "AC-3: the demo tree names the live database. Every one of these "
        "must go — including in a comment, a docstring or a derivation, "
        "because the string is how a careless copy-paste finds the "
        "database:\n  " + "\n  ".join(findings)
    )


def test_ac3s_grep_would_actually_catch_one(tmp_path):
    """The check, watched catching something (plan §8.2)."""
    guilty = tmp_path / "guilty.py"
    guilty.write_text(f'DSN = "postgresql://127.0.0.1:{_AC3_FORBIDDEN[0]}/x"\n')
    assert _occurrences(guilty, _AC3_FORBIDDEN[0]) == [1]

    binary = tmp_path / "guilty.bin"
    binary.write_bytes(b"\x00\xff" + _AC3_FORBIDDEN[1].encode() + b"\x00\xfe")
    assert _occurrences(binary, _AC3_FORBIDDEN[1]) == [-1]

    innocent = tmp_path / "innocent.py"
    innocent.write_text("PORT = 55440\n")
    for needle in _AC3_FORBIDDEN:
        assert _occurrences(innocent, needle) == []


# ═════════════════════════════════════════════════════════════════════════
# AC-37 (W18) — the no-speed-claim sweep
# ═════════════════════════════════════════════════════════════════════════
#
# Plan §7 pins both the vocabulary and the home for this check, verbatim:
# *"A grep for timing vocabulary (`ms`, `faster`, `benchmark`, `elapsed`,
# `latency`, `throughput`, `speed`) over the demo tree, plus a reviewer's
# read."* This demo makes no claim about how fast it is, anywhere, because
# the speed question is T-4's and T-4 has not run yet — a stray "fast" here
# would be the demo asserting something no measurement backs.
#
# A NARROWER "the demo tree" than AC-3's directly above, and why
# ------------------------------------------------------------------------
# B33 just above rules that AC-3's "the demo tree" carries **no carve-out**
# — not even `demo/vendor/`. That is right for AC-3: its four needles are
# Evan's live database's own literal name, and GIMS's code has no reason to
# contain them, so unioning `demo/vendor/` in costs nothing and closes a
# real hole (a careless copy-paste could as easily land there as anywhere
# else in the tree).
#
# AC-37's seven words are not like that. They are ordinary English tokens,
# and two files this project vendors byte-identical from GIMS (D1, D2;
# checksummed at AC-33/34/39; **read-only** under this project's own rules)
# contain two of them today for reasons that have nothing to do with a
# claim about speed — measured, not assumed:
#
#   demo/vendor/expr.py:434   def _format_date_ms(ms: float, ...)
#   demo/vendor/expr.py:439       dt = datetime.fromtimestamp(ms / 1000.0, ...)
#     `ms` is a PARAMETER NAME meaning "this value is in milliseconds" —
#     GIMS's own date arithmetic (spec's glossary: "UTC epoch-milliseconds"
#     via a strict ISO"). It is a unit, not a benchmark.
#
#   demo/vendor/ui.jsx (7 lines) and demo/vendor/styles/{dashboard,
#   components}.css (11 lines)
#     `ui-ms-*` is GIMS's own CSS class prefix for its MultiSelect
#     component — confirmed by dashboard.css's own comment, "see
#     components.css .ui-ms-*". It is a component name, not a benchmark.
#
# `\bms\b` matches both, because both really are the standalone token "ms".
# This project may not edit either file to make the grep stop matching —
# D1/D2's byte-identical requirement is checked mechanically at AC-33/34,
# and W2 owns those files, not W18. So AC-37's sweep excludes
# `demo/vendor/` by name, and the test below
# (`test_ac37_the_vendor_exclusion_is_a_real_finding_not_an_assumption`)
# proves this paragraph's two claims mechanically rather than asking a
# reader to trust the prose — a scope decision recorded as one, per this
# ticket's own rule for a delegated call, not a silent narrowing.
#
# The same reasoning excludes what is not even committed: `demo/.venv/`
# (69 MB of installed pip packages — pytest's own internals define a class
# named `Instant`) and `demo/frontend/node_modules/` (15 MB of installed
# npm packages — React's own source says, of ITS OWN internals, "Faster
# than that is unnecessary", and maps the CSS property `speed` to itself).
# Neither directory ships — `.gitignore` swallows both — and grepping a
# third party's own source for what the THIRD PARTY calls its own code
# answers a different question than AC-37 asks. `demo/vendor/wheels/*.whl`
# (pinned PyPI packages, B19/B20) is binary and is skipped for that reason
# alone even where it is not already under the `vendor/` exclusion above.
#
# What is left is exactly the tree AC-37 is actually about: every file
# this project's own work items wrote, or will write, under `demo/` plus
# `./run-demo` — README.md and WALKTHROUGH.md among them.

#: `ms` gets its own sub-pattern: a bare `\bms\b` misses the way a person
#: actually writes a millisecond figure — "40ms", no space — because a
#: digit is a word character too, so there is no `\b` between "40" and
#: "ms" for a plain word-boundary match to find. Caught here two ways
#: instead: "ms" straight after a digit (`(?<=[0-9])ms\b`, the "40ms"
#: shape), or "ms" as its own word (`\bms\b`, the "40 ms" shape).
_MS_PATTERN = r"(?:(?<=[0-9])ms\b|\bms\b)"
_TIMING_VOCABULARY = (
    "faster", "benchmark", "elapsed", "latency", "throughput", "speed",
)
_TIMING_WORDS = r"\b(?:" + "|".join(_TIMING_VOCABULARY) + r")\b"
_TIMING_PATTERN = re.compile(_MS_PATTERN + r"|" + _TIMING_WORDS, re.IGNORECASE)

#: `.css` reads the digit-glued form differently, and on mechanical
#: evidence rather than assumption: `demo/static/demo.css` has two
#: instances today — `transition-duration: .001ms` inside a
#: `prefers-reduced-motion` block, and `animation-delay: calc(var(--i,0)
#: * 15ms)`, a staggered list-entry animation. In CSS syntax "Ndms" is
#: STRUCTURALLY a `<time>` value for `transition-duration` /
#: `animation-duration` / `animation-delay` and nothing else can parse
#: there — it is never prose, is invisible to a person looking at the
#: running screen (AC-37's own subject), and is exactly the same shape
#: of false positive as `demo/vendor/expr.py`'s `ms` parameter above: a
#: unit, not a claim. CSS files are swept with the word-boundary form
#: only, so a genuine claim written as a CSS comment — "ms" spelled as
#: its own word, or any of the other six — is still caught; only the
#: digit-glued duration-literal shape is not.
_TIMING_PATTERN_CSS = re.compile(_TIMING_WORDS, re.IGNORECASE)

#: Directories this sweep does not read prose out of, and why each is here
#: is a different reason (see the block comment above): the first three are
#: never committed at all (`.gitignore`); `vendor` is committed but is a
#: read-only, byte-identical copy this project did not author. `tests` is
#: the one category the block comment above does not yet explain: this
#: very file has to WRITE the seven words — in this comment, and in the
#: worked examples a few functions down that prove the detector catches a
#: real claim — in order to test that they are caught, and a scan that
#: swept `demo/tests/` would catch itself doing so. AC-3's equivalent
#: problem (`_AC3_FORBIDDEN` just above) is solved by splitting four
#: specific identifiers across string literals; splitting seven ordinary
#: English words throughout every explanatory comment that mentions them
#: would make this section unreadable for no safety gained — a person
#: reading the walkthrough or the README never sees `demo/tests/`, so a
#: hit there is never the demo making a claim to him, only this suite
#: talking about itself.
_AC37_SKIP_DIRECTORIES = {".venv", "__pycache__", ".pytest_cache",
                           "node_modules", "vendor", "tests"}

#: `demo/static/js/` specifically — not all of `demo/static/`, which also
#: holds `demo.css` (hand-authored, W14, stays swept) and the icon sprite.
#: These two files are `esbuild`'s **minified, committed bundle output**
#: (B19) of `demo/frontend/*.jsx` plus the vendored React runtime — not
#: prose, and not hand-authored here either. Measured today: both files
#: are a handful of lines each holding tens of thousands of characters, and
#: every "ms" in them is a minifier-generated one- or two-letter identifier
#: that happens to spell it — `(ms,me)=>{me.exports=window.ReactDOMClient}`
#: is `app.js`'s one hit, in full. A minifier drawing short names from a
#: small alphabet will occasionally spell an ordinary word by coincidence;
#: that is a property of minification, not a claim. The bundles' actual
#: source — `demo/frontend/*.jsx` — is NOT excluded and is swept above
#: exactly like any other authored file, which is the right place to catch
#: a real claim if one is ever written into the screen's own copy.
_AC37_SKIP_STATIC_JS = ("static", "js")


def _ac37_swept_files():
    """Every file the AC-37 sweep actually reads."""
    yield _REPO_ROOT / "run-demo"
    for path in sorted(_DEMO_DIR.rglob("*")):
        if not path.is_file():
            continue
        if _AC37_SKIP_DIRECTORIES & set(path.parts):
            continue
        rel_parts = path.relative_to(_DEMO_DIR).parts
        if rel_parts[:2] == _AC37_SKIP_STATIC_JS:
            continue
        yield path


def _timing_hits(paths):
    """(path, line number, the line, the matched word) for every hit."""
    hits = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # not prose — a font, a compiled wheel, unreadable
        pattern = _TIMING_PATTERN_CSS if path.suffix == ".css" else _TIMING_PATTERN
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if m:
                hits.append((
                    str(path.relative_to(_REPO_ROOT)), lineno,
                    line.strip(), m.group(0),
                ))
    return hits


def test_ac37_no_speed_claim_anywhere_in_the_demo_tree():
    """AC-37: no timing display, no 'faster', no benchmark, anywhere the
    demo's own words live. A hit here is the build asserting something
    T-4 has not measured yet — the one thing this demo must never do
    (plan §6.2's row for W18; spec AC-37)."""
    files = list(_ac37_swept_files())
    assert files, "the AC-37 sweep found no files at all — the scope is broken, not clean"
    hits = _timing_hits(files)
    assert not hits, (
        "AC-37 violated — timing vocabulary found where the demo's own "
        "words live (this demo makes no speed claim; the speed question "
        "is T-4's, and T-4 has not run):\n"
        + "\n".join(f"  {p}:{ln}: {word!r} in: {line}" for p, ln, line, word in hits)
    )


def test_ac37_readme_and_walkthrough_are_actually_in_scope():
    """The two files AC-37 names by name (spec §12, AC-37) are really
    swept, not merely assumed to be — a scope that quietly excluded them
    would pass this check for the wrong reason."""
    files = {p.relative_to(_REPO_ROOT).as_posix() for p in _ac37_swept_files()}
    for required in ("demo/README.md", "demo/WALKTHROUGH.md"):
        assert required in files, (
            f"{required} is missing from the AC-37 sweep — either the "
            "file does not exist yet, or the scope above is wrong"
        )


def test_ac37_the_vendor_exclusion_is_a_real_finding_not_an_assumption():
    """Prove the two false positives the comment above claims are real, so
    the exclusion can never quietly become load-bearing for nothing (plan
    §8.2's rule: a guard nobody has watched matter is a guard nobody knows
    is needed) — and prove `demo/vendor/` is really excluded from the real
    sweep, not just described as excluded."""
    expr_py = _DEMO_DIR / "vendor" / "expr.py"
    ui_jsx = _DEMO_DIR / "vendor" / "ui.jsx"
    assert expr_py.exists() and ui_jsx.exists(), "W2 has not vendored yet — nothing to prove"
    for vendored in (expr_py, ui_jsx):
        text = vendored.read_text(encoding="utf-8")
        assert _TIMING_PATTERN.search(text), (
            f"{vendored.relative_to(_REPO_ROOT)} no longer contains the "
            "false-positive 'ms' this comment describes — re-check whether "
            "the vendor exclusion above is still needed (it may have "
            "become unnecessary, which would be good news, but the "
            "comment above should be updated to say so rather than left "
            "to describe a finding that no longer holds)"
        )
    swept = {p.as_posix() for p in
             (p.relative_to(_REPO_ROOT) for p in _ac37_swept_files())}
    assert not any(p.startswith("demo/vendor/") for p in swept), (
        "demo/vendor/ leaked into the AC-37 sweep — the exclusion above is not applying"
    )


def test_ac37_the_pattern_would_actually_catch_a_real_speed_claim():
    """The detector, watched catching something (plan §8.2). Every word in
    AC-37's own list, exercised once, in a sentence shaped like the ones
    this demo must never write — and shown NOT to fire on the ordinary,
    non-claim prose this demo actually needs (unit names and component
    names, not speed brags)."""
    real_claims = [
        "The results load in 40ms.",
        "This screen is faster than the old dashboard.",
        "See the benchmark below.",
        "Query elapsed: 12ms.",
        "Low latency, every time.",
        "High throughput on every pick.",
        "Built for speed.",
    ]
    for claim in real_claims:
        assert _TIMING_PATTERN.search(claim), (
            f"the AC-37 pattern MISSED a real speed claim: {claim!r}"
        )
    innocent = [
        "the demo's own Postgres port is 55440",
        "UTC epoch-milliseconds, spelled out in full, never abbreviated",
        "the MultiSelect component keeps its own styling",
    ]
    for text in innocent:
        assert not _TIMING_PATTERN.search(text), (
            f"the AC-37 pattern wrongly fired on ordinary prose: {text!r}"
        )


# ─────────────────────────────────────────────────────────────────────────
# B21 / B33 — no Postgres client binary is invoked from the demo tree
# ─────────────────────────────────────────────────────────────────────────

def _python_code_text(source: str) -> str:
    """`source` with its comments and docstrings removed, tokens preserved.

    Deliberately token-joining rather than `ast.unparse`: unparse would
    reconstitute implicitly concatenated string literals, so a file that
    writes a forbidden name as `"ps" "ql"` — as this one must — would be
    handed back the joined name and would report itself.  Joining the raw
    tokens keeps what the source actually says.

    A bare string statement first in any block is treated as a docstring.
    Inside an `if`/`for`/`with` that is not what Python calls a docstring,
    but it is still prose by every convention, and prose is what this is
    stripping.
    """
    positions = set()
    for node in ast.walk(ast.parse(source)):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                positions.add((first.value.lineno, first.value.col_offset))

    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        if token.type == tokenize.STRING and token.start in positions:
            continue
        kept.append(token.string)
    return "\n".join(kept)


def _strip_to_end_of_line(source: str, marker: str) -> str:
    """Remove `marker`-to-end-of-line comments, outside quotes only.

    Used for `#` (shell, YAML) and `--` (SQL).  A marker only starts a
    comment at the beginning of a word, which is the rule in all three.
    """
    out = []
    for line in source.splitlines():
        quote = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote is not None:
                if ch == "\\" and quote == '"' and i + 1 < len(line):
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in "'\"":
                quote = ch
                i += 1
                continue
            if line.startswith(marker, i) and (i == 0 or line[i - 1].isspace()):
                break
            i += 1
        out.append(line[:i])
    return "\n".join(out)


def _markdown_code_blocks(source: str) -> str:
    """Only what is inside ``` fences.

    A Markdown file is prose with commands embedded in it.  Telling a
    person to run a client is a violation; writing that this machine has
    none of them is the documentation B21 asks for.
    """
    kept = []
    inside = False
    for line in source.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            kept.append(line)
    return "\n".join(kept)


def _code_text(path: Path) -> str | None:
    """The file with its prose removed — or None if it is not text at all."""
    try:
        source = path.read_text()
    except UnicodeDecodeError:
        return None
    if path.suffix == ".py":
        return _python_code_text(source)
    if path.suffix in (".yaml", ".yml", ".sh") or path.name == "run-demo":
        return _strip_to_end_of_line(source, "#")
    if path.suffix == ".sql":
        return _strip_to_end_of_line(source, "--")
    if path.suffix in (".md", ".markdown"):
        return _markdown_code_blocks(source)
    return source


#: B21's one named exception: the container's own HEALTHCHECK, which runs
#: `pg_isready` INSIDE the image (where it exists) and which `./run-demo`
#: never reads.  Built from the tuple rather than typed, so this pattern
#: cannot be the thing that puts the name in this file.
_HEALTHCHECK_TEST_RE = re.compile(
    r'^\s*test:\s*\[\s*"CMD-SHELL"\s*,\s*"'
    + re.escape(_B21_CLIENT_BINARIES[1])
    + r'(?: [^"]*)?"\s*\]\s*$'
)


def _permitted_healthcheck_lines(path: Path) -> list[str]:
    """The compose lines B21's parenthesis allows — asserted by POSITION.

    A line is permitted only if it is the `test:` command of a block whose
    owning key is `healthcheck:`.  The same text one key higher up — say as
    a `command:` for the service itself — is not permitted, because that
    would run on the host's behalf rather than inside the image.
    """
    lines = path.read_text().splitlines()
    permitted = []
    for n, line in enumerate(lines):
        if not _HEALTHCHECK_TEST_RE.match(line):
            continue
        indent = len(line) - len(line.lstrip())
        for previous in reversed(lines[:n]):
            if not previous.strip() or previous.lstrip().startswith("#"):
                continue
            if len(previous) - len(previous.lstrip()) < indent:
                if previous.strip() == "healthcheck:":
                    permitted.append(line.strip())
                break
    return permitted


def test_b21_no_postgres_client_binary_is_invoked_from_the_demo_tree():
    """B33 part 1 — the three names, over the demo tree's CODE."""
    compose = _DEMO_DIR / "compose.yaml"
    permitted = set(_permitted_healthcheck_lines(compose)) if compose.exists() else set()

    findings = []
    for path in _demo_tree_files():
        where = str(path.relative_to(_REPO_ROOT))
        code = _code_text(path)
        if code is None:
            raw = path.read_bytes()
            for name in _B21_CLIENT_BINARIES:
                if name.encode() in raw:
                    findings.append(f"{where} (binary) — {name}")
            continue
        for line in code.splitlines():
            for name in _B21_CLIENT_BINARIES:
                if name not in line:
                    continue
                if path == compose and line.strip() in permitted:
                    continue  # B21's own parenthesis; asserted separately
                findings.append(f"{where} — {name} — {line.strip()[:100]}")

    assert findings == [], (
        "B21/B33: a Postgres client binary is named in the demo tree's code. "
        "This machine has none of them on the host; the readiness wait is a "
        "Python poll, the load is COPY through the driver, and runtime.sql "
        "is one execute:\n  " + "\n  ".join(findings)
    )


def test_b21_the_healthcheck_exception_is_exactly_one_line_and_is_where_it_says():
    """B33 part 2 — the one permitted occurrence, bounded."""
    compose = _DEMO_DIR / "compose.yaml"
    permitted = _permitted_healthcheck_lines(compose)
    assert len(permitted) == 1, (
        "B21 permits ONE occurrence — the container's own HEALTHCHECK — and "
        f"this file has {len(permitted)}: {permitted}"
    )
    assert "CMD-SHELL" in permitted[0], (
        "the permitted occurrence must run inside the image"
    )

    code = _code_text(compose)
    assert code.count(_B21_CLIENT_BINARIES[1]) == 1, (
        "the readiness client appears in compose.yaml's code more than once; "
        "only the HEALTHCHECK's test command may name it"
    )
    for name in (_B21_CLIENT_BINARIES[0], _B21_CLIENT_BINARIES[2]):
        assert name not in code, (
            f"{name} has no exception anywhere, including in compose.yaml"
        )


_PROCESS_STARTING_ATTRIBUTES = (
    "system", "popen", "execv", "execve", "execl", "execlp", "execvp",
    "spawnv", "spawnl", "fork", "forkpty", "posix_spawn",
)


def _process_starting_nodes(path: Path) -> list[str]:
    """Every place this file starts, or prepares to start, a process."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("subprocess", "pty", "multiprocessing"):
                    found.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in ("subprocess", "pty", "multiprocessing"):
                found.append(f"line {node.lineno}: from {node.module} import …")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                dotted = f"{func.value.id}.{func.attr}"
                if func.value.id == "subprocess" or (
                    func.value.id == "os" and func.attr in _PROCESS_STARTING_ATTRIBUTES
                ):
                    found.append(f"line {node.lineno}: {dotted}(…)")
    return found


def test_b21_nothing_the_demo_actually_runs_starts_a_process():
    """B33 part 3 — the demo's own modules never fork.

    `demo/tests/` is excluded and says so out loud: the suite really does
    run `git status` (AC-35) and `venv` + `pip` (the wheelhouse), and both
    are checks ABOUT the demo rather than things the demo does.  They are
    held to part 1 instead, which is what stops a test shelling out to a
    client the demo itself is forbidden.
    """
    offenders = {}
    for path in _demo_tree_files():
        if path.suffix != ".py" or "tests" in path.parts:
            continue
        found = _process_starting_nodes(path)
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, (
        "the demo starts a process. The readiness wait is a Python poll "
        "(B21), the load is COPY through the driver and runtime.sql is one "
        f"execute — nothing here needs to fork: {offenders}"
    )


def test_b21s_checker_would_actually_catch_one(tmp_path):
    """B33 part 4 — the checker, watched catching something (plan §8.2).

    Three files: one shell script that really invokes a client, one Python
    module that really starts one, and one that only talks about them.  A
    checker that has only ever returned "clean" is a checker nobody has
    seen work.
    """
    client = _B21_CLIENT_BINARIES[0]

    guilty_shell = tmp_path / "run-demo"
    guilty_shell.write_text(
        "#!/usr/bin/env bash\n"
        f"# this comment mentions {client} and is not the violation\n"
        f'{client} -h 127.0.0.1 -p 55440 -c "select 1"\n'
    )
    code = _code_text(guilty_shell)
    assert code.count(client) == 1, (
        "the comment should have been stripped and the command kept"
    )

    guilty_python = tmp_path / "guilty.py"
    guilty_python.write_text(
        '"""A docstring saying we never shell out."""\n'
        "import subprocess\n"
        f'subprocess.run(["{client}", "-l"])\n'
    )
    assert _process_starting_nodes(guilty_python) == [
        "line 2: import subprocess",
        "line 3: subprocess.run(…)",
    ]
    assert client in _code_text(guilty_python)

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        f'"""This machine has no {client}, which is why B21 exists."""\n'
        f"# and no {_B21_CLIENT_BINARIES[1]} either\n"
        "PORT = 55440\n"
    )
    assert _process_starting_nodes(innocent) == []
    for name in _B21_CLIENT_BINARIES:
        assert name not in _code_text(innocent), (
            "prose about a client is not an invocation of one"
        )

    innocent_markdown = tmp_path / "notes.md"
    innocent_markdown.write_text(
        f"This machine has no {client}.\n\n```\nrun-demo up\n```\n"
    )
    assert client not in _code_text(innocent_markdown)


# ═════════════════════════════════════════════════════════════════════════
# AC-32 (round-1 review) — nothing the page loads reaches another host
# ═════════════════════════════════════════════════════════════════════════
#
# WHAT WENT WRONG, AND WHY THE GUARD THAT EXISTED COULD NOT SEE IT
# -------------------------------------------------------------------------
# `demo/vendor/styles/watery.css:8` is a live `@import url(…)` pointing at
# Google's font service.  `demo/static/index.html` links that sheet, a
# browser fetches an applied sheet's `@import` unconditionally, and the app
# served the file verbatim — so every page load of a demo presented as
# fully offline went out to another host.  No Content-Security-Policy
# stopped it and no service worker intercepted it.
#
# The guard that was supposed to stop this
# (`test_ui.py::test_nothing_on_the_page_is_fetched_from_another_host`)
# read exactly two files BY NAME — `index.html` and `demo.css` — neither of
# which has ever contained the string it searches for.  It was structurally
# incapable of failing on the file that broke the promise.  The assertion
# was not wrong; the SCOPE was.  A hand-listed pair of files is a guess
# about where the violation will be, and the violation was elsewhere.
#
# WHAT THIS ONE DOES INSTEAD
# -------------------------------------------------------------------------
# It reads no list of files.  It starts at `GET /` and FOLLOWS what the
# screen actually loads — the stylesheets it links, the `@import`s and
# `url(…)`s inside those, the two bundles, the sprite the bundles resolve,
# the fonts `demo.css` declares — fetching every one THROUGH THE APP, so
# what is scanned is the bytes on the wire rather than the bytes on disk.
#
# That distinction is the whole point, twice over.  It is why this test can
# see the vendored `@import` at all (it lives on disk in a file this
# project may not edit — D1 vendors `watery.css` byte-identical from GIMS
# and `demo/manifest.json` pins its digest), and it is why it can confirm
# the fix (which happens on the wire, in the serving layer that composes
# what goes out: `demo/server/app.py :: offline_css`).
#
# THE RULE, AND WHY IT IS COARSER THAN THE PROPERTY
# -------------------------------------------------------------------------
# No TEXT asset the page loads may contain any URL that names a host —
# `scheme://host…` or `//host…` — in ANY position at all.  Not "no URL in a
# fetching position": deciding whether a string literal buried in minified
# JavaScript is an argument to `fetch` is a judgement call, and a guard
# that has to make judgement calls about 140 KB of minified React is a
# guard nobody can check.  A substring rule cannot be argued past.  The
# price is that the handful of literals which genuinely are NOT addresses
# have to be named — and naming six of them once, with each one's
# inertness proved rather than asserted, is the cheaper half of the trade.
#
# TWO CARVE-OUTS, BOTH NARROW AND BOTH CHECKED
# -------------------------------------------------------------------------
#   BINARY assets are not scanned.  `inter-latin-ext.woff2` contains the
#   two bytes `//` three times by coincidence — it is a compressed font,
#   not a document, and no browser follows a URL out of one.  The carve-out
#   is decided by the CONTENT TYPE THE APP SERVED, not by file extension,
#   and a test below pins the not-scanned set to exactly the two fonts, so
#   it cannot quietly widen to cover a stylesheet.
#
#   LOOPBACK is not "another host".  `127.0.0.1`/`localhost`/`[::1]` cannot
#   leave the machine, and AC-32 is about the network.  Nothing served uses
#   one today; a test below says so, so the exemption stays visible.

import html.parser  # noqa: E402
import urllib.parse  # noqa: E402

#: The host the vendored sheet imports from, written split for the reason
#: `_AC3_FORBIDDEN` above is written split: this file is inside the demo
#: tree, and a sweep for off-host addresses must not find its own guard.
_GOOGLE_FONTS_HOST = "fonts." "googleapis.com"

#: A URL that names a host to go to.  `data:`, `about:blank`, `mailto:` and
#: every relative path have no authority component and are not matched.
_URL_WITH_A_HOST = re.compile(
    r"""
      [a-z][a-z0-9+.\-]* :// [^\s"'`)<>\\]+          # scheme://host/…
    | (?<![A-Za-z0-9_.\-])
      // [A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}    # //host/…  (dotted)
      [^\s"'`)<>\\]*
    """,
    re.I | re.X,
)

#: Hosts that cannot leave this machine.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1", "0.0.0.0")

#: The URLs that appear in what the page loads and are NOT addresses to
#: fetch.  Each is here with the reason it is inert, and each reason is
#: proved mechanically by
#: `test_ac32_every_named_inert_literal_is_still_there_and_still_inert`
#: below, and by the fetching-position check under it, which applies to
#: every off-host URL whether it is on this list or not — an allowlist
#: nobody re-checks is how the next one gets in.
_INERT_NOT_AN_ADDRESS = {
    # The five XML namespace IDENTIFIERS.  A namespace URI is a name, not a
    # location: `createElementNS`/`setAttributeNS` compare it as a string
    # and no user agent has ever dereferenced one.  React carries all five;
    # the two SVG sprites carry the first as their `xmlns`.
    "http://www.w3.org/2000/svg": "XML namespace identifier",
    "http://www.w3.org/1999/xhtml": "XML namespace identifier",
    "http://www.w3.org/1998/Math/MathML": "XML namespace identifier",
    "http://www.w3.org/1999/xlink": "XML namespace identifier",
    "http://www.w3.org/XML/1998/namespace": "XML namespace identifier",
    # React's minified-error text.  React concatenates this into the
    # MESSAGE of an Error it throws, for a developer to paste into a
    # browser by hand; nothing in React fetches it.
    "https://reactjs.org/docs/error-decoder.html?invariant=":
        "an address printed inside an error message, never fetched",
}

#: The syntax that turns a string into a request.  Matched against the
#: characters IMMEDIATELY BEFORE a URL, which is where every one of these
#: puts it — `fetch("…`, `new WebSocket("…`, `src="…`, `.href = "…`.
#:
#: This is the check that carries the allowlist above.  Proving a minified
#: literal is "used as a namespace" by looking for nearby words does not
#: work — minified React puts three namespace comparisons in one 200-byte
#: stretch and a fourth 400 bytes from anything recognisable — and a window
#: widened until it passes is not a check.  Proving it is NOT in a fetching
#: position does work, is exact, and is the property AC-32 actually needs.
_FETCHING_POSITION = re.compile(
    r"""
      (?: fetch | importScripts | sendBeacon | XMLHttpRequest | EventSource
        | WebSocket | Worker | SharedWorker | import | require | open | load )
      \s*\(\s*["'`]\s*$
    | (?: src | href | action | data | poster | srcset | formaction
        | \bxlink:href )
      \s*=\s*["'`]?\s*$
    | (?: @import\s+ )? url\(\s*["'`]?\s*$
    | @import\s+["'`]\s*$
    """,
    re.I | re.X,
)


def _fetching_positions(text: str) -> list[tuple[str, str]]:
    """Every off-host URL in `text` that something is about to FETCH."""
    caught = []
    for m in _URL_WITH_A_HOST.finditer(text):
        before = text[max(0, m.start() - 80):m.start()]
        if _FETCHING_POSITION.search(before):
            caught.append((m.group(0), before[-40:]))
    return caught


def _off_host_urls(text: str) -> list[str]:
    """Every URL in `text` that names a host other than this machine."""
    found = []
    for m in _URL_WITH_A_HOST.finditer(text):
        url = m.group(0)
        host = urllib.parse.urlsplit(
            url if "://" in url else "http:" + url
        ).hostname or ""
        if host in _LOOPBACK_HOSTS:
            continue
        found.append(url)
    return found


# ─────────────────────────────────────────────────────────────────────────
# Following what the screen loads, rather than listing it
# ─────────────────────────────────────────────────────────────────────────

#: Elements whose attribute below makes the browser FETCH something as part
#: of loading the page.  `<a href>` and `<form action>` are navigation, not
#: loading, and are checked for off-host targets without being followed.
_LOADS_A_SUBRESOURCE = {
    "link": ("href",),
    "script": ("src",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "image": ("href", "xlink:href"),
    "use": ("href", "xlink:href"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "iframe": ("src",),
}

_NAVIGATES = {"a": ("href",), "form": ("action",), "area": ("href",)}


class _SubresourceCollector(html.parser.HTMLParser):
    """Every reference an HTML (or SVG) document makes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.loads: list[str] = []
        self.navigates: list[str] = []
        self.inline_style = False
        self.styles: list[str] = []

    def handle_starttag(self, tag, attrs):
        got = {k.lower(): (v or "") for k, v in attrs}
        for attr in _LOADS_A_SUBRESOURCE.get(tag, ()):
            if got.get(attr):
                self.loads.extend(
                    p.strip().split(" ")[0]
                    for p in got[attr].split(",") if p.strip()
                )
        for attr in _NAVIGATES.get(tag, ()):
            if got.get(attr):
                self.navigates.append(got[attr])
        if got.get("style"):
            self.styles.append(got["style"])
        if tag == "style":
            self.inline_style = True

    def handle_endtag(self, tag):
        if tag == "style":
            self.inline_style = False

    def handle_data(self, data):
        if self.inline_style:
            self.styles.append(data)


#: `@import url(…)` / `@import "…"`, and every other `url(…)`.  Quoted
#: forms are matched as whole strings so that a semicolon INSIDE the URL
#: (the Google Fonts one has four, in `wght@300;400;…`) cannot end the
#: at-rule early and leave half an address behind.
_CSS_AT_IMPORT = re.compile(
    r"""@import\s+
        (?: url\(\s* (?: '(?P<a>[^']*)' | "(?P<b>[^"]*)" | (?P<c>[^)\s]*) ) \s*\)
          | '(?P<d>[^']*)' | "(?P<e>[^"]*)" )
        [^;]*;?""",
    re.I | re.X,
)
_CSS_URL = re.compile(
    r"""url\(\s* (?: '(?P<a>[^']*)' | "(?P<b>[^"]*)" | (?P<c>[^)\s]*) ) \s*\)""",
    re.I | re.X,
)

#: Same-origin asset paths written as string literals in the bundles —
#: how `demo/vendor/ui.jsx`'s `Icon` resolves `/static/icons.svg#i-…` and
#: how `app.jsx` names `/static/icons-demo.svg`.  Followed so that an asset
#: only JavaScript knows about is still scanned.
_JS_ASSET_PATH = re.compile(r"""["'`](/(?:static|vendor)/[A-Za-z0-9._/\-]+)""")


def _target(m: re.Match) -> str:
    for name in ("a", "b", "c", "d", "e"):
        try:
            value = m.group(name)
        except IndexError:
            continue
        if value is not None:
            return value.strip()
    return ""


def _references_in(content_type: str, text: str) -> list[str]:
    """Every reference one served asset makes to another."""
    kind = content_type.split(";")[0].strip().lower()
    refs: list[str] = []
    if kind in ("text/html", "image/svg+xml", "application/xhtml+xml"):
        collector = _SubresourceCollector()
        collector.feed(text)
        refs.extend(collector.loads)
        for style in collector.styles:
            refs.extend(_target(m) for m in _CSS_AT_IMPORT.finditer(style))
            refs.extend(_target(m) for m in _CSS_URL.finditer(style))
    elif kind == "text/css":
        refs.extend(_target(m) for m in _CSS_AT_IMPORT.finditer(text))
        refs.extend(_target(m) for m in _CSS_URL.finditer(text))
    elif kind in ("text/javascript", "application/javascript"):
        refs.extend(_JS_ASSET_PATH.findall(text))
    return [r for r in refs if r and not r.startswith(("#", "data:", "about:"))]


def what_the_page_loads(fetch) -> dict[str, tuple[str, bytes]]:
    """Walk out from `/`, following every reference, and return what came
    back: url → (content type, body).

    `fetch(url)` returns `(status, content_type, body)`.  It is a parameter
    rather than a hard-wired client so that the detector test below can run
    this exact walk over a server that answers with a re-introduced remote
    URL — the machinery under test is then the real one, not a copy of it.
    """
    served: dict[str, tuple[str, bytes]] = {}
    queue = ["/"]
    while queue:
        url = queue.pop(0)
        base = url.split("#")[0]
        if base in served:
            continue
        status, content_type, body = fetch(base)
        assert status == 200, (
            f"the page loads {base}, and this app answers {status} for it — "
            "a screen with a broken reference is not a screen that passes"
        )
        served[base] = (content_type, body)
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary: nothing to follow out of it
        for ref in _references_in(content_type, text):
            if _off_host_urls(ref):
                continue  # reported as a violation, not followed off-host
            queue.append(urllib.parse.urljoin(base, ref).split("#")[0])
    return served


def _text_assets(served: dict) -> dict[str, str]:
    """The served assets that are documents, and can therefore carry an
    address a browser would follow."""
    out = {}
    for url, (content_type, body) in served.items():
        kind = content_type.split(";")[0].strip().lower()
        if kind.startswith("font/") or kind in ("application/font-woff2",
                                                "application/octet-stream"):
            continue
        try:
            out[url] = body.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out


@pytest.fixture(scope="module")
def served_page():
    """Everything `GET /` pulls in, as this app actually serves it."""
    from fastapi.testclient import TestClient

    from demo.server import app as server_app

    client = TestClient(server_app.app)

    def fetch(url):
        r = client.get(url)
        return r.status_code, r.headers.get("content-type", ""), r.content

    return what_the_page_loads(fetch)


def test_ac32_the_walk_reaches_everything_the_screen_actually_loads(served_page):
    """The scope, proved rather than assumed.

    The old guard passed because it looked at two files.  A walk that
    silently followed nothing would pass the same way, so the walk states
    what it must have reached — and reaching it is the test.
    """
    reached = set(served_page)
    required = {
        "/",
        "/vendor/styles/watery.css",
        "/vendor/styles/dashboard.css",
        "/vendor/styles/shell.css",
        "/vendor/styles/components.css",
        "/static/demo.css",
        "/static/js/vendor.js",
        "/static/js/app.js",
        "/static/fonts/inter-latin.woff2",
        "/static/fonts/inter-latin-ext.woff2",
        "/static/icons.svg",
        "/static/icons-demo.svg",
    }
    missing = sorted(required - reached)
    assert not missing, (
        "the AC-32 walk did not reach these, so nothing checked them:\n  "
        + "\n  ".join(missing)
        + "\nEither the screen stopped loading them or the walk stopped "
          "following the syntax that pulls them in."
    )


def test_ac32_nothing_the_page_loads_names_another_host(served_page):
    """AC-32.  Every byte the screen pulls in, over every asset it pulls
    in, as served — a screen that only looks right online is a screen that
    is wrong."""
    findings = []
    for url, text in sorted(_text_assets(served_page).items()):
        for found in _off_host_urls(text):
            if found in _INERT_NOT_AN_ADDRESS:
                continue
            line = text[:text.index(found)].count("\n") + 1
            findings.append(f"{url}:{line} — {found}")
    assert findings == [], (
        "AC-32 violated — the screen reaches another host. These are the "
        "addresses, in what this app actually served:\n  "
        + "\n  ".join(findings)
        + "\nIf the file carrying it is under demo/vendor/ it may not be "
          "edited (D1, and demo/manifest.json pins its digest): remove it "
          "in the layer that SERVES the file — demo/server/app.py :: "
          "offline_css — the way watery.css's @import is removed."
    )


def test_ac32_only_the_fonts_are_left_unscanned(served_page):
    """The binary carve-out, pinned.  A stylesheet that started arriving as
    `application/octet-stream` would otherwise skip the sweep entirely."""
    scanned = set(_text_assets(served_page))
    unscanned = sorted(set(served_page) - scanned)
    assert unscanned == [
        "/static/fonts/inter-latin-ext.woff2",
        "/static/fonts/inter-latin.woff2",
    ], (
        "the set of assets AC-32's sweep does not read has changed. Only "
        "the two committed woff2 files belong here — a font is not a "
        f"document. Now unscanned: {unscanned}"
    )


def test_ac32_the_page_uses_no_absolute_url_at_all_not_even_loopback(served_page):
    """The loopback exemption, kept visible.  `http://127.0.0.1:8787/…`
    would not break AC-32 — it cannot leave the machine — but nothing the
    screen loads uses one, and an exemption nobody watches is how the next
    absolute URL gets in."""
    with_absolute = {
        url: [m.group(0) for m in _URL_WITH_A_HOST.finditer(text)
              if m.group(0) not in _INERT_NOT_AN_ADDRESS]
        for url, text in _text_assets(served_page).items()
    }
    offenders = {u: v for u, v in with_absolute.items() if v}
    assert offenders == {}, (
        "the screen has started using an absolute URL where a relative "
        f"path would do: {offenders}"
    )


def test_ac32_nothing_the_page_loads_is_about_to_fetch_an_off_host_url(served_page):
    """The allowlist cannot be used to smuggle a real request in.

    The sweep above lets six literals through by NAME.  This one lets
    nothing through: named or not, no off-host URL in anything the page
    loads may sit where the next thing that happens to it is a request.
    An entry on the allowlist that turned into a `fetch("…` argument
    tomorrow fails here even though its text has not changed.
    """
    findings = []
    for url, text in sorted(_text_assets(served_page).items()):
        for found, before in _fetching_positions(text):
            findings.append(f"{url} — {found}   (after: …{before})")
    assert findings == [], (
        "something the page loads is about to fetch another host:\n  "
        + "\n  ".join(findings)
    )


def test_ac32_every_named_inert_literal_is_still_there_and_still_inert(served_page):
    """The allowlist, re-earned rather than trusted (plan §8.2's rule).

    Two ways an allowlist rots: an entry stops being true, or an entry
    stops being NEEDED and stays on as cover for the next one.  Both fail
    here — the first via the fetching-position check above, applied per
    literal; the second because a literal nothing carries any more must be
    deleted rather than left lying about.

    React's error address gets one extra assertion of its own: it is not
    merely "not fetched", it is spliced into a string.  Every occurrence is
    immediately followed by `"+`, which is React concatenating the invariant
    number onto it to build the text of an Error it is about to throw.
    """
    text_by_url = _text_assets(served_page)
    everything = "\n".join(text_by_url.values())
    for literal in sorted(_INERT_NOT_AN_ADDRESS):
        assert literal in everything, (
            f"{literal!r} is named inert above but nothing the page loads "
            "contains it any more. Delete the entry — an allowlist longer "
            "than it needs to be is cover for the next entry."
        )
        for url, text in text_by_url.items():
            start = 0
            while (at := text.find(literal, start)) != -1:
                start = at + len(literal)
                before = text[max(0, at - 80):at]
                assert not _FETCHING_POSITION.search(before), (
                    f"{url} is about to fetch {literal!r}: …{before[-40:]}"
                )

    react = "https://reactjs.org/docs/error-decoder.html?invariant="
    bundle = text_by_url["/static/js/vendor.js"]
    start = 0
    seen = 0
    while (at := bundle.find(react, start)) != -1:
        start = at + len(react)
        seen += 1
        assert bundle[at + len(react):at + len(react) + 2] == '"+', (
            "React's error address is no longer being concatenated into a "
            "message. Re-read what it has become before trusting it."
        )
    assert seen == 1, f"expected one occurrence, found {seen}"


def test_ac32_the_vendored_sheet_is_still_the_reason_this_exists(served_page):
    """The strip, proved load-bearing from both sides (plan §8.2).

    On disk the vendored sheet still carries the off-host `@import` — it
    must, D1 pins it byte-identical to GIMS's own and `test_vendor.py`
    checks the digest.  On the wire it does not.  Remove the serving-layer
    strip and this fails; re-vendor a sheet that no longer has the import
    and this fails too, saying so, rather than leaving dead machinery in
    place that nobody notices has stopped mattering.
    """
    on_disk = (_DEMO_DIR / "vendor" / "styles" / "watery.css").read_text()
    assert _GOOGLE_FONTS_HOST in on_disk, (
        "demo/vendor/styles/watery.css no longer imports a remote font. "
        "Good news — but demo/server/app.py's offline_css and this whole "
        "section now guard nothing. Check whether they are still needed."
    )
    served = served_page["/vendor/styles/watery.css"][1].decode("utf-8")
    assert _GOOGLE_FONTS_HOST not in served, (
        "the vendored sheet is being served verbatim again — the strip in "
        "demo/server/app.py :: offline_css is not applying, and every page "
        "load goes out to another host"
    )
    from demo.server import app as server_app
    assert server_app.STRIPPED_FROM_VENDORED_CSS.get("watery.css"), (
        "nothing was recorded as stripped, so the sheet either changed or "
        "the route stopped running"
    )

    # And the self-hosted face the strip leaves behind really is served.
    inter = served_page["/static/demo.css"][1].decode("utf-8")
    assert "@font-face" in inter and "fonts/inter-latin.woff2" in inter, (
        "the remote Inter is gone and the local one is not there — the "
        "screen would fall back to a system face (D11)"
    )


# ─────────────────────────────────────────────────────────────────────────
# Round-2 review, finding 2 — the strip must hold at EVERY request spelling
# ─────────────────────────────────────────────────────────────────────────
#
# The round-1 fix registered `/vendor/styles/{name}.css` before the raw
# `/vendor` mount, so the CANONICAL path was stripped — and every other
# spelling that resolves to the same file (`/vendor//styles/…`,
# `/vendor/./styles/…`, a `%2e%2e` detour, a trailing slash) fell through
# to the raw mount and went out verbatim, live `@import` and all.  The walk
# above cannot see this: it follows the links the page actually emits,
# which are canonical.  And a test listing the five measured spellings
# would repeat the same mistake one door down — so the spellings below are
# GENERATED from the path's own structure, and the property asserted is
# the fix's stated guarantee itself: no request path serves a vendored
# stylesheet raw.
#
# The client matters as much as the spellings: httpx (and so TestClient)
# collapses dot-segments before sending, exactly the normalisation a
# fronting proxy or a non-browser client is not obliged to do.  So these
# requests are driven as raw ASGI scopes — the same shape uvicorn hands
# the app for such a request: `path` percent-decoded, dot-segments NOT
# collapsed.

def _spellings_of(canonical: str) -> list[str]:
    """Every spelling of `canonical` this generator can derive that a path
    resolver maps to the same file: a doubled slash, a `.` segment, an
    `up-and-back` detour and its percent-encoded twin at EVERY boundary,
    and the trailing-slash forms — derived, not enumerated."""
    parts = canonical.strip("/").split("/")
    out = {canonical}
    for i in range(1, len(parts)):
        head = "/" + "/".join(parts[:i])
        tail = "/".join(parts[i:])
        out.add(f"{head}//{tail}")
        out.add(f"{head}/./{tail}")
        out.add(f"{head}/%2e/{tail}")
        out.add(f"{head}/{parts[i]}/../{tail}")
        out.add(f"{head}/{parts[i]}/%2e%2e/{tail}")
    out.add(canonical + "/")
    out.add(canonical + "//")
    out.add(canonical + "/.")
    return sorted(out)


def _asgi_get_raw(asgi_app, spelling: str) -> tuple[int, bytes]:
    """GET one URL with the path EXACTLY as spelled — no client-side
    normalisation between this test and the app's router."""
    import asyncio

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": urllib.parse.unquote(spelling),
        "raw_path": spelling.encode("latin-1"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"127.0.0.1:8787")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8787),
    }
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(asgi_app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent
                    if m["type"] == "http.response.body")
    return status, body


#: The five spellings round 2 measured serving the raw sheet, kept as
#: witnesses that the GENERATOR covers the known-live bypasses — a subset
#: check on the generator's output, never the guard itself.
_ROUND_2_MEASURED_BYPASSES = (
    "/vendor/./styles/watery.css",
    "/vendor//styles/watery.css",
    "/vendor/styles/watery.css/",
    "/vendor/styles/../styles/watery.css",
    "/vendor/styles/%2e%2e/styles/watery.css",
)


def test_ac32_no_request_spelling_serves_a_vendored_sheet_raw():
    """Finding 2's guarantee, asserted as stated: for every vendored
    stylesheet and every derived spelling, whatever the app serves carries
    no off-host reference — and anything served 200 is byte-identical to
    the canonical offline sheet, so there is exactly ONE version of each
    sheet on the wire, whatever the request looked like."""
    from demo.server import app as server_app

    host = _GOOGLE_FONTS_HOST.encode()
    reached_noncanonical = 0
    for sheet in ("watery", "dashboard", "shell", "components"):
        canonical = f"/vendor/styles/{sheet}.css"
        status, canon_body = _asgi_get_raw(server_app.app, canonical)
        assert status == 200, f"{canonical} answers {status}"
        assert host not in canon_body

        for spelling in _spellings_of(canonical):
            status, body = _asgi_get_raw(server_app.app, spelling)
            assert host not in body, (
                f"{spelling} served the vendored sheet RAW — the off-host "
                "@import is on the wire at a non-canonical spelling, and a "
                "trailing-slash link, a fronting proxy, or GIMS referencing "
                "the sheet differently would leak on every page load"
            )
            if status == 200:
                assert body == canon_body, (
                    f"{spelling} answers 200 with bytes that differ from the "
                    "canonical offline sheet — two versions of one sheet are "
                    "on the wire, and only one of them was checked"
                )
                if spelling != canonical:
                    reached_noncanonical += 1

    # The sweep must actually have exercised the serving path at
    # non-canonical spellings — a wall of 404s would make it vacuous.
    assert reached_noncanonical > 0, (
        "no non-canonical spelling reached a stylesheet at all, so this "
        "test proved nothing about how one is served — if routing changed, "
        "re-derive the spellings before trusting this green"
    )

    # And the generator covers the five bypasses round 2 measured live —
    # the regression this test exists to hold shut.
    generated = set(_spellings_of("/vendor/styles/watery.css"))
    missing = [s for s in _ROUND_2_MEASURED_BYPASSES if s not in generated]
    assert missing == [], (
        f"the spelling generator no longer derives {missing} — the measured "
        "bypasses are outside the sweep, which is the round-1 blindness again"
    )


def test_ac32_the_sweep_would_actually_catch_a_reintroduced_remote_url():
    """The detector, watched catching something (plan §8.2).

    The real walk, over a server that answers exactly as this one does
    except that four assets have grown an off-host reference — one per
    syntax that actually fetches.  The old guard would have caught none of
    these four: three of them are in files it never opened.
    """
    from fastapi.testclient import TestClient

    from demo.server import app as server_app

    client = TestClient(server_app.app)
    cdn = "https://" + "cdn.example" + ".invalid"
    planted = {
        # a stylesheet the page links, but not one the old guard read
        "/vendor/styles/dashboard.css": f"@import url('{cdn}/x.css');\n",
        # the demo's own sheet, via a declaration rather than an at-rule
        "/static/demo.css": f".x {{ background: url({cdn}/bg.png); }}\n",
        # the page itself
        "/": f'<link rel="stylesheet" href="{cdn}/y.css">\n',
        # a committed bundle
        "/static/js/app.js": f'\nvar t = "{cdn}/beacon.gif";\n',
    }
    for url, injected in planted.items():
        def fetch(u, _url=url, _injected=injected):
            r = client.get(u)
            body = r.content
            if u == _url:
                body = _injected.encode() + body
            return r.status_code, r.headers.get("content-type", ""), body

        served = what_the_page_loads(fetch)
        caught = {
            u: [f for f in _off_host_urls(text)
                if f not in _INERT_NOT_AN_ADDRESS]
            for u, text in _text_assets(served).items()
        }
        caught = {u: f for u, f in caught.items() if f}
        assert caught, (
            f"the AC-32 sweep MISSED an off-host URL planted in {url} — "
            "this is the exact shape of the defect it exists to catch"
        )
        assert url in caught, (
            f"the sweep fired, but not on {url} (it reported {sorted(caught)}) "
            "— the walk is not reaching the asset that was poisoned"
        )

        # Three of the four also sit in a fetching position, and the
        # narrower check must see those three.  The fourth — a bare string
        # in a bundle — does NOT, and that asymmetry is the whole argument
        # for the substring rule being the primary one: the narrow check
        # is exact where it applies and blind where it does not.
        fetching = _fetching_positions(_text_assets(served)[url])
        if url == "/static/js/app.js":
            assert not fetching, (
                "a bare string literal is not a fetching position; if this "
                "started matching, the position check has become loose"
            )
        else:
            assert fetching, (
                f"the fetching-position check MISSED the URL planted in "
                f"{url}, which really is about to be fetched"
            )

    # …and does not fire on the page as it really is.
    def honest(u):
        r = client.get(u)
        return r.status_code, r.headers.get("content-type", ""), r.content

    real = what_the_page_loads(honest)
    assert not [
        f for t in _text_assets(real).values() for f in _off_host_urls(t)
        if f not in _INERT_NOT_AN_ADDRESS
    ], "the sweep fires on the page as it really is — it is not usable"


def test_ac32_nothing_the_demo_runs_reaches_out_at_run_time():
    """The other half of the offline promise: no CDN, no telemetry, no
    package index, in anything `up` or `test` executes.

    The sweep above covers what the BROWSER loads.  This covers what the
    machine runs: no module the demo imports carries an outbound HTTP or
    socket client, and the one install the demo performs is fenced with
    `--no-index` (B20).  `run-demo build-ui` is out of scope on purpose and
    that is checked, not assumed: it is a developer verb that says in its
    own usage line that only it uses the network, and `up`/`test` never
    call it.
    """
    outbound = {
        "urllib.request", "urllib.error", "http.client", "requests",
        "httpx", "aiohttp", "socket", "ftplib", "smtplib", "telnetlib",
        "xmlrpc.client", "webbrowser",
    }
    findings = []
    for path in sorted(_DEMO_DIR.rglob("*.py")):
        if _SKIP_DIRECTORIES & set(path.parts):
            continue
        if "tests" in path.relative_to(_DEMO_DIR).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if name in outbound or root in outbound:
                    findings.append(
                        f"{path.relative_to(_REPO_ROOT)}:{node.lineno} — {name}"
                    )
    assert findings == [], (
        "something the demo runs imports an outbound network client:\n  "
        + "\n  ".join(findings)
    )

    launcher = (_REPO_ROOT / "run-demo").read_text().splitlines()
    installs = [
        (n, line) for n, line in enumerate(launcher, start=1)
        if re.search(r"\bpip\b.*\binstall\b", line) and not line.lstrip().startswith("#")
    ]
    assert installs, "no pip install found in run-demo — has the launcher moved?"
    for n, line in installs:
        assert "--no-index" in line, (
            f"run-demo:{n} installs without --no-index (B20), so the demo "
            f"can reach a package index at run time: {line.strip()}"
        )

    # Every `npm` in the launcher is inside build_ui(), the one verb that
    # says it uses the network — asserted by which function encloses it.
    enclosing = None
    npm_lines = []
    for n, line in enumerate(launcher, start=1):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", line)
        if m:
            enclosing = m.group(1)
        if re.search(r"(?<![A-Za-z_-])npm\s", line) and not line.lstrip().startswith("#"):
            npm_lines.append((n, enclosing, line.strip()))
    for n, where, line in npm_lines:
        assert where == "build_ui", (
            f"run-demo:{n} runs npm from {where!r}, not from build_ui — "
            f"`up` and `test` must not touch the network: {line}"
        )


def test_ac32_the_page_carries_a_policy_that_names_no_other_host(served_page):
    """The second fence.

    The sweep above proves nothing the page loads TODAY reaches another
    host.  The Content-Security-Policy proves the browser would refuse one
    tomorrow, in the window between a mistake landing and this suite
    running — which for a demo shown on an employer's network is the
    window that matters.  Its one `'unsafe-inline'` is for style only and
    grants no origin: React writes `element.style` directly and the policy
    has to allow that; what it must never allow is another host.
    """
    page = served_page["/"][1].decode("utf-8")
    m = re.search(
        r"""<meta\s+http-equiv=(?P<q>["'])Content-Security-Policy(?P=q)\s+"""
        r"""content=(?P<r>["'])(?P<policy>.*?)(?P=r)""",
        page, re.I | re.X | re.S,
    )
    assert m, (
        "the page carries no Content-Security-Policy. Without one, a "
        "remote reference that slips into any asset is fetched — which is "
        "exactly how watery.css:8 went out on every page load."
    )
    policy = m.group("policy")
    directives = {
        part.split()[0]: part.split()[1:]
        for part in (p.strip() for p in policy.split(";")) if part
    }
    for directive in ("default-src", "script-src", "style-src", "font-src",
                      "img-src", "connect-src"):
        assert directive in directives, f"{directive} is not in the policy"
        sources = directives[directive]
        assert "'self'" in sources, f"{directive} does not allow this host"
        for source in sources:
            assert source in ("'self'", "'unsafe-inline'", "data:", "'none'"), (
                f"{directive} allows {source!r} — the policy is supposed to "
                "name no host but this one, and a wildcard or an origin "
                "here undoes AC-32"
            )
    assert directives.get("style-src") == ["'self'", "'unsafe-inline'"], (
        "style-src has changed; 'unsafe-inline' is deliberate and narrow "
        "and any other relaxation needs its own reason"
    )
    assert "'unsafe-inline'" not in directives.get("script-src", []), (
        "script-src must not allow inline script: the bundles are "
        "committed files served from this host (B19)"
    )
    assert not _off_host_urls(policy), (
        f"the policy itself names another host: {_off_host_urls(policy)}"
    )


# ═════════════════════════════════════════════════════════════════════════
# Plan §8.1 row 3 (round-1 review) — there is no tolerance, anywhere
# ═════════════════════════════════════════════════════════════════════════
#
# Row 3 of the plan's risk table, verbatim:
#
#   "A near miss hides inside a tolerance.  An absolute difference
#    compared against a tiny negative exponent swallows a real difference
#    … There is no tolerance anywhere in this suite.
#    §7.2's exact-decimal rule makes every compared number a
#    Decimal/numeric rounded half-up to 6 places, so comparison is `==`.
#    A GREP TEST FAILS THE BUILD if math.isclose, pytest.approx, an
#    absolute-difference-under-an-epsilon comparison, or a rel_/abs_
#    tolerance keyword appears anywhere under `demo/`.  Row 3 writes those
#    four out as literal needles; every one of them is written SPLIT below,
#    because this file is inside `demo/` and is swept by its own check.
#    A tolerance is not a testing convenience here; it is
#    the mechanism by which the defect this demo exists to show would be
#    hidden."
#
# §8.3 restates it in one line: "No tolerance. §8.1 row 3, enforced by
# grep."  The grep was never written.  The round-1 review checked by hand
# that the property holds today and found it does — which is the point: a
# rule that holds by discipline holds until the day it does not, and this
# demo's whole subject is a wrong number that runs clean.  A tolerance is
# the one edit that would make the demo's own control stop being able to
# see the thing it exists to see.
#
# WIDER THAN THE FOUR SPELLINGS, AND WHY  (a scope decision, recorded)
# -------------------------------------------------------------------------
# Row 3 names four spellings.  The CONTRACT it is enforcing is "no numeric
# tolerance anywhere in the comparison path", and four spellings are not
# the four ways a tolerance gets in — `unittest`'s own assertion takes one
# as `places=`, `numpy` spells the same keywords r/a + tol, and any
# module's `isclose` does the same job as `math`'s.  A guard that caught
# only the four named spellings would let the next one through and report
# green, which is exactly the failure mode the review found in AC-32's
# guard two sections up.  So the four are rows 1-4 below and the near
# neighbours are rows 5-6, and this paragraph is the record that the scope
# was widened deliberately rather than drifting.
#
# WHAT IS NOT SWEPT
# -------------------------------------------------------------------------
#   `demo/vendor/wheels/*.whl` — third-party distributions, and `pytest`'s
#   own wheel necessarily contains its `approx` helper: shipping an API is
#   not this demo using it, and nothing in these files is on the comparison
#   path (`run-demo` installs them with --no-index, B20).  The exclusion is
#   proved to be load-bearing below rather than assumed, the way AC-37's
#   vendor exclusion is.
#
#   `demo/.venv/`, `__pycache__/`, `.pytest_cache/`, `node_modules/` — not
#   committed at all (`.gitignore`), the same set AC-3's sweep skips.
#
# Everything else is in, `demo/vendor/`'s source files included: a
# tolerance in vendored code the comparison path calls would hide a near
# miss exactly as well as one written here.

#: The needles, each split across two string literals for the reason
#: `_AC3_FORBIDDEN` above is split: this file is inside `demo/`, it is
#: swept by its own check, and it has to be able to WRITE what it looks
#: for.  Python joins each pair at compile time, so the values at run time
#: are the real names and the source text is not a hit.
_ISCLOSE = "iscl" "ose"
_APPROX = "appr" "ox"
_ABS = "ab" "s"
_ALMOST = "Almost" "Equal"
_ALMOST_SNAKE = "al" "most_equal"
_TOL = "t" "ol"

#: (name, pattern, what a hit means).  A tolerance is a comparison that
#: says "close enough"; every row here is one of the ways to write one.
_TOLERANCE_NEEDLES = (
    (
        f"math.{_ISCLOSE}",
        re.compile(rf"(?:\.|\b){_ISCLOSE}\s*\("),
        "a relative/absolute closeness test in place of ==",
    ),
    (
        f"pytest.{_APPROX}",
        re.compile(rf"(?:\.|\b){_APPROX}\s*\(|import[^\n]*\b{_APPROX}\b"),
        "pytest's tolerance wrapper",
    ),
    (
        f"{_ISCLOSE}/{_APPROX} imported by name",
        re.compile(rf"from\s+\S+\s+import[^\n]*\b(?:{_ISCLOSE}|{_APPROX})\b"),
        "the same helpers, brought in under a bare name",
    ),
    (
        "a tolerance keyword",
        re.compile(rf"\b(?:rel_{_TOL}|{_ABS}_{_TOL}|r{_TOL}|a{_TOL})\s*="),
        "the keyword arguments that turn == into 'close enough'",
    ),
    (
        f"{_ABS}(…) compared against an epsilon",
        re.compile(
            rf"\b{_ABS}\s*\([^()\n]*(?:\([^()\n]*\)[^()\n]*)*\)\s*[<>]=?\s*"
            rf"[^\s;,)]*(?:\de-\d|eps|epsilon|tol)",
            re.I,
        ),
        "row 3's own example: a difference, under a tiny exponent",
    ),
    (
        f"assert{_ALMOST} and friends",
        re.compile(rf"assert{_ALMOST}|assertNot{_ALMOST}|{_ALMOST_SNAKE}"),
        "unittest's tolerance, whose default is seven decimal places",
    ),
)

#: Not swept, and each entry's reason is in the block comment above.
_TOLERANCE_SKIP_DIRECTORIES = {
    ".venv", "__pycache__", ".pytest_cache", "node_modules", "wheels",
}


def _tolerance_swept_files():
    """Every file the no-tolerance sweep actually reads."""
    for path in sorted(_DEMO_DIR.rglob("*")):
        if not path.is_file():
            continue
        if _TOLERANCE_SKIP_DIRECTORIES & set(path.parts):
            continue
        yield path


def _tolerance_hits(paths):
    """(path, line number, the line, which needle) for every hit."""
    hits = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a font, a compiled artefact — not a comparison
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pattern, _meaning in _TOLERANCE_NEEDLES:
                if pattern.search(line):
                    try:
                        where = str(path.relative_to(_REPO_ROOT))
                    except ValueError:
                        where = str(path)  # a tmp_path file, in the detector
                    hits.append((where, lineno, line.strip(), name))
    return hits


def test_no_tolerance_anywhere_under_demo():
    """Plan §8.1 row 3 / §8.3, enforced rather than remembered.

    §7.2's exact-decimal rule makes every compared number a Decimal
    rounded half-up to six places, so the comparison is `==` and there is
    nothing a tolerance could be for.  A tolerance appearing here would
    not be a convenience; it is the one edit that makes this demo's
    control stop being able to see a subtly wrong number.
    """
    files = list(_tolerance_swept_files())
    assert files, (
        "the no-tolerance sweep found no files at all — the scope is "
        "broken, not clean"
    )
    hits = _tolerance_hits(files)
    assert hits == [], (
        "plan §8.1 row 3 violated — a numeric tolerance is present under "
        "demo/. Every one of these must go: this demo exists to make a "
        "subtly wrong number visible, and a tolerance is how such a "
        "number stops being visible:\n  "
        + "\n  ".join(f"{p}:{ln}: [{name}] {line}" for p, ln, line, name in hits)
    )


def test_no_tolerance_the_sweep_actually_covers_the_comparison_path():
    """The scope, proved rather than assumed.

    A sweep that quietly stopped reading the files where a tolerance would
    matter would pass exactly as this one does.  These are the files the
    two panes are compared in and the arithmetic they compare.
    """
    swept = {p.relative_to(_REPO_ROOT).as_posix() for p in _tolerance_swept_files()}
    for required in (
        "demo/pyrunner/evaluate.py",
        "demo/pyrunner/order.py",
        "demo/server/app.py",
        "demo/tests/test_walkthrough.py",
        "demo/tests/test_decimal.py",
        "demo/tests/test_isolation.py",
        "demo/vendor/expr.py",
    ):
        assert required in swept, (
            f"{required} is not in the no-tolerance sweep — either it has "
            "moved or the scope above is wrong"
        )


def test_no_tolerance_the_wheelhouse_exclusion_is_a_real_finding_not_an_assumption():
    """The one carve-out, shown to be needed (plan §8.2's rule).

    `pytest` ships its own tolerance helper inside its own wheel.  That is
    a library offering an API, not this demo using one — but the exclusion
    only earns its place while the collision is real, and an exclusion
    that has quietly stopped being needed is cover for the next one.
    """
    import zipfile

    wheels = sorted((_DEMO_DIR / "vendor" / "wheels").glob("pytest-*.whl"))
    assert wheels, "the committed wheelhouse has no pytest wheel — B20 has moved"
    found = False
    with zipfile.ZipFile(wheels[0]) as zf:
        for entry in zf.namelist():
            if not entry.endswith(".py"):
                continue
            try:
                text = zf.read(entry).decode("utf-8")
            except (UnicodeDecodeError, KeyError):
                continue
            if re.search(rf"(?:\.|\b){_APPROX}\s*\(", text):
                found = True
                break
    assert found, (
        f"{wheels[0].name} no longer contains a {_APPROX} call. The "
        "wheelhouse exclusion above may have stopped being needed — "
        "re-check it rather than leaving it in place."
    )
    swept = {p.relative_to(_REPO_ROOT).as_posix() for p in _tolerance_swept_files()}
    assert not any(p.startswith("demo/vendor/wheels/") for p in swept), (
        "demo/vendor/wheels/ leaked into the no-tolerance sweep"
    )
    # …and the rest of demo/vendor/ did NOT get excluded with it.
    assert "demo/vendor/expr.py" in swept, (
        "the wheelhouse exclusion has widened to all of demo/vendor/ — the "
        "vendored calculator is on the comparison path and must be swept"
    )


def test_no_tolerance_the_grep_would_actually_catch_one(tmp_path):
    """The detector, watched catching something (plan §8.2).

    Every spelling in the table, once each, written the way someone would
    actually write it while making a flaky comparison go away — and shown
    NOT to fire on the exact comparisons this suite really does make,
    which are exact equalities and the spec's own two sanctioned bands
    (AC-8's 88-92%, AC-40(a)'s 700-1100).
    """
    real_tolerances = [
        f"assert math.{_ISCLOSE}(sql_total, py_total)",
        f"assert py_total == pytest.{_APPROX}(sql_total)",
        f"from pytest import {_APPROX}",
        f"from math import {_ISCLOSE}",
        f"assert math.{_ISCLOSE}(a, b, rel_{_TOL}=1e-9)",
        f"numpy.allclose(a, b, r{_TOL}=1e-05)",
        f"assert {_ABS}(sql_total - py_total) < 1e-9",
        f"if {_ABS}(a - b) <= EPSILON: return True",
        f"assert {_ABS}(float(x) - float(y)) < {_TOL}",
        f"self.assert{_ALMOST}(sql_total, py_total)",
    ]
    for line in real_tolerances:
        guilty = tmp_path / "guilty.py"
        guilty.write_text(line + "\n")
        hits = _tolerance_hits([guilty])
        assert hits, f"the no-tolerance grep MISSED a real tolerance: {line!r}"

    innocent = [
        "assert py_total == sql_total",
        'assert rows[0]["total"] == Decimal("400207.000000")',
        "assert 88 <= pct <= 92  # AC-8's band, and 861 is asserted exactly",
        "assert 700 <= elapsed_rows <= 1100  # AC-40(a)'s band",
        f"width = {_ABS}(left - right)",
        f"n = {_ABS}(index)",
        "# the two panes are compared exactly, never approximately",
        "assert kind == 'numeric' and value == Decimal('1.100000')",
    ]
    for line in innocent:
        clean = tmp_path / "clean.py"
        clean.write_text(line + "\n")
        hits = _tolerance_hits([clean])
        assert not hits, (
            f"the no-tolerance grep wrongly fired on an exact comparison: "
            f"{line!r} → {hits}"
        )
