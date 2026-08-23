"""demo/tests/test_walkthrough_doc.py — W15: WALKTHROUGH.md's numbers, checked.

Plan §6.2's row for W15: *"Every number in the document equals the
corresponding entry in `expected-answers.json` (a test, not a read)."* This
file is that test.

HOW THE CHECK WORKS
--------------------
`demo/WALKTHROUGH.md` writes every number it takes from
`demo/expected-answers.json` in one fixed shape: the number itself in inline
code, immediately followed — no space — by an HTML comment naming the exact
JSON path it came from, e.g.::

    `8,400`<!--#steps[1].expect.row_count-->

The comment is invisible wherever the file is rendered as Markdown (this
file is read as *text* here, never rendered) and exists for exactly one
reason: so a test can resolve it. This file does three things with that:

1. **Soundness.** For every `` `value` ``<!--#path--> found in the walkthrough,
   resolve `path` against the real JSON and assert the two are equal —
   commas in the document are cosmetic and stripped before comparing, but
   nothing else is: a decimal string like ``"27.000000"`` must match to the
   digit, and ``"1e+300"`` must match to the character.
2. **Completeness.** Every *numeric* leaf value that actually lives under
   `expected-answers.json`'s `corpus` and `steps` sections is computed
   independently (by walking the JSON itself, not by hand-copying a list —
   the required set can never silently drift from the file it is checking
   against) and asserted to appear, annotated, somewhere in the document.
   A number quietly left out of the walkthrough is exactly as much a defect
   as a number written wrong, and this is the half of the check that a
   simple "does this string appear somewhere" grep would miss.
3. **A negative control.** The detector is exercised on a small planted
   walkthrough with a deliberately wrong number, to prove it would actually
   fail a document that needed to fail (plan §8.2's rule: a check nobody has
   watched catch something is a check nobody knows works).

"A number" here means anything the JSON itself represents as numeric: a
Python `int`, or a `str` that parses cleanly as a float (`"400207"`,
`"27.000000"`, `"1e+300"`) — which is how this project's own
`expected-answers.json` represents every exact-decimal value (B7's
`Decimal(str)` route). A non-finite spelling such as `"inf"` would count
here too, by the same rule; the file does not currently hold one. (It held
one until 2026-08-22, at `steps[12].expect.python_pane` — corrected to
`"raised"` when the `inf` turned out never to be produced; see the note
beside AC-17 in `.autodev/specs/T-2.md`.) Plain strings such as key names
(`"hb-01-0000"`) or timestamps (`"2026-08-20T23:00:00Z"`) are not "numbers"
in this sense and are not required to be annotated, even though the
walkthrough does state most of them for the reader's benefit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_WALKTHROUGH = _REPO_ROOT / "demo" / "WALKTHROUGH.md"
_ANSWERS_JSON = _REPO_ROOT / "demo" / "expected-answers.json"

# Top-level sections a required number may live under. `$comment` and
# `independence` are provenance metadata about the file itself, not
# entries a walkthrough step demonstrates, and are deliberately excluded —
# a stray digit inside a sentence of provenance text is not "a number in
# the document" in the sense plan §6.2 means.
_REQUIRED_SECTIONS = ("corpus", "steps")

# Keys that are step *metadata*, not an answer the walkthrough demonstrates
# — skipped everywhere they occur so a `"step": 7` or a title string never
# becomes a phantom requirement (and, for `derivation`, so prose inside a
# JSON derivation string is never walked as if it were structured data).
_METADATA_KEYS = {"derivation", "title", "step"}


# ---------------------------------------------------------------------------
# Walking expected-answers.json into a flat {path: value} map
# ---------------------------------------------------------------------------

def _is_leaf_wrapper(node: object) -> bool:
    """True for the ``{"value": ..., "derivation": "..."}`` shape B8 uses
    for every entry — the wrapper is metadata; the path continues into
    ``value`` without advancing, which is what lets ``steps[6].expect.sum``
    name a leaf directly instead of ``steps[6].expect.sum.value``."""
    return (
        isinstance(node, dict)
        and "value" in node
        and isinstance(node.get("derivation"), str)
    )


def _flatten(node: object, path: str = ""):
    """Yield ``(path, value)`` for every leaf reachable from ``node``.

    A "leaf" is anything that is not itself a dict or a list once wrapper
    dicts have been unwrapped: an int, a float, a str, a bool, or None.
    """
    if _is_leaf_wrapper(node):
        yield from _flatten(node["value"], path)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in _METADATA_KEYS:
                continue
            yield from _flatten(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _flatten(value, f"{path}[{index}]")
    else:
        yield (path, node)


def _is_numeric(value: object) -> bool:
    """Matches this project's own notion of "a number" — see the module
    docstring. ``bool`` is excluded even though Python's ``bool`` is an
    ``int`` subclass: ``true``/``false`` are not numbers a reader checks."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def _required_numbers(answers: dict) -> dict:
    """Every numeric leaf under `corpus` and `steps`, keyed by its exact
    dotted/bracketed path — the walkthrough's complete "must appear,
    annotated, somewhere" list, computed fresh from the JSON every run."""
    required = {}
    for section in _REQUIRED_SECTIONS:
        for path, value in _flatten(answers[section], section):
            if _is_numeric(value):
                required[path] = value
    return required


