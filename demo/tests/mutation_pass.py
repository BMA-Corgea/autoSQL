"""demo/mutation_pass.py — plan §8.2's mutation pass. The part that proves the catchers work.

WHY THIS EXISTS, IN THE PLAN'S OWN WORDS
----------------------------------------
`.autodev/specs/T-2-plan.md` §8.2 (line 1335):

    "There is a precedent in this repository and it is the reason this section exists."
    T-1's re-check drove its conformance harness with six deliberately wrong compilations
    and discovered that every branch which reports a failure had 0 executions across a full
    run -- "those branches were dead, not broken." A suite whose failure paths have never
    been emitted is a suite nobody has watched work.

    "So the build runs a mutation pass before it hands over: a committed list of one-line
    defects, each applied in turn, each with the named criterion that must fail.
    `./run-demo test --mutants` applies each, runs only that criterion, asserts it FAILS,
    and reverts. A mutant that survives is a build failure -- it means the criterion is
    decorative."

It had never run. Four of the sixteen (M1, M4, M8, M16) were hand-run once during an
auto-review; three (M6, M12, M13) have standing detector tests. The other nine had never
been watched failing.

THE TWO RULES THAT MAKE THIS HONEST
-----------------------------------
1. A MUTANT THAT CANNOT BE ANCHORED FAILS THE RUN. It is never skipped. `run-demo:593`
   states the reason: a mutation pass that skips what it cannot apply becomes the very
   thing §8.2 was written against -- a green report over branches nobody drove.

2. THE CRITERION MUST PASS BEFORE IT IS ALLOWED TO FAIL. A criterion that is already red
   proves nothing when it goes red again, so every mutant runs its criterion on the clean
   tree first. Three outcomes, not two: a mutant is KILLED (clean pass, mutated fail),
   SURVIVED (mutated still passes -- the criterion is decorative), or INVALID (the
   criterion was not green to begin with, or the anchor did not apply). Only KILLED counts.

Every edit is reverted from an in-memory copy of the original bytes and verified
byte-identical afterwards, in a `finally`, so an interrupted run cannot leave a mutant on
disk. `--dry-run` checks every anchor and runs nothing.

M6 IS THE ROW TO READ TWICE, AND §8.2 SAYS SO ITSELF
----------------------------------------------------
The `::timestamp` cast returns the IDENTICAL answer on this seed, because the seed is UTC
throughout. Every number on the screen is right. The only thing that catches it is a
criterion asserting the CAST, not the RESULT -- which is why AC-43(a) is a grep, and why a
build must not "simplify" it into an assertion about buckets. If that grep ever becomes a
comparison, M6 survives here and this whole pass turns decorative.

USAGE
    ./run-demo test --mutants          # the pass
    ./run-demo test --mutants --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# This file lives under demo/tests/ deliberately. B21 asserts that nothing the demo RUNS
# starts a process, and this harness spawns pytest sixteen times -- but demo/tests/ is
# excluded from that guard, and says so out loud, because the suite legitimately forks.
# The mutation pass is suite machinery, not demo runtime, so it belongs on the excluded
# side of that line rather than being made an exception to it.
DEMO = Path(__file__).resolve().parent.parent
ROOT = DEMO.parent

# The sixteen, verbatim from plan §8.2's table. `defect` and `criterion` are the plan's own
# words; `anchor`/`replacement` are how that one-line defect is expressed in this tree.
MUTANTS = [
    dict(id="M1",
         defect="Python rolling window divides by 3 always",
         criterion="AC-24(d), Python half, rows 1 and 2",
         file="pyrunner/evaluate.py",
         anchor="out[i] = q6(total / Decimal(len(present)))",
         replacement="out[i] = q6(total / Decimal(3))",
         selector="tests/test_pyrunner.py::test_ac24d_divisors_one_two_three_synthetic"),
    dict(id="M2",
         defect="Python rolling window returns None until three rows accumulate",
         criterion="AC-24(d), Python half",
         file="pyrunner/evaluate.py",
         anchor="            if not present:\n                out[i] = None",
         replacement="            if len(present) < 3:\n                out[i] = None",
         selector="tests/test_pyrunner.py::test_ac24d_divisors_one_two_three_synthetic"),
    dict(id="M3",
         defect="Python sort uses sorted(..., reverse=True) over a tuple containing key",
         criterion="AC-41(d) -- ten highest keys instead of ten lowest",
         file="pyrunner/shape.py",
         anchor="    indices.sort(\n        key=lambda i: ev.row_sort_key(\n"
                "            rows[i], sort_steps, cells[i], sort_alias, direction\n        )\n    )",
         replacement="    indices.sort(\n        key=lambda i: ev.row_sort_key(\n"
                     "            rows[i], sort_steps, cells[i], sort_alias, direction\n"
                     "        ),\n        reverse=True,\n    )",
         selector="tests/test_order.py"),
    dict(id="M4",
         defect="operation 9 compares the whole record (drop - 'ts')",
         criterion="AC-40(a) -- 8,400 kept against a band of 700-1,100",
         file="builder.py",
         anchor='COMPARED_EXPR = "r.data - \'ts\'"',
         replacement='COMPARED_EXPR = "r.data"',
         selector="tests/test_builder_sql.py::TestShapesRun::test_shape_b_changed_kept_count_in_band"),
    dict(id="M5",
         defect="operation 9 uses <> instead of IS DISTINCT FROM",
         criterion="AC-40(d) -- the 50 first beats vanish",
         file="builder.py",
         anchor="             IS DISTINCT FROM ( {COMPARED_EXPR} ) )",
         replacement="             <> ( {COMPARED_EXPR} ) )",
         selector="tests/test_builder_sql.py::TestShapesRun::test_shape_b_changed_kept_count_in_band"),
    dict(id="M6",
         defect="the bucket cast becomes ::timestamp",
         criterion="AC-43(a) -- AND NOTHING ELSE, which is the point: "
                   "it returns the right answer on this seed",
         file="builder.py",
         anchor="date_trunc({g}, (data ->> 'ts')::timestamptz)",
         replacement="date_trunc({g}, (data ->> 'ts')::timestamp)",
         selector="tests/test_builder_sql.py::TestAC43a::test_expression_and_cast"),
    dict(id="M7",
         defect="the session time zone is not set",
         criterion="AC-43(b) -- 8 uneven buckets under the hostile inheritance",
         # There are TWO protections, and removing the connect option leaves the other
         # standing -- so the criterion passes and the mutant proves nothing. _verify()
         # runs settings.PINNED_SESSION_SQL, an explicit SET, before it checks.
         # "The session time zone is not set" is that SET.
         file="server/settings.py",
         anchor='    "SET TIME ZONE \'UTC\';",',
         replacement="",
         # The PGTZ half, NOT the database-default half. That test's own docstring records
         # that the database-default case is "the WEAKER of the two" because `-c
         # timezone=UTC` in the startup packet already beats a database-level default --
         # "under PGTZ it is the only one". A mutant removing the session setting is only
         # decisive against the half where the session setting is the sole protection.
         selector="tests/test_walkthrough.py::test_ac43b_a_hostile_client_zone_does_not_move_the_day_boundary"),
    dict(id="M8",
         defect="Python rounding left at ROUND_HALF_EVEN",
         criterion="AC-24(b)",
         file="pyrunner/decimals.py",
         # NOT the _Q6_CONTEXT definition: quantize() is passed `rounding=` explicitly,
         # which overrides the context, so mutating the context changes nothing at all.
         anchor="    result = x.quantize(SIX_PLACES, rounding=ROUND_HALF_UP, context=_Q6_CONTEXT)",
         replacement='    result = x.quantize(SIX_PLACES, rounding="ROUND_HALF_EVEN", context=_Q6_CONTEXT)',
         selector="tests/test_decimal.py"),
    dict(id="M9",
         defect="Decimal(v) from the float instead of from the JSON text",
         criterion="AC-24(a) on a noun:Sample aggregate over a 4-decimal field_n (B7)",
         # B7's "double parse": json.loads with parse_float=Decimal keeps the JSON TEXT
         # exactly. Dropping it hands arithmetic the binary float instead.
         # The PYTHON pane's exact read (rows.py's record_d), not the SQL pane's
         # jsonb loader: M9 is "Decimal(v) from the float instead of from the JSON
         # text", and record_d IS that text parse. Mutating db._exact_loads changes
         # what the SQL pane decodes, which the aggregate does not read as jsonb.
         file="pyrunner/rows.py",
         anchor="        record_d=json.loads(raw, parse_float=Decimal),",
         replacement="        record_d=json.loads(raw),",
         # The dedicated end-to-end case the plan asked for, named in the suite as
         # "§8.2 M9's own words" -- not the whole file, which passes on other grounds.
         selector="tests/test_decimal.py::test_sample_4_decimal_aggregates_end_to_end"),
    dict(id="M10",
         defect="fragment prefixes removed, so every fragment names p0",
         criterion="B11's merge test -- three distinct literals collapse to one",
         # probes._namespace's inline rewrite is an `except ImportError` FALLBACK that
         # never runs: the import succeeds and it delegates to builder.namespace. Mutating
         # the fallback mutates dead code and every criterion stays green.
         file="builder.py",
         anchor="    if not _PREFIX_RE.match(prefix):",
         replacement="    return frag.sql, dict(frag.params)\n    if not _PREFIX_RE.match(prefix):",
         selector="tests/test_probes.py::TestMechanics::test_b11_namespacing_keeps_three_literals_distinct"),
    dict(id="M11",
         defect="the probe routed through xpr.f8",
         criterion="AC-17 -- 1e400 stops being refused, because the guard returns NULL",
         file="probes.py",
         anchor='"             AND abs( ( " + op_sql + " #>> \'{}\' )::numeric ) >= "',
         replacement='"             AND abs( xpr.f8( " + op_sql + " ) ) >= "',
         selector="tests/test_probes.py"),
    dict(id="M12",
         defect="the gate accepts only the ten leaf/structural tags",
         criterion="AC-14's tag half -- and every comparison in the demo is refused",
         file="gate.py",
         anchor='    {"num", "str", "bool", "null", "field", "neg", "not", "and", "or", "cmp", "bin", "call"}',
         replacement='    {"num", "str", "bool", "null", "field", "neg", "not", "and", "or", "call"}',
         selector="tests/test_gate.py::test_each_of_the_twelve_tags_is_accepted_at_the_tag"),
    dict(id="M13",
         defect="re.match instead of re.fullmatch in the alias validator",
         criterion='AC-38(a) -- alive"; DROP TABLE demo.records; -- is accepted',
         file="gate.py",
         anchor="    if re.fullmatch(ALIAS_RE, name) is None:",
         replacement="    if re.match(ALIAS_RE, name) is None:",
         selector="tests/test_alias.py::test_the_injection_name_is_refused_at_the_pattern"),
    dict(id="M14",
         defect="the numeric read's jsonb_typeof guard removed",
         criterion="the noun:Sample aggregate raises 22P02; a LOUD failure, and the mutant "
                   "proves the guard is load-bearing rather than defensive",
         file="probes.py",
         anchor='        "( jsonb_typeof( " + op_sql + " ) = \'number\'\\n"',
         replacement='        "( true\\n"',
         selector="tests/test_probes.py"),
    dict(id="M15",
         defect="ORDER BY dropped from one multi-row statement",
         criterion="AC-41(a) grep, and AC-41(b)'s ten runs",
         # AC-41(a) is test_builder_sql.py's grep over the emitted BUILDER statements;
         # a probe's internal ORDER BY is not what it reads.
         file="builder.py",
         anchor='        return f" ORDER BY {lead}, {q}key ASC"',
         replacement='        return ""',
         selector="tests/test_builder_sql.py::TestAC41a"),
    dict(id="M16",
         defect="a test writes a row and does not clean up",
         criterion="B10's end-of-session checksum guard",
         file="tests/test_alias.py",
         anchor="    finally:\n        aconn.rollback()",
         replacement="    finally:\n        aconn.commit()",
         # B10 is a SESSION hook, not a node: it reads demo.records at session start and
         # end. So this one criterion is a whole pytest session over the mutated file, and
         # the assertion is on the guard's own verdict rather than on a test outcome.
         selector="tests/test_alias.py",
         session_guard=True),
]

KILLED, SURVIVED, INVALID = "KILLED", "SURVIVED", "INVALID"


def _pytest(selector: str, timeout: int = 900):
    return subprocess.run(
        [sys.executable, "-m", "pytest", selector, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=DEMO, capture_output=True, text=True, timeout=timeout)


def _b10_leaked(out: str) -> bool:
    # The guard sets _GUARD["state"]="LEAKED" internally but PRINTS a banner reading
    # "B10 CHECKSUM GUARD FAILED". Matching only the internal word made M16 look like a
    # survivor while the guard had in fact fired -- a detection bug in the detector.
    return ("B10 CHECKSUM GUARD FAILED" in out) or ("LEAKED" in out)


# ---------------------------------------------------------------------------------
# THE DATABASE GUARD.
#
# M16's whole defect is that a test writes a row and does not clean up, so running it
# LEAVES A ROW IN demo.records. Reverting the source file does not undo that, and the
# first version of this harness did exactly that: it restored the .py, left the
# committed scratch row behind, and the next pytest session opened with
# "B10 CHECKSUM GUARD FAILED — the database did not match demo/manifest.json BEFORE
# this run started". A mutation pass that corrupts the fixture it measures against is
# worse than no mutation pass, because every later result is taken on a tree nobody
# knows the state of.
#
# So the digest is read before the pass and after EVERY mutant, restored when it
# drifts, and the run ABORTS if it cannot be restored.
# ---------------------------------------------------------------------------------
SEEDED = ("noun:Heartbeat", "noun:Sample", "noun:EdgeCase")


def _digest():
    """B10's own digest, via the seed loader the guard itself uses."""
    sys.path.insert(0, str(ROOT))
    from demo.seed.load import demo_connection, records_digest
    conn = demo_connection()
    try:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        return records_digest(conn)
    finally:
        conn.close()


