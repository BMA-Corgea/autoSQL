#!/usr/bin/env node
/**
 * gate-ping.mjs — announce a gate that is PARKED BY ARRIVAL.
 *
 * WHY THIS FILE EXISTS
 *   AutoDev's tracker emits `gate_waiting` in exactly one place: inside the advance path,
 *   when an advance is REFUSED because a human gate is uncleared
 *   (plugin scripts/tracker.mjs:1561-1568). A ticket that ARRIVES at such a stage is
 *   silent — the event, the "waiting at gate X" passport stamp, the CURRENT-WORK hold
 *   entry and the packet notify.mjs would render are all lost.
 *
 *   Demonstrated 2026-09-08: T-4 was advanced into `sp-decide` with `sp_decide` uncleared
 *   and human-held, and nothing announced it. A human relayed it by hand.
 *
 *   THERE IS A SECOND, WORSE CAUSE, and it is why this cannot be worked around by simply
 *   attempting an advance. The gate check sits AFTER the validator check in that same
 *   function, so for a stage whose work IS the human's decision the advance returns
 *   `validator_pending` and never reaches the gate at all. The ordering is circular: no
 *   page until the validator passes, the validator ("ADR recorded") cannot pass until the
 *   human decides, and the human does not know to decide because there was no page.
 *   Measured over this repo's whole history: `spec_ready` 7 emissions and `accept` 6 —
 *   gates whose validator an AGENT can satisfy — and `sp_decide` exactly ZERO. The pager
 *   is structurally unreachable for precisely the gates that most need it.
 *
 *   This watchdog sidesteps both causes by never touching the advance path.
 *
 * THE FAILURE DIRECTION, CHOSEN DELIBERATELY
 *   For a pager, a duplicate costs the reader two seconds and a miss costs a night. So
 *   every ambiguity here resolves toward ANNOUNCING, and every failure is loud:
 *     - a gate policy this tool does not recognise is treated as human and pinged;
 *     - a ticket whose route cannot be read is COUNTED, reported, and makes the run exit
 *       non-zero — it is never silently dropped;
 *     - if the tracker cannot be found at all the tool errors out instead of reporting a
 *       clean board. That last one was a real bug here: with a bad tracker path it printed
 *       "nothing parked at an uncleared human gate" and exited 0, which under the Stop
 *       hook's `>/dev/null 2>&1` is a permanent silent all-clear — the exact defect this
 *       tool exists to prevent, wearing a clean bill of health.
 *
 * WHY HERE AND NOT IN THE PLUGIN
 *   The plugin is third-party (github.com/RShuken/autodev-plugin), the running version is
 *   0.53.0 and the only local checkout is 0.50.4. This repo has already ruled on cache
 *   patches: .autodev/data/gates.json says in its own header that it lives repo-local
 *   "because tracker.mjs resolves gates.json from .autodev/data/ first and falls back to
 *   the plugin — so this survives a plugin update, which a patch to the plugin cache would
 *   not." ops/notify-telegram.sh is the same pattern.
 *
 * WHAT IT DOES NOT DO
 *   It never writes ticket state (AutoDev rule 1: the tracker is the only mover). So the
 *   ledger still gets no `gate_waiting` event and the passport no stamp — only the plugin
 *   can restore those, and every packet says so. A ping from here is not evidence that the
 *   record is whole.
 *
 * USAGE
 *   ops/gate-ping.mjs --dry-run    report; write nothing, send nothing
 *   ops/gate-ping.mjs --no-send    write packets into the outbox; do not deliver
 *   ops/gate-ping.mjs              write packets and drain via ops/notify-telegram.sh
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath, NOT url.pathname: this repo lives under "Coding Projects" and a URL
// percent-encodes the space, so `.pathname` yields "…/Coding%20Projects/…" — a directory
// that does not exist. Caught on the first real run, when the tool silently found no
// tickets and printed nothing at all.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.AUTODEV_ROOT ?? path.resolve(HERE, "..");
const STATE = path.join(ROOT, ".autodev");
const OUTBOX = path.join(STATE, "outbox");
const LEDGER = path.join(STATE, "events.jsonl");
const SEEN = path.join(STATE, "notify", "gate-ping.jsonl");
const SPAWN_MS = 5000;   // the Stop hook's `|| true` bounds exit status, never runtime

const argv = new Set(process.argv.slice(2));
const DRY = argv.has("--dry-run");
const NO_SEND = argv.has("--no-send");

/** Resolved ONCE, up front, and it throws rather than returning a false all-clear. */
export function findTracker() {
  const tried = [];
  const cands = [];
  if (process.env.AUTODEV_TRACKER) cands.push(process.env.AUTODEV_TRACKER);
  if (process.env.CLAUDE_PLUGIN_ROOT) {
    cands.push(path.join(process.env.CLAUDE_PLUGIN_ROOT, "scripts", "tracker.mjs"));
  }
  const market = path.join(process.env.HOME ?? "/root", ".claude", "plugins", "cache",
                           "autodev-marketplace", "autodev");
  try {
    for (const v of fs.readdirSync(market).sort().reverse()) {
      cands.push(path.join(market, v, "scripts", "tracker.mjs"));
    }
  } catch { /* not installed under this home; the env vars still may point at it */ }
  for (const c of cands) { tried.push(c); if (fs.existsSync(c)) return c; }
  throw new Error(`cannot find tracker.mjs. Set AUTODEV_TRACKER. Tried:\n  ${tried.join("\n  ")}`);
}

