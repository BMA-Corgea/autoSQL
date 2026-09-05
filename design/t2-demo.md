# T-2 — Design brief: the demo screen

**Ticket** T-2, stage `design` (modifier `design@v1`, pinned because Q27 asked for it) ·
**Written** 2026-08-21 · **Authority** GA-4 (the standing delegation on T-2) and GA-5
(*"I'm about to be AFK for a long time. Be as autonomous as possible…"*, `.autodev/events.jsonl`,
2026-08-21T20:36:56Z).

**Companion artefact:** the mock published beside this document in `design/`. The mock is the
authority on *appearance*; this document is the authority on *intent and rule*. Where the two
disagree about a rule, this document wins and the mock is the thing that gets fixed.

**Read alongside:** `.autodev/specs/T-2.md` — §5 (the control that must not be cut), §9.2 (the three regions),
§9.3 (the SQL pane), §12 AC-11, AC-16, AC-20–AC-22, AC-25–AC-29. **This brief adds nothing to the
spec's scope and removes nothing from it.** Every visual decision below serves a criterion that is
already written down.

**Citation convention:** a bare **§** always means a section of `.autodev/specs/T-2.md`; sections of
*this* document are cited as **part n**. **Part 3.1 is numbered as it is on purpose** — it was added
on 2026-08-21 and renumbering parts 4–11 would have silently broken every citation of them, in this
document and outside it. `D1…D12` are this document's rulings; `R1…R19` are the
spec's. `AC-n` are the spec's acceptance criteria; `DR-1` is part 4's hard requirement.

---

## 0. What this document is for

Spec §9.2 ends: *"The design stage (§13) decides how this looks. This spec fixes only what must be
present."* This is that decision, written down.

It exists for three readers: the builder, who needs to know what to make; the reviewer and QA, who
need something to compare the built screen against; and the next session, which must not re-derive
the look from scratch or invent a second one.

It is **not** a style guide. The style guide is GIMS's, it is finished, and it is not ours to
rewrite. This is the record of what *this screen* does with it.

---

## 1. The style: Watery, and why

**Q23**, verbatim from `kb/notes/owner-answers.md`:

> **"Its own app, but built GIMS's way"**

The look follows from the second half of that sentence. "GIMS's way" is not only React 18 + esbuild +
committed bundles + a small FastAPI server (§9.1) — it is also GIMS's house style, which is called
**Watery**: deep teal-green water, warm sun-shaft light from above, luminous aqua as the accent,
bioluminescent green for verified. It is documented at
`../GUTS/spine/L1-memory/gims-ledger/design/watery.md` and defined at
`static/styles/watery.css`, whose own header says the operative rule: *"Recolor a :root variable, not
40 hex codes."*

**The demo recolours nothing.** Not a token, not a component, not a hex code. It inherits
`watery.css` as it stands and adds only what part 5 below justifies. The reason is the same reason Q23
gave: this screen is a sibling of `/dashboard_admin`, and the whole point of building it GIMS's way
is that it can move into GIMS later without a rewrite. A screen carrying its own palette does not
move; it gets re-skinned, and re-skinning is where a screen quietly stops matching the system it is
supposed to belong to.

The demo is deliberately **not** built on the generic dark "Nocturne" default. `watery.md` opens by
saying so: *"This is GIMS's house style; it is **not** the generic 'Nocturne' default."*

### 1.1 The token file it inherits from, and how it gets there

Obligation 1 of §3 forbids the demo from depending on either GIMS checkout at run time. That applies
to stylesheets exactly as it applies to `expr.py`, so the same answer applies: **vendor it**, with a
sha256 in the demo's manifest and the loud-skip drift check §9.7 defines (D1 below).

Six files, verified 2026-08-21 to be **byte-identical in both GIMS checkouts** — the same finding
§9.7 records for `expr.py`, so it does not matter which tree is present:

| vendored file | sha256 | why it is needed |
|---|---|---|
| `static/styles/watery.css` | `684dc2cc4eecb6eb69467af22593a5411fe15f322f6c7aaa99065c0ac013132e` | the `:root` tokens, `.panel`, `.icon-chip`, `.count-pill`, `.btn-primary`, fields, chips, motion |
| `static/styles/dashboard.css` | `0fb91d03fb0a9269e4eeba33405c46277dad70ed4c60775ae395872ecaafc706` | `.w-card` / `.w-head` / `.w-body`, `.w-value-num`, the validated 6-hue chart palette |
| `static/styles/shell.css` | `894b642ba54f5d178c4f7f7598dff9cdea5517c8edce55a3a6cce925ffd9feca` | `.gims-state` — the canonical empty / loading / error block, and `.gims-spinner` |
| `static/styles/components.css` | `13d256f66cd5cc38ee6b0b0beed8be5296aa2cfe2593a3e5e2efbc6347a48959` | the `.ui-*` component layer that `ui.jsx` renders into |
| `static/icons.svg` | `4c8ef8978924095ab365e88478d1075d9d0c8215a337f6b925b045c445e0d5cc` | the `<symbol>` sprite; `Icon` resolves `/static/icons.svg#i-<name>`, so it must be served at that path |
| `frontend/lib/ui.jsx` | `df7ac5925b437e0abc0a8adee39b2af8c988025905f8ec34321a252c3739a53c` | `Icon`, `StateBlock`, `GridTable`, `MultiSelect`. Imports **only** React — nothing else follows it in |

**Whole files, never fragments** (D2). A fragment cannot be sha256'd against its source, so a
fragment is a fork that nobody will notice has drifted.

### 1.2 The colour roles, restated because they are the thing most likely to be broken

`watery.md`'s rule, quoted: *"green = surface/card, tan = card frame, cyan/aqua = icon-chip edge &
accent, blue = action. Keep these distinct — don't tint a card blue or make a button cyan."*

As this screen uses them:

| role | token | on this screen |
|---|---|---|
| surface | `--bg` → `--surface2` | the page floor and the input wells |
| card | `--card` / `--card-2` | every `.panel` body — the pick panel, the SQL panel, both answer panels |
| card frame | `--card-edge` (2px, tan) | every panel's frame. **The one exception is D3's disagreement state** |
| accent | `--accent` / `--accent-2` | focus rings, `.icon-chip` edges, panel-head icons, `.count-pill`, and the substituted bind values in the SQL slab (D6) |
| action | `--blue` family | exactly one thing: the **Run pick** `.btn-primary`. Nothing else on this screen is blue |
| verified | `--green` / `--green-text` | the verdict banner when the two panes agree, and only there |
| warn | `--amber` | refusals (D4) and the INVENTED DATA chip |
| danger | `--red` / `--red-text` | **reserved.** Coral appears on this screen only when the two answers differ (§5, D3) |
| warm light | `--warm` | ambient, plus one added role: the emitted alias in the SQL slab (D6) |

