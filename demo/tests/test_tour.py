"""demo/tests/test_tour.py — the guided tour (T-22), guarded where it actually breaks.

The tour is three files with three different owners, and every defect found while
building it lived in the seam between two of them:

    demo/vendor/tour/tour.js, tour.css   the vendored engine  — NOT ours, NOT forked
    demo/static/tour/steps.js            the content          — ours
    demo/static/tour/tour-tokens.css     the palette          — ours

So this file does not test that the tour "works" (only a browser can say that, and one
did — see demo/EVIDENCE.md).  It pins the four seams, each of which produced a real
defect that no assertion I had written could see:

  1. THE ENGINE SHADOWS THREE OF ITS OWN TOKENS.  tour.js `_build()` sets
     `--tour-dim`, `--tour-ring` and `--tour-radius` as INLINE custom properties on
     `.tour-root`, the ancestor of every element that consumes them.  Inline beats any
     stylesheet, and custom properties inherit — so the per-skin values authored at
     `:root` were correct, live, and painted on nothing.  All seven skins ran the
     engine's Nocturne default dim, ring and corner from the first build.  A `:root`
     assertion cannot see this: the declaration it reads IS correct.  Only the
     consumption was ever in question.  `test_the_engine_shadows_tokens_...` below is
     the check that would have caught it, and it is written to stay true if the
     vendored engine is bumped and starts shadowing a fourth name.

  2. AN INVENTED HOOK.  steps.js first called `onShow`, which the engine does not
     define; the tour ran, showed every step, and silently never ran the hook.  A
     missing callback is indistinguishable from a callback that did nothing.

  3. THE ANCHORS ARE IN THE .jsx, WHICH IS DIGEST-COVERED.  Five `data-tour`
     attributes are the tour's only contract with the app.  A redesign that renames
     one leaves a tour whose spotlight lands on nothing, and the engine's retry-resolve
     means it fails by hanging rather than by erroring.

  4. "VENDORED UNMODIFIED" WAS A CLAIM WITH NO CHECK.  PROVENANCE.md said the engine
     was not forked.  Nothing verified it.  It now carries digests, and they are read
     from that file rather than duplicated here, so the document and the check cannot
     drift apart.

The load-order dependency in (1) is itself asserted: the fix works only because
tour-tokens.css is linked after tour.css at equal specificity.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_JS = REPO_ROOT / "demo/vendor/tour/tour.js"
ENGINE_CSS = REPO_ROOT / "demo/vendor/tour/tour.css"
PROVENANCE = REPO_ROOT / "demo/vendor/tour/PROVENANCE.md"
TOKENS = REPO_ROOT / "demo/static/tour/tour-tokens.css"
STEPS = REPO_ROOT / "demo/static/tour/steps.js"
INDEX = REPO_ROOT / "demo/static/index.html"
FRONTEND = REPO_ROOT / "demo/frontend"

# The skill that ships the engine.  Outside the repo, so its absence is a loud skip
# (§9.7's contract), never a silent pass.
SKILL_REFERENCE = Path.home() / ".claude/skills/guided-tour/reference"

# The seven skins demo/static/js/skin.js offers.  `system` is the ABSENCE of a
# data-theme attribute, so it is the bare :root block rather than a selector.
SKINS_WITH_ATTR = ["light", "dark", "gunmetal", "titanium", "classic", "jrpg"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 1. the seam that cost seven skins their palette ────────────────────────────────


def _tokens_the_engine_sets_inline() -> set[str]:
    """Every custom property tour.js writes onto an element with .style.setProperty.

    Read out of the engine rather than hard-coded, so bumping the engine updates the
    fact and the assertions below compare against what is actually there.
    """
    src = ENGINE_JS.read_text(encoding="utf-8")
    return set(re.findall(r'\.style\.setProperty\(\s*"(--[a-z0-9-]+)"', src))


def _declared_in(css: str) -> set[str]:
    """Custom properties DECLARED (not merely referenced) in a stylesheet."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", body))


