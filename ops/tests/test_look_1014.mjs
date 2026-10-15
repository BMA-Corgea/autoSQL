/**
 * The operator's look, 2026-10-14 (GA-70) — step 3's builder and Clear filters, run as React runs them.
 *
 *  - (A) Clear filters' Undo stays until something new is made: still there after 60 s, gone the moment a card is
 *    added (a-chk's MA1 put the 8-second timer back, MA2 let it outlive a new card; every other test passed);
 *  - (B) a box's word at the start of its add row sets THAT box's join, before its next card (a-chk's MB1 wrote it
 *    to the top box); an empty box shows no word.
 *
 * The components are JSX, so they are bundled for node with the demo's own esbuild first (as test_t98_question.mjs
 * does), and React renders them into the small stand-in for a page below: just what react-dom touches here.
 * No browser, no new package. The timers are node:test's mock timers, so 60 s pass at once.
 * run: node --test ops/tests/test_look_1014.mjs      (or: ops/run-tests.sh)
 */
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// ── a page, as little of one as react-dom needs ──────────────────────────
class Node {
  constructor(doc) { this.ownerDocument = doc; this.parentNode = null; this.childNodes = []; this._on = {}; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get nextSibling() { const s = this.parentNode && this.parentNode.childNodes; return s ? s[s.indexOf(this) + 1] || null : null; }
  appendChild(n) { if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this; this.childNodes.push(n); return n; }
  insertBefore(n, ref) {
    if (!ref) return this.appendChild(n);
    if (n.parentNode) n.parentNode.removeChild(n);
    n.parentNode = this; this.childNodes.splice(this.childNodes.indexOf(ref), 0, n); return n;
  }
  removeChild(n) { this.childNodes.splice(this.childNodes.indexOf(n), 1); n.parentNode = null; return n; }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(t) { this.childNodes = []; if (t !== "") this.appendChild(this.ownerDocument.createTextNode(String(t))); }
  addEventListener(type, fn, opt) { const capture = opt === true || !!(opt && opt.capture); (this._on[type] ||= []).push({ fn, capture }); }
  removeEventListener(type, fn) { this._on[type] = (this._on[type] || []).filter((l) => l.fn !== fn); }
  dispatchEvent(ev) {
    const pathUp = [];
    for (let n = this; n; n = n.parentNode || (n === n.ownerDocument ? null : null)) pathUp.push(n);
    if (this.ownerDocument && !pathUp.includes(this.ownerDocument)) pathUp.push(this.ownerDocument);
    ev.target = this;
    const run = (n, capture) => { ev.currentTarget = n; for (const l of [...(n._on[ev.type] || [])]) if (l.capture === capture) l.fn.call(n, ev); };
    for (const n of [...pathUp].reverse()) { if (ev._stop) break; ev.eventPhase = n === this ? 2 : 1; run(n, true); }
    for (const n of pathUp) { if (ev._stop || (!ev.bubbles && n !== this)) break; ev.eventPhase = n === this ? 2 : 3; run(n, false); }
    return !ev.defaultPrevented;
  }
}
class Text extends Node {
  constructor(doc, t) { super(doc); this.nodeType = 3; this.nodeName = "#text"; this.nodeValue = t; }
  get data() { return this.nodeValue; } set data(t) { this.nodeValue = t; }
  get textContent() { return this.nodeValue; } set textContent(t) { this.nodeValue = t; }
}
class Element extends Node {
  constructor(doc, tag) {
    super(doc); this.nodeType = 1; this.tagName = this.nodeName = tag.toUpperCase();
    this.namespaceURI = "http://www.w3.org/1999/xhtml"; this.attrs = {}; this.style = { setProperty() {}, removeProperty() {} };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  focus() { this.ownerDocument.activeElement = this; }
  blur() { if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body; }
  get options() { return this.all().filter((e) => e.tagName === "OPTION"); }
  get value() { return this._value !== undefined ? this._value : this.tagName === "OPTION" ? (this.attrs.value ?? this.textContent) : ""; }
  set value(v) { this._value = String(v); }
  all() { return this.childNodes.flatMap((c) => (c.nodeType === 1 ? [c, ...c.all()] : [])); }
  // a selector of [attr="value"] parts only, which is all these tests and the builder ask for
  matches(sel) { return [...sel.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)].every(([, k, v]) => (v === undefined ? k in this.attrs : this.attrs[k] === v)); }
  querySelectorAll(sel) { return this.all().filter((e) => e.matches(sel)); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  getBoundingClientRect() { return { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 }; }
}
class Document extends Node {
  constructor() { super(null); this.ownerDocument = this; this.nodeType = 9; this.nodeName = "#document";
    this.documentElement = this.createElement("html"); this.body = this.documentElement.appendChild(this.createElement("body"));
    this.documentElement.parentNode = this; this.activeElement = this.body; }
  createElement(tag) { return new Element(this, tag); }
  createElementNS(_ns, tag) { return new Element(this, tag); }
  createTextNode(t) { return new Text(this, t); }
  createComment(t) { return new Text(this, t); }
}
class Event {
  constructor(type, init = {}) { this.type = type; this.bubbles = !!init.bubbles; this.cancelable = true; this.defaultPrevented = false; this.timeStamp = Date.now(); this.button = 0; }
  preventDefault() { this.defaultPrevented = true; }
  stopPropagation() { this._stop = true; }
}
const document = new Document();
const win = { document, Event, HTMLIFrameElement: class {}, navigator: { userAgent: "node" }, addEventListener() {}, removeEventListener() {} };
globalThis.window = win; globalThis.document = document; // node already has a navigator
globalThis.HTMLIFrameElement = win.HTMLIFrameElement; globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// ── the builder and Clear filters, bundled from the source ───────────────
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FRONT = path.join(REPO, "demo", "frontend");
const SRC = process.env.LOOK_FILTER_MODULE || "./dashboard-filter.jsx"; // a mutant's copy, for the mutation run
const esbuild = (await import(pathToFileURL(path.join(FRONT, "node_modules", "esbuild", "lib", "main.js")))).default;
const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "look-1014-")), "bundle.mjs");
await esbuild.build({
  stdin: { contents: `export { FilterBuilder, ClearFilters } from ${JSON.stringify(SRC)}; export * as T from "./filter-tree.js";`
             + 'export { default as React } from "react"; export { createRoot } from "react-dom/client";',
           resolveDir: FRONT, loader: "js" },
  bundle: true, format: "esm", platform: "node", jsx: "automatic", loader: { ".jsx": "jsx" },
  define: { "process.env.NODE_ENV": '"development"' }, outfile: out, logLevel: "silent",
});
const { FilterBuilder, ClearFilters, T, React, createRoot } = await import(pathToFileURL(out));
fs.rmSync(path.dirname(out), { recursive: true, force: true });
const h = React.createElement;

