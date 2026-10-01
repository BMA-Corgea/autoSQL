/**
 * T-27 — ops/notify-telegram.sh is CLOSED BY DEFAULT: nothing reaches a phone unless
 * AUTODEV_NOTIFY_BIN names the sender.
 *
 * Before T-27 an unset AUTODEV_NOTIFY_BIN fell back to notify-telegram.json's `bin` and then to
 * `openclaw`, so any session without the variable delivered every packet in the outbox. Whether
 * this shop pages the owner at all is the owner's question (the morning form's Q6). Until it is
 * answered, delivery is shut unless someone opens it on purpose.
 *
 * HERMETIC, because this is the code that sends messages to a real phone:
 *   - the script runs with AUTODEV_ROOT at a temp root (its own outbox, no config file) and HOME
 *     there too;
 *   - PATH holds ONLY a shim directory and a directory of links to the few tools the script
 *     needs. The shim `openclaw` records its arguments and sends nothing. The real openclaw lives
 *     beside node, and that directory is never on this PATH;
 *   - the environment is built from nothing (never process.env), so a session's own
 *     AUTODEV_NOTIFY_BIN cannot leak in;
 *   - AUTODEV_NOTIFY_TARGET is set, so the script never reads the GUTS bridge's .env for a
 *     recipient.
 *
 * WATCHED FAILING: against the script as it stood on main e6651d0, "closed by default" and
 * "--test with the switch closed" fail (the shim is called), and the rest pass.
 *
 * run: node --test ops/tests/test_notify_telegram.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawnSync } from "node:child_process";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRIPT = process.env.NOTIFY_TELEGRAM_SCRIPT ?? path.join(REPO, "ops", "notify-telegram.sh");
const BASH = execFileSync("bash", ["-c", "command -v bash"], { encoding: "utf8" }).trim();
const TOOLS = ["cat", "mv", "mkdir", "basename", "dirname"];

function world() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "t27-notify-"));
  fs.mkdirSync(path.join(root, ".autodev", "outbox"), { recursive: true });
  fs.writeFileSync(path.join(root, ".autodev", "outbox", "T-1_accept_gate.md"), "[AutoDev] T-1 waits\n");
  const shims = path.join(root, "shims");
  const tools = path.join(root, "tools");
  fs.mkdirSync(shims);
  fs.mkdirSync(tools);
  const log = path.join(root, "openclaw-calls.log");
  fs.writeFileSync(path.join(shims, "openclaw"), `#!${BASH}\necho "$*" >> "${log}"\nexit 0\n`);
  fs.chmodSync(path.join(shims, "openclaw"), 0o755);
  for (const t of TOOLS) {
    const real = execFileSync("bash", ["-c", `command -v ${t}`], { encoding: "utf8" }).trim();
    fs.symlinkSync(real, path.join(tools, t));
  }
  return { root, shims, tools, log };
}

function run(w, args = [], env = {}) {
  const r = spawnSync(BASH, [SCRIPT, ...args], {
    encoding: "utf8",
    env: { PATH: `${w.shims}:${w.tools}`, HOME: w.root, AUTODEV_ROOT: w.root,
           AUTODEV_NOTIFY_TARGET: "t27-test-target", ...env },
  });
  return { out: (r.stdout ?? "") + (r.stderr ?? ""), code: r.status };
}
const calls = (w) => (fs.existsSync(w.log) ? fs.readFileSync(w.log, "utf8").trim().split("\n") : []);
const queued = (w) => fs.readdirSync(path.join(w.root, ".autodev", "outbox")).filter((f) => f.endsWith(".md"));

test("the harness itself: the real openclaw is not reachable from the test PATH", () => {
  const w = world();
  const r = spawnSync(BASH, ["-c", "command -v openclaw"], { encoding: "utf8",
    env: { PATH: `${w.shims}:${w.tools}` } });
  assert.equal(r.stdout.trim(), path.join(w.shims, "openclaw"));
});

test("T-27 — CLOSED BY DEFAULT: with AUTODEV_NOTIFY_BIN unset, nothing is sent and the packet stays", () => {
  const w = world();
  const { out, code } = run(w);
  assert.deepEqual(calls(w), [], "the sender must not be called");
  assert.deepEqual(queued(w), ["T-1_accept_gate.md"], "the packet stays queued for whoever opens delivery");
  assert.match(out, /delivery CLOSED/);
  assert.equal(code, 0, "closed is a policy, not a failure");
});

test("T-27 — --test with the switch closed sends nothing, and says so", () => {
  const w = world();
  const { out, code } = run(w, ["--test"]);
  assert.deepEqual(calls(w), []);
  assert.match(out, /delivery CLOSED/);
  assert.notEqual(code, 0, "a wiring test that sent nothing must not look like a pass");
});

test("OPEN ONLY BY THE SWITCH: AUTODEV_NOTIFY_BIN naming the sender delivers, once", () => {
  // Proves the harness can SEE a send, so the empty call logs above mean something.
  const w = world();
  const { code } = run(w, [], { AUTODEV_NOTIFY_BIN: path.join(w.shims, "openclaw") });
  assert.equal(code, 0);
  const c = calls(w);
  assert.equal(c.length, 1);
  assert.match(c[0], /^message send --channel telegram --target t27-test-target --message \[AutoDev\] T-1 waits/);
  assert.deepEqual(queued(w), [], "a sent packet moves to outbox/sent/");
});

test("a switch that names no executable sends nothing (the foreman-holds-all-pages convention)", () => {
  const w = world();
  const { code } = run(w, [], { AUTODEV_NOTIFY_BIN: "foreman-holds-all-pages" });
  assert.deepEqual(calls(w), []);
  assert.deepEqual(queued(w), ["T-1_accept_gate.md"]);
  assert.notEqual(code, 0);
});

test("--dry-run sends nothing, open or closed", () => {
  for (const env of [{}, { AUTODEV_NOTIFY_BIN: "openclaw" }]) {
    const w = world();
    run(w, ["--dry-run"], env);
    assert.deepEqual(calls(w), [], JSON.stringify(env));
    assert.deepEqual(queued(w), ["T-1_accept_gate.md"]);
  }
});
