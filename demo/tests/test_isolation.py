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