def test_the_engine_shadows_tokens_and_the_skin_layer_uses_none_of_those_names():
    """The seventh witness of `a check that never ran reads exactly like a check that
    passed` — in its subtlest disguise yet, because the check was not even wrong.

    tour.js:114-116 sets --tour-dim / --tour-ring / --tour-radius inline on .tour-root.
    Anything this repo declares under one of those names is shadowed for the whole
    subtree that reads it.  Measured on the classic skin before the fix:

        :root  --tour-dim rgba(0,0,32,.55)   --tour-ring #000080   --tour-radius 0
        used   dim panel  rgba(6,10,20,0.74)  ring       #4f6ef7   radius       10px

    Nothing looked broken.  The navy dim and square ring were declared; they were
    simply never the values painted.
    """
    shadowed = _tokens_the_engine_sets_inline()
    assert shadowed, (
        "tour.js no longer sets any custom property inline — either the engine was "
        "bumped or this regex stopped matching. Re-read tour.js `_build()` before "
        "trusting this file; the whole point of the check is that it knows what the "
        "engine shadows."
    )
    assert shadowed == {"--tour-dim", "--tour-ring", "--tour-radius"}, (
        f"the vendored engine shadows a different set of tokens than when this was "
        f"written: {sorted(shadowed)}. Any of these declared per-skin in "
        f"tour-tokens.css will be silently overridden on every element inside "
        f".tour-root. Rename the repo-side token (the convention here is a `-skin` "
        f"suffix, or `--tour-corner`) and re-drive the affected element from it."
    )

    declared = _declared_in(TOKENS.read_text(encoding="utf-8"))
    collisions = declared & shadowed
    assert not collisions, (
        f"tour-tokens.css declares {sorted(collisions)}, which the engine sets inline "
        f"on .tour-root. Those declarations are dead for everything inside the tour: "
        f"they will read correct at :root and paint nothing. This is exactly the bug "
        f"that cost all seven skins their dim, ring and corner."
    )


def test_the_engine_elements_are_re_driven_from_names_the_engine_cannot_shadow():
    """Renaming the tokens is only half the fix — the engine still reads its own names,
    so this repo has to paint the three elements itself."""
    css = TOKENS.read_text(encoding="utf-8")
    assert re.search(r"\.tour-dimp\s*\{[^}]*var\(--tour-dim-skin\)", css), (
        "nothing re-drives .tour-dimp from --tour-dim-skin, so every skin's dim is "
        "the engine's default again."
    )
    ring = re.search(r"\.tour-ring\s*\{([^}]*)\}", css)
    assert ring, ".tour-ring is not re-driven at all; the ring colour and corner are the engine's."
    assert "var(--tour-corner)" in ring.group(1), "the ring's border-radius is not on --tour-corner"
    assert "var(--tour-ring-skin)" in ring.group(1), "the ring's colour is not on --tour-ring-skin"


def test_every_skin_that_changes_the_ring_gives_it_a_glow_to_match():
    """The engine's ring is a three-layer shadow: a hard 2px edge and two soft layers
    that need the ring colour at alpha.  A skin that sets the edge and not the glow
    gets a coloured ring inside somebody else's halo.  classic sets it transparent on
    purpose — a glow is not a Win9x object."""
    css = TOKENS.read_text(encoding="utf-8")
    blocks = re.findall(r":root\[data-theme=\"([a-z]+)\"\][^{]*\{([^}]*)\}", css)
    for name, body in blocks:
        if "--tour-ring-skin" in body:
            assert "--tour-ring-glow" in body, (
                f'skin "{name}" sets --tour-ring-skin without --tour-ring-glow, so its '
                f"ring keeps the previous skin's halo."
            )
    # and the base, which every skin without an override inherits
    base = re.search(r"^:root\s*\{([^}]*)\}", css, flags=re.M)
    assert base and "--tour-ring-glow" in base.group(1), (
        "the bare :root block (which IS the `system` skin) declares no --tour-ring-glow, "
        "so the outer ring layers fall back to nothing on the default look."
    )


def test_tour_tokens_is_linked_after_the_engine_stylesheet():
    """The re-drive above wins on load order alone — both selectors are a single class.
    Swap the two <link>s and the whole palette silently reverts."""
    html = INDEX.read_text(encoding="utf-8")
    engine = html.find("/vendor/tour/tour.css")
    ours = html.find("/static/tour/tour-tokens.css")
    assert engine != -1 and ours != -1, "one of the tour stylesheets is not linked at all"
    assert engine < ours, (
        "tour-tokens.css is linked BEFORE the vendored tour.css. Every rule this repo "
        "writes for .tour-bubble, .tour-ring, .tour-dimp, .tour-btn and .tour-peek has "
        "the same specificity as the engine's, so the engine now wins all of them and "
        "the tour reverts to the Nocturne dark palette on a white app."
    )


# ── 2. the invented hook ───────────────────────────────────────────────────────────


