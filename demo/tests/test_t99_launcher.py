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


# ── start.sh, hermetic ─────────────────────────────────────────────────────

_SHIMS = {
    # docker: running; `ps -aq --filter name=…` lists the demo's container while it is "left behind"
    "docker": """case "$1" in
        info) exit 0 ;;
        ps) [ -f "$W/container" ] && echo 0123abcd; exit 0 ;;
        *) echo "docker $*" >>"$W/calls"; exit 0 ;;
      esac""",
    # ss: 55440 is held by the leftover container or by a stranger; 8787 by an app that is up
    "ss": """echo "State Recv-Q Send-Q Local Address:Port"
      { [ -f "$W/container" ] || [ -f "$W/stranger" ]; } && echo "LISTEN 0 4096 127.0.0.1:55440 0.0.0.0:*"
      [ -f "$W/up" ] && echo "LISTEN 0 2048 127.0.0.1:8787 0.0.0.0:*"
      exit 0""",
    "lsof": """case "$*" in *55440*) { [ -f "$W/container" ] || [ -f "$W/stranger" ]; } && exit 0 ;; esac
      case "$*" in *8787*) [ -f "$W/up" ] && exit 0 ;; esac
      exit 1""",
    # curl: the app answers once run-demo up has run
    "curl": """[ -f "$W/up" ] && exit 0; exit 7""",
    "xdg-open": "exit 1",
    "open": "exit 1",
}

_STUB_RUN_DEMO = """#!/usr/bin/env bash
echo "run-demo $1" >>"$W/calls"
case "$1" in
  down) rm -f "$W/container" "$(dirname "$0")/demo/.venv/autosql-app.pid" ;;
  up) [ -f "$W/container" ] || [ -f "$W/stranger" ] && { echo "55440 taken" >&2; exit 1; }
      touch "$W/up" ;;
esac
exit 0
"""


def _front_door(tmp_path, *, container=False, pidfile=False, stranger=False):
    tree, w, shims = tmp_path / "tree", tmp_path / "w", tmp_path / "shims"
    for d in (tree / "demo" / ".venv", w, shims):
        d.mkdir(parents=True)
    shutil.copy(START_SH, tree / "start.sh")
    (tree / "run-demo").write_text(_STUB_RUN_DEMO)
    (tree / "run-demo").chmod(0o755)
    for name, body in _SHIMS.items():
        (shims / name).write_text("#!/usr/bin/env bash\n" + body + "\n")
        (shims / name).chmod(0o755)
    if container:
        (w / "container").touch()
    if pidfile:
        (tree / "demo" / ".venv" / "autosql-app.pid").write_text("999999\n")
    if stranger:
        (w / "stranger").touch()
    env = dict(os.environ, W=str(w), PATH=f"{shims}:{os.environ['PATH']}")
    out = subprocess.run(["bash", str(tree / "start.sh")], capture_output=True, text=True, env=env,
                         timeout=120, cwd=tree)
    calls = (w / "calls").read_text().split("\n")[:-1] if (w / "calls").exists() else []
    return out, calls


@pytest.mark.parametrize("left", ["container", "pidfile"])
def test_start_clears_what_an_earlier_run_left_behind_and_comes_up(tmp_path, left):
    out, calls = _front_door(tmp_path, **{left: True})
    said = out.stdout + out.stderr
    assert out.returncode == 0 and "Ready." in said, f"the front door refused its own leftovers:\n{said}"
    assert calls == ["run-demo down", "run-demo up"], calls


def test_start_still_refuses_a_stranger_on_the_database_port(tmp_path):
    out, calls = _front_door(tmp_path, stranger=True)
    said = out.stdout + out.stderr
    assert out.returncode == 1 and "Port 55440 is already taken by something else" in said, said
    assert calls == [], f"start.sh acted on a port it does not own: {calls}"


def test_start_with_nothing_left_behind_goes_straight_up(tmp_path):
    out, calls = _front_door(tmp_path)
    assert out.returncode == 0 and calls == ["run-demo up"], (calls, out.stdout + out.stderr)
