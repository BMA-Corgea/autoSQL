"""INVENTED DATA — installs the demo schema, runtime.sql, and the fabricated rows.

This module owns the write path into the demo database (T-2-plan.md §5, W5):

  1. `demo/seed/schema.sql` — the one table, if it is not already there.
  2. `spikes/T-1/proto/runtime.sql` — installed UNMODIFIED into the `xpr`
     schema (spec §9.6, AC-33): the file's sha256 is checked against
     `demo/manifest.json` before a byte of it is executed, and it is issued
     as one statement batch through the driver (B21 — this machine has no
     Postgres client binaries, and nothing in the demo tree shells out to
     one).
  3. The 10,410 generated rows, via the driver's COPY … FROM STDIN (B21),
     inside one transaction — a failed run leaves nothing behind.

Every row is invented (AC-11, B31 third place): fabricated by
demo/seed/generate.py from fixed literal seeds, describing nothing real.
The console line this module prints on every run says so too.

AC-10's digest: `records_digest()` computes an md5 over all rows ordered by
(collection, key); the expected value is recorded in `demo/manifest.json`
under MANIFEST_DIGEST_KEY (once, via `--record-digest`), so a third party
can check a checkout without running the seed twice. Every ordinary run
verifies the freshly seeded database against that recorded digest and fails
loudly on any difference — this project's failure mode is a subtly wrong
number that still runs clean, so the seed refuses to "run clean" past one.
"""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"
_MANIFEST_PATH = _DEMO_DIR / "manifest.json"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_RUNTIME_SQL_PATH = _REPO_ROOT / "spikes" / "T-1" / "proto" / "runtime.sql"
_RUNTIME_SQL_MANIFEST_KEY = "spikes/T-1/proto/runtime.sql"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from demo.seed import generate  # noqa: E402

# The manifest entry AC-10's checks compare against (W5's done column).
MANIFEST_DIGEST_KEY = "seed:demo.records:md5"

# AC-10's digest, defined once so the seed, the suite and B10's session
# guard can never drift apart: md5 over every row, ordered by
# (collection, key) — byte order, because the cluster is initdb'ed with
# --locale=C (demo/compose.yaml).
DIGEST_SQL = (
    r"SELECT md5(string_agg("
    r"collection || E'\x1f' || key || E'\x1f' || data::text, E'\n' "
    r"ORDER BY collection, key)) FROM demo.records"
)

# B31's third place — printed on every run, seeded or not (AC-11 asserts
# this line and the generator's header).
INVENTED_DATA_LINE = (
    "demo/seed: this database holds INVENTED data only — every row was "
    "fabricated by demo/seed/generate.py from fixed literal seeds; "
    "nothing in it is real."
)

EXPECTED_COUNTS = {
    "noun:Heartbeat": 8400,
    "noun:Sample": 2000,
    "noun:EdgeCase": 10,
}

_DEMO_DB_PORT = 55440  # the ONLY port anything in this tree may dial


class SeedError(RuntimeError):
    """A seed-time check failed. Nothing was committed."""


# ---------------------------------------------------------------------------
# The connection.
# ---------------------------------------------------------------------------

def _compose_config() -> dict:
    """The database name/role/password and host port, read from
    demo/compose.yaml so there is exactly one place they can drift from
    (the same rule ./run-demo applies)."""
    text = (_DEMO_DIR / "compose.yaml").read_text()

    def value(key: str) -> str:
        m = re.search(rf"^\s*{key}:\s*(\S+)\s*$", text, re.MULTILINE)
        if not m:
            raise SeedError(f"demo/compose.yaml: no {key} line found")
        return m.group(1)

    m = re.search(r'"127\.0\.0\.1:(\d+):5432"', text)
    if not m:
        raise SeedError("demo/compose.yaml: no 127.0.0.1-bound host port found")
    return {
        "port": int(m.group(1)),
        "dbname": value("POSTGRES_DB"),
        "user": value("POSTGRES_USER"),
        "password": value("POSTGRES_PASSWORD"),
    }


def demo_connection():
    """A connection to the demo's own database — and never anything else.

    One line, on purpose: `demo/server/db.py :: connect()` is the demo's
    ONE connection factory (plan §4.5, B13) and this is a call to it.

    W5 shipped a self-retiring `_interim_connect()` fallback here because
    the W2→W5→W10→W13 spine makes the seed run before `db.py` can exist.
    W13 landed `db.py`, so the fallback was deleted as that docstring said
    it would be — together with the last `import psycopg` outside the
    factory, which is what `demo/tests/test_isolation.py`'s only-importer
    grep asserts.
    """
    from demo.server.db import connect  # the pinned contract (B13)

    return connect(application_name="autosql-demo-seed")


