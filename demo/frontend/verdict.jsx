// demo/frontend/verdict.jsx — the verdict banner. DR-1's first of three
// independent signals, and the one that carries the WORDS.
//
// DR-1 says a disagreement must be impossible to miss by someone who is
// not expecting one, with all animation disabled. So: colour AND icon AND
// a sentence, never one of the three alone; never dismissible, never
// collapsible, never a toast; and at the top of the working area, above
// everything it describes (design part 2).
//
// B28 — the ruling this file exists to obey: the banner is on EVERY
// accepted pick, green, reading BOTH PANES AGREE. Not only when the
// answers differ. A strip that appears only on disagreement is a strip
// nobody has learned to read.
//   ONE LINE TO OVERTURN: "only speak when they differ" — delete the
//   `agree` branch below and the banner renders in coral and amber only.

import { Ic } from "./icons.jsx";

const TONE = { agree: "ok", disagree: "bad", "no-compare": "warn" };

//: The refusal icon says WHICH check, not just that one fired — V5, V6
//: and V7 are adjacent on purpose and a reader must tell them apart.
const REFUSAL_ICON = { expression: "shield-stop", alias: "lock", probe: "warning" };

function nf(n) {
  return typeof n === "number" ? n.toLocaleString("en-US") : String(n);
}

function Num({ children }) {
  return <span className="num">{children}</span>;
}

/** The differing cell, in words: "row 1, column `biggest` — SQL 1, Python 1e+300". */
function DiffDetail({ answer }) {
  const c = answer.comparison;
  const i = c.first_differing_index;
  if (i == null) return null;
  const sql = answer.panes.sql;
  const py = answer.panes.python;
  const find = (p) => (p.rows || []).find((r) => r.i === i);
  const rs = find(sql);
  const rp = find(py);
  const cols = rs && rs.diff ? rs.diff : [];
  const key = rs && sql.columns.indexOf("key") >= 0 ? rs.c[sql.columns.indexOf("key")] : null;
  return (
    <p>
      The first of them is <b>row {nf(i)}</b>
      {key ? <> — key <code>{key}</code></> : null}
      {cols.map((j) => (
        <span key={j}>
          , column <code>{sql.columns[j]}</code>: SQL says{" "}
          <Num>{rs ? rs.c[j] : "—"}</Num>, Python says <Num>{rp ? rp.c[j] : "—"}</Num>
        </span>
      ))}
      . Both panes are marked on that row, and the pair below opens at it — a
      disagreement is <b>located</b>, not merely announced.
    </p>
  );
}

export function Verdict({ answer, preset }) {
  if (!answer) {
    return (
      <div className="verdict">
        <div className="verdict-top">
          <span className="verdict-ico"><Ic name="dash" /></span>
          <h2>No pick has been run yet.</h2>
        </div>
        <div className="verdict-body">
          <p>
            Choose a source on the left and press <b>Run this pick</b>. The two
            answers are computed from the same rows by two independent
            calculators, and this strip states whether they agreed —{" "}
            <b>on every accepted pick</b>, not only when they differ.
          </p>
        </div>
      </div>
    );
  }

  const v = answer.verdict;
  const c = answer.comparison;
  const ref = answer.refusal;
  const tone = TONE[v] || "warn";

  let icon = "check";
  let head = "";
  let body = null;

  if (v === "agree") {
    icon = "check";
    head = "Both panes agree, to the digit.";
    body = (
      <>
        <p>
          <b>{nf(c.compared_rows)}</b> {c.compared_rows === 1 ? "row" : "rows"} compared,{" "}
          <b>{nf(c.compared_rows)}</b> identical — value for value, column for column,
          over the <b>whole</b> result and not the page below it. There is no
          tolerance anywhere in the comparison: two numbers agree when they are
          the same number.
        </p>
        <p>
          Both sides round half&#8209;up to six decimal places, which is why a value
          like <Num>48.333333</Num> is the same six digits in both panes rather
          than nearly the same.
        </p>
      </>
    );
  } else if (v === "disagree") {
    icon = "neq";
    head =
      c.differing_rows === 1
        ? "The panes disagree on one row."
        : `The panes disagree on ${nf(c.differing_rows)} rows.`;
    body = (
      <>
        <p>
          Of <b>{nf(c.compared_rows)}</b> rows compared, <b>{nf(c.differing_rows)}</b>{" "}
          {c.differing_rows === 1 ? "differs" : "differ"}. <b>Nothing on the SQL side
          reported an error</b> — on its own it returned a plausible number. This is
          the finding, not a fault the demo suffered, and it is the entire reason
          both answers are on screen.
        </p>
        <DiffDetail answer={answer} />
      </>
    );
  } else {
    const kind = (ref && ref.kind) || "probe";
    icon = REFUSAL_ICON[kind] || "warning";
    head = (ref && ref.headline) || "The pick was refused.";
    body = (
      <>
        <p>{ref ? ref.body : "The pick was declined before it could produce a number."}</p>
        {ref && ref.why ? (
          <p>
            <b>What the check said:</b> <code>{ref.why}</code>
          </p>
        ) : null}
        <p>
          {ref && ref.sql_existed
            ? "SQL existed and a probe fired: the database was asked one question ahead of the pick, and it answered in a way that makes the pick unanswerable. The statement itself was never sent."
            : "No SQL was generated, no statement was prepared, and nothing was sent to the database."}{" "}
          This is a correct outcome — the enforcement working as designed — which
          is why it wears amber and not coral.
        </p>
      </>
    );
  }

  return (
    <div className={"verdict t-" + tone} role="status" aria-live="polite">
      <div className="verdict-top">
        <span className="verdict-ico"><Ic name={icon} /></span>
        <h2>{head}</h2>
      </div>
      <div className="verdict-body">{body}</div>
      {preset && preset.ref ? (
        <div className="verdict-ref" dangerouslySetInnerHTML={{ __html: preset.ref }} />
      ) : null}
    </div>
  );
}
