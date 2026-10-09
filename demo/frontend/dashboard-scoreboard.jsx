// dashboard-scoreboard.jsx — step 6, "One row per…" (T-73): the scoreboard.
//
// One row per value of a field, and beside it counts of the rows where a
// set of conditions holds — the "if it's true then add 1" columns. Each
// count column has a name the person types (it appears only in the answer),
// its own conditions, and how they join: All, Any, Exactly one, All or none.
// The server checks every choice (demo/server/dashboard.py :: to_spec) and
// both engines compute the answer; this file draws the choices.

import React from "react";
import { ConditionList, Segmented, Step, isComplete, logicReady, offered } from "./dashboard-steps.jsx";

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
// A match, as the page holds and sends it (T-76): count the rows of
// `dataset` whose `field` equals this row's `matches`. T-74's string form
// (a declared relation, by name) is read as the match it declares.
// A match being picked may be partial (a data set chosen, its fields not
// yet): it is held on screen and not sent, as a waiting condition is.
export function asMatch(ds, countFrom) {
  if (!countFrom) return null;
  if (typeof countFrom !== "string") return whole(countFrom) ? countFrom : null;
  const r = (ds.count_from || []).find((x) => x.id === countFrom);
  return r ? declaredMatch(r) : null;
}
const whole = (m) => !!m && !!m.dataset && !!m.field && !!m.matches;
const declaredMatch = (r) => ({ dataset: r.id, field: r.field, matches: r.matches });
const sameMatch = (a, b) => !!a && !!b && a.dataset === b.dataset && a.field === b.field && a.matches === b.matches;

// The data set a scoreboard counts the rows of, when it is another one.
export function countedSet(setup, sb) {
  const cf = sb && sb.count_from;
  const id = cf && (typeof cf === "string" ? cf : whole(cf) ? cf.dataset : null);
  return id ? setup.datasets.find((d) => d.id === id) || null : null;
}

// The fields a scoreboard's counts read: the data set's own, or — when it
// counts another data set's rows (T-74's declared Heartbeats; any match
// since T-76) — that data set's.
export function countedFields(setup, ds, sb) {
  const rel = countedSet(setup, sb);
  return rel ? rel.fields : ds.fields;
}

// The pairs a person may match between this data set and another: one field
// of each, of the same kind (text with text, number with number, date with
// date), both offered to this viewer — Edge cases' Label never for Everyone.
function matchPairs(setup, ds, other, admin) {
  const can = (fields) => offered(fields, admin).filter((f) => setup.match_kinds.includes(f.kind));
  const mine = can(ds.fields);
  return can(other.fields).flatMap((t) => mine.filter((m) => m.kind === t.kind).map((m) => ({ field: t, matches: m })));
}

// The match a chosen data set opens on: its declared one where there is
// one (Sites → Senders, Site = Name); else no fields picked yet — never a
// first pair that may match nothing (S17 check: Heartbeats, Sender = Name,
// an all-zero board as his first sight).
function openingMatch(setup, ds, other, admin) {
  const r = (ds.count_from || []).find((x) => x.id === other.id);
  const pairs = matchPairs(setup, ds, other, admin);
  if (r && pairs.some((p) => p.field.path === r.field && p.matches.path === r.matches)) return declaredMatch(r);
  return { dataset: other.id, field: null, matches: null };
}

