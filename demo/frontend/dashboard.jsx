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
import { ColumnsStep, DatasetStep } from "./dashboard-steps.jsx";

const WAIT_BEFORE_ASKING = 250; // let a burst of clicks settle into one question

async function getJSON(url, init) {
  const r = await fetch(url, init);
  let body = null;
  try { body = await r.json(); } catch (_) { body = null; }
  if (!r.ok && !(body && body.kind)) throw new Error("bad answer");
  return body;
}

function viewFor(setup, datasetId) {
  const ds = setup.datasets.find((d) => d.id === datasetId);
  return {
    dataset: ds.id,
    columns: [...ds.default_columns],
    conditions: [],
    sort: null,
    show: null,
    summary: null,
  };
}

// ── the answer ───────────────────────────────────────────────────────────

function Cell({ value, kind }) {
  if (value === null || value === undefined) return <td className="dx-td is-blank">—</td>;
  const cls = kind === "number" ? " is-num" : kind === "time" || kind === "date" ? " is-when" : "";
  return <td className={"dx-td" + cls}><span className="dx-cell">{value}</span></td>;
}

function Table({ answer, onPage }) {
  const { columns, rows, page, total } = answer;
  if (!columns.length) {
    return <p className="dx-empty">Pick at least one column to see the rows.</p>;
  }
  const first = page.start + 1;
  const last = page.start + page.count;
  return (
    <>
      <div className="dx-table-box" tabIndex={0} aria-label="Rows">
        <table className="dx-table">
          <thead>
            <tr>{columns.map((c) => <th key={c.path} className={c.kind === "number" ? "is-num" : ""}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={page.start + i}>
                {r.map((v, j) => <Cell key={j} value={v} kind={columns[j].kind} />)}
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
          <button type="button" className="dx-btn" data-page="prev" disabled={page.index === 0} onClick={() => onPage(page.index - 1)}>Previous</button>
          <button type="button" className="dx-btn" data-page="next" disabled={page.index >= page.last} onClick={() => onPage(page.index + 1)}>Next</button>
        </span>
      </nav>
    </>
  );
}

function Answer({ answer, updating, failed, onPage }) {
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
        <h2 className="dx-sentence" data-testid="sentence">{answer.sentence}</h2>
        <p className="dx-status" aria-live="polite">{updating ? "Updating…" : ""}</p>
      </div>
      {answer.kind === "refused" ? (
        <p className="dx-problem" role="alert">{answer.message}</p>
      ) : answer.kind === "invalid" ? (
        <p className="dx-problem" role="alert">{answer.message}</p>
      ) : answer.total === 0 ? (
        <div className="dx-nothing">
          <p className="dx-nothing-title">No rows match</p>
          <p className="dx-nothing-hint">Try removing a condition.</p>
        </div>
      ) : (
        <Table answer={answer} onPage={onPage} />
      )}
    </div>
  );
}

// ── the phone's folded question ──────────────────────────────────────────

function summaryLine(setup, view) {
  const ds = setup.datasets.find((d) => d.id === view.dataset);
  const parts = [ds.name];
  parts.push(view.columns.length === 1 ? "1 column" : `${view.columns.length} columns`);
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

  const seq = useRef(0);
  const inflight = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    getJSON("/api/dashboard/setup")
      .then((s) => { setSetup(s); setView(s.default_view); })
      .catch(() => setSetupFailed(true));
  }, []);

  const ask = useCallback((v, p) => {
    const mine = ++seq.current;
    if (inflight.current) inflight.current.abort();
    const ctl = new AbortController();
    inflight.current = ctl;
    setUpdating(true);
    getJSON("/api/dashboard/answer", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ view: v, page: p }),
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

  // A changed question waits a moment for the clicks to settle; a page
  // turn is asked at once (the server remembers the whole answer).
  const lastView = useRef(null);
  useEffect(() => {
    if (!view) return;
    clearTimeout(timer.current);
    const sameQuestion = lastView.current === view;
    lastView.current = view;
    if (sameQuestion || answer === null) {
      ask(view, page);
      return;
    }
    // Mark the answer as out of date the moment the question changes,
    // not only once the request leaves.
    seq.current += 1;
    if (inflight.current) inflight.current.abort();
    setUpdating(true);
    timer.current = setTimeout(() => ask(view, page), WAIT_BEFORE_ASKING);
    return () => clearTimeout(timer.current);
  }, [view, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const change = useCallback((patch) => {
    setPage(0);
    setView((v) => ({ ...v, ...patch }));
  }, []);

  const ds = useMemo(
    () => (setup && view ? setup.datasets.find((d) => d.id === view.dataset) : null),
    [setup, view],
  );

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
            onPick={(id) => { if (id !== view.dataset) { setPage(0); setView(viewFor(setup, id)); } }}
          />
          <ColumnsStep
            fields={ds.fields}
            value={view.columns}
            onChange={(columns) => change({ columns })}
          />
        </aside>

        <main className="dx-result" aria-label="Answer">
          <Answer answer={answer} updating={updating} failed={failed} onPage={setPage} />
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
