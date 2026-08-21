# Running these scripts against a database

Every script here that talks to Postgres reads its connection string from the environment.
**The password is deliberately not in this repo.** The role these scripts use, `glp_owner`,
also owns the live `glp_strong` database on the same container, so committing its password
would put a working credential for real data into git history — permanently, and regardless
of whether the repository is private today.

Scrubbed 2026-08-21, before this tree's first commit.

## To reproduce

```bash
export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55433 user=glp_owner password=<yours> dbname=autosql_spike"
```

`conformance.py` builds its connection from keyword arguments rather than a string; it picks the
password up from `PGPASSWORD` or `~/.pgpass` in the normal libpq way:

```bash
export PGPASSWORD=<yours>
```

## What the database was

A scratch database named `autosql_spike`, created on the `glp-strong-db` container (host port
55433) purely so the spike had somewhere to load test tables. It held tables from 1,000 up to
1,000,000 rows and reached about 1,060 MB.

**It no longer exists.** The container was rebuilt on 2026-08-21 and only `glp_strong` remains.
Evan's ruling on that (follow-up item: "Leave it gone") was to not reload it; anything that needs
those tables again rebuilds them from `load_data.py`. Written instructions for regenerating the
corpus are still outstanding — see `ANSWERS-FROM-EVAN.md`, Q31.
