// demo/frontend/panes.jsx — the side-by-side. D5, B25, B29, B31, D8.
//
// ONE framed surface, TWO halves, ONE spine down the middle. Not two
// frames: the spine is where the per-row ✓ / ≠ mark lives (D8) and two
// independent frames have nowhere to put it. Equal width, equal height,
// SQL left and Python right, fixed — B29, and D5's "neither collapsible,
// hideable, reorderable or stackable". There is no collapse affordance
// anywhere in this file and AC-20's contract test asserts there is not.
//
// B25 — what is compared and what is shown are different things:
//   the COMPARISON is over the whole result, on the server, with no
//   tolerance; the RENDER is a page of at most 50 rows. The count pill
//   shows the true total and the note under each pane says which page it
//   is looking at, so nobody can mistake a page for the answer. When the
//   first differing row is past the page, the server starts the page five
//   rows before it — a disagreement is never below the fold of a
//   paginator.
//
// B31 place 2 of 3 — the `invented` chip in EACH pane head. The mock's
// two invented-data labels both live in the page header, and a screenshot
// of these two panes alone (which is exactly what gets pasted into a
// message) carries neither. This is the one addition to the approved
// drawing that this build makes deliberately.
//   ONE LINE TO OVERTURN: "the header chip is enough" — delete the
//   <InventedChip/> below and the .pane-invented rule in demo.css.

import { useEffect, useRef } from "react";
import { StateBlock } from "../vendor/ui.jsx";
import { Ic } from "./icons.jsx";

function nf(n) {
  return typeof n === "number" ? n.toLocaleString("en-US") : String(n);
}

function InventedChip() {
  return (
    <span className="chip warn pane-invented" title="Every record in this pane is invented data.">
      invented
    </span>
  );
}

// ── column widths, derived from the answer rather than hand-tuned ─────
function widthFor(name, kind) {
  if (name === "collection") return "132px";
  if (name === "key") return "118px";
  if (name === "bucket") return "minmax(150px,1fr)";
  if (name === "data") return "minmax(220px,2.4fr)";
  if (kind === "exact" || kind === "int") return "112px";
  return "minmax(110px,1fr)";
}
function narrowFor(name, kind) {
  if (name === "collection") return "108px";
  if (name === "key") return "104px";
  if (name === "data") return "minmax(150px,2fr)";
  if (kind === "exact" || kind === "int") return "96px";
  return "minmax(88px,1fr)";
}
function template(columns, kinds, fn) {
  return columns.map((c, i) => fn(c, kinds[i])).join(" ");
}

// ── one cell's tone, from the server's own type tag ───────────────────
function toneClass(tag, column, value) {
  switch (tag) {
    case "number":
      return "cell-num";
    case "number-nonfinite":
      return "cell-num cell-warn";
    case "null":
      return "cell-null cell-num";
    case "boolean":
      return "cell-bool " + (value === "true" ? "cell-t" : "cell-f");
    case "string":
      if (column === "key") return "cell-key";
      if (column === "status")
        return "cell " + (value === "ok" ? "st-ok" : value === "warn" ? "st-warn" : "st-error");
      return "cell-mono";
    default:
      return "cell-mono";
  }
}

function Cell({ value, tag, column, isDiff }) {
  const inner = isDiff ? <span className="diffcell">{value}</span> : value;
  return (
    <span className={toneClass(tag, column, value)} title={value}>
      {inner}
    </span>
  );
}

function PaneHead({ side, sub, count, col, row }) {
  const isSql = side === "sql";
  return (
    <div className="cmp-cell pane-head" style={{ gridColumn: col, gridRow: row }}>
      <span className="icon-chip"><Ic name={isSql ? "terminal" : "python"} /></span>
      <span>
        <span className="pane-name">
          {isSql ? "SQL — Postgres" : "Python — in‑memory"}
          <InventedChip />
        </span>
        <span className="pane-sub">{sub}</span>
      </span>
      {count ? <span className="count-pill pane-count">{count}</span> : null}
    </div>
  );
}

