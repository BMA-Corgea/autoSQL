# Running these scripts against a database

Every script here that talks to Postgres reads its connection string from the environment.
**The password is deliberately not in this repo.** The role these scripts use, `glp_owner`,
also owns the live `glp_strong` database on the same container, so committing its password
would put a working credential for real data into git history — permanently, and regardless
of whether the repository is private today.

Scrubbed 2026-08-21, before this tree's first commit.

## To reproduce

Point the scripts at a **throwaway** Postgres container of your own — never at `glp-strong-db`
on port **55433**, which is the owner's live data. `REGENERATE-CORPUS.md` §3 gives the container
command and §4 gives the load; the port below is that throwaway container's.

```bash
export AUTOSQL_SPIKE_DSN="host=127.0.0.1 port=55434 user=glp_owner password=<yours> dbname=autosql_spike"
```

**Setting it is not optional.** With `AUTOSQL_SPIKE_DSN` unset, `load_data.py:12` and
`bench.py:33-34` fall back to `host=127.0.0.1 port=55433 user=glp_owner dbname=autosql_spike`
— the live container — and `load_data.py` opens each size with `DROP TABLE IF EXISTS`
(`load_data.py:27`). Creating the throwaway container with `POSTGRES_USER=glp_owner` matches the
*role* name but changes nothing about this: the fallback pins the **port**, and no script in this
directory mentions 55434 anywhere.

`conformance.py` builds its connection from keyword arguments rather than a string; it picks the
password up from `PGPASSWORD` or `~/.pgpass` in the normal libpq way:

```bash
export PGPASSWORD=<yours>
```

**`conformance.py` cannot be redirected by `AUTOSQL_SPIKE_DSN` at all.** Its connection is a
literal `dict(host="127.0.0.1", port=55433, user="glp_owner", dbname="autosql_spike")` at
`conformance.py:55`, and the file contains no `os.environ` reference. Exporting `PGPASSWORD`
therefore fixes the password while leaving the target pointed at the live container. Edit line 55
to your throwaway port before running it.

## What the database was

A scratch database named `autosql_spike`, created on the `glp-strong-db` container (host port
55433) purely so the spike had somewhere to load test tables. It held tables from 1,000 up to
1,000,000 rows and reached about 1,060 MB.

### What actually happened to it on 2026-08-21

Stated plainly, because an earlier version of this file got both halves of it wrong — it said the
database was gone *because the container had been rebuilt*, and neither the reason nor the state
was right.

1. The corpus tables this spike measured against are gone and stay gone, under the owner's Q31 ruling —
   **"Leave it gone."**
2. Later on 2026-08-21, one of this session's own workers **recreated an `autosql_spike` database
   on the live `glp-strong-db` container**. It was effectively empty: **no tables at all**, only the
   21 `xpr` helper functions, **7,567 kB** in total.
3. The driving session found it, confirmed it had **zero active connections**, and **dropped it at
   about 20:55** — to execute Q31 as written, and to keep this spike's work off the owner's live
   container.

**The container was never rebuilt.** `glp-strong-db` has been up continuously — `docker ps` read
`Up 5 hours (healthy)` while this was being written — and `glp_strong` itself was never touched.
It is 95 MB.

**If you find `autosql_spike` back on `glp-strong-db`, that is a mistake, not a resource.** Do not
reuse it and do not reload into it. Drop it, and rebuild the corpus into a throwaway container
instead — `REGENERATE-CORPUS.md` §3 for the container, §4 for the load, §9 for the teardown.
Nothing in this spike needs the live container for anything except reading, and it does not need
that either.

Q31's outstanding note is now closed: `REGENERATE-CORPUS.md` is the written procedure for
regenerating the corpus, and its §5 checks a rebuild against reference checksums, sizes and
selectivity.
