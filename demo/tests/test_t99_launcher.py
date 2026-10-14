"""demo/tests/test_t99_launcher.py — T-99: the front door stays up, and clears its own leftovers.

1. **The app ignores SIGHUP.** When ``./start.sh`` is a terminal's whole command (double-clicked,
   "Run in Terminal", ``script -qec ./start.sh``), the window closing sends SIGHUP to the script's
   process group, and the app ``run-demo up`` started in the background died right after "Ready.".
   ``start_app`` now ignores HUP before the exec.  Held by running the real ``start_app`` (``run-demo``
   is sourced; nothing is dispatched) with a stub app that only sleeps, then reading the stub's
   ignored-signal mask (``/proc/<pid>/status`` SigIgn, bit 0 = SIGHUP).  No port, no database.
2. **start.sh clears the demo's own leftovers and still refuses a stranger.** A copy of ``start.sh``
   runs beside a stub ``run-demo`` with shims for docker, ss, lsof, curl and the browser openers —
   hermetic: no docker daemon, no real port, no browser window, the real stack untouched.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_DEMO = Path(os.environ.get("T99_RUN_DEMO", _REPO_ROOT / "run-demo"))
START_SH = Path(os.environ.get("T99_START_SH", _REPO_ROOT / "start.sh"))

pytestmark = pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="reads /proc (Linux)")


def _default_hup():
    # The child starts with SIGHUP at its default, whatever this test runner was started under
    # (a shell started with HUP ignored can never un-ignore it, so the check could not go red).
    signal.signal(signal.SIGHUP, signal.SIG_DFL)


def _ignores_hup(pid: int) -> bool:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("SigIgn:"):
            return bool(int(line.split()[1], 16) & 1)
    raise AssertionError(f"no SigIgn line for pid {pid}")


def _stop(pid: int) -> None:
    # Only the stub this test started: checked by its command line before the kill.
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        return
    if cmd[:2] == [b"sleep", b"300"]:
        os.kill(pid, signal.SIGKILL)


def test_the_app_run_demo_starts_ignores_sighup(tmp_path):
    (tmp_path / "venv" / "bin").mkdir(parents=True)
    stub = tmp_path / "venv" / "bin" / "python"
    stub.write_text("#!/bin/sh\nexec sleep 300\n")
    stub.chmod(0o755)
    js = tmp_path / "demo" / "static" / "js"
    js.mkdir(parents=True)
    for f in ("vendor.js", "app.js"):
        (js / f).write_text("")
    (tmp_path / "demo" / "static" / "index.html").write_text("")
    harness = textwrap.dedent(f"""
        source "$1"
        set +e
        exec {{TEST_LOCK_FD}}>/dev/null
        sleep 300 >/dev/null 2>&1 </dev/null & echo "control=$!"
        VENV_DIR="{tmp_path}/venv"; DEMO_DIR="{tmp_path}/demo"; REPO_ROOT="{tmp_path}"
        APP_LOG="{tmp_path}/app.log"; APP_PIDFILE="{tmp_path}/app.pid"; APP_READY_TIMEOUT_SECONDS=10
        DB_HOST=127.0.0.1; APP_PORT=1
        pid_holds_port() {{ return 0; }}
        app_answers() {{ return 0; }}
        start_app; echo "start_app=$?"
    """)
    out = subprocess.run(["bash", "-c", harness, "harness", str(RUN_DEMO)], capture_output=True, text=True,
                         timeout=60, preexec_fn=_default_hup)
    got = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line and " " not in line)
    control = int(got["control"])
    app = int((tmp_path / "app.pid").read_text()) if (tmp_path / "app.pid").exists() else None
    try:
        assert got.get("start_app") == "0" and app, out.stdout + out.stderr
        assert not _ignores_hup(control), "the control already ignores SIGHUP: this check could not go red"
        assert _ignores_hup(app), (
            "the app run-demo up started does not ignore SIGHUP: a terminal closing after ./start.sh kills it")
    finally:
        _stop(control)
        if app:
            _stop(app)


# ── start.sh, in a sandbox, with the REAL run-demo ─────────────────────────
#
# A sandbox tree holds byte copies of start.sh and run-demo with one line changed in each: the
# container's name, so the host-wide lock file (/tmp/run-demo.<name>.lock) is the sandbox's own and
# never the real stack's. `down` is the real run-demo's (its lock, its pidfile check, its compose
# call); only `up` is stubbed — a real `up` builds a venv and seeds 10,470 rows. docker, ss, lsof,
# curl and the browser openers are shims that log every call: nothing real is created, removed or
# opened, no real port is touched.

_SHIMS = {
    # docker: running; the sandbox's container is "running" / "exited" per $W/container
    "docker": r"""echo "docker $*" >>"$W/calls"
      case "$1" in
        info) exit 0 ;;
        ps) if [ -f "$W/container" ]; then
              case "$*" in *State*) cat "$W/container" ;; *) echo 0123abcd ;; esac
            fi; exit 0 ;;
        compose) case "$*" in *" down"*)
              [ -f "$W/down-fails" ] && { echo "Error response from daemon: removal of container is already in progress" >&2; exit 1; }
              rm -f "$W/container"; exit 0 ;; esac; exit 0 ;;
      esac
      exit 0""",
    # ss: 55440 is held by the sandbox's container or by a stranger; 8787 by an app that is up
    "ss": r"""echo "State Recv-Q Send-Q Local Address:Port"
      { [ -f "$W/container" ] || [ -f "$W/stranger" ]; } && echo "LISTEN 0 4096 127.0.0.1:55440 0.0.0.0:*"
      { [ -f "$W/up" ] || [ -f "$W/slow" ]; } && echo "LISTEN 0 2048 127.0.0.1:8787 0.0.0.0:*"
      exit 0""",
    "lsof": r"""case "$*" in *55440*) { [ -f "$W/container" ] || [ -f "$W/stranger" ]; } && exit 0 ;; esac
      case "$*" in *8787*) { [ -f "$W/up" ] || [ -f "$W/slow" ]; } && exit 0 ;; esac
      exit 1""",
    # curl: the app answers once it is up; a slow app answers only a caller that waits 5 s or more
    "curl": r"""m=3; prev=""; for a in "$@"; do [ "$prev" = "-m" ] && m="$a"; prev="$a"; done
      echo "curl -m $m" >>"$W/calls"
      [ -f "$W/up" ] && exit 0
      [ -f "$W/slow" ] && [ "$m" -ge 5 ] && exit 0
      exit 28""",
    "xdg-open": "exit 1",
    "open": "exit 1",
}

#: the sandbox's run-demo: `up` stubbed, every other verb the real one
_RUN_DEMO = r"""#!/usr/bin/env bash
if [ "$1" = up ]; then
  echo "run-demo up (lock held: ${RUN_DEMO_LOCK_HELD:-no})" >>"$W/calls"
  { [ -f "$W/container" ] || [ -f "$W/stranger" ]; } && { echo "55440 taken" >&2; exit 1; }
  touch "$W/up"; exit 0