function MobileSep() {
  return (
    <div className="mobile-sep">
      <Ic name="dash" /> the same pick, answered the other way
    </div>
  );
}

/** A whole-pane refusal, in GIMS's own state block with D4's amber modifier. */
function RefusedPane({ title, body, rows }) {
  return (
    <div className="pane-refused">
      <div className="refused-head">
        <span className="icon-chip"><Ic name="warning" /></span>
        <span className="refused-t">{title}</span>
      </div>
      <div className="refused-body">{body}</div>
      {rows ? <div className="refused-rows">{rows}</div> : null}
    </div>
  );
}

export function Panes({ answer, hot, setHot }) {
  const gridRef = useRef(null);
  const first = answer && answer.comparison ? answer.comparison.first_differing_index : null;

  // D8: the pair opens AT the disagreement, in both panes.
  useEffect(() => {
    if (first == null || !gridRef.current) return;
    const el = gridRef.current.querySelector('[data-r="' + first + '"]');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "center", behavior: "auto" });
  }, [answer, first]);

  // ── before the first pick — GIMS's canonical empty state, verbatim ──
  if (!answer) {
    return (
      <section className="panel cmp" aria-label="The same pick, two answers">
        <div className="panel-head">
          <Ic name="columns" />
          <span className="panel-title">The same pick, two answers</span>
          <div className="cmp-head-right"><span className="chip">nothing run yet</span></div>
        </div>
        <div className="cmp-scroll">
          <div className="cmp-grid pane-pair" style={{ "--cols": "1fr" }}>
            <PaneHead side="sql" sub="waiting for a pick" count="" col={1} row={1} />
            <div className="cmp-cell" style={{ gridColumn: 1, gridRow: 2 }}>
              <StateBlock kind="empty" title="No pick yet"
                          message="Choose a source on the left and press Run pick." />
            </div>
            <div className="cmp-cell spine spine-head" style={{ gridColumn: 2, gridRow: 1 }}>
              <span className="spine-mark">vs</span>
            </div>
            <div className="cmp-cell spine spine-band" style={{ gridColumn: 2, gridRow: 2 }} />
            <MobileSep />
            <PaneHead side="py" sub="waiting for a pick" count="" col={3} row={1} />
            <div className="cmp-cell" style={{ gridColumn: 3, gridRow: 2 }}>
              <StateBlock kind="empty" title="No pick yet"
                          message="Choose a source on the left and press Run pick." />
            </div>
          </div>
        </div>
      </section>
    );
  }

  const sql = answer.panes.sql;
  const py = answer.panes.python;
  const cmp = answer.comparison;
  const page = answer.page || {};
  const differs = cmp.verdict === "disagree";
  const bothAnswered = sql.state === "answered" && py.state === "answered";

  // The head chip — three states, three words, never colour alone.
  let headChip;
  if (answer.refusal) headChip = <span className="chip warn">refused{answer.refusal.layer === 2 ? " at the probe" : ""}</span>;
  else if (differs)
    headChip = (
      <span className="chip bad">
        {nf(cmp.differing_rows)} {cmp.differing_rows === 1 ? "row differs" : "rows differ"}
      </span>
    );
  else
    headChip = (
      <span className="chip ok">
        {nf(cmp.compared_rows)} of {nf(cmp.compared_rows)} identical
      </span>
    );

  const shown = (p) => (p.rows || []).length;
  const subFor = (p) => {
    if (p.state !== "answered") return "the pick was declined";
    if (shown(p) < p.row_count)
      return `showing ${nf(page.start + 1)}–${nf(page.start + shown(p))} of ${nf(p.row_count)}, ordered by ${page.ordered_by || "key"}`;
    return `${nf(p.row_count)} ${p.row_count === 1 ? "row" : "rows"}, ordered by ${page.ordered_by || "key"}`;
  };

  const columns = bothAnswered ? sql.columns : sql.columns.length ? sql.columns : py.columns;
  const kinds = bothAnswered ? sql.kinds : sql.kinds.length ? sql.kinds : py.kinds;
  const n = bothAnswered ? Math.max(shown(sql), shown(py)) : shown(py);
  const lastRow = 2 + n; // header = 1, column head = 2, data = 3 … 2+n

  const style = {
    "--cols": columns.length ? template(columns, kinds, widthFor) : "1fr",
    "--cols-m": columns.length ? template(columns, kinds, narrowFor) : "1fr",
  };

  // q8 (Evan, GA-8): "move the differing column beside the marker".  The server
  // publishes the permutation; this view only follows it.  The grid is
  // [SQL | spine | Python], so the two orders are mirrored about the spine and
  // each pane needs its OWN track template — hence the inline --cols here,
  // which overrides the container's for that pane's rows only.
  const natural = columns.map((_, j) => j);
  const orders = answer && answer.column_order
    ? answer.column_order
    : { sql: natural, python: natural };
  const orderOf = (side) =>
    (orders && orders[side] && orders[side].length === columns.length)
      ? orders[side]
      : natural;

  const tracksFor = (order) => ({
    "--cols": columns.length
      ? order.map((j) => widthFor(columns[j], kinds[j])).join(" ") : "1fr",
    "--cols-m": columns.length
      ? order.map((j) => narrowFor(columns[j], kinds[j])).join(" ") : "1fr",
  });

  const ColHead = ({ col, side }) => {
    const order = orderOf(side);
    return (
      <div className="cmp-cell rowcells colhead"
           style={{ gridColumn: col, gridRow: 2, ...tracksFor(order) }}>
        {order.map((j) => <span key={columns[j]}>{columns[j]}</span>)}
      </div>
    );
  };

  const DataRows = ({ col, pane, side }) => {
    const order = orderOf(side);
    const tracks = tracksFor(order);
    return (pane.rows || []).map((r, i) => (
      <div
        key={r.i}
        className={
          "cmp-cell rowcells datarow" +
          (i % 2 ? " alt" : "") +
          (r.diff ? " diff" : "") +
          (hot === r.i ? " hot" : "")
        }
        data-r={r.i}
        style={{ gridColumn: col, gridRow: 3 + i, "--i": i, ...tracks }}
        onMouseEnter={() => setHot(r.i)}
        onMouseLeave={() => setHot(null)}
      >
        {order.map((j) => (
          <Cell key={j} value={r.c[j]} tag={r.t[j]} column={columns[j]}
                isDiff={!!(r.diff && r.diff.indexOf(j) >= 0)} />
        ))}
      </div>
    ));
  };

  const Note = ({ col, text }) => (
    <div className="cmp-cell pane-note" style={{ gridColumn: col, gridRow: lastRow + 1 }}>
      {text}
    </div>
  );

  let cells;
  if (!bothAnswered && sql.state === "not-asked") {
    // ── both panes empty: a layer-1 refusal, before any SQL existed ──
    const empty = (col, note) => (
      <div className="cmp-cell" style={{ gridColumn: col, gridRow: 2 }}>
        <div className="pane-empty">
          <span className="icon-chip"><Ic name="lock" /></span>
          <span className="pane-empty-t">No result</span>
          <span className="pane-empty-s">
            The pick was declined before a statement existed, so there is nothing
            for either side to answer.
          </span>
        </div>
        <div className="pane-note">{note}</div>
      </div>
    );
    cells = (
      <>
        <PaneHead side="sql" sub="the pick was declined" count="" col={1} row={1} />
        {empty(1, sql.note)}
        <div className="cmp-cell spine spine-head" style={{ gridColumn: 2, gridRow: 1 }}>
          <span className="spine-mark">vs</span>
        </div>
        <div className="cmp-cell spine spine-band" style={{ gridColumn: 2, gridRow: 2 }} />
        <MobileSep />
        <PaneHead side="py" sub="the pick was declined" count="" col={3} row={1} />
        {empty(3, py.note)}
      </>
    );
  } else if (!bothAnswered) {
    // ── layer 2: SQL abandoned. Python answers, or says it cannot ────
    const ref = answer.refusal || {};
    const span = "2 / " + (lastRow + 2);
    cells = (
      <>
        <PaneHead side="sql" sub="no answer for this pick" count="" col={1} row={1} />
        <div className="cmp-cell" style={{ gridColumn: 1, gridRow: span }}>
          <RefusedPane
            title="No number to show."
            body={sql.note}
            rows={
              ref.row_key
                ? <>
                    <span>first offending row · key</span> {ref.row_key}
                    {ref.member ? <> · <span>probe</span> ({ref.member})</> : null}
                  </>
                : null
            }
          />
        </div>
        <div className="cmp-cell spine spine-head" style={{ gridColumn: 2, gridRow: 1 }}>
          <span className="spine-mark">vs</span>
        </div>
        <div className="cmp-cell spine" style={{ gridColumn: 2, gridRow: span }} />
        <MobileSep />
        <PaneHead side="py"
                  sub={py.state === "answered" ? "answered, and labelled as a fallback" : "could not read it either"}
                  count={py.state === "answered" ? nf(py.row_count) + " rows" : ""}
                  col={3} row={1} />
        {py.state === "answered" ? (
          <>
            <ColHead col={3} side="python" />
            <DataRows col={3} pane={py} side="python" />
            <Note col={3} text={py.note} />
          </>
        ) : (
          <div className="cmp-cell" style={{ gridColumn: 3, gridRow: span }}>
            <RefusedPane title="Neither engine can represent it." body={py.note} rows={null} />
          </div>
        )}
      </>
    );
  } else {
    // ── both sides answered: the state the screen is in nine times in ten ──
    cells = (
      <>
        <PaneHead side="sql" sub={subFor(sql)} count={nf(sql.row_count) + (sql.row_count === 1 ? " row" : " rows")} col={1} row={1} />
        <ColHead col={1} side="sql" />
        <DataRows col={1} pane={sql} side="sql" />
        <Note col={1} text={sql.note} />

        <div className="cmp-cell spine spine-head" style={{ gridColumn: 2, gridRow: 1 }}>
          <span className="spine-mark">vs</span>
        </div>
        <div className={"cmp-cell spine spine-band" + (differs ? "" : " spine-ok")}
             style={{ gridColumn: 2, gridRow: 2 }} />
        {(sql.rows || []).map((r, i) => {
          const isDiff = !!r.diff;
          return (
            <div key={r.i}
                 className={"cmp-cell spine " + (isDiff ? "spine-diff" : "spine-ok") + (hot === r.i ? " hot" : "")}
                 data-r={r.i}
                 style={{ gridColumn: 2, gridRow: 3 + i }}
                 onMouseEnter={() => setHot(r.i)}
                 onMouseLeave={() => setHot(null)}>
              <span className="spine-mark">{isDiff ? "≠" : <Ic name="check" />}</span>
            </div>
          );
        })}
        <div className={"cmp-cell spine" + (differs ? "" : " spine-ok")}
             style={{ gridColumn: 2, gridRow: lastRow + 1 }} />

        <MobileSep />
        <PaneHead side="py" sub={subFor(py)} count={nf(py.row_count) + (py.row_count === 1 ? " row" : " rows")} col={3} row={1} />
        <ColHead col={3} side="python" />
        <DataRows col={3} pane={py} side="python" />
        <Note col={3} text={py.note} />
      </>
    );
  }

  return (
    <section className={"panel cmp" + (differs ? " is-diff" : "")}
             aria-label="The same pick, two answers">
      <div className="panel-head">
        <Ic name="columns" />
        <span className="panel-title">The same pick, two answers</span>
        <div className="cmp-head-right">{headChip}</div>
      </div>
      <div className="cmp-scroll">
        <div className="cmp-grid pane-pair" style={style} ref={gridRef}>
          {cells}
        </div>
      </div>
    </section>
  );
}