# ---------------------------------------------------------------------------
# Resolving a path string against the same JSON, the same way _flatten does
# ---------------------------------------------------------------------------

_PATH_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$")


def _resolve(answers: dict, path: str):
    """The value ``_flatten`` would have yielded at ``path`` — walking the
    JSON the same way, unwrapping the same B8 leaf-wrapper shape at every
    step, so a path taken from the walkthrough always means what
    ``_required_numbers`` above means by the same string."""
    def unwrap(node):
        while _is_leaf_wrapper(node):
            node = node["value"]
        return node

    node = unwrap(answers)
    for segment in path.split("."):
        m = _PATH_SEGMENT.match(segment)
        if not m:
            raise ValueError(f"unparseable path segment {segment!r} in {path!r}")
        key, indices = m.group(1), m.group(2)
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"{key!r} not found resolving {path!r}")
        node = unwrap(node[key])
        for idx in re.findall(r"\[(\d+)\]", indices):
            i = int(idx)
            if not isinstance(node, list) or i >= len(node):
                raise IndexError(f"index {i} out of range resolving {path!r}")
            node = unwrap(node[i])
    return node


# ---------------------------------------------------------------------------
# Parsing the walkthrough document itself
# ---------------------------------------------------------------------------

#: `` `value` `` immediately followed (no gap) by `<!--#path-->`. Deliberately
#: strict about adjacency: an annotation that could drift onto the wrong
#: number by way of stray whitespace would defeat the entire point of it.
_ANNOTATION = re.compile(r"`([^`\n]+)`<!--#([^\s>]+)-->")


def _annotations(text: str):
    """(path, doc_token, line number) for every annotation in ``text``."""
    out = []
    for m in _ANNOTATION.finditer(text):
        token, path = m.group(1), m.group(2)
        line = text.count("\n", 0, m.start()) + 1
        out.append((path, token, line))
    return out


def _tokens_equal(doc_token: str, expected: object) -> bool:
    """Compare the way §7.2/B7 require: commas are formatting and are
    stripped; nothing else is. No float() coercion — a decimal string's
    trailing zeros and an exponent's exact spelling are the entire point
    of B7's exact-decimal rule, and float() would erase both."""
    normalised = doc_token.replace(",", "")
    if isinstance(expected, bool):
        return False  # not reached by _required_numbers, kept for safety
    if isinstance(expected, int):
        try:
            return int(normalised) == expected
        except ValueError:
            return False
    # int or numeric str: expected is a numeric string (B7's Decimal(str)
    # route) — exact text match after de-comma-ing, e.g. "27.000000" or
    # "1e+300". A non-finite spelling would compare the same way.
    return normalised == str(expected)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def answers() -> dict:
    assert _ANSWERS_JSON.exists(), f"missing {_ANSWERS_JSON}"
    return json.loads(_ANSWERS_JSON.read_text())


@pytest.fixture(scope="module")
def walkthrough_text() -> str:
    assert _WALKTHROUGH.exists(), (
        f"missing {_WALKTHROUGH} — W15 has not written it yet"
    )
    return _WALKTHROUGH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

def test_the_document_exists_and_has_fourteen_steps():
    assert _WALKTHROUGH.exists()
    text = _WALKTHROUGH.read_text(encoding="utf-8")
    headings = re.findall(r"^## Step (\d+)\b", text, re.MULTILINE)
    assert [int(n) for n in headings] == list(range(1, 15)), (
        f"expected steps 1..14 in order, found headings {headings!r}"
    )


def test_every_annotated_number_matches_expected_answers(answers, walkthrough_text):
    """Soundness: every `` `value` ``<!--#path--> in the document really is
    what expected-answers.json says at that path."""
    found = _annotations(walkthrough_text)
    assert found, "no annotated numbers found at all — the annotation shape may have drifted"

    mismatches = []
    broken_paths = []
    for path, token, line in found:
        try:
            expected = _resolve(answers, path)
        except (KeyError, IndexError, ValueError) as exc:
            broken_paths.append(f"line {line}: {path!r} does not resolve — {exc}")
            continue
        if not _tokens_equal(token, expected):
            mismatches.append(
                f"line {line}: {path} — document says {token!r}, "
                f"expected-answers.json says {expected!r}"
            )

    assert not broken_paths, (
        "WALKTHROUGH.md annotates a path that does not exist in "
        "expected-answers.json:\n  " + "\n  ".join(broken_paths)
    )
    assert not mismatches, (
        "WALKTHROUGH.md states a number that does not match "
        "expected-answers.json:\n  " + "\n  ".join(mismatches)
    )


