"""demo/seed/expectations.py — the THIRD independent path (T-2-plan.md B8).

INVENTED DATA — every number below describes fabricated rows (see
demo/seed/generate.py's header). Nothing here was measured anywhere.

WHAT THIS FILE IS FOR, AND THE ONE RULE THAT MAKES IT WORTH ANYTHING
-------------------------------------------------------------------
The demo answers every pick twice — once in SQL against Postgres, once in
Python (demo/pyrunner/) — and puts the two answers side by side. That
catches an error in either one. It cannot catch an error both make: two
implementations of one misreading agree perfectly, the side-by-side stays
green, and §5's control never fires (plan §9, failure mode 1).

So there is a third producer, and it is this file. It derives every
walkthrough number from the generator's own in-memory model with plain
Python, and it may not borrow a line of reasoning from either pane:

    B8.1 — it imports NOTHING from demo/pyrunner/, demo/builder.py or
           demo/probes.py. A test walks this module's AST and fails on any
           such import (demo/tests/test_walkthrough.py). That assertion is
           the whole point: good intentions do not survive a refactor, and
           an import added six weeks from now silently turns AC-31 back
           into the tautology B8 exists to remove.
    B8.2 — it computes from generate.py's rows, NOT by querying the
           database and NOT by running a pick.
    B8.3 — every number carries a `derivation` saying how it was reached.
           "Whatever the code returned" is not admissible; a reviewer reads
           this field, and a number whose derivation does not reconstruct it
           by hand is a number nobody has checked.

WHAT IT MAY IMPORT, AND WHY THAT IS NOT A LOOPHOLE
--------------------------------------------------
It imports demo.seed.generate — the rows themselves. That is B8.2's
instruction, not an exception to B8.1: generate.py is the *subject* both
panes are computing over, the one input all three producers must share or
they are not answering the same question. What B8 forbids is importing a
producer's *arithmetic*. The three arithmetics stay separate:

    the SQL      — Postgres, via demo/builder.py
    the Python   — demo/pyrunner/
    this file    — sums, groups and walks written out below, from scratch

Every rule this file re-implements is re-implemented from the spec text,
not called out to. Where that duplicates pyrunner, the duplication IS the
mechanism — two independent readings of one spec paragraph that agree are
evidence; one reading called twice is not.

THE SPEC PARAGRAPHS RE-IMPLEMENTED HERE (each cited at its use site)
-------------------------------------------------------------------
  §7.1 window rule       — the 3-point trailing frame, and what a short
                           window returns (divisor = non-null rows in the
                           frame, recounted per row; never the constant 3).
  §7.1 comparison rule   — operation 9 compares the record MINUS its
                           ordering key, parsed values, first row of each
                           partition always kept.
  §7.1 time-bucket rule  — the day bucket and its fixed-width UTC label.
  §7.2 exact-decimal     — accumulate in Decimal; every division followed
                           immediately by round-half-up to 6 places.
  §7.2 item 5            — the numeric read: a value counts only if it is
                           an int or a float AND is not a bool.
  §7.4 total order       — ORDER BY key; the tiebreak is always key ASC,
                           whichever way the sort field runs.

Determinism: nothing here reads the clock (plan §5.5's grep covers this
directory), and the output is a pure function of generate.py's rows.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# B8.1: demo.seed.generate ONLY. No pyrunner, no builder, no probes.
from demo.seed import generate

_OUT = Path(__file__).resolve().parents[1] / "expected-answers.json"


# ===========================================================================
# The primitives, written out from the spec text (not imported from a pane).
# ===========================================================================

_Q6 = Decimal("0.000001")


def q6(value: Decimal) -> Decimal:
    """§7.2 item 2 — round half-up to 6 decimal places, ties away from zero.

    ROUND_HALF_UP is passed explicitly because Python's default is
    ROUND_HALF_EVEN (banker's rounding), which is not what a reader checking
    by hand does. Postgres's numeric round(x, 6) is documented to round half
    away from zero, which is the same rule; that is what makes the two panes
    agree on the last digit rather than nearly agree.
    """
    return value.quantize(_Q6, rounding=ROUND_HALF_UP)


def numeric_read(value: Any) -> Optional[Decimal]:
    """§7.2 item 5 — how a number gets out of the JSON, Python side.

    A value counts only if it is an int or a float AND is not a bool.
    Python's bool subclasses int, so a bare isinstance(v, (int, float))
    accepts True and scores it as 1, while jsonb_typeof calls it 'boolean'
    and the SQL side scores it as nothing. Anything else — a string, a null,
    an object, an array, a missing key — reads as None, which drops out of
    both the sum and the divisor, exactly as SQL's null does.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return None


def path_get(record: Dict[str, Any], *parts: str) -> Any:
    """Read $.a.b out of a parsed record; a missing key reads as None."""
    node: Any = record
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def by_key(rows: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
    """§7.4 — ORDER BY key, ascending, under the C collation.

    The database is initialised --locale=C (plan §11.2), so its text order is
    byte order; Python's str comparison over these ASCII keys is the same
    order. R19 makes every key fixed-width (hb-NN-BBBB), so text order is
    also record order and no numeric parse is needed to agree with SQL.
    """
    return sorted(rows, key=lambda pair: pair[0])


# ===========================================================================
# The model — generate.py's rows, parsed once (B8.2: no database, no pick).
# ===========================================================================

def heartbeats() -> List[Tuple[str, Dict[str, Any]]]:
    """Every noun:Heartbeat row as (key, parsed record), in generator order."""
    return [(key, json.loads(data)) for _c, key, data in generate.heartbeat_rows()]


def per_sender(rows: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, List[Tuple[str, Dict[str, Any]]]]:
    """§7.1's window frame: PARTITION BY sender_id ORDER BY ts, key.

    Both components are compared as TEXT on purpose. sender_id is text
    already; ts is fixed-width UTC ISO-8601 (YYYY-MM-DDTHH:MM:SSZ), the one
    form in which text order IS time order — so neither pane parses a date
    to reach the same sequence, and this file does not either.
    """
    groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    for key, record in rows:
        groups[str(record.get("sender_id"))].append((key, record))
    for sender in groups:
        groups[sender].sort(key=lambda pair: (str(pair[1].get("ts")), pair[0]))
    return dict(groups)


# ---------------------------------------------------------------------------
# Operation 8 — the 3-point trailing rolling average (§7.1's window rule).
# ---------------------------------------------------------------------------

def rolling_average(
    groups: Dict[str, List[Tuple[str, Dict[str, Any]]]],
    *parts: str,
) -> List[Tuple[str, Optional[Decimal]]]:
    """(key, 3-point trailing rolling average) for every heartbeat row.

    The frame is ROWS BETWEEN 2 PRECEDING AND CURRENT ROW inside one sender.
    §7.1's window rule pins what a SHORT window returns, and the divisor is
    written the long way because the rule is the long way:

        the divisor is the number of rows actually in the frame whose value
        is non-null, recounted for every row — NEVER the constant 3.

    On the seeded data payload.load is always present, so rows 3+ divide by
    3; rows 1 and 2 divide by 1 and 2. A build that divides by 3 always, or
    that emits null until three rows have accumulated, disagrees with SQL on
    the first two rows of all 50 senders — 100 cells — and agrees everywhere
    else. That is a false disagreement, the one thing §5 says the screen must
    never manufacture, which is why this file recomputes it rather than
    trusting either pane to have got it right.
    """
    out: List[Tuple[str, Optional[Decimal]]] = []
    for sender in sorted(groups):
        ordered = groups[sender]
        for index, (key, _record) in enumerate(ordered):
            frame = ordered[max(0, index - 2): index + 1]
            values = [
                v for v in (numeric_read(path_get(r, *parts)) for _k, r in frame)
                if v is not None
            ]
            if not values:
                # Every row in the frame is null -> the cell is null, not a
                # zero. Both panes print null (§7.1's window rule).
                out.append((key, None))
            else:
                out.append((key, q6(sum(values, Decimal(0)) / Decimal(len(values)))))
    return out


# ---------------------------------------------------------------------------
# Operation 9 — show only rows that changed (§7.1's comparison rule).
# ---------------------------------------------------------------------------

def changed_keys(groups: Dict[str, List[Tuple[str, Dict[str, Any]]]]) -> List[str]:
    """The keys operation 9 keeps, in §7.4's total order (ORDER BY key).

    The compared value is THE RECORD MINUS ITS ORDERING KEY — the Python
    spelling of SQL's `data - 'ts'`. Excluding ts is structural, not a
    preference about this data: a sequence whose ordering key changes at
    every step is what a sequence IS, so letting it count as a change makes
    the operation keep all 8,400 rows and do nothing while appearing to work.

    Two details this re-implementation pins, each a divergence if guessed:
      * the comparison is over PARSED values, never serialised text — jsonb
        reorders object keys and normalises numbers, json.dumps does neither,
        so two equal records would compare unequal if either side compared
        strings;
      * the first row of each partition has no predecessor and is ALWAYS
        kept — SQL gets that from IS DISTINCT FROM against a NULL lag(); here
        it is the `previous is None` arm, which is the same convention and
        not a special case bolted on afterwards.
    """
    kept: List[str] = []
    for sender in sorted(groups):
        previous: Optional[Dict[str, Any]] = None
        for key, record in groups[sender]:
            compared = {k: v for k, v in record.items() if k != "ts"}
            if previous is None or compared != previous:
                kept.append(key)
            previous = compared
    return sorted(kept)


# ---------------------------------------------------------------------------
# Operation 7 — day buckets (§7.1's time-bucket rule).
# ---------------------------------------------------------------------------

def day_buckets(rows: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, int]]:
    """(bucket label, row count) per UTC day, ordered by label.

    The label is the same fixed-width UTC ISO-8601 form ts itself uses, which
    is what SQL's to_char(..., 'YYYY-MM-DD"T"HH24:MI:SS"Z"') produces. Left to
    themselves the two engines spell one instant differently — Postgres's
    default timestamptz rendering is `2026-08-14 00:00:00+00`, Python's
    datetime.isoformat() is `2026-08-14T00:00:00+00:00` — and `bucket` is a
    real output column both panes key their rows by, so two spellings of one
    instant are two different keys and every bucketed row disagrees while
    every count inside them agrees.

    Truncating to the day is a slice of the first 10 characters, not a date
    parse: ts is fixed-width and already UTC, so `2026-08-14T04:00:00Z`[:10]
    is the day, exactly as date_trunc('day', ...) in a UTC session gives it.
    The session time zone is what makes this 7 buckets and not 8 — a session
    an hour off the meridian splits the span across an eighth day — and the
    demo pins it to UTC on every connection it opens.
    """
    counts: Dict[str, int] = defaultdict(int)
    for _key, record in rows:
        ts = str(record.get("ts"))
        counts[ts[:10] + "T00:00:00Z"] += 1
    return sorted(counts.items())


# ---------------------------------------------------------------------------
# Step 8's worked example — which sender, chosen by a stated rule.
# ---------------------------------------------------------------------------

def worked_example_sender(
    groups: Dict[str, List[Tuple[str, Dict[str, Any]]]],
) -> Tuple[str, List[int], List[Decimal]]:
    """Pick the sender whose first five rolling values actually DEMONSTRATE
    §7.1's window rule, and return it with its loads and its five values.

    NEW RULING (W6-R1) — see the module note at build_answers(). §10 step 8
    says the walkthrough "shows one sender's first five values worked out by
    hand" and never says which sender. The obvious pick, hb-01, is the one
    that demonstrates nothing: its first five loads are all 18, so ÷1, ÷2 and
    ÷3 all return 18.000000 and a reader cannot tell a correct divisor from
    any of the three wrong ones the window rule exists to forbid.

    The rule this function applies instead, stated so it is reproducible and
    not a cherry-pick:

        the lowest-numbered sender whose first three rolling values are
        pairwise distinct (so ÷1, ÷2 and ÷3 are each visibly different)
        AND whose first three loads do not sum to a multiple of 3 (so the
        third value is the non-terminating division §7.2 says step 8 exists
        to exercise).

    On the seeded corpus exactly one sender satisfies it, so there is no
    tie to break and the choice is forced rather than preferred. The
    assertion below fails loudly if a reseed ever makes it ambiguous or
    empty, because a silent fallback to "the first one" would quietly
    reinstate the hb-01 problem this rule exists to fix.
    """
    matches: List[Tuple[str, List[int], List[Decimal]]] = []
    for sender in sorted(groups):
        first_five = groups[sender][:5]
        loads = [int(path_get(r, "payload", "load")) for _k, r in first_five]
        values = [
            q6(Decimal(sum(loads[max(0, i - 2): i + 1]))
               / Decimal(len(loads[max(0, i - 2): i + 1])))
            for i in range(len(loads))
        ]
        if len(set(values[:3])) == 3 and sum(loads[:3]) % 3 != 0:
            matches.append((sender, loads, values))
    if len(matches) != 1:
        raise AssertionError(
            "step 8's worked-example rule selected "
            f"{len(matches)} senders {[m[0] for m in matches]}, expected exactly 1 — "
            "the seed changed; re-state the rule rather than picking one by hand"
        )
    return matches[0]


# ===========================================================================
# The answers.
# ===========================================================================

def entry(value: Any, derivation: str) -> Dict[str, Any]:
    """One expected value and how it was reached (B8.3).

    The derivation is not decoration and it is not a restatement of the
    value. It must let a reader reconstruct the number without running
    anything — the arithmetic, or the spec rule that fixes it, or both.
    """
    if not derivation or not derivation.strip():
        raise AssertionError(f"B8.3: a derivation is required for value {value!r}")
    return {"value": value, "derivation": derivation}


def d6(value: Optional[Decimal]) -> Optional[str]:
    """A rounded value as the fixed 6-place STRING both panes compare.

    Emitted as a string, not a JSON number: step 8's whole claim is
    digit-for-digit agreement (AC-24(a)), and a JSON number would be read
    back as a binary float — which is exactly the representation §7.2 spends
    its length removing from these three operations. `null` stays null.
    """
    return None if value is None else f"{value:.6f}"


def build_answers() -> Dict[str, Any]:
    """Every walkthrough number, derived here and nowhere else.

    NEW RULINGS taken in this file, both recorded in the W6 report:

      W6-R1 — §10 step 8 does not say WHICH sender's five values the
              walkthrough works out by hand, and the obvious choice (hb-01)
              demonstrates nothing: its first five loads are identical, so
              ÷1, ÷2 and ÷3 all print 18.000000. worked_example_sender()
              states a selection rule that picks the sender which actually
              exercises the short-window cases and the non-terminating
              division. Exactly one sender qualifies.

      W6-R2 — step 8 additionally publishes a digest over the WHOLE 8,400-row
              rolling column, not just the five worked cells. Five cells from
              one sender cannot detect the 100-cell failure §7.1's window rule
              is written to prevent unless that sender happens to be one of
              the ones affected — and every sender is affected, but only in
              its first two rows. The digest makes the entire column checkable
              by one comparison, which is what AC-24(d) needs to be more than
              a spot check.
    """
    rows = heartbeats()
    groups = per_sender(rows)
    ordered = by_key(rows)

    # -- the shared totals, each recomputed here -----------------------------
    total_rows = len(rows)
    senders = sorted(groups)
    beats = len(groups[senders[0]])

    ok_rows = [(k, r) for k, r in ordered if r.get("status") == "ok"]
    not_ok_rows = [(k, r) for k, r in ordered if r.get("status") != "ok"]

    load_values = [numeric_read(path_get(r, "payload", "load")) for _k, r in rows]
    load_sum = sum((v for v in load_values if v is not None), Decimal(0))

    buckets = day_buckets(rows)
    kept = changed_keys(groups)
    rolling = rolling_average(groups, "payload", "load")
    example_sender, example_loads, example_values = worked_example_sender(groups)

    # The sort of step 5, written the way §7.4 insists the Python side write
    # it: key ASCENDING first, then a STABLE sort on the sort field in the
    # chosen direction. Never sorted(..., reverse=True) over a tuple holding
    # key — that reverses the whole tuple and sorts key DESCENDING, which
    # returns the ten HIGHEST keys at the latest ts instead of the ten
    # lowest, disagreeing with SQL on all ten rows of this very step.
    step5 = list(ordered)
    step5.sort(key=lambda pair: str(pair[1].get("ts")), reverse=True)
    step5_top10 = [k for k, _r in step5[:10]]
    latest_ts = str(step5[0][1].get("ts"))

    # W6-R2 — a digest over the whole rolling column, in key order, each cell
    # in the same 6-place form the panes compare. One comparison covers all
    # 8,400 cells instead of the five worked by hand.
    digest = hashlib.sha256()
    for key, value in sorted(rolling, key=lambda pair: pair[0]):
        digest.update(key.encode())
        digest.update(b"\x1f")
        digest.update(("null" if value is None else f"{value:.6f}").encode())
        digest.update(b"\n")
    rolling_digest = digest.hexdigest()

    steps: List[Dict[str, Any]] = []

    # -- step 1 --------------------------------------------------------------
    steps.append({
        "step": 1,
        "title": "Run the one command from a clean checkout",
        "pick": {"operation": None, "note": "./run-demo up"},
        "derivation": (
            "Infrastructure, not data. The two ports are fixed constants of this demo "
            "(plan §11.2) and the row counts are the seed's by construction."
        ),
        "expect": {
            # AC-3 forbids the live database's port number ANYWHERE in the
            # demo tree, and a derivation is part of the tree. Say what the
            # rule is; do not repeat the number the rule is about.
            "db_port": entry(55440, "The demo's own Postgres port, fixed at plan §11.2. It is deliberately not the port of the live database on this machine, which this demo must never reach — and AC-3 forbids that number appearing anywhere in the demo tree, including in this sentence."),
            "app_port": entry(8787, "The demo's own app port, fixed at plan §11.2."),
            "rows_loaded": entry(
                total_rows + generate.SAMPLES + len(generate.EDGE_CASES),
                f"{total_rows} heartbeats + {generate.SAMPLES} samples + "
                f"{len(generate.EDGE_CASES)} edge cases = "
                f"{total_rows + generate.SAMPLES + len(generate.EDGE_CASES)} rows, counted from the generator's own streams.",
            ),
        },
    })

    # -- step 2 --------------------------------------------------------------
    steps.append({
        "step": 2,
        "title": "Choose source noun:Heartbeat, no other pick",
        "pick": {"operation": 1, "source": "noun:Heartbeat"},
        "derivation": (
            "A plain select over demo.records with the collection as a bind parameter, "
            "ending in ORDER BY key. No sort field is picked, so §7.4's total order is "
            "the tiebreak alone — which is what makes 'the first row' a thing that exists."
        ),
        "expect": {
            "row_count": entry(
                total_rows,
                f"{len(senders)} senders x {beats} hourly beats = {total_rows}. "
                f"R5 fixes the senders at {len(senders)} (hb-01 … hb-{len(senders):02d}); R17 fixes the span at "
                f"7 whole UTC days x 24 hours = {beats} beats. Counted from generate.heartbeat_rows().",
            ),
            "first_key": entry(ordered[0][0], "The lowest key under ORDER BY key: sender hb-01's beat 0000. R19's fixed-width keys make text order record order."),
            "last_key": entry(ordered[-1][0], f"The highest key under ORDER BY key: sender hb-{len(senders):02d}'s beat {beats - 1:04d}."),
        },
    })

    # -- step 3 --------------------------------------------------------------
    steps.append({
        "step": 3,
        "title": 'Add a computed column alive = $.status == "ok"',
        "pick": {"operation": 2, "source": "noun:Heartbeat", "alias": "alive", "expression": '$.status == "ok"'},
        "derivation": (
            "Accepted, not refused — §4.6's ruling in action; under reading B a field "
            "reference beside == would have been refused here. The counts are a partition "
            "of the 8,400 rows by one closed-set field (R16: ok / warn / error)."
        ),
        "expect": {
            "true_count": entry(
                len(ok_rows),
                f"Rows whose status is exactly 'ok': {len(ok_rows)} of {total_rows}, counted one row at a time "
                f"off the generator. R16 draws status about 90/8/2 across ok/warn/error, so ~90% of "
                f"{total_rows} is ~{round(total_rows * 0.9)} and {len(ok_rows)} sits where that predicts.",
            ),
            "false_count": entry(
                len(not_ok_rows),
                f"{total_rows} - {len(ok_rows)} = {len(not_ok_rows)}. The two counts must sum to the step-2 total, "
                f"and they do; status is never null on this collection so there is no third bucket.",
            ),
        },
    })

    # -- step 4 --------------------------------------------------------------
    steps.append({
        "step": 4,
        "title": 'Filter $.status != "ok"',
        "pick": {"operation": 3, "source": "noun:Heartbeat", "filter": '$.status != "ok"'},
        "derivation": (
            "The complement of step 3's true_count, and the same 857 rows. 'The first row' "
            "is defined only because ORDER BY key is always emitted (§7.4) — without it "
            "Postgres promises no order here and the two panes could disagree while both "
            "were correct."
        ),
        "expect": {
            "row_count": entry(
                len(not_ok_rows),
                f"The complement of step 3: {total_rows} - {len(ok_rows)} = {len(not_ok_rows)}. "
                f"Derived as its own count here, then checked against step 3's subtraction — "
                f"two routes to one number.",
            ),
            "first_key": entry(
                not_ok_rows[0][0],
                f"The lowest key among the {len(not_ok_rows)} non-ok rows under ORDER BY key. "
                f"Its status is '{not_ok_rows[0][1].get('status')}'.",
            ),
            "first_status": entry(
                not_ok_rows[0][1].get("status"),
                f"Read off row {not_ok_rows[0][0]} — the first non-ok row in key order. It is not 'ok', "
                f"which is the filter's whole assertion.",
            ),
        },
    })

    # -- step 5 --------------------------------------------------------------
    steps.append({
        "step": 5,
        "title": "Sort by $.ts descending, cap at 10",
        "pick": {"operation": 4, "source": "noun:Heartbeat", "sort": "$.ts", "direction": "desc", "limit": 10},
        "derivation": (
            "Every ts is shared by all 50 senders, so the whole result is ONE tie and the "
            "LIMIT boundary sits inside it. §7.4(1a) breaks it by key ASCENDING even though "
            "the sort is descending — so these are the ten LOWEST keys at the latest "
            "timestamp. A Python pane written as sorted(..., reverse=True) over a tuple "
            "containing key would return the ten HIGHEST instead and disagree on all ten."
        ),
        "expect": {
            "latest_ts": entry(
                latest_ts,
                f"Beat {beats - 1} of the span R17 fixes: 2026-08-14T00:00:00Z + {beats - 1} hours = {latest_ts}. "
                f"All {len(senders)} senders carry it, which is what makes the tie total.",
            ),
            "keys": entry(
                step5_top10,
                f"The 10 lowest keys at {latest_ts}, i.e. senders hb-01 … hb-10 at beat {beats - 1:04d}. "
                f"Derived by sorting key ascending, then STABLE-sorting on ts descending — never "
                f"reverse=True over a tuple holding key.",
            ),
            "row_count": entry(10, "The row cap, applied after sorting (operation 5). 8,400 rows are available, so the cap binds."),
        },
    })

    # -- step 6 --------------------------------------------------------------
    steps.append({
        "step": 6,
        "title": "Aggregate: sum of $.payload.load",
        "pick": {"operation": 6, "source": "noun:Heartbeat", "aggregate": "sum", "field": "$.payload.load"},
        "derivation": (
            "B8's headline case. This is the ONE walkthrough number that had no per-pane "
            "absolute assertion, so AC-31 compared the pane against itself. This figure is "
            "the third path: 8,400 integers added up in decimal.Decimal, straight off the "
            "generator, with no database and no pick involved. B8.4 requires it be asserted "
            "on EACH pane separately against this value before the panes are compared."
        ),
        "expect": {
            "sum": entry(
                str(load_sum),
                f"The sum of payload.load over all {total_rows} heartbeat rows = {load_sum}. "
                f"Accumulated in decimal.Decimal, one row at a time, in generator order. Every load "
                f"is an integer 0–100 (R16), so the total is an integer and floating point never "
                f"enters: a float8 accumulation could return {load_sum}.000000000001 and be "
                f"uncheckable by eye, which §7.2 exists to prevent. Bounds a reader can check "
                f"without adding anything up: 0 <= {load_sum} <= {total_rows} x 100 = {total_rows * 100}, "
                f"and the mean load is {load_sum}/{total_rows} = "
                f"{q6(load_sum / Decimal(total_rows))}, which sits where a uniform 0–100 draw predicts (~50).",
            ),
            "row_count": entry(
                total_rows,
                f"All {total_rows} rows contribute: payload.load is present and an integer on every "
                f"heartbeat row, so §7.2 item 5's numeric read returns a number for each and none "
                f"drops out of the sum.",
            ),
        },
    })

    # -- step 7 --------------------------------------------------------------
    steps.append({
        "step": 7,
        "title": "Time bucket by day, count per bucket",
        "pick": {"operation": 7, "source": "noun:Heartbeat", "granularity": "day", "aggregate": "count"},
        "derivation": (
            "7 buckets and not 8 is the session time zone doing its job: the span is seven "
            "whole UTC days, and a session an hour off the meridian splits it across an "
            "eighth. The labels are compared AS STRINGS, so the two engines' default "
            "spellings of one instant would be two different keys."
        ),
        "expect": {
            "bucket_count": entry(
                len(buckets),
                f"R17's span is 7 whole UTC days (2026-08-14 … 2026-08-20) and every beat sits "
                f"inside it, so a UTC day bucket gives exactly {len(buckets)}. Counted from the "
                f"distinct ts[:10] values in the generator's rows.",
            ),
            "rows_per_bucket": entry(
                sorted({count for _label, count in buckets}),
                f"{len(senders)} senders x 24 hourly beats per day = {len(senders) * 24} rows in every "
                f"bucket. Every bucket holds the same count because the span is whole days and no "
                f"sender misses a beat — which is also why {len(buckets)} x {len(senders) * 24} = "
                f"{len(buckets) * len(senders) * 24} must equal step 2's {total_rows}, and it does.",
            ),
            "buckets": entry(
                [{"bucket": label, "count": count} for label, count in buckets],
                "Each label is the day's midnight in the same fixed-width UTC ISO-8601 form ts uses "
                "(YYYY-MM-DDTHH:MM:SSZ), which is what to_char(..., 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                "emits. Counts are rows per day, tallied off the generator. Ordered by label, which "
                "is a total order because the labels are distinct and fixed-width.",
            ),
        },
    })

    # -- step 8 --------------------------------------------------------------
    example_rows = [k for k, _r in groups[example_sender][:5]]
    steps.append({
        "step": 8,
        "title": "Rolling window: 3-point rolling average of $.payload.load per sender",
        "pick": {"operation": 8, "source": "noun:Heartbeat", "field": "$.payload.load", "width": 3, "shape": "trailing average"},
        "derivation": (
            "§7.1's window rule, whose entire purpose is that the SHORT windows agree. The "
            "divisor is the number of non-null values actually in the frame, recounted every "
            "row — never the constant 3. A pane that divides by 3 always, or that returns null "
            "until three rows exist, is wrong on rows 1 and 2 of all 50 senders (100 cells) and "
            "right everywhere else: a false disagreement, which §5 calls the single most "
            "damaging thing this screen can produce."
        ),
        "expect": {
            "worked_sender": entry(
                example_sender,
                "W6-R1: §10 step 8 does not name a sender, and hb-01 — the obvious pick — has five "
                "identical loads, so ÷1, ÷2 and ÷3 all print the same number and the step "
                "demonstrates nothing. Selection rule: the lowest-numbered sender whose first three "
                "rolling values are pairwise distinct AND whose first three loads do not sum to a "
                "multiple of 3. Exactly one sender on this corpus qualifies, so the choice is forced.",
            ),
            "worked_loads": entry(
                example_loads,
                f"The payload.load of {example_sender}'s first five beats, in (ts, key) order, read "
                f"straight off the generator: {example_loads}.",
            ),
            "worked_values": entry(
                [
                    {"key": k, "window": example_loads[max(0, i - 2): i + 1], "value": d6(v)}
                    for i, (k, v) in enumerate(zip(example_rows, example_values))
                ],
                "Worked by hand, and every one of these is checkable without running anything: "
                + "; ".join(
                    "{key} = ({terms}) / {n} = {val}".format(
                        key=k,
                        terms=" + ".join(str(x) for x in example_loads[max(0, i - 2): i + 1]),
                        n=len(example_loads[max(0, i - 2): i + 1]),
                        val=d6(v),
                    )
                    for i, (k, v) in enumerate(zip(example_rows, example_values))
                )
                + ". Row 1 divides by 1 (its own load, NOT blank and NOT ÷3); row 2 by 2; rows 3–5 by 3. "
                  "Row 3 is the non-terminating division §7.2 says this step exists to exercise — it "
                  "does not terminate in decimal, so the 6-place half-up round is what decides its "
                  "last digit. Note honestly: a ÷3 can never produce an exact half, so this cell does "
                  "NOT discriminate half-up from banker's rounding; AC-24(b)'s own tie fixture is what "
                  "tests that, and this file does not claim to.",
            ),
            "column_sha256": entry(
                rolling_digest,
                "W6-R2: sha256 over all " + str(len(rolling)) + " rolling cells in key order, each as "
                "'<key>\\x1f<value at 6dp>\\n' with a null cell written 'null'. Five worked cells from "
                "one sender cannot catch the 100-cell short-window failure unless that sender is "
                "affected; every sender is, but only in its first two rows. This digest makes the whole "
                "column one comparison. A pane that divides by 3 always changes it.",
            ),
            "row_count": entry(
                len(rolling),
                f"One cell per heartbeat row — {len(rolling)}. The window drops no row and pads no row "
                f"(§7.1's window rule), so this must equal step 2's {total_rows}.",
            ),
        },
    })

    # -- step 9 --------------------------------------------------------------
    steps.append({
        "step": 9,
        "title": "Show only rows that changed, per sender",
        "pick": {"operation": 9, "source": "noun:Heartbeat"},
        "derivation": (
            "The case the project was pitched on. What 'changed' compares is the record MINUS "
            "its ordering key — status and payload, jointly; ts is excluded by construction. "
            "That exclusion is the whole operation: put ts back and every row differs from its "
            "predecessor, all 8,400 are kept, and the step does nothing while appearing to work "
            "— with both panes agreeing perfectly, which is why this third path exists."
        ),
        "expect": {
            "kept_count": entry(
                len(kept),
                f"{len(kept)} of {total_rows} rows kept. Derived by walking each sender's beats in "
                f"(ts, key) order and keeping a row when {{k: v for k, v in record.items() if k != 'ts'}} "
                f"differs from its predecessor's. Two independent checks a reader can do on this "
                f"number: (a) each of the {len(senders)} senders' first beat has no predecessor and is "
                f"always kept, so the count cannot be below {len(senders)}; (b) B27 redraws on a 0.10 "
                f"coin at each of the remaining {beats - 1} beats, so the expected total is about "
                f"{len(senders)} + {len(senders)} x {beats - 1} x 0.10 = "
                f"{round(len(senders) + len(senders) * (beats - 1) * 0.10)}, and {len(kept)} sits there. "
                f"AC-40's band is 700–1,100 and this is inside it.",
            ),
            "first_five_keys": entry(
                kept[:5],
                "The five lowest kept keys under §7.4's total order (ORDER BY key over the kept rows), "
                "so 'the first five' is defined rather than whatever the plan happened to emit. All "
                "five are hb-01's, because key order groups a sender's beats together and hb-01 sorts "
                "first; the first of them is hb-01's beat 0000, kept because it has no predecessor.",
            ),
            "kept_if_ts_included": entry(
                total_rows,
                f"The NEGATIVE control, stated as a number so the failure is named and not merely "
                f"counted: if the compared value wrongly included ts, every row would differ from its "
                f"predecessor and all {total_rows} would be kept. That is not a near miss but a "
                f"{round(total_rows / len(kept))}-fold one, visible in a single integer. AC-40 asserts "
                f"both this and the {len(kept)} above.",
            ),
            "band": entry(
                [700, 1100],
                "AC-40's band, quoted from the spec so a reader can see the kept_count sits inside it. "
                "The band comes from AC-8's independently-pinned 88–92% repeat rate, which is the same "
                "property read from the other side.",
            ),
        },
    })

    # -- step 10 -------------------------------------------------------------
    steps.append({
        "step": 10,
        "title": "Type round($.payload.load, 1) as a computed column",
        "pick": {"operation": 2, "source": "noun:Heartbeat", "alias": "rounded", "expression": "round($.payload.load, 1)"},
        "derivation": (
            "Refused by the STATIC gate — before any SQL exists. §4.2 lists round among the "
            "three rounding functions outside the safe subset (round, floor, ceil), so the "
            "refusal is a property of the subset definition, not of the data."
        ),
        "expect": {
            "verdict": entry("refused", "§4.2: round is one of the 16 refused constructs. Layer 1 catches it, so nothing is compiled and nothing runs."),
            "refused_by": entry("static gate (layer 1)", "§4.4. The gate walks the AST before compilation; no database round trip happens."),
            "names_construct": entry("round", "§4.4 requires every refusal to name the construct or the rule. The message must contain 'round'."),
            "sql_pane": entry(None, "No SQL is generated at all — this is what distinguishes a layer-1 refusal from a layer-2 one (steps 12 and 13)."),
            "python_pane": entry(None, "Both panes stay empty. The gate is upstream of both, so neither calculator is reached."),
            "why_it_proves_something": entry(
                "compile.py implements round at :394",
                "Without the gate this step would compile, run and print a number. That is what makes "
                "it a real test of the subset rather than a demonstration of something impossible.",
            ),
        },
    })

    # -- step 11 -------------------------------------------------------------
    # 2026-08-23, q4/GA-7 (the dated note beside AC-22 in T-2.md): the demo
    # adopted T-3's corrected runtime.sql, whose 309-digit guard reads 1e300
    # correctly — so max($.l) over [1e300, 1] now AGREES (both panes 1e+300)
    # and can no longer carry §5's shown disagreement. The step moved to the
    # divergence T-3 measured as SURVIVING the fix: the Unicode-digit gap.
    # T-6 will convert that gap to a named refusal, at which point this step
    # moves again (Evan was told this in the q4 form and chose adopt).
    steps.append({
        "step": 11,
        "title": "Source noun:EdgeCase, computed column biggest = max($.m)",
        "pick": {"operation": 2, "source": "noun:EdgeCase", "alias": "biggest", "expression": "max($.m)"},
        "derivation": (
            "§5's control, demonstrated: the two panes disagree, visibly and deliberately, and "
            "the screen flags it. Note max IS in the safe subset (§4.2 allows abs, coalesce, "
            "count, if, length, max, min) — it is sum and avg that are refused, which is why "
            "this step runs at all where step 10 does not."
        ),
        "expect": {
            "row": entry("edge-01", 'The only seeded EdgeCase row carrying an `m` key; its value is the array ["１２３", 1] (B24 as amended 2026-08-23) — a string of FULLWIDTH digits (U+FF11 U+FF12 U+FF13) beside a plain number.'),
            "python_value": entry(
                "123",
                "Python's max over the parsed array [\"１２３\", 1]. Python's string-to-number "
                "coercion is float(), and float() accepts any Unicode decimal digit — "
                "float(\"１２３\") is 123.0 — so the string converts, 123.0 > 1, and the ECMA "
                "shortest rendering of 123.0 is 123. (T-3's finding 1: the Unicode-digit gap, "
                "the divergence that SURVIVES the corrected runtime.)",
            ),
            "sql_value": entry(
                "1",
                "Derived from the corrected runtime's string gate, not from running anything: "
                "its string-to-number regex admits ASCII digits [0-9] only, so \"１２３\" reads "
                "as missing on the SQL side. max ignores anything missing, and the only element "
                "left of [\"１２３\", 1] is 1.",
            ),
            "panes_agree": entry(False, "The asserted disagreement of AC-22 (as amended 2026-08-23, q4/GA-7). This one is SUPPOSED to differ; a run where the panes agree here is a FAILING run."),
            "flagged": entry(True, "§5 requires the screen to flag the disagreement rather than silently show two numbers."),
        },
    })

    # -- step 12 -------------------------------------------------------------
    steps.append({
        "step": 12,
        "title": 'Still on noun:EdgeCase, filter $.where == "alpha"',
        "pick": {"operation": 3, "source": "noun:EdgeCase", "filter": '$.where == "alpha"'},
        "derivation": (
            "Refused at RUNTIME — layer 2 member (b) — because one row's operand resolves to a "
            "container. §4.6's reading puts this at runtime rather than in the static gate: the "
            "gate cannot know what $.where holds until it looks at a row."
        ),
        "expect": {
            "verdict": entry("refused", "Layer 2 fires on the row whose operand is an object."),
            "refused_by": entry("runtime probe (layer 2, member (b))", "§4.5. The SQL pane shows the probe that fired and no number."),
            "offending_row": entry("edge-02", 'The one seeded EdgeCase row with a `where` key; it holds the object {"code":"alpha","n":7} (B24). §4.5 requires the refusal to name the row.'),
            "sql_pane": entry(None, "No number — the probe fired before the query returned one."),
            "python_pane_rows_kept": entry(
                0,
                "The REPORTED FALLBACK (§4.5): the Python pane still shows Python's answer, labelled "
                "as such. Derived from the seeded rows: exactly one EdgeCase row has a `where` key and "
                "it is an object, and an object is not equal to the string \"alpha\"; the other nine "
                "rows have no `where` at all. So Python keeps 0 of the 10 rows.",
            ),
        },
    })

    # -- step 13 -------------------------------------------------------------
    steps.append({
        "step": 13,
        "title": "Still on noun:EdgeCase, computed column scaled = $.huge * 1",
        "pick": {"operation": 2, "source": "noun:EdgeCase", "alias": "scaled", "expression": "$.huge * 1"},
        "derivation": (
            "Refused at RUNTIME — layer 2 member (a) — naming the out-of-range magnitude. This "
            "is the step that shows WHY refusing beats printing: the second calculator cannot "
            "read this value either — it raises rather than answering — so NEITHER side "
            "produces a number here, and saying that plainly is a truer statement than either "
            "side inventing one."
        ),
        "expect": {
            "verdict": entry("refused", "Layer 2 member (a): the magnitude is out of range."),
            "refused_by": entry("runtime probe (layer 2, member (a))", "§4.5. Layer 2 fires while the query runs, on the row whose magnitude is out of range — unlike step 10, SQL WAS generated here, which is the visible difference between a static refusal and a runtime one."),
            "offending_row": entry("edge-03", "The one seeded EdgeCase row with a `huge` key, whose stored JSON number is 1e400 (B24, written as raw JSON text precisely so it survives into the database exactly)."),
            "sql_pane": entry(None, "No number: the probe fired instead of returning a value. The pane shows the probe, not a blank — a blank would be indistinguishable from a query that returned nothing."),
            "python_pane": entry(
                "raised",
                "No number on this side either — the pane's state is `raised`. Postgres holds a "
                "jsonb number as an exact `numeric` and renders it in FULL POSITIONAL DIGITS, so "
                "`data::text` carries edge-03's `huge` as a bare 401-digit INTEGER literal: no "
                "decimal point, no exponent. JSON's grammar calls a literal with neither of those "
                "an integer, so Python's parser routes it through its integer hook and never its "
                "float hook, and hands back an EXACT arbitrary-precision int. The float conversion "
                "that would have produced inf is therefore never performed — inf never comes into "
                "existence. Multiplying that int by 1 in the float world then has to make a double "
                "of it, and a 401-digit integer has no double: the conversion raises OverflowError, "
                "which the pane reports by name. Derived from jsonb's numeric rendering and JSON's "
                "integer-vs-float grammar, not by running the pane. AC-17 pins the pair: 1e400 "
                "refuses and 1e300 does NOT — the guard must not be a blanket ban on large numbers. "
                "(CORRECTION, 2026-08-22: this entry read `inf` and derived it from the IEEE-754 "
                "double range. That derivation assumed the value reaches Python as a FLOAT literal; "
                "it does not. See the note beside AC-17 in .autodev/specs/T-2.md.)",
            ),
        },
    })

    # -- step 14 -------------------------------------------------------------
    hostile_alias = 'alive"; DROP TABLE demo.records; --'
    steps.append({
        "step": 14,
        "title": "Back on noun:Heartbeat, a computed column whose NAME is a SQL injection",
        "pick": {"operation": 2, "source": "noun:Heartbeat", "alias": hostile_alias, "expression": '$.status == "ok"'},
        "derivation": (
            "R10 demonstrated. The alias is the ONE piece of what you type that has to go into "
            "the SQL text — everything else is a bind parameter — so it is the one place §4.10's "
            "allowlist has to hold."
        ),
        "expect": {
            "hostile_alias": entry(hostile_alias, "The name typed. The expression is irrelevant and valid; it is the NAME that is the attack."),
            "verdict": entry("refused", "§4.10's allowlist refuses it before any SQL exists."),
            "refused_before_sql": entry(True, "Nothing is sent to the database. This is stronger than escaping: the string never reaches SQL text at all."),
            "names_the_name_and_rule": entry(True, "§4.10 requires the refusal to name both the offending name and the rule."),
            "table_survives": entry(
                total_rows,
                f"After the refusal, noun:Heartbeat still returns {total_rows} rows on the next pick — "
                f"the same count as step 2. That is the assertion that the DROP TABLE never ran; a "
                f"refusal message alone would not prove it.",
            ),
            "retyped_alias": entry("alive", "Retyping the name as a plain identifier is accepted."),
            "retyped_emitted_as": entry('AS "alive"', "The SQL pane shows the accepted alias emitted as a quoted identifier."),
        },
    })

    return {
        "$comment": (
            "GENERATED — do not edit by hand. Produced by demo/seed/expectations.py, the third "
            "independent path (T-2-plan.md B8). Every number here is derived from the seed "
            "generator's in-memory rows by arithmetic written out in that file, WITHOUT importing "
            "demo/pyrunner/, demo/builder.py or demo/probes.py — an AST test in "
            "demo/tests/test_walkthrough.py enforces that, and it is the only thing standing "
            "between AC-31 and a tautology. INVENTED DATA: none of these rows describe anything "
            "real. Regenerate with: python -m demo.seed.expectations"
        ),
        "independence": {
            "produced_by": "demo/seed/expectations.py",
            "imports_allowed": ["demo.seed.generate", "the standard library"],
            "imports_forbidden": ["demo.pyrunner", "demo.builder", "demo.probes"],
            "why": (
                "Three producers answer every walkthrough number: the SQL, the Python pane, and "
                "this file. Two of them agreeing is only evidence if the third was written "
                "without reference to either."
            ),
        },
        "corpus": {
            "heartbeat_rows": entry(total_rows, f"{len(senders)} senders x {beats} beats (R5, R17)."),
            "sample_rows": entry(generate.SAMPLES, "generate.SAMPLES — the literal 2,000 of plan §5.3."),
            "edge_case_rows": entry(len(generate.EDGE_CASES), "The ten rows B24 names individually."),
        },
        "steps": steps,
    }


def write(path: Path = _OUT) -> Path:
    """Write demo/expected-answers.json and return where it went."""
    payload = build_answers()
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return path


if __name__ == "__main__":
    written = write()
    print(f"wrote {written} (INVENTED DATA — derived from the seed, no database read)")
