"""operations.py — the single source of truth for the nine controls (B22).

Ruling B22 point 1 of ``.autodev/specs/T-2-plan.md``:

    ``demo/server/operations.py`` is the single source of truth for the
    nine controls — for each operation: its number, its label, its
    control shape (select / input / textarea / toggle / repeatable),
    its closed set of options where it has one, its ``.ctl-fixed`` note
    where it has one, and — computed by ``demo/legality.py`` for the
    current pick — whether it is enabled, and if not, the ``.op-why``
    reason.  It is served at ``GET /api/operations`` and re-derived on
    every pick.

W8 defines and tests this contract; W13 serves it (``server/app.py``)
and W14 renders it — ``pick.jsx`` invents no control (B22 point 2).

The one legality function is :func:`demo.legality.evaluate`; this file
never re-derives a rule, it merges that answer with the static control
descriptions below (§4.5: one function, so the screen and the server
cannot disagree).

Shape of one entry in ``contract(pick)["operations"]``::

    {
      "n":         1..9,
      "label":     the operation's name, as the approved mock names it,
      "kind":      "select" | "input" | "textarea" | "toggle" | "repeatable",
      "enabled":   bool,
      "why":       "" when enabled; the NON-EMPTY .op-why text when not (B5b/DR-2),
      "ctl_fixed": the dashed .ctl-fixed note, or None — ops 7, 8 and 9
                   carry one (design 3.1.1: R13/R14/Q20 are honoured by
                   NOT building something, and the absence is stated),
      "note":      a state-dependent hint, or None (op 2 on SCALAR/BUCKET:
                   defined, not emitted — B2),
      "controls":  [ {"name", "kind",
                      "options":      [{"value","label"}, ...] | None  (closed set),
                      "options_from": "fields" | "numeric_fields" | None
                                      (dynamic — served by /api/fields),
                      "range":        {"min","max"} | None,
                      "enabled":      bool,
                      "why":          "" | non-empty}, ... ],
      "transition": op 7 only — B5c's visible coercion, for the screen:
                   turning op 7 on while op 6 is none SETS op 6 to count,
                   in the control, with the stated reason.  Never silent.
    }

Top level::

    contract(pick) -> {"shape", "source", "operations": [nine entries],
                       "violations": [...]}   # violations: see legality.evaluate

Pure stdlib.  No FastAPI import here — W13 wires the route.
"""

from __future__ import annotations

import sys
from pathlib import Path

# demo/ is not a package; the server runs with demo/ on sys.path
# (run-demo launches it so).  Make the import hold regardless of cwd.
_DEMO_DIR = str(Path(__file__).resolve().parent.parent)
if _DEMO_DIR not in sys.path:
    sys.path.insert(0, _DEMO_DIR)

import legality  # noqa: E402  (path bootstrap above)


# ── static descriptions of the nine controls (design part 3.1.1) ────────

#: Row counts are §5's arithmetic: 50 × 168, 2,000, 10.
_SOURCE_OPTIONS = [
    {"value": "noun:Heartbeat", "label": "noun:Heartbeat · 8,400 rows"},
    {"value": "noun:Sample", "label": "noun:Sample · 2,000 rows"},
    {"value": "noun:EdgeCase", "label": "noun:EdgeCase · 10 rows"},
]

_AGG_OPTIONS = [
    {"value": "none", "label": "— none —"},
    {"value": "count", "label": "count"},
    {"value": "sum", "label": "sum"},
    {"value": "avg", "label": "avg"},
    {"value": "min", "label": "min"},
    {"value": "max", "label": "max"},
]

_BUCKET_OPTIONS = [
    {"value": "off", "label": "not bucketed"},
    {"value": "hour", "label": "per hour"},
    {"value": "day", "label": "per day"},
]

_SORT_DIR_OPTIONS = [
    {"value": "asc", "label": "ascending"},
    {"value": "desc", "label": "descending"},
]

_CTL_FIXED_7 = (
    "Two granularities and no more. hour and day are what Q20's own "
    "option text names, so they are a closed set — there is no week, no "
    "month and no free-text unit. What aggregates inside a bucket is "
    "operation 6's function."
)
_CTL_FIXED_8 = (
    "The field is the whole of this operation's input. Width 3, "
    "trailing, and an arithmetic mean are all fixed by R14 — there is "
    "deliberately no width box, no direction switch and no second "
    "aggregate here."
)
_CTL_FIXED_9 = (
    "An on/off toggle is the only control this operation gets. What it "
    "compares is the record minus its ordering key — status and "
    "payload, jointly — fixed by R13, so there is no picker for it and "
    "there must not be one."
)

