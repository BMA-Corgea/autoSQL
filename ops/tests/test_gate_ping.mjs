/**
 * T-18 — tests for ops/gate-ping.mjs, the parked-gate watchdog.
 *
 * AC9 is the point of this file: every guard is WATCHED FAILING before it is trusted.
 * Each test builds a tree that VIOLATES the rule, proves the watchdog reacts to it, then
 * builds the compliant tree and proves it does not. A guard only ever seen passing has not
 * been shown to be a guard — this repo has shipped that mistake (proto/conformance.py had
 * three failure branches that never executed) and T-17's own guard exercise found two holes
 * in itself before merge.
 *
 * run: node --test ops/tests/
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/%20/g, " ")), "..", "..");
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

/** A tree with a stub tracker, so the tests never depend on the real board. */
function tree(tickets, routes, { legacySent = [], seen = null } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gateping-"));
  fs.mkdirSync(path.join(dir, ".autodev", "tickets"), { recursive: true });
  fs.mkdirSync(path.join(dir, ".autodev", "data"), { recursive: true });
  fs.mkdirSync(path.join(dir, ".autodev", "outbox", "sent"), { recursive: true });
  fs.mkdirSync(path.join(dir, "ops"), { recursive: true });
  fs.writeFileSync(path.join(dir, ".autodev", "data", "gates.json"), JSON.stringify(GATES));
  for (const t of tickets) {
    fs.writeFileSync(path.join(dir, ".autodev", "tickets", `${t.id}.json`), JSON.stringify(t));
  }
  for (const f of legacySent) {
    fs.writeFileSync(path.join(dir, ".autodev", "outbox", "sent", f), "already announced");
  }
  if (seen) {
    fs.mkdirSync(path.join(dir, ".autodev", "notify"), { recursive: true });
    fs.writeFileSync(path.join(dir, ".autodev", "notify", "gate-ping.jsonl"),
      seen.map((k) => JSON.stringify({ key: k })).join("\n") + "\n");
  }
  // stub tracker: answers `next <id>` from the routes map
  fs.writeFileSync(path.join(dir, "tracker-stub.mjs"),
    `const R=${JSON.stringify(routes)};const i=process.argv[3];` +
    `if(!R[i]){process.exit(3)}process.stdout.write(JSON.stringify(R[i]));\n`);
  // stub deliverer: records that it was called, so "did it try to send" is observable
  fs.writeFileSync(path.join(dir, "ops", "notify-telegram.sh"),
    `#!/usr/bin/env bash\necho called >> "${dir}/.autodev/delivered.log"\n`);
  fs.chmodSync(path.join(dir, "ops", "notify-telegram.sh"), 0o755);
  return dir;
}

function runTool(dir, args = []) {
  return execFileSync("node", [TOOL, ...args], {
    encoding: "utf8",
    env: { ...process.env, AUTODEV_ROOT: dir, AUTODEV_TRACKER: path.join(dir, "tracker-stub.mjs") },
  });
}
const packets = (dir) =>
  fs.readdirSync(path.join(dir, ".autodev", "outbox")).filter((f) => f.endsWith(".md"));
const delivered = (dir) => fs.existsSync(path.join(dir, ".autodev", "delivered.log"));

const PARKED = {
  tickets: [{ id: "T-4", title: "Timing run", stage: "sp-decide" }],
  routes: { "T-4": { ticket: "T-4", stage: "sp-decide",
    gate: { name: "sp_decide", cleared: false, policy: "human", keyholder: "human:owner",
            question: GATES.gates.sp_decide.question } } },
};

test("AC1 — --dry-run reports the parked gate and writes nothing", () => {
  const dir = tree(PARKED.tickets, PARKED.routes);
  const out = runTool(dir, ["--dry-run"]);
  assert.match(out, /T-4 @ sp-decide gate sp_decide/);
  assert.match(out, /WOULD SEND/);
  assert.equal(packets(dir).length, 0, "dry-run must write no packet");
  assert.equal(delivered(dir), false, "dry-run must not deliver");
});

test("AC2 — the packet carries the gate's OWN question and keyholder", () => {
  const dir = tree(PARKED.tickets, PARKED.routes);
  runTool(dir, ["--no-send"]);
  const files = packets(dir);
  assert.deepEqual(files, ["T-4_sp_decide_gate.md"]);
  const body = fs.readFileSync(path.join(dir, ".autodev", "outbox", files[0]), "utf8");
  assert.ok(body.includes(GATES.gates.sp_decide.question), "must quote the gate's own question");
  assert.ok(body.includes("human:owner"), "must name the keyholder");
  assert.ok(body.includes("Read the options doc before ruling."), "must carry the instructions");
  assert.ok(body.includes("T-4") && body.includes("Timing run") && body.includes("sp-decide"));
  assert.ok(body.includes("no gate_waiting event"), "must disclose it did not fix the ledger");
});

