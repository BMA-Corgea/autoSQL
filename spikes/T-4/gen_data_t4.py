"""T-4 timing run -- the EXTENDED corpus generator.

Run 2 (T-4) needs two fields the T-1 corpus does not carry, because its widget is
built around coalesce() over a frequently-missing key:

    queue_depth    always present, randint(0, 200)
    retest_count   present ~15% of the time, randint(0, 3)

REGENERATE-CORPUS.md section 7 gives that patch and notes Q7 permits editing
gen_data.py in place.  This file does NOT do that, deliberately:

  * Everything under spikes/ is FROZEN EVIDENCE (kb/CURRENT-WORK.md).  gen_data.py
    is the artifact the existing sweep's numbers were produced by.
  * Section 7 consequence 1 requires the new baseline be recorded "next to the old
    one rather than replacing it -- the old corpus is what the existing sweep's
    numbers refer to."  Editing in place would leave the OLD corpus unbuildable
    from this tree and break the cold-rebuild reproducibility the T-1 handoff
    claims.

So the frozen generator stays byte-identical and this module extends it.

THE RANDOM STREAM IS IDENTICAL TO SECTION 7's PATCH.  The patch appends its two
draws at the end of make_row(), immediately before `return row`.  Calling the
frozen make_row() and then drawing here puts those draws at exactly the same
point in the stream, and appends the keys in the same order -- so this produces
the same rows, byte for byte, as the documented in-place edit would have.
Verified against section 7's own measured figures: 5.31% selectivity and
303.2 mean stored JSON bytes per row at N=100,000.
"""
from __future__ import annotations
import csv, json, random, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "T-1", "proto"))
from gen_data import make_row as _frozen_make_row, SEED, COLLECTION   # noqa: E402


def make_row(i: int, rnd: random.Random) -> dict:
    row = _frozen_make_row(i, rnd)
    row["queue_depth"] = rnd.randint(0, 200)
    if rnd.random() < 0.15:
        row["retest_count"] = rnd.randint(0, 3)   # absent 85% of the time -- what coalesce is for
    return row


def write_csv(n: int, path: str) -> int:
    rnd = random.Random(SEED)                     # rule 3: same seed => same per-row shape
    total = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        for i in range(n):
            d = json.dumps(make_row(i, rnd), separators=(",", ":"))
            total += len(d)
            w.writerow([COLLECTION, f"S-{i}", d])
    return total


if __name__ == "__main__":
    n = int(sys.argv[1]); path = sys.argv[2]
    b = write_csv(n, path)
    print(json.dumps({"rows": n, "json_bytes": b, "avg_json_bytes": round(b / n, 1)}))
