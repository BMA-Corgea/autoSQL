"""demo/server/db.py — THE ONLY connection factory in this tree (B13).

Plan §4.5's last row: *"the connection — ``demo/server/db.py :: connect()``
— everything; nothing else imports the driver."*  ``connect()`` is the one
function in ``demo/`` that returns a database connection, and it **raises**
rather than dials if the endpoint it is about to open is not this demo's
own Postgres on ``127.0.0.1:55440``.

──────────────────────────────────────────────────────────────────────────
THE MECHANISM (B13)
──────────────────────────────────────────────────────────────────────────
Every libpq connection parameter is passed **explicitly**.  libpq's
environment variables are defaults consulted only when the parameter is
absent, so with all of them supplied no environment variable can change
where the demo connects — including ones nobody thought to enumerate.  A
test that only unsets known names could never prove that; passing them all
can.

THE LIST (B13), the union of AC-2(c)'s and §11.2's, enumerated once here
and poisoned wholesale by ``demo/tests/test_isolation.py``:

    AUTOSQL_SPIKE_DSN, PGHOST, PGHOSTADDR, PGPORT, PGDATABASE, PGUSER,
    PGPASSWORD, PGPASSFILE, PGSERVICE, PGSERVICEFILE, PGSSLMODE, PGOPTIONS,
    PGCONNECT_TIMEOUT

— and ``HOME`` pointed at a temporary directory containing a hostile
``.pgpass``, which is the only way to test the ``~/.pgpass`` half at all.

──────────────────────────────────────────────────────────────────────────
THREE EXTENSIONS TO B13, EACH MEASURED ON THIS MACHINE BEFORE IT WAS
WRITTEN.  B13 names eight parameters.  Passing exactly those eight does
NOT hold its own poisoned list; here is what was measured against
psycopg 3.3.4 / libpq 16, and what each measurement forced.
──────────────────────────────────────────────────────────────────────────

**B13-EXT-1 — ``hostaddr`` must be passed, or ``PGHOSTADDR`` redirects the
connection.**  B13's eight are host, port, dbname, user, password, sslmode,
connect_timeout, application_name.  ``hostaddr`` is not among them, yet
``PGHOSTADDR`` is on B13's own poisoned list.  Measured: with
``host="127.0.0.1"`` passed explicitly and ``PGHOSTADDR=127.0.0.9`` in the
environment, libpq dialled **127.0.0.9** — *"connection to server at
127.0.0.9, port 55440 failed"*.  ``host`` is used only for name lookup and
certificate matching once ``hostaddr`` is set; ``hostaddr`` is the address
actually dialled.  Passing it explicitly closes the hole, and the poisoned
run then reaches the demo's own database.  **This was the one parameter
whose absence could still send the demo somewhere it did not choose.**

**B13-EXT-2 — ``PGSERVICE``/``PGSERVICEFILE`` are removed from the
environment for the duration of the call.**  Measured twice:
(a) a service file that redefines host and port does **not** override the
explicitly-passed ones — the connection still reached this demo's own
database, so a service cannot *redirect* anything; but
(b) ``PGSERVICE`` naming a service that does not exist makes libpq refuse
to connect at all — *"definition of service … not found"* — and passing
``service=""`` does not help, because libpq then looks for a service named
``""`` and fails on that instead.
So the service variables can only ever **break** this connection, never
move it, and AC-2(c) requires the factory to still return its connection
with ``PGSERVICE`` set to nonsense.  They are therefore removed for the
duration of the ``psycopg.connect`` call and restored immediately.  This is
the one place where a named variable is touched, it is done for the two
variables that provably cannot redirect, and every parameter stays
explicit regardless.

**B13-EXT-3 — the two pinned session values are ``SET`` and then read back,
because ``options`` does not hold ``PGTZ``.**  ``demo/seed/load.py`` passed
them as ``options="-c timezone=UTC -c extra_float_digits=1"``.  Measured:
``PGOPTIONS`` in the environment is correctly ignored when ``options`` is
passed — but ``PGTZ=America/New_York`` **wins over it**, and the session
opened at ``TimeZone = America/New_York``.  That is precisely the silent
wrong number this project exists to prevent: an inherited ``PGTZ`` turns
walkthrough step 7 from seven buckets into eight while every query still
runs clean.  ``options`` is still passed (it closes ``PGOPTIONS``), and on
top of it every connection executes ``SET extra_float_digits = 1`` and
``SET TIME ZONE 'UTC'`` and then **reads both back**, raising if either is
not what §4.9 and §7.1's time-bucket rule pin.  The approved mock already
draws those two statements at the head of the SQL pane — after this
measurement they are literally the statements that ran.

──────────────────────────────────────────────────────────────────────────
THE FENCE
──────────────────────────────────────────────────────────────────────────
* ``connect()`` is the only function here that returns a connection.
* It reads the host port from ``demo/compose.yaml`` and **raises**
  :class:`WrongDatabase` if it is not ``55440``, or if the host is not
  ``127.0.0.1`` — before the driver is called, so a wrong endpoint is never
  dialled rather than dialled and dropped.
* After connecting it confirms it reached the database and role the compose
  file names, and raises if it did not.
* ``demo/tests/test_isolation.py`` asserts no other module in the demo tree
  imports the driver.

There is deliberately no way to ask this module for a connection to
anything else.  It takes no host, port, database or DSN argument, and the
guard is on the path that dials rather than in a helper a caller could
route around.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from decimal import Decimal

import psycopg
from psycopg import postgres
from psycopg.types.json import set_json_loads

from . import settings

__all__ = [
    "WrongDatabase", "POISONED_ENVIRONMENT", "SERVICE_ENVIRONMENT",
    "connect", "connection_parameters",
    "exact_json_cursor", "column_kinds",
]


#: B13's union list, enumerated once, in code, so the test poisons exactly
#: this and a new name is added in one place.  ``HOME`` is listed last
#: because it is not a libpq variable: it is how ``~/.pgpass`` is reached.
POISONED_ENVIRONMENT = (
    "AUTOSQL_SPIKE_DSN",
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSSLMODE",
    "PGOPTIONS",
    "PGCONNECT_TIMEOUT",
    "HOME",
)

#: B13-EXT-2 — the two that can only break the connection, never move it.
SERVICE_ENVIRONMENT = ("PGSERVICE", "PGSERVICEFILE")


class WrongDatabase(RuntimeError):
    """The factory was about to open a connection it is not allowed to open.

    Raised **before** the driver is called.  This demo owns one database,
    on one loopback port, in a container it created; every other Postgres
    on this machine — including live ones holding real data — is out of
    bounds, and the correct behaviour on any doubt is to refuse rather than
    to connect and find out.
    """


@contextmanager
def _without_service_environment():
    """B13-EXT-2, scoped as tightly as it can be scoped."""
    saved = {k: os.environ[k] for k in SERVICE_ENVIRONMENT if k in os.environ}
    for k in saved:
        del os.environ[k]
    try:
        yield
    finally:
        os.environ.update(saved)


def connection_parameters(application_name: str | None = None) -> dict:
    """Every libpq parameter this demo passes, explicitly, as a dict.

    Exposed so ``demo/tests/test_isolation.py`` can assert the set rather
    than trust the prose above, and so a reviewer can read the whole
    connection in one screen.  Building it does not open anything.
    """
    cfg = settings.compose_config()
    return {
        # where — host for name/certificate purposes, hostaddr for the
        # address actually dialled (B13-EXT-1).
        "host": settings.DB_HOST,
        "hostaddr": settings.DB_HOST,
        "port": cfg["port"],
        # what
        "dbname": cfg["dbname"],
        "user": cfg["user"],
        "password": cfg["password"],
        # how
        "sslmode": settings.SSLMODE,
        "connect_timeout": settings.CONNECT_TIMEOUT,
        "application_name": application_name or settings.APPLICATION_NAME,
        # the two pinned values, also SET and verified after connecting
        # (B13-EXT-3); passing them here is what closes PGOPTIONS.
        "options": (
            f"-c timezone={settings.TIME_ZONE}"
            f" -c extra_float_digits={settings.EXTRA_FLOAT_DIGITS}"
        ),
    }


def _guard(host: str, port: int) -> None:
    """Refuse any endpoint but this demo's own.  Called before every dial."""
    if host != settings.DB_HOST or port != settings.DB_PORT:
        raise WrongDatabase(
            f"refusing to connect to {host}:{port} — this demo owns "
            f"{settings.DB_HOST}:{settings.DB_PORT} (its own container, its "
            "own invented rows) and connects to nothing else on this "
            "machine, under any circumstance"
        )


