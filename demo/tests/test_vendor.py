"""demo/tests/test_vendor.py — the vendoring + drift machinery (W2).

Covers AC-33, AC-34 (both halves), AC-35, and AC-39's loud-skip contract, per
`.autodev/specs/T-2-plan.md` §6.2 (W2) and `.autodev/specs/T-2.md` §9.7 / §9.5,
and D1/D2 of `design/t2-demo.md`.

§9.7's four-part loud skip, and how each part is met here:

  1. The check reports SKIPPED, never PASSED and never nothing at all
     -> every tree-dependent check below calls `pytest.skip(...)`, which
     pytest reports as SKIPPED (never silently passed, never silently
     omitted from the run).
  2. The skip line names the path it looked for, and names the override
     variable -> every skip reason is built by `_skip_reason(...)` below,
     which always includes both.
  3. The suite's final summary line counts skips separately from passes
     -> that is `./run-demo test`'s job (W16); nothing to do here except
     not swallow the skip (see 1).
  4. Everything that does not need the tree still runs and still has to
     pass -> every AC below that has a "manifest half" or an
     unconditional half is a *separate* test function from its
     tree-dependent half, so one skipping can never hide the other
     failing (or not running).

AC-39(c) ("`./run-demo up` completes and answers walkthrough steps 2 and 8
with both variables pointing at nothing") was a `run=False` xfail while the
stack did not exist (W2).  The stack exists, so it is asserted for real at
the bottom of this file, in two standing halves: nothing `up` or a pick can
execute so much as names the tree variables or the checkout paths, and the
demo answers walkthrough steps 2 and 8 — both panes populated, agreeing,
against expected-answers.json — with both variables pointed at paths that
do not exist.  (The one part no in-suite test can re-run is a cold-start
`./run-demo up` itself: the suite's own stack holds 55440/8787, and `up`
correctly refuses a taken port.  That cold-start run with the poisoned
variables is recorded in demo/EVIDENCE.md, Run D; the static half here is
what keeps it true.)

The round-1 review's refusal findings are also pinned at the bottom of
this file (this suite's groups are split by owned file, and this is the
refusals group's test file): the gate's finiteness row, the float8
runtime refusal, the malformed-pick-shape refusals, and the read-only
guard on the transaction a pick actually runs in — each asserted to
refuse BY NAME, because a bare "invalid" (or worse, a bare 500) is the
defect, not the fix.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths and the manifest
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO_ROOT / "demo"
MANIFEST_PATH = DEMO_ROOT / "manifest.json"

# Recorded once at test-collection time so a check for "did anything write
# under the tree during this run" (AC-35) has a fixed reference point.
_SESSION_START = time.time()


def _manifest() -> dict[str, str]:
    return json.loads(MANIFEST_PATH.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_tree(env_var: str, default_relative: str) -> tuple[Path, bool]:
    """Resolve a GIMS-family checkout path per §9.7.

    Returns (path, exists). `path` is always returned, even when it does
    not exist, so callers can name it in a loud-skip message (§9.7 part 2).
    """
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
    else:
        path = (REPO_ROOT / default_relative).resolve()
    return path, path.is_dir()


def _gims_tree() -> tuple[Path, bool]:
    return _resolve_tree("AUTOSQL_GIMS_TREE", "../GIMS-Project")


def _guts_tree() -> tuple[Path, bool]:
    return _resolve_tree("AUTOSQL_GUTS_TREE", "../GUTS/spine/L1-memory/gims-ledger")


def _skip_reason(ac: str, half: str, env_var: str, path: Path) -> str:
    return (
        f"{ac} ({half}): no GIMS checkout at {path} "
        f"— set {env_var} to point at one"
    )


# ---------------------------------------------------------------------------
# The vendored-from-GIMS files: vendored path -> path relative to a checkout
# ---------------------------------------------------------------------------
# `expr.py` is AC-34's named subject. The six style assets are D1's — same
# byte-identical-copy-plus-drift-check shape, cited by name in the manifest
# but not individually numbered in §12's 45 criteria.

VENDORED_FROM_GIMS: dict[str, str] = {
    "demo/vendor/expr.py": "core/dashboard/expr.py",
    "demo/vendor/styles/watery.css": "static/styles/watery.css",
    "demo/vendor/styles/dashboard.css": "static/styles/dashboard.css",
    "demo/vendor/styles/shell.css": "static/styles/shell.css",
    "demo/vendor/styles/components.css": "static/styles/components.css",
    "demo/vendor/icons.svg": "static/icons.svg",
    "demo/vendor/ui.jsx": "frontend/lib/ui.jsx",
}

# The spike file AC-33 still covers in place. Reused *as is* (Q19), not
# vendored — there is no live-tree half for it, only "has the committed file
# changed since the ticket started".
AC33_FILES = (
    "spikes/T-1/proto/compile.py",
)

# runtime.sql USED to be in AC33_FILES, reused in place. It was moved to
# demo/vendor/runtime.sql on 2026-08-22 because T-3 legitimately changed the
# shared file underneath this ticket: its correctness run found the range guard
# was 297 digits where DBL_MAX needs 309, so every finite double above ~1.8e296
# was silently nulled — a wrong answer wearing a null's clothes. T-3 fixed it
# and made the out-of-range branch RAISE a named XPR01 refusal.
#
# For one day the demo PINNED the pre-fix version and this file asserted the
# two copies stayed DIFFERENT — a ruling under delegated authority (Evan's
# wrap-up item 28), because T-2's signed criteria described the pre-fix
# behaviour.  That divergence ruling was SUPERSEDED on 2026-08-23 by Evan's
# own form answer q4 under GA-7 — "Adopt it — update the four criteria" — so
# the demo now vendors T-3's corrected version, B15/B24/AC-13/AC-17 carry
# dated amendment notes (plus AC-22, a consequence recorded the same way),
# and the test below asserts the two copies are IDENTICAL: a drift apart now
# means someone edited one side without a decision.
#
# Worth knowing (he was told, and chose adopt): the q5 ruling means T-6 will
# change the shared runtime AGAIN — pinning extra_float_digits and converting
# the Unicode-digit gap to a named refusal — so this vendored copy will need
# a second update, and a second decision trail, after that re-run.
RUNTIME_PINNED = "demo/vendor/runtime.sql"
RUNTIME_UPSTREAM = "runtime/runtime.sql"


def test_runtime_sql_is_adopted_and_matches_the_spike() -> None:
    """The demo's runtime.sql IS the shipping runtime, byte for byte.

    2026-09-01, T-8: the upstream moved. It was spikes/T-1/proto/runtime.sql,
    which is now FROZEN EVIDENCE -- its sha is cited in T-3's and T-6's findings
    and in 42 battery outputs, so it can never change again. The runtime a
    product ships lives at runtime/runtime.sql, is GENERATED, and is what the
    demo now vendors.

    Until 2026-08-23 this test asserted the OPPOSITE — the pinned copy and
    the spike's copy deliberately different.  It was correct for the old
    ruling and wrong for Evan's q4 (GA-7), which superseded it; see the
    note above.  Identity is asserted, not just digest-validity, so neither
    side can be edited without the other — the same one-file-one-truth
    property the divergence assertion used to protect, pointed the other
    way.
    """
    manifest = _manifest()
    assert RUNTIME_PINNED in manifest, (
        f"{RUNTIME_PINNED} has no recorded digest — the demo must not install "
        "an unverifiable runtime.sql"
    )
    vendored = _sha256(REPO_ROOT / RUNTIME_PINNED)
    assert vendored == manifest[RUNTIME_PINNED], (
        f"{RUNTIME_PINNED} does not match its recorded digest — expected "
        f"{manifest[RUNTIME_PINNED]}, got {vendored}"
    )

    upstream_path = REPO_ROOT / RUNTIME_UPSTREAM
    if not upstream_path.exists():
        pytest.skip(
            f"SKIPPED — {RUNTIME_UPSTREAM} is absent, so the adoption cannot "
            "be checked against it. The vendored copy above is still verified."
        )
    upstream = _sha256(upstream_path)
    assert upstream == vendored, (
        f"{RUNTIME_PINNED} no longer matches {RUNTIME_UPSTREAM}. The demo vendors "
        "the shipping runtime byte-for-byte, so one of them was edited without a "
        "decision. runtime/runtime.sql is GENERATED — if it is the one that moved, "
        "re-run `python3 runtime/generate.py` and re-vendor rather than editing "
        "either copy by hand."
    )


# ---------------------------------------------------------------------------
# AC-33 — the two spike files are byte-identical to their committed state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", AC33_FILES)
def test_ac33_spike_file_unchanged(relpath: str) -> None:
    manifest = _manifest()
    assert relpath in manifest, f"AC-33: {relpath} has no recorded digest in demo/manifest.json"
    actual = _sha256(REPO_ROOT / relpath)
    assert actual == manifest[relpath], (
        f"AC-33: {relpath} does not match its recorded digest — "
        f"expected {manifest[relpath]}, got {actual}. Q19 said 'as-is'."
    )


# ---------------------------------------------------------------------------
# AC-34 (and D1's equivalent for the six style assets) — two independent
# halves per file: the manifest half (always) and the tree half (loud skip)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vendored_relpath", sorted(VENDORED_FROM_GIMS))
def test_ac34_manifest_half(vendored_relpath: str) -> None:
    """Runs always, no checkout needed. This half must never be among the
    suite's skips (AC-39(b))."""
    manifest = _manifest()
    assert vendored_relpath in manifest, (
        f"{vendored_relpath} has no recorded digest in demo/manifest.json"
    )
    actual = _sha256(REPO_ROOT / vendored_relpath)
    assert actual == manifest[vendored_relpath], (
        f"vendored copy {vendored_relpath} does not match the digest recorded "
        f"in demo/manifest.json — expected {manifest[vendored_relpath]}, got {actual}. "
        f"D1/D2: vendored files are never edited."
    )


