"""T-5 P1 - does GIMS's own CSV import path admit a non-ASCII digit into a number field?

READ-ONLY. Opens no database. Imports the REAL GIMS validator and the REAL
autoSQL expression evaluator, and drives a synthetic in-memory CSV through them.
"""
import csv, io, re, sys, json, importlib.util
from pathlib import Path

GIMS = Path("/home/corgea/Desktop/Coding Projects/GIMS-Project")
AUTOSQL = Path("/home/corgea/Desktop/Coding Projects/autoSQL")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

# The REAL GIMS number validator. core/words/validation.py does absolute
# `from core.words...` imports, so put the GIMS tree on sys.path and import it
# as the package module it is -- this is the same object the API calls.
sys.path.insert(0, str(GIMS))
from core.words.validation import is_number

# The REAL autoSQL Python-side coercion the dashboard uses today.
xpr = load("xpr_expr", AUTOSQL / "demo/vendor/expr.py")
_to_num = xpr._to_num

# xpr.num's string branch, reproduced EXACTLY from demo/vendor/runtime.sql:73-77.
# No database is opened; the two lines that decide the outcome are transcribed verbatim:
#     t := btrim(j #>> '{}', E' \t\n\r\f\v');
#     IF t !~ '^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?$' THEN RETURN NULL;
# Note btrim's set is ASCII whitespace ONLY, and the class is [0-9], not \d.
SQL_BTRIM = " \t\n\r\f\v"
SQL_NUM_RE = re.compile(r"^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?$")

def sql_num(v):
    t = v.strip(SQL_BTRIM)
    if not SQL_NUM_RE.match(t):
        return None
    return float(t)


CASES = [
    ("ASCII control",        "123"),
    ("full-width",           "１２３"),
    ("Arabic-Indic",         "١٢٣"),
    ("Persian",              "۱۲۳"),
    ("Thai",                 "๑๒๓"),
    ("Devanagari",           "१२३"),
    ("full-width decimal",   "１.５"),
    ("Arabic-Indic decimal", "٣.٥"),
    ("NBSP-wrapped ASCII",   " 7 "),
    ("non-numeric text",     "n/a"),
]

print("=" * 78)
print("P1 - the CSV import path, end to end")
print("=" * 78)
print()
print("Step 1: what csv.DictReader produces from a UTF-8 CSV cell")
print("-" * 78)
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["sample_id", "weight"])
for label, v in CASES:
    w.writerow(["S-" + label.replace(" ", "-"), v])
buf.seek(0)
parsed = [dict(r) for r in csv.DictReader(buf)]
cell = parsed[1]["weight"]
print("  cell for 'full-width'      -> %r   type=%s" % (cell, type(cell).__name__))
print("  every cell is a str, verbatim: %s" % all(isinstance(r["weight"], str) for r in parsed))
print()

print("Step 2: does GIMS accept it as a NUMBER field, and what do the two engines do?")
print("-" * 78)
hdr = "%-22s %-14s %-9s %-12s %-12s %s" % (
    "case", "stored value", "GIMS", "Python dash", "compiled SQL", "verdict")
print(hdr)
print("-" * 78)

admitted_and_divergent = []
for label, v in CASES:
    ok = is_number(v)                       # GIMS's real validator
    py = _to_num(v)                         # today's dashboard answer
    sql = sql_num(v)
    if ok and py is not None and sql is None:
        verdict = "*** SILENT WRONG NUMBER ***"
        admitted_and_divergent.append((label, v))
    elif not ok:
        verdict = "rejected at import"
    elif py == sql:
        verdict = "agree"
    else:
        verdict = "differs (other)"
    print("%-22s %-14r %-9s %-12s %-12s %s" % (
        label, v, "ACCEPTS" if ok else "rejects", py, sql, verdict))

print()
print("=" * 78)
print("RESULT: %d of %d cases are admitted by GIMS's own number validator AND" %
      (len(admitted_and_divergent), len(CASES)))
print("        produce a different answer on the compiled-SQL path, silently.")
print("=" * 78)
for label, v in admitted_and_divergent:
    print("  - %-22s %r" % (label, v))
print()
print("The gate that lets them through, verbatim from")
print("GIMS-Project/core/words/validation.py:88-97 :")
print()
import inspect
print(inspect.getsource(is_number))
