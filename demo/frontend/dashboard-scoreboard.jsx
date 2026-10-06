// dashboard-scoreboard.jsx — step 6, "One row per…" (T-73): the scoreboard.
//
// One row per value of a field, and beside it counts of the rows where a
// set of conditions holds — the "if it's true then add 1" columns. Each
// count column has a name the person types (it appears only in the answer),
// its own conditions, and how they join: All, Any, Exactly one, All or none.
// The server checks every choice (demo/server/dashboard.py :: to_spec) and
// both engines compute the answer; this file draws the choices.

import React from "react";
import { ConditionList, Segmented, Step, isComplete, logicReady } from "./dashboard-steps.jsx";

let nextKey = 1;

// A new count column, named "Count N" with N one past the highest "Count N"
// on screen — so the names stay in order down the list, and never collide
// (T-75: removing "Count 1" and adding read "Count 2, Count 3, Count 1").
export function freshCount(existing) {
  let n = existing.length;
  for (const c of existing) {
    const m = /^count (\d+)$/i.exec(c.label.trim());
    if (m) n = Math.max(n, Number(m[1]));
  }
  return { _k: nextKey++, label: `Count ${n + 1}`, logic: "all", conditions: [], pct: false };
}

// Is a count column ready to send? A name, at least one condition with a
// value, and enough conditions for its logic. One that isn't is kept on
// screen, marked, and not sent — it is not a question yet.
// The fields a scoreboard's counts read: the data set's own, or — when it
// counts from a declared related data set (T-74: a sender's Heartbeats) —
// that data set's.
export function countedFields(setup, ds, sb) {
  if (sb && sb.count_from) {
    const rel = setup.datasets.find((d) => d.id === sb.count_from);
    if (rel) return rel.fields;
  }
  return ds.fields;
}

export function countWaiting(c, fields) {
  const done = c.conditions.filter((x) => isComplete(x, fields.find((f) => f.path === x.field))).length;
  if (!c.label.trim()) return "Not counted until it has a name.";
  if (done === 0) return "Not counted until a condition has a value.";
  if (!logicReady(c.logic, done)) return "Not counted until two conditions have values.";
  return null;
}

function CountCard({ c, n, fields, shown, admin, opWords, logics, needsTwo, labelMax, onChange, onRemove, what, whose }) {
  const waiting = countWaiting(c, fields);
  return (
    <div className={"dx-count" + (waiting ? " is-waiting" : "")} data-count={n - 1}>
      <div className="dx-count-top">
        <input className="dx-input dx-count-name" type="text" value={c.label} maxLength={labelMax}
          aria-label={`Count column ${n}: name`} placeholder="Name this column"
          onChange={(e) => onChange({ ...c, label: e.target.value })} />
        <button type="button" className="dx-remove" aria-label="Remove this count column" onClick={onRemove}>×</button>
      </div>
      <p className="dx-count-says">Counts the {what} in each group where:</p>
      <ConditionList fields={fields} shown={shown} admin={admin} value={c.conditions} opWords={opWords}
        onChange={(conditions) => onChange(conditions.length < 2 ? { ...c, conditions, logic: "all" } : { ...c, conditions })}
        logic={c.logic} onLogic={(logic) => onChange({ ...c, logic })}
        logics={logics} needsTwo={needsTwo} addLabel="Add a condition" action="add-count-condition" />
      <label className="dx-check-line">
        <input type="checkbox" checked={c.pct} onChange={() => onChange({ ...c, pct: !c.pct })} data-pct={n - 1} />
        <span>Also show it as a % of {whose}</span>
      </label>
      {waiting ? <p className="dx-waiting">{waiting}</p> : null}
    </div>
  );
}

function groupedReasons(fields) {
  const by = new Map();
  for (const f of fields) by.set(f.group.why, [...(by.get(f.group.why) || []), f.label]);
  return [...by.entries()];
}

