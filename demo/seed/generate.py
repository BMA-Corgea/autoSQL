"""INVENTED DATA — every row this module produces is fabricated.

This is the deterministic generator for the demo's three collections
(T-2-plan.md §5; spec §8.3/§8.4). None of it is real: no sender exists, no
sample was measured, nothing here was ever observed anywhere. The data is
invented so the demo can show its SQL against rows whose right answers are
known by construction (AC-11, B31 third place).

Determinism (plan §5.5, B27):
  * Every constant below is a literal — the span (R17), the seed material
    (B27), the vocabulary, the distributions. Nothing reads the clock; a
    grep test in demo/tests/test_data.py holds this module to that.
  * Randomness comes only from per-entity `random.Random` streams seeded by
    an explicit sha256 of a literal string, so the output is stable across
    Python versions by construction and independent of loop order — running
    the generator twice produces byte-identical rows (AC-10).

The three collections (plan §5.1–§5.4):
  * noun:Heartbeat — 8,400 rows: 50 senders × 168 hourly beats (R5, R16,
    R17, R19, B27).
  * noun:Sample    — 2,000 rows: the record rule of
    spikes/T-1/proto/gen_data.py:25-46, verbatim in behaviour, with R19's
    key format and B26's id-matches-key correction.
  * noun:EdgeCase  — 10 rows, all named at B24, written as raw JSON text so
    values no Python float can hold (1e400) survive exactly (AC-13).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import random
from typing import Iterator, Tuple

Row = Tuple[str, str, str]  # (collection, key, data) — data is JSON text

# ---------------------------------------------------------------------------
# Shared constants — all literal, none from the clock.
# ---------------------------------------------------------------------------

# B27's seed material, written out as an explicit hash so it is stable across
# Python versions by construction rather than by documentation.
_SEED_NAMESPACE = "T-2"


def _stream(entity: str) -> random.Random:
    """The per-entity RNG stream B27 pins: sha256(f"T-2:{entity}")[:8]."""
    material = f"{_SEED_NAMESPACE}:{entity}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


# The fixed 16-word vocabulary (plan §5.2; the exact words are the builder's
# per §10.1, and these are the spike's own sixteen, kept for continuity).
WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
]

# ---------------------------------------------------------------------------
# noun:Heartbeat — 8,400 rows (plan §5.2, B27).
# ---------------------------------------------------------------------------

SENDERS = 50          # Q22 — hb-01 … hb-50
BEATS = 168           # R17 — 7 whole UTC days × 24 hourly beats
CHANGE_PROBABILITY = 0.10  # B27 — the coin AC-8 and AC-40 both measure

# R17: the span is the seven whole UTC days 2026-08-14T00:00:00Z through
# 2026-08-20T23:00:00Z, a literal constant, never derived from the clock.
# Beat b sits at 00:00Z of Aug 14 plus b hours; the whole span stays inside
# August 2026, so the timestamp is pure integer arithmetic on day and hour.
_SPAN_YEAR_MONTH = "2026-08"
_SPAN_FIRST_DAY = 14


def _beat_ts(b: int) -> str:
    """Fixed-width UTC ISO-8601 for beat b (0…167), per R17."""
    return f"{_SPAN_YEAR_MONTH}-{_SPAN_FIRST_DAY + b // 24:02d}T{b % 24:02d}:00:00Z"


def _draw_status(rng: random.Random) -> str:
    """R16's closed set, about 90 / 8 / 2."""
    r = rng.random()
    if r < 0.90:
        return "ok"
    if r < 0.98:
        return "warn"
    return "error"


def _draw_state(rng: random.Random) -> tuple:
    """One fresh (status, load, note) draw — B27's beat-0 rule."""
    return (_draw_status(rng), rng.randint(0, 100), rng.choice(WORDS))


