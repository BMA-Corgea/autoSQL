"""T-6 P0 - build the Postgres Nd character class, and verify it exhaustively.

Postgres has no Unicode decimal-digit class: [[:digit:]] matches only ASCII, and
its ctype classes non-ASCII digits as [[:alpha:]]. So the class is written out
from Python's own 670 non-ASCII Nd code points, and then CHECKED against Postgres
rather than trusted.

Usage: python3 P0_nd_class.py [--dsn-container <docker name>]
Writes: nd_class.txt (the class), P0_nd_class.txt (the verification)
"""
import subprocess, sys, unicodedata, io, os

CONTAINER = "autosql-t6-db"
HERE = os.path.dirname(os.path.abspath(__file__))

nd = [cp for cp in range(0x110000)
      if not chr(cp).isascii() and unicodedata.category(chr(cp)) == "Nd"]
ndset = set(nd)

ranges, s, p = [], nd[0], nd[0]
for cp in nd[1:]:
    if cp == p + 1:
        p = cp
        continue
    ranges.append((s, p)); s = cp; p = cp
ranges.append((s, p))

def esc(cp):
    return "\\u%04X" % cp if cp <= 0xFFFF else "\\U%08X" % cp

CLS = "".join(("%s-%s" % (esc(a), esc(b))) if a != b else esc(a) for a, b in ranges)
io.open(os.path.join(HERE, "nd_class.txt"), "w").write(CLS)

# Controls: non-ASCII, NOT Nd. Confusables first, then a strided sample.
ctrl = [0x00A0, 0x2028, 0x2500, 0x26A0, 0x2014, 0x03B4, 0x6F22, 0x00BD, 0x2168, 0x2462]
sample = [cp for cp in range(0x80, 0x30000, 7)
          if cp not in ndset and unicodedata.category(chr(cp)) not in ("Cs", "Cn")]
rows = [(cp, 1) for cp in nd] + [(cp, 0) for cp in ctrl + sample]

sql = ["create temp table ndprobe(cp int, expected int, ch text);",
       "insert into ndprobe(cp,expected,ch) values",
       ",\n".join("(%d,%d,chr(%d))" % (cp, e, cp) for cp, e in rows) + ";",
       "select 'probed', count(*)::text from ndprobe",
       "union all select 'nd_expected', count(*)::text from ndprobe where expected=1",
       "union all select 'false_negatives', count(*)::text from ndprobe "
       "where expected=1 and ch !~ '[" + CLS + "]'",
       "union all select 'false_positives', count(*)::text from ndprobe "
       "where expected=0 and ch ~ '[" + CLS + "]';"]

out = subprocess.run(
    ["docker", "exec", "-i", CONTAINER, "psql", "-U", "glp_owner", "-d", "autosql_spike", "-tA"],
    input="\n".join(sql), capture_output=True, text=True)

report = []
report.append("non-ASCII Nd code points (Python):      %d" % len(nd))
report.append("contiguous ranges emitted:             %d" % len(ranges))
report.append("class length (characters):             %d" % len(CLS))
report.append("")
report.append("Postgres cannot do this natively -- shown, not assumed:")
probe2 = ("select 'digit_class', ('١' ~ '[[:digit:]]')::text "
          "union all select 'alpha_class', ('١' ~ '[[:alpha:]]')::text;")
o2 = subprocess.run(
    ["docker", "exec", "-i", CONTAINER, "psql", "-U", "glp_owner", "-d", "autosql_spike", "-tA"],
    input=probe2, capture_output=True, text=True)
for line in o2.stdout.strip().splitlines():
    report.append("  Arabic-Indic ONE, %s" % line.replace("|", " = "))
report.append("")
report.append("Verification against Postgres:")
for line in out.stdout.strip().splitlines():
    if "|" in line:
        report.append("  %-18s %s" % tuple(line.split("|")[:2]))
if out.returncode != 0:
    report.append("  psql stderr: " + out.stderr.strip()[:400])

text = "\n".join(report)
io.open(os.path.join(HERE, "P0_nd_class.txt"), "w").write(text + "\n")
print(text)
