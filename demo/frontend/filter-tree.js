// demo/frontend/filter-tree.js — T-96: the filter as the screen holds it, a tree of boxes (pure functions).
//
// A box is { _k, join, items, collapsed }; a card is a condition { _k, field, op, value, value2, values }.
// `_k` is the screen's own handle (React keys, drag and "Move to…"); it is never sent. What is sent is
// picks/view.py's tree: { version: 1, join, items: [card | { join, items }] } — only the cards that are
// complete, an empty box dropped, and a box whose join needs two ("exactly one of", "all or none of")
// held back until two of its items are live. Every function here returns a new tree; none mutates.

export const FILTER_VERSION = 1;
export const NEEDS_TWO = new Set(["one", "allnone"]);

let nextKey = 1;
export function key() {
  return nextKey++;
}

export function isBox(node) {
  return !!node && Array.isArray(node.items);
}

export function newBox(join = "all", items = []) {
  return { _k: key(), join, items, collapsed: false };
}

// The old flat form, read as a one-box tree (a link or a default view may still carry it).
export function fromFlat(conditions, logic) {
  return newBox(logic || "all", (conditions || []).map((c) => ({ ...c, _k: c._k || key() })));
}

// A tree as sent (no handles) → a tree as held (handles back on every node).
export function fromSent(tree) {
  const walk = (n) => (isBox(n) ? { _k: key(), join: n.join || "all", items: n.items.map(walk), collapsed: false }
    : { ...n, _k: key() });
  return walk(tree && isBox(tree) ? tree : newBox());
}

// How many cards a tree holds (those `keep` says yes to, when given).
export function countCards(node, keep = null) {
  if (isBox(node)) return node.items.reduce((n, it) => n + countCards(it, keep), 0);
  return !keep || keep(node) ? 1 : 0;
}

// How many items of a box are live: complete cards, and boxes that are themselves live.
function live(node, complete) {
  if (!isBox(node)) return complete(node) ? 1 : 0;
  return liveItems(node, complete).length && boxReady(node, complete) ? 1 : 0;
}

function liveItems(box, complete) {
  return box.items.filter((it) => live(it, complete));
}

// Is a box ready for its join? "exactly one of" and "all or none of" need two live items.
export function boxReady(box, complete) {
  return !NEEDS_TWO.has(box.join) || liveItems(box, complete).length >= 2;
}

// What is sent: complete cards only, no handles, empty and held boxes left out.
export function sendable(root, complete) {
  const walk = (box) => {
    const items = [];
    for (const it of box.items) {
      if (isBox(it)) {
        const b = walk(it);
        if (b) items.push(b);
      } else if (complete(it)) {
        const { _k, ...card } = it; // eslint-disable-line no-unused-vars
        items.push(card);
      }
    }
    if (!items.length) return null;
    if (NEEDS_TWO.has(box.join) && items.length < 2) return null;
    return { join: box.join, items };
  };
  const top = walk(root);
  return { version: FILTER_VERSION, join: top ? top.join : "all", items: top ? top.items : [] };
}

// ── finding and moving (paths are lists of item indexes from the root) ──────

export function at(root, path) {
  return path.reduce((n, i) => n.items[i], root);
}

export function pathOf(root, k) {
  const walk = (n, p) => {
    if (n._k === k) return p;
    if (!isBox(n)) return null;
    for (let i = 0; i < n.items.length; i++) {
      const r = walk(n.items[i], [...p, i]);
      if (r) return r;
    }
    return null;
  };
  return walk(root, []);
}

function replaceAt(root, path, fn) {
  if (!path.length) return fn(root);
  const [i, ...rest] = path;
  return { ...root, items: root.items.map((it, j) => (j === i ? replaceAt(it, rest, fn) : it)) };
}

export function update(root, k, fn) {
  const p = pathOf(root, k);
  return p ? replaceAt(root, p, fn) : root;
}

export function remove(root, k) {
  const p = pathOf(root, k);
  if (!p || !p.length) return root;
  return replaceAt(root, p.slice(0, -1), (b) => ({ ...b, items: b.items.filter((_, j) => j !== p[p.length - 1]) }));
}

export function append(root, boxKey, node) {
  return update(root, boxKey, (b) => ({ ...b, items: [...b.items, node] }));
}

// Is `inner` the node `outer` or somewhere inside it? (A box can't be moved into itself.)
export function within(root, outerKey, innerKey) {
  const p = pathOf(root, outerKey);
  return !!p && pathOf(at(root, p), innerKey) !== null;
}

// Move a node into a box, before its item `index` (or at the end). Refused (unchanged) into itself.
export function move(root, k, boxKey, index = null) {
  const to = pathOf(root, boxKey);
  if (k === root._k || !to || !isBox(at(root, to)) || !pathOf(root, k) || within(root, k, boxKey)) return root;
  const node = at(root, pathOf(root, k));
  const from = pathOf(root, k);
  const fromBox = at(root, from.slice(0, -1));
  let i = index === null ? null : index;
  // moving within the same box past its own place: the index shifts by one once it is taken out
  if (i !== null && fromBox._k === boxKey && from[from.length - 1] < i) i -= 1;
  const without = remove(root, k);
  return update(without, boxKey, (b) => {
    const items = [...b.items];
    items.splice(i === null ? items.length : Math.max(0, Math.min(i, items.length)), 0, node);
    return { ...b, items };
  });
}

// Put a node into a new box of its own, where it stands.
export function wrap(root, k, join = "all") {
  const p = pathOf(root, k);
  if (!p || !p.length) return root;
  return replaceAt(root, p, (n) => newBox(join, [n]));
}

// Every box a node could be moved into, by its name on screen: "Top level", "Group 2", "Group 2 › Group 1".
// A box is named by its place among its parent's boxes. The node itself and what is inside it are left out.
export function destinations(root, k) {
  const out = [];
  const walk = (box, name) => {
    if (box._k === k || within(root, k, box._k)) return;
    out.push({ key: box._k, name });
    let n = 0;
    for (const it of box.items) {
      if (isBox(it)) {
        n += 1;
        walk(it, box === root ? `Group ${n}` : `${name} › Group ${n}`);
      }
    }
  };
  walk(root, "Top level");
  return out;
}

// Take out every card naming one of these fields (the Everyone view's hidden fields), at any depth.
export function withoutFields(root, hidden) {
  const walk = (box) => ({ ...box, items: box.items.filter((it) => isBox(it) || !hidden.has(it.field)).map(
    (it) => (isBox(it) ? walk(it) : it)) });
  return walk(root);
}