def _verify(conn, params: dict) -> None:
    """Confirm what was actually reached, and what the values actually are.

    Four reads, and each one is a claim this demo makes on screen:
    the database and the role are the compose file's, ``extra_float_digits``
    is 1 and ``TimeZone`` is UTC.  A mismatch raises — B13-EXT-3 measured a
    real environment that quietly changed the last of them.
    """
    for statement in settings.PINNED_SESSION_SQL:
        conn.execute(statement)

    got_db, got_user = conn.execute(
        "SELECT current_database(), current_user"
    ).fetchone()
    if got_db != params["dbname"] or got_user != params["user"]:
        raise WrongDatabase(
            f"connected to database {got_db!r} as {got_user!r}, but "
            f"demo/compose.yaml describes {params['dbname']!r} as "
            f"{params['user']!r} — refusing to use this connection"
        )

    got_tz = conn.execute("SHOW TimeZone").fetchone()[0]
    got_efd = conn.execute("SHOW extra_float_digits").fetchone()[0]
    if got_tz != settings.TIME_ZONE:
        raise WrongDatabase(
            f"the session opened at TimeZone = {got_tz!r} and would not "
            f"stay at {settings.TIME_ZONE!r}; the time zone decides where a "
            "day starts, so a bucketed answer on this connection would be "
            "wrong while looking entirely correct (§7.1's time-bucket rule)"
        )
    if got_efd != settings.EXTRA_FLOAT_DIGITS:
        raise WrongDatabase(
            f"the session opened at extra_float_digits = {got_efd!r} and "
            f"would not stay at {settings.EXTRA_FLOAT_DIGITS!r}; the setting "
            "decides how many digits a float prints (§4.9)"
        )


