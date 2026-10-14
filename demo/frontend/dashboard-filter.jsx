// dashboard-filter.jsx — T-96: the filter builder. Cards joined by AND / OR, groups inside groups to
// any depth, moved by a handle (mouse and touch) or by "Move to…" (keyboard).
//
// One builder: step 3's "Only rows where" and each count column of a scoreboard. It draws the tree
// filter-tree.js holds and reports each change as a new tree; what is sent is that module's
// `sendable`. Every word a person reads here is plain: AND, OR, "exactly one of", "all or none of".

import React from "react";
import { ConditionRow, firstField, freshCondition, isComplete } from "./dashboard-steps.jsx";
import * as T from "./filter-tree.js";

const JOINS = ["all", "any", "one", "allnone"];

//: What each join means, said for a person (the chip's menu).
const MEANING = {
  all: "Every one of these holds.",
  any: "At least one of these holds.",
  one: "Exactly one of these holds; the rest don't.",
  allnone: "All of these hold, or none of them does.",
};

// ── the chip between two items ───────────────────────────────────────────

// An open menu shuts on a press anywhere outside it, or on Escape.
function useShutOutside(open, shut) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return undefined;
    const press = (e) => { if (ref.current && !ref.current.contains(e.target)) shut(); };
    const key = (e) => { if (e.key === "Escape") shut(); };
    document.addEventListener("pointerdown", press);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", press); document.removeEventListener("keydown", key); };
  }, [open]);
  return ref;
}

