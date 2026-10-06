// dashboard.jsx — the dashboard's entry (T-71): the question on the left,
// the answer on the right, and on a phone the question folded into one bar.
//
// THE SPLIT. demo/server/dashboard.py owns every rule: which choices exist,
// how a click becomes the statement, the sentence, how a cell reads. This
// file keeps the clicks in one `view` object, sends it, and draws the
// answer. The suite tests the rules without a browser (AC-36); the browser
// proof is demo/tools/dashboard-drive.mjs and the screenshot pairs.
//
// STALE ANSWERS. Picks can change before an answer arrives. Every request
// carries a sequence number and an AbortController; an answer is drawn only
// if it belongs to the newest request, so an old answer can never paint over
// a newer question. While a request is out, the previous answer stays on
// screen dimmed under an "Updating" label, never presented as current.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AdminPanel } from "./dashboard-admin.jsx";
import { ColumnsStep, ConditionsStep, DatasetStep, SortShowStep, SummaryStep, answerShape, isComplete, logicReady } from "./dashboard-steps.jsx";
import { ScoreboardStep, countWaiting, countedFields, nextSort } from "./dashboard-scoreboard.jsx";

const WAIT_BEFORE_ASKING = 250; // let a burst of clicks settle into one question

async function getJSON(url, init) {
  const r = await fetch(url, init);
  let body = null;
  try { body = await r.json(); } catch (_) { body = null; }
  if (!r.ok && !(body && body.kind)) throw new Error("bad answer");
  return body;
}

function viewFor(setup, datasetId, admin) {
  return JSON.parse(JSON.stringify((admin ? setup.admin_default_views : setup.default_views)[datasetId]));
}

