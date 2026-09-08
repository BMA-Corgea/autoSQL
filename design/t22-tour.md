# T-22 — the guided tour over the demo screen

**Status: DRAWN, NOT BUILT. Parked at the `design` gate, which is `human:strict`.**
Nothing in `demo/` has been changed. This document and `design/t22-tour-mock.html` are the
whole deliverable so far, deliberately — this shop's own T-2 pattern, where the mock was
approved *"as drawn"* before a line was built.

**One glance version:** https://claude.ai/code/artifact/8fbca01d-ba11-40e5-9446-526635e99ec5 — or open `design/t22-tour-mock.html` in a browser. It shows the narrator,
the bubble, the spotlight, and the step list, on four of the seven skins, with no engine
behind it.

---

## 1. What this tour is for, which decides everything else

**It teaches the SCREEN, not the query language.** A first-time visitor does not need to be
walked through fourteen picks; they need to learn to read two panes, understand that
agreement is the boring default, and then be shown the one place where agreement is the
entire point.

**The tour's destination is step 11.** `noun:EdgeCase`, `biggest = max($.m)`, over the array
`["１２３", 1]` — where those are **fullwidth digits** `U+FF11 U+FF12 U+FF13`. Both engines
read **123**. That is the value that used to be silently wrong, and everything before it in
the tour exists to make a visitor able to see why that matters.

## 2. The step list — SEVEN steps, and what I cut

| # | anchor | what it says | advance |
|---|---|---|---|
| 1 | the whole screen | "Two panes. Same question, answered two different ways — Postgres on the left, Python on the right. When they agree, the number is boring. When they don't, something is wrong." | `next` |
| 2 | the pick form | "This is where you ask. Pick a source, add a computed column, filter, sort — the same shapes a real dashboard offers." | `next` |
| 3 | Run this pick | "Run it." — **`target-click`**: the visitor actually clicks, and the host runs the pick. | `target-click` |
| 4 | the two panes, agreeing | "Both panes read the same. That is the normal case, and it is what 11,367 expressions of testing bought." | `next` |
| 5 | the gate / "how far this pick got" | "Compile → Gate → Execute. Not every expression is allowed through; the gate is what refuses the ones that cannot be answered identically." | `next` |
| 6 | **the step-11 result cell** | **the payload.** `max($.m)` over `["１２３", 1]`. "Those are not ASCII digits. `１２３` is three fullwidth code points. Python's `float()` accepts them; so, now, does the SQL — the same 670-digit mapping on both sides. Both read 123. **This is the cell that used to be silently wrong.**" | `next` |
| 7 | the skin switcher + replay | "Seven looks, and the tour again whenever you want it." | `next` |

**Step 6 is driven, not typed.** `beforeShow(api)` sets the pick to `noun:EdgeCase` /
`biggest = max($.m)` and runs it, so the visitor arrives at the payload without eight
manual actions. That is what the engine's `beforeShow` hook is for.

### What I cut, deliberately

**Demo steps 3–10 and 13–14** — filter, sort, aggregate, time-bucket, rolling window,
changed-rows, `round()`, and the SQL-injection column name.

**Why:** they teach the *expression language*, and `demo/README.md`'s walkthrough already
does that better than a bubble can, at the reader's own pace. A tour that walks all fourteen
evenly spends its attention budget before it reaches the only step whose result a visitor
could not have predicted. **Restraint is the point:** the tour highlights the happy path to
one destination; it is not a tooltip on every control.

**The one I most nearly kept is demo step 14** — a computed column whose *name* is a SQL
injection, refused by the alias validator. It is a good story and it is genuinely alarming
in the right way. I cut it because it is a *security* anecdote, and putting it after step 11
would leave the visitor's last impression on the wrong subject. **Easy to add back as an
eighth step if he wants it** — it costs one entry in the `STEPS` array and no engine change.

## 3. The narrator — two options, drawn side by side

The mock shows both. **My recommendation is A**, and B is one line to switch to.

- **A — the mark.** No character. The demo's own brand mark in a small disc, and a bubble in
  the demo's type. Sober, matches a tool whose whole subject is *"is this number right"*, and
  it cannot age badly or read as cute on a screen showing a correctness failure.
