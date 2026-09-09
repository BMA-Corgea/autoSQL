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
    # [a-z0-9-]+ and not [a-z]+ — a future `hi-contrast` or `solarized-dark` skin would
    # otherwise drop out of the loop silently, which is the failure mode, not a typo.
    blocks = re.findall(r":root\[data-theme=\"([a-z0-9-]+)\"\][^{]*\{([^}]*)\}", css)
    for name, body in blocks:
        if "--tour-ring-skin" in body:
            assert "--tour-ring-glow" in body, (
                f'skin "{name}" sets --tour-ring-skin without --tour-ring-glow, so its '
                f"ring keeps the previous skin's halo."
            )
    # And the base, which every skin without an override inherits. Find it by the token it
    # must carry, NOT by "the first :root block" — this file legitimately has more than one
    # bare :root (the peek height lives in its own), and a positional match would silently
    # start asserting against the wrong block the moment their order changed. That is the
    # same class of mistake this whole file exists to guard.
    bases = [
        body
        for body in re.findall(r"(?<![\]\w]):root\s*\{([^}]*)\}", css)
        if "--tour-ring-skin" in body
    ]
    assert len(bases) == 1, (
        f"expected exactly one bare :root block to define the base ring, found {len(bases)}"
    )
    assert "--tour-ring-glow" in bases[0], (
        "the bare :root block (which IS the `system` skin) declares no --tour-ring-glow, "
        "so the outer ring layers fall back to nothing on the default look."
    )


def _token_block(css: str, selector_re: str) -> dict[str, str]:
    """The custom properties declared by the first block whose selector matches."""
    m = re.search(selector_re + r"\s*\{([^}]*)\}", css)
    if not m:
        return {}
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1)))


def _resolved_tokens(css: str, skin: str | None) -> dict[str, str]:
    """What a skin ACTUALLY gets: the base :root, then its own block on top.

    Deliberately does NOT fold in the prefers-color-scheme block — after the fix that block
    is guarded `:root:not([data-theme])`, so it reaches only the `system` skin, and the whole
    point of `test_the_os_dark_block_reaches_only_the_system_skin` is to keep it that way.
    """
    base = _token_block(css, r"(?<![\]\w]):root")
    if skin is None:
        return base
    out = dict(base)
    out.update(_token_block(css, r':root\[data-theme="' + skin + r'"\]'))
    return out


