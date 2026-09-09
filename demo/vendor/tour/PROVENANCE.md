# demo/vendor/tour — what is vendored here, and from where

| file | origin | licence |
|---|---|---|
| `tour.js`, `tour.css` | the `guided-tour` skill's shipped engine (`reference/`) | vendored unmodified; the steps are the product, the engine is not forked |
| `gnome-tour.png` | **`gims-oss`** — `github.com/BMA-Corgea/gims-oss`, `static/images/gnome-tour.png`, verified on `origin/main` | **AGPL-3.0**, the same licence autoSQL ships under |

**Why the gims-oss copy and not the one in the private checkout.** autoSQL is a public repo, so
vendoring an asset publishes it. `gnome-tour.png` is already published in `gims-oss` under a
licence that can be cited; the visually identical `Transparent gnome.png` at the root of the
private GIMS checkout is in no public tree. Taking the published one means the provenance question
never has to be answered after the fact.

**Why the gnome at all.** autoSQL is a **GIMS component, not a standalone product**. The tour uses
GIMS's own narrator rather than inventing an identity, and the bubble carries a **GIMS** byline.

That byline is rendered by `steps.js` (`ensureByline`), **not** by the engine. `tour.js`'s usage
comment documents `narrator: { image, name }`, and the engine reads `image` and ignores `name` —
so the first version of this sentence described something that did not exist, and a browser-run
record in `demo/EVIDENCE.md` claimed to have *confirmed* it. Both are corrected there, dated, and
`demo/tests/test_tour.py` now fails on any config key the engine does not read.

`tour.js` and `tour.css` are **not modified**. Everything specific to this UI lives in
`steps.js` (content) and `tour-tokens.css` (palette and per-skin placement).

### The digests, so "not modified" is checkable and not merely asserted

| file | sha256 |
|---|---|
| `tour.js` | `b341d9c9fcca7aa8def96fce53a51489ba16229dfd7a4fe836b63bf8c6c8c10d` |
| `tour.css` | `345e049617e379b79eea95d867120845738f6b94e697dcd1326838a837b2ab29` |
| `gnome-tour.png` | `7c192cb791e310fe239e17d949f6efbf760b218211e3add297e088a61c573727` |

`demo/tests/test_tour.py` reads this table and re-digests the files, so an edit to the engine
turns the suite red and names the file. It also compares against the skill's own
`reference/` copies **when that directory is present**, and says out loud when it is not —
the digests above were taken with both sides in hand and the `tour.js` / `tour.css` pair
matched byte for byte.


## Why these live under `demo/vendor/` rather than `demo/static/`

**Because this repo already has a home for third-party code, and its guards know about it.**
AC-37 — *no speed claim anywhere the demo's own words live* — excludes `demo/vendor/`, and
`test_ac37_the_vendor_exclusion_is_a_real_finding_not_an_assumption` exists specifically to prove
that exclusion is real rather than assumed.

The engine legitimately says `ms`: it has a `wait(ms)` helper and an `advanceDelay` option. That
is a third-party library's vocabulary, **not a claim this demo makes about speed** — the speed
question is T-4's. Putting the engine where vendored code belongs is what makes AC-37 pass, and it
is the faithful reading rather than widening the guard's exclusions to accommodate a file placed
in the wrong directory.

**Only the vendored half moved.** `demo/static/tour/` still holds what this repo wrote:
`steps.js` (the content) and `tour-tokens.css` (the palette and per-skin placement). Those are the
demo's own words and are correctly in scope for every guard.

**D1 pins a named list of six style assets, not the whole directory**, so adding `vendor/tour/`
does not touch it.
