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
p, _, _ = SEVEN_STATES["disagree"]
_, a = post("/api/pick", p)
c = a["comparison"]; cols = a["panes"]["sql"]["columns"]; o = a["column_order"]
i = c["first_differing_index"]
srow = next(r for r in a["panes"]["sql"]["rows"] if r["i"] == i)
prow = next(r for r in a["panes"]["python"]["rows"] if r["i"] == i)
print()
print("The disagreement, located rather than announced:")
print("  differing rows   : %s   first at index %s" % (c["differing_rows"], i))
print("  differing column : %s" % ", ".join(cols[j] for j in srow["diff"]))
print("  SQL   order      : %s" % " / ".join(cols[j] for j in o["sql"]))
print("  Python order     : %s" % " / ".join(cols[j] for j in o["python"]))
print("  at the marker    : SQL %r  [marker]  %r Python"
      % (srow["c"][o["sql"][-1]], prow["c"][o["python"][0]]))
assert c["differing_rows"] >= 1 and srow.get("diff"), "the disagreement is not located"
assert o["sql"][-1] == o["python"][0], "the differing column is not beside the marker on both sides"
print()
print("page /           : HTTP %s" % urllib.request.urlopen(BASE + "/", timeout=20).status)
print("static/js/app.js : HTTP %s" % urllib.request.urlopen(BASE + "/static/js/app.js", timeout=20).status)
print()
print("RESULT: %s" % ("all seven states reach the outcome their view describes, and the differing "
                      "column sits beside the marker on both sides" if ok else "MISMATCH - see above"))
sys.exit(0 if ok else 1)
