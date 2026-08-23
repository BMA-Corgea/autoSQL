# T-2 · live feedback — the screen, actually rendered and actually looked at

**2026-08-22, verify stage.** Eight screenshots in this folder, captured from the running app on
`http://127.0.0.1:8787` against the seeded invented database on 55440.

## First: the gap this closes, and the gap it does not

Every prior document on this ticket — the design receipt, W14's build report, `demo/VERIFY.md` §6 —
says the same thing honestly: **nobody had looked at this screen in a real browser.** There is no
browser on `PATH`, and AC-32 forbids fetching one.

There *is* one already on this machine, in the Playwright cache at
`~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`. **AC-32 forbids fetching browser
automation over the network; it does not forbid using a browser that is already here**, and nothing
was downloaded. It also sits entirely outside the demo tree, so it changes none of the demo's own
dependencies.

So the page's JavaScript has now genuinely executed and rendered. **What that closes:** the screen
builds, all seven states reach the real API and paint, and the layout is not broken. **What it does
NOT close:** a person's judgement of whether this reads right. A screenshot proves the pixels exist;
it does not prove they are the pixels Evan wants. That remains his, and it is what his acceptance
gate is for.

## What renders correctly

All seven states of the approved mock are reachable by URL fragment (`#agree`, `#buckets`,
`#changed`, `#disagree`, `#gate`, `#alias`, `#probe`) and all seven paint against live data.

The house style is right: GIMS's Watery palette, the seven-tab strip, the picking column on the
left with its nine numbered operations, the verdict banner spanning both panes, the four-stage
GATE / COMPILE / PROBES / EXECUTE strip, and the generated SQL last and full width.

**The invented-data labelling is emphatic and works.** The masthead carries the amber
`⚠ INVENTED DATA` chip; a standing banner under it spells out that every record is invented and
names the database and row count; and **each answer pane carries its own `INVENTED` chip** — that is
ruling **B31**, the one deliberate addition beyond the drawing, made because a screenshot of the
panes alone is exactly what gets pasted into a message to an employer. **Seeing it rendered, B31 was
the right call:** in `04-disagree.png` the pane headers are legible on their own, and each one says
`INVENTED` without the masthead being in frame.

**The disagreement state is the demo working.** `04-disagree.png`: a coral `≠` banner reading *"The
panes disagree on one row"*, the sentence *"Nothing on the SQL side reported an error — on its own it
returned a plausible number. This is the finding, not a fault the demo suffered"*, the values called
out inline (**SQL says `1`, Python says `1e+300`**, key `edge-01`, column `biggest`), a `1 ROW
DIFFERS` chip on the pane pair, and the `edge-01` row itself struck through with a coral `≠` marker
while the other nine carry green ticks.

## FINDING — the column carrying the disagreement is clipped at the design's own target width

**This is the one thing looking at it found that reading it could not.**

The banner promises, in its own words, that *"the pair below opens at it — a disagreement is
**located**, not merely announced."* At **1440px, the design brief's stated target width**, it is
announced but not located:

- In the **SQL pane**, the `BIGGEST` column — the column the disagreement is *in* — is clipped at the
  pane boundary. The header reads `COLLECTION · KEY · DATA · BIGGE…` and the values are not visible.
- In the **Python pane**, the same column is off-screen entirely.
- At **1920px** (`08-disagree-1920.png`) the SQL pane's `BIGGEST` column becomes visible — **but the
  Python pane's is still clipped.** So widening the window does not fully solve it.

The reader can see *which row* differs, because the coral `≠` marker is on the row. They cannot see
*the two values that differ* without scrolling horizontally inside the pane — even though the banner
above has just told them what those values are.

**Severity is a judgement, not a defect claim.** Nothing is wrong: no number is incorrect, the
correct row is marked, and the values are stated in the banner. The `DATA` column is wide and carries
raw JSON, which is what pushes the computed column off the edge. But the pane pair's stated purpose
is to *locate* the disagreement, and at the target width it does not quite. **This belongs in Evan's
acceptance decision** — it is a layout call, it is cheap to change now (narrow or truncate `DATA`,
or float the differing column adjacent to the marker), and it is exactly the class of thing his
Q27 look sign-off existed to catch.

## Two mock-vs-shipped divergences, already recorded in `demo/VERIFY.md`

1. **State 7** draws `inf` in the mock; the shipped screen correctly reports `raised` /
   `OverflowError`. That is the **AC-17 correction** landing — the mock was drawn before we learned
   that Python raises rather than producing an infinity. **The screen is right and the drawing is now
   out of date.** Evan approved the drawing, so he should know the shipped behaviour is the corrected
   one.
2. The mock names `edge-04` where the shipped seed puts `huge` on `edge-03`.

## The files

| file | what it shows |
| --- | --- |
| `01-agree.png` | Agreement — green banner, 8 of 8 identical |
| `02-buckets.png` | Time buckets |
| `03-changed.png` | Only what changed |
| `04-disagree.png` | **The disagreement — the centrepiece**, at 1440 |
| `05-gate.png` | Refused: the expression (layer 1, the static gate) |
| `06-alias.png` | Refused: the column name |
| `07-probe.png` | Refused while running (layer 2, the runtime probe) |
| `08-disagree-1920.png` | The same disagreement at 1920, showing the clipping is width-driven |

Captured headless at `--virtual-time-budget=9000` so animation and data-fetch had settled.
Nothing was downloaded; the demo stack was untouched; Evan's live `glp-strong-db` on 55433 was never
connected to.