function defaultRun(bin, args) {
  return execFileSync("node", [bin, ...args],
    { encoding: "utf8", maxBuffer: 32 << 20, timeout: SPAWN_MS });
}

export function routeOf(id, bin, run = defaultRun) {
  return JSON.parse(run(bin, ["next", id, "--root", ROOT]));
}

/** Gate policies the tracker treats as human (tracker.mjs:893 HUMAN_POLICIES).
 *  Anything unrecognised is ALSO treated as human — see the failure direction above. The
 *  repo's own gates.json names `autonomous | recommend-and-wait | auto-unless-contested`
 *  as future dials, and none of those start with "human". */
const AUTO_POLICIES = new Set(["auto", "none", "off", "disabled", "autonomous"]);
export const isHumanPolicy = (p) => p != null && !AUTO_POLICIES.has(String(p).toLowerCase());

/** Has the PLUGIN already emitted this exact occurrence? Read from the ledger — the real
 *  source of truth — not from a filename convention.
 *
 *  The previous version probed `outbox/sent/<ticket>_<gate>_gate.md`, which was wrong twice
 *  over. notify.mjs keys packets `[ticket, stage, type, at]` (notify.mjs:56), so it never
 *  writes that name; the two files that inspired it are HAND-WRITTEN prose from the manual
 *  seam. And `notify-telegram.sh` moves drained packets to `sent/` and never prunes, so
 *  matching on a name in a permanent archive was a PERMANENT mute: once a gate had been
 *  announced, every later occurrence of it was silently adopted forever. */
export function pluginAlreadyEmitted(ticket, stage, gate, ledger = LEDGER) {
  let txt;
  try { txt = fs.readFileSync(ledger, "utf8"); } catch { return false; }
  for (const line of txt.split("\n")) {
    if (!line.includes("gate_waiting")) continue;
    let e; try { e = JSON.parse(line); } catch { continue; }
    if (e.type === "gate_waiting" && e.ticket === ticket && e.stage === stage && e.gate === gate) {
      return true;
    }
  }
  return false;
}

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
      try { out.add(JSON.parse(line).key); } catch { /* a torn line must not mute the watchdog */ }
    }
  } catch { /* first run */ }
  return out;
}

export function gateSpec(gate, dataDir = path.join(STATE, "data")) {
  try {
    const g = JSON.parse(fs.readFileSync(path.join(dataDir, "gates.json"), "utf8"));
    return g?.gates?.[gate] ?? null;
  } catch { return null; }
}

const isDone = (t, r) =>
  Boolean(t.completed) || t.terminal === true || Boolean(t.closed) ||
  String(t.status ?? "") === "complete" || r?.action?.do === "done";

/** Which tickets are parked at an uncleared human gate right now.
 *  Returns { found, failures } — failures are NEVER folded into silence. */