test("AC3 — idempotent: a second run sends nothing", () => {
  const dir = tree(PARKED.tickets, PARKED.routes);
  runTool(dir, ["--no-send"]);
  assert.equal(packets(dir).length, 1);
  fs.unlinkSync(path.join(dir, ".autodev", "outbox", "T-4_sp_decide_gate.md")); // simulate a drain
  const out = runTool(dir, ["--no-send"]);
  assert.equal(packets(dir).length, 0, "the same occurrence must not be announced twice");
  assert.match(out, /nothing parked/);
});

test("AC4 — never pings a CLEARED gate, nor a non-human gate", () => {
  // watched failing first: the same tree with an uncleared human gate DOES ping
  const live = tree(PARKED.tickets, PARKED.routes);
  assert.match(runTool(live, ["--dry-run"]), /WOULD SEND/);

  const cleared = tree(PARKED.tickets, { "T-4": { ...PARKED.routes["T-4"],
    gate: { ...PARKED.routes["T-4"].gate, cleared: true } } });
  assert.match(runTool(cleared, ["--dry-run"]), /nothing parked/);

  const auto = tree(PARKED.tickets, { "T-4": { ...PARKED.routes["T-4"],
    gate: { ...PARKED.routes["T-4"].gate, policy: "auto" } } });
  assert.match(runTool(auto, ["--dry-run"]), /nothing parked/);
});

test("AC5 — the route comes from the tracker, not from a local map", () => {
  const src = fs.readFileSync(TOOL, "utf8");
  assert.ok(/\["next", id/.test(src), "must call `tracker next <id>`");
  assert.ok(!/sp-frame|sp-investigate|sp-synth/.test(src),
    "must not hard-code pipeline stages — rule 1: sessions ask the tracker for a route");
  // and stubbing the tracker changes the answer, proving the tracker is really consulted
  const dir = tree(PARKED.tickets, { "T-4": { ticket: "T-4", stage: "elsewhere",
    gate: { name: "merge", cleared: false, policy: "human", keyholder: "human:owner" } } });
  assert.match(runTool(dir, ["--dry-run"]), /T-4 @ elsewhere gate merge/);
});

test("AC6 — a NEW occurrence (different stage) pings again", () => {
  const dir = tree(PARKED.tickets, PARKED.routes, { seen: ["T-4|sp-decide|sp_decide"] });
  assert.match(runTool(dir, ["--dry-run"]), /nothing parked/, "the recorded occurrence is silent");

  const moved = tree(PARKED.tickets, { "T-4": { ticket: "T-4", stage: "sp-spawn",
    gate: { name: "sp_decide", cleared: false, policy: "human", keyholder: "human:owner" } } },
    { seen: ["T-4|sp-decide|sp_decide"] });
  assert.match(runTool(moved, ["--dry-run"]), /T-4 @ sp-spawn/, "a new stage is a new occurrence");
});

test("AC7 — never pings a completed or closed ticket", () => {
  for (const done of [{ completed: true }, { terminal: true }, { closed: "done-elsewhere" }]) {
    const dir = tree([{ id: "T-4", title: "Timing run", stage: "sp-decide", ...done }], PARKED.routes);
    assert.match(runTool(dir, ["--dry-run"]), /nothing parked/, `must skip ${JSON.stringify(done)}`);
  }
});

test("AC8 — a gate the plugin already announced is adopted, not repeated", () => {
  const dir = tree(PARKED.tickets, PARKED.routes, { legacySent: ["T-4_sp_decide_gate.md"] });
  const out = runTool(dir, ["--no-send"]);
  assert.match(out, /adopted/);
  assert.equal(packets(dir).length, 0, "must not write a second packet for the same gate");
  // and having adopted it, it stays quiet next time
  assert.match(runTool(dir, ["--dry-run"]), /nothing parked/);
});

test("delivery is attempted only when a packet was actually written", () => {
  const quiet = tree(PARKED.tickets, { "T-4": { ...PARKED.routes["T-4"],
    gate: { ...PARKED.routes["T-4"].gate, cleared: true } } });
  runTool(quiet);
  assert.equal(delivered(quiet), false, "nothing to send must not invoke the deliverer");

  const live = tree(PARKED.tickets, PARKED.routes);
  runTool(live);
  assert.equal(delivered(live), true, "a written packet must be handed to the deliverer");
});