def test_every_required_number_is_annotated_somewhere(answers, walkthrough_text):
    """Completeness: every numeric leaf under `corpus`/`steps` in
    expected-answers.json is cited, annotated, at least once. Computed
    fresh from the JSON (never a hand-copied list), so this can never
    silently fall behind a reseed or a new field in expectations.py."""
    required = _required_numbers(answers)
    assert required, "computed zero required numbers — the walker is broken, not the data"

    present = {path for path, _token, _line in _annotations(walkthrough_text)}
    missing = sorted(set(required) - present)
    assert not missing, (
        "WALKTHROUGH.md is missing these numbers from expected-answers.json "
        "(plan §6.2, W15: every number, not a subset of them):\n"
        + "\n".join(f"  {p} = {required[p]!r}" for p in missing)
    )


def test_the_required_set_has_the_shape_this_walkthrough_was_written_against():
    """A pin, not a duplicate of the two tests above: if this count moves,
    something changed under `corpus`/`steps` that the prose may not have
    caught up with yet, even where every individual number still resolves
    (e.g. a field renamed to something that happens to parse as numeric
    under the old name too). A moved count is a prompt to re-read the
    walkthrough by eye once, not a failure on its own — so this asserts a
    generous range rather than the exact number, and the real coverage
    guarantee is the completeness test above."""
    answers = json.loads(_ANSWERS_JSON.read_text())
    required = _required_numbers(answers)
    assert 55 <= len(required) <= 75, (
        f"expected roughly 55-75 required numbers under corpus/steps, "
        f"found {len(required)} — expected-answers.json's shape has "
        f"changed enough to warrant re-reading WALKTHROUGH.md by eye"
    )


def test_the_checker_would_actually_catch_a_wrong_number(answers):
    """The detector, watched catching something (plan §8.2). A tiny planted
    document, one number deliberately wrong, must fail — proving the two
    tests above are not vacuously passing because nothing is ever compared.
    """
    real_value = _resolve(answers, "steps[1].expect.row_count")
    assert real_value == 8400  # sanity: this test's own premise

    wrong_doc = "`8,401`<!--#steps[1].expect.row_count-->\n"
    (path, token, _line), = _annotations(wrong_doc)
    assert not _tokens_equal(token, _resolve(answers, path)), (
        "the checker did not notice a deliberately wrong number — it is not "
        "actually checking anything"
    )

    right_doc = "`8,400`<!--#steps[1].expect.row_count-->\n"
    (path, token, _line), = _annotations(right_doc)
    assert _tokens_equal(token, _resolve(answers, path))

    # And a document missing a required number entirely must be caught by
    # the completeness side, not just silently accepted as "nothing wrong".
    incomplete_doc = "no numbers here at all\n"
    present = {p for p, _t, _l in _annotations(incomplete_doc)}
    required = _required_numbers(answers)
    assert set(required) - present, (
        "the completeness detector did not notice a document with zero "
        "annotations missing every required number"
    )


def test_decimal_precision_is_checked_to_the_digit_not_by_value(answers):
    """B7's exact-decimal rule has teeth here specifically: `27.00000` (5
    places) and `27.000000` (6, what the JSON actually holds) are numerically
    identical and must NOT be treated as a match — this project's failure
    mode is "a subtly wrong number that still runs clean", and a rounding-
    tolerant comparison here would be exactly that hole."""
    exact = _resolve(answers, "steps[7].expect.worked_values[0].value")
    assert exact == "27.000000"
    assert not _tokens_equal("27.00000", exact), (
        "a value with the wrong number of decimal places wrongly compared equal"
    )
    assert not _tokens_equal("27.0", exact), (
        "a value with the wrong number of decimal places wrongly compared equal"
    )
    assert _tokens_equal("27.000000", exact)

    # The two special-float strings (step 11) are exact-text, not float(),
    # comparisons too — float("1e+300") == float("1e300"), but the document
    # must spell it exactly as expected-answers.json does.
    py_value = _resolve(answers, "steps[10].expect.python_value")
    assert py_value == "1e+300"
    assert _tokens_equal("1e+300", py_value)
    assert not _tokens_equal("1e300", py_value), (
        "a differently-spelled but numerically-equal exponent wrongly compared equal"
    )
