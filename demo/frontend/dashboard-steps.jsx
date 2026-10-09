// dashboard-steps.jsx — the left panel: "Your question", in numbered steps.
//
// Every choice here is a click. Nothing a person does on this page is typed
// in any language: the server's contract (demo/server/dashboard.py) turns
// the clicks into the statement. This file draws the choices the contract
// offers and reports which one was clicked. It decides nothing.

import React from "react";

export function Step({ n, title, hint, children }) {
  return (
    <section className="dx-step" aria-labelledby={`dx-step-${n}`}>
      <h3 className="dx-step-title" id={`dx-step-${n}`}>
        <span className="dx-step-n" aria-hidden="true">{n}</span>
        {title}
      </h3>
      {hint ? <p className="dx-step-hint">{hint}</p> : null}
      {children}
    </section>
  );
}

export function DatasetStep({ datasets, value, onPick }) {
  return (
    <Step n={1} title="Data set">
      <div className="dx-cards" role="radiogroup" aria-label="Data set">
        {datasets.map((d) => (
          <button
            key={d.id}
            type="button"
            role="radio"
            aria-checked={d.id === value}
            className={"dx-card" + (d.id === value ? " is-on" : "")}
            data-dataset={d.id}
            onClick={() => onPick(d.id)}
          >
            <span className="dx-card-head">
              <span className="dx-card-name">{d.name}</span>
              <span className="dx-card-count">{d.rows.toLocaleString("en-US")}</span>
            </span>
            <span className="dx-card-about">{d.about}</span>
          </button>
        ))}
      </div>
    </Step>
  );
}

export function ColumnsStep({ fields, value, onChange, why, children }) {
  const on = new Set(value);
  const toggle = (path) => {
    // Keep the data set's own field order, whatever order they were clicked in.
    const next = on.has(path) ? value.filter((p) => p !== path) : fields.map((f) => f.path).filter((p) => p === path || on.has(p));
    onChange(next);
  };
  return (
    <Step n={2} title="Columns" hint={why || null}>
      <fieldset className="dx-fieldset" disabled={!!why}>
      <div className="dx-quick">
        <button type="button" className="dx-link" onClick={() => onChange(fields.map((f) => f.path))}>All</button>
        <button type="button" className="dx-link" onClick={() => onChange([])}>None</button>
      </div>
      <div className="dx-checks">
        {fields.map((f) => (
          <label key={f.path} className={"dx-check" + (on.has(f.path) ? " is-on" : "")}>
            <input
              type="checkbox"
              checked={on.has(f.path)}
              onChange={() => toggle(f.path)}
              data-column={f.path}
            />
            <span>{f.label}</span>
          </label>
        ))}
      </div>
      {children}
      </fieldset>
    </Step>
  );
}

// The fields a viewer may pick, in every step: Everyone never sees a field
// the data set hides from it (Edge cases' Label, whose values are engineer
// text); Admin sees every field (T-77).
export function offered(fields, admin) {
  return admin ? fields : fields.filter((f) => !f.hidden_by_default);
}

// ── 3 · Only rows where ─────────────────────────────────────────────────

const NO_VALUE = new Set(["present", "blank", "yes", "no"]);

// Is this condition ready to ask about? One still waiting for its value is
// kept on screen, marked, and not sent: it is not a question yet.
export function isComplete(c, field) {
  if (!field || !field.ops.includes(c.op)) return false;
  if (NO_VALUE.has(c.op)) return true;
  const has = (v) => v !== undefined && v !== null && v !== "" && !(typeof v === "number" && !Number.isFinite(v));
  if (c.op === "in") return Array.isArray(c.values) && c.values.length > 0;
  if (c.op === "between") return has(c.value) && has(c.value2);
  return has(c.value);
}

let nextKey = 1;

export function freshCondition(field) {
  // _k is the screen's own handle on the row (so removing one row never
  // hands its neighbour's half-typed value to another); it is not sent.
  return { _k: nextKey++, field: field.path, op: field.ops[0], value: "", value2: "", values: [] };
}

function toMinute(text) {
  // the data's "2026-08-14T00:00:00Z" → an input's "2026-08-14T00:00"
  return text ? text.slice(0, 16) : undefined;
}