// View as: remembered for the visit. Storage can be missing or refuse
// (a private window, blocked site data): the page then simply starts as
// Everyone.
const VIEW_AS_KEY = "autosql.dashboard.view-as";
function loadViewAs() {
  try { return window.localStorage.getItem(VIEW_AS_KEY) === "admin"; } catch (_) { return false; }
}
function saveViewAs(admin) {
  try { window.localStorage.setItem(VIEW_AS_KEY, admin ? "admin" : "everyone"); } catch (_) { /* not remembered */ }
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// The choices that are off for this view, and why — the contract's own
// verdicts, carried in the setup (setup.unavailable, from /api/operations).
const SCOREBOARD_SORT_OFF = "A scoreboard sorts by its own columns: tap a column's name.";
function offFor(setup, view) {
  if (view.scoreboard) return { sort: SCOREBOARD_SORT_OFF };
  return setup.unavailable[view.dataset][answerShape(view)] || {};
}

// What is sent: the view without the conditions still waiting for a value,
// without the screen's own row handles, and without the choices that are
// greyed out right now. A greyed choice is kept on screen (it comes back
// when the summary is turned off), shown as off with its reason, and not
// asked about.
function sendable(setup, view) {
  const ds = setup.datasets.find((d) => d.id === view.dataset);
  const conditions = view.conditions
    .filter((c) => isComplete(c, ds.fields.find((f) => f.path === c.field)))
    .map(({ _k, ...c }) => c); // eslint-disable-line no-unused-vars
  const off = offFor(setup, view);
  // "Exactly one" / "All or none" over fewer than two conditions with values
  // is not a question yet: the conditions are marked "not used yet" on
  // screen and not sent.
  const logic = view.logic || "all";
  // Not ready: no conditions and the logic All, so the answer matches the
  // "Not used yet" note on screen instead of being refused (T-75).
  const ready = logicReady(logic, conditions.length);
  const out = { ...view, conditions: ready ? conditions : [], logic: ready ? logic : "all" };
  if (view.summary || view.scoreboard) out.columns = []; // kept on screen, greyed, for when it is turned off
  if (off.sort) out.sort = null;
  if (off.show) out.show = null;
  if (view.scoreboard) out.scoreboard = sendableScoreboard(setup, ds, view.scoreboard);
  return out;
}

// A scoreboard as sent: only the count columns that are ready (a name, a
// condition with a value, enough conditions for their logic); the others
// stay on screen marked "not counted until …". Each column travels with
// its own id (the screen's handle, _k), the answer's headers come back as
// "count:<id>" / "pct:<id>", and a sort names a column the same way — one
// numbering end to end, so a column held back cannot shift which column a
// header or a sort means. A sort on a column that is not sent is not sent.
function sendableScoreboard(setup, ds, sb) {
  const fields = countedFields(setup, ds, sb);
  const counts = [];
  sb.counts.forEach((c) => {
    if (countWaiting(c, fields)) return;
    counts.push({
      id: c._k,
      label: c.label.trim(),
      logic: c.logic,
      pct: c.pct,
      conditions: c.conditions
        .filter((x) => isComplete(x, fields.find((f) => f.path === x.field)))
        .map(({ _k, ...x }) => x), // eslint-disable-line no-unused-vars
    });
  });
  let sort = sb.sort;
  if (sort) {
    const m = /^(count|pct):(\d+)$/.exec(sort.column);
    if (m) {
      const sent = counts.find((c) => c.id === Number(m[2]));
      if (!sent || (m[1] === "pct" && !sent.pct)) sort = null;
    }
  }
  return { by: sb.by, count_from: sb.count_from || null, counts, time: sb.time || null,
           measure: sb.measure || null, sort };
}

const COLUMNS_OFF = "Columns don't apply to a summary.";
const COLUMNS_OFF_SCOREBOARD = "Columns don't apply to a scoreboard: it has its own, in step 6.";

// ── the answer ───────────────────────────────────────────────────────────

function Cell({ value, kind, title, pinned }) {
  // A cell with an exact value beside it (a scoreboard average) shows that
  // value on hover, and on a tap or Enter, since a phone has no hover (T-75).
  const [exact, setExact] = useState(false);
  if (value === null || value === undefined) return <td className="dx-td is-blank">—</td>;
  const cls = kind === "number" ? " is-num" : kind === "time" || kind === "date" ? " is-when" : "";
  if (pinned) {
    // The pinned group column is capped so the counts beside it stay in view;
    // a name too long for it is cut short, whole on hover, tap or Enter.
    return (
      <td className={"dx-td is-pinned" + cls} title={String(value)}>
        <span className={"dx-cell dx-pin" + (exact ? " is-open" : "")} role="button" tabIndex={0} data-pinned=""
          onClick={() => setExact(!exact)} onKeyDown={(e) => { if (e.key === "Enter") setExact(!exact); }}>
          {value}
        </span>
      </td>
    );
  }
  if (!title) return <td className={"dx-td" + cls}><span className="dx-cell">{value}</span></td>;
  return (
    <td className={"dx-td" + cls + " has-exact"} title={title}>
      <span className="dx-cell" role="button" tabIndex={0} data-exact={title.replace("To six places: ", "")}
        onClick={() => setExact(!exact)} onKeyDown={(e) => { if (e.key === "Enter") setExact(!exact); }}>
        {exact ? title.replace("To six places: ", "") : value}
      </span>
    </td>
  );
}

function Table({ answer, onPage, updating, sort, onSort }) {
  const { columns, rows, page, total } = answer;
  if (!columns.length) {
    return <p className="dx-empty">Pick at least one column to see the rows.</p>;
  }
  const first = page.start + 1;
  const last = page.start + page.count;
  return (
    <>
      <div className="dx-table-box" tabIndex={0} aria-label="Rows">
        <table className={"dx-table" + (onSort ? " is-board" : "")}>
          <thead>
            <tr>{columns.map((c, j) => (
              <th key={c.path || c.id} className={c.kind === "number" ? "is-num" : ""} title={c.title || undefined}
                aria-sort={onSort && sort && sort.column === c.id ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                {onSort ? (
                  <button type="button" className="dx-th-sort" data-sort={c.id} disabled={updating}
                    onClick={() => onSort(nextSort(sort, c.id))}>
                    {c.label}
                    <span className="dx-th-arrow" aria-hidden="true">
                      {sort && sort.column === c.id ? (sort.dir === "asc" ? " ▲" : " ▼") : (!sort && j === 0 ? " ▲" : "")}
                    </span>
                  </button>
                ) : c.label}
              </th>
            ))}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={page.start + i}>
                {r.map((v, j) => <Cell key={j} value={v} kind={columns[j].kind} pinned={!!onSort && j === 0}
                  title={answer.titles && answer.titles[i] ? answer.titles[i][j] : null} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="dx-pager" aria-label="Pages">
        <span className="dx-pager-where">
          Rows {first.toLocaleString("en-US")}–{last.toLocaleString("en-US")} of {total.toLocaleString("en-US")}
        </span>
        <span className="dx-pager-buttons">
          <button type="button" className="dx-btn" data-page="prev" disabled={updating || page.index === 0} onClick={() => onPage(page.index - 1)}>Previous</button>
          <button type="button" className="dx-btn" data-page="next" disabled={updating || page.index >= page.last} onClick={() => onPage(page.index + 1)}>Next</button>
        </span>
      </nav>
      {onSort ? (
        <details className="dx-legend" data-testid="legend">
          <summary>What the columns count</summary>
          <dl>
            {columns.map((c) => (
              <React.Fragment key={c.id}>
                <dt>{c.label}</dt>
                <dd>{c.title}</dd>
              </React.Fragment>
            ))}
          </dl>
        </details>
      ) : null}
    </>
  );
}

// ── a single number, and a number per hour or day ───────────────────────

function Hero({ number }) {
  return (
    <div className="dx-hero">
      <p className="dx-hero-label">{number.label}</p>
      {number.value === null ? (
        // The server says why it is blank: "No rows match" only when the
        // count over the same choices is really 0.
        <p className="dx-hero-none" data-testid="blank">{number.blank || "No value."}</p>
      ) : (
        <p className="dx-hero-value" title={number.exact !== number.value ? `To six places: ${number.exact}` : undefined}>{number.value}</p>
      )}
      {number.note ? <p className="dx-hero-note" data-testid="note">{number.note}</p> : null}
    </div>
  );
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver((es) => setW(Math.floor(es[0].contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function BarChart({ answer }) {
  const { bars, unit } = answer;
  const [box, width] = useWidth();
  const [hover, setHover] = useState(null);
  const n = bars.length;
  const left = 48, right = 8, top = 24, plotH = 200, bottom = 26;
  const slot = Math.max(unit === "hour" ? 6 : 24, ((width || 600) - left - right) / Math.max(n, 1));
  const bw = Math.max(2, Math.min(24, slot - 2));
  const W = Math.ceil(left + n * slot + right);
  const H = top + plotH + bottom;
  const values = bars.map((b) => (b.value === null ? 0 : b.value));
  const max = niceMax(Math.max(0, ...values));
  const y = (v) => top + plotH - (v / max) * plotH;
  const ticks = [0, max / 2, max];
  const fmt = (v) => v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  let top1 = 0;
  values.forEach((v, i) => { if (v > values[top1]) top1 = i; });
  const read = hover !== null ? bars[hover] : bars[top1];
  return (
    <figure className="dx-chart">
      <figcaption className="dx-chart-read" aria-live="polite">
        {read ? (
          <>
            <span className="dx-chart-read-label">{hover !== null ? read.label : `Highest: ${read.label}`}</span>
            <span className="dx-chart-read-value">{read.empty ? "no rows" : read.text === null ? "—" : read.text}</span>
          </>
        ) : null}
      </figcaption>
      <div className="dx-chart-box" ref={box}>
        <svg width={W} height={H} role="img" aria-label={`${answer.measure}, per ${unit}. The table below lists every value.`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={W - right} y1={y(t)} y2={y(t)} className="dx-grid" />
              <text x={left - 6} y={y(t)} className="dx-tick" textAnchor="end" dominantBaseline="middle">{fmt(t)}</text>
            </g>
          ))}
          {bars.map((b, i) => {
            const x = left + i * slot + (slot - bw) / 2;
            const v = b.value === null ? 0 : b.value;
            const h = (v / max) * plotH;
            const base = top + plotH;
            const r = Math.min(4, h, bw / 2);
            const d = h <= 0 ? null
              : `M${x},${base} V${base - h + r} Q${x},${base - h} ${x + r},${base - h} H${x + bw - r} Q${x + bw},${base - h} ${x + bw},${base - h + r} V${base} Z`;
            // A day's label is "Aug 14" while the bars have room for it, and
            // just the day ("15") when they don't; an hour chart labels each
            // midnight only.
            const roomy = slot >= 52;
            const label = unit === "day"
              ? (roomy || i === 0 ? b.label : b.label.split(" ")[1])
              : (b.start.slice(11, 13) === "00" ? b.label.split(",")[0] : null);
            return (
              <g key={b.start} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => setHover(i)}>
                <rect x={left + i * slot} y={top} width={slot} height={plotH} className="dx-hit" />
                {d ? <path d={d} className={"dx-bar" + (hover === i ? " is-hover" : "")} /> : null}
                {b.empty ? <line x1={x} x2={x + bw} y1={base - 1.5} y2={base - 1.5} className="dx-empty-mark" /> : null}
                {/* Each bar's value, written above it where the slot is wide
                    enough to hold it (T-75); hours are too narrow, and the
                    table below always has every value. */}
                {b.text !== null && !b.empty && slot >= b.text.length * 6.2 + 4 ? (
                  <text x={x + bw / 2} y={base - h - 6} className="dx-bar-value" textAnchor="middle" data-bar-value={i}>{b.text}</text>
                ) : null}
                {label ? (
                  <text x={unit === "day" ? x + bw / 2 : x} y={base + 16} className="dx-tick" textAnchor={unit === "day" ? "middle" : "start"}>{label}</text>
                ) : null}
                <title>{`${b.label}: ${b.empty ? "no rows" : b.text === null ? "no value" : b.text}`}</title>
              </g>
            );
          })}
          <line x1={left} x2={W - right} y1={top + plotH} y2={top + plotH} className="dx-axis" />
        </svg>
      </div>
    </figure>
  );
}

function Answer({ answer, updating, failed, onPage, sort, onSort }) {
  if (failed) {
    return (
      <div className="dx-answer">
        <p className="dx-problem" role="alert">Couldn't reach the data just now. Is the demo still running?</p>
      </div>
    );
  }
  if (!answer) {
    return <div className="dx-answer"><p className="dx-status">Loading…</p></div>;
  }
  return (
    <div className={"dx-answer" + (updating ? " is-updating" : "")} aria-busy={updating}>
      <div className="dx-answer-head">
        <h2 className="dx-sentence" data-testid="sentence">{answer.sentence || "These choices can't be answered as they stand"}</h2>
        <p className="dx-status" aria-live="polite">{updating ? "Updating…" : ""}</p>
      </div>
      {answer.kind === "refused" ? (
        <p className="dx-problem" role="alert">{answer.message}</p>
      ) : answer.kind === "invalid" ? (
        <p className="dx-problem" role="alert">{answer.message}</p>
      ) : answer.kind === "number" ? (
        <Hero number={answer.number} />
      ) : answer.total === 0 ? (
        <div className="dx-nothing">
          <p className="dx-nothing-title">No rows match</p>
          <p className="dx-nothing-hint">Try removing a condition.</p>
        </div>
      ) : answer.kind === "scoreboard" ? (
        <Table answer={answer} onPage={onPage} updating={updating} sort={sort} onSort={onSort} />
      ) : answer.kind === "chart" ? (
        <>
          <BarChart answer={answer} />
          <Table answer={answer} onPage={onPage} updating={updating} />
        </>
      ) : (
        <Table answer={answer} onPage={onPage} updating={updating} />
      )}
    </div>
  );
}

// ── the phone's folded question ──────────────────────────────────────────

function summaryLine(setup, view) {
  const ds = setup.datasets.find((d) => d.id === view.dataset);
  const parts = [ds.name];
  // Only the conditions in use: one still waiting for its value is not asked.
  const n = view.conditions.filter((c) => isComplete(c, ds.fields.find((f) => f.path === c.field))).length;
  if (n) parts.push(n === 1 ? "1 condition" : `${n} conditions`);
  if (view.sort && !offFor(setup, view).sort) {
    const f = ds.fields.find((x) => x.path === view.sort.field);
    const words = setup.sort_words[f.kind][view.sort.dir];
    parts.push(f.path === "ts" ? words : `${f.label}, ${words}`);
  }
  if (view.summary) {
    const sm = view.summary;
    const f = sm.field ? ds.fields.find((x) => x.path === sm.field) : null;
    parts.push(`${setup.summary_fns[sm.fn]}${f ? " " + f.label : ""}${sm.per === "all" ? "" : " per " + sm.per}`);
  }
  if (view.scoreboard) {
    const by = ds.fields.find((x) => x.path === view.scoreboard.by);
    const ready = view.scoreboard.counts.filter((c) => !countWaiting(c, countedFields(setup, ds, view.scoreboard))).length;
    parts.push(`per ${by.label}`);
    const rel = (ds.count_from || []).find((r) => r.id === view.scoreboard.count_from);
    if (rel) parts.push(`counting ${rel.name}`);
    if (ready) parts.push(ready === 1 ? "1 count" : `${ready} counts`);
  }
  if (view.show && !offFor(setup, view).show) parts.push(`first ${view.show}`);
  return parts.join(" · ");
}

// ── the page ─────────────────────────────────────────────────────────────

function App() {
  const [setup, setSetup] = useState(null);
  const [setupFailed, setSetupFailed] = useState(false);
  const [view, setView] = useState(null);
  const [page, setPage] = useState(0);
  const [answer, setAnswer] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false); // phone: is the question open?
  const [admin, setAdmin] = useState(loadViewAs);

  const seq = useRef(0);
  const inflight = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    getJSON("/api/dashboard/setup")
      .then((s) => { setSetup(s); setView(viewFor(s, s.default_view.dataset, loadViewAs())); })
      .catch(() => setSetupFailed(true));
  }, []);

  // The statement and the engines' verdict are asked for only in the Admin
  // view: the Everyone view's answers carry none of it (T-75).
  const adminRef = useRef(admin);
  adminRef.current = admin;

  const ask = useCallback((v, p) => {
    const mine = ++seq.current;
    if (inflight.current) inflight.current.abort();
    const ctl = new AbortController();
    inflight.current = ctl;
    setUpdating(true);
    setFailed(false); // a new question is out: the last failure is not this answer
    getJSON("/api/dashboard/answer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ view: v, page: p, admin: adminRef.current }),
      signal: ctl.signal,
    })
      .then((a) => {
        if (mine !== seq.current) return; // a newer question is out: drop this
        setAnswer(a);
        setFailed(false);
        setUpdating(false);
      })
      .catch((e) => {
        if (mine !== seq.current || (e && e.name === "AbortError")) return;
        setFailed(true);
        setUpdating(false);
      });
  }, []);

  // What is actually asked. Editing a condition that is still waiting for
  // its value changes the view but not the question, and asks nothing.
  const question = useMemo(() => (setup && view ? JSON.stringify(sendable(setup, view)) : null), [setup, view]);

  // A changed question waits a moment for the clicks to settle; a page
  // turn is asked at once (the server remembers the whole answer).
  const lastQuestion = useRef(null);
  useEffect(() => {
    if (!question) return;
    clearTimeout(timer.current);
    const sameQuestion = lastQuestion.current === question;
    lastQuestion.current = question;
    const v = JSON.parse(question);
    if (sameQuestion || answer === null) {
      ask(v, page);
      return;
    }
    // Mark the answer as out of date the moment the question changes,
    // not only once the request leaves.
    seq.current += 1;
    if (inflight.current) inflight.current.abort();
    setUpdating(true);
    setFailed(false); // a new question is out: the last failure is not this answer
    timer.current = setTimeout(() => ask(v, page), WAIT_BEFORE_ASKING);
    return () => clearTimeout(timer.current);
  }, [question, page, admin]); // eslint-disable-line react-hooks/exhaustive-deps

  const change = useCallback((patch) => {
    setPage(0);
    setView((v) => ({ ...v, ...patch }));
  }, []);

  const ds = useMemo(
    () => (setup && view ? setup.datasets.find((d) => d.id === view.dataset) : null),
    [setup, view],
  );

  const flipViewAs = (toAdmin) => {
    if (toAdmin === admin) return;
    setAdmin(toAdmin);
    saveViewAs(toAdmin);
    // A data set still on the other view's starting columns moves to this
    // view's (Edge cases' Label is on for Admin, off for Everyone).
    const from = (toAdmin ? setup.default_views : setup.admin_default_views)[view.dataset];
    const to = (toAdmin ? setup.admin_default_views : setup.default_views)[view.dataset];
    if (same(view.columns, from.columns) && !same(from.columns, to.columns)) change({ columns: [...to.columns] });
    // A scoreboard grouped by a field Everyone doesn't see (Edge cases'
    // Label) moves to the first group Everyone may use (T-75).
    const sb = view.scoreboard;
    if (!toAdmin && sb) {
      const fields = setup.datasets.find((d) => d.id === view.dataset).fields;
      const by = fields.find((f) => f.path === sb.by);
      if (by && by.hidden_by_default) {
        const next = fields.find((f) => f.group.ok && !f.hidden_by_default);
        change({ scoreboard: next ? { ...sb, by: next.path, sort: null } : null });
      }
    }
  };

  if (setupFailed) {
    return <main className="dx-shell"><p className="dx-problem" role="alert">Couldn't reach the data just now. Is the demo still running?</p></main>;
  }
  if (!setup || !view) {
    return <main className="dx-shell"><p className="dx-status">Loading…</p></main>;
  }

  return (
    <div className="dx-shell">
      <header className="dx-header">
        <div className="dx-brand">
          <h1 className="dx-title">Data explorer</h1>
          <span className="dx-tag">Invented demo data</span>
        </div>
        <div className="dx-viewas">
          <span className="dx-viewas-label" id="dx-viewas-label">View as</span>
          <div className="dx-seg" role="radiogroup" aria-labelledby="dx-viewas-label">
            {[[false, "Everyone"], [true, "Admin"]].map(([v, text]) => (
              <button key={text} type="button" role="radio" aria-checked={admin === v} data-viewas={v ? "admin" : "everyone"}
                className={"dx-seg-btn" + (admin === v ? " is-on" : "")} onClick={() => flipViewAs(v)}>{text}</button>
            ))}
          </div>
        </div>
      </header>

      <div className={"dx-main" + (editing ? " is-editing" : "")}>
        <button
          type="button"
          className="dx-fold"
          aria-expanded={editing}
          aria-controls="dx-question"
          onClick={() => setEditing((e) => !e)}
        >
          <span className="dx-fold-text">{summaryLine(setup, view)}</span>
          <span className="dx-fold-act">{editing ? "Done" : "Edit"}</span>
        </button>

        <aside className="dx-question" id="dx-question" aria-label="Your question">
          <h2 className="dx-question-title">Your question</h2>
          <DatasetStep
            datasets={setup.datasets}
            value={view.dataset}
            onPick={(id) => { if (id !== view.dataset) { setPage(0); setView(viewFor(setup, id, admin)); } }}
          />
          <ColumnsStep
            fields={ds.fields}
            value={view.columns}
            onChange={(columns) => change({ columns })}
            why={view.scoreboard ? COLUMNS_OFF_SCOREBOARD : view.summary ? COLUMNS_OFF : null}
          />
          <ConditionsStep
            fields={ds.fields}
            shown={view.columns}
            admin={admin}
            value={view.conditions}
            opWords={setup.op_labels}
            onChange={(conditions) => change(conditions.length < 2 ? { conditions, logic: "all" } : { conditions })}
            logic={view.logic}
            onLogic={(logic) => change({ logic })}
            logics={setup.logics}
            needsTwo={setup.logic_needs_two}
            scoreboardOn={view.scoreboard ? {
              rel: ((ds.count_from || []).find((r) => r.id === view.scoreboard.count_from) || {}).name,
              one: ds.one, many: ds.name.toLowerCase(),
            } : null}
          />
          <SortShowStep
            fields={ds.fields}
            sort={view.sort}
            show={view.show}
            showChoices={setup.show}
            sortWords={setup.sort_words}
            onChange={change}
            off={offFor(setup, view)}
          />
          <SummaryStep
            fields={ds.fields}
            summary={view.summary}
            fns={setup.summary_fns}
            off={offFor(setup, view)}
            onChange={(patch) => change(patch.summary ? { ...patch, scoreboard: null } : patch)}
          />
          <ScoreboardStep
            ds={ds}
            fields={ds.fields}
            value={view.scoreboard || null}
            shown={view.columns}
            admin={admin}
            setup={setup}
            onChange={(patch) => change(patch.scoreboard ? { ...patch, summary: null } : patch)}
          />
        </aside>

        <main className="dx-result" aria-label="Answer">
          {admin ? <AdminPanel answer={answer} updating={updating} failed={failed} /> : null}
          <Answer answer={answer} updating={updating} failed={failed} onPage={setPage}
            sort={view.scoreboard ? view.scoreboard.sort : null}
            onSort={view.scoreboard ? (sort) => change({ scoreboard: { ...view.scoreboard, sort } }) : null} />
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
