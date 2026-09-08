#!/usr/bin/env node
/**
 * gate-ping.mjs — announce a gate that is PARKED BY ARRIVAL.
 *
 * WHY THIS FILE EXISTS
 *   AutoDev's tracker emits `gate_waiting` in exactly one place: inside the advance path,
 *   when an advance is REFUSED because a human gate is uncleared
 *   (plugin scripts/tracker.mjs:1561-1568). A ticket that ARRIVES at such a stage is
 *   silent — the event, the "waiting at gate X" passport stamp, the CURRENT-WORK hold
 *   entry and the packet notify.mjs would render are all lost. The ping therefore fires
 *   only when something bumps into a parked ticket, which is why it looked intermittent
 *   rather than broken: the two packets ever delivered (T-2_accept_gate,
 *   T-3_sp_decide_gate) came from workers trying to advance past a gate.
 *
 *   Demonstrated 2026-09-08: T-4 was advanced into `sp-decide` with `sp_decide` uncleared
 *   and human-held, and nothing announced it. A human relayed it by hand.
 *
 *   THERE IS A SECOND, WORSE CAUSE, and it is why this cannot be worked around by simply
 *   attempting an advance. The gate check sits AFTER the validator check in that same
 *   function, so for a stage whose work IS the human's decision the advance returns
 *   `validator_pending` and never reaches the gate at all. The ordering is circular: no page
 *   until the validator passes, the validator ("ADR recorded") cannot pass until the human
 *   decides, and the human does not know to decide because there was no page. Measured over
 *   this repo's whole history: `spec_ready` emitted 7 times and `accept` 6 — gates whose
 *   validator an AGENT can satisfy — and `sp_decide` exactly ZERO. The pager is structurally
 *   unreachable for precisely the gates that most need it.
 *
 *   This watchdog sidesteps both causes by never touching the advance path.
 *
 * WHY HERE AND NOT IN THE PLUGIN
 *   The plugin is third-party (github.com/RShuken/autodev-plugin), the running version is
 *   0.53.0 and the only local checkout is 0.50.4. This repo has already ruled on cache
 *   patches: .autodev/data/gates.json says in its own header that it lives repo-local
 *   "because tracker.mjs resolves gates.json from .autodev/data/ first and falls back to
 *   the plugin — so this survives a plugin update, which a patch to the plugin cache would
 *   not." Same reasoning, same place. ops/notify-telegram.sh is the precedent: it exists
 *   because the plugin's telegram transport is an adapter slot that fails closed.
 *
 * WHAT IT DOES NOT DO
 *   It never writes ticket state (AutoDev rule 1: the tracker is the only mover). So it
 *   cannot emit a real `gate_waiting` event or write a passport stamp — those stay lost
 *   until the plugin is fixed upstream, and every packet says so in as many words.
 *
 * USAGE
 *   ops/gate-ping.mjs --dry-run    report what would be sent; write nothing
 *   ops/gate-ping.mjs --no-send    write packets into the outbox; do not deliver
 *   ops/gate-ping.mjs              write packets and drain via ops/notify-telegram.sh
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath, NOT url.pathname: this repo lives under "Coding Projects" and a URL
// percent-encodes the space, so `.pathname` yields "…/Coding%20Projects/…" — a directory
// that does not exist. Caught on the first real run, when the watchdog silently found no
// tickets and printed nothing at all. Same hazard bites the main-module check below.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.AUTODEV_ROOT ?? path.resolve(HERE, "..");
const STATE = path.join(ROOT, ".autodev");
const OUTBOX = path.join(STATE, "outbox");
const SENT = path.join(OUTBOX, "sent");
const SEEN = path.join(STATE, "notify", "gate-ping.jsonl");

const argv = new Set(process.argv.slice(2));
const DRY = argv.has("--dry-run");
const NO_SEND = argv.has("--no-send");

function tracker() {
  if (process.env.AUTODEV_TRACKER) return process.env.AUTODEV_TRACKER;
  const guesses = [
    "/home/corgea/.claude/plugins/cache/autodev-marketplace/autodev/0.53.0/scripts/tracker.mjs",
  ];
  const glob = "/home/corgea/.claude/plugins/cache/autodev-marketplace/autodev";
  try {
    for (const v of fs.readdirSync(glob).sort().reverse()) {
      guesses.push(path.join(glob, v, "scripts", "tracker.mjs"));
    }
  } catch { /* not installed here; the explicit guess or the env var has to do */ }
  for (const g of guesses) if (fs.existsSync(g)) return g;
  throw new Error("cannot find tracker.mjs; set AUTODEV_TRACKER");
}

/** Ask the TRACKER for the route. Rule 1: sessions ask, they never compute a route. */
export function routeOf(id, run = defaultRun) {
  const out = run(tracker(), ["next", id, "--root", ROOT]);
  return JSON.parse(out);
}
function defaultRun(bin, args) {
  return execFileSync("node", [bin, ...args], { encoding: "utf8", maxBuffer: 32 << 20 });
}

const isHuman = (policy) => typeof policy === "string" && policy.startsWith("human");

export function ticketFiles(dir = path.join(STATE, "tickets")) {
  try {
    return fs.readdirSync(dir).filter((f) => f.endsWith(".json")).map((f) => path.join(dir, f));
  } catch { return []; }
}