---

## 2. The screen: three regions, in this order

Spec §9.2 fixes the regions; this fixes their arrangement.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ autoSQL · the picking screen         [INVENTED DATA] [8,400 rows in source]  │
├──────────────────────┬───────────────────────────────────────────────────────┤
│ THE PICK             │ ▓▓ VERDICT ▓▓   agree / disagree / refused            │
│  1 source     [sel]  ├───────────────────────────────────────────────────────┤
│  2 computed  [in][in]│ GATE ▸ COMPILE ▸ PROBES ▸ EXECUTE  — where it stopped │
│  3 filter  [textarea]├───────────────────────────┬───────────────────────────┤
│  4 sort     [sel×2]  │ SQL — Postgres            │ Python — in-memory        │
│  5 row cap    [num]  │                           │                           │
│  6 aggregate[sel×2]  │  equal width / height,    │  never collapsed,         │
│  7 time bucket[sel]  │  never reordered,         │  never stacked,           │
│  8 rolling wnd[sel]  │  one spine between them,  │  the same rows keyed      │
│  9 changed [toggle]  │  marked row for row       │  the same way             │
│                      ├───────────────────────────┴───────────────────────────┤
│  [ Run this pick ]   │ THE GENERATED SQL                                     │
├──────────────────────┤ the statement · both probes · the two session values  │
│ THE SEEDED DATABASE  │                                                       │
└──────────────────────┴───────────────────────────────────────────────────────┘
```

- **Pick controls at the left**, one column, in the operation order §7.1 numbers them. Nine
  operations, no tabs, no accordion: AC-25 requires every one of them reachable, and a person driving
  the walkthrough works down the list in order. **Each one is a control, not a summary of a control**
  — part 3.1 fixes their shapes.
  **Correction, 2026-08-21: this said "sticky" and the mock is not.** Once every operation carries a
  real control the pick panel measures **1,949–2,236px** at 1440 against a working area of
  **1,081–1,748px** beside it — more than twice a 900px-tall viewport — so `position: sticky` would
  strand its own foot, the **Run this pick** button, permanently off-screen. Sticky is the right instinct for a short rail and the wrong mechanism for this one;
  what it was reaching for (the pick stays legible while the answers are read) is delivered by the
  verdict banner being at the **top** of the working area instead, below.
- **The verdict banner first, at the top of the working area, above everything it describes.** This
  is a change from an earlier draft, which put it between the SQL pane and the pair.
  **DR-1 is the reason:** *impossible to miss* by someone who is not expecting a disagreement is a
  claim about the first thing they see, and the first thing they see is the top of the working area.
  Below the SQL slab it is one scroll away from being missed, and DR-1.1 forbids it ever scrolling
  out of the pair it describes.
- **The enforcement rail directly under it** — gate ▸ compile ▸ probes ▸ execute, four stops, the one
  that stopped marked. It answers *how far did this pick get* in one glance, which is the difference
  §9.3 asks the screen to make between a layer-1 and a layer-2 refusal.
- **The two answer panes side by side, equal width, equal height, SQL left and Python right, fixed**
  (D5). Not stacked. Two numbers a person is asked to compare have to be comparable in one glance,
  which is the entire mechanism §5 relies on. They live inside **one** framed surface with a spine
  down the middle rather than in two separate frames — the spine is what carries the per-row `✓` /
  `≠` mark that D8 requires, and two independent frames have no place to put it.
- **The SQL pane last, full width.** §9.3 loads it with the statement, both probes and the two
  session values, so it is the tallest content on the screen; above the answers it pushes the thing
  the demo exists to show below the fold. **An earlier draft put it at the top and that was the
  wrong way round.**

---

## 3. The seven views the mock shows

**This section named five views and the mock shipped a different five.** They agreed on three
(disagreement, and the two refusals) and disagreed on the other two: this document asked for a
*resting* view and a *shaped result — time bucket / rolling window*; the mock drew agreement **with
the rolling window already in it** and spent its fifth artboard on **operation 9**, which this
document did not list at all. A builder and a QA seat handed those two lists would have built and
checked against different screens.

**Resolved 2026-08-21 by drawing the union, not by picking a winner** (D9, rewritten). The count is
**seven**. Each of the three moves is named below with the reason, because "we changed our minds" is
not a reason a later session can check:

| move | what happened | why that way and not the other |
|---|---|---|
| **V1 and V2 merged** | The old V1 (*resting*) and the rolling-window half of the old V2 are one view — the mock's **Agreement**, which already carries the 3-point window and the six-decimal numbers | A "resting" pick with nothing switched on has no answer worth comparing, so it demonstrates neither AC-20 nor §5. Two artboards were being spent on one screen |
| **The time bucket was split out and drawn** | The other half of the old V2 became its own view, **Time buckets** — the one the mock was missing | This is the case where the brief named a view that genuinely should exist, so the rule was to draw it rather than delete it. A bucketed answer is a **derived table** — 7 labels and 7 counts, not a row list — which is a result shape nothing else on the screen shows; and it is the only view where the **session time zone** is load-bearing (§7.1's time-bucket rule, AC-43: the same 8,400 beats fall into 8 buckets rather than 7 if it is wrong, with both panes computing correctly) |
| **Operation 9 was adopted from the mock** | **Only what changed** stays, as a view in its own right | §7.1's operation-9 ruling: *"Without operation 9, the defining property of the demo's headline collection is never shown to anyone."* It is the case the project was pitched on, it is walkthrough step 9, and its answer is a **count** rather than a table — a third result shape |
| **The alias refusal was split out and drawn** | The old V4 covered *"the static gate refused the expression, **or** §4.10's allowlist refused the alias"* in one view, and the mock drew only the first half. They are now two views, **Refused: the expression** and **Refused: the column name** | The two refusals are different controls, in different code paths, refusing different inputs — a construct against §4.4's allowlist, a name against §4.10's. This document's own standard everywhere else (§5, §8.3's R11, part 4) is that **a control nobody can watch fire is not trustworthy**, and the alias check was asserted only in a footnote. It is also the one walkthrough step the owner drives himself against hostile input (step 14) |

Each view is one artboard, reachable by its own tab, by keyboard, and by URL fragment. Each maps to
walkthrough steps and to acceptance criteria, so QA compares against a thing and not against a taste.

| # | View | id | Walkthrough | What it is for |
|---|---|---|---|---|
| **V1** | **Agreement — an accepted pick, the panes agree to the digit** | `#agree` | steps 2–6, 8 | The skeleton, and the state the screen is in nine times out of ten. A 3-point rolling average carried to six decimal places, eight rows, eight matches. Proves AC-20 (both panes populated from the same rows, neither hidden or collapsed), AC-25 (all nine controls present, with operations 7/8/9 in their ruled shapes), AC-29 (no login, no role, no saved-view mode) and AC-11 (the data is labelled invented, on the screen). Establishes the type scale, the panel rhythm and the resting verdict. It is also where an **accepted** alias is visible, emitted as `AS "alive"` — the other half of V6 |
| **V2** | **Time buckets — a derived table, and the setting that decides its shape** | `#buckets` | step 7 | The answer is not a row list but 7 bucket labels and 7 counts. Shows how a bucketed result is keyed, that both panes agree on the labels **as strings**, and — load-bearing — the **session-value strip**. The time zone is what makes the answer 7 buckets and not 8, and it appears nowhere else on the screen (§9.3, AC-26, AC-43). It is also where two of part 3.1's DISABLED rules fire |
| **V3** | **Only what changed — the case the project was pitched on** | `#changed` | step 9 | 912 of 8,400 beats survive. The answer here is a **number**, and the view is built round making that number checkable: one sender's 168 beats, lit where the record changed. Proves what the operation is *for* — put `ts` back into the compared value and every cell lights, the count reads 8,400, and both panes agree perfectly about a filter that filtered nothing (§7.1's comparison rule, AC-40) |
| **V4** | **Disagreement** | `#disagree` | step 11 | §5's control, firing. Python `1e+300` beside SQL `1`, flagged. This is the view the whole design is arranged around — see part 4 |
| **V5** | **Refused before any SQL existed — the expression** | `#gate` | step 10 | §4.4's static gate refused a construct. There is no SQL to show and both answer panes are empty (AC-16). The view has to read as *the safety system worked*, not as *the app broke* — and it must name the construct (`round`) and the rule. The SQL pane shows the gate's walk over the parsed tree, node by node |
| **V6** | **Refused before any SQL existed — the column name** | `#alias` | step 14 | §4.10's allowlist refused an alias: `alive"; DROP TABLE demo.records; --`. Same layer, same shape, same amber — a *different check*, on the one piece of user-typed text that has to reach SQL text. The SQL pane shows the five checks in order with the one that stopped it marked, and **the statement the check kept out**, struck through and labelled *never built, never prepared, never sent*. That last block is the whole point of drawing this view: it is what `re.match` would have let through and `re.fullmatch` does not |
| **V7** | **Refused at runtime — layer 2** | `#probe` | steps 12–13 | SQL existed, a probe fired, the pick was abandoned before its own query ran. The SQL pane shows the probe and the condition it found; the SQL side shows no number; **the Python pane still shows its answer, labelled as the reported fallback** (AC-17, AC-18). V5, V6 and V7 are adjacent artboards on purpose: a reader must be able to tell at a glance which layer refused, because that is the difference between "we never asked the database" and "we asked, and it told us to stop" |