@pytest.mark.parametrize("vendored_relpath,tree_relpath", sorted(VENDORED_FROM_GIMS.items()))
def test_ac34_tree_half(vendored_relpath: str, tree_relpath: str) -> None:
    """Runs when a GIMS checkout is present; skips loudly (§9.7) when not.
    Either checkout satisfies it (§9.7 verified both carry the same bytes)."""
    manifest = _manifest()
    gims_path, gims_present = _gims_tree()
    guts_path, guts_present = _guts_tree()

    if not gims_present and not guts_present:
        ac = "AC-34" if vendored_relpath == "demo/vendor/expr.py" else "D1"
        pytest.skip(_skip_reason(ac, "tree half", "AUTOSQL_GIMS_TREE", gims_path))

    tree_root, which = (gims_path, "AUTOSQL_GIMS_TREE") if gims_present else (guts_path, "AUTOSQL_GUTS_TREE")
    live_file = tree_root / tree_relpath
    assert live_file.is_file(), f"{which}={tree_root} has no {tree_relpath}"

    live_hash = _sha256(live_file)
    recorded = manifest.get(vendored_relpath)
    assert recorded is not None, f"{vendored_relpath} has no recorded digest to compare the tree against"
    assert live_hash == recorded, (
        f"DRIFT DETECTED: {tree_relpath} in the live checkout at {tree_root} "
        f"no longer matches the recorded sha256 {recorded} (got {live_hash}). "
        f"Per R4/§9.5: the vendored copy stays the authority for the demo — "
        f"this is a finding to write down, not a demo failure."
    )


