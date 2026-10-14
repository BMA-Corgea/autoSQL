/**
 * T-96 S2 — demo/frontend/filter-tree.js: the filter tree as the screen holds it.
 *
 * What is sent (only complete cards; empty and held groups left out; no handles), and the moves a drag
 * or "Move to…" makes (into, out of, between groups; never a group into itself; the same box's own
 * index shift). Pure functions, so they are tested here with no browser; the screen that calls them is
 * driven headless (.autodev/foreman/2026-10-13-filters/dash-check-t96.mjs).
 *
 * run: node --test ops/tests/test_filter_tree.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const T = await import(pathToFileURL(process.env.FILTER_TREE_MODULE || path.join(REPO, "demo/frontend/filter-tree.js")));

const card = (field, value = "x") => ({ _k: T.key(), field, op: "eq", value, value2: "", values: [] });
const blank = (field) => card(field, "");
const complete = (c) => c.value !== "";
const strip = (n) => (T.isBox(n) ? { join: n.join, items: n.items.map(strip) } : (({ _k, ...c }) => c)(n));

test("a whole tree is sent as it stands, without the screen's handles", () => {
  const t = T.newBox("all", [card("ts"), T.newBox("any", [card("status", "warn"), card("status", "error")])]);
  const sent = T.sendable(t, complete);
  assert.deepEqual(sent, { version: 1, ...strip(t) });
  assert.ok(!JSON.stringify(sent).includes("_k"), "a handle was sent");
  assert.ok(!JSON.stringify(sent).includes("collapsed"), "the screen's collapsed state was sent");
});

test("a card waiting for its value, and a group left empty by that, are not sent", () => {
  const t = T.newBox("all", [card("ts"), T.newBox("any", [blank("status")]), T.newBox("any", [])]);
  assert.deepEqual(T.sendable(t, complete), { version: 1, join: "all", items: [strip(card("ts"))].map((c) => ({ ...c })) });
});

test("an 'exactly one of' group with one live item is held back, at any depth, and nothing else is", () => {
  const held = T.newBox("one", [card("a"), blank("b")]);
  const t = T.newBox("all", [card("ts"), T.newBox("any", [card("c"), held])]);
  assert.equal(T.boxReady(held, complete), false);
  const sent = T.sendable(t, complete);
  assert.deepEqual(sent.items[1], { join: "any", items: [strip(card("c"))] });
  // the root itself held: nothing is filtered
  const root = T.newBox("allnone", [card("a")]);
  assert.deepEqual(T.sendable(root, complete), { version: 1, join: "all", items: [] });
});

test("a card moves into a group, out of it, and between groups", () => {
  const c1 = card("a"), c2 = card("b"), g1 = T.newBox("any", []), g2 = T.newBox("all", [card("c")]);
  let t = T.newBox("all", [c1, c2, g1, g2]);
  t = T.move(t, c1._k, g1._k);
  assert.deepEqual(T.at(t, [1]).items.map((x) => x._k), [c1._k], "into a group");
  t = T.move(t, c1._k, g2._k, 0);
  assert.deepEqual(T.at(t, [2]).items[0]._k, c1._k, "between groups, at the place dropped");
  assert.equal(T.at(t, [1]).items.length, 0, "taken out of where it was");
  t = T.move(t, c1._k, t._k, 0);
  assert.equal(t.items[0]._k, c1._k, "out to the top level");
  assert.equal(T.countCards(t), 3);
});

test("moving down within the same box lands where it was dropped", () => {
  const a = card("a"), b = card("b"), c = card("c");
  const t = T.move(T.newBox("all", [a, b, c]), a._k, null ?? undefined, 2);
  assert.deepEqual(t.items.map((x) => x.field), ["a", "b", "c"], "an unknown box changes nothing");
  const root = T.newBox("all", [a, b, c]);
  const moved = T.move(root, a._k, root._k, 2);
  assert.deepEqual(moved.items.map((x) => x.field), ["b", "a", "c"], "dropped before c, after b");
});

test("a group can't be moved into itself or into a group inside it", () => {
  const inner = T.newBox("any", [card("b")]);
  const outer = T.newBox("all", [card("a"), inner]);
  const t = T.newBox("all", [outer, card("c")]);
  assert.equal(T.move(t, outer._k, inner._k), t, "into its own child");
  assert.equal(T.move(t, outer._k, outer._k), t, "into itself");
  const names = T.destinations(t, outer._k).map((d) => d.name);
  assert.deepEqual(names, ["Top level"], "its own groups are offered as places to go");
});

test("Move to… names every other group by its place", () => {
  const c = card("x");
  const g11 = T.newBox("any", []);
  const g1 = T.newBox("all", [card("a"), g11]);
  const g2 = T.newBox("any", [card("b")]);
  const t = T.newBox("all", [c, g1, g2]);
  assert.deepEqual(T.destinations(t, c._k).map((d) => d.name), ["Top level", "Group 1", "Group 1 › Group 1", "Group 2"]);
});

test("a card can be wrapped in a new group where it stands", () => {
  const a = card("a"), b = card("b");
  const t = T.wrap(T.newBox("all", [a, b]), b._k, "any");
  assert.ok(T.isBox(t.items[1]) && t.items[1].join === "any" && t.items[1].items[0]._k === b._k);
});

test("the Everyone view's hidden fields are taken out at any depth", () => {
  const t = T.newBox("all", [card("label"), T.newBox("any", [card("status"), T.newBox("all", [card("label")])])]);
  const kept = T.withoutFields(t, new Set(["label"]));
  assert.equal(T.countCards(kept), 1);
  assert.ok(!JSON.stringify(kept).includes('"label"'));
});

test("the old flat form and a sent tree are read back with handles on every node", () => {
  const flat = T.fromFlat([{ field: "a", op: "eq", value: "x", value2: "", values: [] }], "any");
  assert.equal(flat.join, "any");
  assert.ok(flat.items[0]._k);
  const back = T.fromSent({ version: 1, join: "all", items: [{ join: "one", items: [{ field: "a" }, { field: "b" }] }] });
  assert.ok(back._k && back.items[0]._k && back.items[0].items[1]._k);
  assert.equal(back.items[0].join, "one");
});
