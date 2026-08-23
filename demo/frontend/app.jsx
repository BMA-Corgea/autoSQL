// demo/frontend/app.jsx — the screen: three regions, in design part 2's order.
//
//   masthead  →  the invented-data chip and the standing banner (B31, place 1 of 3)
//   left      →  the picking panel, nine operations, one column
//   right     →  the VERDICT BANNER FIRST, then the enforcement rail, then
//                the two answer panes side by side, then the SQL pane LAST
//
// The verdict is at the top of the working area because DR-1's "impossible
// to miss by someone not expecting a disagreement" is a claim about the
// first thing they see. The SQL pane is last because it is the tallest
// content on the screen and above the answers it would push the thing the
// demo exists to show below the fold.
//
// THE SEVEN STATES, AND WHAT THE TAB STRIP IS FOR
//   The approved mock draws a seven-tab strip because a mock switches
//   artboards. This screen keeps the strip and makes it real: a tab loads
//   that state's pick INTO THE NINE CONTROLS and runs it against the
//   database. Same seven ids, same URL fragments (#agree #buckets
//   #changed #disagree #gate #alias #probe), same order. Nothing is
//   staged — every number below a tab is computed by the two calculators
//   on the spot, which is the same standard design part 3.1.2 applies to
//   the DISABLED rules: watch the control fire, do not take its word.
//
//   What is NOT copied from the mock's masthead: its two "T-2 · design
//   stage" and "visual target · not a build" chips. They are true of a
//   drawing and false of this page, and a screen that says it is not a
//   build when it is a build is worse than one that says nothing.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Ic } from "./icons.jsx";
import { PickPanel } from "./pick.jsx";
import { Verdict } from "./verdict.jsx";
import { Rail } from "./rail.jsx";
import { Panes } from "./panes.jsx";
import { SqlPane } from "./sqlpane.jsx";

const HEARTBEAT = "noun:Heartbeat";
const EDGECASE = "noun:EdgeCase";

function basePick(over) {
  return Object.assign(
    {
      source: HEARTBEAT,
      computed: [],
      filter: null,
      sort: null,
      cap: null,
      aggregate: { fn: "none", field: null },
      bucket: "off",
      window: null,
      changed: false,
    },
    over || {}
  );
}

//: The seven the mock draws, in the mock's order, with the mock's own
//: reference lines. The picks are real picks; the numbers are not here.
export const STATES = [
  {
    id: "agree", n: 1, tab: "Agreement", tabIcon: "check",
    ref: "walkthrough step 8 &middot; §7.1 window rule &middot; §7.2 exact-decimal rule",
    pick: basePick({
      computed: [{ name: "alive", expr: '$.status == "ok"' }],
      cap: 8,
      window: { field: "$.payload.load" },
    }),
  },
  {
    id: "buckets", n: 2, tab: "Time buckets", tabIcon: "clock",
    ref: "walkthrough step 7 &middot; §7.1 time-bucket rule &middot; AC-26, AC-43",
    pick: basePick({ bucket: "day", aggregate: { fn: "count", field: null } }),
  },
  {
    id: "changed", n: 3, tab: "Only what changed", tabIcon: "pulse",
    ref: "walkthrough step 9 &middot; §7.1 comparison rule &middot; the case the project was pitched on",
    pick: basePick({ changed: true }),
  },
  {
    id: "disagree", n: 4, tab: "Disagreement", tabIcon: "neq",
    ref: "walkthrough step 11 &middot; §5 the correctness control &middot; the eighth row of §5’s divergence table",
    pick: basePick({ source: EDGECASE, computed: [{ name: "biggest", expr: "max($.l)" }] }),
  },
  {
    id: "gate", n: 5, tab: "Refused: the expression", tabIcon: "shield",
    ref: "walkthrough step 10 &middot; §4.4 layer 1, the static gate",
    pick: basePick({ computed: [{ name: "hot", expr: "round($.payload.load, 1)" }] }),
  },
  {
    id: "alias", n: 6, tab: "Refused: the column name", tabIcon: "lock",
    ref: "walkthrough step 14 &middot; §4.10 the alias allowlist &middot; R10, AC-38, AC-45",
    pick: basePick({
      computed: [{ name: 'alive"; DROP TABLE demo.records; --', expr: '$.status == "ok"' }],
    }),
  },
  {
    id: "probe", n: 7, tab: "Refused while running", tabIcon: "search",
    ref: "walkthrough step 13 &middot; §4.5 layer 2, member (a)",
    pick: basePick({ source: EDGECASE, computed: [{ name: "scaled", expr: "$.huge * 1" }] }),
  },
];

