/**
 * T-18 — tests for ops/gate-ping.mjs, the parked-gate watchdog.
 *
 * Every guard is WATCHED FAILING before it is trusted: each test builds a tree that
 * VIOLATES the rule, proves the watchdog reacts, then builds the compliant tree and proves
 * it does not. A guard only ever seen passing has not been shown to be a guard — this repo
 * shipped that mistake once (proto/conformance.py had three failure branches that never
 * executed) and T-17's own guard exercise found two holes in itself before merge.
 *
 * run: node --test ops/tests/test_gate_ping.mjs      (or: ops/run-tests.sh)
 * NOTE: `node --test ops/tests/` does NOT work on Node 22 — it tries to load the directory
 * as a module. Name the file.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawnSync } from "node:child_process";

// fileURLToPath, not a %20 hand-patch: this repo's path contains a space and the tool
// itself spends four lines explaining why. A hand-rolled decode fixes only %20 and breaks
// on any other encoded character, or on Windows (/C:/…), which this operator also runs.
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const TOOL = path.join(REPO, "ops", "gate-ping.mjs");

const GATES = {
  gates: {
    sp_decide: {
      name: "sp_decide",
      question: "The research is in — do you accept the recommendation?",
      keyholder: { seat: "human:owner", instructions: "Read the options doc before ruling." },
    },
    merge: { name: "merge", question: "Merge it?", keyholder: { seat: "human:owner" } },
  },
};

function tree(tickets, routes, { seen = null, ledger = [] } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateping-"));
  for (const d of [["tickets"], ["data"], ["outbox", "sent"], ["notify"]]) {
    fs.mkdirSync(path.join(dir, ".autodev", ...d), { recursive: true });
  }
  fs.mkdirSync(path.join(dir, "ops"), { recursive: true });
  fs.writeFileSync(path.join(dir, ".autodev", "data", "gates.json"), JSON.stringify(GATES));
  for (const t of tickets) {
    fs.writeFileSync(path.join(dir, ".autodev", "tickets", `${t.id}.json`), JSON.stringify(t));
  }
  fs.writeFileSync(path.join(dir, ".autodev", "events.jsonl"),
    ledger.map((e) => JSON.stringify({ type: "gate_waiting", ...e })).join("\n") + (ledger.length ? "\n" : ""));
  if (seen) {
    fs.writeFileSync(path.join(dir, ".autodev", "notify", "gate-ping.jsonl"),
      seen.map((k) => JSON.stringify({ key: k })).join("\n") + "\n");
  }
  fs.writeFileSync(path.join(dir, "tracker-stub.mjs"),
    `const R=${JSON.stringify(routes)};const i=process.argv[3];` +
    `if(!R[i]){process.exit(3)}process.stdout.write(JSON.stringify(R[i]));\n`);
  fs.writeFileSync(path.join(dir, "ops", "notify-telegram.sh"),
    `#!/usr/bin/env bash\necho called >> "${dir}/.autodev/delivered.log"\n`);
  fs.chmodSync(path.join(dir, "ops", "notify-telegram.sh"), 0o755);
  return dir;
}

function runTool(dir, args = [], extraEnv = {}) {
  const r = spawnSync("node", [TOOL, ...args], {
    encoding: "utf8",
    env: { ...process.env, AUTODEV_ROOT: dir,
           AUTODEV_TRACKER: path.join(dir, "tracker-stub.mjs"), ...extraEnv },
  });
  return { out: r.stdout ?? "", err: r.stderr ?? "", code: r.status };
}
const packets = (dir) =>
  fs.readdirSync(path.join(dir, ".autodev", "outbox")).filter((f) => f.endsWith(".md"));
const delivered = (dir) => fs.existsSync(path.join(dir, ".autodev", "delivered.log"));

const T4 = { id: "T-4", title: "Timing run", stage: "sp-decide" };
const ROUTE_PARKED = { "T-4": { ticket: "T-4", stage: "sp-decide",
  gate: { name: "sp_decide", cleared: false, policy: "human", keyholder: "human:owner",
          question: GATES.gates.sp_decide.question } } };

test("AC1 — --dry-run reports the parked gate and writes nothing", () => {
  const dir = tree([T4], ROUTE_PARKED);
  const { out, code } = runTool(dir, ["--dry-run"]);
  assert.match(out, /T-4 @ sp-decide gate sp_decide/);
  assert.match(out, /WOULD SEND/);
  assert.equal(code, 0);
  assert.equal(packets(dir).length, 0);
  assert.equal(delivered(dir), false);
});

test("AC2 — the packet carries the gate's OWN question, keyholder and instructions", () => {
  const dir = tree([T4], ROUTE_PARKED);
  runTool(dir, ["--no-send"]);
  assert.deepEqual(packets(dir), ["T-4_sp_decide_gate.md"]);
  const body = fs.readFileSync(path.join(dir, ".autodev", "outbox", packets(dir)[0]), "utf8");
  assert.ok(body.includes(GATES.gates.sp_decide.question));
  assert.ok(body.includes("human:owner"));
  assert.ok(body.includes("Read the options doc before ruling."));
  assert.ok(body.includes("T-4") && body.includes("Timing run") && body.includes("sp-decide"));
  assert.ok(body.includes("no gate_waiting event"), "must disclose it did not fix the ledger");
});

test("AC3 — idempotent: the same occurrence is announced once", () => {
  const dir = tree([T4], ROUTE_PARKED);
  runTool(dir, ["--no-send"]);
  assert.equal(packets(dir).length, 1);
  fs.unlinkSync(path.join(dir, ".autodev", "outbox", "T-4_sp_decide_gate.md")); // simulate a drain
  const { out } = runTool(dir, ["--no-send"]);
  assert.equal(packets(dir).length, 0);
  assert.match(out, /nothing parked/);
});

test("AC4 — never pings a CLEARED gate; DOES ping an unrecognised policy", () => {
  assert.match(runTool(tree([T4], ROUTE_PARKED), ["--dry-run"]).out, /WOULD SEND/);

  const cleared = tree([T4], { "T-4": { ...ROUTE_PARKED["T-4"],
    gate: { ...ROUTE_PARKED["T-4"].gate, cleared: true } } });
  assert.match(runTool(cleared, ["--dry-run"]).out, /nothing parked/);

  const auto = tree([T4], { "T-4": { ...ROUTE_PARKED["T-4"],
    gate: { ...ROUTE_PARKED["T-4"].gate, policy: "auto" } } });
  assert.match(runTool(auto, ["--dry-run"]).out, /nothing parked/);

  // The failure direction: a policy this tool has never heard of must PING, not go quiet.
  // gates.json names `recommend-and-wait` and `auto-unless-contested` as future dials, and
  // neither starts with "human" — a prefix test would have silently dropped both.
  for (const policy of ["recommend-and-wait", "human:strict", "needs-owner"]) {
    const odd = tree([T4], { "T-4": { ...ROUTE_PARKED["T-4"],
      gate: { ...ROUTE_PARKED["T-4"].gate, policy } } });
    assert.match(runTool(odd, ["--dry-run"]).out, /WOULD SEND/, `policy ${policy} must ping`);
  }
});

test("AC5 — the route comes from the tracker, not from a local map", () => {
  const src = fs.readFileSync(TOOL, "utf8");
  assert.ok(/\["next", id/.test(src), "must call `tracker next <id>`");
  assert.ok(!/sp-frame|sp-investigate|sp-synth/.test(src), "must not hard-code pipeline stages");
  const dir = tree([T4], { "T-4": { ticket: "T-4", stage: "elsewhere",
    gate: { name: "merge", cleared: false, policy: "human", keyholder: "human:owner" } } });
  assert.match(runTool(dir, ["--dry-run"]).out, /T-4 @ elsewhere gate merge/);
});

test("AC6 — a NEW occurrence (different stage) pings again", () => {
  const dir = tree([T4], ROUTE_PARKED, { seen: ["T-4|sp-decide|sp_decide"] });
  assert.match(runTool(dir, ["--dry-run"]).out, /nothing parked/);

  const moved = tree([T4], { "T-4": { ticket: "T-4", stage: "sp-spawn",
    gate: { name: "sp_decide", cleared: false, policy: "human", keyholder: "human:owner" } } },
    { seen: ["T-4|sp-decide|sp_decide"] });
  assert.match(runTool(moved, ["--dry-run"]).out, /T-4 @ sp-spawn/);
});

test("AC7 — never pings a finished ticket, by any of the ways it can be finished", () => {
  for (const done of [{ completed: true }, { terminal: true }, { closed: "done-elsewhere" },
                      { status: "complete" }]) {
    const dir = tree([{ ...T4, ...done }], ROUTE_PARKED);
    assert.match(runTool(dir, ["--dry-run"]).out, /nothing parked/, `must skip ${JSON.stringify(done)}`);
  }
  // and the tracker's own word for it, which is canonical
  const viaTracker = tree([T4], { "T-4": { ...ROUTE_PARKED["T-4"], action: { do: "done" } } });
  assert.match(runTool(viaTracker, ["--dry-run"]).out, /nothing parked/);
});

test("AC8 — an occurrence the PLUGIN already emitted is adopted, not repeated", () => {
  // watched failing first: no ledger entry -> it announces
  assert.match(runTool(tree([T4], ROUTE_PARKED), ["--dry-run"]).out, /WOULD SEND/);

  const dir = tree([T4], ROUTE_PARKED,
    { ledger: [{ ticket: "T-4", stage: "sp-decide", gate: "sp_decide" }] });
  const { out } = runTool(dir, ["--no-send"]);
  assert.match(out, /adopted/);
  assert.equal(packets(dir).length, 0, "the plugin's own pager already has this occurrence");
  // and --dry-run must SAY it would adopt, not claim it would send. A FRESH tree: the
  // run above already recorded the occurrence, so re-running on `dir` correctly sees
  // nothing at all.
  const fresh = tree([T4], ROUTE_PARKED,
    { ledger: [{ ticket: "T-4", stage: "sp-decide", gate: "sp_decide" }] });
  assert.match(runTool(fresh, ["--dry-run"]).out, /would ADOPT \(not send\)/);
});

test("AC6+AC8 TOGETHER — a past occurrence must not mute a NEW one", () => {
  // This is the interaction that hid a permanent-mute bug: adoption used to match a
  // filename in outbox/sent/, which notify-telegram.sh never prunes, so once a gate had
  // been announced ONCE every later occurrence of it was adopted forever. Neither AC6 nor
  // AC8 alone could catch it, because neither built both conditions.
  const dir = tree([T4], { "T-4": { ticket: "T-4", stage: "sp-spawn",
      gate: { name: "sp_decide", cleared: false, policy: "human", keyholder: "human:owner" } } },
    { ledger: [{ ticket: "T-4", stage: "sp-decide", gate: "sp_decide" }] });   // OLD stage
  const { out } = runTool(dir, ["--dry-run"]);
  assert.match(out, /T-4 @ sp-spawn/, "a new stage is a new occurrence even if an old one was emitted");
  assert.match(out, /WOULD SEND/, "it must actually SEND, not adopt");
  assert.doesNotMatch(out, /ADOPT/i, "adopting here would be the permanent mute");
});

test("LOUD 1 — a tracker that cannot be found is NOT an all-clear", () => {
  const dir = tree([T4], ROUTE_PARKED);
  const r = runTool(dir, ["--dry-run"], { AUTODEV_TRACKER: "/nonexistent/tracker.mjs",
                                          HOME: "/tmp/gateping-nohome", CLAUDE_PLUGIN_ROOT: "" });
  assert.equal(r.code, 2, "must exit non-zero");
  assert.match(r.err, /CANNOT READ THE BOARD/);
  assert.match(r.err, /NOT an all-clear/);
  assert.doesNotMatch(r.out, /nothing parked/, "must never claim the board is clear");
});

test("LOUD 2 — a ticket whose route cannot be read is counted, not dropped", () => {
  const dir = tree([T4, { id: "T-99", title: "Unknown", stage: "x" }], ROUTE_PARKED);
  const r = runTool(dir, ["--dry-run"]);          // the stub exits 3 for T-99
  assert.equal(r.code, 1, "an unreadable ticket must make the run fail");
  assert.match(r.err, /COULD NOT BE CHECKED/);
  assert.match(r.err, /T-99/);
  assert.match(r.out, /T-4 @ sp-decide/, "the tickets it COULD read are still reported");
});

test("LOUD 3 — a malformed ticket file is counted, not silently skipped", () => {
  const dir = tree([T4], ROUTE_PARKED);
  fs.writeFileSync(path.join(dir, ".autodev", "tickets", "broken.json"), "{not json");
  const r = runTool(dir, ["--dry-run"]);
  assert.equal(r.code, 1);
  assert.match(r.err, /broken\.json/);
});

test("delivery is attempted only when a packet was actually written", () => {
  const quiet = tree([T4], { "T-4": { ...ROUTE_PARKED["T-4"],
    gate: { ...ROUTE_PARKED["T-4"].gate, cleared: true } } });
  runTool(quiet);
  assert.equal(delivered(quiet), false);
  const live = tree([T4], ROUTE_PARKED);
  runTool(live);
  assert.equal(delivered(live), true);
});

test("CONTRACT — the REAL tracker still returns the shape this tool reads", { skip: false }, () => {
  // Every other test stubs the tracker, so a plugin upgrade that renames `gate.policy` or
  // nests `gate` would produce zero pings forever with all of them green. This is the one
  // test that pins the actual contract.
  let bin;
  try {
    bin = execFileSync("node", ["-e",
      `import(${JSON.stringify(TOOL)}).then(m=>process.stdout.write(m.findTracker()))`],
      { encoding: "utf8" }).trim();
  } catch { return; }            // plugin not installed here — nothing to pin
  if (!bin || !fs.existsSync(bin)) return;
  const out = execFileSync("node", [bin, "next", "T-4", "--root", REPO],
    { encoding: "utf8", maxBuffer: 32 << 20 });
  const r = JSON.parse(out);
  assert.ok("stage" in r, "tracker `next` must return .stage");
  assert.ok("gate" in r, "tracker `next` must return .gate");
  if (r.gate) {
    for (const f of ["name", "cleared", "policy"]) {
      assert.ok(f in r.gate, `tracker gate must carry .${f} — the tool reads it`);
    }
  }
});
