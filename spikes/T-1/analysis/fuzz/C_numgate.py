"""T-1 fuzz seat, battery C.

xpr.num's regex gate + btrim  vs  _to_num / _NUM_RE / str.strip (expr.py:302-319).

Python's `re` \\d matches UNICODE decimal digits and float() accepts them;
Python's str.strip() strips UNICODE whitespace.
The SQL uses the ASCII class [0-9] and a 6-character btrim set.
Every non-ASCII probe below is written with \\u escapes so the source stays ASCII.
"""
import sys
sys.path.insert(0, '.')
from differ import run_case

print("=== C. xpr.num gate vs _to_num (expr.py:302-319) ===")
print()

strings = [
    ("12", "ASCII -- control"),
    ("١٢٣", "ARABIC-INDIC digits U+0661.. -- re \\d matches, float() accepts"),
    ("１２３", "FULLWIDTH digits U+FF11.. (common in CJK exports)"),
    ("१२", "DEVANAGARI digits U+0967.."),
    ("߁߂", "NKO digits U+07C1.."),
    (" 12 ", "NBSP U+00A0 padding (survives copy/paste from HTML)"),
    (" 12", "THIN SPACE U+2009"),
    ("　12", "IDEOGRAPHIC SPACE U+3000"),
    ("12", "UNIT SEPARATOR U+001F (str.strip strips it, btrim does not)"),
    ("12", "NEL U+0085"),
    (" 12", "LINE SEPARATOR U+2028"),
    ("1.", "trailing bare dot -- \\d+\\.\\d* matches"),
    ("+.5", "leading plus, bare fraction"),
    ("-.5", ""),
    (".5e3", ""),
    ("1_000", "underscores -- both must reject"),
    ("0x10", "hex -- both must reject"),
    ("inf", "both must reject"),
    ("Infinity", "both must reject"),
    ("nan", "both must reject"),
    ("1e400", "beyond DBL_MAX (KNOWN_DIVERGENCES num_out_of_float8_range)"),
    ("-1e400", ""),
    ("1e-400", "underflows to 0.0 in Python"),
    ("  12  ", "ASCII spaces -- control"),
    ("\t12\n", "ASCII tab/newline -- control"),
    ("1e309", "just past DBL_MAX"),
    ("1.7976931348623158e296", "just over the buggy 297-digit guard"),
]

div = 0
for s, note in strings:
    o = run_case("number($.s)", {"s": s}, None, note=note)
    star = "" if o["verdict"] == "AGREE" else "  <<<"
    print("   %-14s %-28s %s%s" % ("<" + o["verdict"] + ">", ascii(s), note, star))
    if o["verdict"] != "AGREE":
        div += 1
        print("                  py=%s  sql=%s (%s)%s" % (
            o.get('python'), o.get('sql_value'), o.get('sql_typeof'),
            '  RAISED ' + str(o.get('sql_raised')) if o.get('sql_raised') else ''))

print()
print("%d of %d string->number coercions diverge" % (div, len(strings)))
