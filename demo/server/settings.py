"""demo/server/settings.py — the compose-file constants and the two pinned
session values.

**One source of truth.**  The database name, the role, the password and the
host port are read out of ``demo/compose.yaml`` at import time rather than
retyped here, exactly as ``./run-demo`` and ``demo/seed/load.py`` read them.
A demo whose server and whose compose file disagree about the port would be
a demo that connects somewhere the compose file never described, which is
the whole class of accident AC-2 exists to make impossible.

**The two pinned session values** (spec §4.9 and §7.1's time-bucket rule):

* ``extra_float_digits = 1`` — how many digits a float prints.
* ``TimeZone = UTC`` — where a day starts, and therefore whether
  walkthrough step 7 has seven buckets or eight.

Both change the answer and neither is visible anywhere else on the screen,
so §9.3 puts them at the foot of the SQL pane and AC-26 asserts they are
there.  ``db.connect()`` SETs them explicitly on every connection and reads
them back — see B13-EXT-3 in that module for the measurement that made an
explicit ``SET`` necessary rather than merely tidy.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "DEMO_DIR", "COMPOSE_FILE",
    "DB_HOST", "DB_PORT", "APP_HOST", "APP_PORT",
    "SSLMODE", "CONNECT_TIMEOUT", "APPLICATION_NAME",
    "TIME_ZONE", "EXTRA_FLOAT_DIGITS", "PINNED_SESSION_SQL",
    "PAGE_SIZE", "COLLECTION_KEYS_SQL",
    "compose_config",
]

DEMO_DIR = Path(__file__).resolve().parent.parent
COMPOSE_FILE = DEMO_DIR / "compose.yaml"

#: The demo's own database, and the only endpoint db.connect() will dial.
#: Both halves are checked before every connection (B13).
DB_HOST = "127.0.0.1"
DB_PORT = 55440

#: The app (spec §11.2).  Loopback only.
APP_HOST = "127.0.0.1"
APP_PORT = 8787

SSLMODE = "disable"          # loopback to a container the demo created
CONNECT_TIMEOUT = 10         # seconds; explicit so PGCONNECT_TIMEOUT cannot bite
APPLICATION_NAME = "autosql-demo"

#: The two pinned session values, as the names Postgres shows them under.
TIME_ZONE = "UTC"
EXTRA_FLOAT_DIGITS = "1"

#: What db.connect() executes on every connection — and what the SQL pane
#: prints at its head, so the pane's first two lines are literally the
#: statements that ran (the approved mock draws exactly these two lines).
PINNED_SESSION_SQL = (
    "SET extra_float_digits = 1;",
    "SET TIME ZONE 'UTC';",
)

#: B25 — the panes render a page; the comparison is over the whole result.
PAGE_SIZE = 50

#: §4.4 item 3's per-collection vocabulary read, written exactly once here
#: and used by /api/fields, by the alias validator's caller and by nothing
#: else.  The alias check is only as trustworthy as this list being read
#: from the data rather than typed.
COLLECTION_KEYS_SQL = (
    "SELECT DISTINCT k FROM demo.records, LATERAL jsonb_object_keys(data) AS k"
    " WHERE collection = %(collection)s ORDER BY k"
)


class ComposeMismatch(RuntimeError):
    """demo/compose.yaml does not describe the database this demo owns."""


def _value(text: str, key: str) -> str:
    m = re.search(rf"^\s*{key}:\s*(\S+)\s*$", text, re.MULTILINE)
    if not m:
        raise ComposeMismatch(f"demo/compose.yaml: no {key} line found")
    return m.group(1)


def compose_config() -> dict:
    """The four values the connection needs, read from ``demo/compose.yaml``.

    Returns ``{"port", "dbname", "user", "password"}``.  The port is
    returned as the compose file states it — **not** as the constant above
    — precisely so that ``db.connect()``'s guard has something real to
    check.  A guard that compares a constant to itself proves nothing.
    """
    text = COMPOSE_FILE.read_text()
    m = re.search(r'"127\.0\.0\.1:(\d+):5432"', text)
    if not m:
        raise ComposeMismatch(
            "demo/compose.yaml: no 127.0.0.1-bound host port mapping found"
        )
    return {
        "port": int(m.group(1)),
        "dbname": _value(text, "POSTGRES_DB"),
        "user": _value(text, "POSTGRES_USER"),
        "password": _value(text, "POSTGRES_PASSWORD"),
    }