_NOTE_CC_NOT_EMITTED = (
    "computed columns are defined, not emitted, while the pick returns "
    "one number per group: usable as operation 6's field, re-emitted "
    "inline (B2)"
)

#: B5c, stated once, carried on operation 7 for the screen to obey
#: visibly (never a silent default; a pick that skips the screen and
#: arrives with op 7 on over op 6 = none is refused by legality.evaluate).
_TRANSITION_7 = {
    "rule": "B5c",
    "when": "operation 7 turns on while operation 6 is none",
    "set": {"operation": 6, "fn": "count"},
    "why": legality.WHY_BUCKET_NEEDS_AGG,
}


def default_pick() -> dict:
    """The screen's initial state — re-exported from legality."""
    return legality.default_pick()


def contract(pick: dict | None = None) -> dict:
    """The whole ``/api/operations`` payload for one pick.

    Re-derived on every pick (B22): the caller hands the current pick
    and gets the nine operations with their enabled state and reasons.
    With no pick, the initial state.
    """
    if pick is None:
        pick = default_pick()

    lg = legality.evaluate(pick)
    ops = lg["ops"]
    shape = lg["shape"]
    agg_fn = (pick.get("aggregate") or {}).get("fn") or "none"

    def op(n: int, **fields) -> dict:
        entry = {
            "n": n,
            "enabled": ops[n]["enabled"],
            "why": ops[n]["why"],
            "ctl_fixed": None,
            "note": None,
        }
        entry.update(fields)
        # An operation's disable propagates to its controls, same reason.
        if not entry["enabled"]:
            for c in entry.get("controls", []):
                c["enabled"] = False
                c["why"] = entry["why"]
        return entry

    def ctl(name: str, kind: str, *, options=None, options_from=None,
            range=None, enabled=True, why="") -> dict:
        return {
            "name": name,
            "kind": kind,
            "options": options,
            "options_from": options_from,
            "range": range,
            "enabled": enabled,
            "why": why,
        }

    # Operation 6's field picker — the rule inside the operation
    # (count takes no field; none has no field to read).
    agg_field_state = lg["aggregate_field"]

    # B5a: on BUCKET, operation 6 may not be none — the option is not
    # offered (B5c seeds count on the way in; there is no way back to
    # none while bucketed).
    agg_options = (
        [o for o in _AGG_OPTIONS if o["value"] != "none"]
        if shape == legality.BUCKET
        else list(_AGG_OPTIONS)
    )

    operations = [
        op(1, label="Choose a source", kind="select", controls=[
            ctl("source", "select", options=list(_SOURCE_OPTIONS)),
        ]),
        op(2, label="Computed columns", kind="repeatable",
           note=(_NOTE_CC_NOT_EMITTED if shape != legality.ROWS else None),
           controls=[
               ctl("name", "input"),
               ctl("expression", "input"),
           ]),
        op(3, label="One filter", kind="textarea", controls=[
            ctl("filter", "textarea"),
        ]),
        op(4, label="Sort field", kind="select", controls=[
            ctl("field", "select", options_from="fields"),
            ctl("direction", "select", options=list(_SORT_DIR_OPTIONS)),
        ]),
        op(5, label="Row cap", kind="input", controls=[
            ctl("cap", "input", range={"min": legality.CAP_MIN,
                                       "max": legality.CAP_MAX}),
        ]),
        op(6, label="Aggregate", kind="select", controls=[
            ctl("fn", "select", options=agg_options),
            ctl("field", "select", options_from="numeric_fields",
                enabled=agg_field_state["enabled"],
                why=agg_field_state["why"]),
        ]),
        op(7, label="Time buckets", kind="select",
           ctl_fixed=_CTL_FIXED_7,
           transition=dict(_TRANSITION_7),
           controls=[
               ctl("granularity", "select", options=list(_BUCKET_OPTIONS)),
           ]),
        # R14: ONE field control — no width, no direction, no aggregate.
        op(8, label="Rolling window", kind="select",
           ctl_fixed=_CTL_FIXED_8,
           controls=[
               ctl("field", "select", options_from="numeric_fields"),
           ]),
        # R13 / AC-40(e): a toggle and NO value picker.
        op(9, label="Show only rows that changed", kind="toggle",
           ctl_fixed=_CTL_FIXED_9,
           controls=[
               ctl("changed", "toggle"),
           ]),
    ]

    return {
        "shape": shape,
        "source": lg["source"],
        "operations": operations,
        "violations": lg["violations"],
    }