# ---------------------------------------------------------------------------
# AC-35 — no file this ticket vendors is modified in either GIMS checkout
#
# RE-SCOPED 2026-08-23 — Evan's own decision (form answer q3, GA-7; the dated
# note beside AC-35 in .autodev/specs/T-2.md). As signed, AC-35 asserted the
# ENTIRE `git status --porcelain` of both checkouts empty, which failed on his
# own uncommitted 2026-08-13 edits (api/app.py, account_roles/logins_db.py,
# RunlogTest data dumps) — files this ticket never reads. What the criterion
# always meant, and now says: THIS TICKET wrote nothing into his trees —
# none of the seven vendored files is modified, and no __pycache__ was
# written into a checkout during the build window.
#
# The seven vendored files are read from demo/manifest.json at test time,
# never from a hardcoded list that can drift; `_vendored_tree_paths()` fails
# loudly if the manifest and the vendored-path mapping ever disagree. The
# check is a pure function of the porcelain text (`_ac35_violations`), so a
# standing self-test can prove it still FAILS on a modified vendored file —
# by feeding it the status line such a modification produces, never by
# writing into the read-only checkouts.
# ---------------------------------------------------------------------------


def _git_status_porcelain(tree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(tree), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _vendored_tree_paths() -> dict[str, str]:
    """checkout-relative path -> vendored path, for the seven files this
    ticket vendors FROM THE CHECKOUTS, derived from demo/manifest.json.

    demo/vendor/runtime.sql is excluded on purpose: it is vendored from
    spikes/T-1/proto/, not from a GIMS checkout, so no checkout path exists
    for it and AC-35 has nothing to say about it.
    """
    manifest = _manifest()
    vendored = {
        key for key in manifest
        if key.startswith("demo/vendor/") and key != RUNTIME_PINNED
    }
    # Both directions asserted, so neither the manifest nor the mapping can
    # drift without this whole check failing loudly (never silently
    # narrowing AC-35's scope).
    assert vendored == set(VENDORED_FROM_GIMS), (
        "AC-35: demo/manifest.json's vendored files and VENDORED_FROM_GIMS "
        f"disagree — manifest-only: {sorted(vendored - set(VENDORED_FROM_GIMS))}, "
        f"mapping-only: {sorted(set(VENDORED_FROM_GIMS) - vendored)}"
    )
    return {VENDORED_FROM_GIMS[key]: key for key in sorted(vendored)}


def _ac35_violations(status_text: str, tree_paths: set[str]) -> list[str]:
    """The porcelain lines AC-35 (as re-scoped) fails on: a status entry for
    one of the seven vendored files, or any __pycache__ entry. Everything
    else in the checkout — including its owner's own uncommitted work — is
    none of this ticket's business."""
    hits: list[str] = []
    for line in status_text.splitlines():
        if len(line) < 4:
            continue
        code, rest = line[:2], line[3:]
        # A rename line reads `R  old -> new`; both sides count.
        for raw in rest.split(" -> "):
            path = raw.strip().strip('"')
            if path in tree_paths:
                hits.append(f"{code} {path} (a file this ticket vendors)")
            elif "__pycache__" in path:
                hits.append(f"{code} {path} (__pycache__ written into the checkout)")
    return hits


def _newest_pycache_mtime(tree: Path) -> float | None:
    newest: float | None = None
    for cache_dir in tree.rglob("__pycache__"):
        if not cache_dir.is_dir():
            continue
        for entry in cache_dir.rglob("*"):
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


@pytest.mark.parametrize(
    "which,resolver",
    [("GIMS-Project", _gims_tree), ("GUTS spine copy", _guts_tree)],
)
def test_ac35_gims_tree_not_modified(which: str, resolver) -> None:
    path, present = resolver()
    env_var = "AUTOSQL_GIMS_TREE" if which == "GIMS-Project" else "AUTOSQL_GUTS_TREE"
    if not present:
        pytest.skip(_skip_reason("AC-35", which, env_var, path))

    tree_paths = set(_vendored_tree_paths())
    hits = _ac35_violations(_git_status_porcelain(path), tree_paths)
    assert hits == [], (
        f"AC-35 (re-scoped, q3/GA-7): {which} at {path} shows changes to what "
        f"this ticket vendors — this ticket must never write to it:\n"
        + "\n".join(hits)
    )

    newest = _newest_pycache_mtime(path)
    if newest is not None:
        assert newest < _SESSION_START, (
            f"AC-35: {which} at {path} has a __pycache__ entry with mtime "
            f"{newest} inside this test run's build window (started {_SESSION_START}) "
            f"— something executed Python inside the read-only tree during the build."
        )


def test_ac35_rescoped_check_still_fails_on_a_vendored_modification() -> None:
    """AC-35's re-scope must NOT be a tautology. Each of the seven vendored
    files, reported modified/deleted/renamed, still fails the check — and a
    __pycache__ entry does too — proven against the pure check function,
    without a byte written into the read-only checkouts."""
    tree_paths = set(_vendored_tree_paths())
    assert len(tree_paths) == 7, (
        f"the ticket vendors seven files from the checkouts; got {sorted(tree_paths)}"
    )
    for tree_path in sorted(tree_paths):
        assert _ac35_violations(f" M {tree_path}\n", tree_paths), (
            f"AC-35 would silently tolerate a modified {tree_path}"
        )
    assert _ac35_violations(" D core/dashboard/expr.py\n", tree_paths)
    assert _ac35_violations(
        "R  static/icons.svg -> static/icons-old.svg\n", tree_paths
    ), "a rename OF a vendored file must count as a modification"
    assert _ac35_violations(
        "?? core/dashboard/__pycache__/expr.cpython-312.pyc\n", tree_paths
    ), "a __pycache__ written into the checkout must fail, tracked or not"


def test_ac35_rescoped_check_ignores_the_owners_own_work() -> None:
    """The other half of the q3 ruling: the exact status lines that were
    failing the suite — Evan's own 2026-08-13 edits, in files this ticket
    never reads — are NOT violations."""
    tree_paths = set(_vendored_tree_paths())
    his_edits = (
        " M api/app.py\n"
        " M api/manifest/resolver.py\n"
        " M api/routers/account_roles/logins_db.py\n"
        " M backups/_config/schedules.json\n"
        " M nodes/login_fastapi_users_node.py\n"
        " M projects/RunlogTest/autogen_counters.json\n"
        " M projects/RunlogTest/verbs/Chemistry/data_dumps/R1/grid_save_debug.log\n"
        "?? tests/test_rds_fallback_is_announced.py\n"
    )
    assert _ac35_violations(his_edits, tree_paths) == []


def test_ac35_wired_test_fires_end_to_end(monkeypatch) -> None:
    """The proof one level up: the WIRED test (not just the helper) fails
    when the status reader reports a modified vendored file. The reader is
    monkeypatched to simulate the signal, so nothing touches the read-only
    checkout; skips loudly when no checkout is present, exactly like the
    test it is proving."""
    import sys

    this_module = sys.modules[__name__]

    gims_path, gims_present = _gims_tree()
    guts_path, guts_present = _guts_tree()
    if not gims_present and not guts_present:
        pytest.skip(_skip_reason("AC-35", "self-check", "AUTOSQL_GIMS_TREE", gims_path))
    which, resolver = (
        ("GIMS-Project", _gims_tree) if gims_present else ("GUTS spine copy", _guts_tree)
    )
    monkeypatch.setattr(
        this_module, "_git_status_porcelain",
        lambda tree: " M core/dashboard/expr.py\n",
    )
    with pytest.raises(AssertionError, match=r"expr\.py"):
        test_ac35_gims_tree_not_modified(which, resolver)


# ---------------------------------------------------------------------------
# AC-39 — every criterion depending on a GIMS checkout skips loudly when
# absent, and the demo itself never depends on one
# ---------------------------------------------------------------------------


def test_ac39a_tree_dependent_checks_skip_loudly_when_absent() -> None:
    """AC-39(a), exercised directly: with AUTOSQL_GIMS_TREE and
    AUTOSQL_GUTS_TREE pointed at paths that do not exist, the tree-dependent
    checks in *this* module report SKIPPED and name the path.

    This runs the check functions in-process against forced-missing paths,
    independent of whatever the ambient environment happens to have set —
    so it proves the mechanism itself, not just today's environment.
    """
    nope_gims = Path("/nope")
    nope_guts = Path("/also-nope")

    reason = _skip_reason("AC-34", "tree half", "AUTOSQL_GIMS_TREE", nope_gims)
    assert "SKIPPED" not in reason  # pytest itself prints the SKIPPED verdict; the
    # reason text supplies the rest — part 2's requirement.
    assert str(nope_gims) in reason
    assert "AUTOSQL_GIMS_TREE" in reason

    reason35 = _skip_reason("AC-35", "GIMS-Project", "AUTOSQL_GIMS_TREE", nope_gims)
    assert str(nope_gims) in reason35
    assert "AUTOSQL_GIMS_TREE" in reason35

    # And the actual resolver, pointed at a path that does not exist, agrees
    # it is absent — the precondition every tree-dependent test above checks
    # before deciding whether to skip.
    forced_path, forced_present = _resolve_tree("AUTOSQL_GIMS_TREE_TEST_ONLY_DOES_NOT_EXIST", "does/not/exist")
    assert forced_present is False


def test_ac39b_manifest_halves_never_skip() -> None:
    """AC-39(b): re-assert that every manifest-half / spike-file check is
    unconditional — no `pytest.skip` anywhere in its path — by re-running
    the underlying comparison directly rather than through pytest, so this
    test cannot itself be skipped into a false pass."""
    manifest = _manifest()
    for relpath in AC33_FILES:
        actual = _sha256(REPO_ROOT / relpath)
        assert actual == manifest[relpath], f"AC-33 manifest check failed for {relpath}"
    for vendored_relpath in VENDORED_FROM_GIMS:
        actual = _sha256(REPO_ROOT / vendored_relpath)
        assert actual == manifest[vendored_relpath], (
            f"AC-34 manifest half failed for {vendored_relpath}"
        )


#: The two override variables AC-39 is about, and the checkout paths their
#: defaults resolve to.  If any of these strings appears in something `up`
#: or a pick can execute, the demo has grown a tree dependency.
_TREE_NEEDLES = (
    "AUTOSQL_GIMS_TREE",
    "AUTOSQL_GUTS_TREE",
    "GIMS-Project",
    "gims-ledger",
)


def _files_up_can_execute() -> list[Path]:
    """Everything `./run-demo up` and a pick can run: the launcher itself
    and every Python file in the demo tree OUTSIDE demo/tests/ (the tests
    are exactly where the tree variables are ALLOWED — that is AC-34/AC-35's
    loud-skip machinery).  demo/.venv is installed third-party code and
    demo/frontend is `build-ui`'s Node toolchain; neither is the demo's own
    `up` path."""
    files = [REPO_ROOT / "run-demo"]
    for path in sorted(DEMO_ROOT.rglob("*.py")):
        rel = path.relative_to(DEMO_ROOT)
        if rel.parts[0] in ("tests", ".venv", "frontend"):
            continue
        files.append(path)
    return files


def test_ac39c_nothing_up_runs_can_even_name_a_tree() -> None:
    """AC-39(c), the standing static half: no file `up` or a pick executes
    mentions the tree variables or the checkout paths AT ALL, so `./run-demo
    up`, the seed, the builder and the server cannot depend on a GIMS
    checkout on any machine — there is no code through which they could.

    This is the half that stays true on the owner's machine, where
    ../GIMS-Project resolves and a behavioural test alone would pass even
    if `up` quietly started reading it."""
    hits: list[str] = []
    for path in _files_up_can_execute():
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in _TREE_NEEDLES:
            if needle in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {needle!r}")
    assert hits == [], (
        "AC-39(c): the demo itself must never depend on a GIMS checkout, but "
        "these executable files name one — either remove the dependency or, "
        "if it belongs to the loud-skip machinery, move it under demo/tests/:\n"
        + "\n".join(hits)
    )


def test_ac39c_steps_2_and_8_answer_with_both_tree_vars_pointed_at_nothing(
    monkeypatch,
) -> None:
    """AC-39(c), the behavioural half: with AUTOSQL_GIMS_TREE and
    AUTOSQL_GUTS_TREE pointed at paths that do not exist, the demo answers
    walkthrough steps 2 and 8 with both panes populated and agreeing,
    against demo/expected-answers.json — driven through ``run_pick``, the
    same code ``POST /api/pick`` runs, on a connection guarded the same
    way (this file cannot re-run a cold-start `up`; see the module
    docstring)."""
    monkeypatch.setenv("AUTOSQL_GIMS_TREE", "/nope")
    monkeypatch.setenv("AUTOSQL_GUTS_TREE", "/also-nope")

    from demo.server import app as server_app
    from demo.server import db

    expected = json.loads((DEMO_ROOT / "expected-answers.json").read_text())
    steps = {s["step"]: s["expect"] for s in expected["steps"]}

    conn = db.connect(application_name="autosql-demo-ac39c")
    try:
        server_app.refuse_writes(conn)  # what api_pick does before a pick

        # Step 2 — the plain heartbeat select, ORDER BY key.
        r2 = server_app.run_pick(conn, {"source": "noun:Heartbeat"})
        assert r2["accepted"], f"step 2 was refused: {r2['refusal']}"
        assert r2["verdict"] == "agree"
        assert (
            r2["comparison"]["compared_rows"]
            == steps[2]["row_count"]["value"]
            == 8400
        )
        for side, pane in r2["panes"].items():
            assert pane["state"] == "answered", f"step 2 {side} pane not populated"
            assert pane["row_count"] == 8400
            assert pane["rows"], f"step 2 {side} pane page is empty"
        key_col = r2["panes"]["sql"]["columns"].index("key")
        assert (
            r2["panes"]["sql"]["rows"][0]["c"][key_col]
            == steps[2]["first_key"]["value"]
        )

        # Step 8 — the 3-point rolling average per sender.
        r8 = server_app.run_pick(
            conn,
            {"source": "noun:Heartbeat", "window": {"field": "$.payload.load"}},
        )
        assert r8["accepted"], f"step 8 was refused: {r8['refusal']}"
        assert r8["verdict"] == "agree"
        assert (
            r8["comparison"]["compared_rows"] == steps[8]["row_count"]["value"]
        )
        assert "rolling_avg" in r8["panes"]["sql"]["columns"]
        for side, pane in r8["panes"].items():
            assert pane["state"] == "answered", f"step 8 {side} pane not populated"
            assert pane["rows"], f"step 8 {side} pane page is empty"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Round-1 review, the refusals group — four inputs that produced a bare
# HTTP 500 (neither layer's refusal, naming nothing), and a read-only
# guard that did not cover the transaction it claimed to.  Spec §4.3's
# doctrine, which every test below asserts: WHICHEVER layer refuses, the
# person sees it, and it names what caused it.
# ---------------------------------------------------------------------------


def _api_pick(body: dict) -> tuple[int, dict]:
    """One body through the real route function — the same code path an
    HTTP POST runs, without needing an HTTP client."""
    from demo.server import app as server_app

    response = server_app.api_pick(body)
    return response.status_code, json.loads(response.body)


def test_gate_refuses_a_non_finite_numeric_literal_by_name() -> None:
    """The gate's finiteness row (round-1 finding: `1e400` parsed to
    float('inf'), passed the gate, and the pinned compiler's Uncompilable
    escaped as a bare 500)."""
    import gate

    for hostile in (float("inf"), float("-inf"), float("nan"), 10**400):
        with pytest.raises(gate.Refused) as excinfo:
            gate.gate(("num", hostile))
        # Named: the construct is the literal itself, and the rule says
        # what a number has to be — never a bare "invalid".
        assert excinfo.value.construct == repr(hostile)
        assert "finite" in excinfo.value.why
        assert "invalid" not in excinfo.value.why.lower()

    # The boundary from the other side: real numbers still pass.
    for fine in (0, 1.5, -2.5, 1e308, -1e308, 2**31):
        gate.gate(("num", fine))


@pytest.mark.parametrize(
    "expr",
    ["1e400", "1e309", "$.payload.load * 1e309"],
)
def test_an_overflow_literal_is_a_named_layer_1_refusal_not_a_500(expr: str) -> None:
    """End to end through the route: the review's exact reproductions
    (`computed [{name: c1, expr: "1e400"}]` and the filter spelling) now
    answer 422 with a layer-1 refusal naming the literal, where they
    answered HTTP 500 'Internal Server Error' with an empty body."""
    status, body = _api_pick(
        {"pick": {"source": "noun:Heartbeat",
                  "computed": [{"name": "c1", "expr": expr}]}}
    )
    assert status == 422, f"expected a refusal, got HTTP {status}"
    refusal = body["refusal"]
    assert refusal is not None
    assert refusal["layer"] == 1
    assert refusal["construct"] == "inf"
    assert "finite" in refusal["why"]
    assert body["sql"]["statement_sent"] is False


def test_float8_overflow_at_runtime_is_a_named_refusal_not_a_500() -> None:
    """The pinned compiler's recorded divergence
    (KNOWN_DIVERGENCES.float8_overflow_raises), reachable from the screen:
    seeded edge-00's a = 1e300 is well inside the range guard, so $.a * $.a
    passes every gate and overflows float8 INSIDE the statement (1e600 is
    not a double).  Round-1 measured a bare 500; now it is a named runtime
    refusal, the Python pane still answers (Python's float multiply yields
    inf where Postgres raises), and the next pick is unharmed.

    CHANGED 2026-08-23 (q4/GA-7): this test drove $.g * $.g while edge-04's
    g sat just below the pre-fix 297-digit guard.  With the corrected
    runtime adopted, edge-04/edge-05 straddle DBL_MAX itself, so $.g now
    fires the layer-2 magnitude probe (naming edge-05) BEFORE any statement
    runs — the wrong refusal for this test's purpose.  edge-00's $.a is the
    row that still reaches the statement and overflows inside it."""
    status, body = _api_pick(
        {"pick": {"source": "noun:EdgeCase",
                  "computed": [{"name": "sq", "expr": "$.a * $.a"}]}}
    )
    assert status == 422, f"expected a refusal, got HTTP {status}"
    refusal = body["refusal"]
    assert refusal is not None
    assert refusal["layer"] == 2
    assert refusal["kind"] == "runtime"
    assert refusal["construct"] == "float8 overflow"
    assert "overflow" in refusal["why"]
    assert "22003" in refusal["why"]
    assert "invalid" not in refusal["why"].lower()
    # The statement really ran — this is not the probe path.
    assert refusal["sql_existed"] is True
    assert refusal["statement_sent"] is True
    # The Python pane answers beside the refusal, labelled (the reported
    # fallback), because Python's float CAN hold the square.
    assert body["panes"]["python"]["state"] == "answered"
    assert body["panes"]["python"]["row_count"] == 10
    assert body["panes"]["sql"]["state"] == "raised"
    assert body["panes"]["sql"]["rows"] == []

    # And the crash is a refusal, not poison: the very next pick answers.
    status2, body2 = _api_pick({"pick": {"source": "noun:Heartbeat"}})
    assert status2 == 200
    assert body2["verdict"] == "agree"


#: The six malformed shapes round-1 measured as bare 500s, with the
#: operation each names when refused (DR-2: every malformed input gets a
#: named refusal).
_MALFORMED_PICKS = [
    ({"source": "noun:Heartbeat", "aggregate": "sum"}, 6),
    ({"source": "noun:Heartbeat", "sort": "ts"}, 4),
    ({"source": "noun:Heartbeat", "window": "payload.load"}, 8),
    ({"source": "noun:Heartbeat", "computed": "notalist"}, 2),
    ({"source": "noun:Heartbeat", "computed": 42}, 2),
    ({"source": "noun:Heartbeat",
      "computed": [{"name": "c1", "expr": "2 + 2"}, "stray"]}, 2),
]


@pytest.mark.parametrize("pick,operation", _MALFORMED_PICKS)
def test_a_malformed_pick_shape_is_a_named_refusal_not_a_500(
    pick: dict, operation: int
) -> None:
    status, body = _api_pick({"pick": pick})
    assert status == 422, f"expected a refusal, got HTTP {status}"
    refusal = body["refusal"]
    assert refusal is not None
    assert refusal["kind"] == "illegal"
    named_ops = [v["operation"] for v in refusal["violations"]]
    assert operation in named_ops, (
        f"the refusal names operations {named_ops}, not the malformed "
        f"operation {operation}"
    )
    why = refusal["why"]
    assert why.strip(), "the refusal carries no words at all"
    assert "invalid" not in why.lower(), (
        f"a bare 'invalid' is the defect, not the fix: {why!r}"
    )
    # The refusal names what the slot actually held, so a reader can act.
    assert "carries" in why


@pytest.mark.parametrize("pick,operation", _MALFORMED_PICKS[:3])
def test_api_operations_refuses_a_malformed_shape_by_name(
    pick: dict, operation: int
) -> None:
    """The contract route the screen re-derives its controls from: the
    same malformed shapes, refused in the route's own 422 {detail} form
    (round-1 measured a bare 500 out of legality's readers)."""
    from demo.server import app as server_app

    response = server_app.api_operations(json.dumps(pick))
    assert response.status_code == 422
    detail = json.loads(response.body)["detail"]
    assert f"operation {operation}" in detail
    assert "invalid" not in detail.lower()


# ---------------------------------------------------------------------------
# Round-2 review, finding 1 — the list above is the defect, not the guard.
#
# `_MALFORMED_PICKS` holds exactly the six holder-type shapes round 1 had
# already named, so the test over it passed green while six INNER-value
# shapes (`aggregate.field` a dict, `window.field` a list, `computed[i].name`
# a dict, …) still took `/api/pick` down as a bare 500 — the same structural
# blindness round 1 flagged for the AC-32 font guard, reproduced inside the
# very test written to close that finding.  A hand-maintained list of
# known-bad inputs is a guess about where the next malformed pick will be,
# and the next one was one level deeper.
#
# So the guard below is GENERATIVE, not enumerated.  The pick's schema is
# pinned beside `legality.default_pick` (every slot, every inner key, every
# legal JSON type); the table below writes that schema down as substitution
# points, and the tests substitute a wrong-typed value — one of every JSON
# type, in a truthy AND a falsy spelling, because several readers default a
# falsy slot with `or` and a falsy malformed value would otherwise sail
# through as "not set" — into EVERY point, nested ones included.  Nothing
# may 500, and everything type-illegal must be refused BY NAME.  The next
# unlisted shape is then caught by this test rather than by a reviewer.
# ---------------------------------------------------------------------------

_H = "noun:Heartbeat"

#: One value of every JSON type, truthy and falsy where the type has both.
#: `0`/`7` also cover the bool-is-int trap from the other side: the legality
#: decision below compares `type(probe)`, never `isinstance`, so `True` is
#: bool (never a legal int) and `0` is int (never a legal bool).
_TYPE_PROBES = (None, True, False, 0, 7, 2.5, [], ["x"], {}, {"x": 1})

#: The extra probe for slots that must not hold TEXT either (a holder, the
#: cap, the toggle).  Not applied where `str` is legal — a wrong VALUE in a
#: right-typed slot is the legality matrix's job, not this guard's.
_STR_PROBE = "zzz"

#: The pick's pinned schema as substitution points:
#: (path into the pick, the legal Python types there, a base pick that
#: engages the point).  `type(None)` marks the slots where the pinned shape
#: itself says `| None` / "absent means not set".  The base picks carry the
#: MINIMUM around each point so a malformed value cannot hide behind a
#: sibling: `aggregate.fn`'s base deliberately carries no field, because
#: `{"fn": False}` with no field used to read as "no aggregate at all" and
#: answer 200 — a silent repair, which DR-2 forbids as surely as a crash.
_CC = {"source": _H, "computed": [{"name": "c1", "expr": "$.priority"}]}
_SORTED = {"source": _H, "sort": {"field": "ts", "dir": "asc"}}
_AGG = {"source": _H, "aggregate": {"fn": "sum", "field": "$.payload.load"}}
_PICK_SCHEMA: list[tuple[tuple, tuple, dict]] = [
    (("source",), (str, type(None)), {"source": _H}),
    (("computed",), (list, type(None)), {"source": _H}),
    (("computed", 0), (dict,), _CC),
    (("computed", 0, "name"), (str,), _CC),
    (("computed", 0, "expr"), (str,), _CC),
    (("filter",), (str, type(None)), {"source": _H}),
    (("sort",), (dict, type(None)), {"source": _H}),
    (("sort", "field"), (str,), _SORTED),
    (("sort", "dir"), (str,), _SORTED),
    (("cap",), (int, type(None)), {"source": _H}),
    (("aggregate",), (dict, type(None)), {"source": _H}),
    (("aggregate", "fn"), (str,), {"source": _H, "aggregate": {"fn": "sum"}}),
    (("aggregate", "field"), (str, type(None)), _AGG),
    (("bucket",), (str, type(None)),
     {"source": _H, "bucket": "day", "aggregate": {"fn": "count", "field": None}}),
    (("window",), (dict, type(None)), {"source": _H}),
    (("window", "field"), (str,), {"source": _H, "window": {"field": "$.payload.load"}}),
    (("changed",), (bool, type(None)), {"source": _H}),
]

#: Which operation each top-level slot belongs to — what a refusal must name.
_SLOT_OPERATION = {"source": 1, "computed": 2, "filter": 3, "sort": 4,
                   "cap": 5, "aggregate": 6, "bucket": 7, "window": 8,
                   "changed": 9}


def _with(base: dict, where: tuple, value):
    """A deep copy of `base` with `value` substituted at `where`."""
    out = json.loads(json.dumps(base))  # base picks are plain JSON
    node = out
    for step in where[:-1]:
        node = node[step]
    node[where[-1]] = value
    return out


def _generated_malformed_picks():
    """(id, where, probe, pick, type_illegal) over the WHOLE schema."""
    for where, legal, base in _PICK_SCHEMA:
        probes_here = _TYPE_PROBES if str in legal else _TYPE_PROBES + (_STR_PROBE,)
        for probe in probes_here:
            slot = ".".join(str(s) for s in where)
            yield (f"{slot}<-{probe!r}", where, probe,
                   _with(base, where, probe), type(probe) not in legal)


_GENERATED = list(_generated_malformed_picks())


def test_the_malformed_pick_schema_covers_every_slot_of_the_pick() -> None:
    """The generator's scope, proved rather than assumed (the round-1 AC-32
    lesson, once more): if a slot is added to the pick, this fails until the
    schema table above learns it — the sweep cannot quietly fall behind the
    thing it sweeps.  The nested points are pinned too: every object-valued
    slot must have at least one inner substitution point, because the inner
    values are exactly what the round-2 review found unswept."""
    import legality

    covered = {where[0] for where, _, _ in _PICK_SCHEMA}
    assert covered == set(legality.default_pick()), (
        "the substitution schema no longer matches the pick's pinned slots — "
        f"schema has {sorted(covered)}, the pick has "
        f"{sorted(legality.default_pick())}"
    )
    nested = {where for where, _, _ in _PICK_SCHEMA if len(where) > 1}
    for holder, inner in (("sort", ("field", "dir")),
                          ("aggregate", ("fn", "field")),
                          ("window", ("field",))):
        for key in inner:
            assert (holder, key) in nested, f"({holder}, {key}) is unswept"
    assert ("computed", 0) in nested and ("computed", 0, "name") in nested \
        and ("computed", 0, "expr") in nested


@pytest.mark.parametrize(
    "where,probe,pick,type_illegal",
    [g[1:] for g in _GENERATED], ids=[g[0] for g in _GENERATED],
)
def test_no_wrong_typed_value_in_any_slot_can_500_the_pick_route(
    where: tuple, probe, pick: dict, type_illegal: bool
) -> None:
    """The whole sweep, against the crash: WHATEVER sits in WHATEVER slot,
    `/api/pick` answers — 200 for a pick that is genuinely legal, 422 with a
    refusal for one that is not, never an unhandled exception (which the
    HTTP layer would render as the bare 500 both review rounds measured)."""
    status, body = _api_pick({"pick": pick})  # a crash raises out of here
    assert status < 500, f"{where} holding {probe!r}: HTTP {status}"
    assert status in (200, 422)
    if status == 422:
        assert body["refusal"] is not None, "refused with no refusal payload"


@pytest.mark.parametrize(
    "where,probe,pick",
    [g[1:4] for g in _GENERATED if g[4]],
    ids=[g[0] for g in _GENERATED if g[4]],
)
def test_every_wrong_typed_value_in_any_slot_is_a_named_refusal(
    where: tuple, probe, pick: dict
) -> None:
    """The type-illegal half, against the silent repair: a slot holding a
    JSON type the pinned shape forbids is REFUSED — never answered as if
    the slot were empty — and the refusal names what it found, in words a
    reader can act on (DR-2; spec §4.3's doctrine)."""
    status, body = _api_pick({"pick": pick})
    assert status == 422, (
        f"{where} holding {probe!r} was not refused (HTTP {status}) — a "
        "malformed slot answered as though it were not set is a silent repair"
    )
    refusal = body["refusal"]
    assert refusal is not None
    if refusal["kind"] == "illegal":
        named = [v["operation"] for v in refusal["violations"]]
        assert _SLOT_OPERATION[where[0]] in named, (
            f"the refusal names operations {named}, not operation "
            f"{_SLOT_OPERATION[where[0]]} where the malformed value sits"
        )
        words = " ".join(v["why"] for v in refusal["violations"])
    else:
        # A named layer-1 refusal is also an honest answer — but it must
        # actually name the construct it refused.
        assert refusal["layer"] == 1
        assert str(refusal["construct"]).strip()
        words = refusal["why"]
    assert words.strip(), "the refusal carries no words at all"
    assert "invalid" not in words.lower(), (
        f"a bare 'invalid' is the defect, not the fix: {words!r}"
    )


@pytest.mark.parametrize(
    "where,probe,pick,type_illegal",
    [g[1:] for g in _GENERATED], ids=[g[0] for g in _GENERATED],
)
def test_api_operations_never_500s_on_any_wrong_typed_slot(
    where: tuple, probe, pick: dict, type_illegal: bool
) -> None:
    """The contract route, same sweep: the screen re-derives its controls
    from `/api/operations` on every change, so a malformed slot must read
    as a named 422 there too — and a type-illegal slot must never come back
    as a 200 contract quietly computed from garbage."""
    from demo.server import app as server_app

    response = server_app.api_operations(json.dumps(pick))
    assert response.status_code < 500
    if type_illegal:
        assert response.status_code == 422, (
            f"{where} holding {probe!r}: /api/operations answered "
            f"{response.status_code}, a contract derived from a slot whose "
            "type the pick's shape forbids"
        )
        detail = json.loads(response.body)["detail"]
        assert f"operation {_SLOT_OPERATION[where[0]]}" in detail
        assert "invalid" not in detail.lower()


def test_a_pick_that_is_not_an_object_is_answered_not_crashed() -> None:
    """{'pick': 'hello'} used to reach normalised_pick's TypeError and die
    as a 500; a client defect must read as a client defect."""
    status, body = _api_pick({"pick": "hello"})
    assert status == 422
    assert "JSON object" in body["detail"]


def test_the_connection_a_pick_runs_on_cannot_write() -> None:
    """The read-only guard, on the transaction a pick ACTUALLY uses.

    Round-1 measured the defect: db.connect()'s verification reads open a
    transaction BEFORE api_pick's old `SET SESSION CHARACTERISTICS AS
    TRANSACTION READ ONLY`, which only affects LATER transactions — so
    `SHOW transaction_read_only` read `off` and an UPDATE was ACCEPTED on
    the very transaction every pick ran in.  The seed was protected only
    by the accident that nothing calls commit().

    This test replicates api_pick's exact sequence — same factory, same
    application_name, the same refuse_writes() call — and proves a write
    is refused (a) inside the transaction the pick runs in, and (b) after
    a rollback, on the next transaction the same connection opens."""
    from demo.server import app as server_app
    from demo.server import db

    conn = db.connect(application_name="autosql-demo-pick")
    try:
        server_app.refuse_writes(conn)

        # (a) The CURRENT transaction — the one db.connect() already
        # opened, which the old guard provably did not cover.
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        answer = server_app.run_pick(conn, {"source": "noun:Heartbeat"})
        assert answer["accepted"]
        with pytest.raises(Exception) as excinfo:
            conn.execute("UPDATE demo.records SET key = key WHERE false")
        assert getattr(excinfo.value, "sqlstate", None) == "25006", (
            "the write was not refused by READ ONLY "
            f"(got {type(excinfo.value).__name__}: {excinfo.value})"
        )
        assert "read-only" in str(excinfo.value)

        # (b) Across a mid-pick rollback.  A rollback REVERTS the guard —
        # SET, session characteristics included, is transactional (measured
        # here: after a bare rollback the next transaction accepted a
        # write) — and the float8-overflow refusal is the one code path
        # that rolls back mid-pick, so it must re-arm the guard itself.
        # Mirror a fresh request, run that exact pick, and prove the
        # connection it leaves behind still refuses the write.
        conn.rollback()
        server_app.refuse_writes(conn)  # what every fresh request does
        overflow = server_app.run_pick(
            conn,
            {"source": "noun:EdgeCase",
             "computed": [{"name": "sq", "expr": "$.g * $.g"}]},
        )
        assert overflow["accepted"] is False  # the named runtime refusal
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on", (
            "the float8-overflow path rolled back and did not re-arm the "
            "read-only guard — the connection can write"
        )
        with pytest.raises(Exception) as excinfo2:
            conn.execute("UPDATE demo.records SET key = key WHERE false")
        assert getattr(excinfo2.value, "sqlstate", None) == "25006"
        conn.rollback()
    finally:
        conn.close()