def _luminance(color: str) -> float:
    """Relative luminance (WCAG) of a #rrggbb or rgba(...) token value."""
    color = color.strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", color)
    if m:
        rgb = [int(m.group(1)[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    else:
        m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", color)
        assert m, f"cannot read a colour out of {color!r}"
        rgb = [int(m.group(i)) / 255 for i in (1, 2, 3)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_the_os_dark_block_reaches_only_the_system_skin():
    """`system` is the absence of a data-theme attribute — the OS decides for THAT skin and
    no other. An earlier draft guarded the block `:not([data-theme="light"])`, which excludes
    only light, so the OS-dark values still landed on every other explicit skin for every
    token that skin did not itself declare: titanium ("built for daylight") rendered a dark
    bubble on a cream page whenever the visitor's OS was dark.

    demo/static/skins/base.css had already settled this and says why in its own comment. This
    test exists so that pattern cannot be quietly re-derived a third time.
    """
    css = TOKENS.read_text(encoding="utf-8")
    blocks = re.findall(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*([^{]*)\{", css)
    assert blocks, "no prefers-color-scheme block at all — the `system` skin has no dark mode"
    for selector in blocks:
        assert selector.strip() == ":root:not([data-theme])", (
            f"the OS-dark block is guarded `{selector.strip()}`. It must be "
            f"`:root:not([data-theme])`, or its values leak into every explicit skin that "
            f"does not itself redeclare them — which is invisible until someone changes "
            f"their operating system. demo/static/skins/base.css uses the correct form and "
            f"explains it."
        )


def test_every_skin_resolves_to_a_readable_bubble():
    """The washed-out-text defect, made impossible to reintroduce on any skin.

    The engine paints .tour-bubble a dark gradient and picks text colours to sit on it. An
    earlier version of this file overrode only the BACKGROUND, leaving pale blue-grey text on
    a white bubble: legible in the DOM, correct to every selector I had asserted, and washed
    out on screen. It took a screenshot to see.

    A partial per-skin override reintroduces exactly that, so the check is on the RESOLVED
    pair — base plus the skin's own block, which is what a visitor on that skin actually
    gets — and the bar is WCAG AA for body text.
    """
    css = TOKENS.read_text(encoding="utf-8")
    for skin in [None] + SKINS_WITH_ATTR:
        tokens = _resolved_tokens(css, skin)
        name = skin or "system"
        for key in ("--tour-bubble-bg", "--tour-bubble-fg", "--tour-muted", "--tour-accent",
                    "--tour-btn-fg", "--tour-bubble-bd", "--tour-ring-skin"):
            assert key in tokens, (
                f"skin `{name}` resolves no {key}. Every skin gets the base :root plus its "
                f"own block and nothing else — a token missing from both is a token the "
                f"engine falls back to its own default for."
            )
        ratio = _contrast(tokens["--tour-bubble-fg"], tokens["--tour-bubble-bg"])
        assert ratio >= 4.5, (
            f"skin `{name}`: bubble text {tokens['--tour-bubble-fg'].strip()} on bubble "
            f"{tokens['--tour-bubble-bg'].strip()} is {ratio:.2f}:1, below WCAG AA (4.5:1). "
            f"This is the washed-out-bubble defect returning on one skin."
        )
        btn = _contrast(tokens["--tour-btn-fg"], tokens["--tour-accent"])
        assert btn >= 4.5, (
            f"skin `{name}`: the primary button's {tokens['--tour-btn-fg'].strip()} on "
            f"{tokens['--tour-accent'].strip()} is {btn:.2f}:1, below WCAG AA. Next is the "
            f"control the whole tour depends on."
        )


def test_every_skin_the_picker_offers_has_a_tour_block():
    """SKINS_WITH_ATTR was defined here, carefully commented, and referenced by nothing — so
    deleting the entire :root[data-theme="jrpg"] block left the gold-on-teal skin with a white
    bubble, a blue ring and a grey dim, and every test in this file still passed.

    The list is not a constant either: it is read out of demo/static/js/skin.js, which is the
    file that decides what the picker offers. Add an eighth skin there and this goes red until
    the tour has an answer for it.
    """
    skin_js = (REPO_ROOT / "demo/static/js/skin.js").read_text(encoding="utf-8")
    offered = re.findall(r'\{\s*name:\s*"([a-z0-9-]+)"', skin_js)
    assert len(offered) >= 7, f"skin.js offers {offered}, which is fewer than the seven skins"
    assert set(SKINS_WITH_ATTR) | {"system"} == set(offered), (
        f"skin.js offers {sorted(offered)}, this file knows about "
        f"{sorted(set(SKINS_WITH_ATTR) | {'system'})}. A skin the picker offers and the tour "
        f"has never been checked against is a skin the tour may look broken on."
    )
    css = TOKENS.read_text(encoding="utf-8")
    for skin in SKINS_WITH_ATTR:
        assert _token_block(css, r':root\[data-theme="' + skin + r'"\]'), (
            f'tour-tokens.css has no :root[data-theme="{skin}"] block, so that skin silently '
            f"takes the base light palette. On a dark-page skin that is a white bubble on a "
            f"near-black screen."
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


def _strip_comments(src: str) -> str:
    """Block and line comments out of JS. The step region is heavily commented, and prose
    like `max-width:1520px` or `the answer branch:` reads as a key to any regex."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _bracket_region(src: str, opener: str) -> str:
    """The text from `opener` to its matching `]` — used instead of an indentation-anchored
    regex, which is the whole point of the guard below."""
    i = src.index(opener)
    j = i + len(opener) - 1
    depth = 0
    while True:
        if src[j] == "[":
            depth += 1
        elif src[j] == "]":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
        j += 1


def test_steps_js_calls_only_hooks_the_engine_actually_defines():
    """steps.js first wrapped `onShow`. The engine has `beforeShow` / `afterShow`. Nothing
    errored: the tour ran, every step displayed, and the hook that drives the app to the
    EdgeCase pick simply never fired. A hook that is never called is indistinguishable from a
    hook that did nothing.

    THE FIRST VERSION OF THIS TEST COULD MATCH NOTHING AND PASS. It anchored on exactly six
    leading spaces, so re-indenting steps.js by one level — dropping the IIFE for a module, a
    formatter with a different indent width, `var STEPS = [{` on one line — emptied the
    matched set and the assertion became vacuous. Verified by running it against a de-indented
    copy: `used` went from eleven keys to zero, and the test reported green while checking
    nothing. That is precisely the class the file exists to guard, wearing this file's own
    clothes.

    It now walks the STEPS array by bracket matching, which has no opinion about whitespace,
    and asserts what it found is not empty before drawing any conclusion from it.
    """
    engine = ENGINE_JS.read_text(encoding="utf-8")
    steps = STEPS.read_text(encoding="utf-8")

    engine_step_keys = set(re.findall(r"step\.([a-zA-Z]+)", engine))
    assert {"beforeShow", "afterShow", "advanceOn", "target"} <= engine_step_keys, (
        f"the engine's step vocabulary changed: {sorted(engine_step_keys)}"
    )

    region = _strip_comments(_bracket_region(steps, "var STEPS = ["))
    used = set(re.findall(r"(?:^\s*|[{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", region, flags=re.M))
    assert len(used) >= 5, (
        f"only {sorted(used)} was found inside `var STEPS = [ … ]`. A step object has at "
        f"least `target` and `text`; finding almost nothing means this scan stopped working, "
        f"not that the steps stopped using keys. Fix the scan before trusting a green here."
    )
    assert {"target", "text"} <= used, (
        f"the STEPS scan found {sorted(used)} but not the two keys every step must have — "
        f"it is looking at the wrong region."
    )

    ours_only = {"gnome"}  # handled by steps.js's own wrapper, documented there
    invented = used - engine_step_keys - ours_only
    assert not invented, (
        f"steps.js sets step keys the engine never reads: {sorted(invented)}. The tour will "
        f"run and look correct; whatever those keys were meant to do will not happen, "
        f"silently. (If a key is deliberately steps.js's own, add it to `ours_only` here AND "
        f"handle it in the wrapper — that is the whole contract.)"
    )


def test_the_config_steps_js_passes_uses_only_options_the_engine_reads():
    """The same rule one level up, and the one that caught `narrator.name`.

    `narrator: { image, name }` is what the engine's usage comment documents, so I passed
    `name: "GIMS"` and then recorded in demo/EVIDENCE.md that a browser run had CONFIRMED a
    bubble "bylined GIMS". It had not: tour.js reads `narrator.image` and reads `name`
    nowhere, there was no byline element in the DOM at all, and the string was inert config.
    A key a library accepts and ignores looks exactly like a key that worked. The byline is
    now built by steps.js itself (`ensureByline`), which is why `name` is listed as ours.
    """
    engine = ENGINE_JS.read_text(encoding="utf-8")
    steps = STEPS.read_text(encoding="utf-8")
    engine_cfg_keys = (
        set(re.findall(r"cfg\.([a-zA-Z]+)", engine))
        | set(re.findall(r"config\.([a-zA-Z]+)", engine))
        | set(re.findall(r"cfg\.[a-zA-Z]+\.([a-zA-Z]+)", engine))  # e.g. cfg.narrator.image
        | set(re.findall(r"^\s{4}([a-zA-Z]+):", engine, flags=re.M))  # the DEFAULTS block
    )
    body = steps[steps.index("function config("):]
    body = body[: body.index("\n  }")]
    # A key is a name in property position: it opens a line or follows `{` or `,`. Matching
    # bare `word:` would also swallow the `:` of a ternary (`force ? null : KEY`).
    used = set(re.findall(r"(?:^\s*|[{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", body, flags=re.M))
    assert {"steps", "storageKey"} <= used, (
        f"the config scan found {sorted(used)} — it is not looking at Tour.start's argument"
    )
    # keys this repo consumes itself rather than handing to the engine
    ours = {"name"}  # rendered by ensureByline(); the engine never reads narrator.name
    invented = used - engine_cfg_keys - ours
    assert not invented, (
        f"steps.js passes config keys the engine never reads: {sorted(invented)}. They will "
        f"be accepted and ignored, and will look exactly like they worked. Either drop them "
        f"or consume them in this repo's own code and list them in `ours` here."
    )


def test_the_tour_root_carries_the_z_index_that_makes_next_clickable():
    """The highest-value line in the whole change had no assertion on it.

    `.tour-root` is `position: fixed`, and position:fixed CREATES A STACKING CONTEXT
    REGARDLESS OF Z-INDEX. So the bubble's own `z-index: 9003` was confined inside that
    context, which competed against #skin-picker's 60 at an effective 0 — and WebDriver said
    so in as many words: "element click intercepted: <button class=tour-btn tour-primary> is
    not clickable at point (1442,821) because another element <div id=skin-picker> obscures
    it". A visitor pressing Next where the bubble lands bottom-right would have hit the skin
    switcher instead.

    Delete the z-index on `.tour-root` and the tour's primary button is intercepted on every
    skin, with a green suite. It cost a browser run to find and nothing was watching it.
    """
    css = TOKENS.read_text(encoding="utf-8")
    m = re.search(r"\.tour-root\s*\{([^}]*)\}", css)
    assert m, (
        ".tour-root has no rule in tour-tokens.css. It needs an explicit z-index: the element "
        "is position:fixed, so it opens a stacking context and its children's z-indexes are "
        "trapped inside it — they cannot out-rank #skin-picker on their own."
    )
    z = re.search(r"z-index\s*:\s*(\d+)", m.group(1))
    assert z, "the .tour-root rule sets no z-index — see this test's docstring"
    assert int(z.group(1)) > 60, (
        f".tour-root's z-index is {z.group(1)}. #skin-picker sits at 60 "
        f"(demo/static/skins/base.css), and the tour's whole stacking context has to clear "
        f"it or Next is unclickable where the bubble lands bottom-right."
    )


# ── 3. the anchors, which live in digest-covered .jsx ──────────────────────────────


def test_every_data_tour_anchor_the_steps_target_exists_in_the_frontend():
    """The tour's only contract with the app is five attributes. The engine retries an
    unresolved target rather than throwing, so a renamed anchor fails as a tour that
    hangs on a step — not as an error anyone would see in a log."""
    steps = STEPS.read_text(encoding="utf-8")
    wanted = set(re.findall(r'\[data-tour="([a-z0-9-]+)"\]', steps))
    assert wanted, "steps.js targets no data-tour anchors at all"

    present: set[str] = set()
    for jsx in sorted(FRONTEND.glob("*.jsx")):
        present |= set(re.findall(r'data-tour="([a-z0-9-]+)"', jsx.read_text(encoding="utf-8")))

    missing = wanted - present
    assert not missing, (
        f"steps.js spotlights {sorted(missing)}, which no .jsx carries. The tour will "
        f"stall on that step. Note the anchors are inside digest-covered sources: "
        f"restoring one needs ./run-demo build-ui, and the digest guard should go red "
        f"before it is re-baselined."
    )


def _opening_tags(jsx: str) -> list[str]:
    """Every JSX opening tag in a file, as flat text (attributes may span lines)."""
    return [m.group(0) for m in re.finditer(r"<[A-Za-z][^<>]*?>", jsx, flags=re.S)]


def _identity_of(tag: str) -> str | None:
    """What makes one rendered element 'the same control' as another across branches.

    `aria-label` first — it is the accessible name, it is stable, and in this codebase two
    render paths of the same component carry the identical one. `className` is the fallback
    for the elements that have no label.
    """
    m = re.search(r'aria-label="([^"]+)"', tag)
    if m:
        return "aria-label=" + m.group(1)
    m = re.search(r'className="([^"{]+)"', tag)
    if m:
        return "className=" + m.group(1)
    return None


def test_every_render_path_of_an_anchored_control_carries_its_anchor():
    """THE EIGHTH WITNESS, and the guard that would have caught it.

    `test_every_data_tour_anchor_the_steps_target_exists_in_the_frontend` above searches each
    file for the attribute and unions what it finds. That is a check on whether the FILE
    CONTAINS THE STRING — not on whether every render path emits it. `demo/frontend/panes.jsx`
    has two returns: the answer branch and the `if (!answer)` empty state, both
    `<section aria-label="The same pick, two answers">`. Only the answer branch carried
    `data-tour="panes"`. The file-level search reported the anchor present, and it was — on
    one of two paths.

    What that cost, concretely: the tour starts as soon as `[data-tour="screen"]` exists,
    which is the first paint, before the initial `POST /api/pick` resolves — and permanently
    if that request fails, because the app then renders its error banner and never sets
    `answer`. Steps 4 and 6 both target `[data-tour="panes"]`; the engine's `resolve()` polls,
    gives up, returns null, and `_reposition` blacks the whole screen with no ring. The
    visitor reads "They agree, and that is the normal case" over a fully dimmed page, and then
    the tour's climax the same way. Every one of this file's other tests stayed green.

    So: an element carrying an anchor establishes an IDENTITY (its aria-label, else its
    className). Every opening tag in the same file with that identity must carry the same
    anchor. Multi-branch components are the normal shape in this codebase, and this is the
    invariant that makes an anchor mean "this control", not "somewhere in this file".
    """
    offenders: list[str] = []
    checked = 0
    for jsx in sorted(FRONTEND.glob("*.jsx")):
        text = jsx.read_text(encoding="utf-8")
        tags = _opening_tags(text)
        anchored = {}  # identity -> anchor name
        for tag in tags:
            m = re.search(r'data-tour="([a-z0-9-]+)"', tag)
            if not m:
                continue
            ident = _identity_of(tag)
            assert ident, (
                f"{jsx.name}: an element carries data-tour=\"{m.group(1)}\" but has neither "
                f"an aria-label nor a plain className, so no other render path of it can be "
                f"identified. Give it one, or this guard cannot see a second branch:\n  {tag}"
            )
            anchored[ident] = m.group(1)
        for ident, name in anchored.items():
            checked += 1
            for tag in tags:
                if _identity_of(tag) == ident and f'data-tour="{name}"' not in tag:
                    offenders.append(
                        f'{jsx.name}: <{tag.split()[0].lstrip("<")} {ident}> is a render path '
                        f'of the control anchored as data-tour="{name}", and does NOT carry '
                        f"the anchor. The tour will spotlight nothing on whichever branch "
                        f"renders. Tag:\n      {tag.strip()[:160]}"
                    )
    assert checked >= 5, (
        f"expected at least the five known anchors to be identifiable, matched {checked} — "
        f"the JSX shape changed and this guard is now looking at less than it thinks"
    )
    assert not offenders, "\n".join(offenders)


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
    # The table must cover EVERYTHING vendored, not merely be non-empty: dropping the
    # tour.js row would leave the engine forkable with a green suite, which is the same
    # "a claim with no check" shape this test exists to close.
    on_disk = {
        p.name for p in PROVENANCE.parent.iterdir()
        if p.is_file() and p.name != PROVENANCE.name
    }
    unpinned = sorted(on_disk - set(recorded))
    assert not unpinned, (
        f"demo/vendor/tour/ holds {unpinned}, which PROVENANCE.md's digest table does not "
        f"pin. Vendored files are pinned or they are not vendored — an unpinned one can be "
        f"edited, and 'vendored unmodified' goes back to being a claim with no check."
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
