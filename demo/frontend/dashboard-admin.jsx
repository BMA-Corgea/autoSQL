// dashboard-admin.jsx — what View as: Admin adds (T-71 S4, AC10).
//
// The panel shows the statement the clicks wrote, and it rewrites itself in
// place as the picks change: the lines that changed are marked for a moment,
// so an admin can watch the statement follow each click. The statement is
// shown with its values written in, for reading; the panel says plainly that
// the database receives them separately, and shows that form too.
//
// None of this is drawn in the Everyone view (AC9): the words here are for
// the people who asked for them.

import React, { useEffect, useRef, useState } from "react";

// Which lines of `next` are not in `prev`, in order (a longest common
// subsequence over whole lines; statements are a few dozen lines).
export function changedLines(prev, next) {
  const a = prev || [], b = next || [];
  const n = a.length, m = b.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const changed = new Set();
  // Lines of the old statement with no place in the new one: marked at the
  // new line they would have stood before (m = after the last line), so a
  // removal shows as well as an addition (T-75).
  const removedBefore = new Map();
  let i = 0, j = 0;
  while (j < m || i < n) {
    if (i < n && j < m && a[i] === b[j]) { i++; j++; }
    else if (i < n && (j >= m || L[i + 1][j] >= L[i][j + 1])) {
      removedBefore.set(j, (removedBefore.get(j) || 0) + 1); i++;
    }
    else { changed.add(j); j++; }
  }
  // A removal right where a line changed is often that line's edit (the
  // last column goes, and its neighbour loses a comma): each changed line
  // at the spot absorbs one removed line, so "− 1 line removed" counts the
  // column, not the comma.
  // An edited line is one removed plus one changed: it shows as changed
  // only, with no removal marker.
  for (const [at, count] of [...removedBefore]) {
    let run = 0;
    while (changed.has(at + run)) run += 1;
    const left = count - run;
    if (left > 0) removedBefore.set(at, left);
    else removedBefore.delete(at);
  }
  changed.removedBefore = removedBefore;
  return changed;
}

function Removed({ count }) {
  return (
    <span className="dx-sql-removed" data-testid="removed" aria-label={`${count} ${count === 1 ? "line" : "lines"} removed here`}>
      {"− " + count + (count === 1 ? " line removed\n" : " lines removed\n")}
    </span>
  );
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }
}

function Checked({ admin, kind }) {
  if (admin.verdict === "agree") {
    // A table and a scoreboard both say how many rows were checked (T-77).
    const what = kind === "table" || kind === "scoreboard"
      ? `the same ${admin.compared_rows.toLocaleString("en-US")} ${admin.compared_rows === 1 ? "row" : "rows"}`
      : "the same answer";
    return (
      <p className="dx-checked" data-testid="checked">
        <span aria-hidden="true">✓</span> Double-checked — a second engine computed {what} from the source data.
      </p>
    );
  }
  if (admin.verdict === "disagree") {
    return (
      <div className="dx-disagree" role="alert" data-testid="disagree">
        <strong>The two engines disagree.</strong> {admin.differing_rows.toLocaleString("en-US")} of {admin.compared_rows.toLocaleString("en-US")} rows differ.
        This answer may be wrong — open the two-pane screen to see where.
      </div>
    );
  }
  // The server says why, true to what happened: the statement may have
  // answered and the second engine not (T-79).
  return <p className="dx-checked is-none" data-testid="checked">{admin.unchecked || "Not double-checked."}</p>;
}

// Open or folded: remembered for the visit (T-72: admins see the SQL,
// folded away). Storage that refuses means the panel simply starts folded.
const SQL_OPEN_KEY = "autosql.dashboard.sql-open";
function loadOpen() {
  try { return window.localStorage.getItem(SQL_OPEN_KEY) === "open"; } catch (_) { return false; }
}
function saveOpen(open) {
  try { window.localStorage.setItem(SQL_OPEN_KEY, open ? "open" : "folded"); } catch (_) { /* not remembered */ }
}

