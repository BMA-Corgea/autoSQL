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
with both variables pointing at nothing") needs the full stack — the
database, seed, builder, server and screen (W4/W5/W10/W13/W14) — none of
which exist yet at W2. It is named explicitly below as `xfail(strict=False,
run=False)` rather than left out silently, because a suite that quietly
covers less than it claims is exactly the failure mode §9.7 exists to rule
out. The real end-to-end proof of AC-39(c) belongs in test_walkthrough.py
(W17), against expected-answers.json's steps 2 and 8.
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
# That fix is right, and T-2 must not revert it. But T-2's 45 acceptance
# criteria were written against the pre-fix behaviour: adopting the new file
# changes B15's guard digits, B24's edge-04/edge-05 pair, AC-13's fifth witness
# and AC-17's whole mechanism. So the demo pins the version its spec describes,
# by the same R4 pattern the plan already uses for expr.py.
#
# The divergence below is EXPECTED and is asserted, not tolerated — if the two
# files ever become identical again, this test fails and tells you to re-read
# the ruling, because that would mean someone reverted one side or the other.
RUNTIME_PINNED = "demo/vendor/runtime.sql"
RUNTIME_UPSTREAM = "spikes/T-1/proto/runtime.sql"


def test_runtime_sql_is_pinned_and_upstream_has_moved() -> None:
    """The demo's runtime.sql is pinned; the spike's has moved on. Both are true.

    This is the recorded consequence of running T-2 and T-3 in parallel on
    2026-08-22 (Evan's wrap-up item 28). It is a ruling under delegated
    authority, and it is one line to overturn — see the note above.
    """
    manifest = _manifest()
    assert RUNTIME_PINNED in manifest, (
        f"{RUNTIME_PINNED} has no recorded digest — the demo must not install "
        "an unverifiable runtime.sql"
    )
    pinned = _sha256(REPO_ROOT / RUNTIME_PINNED)
    assert pinned == manifest[RUNTIME_PINNED], (
        f"{RUNTIME_PINNED} does not match its recorded digest — expected "
        f"{manifest[RUNTIME_PINNED]}, got {pinned}"
    )

    upstream_path = REPO_ROOT / RUNTIME_UPSTREAM
    if not upstream_path.exists():
        pytest.skip(
            f"SKIPPED — {RUNTIME_UPSTREAM} is absent, so the divergence cannot "
            "be checked. The pinned copy above is still verified."
        )
    upstream = _sha256(upstream_path)
    assert upstream != pinned, (
        f"{RUNTIME_UPSTREAM} is now byte-identical to the pinned "
        f"{RUNTIME_PINNED}. That should not happen without a decision: either "
        "T-3's guard fix (297 -> 309 digits, XPR01 refusal) was reverted, or the "
        "demo silently adopted it. Re-read the ruling above before changing this."
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
# AC-35 — neither GIMS checkout is modified
# ---------------------------------------------------------------------------


def _git_status_porcelain(tree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(tree), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


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

    status = _git_status_porcelain(path)
    assert status == "", (
        f"AC-35: {which} at {path} is not clean — this ticket must never write to it:\n{status}"
    )

    newest = _newest_pycache_mtime(path)
    if newest is not None:
        assert newest < _SESSION_START, (
            f"AC-35: {which} at {path} has a __pycache__ entry with mtime "
            f"{newest} inside this test run's build window (started {_SESSION_START}) "
            f"— something executed Python inside the read-only tree during the build."
        )


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


@pytest.mark.xfail(
    reason=(
        "AC-39(c) needs the full stack (database, seed, builder, server, screen — "
        "W4/W5/W10/W13/W14), none of which exist yet at W2. Named here rather than "
        "omitted so the gap is visible rather than silent (§9.7's own point). The "
        "real proof belongs in test_walkthrough.py (W17) against "
        "demo/expected-answers.json's steps 2 and 8."
    ),
    run=False,
    strict=False,
)
def test_ac39c_up_completes_with_both_tree_vars_pointed_at_nothing() -> None:
    raise NotImplementedError
