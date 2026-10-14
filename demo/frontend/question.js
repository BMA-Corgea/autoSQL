// question.js — what a view sends as its question (T-98 moved it out of dashboard.jsx, unchanged,
// so a test can hold it without a browser: ops/tests/test_t98_question.mjs). Plain functions over the
// setup and the view the screen holds.
import { answerShape, isComplete } from "./dashboard-steps.jsx";
import { asMatch, countComplete, countWaiting, countedFields } from "./dashboard-scoreboard.jsx";
import { sendableMatched } from "./dashboard-matched.jsx";
import * as T from "./filter-tree.js";

// The choices that are off for this view, and why — the contract's own
// verdicts, carried in the setup (setup.unavailable, from /api/operations).
const SCOREBOARD_SORT_OFF = "A scoreboard sorts by its own columns: tap a column's name.";
export function offFor(setup, view) {
  if (view.scoreboard) return { sort: SCOREBOARD_SORT_OFF };
  return setup.unavailable[view.dataset][answerShape(view)] || {};
}

// What is sent: the view without the conditions still waiting for a value,
// without the screen's own row handles, and without the choices that are
// greyed out right now. A greyed choice is kept on screen (it comes back
// when the summary is turned off), shown as off with its reason, and not
// asked about.
export function sendable(setup, view, admin, zone) {
  const ds = setup.datasets.find((d) => d.id === view.dataset);
  const off = offFor(setup, view);
  // The filter as a tree (T-96): only the cards with their values, no group
  // left empty, and a group whose "exactly one of" / "all or none of" isn't
  // ready yet held back — marked "not applied yet" on screen, not sent.
  const complete = (c) => isComplete(c, ds.fields.find((f) => f.path === c.field));
  const out = { ...view, filter: T.sendable(view.filter, complete) };
  if (view.summary || view.scoreboard) out.columns = []; // kept on screen, greyed, for when it is turned off
  if (off.sort) out.sort = null;
  if (off.show) out.show = null;
  if (view.scoreboard) out.scoreboard = sendableScoreboard(setup, ds, view.scoreboard);
  // Columns from another data set (T-78): beside a table's rows only, and
  // only once whole with a field ticked; kept on screen otherwise.
  const matched = view.summary || view.scoreboard ? null : sendableMatched(setup, ds, view.matched, admin);
  if (matched) out.matched = matched;
  else delete out.matched;
  if (zone) out.zone = zone; // T-98: the question's clock travels inside the question
  return out;
}

// A scoreboard as sent: only the count columns that are ready (a name, a
// condition with a value, enough conditions for their logic); the others
// stay on screen marked "not counted until …". Each column travels with
// its own id (the screen's handle, _k), the answer's headers come back as
// "count:<id>" / "pct:<id>", and a sort names a column the same way — one
// numbering end to end, so a column held back cannot shift which column a
// header or a sort means. A sort on a column that is not sent is not sent.
export function sendableScoreboard(setup, ds, sb) {
  const fields = countedFields(setup, ds, sb);
  const counts = [];
  sb.counts.forEach((c) => {
    if (countWaiting(c, fields)) return;
    counts.push({
      id: c._k,
      label: c.label.trim(),
      pct: c.pct,
      filter: T.sendable(c.filter, countComplete(fields)),   // T-96: a count column's tree
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