# ---------------------------------------------------------------------------
# The install steps. Every step runs on the caller's connection, inside the
# caller's transaction; nothing here commits.
# ---------------------------------------------------------------------------

def _table_exists(conn) -> bool:
    row = conn.execute("SELECT to_regclass('demo.records')").fetchone()
    return row[0] is not None


def install_schema(conn) -> None:
    conn.execute(_SCHEMA_PATH.read_text())


def install_runtime_sql(conn) -> None:
    """Install spikes/T-1/proto/runtime.sql UNMODIFIED (spec §9.6).

    The file's sha256 is verified against demo/manifest.json first, so a
    locally edited runtime can never be installed silently; then the whole
    file is issued as one statement batch through the driver (B21). Its
    statements are CREATE SCHEMA IF NOT EXISTS / CREATE OR REPLACE, so
    re-running is idempotent.
    """
    raw = _RUNTIME_SQL_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(_MANIFEST_PATH.read_text())
    expected = manifest.get(_RUNTIME_SQL_MANIFEST_KEY)
    if expected is None:
        raise SeedError(
            f"demo/manifest.json has no entry for {_RUNTIME_SQL_MANIFEST_KEY} — "
            "W2 records it; refusing to install an unverifiable runtime.sql"
        )
    if actual != expected:
        raise SeedError(
            f"{_RUNTIME_SQL_MANIFEST_KEY} does not match demo/manifest.json "
            f"(sha256 {actual} != recorded {expected}) — runtime.sql must be "
            "installed unmodified (AC-33); refusing"
        )
    conn.execute(raw.decode())


def copy_rows(conn) -> int:
    """COPY all generated rows in through the driver (B21), returning how
    many were written."""
    written = 0
    with conn.cursor() as cur:
        with cur.copy("COPY demo.records (collection, key, data) FROM STDIN") as copy:
            for collection, key, data in generate.rows():
                copy.write_row((collection, key, data))
                written += 1
    return written


def collection_counts(conn) -> dict:
    rows = conn.execute(
        "SELECT collection, count(*) FROM demo.records GROUP BY collection"
    ).fetchall()
    return {collection: int(n) for collection, n in rows}


def records_digest(conn) -> str:
    """AC-10's md5 over all rows ordered by (collection, key)."""
    return conn.execute(DIGEST_SQL).fetchone()[0]


# ---------------------------------------------------------------------------
# The entry point ./run-demo up drives.
# ---------------------------------------------------------------------------

def run(conn, record_digest: bool = False) -> str:
    """Install schema + runtime.sql, seed if empty, verify counts and the
    AC-10 digest. One transaction: any failure rolls everything back.
    Returns the digest."""
    print(INVENTED_DATA_LINE)

    if not _table_exists(conn):
        install_schema(conn)
    install_runtime_sql(conn)

    existing = conn.execute("SELECT count(*) FROM demo.records").fetchone()[0]
    if existing == 0:
        written = copy_rows(conn)
        print(f"demo/seed: wrote {written:,} invented rows into demo.records")
    else:
        print(f"demo/seed: demo.records already holds {existing:,} rows — not reseeding")

    counts = collection_counts(conn)
    if counts != EXPECTED_COUNTS:
        raise SeedError(
            f"collection counts are wrong: got {counts}, expected {EXPECTED_COUNTS} (AC-7)"
        )

    digest = records_digest(conn)
    manifest = json.loads(_MANIFEST_PATH.read_text())
    recorded = manifest.get(MANIFEST_DIGEST_KEY)

    if record_digest:
        manifest[MANIFEST_DIGEST_KEY] = digest
        _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"demo/seed: recorded {MANIFEST_DIGEST_KEY} = {digest} in demo/manifest.json")
    elif recorded is None:
        raise SeedError(
            f"demo/manifest.json has no {MANIFEST_DIGEST_KEY} entry — the build "
            "records it once with `python demo/seed/load.py --record-digest`; "
            "refusing to declare an unverifiable seed good"
        )
    elif digest != recorded:
        raise SeedError(
            f"AC-10 digest mismatch: database md5 {digest} != recorded {recorded} — "
            "the data in demo.records is not the data the manifest promises"
        )
    else:
        print(f"demo/seed: AC-10 digest verified against demo/manifest.json ({digest})")

    conn.commit()
    print(
        "demo/seed: demo.records holds "
        + " / ".join(f"{counts[c]:,} {c}" for c in sorted(counts))
        + " — all of it invented"
    )
    return digest


def main(argv: list) -> int:
    record = "--record-digest" in argv
    conn = demo_connection()
    try:
        run(conn, record_digest=record)
    except SeedError as exc:
        conn.rollback()
        print(f"demo/seed: FAILED — {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
