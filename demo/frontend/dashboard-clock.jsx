// dashboard-clock.jsx — the clock the page reads times on (T-98).
//
// The owner's answer to the form (GA-68 Q7): times read on the viewer's own clock, and "we need
// to be able to just set the clock in some setting somewhere". So the clock starts as this
// computer's (the browser's own zone) and a setting in the header changes it. The list comes
// from the server (/api/dashboard/zones): one entry per place, UTC first, and every zone the
// two engines can't agree on still listed, greyed, with why in one line, so nobody wonders
// where their city went. A zone the page can't use falls back to UTC, and says so.
//
// The choice is remembered in this browser for convenience only; the zone a question uses
// travels inside the question itself, so a shared question reads the same everywhere.

import React, { useEffect, useMemo, useRef, useState } from "react";

const KEY = "dx-clock";

function loadChosen() {
  try { return window.localStorage.getItem(KEY) || null; } catch (_) { return null; }
}

function saveChosen(zone) {
  try {
    if (zone) window.localStorage.setItem(KEY, zone);
    else window.localStorage.removeItem(KEY);
  } catch (_) { /* a private window: the choice lasts as long as the page */ }
}

export function browserZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch (_) { return "UTC"; }
}

const AREA_WORDS = {
  Africa: "Africa", America: "The Americas", Antarctica: "Antarctica", Arctic: "Arctic",
  Asia: "Asia", Atlantic: "Atlantic Ocean", Australia: "Australia", Europe: "Europe",
  Indian: "Indian Ocean", Pacific: "Pacific",
};

// One zone name → the list's entry for it: listed itself, by an old name, or a fixed offset.
export function findZone(list, zone) {
  if (!list || !zone) return null;
  const listed = list.zones.find((e) => e.zone === zone);
  if (listed) return listed;
  const alias = list.aliases[zone];
  if (alias) return list.zones.find((e) => e.zone === alias) || null;
  return list.others.find((e) => e.zone === zone) || null;
}

const UTC = { zone: "UTC", label: "UTC", place: "UTC", area: "", why: null };

// What the page reads times on, and a line to say why when it isn't what was asked for.
export function resolveClock(list, chosen, computer) {
  const want = chosen || computer;
  if (!list) return { entry: { ...UTC, zone: want, label: "…" }, note: null, ready: false };
  const found = findZone(list, want);
  const whose = chosen ? "That clock" : "Your computer's clock";
  if (!found) {
    return { entry: list.zones[0] || UTC, ready: true,
      note: `${whose} isn't one this page knows, so times are in UTC.` };
  }
  if (found.why) {
    return { entry: list.zones[0] || UTC, ready: true,
      note: `${found.label} can't be used yet, so times are in UTC.` };
  }
  return { entry: found, note: null, ready: true };
}

export function useClock() {
  const computer = useMemo(browserZone, []);
  const [list, setList] = useState(null);
  const [chosen, setChosen] = useState(loadChosen);
  useEffect(() => {
    let live = true;
    fetch("/api/dashboard/zones").then((r) => (r.ok ? r.json() : null)).then((body) => {
      if (live && body && Array.isArray(body.zones)) setList(body);
    }).catch(() => {});
    return () => { live = false; };
  }, []);
  const { entry, note, ready } = resolveClock(list, chosen, computer);
  const choose = (zone) => { const z = zone === null ? null : zone; setChosen(z); saveChosen(z); };
  return { zone: entry.zone, label: entry.label, note, ready, list, chosen, computer, choose };
}

function matches(e, q) {
  if (!q) return true;
  const hay = `${e.place} ${e.label} ${e.zone} ${AREA_WORDS[e.area] || ""}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
}

function Entry({ e, on, onPick, extra }) {
  const off = !!e.why;
  return (
    <li>
      <button type="button" className={"dx-clock-item" + (on ? " is-on" : "") + (off ? " is-off" : "")}
        aria-disabled={off} aria-current={on ? "true" : undefined}
        data-zone={e.zone} onClick={() => { if (!off) onPick(); }}>
        <span className="dx-clock-item-name">{extra ? <><strong>{extra}</strong> · </> : null}{e.label}</span>
        {off ? <span className="dx-clock-item-why">{e.why}</span> : null}
      </button>
    </li>
  );
}

function ClockPanel({ clock, onClose }) {
  const [q, setQ] = useState("");
  const box = useRef(null);
  const input = useRef(null);
  useEffect(() => {
    if (input.current) input.current.focus();
    const key = (ev) => { if (ev.key === "Escape") onClose(); };
    const away = (ev) => { if (box.current && !box.current.contains(ev.target)) onClose(); };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", away);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("mousedown", away); };
  }, [onClose]);

  const list = clock.list;
  const pick = (zone) => { clock.choose(zone); onClose(); };
  const mine = list ? findZone(list, clock.computer) : null;
  const shown = list ? list.zones.filter((e) => e.zone !== "UTC" && matches(e, q)) : [];
  const areas = [];
  for (const e of shown) {
    const last = areas[areas.length - 1];
    if (last && last.area === e.area) last.items.push(e);
    else areas.push({ area: e.area, items: [e] });
  }
  const utc = list ? list.zones.find((e) => e.zone === "UTC") : null;

  return (
    <div className="dx-clock-panel" role="dialog" aria-modal="false" aria-labelledby="dx-clock-title" ref={box}>
      <div className="dx-clock-head">
        <h2 className="dx-clock-title" id="dx-clock-title">Show times in</h2>
        <button type="button" className="dx-clock-close" aria-label="Close" onClick={onClose}>×</button>
      </div>
      <p className="dx-clock-hint">Days, times and times of day are read on this clock. Summaries per hour or day stay in UTC.</p>
      <input ref={input} className="dx-input dx-clock-find" type="search" placeholder="Find a place"
        aria-label="Find a place" value={q} onChange={(ev) => setQ(ev.target.value)} />
      {!list ? <p className="dx-status">Loading the list…</p> : (
        <ul className="dx-clock-list">
          {!q && mine ? <Entry e={mine} on={!clock.chosen && clock.zone === mine.zone} extra="This computer's clock"
            onPick={() => pick(null)} /> : null}
          {utc && matches(utc, q) ? <Entry e={utc} on={clock.chosen === "UTC" || (!clock.chosen && clock.zone === "UTC" && !mine)} onPick={() => pick("UTC")} /> : null}
          {areas.map((a) => (
            <li key={a.area} className="dx-clock-area">
              <h3 className="dx-clock-area-title">{AREA_WORDS[a.area] || a.area}</h3>
              <ul className="dx-clock-list">
                {a.items.map((e) => <Entry key={e.zone} e={e} on={clock.chosen === e.zone} onPick={() => pick(e.zone)} />)}
              </ul>
            </li>
          ))}
          {q && !shown.length && !(utc && matches(utc, q)) ? <li className="dx-status">No place matches “{q}”.</li> : null}
        </ul>
      )}
    </div>
  );
}

export function ClockSetting({ clock }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="dx-clock">
      <button type="button" className="dx-clock-btn" aria-haspopup="dialog" aria-expanded={open}
        data-testid="clock" onClick={() => setOpen((o) => !o)}>
        <span className="dx-clock-btn-label">Times in</span>
        <span className="dx-clock-btn-zone">{clock.label}</span>
        <span className="dx-clock-btn-act" aria-hidden="true">▾</span>
      </button>
      {open ? <ClockPanel clock={clock} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

export function ClockNote({ clock }) {
  return clock.note ? <p className="dx-clock-note" role="status">{clock.note}</p> : null;
}