**Not given an artboard: the screen before the first pick.** It is `StateBlock kind="empty"`
(`ui.jsx:104`) inside both answer panes, title *"No pick yet"*, message *"Choose a source on the left
and press Run pick."* — GIMS's canonical empty state, used verbatim with no additions. Drawing it
would be drawing someone else's finished component (D9).

---

## 3.1 The picking panel — nine controls, and the two states a mock has to draw

**This section is new, and it is new because the mock had no controls.** It drew a *summary of a
pick* — nine rows of read-only text — where half the screen is the half a person operates. There was
no `input`, `select`, `textarea` or toggle anywhere in the file and one button on the whole page, so
a builder copying the mock had nothing to copy for the operations, and AC-25's *"a UI test asserts
each control exists"* had nothing to assert against.

**Everything below is built from `watery.css`'s own primitives** — `.field`, `.field-label`,
`.input`, `.select`, `textarea.input`, `.toggle`, `.btn`, `.btn.sm`, `.btn.ghost` — which part 5.1
already listed as reused-unchanged. The brief was right and the mock had not caught up.

### 3.1.1 The nine shapes

| # | Operation | Control | Fixed by |
|---|---|---|---|
| 1 | Choose a source | one `.select`, three options | closed set, §4.4 row 7 |
| 2 | Computed columns | a repeatable row: `.input` **name** + `=` + `.input` **expression**, a `.btn.sm.ghost` remove per row, one `.btn.sm.ghost` **Add computed column** | §7.1 op 2; the name is §4.10's surface |
| 3 | One filter | one `textarea.input` | §7.1 op 3 |
| 4 | Sort field | `.select` field + `.select` direction (`asc` / `desc`) | closed set of two, §4.4 row 7; §7.4 |
| 5 | Row cap | one numeric `.input`, `min=1 max=20000` | §4.4 row 5's range check, `MAX_SCAN` |
| 6 | Aggregate | `.select` function (`none`/`count`/`sum`/`avg`/`min`/`max`) + `.select` field | closed set of five, §4.4 row 7 |
| 7 | Time buckets | one `.select`: `off` / `per hour` / `per day` — **and nothing else** | Q20's own option text; §4.4 row 7 |
| 8 | Rolling window | one `.select`, a numeric field — **no width, no direction, no aggregate** | **R14**, asserted by AC-25 |
| 9 | Show only rows that changed | one `.toggle` — **and no picker for what it compares** | **R13**, asserted by AC-25 and AC-40(e) |

Operations 7, 8 and 9 carry a **dashed `.ctl-fixed` note** stating what the control deliberately does
*not* offer. R13 and R14 are rulings that a build can only honour by *not* building something, and a
thing that is absent leaves no trace in a mock unless the absence is drawn. AC-25 tests exactly these
three absences.

### 3.1.2 DR-2 — a control that can be illegal must show itself illegal