def _manifest_digest():
    import json
    m = json.loads((DEMO / "manifest.json").read_text())
    for k, v in m.items():
        if "records" in str(k) and "md5" in str(k):
            return v
    return None


def _restore_db() -> bool:
    """Delete anything outside the three seeded collections and report whether that
    put the digest back. Deliberately narrow: it removes rows a mutant added, and it
    cannot repair a modified seeded row -- which is why the caller aborts on failure
    rather than continuing."""
    sys.path.insert(0, str(ROOT))
    from demo.seed.load import demo_connection
    conn = demo_connection()
    try:
        conn.execute("DELETE FROM demo.records WHERE collection <> ALL(%(keep)s)",
                     {"keep": list(SEEDED)})
        conn.commit()
    finally:
        conn.close()
    return True


def run(dry_run: bool = False, only: list[str] | None = None) -> int:
    chosen = [m for m in MUTANTS if not only or m["id"] in only]

    # ---- anchor check FIRST, for every mutant, before anything is applied ----------
    # A mutant that cannot be anchored fails the run; it is never skipped.
    unanchored = []
    for m in chosen:
        p = DEMO / m["file"]
        if not p.exists():
            unanchored.append((m["id"], f"{m['file']} does not exist")); continue
        n = p.read_text().count(m["anchor"])
        if n != 1:
            unanchored.append((m["id"], f"anchor appears {n} times in {m['file']}, expected exactly 1"))
    if unanchored:
        print("mutation pass: CANNOT ANCHOR — refusing to run a partial pass\n")
        for mid, why in unanchored:
            print(f"  {mid}: {why}")
        print("\nplan §8.2: a mutant that cannot be anchored has to fail the run rather than\n"
              "be skipped — otherwise the mutation pass becomes the thing it was written against.")
        return 2
    print(f"mutation pass: all {len(chosen)} anchors resolve, exactly once each.")
    if dry_run:
        print("mutation pass: --dry-run, nothing applied.")
        return 0

    # ---- the fixture must be sound before anything is measured against it ---------
    baseline = manifest = None
    try:
        baseline, manifest = _digest(), _manifest_digest()
    except Exception as exc:
        print(f"mutation pass: cannot read demo.records ({type(exc).__name__}: {exc}).")
        print("mutation pass: refusing to run — B10's fixture is the thing every criterion "
              "is measured against.")
        return 2
    if manifest and baseline != manifest:
        print(f"mutation pass: demo.records does NOT match demo/manifest.json before the run\n"
              f"  digest {baseline}\n  manifest {manifest}\n"
              "Re-seed before running a mutation pass; measuring against a fixture of "
              "unknown state proves nothing.")
        return 2
    print(f"mutation pass: fixture verified against manifest (md5 {baseline}).")

    results = []
    for m in chosen:
        p = DEMO / m["file"]
        original = p.read_text()
        t0 = time.time()
        print(f"\n--- {m['id']}: {m['defect']}\n    criterion: {m['criterion']}", flush=True)

        base = _pytest(m["selector"])
        base_ok = (base.returncode == 0)
        if m.get("session_guard"):
            base_ok = base_ok and not _b10_leaked(base.stdout)
        if not base_ok:
            results.append((m, INVALID, "the criterion was NOT GREEN before the mutant was "
                                        "applied, so its going red proves nothing"))
            print(f"    INVALID — criterion not green on the clean tree", flush=True)
            continue

        try:
            p.write_text(original.replace(m["anchor"], m["replacement"], 1))
            got = _pytest(m["selector"])
            if m.get("session_guard"):
                caught = _b10_leaked(got.stdout)
                how = "B10 reported LEAKED" if caught else "B10 did not report a leak"
            else:
                caught = (got.returncode != 0)
                how = "criterion failed" if caught else "criterion still passed"
        finally:
            p.write_text(original)
            assert p.read_text() == original, f"{m['file']} was not restored after {m['id']}"

        results.append((m, KILLED if caught else SURVIVED, how))
        print(f"    {'KILLED' if caught else '*** SURVIVED ***'} — {how} ({time.time()-t0:.0f}s)",
              flush=True)

        # ---- the fixture, after every mutant, not just the data-mutating one --------
        now = _digest()
        if now != baseline:
            print(f"    fixture drifted (md5 {now}) — restoring", flush=True)
            _restore_db()
            now = _digest()
            if now != baseline:
                print(f"\nmutation pass: ABORTING — demo.records could not be restored after "
                      f"{m['id']}.\n  now {now}\n  baseline {baseline}\n"
                      "Every later result would be measured against an unknown fixture.")
                return 2
            print("    fixture restored", flush=True)

    print("\n" + "=" * 78)
    killed = [r for r in results if r[1] == KILLED]
    survived = [r for r in results if r[1] == SURVIVED]
    invalid = [r for r in results if r[1] == INVALID]
    print(f"mutation pass: {len(killed)} killed, {len(survived)} SURVIVED, {len(invalid)} INVALID, "
          f"of {len(chosen)}")
    for m, _, how in survived:
        print(f"  SURVIVED {m['id']} — {m['criterion']}\n    {how}: the criterion is DECORATIVE")
    for m, _, how in invalid:
        print(f"  INVALID  {m['id']} — {how}")
    if survived or invalid:
        print("\nplan §8.2: a mutant that survives is a BUILD FAILURE — it means the criterion\n"
              "is decorative. This pass does not pass.")
    else:
        print("\nEvery criterion was watched failing against its own mutant.")
    print("=" * 78)
    return 0 if (not survived and not invalid) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="plan §8.2's mutation pass")
    ap.add_argument("--dry-run", action="store_true", help="check anchors; apply nothing")
    ap.add_argument("--only", help="comma-separated mutant ids, e.g. M6,M12")
    a = ap.parse_args()
    raise SystemExit(run(dry_run=a.dry_run, only=a.only.split(",") if a.only else None))
