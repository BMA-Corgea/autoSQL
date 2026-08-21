# T-2 — Design brief: the demo screen

**Ticket** T-2, stage `design` (modifier `design@v1`, pinned because Q27 asked for it) ·
**Written** 2026-08-21 · **Authority** GA-4 (the standing delegation on T-2) and GA-5
(*"I'm about to be AFK for a long time. Be as autonomous as possible…"*, `.autodev/events.jsonl`,
2026-08-21T20:36:56Z).

**Companion artefact:** the mock published beside this document in `design/`. The mock is the
authority on *appearance*; this document is the authority on *intent and rule*. Where the two
disagree about a rule, this document wins and the mock is the thing that gets fixed.

**Read alongside:** `specs/T-2.md` — §5 (the control that must not be cut), §9.2 (the three regions),
§9.3 (the SQL pane), §12 AC-11, AC-16, AC-20–AC-22, AC-25–AC-29. **This brief adds nothing to the
spec's scope and removes nothing from it.** Every visual decision below serves a criterion that is
already written down.

**Citation convention:** a bare **§** always means a section of `specs/T-2.md`; sections of
*this* document are cited as **part n**. `D1…D12` are this document's rulings; `R1…R19` are the
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

**Q23**, verbatim from `ANSWERS-FROM-EVAN.md`:

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
┌─────────────────────────────────────────────────────────────────────────────┐
│ autoSQL · demo                                      [INVENTED DATA] [10,410]│
├────────────────────┬────────────────────────────────────────────────────────┤
│ PICK  ·  sticky    │ GENERATED SQL                                          │
│                    │ the statement · both probes · the two session values   │
│  1 source          │                                                        │
│  2 computed column ├────────────────────────────────────────────────────────┤
│  3 filter          │ ▓▓ VERDICT ▓▓  agree / disagree / no comparison        │
│  4 sort            ├───────────────────────────┬────────────────────────────┤
│  5 row cap         │ SQL ANSWER                │ PYTHON ANSWER              │
│  6 aggregate       │ (.panel)                  │ (.panel)                   │
│  7 time bucket     │                           │                            │
│  8 rolling average │   equal width / height,   │   never collapsed,         │
│  9 changed only    │   never reordered,        │   never stacked            │
│                    │                           │                            │
│  [ Run pick ]      │                           │                            │
└────────────────────┴───────────────────────────┴────────────────────────────┘
```

- **Pick controls at the left**, one column, sticky, in the operation order §7.1 numbers them. Nine
  operations, no tabs, no accordion: AC-25 requires every one of them reachable, and a person driving
  the walkthrough works down the list in order.
- **The SQL pane full-width across the top of the working area**, because §9.3 loads it with the
  statement, two probes and two session values, and it is the widest content on the screen.
- **The two answer panes side by side, equal width, equal height, SQL left and Python right, fixed**
  (D5). Not stacked. Two numbers a person is asked to compare have to be comparable in one glance,
  which is the entire mechanism §5 relies on.
- **The verdict banner spans both answer panes**, between the SQL pane and the pair. It is attached
  to the pair, not to either pane, because it is a statement about the relationship between them.

---

## 3. The five views the mock shows

Each is one artboard. Each maps to walkthrough steps and to acceptance criteria, so QA compares
against a thing and not against a taste.

| # | View | Walkthrough | What it is for |
|---|---|---|---|
| **V1** | **Resting — an accepted pick, the panes agree** | steps 2–6 | The skeleton, and the state the screen is in nine times out of ten. Proves AC-20 (both panes populated from the same rows, neither hidden or collapsed), AC-25 (all nine controls present, with operations 7/8/9 in their ruled shapes), AC-29 (no login, no role, no saved-view mode) and AC-11 (the data is labelled invented, on the screen). Establishes the type scale, the panel rhythm and the resting verdict |
| **V2** | **A shaped result — time bucket / rolling window** | steps 7–8 | The answer is not a row list but a derived table: 7 bucket labels and 7 counts, or a per-sender rolling average carried to 6 decimal places. Shows how a computed column is labelled, how the two panes key the same rows, and — load-bearing — the **session-value strip** (`extra_float_digits`, session time zone). The time zone is what makes step 7's answer 7 buckets and not 8, and it appears nowhere else on the screen (§9.3, AC-26, AC-43) |
| **V3** | **Disagreement** | step 11 | §5's control, firing. Python `1e+300` beside SQL `1`, flagged. This is the view the whole design is arranged around — see part 4 |
| **V4** | **Refused before any SQL existed — layer 1** | steps 10 and 14 | The static gate refused the expression, or §4.10's allowlist refused the alias. There is no SQL to show and both answer panes are empty (AC-16). The view has to read as *the safety system worked*, not as *the app broke* — and it must name the construct (`round`) or the name (`alive"; DROP TABLE …`) and the rule |
| **V5** | **Refused at runtime — layer 2** | steps 12–13 | SQL existed, a probe fired, the pick was abandoned before its own query ran. The SQL pane shows the probe and the condition it found; the SQL side shows no number; **the Python pane still shows its answer, labelled as the reported fallback** (AC-17, AC-18). V4 and V5 are drawn as adjacent artboards on purpose: a reader must be able to tell at a glance which layer refused, because that is the difference between "we never asked the database" and "we asked, and it told us to stop" |