export function AdminPanel({ answer, updating, failed }) {
  const admin = answer && answer.admin;
  const statement = admin ? admin.statement : null;
  const lines = statement ? statement.split("\n") : [];
  const prev = useRef(null);
  const [fresh, setFresh] = useState({ set: new Set(), round: 0 });
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(loadOpen);
  const [tall, setTall] = useState(false);   // the whole statement, unclipped
  const [clipped, setClipped] = useState(false);
  const sqlBox = useRef(null);
  // "Show all" is offered only when the box actually cuts the statement off.
  useEffect(() => {
    const el = sqlBox.current;
    if (!el) return undefined;
    const measure = () => setClipped(el.scrollHeight > el.clientHeight + 1);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  });

  useEffect(() => {
    if (statement === prev.current) return undefined;
    const before = prev.current;
    prev.current = statement;
    if (before === null || statement === null) return undefined;
    setFresh((f) => ({ set: changedLines(before.split("\n"), statement.split("\n")), round: f.round + 1 }));
    return undefined;
  }, [statement]);

  if (!admin) return null;
  const params = admin.parameters || [];
  // The panel only ever presents the statement that produced the answer on
  // screen as current. While a newer question is out it is dimmed and says
  // so, with no double-checked mark and nothing to copy; after a failed
  // request it shows no statement at all. The mark (or the line standing
  // in for it) shows whether the SQL is folded or open.
  const current = !updating && !failed;
  const toggle = () => { setOpen(!open); saveOpen(!open); };
  return (
    <section className={"dx-admin" + (updating ? " is-updating" : "") + (failed ? " is-stale" : "") + (open ? " is-open" : " is-folded")}
      aria-label="SQL for this view" data-testid="admin" aria-busy={updating}>
      <header className="dx-admin-head">
        <button type="button" className="dx-btn dx-btn-small dx-fold-sql" data-action="toggle-sql"
          aria-expanded={open} aria-controls="dx-sql-body" onClick={toggle}>
          {open ? "Hide SQL" : "Show SQL"}
        </button>
        <span className="dx-admin-actions">
          {open && statement && !failed ? (
            <button type="button" className="dx-btn dx-btn-small" data-action="copy" disabled={!current}
              onClick={async () => { setCopied(await copyText(statement)); setTimeout(() => setCopied(false), 1800); }}>
              {copied ? "Copied" : "Copy"}
            </button>
          ) : null}
          <a className="dx-link" href="/" data-testid="two-pane">Two-pane screen →</a>
        </span>
      </header>
      {failed ? (
        <p className="dx-admin-stale" data-testid="stale">No statement to show: the last request didn't get through, so nothing here would match these choices.</p>
      ) : current ? <Checked admin={admin} kind={answer.kind} /> : (
        <p className="dx-admin-stale" data-testid="stale">Updating — {open ? "below is" : "the SQL holds"} the statement for the previous choices.</p>
      )}
      {/* The fold's target always exists; it is hidden while folded (T-75). */}
      <div id="dx-sql-body" hidden={!open || failed}>
      {open && !failed ? (
        <div>
          {(admin.notes || []).map((n) => <p key={n} className="dx-admin-note-loud" data-testid="admin-note">{n}</p>)}
          {admin.refusal ? (
            <p className="dx-admin-refusal"><strong>{admin.refusal.headline}.</strong> {admin.refusal.why}</p>
          ) : null}
          {statement ? (
            <>
              <pre ref={sqlBox} className={"dx-sql" + (tall ? " is-tall" : "")} data-testid="statement" aria-live="polite">
                {lines.map((line, i) => (
                  <React.Fragment key={`${fresh.round}:${i}`}>
                    {fresh.set.removedBefore && fresh.set.removedBefore.get(i) ? <Removed count={fresh.set.removedBefore.get(i)} /> : null}
                    <span className={"dx-sql-line" + (fresh.set.has(i) ? " is-new" : "")}>{line + "\n"}</span>
                  </React.Fragment>
                ))}
                {fresh.set.removedBefore && fresh.set.removedBefore.get(lines.length) ? <Removed count={fresh.set.removedBefore.get(lines.length)} /> : null}
              </pre>
              {tall || clipped ? (
                <button type="button" className="dx-link dx-sql-tall" data-action="sql-tall" onClick={() => setTall(!tall)}>
                  {tall ? "Show less" : `Show all ${lines.length} lines`}
                </button>
              ) : null}
              <p className="dx-admin-note">
                The values are written into the statement above so it reads plainly. The database never receives it that way:
                it gets the statement with placeholders, and {params.length === 1 ? "one value" : `these ${params.length} values`} separately, as parameters.
              </p>
              <details className="dx-sent">
                <summary>The statement as the database receives it</summary>
                <pre className="dx-sql">{admin.parameterised}</pre>
                <table className="dx-params">
                  <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
                  <tbody>{params.map((p) => <tr key={p.name}><td>{p.name}</td><td>{p.value}</td></tr>)}</tbody>
                </table>
              </details>
            </>
          ) : (
            <p className="dx-admin-note">No statement was written for these choices.</p>
          )}
        </div>
      ) : null}
      </div>
    </section>
  );
}
