// demo/frontend/sqlpane.jsx — the generated SQL, at rest, in full.
//
// B30 — the ruling this file obeys: THE STATEMENT AND BOTH PROBES, OPEN,
// IN FULL. The probe that did not run is stated in a comment rather than
// hidden. Nothing in here collapses, and there is no disclosure control
// to add: "the SQL on screen IS the query" is the demo's one claim, and a
// collapsed probe is a question the demo asked the database and did not
// show. That is also why design part 2 puts this pane LAST — it is the
// tallest content on the screen and above the answers it would push the
// thing the demo exists to show below the fold.
//   ONE LINE TO OVERTURN: "collapse the probes" — and the pane stops
//   being a statement of what ran.
//
// The pane text itself is the SERVER's (`sql.pane_text`): session values,
// probe (a), probe (b), then the pick's own query, each labelled with
// what happened. This file tokenises and colours it and adds nothing to
// it. D6 asks the pane to distinguish what arrived as a bind parameter
// from the one piece of user-typed text that reaches SQL text; the
// approved mock draws that as warm single-quoted values against a BOXED
// warm-2 identifier, and where D6's wording and the drawing differ the
// drawing is what Evan approved. The two spans below therefore carry
// BOTH vocabularies — `.s`/`.sql-bind` and `.alias`/`.sql-alias` — so
// part 5.2's inventory and the drawing are the same thing.

import { Ic } from "./icons.jsx";

const KW = new Set([
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "ORDER", "BY", "GROUP", "LIMIT",
  "AS", "OVER", "PARTITION", "ROWS", "BETWEEN", "PRECEDING", "CURRENT", "ROW",
  "CASE", "WHEN", "THEN", "ELSE", "END", "IS", "DISTINCT", "IN", "SET", "TIME",
  "ZONE", "AT", "ASC", "DESC", "NULLS", "LAST", "NULL", "ON", "WITH", "EXISTS",
]);
const FN = new Set([
  "count", "round", "avg", "abs", "lag", "sum", "min", "max", "to_jsonb",
  "jsonb_typeof", "nullif", "date_trunc", "to_char", "xpr.reduce_one",
  "xpr.num", "xpr.f8", "xpr.ord", "xpr.div", "xpr.truthy",
]);

const TOKEN =
  /('(?:[^']|'')*')|("[^"]*")|(\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)|(\s+)|([\s\S])/g;

function tokenise(line, keyPrefix) {
  if (/^\s*--/.test(line)) return [<span className="c" key={keyPrefix}>{line}</span>];
  const out = [];
  let m;
  TOKEN.lastIndex = 0;
  let i = 0;
  while ((m = TOKEN.exec(line)) !== null) {
    const k = keyPrefix + ":" + i++;
    if (m[1]) out.push(<span className="s sql-bind" key={k}>{m[1]}</span>);
    else if (m[2]) out.push(<span className="alias sql-alias" key={k}>{m[2]}</span>);
    else if (m[3]) out.push(<span className="n" key={k}>{m[3]}</span>);
    else if (m[4]) {
      const w = m[4];
      if (KW.has(w.toUpperCase()) && w === w.toUpperCase()) out.push(<span className="k" key={k}>{w}</span>);
      else if (FN.has(w)) out.push(<span className="f" key={k}>{w}</span>);
      else out.push(<span className="id" key={k}>{w}</span>);
    } else if (m[5]) out.push(m[5]);
    else out.push(<span className="o" key={k}>{m[6]}</span>);
  }
  return out;
}

/** The line the pick's own query starts at, so a never-sent statement can be greyed. */
function deadFrom(text, statementSent) {
  if (statementSent) return null;
  const lines = text.split("\n");
  const i = lines.findIndex((l) => l.indexOf("-- the pick's own query") === 0);
  return i < 0 ? null : i;
}

function Slab({ text, statementSent }) {
  const dead = deadFrom(text, statementSent);
  const lines = text.split("\n");
  return (
    <div className="sql-scroll">
      <pre className="sql sql-slab">
        {lines.map((line, i) => (
          <span className={dead != null && i >= dead ? "dead" : undefined} key={i}>
            {tokenise(line, String(i))}
            {i < lines.length - 1 ? "\n" : null}
          </span>
        ))}
      </pre>
    </div>
  );
}

// ── the alias check's five steps, in the order gate.py runs them ──────
const ALIAS_STEPS = [
  ['pattern — re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}")', "pattern"],
  ["length — 1 to 63 characters, Postgres's own limit", "pattern"],
  ["not a reserved name — collection, key, data, and the four the builder emits: agg, bucket, rolling_avg, changed", "reserved"],
  ["not a top-level field of the chosen collection, read out of the data at operation 1", "field"],
  ["not an alias already defined in this pick", "duplicate"],
];

/** Which of the five stopped it — classified from gate.py's own wording. */
function aliasStopAt(why) {
  const w = why || "";
  if (w.indexOf("is not a usable column name") >= 0 || w.indexOf("empty column name") >= 0) return 0;
  if (w.indexOf("already a column of the demo's own table") >= 0) return 2;
  if (w.indexOf("query builder emits itself") >= 0) return 2;
  if (w.indexOf("already a top-level field name") >= 0) return 3;
  if (w.indexOf("already defined as a computed column") >= 0) return 4;
  return 0;
}

const GW_ICON = { ok: "check", no: "x", skip: "dash" };

function GwRow({ state, node, why }) {
  return (
    <div className={"gw-row gw-" + state}>
      <span className="gw-mark"><Ic name={GW_ICON[state]} /></span>
      <span className="gw-node">{node}</span>
      <span className="gw-why">{why}</span>
    </div>
  );
}