**Not given an artboard: the screen before the first pick.** It is `StateBlock kind="empty"`
(`ui.jsx:104`) inside both answer panes, title *"No pick yet"*, message *"Choose a source on the left
and press Run pick."* — GIMS's canonical empty state, used verbatim with no additions. Drawing it
would be drawing someone else's finished component (D9).

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
reused unmodified, on Evan's own instruction — Q19, *"Reuse the throwaway program as-is"* — and it is
known to be wrong in ways the demo's safe subset does not exclude. Eight of the sixteen measured
disagreements at `spikes/T-1/analysis/fuzz/A_f8_guard.txt` are built entirely from constructs the
subset keeps, and one of them, `max($.l)`, returns **`1`** where the true answer is **`1e+300`** — a
plausible, quiet, completely wrong number, from an unremarkable record. Seven of the eight at least
return nothing, which looks wrong on a screen; that eighth one does not. The only thing standing
between that number and a person's trust is Q24 — *"Both answers side by side on screen"* — and the
only thing that makes side-by-side *work* is that the difference between the two sides announces
itself rather than waiting to be noticed. So the visible-disagreement signal is not decoration on a
correctness control; **it is the correctness control, wearing a visual form.** Q19 is safe because of
it and unsafe without it (§5, and Q19's own note in `ANSWERS-FROM-EVAN.md`: *"Safe only because of
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
| `.btn`, `.btn.sm`, `.btn.ghost` | `watery.css` | secondary controls (add computed column, remove, copy SQL) |
| `.field` / `.field-label` / `.input` / `.select` | `watery.css` | all nine operations' controls |
| `.toggle` | `watery.css` | operation 9's on/off — the only control it gets (R13, AC-40(e)) |
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

Everything else on the screen is one of part 5.1's primitives. **A future session adding a fourth entry
to part 5.2 owes this table a row with a reason.**

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
| `pop` (.18s) | the verdict banner, **once**, when its state changes | the only motion this screen adds a trigger for |
| `.gims-spinner` / `pulse-ring` | in-flight, while a pick resolves | GIMS's own loading affordance |

**Not used:** `pulse-dot` (reserved for live indicators — nothing here is live, and it is
bioluminescent green, which on this screen means *verified*); `slide-in` and toasts (see part 5.2);
`fade` and the modal (there is no modal); any transition longer than Watery's .14–.22s band; any
motion on a number, a table row or a result value.

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

Evan did not choose any of the following. Each is a **ruling on delegated authority** — a decision
this document made because he handed the decision over under **GA-4** (*"I feel like these questions
can be answered with your best judgement… I approve the spec for T-2"*) and **GA-5** (*"Be as
autonomous as possible"*) — not a decision he made. Each shows its derivation and each is overturned
by one line from him. This is the pattern `kb/wiki/decision-expr-to-sql.md` §6 established and
`specs/T-2.md` §14.1 follows.

**Numbered `D1…D12`, deliberately separate from the spec's `R1…R19`, so a citation cannot collide.**

| # | The ruling | Derived from | One line that overturns it |
|---|---|---|---|
| **D1** | **The six GIMS style assets are vendored byte-identical into the demo, with sha256s in the demo's manifest and §9.7's loud-skip drift check** — part 1.1's table | §3 obligation 1 (no dependency on either GIMS tree); R4, which settled the identical question for `expr.py`; the measurement that all six are byte-identical in both checkouts | *"Link them from the GIMS checkout."* |
| **D2** | **Whole files are vendored, never fragments** — even where the demo uses a handful of rules out of a 219-line file | A fragment cannot be sha256'd against its source, so D1's drift check would silently pass a fork; `shell.css`'s unused rules are scoped to `.shell-*` and match nothing here | *"Copy just the bits you use."* |
| **D3** | **Coral `--red` is reserved for a disagreement between the panes, and the disagreement state is the one place a semantic colour replaces the tan card frame** — both answer panes take a coral frame | DR-1 / §5; Watery's role table (tan = frame), which this takes an explicit, named exception to rather than quietly bending; the `.toast.err` precedent, where a semantic border already overrides a framed surface | *"Don't recolour the frame — banner only."* |
| **D4** | **Refusals wear amber `--amber`, not coral** — a new `.gims-state.is-refused` modifier | §4.3–§4.5: a refusal is the enforcement working as designed, not a fault; D3, which needs coral to mean exactly one thing; part 7's last row, which keeps coral `.is-error` for real faults | *"Make refusals red too."* |
| **D5** | **The two answer panes are equal-width, equal-height, SQL left and Python right, fixed — neither collapsible, hideable, reorderable or stackable** | AC-20 *"Neither can be hidden, collapsed by default, or switched off in the UI"*; §5, which needs them comparable in one glance | *"Let me collapse one"* — which needs AC-20 rewritten first, and §5 says why that is not a layout question |
| **D6** | **In the SQL slab, bind-substituted values are `--accent-2` and the emitted alias is `--warm`** — adding one role to part 1.2's table: warm = *your typed text, where it reaches SQL text* | §9.3, which asks the pane to show the alias *"exactly as it was emitted"*; Q11 (*"Not acceptable"* to tenant text in SQL text) and R10, which make that one position the thing worth seeing; the fact that `--warm` had no semantic role to collide with — the tan frame is a desaturated derivative of it, not the token itself | *"One colour for the whole statement."* |
| **D7** | **Result values themselves are never recoloured** — no `.w-value.tone-bad` on a wrong number; both panes' numbers stay `--text` | `dashboard.css`'s own rule, *"identity is never color-alone… Text always wears --text-* tokens"*; the risk that a coloured wrong number teaches a reader that an uncoloured number has been verified, when only the verdict banner can say that | *"Colour the wrong one red."* |
| **D8** | **A disagreement is located, not merely announced** — for table answers, the first differing row is marked and scrolled to in both panes, with a count of differing rows | AC-21's *"a visible disagreement marker, not a quiet difference the eye must catch"*, read against a 10-row result where announcing alone still leaves the eye to hunt | *"A count is enough."* |
| **D9** | **Five views are mocked; the pre-first-pick empty screen is specified in words, not drawn** — it is `StateBlock kind="empty"`, verbatim | Q23 (built GIMS's way — it is already designed, by GIMS); the design stage exists to settle what is unsettled | *"Draw it."* |
| **D10** | **One theme only: deep-water Watery. No `classic` light skin, no `.theme-switch`** | Q23 scopes this to its own app; a skin switcher is a control that proves nothing about the demo's one claim and doubles the palette QA has to check; §6's out-of-scope discipline | *"Ship the classic skin too"* — `classic.css` is a seventh vendored file and every view is checked twice |
| **D11** | **Inter is self-hosted** — the woff2 files are committed under `demo/static/fonts/` and declared by the demo's own stylesheet, loaded before `watery.css` | `watery.css:8` imports Inter from Google Fonts, and AC-32 requires the suite to pass *"with no network access beyond pulling the Postgres image"* — offline, the import is a no-op and the screen silently falls back to the system sans; D1 forbids editing `watery.css` to fix it | *"Let it fall back to the system font"* — nothing is vendored and the screen looks different offline |
| **D12** | **Agreement is stated, not implied** — the verdict banner is present on every accepted pick, green and reading *BOTH PANES AGREE*, not only when the answers differ | `watery.md`'s role for `--green` (*verified*); AC-20, which makes the comparison happen on every accepted pick, so a screen that says nothing is a screen that ran a check and kept the result to itself; §5, which needs a reader trained to look at the strip **before** the one pick where it turns coral | *"Only speak when they differ"* — the strip renders only in its coral and amber states, and open question 1 is answered |

---

## 9. Open questions for the look sign-off

Four things a mock cannot settle. None blocks the build; each is one line from him.

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
   probes and both session values to be present. The mock shows the pick's own statement open and the
   two probes collapsed behind a one-line summary. That is a judgement about reading comfort that
   trades against "visible rather than hidden", and it is his to make.
4. **How insistently should the invented data say it is invented?** AC-11 requires the label on the
   screen without saying how often. The mock puts one `INVENTED DATA` chip in the header. The other
   option is a line on every result pane. He may be showing this to an employer (Q43), which is the
   only reason the question has any weight.

---

## 10. Evidence

| Claim | Where |
|---|---|
| Q23, Q24, Q25, Q27, Q21, Q19, Q43 verbatim | `ANSWERS-FROM-EVAN.md` |
| GA-4 and GA-5, verbatim, with timestamps | `.autodev/events.jsonl` (read only) |
| The Watery style guide, mood, palette, roles, motion, component list | `../GUTS/spine/L1-memory/gims-ledger/design/watery.md` |
| Every token value and base component cited above | `../GUTS/spine/L1-memory/gims-ledger/static/styles/watery.css` (242 lines) |
| `.w-card`, `.w-value-num`, the chart palette, "identity is never color-alone" | `.../static/styles/dashboard.css` |
| `.gims-state`, `.is-error`, `.gims-spinner` | `.../static/styles/shell.css:177-189` |
| `Icon`, `StateBlock`, `GridTable`, `MultiSelect`; the `/static/icons.svg#i-<name>` contract | `.../frontend/lib/ui.jsx` |
| The sibling screen this demo is built alongside | `.../frontend/lib/dashboard/builder.jsx` (406 lines) |
| The six vendorable files are byte-identical in both GIMS checkouts | `sha256sum` over both trees, 2026-08-21 — hashes in part 1.1 |
| The screen's obligations: three regions, the SQL pane's contents, the side-by-side control | `specs/T-2.md` §9.2, §9.3, §5 |
| `max($.l)` → `1` where Python says `1e+300`; the eight in-subset divergences | `spikes/T-1/analysis/fuzz/A_f8_guard.txt` §A1–A3, via `specs/T-2.md` §5 |
| AC-11, AC-16, AC-20, AC-21, AC-22, AC-25, AC-26, AC-29, AC-37, AC-40(e), AC-43 | `specs/T-2.md` §12 |

**Read-only throughout.** Nothing in this stage wrote to either GIMS checkout, to `spikes/`, to
`tracker.mjs`, to `.autodev/tickets/` or to `.autodev/events.jsonl`.
