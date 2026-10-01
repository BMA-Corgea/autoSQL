/**
 * T-55 — ops/checks/neighbour-ports.sh must never destroy a kept demo stack, and must never say
 * PASS (or FAIL) when it could not look.
 *
 * (3) The check's cycle ends in `./run-demo down`, which is `docker compose down --volumes`: over
 *     a demo stack somebody had kept, the old check started it and then deleted its volume, data
 *     and all (measured 2026-10-01 on a throwaway: PASS, exit 0, volume gone). It must refuse,
 *     exit 2, when the demo's container or volume exists before the cycle, and must hold
 *     run-demo's host-wide lock (T-62) across the whole cycle.
 * (4) Each snapshot command ended in `|| true`: a failing `docker ps`, or an `ss` that was missing,
 *     failed or printed nothing, gave an empty half that compared clean, and the check said PASS.
 *     Each must now be exit 2, "COULD NOT TELL".
 *
 * HERMETIC: no docker daemon, no port, no real run-demo. The script runs from a temp copy of the
 * layout it expects (ops/checks/…, demo/compose.yaml, run-demo) with PATH holding ONLY shims for
 * `docker` and `ss` and links to the few tools the script needs. The stub run-demo binds nothing; it
 * logs each call with the RUN_DEMO_LOCK_HELD it was handed, whether the lock file is open in it, and
 * whether the lock is held. Each run uses its own container name, so its own lock file
 * (/tmp/run-demo.<name>.lock), removed afterwards by that exact path.
 *
 * WATCHED FAILING: with NEIGHBOUR_PORTS_SCRIPT=<the script as it stood on main 9773300>, every test
 * below must fail except the FAIL control. The record is .autodev/evidence/T-55/08-test-watched-failing.log.
 *
 * run: node --test ops/tests/test_neighbour_ports.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawnSync } from "node:child_process";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRIPT = process.env.NEIGHBOUR_PORTS_SCRIPT || path.join(REPO, "ops/checks/neighbour-ports.sh");
const TOOLS = ["bash", "env", "python3", "awk", "sort", "comm", "flock", "sed", "grep", "dirname", "cat", "readlink"];
const which = (t) => execFileSync("bash", ["-c", `command -v ${t}`], { encoding: "utf8" }).trim();

// `docker`: canned answers, steered by the environment; every call is logged.
const DOCKER_SHIM = `#!/usr/bin/env bash
echo "docker $*" >> "$T55_DIR/docker.log"
fail() { echo "Cannot connect to the Docker daemon (T-55 shim)" >&2; exit 1; }
case "$1" in
  compose) printf '{"name":"t55","services":{"db":{"container_name":"%s"}},"volumes":{"data":{"name":"%s"}}}\\n' "$T55_C" "$T55_V" ;;
  volume) [[ "$T55_FAIL" == volume ]] && fail; printf '%s' "\${T55_VOLUMES:-}" ;;
  ps)
    if [[ "$*" == *.Ports* ]]; then
      n=$(( $(cat "$T55_DIR/ps.count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$T55_DIR/ps.count"
      [[ "$T55_FAIL" == ps || ( "$T55_FAIL" == ps-after && $n -ge 2 ) ]] && fail
      printf 'abc123\\t127.0.0.1:5999->5432/tcp\\trunning\\n'
    else
      [[ "$T55_FAIL" == ps || "$T55_FAIL" == ps-a ]] && fail
      printf '%s' "\${T55_CONTAINERS:-}"
    fi ;;
  *) echo "docker shim: unexpected: $*" >&2; exit 99 ;;
esac
`;
// `ss`: a listener on 7777 that the FAIL control drops after the cycle.
const SS_SHIM = `#!/usr/bin/env bash
n=$(( $(cat "$T55_DIR/ss.count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$T55_DIR/ss.count"
case "$T55_SS" in fails) echo "ss: Cannot open netlink socket (T-55 shim)" >&2; exit 1 ;; silent) exit 0 ;; esac
echo "State  Recv-Q Send-Q Local Address:Port Peer Address:Port"
echo "LISTEN 0      4096   127.0.0.1:5999     0.0.0.0:*"
[[ "$T55_SS" == drops-7777 && $n -ge 2 ]] || echo "LISTEN 0      128    127.0.0.1:7777     0.0.0.0:*"
echo "LISTEN 0      4096   127.0.0.1:55440    0.0.0.0:*"
`;
const RUN_DEMO_STUB = `#!/usr/bin/env bash
lock="/tmp/run-demo.$T55_C.lock"; open=no
for fd in /proc/$$/fd/*; do [[ "$(readlink "$fd")" == "$lock" ]] && open=yes; done
if flock -n "$lock" true; then held=no; else held=yes; fi
echo "$1 held_env=\${RUN_DEMO_LOCK_HELD:-unset} fd_open=$open lock_held=$held" >> "$T55_DIR/run-demo.log"
[[ "$1" == up && -n "\${T55_UP_EXIT:-}" ]] && exit "$T55_UP_EXIT"
exit 0
`;

// What `docker ps -a` / `docker volume ls` list: a string, or a function of the run's own container name.
const names = (v, C) => (typeof v === "function" ? v(C) : v ?? "");

let n = 0;
function run(opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "t55-test-"));
  const C = `t55-test-${process.pid}-${++n}-db`;
  const lock = `/tmp/run-demo.${C}.lock`;
  try {
    for (const d of ["ops/checks", "demo", "bin"]) fs.mkdirSync(path.join(dir, d), { recursive: true });
    fs.copyFileSync(SCRIPT, path.join(dir, "ops/checks/neighbour-ports.sh"));
    fs.writeFileSync(path.join(dir, "demo/compose.yaml"), "# read through the docker shim only\n");
    fs.writeFileSync(path.join(dir, "run-demo"), RUN_DEMO_STUB, { mode: 0o755 });
    fs.writeFileSync(path.join(dir, "bin/docker"), DOCKER_SHIM, { mode: 0o755 });
    if (!opts.noSs) fs.writeFileSync(path.join(dir, "bin/ss"), SS_SHIM, { mode: 0o755 });
    for (const t of TOOLS) fs.symlinkSync(which(t), path.join(dir, "bin", t));
    const env = {
      PATH: path.join(dir, "bin"), T55_DIR: dir, T55_C: C, T55_V: `${C}-data`,
      T55_CONTAINERS: names(opts.containers, C), T55_VOLUMES: names(opts.volumes, C),
      T55_FAIL: opts.fail ?? "", T55_SS: opts.ss ?? "", T55_UP_EXIT: opts.upExit ?? "",
      ...(opts.inheritedHeld ? { RUN_DEMO_LOCK_HELD: C } : {}),
    };
    const r = spawnSync(which("bash"), [path.join(dir, "ops/checks/neighbour-ports.sh")], { env, encoding: "utf8", timeout: 60000 });
    const log = (f) => (fs.existsSync(path.join(dir, f)) ? fs.readFileSync(path.join(dir, f), "utf8") : "");
    return { code: r.status, out: r.stdout + r.stderr, calls: log("run-demo.log"), C };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
    fs.rmSync(lock, { force: true });
  }
}
const couldNotTell = (r, why) => {
  assert.equal(r.code, 2, `${why}: expected exit 2, got ${r.code}\n${r.out}`);
  assert.doesNotMatch(r.out, /\bPASS\b|\bFAIL\b/, `${why}: printed a verdict\n${r.out}`);
};

test("all visible, nothing kept: PASS, with run-demo's lock held for the whole cycle (T-62)", () => {
  const r = run();
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /PASS/);
  const want = (verb) => `${verb} held_env=${r.C} fd_open=no lock_held=yes`;
  assert.equal(r.calls, `${want("up")}\n${want("down")}\n`, "up then down, each told the lock is held, the fd closed, the lock held");
});

test("the FAIL control: a listener that vanishes across the cycle is still FAIL, exit 1", () => {
  const r = run({ ss: "drops-7777" });
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /FAIL[\s\S]*127\.0\.0\.1:7777/);
});

test("(3) a kept demo container, or its volume alone: exit 2, and run-demo is never called", () => {
  const kept = {
    container: run({ containers: (C) => `other\n${C}\n` }),
    volume: run({ volumes: (C) => `other\n${C}-data\n` }),
  };
  for (const [what, r] of Object.entries(kept)) {
    assert.equal(r.code, 2, `${what}: ${r.out}`);
    assert.match(r.out, /COULD NOT RUN SAFELY/, what);
    assert.equal(r.calls, "", `${what}: run-demo was called over a kept stack`);
  }
});

test("(4) docker could not be read — before the cycle, or only after it: exit 2, never a verdict", () => {
  for (const fail of ["ps-a", "volume", "ps", "ps-after"]) couldNotTell(run({ fail }), `docker ${fail} fails`);
  assert.equal(run({ fail: "ps" }).calls, "", "a snapshot that could not be taken must stop the check before the cycle");
});

test("(4) ss missing, failing, or silent: exit 2, never a verdict", () => {
  couldNotTell(run({ noSs: true }), "ss missing");
  couldNotTell(run({ ss: "fails" }), "ss fails");
  couldNotTell(run({ ss: "silent" }), "ss prints nothing");
});

test("a failed `./run-demo up` is exit 2, not a FAIL verdict, and no `down` follows", () => {
  const r = run({ upExit: "1" });
  couldNotTell(r, "up failed");
  assert.match(r.calls, /^up /);
  assert.doesNotMatch(r.calls, /^down /m);
});

test("an inherited RUN_DEMO_LOCK_HELD does not let it skip the lock", () => {
  const r = run({ inheritedHeld: true });
  assert.equal(r.code, 0, r.out);
  assert.match(r.calls, /^up held_env=\S+ fd_open=no lock_held=yes$/m);
});
