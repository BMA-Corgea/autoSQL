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
  let i = 0, j = 0;
  while (j < m) {
    if (i < n && a[i] === b[j]) { i++; j++; }
    else if (i < n && L[i + 1][j] >= L[i][j + 1]) i++;
    else { changed.add(j); j++; }
  }
  return changed;
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
    const what = kind === "table"
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
  return <p className="dx-checked is-none" data-testid="checked">Not double-checked: this one was refused before an answer existed.</p>;
}

// Open or folded: remembered for the visit (T-72, Q2 "admins, folded
// away"). Storage that refuses means the panel simply starts folded.
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
      {open && !failed ? (
        <div id="dx-sql-body">
          {admin.refusal ? (
            <p className="dx-admin-refusal"><strong>{admin.refusal.headline}.</strong> {admin.refusal.why}</p>
          ) : null}
          {statement ? (
            <>
              <pre className="dx-sql" data-testid="statement" aria-live="polite">
                {lines.map((line, i) => (
                  <span key={`${fresh.round}:${i}`} className={"dx-sql-line" + (fresh.set.has(i) ? " is-new" : "")}>{line + "\n"}</span>
                ))}
              </pre>
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
    </section>
  );
}
