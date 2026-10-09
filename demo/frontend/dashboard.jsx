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

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AdminPanel } from "./dashboard-admin.jsx";
import { ColumnsStep, ConditionsStep, DatasetStep, SortShowStep, SummaryStep, answerShape, isComplete, logicReady, offered } from "./dashboard-steps.jsx";
import { ScoreboardStep, asMatch, countWaiting, countedFields, countedSet, nextSort } from "./dashboard-scoreboard.jsx";

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
  return { by: sb.by, count_from: asMatch(ds, sb.count_from), counts, time: sb.time || null,
           measure: sb.measure || null, sort };
}

const COLUMNS_OFF = "Columns don't apply to a summary.";
const COLUMNS_OFF_SCOREBOARD = "Columns don't apply to a scoreboard: it has its own, in step 6.";

// ── the answer ───────────────────────────────────────────────────────────

// Is this element's text cut short? Measured after layout, and again when
// its box changes size (a phone turned, a window resized).
function useCutShort(ref, deps) {
  const [cut, setCut] = useState(false);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setCut(el.scrollWidth > el.clientWidth + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, deps);
  return cut;
}

function PinnedCell({ value, cls }) {
  // The pinned group column is capped so the counts beside it stay in view;
  // a name too long for it is cut short, whole on hover, tap or Enter. Only
  // such a cell (or one opened) is a tab stop: a board of short names is not
  // one stop per row (T-77).
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const cut = useCutShort(ref, [value]);
  const acts = cut || open;
  return (
    <td className={"dx-td is-pinned" + cls} title={String(value)}>
      <span ref={ref} className={"dx-cell dx-pin" + (open ? " is-open" : "")} data-pinned=""
        role={acts ? "button" : undefined} tabIndex={acts ? 0 : undefined}
        onClick={() => { if (acts) setOpen(!open); }}
        onKeyDown={(e) => { if (acts && e.key === "Enter") setOpen(!open); }}>
        {value}
      </span>
    </td>
  );
}

function Cell({ value, kind, title, pinned }) {
  // A cell with an exact value beside it (a scoreboard average) shows that
  // value on hover, and on a tap or Enter, since a phone has no hover (T-75).
  const [exact, setExact] = useState(false);
  if (value === null || value === undefined) return <td className="dx-td is-blank">—</td>;
  const cls = kind === "number" ? " is-num" : kind === "time" || kind === "date" ? " is-when" : "";
  if (pinned) return <PinnedCell value={value} cls={cls} />;
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

function Answer({ answer, updating, failed, current, onPage, sort, onSort }) {
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
        // A refusal says why one pick can't be answered: never left standing
        // under another pick while that one is asked (S17 check, MEDIUM).
        current ? <p className="dx-problem" role="alert">{answer.message}</p> : null
      ) : answer.kind === "invalid" ? (
        // The same for a pick the page could not ask (T-79).
        current ? <p className="dx-problem" role="alert">{answer.message}</p> : null
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
    const rel = countedSet(setup, view.scoreboard);
    // Short enough for a phone: "Senders · their Heartbeats", as the
    // sentence reads it — never "Senders · per Sender".
    const own = (ds.own_keys || []).includes(by.path);
    if (!own) parts.push(`per ${by.label}`);
    if (rel) parts.push(`their ${rel.name}`);
    else if (own) parts.push("one row each");
    if (ready) parts.push(ready === 1 ? "1 count" : `${ready} counts`);
  }
  if (view.show && !offFor(setup, view).show) parts.push(`first ${view.show}`);
  return parts;
}

// ── the page ─────────────────────────────────────────────────────────────

