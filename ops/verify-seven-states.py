"""T-2 verify (2026-09-01, GA-11) - the seven states, over HTTP, on the running stack.

Not the in-process TestClient: real requests to 127.0.0.1:8787, the same way a
person meets the screen.
"""
import json, sys, urllib.request, urllib.error

BASE = "http://127.0.0.1:8787"
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL")
sys.path.insert(0, "/home/corgea/Desktop/Coding Projects/autoSQL/demo")
from demo.tests.test_ui import SEVEN_STATES

def post(path, body):
    req = urllib.request.Request(BASE + path, method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

print("T-2 VERIFY - the seven states, live over HTTP, 2026-09-01")
print("=" * 92)
print("%-9s %-5s %-11s %-9s %-22s %s" % ("state", "http", "verdict", "accepted", "refusal", "beside the marker"))
print("-" * 92)

ok = True
for name in sorted(SEVEN_STATES):
    p, want_verdict, want_refusal = SEVEN_STATES[name]
    code, a = post("/api/pick", p)
    got = a.get("verdict")
    acc = a.get("accepted")
    ref = a.get("refusal") or (a.get("detail") if isinstance(a.get("detail"), dict) else None)
    refs = "%s/%s" % (ref["kind"], ref["layer"]) if isinstance(ref, dict) and "kind" in ref else "-"
    beside = "-"
    if a.get("column_order") and a.get("panes", {}).get("sql", {}).get("columns"):
        cols = a["panes"]["sql"]["columns"]; o = a["column_order"]
        beside = "%s | %s" % (cols[o["sql"][-1]], cols[o["python"][0]])
    if want_refusal:
        good = (refs == "%s/%s" % want_refusal)
    else:
        good = code == 200 and got == want_verdict and acc is True
    ok = ok and good
    print("%-9s %-5s %-11s %-9s %-22s %s%s" % (name, code, got, acc, refs, beside, "" if good else "  <-- MISMATCH"))

print("-" * 92)
p, _, _ = SEVEN_STATES["reconciled"]
_, a = post("/api/pick", p)
c = a["comparison"]; cols = a["panes"]["sql"]["columns"]; o = a["column_order"]
col = cols.index("biggest")
srow = next(r for r in a["panes"]["sql"]["rows"] if r["c"][cols.index("key")] == "edge-01")
prow = a["panes"]["python"]["rows"][srow["i"]]
print()
print("The value that used to come back wrong (edge-01, max($.m) over [FULLWIDTH 123, 1]):")
print("  differing rows   : %s   first at index %s" % (c["differing_rows"], c["first_differing_index"]))
print("  SQL              : %r" % srow["c"][col])
print("  Python           : %r" % prow["c"][col])
print("  marked as differing: %s" % bool(srow.get("diff")))
print("  column order     : natural on both panes (nothing differs, so nothing is moved)")
assert c["differing_rows"] == 0 and c["first_differing_index"] is None
assert srow["c"][col] == prow["c"][col] == "123", "the two engines no longer read this the same"
assert not srow.get("diff")
assert o["sql"] == list(range(len(cols))) and o["python"] == list(range(len(cols)))
print()
print("page /           : HTTP %s" % urllib.request.urlopen(BASE + "/", timeout=20).status)
print("static/js/app.js : HTTP %s" % urllib.request.urlopen(BASE + "/static/js/app.js", timeout=20).status)
print()
print("RESULT: %s" % ("all seven states reach the outcome their view describes, and the value that "
                      "used to be wrong now reads 123 on both engines" if ok else "MISMATCH - see above"))
sys.exit(0 if ok else 1)
