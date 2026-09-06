"""demo/tests/test_prose_matches_data.py — T-17: the prose files, checked against the data.

WHY THIS FILE EXISTS
--------------------
On 2026-09-05 three defects of one shape surfaced in a single day:

* ``demo/README.md`` described walkthrough step 11 as a *live* disagreement between the
  two engines. T-8 had reconciled that case weeks earlier (T-13).
* the top-level ``README.md`` carried a caveat saying ``demo/README.md`` was out of date
  about step 11 — which stopped being true the moment T-13 fixed it (also T-13).
* ``demo/EVIDENCE.md``'s newest word on step 11 still predicted a divergence that T-8 had
  since removed (T-15).

The demo states the same facts in five places. Only one of them — ``demo/WALKTHROUGH.md`` —
was covered by a test (``test_walkthrough_doc.py``), and it is the only one that never
drifted. That is the whole argument for this file.

WHAT IS CHECKED, AND WHAT DELIBERATELY IS NOT
---------------------------------------------
``demo/README.md`` and the top-level ``README.md`` are **current-state** documents: they
describe how the demo behaves now, so they must agree with ``demo/expected-answers.json``.

``demo/EVIDENCE.md`` is **NOT** checked against the data, and must not be. It is a frozen,
append-only record of the build as it ran on 2026-08-22, corrected by appending dated notes
rather than by rewriting — exactly like ``spikes/``. Its ``steps[10]`` figures are *supposed*
to describe a state the build no longer has. Asserting they match today's data would force
the rewrite that would destroy the evidence, and would fail permanently by design. What is
checked instead is that it still carries the header saying it is history — because that
header is the entire reason excluding it is honest.

EVERY ASSERTION IS DERIVED FROM THE DATA, never hard-coded. If a future runtime change makes
the two engines disagree again, ``panes_agree`` flips and these checks invert with it: the
prose would then be *required* to say so. A test that has to be remembered is a test that
will not be.
"""

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "demo"

#: The documents that describe how the demo behaves *now*.
#: ``demo/WALKTHROUGH.md`` is absent on purpose — ``test_walkthrough_doc.py`` already
#: resolves every annotated number in it against the JSON, more strictly than anything here.
CURRENT_STATE_PROSE = ("demo/README.md", "README.md")

#: The frozen record. Excluded from the value and claim checks; see the module docstring.
FROZEN_RECORD = "demo/EVIDENCE.md"

#: Step 11 is ``steps[10]`` — the walkthrough numbers steps from 1, the JSON indexes from 0.
STEP_11 = 10

#: Present-tense assertions that the two engines disagree. Taken verbatim from the shapes the
#: pre-T-13 text actually used, not invented: "the two answers are supposed to come out
#: different". Past-tense narration ("the text used to drop out", "two plausible answers,
#: silently different, and a genuine bug") is deliberately NOT matched — the current, correct
#: text says exactly that while explaining the history, and a guard that forbade discussing
#: the past would push the docs into saying less than they should.
_PRESENT_TENSE_DISAGREEMENT = (
    r"are\s+supposed\s+to\s+come\s+out\s+different",
    r"are\s+supposed\s+to\s+(?:be\s+)?differ",
    r"are\s+supposed\s+to\s+disagree",
    r"\bdrops\s+out\s+of\s+the\s+calculation\b",
)

#: The mirror of the above: present-tense assertions that the two engines AGREE. Banned when
#: the data says they do not. Without this the guard was one-directional — the correct
#: past-tense text ("two plausible answers, silently different, and a genuine bug") contains
#: the word "different", so a naive search for "differ" could never fail and the "must say
#: so" branch passed vacuously. That was a real hole, found by running this file against a
#: synthetic tree with ``panes_agree`` flipped.
_PRESENT_TENSE_AGREEMENT = (
    r"both\s+panes\s+now\s+report",
    r"they\s+now\s+both\s+report",
    r"reading\s+the\s+same\s+on\s+both",
    r"the\s+panes\s+agree\b",
)

#: A current-state file must never advertise that another file is out of date. That is a
#: known-drift marker: the answer is to fix the other file, not to annotate around it. This
#: is the exact shape of the caveat T-13 removed from the top-level README.
_STALENESS_POINTER = (
    r"still\s+describes\s+step\s+11",
    r"still\s+calls\s+step\s+11",
    r"still\s+says\s+step\s+11",
)


def _names_value(blob, value):
    """Is ``value`` actually *named* in ``blob``, rather than merely appearing inside it?

    A bare ``value in blob`` is worthless for short values: ``"1" in blob`` is true of almost
    any English text, and of ``step 11`` and ``` `123` ``` in particular. So a value counts as
    named only when it is written the way this project writes values — in backticks — or
    stands alone as a token. Found by watching the substring form pass a tree it should have
    failed.
    """
    esc = re.escape(str(value))
    return re.search(rf"`{esc}`|(?<![0-9A-Za-z]){esc}(?![0-9A-Za-z])", blob) is not None