// Step 6's match: which data set, and which field of it equals which field
// of this one. Only pairs of one kind are offered; a data set with none is
// shown, greyed, with the reason.
function MatchPicker({ setup, ds, admin, value, onChange }) {
  const v = value || { dataset: null, field: null, matches: null };
  const others = setup.datasets.filter((d) => d.id !== ds.id);
  const other = setup.datasets.find((d) => d.id === v.dataset);
  const pairs = other ? matchPairs(setup, ds, other, admin) : [];
  const theirs = pairs.map((p) => p.field).filter((f, i, all) => all.findIndex((g) => g.path === f.path) === i);
  const mine = pairs.filter((p) => p.field.path === v.field).map((p) => p.matches);
  return (
    <div className="dx-match" data-testid="match-picker">
      <div className="dx-row">
        <label className="dx-label" htmlFor="dx-match-set">From</label>
        <select id="dx-match-set" className="dx-select" value={v.dataset || ""}
          onChange={(e) => {
            const next = setup.datasets.find((d) => d.id === e.target.value);
            if (next) onChange(openingMatch(setup, ds, next, admin));
          }}>
          {v.dataset ? null : <option value="">Pick a data set…</option>}
          {others.map((d) => {
            const none = !matchPairs(setup, ds, d, admin).length;
            return <option key={d.id} value={d.id} disabled={none}>{d.name}{none ? " (no field to match)" : ""}</option>;
          })}
        </select>
      </div>
      {other ? (
        <div className="dx-row">
          <label className="dx-label" htmlFor="dx-match-field">Their</label>
          <select id="dx-match-field" className="dx-select" value={v.field || ""}
            onChange={(e) => {
              const f = e.target.value;
              if (!f) return;
              // Keep this data set's field if it still pairs; else leave it
              // to him to pick, even when only one field can pair: nothing is
              // counted on a match he hasn't chosen (T-79).
              const can = pairs.filter((p) => p.field.path === f).map((p) => p.matches.path);
              const matches = can.includes(v.matches) ? v.matches : null;
              onChange({ ...v, field: f, matches });
            }}>
            {v.field ? null : <option value="">Pick a field…</option>}
            {theirs.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
          </select>
        </div>
      ) : null}
      {other && v.field ? (
        <div className="dx-row">
          <label className="dx-label" htmlFor="dx-match-matches">Equals its</label>
          <select id="dx-match-matches" className="dx-select" value={v.matches || ""}
            onChange={(e) => { if (e.target.value) onChange({ ...v, matches: e.target.value }); }}>
            {v.matches ? null : <option value="">Pick a field…</option>}
            {mine.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
          </select>
        </div>
      ) : null}
    </div>
  );
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

export function ScoreboardStep({ ds, fields, value, shown, admin, setup, onChange, match }) {
  const groupable = fields.filter((f) => f.group.ok);
  const notGroupable = fields.filter((f) => !f.group.ok);
  const sb = value;
  // What the counts read: the parent's own rows, or its related rows.
  const counted = offered(countedFields(setup, ds, sb), admin);
  const rel = countedSet(setup, sb);
  const cf = sb ? asMatch(ds, sb.count_from) : null;          // whole, or null
  const draft = sb && sb.count_from && typeof sb.count_from !== "string" ? sb.count_from : cf;
  // The switch reads the declared chip ("Their Heartbeats") while the match
  // is the declared one and the person hasn't asked to choose another.
  const chip = cf && !sb.picking ? (ds.count_from || []).find((r) => sameMatch(declaredMatch(r), cf)) : null;
  const canOther = setup.datasets.some((d) => d.id !== ds.id && matchPairs(setup, ds, d, admin).length);
  // A new counted data set means new fields to count by: the count columns,
  // the time and the measure start afresh. The same data set keeps them.
  const pickMatch = (next, picking) => {
    const after = asMatch(ds, next);
    return set((rel ? rel.id : null) === (after ? after.dataset : null)
      ? { count_from: next, picking }
      : { count_from: next, picking, counts: [], time: null, measure: null, sort: null });
  };
  const times = counted.filter((f) => f.kind === "time" || f.kind === "date");
  const numbers = counted.filter((f) => f.kind === "number");
  const set = (patch) => onChange({ scoreboard: { ...sb, ...patch } });
  const counts = sb ? sb.counts : [];
  // The off-state hint's example is this data set's own: its first two
  // fields to group by, leaving out one with a value per row (Senders' own
  // Sender and Name), so it never names a field the data set lacks (T-77).
  const example = groupable.filter((f) => f.group.groups < ds.rows).slice(0, 2);
  return (
    <Step n={6} title="One row per…">
      <div className="dx-row">
        <label className="dx-label" htmlFor="dx-sb-by">Group</label>
        <select id="dx-sb-by" className="dx-select" value={sb ? sb.by : ""}
          onChange={(e) => onChange(e.target.value
            ? { scoreboard: { ...(sb || { counts: [], time: null, measure: null, sort: null }), by: e.target.value, sort: null } }
            : { scoreboard: null })}>
          <option value="">Off — no scoreboard</option>
          {fields.map((f) => (
            <option key={f.path} value={f.path} disabled={!f.group.ok}>
              {f.group.ok ? f.label : `${f.label} (can't)`}
            </option>
          ))}
        </select>
      </div>
      {sb ? null : (
        <p className="dx-step-hint" data-testid="board-hint">
          A scoreboard gives one row per value{example.length ? ` — ${example.map((f) => `per ${f.label}`).join(", ")} —` : ""} with
          counts beside it.
        </p>
      )}
      {sb ? (
        <>
          {(ds.count_from || []).length || canOther ? (
            <div className="dx-stack dx-count-from">
              <span className="dx-label">Count</span>
              <Segmented
                label="Count"
                value={chip ? chip.id : cf || sb.picking ? "other" : null}
                options={[[null, "Its own rows"], ...(ds.count_from || []).map((r) => [r.id, `Their ${r.name}`]),
                  ...(canOther ? [["other", "Another data set…"]] : [])]}
                onChange={(v) => {
                  if (v === null) return pickMatch(null, false);
                  if (v === "other") {
                    if (cf) return set({ picking: true });
                    // Its declared match where it has one; else nothing yet.
                    const r = (ds.count_from || [])[0];
                    return pickMatch(r ? declaredMatch(r) : null, true);
                  }
                  return pickMatch(declaredMatch(ds.count_from.find((r) => r.id === v)), false);
                }}
              />
            </div>
          ) : null}
          {(cf || sb.picking) && !chip ? (
            <MatchPicker setup={setup} ds={ds} admin={admin} value={draft} onChange={(next) => pickMatch(next, true)} />
          ) : null}
          {sb.picking && !cf ? (
            <p className="dx-step-hint" data-testid="match-prompt">
              {draft && draft.dataset ? `Pick which of their fields equals which of this ${ds.one}'s.`
                : "Pick the data set to count rows from."} Until then, each row counts its own rows.
            </p>
          ) : null}
          {rel && chip ? (
            <p className="dx-step-hint" data-testid="count-from-hint">
              Each row is one {ds.one}: it shows how many {rel.name} that {ds.one} has (0 when none), and the
              count columns look at that {ds.one}'s {rel.name}.
            </p>
          ) : rel ? (
            <p className="dx-step-hint" data-testid="count-from-hint">
              Each row shows how many {rel.name.toLowerCase()} match it (0 when none), and the count columns look
              at those {rel.name.toLowerCase()}.
            </p>
          ) : (
            <p className="dx-step-hint">
              Each row shows how many {ds.name.toLowerCase()} the group holds, then your count columns.
            </p>
          )}
          {rel && match && match.preview ? (
            <p className="dx-step-hint dx-preview" data-testid="match-preview">{match.preview}</p>
          ) : null}
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