function App() {
  const [setup, setSetup] = useState(null);
  const [setupFailed, setSetupFailed] = useState(false);
  const [view, setView] = useState(null);
  const [page, setPage] = useState(0);
  const [answer, setAnswer] = useState(null);
  // The question the answer on screen was asked for (S17 check, MEDIUM): a
  // line that describes a pick — the match preview, a refusal — is drawn only
  // while that question is the one on screen and its request didn't fail.
  const [answered, setAnswered] = useState(null);
  // Which view the answer on screen was asked for: an Admin answer (Edge
  // cases' Label in it) is never drawn once the page is back on Everyone,
  // not even dimmed while the Everyone answer is asked (T-79).
  const [answeredAdmin, setAnsweredAdmin] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false); // phone: is the question open?
  const [admin, setAdmin] = useState(loadViewAs);

  const seq = useRef(0);
  const inflight = useRef(null);
  const timer = useRef(null);

  // The setup, as each view gets it (T-79): the Everyone view's names no
  // field hidden from it, so it is fetched for the view on screen, and the
  // other view's is fetched when the switch is flipped. Each is kept once
  // fetched: the seed can't change under the page.
  const setups = useRef({});
  const loadSetup = useCallback((asAdmin) => {
    const key = asAdmin ? "admin" : "everyone";
    if (setups.current[key]) return Promise.resolve(setups.current[key]);
    return getJSON(`/api/dashboard/setup?view=${key}`).then((s) => { setups.current[key] = s; return s; });
  }, []);
  useEffect(() => {
    const asAdmin = loadViewAs();
    loadSetup(asAdmin)
      .then((s) => { setSetup(s); setView(viewFor(s, s.default_view.dataset, asAdmin)); })
      .catch(() => setSetupFailed(true));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // The statement and the engines' verdict are asked for only in the Admin
  // view: the Everyone view's answers carry none of it (T-75).
  const adminRef = useRef(admin);
  adminRef.current = admin;

  const ask = useCallback((v, p) => {
    const mine = ++seq.current;
    if (inflight.current) inflight.current.abort();
    const ctl = new AbortController();
    inflight.current = ctl;
    const asAdmin = adminRef.current;
    setUpdating(true);
    setFailed(false); // a new question is out: the last failure is not this answer
    getJSON("/api/dashboard/answer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ view: v, page: p, admin: asAdmin }),
      signal: ctl.signal,
    })
      .then((a) => {
        if (mine !== seq.current) return; // a newer question is out: drop this
        setAnswer(a);
        setAnswered(JSON.stringify(v));
        setAnsweredAdmin(asAdmin);
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
  // Is the answer on screen the answer to the pick on screen?
  const current = !!answer && !failed && answered === question;

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

  // A flip asks for the other view's setup first (once), then switches the
  // view and the setup together. Only the newest flip lands.
  const flips = useRef(0);
  const flipViewAs = (toAdmin) => {
    if (toAdmin === admin) return;
    const mine = ++flips.current;
    loadSetup(toAdmin)
      .then((next) => { if (mine === flips.current) applyFlip(toAdmin, next); })
      .catch(() => { if (mine === flips.current) setSetupFailed(true); });
  };
  const applyFlip = (toAdmin, nextSetup) => {
    setAdmin(toAdmin);
    saveViewAs(toAdmin);
    const patch = {};
    // A data set still on the other view's starting columns moves to this
    // view's (Edge cases' Label is on for Admin, off for Everyone). Admin's
    // starting views are in Admin's setup only.
    const adminSetup = toAdmin ? nextSetup : setup;
    const from = (toAdmin ? setup.default_views : adminSetup.admin_default_views)[view.dataset];
    const to = (toAdmin ? adminSetup.admin_default_views : nextSetup.default_views)[view.dataset];
    if (same(view.columns, from.columns) && !same(from.columns, to.columns)) patch.columns = [...to.columns];
    if (!toAdmin) {
      // Everyone keeps nothing that names a field hidden from it (T-77):
      // not a column, a condition, the sort, the group or a count's condition.
      const hiddenIn = (fields) => new Set(fields.filter((f) => f.hidden_by_default).map((f) => f.path));
      const hidden = hiddenIn(ds.fields);
      const cols = (patch.columns || view.columns).filter((p) => !hidden.has(p));
      if (cols.length !== (patch.columns || view.columns).length) patch.columns = cols;
      const conds = view.conditions.filter((c) => !hidden.has(c.field));
      if (conds.length !== view.conditions.length) {
        patch.conditions = conds;
        if (conds.length < 2) patch.logic = "all";
      }
      if (view.sort && hidden.has(view.sort.field)) patch.sort = null;
      const sb = view.scoreboard;
      if (sb) {
        let next = sb;
        // A scoreboard grouped by a field Everyone doesn't see moves to the
        // first group Everyone may use (T-75).
        if (hidden.has(sb.by)) {
          const by = ds.fields.find((f) => f.group.ok && !f.hidden_by_default);
          next = by ? { ...sb, by: by.path, sort: null } : null;
        }
        // A match on a field Everyone doesn't see is dropped, with what it
        // counted (T-76: the match pickers follow T-77's rule too).
        const m = next && asMatch(ds, next.count_from);
        if (m && (hidden.has(m.matches) || hiddenIn(countedFields(setup, ds, next)).has(m.field))) {
          next = { ...next, count_from: null, picking: false, counts: [], time: null, measure: null, sort: null };
        }
        const hiddenCounted = hiddenIn(countedFields(setup, ds, next || sb));
        if (next && next.counts.some((c) => c.conditions.some((x) => hiddenCounted.has(x.field)))) {
          next = { ...next, counts: next.counts.map((c) => {
            const kept = c.conditions.filter((x) => !hiddenCounted.has(x.field));
            return kept.length === c.conditions.length ? c : { ...c, conditions: kept, logic: kept.length < 2 ? "all" : c.logic };
          }) };
        }
        if (next !== sb) patch.scoreboard = next;
      }
    }
    setSetup(nextSetup);
    if (Object.keys(patch).length) change(patch);
  };

  if (setupFailed) {
    return <main className="dx-shell"><p className="dx-problem" role="alert">Couldn't reach the data just now. Is the demo still running?</p></main>;
  }
  if (!setup || !view) {
    return <main className="dx-shell"><p className="dx-status">Loading…</p></main>;
  }
  const picks = offered(ds.fields, admin);

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
          <span className="dx-fold-text">
            {/* Each part whole: a second line starts at a " · ", never inside "2 counts". */}
            {summaryLine(setup, view).map((p, i) => (
              <React.Fragment key={i}>{i ? " · " : ""}<span className="dx-fold-part">{p}</span></React.Fragment>
            ))}
          </span>
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
            fields={picks}
            value={view.columns}
            onChange={(columns) => change({ columns })}
            why={view.scoreboard ? COLUMNS_OFF_SCOREBOARD : view.summary ? COLUMNS_OFF : null}
          />
          <ConditionsStep
            fields={picks}
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
              rel: (countedSet(setup, view.scoreboard) || {}).name,
              one: ds.one, many: ds.name.toLowerCase(),
            } : null}
          />
          <SortShowStep
            fields={picks}
            sort={view.sort}
            show={view.show}
            showChoices={setup.show}
            sortWords={setup.sort_words}
            onChange={change}
            off={offFor(setup, view)}
          />
          <SummaryStep
            name={ds.name}
            fields={picks}
            summary={view.summary}
            fns={setup.summary_fns}
            off={offFor(setup, view)}
            onChange={(patch) => change(patch.summary ? { ...patch, scoreboard: null } : patch)}
          />
          <ScoreboardStep
            ds={ds}
            fields={picks}
            value={view.scoreboard || null}
            shown={view.columns}
            admin={admin}
            setup={setup}
            match={current && answer.kind !== "invalid" && (admin || !answeredAdmin) ? answer.match : null}
            onChange={(patch) => change(patch.scoreboard ? { ...patch, summary: null } : patch)}
          />
        </aside>

        <main className="dx-result" aria-label="Answer">
          {admin ? <AdminPanel answer={answer} updating={updating} failed={failed} /> : null}
          <Answer answer={answeredAdmin && !admin ? null : answer} updating={updating} failed={failed} current={current} onPage={setPage}
            sort={view.scoreboard ? view.scoreboard.sort : null}
            onSort={view.scoreboard ? (sort) => change({ scoreboard: { ...view.scoreboard, sort } }) : null} />
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
