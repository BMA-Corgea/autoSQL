/**
 * T-55 — ops/checks/neighbour-ports.sh must never destroy a kept demo stack, and must never give a
 * verdict (PASS or FAIL) it did not look for.
 *
 * (3) The check's cycle ends in `./run-demo down`, which is `docker compose down --volumes`: over
 *     a demo stack somebody had kept, the old check started it and then deleted its volume, data
 *     and all (measured 2026-10-01 on a throwaway: PASS, exit 0, volume gone). It must refuse,
 *     exit 2, when the demo's container, volume or network exists before the cycle, and must hold
 *     run-demo's host-wide lock (T-62) across the whole cycle — the lock run-demo itself takes.
 * (4) Each snapshot command ended in `|| true`: a failing `docker ps`, or an `ss` that was missing,
 *     failed or printed nothing, gave an empty half that compared clean, and the check said PASS.
 *     Each must now be exit 2, "COULD NOT TELL" — and so must an `ss` or `docker` that answers but
 *     cannot see the demo while it is up, and any stop before the verdict lines (exit 1 is FAIL's).
 *
 * HERMETIC: no docker daemon, no port, no real run-demo. The script runs from a temp copy of the
 * layout it expects (ops/checks/…, demo/compose.yaml, run-demo) with PATH holding ONLY shims for
 * `docker` and `ss` and links to the few tools the script needs. The stub run-demo binds nothing; it
 * logs each call with the RUN_DEMO_LOCK_HELD it was handed, whether the lock file is open in it and
 * whether the lock is held, and records "up"/"down" so the shims can show the demo while it is up.
 * Each run uses its own container name, so its own lock file (/tmp/run-demo.<name>.lock), removed
 * afterwards by that exact path.
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
const TOOL_PATHS = Object.fromEntries(TOOLS.map((t) => [t, which(t)]));

// `docker`: canned answers, steered by the environment; every call is logged.
const DOCKER_SHIM = `#!/usr/bin/env bash
echo "docker $*" >> "$T55_DIR/docker.log"
fail() { echo "Cannot connect to the Docker daemon (T-55 shim)" >&2; exit 1; }
demo_is_up() { [[ "$(cat "$T55_DIR/state" 2>/dev/null)" == up ]]; }
case "$1" in
  compose) printf '{"name":"t55","services":{"db":{"container_name":"%s"}},"volumes":{"data":{"name":"%s"}},"networks":{"default":{"name":"%s"}}}\\n' "$T55_C" "$T55_V" "$T55_N" ;;
  volume) [[ "$T55_FAIL" == volume ]] && fail; printf '%s' "\${T55_VOLUMES:-}" ;;
  network) [[ "$T55_FAIL" == network ]] && fail; printf 'bridge\\nhost\\n%s' "\${T55_NETWORKS:-}" ;;
  ps)
    if [[ "$*" == *.ID* ]]; then              # a snapshot
      n=$(( $(cat "$T55_DIR/ps.count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$T55_DIR/ps.count"
      [[ "$T55_FAIL" == ps || ( "$T55_FAIL" == ps-after && $n -ge 2 ) ]] && fail
      printf 'abc123\\t127.0.0.1:5999->5432/tcp\\trunning\\n'
    elif [[ "$*" == *.Ports* ]]; then         # the look at the demo while it is up
      [[ "$T55_FAIL" == ps ]] && fail
      printf '127.0.0.1:5999->5432/tcp\\n'
      if demo_is_up && [[ "$T55_BLIND" != docker ]]; then printf '127.0.0.1:55440->5432/tcp\\n'; fi
    else                                      # ps -a: what exists
      [[ "$T55_FAIL" == ps || "$T55_FAIL" == ps-a ]] && fail
      printf '%s' "\${T55_CONTAINERS:-}"
    fi ;;
  *) echo "docker shim: unexpected: $*" >&2; exit 99 ;;
esac
exit 0
`;
// `ss`: 5999 always, 7777 until the FAIL control drops it, the app's 8787 while the demo is up.
const SS_SHIM = `#!/usr/bin/env bash
n=$(( $(cat "$T55_DIR/ss.count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$T55_DIR/ss.count"
case "$T55_SS" in fails) echo "ss: Cannot open netlink socket (T-55 shim)" >&2; exit 1 ;; silent) exit 0 ;; esac
echo "State  Recv-Q Send-Q Local Address:Port Peer Address:Port"
[[ "$T55_SS" == blind ]] && exit 0            # the header, and no socket table behind it
echo "LISTEN 0      4096   127.0.0.1:5999     0.0.0.0:*"
[[ "$T55_SS" == drops-7777 && $n -ge 2 ]] || echo "LISTEN 0      128    127.0.0.1:7777     0.0.0.0:*"
[[ "$(cat "$T55_DIR/state" 2>/dev/null)" == up ]] && echo "LISTEN 0      2048   127.0.0.1:8787     0.0.0.0:*"
echo "LISTEN 0      4096   127.0.0.1:55440    0.0.0.0:*"
exit 0
`;
const runDemoStub = (dbContainer) => `#!/usr/bin/env bash
DB_CONTAINER="${dbContainer}"
lock="/tmp/run-demo.$T55_C.lock"; open=no
for fd in /proc/$$/fd/*; do [[ "$(readlink "$fd")" == "$lock" ]] && open=yes; done
# Probe on a descriptor, not \`flock <file> <cmd>\` (which would exec a command PATH may not hold), and
# with a conflict code of its own, so an error can never read as "held".
held=no
if [[ -e "$lock" ]]; then
  exec 9<"$lock"; flock -n -E 75 9; rc=$?
  case $rc in 0) flock -u 9 ;; 75) held=yes ;; *) held="error-$rc" ;; esac
  exec 9<&-
fi
echo "$1 held_env=\${RUN_DEMO_LOCK_HELD:-unset} fd_open=$open lock_held=$held" >> "$T55_DIR/run-demo.log"
[[ "$1" == up && -n "\${T55_UP_EXIT:-}" ]] && exit "$T55_UP_EXIT"
echo "$1" > "$T55_DIR/state"
exit 0
`;

// What `docker ps -a` / `volume ls` / `network ls` list: a string, or a function of the run's container name.
const names = (v, C) => (typeof v === "function" ? v(C) : v ?? "");

let n = 0;
function run(opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "t55-test-"));
  const C = `t55-test-${process.pid}-${++n}-db`;
  const lock = `/tmp/run-demo.${C}.lock`;
  let full;
  try {
    for (const d of ["ops/checks", "demo", "bin"]) fs.mkdirSync(path.join(dir, d), { recursive: true });
    fs.copyFileSync(SCRIPT, path.join(dir, "ops/checks/neighbour-ports.sh"));
    fs.writeFileSync(path.join(dir, "demo/compose.yaml"), "# read through the docker shim only\n");
    fs.writeFileSync(path.join(dir, "run-demo"), runDemoStub(names(opts.runDemoContainer, C) || C), { mode: 0o755 });
    fs.writeFileSync(path.join(dir, "bin/docker"), DOCKER_SHIM, { mode: 0o755 });
    if (!opts.noSs) fs.writeFileSync(path.join(dir, "bin/ss"), SS_SHIM, { mode: 0o755 });
    for (const t of TOOLS) fs.symlinkSync(TOOL_PATHS[t], path.join(dir, "bin", t));
    const env = {
      PATH: path.join(dir, "bin"), T55_DIR: dir, T55_C: C, T55_V: `${C}-data`, T55_N: `${C}_default`,
      T55_CONTAINERS: names(opts.containers, C), T55_VOLUMES: names(opts.volumes, C),
      T55_NETWORKS: names(opts.networks, C), T55_FAIL: opts.fail ?? "", T55_SS: opts.ss ?? "",
      T55_BLIND: opts.blind ?? "", T55_UP_EXIT: opts.upExit ?? "",
      ...(opts.inheritedHeld ? { RUN_DEMO_LOCK_HELD: C } : {}),
    };
    if (opts.stdoutFull) full = fs.openSync("/dev/full", "w");
    const r = spawnSync(TOOL_PATHS.bash, [path.join(dir, "ops/checks/neighbour-ports.sh")], {
      env, encoding: "utf8", timeout: 60000, stdio: ["ignore", full ?? "pipe", "pipe"],
    });
    const log = (f) => (fs.existsSync(path.join(dir, f)) ? fs.readFileSync(path.join(dir, f), "utf8") : "");
    return { code: r.status, out: (r.stdout ?? "") + (r.stderr ?? ""), calls: log("run-demo.log"), C };
  } finally {
    if (full !== undefined) fs.closeSync(full);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.rmSync(lock, { force: true });
  }
}
const couldNotTell = (r, why) => {
  assert.equal(r.code, 2, `${why}: expected exit 2, got ${r.code}\n${r.out}`);
  assert.doesNotMatch(r.out, /\bPASS\b|\bFAIL\b/, `${why}: printed a verdict\n${r.out}`);
};
const verbs = (calls) => calls.split("\n").filter(Boolean).map((l) => l.split(" ")[0]).join(",");

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

test("(3) a kept container, volume or network of the demo: exit 2, and run-demo is never called", () => {
  const kept = {
    container: run({ containers: (C) => `other\n${C}\n` }),
    volume: run({ volumes: (C) => `other\n${C}-data\n` }),
    network: run({ networks: (C) => `${C}_default\n` }),
  };
  for (const [what, r] of Object.entries(kept)) {
    assert.equal(r.code, 2, `${what}: ${r.out}`);
    assert.match(r.out, new RegExp(`COULD NOT RUN SAFELY — the demo stack is already here: ${what} `), what);
    assert.equal(r.calls, "", `${what}: run-demo was called over a kept stack`);
  }
});

test("(3) a run-demo built around another container: exit 2 — this check's lock would not be run-demo's", () => {
  const r = run({ runDemoContainer: "some-other-db" });
  couldNotTell(r, "lock name mismatch");
  assert.match(r.out, /lock would not be run-demo's/);
  assert.equal(r.calls, "");
});

test("(4) docker could not be read — before the cycle, or only after it: exit 2, never a verdict", () => {
  for (const fail of ["ps-a", "volume", "network", "ps", "ps-after"]) couldNotTell(run({ fail }), `docker ${fail} fails`);
  assert.equal(run({ fail: "ps" }).calls, "", "a look that could not be taken must stop the check before the cycle");
});

test("(4) ss missing, failing, or silent: exit 2, never a verdict", () => {
  couldNotTell(run({ noSs: true }), "ss missing");
  couldNotTell(run({ ss: "fails" }), "ss fails");
  couldNotTell(run({ ss: "silent" }), "ss prints nothing");
});

test("(4) an ss or docker that answers but cannot see the demo while it is up: exit 2, and the stack is still taken down", () => {
  for (const [why, opts] of [["ss shows a header and no sockets", { ss: "blind" }], ["docker does not show :55440", { blind: "docker" }]]) {
    const r = run(opts);
    couldNotTell(r, why);
    assert.match(r.out, /could not see it/, why);
    assert.equal(verbs(r.calls), "up,down", `${why}: the stack this run brought up must be taken down`);
  }
});

test("a failed `./run-demo up` is exit 2, not a FAIL verdict, and no `down` follows", () => {
  const r = run({ upExit: "1" });
  couldNotTell(r, "up failed");
  assert.equal(verbs(r.calls), "up");
});

test("a stop before the verdict lines is exit 2, never FAIL's exit 1 (stdout on /dev/full)", () => {
  const r = run({ stdoutFull: true });
  assert.equal(r.code, 2, r.out);
  assert.match(r.out, /COULD NOT TELL — stopped early/);
});

test("an inherited RUN_DEMO_LOCK_HELD does not let it skip the lock", () => {
  const r = run({ inheritedHeld: true });
  assert.equal(r.code, 0, r.out);
  assert.match(r.calls, /^up held_env=\S+ fd_open=no lock_held=yes$/m);
});
