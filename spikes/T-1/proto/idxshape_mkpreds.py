"""T-1 index-shape seat: compile real dashboard predicates with the spike compiler.

No expression is invented here: each one is either verbatim from
tests/fixtures/expr_vectors.json, or a fixture SHAPE with the probe table's own key
names substituted (noted per row).  Parsing is the REAL core.dashboard.expr.parse().
"""
import json
import sys

sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto")

from core.dashboard import expr           # noqa: E402
import compile as C                        # noqa: E402

# ctx.now pinned so the compiled SQL is reproducible (the harness seat did the same;
# xpr.now_ms(ctx) reads ctx->'now' when present -> expr.py:449).
CTX = {"now": "2026-08-19T12:00:00Z"}

PREDS = [
    ("W1", "$.status == \"open\"",
     "fixture shape '$.s == \"FAIL\"' (case 28) with the probe's own 'status' key"),
    ("W2", "$.score > 90",
     "fixture shape '$.n < 7' (case 25) with the probe's own numeric 'score' key"),
    ("W3", "$.score * 2 > 180",
     "fixture shapes '$.a * 2' (case 23) + '$.n < 7' composed -- arithmetic predicate"),
    ("W4", "days_between(today(), $.due_date) < 7",
     "VERBATIM fixture case 114, and the exact widget in sources.py's own docstring (:25-26)"),
    ("W5", "$.status == \"done\" or $.status == \"blocked\"",
     "fixture shape '$.result == \"FAIL\" or $.result == \"ERROR\"' (case 115)"),
    ("W6", "$.actor == \"goms\"",
     "the ledger's OWN containment field (_INDEXABLE_FIELDS), written as an expr predicate"),
    ("W7", "lower($.status) == \"open\"",
     "fixture shape 'lower($.s)' (case 70) used as a predicate"),
    ("W8", "contains($.summary, \"hold\")",
     "fixture shape 'contains($.s, \"ell\")' (case 73)"),
    ("W9", "$.actor == \"goms\" and $.risk_level == \"high\"",
     "fixture shape '$.n > 0 and $.n < 10' (case 48) over two whitelisted ledger fields"),
    ("D1", "days_between(today(), $.due_date)",
     "VERBATIM fixture case 117 shape -- the DERIVE column 'days_left' from sources.py:25"),
    ("S1", "$.score",
     "the SORT key: sources.py:26 sort={field:'score'} -> _sort_key(_field_value(row,'score'))"),
]

out = {}
for pid, src, prov in PREDS:
    ast = expr.parse(src)
    try:
        comp = C.compile_ast(ast, column="data", ctx_param="ctx")
        rendered = C.render_for_display(comp.sql, comp.params, "ctx",
                                        "'" + json.dumps(CTX) + "'::jsonb")
        out[pid] = {"expr": src, "provenance": prov, "ast": repr(ast),
                    "sql": comp.sql, "params": comp.params, "rendered": rendered,
                    "compiled": True}
    except C.Uncompilable as e:
        out[pid] = {"expr": src, "provenance": prov, "ast": repr(ast),
                    "compiled": False, "reason": e.reason}

json.dump(out, open(sys.argv[1], "w"), indent=1)
for pid, v in out.items():
    print("=" * 78)
    print(pid, v["expr"], "  --", v["provenance"])
    if v["compiled"]:
        print("  AST     :", v["ast"])
        print("  SQL     :", v["sql"])
        print("  PARAMS  :", v["params"])
        print("  RENDERED:", v["rendered"])
    else:
        print("  UNCOMPILABLE:", v["reason"])
