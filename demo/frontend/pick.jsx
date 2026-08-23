// demo/frontend/pick.jsx — the nine operations, as nine real controls.
//
// B22 POINT 2: THIS FILE INVENTS NO CONTROL. Every operation's label,
// shape, closed option set, range, enabled state, .ctl-fixed note and
// .op-why reason arrives from GET /api/operations, which is computed by
// demo/legality.py — the same one function the pick handler refuses
// against. The screen and the server therefore cannot disagree about
// what is legal, because there is only one of them deciding.
//
// What IS drawn here rather than served: each operation's ICON and its
// .ctl-hint prose. Both are drawing, not policy — the mock's own, kept
// verbatim.
//
// DR-2 / D15: a control that can be illegal shows itself illegal, with
// the reason beside it, and never silently. The rules are LIVE: changing
// the source re-derives the contract, so a reader can watch three
// controls go unavailable rather than take a drawing's word for it.
//
// B32 — the picking column is left AS DRAWN: every .ctl-hint stays in
// place and nothing moves behind a `?`.
//   ONE LINE TO OVERTURN: "put the hints behind a ?" — each .ctl-hint
//   becomes a popover; the column is measured at 1,949–2,236px today.

import { Ic } from "./icons.jsx";

//: The mock's own icons and hints, in the mock's own words.
const DRAWN = {
  1: {
    icon: "noun",
    hint: (
      <>A <b>closed set</b> of three, sent as a bind parameter. Choosing one
      re-reads that collection’s top-level field names — which fill every picker
      below.</>
    ),
  },
  2: {
    icon: "sparkle",
    hint: (
      <>Right of the <span className="mono">=</span>, every value and field name goes
      down as a bind parameter. <b>The name left of it is the one thing that reaches
      SQL text</b>, so it is checked against §4.10’s allowlist before it is emitted.</>
    ),
  },
  3: {
    icon: "filter",
    hint: <>One filter, one expression, through the same static gate the computed
      columns use.</>,
  },
  4: {
    icon: "sort",
    hint: (
      <>Nulls last, <b>ties broken by <span className="mono">key</span> ascending even
      when the sort is descending</b> (§7.4).</>
    ),
  },
  5: {
    icon: "cap",
    hint: (
      <>Applied <b>after</b> the sort. Range-checked as a positive integer no greater
      than <span className="mono">20,000</span>; anything else is refused before a
      query is built.</>
    ),
  },
  6: { icon: "sigma", hint: null },
  7: {
    icon: "clock",
    hint: (
      <><b>The session time zone decides where a day starts</b>, which is why the SQL
      pane prints it: it is the difference between seven buckets and eight.</>
    ),
  },
  8: {
    icon: "wave",
    hint: (
      <>Per sender, ordered by <span className="mono">ts</span> then{" "}
      <span className="mono">key</span>. First beat divides by 1, second by 2 — never
      by a phantom 3.</>
    ),
  },
  9: {
    icon: "pulse",
    hint: <>Each sender’s first beat has no predecessor and is always kept.</>,
  },
};

const OP_STATE = { on: "on", off: "not set", refused: "refused", disabled: "unavailable" };

function isOn(pick, n) {
  switch (n) {
    case 1: return true;
    case 2: return (pick.computed || []).some((c) => c && (c.name || c.expr));
    case 3: return !!(pick.filter || "").trim();
    case 4: return !!(pick.sort && pick.sort.field);
    case 5: return pick.cap != null && pick.cap !== "";
    case 6: return ((pick.aggregate || {}).fn || "none") !== "none";
    case 7: return (pick.bucket || "off") !== "off";
    case 8: return !!(pick.window && pick.window.field);
    case 9: return !!pick.changed;
    default: return false;
  }
}

function Select({ ctl, value, onChange, disabled, focus, options }) {
  return (
    <span className="sel-wrap">
      <select className={"select" + (focus ? " is-focus" : "")}
              value={value == null ? "" : value}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <Ic name="caret" className="caret" />
    </span>
  );
}