function nf(n) {
  return typeof n === "number" ? n.toLocaleString("en-US") : String(n);
}

async function getJSON(url, init) {
  const r = await fetch(url, init);
  const body = await r.json().catch(() => null);
  if (body == null) throw new Error(url + " answered " + r.status + " with no JSON");
  return body;
}

/** The source's true row count, taken out of the contract's own option
 *  label ("noun:Heartbeat · 8,400 rows") rather than counted here. */
function sourceRows(contract, source) {
  const op1 = ((contract && contract.operations) || []).find((o) => o.n === 1);
  const ctl = op1 && (op1.controls || [])[0];
  const opt = ctl && (ctl.options || []).find((o) => o.value === source);
  if (!opt) return null;
  const m = /([\d,]+)\s+rows/.exec(opt.label);
  return m ? Number(m[1].replace(/,/g, "")) : null;
}

// ── operation 9's reduction block: what survived, made checkable ──────
function Reduce({ answer, total }) {
  const pick = answer && answer.pick;
  if (!answer || !answer.accepted || !pick || !pick.changed) return null;
  const kept = answer.comparison.compared_rows;
  const rows = answer.panes.sql.rows || [];
  const cols = answer.panes.sql.columns || [];
  const ki = cols.indexOf("key");
  if (ki < 0) return null;

  // One sender's beats, lit where the record changed — read out of the
  // rows on screen, never invented: the page is ordered by key, so the
  // first sender's kept beats are all on it.
  const firstKey = rows.length ? rows[0].c[ki] : "";
  const m = /^(.+)-(\d+)$/.exec(firstKey);
  const sender = m ? m[1] : null;
  const lit = new Set();
  let width = 168;
  if (sender) {
    rows.forEach((r) => {
      const mm = new RegExp("^" + sender + "-(\\d+)$").exec(r.c[ki]);
      if (mm) lit.add(Number(mm[1]));
    });
  }
  const complete = sender && rows.some((r) => r.c[ki].indexOf(sender + "-") !== 0);
  const pct = total ? ((kept / total) * 100).toFixed(1) : null;

  return (
    <section className="panel reduce" aria-label="What survived">
      <div className="panel-head">
        <Ic name="pulse" />
        <span className="panel-title">What survived</span>
      </div>
      <div className="panel-body">
        <div>
          <div className="reduce-top">
            <div className="reduce-fig">
              <span className="reduce-num">{nf(kept)}</span>
              <span className="reduce-of">
                of <b>{total ? nf(total) : "—"}</b> beats kept
              </span>
            </div>
            {pct ? (
              <div className="reduce-pct"><b>{pct}%</b> of the collection</div>
            ) : null}
          </div>
          <div className="bar">
            <span className="bar-fill" style={{ width: (pct || 0) + "%" }} />
          </div>
          <div className="bar-scale">
            <span>0</span>
            <span>{total ? nf(total) + " beats" : ""}</span>
          </div>
          {sender && complete ? (
            <div className="beats">
              <div className="beats-lab">
                {sender}
                <span>
                  — every one of its {width} beats, lit where the record changed
                </span>
              </div>
              <div className="beatgrid">
                {Array.from({ length: width }, (_, i) => (
                  <span key={i} className={"beat" + (lit.has(i) ? " on" : "")} />
                ))}
              </div>
              <p className="beats-note">
                <b>{lit.size}</b> of this sender’s {width} beats changed something.{" "}
                <b>If the comparison included <code>ts</code>, every cell above would
                be lit</b> and the count would read {total ? nf(total) : "every row"}{" "}
                — which is why the number, not the screenful of rows, is the thing to
                check.
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function stateIndexFromHash() {
  const id = (location.hash || "").replace("#", "");
  const i = STATES.findIndex((s) => s.id === id);
  return i < 0 ? 0 : i;
}

function App() {
  const [current, setCurrent] = useState(stateIndexFromHash);
  const [pick, setPick] = useState(() => STATES[stateIndexFromHash()].pick);
  const [contract, setContract] = useState(null);
  const [vocab, setVocab] = useState({ fields: [], numeric_fields: [] });
  const [answer, setAnswer] = useState(null);
  const [ranFrom, setRanFrom] = useState(null); // the preset a shown answer came from
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [hot, setHot] = useState(null);
  const canon = useRef("");

  const dirty = JSON.stringify(pick) !== canon.current;

  // ── the contract, re-derived for the current pick (B22, DR-2) ───────
  const refresh = useCallback(async (p) => {
    try {
      const c = await getJSON("/api/operations?pick=" + encodeURIComponent(JSON.stringify(p)));
      setContract(c);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadVocab = useCallback(async (source) => {
    try {
      setVocab(await getJSON("/api/fields?source=" + encodeURIComponent(source)));
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const run = useCallback(async (p, preset) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/pick", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pick: p }),
      });
      const body = await r.json();
      setAnswer(body);
      setRanFrom(preset || null);
      canon.current = JSON.stringify(p);
      if (body.operations) setContract(body.operations);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const show = useCallback(
    (i, fromUrl) => {
      const st = STATES[i];
      setCurrent(i);
      if (!fromUrl && location.hash !== "#" + st.id) history.replaceState(null, "", "#" + st.id);
      const p = JSON.parse(JSON.stringify(st.pick));
      setPick(p);
      loadVocab(p.source);
      refresh(p);
      run(p, st);
    },
    [loadVocab, refresh, run]
  );

  useEffect(() => {
    show(stateIndexFromHash(), true);
    const onHash = () => show(stateIndexFromHash(), true);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onChange = useCallback((p) => setPick(p), []);
  const onCommit = useCallback(
    (p) => {
      setPick(p);
      if (p.source !== (vocab.source || p.source)) loadVocab(p.source);
      else if (!vocab.source) loadVocab(p.source);
      refresh(p);
    },
    [refresh, loadVocab, vocab.source]
  );

  useEffect(() => {
    if (vocab.source && vocab.source !== pick.source) loadVocab(pick.source);
  }, [pick.source, vocab.source, loadVocab]);

  const total = useMemo(() => sourceRows(contract, pick.source), [contract, pick.source]);
  const preset = !dirty && ranFrom ? ranFrom : null;

  const onKeyDown = (e) => {
    const n = STATES.length;
    let t = -1;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") t = (current + 1) % n;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") t = (current + n - 1) % n;
    else if (e.key === "Home") t = 0;
    else if (e.key === "End") t = n - 1;
    else return;
    e.preventDefault();
    show(t);
    const el = document.getElementById("tab-" + STATES[t].id);
    if (el) el.focus();
  };

  return (
    <div className="wrap">
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark"><Ic name="drop" /></span>
          <div>
            <h1>autoSQL — the picking screen</h1>
            <p>A pick, the SQL it wrote, and both answers to it.</p>
          </div>
        </div>
        <div className="masthead-right">
          {/* B31, place 1 of 3 — the masthead chip, as drawn */}
          <span className="chip warn">
            <Ic name="warning" className="icon-sm" />invented data
          </span>
          <span className="count-pill">
            {total ? nf(total) + " rows in this source" : "—"}
          </span>
        </div>
      </header>

      {/* B31, place 1 of 3 — the standing banner under it, as drawn */}
      <div className="banner">
        <Ic name="info" />
        <div>
          <b>Every record on this screen is invented</b>, and the heartbeat shape in
          particular was made up — no heartbeat schema exists in either GIMS
          checkout. The database behind it is this demo's own, on 127.0.0.1:55440,
          seeded with 10,410 rows from a fixed seed and nothing else.
        </div>
      </div>

      <div className="tabbar">
        <div className="tabs" role="tablist" aria-label="Screen states" onKeyDown={onKeyDown}>
          {STATES.map((s, i) => (
            <button type="button" className="tab" role="tab" key={s.id} id={"tab-" + s.id}
                    aria-controls="statepanel" aria-selected={i === current}
                    tabIndex={i === current ? 0 : -1} disabled={busy}
                    onClick={() => show(i)}>
              <span className="tab-n">{s.n}</span>
              {s.tab}
            </button>
          ))}
        </div>
        <div className="legend" role="list" aria-label="What the colours mean">
          <span><i className="lg-ok" />the panes agree</span>
          <span><i className="lg-bad" />they disagree</span>
          <span><i className="lg-warn" />refused</span>
        </div>
      </div>

      {error ? (
        <div className="banner" role="alert">
          <Ic name="warning" />
          <div><b>The screen could not reach the demo's API.</b> {error}</div>
        </div>
      ) : null}

      <div className="layout" id="statepanel" role="tabpanel" tabIndex={-1}
           aria-labelledby={"tab-" + STATES[current].id}>
        <PickPanel contract={contract} vocab={vocab} pick={pick} answer={answer}
                   onChange={onChange} onCommit={onCommit}
                   onRun={() => run(pick, null)} dirty={dirty} busy={busy} />
        <div>
          <Verdict answer={answer} preset={preset} />
          <Rail answer={answer} />
          <Reduce answer={answer} total={total} />
          <Panes answer={answer} hot={hot} setHot={setHot} />
          <SqlPane answer={answer} />
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
