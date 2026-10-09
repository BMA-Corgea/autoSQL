// dashboard-matched.jsx — step 2's "Columns from another data set" (T-78).
//
// A plain table can show another data set's fields beside each row: pick the
// data set, which of its fields equals which field of this one, then tick its
// fields to show. The server checks every choice (demo/server/dashboard.py ::
// to_lookup), both engines answer, and a pick where one row would match two
// rows is refused there, with its numbers; this file draws the choices.
//
// The match as the page holds it: {dataset, field, matches, columns}, any
// part still empty while it is being picked. It is sent only once it is whole
// and at least one field is ticked; until then the table shows its own
// columns, and the step says what is missing.

import React from "react";
import { matchPairs } from "./dashboard-scoreboard.jsx";
import { offered } from "./dashboard-steps.jsx";

const EMPTY = { dataset: null, field: null, matches: null, columns: [] };

// The match a table opens on: a declared relation read the other way (each
// heartbeat's sender, each sender's site), when this viewer may use it; else
// nothing picked yet — never a pair filled in for him (T-79).
export function openingMatched(setup, ds, admin) {
  for (const x of ds.lookups || []) {
    const other = setup.datasets.find((d) => d.id === x.id);
    if (other && matchPairs(setup, ds, other, admin).some((p) => p.field.path === x.field && p.matches.path === x.matches)) {
      return { dataset: x.id, field: x.field, matches: x.matches, columns: [] };
    }
  }
  return { ...EMPTY };
}

// What is sent: the match when it is whole and shows at least one field,
// with only the fields this viewer may see; else nothing.
export function sendableMatched(setup, ds, m, admin) {
  if (!m || !m.dataset || !m.field || !m.matches) return null;
  const other = setup.datasets.find((d) => d.id === m.dataset);
  if (!other) return null;
  const seen = new Set(offered(other.fields, admin).map((f) => f.path));
  const columns = m.columns.filter((p) => seen.has(p));
  return columns.length ? { dataset: m.dataset, field: m.field, matches: m.matches, columns } : null;
}

// What the step says while the match is not yet a question.
function waiting(ds, m) {
  if (!m.dataset) return "Pick the data set to take fields from.";
  if (!m.field || !m.matches) return `Pick which of their fields equals which of this ${ds.one}'s.`;
  if (!m.columns.length) return "Tick the fields of theirs to show.";
  return null;
}

export function MatchedColumns({ setup, ds, admin, value, onChange, match, off }) {
  const others = setup.datasets.filter((d) => d.id !== ds.id);
  const can = others.some((d) => matchPairs(setup, ds, d, admin).length);
  if (!value) {
    if (!can) return null;
    return (
      <button type="button" className="dx-add dx-matched-add" data-action="add-matched"
        onClick={() => onChange(openingMatched(setup, ds, admin))}>
        + Columns from another data set
      </button>
    );
  }
  const m = value;
  const other = setup.datasets.find((d) => d.id === m.dataset);
  const pairs = other ? matchPairs(setup, ds, other, admin) : [];
  const theirs = pairs.map((p) => p.field).filter((f, i, all) => all.findIndex((g) => g.path === f.path) === i);
  const mine = pairs.filter((p) => p.field.path === m.field).map((p) => p.matches);
  const shown = other ? offered(other.fields, admin) : [];
  const on = new Set(m.columns);
  const hold = off ? null : waiting(ds, m);
  return (
    <div className={"dx-count dx-matched" + (hold ? " is-waiting" : "")} data-testid="matched">
      <div className="dx-count-top">
        <span className="dx-matched-title">Columns from another data set</span>
        <button type="button" className="dx-remove" aria-label="Remove the columns from another data set"
          onClick={() => onChange(null)}>×</button>
      </div>
      <div className="dx-row">
        <label className="dx-label" htmlFor="dx-mt-set">From</label>
        <select id="dx-mt-set" className="dx-select" value={m.dataset || ""}
          onChange={(e) => { if (e.target.value) onChange({ ...EMPTY, dataset: e.target.value }); }}>
          {m.dataset ? null : <option value="">Pick a data set…</option>}
          {others.map((d) => {
            const none = !matchPairs(setup, ds, d, admin).length;
            return <option key={d.id} value={d.id} disabled={none}>{d.name}{none ? " (no field to match)" : ""}</option>;
          })}
        </select>
      </div>
      {other ? (
        <div className="dx-row">
          <label className="dx-label" htmlFor="dx-mt-field">Their</label>
          <select id="dx-mt-field" className="dx-select" value={m.field || ""}
            onChange={(e) => {
              const f = e.target.value;
              if (!f) return;
              // Keep this data set's field if it still pairs; else he picks it.
              const still = pairs.some((p) => p.field.path === f && p.matches.path === m.matches);
              onChange({ ...m, field: f, matches: still ? m.matches : null });
            }}>
            {m.field ? null : <option value="">Pick a field…</option>}
            {theirs.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
          </select>
        </div>
      ) : null}
      {other && m.field ? (
        <div className="dx-row">
          <label className="dx-label" htmlFor="dx-mt-matches">Equals its</label>
          <select id="dx-mt-matches" className="dx-select" value={m.matches || ""}
            onChange={(e) => { if (e.target.value) onChange({ ...m, matches: e.target.value }); }}>
            {m.matches ? null : <option value="">Pick a field…</option>}
            {mine.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
          </select>
        </div>
      ) : null}
      {other ? (
        <>
          <p className="dx-count-says">Show their:</p>
          <div className="dx-checks">
            {shown.map((f) => (
              <label key={f.path} className={"dx-check" + (on.has(f.path) ? " is-on" : "")}>
                <input type="checkbox" checked={on.has(f.path)} data-matched-column={f.path}
                  onChange={() => onChange({ ...m, columns: on.has(f.path)
                    ? m.columns.filter((p) => p !== f.path)
                    : shown.map((x) => x.path).filter((p) => p === f.path || on.has(p)) })} />
                <span>{f.label}</span>
              </label>
            ))}
          </div>
        </>
      ) : null}
      {hold ? <p className="dx-waiting" data-testid="matched-waiting">{hold} Until then, the table shows its own columns.</p> : null}
      {!hold && match && match.preview ? (
        <p className="dx-step-hint dx-preview" data-testid="matched-preview">{match.preview}</p>
      ) : null}
    </div>
  );
}
