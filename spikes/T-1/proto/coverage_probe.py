"""T-1 spike - THROWAWAY probe for the UNEXERCISED middle column (FRAMING.md section 4,
finding #2).  Not a library; nothing imports it.

The 130 fixture cases leave most of the language's VALUE DOMAIN untouched
(_eq 7/36 operand-kind cells, _order_cmp 4/36, `<=` never used at all).  Those cells
compile -- compile.py refuses no construct -- so they are the place a silent wrong
answer would hide.  This probes them against live Postgres.

ORACLE REUSE: matches(), run_sql(), SqlRaised and DSN are imported from
conformance.py, NOT reimplemented, so a probe is scored by exactly the rule the
conformance run used (mirrored from GIMS-Project/tests/test_dashboard_expr.py:20-25).
"""
import importlib.util, json, os, sys

PROTO = os.path.dirname(os.path.abspath(__file__))
GIMS = "/home/corgea/Desktop/Coding Projects/GIMS-Project"
sys.path.insert(0, GIMS)
from core.dashboard import expr

_s = importlib.util.spec_from_file_location("proto_conf", os.path.join(PROTO, "conformance.py"))
conf = importlib.util.module_from_spec(_s); _s.loader.exec_module(conf)
proto_compile = conf.proto_compile
import psycopg2

# ---- representative value per JSON kind (used to build the 6x6 matrices) ----
KINDS = {
    "null":   None,
    "bool":   True,
    "number": 5,
    "string": "5",
    "list":   [1, 2],
    "dict":   {"k": 1},
}

def probes():
    P = []
    def add(group, name, e, rec=None, ctx=None):
        P.append(dict(group=group, name=name, expr=e, record=rec or {}, context=ctx or {}))

    # 1. every comparison operator over every operand-kind pair (6x6x6 = 216)
    for op in ("==", "!=", "<", "<=", ">", ">="):
        for ka in KINDS:
            for kb in KINDS:
                add("cmp-matrix", f"{ka}{op}{kb}", f"$.a {op} $.b",
                    {"a": KINDS[ka], "b": KINDS[kb]})
    # 2. unary coercions over every kind
    for k, v in KINDS.items():
        add("to_num",  f"num_{k}",      "number($.a)", {"a": v})
        add("to_num",  f"arith_{k}",    "$.a + 0",     {"a": v})
        add("to_num",  f"neg_{k}",      "-$.a",        {"a": v})
        add("to_str",  f"string_{k}",   "string($.a)", {"a": v})
        add("to_str",  f"concat_{k}",   "concat($.a)", {"a": v})
        add("to_str",  f"lower_{k}",    "lower($.a)",  {"a": v})
        add("truthy",  f"not_{k}",      "not $.a",     {"a": v})
        add("truthy",  f"if_{k}",       "if($.a,1,2)", {"a": v})
        add("truthy",  f"and_{k}",      "$.a and true",{"a": v})
        add("length",  f"length_{k}",   "length($.a)", {"a": v})
        add("date",    f"dbetween_{k}", 'days_between($.a,"2026-01-01")', {"a": v})
        add("date",    f"dateadd_{k}",  "date_add($.a,1)", {"a": v})
        add("contains",f"hay_{k}",      "contains($.a,1)", {"a": v})
        add("contains",f"needle_{k}",   "contains($.h,$.a)", {"a": v, "h": [v, 9]})
    # 3. empty/edge containers (truthiness boundary)
    for nm, v in (("empty_list", []), ("empty_dict", {}), ("empty_str", ""),
                  ("zero", 0), ("false", False), ("nested", [[1], {"x": None}])):
        add("truthy", f"not_{nm}", "not $.a", {"a": v})
        add("length", f"length_{nm}", "length($.a)", {"a": v})
        add("to_str", f"string_{nm}", "string($.a)", {"a": v})
    # 4. bare $ (whole record) - never exercised by the fixture
    for e in ("length($)", "string($)", "$ == $", "not $", "contains($,1)", "number($)"):
        add("bare-$", e, e, {"a": 1})
        add("bare-$", e + " |empty", e, {})
    # 5. deep equality of containers (jsonb structural vs _eq)
    for nm, a, b in (
        ("list_same",        [1, 2],           [1, 2]),
        ("list_int_float",   [1],              [1.0]),
        ("list_bool_one",    [True],           [1]),
        ("list_order",       [1, 2],           [2, 1]),
        ("list_len",         [1],              [1, 2]),
        ("list_nested_null", [None],           [None]),
        ("dict_same",        {"a": 1},         {"a": 1}),
        ("dict_keyorder",    {"a": 1, "b": 2}, {"b": 2, "a": 1}),
        ("dict_int_float",   {"a": 1},         {"a": 1.0}),
        ("dict_bool_one",    {"a": True},      {"a": 1}),
        ("dict_extra_key",   {"a": 1},         {"a": 1, "b": 2}),
        ("dict_nested",      {"a": {"b": [1]}},{"a": {"b": [1]}}),
        ("num_int_float",    1,                1.0),
        ("num_neg_zero",     0.0,              -0.0),
    ):
        add("deep-eq", nm, "$.a == $.b", {"a": a, "b": b})
        add("deep-eq", nm + "|ne", "$.a != $.b", {"a": a, "b": b})
    # 6. aggregate arity/domain variants the fixture never uses
    for e in ("count()", "sum()", "avg()", "min()", "max()", "concat()", "coalesce(1)",
              "count(1,2)", "avg(1,2)", "min(1,2)", "max(1,2)", "sum(1,2)",
              "count($.a)", "sum($.a)", "avg($.a)", "min($.a)", "max($.a)",
              "count(1)", "sum(1)", "min($.a,$.b)", "max($.a,$.b)"):
        add("agg-arity", e, e, {"a": [1, "x", None, True], "b": 3})
    # 7. arity edge cases across the whole whitelist
    for e in ("lower()", "upper()", "number()", "string()", "length()", "abs()",
              "floor()", "ceil()", "round()", "contains(1)", "contains(1,2,3)",
              "days_between(1)", 'days_between("2026-01-01","2026-01-02","x")',
              "date_add(1)", "if(1,2)", "if(1,2,3,4)", "coalesce()",
              "lower($.a,$.b)", "today(1)", "now($.a)", "round(1.5,-1)",
              "round(-2.5)", "round(2.5)", "round(1.2345,2)"):
        add("arity-edge", e, e, {"a": "AbC", "b": "z"})
    return P

