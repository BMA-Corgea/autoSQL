/**
 * T-98 (c) — what the screen sends and shows about the question's clock, held with no browser.
 *
 *  - the question carries the zone of the clock setting (a-chk's W1 took it out and every other test passed);
 *  - a computer whose browser names its zone the old way (Asia/Calcutta) reads on that place's clock, and the
 *    zone sent is the current name;
 *  - when the list of zones can't be had, the page still answers: on this computer's clock when it names one,
 *    else on UTC, and says so in one line;
 *  - a group shut to one line words a time-of-day card as the sentence does ("from 5:00 PM", never "17:00").
 *
 * The modules are JSX, so they are bundled for node with the demo's own esbuild first.
 * run: node --test ops/tests/test_t98_question.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FRONT = path.join(REPO, "demo", "frontend");
const esbuild = (await import(pathToFileURL(path.join(FRONT, "node_modules", "esbuild", "lib", "main.js")))).default;
const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "t98-question-")), "bundle.mjs");
await esbuild.build({
  stdin: { contents: 'export { sendable, offFor } from "./question.js"; export * from "./dashboard-clock.jsx"; '
             + 'export { treeWords, key } from "./filter-tree.js";',
           resolveDir: FRONT, loader: "js" },
  bundle: true, format: "esm", platform: "node", jsx: "automatic", loader: { ".jsx": "jsx" },
  outfile: out, logLevel: "silent",
});
const M = await import(pathToFileURL(out));
fs.rmSync(path.dirname(out), { recursive: true, force: true });

const TS = { path: "ts", label: "Time", kind: "time", ops: ["on", "after", "before", "between", "present", "blank"] };
const STATUS = { path: "status", label: "Status", kind: "text", ops: ["eq", "ne", "in", "present", "blank"] };
const SETUP = { datasets: [{ id: "heartbeats", fields: [TS, STATUS], lookups: [], count_from: [] }], unavailable: { heartbeats: {} } };
const view = (items) => ({ dataset: "heartbeats", columns: ["ts"], sort: null, show: null, summary: null,
  filter: { _k: 1, join: "all", items, collapsed: false } });

test("the question carries the clock setting's zone", () => {
  const sent = M.sendable(SETUP, view([{ _k: 2, field: "ts", op: "on", value: "2026-08-20", value2: "", values: [] }]), true, "America/Denver");
  assert.equal(sent.zone, "America/Denver");
  assert.equal(M.sendable(SETUP, view([]), true, "UTC").zone, "UTC");
});

test("a time-of-day card is sent whole, with its part", () => {
  const card = { _k: 3, field: "ts", part: "time_of_day", op: "from", value: "17:00", value2: "", values: [] };
  const sent = M.sendable(SETUP, view([card]), true, "America/Denver");
  assert.deepEqual(sent.filter.items, [{ field: "ts", part: "time_of_day", op: "from", value: "17:00", value2: "", values: [] }]);
});

const LIST = {
  zones: [{ zone: "UTC", label: "UTC", place: "UTC", area: "", why: null },
          { zone: "Asia/Kolkata", label: "Kolkata time", place: "Kolkata", area: "Asia", why: null },
          { zone: "America/Denver", label: "Denver time", place: "Denver", area: "America", why: null }],
  aliases: { "Asia/Calcutta": "Asia/Kolkata" }, others: [],
};

test("a browser that names its zone the old way reads on that place's clock, sent by its current name", () => {
  const c = M.resolveClock(LIST, null, "Asia/Calcutta");
  assert.equal(c.entry.zone, "Asia/Kolkata");
  assert.equal(c.entry.label, "Kolkata time");
  assert.equal(c.note, null);
});

test("when the list of zones can't be had, the page answers on this computer's clock, and says so", () => {
  const c = M.resolveClock(M.LIST_FAILED, null, "America/Denver");
  assert.equal(c.ready, true);
  assert.equal(c.entry.zone, "America/Denver");
  assert.equal(c.entry.label, "Denver time");
  assert.equal(c.note, "The list of time zones didn't load, so times are on this computer's clock (Denver time).");
});

test("...and on UTC when the computer names no zone", () => {
  const c = M.resolveClock(M.LIST_FAILED, null, "");
  assert.equal(c.ready, true);
  assert.equal(c.entry.zone, "UTC");
  assert.equal(c.note, "The list of time zones didn't load, so times are in UTC.");
});

test("a shut group words a time-of-day card as the sentence does", () => {
  const ops = { on: "is on", eq: "is" };
  const done = () => true;
  const card = (op, value, value2 = "") => ({ _k: M.key(), field: "ts", part: "time_of_day", op, value, value2, values: [] });
  const box = (...items) => ({ _k: M.key(), join: "all", items, collapsed: true });
  assert.equal(M.treeWords(box(card("from", "17:00")), [TS], ops, done), "Time (time of day) from 5:00 PM");
  assert.equal(M.treeWords(box(card("until", "17:00:15")), [TS], ops, done), "Time (time of day) until 5:00:15 PM");
  assert.equal(M.treeWords(box(card("between", "22:00", "02:00")), [TS], ops, done),
    "Time (time of day) between 10:00 PM and 2:00 AM");
  assert.equal(M.treeWords(box(card("from", "00:00")), [TS], ops, done), "Time (time of day) from 12:00 AM");
});
