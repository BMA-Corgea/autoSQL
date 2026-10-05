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

export function ColumnsStep({ fields, value, onChange }) {
  const on = new Set(value);
  const toggle = (path) => {
    // Keep the data set's own field order, whatever order they were clicked in.
    const next = on.has(path) ? value.filter((p) => p !== path) : fields.map((f) => f.path).filter((p) => p === path || on.has(p));
    onChange(next);
  };
  return (
    <Step n={2} title="Columns">
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
    </Step>
  );
}
