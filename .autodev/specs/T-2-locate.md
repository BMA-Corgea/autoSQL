# T-2 — Locate

**Where the demo lands, what it builds on, what it must not touch, and what this machine
actually has.**

| | |
|---|---|
| Ticket | `T-2` · stage `locate` · pipeline `feature@v1` + `design@v1` |
| Written | 2026-08-22 |
| Process | **FULL, not lean** — `.autodev/shop.json → settings.lean = false`, set 2026-08-22 under GA-6 (wrap-up item 5, *"Run the rest full"*) |
| Inputs | `.autodev/specs/T-2.md` (signed, 2,546 lines, 45 AC, R1–R19) · `.autodev/specs/T-2-punchlist.md` (16 items) · `design/t2-demo.md` (D1–D15) + `design/t2-demo-mock.html` (**approved as drawn**, Evan, 2026-08-22, GA-6) · `.autodev/specs/T-2-queue.md` |
| Companion | `.autodev/specs/T-2-plan.md` — the ordered build plan and the sixteen punch-list resolutions |

**What this document is for.** The repo is greenfield for the demo: **there is no `demo/`
directory, no seed script, no application.** So "locate" here cannot mean *find the code that
changes*. It means four things instead, and this document is those four:

1. **The exact file tree the build creates** — every path, with what is in it and which criterion
   or ruling forces it (§3).
2. **What already exists that it builds on** — the T-1 throwaway prototype, the `expr.py` to be
   vendored, the six Watery style assets, and the approved mock's own markup (§4).
3. **What it must not touch** — enumerated, with the reason each fence exists (§5).
4. **Every external dependency, at the version actually present on this machine** — verified by
   running the check, not assumed (§6).

§7 collects **eleven things found while locating that neither the spec nor the design settles** —
five of which would stop the build dead if a builder met them cold. They are resolved in the plan,
not here; locate names them and says where the resolution lives.

**Words used here.** *Ruling on delegated authority* — a decision a session took **for** Evan under
a recorded go-ahead rather than one he made himself; always labelled, always showing its derivation,
always overturnable by one line from him. *R1–R19* are the spec's rulings, *D1–D15* the design
brief's, *B1–B27* the plan's. *AC-n* are the spec's 45 acceptance criteria. A bare **§** means a
section of `.autodev/specs/T-2.md`; **part n** means a part of `design/t2-demo.md`.

---

## 1. The starting state, verified today

Everything below was re-read or re-run on **2026-08-22** on this Linux box. Where a figure differs
from a document already in the repo, the difference is stated rather than smoothed over.

