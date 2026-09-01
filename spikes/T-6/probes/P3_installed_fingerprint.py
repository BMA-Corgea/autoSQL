"""T-6 P3 - WHICH runtime did the batteries actually run against?

The harness prints `runtime.sql sha256=...` by hashing the FILE it expects
(spikes/T-1/proto/runtime.sql), not the functions installed in the database. So
every battery output in this run carries T-1's hash while the database holds
T-6's patched runtime. Left unchecked that would attribute T-6's numbers to T-3's
runtime -- an evidence-integrity defect in the instrument, not in the result.

This closes it by reading the INSTALLED function body out of pg_proc.
"""
import hashlib, io, os, sys
import psycopg2

DSN = os.environ["AUTOSQL_SPIKE_DSN"]
assert "port=55433" not in DSN
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

cx = psycopg2.connect(DSN); cx.autocommit = True
with cx.cursor() as cur:
    cur.execute("""
        select p.proname, pg_get_functiondef(p.oid)
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'xpr' order by p.proname, p.oid""")
    defs = cur.fetchall()

body = "\n".join(d for _, d in defs)
installed_sha = hashlib.sha256(body.encode()).hexdigest()

def filesha(p):
    return hashlib.sha256(io.open(os.path.join(ROOT, p), "rb").read()).hexdigest()

num_def = next(d for n, d in defs if n == "num")
has_xpr02 = "XPR02" in num_def
has_log   = "xpr.refusal XPR02" in num_def
old_null  = "RETURN NULL;\n    END IF;" in num_def

out = []
out.append("P3 - which runtime the batteries actually ran against")
out.append("=" * 78)
out.append("functions installed in schema xpr:        %d" % len(defs))
out.append("sha256 of the INSTALLED definitions:      %s" % installed_sha[:16])
out.append("")
out.append("file hashes, for comparison:")
out.append("  spikes/T-1/proto/runtime.sql           %s" % filesha("spikes/T-1/proto/runtime.sql")[:16])
out.append("  spikes/T-6/runtime.sql                 %s" % filesha("spikes/T-6/runtime.sql")[:16])
out.append("")
out.append("What the battery outputs PRINT as `runtime.sql sha256` is the first of those")
out.append("two -- the file the harness expects, hashed off disk. It is NOT evidence about")
out.append("what is installed. The checks below are.")
out.append("")
out.append("installed xpr.num carries the XPR02 refusal:      %s" % has_xpr02)
out.append("installed xpr.num carries the RAISE LOG record:   %s" % has_log)
out.append("")
ok = has_xpr02 and has_log
if ok:
    out.append("CONFIRMED: the batteries ran against T-6's patched runtime.")
else:
    out.append("FAILED: the installed runtime is NOT the patched one. Results are void.")
text = "\n".join(out)
io.open(os.path.join(HERE, "P3_installed_fingerprint.txt"), "w").write(text + "\n")
print(text)
sys.exit(0 if ok else 1)
