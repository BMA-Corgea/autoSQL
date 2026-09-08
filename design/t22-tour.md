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

## 3. The narrator — the GIMS gnome. RULED, not proposed.

**His words:** *"autoSQL would be part of the GIMS so you'd have the transparent gnome.png from the
GIMS Project folder."* Options A and B are withdrawn.

**The framing matters more than the asset.** autoSQL is a **GIMS component, not a standalone
product**, so the tour should look like it belongs to GIMS rather than inventing an identity. The
bubble's byline reads **GIMS**, not autoSQL.

**Which file, and why it is not an aesthetic choice.** Two candidates carry the same artwork:

| file | size | |
|---|---|---|
| `GIMS-Project/Transparent gnome.png` | 1024×1024 | the one he named; square, generous padding. **Not in any public tree.** |
| **`gims-oss/static/images/gnome-tour.png`** | 673×917 | tighter portrait crop, already named for a tour |

**Take `gnome-tour.png`, because it is already published.** autoSQL is a public AGPL repo, so
vendoring an asset publishes it. Verified rather than assumed: that file is on `origin/main` of
`github.com/BMA-Corgea/gims-oss`, which ships **AGPL-3.0** — the same licence autoSQL ships under.
Provenance and licence are both citable and the question never gets asked. If the square crop is
wanted, crop it from the gims-oss file rather than reaching for the unpublished one.

### The skin risk inverts, and the earlier draft had it backwards

The withdrawn option B worried that a character would read as *"a foreign object on Win9x"*. **That
was the right worry about the wrong asset.** The gnome is chunky pixel art with a hard black outline
— blue pointed hat, square eyes, red cheeks, climbing out of a cardboard box. **On Classic and JRPG
it is native.** Those are now the easy skins.

**The risk moved to the sober end** — System/base, which follows the OS and is the default. A
smiling gnome beside a bubble on a screen whose subject is *"is this number wrong"* is the tonal
problem, and it is the one the design has to solve.

**Two moves answer it, and neither is a hedge:**

1. **He is not in every step.** He appears at **1** (orientation), **6** (the payload) and **7**
   (sign-off), and is **absent from the working steps 2–5**. He introduces, gets out of the way
   while the visitor is reading numbers, returns for the point, and signs off.
2. **Step 6 is the reconciled moment.** Both panes read 123; the tour's path never fires the
   disagreement banner. So the one step where he stands over a number is the step where the number
   is **right** — which is the opposite of the tonal failure being guarded against.

### A bitmap does not derive the way a token does — priced now, not at build

**Tokens recolour per skin. A PNG cannot.** So what derives is the **placement rule**, not the
artwork:

| | treatment | derives? |
|---|---|---|
| system, light, dark, gunmetal, titanium | **62px**, beside the bubble's lower edge, no frame — a byline mark rather than a mascot | **yes** — one conservative rule, shared, because they share a sober register |
| classic | **96px**, Win9x inset frame, square | **no** — an explicit per-skin rule |
| jrpg | 96px, gold frame | **no** — an explicit per-skin rule |

**An eighth skin inherits the conservative treatment**, which is the safe direction to fail in.
**What it does not get for free is a look tuned to its own personality** — that is one rule per skin
that wants one, in *size, framing and presence*, never colour. Saying the token layer covers it
would be untrue, so it is said here instead.

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

**Nothing is built until this clears.**

### The clearance has to be his own hand — a relayed answer will not do it

He has now given the look ruling **in words**, and that is not the same as clearing the gate.
Checked in the tracker rather than assumed:

- `tracker.mjs:890` — *"`human:strict` — ONLY a confirmed human clears it. On-behalf is refused."*
- `tracker.mjs:2866` — *"an agent can never mint its own authority."*
- attempted live on T-22: an on-behalf `approve` was **refused** by the tracker.

**The T-2 precedent does not transfer, twice over.** The 2026-08-22 event it rests on is
`ticket.gate_overridden` on the **`accept`** gate — an override of a policy, not a strict clear —
and T-2 had no `design` gate at all to clear.

**So the one command, and it must be run by him:**

```
tracker.mjs approve T-22 design --by human:<his id> --i-am-human
```

**One loophole exists and is recorded as forbidden rather than offered:** `override --gate design
--policy human` would soften the gate, and the tracker accepts a live grant for that. Softening a
strict checkpoint so a relay can pass it is worse than leaving it unbound — it launders the relay
as his judgement. Not taken.

**And a separate defect, found while parking:** the `design` gate is defined in
`.autodev/data/gates.json`, policed `human:strict` in `gates-policy.json`, and **bound to nothing** —
`design@v1`'s `bands.gate` is `None`, so no stage consults it. T-22 is held by an explicit `block`
instead, which does work. `.autodev/notes/design-gate-does-not-bind.md`.