- **B — a character.** A small illustrated guide beside the bubble. Warmer and more obviously
  a tutorial. It needs an asset that does not exist yet, and it has to survive seven skins
  including a Win9x one.

## 4. The spotlight, and the seven-skin problem

**The mechanism** (from the engine, not invented here): the dim is **four panels around** the
target rectangle, not one full-screen sheet the target must out-`z-index`. The target is
simply left uncovered, so it stays natively clickable however it is nested. That is what
makes it survive the demo's transformed panes.

**The skin problem, stated plainly:** the demo has seven looks and `system` follows the OS.
A spotlight tuned to one of them is broken for anyone who switches — including the reader who
never switches but whose laptop goes dark at sunset.

**The answer is the token layer, and it follows the contract the skins already use:**

- a NEW file, `demo/static/tour-tokens.css`, declaring the tour's own custom properties
- one bare `:root` block (the light default), one `@media (prefers-color-scheme: dark)` block
  guarded as `:root:not([data-theme="light"])` for **system**, and one
  `:root[data-theme="<name>"]` block per skin that needs to differ
- **`demo/static/demo.css` gains nothing.** It declares **zero** custom properties today and
  B18 asserts it must keep declaring none. Verified: `grep -cE '^\s*--[a-z-]+\s*:'` → 0.
- **`demo/vendor/styles/*.css` are not touched.** They are sha256-pinned by D1.

**Two skins need explicit treatment rather than inheritance:**

| skin | why it cannot inherit |
|---|---|
| **classic** (Win9x) | square corners and a hard 2px border are the whole look. A rounded, glowing ring reads as a foreign object. Gets: square ring, no glow, navy. |
| **jrpg** | gold frames on a teal field. A neutral grey dim turns the palette to mud. Gets: a warmer dim and a gold ring. |

The other five derive from existing skin tokens, so **an eighth skin gets a sane tour for
free** — which is the same property `skin.js`'s own contract has.

## 5. What building it will need — flagged now, because one item is not free

**`demo/frontend/*.jsx` is covered by `manifest.json`'s `ui:frontend-sources:sha256`.**

The engine anchors each step to a stable selector, and the demo has **two `id`s and three
`data-` attributes across all six `.jsx` files**. There is nothing to anchor to. The options:

| | approach | cost |
|---|---|---|
| **A (recommended)** | add `data-tour="…"` to ~8 controls in the `.jsx`, then `./run-demo build-ui` and re-baseline the digest | a real `.jsx` edit — the exact step T-14 skipped and T-16 had to repair. Done properly it is mechanical, and T-16 proved the bundles come back byte-identical when only comments change |
| B | anchor on structural selectors (`nth-child` chains) | the engine's own docs call this the number-one cause of tours breaking on redesign |
| C | have the tour find controls by visible label text at runtime and tag them itself | no `.jsx` edit, but it silently breaks when a label is reworded, and it hides the coupling instead of removing it |

**A is the honest one and it is the one I recommend — but it edits digest-covered files, so
it is on this page rather than in a commit.** Nothing about it is risky when the procedure is
followed; the risk is doing it without `build-ui`, which is a known, named, already-repaired
failure in this repo.

**Everything else is free:** the engine builds its own DOM and appends to `<body>`, exactly as
`skin.js` already does, so no `.jsx` is needed for the overlay itself. `tour.js` and
`tour-tokens.css` are new files loaded like any other — the CSP is `script-src 'self'` and
they are self-hosted, so no inline script is involved.

## 6. What is being asked at this gate

1. **The step list** — seven steps arriving at step 11. Is that the right destination, and is
   cutting demo steps 3–10 and 13–14 the right cut? Step 14 (the injection name) is the one I
   would add back first.
2. **Narrator A (the mark) or B (a character).**
3. **The `.jsx` edit** — approach A above, `data-tour` hooks plus `./run-demo build-ui` and a
   re-baselined digest.

**Nothing is built until this clears.** The gate is `human:strict`; it refuses an on-behalf
clear by design, and that is the correct behaviour, not an obstacle.
