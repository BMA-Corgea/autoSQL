"""T-5 P2 - the tier-B denominator T-1 never computed.

READ-ONLY: every database is opened file:...?mode=ro&immutable=1 (the form
T-1 §D.1 used). No Postgres connection is opened at all.

T-1 §D.4 reported "0 non-ASCII digits out of 1,096,202 strings + keys". That
denominator is EVERY string. The decision turns on a much smaller one: strings
a dashboard would actually try to turn into a number (FRAMING §4.2 tier B).
This computes both, per corpus, and never pools them (FRAMING §9 rule 3).
"""
import sqlite3, json, re, sys, unicodedata
from pathlib import Path

ROOT = Path("/home/corgea/Desktop/Coding Projects")
DBS = [
    ("GIMS-Project · LIMS-System",  ROOT / "GIMS-Project/projects/LIMS-System/objects.db"),
    ("GIMS-Project · LIMS archive", ROOT / "GIMS-Project/projects/LIMS-System/archive.db"),
    ("GIMS-Project · DurationDemo", ROOT / "GIMS-Project/projects/DurationDemo/objects.db"),
    ("GIMS-Project · RunlogTest",   ROOT / "GIMS-Project/projects/RunlogTest/objects.db"),
    ("GIMS-Project · Sterility",    ROOT / "GIMS-Project/projects/Sterility/objects.db"),
    ("gims-ledger · guts-ledger",   ROOT / "GUTS/spine/L1-memory/gims-ledger/projects/guts-ledger/objects.db"),
    ("gims-ledger · guts",          ROOT / "GUTS/spine/L1-memory/gims-ledger/projects/guts/objects.db"),
    ("gims-ledger · guts-code",     ROOT / "GUTS/spine/L1-memory/gims-ledger/projects/guts-code/objects.db"),
]

# Python-side coercion gate, verbatim from demo/vendor/expr.py:302
PY_NUM_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
# SQL-side gate, verbatim from demo/vendor/runtime.sql:74  (note [0-9], not \d)
SQL_NUM_RE = re.compile(r"^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?$")
SQL_BTRIM = " \t\n\r\f\v"

def has_nonascii_nd(s):
    return any((not c.isascii()) and unicodedata.category(c) == "Nd" for c in s)

def has_nonascii_space(s):
    return any((not c.isascii()) and c.isspace() for c in s)

def walk(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(k); walk(v, out)
    elif isinstance(o, list):
        for v in o: walk(v, out)
    elif isinstance(o, str):
        out.append(o)

TOT = dict(rows=0, strings=0, tierA=0, tierB=0, coercible=0, nonascii_any=0, ws=0)
print("=" * 100)
print("P2 - tier-A (contains) vs tier-B (coerces), per corpus, never pooled")
print("=" * 100)
print("%-30s %7s %9s %11s %9s %8s %8s" % (
    "corpus", "rows", "strings", "coercible", "non-ASCII", "tierA", "tierB"))
print("-" * 100)

witnesses = []
for label, path in DBS:
    if not path.exists():
        print("%-30s %s" % (label, "(absent)")); continue
    try:
        cx = sqlite3.connect("file:%s?mode=ro&immutable=1" % path, uri=True)
        tabs = [r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    except Exception as e:
        print("%-30s ERROR %s" % (label, e)); continue

    rows = strings = coercible = tierA = tierB = nonascii_any = ws = 0
    for t in tabs:
        cols = [r[1] for r in cx.execute("PRAGMA table_info(\"%s\")" % t).fetchall()]
        if "data" not in cols:
            continue
        for (blob,) in cx.execute("SELECT data FROM \"%s\"" % t):
            rows += 1
            try:
                doc = json.loads(blob)
            except Exception:
                continue
            vals = []
            walk(doc, vals)
            for s in vals:
                strings += 1
                if not s.isascii():
                    nonascii_any += 1
                if has_nonascii_space(s):
                    ws += 1
                # tier B denominator: would the Python dashboard coerce this at all?
                if PY_NUM_RE.match(s.strip()):
                    coercible += 1
                    # tier B: it coerces in Python but the SQL gate rejects it
                    if not SQL_NUM_RE.match(s.strip(SQL_BTRIM)):
                        tierB += 1
                        witnesses.append((label, t, s))
                if has_nonascii_nd(s):
                    tierA += 1
                    if len(witnesses) < 40:
                        witnesses.append((label, t, s))
    cx.close()
    print("%-30s %7d %9d %11d %9d %8d %8d" % (
        label, rows, strings, coercible, nonascii_any, tierA, tierB))
    for k, v in dict(rows=rows, strings=strings, tierA=tierA, tierB=tierB,
                     coercible=coercible, nonascii_any=nonascii_any, ws=ws).items():
        TOT[k] += v

print("-" * 100)
print("%-30s %7d %9d %11d %9d %8d %8d" % (
    "TOTAL (shown, not pooled as a rate)", TOT["rows"], TOT["strings"],
    TOT["coercible"], TOT["nonascii_any"], TOT["tierA"], TOT["tierB"]))
print()
print("=" * 100)
print("THE DENOMINATOR")
print("=" * 100)
print("  T-1 §D.4 published:      0 of 1,096,202  (every string value + object key)")
print("  the decision-relevant :  %d of %s  (strings the dashboard would coerce)" % (
    TOT["tierB"], format(TOT["coercible"], ",")))
if TOT["coercible"]:
    print("  ratio of denominators :  the honest base is %.2f%% the size of the published one" % (
        100.0 * TOT["coercible"] / 1096202))
print()
print("  Unicode-tolerance control (FRAMING §9 rule 1):")
print("    strings carrying ANY non-ASCII character: %s of %s (%.2f%%)" % (
    format(TOT["nonascii_any"], ","), format(TOT["strings"], ","),
    100.0 * TOT["nonascii_any"] / max(TOT["strings"], 1)))
print("    -> a zero below is %s" % (
    "LOAD-BEARING: this corpus does carry non-ASCII, just not digits"
    if TOT["nonascii_any"] else "WORTHLESS: corpus is ASCII-only"))
print()
print("  non-ASCII whitespace anywhere in a string: %d" % TOT["ws"])
print()
if witnesses:
    print("  WITNESSES (%d):" % len(witnesses))
    for w in witnesses[:40]:
        print("    %-30s %-20s %r" % w)
else:
    print("  WITNESSES: none. Tier A = 0 and tier B = 0 on every corpus above.")
