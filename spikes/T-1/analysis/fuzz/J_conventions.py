"""T-1 fuzz seat, battery J -- the convention corners.

truthy / ord / contains / length / count / sum / avg / min / max,
especially the empty and all-null conventions, container equality, and the
places where the two runtimes could quietly pick different rules.
"""
import sys

sys.path.insert(0, '.')
from differ import run_case

CASES = [
    # ---- count vs sum/avg/min/max on empty and all-null -------------------
    ('count($.l)', {"l": []}, "count of empty list -> 0.0, NOT null"),
    ('sum($.l)', {"l": []}, "sum of empty list -> null"),
    ('avg($.l)', {"l": []}, "avg of empty list -> null"),
    ('min($.l)', {"l": []}, "min of empty"),
    ('max($.l)', {"l": []}, "max of empty"),
    ('count($.l)', {"l": [None, None]}, "count of all-null list"),
    ('sum($.l)', {"l": [None, None]}, "sum of all-null list"),
    ('count($.missing)', {}, "count of a missing field"),
    ('sum($.missing)', {}, "sum of a missing field"),
    ('count()', {}, "count with NO arguments"),
    ('sum()', {}, "sum with no arguments"),
    ('count($.a, $.b)', {"a": None, "b": 1}, "count, two scalar args"),
    ('sum($.a, $.b)', {"a": "3", "b": True}, "sum coerces strings and bools"),
    ('avg($.l)', {"l": ["1", True, None, "x", 3]}, "avg over a mixed list"),
    ('sum($.l)', {"l": [{"x": 1}, [1], "2"]}, "sum over containers + a numeric string"),
    ('count($.l)', {"l": [{"x": 1}, [1], "2"]}, "count over the same"),
    ('count($.o)', {"o": {"a": 1, "b": 2}}, "count of a DICT arg (not unwrapped by _as_list)"),
    ('sum($.o)', {"o": {"a": 1, "b": 2}}, "sum of a dict arg"),
    ('min($.l)', {"l": [3, "2", True]}, "min mixes number/string/bool through _to_num"),
    ('sum($.l)', {"l": [0.1, 0.2, 0.3]}, "float summation ORDER matters"),
    ('sum($.l)', {"l": [1e16, 1.0, -1e16]}, "catastrophic-cancellation order test"),
    ('sum($.l)', {"l": [-0.0]}, "sum of a single negative zero"),
    ('sum($.l)', {"l": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}, "control"),

    # ---- truthy ----------------------------------------------------------
    ('if($.v, "T", "F")', {"v": 0}, "0 is falsy"),
    ('if($.v, "T", "F")', {"v": -0.0}, "-0.0 is falsy"),
    ('if($.v, "T", "F")', {"v": ""}, "empty string"),
    ('if($.v, "T", "F")', {"v": " "}, "one space"),
    ('if($.v, "T", "F")', {"v": []}, "empty list"),
    ('if($.v, "T", "F")', {"v": {}}, "empty dict"),
    ('if($.v, "T", "F")', {"v": [None]}, "list containing one null"),
    ('if($.v, "T", "F")', {"v": {"a": None}}, "dict with a null value"),
    ('if($.v, "T", "F")', {"v": None}, "explicit null"),
    ('if($.v, "T", "F")', {}, "missing field"),
    ('if($.v, "T", "F")', {"v": False}, "false"),
    ('if($.v, "T", "F")', {"v": "0"}, 'the STRING "0" is truthy'),
    ('if($.v, "T", "F")', {"v": "false"}, 'the STRING "false" is truthy'),

    # ---- ord (three-valued, type-homogeneous) ----------------------------
    ('$.a < $.b', {"a": True, "b": False}, "bool operands -> null, NOT a coercion"),
    ('$.a < $.b', {"a": True, "b": 2}, "bool vs number -> null"),
    ('$.a < $.b', {"a": 1, "b": "2"}, "number vs string -> null"),
    ('$.a < $.b', {"a": [1], "b": [2]}, "list vs list -> null"),
    ('$.a < $.b', {"a": None, "b": 1}, "null operand -> null"),
    ('$.a <= $.a', {"a": "x"}, "string self-comparison"),
    ('$.a < $.b', {"a": "Z", "b": "a"}, "ASCII case ordering"),
    ('$.a < $.b', {"a": "é", "b": "z"}, "non-ASCII ordering (codepoint vs C collation)"),

    # ---- eq / contains ---------------------------------------------------
    ('$.a == $.b', {"a": True, "b": 1}, "bool vs 1 must be FALSE (test_dashboard_expr.py:37)"),
    ('$.a == $.b', {"a": 1, "b": 1.0}, "int vs float must be TRUE"),
    ('$.a == $.b', {"a": {"x": 1, "y": 2}, "b": {"y": 2, "x": 1}}, "dict key ORDER is irrelevant"),
    ('$.a == $.b', {"a": [1, 2], "b": [1, 2]}, "list equality"),
    ('$.a == $.b', {"a": [1, 2], "b": [1.0, 2.0]}, "list of int vs list of float"),
    ('$.a == $.b', {"a": [True], "b": [1]}, "list of bool vs list of number"),
    ('$.a == $.b', {"a": None, "b": None}, "null == null is TRUE"),
    ('$.a == null', {"a": None}, "explicit null literal"),
    ('$.a == null', {}, "missing field == null"),
    ('contains($.l, $.n)', {"l": [1, 2, 3], "n": 2}, "array membership"),
    ('contains($.l, $.n)', {"l": [1, 2, 3], "n": 2.0}, "array membership, float needle"),
    ('contains($.l, $.n)', {"l": [True], "n": 1}, "bool element vs number needle -> FALSE"),
    ('contains($.l, $.n)', {"l": [None], "n": None}, "null element, null needle"),
    ('contains($.l, $.n)', {"l": [[1]], "n": [1]}, "nested list needle"),
    ('contains($.l, $.n)', {"l": [{"a": 1}], "n": {"a": 1}}, "dict needle"),
    ('contains($.s, $.n)', {"s": "abc", "n": ""}, "empty needle in a string"),
    ('contains($.s, $.n)', {"s": "", "n": ""}, "empty needle in an empty string"),
    ('contains($.s, $.n)', {"s": "abc", "n": None}, "null needle -> FALSE"),
    ('contains($.s, $.n)', {"s": None, "n": "a"}, "null haystack -> FALSE (not null!)"),
    ('contains($.s, $.n)', {"s": 12345, "n": 234}, "number haystack coerced to text"),
    ('contains($.o, $.n)', {"o": {"a": 1}, "n": "a"}, "dict haystack -> _to_str is None -> FALSE"),

    # ---- length ----------------------------------------------------------
    ('length($.v)', {"v": "abc"}, "string length"),
    ('length($.v)', {"v": ""}, "empty string"),
    ('length($.v)', {"v": []}, "empty list"),
    ('length($.v)', {"v": {}}, "empty dict"),
    ('length($.v)', {"v": {"a": 1, "b": 2}}, "dict length = key count"),
    ('length($.v)', {"v": 12345}, "number -> null"),
    ('length($.v)', {"v": True}, "bool -> null"),
    ('length($.v)', {"v": None}, "null -> null"),
    ('length($.v)', {"v": "é"}, "combining accent: 2 code points"),
    ('length($.v)', {"v": "\U0001F600"}, "astral emoji: 1 code point in Python"),
    ('length($.v)', {"v": "\U0001F1E6\U0001F1E7"}, "flag sequence: 2 code points"),

    # ---- concat / string -------------------------------------------------
    ('concat($.a, $.b)', {"a": None, "b": "x"}, "null argument becomes '' in concat"),
    ('concat($.a, $.b)', {"a": [1], "b": "x"}, "list argument becomes ''"),
    ('concat()', {}, "concat with no args -> ''"),
    ('string($.v)', {"v": True}, "bool -> 'true'"),
    ('string($.v)', {"v": [1]}, "list -> null"),
    ('string($.v)', {"v": 1e21}, "ECMA switches to exponent at 1e21"),
    ('string($.v)', {"v": 1e20}, "1e20 stays positional"),
    ('string($.v)', {"v": 1e-6}, "1e-6 stays positional"),
    ('string($.v)', {"v": 1e-7}, "1e-7 switches to exponent"),
    ('string($.v)', {"v": -0.0}, "negative zero -> '0'"),

    # ---- field paths -----------------------------------------------------
    ('$.a[0]', {"a": "abc"}, "index into a STRING -> null (not 'a')"),
    ('$.a[0]', {"a": 5}, "index into a scalar -> null"),
    ('$.a[-1]', {"a": [1, 2, 3]}, "negative index"),
    ('$.a[-4]', {"a": [1, 2, 3]}, "out-of-range negative index"),
    ('$.a[3]', {"a": [1, 2, 3]}, "out-of-range positive index"),
    ('$.a.b', {"a": [1, 2]}, "key into a list -> null"),
    ('$.a.b', {"a": "x"}, "key into a string -> null"),
    ('$["a b"]', {"a b": 7}, "quoted key with a space"),
    ('$.a', {"a": None}, "JSON null vs absent are indistinguishable"),
]

div = 0
for src, rec, note in CASES:
    o = run_case(src, rec, None, note=note)
    ok = o["verdict"] == "AGREE"
    if not ok:
        div += 1
    print("   %-13s %-24s %-40s %s" % ("<" + o["verdict"] + ">", src, ascii(rec)[:40], note))
    if not ok:
        print("                 py=%s  sql=%s (%s)%s" % (
            o.get("python"), o.get("sql_value"), o.get("sql_typeof"),
            "  RAISED " + str(o.get("sql_raised")) if o.get("sql_raised") else ""))

print()
print("%d of %d convention probes diverge" % (div, len(CASES)))