def heartbeat_rows() -> Iterator[Row]:
    """50 senders × 168 beats. Per-sender independent streams (B27)."""
    for s in range(1, SENDERS + 1):
        sender_id = f"hb-{s:02d}"
        rng = _stream(sender_id)
        state = _draw_state(rng)  # beat 0
        for b in range(BEATS):
            if b > 0:
                if rng.random() < CHANGE_PROBABILITY:
                    # Redraw until the pair actually differs — B27 calls this
                    # clause load-bearing: a "change" that redraws the same
                    # values would silently drift AC-40's kept-row count.
                    new_state = _draw_state(rng)
                    while new_state == state:
                        new_state = _draw_state(rng)
                    state = new_state
                # else: carry (status, payload) forward unchanged; ts is
                # never part of the change decision and advances regardless.
            status, load, note = state
            data = json.dumps(
                {
                    "sender_id": sender_id,
                    "ts": _beat_ts(b),
                    "status": status,
                    "payload": {"load": load, "note": note},
                },
                separators=(",", ":"),
            )
            yield ("noun:Heartbeat", f"{sender_id}-{b:04d}", data)


# ---------------------------------------------------------------------------
# noun:Sample — 2,000 rows (plan §5.3, B26).
#
# The record rule of spikes/T-1/proto/gen_data.py:25-46, verbatim in
# behaviour: same fields, same distributions, same draw order. Two ruled
# departures: R19's zero-padded key format replaces the spike's unpadded
# `S-{i}`, and B26 makes the in-record `id` hold the same string as the key.
# ---------------------------------------------------------------------------

SAMPLES = 2000
_STATUS_OTHER = ["closed", "hold", "void"]
# The spike's BASE_DAY (gen_data.py:15) — a literal constant matching its
# CTX_NOW, kept verbatim; not the clock. Held as an ordinal and advanced by
# integer addition so demo/seed/ satisfies plan §5.5's grep exactly as
# written (the word "timedelta" carries §5.5's third forbidden string as a
# bare substring).
_SAMPLE_BASE_ORDINAL = datetime.date(2026, 8, 19).toordinal()


def _sample_row(key: str, rnd: random.Random) -> dict:
    """gen_data.py's make_row, with B26's id correction."""
    row = {"id": key}  # B26 — one identifier per row, not two
    row["status"] = "open" if rnd.random() < 0.60 else rnd.choice(_STATUS_OTHER)
    if rnd.random() >= 0.05:  # 5% of rows omit due_date entirely
        d = datetime.date.fromordinal(_SAMPLE_BASE_ORDINAL + rnd.randint(-30, 370))
        row["due_date"] = d.isoformat()
    row["priority"] = rnd.randint(1, 5)
    for n in range(rnd.randint(5, 15)):  # 5–15 extra keys, field_0 … field_14
        k = f"field_{n}"
        t = rnd.randint(0, 4)
        if t == 0:
            row[k] = rnd.choice(WORDS) + "-" + str(rnd.randint(0, 9999))
        elif t == 1:
            row[k] = round(rnd.uniform(-1000, 1000), 4)
        elif t == 2:
            row[k] = bool(rnd.getrandbits(1))
        elif t == 3:
            row[k] = None  # a present JSON null — one of §7.4's two nulls
        else:
            row[k] = {"code": rnd.choice(WORDS), "n": rnd.randint(0, 100)}
    return row


def sample_rows() -> Iterator[Row]:
    """2,000 rows, keys smp-0000 … smp-1999 (R19), per-row streams."""
    for i in range(SAMPLES):
        key = f"smp-{i:04d}"
        yield ("noun:Sample", key, json.dumps(_sample_row(key, _stream(key)), separators=(",", ":")))


# ---------------------------------------------------------------------------
# noun:EdgeCase — 10 rows, every one named at B24 (plan §5.4, R11).
#
# Written as raw JSON text, not through json.dumps: edge-03's 1e400 exceeds
# every Python float, and edge-04/edge-05's boundary digits must land in the
# database exactly as B24 spells them (Postgres stores jsonb numbers as
# numeric, which holds all of these exactly). Two constraints B24 pins:
# no row here carries a `status` key (AC-45(a) needs `status` acceptable as
# an alias on this collection), and every row carries a `label` stating its
# purpose in plain words (R11 renders it on screen).
# ---------------------------------------------------------------------------