def main():
    conn = psycopg2.connect(**conf.DSN)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET extra_float_digits = 1")
    out = []
    for p in probes():
        row = dict(p)
        try:
            ast = expr.parse(p["expr"])
        except expr.ExprError as ex:
            row.update(outcome="PARSE_ERROR", detail=str(ex)); out.append(row); continue
        try:
            pyv = expr.evaluate(ast, p["record"], p["context"])
            row["python"] = pyv
        except Exception as ex:                     # expr claims this is impossible
            row.update(outcome="PYTHON_RAISED", detail=f"{type(ex).__name__}: {ex}")
            out.append(row); continue
        try:
            c = proto_compile.compile_ast(ast)
        except proto_compile.Uncompilable as ex:
            row.update(outcome="DID_NOT_COMPILE", detail=ex.reason); out.append(row); continue
        except Exception as ex:
            row.update(outcome="COMPILER_CRASHED", detail=f"{type(ex).__name__}: {ex}")
            out.append(row); continue
        try:
            isnull, jtype, jtext = conf.run_sql(cur, c.sql, c.params, p["record"], p["context"])
            conn.commit()
        except conf.SqlRaised as ex:
            conn.rollback()
            row.update(outcome="SQL_ERROR", detail=f"{ex.sqlstate}: {ex.message}")
            out.append(row); continue
        sqlv = None if isnull else json.loads(jtext)
        row["sql"] = "SQL NULL" if isnull else jtext
        if not isnull and jtype == "null":
            row.update(outcome="COMPILED_DIVERGES",
                       detail="top-level jsonb 'null' breaks compile.py:20-30 contract")
        elif conf.matches(sqlv, pyv) and conf.deep_strict(sqlv, pyv):
            row["outcome"] = "COMPILED_AGREES"
        elif conf.matches(sqlv, pyv):
            row.update(outcome="COMPILED_AGREES_LOOSE_ONLY",
                       detail="mirrored rule passes, strict deep check fails")
        else:
            row.update(outcome="COMPILED_DIVERGES", detail="matches() is False")
        out.append(row)
    dest = os.path.join(PROTO, "coverage_probe_results.json")
    json.dump(out, open(dest, "w"), indent=1, default=str)
    import collections
    ctr = collections.Counter(r["outcome"] for r in out)
    print(f"probes: {len(out)}")
    for k, v in sorted(ctr.items(), key=lambda kv: -kv[1]):
        print(f"  {v:5d}  {k}")
    print(f"\nwrote {dest}")
    return out

if __name__ == "__main__":
    main()