/** V6's whole reason for existing: the text the check kept out. */
function NeverBuilt({ name, source }) {
  return (
    <div className="gw-never">
      <div className="gw-never-t">
        <Ic name="shield-stop" /> What the check kept out of the statement
      </div>
      <pre>
        <s>
          {"SELECT r.collection,\n       r.key,\n       r.data,\n       to_jsonb( … )  AS \""}
          <span className="hot">{name}</span>
          {"\"\n  FROM demo.records AS r\n WHERE r.collection = '" + source + "'"}
        </s>
      </pre>
      <p className="gw-never-s">
        <b>Never built, never prepared, never sent</b> — this is the text the check
        refused, printed so the control can be watched working rather than taken on
        trust. It is what <code>re.match</code> would have allowed:{" "}
        <code>re.match</code> anchors only the beginning, so it matches the leading
        letters, returns happily, and leaves everything after it to be pasted
        straight in. <b>re.fullmatch</b> is the whole difference.
      </p>
    </div>
  );
}

function GateWalk({ answer }) {
  const ref = answer.refusal;
  const pick = answer.pick || {};
  if (ref.kind === "alias") {
    const stop = aliasStopAt(ref.why);
    const bad = (pick.computed || []).find((c) => c && c.name === ref.construct);
    return (
      <div className="gatewalk">
        <div className="gw-title">What the alias check ran, in order</div>
        {ALIAS_STEPS.map(([text], i) => (
          <GwRow key={i}
                 state={i < stop ? "ok" : i === stop ? "no" : "skip"}
                 node={<><strong>{i + 1}</strong>&nbsp;&nbsp;{text}</>}
                 why={i < stop ? "passed" : i === stop ? "stopped here" : "not reached"} />
        ))}
        <NeverBuilt name={ref.construct} source={pick.source || ""} />
        <p className="gw-foot">
          <b>What the check said:</b> {ref.why}
          <br />
          The rule is an <b>allowlist</b>, for the same reason the expression gate is
          one. Escaping asks <em>“is there any input I have failed to neutralise?”</em>{" "}
          — open-ended, and answered wrongly the first time a case is missed. An
          allowlist asks <em>“is this one of the shapes already known to be safe?”</em>,
          so every future Unicode form and every driver quirk lands outside it and is
          refused. It <b>fails closed</b>, and it costs nothing real — <b>alive</b>,{" "}
          <b>busy</b>, <b>days_left</b> and <b>pct_ok</b> are all inside the pattern.
          {bad ? <> The expression on the right of the <code>=</code> was fine and was never the problem.</> : null}
        </p>
      </div>
    );
  }
  return (
    <div className="gatewalk">
      <div className="gw-title">What the gate saw</div>
      <GwRow state="no"
             node={<><strong>{ref.construct}</strong> <em>— the construct that stopped it</em></>}
             why="outside the safe subset" />
      <p className="gw-foot">
        <b>What the gate said:</b> {ref.why}
        <br />
        The gate is an <b>allowlist</b>, not a list of the refused names. A block-list
        goes stale the moment GIMS's expression language grows another function; an
        allowlist <b>fails closed</b> — the new construct is simply not among the
        thirty-two, and is refused until somebody deliberately adds it.
        <br />
        <em>
          The node-by-node walk the approved mock draws needs the parsed tree, which
          the API does not return; what is here is the node that stopped it and the
          rule it broke — which is what §9.3 asks the pane to name.
        </em>
      </p>
    </div>
  );
}

export function SqlPane({ answer }) {
  if (!answer) {
    return (
      <section className="panel sqlpanel" aria-label="The generated SQL">
        <div className="panel-head">
          <Ic name="terminal" />
          <span className="panel-title">The generated SQL</span>
        </div>
        <div className="sql-scroll">
          <pre className="sql sql-slab">
            <span className="c">-- No pick has been run yet, so no SQL has been generated.</span>
          </pre>
        </div>
      </section>
    );
  }

  const block = answer.sql || {};
  const ref = answer.refusal;
  const layerOne = !!(ref && ref.layer === 1);
  const pinned = answer.pinned || {};

  return (
    <section className="panel sqlpanel" aria-label="The generated SQL">
      <div className="panel-head">
        <Ic name="terminal" />
        <span className="panel-title">
          {layerOne ? "No SQL was generated" : "The generated SQL"}
        </span>
      </div>

      {layerOne ? <GateWalk answer={answer} /> : null}

      {block.pane_text ? <Slab text={block.pane_text} statementSent={block.statement_sent} /> : null}

      <div className="sql-foot">
        <p className="sql-foot-t">
          Shown with its bind parameters substituted in, so it reads as a real query.{" "}
          <b>What runs is the parameterised form</b> — every value and every JSON field
          name handed to Postgres separately. The boxed words are identifiers — column
          names, not values. Of them, only the alias you typed came from a person, and
          it is checked against a strict allowlist before it is emitted; SQL has no bind
          position for an identifier, which is why the check exists.
        </p>
        {/* The two session values live NOWHERE else on the screen (§9.3,
            AC-26). On a bucketed pick the time zone is the difference
            between seven buckets and eight, so it wears .chip.accent
            there — the mock's own `sessionHot`. */}
        <div className="session">
          <span className="chip">extra_float_digits = {pinned.extra_float_digits}</span>
          <span className={"chip" + (answer.shape === "BUCKET" ? " accent" : "")}>
            TimeZone = {pinned.time_zone}
          </span>
        </div>
      </div>
    </section>
  );
}