export function seenKeys(file = SEEN) {
  const out = new Set();
  try {
    for (const line of fs.readFileSync(file, "utf8").split("\n")) {
      if (!line.trim()) continue;
      try { out.add(JSON.parse(line).key); } catch { /* a corrupt line must not mute the watchdog */ }
    }
  } catch { /* first run */ }
  return out;
}

/** The plugin may already have announced this gate, from a worker bumping into it.
 *  Its packets are keyed <ticket>_<gate>_gate.md; adopt them rather than repeat them. */
export function legacyAnnounced(ticket, gate, sentDir = SENT, outboxDir = OUTBOX) {
  const name = `${ticket}_${gate}_gate.md`;
  return fs.existsSync(path.join(sentDir, name)) || fs.existsSync(path.join(outboxDir, name));
}

export function gateSpec(gate, dataDir = path.join(STATE, "data")) {
  try {
    const g = JSON.parse(fs.readFileSync(path.join(dataDir, "gates.json"), "utf8"));
    return g?.gates?.[gate] ?? null;
  } catch { return null; }
}

/** Which tickets are parked at an uncleared HUMAN gate right now. */
export function pending({ files = ticketFiles(), route = routeOf, seen = seenKeys(),
                          legacy = legacyAnnounced } = {}) {
  const out = [];
  for (const f of files) {
    let t;
    try { t = JSON.parse(fs.readFileSync(f, "utf8")); } catch { continue; }
    if (!t?.id) continue;
    // AC7: a finished ticket is not waiting for anybody.
    if (t.completed || t.terminal || t.closed) continue;

    let r;
    try { r = route(t.id); } catch { continue; }
    const g = r?.gate;
    if (!g || !g.name) continue;
    // AC4: only gates that are BOTH uncleared and human-held.
    if (g.cleared) continue;
    if (!isHuman(g.policy)) continue;

    // AC6: the occurrence is (ticket, stage, gate) — the same key the plugin uses — so a
    // loopback and re-arrival at a different stage is a NEW occurrence and pings again.
    const key = `${t.id}|${r.stage}|${g.name}`;
    if (seen.has(key)) continue;
    const adopted = legacy(t.id, g.name);
    out.push({ id: t.id, title: t.title, stage: r.stage, gate: g.name,
               keyholder: g.keyholder ?? gateSpec(g.name)?.keyholder?.seat ?? "unset",
               question: g.question ?? gateSpec(g.name)?.question ?? "",
               instructions: gateSpec(g.name)?.keyholder?.instructions ?? "",
               key, adopted });
  }
  return out;
}

export function render(p) {
  return `[AutoDev] ${p.id} is waiting on you — gate \`${p.gate}\`

**${p.title}**

It is parked at stage \`${p.stage}\` and nothing can move it until you rule.

**${p.question}**

${p.instructions ? `${p.instructions}\n\n` : ""}Keyholder: ${p.keyholder}

---
This ping came from ops/gate-ping.mjs, not from AutoDev. The tracker only announces a gate
when something tries to ADVANCE past it, so a ticket parked by ARRIVAL is silent — no
event, no passport stamp, no notification. This watchdog reads the board and fills that
gap. It does not write ticket state, so the ledger still has no gate_waiting event for
this gate; that needs a fix in the plugin itself (T-18).
`;
}

export function run({ write = true, send = true } = {}) {
  const found = pending();
  const acted = [];
  for (const p of found) {
    if (p.adopted) {                       // AC8: already announced; adopt, do not repeat
      if (write) record(p, "adopted-existing-packet");
      acted.push({ ...p, action: "adopted" });
      continue;
    }
    if (write) {
      fs.mkdirSync(OUTBOX, { recursive: true });
      fs.writeFileSync(path.join(OUTBOX, `${p.id}_${p.gate}_gate.md`), render(p));
      record(p, "written");
    }
    acted.push({ ...p, action: "written" });
  }
  if (write && send && acted.some((a) => a.action === "written")) {
    try {
      execFileSync(path.join(ROOT, "ops", "notify-telegram.sh"), [], { stdio: "inherit" });
    } catch (e) {
      // A delivery failure must not lose the packet: notify-telegram.sh leaves anything it
      // could not send in the outbox and retries on the next drain.
      console.error(`gate-ping: delivery failed (${e.message}); packets stay queued`);
    }
  }
  return acted;
}

function record(p, how) {
  fs.mkdirSync(path.dirname(SEEN), { recursive: true });
  fs.appendFileSync(SEEN, JSON.stringify({ key: p.key, id: p.id, stage: p.stage,
                                           gate: p.gate, how, ts: new Date().toISOString() }) + "\n");
}

const isMain = process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  const acted = run({ write: !DRY, send: !DRY && !NO_SEND });
  if (!acted.length) { console.log("gate-ping: nothing parked at an uncleared human gate."); }
  for (const a of acted) {
    console.log(`gate-ping: ${a.id} @ ${a.stage} gate ${a.gate} (keyholder ${a.keyholder}) — ` +
                (DRY ? "WOULD SEND" : a.action));
  }
  if (DRY) console.log("gate-ping: --dry-run, nothing written and nothing sent.");
}
