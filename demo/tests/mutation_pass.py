"""demo/tests/mutation_pass.py — plan §8.2's mutation pass. The part that proves the catchers work.

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
import os
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
         # test_order.py:357 says it outright: "AC-41(d) is walkthrough step 5 and
         # lives in test_walkthrough.py". That test's docstring names THIS mutant --
         # "a Python pane written as sorted(..., reverse=True) over a tuple containing
         # key returns the ten HIGHEST keys and must fail here". Pointing at
         # test_order.py made M3 go red on a different test entirely.
         selector="tests/test_walkthrough.py::test_step_5_the_tiebreak_runs_ascending_under_a_descending_sort"),
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
         selector="tests/test_decimal.py::test_q6_rounds_ties_half_up"),
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
         selector="tests/test_probes.py::TestAC17::test_1e400_refuses_naming_cause_and_row"),
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
         # NOT tests/test_probes.py: no test there issues a noun:Sample aggregate and
         # the string 22P02 appears nowhere in it. The mutant was being killed by
         # `assert "jsonb_typeof(" in probe.sql` -- a no-database substring check that
         # proves the text is present and proves NOTHING about the guard being
         # load-bearing. This node actually executes the aggregate.
         selector="tests/test_decimal.py::test_sample_4_decimal_aggregates_end_to_end"),
    dict(id="M15",
         defect="ORDER BY dropped from one multi-row statement",
         criterion="AC-41(a) grep, and AC-41(b)'s ten runs",
         # AC-41(a) is test_builder_sql.py's grep over the emitted BUILDER statements;
         # a probe's internal ORDER BY is not what it reads.
         file="builder.py",
         anchor='        return f" ORDER BY {lead}, {q}key ASC"',
         replacement='        return ""',
         # The plan names BOTH halves -- "AC-41(a) grep, AND AC-41(b)'s ten runs" --
         # and (b) is the half that catches an order stable by luck of the plan rather
         # than by ORDER BY, which is the interesting half against a dropped ORDER BY.
         selector=("tests/test_builder_sql.py::TestAC41a",
                   "tests/test_order.py::test_ac41b_ten_runs_of_one_pick_return_one_sequence")),
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

# ---------------------------------------------------------------------------------
# KNOWN SURVIVORS — the reason this pass does not decay into noise.
#
# A permanently-red pass gets made green the easy way by whoever meets it next, which
# is exactly the move §8.2 exists to prevent. But a pass that only prints a total
# cannot tell "M15, known decorative, tracked" from "something that used to be killed
# is surviving now" -- and this repo has already shipped a check that could not
# distinguish "did not run" from "found nothing". This is the mirror image of that,
# and it is not going to be shipped.
#
# So: a survivor listed HERE is expected and does not fail the run. A survivor that is
# NOT listed is NEW, and exits 3. An entry that stops surviving is also reported --
# quietly wrong lists are how this decays.
#
# Every entry carries a reason and a ticket. An entry without a ticket is a to-do
# wearing a data structure.
# ---------------------------------------------------------------------------------
EXPECTED_SURVIVORS = {
    "M15": dict(
        ticket="T-20",
        half="tests/test_order.py::test_ac41b_ten_runs_of_one_pick_return_one_sequence",
        reason=(
            "AC-41(b) cannot detect a dropped ORDER BY on this fixture. The mutant DOES "
            "reach the statement it runs -- verified in clean subprocesses, the emitted SQL "
            "goes from 'ORDER BY ( r.data #> %(sort_path)s ) DESC NULLS LAST, r.key ASC "
            "LIMIT %(cap)s' to 'LIMIT %(cap)s' -- but ten runs still return one sequence. "
            "T-2.md's 'why half (2) exists' lists what makes an unordered query reorder: a "
            "different plan, a synchronised sequential scan joining mid-way, a parallel "
            "worker finishing first. MEASURED: demo.records is 2,880 kB / 10,410 rows, and "
            "with max_parallel_workers_per_gather=4, parallel_setup_cost=0 and "
            "min_parallel_table_scan_size=0 the order is IDENTICAL -- LIMIT 10 stops the "
            "scan before any of those effects can appear. AC-41(a)'s grep is the real "
            "detector; AC-41(b) is a repeatability test, not an ORDER BY detector. "
            "NOT edited to make the mutant die: T-19 spec, Out of scope."),
    ),
}


def _write_atomic(path, text: str) -> None:
    """Temp file + os.replace. write_text() truncates before it writes, so a SIGKILL,
    an OOM or a power loss in between leaves a TRUNCATED source file -- worse than a
    mutant, and the module docstring's promise that an interrupted run cannot leave a
    mutant on disk was stronger than the code that backed it."""
    tmp = path.with_suffix(path.suffix + f".mutant-tmp-{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, path)


def _selectors(m) -> tuple:
    sel = m["selector"]
    return (sel,) if isinstance(sel, str) else tuple(sel)


def _pytest(selector: str, timeout: int = 900):
    return subprocess.run(
        [sys.executable, "-m", "pytest", selector, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=DEMO, capture_output=True, text=True, timeout=timeout)


def _b10_leaked(out: str) -> bool:
    # The guard sets _GUARD["state"]="LEAKED" internally but PRINTS a banner reading
    # "B10 CHECKSUM GUARD FAILED". Matching only the internal word made M16 look like a
    # survivor while the guard had in fact fired -- a detection bug in the detector.
    # ONLY the printed banner (conftest.py:247). A bare `"LEAKED" in out` matches
    # anywhere in pytest's whole stdout -- and conftest.py:229 contains the literal
    # source line `_GUARD["state"] = "LEAKED"`, so any traceback surfacing that line
    # would make M16 report KILLED with the guard never having fired. Re-opening the
    # looseness this detector was rewritten to close.
    return "B10 CHECKSUM GUARD FAILED" in out


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


MANIFEST_KEY = "seed:demo.records:md5"


def _manifest_digest():
    """Read the recorded digest BY NAME. A scan that returns None on no match turns the
    pass's strongest precondition into a silent no-op that still prints
    'fixture verified against manifest'."""
    import json
    m = json.loads((DEMO / "manifest.json").read_text())
    if MANIFEST_KEY not in m:
        raise KeyError(
            f"demo/manifest.json has no {MANIFEST_KEY!r} — the mutation pass compares the "
            "live fixture against it before running, and cannot silently skip that check")
    return m[MANIFEST_KEY]


MAX_RESTORE_DELETE = 50   # a mutant leaks a row or two; anything more is not a leak


def _restore_db() -> bool:
    """Delete rows a mutant ADDED outside the seeded collections. Returns whether it
    deleted anything.

    Deliberately narrow, and bounded. It cannot repair a MODIFIED seeded row -- the
    caller aborts on that. And it refuses to delete more than MAX_RESTORE_DELETE rows:
    SEEDED duplicates knowledge that really lives in demo/seed/, so if the seed ever
    grows a fourth collection this function would otherwise delete every row of it on
    the first digest drift, and `run-demo up` does not re-seed a non-empty table."""
    sys.path.insert(0, str(ROOT))
    from demo.seed.load import demo_connection
    conn = demo_connection()
    try:
        n = conn.execute("SELECT count(*) FROM demo.records WHERE collection <> ALL(%(keep)s)",
                         {"keep": list(SEEDED)}).fetchone()[0]
        if n == 0:
            return False
        if n > MAX_RESTORE_DELETE:
            raise RuntimeError(
                f"{n} rows sit outside {SEEDED}; refusing to delete that many. This is not "
                "a mutant's leak -- either the seed grew a collection this list does not "
                "know about, or something else wrote to demo.records.")
        conn.execute("DELETE FROM demo.records WHERE collection <> ALL(%(keep)s)",
                     {"keep": list(SEEDED)})
        conn.commit()
        return True
    finally:
        conn.close()


def run(dry_run: bool = False, only: list[str] | None = None) -> int:
    known = {m["id"] for m in MUTANTS}
    if only:
        unknown = [i for i in only if i not in known]
        if unknown:
            print(f"mutation pass: --only names no such mutant: {unknown}")
            print(f"mutation pass: the sixteen are {sorted(known, key=lambda x: int(x[1:]))}")
            return 2
    chosen = [m for m in MUTANTS if not only or m["id"] in only]
    if not chosen:
        # `--only M17` used to select nothing and then print "0 killed, 0 SURVIVED,
        # 0 INVALID, of 0" followed by "Every criterion was watched failing against its
        # own mutant", and exit 0 — a green report over branches nobody drove, which is
        # precisely what §8.2 exists to prevent.
        print("mutation pass: nothing selected — refusing to report a pass over nothing.")
        return 2

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

        sels = _selectors(m)
        try:
            # -- every named half must be GREEN before any of them is allowed to fail --
            not_green = []
            for sel in sels:
                base = _pytest(sel)
                ok = base.returncode == 0
                if m.get("session_guard"):
                    ok = ok and not _b10_leaked(base.stdout)
                if not ok:
                    not_green.append(sel)
            if not_green:
                results.append((m, INVALID,
                                f"not green on the clean tree: {', '.join(not_green)} — "
                                "going red proves nothing"))
                print(f"    INVALID — criterion not green on the clean tree: {not_green}",
                      flush=True)
                continue

            try:
                _write_atomic(p, original.replace(m["anchor"], m["replacement"], 1))
                per = []
                for sel in sels:
                    got = _pytest(sel)
                    if m.get("session_guard"):
                        hit = _b10_leaked(got.stdout)
                    else:
                        hit = got.returncode != 0
                    per.append((sel, hit))
            finally:
                _write_atomic(p, original)
                if p.read_text() != original:   # explicit: `assert` is stripped by python -O
                    raise RuntimeError(f"{m['file']} was NOT restored after {m['id']}")

            # The plan names the criterion; where it names TWO halves (M15), BOTH are
            # required, because a half that does not catch the defect is exactly the
            # decorative criterion §8.2 is looking for.
            caught = all(hit for _, hit in per)
            missed = [sel for sel, hit in per if not hit]
            how = ("criterion failed" if caught
                   else f"still passed: {', '.join(missed)}")
            if m.get("session_guard"):
                how = "B10 reported the guard failed" if caught else "B10 did not report a leak"

            results.append((m, KILLED if caught else SURVIVED, how))
            print(f"    {'KILLED' if caught else '*** SURVIVED ***'} — {how} "
                  f"({time.time()-t0:.0f}s)", flush=True)
        finally:
            # ---- the fixture, on EVERY exit path from this mutant --------------------
            # Not after the result: an INVALID `continue`, a pytest timeout and a Ctrl-C
            # all used to skip this, and M16's mutated run COMMITS a row by design. That
            # is the exact incident this pass already caused once — a scratch row left in
            # demo.records and the next session opening with B10 CHECKSUM GUARD FAILED.
            now = _digest()
            if now != baseline:
                print(f"    fixture drifted (md5 {now}) — restoring", flush=True)
                _restore_db()
                now = _digest()
                if now != baseline:
                    print(f"\nmutation pass: ABORTING — demo.records could not be restored "
                          f"after {m['id']}.\n  now {now}\n  baseline {baseline}\n"
                          "Every later result would be measured against an unknown fixture.")
                    return 2
                print("    fixture restored", flush=True)

    print("\n" + "=" * 78)
    killed = [r for r in results if r[1] == KILLED]
    survived = [r for r in results if r[1] == SURVIVED]
    invalid = [r for r in results if r[1] == INVALID]
    expected = [r for r in survived if r[0]["id"] in EXPECTED_SURVIVORS]
    new_survivors = [r for r in survived if r[0]["id"] not in EXPECTED_SURVIVORS]
    # an entry that has stopped surviving: the list is now wrong, and a wrong list is
    # how this decays back into noise
    resurrected = [r for r in killed if r[0]["id"] in EXPECTED_SURVIVORS]

    print(f"mutation pass: {len(killed)} killed, {len(survived)} survived "
          f"({len(expected)} known, {len(new_survivors)} NEW), {len(invalid)} INVALID, "
          f"of {len(chosen)}")

    for m, _, how in expected:
        e = EXPECTED_SURVIVORS[m["id"]]
        print(f"\n  KNOWN SURVIVOR {m['id']} — tracked in {e['ticket']}")
        print(f"    criterion: {m['criterion']}")
        print(f"    the half that does not fire: {e['half']}")
        print(f"    why: {e['reason']}")
    for m, _, how in new_survivors:
        print(f"\n  *** NEW SURVIVOR {m['id']} *** — {m['criterion']}\n"
              f"    {how}\n"
              f"    This was not a known survivor. Either the criterion has been weakened,\n"
              f"    or the mutant no longer reaches it. Do NOT add it to EXPECTED_SURVIVORS\n"
              f"    to make this green -- that is the move §8.2 exists to prevent.")
    for m, _, how in invalid:
        print(f"\n  INVALID  {m['id']} — {how}")
    for m, _, _ in resurrected:
        e = EXPECTED_SURVIVORS[m["id"]]
        print(f"\n  NOTE: {m['id']} is listed as a known survivor but was KILLED this run.\n"
              f"    {e['ticket']} may be done — remove it from EXPECTED_SURVIVORS, or the list\n"
              f"    starts hiding a real regression behind a stale entry.")

    print()
    if new_survivors or invalid:
        print("plan §8.2: a mutant that survives is a BUILD FAILURE — it means the criterion\n"
              "is decorative. This pass does not pass.")
        rc = 3 if new_survivors else 1
    elif expected:
        print(f"Every criterion was watched failing against its own mutant, except the "
              f"{len(expected)} known and tracked above.\n"
              "Those are the pass WORKING: it found a criterion that only looks like it works.")
        rc = 0
    else:
        print("Every criterion was watched failing against its own mutant.")
        rc = 0
    print("=" * 78)
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="plan §8.2's mutation pass")
    ap.add_argument("--dry-run", action="store_true", help="check anchors; apply nothing")
    ap.add_argument("--only", help="comma-separated mutant ids, e.g. M6,M12")
    a = ap.parse_args()
    raise SystemExit(run(dry_run=a.dry_run, only=a.only.split(",") if a.only else None))