def connect(*, application_name: str | None = None, autocommit: bool = False):
    """Open the demo's one connection, or raise.

    The only function in ``demo/`` that returns a database connection.  It
    takes no endpoint argument on purpose: there is nowhere else to go.
    """
    params = connection_parameters(application_name)
    _guard(params["host"], params["port"])
    # `hostaddr` is the address actually dialled (B13-EXT-1), so it is
    # guarded too.  It is checked when present rather than demanded,
    # because `test_isolation.py` removes it on purpose to show what its
    # absence costs — and the whole point of that test is that libpq, not
    # a KeyError, is what answers.
    if "hostaddr" in params:
        _guard(params["hostaddr"], params["port"])
    with _without_service_environment():
        conn = psycopg.connect(**params, autocommit=autocommit)
    try:
        _verify(conn, params)
    except BaseException:
        conn.close()
        raise
    return conn


# ═════════════════════════════════════════════════════════════════════════
# The driver boundary, kept here for the same reason the connection is:
# nothing else in demo/ imports psycopg (plan §4.5).
# ═════════════════════════════════════════════════════════════════════════

#: Postgres type OID → the demo's four value kinds.  The kind decides how a
#: cell is compared and how it is displayed, and it is read from the
#: EXECUTED statement's own cursor rather than guessed from a column name,
#: so a builder change cannot quietly re-type a column behind the panes.
_KIND_BY_TYPE_NAME = {
    "text": "text", "varchar": "text", "bpchar": "text", "name": "text",
    "jsonb": "json", "json": "json",
    "numeric": "exact",
    "int2": "int", "int4": "int", "int8": "int",
    "bool": "bool",
}


def _exact_loads(data):
    """json.loads with every non-integer number kept as an exact Decimal.

    The two panes are compared with ``==`` and no tolerance anywhere
    (plan §8.1 row 3).  The default loader turns a jsonb number into a
    Python float, which loses digits for any value a double cannot hold —
    and a lost digit on one side only reads as a disagreement that is not
    real.  Reading jsonb exactly removes that whole class of false
    disagreement, and costs nothing: the Python pane already parses the
    same text the same way (B7's ``record_d``).
    """
    import json  # local: keeps the module's import list to the driver

    return json.loads(data, parse_float=Decimal)


def exact_json_cursor(conn):
    """A cursor on *conn* whose jsonb arrives as exact Python values.

    Scoped to the cursor on purpose.  The connection's own loaders are
    left alone so that every other caller in the suite keeps the ordinary
    float behaviour it was written against.
    """
    cur = conn.cursor()
    set_json_loads(_exact_loads, context=cur)
    return cur


def column_kinds(cursor) -> tuple:
    """The value kind of each column of an executed statement.

    One of ``text`` / ``json`` / ``exact`` / ``int`` / ``bool`` per column.
    ``exact`` is Postgres's ``numeric`` — the type §7.2's exact-decimal
    rule lands in, and the one whose scale must survive to the screen so
    ``41.000000`` does not print as ``41``.
    """
    kinds = []
    for col in cursor.description:
        info = postgres.types.get(col.type_code)
        name = info.name if info is not None else None
        if name not in _KIND_BY_TYPE_NAME:
            raise WrongDatabase(
                f"column {col.name!r} came back as Postgres type "
                f"{name or col.type_code!r}, which this demo has no "
                "comparison rule for — refusing to guess"
            )
        kinds.append(_KIND_BY_TYPE_NAME[name])
    return tuple(kinds)
