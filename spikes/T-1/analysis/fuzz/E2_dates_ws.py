"""T-1 fuzz seat, battery E2 -- the whitespace/digit gate on DATE strings specifically.

_parse_date_ms does `_DATE_RE.match(v.strip())` (expr.py:415): Python's str.strip()
strips UNICODE whitespace and Python's re \\d matches UNICODE digits.
xpr.pdate_ms does btrim over 6 ASCII characters and a [0-9]-equivalent \\d.
All probes are built from \\u escapes so this source file stays pure ASCII.
"""
import sys
sys.path.insert(0, '.')
from differ import run_case

WS = {
    "U+0020 SPACE": " ",
    "U+00A0 NBSP": " ",
    "U+0085 NEL": "",
    "U+001C FILE SEP": "",
    "U+001F UNIT SEP": "",
    "U+2000 EN QUAD": " ",
    "U+2009 THIN SPACE": " ",
    "U+2028 LINE SEP": " ",
    "U+2029 PARA SEP": " ",
    "U+3000 IDEOGRAPHIC SPACE": "　",
    "U+000B VTAB": "",
    "U+000C FF": "",
}

print("=== E2. date-string trimming: str.strip() vs btrim(E' \\t\\n\\r\\f\\v') ===")
print("    expr.py:415 vs runtime.sql:273")
print()
div = 0
for name, ch in WS.items():
    rec = {"d": ch + "2024-01-01" + ch}
    o = run_case('days_between($.d, "2024-01-02")', rec, None)
    pystrip = repr((ch + "2024-01-01" + ch).strip())
    flag = "" if o["verdict"] == "AGREE" else "   <<< DIVERGES"
    print("   %-14s %-28s python str.strip -> %-16s py=%s sql=%s%s" % (
        "<" + o["verdict"] + ">", name, ascii(pystrip),
        o.get("python"), o.get("sql_value"), flag))
    if o["verdict"] != "AGREE":
        div += 1

print()
print("=== E2b. UNICODE DIGITS inside a date, and inside number() ===")
DIGITS = {
    "ASCII 0-9": "0123456789",
    "U+0660 ARABIC-INDIC": "٠١٢٣٤٥٦٧٨٩",
    "U+06F0 EXT ARABIC-INDIC": "۰۱۲۳۴۵۶۷۸۹",
    "U+0966 DEVANAGARI": "०१२३४५६७८९",
    "U+FF10 FULLWIDTH": "０１２３４５６７８９",
    "U+1D7CE MATH BOLD": "".join(chr(0x1D7CE + i) for i in range(10)),
    "U+104A0 OSMANYA": "".join(chr(0x104A0 + i) for i in range(10)),
}
for name, tab in DIGITS.items():
    def x(s):
        return "".join(tab[int(c)] if c.isdigit() else c for c in s)
    d = x("2024-01-01")
    o1 = run_case('days_between($.d, "2024-01-02")', {"d": d}, None)
    o2 = run_case('number($.s)', {"s": x("123")}, None)
    f1 = "" if o1["verdict"] == "AGREE" else " <<<"
    f2 = "" if o2["verdict"] == "AGREE" else " <<<"
    print("   %-26s date:%-12s py=%-6s sql=%-6s%s | number(): %-12s py=%-7s sql=%-6s%s" % (
        name, "<" + o1["verdict"] + ">", o1.get("python"), o1.get("sql_value"), f1,
        "<" + o2["verdict"] + ">", o2.get("python"), o2.get("sql_value"), f2))
    if o1["verdict"] != "AGREE":
        div += 1
    if o2["verdict"] != "AGREE":
        div += 1

print()
print("%d divergences in E2" % div)
