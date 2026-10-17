/**
 * T-85 — a shut group's words: one pair of brackets, never "((…))".
 *
 * A shut group holding exactly one nested group of two cards read "((Status is warn or Status is error))" (run 8,
 * a-chk's look-1014 LOW): the nested group's own brackets inside the shut summary's. A group with one part is now
 * that part, so only the summary's brackets remain; a part among others is still bracketed.
 * run: node --test ops/tests/test_t85_words.mjs      (or: ops/run-tests.sh)
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
const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "t85-words-")), "bundle.mjs");
await esbuild.build({
  stdin: { contents: 'export { treeWords, key } from "./filter-tree.js";', resolveDir: FRONT, loader: "js" },
  bundle: true, format: "esm", platform: "node", outfile: out, logLevel: "silent",
});
const M = await import(pathToFileURL(out));
fs.rmSync(path.dirname(out), { recursive: true, force: true });

const STATUS = { path: "status", label: "Status", kind: "text", ops: ["eq", "ne"] };
const ops = { eq: "is", ne: "is not" };
const done = () => true;
const card = (v) => ({ _k: M.key(), field: "status", op: "eq", value: v, value2: "", values: [] });
const box = (join, ...items) => ({ _k: M.key(), join, items, collapsed: true });
const words = (node) => M.treeWords(node, [STATUS], ops, done);

test("a shut group holding one nested group of two cards reads with one pair of brackets", () => {
  const shut = box("all", box("any", card("warn"), card("error")));
  assert.equal(words(shut), "Status is warn or Status is error");   // the summary adds its own one pair
  assert.equal(`(${words(shut)})`, "(Status is warn or Status is error)");
});

test("one group inside one group inside one group: still the one pair", () => {
  assert.equal(words(box("all", box("all", box("any", card("warn"), card("error"))))), "Status is warn or Status is error");
});

test("a nested group beside another part is still bracketed", () => {
  const shut = box("all", card("ok"), box("any", card("warn"), card("error")));
  assert.equal(words(shut), "Status is ok and (Status is warn or Status is error)");
});
