"""T-3 thin driver for the 130-case contract fixture (proto/conformance.py).

Calls conformance.run() directly -- never main() -- so proto/results.json and
proto/CONFORMANCE.md (T-1's committed outputs) are not overwritten.  Writes the full
results JSON to spikes/T-3/out/ named by setting and runtime state, and prints the
totals line.  The fixture is ONE input set among several and may never be presented
as the acceptance test (Q2; framing section 5 item 6).

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python fixture_driver.py <tag>
"""
import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True
PROTO = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto"
OUT = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-3/out"

tag = sys.argv[1] if len(sys.argv) > 1 else "run"

_spec = importlib.util.spec_from_file_location("conformance_t3", os.path.join(PROTO, "conformance.py"))
conf = importlib.util.module_from_spec(_spec)
sys.modules["conformance_t3"] = conf
_spec.loader.exec_module(conf)

res = conf.run()
efd = res["meta"]["extra_float_digits"]
path = os.path.join(OUT, "fixture_%s_efd%s.json" % (tag, efd))
with open(path, "w") as fh:
    json.dump(res, fh, indent=1, default=repr)
t = res["totals"]
print("FIXTURE tag=%s efd=%s totals=%s" % (tag, efd, json.dumps(t)))
print("  meta: pg=%s  runtime_sql_sha256=%s  compile_py_sha256=%s  fixture_sha256=%s" % (
    res["meta"]["postgres"].split(" on ")[0], res["meta"]["runtime_sql_sha256"][:16],
    res["meta"]["compile_py_sha256"][:16], res["meta"]["fixture_sha256"][:16]))
nc = res.get("negative_controls")
if nc is not None:
    bad = [c for c in nc if not c.get("passed", True)]
    print("  negative controls: %d run, %d failed" % (len(nc), len(bad)))
print("  written: %s" % path)
