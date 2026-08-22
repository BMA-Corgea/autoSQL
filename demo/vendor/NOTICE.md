# `demo/vendor/` — what is here, where it came from, and under what ruling

Everything under this directory except `NOTICE.md` itself and `wheels/` is a **byte-identical
copy** of a file that lives in one of the two GIMS checkouts. Nothing here is edited, fragmented,
or recoloured — see `T-2-plan.md` rulings **D1**, **D2** and **R4**, and `T-2.md` §9.5 and §9.7.

Both source checkouts carry identical bytes for every file below (re-verified at vendoring time,
2026-08-22, by `sha256sum` — see `demo/manifest.json` for the recorded digests and
`demo/tests/test_vendor.py` for the drift check that re-runs this comparison against whichever
checkout is present at test time).

| vendored file | source (either checkout; both match) | ruling |
|---|---|---|
| `expr.py` | `core/dashboard/expr.py` | R4, §9.5 — the second calculator's parser and evaluator |
| `styles/watery.css` | `static/styles/watery.css` | D1, D2 — the `:root` tokens, `.panel`, `.icon-chip`, `.count-pill`, `.btn-primary`, fields, chips, motion |
| `styles/dashboard.css` | `static/styles/dashboard.css` | D1, D2 — `.w-card` / `.w-head` / `.w-body`, `.w-value-num`, the 6-hue chart palette |
| `styles/shell.css` | `static/styles/shell.css` | D1, D2 — `.gims-state`, `.gims-spinner` |
| `styles/components.css` | `static/styles/components.css` | D1, D2 — the `.ui-*` component layer `ui.jsx` renders into |
| `icons.svg` | `static/icons.svg` | D1, D2 — the 54-symbol sprite; `Icon` resolves `/static/icons.svg#i-<name>` |
| `ui.jsx` | `frontend/lib/ui.jsx` | D1, D2 — `Icon`, `StateBlock`, `GridTable`, `MultiSelect`. Imports only React |

**Source checkouts**, both siblings of this repository (§9.7):

- `GIMS-Project` — `../GIMS-Project`, absolute `/home/corgea/Desktop/Coding Projects/GIMS-Project`
- the GUTS spine copy — `../GUTS/spine/L1-memory/gims-ledger`, absolute
  `/home/corgea/Desktop/Coding Projects/GUTS/spine/L1-memory/gims-ledger`

Both are **read-only** to this ticket, always. Overridable at test time by the environment variables
`AUTOSQL_GIMS_TREE` and `AUTOSQL_GUTS_TREE`.

**Two files elsewhere in the repo carry digests in `demo/manifest.json` too, though they are not
copied here** — `spikes/T-1/proto/compile.py` and `spikes/T-1/proto/runtime.sql` are reused
**in place** (Q19: *as-is*), not vendored, so AC-33 checksums them where they already live.

## Why whole files, never fragments (D2)

A fragment cannot be `sha256sum`'d against its source, so a fragment is a fork nobody will notice
has drifted. Every file above is copied in full even where the demo uses only part of it — e.g.
`shell.css`'s unused rules are scoped to `.shell-*` and match nothing on this screen, and stay
anyway.

## The drift check (§9.7's four-part loud skip)

`demo/tests/test_vendor.py` re-hashes each vendored file against `demo/manifest.json` **always**
(no checkout needed — this is what AC-34's "manifest half" means), and separately re-hashes
`expr.py` and the six style assets against whichever GIMS checkout is present, when one is. When
neither `AUTOSQL_GIMS_TREE`/`AUTOSQL_GUTS_TREE` nor the default sibling paths resolve to a real
checkout, that second check **skips loudly** — reported `SKIPPED`, naming the path it looked for,
counted separately in the suite's summary — rather than silently passing or silently not running.
`./run-demo up` never depends on either tree in any circumstance; only this re-check does.
