"""How much of expr does the jsonpath-pushdown subset actually cover?
Classify every fixture case's AST: is it  cmp(op, field-path, literal)  -- the ONLY shape
Postgres jsonpath can express as an index-accelerable predicate?"""
import json, sys
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/GIMS-Project")
from core.dashboard import expr
fx = json.load(open("/home/corgea/Desktop/Coding Projects/GIMS-Project/tests/fixtures/expr_vectors.json"))
LIT = {"num", "str", "bool", "null"}
def is_path(n): return n[0] == "field" and all(s[0] == "key" for s in n[1])
def classify(a):
    if a[0] == "cmp" and is_path(a[2]) and a[3][0] in LIT: return "cmp(path, literal)"
    if a[0] == "cmp" and a[2][0] in LIT and is_path(a[3]): return "cmp(literal, path)"
    if is_path(a): return "bare path"
    if a[0] in LIT: return "bare literal"
    return "OTHER (no jsonpath equivalent)"
from collections import Counter
c = Counter()
for case in fx["cases"]:
    c[classify(expr.parse(case["expr"]))] += 1
tot = sum(c.values())
for k, v in c.most_common(): print(f"{v:4d}  {100*v/tot:5.1f}%  {k}")
print(f"{tot:4d}  total")
