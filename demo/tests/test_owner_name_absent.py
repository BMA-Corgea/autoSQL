"""T-14's rule, invoked by something that always runs.

WHY THIS FILE EXISTS
    ops/name-check.sh is a sound check: it exits 1 with the name present and 0 on a clean
    tree, and it was watched refusing in both directions before it was trusted. That was
    never the problem.

    The problem was that NOTHING CALLED IT. Its own header documented the usage as
    `ops/name-check.sh && git push` — a human or an agent remembering to type it — and on
    2026-09-08 the previous arrangement failed for exactly that reason: the grep fired, the
    result was not consumed, and the name reached origin/main. Replacing a check nobody ran
    with a better check nobody runs fixes nothing.

    kb/wiki/lessons.md names the class — a check that never ran reads exactly like a check
    that passed — and this is its fifth member and a different one. The other four had a
    failure path that never executed. This one's failure path works perfectly; what was
    missing was the INVOCATION.

WHY THE SUITE AND NOT A HOOK
    `.git/hooks/` is not tracked, so a hook does not travel with the repo and a fresh clone
    is unprotected — which for a public repo is the case that matters. There is no CI here
    to extend. The suite travels, and it always runs. T-17's prose guard set the precedent:
    a repo-level guard living in demo/tests/ and reading files at the repo root.

    It runs the SCRIPT rather than reimplementing the grep, so there is one implementation
    and this test also fails if the script itself breaks.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "name-check.sh"


def test_the_name_check_script_is_present_and_executable():
    assert SCRIPT.is_file(), f"{SCRIPT} is missing — T-14's rule has no instrument"
    assert SCRIPT.stat().st_mode & 0o111, f"{SCRIPT} is not executable"


def test_the_tracked_tree_carries_no_owner_name():
    """The check itself, invoked. This is the line that makes it a guard rather than a
    tool: it runs whether or not anyone remembers to type it."""
    r = subprocess.run([str(SCRIPT)], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, (
        "ops/name-check.sh refused — the owner's name is in the tracked tree (T-14).\n"
        + r.stdout + r.stderr)


def test_the_check_actually_refuses_when_the_name_is_present():
    """Watched failing, every run.

    A guard only ever seen passing has not been shown to be a guard, and this one is
    cheap to drive: feed the script a tree containing the name and require exit 1. Without
    this, a script that had been broken into always returning 0 would keep the test above
    green forever — which is the class this whole file is about.
    """
    r = subprocess.run(
        ["bash", "-c",
         # a throwaway git repo carrying the name, so the real tree is never touched
         'd=$(mktemp -d) && cd "$d" && git init -q . && mkdir -p ops design '
         '&& cp "$1" ops/name-check.sh && printf "human:evan\\n" > design/probe.md '
         '&& git add -A >/dev/null && git -c user.email=t -c user.name=t commit -qm x '
         '&& ./ops/name-check.sh; rc=$?; rm -rf "$d"; exit $rc',
         "_", str(SCRIPT)],
        capture_output=True, text=True)
    assert r.returncode == 1, (
        "ops/name-check.sh did NOT refuse a tree containing the owner's name — "
        f"exit {r.returncode}. The guard is not guarding.\n{r.stdout}{r.stderr}")
    assert "REFUSING" in (r.stdout + r.stderr)