def test_steps_js_calls_only_hooks_the_engine_actually_defines():
    """steps.js first wrapped `onShow`. The engine has `beforeShow` / `afterShow`.
    Nothing errored: the tour ran, every step displayed, and the hook that drives the
    app to the EdgeCase pick simply never fired. A hook that is never called is
    indistinguishable from a hook that did nothing."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    steps = STEPS.read_text(encoding="utf-8")
    # the per-step keys the engine reads off a step object
    engine_step_keys = set(re.findall(r"step\.([a-zA-Z]+)", engine))
    assert {"beforeShow", "afterShow", "advanceOn", "target"} <= engine_step_keys, (
        f"the engine's step vocabulary changed: {sorted(engine_step_keys)}"
    )

    # steps.js writes at two levels — the Tour.start({...}) config and each step
    # object — at the same indent, so both vocabularies count as "defined".
    engine_cfg_keys = (
        set(re.findall(r"cfg\.([a-zA-Z]+)", engine))          # copied onto this.cfg
        | set(re.findall(r"config\.([a-zA-Z]+)", engine))     # read straight off the argument
        | set(re.findall(r"^\s{4}([a-zA-Z]+):", engine, flags=re.M))  # the DEFAULTS block
    )
    ours_only = {"gnome"}  # handled by steps.js's own wrapper, documented there
    used = set(re.findall(r"^\s{6}([a-zA-Z]+):", steps, flags=re.M))
    invented = used - engine_step_keys - engine_cfg_keys - ours_only
    assert not invented, (
        f"steps.js sets step keys the engine never reads: {sorted(invented)}. The tour "
        f"will run and look correct; whatever those keys were meant to do will not "
        f"happen, silently. (If a key is deliberately steps.js's own, add it to "
        f"`ours_only` here AND handle it in the wrapper — that is the whole contract.)"
    )


# ── 3. the anchors, which live in digest-covered .jsx ──────────────────────────────


def test_every_data_tour_anchor_the_steps_target_exists_in_the_frontend():
    """The tour's only contract with the app is five attributes. The engine retries an
    unresolved target rather than throwing, so a renamed anchor fails as a tour that
    hangs on a step — not as an error anyone would see in a log."""
    steps = STEPS.read_text(encoding="utf-8")
    wanted = set(re.findall(r'\[data-tour="([a-z]+)"\]', steps))
    assert wanted, "steps.js targets no data-tour anchors at all"

    present: set[str] = set()
    for jsx in sorted(FRONTEND.glob("*.jsx")):
        present |= set(re.findall(r'data-tour="([a-z]+)"', jsx.read_text(encoding="utf-8")))

    missing = wanted - present
    assert not missing, (
        f"steps.js spotlights {sorted(missing)}, which no .jsx carries. The tour will "
        f"stall on that step. Note the anchors are inside digest-covered sources: "
        f"restoring one needs ./run-demo build-ui, and the digest guard should go red "
        f"before it is re-baselined."
    )


# ── 4. "vendored unmodified", made checkable ───────────────────────────────────────


def _recorded_digests() -> dict[str, str]:
    """Read the digest table out of PROVENANCE.md, so the prose and the check are the
    same fact rather than two copies of it."""
    text = PROVENANCE.read_text(encoding="utf-8")
    return {
        name: digest
        for name, digest in re.findall(r"\|\s*`([a-z0-9.\-]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|", text)
    }


def test_the_vendored_engine_still_matches_the_digests_provenance_records():
    recorded = _recorded_digests()
    assert recorded, (
        f"{PROVENANCE} records no sha256 table. The claim that the engine is 'vendored "
        f"unmodified' is then a claim with no check behind it, which is the defect "
        f"class this repo keeps finding."
    )
    for name, digest in sorted(recorded.items()):
        path = PROVENANCE.parent / name
        assert path.exists(), f"PROVENANCE.md pins {name}, which is not in {PROVENANCE.parent}"
        actual = _sha256(path)
        assert actual == digest, (
            f"demo/vendor/tour/{name} no longer matches the sha256 PROVENANCE.md "
            f"records ({digest[:16]}…, got {actual[:16]}…). The engine is vendored "
            f"UNMODIFIED on purpose: the steps are the product and the engine is not "
            f"forked. If a change to it is genuinely wanted, it belongs in "
            f"tour-tokens.css or steps.js — and if it truly cannot, update the table "
            f"AND say in PROVENANCE.md what was changed and why."
        )


def test_the_vendored_engine_matches_the_skill_that_ships_it():
    """The stronger half: not just unchanged since we copied it, but the same bytes as
    upstream. The skill lives outside the repo, so this SKIPS LOUDLY when it is not
    here — it never passes by default."""
    if not SKILL_REFERENCE.is_dir():
        pytest.skip(
            f"the guided-tour skill's engine is not on this machine — looked for "
            f"{SKILL_REFERENCE}. The digest half of this pair "
            f"(test_the_vendored_engine_still_matches_the_digests_provenance_records) "
            f"still ran and still had to pass; what is NOT verified here is that those "
            f"digests match upstream."
        )
    for vendored in (ENGINE_JS, ENGINE_CSS):
        upstream = SKILL_REFERENCE / vendored.name
        assert upstream.exists(), f"the skill has no {vendored.name} to compare against"
        assert _sha256(vendored) == _sha256(upstream), (
            f"demo/vendor/tour/{vendored.name} differs from the skill's shipped copy at "
            f"{upstream}. Either the engine was forked here (it must not be) or the "
            f"skill was updated — in which case re-vendor deliberately and re-record "
            f"the digest in PROVENANCE.md."
        )