function Chips({ options, selected, multi, onChange, label }) {
  return (
    <div className="dx-chips" role={multi ? "group" : "radiogroup"} aria-label={label}>
      {options.map((v) => {
        const on = selected.includes(v);
        return (
          <button
            key={v}
            type="button"
            role={multi ? "checkbox" : "radio"}
            aria-checked={on}
            className={"dx-chip" + (on ? " is-on" : "")}
            data-value={v}
            onClick={() => onChange(multi ? (on ? selected.filter((x) => x !== v) : [...selected, v]) : (on ? [] : [v]))}
          >
            {v}
          </button>
        );
      })}
    </div>
  );
}

const LIST_SHOWN = 40;

function SearchList({ options, selected, multi, onChange, label }) {
  const [q, setQ] = React.useState("");
  const needle = q.trim().toLowerCase();
  const matches = options.filter((v) => !selected.includes(v) && (!needle || v.toLowerCase().includes(needle)));
  const shown = matches.slice(0, LIST_SHOWN);
  const full = !multi && selected.length > 0;
  return (
    <div className="dx-search">
      {selected.length > 0 ? (
        <div className="dx-chips">
          {selected.map((v) => (
            <button key={v} type="button" className="dx-chip is-on" aria-label={`Remove ${v}`} onClick={() => onChange(selected.filter((x) => x !== v))}>
              {v} <span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      ) : null}
      {full ? null : (
        <>
          <input
            className="dx-input"
            type="search"
            placeholder={`Search ${options.length.toLocaleString("en-US")} values`}
            aria-label={label}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="dx-options" role="listbox" aria-label={label}>
            {shown.map((v) => (
              <button key={v} type="button" role="option" aria-selected="false" className="dx-option" data-value={v}
                onClick={() => { onChange(multi ? [...selected, v] : [v]); setQ(""); }}>
                {v}
              </button>
            ))}
            {matches.length > shown.length ? (
              <p className="dx-options-more">and {(matches.length - shown.length).toLocaleString("en-US")} more — keep typing to narrow it</p>
            ) : null}
            {matches.length === 0 ? <p className="dx-options-more">Nothing matches.</p> : null}
          </div>
        </>
      )}
    </div>
  );
}

function NumberInput({ value, onChange, field, label }) {
  // Keeps what was typed, so "1." or "-" can be on the way to a number.
  const [text, setText] = React.useState(value === "" || value === undefined ? "" : String(value));
  const range = field.range;
  return (
    <input
      className="dx-input dx-input-num"
      type="number"
      inputMode="decimal"
      step="any"
      aria-label={label}
      placeholder={range ? `${range.min} to ${range.max}` : "a number"}
      value={text}
      onChange={(e) => {
        const t = e.target.value;
        setText(t);
        const n = t.trim() === "" ? "" : Number(t);
        onChange(n === "" || Number.isFinite(n) ? n : "");
      }}
    />
  );
}

function WhenInput({ field, op, value, onChange, label }) {
  const dayOnly = field.kind === "date" || op === "on";
  const range = field.range || {};
  if (dayOnly) {
    return (
      <input className="dx-input" type="date" aria-label={label} value={value || ""}
        min={range.min ? range.min.slice(0, 10) : undefined} max={range.max ? range.max.slice(0, 10) : undefined}
        onChange={(e) => onChange(e.target.value)} />
    );
  }
  return (
    <span className="dx-when">
      <input className="dx-input" type="datetime-local" aria-label={label} value={value || ""}
        min={toMinute(range.min)} max={toMinute(range.max)} step={60}
        onChange={(e) => onChange(e.target.value)} />
      <span className="dx-unit">UTC</span>
    </span>
  );
}

function ValueControl({ field, c, set }) {
  const label = `${field.label} value`;
  if (NO_VALUE.has(c.op)) return null;
  if (field.kind === "text") {
    const multi = c.op === "in";
    const selected = multi ? c.values : (c.value ? [c.value] : []);
    const onChange = (vals) => set(multi ? { values: vals } : { value: vals[0] || "" });
    const Picker = field.picker === "chips" ? Chips : SearchList;
    return <Picker options={field.values || []} selected={selected} multi={multi} onChange={onChange} label={label} />;
  }
  const one = (key, lbl) =>
    field.kind === "number"
      ? <NumberInput key={key} field={field} value={c[key]} label={lbl} onChange={(v) => set({ [key]: v })} />
      : <WhenInput key={key} field={field} op={c.op} value={c[key]} label={lbl} onChange={(v) => set({ [key]: v })} />;
  if (c.op === "between") {
    return (
      <div className="dx-between">
        {one("value", `${field.label} from`)}
        <span className="dx-and">and</span>
        {one("value2", `${field.label} to`)}
      </div>
    );
  }
  return one("value", label);
}

function ConditionRow({ fields, c, opWords, onChange, onRemove, index, held }) {
  const field = fields.find((f) => f.path === c.field);
  const set = (patch) => onChange({ ...c, ...patch });
  // "held": complete, but not applied, because the set's logic is not ready
  // yet — drawn waiting like an empty row, so nothing looks live that isn't.
  const ready = isComplete(c, field) && !held;
  return (
    <div className={"dx-cond" + (ready ? "" : " is-waiting")} data-condition={index}>
      <div className="dx-cond-top">
        <select className="dx-select" aria-label="Field" value={c.field}
          onChange={(e) => onChange({ ...freshCondition(fields.find((f) => f.path === e.target.value)), _k: c._k })}>
          {fields.map((f) => (
            <option key={f.path} value={f.path} disabled={!f.ops.length}>
              {f.ops.length ? f.label : `${f.label} (can't be matched)`}
            </option>
          ))}
        </select>
        <select className="dx-select" aria-label="Condition" value={c.op}
          onChange={(e) => set({ op: e.target.value, value: "", value2: "", values: c.op === "eq" && e.target.value === "in" && c.value ? [c.value] : [] })}>
          {field.ops.map((op) => <option key={op} value={op}>{opWords[op]}</option>)}
        </select>
        <button type="button" className="dx-remove" aria-label="Remove this condition" onClick={onRemove}>×</button>
      </div>
      <ValueControl key={c.field + ":" + c.op} field={field} c={c} set={set} />
      {ready ? null : <p className="dx-waiting">{held ? "Not applied yet — see below." : "Not used until a value is picked."}</p>}
    </div>
  );
}

// The fields that take no condition, grouped by their own reason.
function groupedWhy(fields) {
  const by = new Map();
  for (const f of fields) by.set(f.why_no_ops, [...(by.get(f.why_no_ops) || []), f.label]);
  return [...by.entries()];
}

// The field a new condition opens on: the first column on screen that can
// be matched, else the first matchable field the Everyone view doesn't hide
// (Edge cases' Label, whose values are engineer text), else any.
function firstField(matchable, shown, admin) {
  const byPath = new Map(matchable.map((f) => [f.path, f]));
  for (const p of shown || []) if (byPath.has(p)) return byPath.get(p);
  return matchable.find((f) => admin || !f.hidden_by_default) || matchable[0];
}

// How a set of conditions joins: All / Any / Exactly one / All or none, with
// what each means said plainly for the number of conditions in play.
export function logicMeaning(logic, k) {
  if (logic === "any") return "At least one of these holds.";
  if (logic === "one") return k === 2 ? "One holds and the other doesn't." : "Exactly one of these holds; the rest don't.";
  if (logic === "allnone") return k === 2 ? "Both hold, or neither does." : "All of these hold, or none of them does.";
  return "Every one of these holds.";
}

// Is a set of conditions ready to send with its logic? "Exactly one" and
// "All or none" need two conditions with values.
export function logicReady(logic, completeCount) {
  return !(logic === "one" || logic === "allnone") || completeCount >= 2;
}

export function LogicChooser({ logic, onLogic, logics, count, complete, needsTwo, label }) {
  const value = logic || "all";
  const ready = logicReady(value, complete);
  return (
    <div className="dx-logic">
      <Segmented
        grid
        label={label}
        value={value}
        options={[["all", "All"], ["any", "Any"], ["one", "Exactly one"], ["allnone", "All or none"]]}
        onChange={onLogic}
      />
      <p className="dx-step-hint dx-logic-meaning" title={logics[value]}>{logicMeaning(value, count)}</p>
      {ready ? null : (
        <p className="dx-waiting dx-held" data-testid="held">
          None of these conditions apply until two of them have a value — “{logics[value]}” {needsTwo}.
        </p>
      )}
    </div>
  );
}

// A list of condition rows with its own "+ Add" — the page's "Only rows
// where", and each count column of a scoreboard, use the same one.
export function ConditionList({ fields, shown, admin, value, opWords, onChange, logic, onLogic, logics, needsTwo, addLabel, action }) {
  const matchable = fields.filter((f) => f.ops.length);
  const complete = value.filter((c) => isComplete(c, fields.find((f) => f.path === c.field))).length;
  const held = !logicReady(logic || "all", complete);
  return (
    <>
      {value.map((c, i) => (
        <ConditionRow
          key={c._k}
          index={i}
          held={held}
          fields={fields}
          c={c}
          opWords={opWords}
          onChange={(next) => onChange(value.map((x, j) => (j === i ? next : x)))}
          onRemove={() => onChange(value.filter((_, j) => j !== i))}
        />
      ))}
      {value.length > 1 ? (
        <LogicChooser logic={logic} onLogic={onLogic} logics={logics} count={value.length}
          complete={complete} needsTwo={needsTwo} label={`${addLabel}: how they join`} />
      ) : null}
      {matchable.length ? (
        <button type="button" className="dx-add" data-action={action}
          onClick={() => onChange([...value, freshCondition(firstField(matchable, shown, admin))])}>
          + {addLabel}
        </button>
      ) : null}
    </>
  );
}

export function ConditionsStep({ fields, shown, admin, value, opWords, onChange, logic, onLogic, logics, needsTwo, scoreboardOn }) {
  const unmatchable = fields.filter((f) => !f.ops.length);
  return (
    <Step n={3} title="Only rows where">
      {value.length === 0 ? <p className="dx-quiet">Every row, for now.</p> : null}
      <ConditionList fields={fields} shown={shown} admin={admin} value={value} opWords={opWords}
        onChange={onChange} logic={logic} onLogic={onLogic} logics={logics} needsTwo={needsTwo}
        addLabel="Add a condition" action="add-condition" />
      {scoreboardOn && scoreboardOn.rel ? (
        <p className="dx-step-hint dx-teach" data-testid="before-grouping">
          These keep or drop whole {scoreboardOn.many}. To count only some of a {scoreboardOn.one}'s{" "}
          {scoreboardOn.rel}, add a count column.
        </p>
      ) : scoreboardOn ? (
        <p className="dx-step-hint dx-teach" data-testid="before-grouping">
          This removes rows before grouping. To count rows instead, add a count column.
        </p>
      ) : null}
      {groupedWhy(unmatchable).map(([why, names]) => (
        <p key={why} className="dx-step-hint dx-why">
          {names.length > 3 ? `${names.length} fields (${names[0]} … ${names[names.length - 1]})` : names.join(", ")} can't be matched: {why.charAt(0).toLowerCase() + why.slice(1)}
        </p>
      ))}
    </Step>
  );
}

// ── 4 · Sort and how many ───────────────────────────────────────────────

const FIRST_DIR = { time: "desc", date: "desc", number: "desc", text: "asc", yesno: "desc" };

export function Segmented({ options, value, onChange, label, disabled, disabledValues = [], grid }) {
  return (
    <div className={"dx-seg" + (grid ? " is-grid" : "")} role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={String(v)} type="button" role="radio" aria-checked={v === value} disabled={disabled || disabledValues.includes(v)}
          className={"dx-seg-btn" + (v === value ? " is-on" : "")} data-choice={String(v)} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

export function SortShowStep({ fields, sort, show, showChoices, sortWords, onChange, off = {} }) {
  const sortable = fields.filter((f) => sortWords[f.kind]);
  const field = sort ? fields.find((f) => f.path === sort.field) : null;
  return (
    <Step n={4} title="Sort and show">
      <div className="dx-row">
        <label className="dx-label" htmlFor="dx-sort-field">Sort by</label>
        <select id="dx-sort-field" className="dx-select" value={sort ? sort.field : ""} disabled={!!off.sort}
          onChange={(e) => {
            const f = fields.find((x) => x.path === e.target.value);
            onChange({ sort: f ? { field: f.path, dir: FIRST_DIR[f.kind] } : null });
          }}>
          <option value="">Stored order</option>
          {sortable.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
        </select>
      </div>
      {field ? (
        <Segmented
          label="Direction"
          value={sort.dir}
          options={[["desc", sortWords[field.kind].desc], ["asc", sortWords[field.kind].asc]].sort((a, b) => (a[0] === FIRST_DIR[field.kind] ? -1 : b[0] === FIRST_DIR[field.kind] ? 1 : 0))}
          onChange={(dir) => onChange({ sort: { ...sort, dir } })}
          disabled={!!off.sort}
        />
      ) : null}
      {off.sort ? <p className="dx-step-hint dx-why">{off.sort}</p> : null}
      <div className="dx-row dx-row-gap">
        <span className="dx-label">Show rows</span>
        <Segmented
          label="How many rows"
          value={show}
          options={showChoices.map((n) => [n, n === null ? "All" : String(n)])}
          onChange={(n) => onChange({ show: n })}
          disabled={!!off.show}
        />
      </div>
      {off.show ? <p className="dx-step-hint dx-why">{off.show}</p> : null}
    </Step>
  );
}

// ── 5 · Summarize ───────────────────────────────────────────────────────

// Which kind of answer a view asks for: rows, one number, or one number per
// hour or day. The setup's `unavailable` table is keyed by it.
export function answerShape(view) {
  if (!view.summary) return "rows";
  return view.summary.per === "all" ? "number" : "per";
}

export function SummaryStep({ name, fields, summary, fns, off, onChange }) {
  const numeric = fields.filter((f) => f.kind === "number");
  // Total, Average, Smallest and Largest each read a number field: with none
  // to read they are shown disabled, with the reason, never a dead end.
  const needNumbers = numeric.length ? [] : Object.keys(fns).filter((k) => k !== "count");
  const fn = summary ? summary.fn : null;
  const set = (patch) => onChange({ summary: { ...summary, ...patch } });
  const pick = (next) => {
    if (next === null) return onChange({ summary: null });
    const base = summary || { per: "all" };
    const field = next === "count" ? null : (base.field || (numeric[0] && numeric[0].path) || null);
    onChange({ summary: { fn: next, field, per: base.per || "all" } });
  };
  const perWhy = off.per; // the same for every shape on a data set without times
  return (
    <Step n={5} title="Summarize">
      <Segmented
        grid
        label="Summarize"
        value={fn}
        options={[[null, "Off"], ...Object.entries(fns).map(([k, v]) => [k, k === "count" ? "Count" : v])]}
        onChange={(next) => (needNumbers.includes(next) ? null : pick(next))}
        disabledValues={needNumbers}
      />
      {needNumbers.length ? (
        <p className="dx-step-hint dx-why" data-testid="summary-why">
          {name} has no field that holds numbers, so there is nothing to total, average or find the
          smallest or largest of. Count works.
        </p>
      ) : null}
      {fn && fn !== "count" ? (
        <div className="dx-row dx-row-gap">
          <label className="dx-label" htmlFor="dx-summary-field">Of</label>
          <select id="dx-summary-field" className="dx-select" value={summary.field || ""}
            onChange={(e) => set({ field: e.target.value })}>
            {numeric.map((f) => <option key={f.path} value={f.path}>{f.label}</option>)}
          </select>
        </div>
      ) : null}
      {fn ? (
        <div className="dx-stack">
          <span className="dx-label">Over</span>
          <Segmented
            grid
            label="Over"
            value={summary.per}
            options={[["all", "Everything"], ["hour", "Per hour"], ["day", "Per day"]]}
            onChange={(per) => (per !== "all" && perWhy ? null : set({ per }))}
            disabledValues={perWhy ? ["hour", "day"] : []}
          />
        </div>
      ) : null}
      {fn && perWhy ? <p className="dx-step-hint dx-why">{perWhy}</p> : null}
    </Step>
  );
}
