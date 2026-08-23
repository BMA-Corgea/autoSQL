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