# 2026-08-23, q4/GA-7 (the dated notes beside B24 in T-2-plan.md and AC-13/
# AC-17/AC-22 in T-2.md): the demo adopted T-3's corrected runtime.sql. Its
# range guard moved from 297 digits (~1.8e296) to the full 309-digit DBL_MAX,
# and past it the runtime now RAISES the named XPR01 refusal instead of
# returning NULL. Three rows moved with it:
#   edge-00  1e300 is now read identically by both engines (the old guard
#            silently nulled it); it stays as the below-the-limit control,
#            and its SQUARE is the float8-overflow (22003) witness.
#   edge-01  keeps l=[1e300,1] (AC-13 witness 2, unchanged) and gains
#            m=["１２３",1] — the Unicode-digit string T-3 measured as the
#            surviving silent divergence: Python's float() reads any Unicode
#            digit (123.0) where the SQL runtime's ASCII-only regex reads
#            NULL. Walkthrough step 11's shown disagreement now rides m.
#            T-6 will convert this gap to a named refusal, at which point
#            this row moves again (the owner was told; he chose adopt).
#   edge-04/edge-05 straddle the CORRECTED guard: just below DBL_MAX is a
#            number; just above is the raised XPR01, no longer a NULL.
EDGE_CASES = [
    ("edge-00",
     '{"label":"edge case: 1e300 is a real double and both engines now read it identically (the pre-fix guard silently nulled it); its square overflows the fast number type, which SQL refuses by name","a":1e300}'),
    ("edge-01",
     '{"label":"edge case: max of [\\"１２３\\", 1] — SQL answers 1, Python answers 123; the demo\'s asserted wrong number (the Unicode-digit gap)","l":[1e300,1],"m":["１２３",1]}'),
    ("edge-02",
     '{"label":"edge case: one key holds an object and one holds an array — an == on either is refused before the query runs","where":{"code":"alpha","n":7},"tags":["a","b"]}'),
    ("edge-03",
     '{"label":"edge case: 1e400 is larger than any double — stored as a JSON number, and refused before its query runs","huge":1e400}'),
    ("edge-04",
     '{"label":"edge case: just below the corrected 309-digit guard (DBL_MAX) — SQL still returns a number for this value","g":1.7976931348623156e+308}'),
    ("edge-05",
     '{"label":"edge case: just above the corrected 309-digit guard — SQL raises the named XPR01 refusal for this value (never a NULL)","g":1.7976931348623158e+308}'),
    ("edge-06",
     '{"label":"edge case: division by zero — both panes must agree on NULL; a control that must not fire","z":0,"d":7}'),
    ("edge-07",
     '{"label":"edge case: the string \'12.5\' converts to a number and \'not a number\' does not; neither raises","s":"12.5","t":"not a number"}'),
    ("edge-08",
     '{"label":"edge case: a present JSON null beside a key absent from every other row — the two kinds of null","n":null,"present":1}'),
    ("edge-09",
     '{"label":"edge case: an empty array, an empty object and an empty string — the truthiness edges","arr":[],"obj":{},"txt":""}'),
]


def edge_case_rows() -> Iterator[Row]:
    for key, data in EDGE_CASES:
        yield ("noun:EdgeCase", key, data)


# ---------------------------------------------------------------------------
# The whole corpus, in (collection, key) order — the digest's order (AC-10).
# ---------------------------------------------------------------------------

def rows() -> Iterator[Row]:
    """All 10,410 rows, emitted in (collection, key) text order."""
    yield from edge_case_rows()   # noun:EdgeCase
    yield from heartbeat_rows()   # noun:Heartbeat
    yield from sample_rows()      # noun:Sample


def corpus_sha256() -> str:
    """A digest over the generated stream itself (not the database) — what
    lets a test prove two in-process runs are byte-identical (AC-10's
    generator half) without a second checkout."""
    h = hashlib.sha256()
    for collection, key, data in rows():
        h.update(collection.encode())
        h.update(b"\x1f")
        h.update(key.encode())
        h.update(b"\x1f")
        h.update(data.encode())
        h.update(b"\n")
    return h.hexdigest()