fi
echo "run-demo $1 (lock held: ${RUN_DEMO_LOCK_HELD:-no})" >>"$W/calls"
exec "$(dirname "$0")/run-demo.real" "$@"
"""


def _sandboxed(src: Path, dest: Path, name: str) -> None:
    text = src.read_text()
    line = 'DB_CONTAINER="autosql-demo-db"'
    assert text.count(line) == 1, f"{src.name}: the container's name is not on one line; the sandbox can't rename it"
    dest.write_text(text.replace(line, f'DB_CONTAINER="{name}"'))
    dest.chmod(0o755)


class _Sandbox:
    def __init__(self, tmp_path):
        self.tree, self.w, shims = tmp_path / "tree", tmp_path / "w", tmp_path / "shims"
        for d in (self.tree / "demo" / ".venv", self.w, shims):
            d.mkdir(parents=True)
        self.name = f"asqlbld-t99-{os.getpid()}-{tmp_path.name[-12:]}"
        self.lock = Path(f"/tmp/run-demo.{self.name}.lock")
        _sandboxed(START_SH, self.tree / "start.sh", self.name)
        _sandboxed(RUN_DEMO, self.tree / "run-demo.real", self.name)
        shutil.copy(_REPO_ROOT / "demo" / "compose.yaml", self.tree / "demo" / "compose.yaml")
        (self.tree / "run-demo").write_text(_RUN_DEMO)
        (self.tree / "run-demo").chmod(0o755)
        for name, body in _SHIMS.items():
            (shims / name).write_text("#!/usr/bin/env bash\n" + body + "\n")
            (shims / name).chmod(0o755)
        self.env = dict(os.environ, W=str(self.w), PATH=f"{shims}:{os.environ['PATH']}")
        self.env.pop("RUN_DEMO_LOCK_HELD", None)

    def mark(self, what, text=""):
        (self.w / what).write_text(text)

    def start(self, **kw):
        return subprocess.Popen(["bash", str(self.tree / "start.sh")], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=self.env, cwd=self.tree, **kw)

    def run(self):
        p = self.start()
        out, _ = p.communicate(timeout=180)
        return p.returncode, out, self.calls()

    def calls(self):
        f = self.w / "calls"
        return [c for c in f.read_text().split("\n") if c] if f.exists() else []

    def close(self):
        if self.lock.exists():
            self.lock.unlink()


@pytest.fixture
def sandbox(tmp_path):
    sb = _Sandbox(tmp_path)
    yield sb
    sb.close()


def _verbs(calls):
    return [c for c in calls if c.startswith("run-demo") or c.startswith("docker compose")]


@pytest.mark.parametrize("state", ["running", "exited"])
def test_start_clears_the_demos_own_database_left_without_its_app_and_comes_up(sandbox, state):
    sandbox.mark("container", state + "\n")
    code, out, calls = sandbox.run()
    assert code == 0 and "Ready." in out, f"the front door refused its own leftovers:\n{out}"
    v = _verbs(calls)
    assert v[0] == "run-demo down (lock held: " + sandbox.name + ")" and "down --volumes" in v[1], v
    assert v[2] == "run-demo up (lock held: " + sandbox.name + ")", v


def test_start_clears_a_stale_pidfile_and_comes_up(sandbox):
    (sandbox.tree / "demo" / ".venv" / "autosql-app.pid").write_text("999999\n")
    code, out, calls = sandbox.run()
    assert code == 0 and "Ready." in out, out
    assert not (sandbox.tree / "demo" / ".venv" / "autosql-app.pid").exists()
    assert [c.split(" (")[0] for c in _verbs(calls)][::2] == ["run-demo down", "run-demo up"], calls


def test_start_still_refuses_a_stranger_on_the_database_port(sandbox):
    sandbox.mark("stranger")
    code, out, calls = sandbox.run()
    assert code == 1 and "Port 55440 is already taken by something else" in out, out
    assert _verbs(calls) == [], f"start.sh acted on a port it does not own: {calls}"


def test_start_with_nothing_left_behind_goes_straight_up(sandbox):
    code, out, calls = sandbox.run()
    assert code == 0 and [c.split(" (")[0] for c in _verbs(calls)] == ["run-demo up"], (calls, out)


def test_start_waits_for_another_run_then_looks_again_before_it_clears_anything(sandbox):
    """The check's MEDIUM (repro A): another run holds the stack while the app isn't answering yet; when
    it lets go the app answers. start.sh must look AFTER the wait — so it finds the demo running and
    removes nothing — and must say that it is waiting."""
    sandbox.mark("container", "running\n")
    if not sandbox.lock.exists():
        sandbox.lock.touch()
    holder = subprocess.Popen(["bash", "-c", f'exec 9<"{sandbox.lock}"; flock 9; echo held; sleep 4; touch "$W/up"'],
                              stdout=subprocess.PIPE, text=True, env=sandbox.env)
    try:
        assert holder.stdout.readline().strip() == "held"
        code, out, calls = sandbox.run()
    finally:
        holder.wait(timeout=30)
    assert not any("down --volumes" in c for c in calls), f"the database was removed after the wait: {calls}"
    assert "Another run is using the demo; waiting" in out, f"the wait was not said:\n{out}"
    assert code == 0 and "Already running." in out, out


def test_start_never_clears_an_app_that_is_up_but_slow(sandbox):
    """The check's repro B: the app answers, but slower than three seconds. It is running."""
    sandbox.mark("container", "running\n")
    sandbox.mark("slow")
    code, out, calls = sandbox.run()
    assert not any("down --volumes" in c for c in calls), f"a running app's database was removed: {calls}"
    assert code == 0 and "Already running." in out, out


def test_a_clear_that_fails_stops_start_in_its_own_words(sandbox):
    """The check's LOW: a `down` that fails is not ignored, and the port is never blamed on a stranger."""
    sandbox.mark("container", "exited\n")
    sandbox.mark("down-fails")
    code, out, calls = sandbox.run()
    assert "It is not this demo" not in out, f"a failed clear was blamed on a stranger:\n{out}"
    assert code == 1 and "could not be cleared" in out, out
    assert "removal of container is already in progress" in out, f"down's own words were hidden:\n{out}"
    assert not any(c.startswith("run-demo up") for c in calls), calls
