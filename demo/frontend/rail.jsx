// demo/frontend/rail.jsx — GATE ▸ COMPILE ▸ PROBES ▸ EXECUTE.
//
// Four stops, the one that stopped marked. It answers "how far did this
// pick get" in one glance, which is the difference §9.3 asks the screen
// to make between a layer-1 and a layer-2 refusal: "we never asked the
// database" against "we asked, and it told us to stop".
//
// Every word below is derived from the response — the refusal payload,
// the probe outcomes and the row counts. The rail states nothing the
// server did not say.

import { Ic } from "./icons.jsx";

const STOP_ICON = { done: "check", stop: "x", skip: "dash", none: "dash" };

function nf(n) {
  return typeof n === "number" ? n.toLocaleString("en-US") : String(n);
}

/** How many expressions this pick actually put through the gate. */
function expressionCount(pick) {
  if (!pick) return 0;
  const cc = (pick.computed || []).filter((c) => c && (c.expr || "").trim()).length;
  return cc + ((pick.filter || "").trim() ? 1 : 0);
}

export function stopsFor(answer) {
  if (!answer) {
    return [
      ["none", "Gate", "no pick run yet"],
      ["none", "Compile", "nothing to compile"],
      ["none", "Probes", "no operand to ask about"],
      ["none", "Execute", "nothing sent"],
    ];
  }
  const ref = answer.refusal;
  const probes = (answer.sql && answer.sql.probes) || [];
  const n = expressionCount(answer.pick);
  const fired = probes.find((p) => p.fired);

  // ── GATE — layer 1, and the alias check that shares the layer ──────
  let gate;
  if (ref && ref.layer === 1 && ref.kind === "expression") {
    gate = ["stop", "Gate", `${ref.construct} is outside the safe subset`];
  } else if (ref && ref.layer === 1 && ref.kind === "alias") {
    gate = ["stop", "Gate", "the column name is not a usable identifier"];
  } else if (n === 0) {
    gate = ["none", "Gate", "no expression typed"];
  } else {
    gate = ["done", "Gate", `${n} ${n === 1 ? "expression" : "expressions"} inside the 32-construct subset`];
  }

  // ── COMPILE ───────────────────────────────────────────────────────
  let compile;
  if (gate[0] === "stop") compile = ["skip", "Compile", "not reached"];
  else if (n === 0) compile = ["none", "Compile", "nothing to compile"];
  else compile = ["done", "Compile", `${n} ${n === 1 ? "expression" : "expressions"} → SQL`];

  // ── PROBES — layer 2 ──────────────────────────────────────────────
  let probe;
  if (gate[0] === "stop") probe = ["skip", "Probes", "not reached"];
  else if (fired)
    probe = ["stop", "Probes", `probe (${fired.member}) fired${fired.row_key ? ` · first row ${fired.row_key}` : ""}`];
  else if (probes.length === 0) probe = ["none", "Probes", "no operand to ask about"];
  else probe = ["done", "Probes", `${probes.length} asked · 0 offending rows`];

  // ── EXECUTE ───────────────────────────────────────────────────────
  let exec;
  if (answer.sql && answer.sql.statement_sent) {
    const rows = answer.comparison.sql_row_count;
    exec = ["done", "Execute", `${nf(rows)} ${rows === 1 ? "row" : "rows"} returned`];
  } else if (probe[0] === "stop") {
    exec = ["skip", "Execute", "compiled, and never sent"];
  } else {
    exec = ["skip", "Execute", "not reached"];
  }

  return [gate, compile, probe, exec];
}

export function Rail({ answer }) {
  const stops = stopsFor(answer);
  return (
    <div className="rail" aria-label="How far this pick got">
      {stops.map((s, i) => (
        <div className={"stop s-" + s[0]} key={i}>
          <span className="stop-dot"><Ic name={STOP_ICON[s[0]]} /></span>
          <span className="stop-t">
            <span className="stop-name">{s[1]}</span>
            <span className="stop-sub">{s[2]}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