export function pending({ files = ticketFiles(), bin = null, route = routeOf,
                          seen = seenKeys(), emitted = pluginAlreadyEmitted } = {}) {
  const tracker = bin ?? findTracker();      // throws here, before any ticket is judged
  const found = [];
  const failures = [];
  for (const f of files) {
    let t;
    try { t = JSON.parse(fs.readFileSync(f, "utf8")); }
    catch (e) { failures.push({ file: path.basename(f), why: `unreadable: ${e.message}` }); continue; }
    if (!t?.id) { failures.push({ file: path.basename(f), why: "no ticket id" }); continue; }

    let r;
    try { r = route(t.id, tracker); }
    catch (e) { failures.push({ id: t.id, why: `tracker next failed: ${e.message}` }); continue; }

    if (isDone(t, r)) continue;
    const g = r?.gate;
    if (!g || !g.name) continue;
    if (g.cleared) continue;
    if (!isHumanPolicy(g.policy)) continue;

    // The occurrence is (ticket, stage, gate) — the key the plugin itself uses — so a
    // loopback and re-arrival at a different stage is a NEW occurrence and pings again.
    const key = `${t.id}|${r.stage}|${g.name}`;
    if (seen.has(key)) continue;
    const already = emitted(t.id, r.stage, g.name);
    found.push({
      id: t.id, title: t.title, stage: r.stage, gate: g.name,
      keyholder: g.keyholder ?? gateSpec(g.name)?.keyholder?.seat ?? "unset",
      question: g.question ?? gateSpec(g.name)?.question ?? "",
      instructions: gateSpec(g.name)?.keyholder?.instructions ?? "",
      key, adopted: already,
    });
  }
  return { found, failures };
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

/** Same-directory temp + rename: the drain `cat`s and `mv`s this directory, and two
 *  sessions ending a turn at once could otherwise send a half-written packet. */
function writeAtomic(file, body) {
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, body);
  fs.renameSync(tmp, file);
}

function record(p, how) {
  fs.mkdirSync(path.dirname(SEEN), { recursive: true });
  fs.appendFileSync(SEEN, JSON.stringify({ key: p.key, id: p.id, stage: p.stage,
                                           gate: p.gate, how, ts: new Date().toISOString() }) + "\n");
}

export function run({ write = true, send = true } = {}) {
  const { found, failures } = pending();
  const acted = [];
  for (const p of found) {
    if (p.adopted) {          // the plugin emitted THIS occurrence; its own pager has it
      if (write) record(p, "adopted: plugin emitted this occurrence");
      acted.push({ ...p, action: "adopted" });
      continue;
    }
    if (write) {
      fs.mkdirSync(OUTBOX, { recursive: true });
      writeAtomic(path.join(OUTBOX, `${p.id}_${p.gate}_gate.md`), render(p));
      record(p, "written");
    }
    acted.push({ ...p, action: "written" });
  }
  if (write && send && acted.some((a) => a.action === "written")) {
    try {
      execFileSync(path.join(ROOT, "ops", "notify-telegram.sh"), [],
                   { stdio: "inherit", timeout: SPAWN_MS * 4 });
    } catch (e) {
      // Delivery failure must not lose the packet: notify-telegram.sh leaves anything it
      // could not send in the outbox and retries on the next drain.
      console.error(`gate-ping: delivery failed (${e.message}); packets stay queued`);
    }
  }
  return { acted, failures };
}

const isMain = process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  let acted, failures;
  try {
    ({ acted, failures } = run({ write: !DRY, send: !DRY && !NO_SEND }));
  } catch (e) {
    console.error(`gate-ping: CANNOT READ THE BOARD — ${e.message}`);
    console.error("gate-ping: this is NOT an all-clear. No gate has been checked.");
    process.exit(2);
  }
  if (!acted.length) console.log("gate-ping: nothing parked at an uncleared human gate.");
  for (const a of acted) {
    // --dry-run reports the action it WOULD take, not a blanket "WOULD SEND". It used to
    // print WOULD SEND for every row including adopted ones — which are precisely the rows
    // that would NOT be sent. A mutation exercise caught it: a regression that made
    // adoption ignore the stage (a permanent mute) was invisible in dry-run output because
    // the muted row still read "WOULD SEND".
    const verb = DRY ? (a.action === "adopted" ? "would ADOPT (not send)" : "WOULD SEND")
                     : a.action;
    console.log(`gate-ping: ${a.id} @ ${a.stage} gate ${a.gate} (keyholder ${a.keyholder}) — ${verb}`);
  }
  if (DRY) console.log("gate-ping: --dry-run, nothing written and nothing sent.");
  if (failures.length) {
    console.error(`gate-ping: ${failures.length} ticket(s) COULD NOT BE CHECKED — ` +
                  `the board above is incomplete:`);
    for (const f of failures) console.error(`  ${f.id ?? f.file}: ${f.why}`);
    process.exit(1);
  }
}
