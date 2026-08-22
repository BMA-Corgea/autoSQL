"""demo/tests/test_wheelhouse.py — the wheelhouse and the venv (W3, B20).

Proves the shape B20 rules, independent of whatever venv happens to be
running this file:

  - `demo/requirements.txt` pins every package (including transitive
    dependencies) to an exact version, with a sha256 hash — i.e. it is a
    pip "hash-checking" requirements file.
  - `demo/vendor/wheels/` holds a wheel matching every hash in that file,
    and nothing pip would need is missing.
  - The wheels are tracked by git, not swallowed by `.gitignore` (B19's
    shape, applied to `demo/vendor/wheels/` instead of `demo/static/js/`).
  - `pip install --no-index --find-links demo/vendor/wheels -r
    demo/requirements.txt` actually succeeds into a *fresh* venv, which is
    the load-bearing proof for AC-32's "no network access" — this test
    does not merely assert absence of a network call, it makes one
    impossible for the invocation under test (`--no-index`) and additionally
    poisons the standard proxy/index environment variables, matching the
    project's own poisoned-environment idiom (cf. AC-2(c)).

This test does not itself require network access and does not require the
wheelhouse install to have already happened — it drives its own fresh venv.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO_ROOT / "demo"
REQUIREMENTS_FILE = DEMO_ROOT / "requirements.txt"
WHEELS_DIR = DEMO_ROOT / "vendor" / "wheels"

_HASH_LINE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s\\]+)")


def _parse_requirements() -> list[tuple[str, str, str]]:
    """Return (canonical_name, version, hash) for every pinned entry."""
    text = REQUIREMENTS_FILE.read_text()
    entries: list[tuple[str, str, str]] = []
    name = version = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        req_match = _REQ_LINE.match(line)
        if req_match:
            name, _extra, version = req_match.group(1), req_match.group(2), req_match.group(3)
            continue
        hash_match = _HASH_LINE.search(line)
        if hash_match and name is not None:
            entries.append((name, version, hash_match.group(1)))
            name = version = None
    return entries


def test_requirements_file_pins_every_package_with_a_hash() -> None:
    entries = _parse_requirements()
    assert entries, "demo/requirements.txt has no pinned, hashed entries"
    names = [e[0] for e in entries]
    assert len(names) == len(set(names)), f"duplicate entries in requirements.txt: {names}"
    for name, version, digest in entries:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{name}: not a sha256 hex digest: {digest}"
        assert version, f"{name}: no version pinned"


def test_every_pinned_hash_matches_a_wheel_in_the_wheelhouse() -> None:
    entries = _parse_requirements()
    wheel_hashes = {
        hashlib.sha256(whl.read_bytes()).hexdigest(): whl.name
        for whl in WHEELS_DIR.glob("*.whl")
    }
    missing = [(name, version, digest) for name, version, digest in entries if digest not in wheel_hashes]
    assert not missing, (
        "requirements.txt pins hashes with no matching wheel in demo/vendor/wheels/: "
        f"{missing}"
    )


def test_wheelhouse_has_no_stray_wheel_outside_requirements() -> None:
    """Every wheel that's present is actually pinned (no dead weight, no
    silent substitution possible)."""
    entries = _parse_requirements()
    pinned_hashes = {digest for _name, _version, digest in entries}
    stray = [
        whl.name
        for whl in WHEELS_DIR.glob("*.whl")
        if hashlib.sha256(whl.read_bytes()).hexdigest() not in pinned_hashes
    ]
    assert not stray, f"wheels present but not pinned in requirements.txt: {stray}"


def test_wheels_are_manylinux_or_pure_python_for_cpython312() -> None:
    for whl in WHEELS_DIR.glob("*.whl"):
        tag = whl.stem.rsplit("-", 2)[-2:]  # [abi, platform] roughly
        joined = "-".join(tag)
        is_pure = whl.name.endswith("-py3-none-any.whl")
        is_manylinux_312 = "cp312" in whl.name and "manylinux" in whl.name and "x86_64" in whl.name
        assert is_pure or is_manylinux_312, (
            f"{whl.name} is neither a pure-Python wheel nor a CPython 3.12 "
            f"manylinux x86-64 wheel ({joined})"
        )


def test_wheels_are_tracked_by_git_not_ignored() -> None:
    """B19's shape, applied to the wheelhouse (B20 says 'same shape as
    B19'). `git check-ignore -q` only accepts one pathname at a time, so
    each wheel is checked individually rather than in one batch call."""
    wheel_paths = sorted(WHEELS_DIR.glob("*.whl"))
    assert wheel_paths, "demo/vendor/wheels/ has no wheels to check"
    ignored = []
    for wheel in wheel_paths:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", str(wheel)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            ignored.append(wheel.name)
        elif result.returncode not in (1,):
            raise RuntimeError(f"git check-ignore errored on {wheel}: {result.stderr}")
    assert not ignored, (
        f"the following wheels are matched by .gitignore and would be silently "
        f"untracked on a fresh clone: {ignored}"
    )


def test_offline_install_succeeds_into_a_fresh_venv_with_network_poisoned() -> None:
    """The load-bearing proof: --no-index makes a network fetch impossible,
    not merely unlikely, and this test additionally poisons every standard
    proxy/index environment variable so even a bug that dropped --no-index
    would fail fast against a bogus address rather than quietly reaching
    the real PyPI.

    Slower than the rest of this module (~5-10s: a real `python -m venv`
    plus a real `pip install` subprocess) because that is the only way to
    prove the claim rather than assert around it."""
    import os

    with tempfile.TemporaryDirectory(prefix="autosql-wheelhouse-test-") as tmp:
        venv_dir = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        pip = venv_dir / "bin" / "pip"

        poisoned_env = dict(os.environ)
        poisoned_env.update(
            {
                "http_proxy": "http://127.0.0.1:1/",
                "https_proxy": "http://127.0.0.1:1/",
                "HTTP_PROXY": "http://127.0.0.1:1/",
                "HTTPS_PROXY": "http://127.0.0.1:1/",
                "PIP_INDEX_URL": "http://127.0.0.1:1/simple-does-not-exist",
            }
        )

        result = subprocess.run(
            [
                str(pip), "install",
                "--no-index",
                "--find-links", str(WHEELS_DIR),
                "-r", str(REQUIREMENTS_FILE),
            ],
            env=poisoned_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"offline install failed with network poisoned:\n{result.stdout}\n{result.stderr}"
        )

        check = subprocess.run(
            [str(venv_dir / "bin" / "python"), "-c",
             "import fastapi, starlette, pydantic, uvicorn, psycopg, httpx, pytest; "
             "import psycopg.pq; assert psycopg.pq.__impl__ == 'binary'"],
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0, f"installed venv cannot import the pinned stack:\n{check.stderr}"


def test_gitignore_does_not_swallow_the_wheelhouse() -> None:
    """Regression guard for the B19-shaped trap L3/L4 describe: a
    `wheels/`, `js/`, or bare `dist/`/`build/` pattern anywhere in
    .gitignore would make this directory vanish on a fresh clone."""
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    for pattern in ("\nwheels/", "\n/wheels/"):
        assert pattern not in gitignore, f".gitignore contains a bare {pattern.strip()} pattern"
