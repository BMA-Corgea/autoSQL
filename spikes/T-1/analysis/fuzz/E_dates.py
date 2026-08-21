"""T-1 fuzz seat, battery E.

xpr.pdate_ms / xpr.pdate_only / xpr.fmt_date_ms
   vs  _parse_date_ms (expr.py:409-431) / _format_date_ms (expr.py:434-445).

Attack surface: the regex subset, UTC offsets, leap years, year 1 / year 9999
boundaries, fractional microseconds, and the rounding mode used to get from
float milliseconds back to a calendar.
"""
import sys
sys.path.insert(0, '.')
from differ import run_case

print("=== E. date parsing / formatting ===")
print()

# (expr, record, note)
CASES = [
    # --- the regex subset -------------------------------------------------
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01"}, "control"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00"}, "hh:mm only"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01 00:00:00"}, "space separator"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00.123456"}, "6-digit fraction"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00.1"}, "1-digit fraction"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00.1234567"}, "7 digits -> both must reject"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00Z"}, "Z"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00+05:30"}, "offset with colon"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00-0800"}, "offset without colon"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T00:00:00+99:99"}, "absurd but regex-legal offset"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-02-29"}, "leap day, leap year"),
    ('days_between($.d, "2024-01-02")', {"d": "2023-02-29"}, "leap day, non-leap -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "1900-02-29"}, "1900 is NOT a leap year"),
    ('days_between($.d, "2024-01-02")', {"d": "2000-02-29"}, "2000 IS a leap year"),
    ('days_between($.d, "2024-01-02")', {"d": "0000-01-01"}, "year 0 -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "0001-01-01"}, "year 1, the Python minimum"),
    ('days_between($.d, "2024-01-02")', {"d": "9999-12-31"}, "year 9999, the Python maximum"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-13-01"}, "month 13 -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-32"}, "day 32 -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T24:00:00"}, "hour 24 -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01T23:59:60"}, "leap second -> both NULL"),
    ('days_between($.d, "2024-01-02")', {"d": "  2024-01-01  "}, "ASCII padding"),
    ('days_between($.d, "2024-01-02")', {"d": " 2024-01-01"}, "NBSP U+00A0 padding"),
    ('days_between($.d, "2024-01-02")', {"d": "٢٠٢٤-٠١-٠١"}, "ARABIC-INDIC digits in a date"),
    ('days_between($.d, "2024-01-02")', {"d": "2024-01-01\n"}, "trailing newline (Python $ vs PG $)"),

    # --- Python's own OverflowError: the offset is applied to the datetime,
    #     and that arithmetic is OUTSIDE the try/except (expr.py:418-431) -----
    ('days_between($.d, "2024-01-02")', {"d": "0001-01-01T00:00:00+14:00"},
     "year 1 pushed BELOW datetime.min by the offset"),
    ('days_between($.d, "2024-01-02")', {"d": "9999-12-31T23:59:59-14:00"},
     "year 9999 pushed ABOVE datetime.max by the offset"),
    ('days_between($.d, "2024-01-02")', {"d": "0001-01-01T00:00:00+00:01"},
     "one minute past the minimum"),
    ('$.d == "x" or days_between($.d, "2024-01-02") > 0', {"d": "0001-01-01T00:00:00+14:00"},
     "same, inside a boolean the dashboard would actually write"),

    # --- date_add / format ------------------------------------------------
    ('date_add($.d, 1)', {"d": "2024-02-28"}, "date_only output"),
    ('date_add($.d, 1)', {"d": "2024-02-28T12:00:00Z"}, "datetime output"),
    ('date_add($.d, 0.5)', {"d": "2024-02-28"}, "half day on a date-only base"),
    ('date_add($.d, -0.5)', {"d": "2024-02-28"}, "negative half day"),
    ('date_add($.d, 1e9)', {"d": "2024-01-01"}, "shift far past year 9999 -> both NULL"),
    ('date_add($.d, -1e9)', {"d": "2024-01-01"}, "shift far below year 1 -> both NULL"),
    ('date_add("0001-01-01", $.n)', {"n": -1.15740740740741e-11},
     "one microsecond BELOW datetime.min"),
    ('date_add("9999-12-31T23:59:59Z", $.n)', {"n": 1.15740740740741e-11},
     "one microsecond ABOVE datetime.max"),
    ('date_add($.d, $.n)', {"d": "1970-01-01T00:00:00Z", "n": 5.78703703703704e-12},
     "+0.5 microsecond: PG numeric round() is half-AWAY, Python is half-EVEN"),
    ('date_add($.d, $.n)', {"d": "1970-01-01T00:00:00Z", "n": 1.73611111111111e-11},
     "+1.5 microseconds: half-even rounds DOWN to 1, half-away rounds UP to 2"),
    ('date_add($.d, $.n)', {"d": "1969-12-31T23:59:59Z", "n": 1.15740740740741e-11},
     "negative epoch side"),

    # --- days_between precision -------------------------------------------
    ('days_between("0001-01-01", $.d)', {"d": "9999-12-31"}, "full calendar span"),
    ('days_between($.a, $.b)', {"a": "2024-01-01T00:00:00.000001", "b": "2024-01-01T00:00:00.000002"},
     "one microsecond apart at a large epoch"),
    ('days_between($.a, $.b)', {"a": "0001-01-01T00:00:00.000001", "b": "0001-01-01T00:00:00.000002"},
     "one microsecond apart at the far negative epoch"),
    ('now()', {}, "wall clock, no ctx -- expr uses per-record, SQL uses per-query"),
    ('today()', {}, "wall clock, no ctx"),
]

div = 0
for src, rec, note in CASES:
    o = run_case(src, rec, None, note=note)
    star = "" if o["verdict"] == "AGREE" else "  <<<"
    print("   %-14s %-46s %-34s %s%s" % (
        "<" + o["verdict"] + ">", src, ascii(rec), note, star))
    if o["verdict"] != "AGREE":
        div += 1
        print("                  py=%s%s" % (
            o.get('python'),
            '  RAISED ' + str(o.get('python_raised')) if o.get('python_raised') else ''))
        print("                  sql=%s (%s)%s" % (
            o.get('sql_value'), o.get('sql_typeof'),
            '  RAISED ' + str(o.get('sql_raised')) if o.get('sql_raised') else ''))

print()
print("%d of %d date probes diverge" % (div, len(CASES)))