// `next`: the same chip at the start of the box's add row, read "…AND the next condition" (the operator's look, 2026-10-14:
// "I think of the AND and then I think of what the other condition is").
function JoinChip({ join, chips, onJoin, boxKey, next = false }) {
  const [open, setOpen] = React.useState(false);
  const ref = useShutOutside(open, () => setOpen(false));
  const flip = () => onJoin(join === "all" ? "any" : "all");
  return (
    <div className={"dx-join" + (next ? " is-next" : "")} data-join-of={boxKey} data-join-next={next ? boxKey : undefined} ref={ref}>
      <span className="dx-join-pill">
        <button type="button" className={"dx-join-chip is-" + join} data-join={join} onClick={flip}
          title={MEANING[join]} aria-label={next
            ? `Next condition joins with ${chips[join]}: ${MEANING[join]} Press to switch between AND and OR.`
            : `${chips[join]}: ${MEANING[join]} Tap to switch between AND and OR.`}>
          {chips[join]}
        </button>
        <button type="button" className="dx-join-more" aria-haspopup="menu" aria-expanded={open}
          aria-label="Other ways to join these" onClick={() => setOpen(!open)}>▾</button>
      </span>
      {open ? (
        <div className="dx-menu dx-join-menu" role="menu" aria-label="Join these by">
          {JOINS.map((j) => (
            <button key={j} type="button" role="menuitemradio" aria-checked={j === join} className="dx-menu-item"
              data-join-pick={j} onClick={() => { onJoin(j); setOpen(false); }}>
              <span className="dx-menu-word">{chips[j]}</span>
              <span className="dx-menu-note">{MEANING[j]}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ── a card's and a group's tools: the handle and the menu ────────────────

function Handle({ k, ctx, label }) {
  return (
    <button type="button" className="dx-handle" data-handle={k} aria-label={`Drag ${label}, or press Enter to move it`}
      onPointerDown={(e) => ctx.startDrag(e, k)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ctx.openMenu(k); } }}>
      <span aria-hidden="true">⠿</span>
    </button>
  );
}

function ItemMenu({ k, ctx, isGroup }) {
  const open = ctx.menu === k;
  const dests = open ? T.destinations(ctx.root, k) : [];
  const here = open ? T.at(ctx.root, T.pathOf(ctx.root, k).slice(0, -1))._k : null;
  const ref = useShutOutside(open, () => ctx.openMenu(null));
  return (
    <span className="dx-item-menu" ref={ref}>
      <button type="button" className="dx-more" aria-haspopup="menu" aria-expanded={open} data-menu={k}
        aria-label={isGroup ? "Move or remove this group" : "Move this condition"} onClick={() => ctx.openMenu(open ? null : k)}>⋯</button>
      {open ? (
        <div className="dx-menu" role="menu" aria-label="Move to…">
          <p className="dx-menu-title">Move to…</p>
          {dests.map((d) => (
            <button key={d.key} type="button" role="menuitem" className="dx-menu-item" data-move-to={d.name}
              disabled={d.key === here} onClick={() => { ctx.set(T.move(ctx.root, k, d.key)); ctx.focusHandle(k); ctx.openMenu(null); }}>
              {d.name}{d.key === here ? " (here)" : ""}
            </button>
          ))}
          <button type="button" role="menuitem" className="dx-menu-item" data-move-to="new group"
            onClick={() => { ctx.set(T.wrap(ctx.root, k)); ctx.focusHandle(k); ctx.openMenu(null); }}>A new group, here</button>
          {isGroup ? (
            <button type="button" role="menuitem" className="dx-menu-item is-danger" data-remove-group={k}
              onClick={() => { ctx.set(T.remove(ctx.root, k)); ctx.openMenu(null); }}>Remove this group and what is in it</button>
          ) : null}
        </div>
      ) : null}
    </span>
  );
}

// ── a slot a dragged item can land in ────────────────────────────────────

function Drop({ box, index, ctx }) {
  const over = ctx.drag && ctx.drag.over && ctx.drag.over.box === box && ctx.drag.over.index === index;
  return <div className={"dx-drop" + (over ? " is-over" : "")} data-drop={`${box}:${index}`} aria-hidden="true" />;
}

// ── a card ───────────────────────────────────────────────────────────────

function Card({ c, ctx }) {
  const dragging = ctx.drag && ctx.drag.key === c._k;
  return (
    <div className={"dx-item" + (dragging ? " is-dragging" : "")} data-item={c._k}>
      <ConditionRow fields={ctx.fields} c={c} opWords={ctx.opWords} held={ctx.held.has(c._k)}
        lead={<Handle k={c._k} ctx={ctx} label="this condition" />}
        tools={<ItemMenu k={c._k} ctx={ctx} />}
        onChange={(next) => ctx.set(T.update(ctx.root, c._k, () => ({ ...next, _k: c._k })))}
        onRemove={() => ctx.set(T.remove(ctx.root, c._k))} />
    </div>
  );
}

// ── a box: the root, or a group ──────────────────────────────────────────

//: What a group shut to one line says when it, or a group inside it, is not applied yet.
const SHUT_HELD = {
  above: "Not applied yet — see below.",
  inside: "Part of this group is not applied yet. Open it to see which.",
};

function Box({ node, depth, ctx }) {
  const root = depth === 0;
  const ready = T.boxReady(node, ctx.complete);
  const n = T.countCards(node);
  const dragging = ctx.drag && ctx.drag.key === node._k;
  const cls = "dx-box" + (root ? " is-root" : depth % 2 ? " is-odd" : " is-even")
    + (dragging ? " is-dragging" : "") + (depth > 4 ? " is-deep" : "");
  const set = (patch) => ctx.set(T.update(ctx.root, node._k, (b) => ({ ...b, ...patch })));
  const add = (item) => ctx.set(T.append(ctx.root, node._k, item));
  const head = root ? null : (
    <div className="dx-box-head">
      <Handle k={node._k} ctx={ctx} label="this group" />
      <button type="button" className="dx-box-toggle" aria-expanded={!node.collapsed} data-collapse={node._k}
        onClick={() => set({ collapsed: !node.collapsed })}>
        <span className="dx-box-caret" aria-hidden="true">{node.collapsed ? "▸" : "▾"}</span>
        <span className="dx-box-name">Group{depth > 4 ? ` · level ${depth}` : ""}</span>
        <span className="dx-box-count">{n === 1 ? "1 condition" : `${n} conditions`}</span>
      </button>
      <ItemMenu k={node._k} ctx={ctx} isGroup />
    </div>
  );
  if (!root && node.collapsed) {
    const w = T.treeWords(node, ctx.fields, ctx.opWords, ctx.complete);
    const why = !ready ? <>Not applied yet — “{ctx.logics[node.join]}” {ctx.needsTwo}.</>
      : ctx.held.has(node._k) ? SHUT_HELD.above : T.holdsAny(node, ctx.held) ? SHUT_HELD.inside : null;
    return (
      <div className={cls + " is-collapsed"} data-box={node._k} data-depth={depth}>
        {head}
        <p className="dx-box-summary">{w ? `(${w})` : "Nothing in it yet."}</p>
        {why ? <p className="dx-waiting dx-held" data-testid="held">{why}</p> : null}
      </div>
    );
  }
  return (
    <div className={cls} data-box={node._k} data-depth={depth}>
      {head}
      {node.items.map((it, i) => (
        <React.Fragment key={it._k}>
          <Drop box={node._k} index={i} ctx={ctx} />
          {i > 0 ? <JoinChip join={node.join} chips={ctx.chips} boxKey={node._k} onJoin={(join) => set({ join })} /> : null}
          {T.isBox(it)
            ? <Box node={it} depth={depth + 1} ctx={ctx} />
            : <Card c={it} ctx={ctx} />}
        </React.Fragment>
      ))}
      <Drop box={node._k} index={node.items.length} ctx={ctx} />
      {!ready ? (
        <p className="dx-waiting dx-held" data-testid="held">
          Not applied yet — “{ctx.logics[node.join]}” {ctx.needsTwo}.
        </p>
      ) : null}
      {!root && !node.items.length ? <p className="dx-quiet">Empty: add a condition, or drag one here.</p> : null}
      <div className="dx-box-foot">
        {node.items.length ? (
          <JoinChip join={node.join} chips={ctx.chips} boxKey={node._k} onJoin={(join) => set({ join })} next />
        ) : null}
        {ctx.matchable.length ? (
          <button type="button" className="dx-add" data-action={ctx.action} data-in={node._k}
            onClick={() => add(freshCondition(firstField(ctx.matchable, ctx.shown, ctx.admin)))}>
            + {root ? ctx.addLabel : "Condition"}
          </button>
        ) : null}
        <button type="button" className="dx-add dx-add-group" data-action="add-group" data-in={node._k}
          onClick={() => add(T.newBox(node.join === "any" ? "all" : "any"))}>+ Group</button>
      </div>
    </div>
  );
}

// ── the builder ──────────────────────────────────────────────────────────

export function FilterBuilder({ fields, shown, admin, value, onChange, opWords, chips, logics, needsTwo,
  addLabel = "Add a condition", action = "add-condition" }) {
  const [drag, setDrag] = React.useState(null);
  const [menu, setMenu] = React.useState(null);
  const host = React.useRef(null);
  const complete = (c) => isComplete(c, fields.find((f) => f.path === c.field));
  const matchable = fields.filter((f) => f.ops.length);
  const latest = React.useRef(value);
  latest.current = value;

  // After a move from the menu, the keyboard stays on the moved item: its handle, wherever it is drawn now.
  const focusTo = React.useRef(null);
  const focusHandle = (k) => { focusTo.current = k; };
  React.useEffect(() => {
    if (focusTo.current === null || !host.current) return;
    const el = host.current.querySelector(`[data-handle="${focusTo.current}"]`);
    focusTo.current = null;
    if (el) el.focus();
  });

  // The slot a pointer is nearest: among the slots whose box spans the pointer across, the one
  // closest up or down. A slot inside the item being dragged is never one.
  const nearest = (x, y, key) => {
    let best = null;
    for (const el of host.current ? host.current.querySelectorAll("[data-drop]") : []) {
      const [box, index] = el.dataset.drop.split(":").map(Number);
      if (box === key || T.within(latest.current, key, box)) continue;
      const r = el.getBoundingClientRect();
      if (x < r.left - 4 || x > r.right + 4) continue;
      const d = Math.abs((r.top + r.bottom) / 2 - y);
      if (!best || d < best.d || (d === best.d && r.left > best.left)) best = { box, index, d, left: r.left };
    }
    return best ? { box: best.box, index: best.index } : null;
  };

  const startDrag = (e, key) => {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    const handle = e.currentTarget;
    try { handle.setPointerCapture(e.pointerId); } catch (_) { /* a synthetic event has no capture */ }
    setMenu(null);
    setDrag({ key, over: null });
    const moveTo = (ev) => setDrag({ key, over: nearest(ev.clientX, ev.clientY, key) });
    const stop = (commit) => (ev) => {
      handle.removeEventListener("pointermove", moveTo);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", esc);
      const over = commit ? nearest(ev.clientX, ev.clientY, key) : null;
      setDrag(null);
      if (over) onChange(T.move(latest.current, key, over.box, over.index));
    };
    const up = stop(true);
    const cancel = stop(false);
    const esc = (ev) => { if (ev.key === "Escape") cancel(ev); };
    handle.addEventListener("pointermove", moveTo);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", esc);
  };

  const ctx = {
    root: value, set: onChange, fields, shown, admin, opWords, chips, logics, needsTwo, addLabel, action,
    complete, matchable, drag, startDrag, menu, openMenu: setMenu, held: T.heldKeys(value, complete), focusHandle,
  };
  return (
    <div className={"dx-filter" + (drag ? " is-dragging-any" : "")} ref={host} data-testid="filter">
      <Box node={value} depth={0} ctx={ctx} />
    </div>
  );
}

// ── T-97: Clear filters, with an Undo ────────────────────────────────────
//
// Clear takes out every card and group of step 3 (nothing else on the page). Undo puts back exactly
// what was there — the same tree, so every card, group, join and shut group returns. It has no timer
// (the operator's look, 2026-10-14: "It should only disappear once I make something as a new filter"): it stays while
// the columns, the sort, the clock or the answer change, and goes the moment step 3 changes again (a
// card or group added) — it never overwrites what was done after the clear. It goes too when the
// fields on offer change, and on another data set or view (the page remounts it per data set and
// view): the tree it would put back may name a field that view doesn't have.
// The keyboard follows: Clear puts it on the Undo, and Undo puts it back on Clear filters.

export function ClearFilters({ value, onChange, fields }) {
  const [undo, setUndo] = React.useState(null); // { before, cleared, offered }
  const offered = fields.map((f) => `${f.path}:${f.ops.join(",")}`).join("|");
  React.useEffect(() => { if (undo && undo.offered !== offered) setUndo(null); }, [offered]); // eslint-disable-line react-hooks/exhaustive-deps
  // once step 3 holds anything else, the Undo is gone for good (it never comes back by undoing that)
  React.useEffect(() => { if (undo && value !== undo.cleared) setUndo(null); }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  const live = !!undo && value === undo.cleared && undo.offered === offered;

  const undoBtn = React.useRef(null);
  const clearBtn = React.useRef(null);
  const focusTo = React.useRef(null);
  React.useEffect(() => {
    const el = focusTo.current && focusTo.current.current;
    focusTo.current = null;
    if (el) el.focus();
  });

  const clear = () => {
    const cleared = T.newBox();
    setUndo({ before: value, cleared, offered });
    onChange(cleared);
    focusTo.current = undoBtn;
  };
  return (
    <div className="dx-clear">
      <p className="dx-undo-line" role="status" aria-live="polite">
        {live ? (
          <>
            Filters cleared.{" "}
            <button type="button" className="dx-link" data-action="undo-clear" ref={undoBtn}
              onClick={() => { onChange(undo.before); setUndo(null); focusTo.current = clearBtn; }}>Undo</button>
          </>
        ) : null}
      </p>
      {value.items.length && !live ? (
        <button type="button" className="dx-link dx-clear-btn" data-action="clear-filters" ref={clearBtn} onClick={clear}>
          Clear filters
        </button>
      ) : null}
    </div>
  );
}
