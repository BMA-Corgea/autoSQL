"""T-1 spike, measurement seat -- THROWAWAY synthetic corpus generator.

Implements the generator rule specified (but deliberately NOT implemented) in
spikes/T-1/recon/baseline.md section 4.2.  Nothing imports this later.

Shape mirrors gims-ledger migrations/pg/0001_instances.sql:13-18 exactly:
    (collection TEXT, key TEXT, data JSONB, PRIMARY KEY (collection, key))
One table per size so a scan of size-N never reads size-M's rows (a single shared
table would make the 1M arm seq-scan 1.156M rows and charge it to the 1M number).
"""
from __future__ import annotations
import csv, io, json, random, sys, datetime

SEED = 1729
BASE_DAY = datetime.date(2026, 8, 19)          # matches CTX_NOW below
CTX_NOW = "2026-08-19T12:00:00Z"               # shape of api/routers/dashboards/routes.py:177
COLLECTION = "noun:Sample"                      # core/storage/factory.collection_for_noun shape

_STATUS_OTHER = ["closed", "hold", "void"]
_WORDS = ["alpha","bravo","charlie","delta","echo","foxtrot","golf","hotel",
          "india","juliet","kilo","lima","mike","november","oscar","papa"]


def make_row(i: int, rnd: random.Random) -> dict:
    # -- the four fixed keys the benchmark widget needs (baseline.md 4.2 rule 1)
    row = {"id": f"S-{i}"}
    row["status"] = "open" if rnd.random() < 0.60 else rnd.choice(_STATUS_OTHER)
    # due_date spread -30..+370 days => "$.days_left < 7" keeps ~9% before the status
    # filter, ~5.5% after it: a real minority, per baseline.md 4.2 rule 1.
    if rnd.random() >= 0.05:                    # 5% omit due_date entirely (SAMPLES' S-4)
        row["due_date"] = (BASE_DAY + datetime.timedelta(days=rnd.randint(-30, 370))).isoformat()
    row["priority"] = rnd.randint(1, 5)
    # -- arbitrary extra keys, 5..15 per row, mixed types (baseline.md 4.2 rule 2)
    for n in range(rnd.randint(5, 15)):
        k = f"field_{n}"
        t = rnd.randint(0, 4)
        if t == 0:
            row[k] = rnd.choice(_WORDS) + "-" + str(rnd.randint(0, 9999))
        elif t == 1:
            row[k] = round(rnd.uniform(-1000, 1000), 4)
        elif t == 2:
            row[k] = bool(rnd.getrandbits(1))
        elif t == 3:
            row[k] = None
        else:
            row[k] = {"code": rnd.choice(_WORDS), "n": rnd.randint(0, 100)}
    return row


def write_csv(n: int, path: str) -> int:
    rnd = random.Random(SEED)                   # rule 3: same seed => same per-row shape
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