| Fact | Verified how | Result |
|---|---|---|
| There is no `demo/` directory and no `./run-demo` | `find . -path ./.git -prune -o -type f -print` | **Confirmed. Nothing has been built.** |
| The spec is on disk at its new path | `wc -l .autodev/specs/T-2.md` | **2,546 lines** (the `refine` receipt's "1,874" is wrong; the handoff already records this) |
| The punch list is on disk | `wc -l .autodev/specs/T-2-punchlist.md` | 77 lines, 16 numbered items |
| The design brief and mock are on disk | `wc -l design/t2-demo.md design/t2-demo-mock.html` | 523 and 1,990 lines |
| The mock is self-contained | one `<style>`, one `<script>`, 110,747 bytes, no external asset reference | Confirmed — see §4.4 for what that means for the build |
| The look sign-off is recorded | ticket passport | *"unblocked at queue: Look sign-off GIVEN by Evan 2026-08-22 under GA-6: wrapup item 3 = 'Approve as drawn'"* |
| The ticket is at `locate` | `.autodev/tickets/T-2-…json → stage` | `locate`, status `locating` |
| The process is full | `.autodev/shop.json → settings.lean` | **`false`** |
| Working tree | `git status` at session start | clean; **T-2's spec, punch list and design are committed** (`f274cd7` and its four predecessors) — the previous handoff's "everything is uncommitted" no longer holds |

---

## 2. The one-paragraph shape of the thing being located

The demo is **one new directory and one new executable**, plus one check that deliberately lives
outside them. It is a small FastAPI process serving committed React bundles on `127.0.0.1:8787`,
talking to a Postgres container it creates itself on `127.0.0.1:55440`, seeded with 10,410 invented
records. Every pick the person makes goes through **gate → compile → probes → execute**, and the
answer is computed **twice** — once by generated SQL and once, independently, by a Python runner
reading the same source rows — and both are shown side by side. That doubling is not a feature; it
is the correctness control §5 of the spec spends its whole length defending, and D5 pins it in CSS
so it cannot be collapsed away.

---

## 3. The file tree the demo creates

Every path below is new. Nothing in this table modifies an existing file except the two marked
**(edit)**.

### 3.1 The demo tree — `demo/` and `./run-demo`

**"The demo tree" is a defined term** (§11.1): *the directory `demo/` and the executable
`./run-demo` at the repo root — nothing else.* AC-3's forbidden-string grep runs over exactly that
set, and AC-4's neighbour check is deliberately kept **outside** it.

```
run-demo                                  # the executable — up | down | build-ui | test   (R8)
demo/
├── README.md                             # what this is, that the data is invented, no speed claim (AC-37)
├── WALKTHROUGH.md                        # the 14 do-this-expect-that steps (§10) + the glossary punch-list 16 asks for
├── expected-answers.json                 # written by the seed; §8.5; kept unless Evan says otherwise (§14.2 item 1)
├── manifest.json                         # sha256 of every vendored file + the two spike files (AC-33, AC-34 manifest half)
├── requirements.txt                       # pinned, installed --no-index from the wheelhouse (§6.3, B24)
├── compose.yaml                          # the demo's own Postgres: name, port, volume, POSTGRES_INITDB_ARGS (§11.2)
│
├── server/                               # the FastAPI app  (§9.1)
│   ├── __init__.py
│   ├── app.py                            # routes: GET /  ·  GET /api/fields  ·  POST /api/pick
│   ├── db.py                             # THE ONLY connection factory. Refuses any port but 55440 (AC-2c)
│   ├── settings.py                       # the two pinned session values + the compose-file constants
│   └── errors.py                         # Refused / RuntimeRefusal — the two refusal shapes §9.3 renders
│
├── gate.py                               # LAYER 1. gate(ast) + validate_alias(). Safety-critical (§4.4, §4.10, R10)
├── builder.py                            # the query builder: SELECT/FROM/WHERE/GROUP BY/ORDER BY/LIMIT, the four
│                                         #   emitted column names agg|bucket|rolling_avg|changed (R8), the four
│                                         #   statement shapes, fragment namespacing (punch-list 11)
├── probes.py                             # LAYER 2. members (a) and (b) of §4.5, built from the compiled operands
├── legality.py                           # which operation combinations are legal — punch-list 5, X1/X2 and beyond
│
├── pyrunner/                             # the second, independent calculator  (§9.5, Q24)
│   ├── __init__.py
│   ├── rows.py                           # reads the SOURCE rows out of Postgres; the double parse (punch-list 7)
│   ├── evaluate.py                       # drives the vendored expr.py over each row
│   ├── shape.py                          # filter · sort · cap · aggregate · bucket · window · changed, in Python
│   ├── order.py                          # §7.4's comparator, written out: cross-type order, C collation, two nulls
│   └── decimals.py                       # the exact-decimal rule: Decimal(str), ROUND_HALF_UP, quantize to 6
│
├── seed/
│   ├── __init__.py
│   ├── schema.sql                        # CREATE SCHEMA demo; CREATE TABLE demo.records (§8.2). No index (AC-12)
│   ├── generate.py                       # the three collections, from a fixed seed (§8.3, §8.4, R5/R16/R17/R18/R19)
│   ├── load.py                           # installs runtime.sql unmodified, then COPYs the rows in (§9.6)
│   └── expectations.py                   # writes expected-answers.json. MAY NOT IMPORT pyrunner/ (punch-list 8, B8)
│
├── vendor/
│   ├── expr.py                           # byte-identical copy, sha256 90cbb56d…  (§9.5, R4, AC-34)
│   ├── NOTICE.md                         # where each vendored file came from and under what ruling
│   ├── styles/
│   │   ├── watery.css                    # 684dc2cc…   (D1)
│   │   ├── dashboard.css                 # 0fb91d03…
│   │   ├── shell.css                     # 894b642b…
│   │   └── components.css                # 13d256f6…
│   ├── icons.svg                         # 4c8ef897…   — GIMS's 54 symbols
│   ├── ui.jsx                            # df7ac592…   — Icon, StateBlock, GridTable, MultiSelect
│   └── wheels/                           # the committed wheelhouse (§6.3, B24) — pip install --no-index
│
├── frontend/
│   ├── build.mjs                         # esbuild, GIMS's own shape (§9.1); ONLY ./run-demo build-ui runs it
│   ├── app.jsx                           # the screen: three regions in part 2's order
│   ├── pick.jsx                          # the nine controls, part 3.1.1's shapes; DR-2's disabled states
│   ├── verdict.jsx                       # the verdict banner — DR-1's three independent signals
│   ├── panes.jsx                         # .pane-pair, the spine, the per-row ✓ / ≠ mark (D5, D8)
│   ├── sqlpane.jsx                       # .sql-slab, .sql-bind, .sql-alias, the session strip (D6, §9.3)
│   └── rail.jsx                          # GATE ▸ COMPILE ▸ PROBES ▸ EXECUTE
│
├── static/
│   ├── index.html                        # links vendor/styles/*.css, then demo.css, then the bundles
│   ├── demo.css                          # ONLY part 5.2's new classes. NOT a copy of watery's tokens (§7.4)
│   ├── icons-demo.svg                    # the 18 symbols the mock draws that GIMS's sprite does not have (§7.3)
│   ├── fonts/                            # Inter woff2, self-hosted (D11, AC-32)
│   └── js/                               # THE COMMITTED BUNDLES — vendor.js + app.js (AC-36). NOT dist/ (§7.1)
│
└── tests/
    ├── conftest.py
    ├── test_gate.py                      # AC-14 — 48 construct rows + all 12 tags + a 13th
    ├── test_alias.py                     # AC-38, AC-45
    ├── test_probes.py                    # AC-17, AC-18
    ├── test_builder_sql.py               # AC-24(c), AC-40(c), AC-41(a), AC-43(a)
    ├── test_legality.py                  # punch-list 5's matrix — every illegal combination is disabled
    ├── test_order.py                     # AC-41(b)(c)(d)(e), AC-44
    ├── test_decimal.py                   # AC-24(b)(d)
    ├── test_data.py                      # AC-7 … AC-13
    ├── test_isolation.py                 # AC-2, AC-3, AC-5, AC-6
    ├── test_walkthrough.py               # AC-30, AC-31, AC-22, AC-23, AC-40(a)(b)(d)
    ├── test_vendor.py                    # AC-33, AC-34, AC-35, AC-39 — the loud-skip machinery
    ├── test_ui.py                        # AC-20, AC-25, AC-26, AC-29, AC-40(e), AC-43(d)
    └── fixtures/expected_step8.json      # the hand-computed short-window numbers (AC-24(d))
```

### 3.2 Outside the demo tree, on purpose

| path | why it is outside | forced by |
|---|---|---|
| `ops/checks/neighbour-ports.sh` **(new dir)** | It records `docker ps` and `ss -ltn` around a run and asserts every listener on every port **other than 55440 and 8787** is unchanged. It has to name ports, and AC-3 greps the demo tree for `55433` — so a check *about* the neighbour container may not live inside the tree it is checking | AC-4, §11.1 |
| `.autodev/specs/T-2-locate.md`, `-plan.md` | Stage documents, not demo code | this ticket |
| `.autodev/handoffs/T-2.md` **(edit)** | The handoff procedure | this ticket |
| `kb/CURRENT-WORK.md` **(edit)** | The NOW layer is updated at every handoff — this stage rewrote T-2's live-edge bullet | KB doctrine |

`ops/` today holds only `notify-telegram.sh` and `autodev-watch-windows.ps1`; `ops/checks/` does not
exist and is created by this ticket.

### 3.3 Counts, so the build has a target

| | |
|---|---|
| New directories | 12 (`demo/` + 10 subdirectories + `ops/checks/`) |
| New Python modules | 21 |
| New JSX modules | 6, plus one `build.mjs` |
| Vendored files, byte-identical | **7** — `expr.py` + the six style assets (D1); **plus** the wheelhouse |
| Committed build products | 2 bundles under `demo/static/js/` (AC-36) |
| Existing files edited | **2**, both process documents (`.autodev/handoffs/T-2.md`, `kb/CURRENT-WORK.md`) |
| Existing product files edited | **0** |

---

## 4. What already exists that the demo builds on

Four bodies of existing material. Each is **read and copied, never edited** — three of them because
a criterion checksums them, the fourth because it is a drawing.

### 4.1 The T-1 throwaway prototype — `spikes/T-1/proto/`

Reused **as-is** on Q19's instruction, checksummed by AC-33, and never imported by anything else in
this repo before now. Two files matter; the other 27 in that directory are the investigation's own
instruments and are not touched.

| file | size | what the demo uses it for | verified today |
|---|---|---|---|
| `spikes/T-1/proto/compile.py` | **464 lines** | `compile_ast(ast, column="data", ctx_param="ctx") -> Compiled(sql, params)`; `render_for_display(sql, params, …)` for the SQL pane | opened; `compile_ast` at `:432`, `render_for_display` at `:450`, `_bind` at `:159-164`, dispatch at `:196` |
| `spikes/T-1/proto/runtime.sql` | **427 lines** | the 21 `xpr.*` helper functions the compiled SQL calls; installed **unmodified** into the demo database, 297-digit guard included | opened; `xpr.f8` at `:28-38`, `xpr.num` at `:44-56` |

**Facts about `compile.py` the build must not re-derive.**

- It imports only `math` and `typing` (`:42-45`). Reusing it drags **no** GIMS dependency in.
- It compiles **all 22** builtins and `%`. `Uncompilable` therefore cannot enforce the safe subset —
  which is exactly why `demo/gate.py` exists (R3, §4.3).
- Its parameter style is `%(name)s` and `_bind` names parameters **`p0`, `p1`, …** counting from
  zero **per `_Compiler` instance**. Every `compile_ast` call constructs a fresh `_Compiler`
  (`:437`), so **two fragments compiled separately both start at `p0`**. That is punch-list item 11,
  confirmed by reading the file rather than inferred. Resolution: plan **B11**.
- `compile_ast` contains a defensive stray-`%` check whose body is `pass` (`:439-441`) — it detects
  nothing. The alias allowlist (§4.10) is what actually keeps `%` out of the statement.
- Its docstring says **"THIS IS NOT A LIBRARY"**. Q19 lifts that for this ticket only; the line stays
  where it is and the demo's import carries a comment naming Q19 (§4.7).

**A fact about `runtime.sql` the build must not re-derive.** The guard literal at `:33` and `:51` is
`17976931348623157` followed by **280 zeros — 297 digits**, i.e. the exact value
**`1.7976931348623157e+296`**. The spec renders it as `1.797693134862316e+296` (§5, §4.5), which is
that value's float8 round-trip at 16 significant digits, not the literal. Punch-list item 15 is
**correct**; the plan carries the exact form (**B15**). And the guard **returns `NULL`, it does not
raise** (`:33-34`) — which is why §4.5's probe may never be routed through `xpr.f8` or `xpr.num`.

**`spikes/T-1/proto/gen_data.py` (65 lines) is a partial source, not a whole one.** §8.3 takes its
**record rule** for `noun:Sample` (`:25-46`) — `id`, `status`, `due_date` with 5% omitted (`:30-31`),
`priority`, and 5–15 mixed-type `field_0…field_14` keys including an object (`:46`) and a JSON null
(`:43-44`). It does **not** take that file's **key format**: `f"S-{i}"` at `:58` is unpadded and
orders `S-0, S-1, S-10, S-100, …` as text, which R19 replaces. It contains **no heartbeat generator
at all** — no `sender_id`, no `ts` — so the heartbeat is written from scratch against §8.3 and
R16/R17. Its row count comes from `argv` (`:63`); R18 fixes it at 2,000.

### 4.2 The GIMS evaluator — vendored, not imported

`../GIMS-Project/core/dashboard/expr.py` and
`../GUTS/spine/L1-memory/gims-ledger/core/dashboard/expr.py` are **byte-identical**, re-verified by
`sha256sum` today:

```
90cbb56d04b08b825ef38dbd1b805ad2b877a0f5e5154e2dc38d9944f4ad4c49
```

R4 vendors it to `demo/vendor/expr.py` with that digest in `demo/manifest.json`. The demo uses both
halves of it: the **parser**, which produces the AST that `demo/gate.py` walks and `compile.py`
compiles, and the **evaluator**, which computes the Python pane's per-row values. Nothing in the
demo's run-time path opens either checkout — that is obligation 1 of §3, and it is the whole reason
the copy exists.

### 4.3 The six Watery style assets — vendored (D1, D2)

All six re-verified today against the GUTS tree, all six matching the digests part 1.1 recorded:

| vendored to | sha256 | lines |
|---|---|---|
| `demo/vendor/styles/watery.css` | `684dc2cc4eecb6eb69467af22593a5411fe15f322f6c7aaa99065c0ac013132e` | 242 |
| `demo/vendor/styles/dashboard.css` | `0fb91d03fb0a9269e4eeba33405c46277dad70ed4c60775ae395872ecaafc706` | 179 |
| `demo/vendor/styles/shell.css` | `894b642ba54f5d178c4f7f7598dff9cdea5517c8edce55a3a6cce925ffd9feca` | 219 |
| `demo/vendor/styles/components.css` | `13d256f66cd5cc38ee6b0b0beed8be5296aa2cfe2593a3e5e2efbc6347a48959` | 187 |
| `demo/vendor/icons.svg` | `4c8ef8978924095ab365e88478d1075d9d0c8215a337f6b925b045c445e0d5cc` | 75 (**54 symbols**) |
| `demo/vendor/ui.jsx` | `df7ac5925b437e0abc0a8adee39b2af8c988025905f8ec34321a252c3739a53c` | 487 |

**Whole files, never fragments** (D2) — a fragment cannot be checksummed against its source, so a
fragment is a fork nobody notices has drifted.

**`watery.css:8` imports Inter from Google Fonts.** That is D11's whole premise, and it is real:
offline the `@import` is a no-op and the screen silently falls back to the system sans. D11 forbids
editing the vendored file, so Inter is **self-hosted** under `demo/static/fonts/` and declared by
`demo/static/demo.css`, loaded **before** `watery.css`.

### 4.4 The approved mock — `design/t2-demo-mock.html`

**Approved as drawn by Evan on 2026-08-22 (GA-6, wrap-up item 3). The build copies it exactly.**
It is 110,747 bytes, one `<style>`, one `<script>`, seven states reachable by tab, keyboard and URL
fragment (`#agree #buckets #changed #disagree #gate #alias #probe`), and **176 distinct CSS
classes**. What the build takes from it, and what it must not:

| what | take it? | why |
|---|---|---|
| The seven states' **markup and class names** — `.verdict`, `.cmp` / `.spine` / `.cmp-grid`, `.sql-scroll`, `.gw-*` (the gate walk and the `.gw-never` struck-through statement), `.op` / `.op-ctl` / `.op-why` / `.ctl-fixed`, `.sel-wrap` + `.caret`, `.rail` / `.stop`, `.beatgrid`, `.reduce` | **yes, verbatim** | This is the approved appearance. The React components render this markup |
| The `<script>`'s **live DR-2 logic** — changing the source re-derives which operations are disabled | **yes, as a behavioural spec** | Part 3.1.2 measured it: `noun:Heartbeat → noun:EdgeCase` takes the disabled count 0 → 3, focus stays on the select. The React version must do the same |
| The **inlined `:root` token block** | **NO** | Compared today: the mock's `:root` is watery.css's minus `--blue-deep` plus `--mono`. Copying it into `demo.css` would be a **fragment fork** of `watery.css` and would break D2 and D1's drift check. The build links the vendored `watery.css` and `demo.css` adds only part 5.2's new classes |
| The **30 `<symbol>` icons** | **partly** — see §7.3 | 12 of the 30 exist in GIMS's sprite; **18 do not**, and three of the 12 have different path data |
| The `<style>` block's rules for `.panel`, `.field`, `.input`, `.select`, `.toggle`, `.btn`, `.chip`, `.count-pill`, `.icon-chip` | **NO** | These are watery.css's own primitives, reproduced inline so the mock could be a single file. In the build they come from the vendored stylesheet |

**The rule that follows, and it is the one a builder gets wrong:** the mock is a *single-file
drawing*, so it inlines everything. The build is a *linked application*, so it inlines nothing that
a vendored file already provides. **`demo/static/demo.css` contains only the ten new classes part 5.2
justifies** — `.verdict`, `.gims-state.is-refused`, `.sql-slab` + `.sql-bind` + `.sql-alias`,
`.pane-pair`, `.sel-wrap` + `.caret`, `.ctl-fixed`, `.op-why`, `.is-focus` / `.is-invalid`,
`.gw-never`, `.cmp.is-diff` — plus the `@font-face` block D11 requires. A grep test asserts `demo.css`
declares **no `--` custom property on `:root`**; that one assertion is what keeps the fork out.

---

## 5. What the build must not touch

Each fence, the reason it exists, and the thing that catches a breach.

| # | Do not touch | Why | Caught by |
|---|---|---|---|
| 1 | **`/home/corgea/Desktop/Coding Projects/GIMS-Project`** — read-only | The "don't build yet" tick governs GIMS; nothing enters it until T-3 and T-4 pass (`kb/wiki/decision-expr-to-sql.md` §6, confirmed by Evan's wrap-up item 2 today). This demo is separate and green-lit | **AC-35** — `git status` clean in the tree, no `__pycache__` mtime inside the build window |
| 2 | **`/home/corgea/Desktop/Coding Projects/GUTS/spine/L1-memory/gims-ledger`** — read-only | Same, and Q12 leaves this copy alone in any case | **AC-35** |
| 3 | **Evan's live container `glp-strong-db`, host port `55433`** | Its role `glp_owner` also owns the live `glp_strong` database. **Running right now** — confirmed today: `pgvector/pgvector:pg16`, `0.0.0.0:55433->5432/tcp`, up 2 hours, healthy. A previous session created a database on it and that was called out as a defect | **AC-3** (grep of the demo tree for `55433`/`glp_owner`/`glp_strong`/`glp-strong-db`), **AC-4** (`ops/checks/neighbour-ports.sh`, by port number, from outside the tree), **AC-2(c)** (the connection factory raises rather than dials any port but 55440) |
| 4 | **`spikes/T-1/proto/compile.py`** and **`spikes/T-1/proto/runtime.sql`** | Q19 said *as-is*. Editing either would remove §5's visible defect, which walkthrough step 11 exists to show | **AC-33** — sha256 against `demo/manifest.json` |
| 5 | **Anything else under `spikes/`** | It is the T-1 investigation's evidence. The demo reads two files out of it and writes nothing into it | code review; nothing in the demo tree opens a path under `spikes/` for writing |
| 6 | **`tracker.mjs`, `.autodev/tickets/`, `.autodev/events.jsonl`** | The dispatching session is the single writer. This is a standing repo rule | this stage wrote none of them |
| 7 | **`.autodev/notes/ANSWERS-FROM-EVAN.md`, `.autodev/notes/QUESTIONS-FOR-EVAN.md`, `.autodev/notes/WRAPUP-FOR-EVAN.md`** | They are the record of what he said. `.autodev/notes/ANSWERS-FROM-EVAN.md`'s "Still outstanding" list is known to be stale (§7.1's operation-9 ruling says so) and is still **not this ticket's to edit** | code review |
| 8 | **The `xpr` schema** | `runtime.sql` is installed unmodified (§9.6). The demo's own probes live in the demo's own schema and never touch `xpr` | **AC-33**, plus a grep asserting no `CREATE`/`ALTER`/`DROP` in the demo tree names `xpr` |
| 9 | **Any index** | Q11: *"index work stays off."* Four `xpr.*` functions are declared `IMMUTABLE` while reading a session setting, and T-1 measured the consequence: the same query over the same 200 rows returned **0 rows with an index and 200 without** | **AC-12** — `pg_indexes WHERE schemaname='demo'` returns exactly **one** row (the primary key, R6) |

**One nuance on fence 3 that the build has to get right.** AC-2(c) requires the connection factory to
return the compose file's DSN *with* `AUTOSQL_SPIKE_DSN`, `PGHOST`, `PGPORT`, `PGPASSWORD` and
`PGSERVICE` set to nonsense in the environment. That is not achieved by unsetting them — a test can
only unset what it knows about. It is achieved by **passing every libpq connection parameter
explicitly**, because libpq's environment variables are *defaults consulted only when the parameter
is absent*. Punch-list items 13 and the plan's **B13** turn that into a single enumerated list and a
test.

---

## 6. External dependencies, at the versions actually on this machine

**Verified by running the check on 2026-08-22, not assumed.** Q26 scopes this to *"Linux and Docker
only"*, so these are the only versions that have to work.

### 6.1 Present and sufficient

| dependency | version found | how checked | what turns on it |
|---|---|---|---|
| **Docker Engine** | **29.1.3** (build `29.1.3-0ubuntu3~24.04.2`) | `docker --version` | `./run-demo up` / `down`, AC-1, AC-2(a), AC-6 |
| **Docker Compose** | **v2.29.2** (the `docker compose` subcommand, not `docker-compose`) | `docker compose version` | `demo/compose.yaml`. **Write `docker compose`, never `docker-compose`** — the v1 binary is not on this machine |
| **Postgres image** | **`postgres:16-alpine` present locally**, id `sha256:de3a4eab…`, 294 MB, created 2026-07-07. `postgres:16` (451 MB) and `pgvector/pgvector:pg16` (438 MB) also present | `docker images` | AC-32's *"no network access beyond pulling the Postgres image"* — on this machine **not even that pull is needed** |
| **Python** | **3.12.3**, `/usr/bin/python3` | `python3 --version` | everything server-side. `decimal`, `json`, `re`, `hashlib` are stdlib; `expr.py` and `compile.py` need nothing else |
| **pip** | 24.0 | `python3 -m pip --version` | see §6.3 |
| **venv** | available | `python3 -m venv --help` | see §6.3 |
| **pytest** | **7.4.4** (system) | `python3 -m pip list` | the suite — but it will be installed into the demo's venv at a pinned version, not taken from the system |
| **Node** | **v22.22.2**, npm **10.9.7** | `node --version` | **`./run-demo build-ui` only.** `up` must work with `node` removed from `PATH` (AC-36) |
| **`ss`** | present (`iproute2`) | `ss -ltn` ran | AC-4's neighbour check, AC-5's port-in-use check |

### 6.2 Absent, and it matters

| dependency | state | consequence |
|---|---|---|
| **`psycopg2` / `psycopg`** | **NOT INSTALLED.** Only the type stubs `types-psycopg2 2.9` are present | The T-1 spike's own scripts `import psycopg2` and could not run today either. The demo needs a driver, and it has to come from somewhere — §6.3 |
| **`fastapi`, `starlette`, `pydantic`** | **NOT INSTALLED** | §9.1 requires a FastAPI server. Same problem |
| **`uvicorn`** | 0.27.1 present system-wide | Useful, but the demo must not depend on a system package it did not install |
| **`esbuild`** | **not on `PATH`** | `npx esbuild` will fetch it on first use, which is a network dependency at `build-ui` time only. `build-ui` is explicitly the one verb allowed to need Node (§11.1); AC-32 and AC-36 concern `up` and `test`, which never run it |
| **`psql` / `pg_isready`** | **not installed** | The seed and the readiness wait may **not** shell out to `psql`. Readiness is polled through the Python driver, and the bulk load uses the driver's `COPY` rather than `psql \copy` |
| **`playwright`** | **NOT INSTALLED** (the design stage used 1.61.1 — that install is gone or was elsewhere) | AC-20/AC-25/AC-29/AC-40(e)/AC-43(d) are described as "a UI test". Plan **B26** rules what a UI test is here without a browser install |

### 6.3 The dependency conflict the spec did not notice — and where it is resolved

**AC-32:** *"The suite passes from a clean checkout with no network access beyond pulling the
Postgres image. Test: `./run-demo test` on a fresh clone."*

**§9.1:** *"a small FastAPI server."*

On this machine FastAPI, psycopg and pydantic are **not installed**, and `/usr/lib/python3.12/
EXTERNALLY-MANAGED` exists — so PEP 668 blocks `pip install` into the system interpreter anyway. A
fresh clone therefore cannot run `./run-demo test` without either a network fetch from PyPI (which
AC-32 forbids) or the packages arriving with the repo.

PyPI **is** reachable from here today (`https://pypi.org/simple/psycopg2-binary/` → 200), so this is
not a blocker; it is a decision about where the bytes live. It is resolved in the plan as **B24** —
a committed wheelhouse under `demo/vendor/wheels/`, installed into `demo/.venv` with
`pip install --no-index --find-links demo/vendor/wheels -r demo/requirements.txt`. That keeps AC-32
literally true, keeps FastAPI per §9.1, and works under PEP 668 because a venv is not
externally managed. `.venv/` is already in `.gitignore`; `demo/vendor/wheels/` is not and must not be.

### 6.4 Two `.gitignore` traps

`.gitignore` today ignores **`dist/`** and **`build/`** at any depth, and `__pycache__/`, `*.py[cod]`,
`.venv/`, `node_modules/`.

1. **The committed bundles must not live in a directory called `dist/` or `build/`.** AC-36 requires
   the front end to run *from committed bundles with no Node present*, and a bundle in `demo/dist/`
   would be silently untracked — the check would pass on the build machine and fail on a fresh clone,
   which is the worst possible shape for a criterion. **The bundles go to `demo/static/js/`** (§3.1),
   and a test asserts `git check-ignore` reports them tracked.
2. **`demo/frontend/build.mjs` must not be confused with GIMS's `build.mjs`.** GIMS's own build file
   is the *pattern* (§9.1, read at spec time); the demo's is a new file in `demo/frontend/`.

---

## 7. Eleven things found while locating that neither the spec nor the design settles

These are **not** the punch list. The punch list's sixteen were found by the sixth spec review;
these were found by putting the file tree, the mock and this machine side by side. Five of them
(**L1, L4, L5, L8, L11**) would stop a builder cold. Each is resolved in
`.autodev/specs/T-2-plan.md` at the ruling named in the last column.

| # | What is missing | Why it bites | Resolved at |
|---|---|---|---|
| **L1** | **18 of the mock's 30 icons do not exist in GIMS's sprite.** GIMS's `static/icons.svg` carries 54 symbols. The mock draws 30. The overlap is 12 — and of those 12, **`i-play`, `i-plus` and `i-search` have different path data** in the mock than in GIMS. The other 18 (`i-ban i-cap i-caret i-code i-columns i-dash i-drop i-neq i-pin i-pulse i-python i-quote i-shield i-shield-stop i-sigma i-sort i-wave i-x`) exist **only** in the approved mock. Part 1.1 vendors `icons.svg` "because `Icon` resolves `/static/icons.svg#i-<name>`", and never noticed the shortfall. `i-neq` in particular is one of DR-1's five independent disagreement signals | The approved screen cannot be rendered from the vendored sprite alone, and D1/D2 forbid editing it | **B17** |
| **L2** | **The mock inlines a near-copy of `watery.css`'s `:root`** (its tokens minus `--blue-deep`, plus `--mono`) | A builder copying the mock's `<style>` into `demo.css` creates an undetectable fork of the vendored stylesheet and defeats D1's drift check | **B18** |
| **L3** | **`.gitignore` ignores `dist/` and `build/`** while AC-36 requires *committed* bundles | The bundle would pass on the build machine and be absent on a fresh clone | **B19** |
| **L4** | **No Postgres driver and no FastAPI on this machine**, and PEP 668 blocks installing into the system interpreter — against AC-32's *"no network access beyond pulling the Postgres image"* | `./run-demo test` on a fresh clone cannot run at all | **B20** |
| **L5** | **No `psql` and no `pg_isready`** | The obvious readiness wait (`until pg_isready`) and the obvious bulk load (`psql \copy`) both fail with *command not found*. `./run-demo up` would appear to hang | **B21** |
| **L6** | **No Playwright / browser automation installed**, while five criteria say *"a UI test asserts…"* (AC-20, AC-25, AC-29, AC-40(e), AC-43(d)) | Either the suite silently drops those assertions or `up`/`test` grows a browser dependency AC-32 cannot afford | **B22** |
| **L7** | **`./run-demo test` does not say whether it starts the stack.** AC-2(a) inspects a running container, AC-2(b) requires the app to answer on 8787, AC-30 performs all 14 walkthrough steps — yet AC-32 runs `test` "on a fresh clone" where nothing is up | A suite that assumes a running stack fails confusingly on a clean machine; one that always brings its own collides with a stack the person is already driving | **B23** |
| **L8** | **`noun:EdgeCase` is specified as "10 rows, one purpose each" and only five purposes are named** (§8.3's table). AC-7 asserts exactly 10 | Five rows have no content, and AC-7 fails or the build invents unlabelled filler in the one collection whose whole point is that every row is labelled | **B24** |
| **L9** | **Nothing says how many rows the answer panes render.** Walkthrough step 2 returns 8,400 rows and asserts both panes agree "row for row"; the mock's agreement view shows **eight** rows | 8,400 rows painted twice is a slow screen and an unreadable one; but AC-41(c) compares the panes "element for element", which must be over the whole result, not the visible page | **B25** |
| **L10** | **AC-40(c) as written is unsatisfiable.** It requires operation 9's SQL to "contain **no arithmetic operator at all**" — but the expression it also requires, `data - 'ts'`, *contains a `-`*. `-` there is jsonb key-deletion, not arithmetic | A literal grep for arithmetic operators fails the criterion the moment the criterion's own required expression is present | **B3b** |
| **L11** | **Operation 7 with operation 6 set to `none` is undefined.** §7.1's time-bucket rule says *"What aggregates inside a bucket is operation 6's chosen function"*; part 3.1.1 lets operation 6 be `none`; nothing says what a bucketed pick with no aggregate emits | `SELECT bucket FROM … GROUP BY bucket` returns 7 rows of nothing, or the build invents `count(*)` silently | **B5c** |

---

## 8. Building in an isolated worktree

The build runs in its **own git worktree** (full process). Four consequences the plan's work items
have to respect, all of them about things that are **not** per-worktree:

| shared resource | the collision | what the build does about it |
|---|---|---|
| **The Docker container name `autosql-demo-db`** | Docker names are global to the daemon. Two worktrees running `./run-demo up` fight over one name and one volume | The name stays fixed (R8 pins it, AC-2(a) inspects it by name). `up` fails with a clear message if the name is taken by a container it did not create — the same shape as AC-5's port check |
| **Host ports 55440 and 8787** | Also global | AC-5 already requires `up` to refuse, naming the port. That refusal is what makes concurrent worktrees safe |
| **`../GIMS-Project` and `../GUTS/…`** | A worktree of `autoSQL` may sit somewhere else on disk, so `<repo root>/../GIMS-Project` resolves to nothing | §9.7 already provides the answer: `AUTOSQL_GIMS_TREE` and `AUTOSQL_GUTS_TREE`. **In a worktree these must be set, or AC-19 / AC-34's tree half / AC-35 skip loudly** — which is a correct outcome, not a failure, and AC-39 tests exactly it |
| **T-4's timing run** | T-4 needs an otherwise-idle machine and this build is exactly the heavy work that voids its numbers | Already sequenced: `.autodev/specs/T-2-queue.md` puts T-4 *not today*. Nothing for the build to do except not start T-4 |

Everything else the demo touches — `demo/`, `run-demo`, `demo/.venv`, the bundles — is inside the
worktree and needs no coordination.

---

## 9. Evidence — what was opened or run for this document

| Claim | How it was established, 2026-08-22 |
|---|---|
| No `demo/`, no `run-demo`, tree contents | `find . -path ./.git -prune -o -type f -print` |
| Spec / punch list / brief / mock sizes | `wc -l` on each |
| Docker 29.1.3, Compose v2.29.2 | `docker --version`, `docker compose version` |
| `glp-strong-db` is up on 55433 right now | `docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'` → `glp-strong-db pgvector/pgvector:pg16 0.0.0.0:55433->5432/tcp Up 2 hours (healthy)` |
| 55440 and 8787 are free | `ss -ltn` — neither appears among the listeners |
| `postgres:16-alpine` present locally | `docker image inspect postgres:16-alpine` → `sha256:de3a4eab8fdfa507ea92aac488b916b08089e515db49b055fe71dfa271ba3a28`, created 2026-07-07 |
| Python 3.12.3, pip 24.0, venv available, PEP 668 in force | `python3 --version`; `python3 -m pip --version`; `python3 -m venv --help`; `ls /usr/lib/python3.12/EXTERNALLY-MANAGED` |
| psycopg2 / psycopg / fastapi / starlette / pydantic / playwright absent; uvicorn 0.27.1 and pytest 7.4.4 present | one `__import__` loop over the eight names |
| `psql` and `pg_isready` absent | `which psql pg_isready` → not found |
| Node v22.22.2, npm 10.9.7, `esbuild` not on `PATH` | `node --version`, `npm --version`, `which esbuild` |
| PyPI reachable | `urllib.request.urlopen('https://pypi.org/simple/psycopg2-binary/')` → **200** |
| `expr.py` byte-identical in both GIMS trees at `90cbb56d…` | `sha256sum` on both paths |
| All six Watery assets match part 1.1's digests | `sha256sum` on each in the GUTS tree |
| `watery.css:8` imports Inter from Google Fonts | `sed -n '1,20p'` on the file |
| The mock's `:root` = watery's minus `--blue-deep`, plus `--mono` | regex diff of the two `:root` blocks |
| GIMS's sprite has 54 symbols; the mock has 30; 18 are new; `i-play`/`i-plus`/`i-search` differ | symbol-by-symbol comparison of the two files |
| `compile.py` — 464 lines, `compile_ast` at `:432`, `_bind` names `p{n}` per instance, stray-`%` check is `pass` | file opened at `:42-45`, `:150-230`, `:420-464` |
| `runtime.sql` — 427 lines; the guard literal is **297 digits**, value `1.7976931348623157e+296`; it returns NULL, never raises | file opened at `:25-60`; digit count taken mechanically |
| `gen_data.py` — 65 lines, `noun:Sample` only, `S-{i}` unpadded at `:58`, no heartbeat path | file read in full |
| `.gitignore` ignores `dist/`, `build/`, `.venv/`, `__pycache__/` | file read |
| `.autodev/shop.json → settings.lean = false` | file read |
| Ticket stage is `locate`; the look sign-off is in the passport | ticket JSON read (read-only) |

**Read-only throughout.** No file under `spikes/`, no file in either GIMS checkout, and no
`tracker.mjs` / `.autodev/tickets/` / `.autodev/events.jsonl` entry was written by this stage.
Nothing was connected to on port 55433.