def _expected():
    data = json.loads((_DEMO_DIR / "expected-answers.json").read_text())
    steps = data["steps"] if "steps" in data else data
    expect = steps[STEP_11]["expect"]
    unwrap = lambda v: v["value"] if isinstance(v, dict) and "value" in v else v
    return {k: unwrap(v) for k, v in expect.items()}


def _step_11_paragraphs(rel):
    """The blank-line-separated paragraphs of ``rel`` that talk about step 11.

    Paragraph-scoped rather than whole-file so that an unrelated mention of the word
    "different" elsewhere in a long README cannot trip a check about step 11.
    """
    text = (_REPO_ROOT / rel).read_text()
    return [p for p in re.split(r"\n\s*\n", text) if re.search(r"step[\s-]*11", p, re.I)]


@pytest.fixture(scope="module")
def expected():
    return _expected()


class TestTheProseAgreesWithTheData:
    """The current-state documents, against ``expected-answers.json``."""

    def test_the_guard_has_something_to_guard(self):
        """At least one current-state document discusses step 11.

        Without this, deleting every mention would silence the checks below while looking
        like a pass — the classic way a failing assertion gets "fixed".
        """
        mentions = {rel: len(_step_11_paragraphs(rel)) for rel in CURRENT_STATE_PROSE}
        assert sum(mentions.values()) > 0, (
            "no current-state document mentions step 11 any more "
            f"({mentions}) — the checks in this class would pass vacuously"
        )

    @pytest.mark.parametrize("rel", CURRENT_STATE_PROSE)
    def test_the_value_it_names_is_the_value_in_the_data(self, rel, expected):
        """AC1 — any step-11 answer the prose names equals the shipped one."""
        paragraphs = _step_11_paragraphs(rel)
        if not paragraphs:
            pytest.skip(f"{rel} does not discuss step 11")
        blob = "\n".join(paragraphs)
        for field in ("python_value", "sql_value"):
            value = str(expected[field])
            assert _names_value(blob, value), (
                f"{rel} discusses step 11 but never names {field}={value!r}, which is what "
                f"demo/expected-answers.json steps[{STEP_11}].expect says the demo produces. "
                "Write it in backticks, the way the other values on the page are written."
            )

    @pytest.mark.parametrize("rel", CURRENT_STATE_PROSE)
    def test_the_claim_it_makes_matches_panes_agree(self, rel, expected):
        """AC2 — whether the prose may assert a live disagreement is decided by the data."""
        paragraphs = _step_11_paragraphs(rel)
        if not paragraphs:
            pytest.skip(f"{rel} does not discuss step 11")
        blob = "\n".join(paragraphs)

        if expected["panes_agree"]:
            for pattern in _PRESENT_TENSE_DISAGREEMENT:
                found = re.search(pattern, blob, re.I)
                assert not found, (
                    f"{rel} asserts the panes presently disagree ({found.group(0)!r}) but "
                    f"steps[{STEP_11}].expect.panes_agree is true — both panes answer "
                    f"{expected['python_value']!r}. Describing the case in the past tense is "
                    "fine; asserting it as current is not."
                )
        else:
            for pattern in _PRESENT_TENSE_AGREEMENT:
                found = re.search(pattern, blob, re.I)
                assert not found, (
                    f"{rel} says the panes presently agree ({found.group(0)!r}) but "
                    f"steps[{STEP_11}].expect.panes_agree is false — Python answers "
                    f"{expected['python_value']!r} and SQL answers {expected['sql_value']!r}. "
                    "A real divergence must not be described as agreement; that is the demo's "
                    "whole argument."
                )

    @pytest.mark.parametrize("rel", CURRENT_STATE_PROSE)
    def test_it_does_not_point_at_another_file_being_out_of_date(self, rel):
        """AC2 — no current-state file advertises another file's drift instead of fixing it."""
        text = (_REPO_ROOT / rel).read_text()
        for pattern in _STALENESS_POINTER:
            found = re.search(pattern, text, re.I)
            assert not found, (
                f"{rel} says another document is out of date about step 11 "
                f"({found.group(0)!r}). Fix that document; a pointer like this goes stale the "
                "moment it is acted on, which is how T-13 created a second contradiction."
            )


class TestTheFrozenRecordStaysMarkedAsFrozen:
    """``demo/EVIDENCE.md`` is excluded from the checks above — this is why that is honest."""

    def test_it_still_declares_itself_superseded(self):
        header = (_REPO_ROOT / FROZEN_RECORD).read_text()[:4000]
        assert "SUPERSEDED" in header, (
            f"{FROZEN_RECORD} no longer declares itself superseded in its opening. It is "
            "excluded from the data checks *because* that header tells a reader its figures "
            "are history. Without it the exclusion is no longer honest — either restore the "
            "header, or the file has become a current-state document and belongs in "
            "CURRENT_STATE_PROSE."
        )

    def test_it_is_not_silently_treated_as_current(self):
        assert FROZEN_RECORD not in CURRENT_STATE_PROSE, (
            f"{FROZEN_RECORD} is an append-only record of the 2026-08-22 build. Checking it "
            "against today's data would force rewriting evidence — see T-15."
        )
