"""T-5 P3 - what is actually STORED in the fields the schema declares as numbers?

READ-ONLY (mode=ro&immutable=1). Confirms first-hand, rather than by quotation,
that number-declared fields hold strings in the real store -- which is what puts
them on the coercion path in the first place.
"""
import sqlite3, json
from pathlib import Path

ROOT = Path("/home/corgea/Desktop/Coding Projects")
NT   = ROOT / "GIMS-Project/projects/LIMS-System/noun_types.json"
DB   = ROOT / "GIMS-Project/projects/LIMS-System/objects.db"

schema = json.load(open(NT))
numfields = {}
for noun, sch in schema.items():
    for fn, fs in (sch.get("fields") or {}).items():
        if isinstance(fs, dict) and fs.get("type") in ("number", "int", "float"):
            numfields.setdefault(noun, []).append((fn, fs.get("required", False)))

cx = sqlite3.connect("file:%s?mode=ro&immutable=1" % DB, uri=True)
tabs = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

print("=" * 92)
print("P3 - number-declared fields, and what is physically stored in them")
print("=" * 92)
print("%-18s %-24s %-9s %-7s %s" % ("noun", "field", "required", "rows", "stored JSON types (count)"))
print("-" * 92)

for t in tabs:
    cols = [r[1] for r in cx.execute('PRAGMA table_info("%s")' % t).fetchall()]
    if "data" not in cols or "collection" not in cols:
        continue
    for (coll, blob) in cx.execute('SELECT collection, data FROM "%s"' % t):
        pass
    break

# collection -> noun is a naming convention; match on the fields present instead.
seen = {}
for t in tabs:
    cols = [r[1] for r in cx.execute('PRAGMA table_info("%s")' % t).fetchall()]
    if "data" not in cols:
        continue
    has_coll = "collection" in cols
    q = 'SELECT %s data FROM "%s"' % ("collection," if has_coll else "'?',", t)
    for row in cx.execute(q):
        coll, blob = row[0], row[-1]
        try:
            doc = json.loads(blob)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for noun, flds in numfields.items():
            for fn, req in flds:
                if fn in doc:
                    key = (noun, fn, req)
                    d = seen.setdefault(key, {"rows": 0, "types": {}, "samples": []})
                    d["rows"] += 1
                    v = doc[fn]
                    tn = "null" if v is None else type(v).__name__
                    d["types"][tn] = d["types"].get(tn, 0) + 1
                    if tn == "str" and len(d["samples"]) < 4:
                        d["samples"].append(v)
cx.close()

if not seen:
    print("(no rows carry any number-declared field)")
for (noun, fn, req), d in sorted(seen.items()):
    types = ", ".join("%s x%d" % (k, v) for k, v in sorted(d["types"].items()))
    print("%-18s %-24s %-9s %-7d %s" % (noun, fn, req, d["rows"], types))
    if d["samples"]:
        print("%-18s %-24s %-9s %-7s samples: %s" % ("", "", "", "", d["samples"]))

print()
print("Declared number-typed fields in the schema, total: %d across %d nouns"
      % (sum(len(v) for v in numfields.values()), len(numfields)))
print("Of those, fields that actually appear on a stored row: %d" % len(seen))
strs = sum(1 for _, d in seen.items() if d["types"].get("str"))
print("Of THOSE, fields physically stored as a STRING on at least one row: %d" % strs)