> **DR-2.** Where the spec makes an operation illegal in combination with the rest of the pick, the
> screen **disables that operation's control and states the reason beside it**. It never leaves a
> control live that will be refused on submit, and it never disables one silently.

Two rules follow from the spec, and both are drawn in the mock:

| | Rule | Where it comes from | Where it fires in the mock |
|---|---|---|---|
| **X1** | **Operations 7, 8 and 9 are unavailable unless the source is `noun:Heartbeat`** | They read `$.ts` and `$.sender_id` (§7.1's window rule and time-bucket rule, written out as `data ->> 'sender_id'` and `data ->> 'ts'`). §4.10's per-collection field lists say those keys exist on the heartbeat and on neither of the other two: `noun:Sample` carries `id, status, due_date, priority, field_0 … field_14`, `noun:EdgeCase` its witness keys | V4 and V7, both on `noun:EdgeCase` — three operations off at once, with the collection's actual field list given as the reason |
| **X2** | **Operation 8 is unavailable while operation 6 has a function**, and **operation 4 is unavailable while operation 7 is bucketing** | §7.3's builder table: op 6 emits one `AS "agg"` for the group, op 8 emits one `AS "rolling_avg"` **per row**, and one statement cannot emit both. §7.1's time-bucket rule: *"Bucketed results are ordered by `ORDER BY bucket`"*, so the sort is decided by op 7 and not by op 4 | V2 — both fire at once |

A third case is drawn inside one operation rather than between two: with `count` chosen, operation
6's **field** picker is disabled, because `count` counts rows and takes no field.

**The rules are live in the mock, not painted on.** Changing the source select re-derives them, so a
reader can watch three controls go unavailable rather than take the drawing's word for it — the same
standard part 3's table applies to the alias check.

### 3.1.3 FOCUS is a drawn state, not only a reachable one

A mock is looked at as a still picture at least as often as it is driven. A focus ring that exists
only while a key is held tells a builder nothing about what to build, so **one control per view
carries the ring persistently**, marked with a small `keyboard focus` tag so nobody mistakes it for
an error:

- **V2** — operation 7's granularity `.select`, in plain focus: aqua border, `0 0 0 3px` aqua glow.
  This is `watery.css:153` verbatim; no new colour, no new token.
- **V6** — operation 2's **name** `.input`, in focus **and** invalid at once. That combination is the
  one a builder will otherwise get wrong, and it is the exact moment step 14 describes: the person is
  still in the field that was refused. Amber border, amber glow, `aria-invalid="true"`.

**Refusals inside the picker wear amber and never coral** (D4), including the invalid field itself.
Coral in this screen means *the two answers differ* and nothing else (D3).

---

## 4. The one hard design requirement

> **DR-1. A disagreement between the two answer panes must be impossible to miss.** Not merely
> present, not merely correct: *impossible to miss* by a person who is looking at the screen for the
> first time, is not expecting a disagreement, and has all animation disabled. It is carried by at
> least three independent signals at once — the verdict banner (colour + icon + words), the frames of
> both answer panes, and a mark on the differing value itself — of which no single one is colour
> alone. **This requirement does not yield to layout.** If the panes will not fit, the layout
> changes; the signal does not shrink.

**Why it is a requirement and not a preference.** The compiler this demo generates SQL with is being
reused unmodified, on the owner's own instruction — Q19, *"Reuse the throwaway program as-is"* — and it is
known to be wrong in ways the demo's safe subset does not exclude. Eight of the sixteen measured
disagreements at `spikes/T-1/analysis/fuzz/A_f8_guard.txt` are built entirely from constructs the
subset keeps, and one of them, `max($.l)`, returns **`1`** where the true answer is **`1e+300`** — a
plausible, quiet, completely wrong number, from an unremarkable record. Seven of the eight at least
return nothing, which looks wrong on a screen; that eighth one does not. The only thing standing
between that number and a person's trust is Q24 — *"Both answers side by side on screen"* — and the
only thing that makes side-by-side *work* is that the difference between the two sides announces
itself rather than waiting to be noticed. So the visible-disagreement signal is not decoration on a
correctness control; **it is the correctness control, wearing a visual form.** Q19 is safe because of
it and unsafe without it (§5, and Q19's own note in `kb/notes/owner-answers.md`: *"Safe only because of
Q24… Q24 is therefore not droppable"*). Trading it down for layout reasons — a smaller badge, a
subtler colour, a marker below the fold, a banner that scrolls away — converts the demo into a
machine that displays confident wrong numbers, which is the exact failure this whole project exists
to prevent, staged as a demonstration of success.

**What follows from it, concretely:**

1. The verdict banner is **never dismissible**, never collapsible, never a toast, and never scrolls
   out of the pane pair it describes.
2. It is legible with `prefers-reduced-motion: reduce` in force — which `watery.css` honours by
   killing every animation (`watery.css:112-114`). No signal may live in a movement.
3. It is legible in greyscale and to a red/green-confused reader: the AGREE and DISAGREE states carry
   different **words** and different **icons** (`i-check` / `i-warning`), not just different hues.
4. The disagreement is **located, not merely announced** (D8). For a scalar answer the two values sit
   side by side already; for a table answer the screen marks the first differing row, scrolls to it
   in both panes, and states how many rows differ.
5. The false-disagreement problem is the mirror of this one and is already handled upstream: §7.1's
   window rule, R9 and R15 pin the short-window divisor, the tiebreak and the session time zone so
   the two panes cannot differ for reasons that mean nothing. Design's obligation is not to
   manufacture a second source of them — hence D7 (the numbers themselves are never recoloured, so
   nothing on the screen looks like a disagreement except a disagreement).

---

## 5. Component inventory

### 5.1 Reused, unchanged — no justification owed

| Primitive | Where from | Used for |
|---|---|---|
| `.panel` + `.panel-head` + `.panel-title` + `.panel-body` | `watery.css` | every boxed surface: pick, SQL, both answer panes. Green body, 2px tan frame, `rise` entrance |
| `.icon-chip` (aqua) | `watery.css` | the mark in each `.panel-head`. `.icon-chip.blue` is **not** used: nothing here is an action context except the one CTA |
| `.count-pill` | `watery.css` | the row count in the header and on each answer pane |
| `.btn-primary` (blue, `ripple` on hover) | `watery.css` | **Run pick**, the only primary action on the screen |
| `.field` / `.field-label` / `.input` / `.select` / `textarea.input` | `watery.css:147-155`, verbatim | all nine operations' controls — part 3.1's table says which shape each one takes. The focus ring is `watery.css:153` and is not restyled |
| `.toggle` (+ its `.track`) | `watery.css:198-205`, verbatim | operation 9's on/off — the only control it gets (R13, AC-40(e)) |
| `.btn`, `.btn.sm`, `.btn.ghost`, `:disabled` | `watery.css:158-166`, verbatim | add / remove a computed column; the disabled treatment of every control |
| `.chip`, `.chip.ok`, `.chip.warn`, `.chip.accent` | `watery.css` | INVENTED DATA (warn), the session values (accent), pane labels |
| `.w-value` / `.w-value-num` / `.w-value-cap` | `dashboard.css` | a scalar answer — the 40px tabular-numerals tile GIMS already uses for exactly this |
| `GridTable` (`ui.jsx:128`) + `.ui-*` | `ui.jsx`, `components.css` | a table answer, in both panes, with the same columns in the same order |
| `StateBlock` (`ui.jsx:104`) + `.gims-state` | `ui.jsx`, `shell.css` | empty ("no pick yet"), loading, and — with D4's variant — refused |
| `MultiSelect` | `ui.jsx` | wherever more than one field is picked |
| monospace slab: `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` on `--bg2` | established GIMS page convention (`audit.css:83`, `prepositional_phrase_runner.css:20`, `template.css:31`, six more) | the SQL statement, the probes, expressions echoed in refusals. **Not a `watery.css` primitive but not an invention either** — it is what every GIMS page that shows code already does |
| `.chart-*` + the validated 6-hue palette | `dashboard.css` | only if a result is ever charted. **Nothing in the walkthrough charts anything**, so the demo ships no chart unless one appears later, and if it does it uses this palette and no other |

### 5.2 New — each with the reason it could not be a reuse

| New | What it is | Why nothing existing does it |
|---|---|---|
| **`.verdict`** — the agreement banner, three states: `.agree` (green), `.disagree` (coral), `.no-compare` (amber) | A full-width, non-dismissible strip spanning both answer panes, carrying an icon, a word, and a sentence | AC-21 demands a **persistent** marker that a reader cannot miss. `.chip.ok` is a 10.5px pill — precisely the *"quiet difference the eye must catch"* the criterion forbids. `.toast` is worse: transient, dismissible, corner-anchored, entrance-animated, and gone for anyone who looked away. Neither can be made to satisfy DR-1 by configuration, so this is new |
| **`.gims-state.is-refused`** — one modifier on GIMS's own state block | Swaps the mark to amber (`--amber` on `--amber-light`, `i-warning`) instead of `.is-error`'s coral | A refusal is the safety system **working**, and `.is-error` would say two wrong things: that something broke, and that coral means something other than "these two answers differ". One modifier line, reusing the whole structure (D4) |
| **`.sql-slab`** — the SQL pane's body | The monospace slab of part 5.1, plus two inline classes: `.sql-bind` (bind-substituted values, `--accent-2`) and `.sql-alias` (the emitted `AS "alive"`, `--warm`) | The slab itself is the reuse. The two inline classes are new because §9.3 asks the pane to make one specific distinction visible — what arrived as a bind parameter versus the one piece of user-typed text that reaches SQL text (§4.10, R10, Q11) — and no existing class expresses it (D6) |
| **`.pane-pair`** | A two-column grid, equal width, equal height, no reflow, no reorder | A layout constraint rather than a component, listed here because it is load-bearing: it is how AC-20 is enforced in CSS instead of by good intentions (D5) |

| **`.sel-wrap` + `.caret`** — a positioned chevron beside a `.select` | An 11px inline-SVG chevron, absolutely positioned, `pointer-events:none`; the `.select` gets `padding-right` and is otherwise untouched | `watery.css:150` sets `appearance:none` on `.select` and draws **no** caret of its own, so an unwrapped `.select` is indistinguishable from an `.input` — and this screen puts six of them next to four text fields. It is a layout affordance rather than a restyle: no token is recoloured and `.select` itself carries no new rule (**D14**) |
| **`.ctl-fixed`** — a dashed note under a control | States what an operation deliberately does *not* offer | R13 and R14 are honoured by **not** building something, and an absence leaves no trace in a mock. AC-25 tests these three absences specifically, so they need somewhere to be visible (part 3.1.1) |
| **`.op-why`** — one line beside a disabled or refused operation | Icon + sentence: why this control is unavailable, or why what was typed was refused | DR-2. `.toast` is transient and `StateBlock` is a whole-pane component; neither attaches a reason to one control among nine |
| **`.is-focus` / `.is-invalid`** — two modifiers on `.input` / `.select` | `.is-focus` paints exactly what `:focus` paints; `.is-invalid` is the amber refused field | A still picture cannot hold a live `:focus`, and part 3.1.3 needs the ring drawn. `.is-invalid` is amber for D4's reason, and it reuses the amber already in `.chip.warn` — no new token |
| **`.gw-never`** — the struck-through statement a check refused to emit | A dashed amber block: the SQL text the alias validator kept out, labelled *never built, never prepared, never sent* | V6's whole reason for existing. A refusal that only says *"refused"* asks to be trusted; showing the exact text that `re.match` would have let through and `re.fullmatch` did not is the same standard §5 applies to the disagreement — **watch the control fire, do not take its word** |
| **`.cmp.is-diff`** — a coral frame on the surface holding both panes | Replaces the tan `--card-edge` while the answers differ | DR-1's second of three independent signals, and D3's named exception to Watery's role table. It sits on the pair's own frame because the mock draws the two panes inside **one** framed surface (part 2) |

Everything else on the screen is one of part 5.1's primitives. **A future session adding a further
entry to part 5.2 owes this table a row with a reason.**

---

## 6. Motion: restrained

The demo uses four of Watery's motions plus GIMS's own loading spinner, and nothing else. `watery.md`'s own heading for the set is
*"Gentle Watery (calm, not busy)"*, and this screen is calmer than the launcher because it is asking
a person to read numbers.

| Motion | Where | Note |
|---|---|---|
| `drift` (~22s) | the page's ambient light blobs, via `.watery-bg` | inherited, untouched |
| `rise` (.4s) | every `.panel`, on first paint | inherited from `.panel`; not re-fired on every pick |
| `ripple` (1.1s) | **Run pick** on hover | inherited from `.btn-primary` |
| `rise` (.34s) | the verdict banner, on paint | **Corrected 2026-08-21: this said `pop` (.18s), "the only motion this screen adds a trigger for".** The mock uses `rise`, the same entrance `.panel` already has, and adds **no** motion trigger of its own. That is the stricter reading of DR-1.2 and of this section's own heading, so the mock is right and this row was wrong |
| `.gims-spinner` / `pulse-ring` | in-flight, while a pick resolves | GIMS's own loading affordance |

**Not used:** `pop` (nothing on this screen pops); `pulse-dot` (reserved for live indicators —
nothing here is live, and it is bioluminescent green, which on this screen means *verified*);
`slide-in` and toasts (see part 5.2); `fade` and the modal (there is no modal); any transition
longer than Watery's .14–.22s band; any motion on a number, a table row or a result value.

**The picker's own motion is Watery's, unchanged:** `.input` / `.select` transition their border and
glow over .18s (`watery.css:152`), `.btn` over .12–.15s, the `.toggle` track over .2s. Nothing was
added and nothing was slowed down. Measured under `prefers-reduced-motion: reduce`, every one of
them resolves to 1e-06s and the disagreement banner is at full opacity — part 11.

**No signal lives in a movement** (DR-1.2). `watery.css:112-114` kills every animation under
`prefers-reduced-motion: reduce`, and the screen must be exactly as readable then.

---

## 7. What is not designed here

| Not designed | Why |
|---|---|
| Anything in §6's out-of-scope list | It is out of scope for the ticket, so it has no visual form: **no timer, no stopwatch, no "faster than"** anywhere on the screen (Q21, AC-37); no GIMS integration; no truncation badge; no index affordance |
| Login, roles, saved views, an author/viewer split | Q25, *"Any viewer can re-slice live"* — AC-29. There is no signed-in state to design |
| A second theme | The demo ships deep-water Watery only. GIMS has a `classic` light skin and a `.theme-switch`; the demo carries neither (D10) |
| Mobile / small-screen layouts | Q26 scopes this to one Linux machine and one browser. The layout is designed at 1440 and must not break at 1280; below that it is undefined |
| Charts | Nothing in the 14-step walkthrough plots anything. If a chart ever appears it uses `dashboard.css`'s validated palette and this table gets rewritten |
| The walkthrough document's own typography | `demo/WALKTHROUGH.md` is Markdown in the repo, not a screen |
| The seed script's console output | Not a UI surface, though AC-11's "labelled invented" applies to it separately |
| Error states that are not refusals | A database that is down, a container that failed to start — `StateBlock kind="error"`, GIMS's own, unchanged. That is what coral `.is-error` is for, and it is why refusals may not borrow it (D4) |

---

## 8. Rulings on delegated authority

The owner did not choose any of the following. Each is a **ruling on delegated authority** — a decision
this document made because he handed the decision over under **GA-4** (*"I feel like these questions
can be answered with your best judgement… I approve the spec for T-2"*) and **GA-5** (*"Be as
autonomous as possible"*) — not a decision he made. Each shows its derivation and each is overturned
by one line from him. This is the pattern `kb/wiki/decision-expr-to-sql.md` §6 established and
`.autodev/specs/T-2.md` §14.1 follows.

**Numbered `D1…D12`, deliberately separate from the spec's `R1…R19`, so a citation cannot collide.**

| # | The ruling | Derived from | One line that overturns it |
|---|---|---|---|
| **D1** | **The six GIMS style assets are vendored byte-identical into the demo, with sha256s in the demo's manifest and §9.7's loud-skip drift check** — part 1.1's table | §3 obligation 1 (no dependency on either GIMS tree); R4, which settled the identical question for `expr.py`; the measurement that all six are byte-identical in both checkouts | *"Link them from the GIMS checkout."* |
| **D2** | **Whole files are vendored, never fragments** — even where the demo uses a handful of rules out of a 219-line file | A fragment cannot be sha256'd against its source, so D1's drift check would silently pass a fork; `shell.css`'s unused rules are scoped to `.shell-*` and match nothing here | *"Copy just the bits you use."* |
| **D3** | **Coral `--red` is reserved for a disagreement between the panes, and the disagreement state is the one place a semantic colour replaces the tan card frame** — the frame that goes coral is the one holding **both** panes, since the mock draws them inside a single framed surface with a spine (part 2); an earlier wording said *"both answer panes take a coral frame"*, which describes a two-frame layout this screen does not have | DR-1 / §5; Watery's role table (tan = frame), which this takes an explicit, named exception to rather than quietly bending; the `.toast.err` precedent, where a semantic border already overrides a framed surface | *"Don't recolour the frame — banner only."* |
| **D4** | **Refusals wear amber `--amber`, not coral** — a new `.gims-state.is-refused` modifier | §4.3–§4.5: a refusal is the enforcement working as designed, not a fault; D3, which needs coral to mean exactly one thing; part 7's last row, which keeps coral `.is-error` for real faults | *"Make refusals red too."* |
| **D5** | **The two answer panes are equal-width, equal-height, SQL left and Python right, fixed — neither collapsible, hideable, reorderable or stackable** | AC-20 *"Neither can be hidden, collapsed by default, or switched off in the UI"*; §5, which needs them comparable in one glance | *"Let me collapse one"* — which needs AC-20 rewritten first, and §5 says why that is not a layout question |
| **D6** | **In the SQL slab, bind-substituted values are `--accent-2` and the emitted alias is `--warm`** — adding one role to part 1.2's table: warm = *your typed text, where it reaches SQL text* | §9.3, which asks the pane to show the alias *"exactly as it was emitted"*; Q11 (*"Not acceptable"* to tenant text in SQL text) and R10, which make that one position the thing worth seeing; the fact that `--warm` had no semantic role to collide with — the tan frame is a desaturated derivative of it, not the token itself | *"One colour for the whole statement."* |
| **D7** | **Result values themselves are never recoloured** — no `.w-value.tone-bad` on a wrong number; both panes' numbers stay `--text` | `dashboard.css`'s own rule, *"identity is never color-alone… Text always wears --text-* tokens"*; the risk that a coloured wrong number teaches a reader that an uncoloured number has been verified, when only the verdict banner can say that | *"Colour the wrong one red."* |
| **D8** | **A disagreement is located, not merely announced** — for table answers, the first differing row is marked and scrolled to in both panes, with a count of differing rows | AC-21's *"a visible disagreement marker, not a quiet difference the eye must catch"*, read against a 10-row result where announcing alone still leaves the eye to hunt | *"A count is enough."* |
| **D9** | **Seven views are mocked** — agreement, time buckets, only-what-changed, disagreement, and three refusals (the expression, the column name, the runtime probe); **the pre-first-pick empty screen is specified in words, not drawn** — it is `StateBlock kind="empty"`, verbatim. *Rewritten 2026-08-21: this said five, and named a different five from the mock's. Part 3's table has the three moves and the reason for each* | Q23 (built GIMS's way — it is already designed, by GIMS); the design stage exists to settle what is unsettled; §5, §7.1's operation-9 ruling and §4.10, each of which names a control that has to be watched firing | *"Draw the empty screen too"*, or *"Five is enough — fold the two refusals-before-SQL back together"*, which costs V6 and with it the only place the alias check is visible. |
| **D10** | **One theme only: deep-water Watery. No `classic` light skin, no `.theme-switch`** | Q23 scopes this to its own app; a skin switcher is a control that proves nothing about the demo's one claim and doubles the palette QA has to check; §6's out-of-scope discipline | *"Ship the classic skin too"* — `classic.css` is a seventh vendored file and every view is checked twice |
| **D11** | **Inter is self-hosted** — the woff2 files are committed under `demo/static/fonts/` and declared by the demo's own stylesheet, loaded before `watery.css` | `watery.css:8` imports Inter from Google Fonts, and AC-32 requires the suite to pass *"with no network access beyond pulling the Postgres image"* — offline, the import is a no-op and the screen silently falls back to the system sans; D1 forbids editing `watery.css` to fix it | *"Let it fall back to the system font"* — nothing is vendored and the screen looks different offline |
| **D13** | **The nine operations are drawn as controls, in `watery.css`'s own field primitives, and part 3.1.1 fixes the shape of each** — including the three whose shape is *an absence* (ops 7, 8, 9), which are drawn as dashed notes stating what is deliberately not offered | AC-25, which asserts the shape of exactly those three; §4.4's inventory table, which names what checks each typed input; the fact that a mock without controls gives a build nothing to copy for half the screen | *"Just list the operations"* — and AC-25's UI test has nothing to assert against. |
| **D14** | **A `.select` is wrapped in `.sel-wrap` and given a positioned chevron** | `watery.css:150` sets `appearance:none` and draws no caret, so six unwrapped selects would read as text inputs on a screen that also has four real ones; the wrapper recolours no token and adds no rule to `.select` itself | *"Leave the selects bare"*, or *"Put the caret into `watery.css`"* — which is an edit to GIMS's stylesheet and D1 forbids it. |
| **D15** | **DR-2: an operation the spec makes illegal in combination is disabled with its reason stated beside it, and the rules are live in the mock rather than painted on** — X1 (ops 7/8/9 need `noun:Heartbeat`) and X2 (op 8 vs op 6; op 4 vs op 7), part 3.1.2 | §7.1's window and time-bucket rules, which read `$.ts` and `$.sender_id`; §4.10's per-collection field lists; §7.3's builder table, where `AS "agg"` and `AS "rolling_avg"` cannot both be emitted; the general rule that a control which will be refused on submit should not have been live | *"Let me try it and tell me afterwards"* — the refusal then happens after the pick is run, which is the shape §4.4 spends its length arguing against. |
| **D12** | **Agreement is stated, not implied** — the verdict banner is present on every accepted pick, green and reading *BOTH PANES AGREE*, not only when the answers differ | `watery.md`'s role for `--green` (*verified*); AC-20, which makes the comparison happen on every accepted pick, so a screen that says nothing is a screen that ran a check and kept the result to itself; §5, which needs a reader trained to look at the strip **before** the one pick where it turns coral | *"Only speak when they differ"* — the strip renders only in its coral and amber states, and open question 1 is answered |

---

## 9. Open questions for the look sign-off

Five things a mock cannot settle. None blocks the build; each is one line from him.

1. **Should agreement speak as loudly as disagreement?** The mock puts a green *BOTH PANES AGREE*
   banner on every accepted pick — that is **D12**, and it is the ruling this
   question exists to let him overturn. The alternative is that agreement is silent and the strip
   appears only when the answers differ. Loud agreement risks banner-blindness — a reader who stops
   reading the strip is a reader who misses the one time it turns coral. Silent agreement risks a
   reader not knowing the check ran at all. Only driving the walkthrough for ten minutes tells you
   which of those you actually do.
2. **Side by side, or stacked, on the screen he will actually use?** The mock commits to side by
   side, because §5's mechanism is a single glance. At 1280px with the SQL slab above, it is tight.
   If it reads as cramped on his machine, the fix is a layout change and it should happen now rather
   than at accept.
3. **How much SQL does he want in front of him at rest?** §9.3 requires the statement, both runtime
   probes and both session values to be present. **Corrected 2026-08-21: this said the mock collapsed
   the two probes behind a one-line summary, and it does not** — it shows the statement and both
   probes open, in full, with the probe that was *not* run stated in a comment rather than hidden.
   That is the maximally-visible reading of §9.3 and it makes the SQL pane the tallest thing on the
   screen, which is why part 2 puts it last. If it is more SQL than he wants to look at at rest, the
   fix is a collapse on the probes and it should happen now rather than at accept.
4. **How insistently should the invented data say it is invented?** AC-11 requires the label on the
   screen without saying how often. The mock puts one amber `INVENTED DATA` chip in the header, plus
   the standing banner under it. The other option is a line on every result pane. He may be showing
   this to an employer (Q43), which is the only reason the question has any weight.
5. **Is the picking column too long?** Measured at 1440, the pick panel is **1,949–2,236px** tall
   against a working area of **1,081–1,748px** beside it — it is the longer of the two columns in
   every one of the seven states, which is why it is not sticky (part 2). Every hint could be moved behind a `?` per
   operation, or dropped from the screen into `demo/WALKTHROUGH.md`. That trades a shorter column
   against a person having to leave the screen to find out what `MAX_SCAN` is, and ten minutes of
   driving the walkthrough answers it in a way no amount of arguing here will.

---

## 10. Evidence

| Claim | Where |
|---|---|
| Q23, Q24, Q25, Q27, Q21, Q19, Q43 verbatim | `kb/notes/owner-answers.md` |
| GA-4 and GA-5, verbatim, with timestamps | `.autodev/events.jsonl` (read only) |
| The Watery style guide, mood, palette, roles, motion, component list | `../GUTS/spine/L1-memory/gims-ledger/design/watery.md` |
| Every token value and base component cited above | `../GUTS/spine/L1-memory/gims-ledger/static/styles/watery.css` (242 lines) |
| `.w-card`, `.w-value-num`, the chart palette, "identity is never color-alone" | `.../static/styles/dashboard.css` |
| `.gims-state`, `.is-error`, `.gims-spinner` | `.../static/styles/shell.css:177-189` |
| `Icon`, `StateBlock`, `GridTable`, `MultiSelect`; the `/static/icons.svg#i-<name>` contract | `.../frontend/lib/ui.jsx` |
| The sibling screen this demo is built alongside | `.../frontend/lib/dashboard/builder.jsx` (406 lines) |
| The six vendorable files are byte-identical in both GIMS checkouts | `sha256sum` over both trees, 2026-08-21 — hashes in part 1.1 |
| The screen's obligations: three regions, the SQL pane's contents, the side-by-side control | `.autodev/specs/T-2.md` §9.2, §9.3, §5 |
| `max($.l)` → `1` where Python says `1e+300`; the eight in-subset divergences | `spikes/T-1/analysis/fuzz/A_f8_guard.txt` §A1–A3, via `.autodev/specs/T-2.md` §5 |
| AC-11, AC-16, AC-20, AC-21, AC-22, AC-25, AC-26, AC-29, AC-37, AC-38, AC-40(e), AC-43, AC-45 | `.autodev/specs/T-2.md` §12 |
| The alias allowlist, its pattern, its three collision groups and what a refusal must say | `.autodev/specs/T-2.md` §4.10; walkthrough step 14 (§10) |
| The two granularities, the fixed window shape, the fixed compared value | `.autodev/specs/T-2.md` §7.1 — the time-bucket rule, R14, R13 |
| Which collections carry `ts` and `sender_id` (X1's derivation) | `.autodev/specs/T-2.md` §4.10's per-collection field lists; §7.1's window and time-bucket rules |
| `AS "agg"` and `AS "rolling_avg"` cannot both be emitted (X2's derivation) | `.autodev/specs/T-2.md` §7.3's division-of-labour table |
| 7 buckets × 1,200, and the labels `2026-08-14T00:00:00Z` … `2026-08-20T00:00:00Z` | `.autodev/specs/T-2.md` §7.1's time-bucket rule and R17; walkthrough step 7 |
| The field primitives, the toggle and the button rules the mock copies verbatim | `.../static/styles/watery.css:147-166, 198-205` |
| The mock re-rendered at 1440 and at 390: no console error, no horizontal page scroll, every state reachable by keyboard | measured 2026-08-21 with a headless Chromium; method and numbers in part 11 |

**Read-only throughout.** Nothing in this stage wrote to either GIMS checkout, to `spikes/`, to
`tracker.mjs`, to `.autodev/tickets/` or to `.autodev/events.jsonl`.

---

## 11. What was measured, on 2026-08-21

The mock was re-rendered in a headless Chromium (Playwright 1.61.1) at **1440×900** and at
**390×900**, every one of its seven states clicked, and the tab strip driven from the keyboard.
These are readings, not intentions.

| Check | Result |
|---|---|
| Console errors, page errors, failed non-`file:` requests | **0** at both widths, across all seven states |
| Console warnings | **0** |
| Horizontal page scroll at 390 (`scrollWidth − clientWidth`) | **0px**, all seven states. Same at 1440 |
| Elements extending past the viewport edge, excluding those inside a deliberate `overflow-x:auto` scroller | **0**, all seven states, both widths |
| Inner scrollers that actually scroll at 390 | the SQL slab only (`.sql-scroll`), which is what it is for; the comparison grid unstacks below 760 and does not |
| Page height at 1440 | 2,477–2,764px depending on state. The pick panel is 1,949–2,236px of it; the working area beside it 1,081–1,748px |
| Controls in the picking panel | **12** `input`/`select`/`textarea` + 2 buttons on a state with one computed column; **10** + 1 where there are none. Nine operations, all present |
| `.toggle` renders its `.track` | 1 per state — this was **broken** on first render (the track element was omitted, so operation 9 had no visible switch) and is fixed |
| DISABLED drawn | X1: **3** operations off on the two `noun:EdgeCase` states. X2: **2** off on the bucketed state. Plus operation 6's field picker off under `count` |
| DISABLED fires live | changing the source select from `noun:Heartbeat` to `noun:EdgeCase` takes the count from 0 to 3 disabled operations, keeps focus on the select, and raises the *unrun pick* note. Choosing an aggregate takes operation 8 to `op is-disabled` with its reason attached |
| FOCUS drawn | 1 control per relevant state — operation 7's select on V2, operation 2's name field on V6 (focused **and** invalid) |
| Invalid drawn | 1 field on each of the two layer-1 refusals |
| **Arrow-key navigation** | **Fixed.** `ArrowRight` ×7 walks all seven tabs and wraps to the first; `ArrowLeft` ×7 walks back and wraps; `Home` → first, `End` → last; `Enter` on a focused tab activates it. `document.activeElement` and `aria-selected` agree at **every** step. Before the fix the handler re-rendered the strip, destroying the focused button, and the second press went nowhere |
| Keyboard reach into the picker | `Tab` from the strip reaches all 13 controls in operation order, then **Run this pick** — `select[source] → cc name → cc expression → remove → add → filter → sort field → sort direction → row cap → aggregate fn → bucket → window field → toggle → Run` |
| Typing does not lose the caret | typing into the refused alias field leaves the value intact and the element still focused. The picker is committed on `change`, never re-rendered under a caret |
| Disagreement legibility, with `prefers-reduced-motion: reduce` | verdict opacity **1**, animation duration **1e-06s**, banner 228px tall at y=252 — above the fold, and the first thing in the working area. **Five independent signals**: the words *"The panes disagree on one row."*, the `#i-neq` icon, the coral frame on the pair, the `1 row differs` chip, and the differing row marked on **both** sides with both values boxed and a `≠` on the spine. None is colour alone, and DR-1 asks for three |

**What was not measured.** Real fonts under a network block (the mock loads Inter from Google Fonts;
the built demo self-hosts it — D11), any browser other than Chromium, and any screen reader.