function Field({ label, children, cls }) {
  return (
    <label className={"field " + (cls || "")}>
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function Fixed({ text }) {
  return (
    <p className="ctl-fixed">
      <Ic name="lock" />
      <span>{text}</span>
    </p>
  );
}

/** The vocabulary a later operation can pick from: the collection's own
 *  field paths (read from the data at operation 1), plus every computed
 *  column already named in this pick. */
function fieldOptions(vocab, pick, numericOnly, invalidName) {
  const names = (numericOnly ? vocab.numeric_fields : vocab.fields) || [];
  const paths = names.map((f) => ({ value: "$." + f, label: "$." + f }));
  const aliases = (pick.computed || [])
    .filter((c) => c && c.name && c.name !== invalidName)
    .map((c) => ({ value: c.name, label: c.name + "   (computed)" }));
  return [{ value: "", label: "— none —" }].concat(paths, aliases);
}

export function PickPanel({ contract, vocab, pick, answer, onChange, onCommit, onRun, dirty, busy }) {
  const ops = (contract && contract.operations) || [];
  const ref = answer && answer.refusal && answer.refusal.layer === 1 ? answer.refusal : null;

  // Which operation the refusal belongs to, and which input inside it.
  let refusedOp = 0;
  let badName = null;
  let badExpr = null;
  if (ref) {
    if (ref.kind === "alias") {
      refusedOp = 2;
      badName = ref.construct;
    } else {
      const c = ref.construct || "";
      if ((pick.filter || "").indexOf(c) >= 0) refusedOp = 3;
      else {
        const hit = (pick.computed || []).find((x) => x && (x.expr || "").indexOf(c) >= 0);
        refusedOp = 2;
        badExpr = hit ? hit.expr : null;
      }
    }
  }

  const set = (patch) => onChange(Object.assign({}, pick, patch));
  const commit = (patch) => onCommit(Object.assign({}, pick, patch));

  const control = (op, name) => (op.controls || []).find((c) => c.name === name) || {};
  const optsOf = (c) => (c.options || []).map((o) => ({ value: o.value, label: o.label }));

  function body(op, disabled) {
    switch (op.n) {
      case 1:
        return (
          <>
            <div className="ctl-row">
              <Field label="Collection" cls="ctl-grow">
                <Select value={pick.source} disabled={disabled}
                        options={optsOf(control(op, "source"))}
                        onChange={(v) => commit({
                          source: v,
                          // §4.10: a new collection is a new vocabulary, so
                          // anything picked out of the old one is dropped.
                          sort: null, aggregate: { fn: (pick.aggregate || {}).fn || "none", field: null },
                          window: null,
                        })} />
              </Field>
            </div>
            <p className="ctl-hint">{DRAWN[1].hint}</p>
          </>
        );

      case 2: {
        const cc = pick.computed || [];
        return (
          <>
            {cc.map((c, j) => (
              <div className="ctl-row" key={j}>
                <Field label="Name" cls="ctl-grow">
                  <input
                    className={"input mono-in" +
                      (badName != null && c.name === badName ? " is-invalid is-focus" : "")}
                    type="text" value={c.name || ""} placeholder="alive"
                    disabled={disabled}
                    aria-invalid={badName != null && c.name === badName ? "true" : undefined}
                    onChange={(e) => {
                      const next = cc.slice();
                      next[j] = Object.assign({}, c, { name: e.target.value });
                      set({ computed: next });
                    }}
                    onBlur={() => onCommit(pick)} />
                </Field>
                <span className="ctl-eq">=</span>
                <Field label="Expression" cls="ctl-grow2">
                  <input
                    className={"input mono-in" +
                      (badExpr != null && c.expr === badExpr ? " is-invalid" : "")}
                    type="text" value={c.expr || ""} placeholder='$.status == "ok"'
                    disabled={disabled}
                    aria-invalid={badExpr != null && c.expr === badExpr ? "true" : undefined}
                    onChange={(e) => {
                      const next = cc.slice();
                      next[j] = Object.assign({}, c, { expr: e.target.value });
                      set({ computed: next });
                    }}
                    onBlur={() => onCommit(pick)} />
                </Field>
                <button type="button" className="btn sm ghost ctl-fix" disabled={disabled}
                        aria-label={"Remove computed column " + (j + 1)}
                        onClick={() => commit({ computed: cc.filter((_, k) => k !== j) })}>
                  <Ic name="x" />
                </button>
              </div>
            ))}
            <div className="ctl-row">
              <button type="button" className="btn sm ghost" disabled={disabled}
                      onClick={() => commit({ computed: cc.concat([{ name: "", expr: "" }]) })}>
                <Ic name="plus" /> Add computed column
              </button>
              {badName != null ? (
                <span className="focus-tag"><Ic name="pin" /> keyboard focus</span>
              ) : null}
            </div>
            {op.note ? <Fixed text={op.note} /> : null}
            <p className="ctl-hint">{DRAWN[2].hint}</p>
          </>
        );
      }

      case 3:
        return (
          <>
            <div className="ctl-row">
              <Field label="Keep only rows where this is true" cls="ctl-grow">
                <textarea className={"input mono-in" + (refusedOp === 3 ? " is-invalid" : "")}
                          rows={2} value={pick.filter || ""} disabled={disabled}
                          placeholder='$.status != "ok"'
                          onChange={(e) => set({ filter: e.target.value })}
                          onBlur={() => onCommit(pick)} />
              </Field>
            </div>
            <p className="ctl-hint">{DRAWN[3].hint}</p>
          </>
        );

      case 4: {
        const sort = pick.sort || {};
        return (
          <>
            <div className="ctl-row">
              <Field label="Field" cls="ctl-grow">
                <Select value={sort.field || ""} disabled={disabled}
                        options={fieldOptions(vocab, pick, false, badName)}
                        onChange={(v) => commit({ sort: v ? { field: v, dir: sort.dir || "asc" } : null })} />
              </Field>
              <Field label="Direction" cls="ctl-grow">
                <Select value={sort.dir || "asc"} disabled={disabled || !sort.field}
                        options={optsOf(control(op, "direction"))}
                        onChange={(v) => commit({ sort: sort.field ? { field: sort.field, dir: v } : null })} />
              </Field>
            </div>
            <p className="ctl-hint">{DRAWN[4].hint}</p>
          </>
        );
      }

      case 5: {
        const range = control(op, "cap").range || { min: 1, max: 20000 };
        return (
          <>
            <div className="ctl-row">
              <Field label="Rows, at most" cls="ctl-grow">
                <input className="input mono-in" type="number" inputMode="numeric"
                       min={range.min} max={range.max} step="1" placeholder="8"
                       value={pick.cap == null ? "" : pick.cap} disabled={disabled}
                       onChange={(e) => set({ cap: e.target.value === "" ? null : Number(e.target.value) })}
                       onBlur={() => onCommit(pick)} />
              </Field>
            </div>
            <p className="ctl-hint">{DRAWN[5].hint}</p>
          </>
        );
      }

      case 6: {
        const agg = pick.aggregate || { fn: "none", field: null };
        const fieldCtl = control(op, "field");
        return (
          <>
            <div className="ctl-row">
              <Field label="Function" cls="ctl-grow">
                <Select value={agg.fn || "none"} disabled={disabled}
                        options={optsOf(control(op, "fn"))}
                        onChange={(v) => commit({ aggregate: { fn: v, field: v === "count" || v === "none" ? null : agg.field } })} />
              </Field>
              <Field label="Of field" cls="ctl-grow">
                <Select value={agg.field || ""} disabled={disabled || !fieldCtl.enabled}
                        options={fieldOptions(vocab, pick, true, badName)}
                        onChange={(v) => commit({ aggregate: { fn: agg.fn, field: v || null } })} />
              </Field>
            </div>
            {!fieldCtl.enabled && fieldCtl.why ? (
              <p className="ctl-hint"><b>{fieldCtl.why}</b> — the field picker is off.</p>
            ) : (
              <p className="ctl-hint">
                A closed set of five, accumulated in <span className="mono">numeric</span> and
                emitted as <span className="mono">AS &quot;agg&quot;</span>.
              </p>
            )}
          </>
        );
      }

      case 7:
        return (
          <>
            <div className="ctl-row">
              <Field label="Granularity" cls="ctl-grow">
                <Select value={pick.bucket || "off"} disabled={disabled}
                        options={optsOf(control(op, "granularity"))}
                        onChange={(v) => {
                          // B5c, made VISIBLE: turning a bucket on while
                          // operation 6 has no function sets it to count,
                          // in the control, never silently.
                          const t = op.transition;
                          const agg = pick.aggregate || { fn: "none", field: null };
                          const needs = v !== "off" && t && (agg.fn || "none") === "none";
                          commit({
                            bucket: v,
                            aggregate: needs ? { fn: t.set.fn, field: null } : agg,
                          });
                        }} />
              </Field>
            </div>
            {op.ctl_fixed ? <Fixed text={op.ctl_fixed} /> : null}
            <p className="ctl-hint">{DRAWN[7].hint}</p>
          </>
        );

      case 8:
        return (
          <>
            <div className="ctl-row">
              <Field label="Numeric field" cls="ctl-grow">
                <Select value={(pick.window || {}).field || ""} disabled={disabled}
                        options={fieldOptions(vocab, pick, true, badName)}
                        onChange={(v) => commit({ window: v ? { field: v } : null })} />
              </Field>
            </div>
            {op.ctl_fixed ? <Fixed text={op.ctl_fixed} /> : null}
            <p className="ctl-hint">{DRAWN[8].hint}</p>
          </>
        );

      case 9:
        return (
          <>
            <div className="ctl-toggle">
              <span className={"toggle" + (disabled ? " is-disabled" : "")}>
                <input type="checkbox" id="op9-changed" checked={!!pick.changed}
                       disabled={disabled}
                       onChange={(e) => commit({ changed: e.target.checked })} />
                <span className="track" />
              </span>
              <label className="ctl-toggle-lab" htmlFor="op9-changed">
                Keep only rows whose value differs from the one before, per sender
              </label>
            </div>
            {op.ctl_fixed ? <Fixed text={op.ctl_fixed} /> : null}
            <p className="ctl-hint">{DRAWN[9].hint}</p>
          </>
        );

      default:
        return null;
    }
  }

  return (
    <div>
      <section className="panel" aria-label="The pick">
        <div className="panel-head">
          <Ic name="columns" />
          <span className="panel-title">The pick</span>
          <span className="count-pill" style={{ marginLeft: "auto" }}>
            {ops.length} operations
          </span>
        </div>
        <div className="panel-body" style={{ padding: "6px 10px 4px" }}>
          <ul className="ops">
            {ops.map((op) => {
              const disabled = !op.enabled;
              const refused = !disabled && refusedOp === op.n;
              const on = !disabled && !refused && isOn(pick, op.n);
              const cls = disabled ? "is-disabled" : refused ? "is-refused" : on ? "is-on" : "is-off";
              const key = disabled ? "disabled" : refused ? "refused" : on ? "on" : "off";
              return (
                <li className={"op " + cls} key={op.n}>
                  <div className="op-hd">
                    <span className="op-n">{op.n}</span>
                    <span className="icon-chip"><Ic name={DRAWN[op.n].icon} /></span>
                    <span className="op-name">{op.label}</span>
                    <span className="op-state">{OP_STATE[key]}</span>
                  </div>
                  <div className="op-ctl">{body(op, disabled)}</div>
                  {disabled && op.why ? (
                    <p className="op-why"><Ic name="ban" /><span>{op.why}</span></p>
                  ) : refused && ref ? (
                    <p className="op-why"><Ic name="warning" /><span>{ref.why}</span></p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
        <div className="pick-foot">
          <div className="pick-dirty" hidden={!dirty}>
            <Ic name="info" />
            <span>
              The controls no longer describe the answers below. Press{" "}
              <b>Run this pick</b> to run the changed pick.
            </span>
          </div>
          <button className="btn-primary" onClick={onRun} disabled={busy}>
            <Ic name="play" />
            {busy ? "Running…" : "Run this pick"}
          </button>
          <p className="pick-note">
            Every visitor gets these controls and this SQL — there is no
            author/viewer split.
          </p>
        </div>
      </section>

      <section className="panel sidecard" aria-label="The seeded database">
        <div className="panel-head">
          <Ic name="noun" />
          <span className="panel-title">The seeded database</span>
        </div>
        <div className="panel-body">
          <div className="srcmeta">
            {optsOf(control(ops[0] || {}, "source")).map((o) => {
              const parts = o.label.split("·");
              return (
                <div className={"srcrow" + (o.value === pick.source ? "" : " dim")} key={o.value}>
                  <span className="k">{parts[0].trim()}</span>
                  <span className="v">{(parts[1] || "").trim()}</span>
                </div>
              );
            })}
            <div className="srcrow dim">
              <span className="k">total</span>
              <span className="v">10,410 rows</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
