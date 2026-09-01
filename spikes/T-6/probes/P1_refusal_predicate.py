"""T-6 P1 - does the new refusal fire EXACTLY where Python coerces and SQL cannot?

Framing stop-condition 4: a refusal that fires where Python ALSO refused would
replace an agreement with a refusal. That is a worse outcome than the bug it
fixes, so it is checked before any battery runs, over every shape that can reach
xpr.num's string branch.

Invisible characters are written as escapes, never literally, so this file can be
read and diffed.

Throwaway container only. Never port 55433.
"""
import os, sys, json, io

sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard.expr import _to_num                      # the REAL evaluator
import psycopg2

DSN = os.environ["AUTOSQL_SPIKE_DSN"]
assert "port=55433" not in DSN, "refusing: that is the live database"

CASES = []
def add(s, why): CASES.append((s, why))

for s in ["123", "-4.5", ".5", "5.", "1e3", "1E-3", "+7", "  7  ", "\t7\n"]:
    add(s, "ascii numeric")
for s in ["n/a", "", "abc", "Item 3", "1,234", "1_2", "0x10", "inf", "nan", "1 2"]:
    add(s, "not numeric in either engine")
for s in ["１２３", "١٢٣", "۱۲۳",
          "๑๒๓", "१२३", "１.５",
          "٣.٥", "1２3", "-１２３", "+٣",
          "１２３.", ".５", "۱۲۳e2", "1e３",
          "١٢٣e١٠", "٣e5", "\U0001D7CE\U0001D7CF"]:
    add(s, "non-ascii digits: python coerces")
for s in ["Item ３", "３abc", "abc１２３xyz",
          "１２３ ４５６", "．５", "٣,٥"]:
    add(s, "has non-ascii digit but python REFUSES")
add(" 7 ", "nbsp-wrapped ascii: python coerces")
add(" 7 ", "line/para separator wrapped")
add("　1　", "ideographic space wrapped")
add("\x1c7\x1f", "ascii separators python strips, sql btrim does not")
add(" １２３ ", "nbsp + non-ascii digits")
add("7 8", "internal nbsp: python refuses")
for s in ["1e400", "-1e400", "1e-400", "9" * 320]:
    add(s, "magnitude: XPR01 territory")

cx = psycopg2.connect(DSN)
cx.autocommit = True
rows = []
for s, why in CASES:
    py = _to_num(s)
    sql, code = None, None
    with cx.cursor() as cur:
        try:
            cur.execute("select xpr.num(%s::jsonb)", (json.dumps(s),))
            sql = cur.fetchone()[0]
        except psycopg2.Error as e:
            code = e.pgcode
            cx.rollback()
    rows.append((s, why, py, sql, code))

def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))

bad = []
for s, why, py, sql, code in rows:
    if code == "XPR02":
        if py is None:
            bad.append(("REFUSED WHERE PYTHON ALSO REFUSED", s, py, sql, code))
    elif code is None:
        if sql is None and py is not None:
            bad.append(("SILENT NULL WHERE PYTHON COERCED", s, py, sql, code))
        elif sql is not None and py is not None and not close(sql, py):
            bad.append(("DIFFERENT NUMBER", s, py, sql, code))

def show(s):
    return "".join(c if (c.isprintable() and c.isascii()) else "\\u%04X" % ord(c) for c in s) or "(empty)"

W = max(len(show(s)) for s, *_ in rows) + 2
out = ["P1 - the refusal predicate, case by case", "=" * 118,
       "%-*s %-40s %-13s %-13s %s" % (W, "string", "why it is here", "python", "sql", "outcome"),
       "-" * 118]
for s, why, py, sql, code in rows:
    if code == "XPR02":
        outcome = "REFUSED XPR02" + ("  <- correct, python coerced" if py is not None else "  <- WRONG")
    elif code == "XPR01":
        outcome = "REFUSED XPR01 (magnitude)"
    elif code:
        outcome = "raised %s" % code
    elif sql is None and py is None:
        outcome = "both null - agree"
    elif sql is None:
        outcome = "SILENT NULL  <- WRONG"
    elif py is None:
        outcome = "sql answered, python did not"
    else:
        outcome = "agree" if close(sql, py) else "DIFFER"
    out.append("%-*s %-40s %-13s %-13s %s" % (W, show(s), why, py, sql, outcome))

out += ["-" * 118,
        "cases: %d   refusals XPR02: %d   refusals XPR01: %d" % (
            len(rows),
            sum(1 for r in rows if r[4] == "XPR02"),
            sum(1 for r in rows if r[4] == "XPR01")),
        ""]
if bad:
    out.append("CONTRACT VIOLATIONS: %d" % len(bad))
    for b in bad:
        out.append("  %s: %s py=%r sql=%r code=%s" % (b[0], show(b[1]), b[2], b[3], b[4]))
else:
    out += ["CONTRACT HOLDS on every case:",
            "  - no refusal fires where Python also refused (stop-condition 4)",
            "  - no silent NULL remains where Python coerced",
            "  - every mutually-answered case agrees within the 1e-9 epsilon"]

text = "\n".join(out)
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "P1_refusal_predicate.txt"),
        "w", encoding="utf-8").write(text + "\n")
print(text)
sys.exit(1 if bad else 0)
