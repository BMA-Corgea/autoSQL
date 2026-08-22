"""T-3 positive control (framing section 5.2) -- did the float-digit setting actually change?

Correction C3: two instruments used to pin extra_float_digits = 1.  If the new plumbing
silently failed, all three "settings" would run at 1 and print three identical passes.
So, per setting, BEFORE the batteries:
  1. read the value back from the session differ.py actually uses;
  2. show a value that must differ across settings: to_jsonb(1.0/3.0) on the REAL value
     channel (M_encoding_guc.txt section M1: 16 / 15 / 12 significant digits at 1/0/-3),
     and the same 1/3 through the REAL compiled path (compile.py + xpr runtime).
The orchestrator collects the three lines and fails if any two settings print identically.

Usage:  AUTOSQL_SPIKE_DSN=... AUTOSQL_EFD=<1|0|-3> python efd_control.py
"""
import sys

sys.dont_write_bytecode = True
FUZZ = "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/analysis/fuzz"
sys.path.insert(0, FUZZ)
import os
os.chdir(FUZZ)

import differ                    # noqa: E402
from differ import run_case      # noqa: E402


def main():
    with differ.conn().cursor() as cur:
        cur.execute("select current_setting('extra_float_digits'), "
                    "to_jsonb(1.0::float8/3.0::float8)::text")
        efd, third = cur.fetchone()
    o = run_case("1 / 3", {}, None)
    print("EFD_CONTROL requested=%s readback=%s to_jsonb(1/3)=%s compiled_path(1/3)=%s verdict=%s"
          % (differ.EFD, efd, third, o.get("sql_text"), o["verdict"]))
    if efd != differ.EFD:
        print("FAILED: session setting does not match the request")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
