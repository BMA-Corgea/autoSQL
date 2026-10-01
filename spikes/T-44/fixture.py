"""T-44 K3: the 130-case contract fixture, run against a NAMED compiler.

proto/conformance.py loads the frozen SPIKE compiler by path into its module global
`proto_compile`. This driver loads conformance.py unchanged, rebinds that global to the
compiler it was asked for, and calls run(), never main(), so T-1's committed outputs are not
overwritten. Then it prints what actually ran. conformance.py's own meta block hashes the
spike FILES whatever was loaded (the T-10 class), so the true fingerprints are recorded beside
it.

Usage: AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=1 fixture.py --compiler {spike,ship,inline} --tag TAG
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True
ROOT = "/home/corgea/Desktop/Coding Projects/autoSQL"
PROTO = os.path.join(ROOT, "spikes/T-1/proto")
COMPILERS = {
    "spike": os.path.join(PROTO, "compile.py"),
    "ship": os.path.join(ROOT, "compiler/compile.py"),
    "inline": os.path.join(ROOT, "spikes/T-44/compile_inline.py"),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", required=True, choices=sorted(COMPILERS))
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    conf = load("conformance_t44", os.path.join(PROTO, "conformance.py"))
    xc = load("t44_compiler_" + a.compiler, COMPILERS[a.compiler])
    conf.proto_compile = xc                     # the one rebinding; nothing else differs
    res = conf.run()
    t = res["totals"]
    import psycopg2
    with psycopg2.connect(**conf.DSN) as c, c.cursor() as cur:
        cur.execute("select current_database()")
        db = cur.fetchone()[0]
        cur.execute("""select p.proname, pg_get_functiondef(p.oid) from pg_proc p
                         join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = 'xpr' order by p.proname, p.oid""")
        installed = hashlib.sha256("\n".join(d for _, d in cur.fetchall()).encode()).hexdigest()
    truth = {"compiler": a.compiler, "compiler_file": COMPILERS[a.compiler],
             "compiler_sha256": hashlib.sha256(open(COMPILERS[a.compiler], "rb").read()).hexdigest(),
             "installed_runtime_sha256": installed, "database": db,
             "efd": res["meta"]["extra_float_digits"],
             "note": "res.meta's compile_py/runtime_sql shas name the spike FILES, not what ran"}
    res["t44_what_actually_ran"] = truth
    out = os.path.join(ROOT, "spikes/T-44/out", f"fixture_{a.tag}.json")
    with open(out, "w") as fh:
        json.dump(res, fh, indent=1, default=repr)
    nc = res.get("negative_controls") or []
    bad = [x for x in nc if not x.get("passed", True)]
    print(f"FIXTURE {a.tag}: totals={json.dumps(t)} negative_controls={len(nc)} failed={len(bad)} "
          f"db={db} runtime={installed[:16]} compiler={truth['compiler_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