const STATUS = { path: "status", label: "Status", kind: "text", ops: ["eq", "ne", "in", "present", "blank"], values: ["error", "ok", "warn"] };
const FIELDS = [STATUS];
const card = (value) => ({ _k: T.key(), field: "status", op: "eq", value, value2: "", values: [] });

// Step 3 as the page holds it: the tree in one place, Clear filters and the builder both writing to it.
function mount(start) {
  const seen = { tree: start };
  function Step3() {
    const [tree, setTree] = React.useState(start);
    seen.tree = tree;
    return h("div", null,
      h(ClearFilters, { value: tree, fields: FIELDS, onChange: setTree }),
      h(FilterBuilder, { fields: FIELDS, shown: ["status"], admin: true, value: tree, onChange: setTree,
        opWords: { eq: "is" }, chips: { all: "AND", any: "OR", one: "exactly one of", allnone: "all or none of" },
        logics: { all: "All of these", any: "Any of these", one: "Exactly one of these", allnone: "All of these, or none of them" },
        needsTwo: "needs two or more conditions" }));
  }
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  React.act(() => root.render(h(Step3)));
  const click = (el) => React.act(() => { el.dispatchEvent(new Event("click", { bubbles: true })); });
  const press = (sel) => {
    const el = host.querySelector(sel);
    assert.ok(!!el, `nothing on screen matches ${sel}`);
    click(el);
  };
  return { host, seen, press, click, done: () => React.act(() => root.unmount()) };
}

test("(A) Clear filters' Undo stays until something new is made: still there after 60 s, gone on a new card", () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const start = T.newBox("all", [card("warn"), T.newBox("any", [card("ok"), card("error")])]);
    const s = mount(start);
    s.press('[data-action="clear-filters"]');
    assert.equal(s.seen.tree.items.length, 0, "Clear filters left something in step 3");
    React.act(() => mock.timers.tick(60_000));
    assert.ok(!!s.host.querySelector('[data-action="undo-clear"]'), "the Undo was gone after 60 s, with nothing new made");
    s.press('[data-action="undo-clear"]');
    assert.ok(s.seen.tree === start, "Undo did not put back the very tree that was cleared");
    // cleared again, then something new: a card added in step 3
    s.press('[data-action="clear-filters"]');
    s.press(`[data-action="add-condition"][data-in="${s.seen.tree._k}"]`);
    assert.equal(s.seen.tree.items.length, 1, "the new card was not added");
    assert.ok(!s.host.querySelector('[data-action="undo-clear"]'), "the Undo outlived a new card in step 3");
    s.done();
  } finally {
    mock.timers.reset();
  }
});

test("(B) a box's word at the start of its add row sets that box's join, before its next card", () => {
  const empty = T.newBox("all", []);
  const g = T.newBox("any", [card("warn")]);
  const start = T.newBox("all", [card("ok"), g, empty]);
  const s = mount(start);
  const next = (k) => `[data-join-next="${k}"]`;
  // (every check is a plain yes/no: a failing assert that prints an element would print React's whole tree)
  assert.ok(!s.host.querySelector(next(empty._k)), "an empty group shows a word");
  assert.ok(!!s.host.querySelector(next(g._k)), "a group with one card shows no word before its next card");
  const word = (k) => s.host.querySelector(next(k)).querySelector("[data-join]");
  // the group's own word, tapped once: the group turns to AND, the top box keeps its word
  s.click(word(g._k));
  assert.equal(T.at(s.seen.tree, [1]).join, "all", "the group's word did not change the group");
  assert.equal(s.seen.tree.join, "all", "the group's word changed the top box");
  // the card added next joins the group with the word picked
  s.press(`[data-action="add-condition"][data-in="${g._k}"]`);
  const grp = T.at(s.seen.tree, [1]);
  assert.equal(grp.items.length, 2, "the next card did not land in the group");
  assert.equal(grp.join, "all", "the next card did not join with the word picked before it");
  // ▾ on the group's add row still offers the other words, and they set the same box
  s.click(s.host.querySelector(next(g._k)).querySelector("[aria-haspopup]"));
  s.click(s.host.querySelector(next(g._k)).querySelector('[data-join-pick="one"]'));
  assert.equal(T.at(s.seen.tree, [1]).join, "one", "▾ on the group's add row did not set the group");
  assert.equal(s.seen.tree.join, "all", "▾ on the group's add row changed the top box");
  // the top box's own word sets the top box only
  s.click(word(s.seen.tree._k));
  assert.equal(s.seen.tree.join, "any", "the top box's word did not change the top box");
  assert.equal(T.at(s.seen.tree, [1]).join, "one", "the top box's word changed the group");
  s.done();
});