export function ScoreboardStep({ ds, fields, value, shown, admin, setup, onChange }) {
  const groupable = fields.filter((f) => f.group.ok);
  const notGroupable = fields.filter((f) => !f.group.ok);
  const sb = value;
  // What the counts read: the parent's own rows, or its related rows.
  const counted = countedFields(setup, ds, sb);
  const rel = sb && sb.count_from ? (ds.count_from || []).find((r) => r.id === sb.count_from) : null;
  const times = counted.filter((f) => f.kind === "time" || f.kind === "date");
  const numbers = counted.filter((f) => f.kind === "number");
  const set = (patch) => onChange({ scoreboard: { ...sb, ...patch } });
  const counts = sb ? sb.counts : [];
  return (
    <Step n={6} title="One row per…">
      <div className="dx-row">
        <label className="dx-label" htmlFor="dx-sb-by">Group</label>
        <select id="dx-sb-by" className="dx-select" value={sb ? sb.by : ""}
          onChange={(e) => onChange(e.target.value
            ? { scoreboard: { ...(sb || { counts: [], time: null, measure: null, sort: null }), by: e.target.value, sort: null } }
            : { scoreboard: null })}>
          <option value="">Off — no scoreboard</option>
          {fields.filter((f) => admin || !f.hidden_by_default || (sb && sb.by === f.path)).map((f) => (
            <option key={f.path} value={f.path} disabled={!f.group.ok}>
              {f.group.ok ? f.label : `${f.label} (can't)`}
            </option>
          ))}
        </select>
      </div>
      {sb ? null : (
        <p className="dx-step-hint">A scoreboard gives one row per value — per Sender, per Status — with counts beside it.</p>
      )}
      {sb ? (
        <>
          {(ds.count_from || []).length ? (
            <div className="dx-stack dx-count-from">
              <span className="dx-label">Count</span>
              <Segmented
                label="Count"
                value={sb.count_from || null}
                options={[[null, "Its own rows"], ...ds.count_from.map((r) => [r.id, `Their ${r.name}`])]}
                // The count columns read different fields once this changes,
                // so they, the time and the measure start afresh.
                onChange={(v) => set({ count_from: v, counts: [], time: null, measure: null, sort: null })}
              />
            </div>
          ) : null}
          {rel ? (
            <p className="dx-step-hint" data-testid="count-from-hint">
              Each row is one {ds.one}: it shows how many {rel.name} that {ds.one} has (0 when none), and the
              count columns look at that {ds.one}'s {rel.name}.
            </p>
          ) : (
            <p className="dx-step-hint">
              Each row shows how many {ds.name.toLowerCase()} the group holds, then your count columns.
            </p>
          )}
          {counts.map((c, i) => (
            <CountCard key={c._k} c={c} n={i + 1} fields={counted} shown={rel ? [] : shown} admin={admin}
              what={rel ? rel.name : "rows"} whose={rel ? `the ${ds.one}'s ${rel.name}` : "the group's rows"}
              opWords={setup.op_labels} logics={setup.logics} needsTwo={setup.logic_needs_two}
              labelMax={setup.label_max}
              onChange={(next) => set({ counts: counts.map((x, j) => (j === i ? next : x)) })}
              onRemove={() => set({ counts: counts.filter((_, j) => j !== i), sort: null })} />
          ))}
          {counts.length < setup.max_counts ? (
            <button type="button" className="dx-add" data-action="add-count"
              onClick={() => set({ counts: [...counts, freshCount(counts)] })}>
              + Add a count column
            </button>
          ) : <p className="dx-step-hint">{setup.max_counts} count columns is the most a scoreboard holds.</p>}
          {times.length ? (
            <div className="dx-row dx-row-gap">
              <label className="dx-label" htmlFor="dx-sb-time">Also</label>
              <select id="dx-sb-time" className="dx-select"
                value={sb.time ? `${sb.time.fn}:${sb.time.field}` : ""}
                onChange={(e) => {
                  const [fn, field] = e.target.value.split(":");
                  set({ time: e.target.value ? { fn, field } : null, sort: null });
                }}>
                <option value="">No time column</option>
                {times.flatMap((f) => [
                  <option key={`l${f.path}`} value={`latest:${f.path}`}>Latest {f.label}</option>,
                  <option key={`e${f.path}`} value={`earliest:${f.path}`}>Earliest {f.label}</option>,
                ])}
              </select>
            </div>
          ) : null}
          {numbers.length ? (
            <div className="dx-row dx-row-gap">
              <label className="dx-label" htmlFor="dx-sb-measure">And</label>
              <select id="dx-sb-measure" className="dx-select"
                value={sb.measure ? `${sb.measure.fn}:${sb.measure.field}` : ""}
                onChange={(e) => {
                  const [fn, field] = e.target.value.split(":");
                  set({ measure: e.target.value ? { fn, field } : null, sort: null });
                }}>
                <option value="">No total or average</option>
                {numbers.flatMap((f) => ["sum", "avg", "min", "max"].map((fn) => (
                  <option key={fn + f.path} value={`${fn}:${f.path}`}>{setup.summary_fns[fn]} {f.label}</option>
                )))}
              </select>
            </div>
          ) : null}
        </>
      ) : null}
      {groupable.length === 0 ? <p className="dx-step-hint">No field here can be grouped by.</p> : null}
      {notGroupable.length ? (
        <details className="dx-why-more">
          <summary>Why some fields can't be grouped by</summary>
          {groupedReasons(notGroupable).map(([why, names]) => (
            <p key={why} className="dx-step-hint">{names.join(", ")}: {why}</p>
          ))}
        </details>
      ) : null}
    </Step>
  );
}

// The scoreboard's own sort control is its column headers: tap one to sort
// by it, tap again to turn it round.
export function nextSort(current, columnId) {
  if (current && current.column === columnId) {
    return { column: columnId, dir: current.dir === "asc" ? "desc" : "asc" };
  }
  return { column: columnId, dir: columnId === "group" ? "asc" : "desc" };
}

