"""demo/server/errors.py — the two refusal shapes §9.3 renders.

**This module defines no new exception.**  There are exactly two ways a
pick is refused, each raised by the file that owns the rule:

* **Layer 1** — :class:`demo.gate.Refused`.  The gate refused a construct
  (§4.4), or the alias validator refused a column name (§4.10).  It happens
  **before any SQL exists**, so there is no statement to show and both
  answer panes stay empty (AC-16).  The approved mock draws this as two
  adjacent views — `#gate` and `#alias` — same layer, same amber, a
  *different check*; the ``kind`` field below is what tells them apart.
* **Layer 2** — :class:`demo.probes.RuntimeRefusal`.  SQL existed, a probe
  fired, and the pick was abandoned **before its own statement ran**
  (§4.5).  The SQL side shows the probe and the condition it found and
  **no number**; the Python pane still shows its answer, labelled as the
  reported fallback (AC-17, AC-18, mock view `#probe`).

Defining a third exception here would put the rule in two places and let
the server disagree with the gate about what a refusal is.  What this file
adds is the one thing the exceptions do not carry: the shape the screen is
built from, so ``verdict.jsx`` and ``sqlpane.jsx`` read one field rather
than sniffing an exception type.
"""

from __future__ import annotations

import sys
from pathlib import Path

# demo/ is not a package; the flat import is what makes the exception
# objects caught here the same objects builder.py and probes.py raise.
_DEMO_DIR = str(Path(__file__).resolve().parent.parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import gate  # noqa: E402  (path bootstrap above)
import probes  # noqa: E402

__all__ = [
    "Refused", "RuntimeRefusal",
    "LAYER_1_HEADLINE", "LAYER_2_HEADLINE",
    "layer_1", "layer_2", "illegal_pick",
]

#: Re-exported so a reader of this module sees both shapes in one place.
Refused = gate.Refused
RuntimeRefusal = probes.RuntimeRefusal

LAYER_1_HEADLINE = "Refused before any SQL existed"
LAYER_2_HEADLINE = "Refused while running"

_LAYER_1_BODY = {
    "expression": (
        "The static gate walked the parsed expression and found a construct "
        "outside the safe subset. Nothing was compiled, nothing was "
        "prepared, and the database was never asked."
    ),
    "alias": (
        "The column-name check refused this name before it could reach SQL "
        "text. A computed column's name is the one piece of typed text that "
        "cannot be a bind parameter, so it is checked against an allowlist "
        "instead — and the statement it would have gone into was never "
        "built, never prepared and never sent."
    ),
    # W13-2.  A third check at the same layer, and a third view on the
    # screen: same amber, same shape as the gate's, a DIFFERENT check —
    # which is what `kind` is for.  It fires when a field slot holds
    # something the two calculators would read as two different fields;
    # see demo/server/app.py :: _as_dollar_path for the two measurements.
    "field": (
        "The field check refused this field slot before any SQL existed. A "
        "field slot is read by both calculators — the SQL side splits it on "
        "the dot and binds the pieces as the path, the Python side parses it "
        "with the vendored expr.py — and they agree on a plain dotted name "
        "and only on a plain dotted name. A slot they would read two "
        "different ways is refused here rather than answered twice, "
        "differently, by two panes that would then have to be compared."
    ),
}

_LAYER_2_BODY = (
    "The expression was inside the subset, so SQL was compiled for it. A "
    "probe then asked the data one question ahead of the pick's own query, "
    "and the answer means the pick cannot be computed honestly. The pick "
    "was abandoned before its own statement ran."
)


def layer_1(exc, *, kind: str) -> dict:
    """The JSON for a :class:`demo.gate.Refused`.

    ``kind`` is ``"expression"``, ``"alias"`` or ``"field"`` — §4.4's gate,
    §4.10's allowlist, or W13-2's field-slot check.  It is supplied by the
    caller because all three are raised by one exception class on purpose:
    the rule lives in one file, and only the call site knows which check it
    was in.
    """
    if kind not in _LAYER_1_BODY:
        raise ValueError(f"unknown layer-1 refusal kind {kind!r}")
    return {
        "layer": 1,
        "kind": kind,
        "headline": LAYER_1_HEADLINE,
        "body": _LAYER_1_BODY[kind],
        "construct": exc.construct,
        "why": exc.why,
        # There is no statement, and saying so is the point of the view.
        "sql_existed": False,
        "statement_sent": False,
    }


def layer_2(exc) -> dict:
    """The JSON for a :class:`demo.probes.RuntimeRefusal`."""
    return {
        "layer": 2,
        "kind": "probe",
        "headline": LAYER_2_HEADLINE,
        "body": _LAYER_2_BODY,
        "member": exc.member,
        "construct": f"probe ({exc.member})",
        "why": exc.cause,
        "row_key": exc.row_key,
        "probe_sql": exc.probe.sql,
        # SQL was compiled for the pick — and deliberately never sent.
        "sql_existed": True,
        "statement_sent": False,
    }


def illegal_pick(violations) -> dict:
    """A pick the legality matrix forbids, arriving other than through the
    screen (DR-2).  Not a layer at all: the screen cannot offer this, so a
    request carrying it is a client defect, answered with the matrix's own
    words rather than silently ignored or silently defaulted."""
    return {
        "layer": 0,
        "kind": "illegal",
        "headline": "This combination of operations is not offered",
        "body": (
            "The legality matrix — the same one function the screen greys "
            "its controls from — refuses this combination. A screen cannot "
            "produce it; a request that carries it is answered rather than "
            "quietly repaired."
        ),
        "violations": [dict(v) for v in violations],
        "why": "; ".join(v["why"] for v in violations),
        "sql_existed": False,
        "statement_sent": False,
    }
