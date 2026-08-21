"""T-1 index-shape seat: generate GIMS-shaped records for the idxprobe table.

Record shape is MODELLED ON REAL DATA, not invented:
  * LedgerRecord  -> gims-ledger/projects/guts-ledger/objects.db, collection 'LedgerRecord'
                     (17,087 real rows; key frequencies measured this session, see doc S1.2)
  * Submission    -> gims-ledger/projects/LIMS-System/noun_types.json, noun type "Submission"
                     (due_date / status / priority / received_date / comments) -- the same
                     shape api/dashboard/sources.py's own docstring example assumes
                     ("days_left": "days_between(today(), $.due_date)", "$.days_left < 7").

Deterministic: random.Random(20260819).  Writes TSV to stdout for COPY.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone

N_LEDGER = 150_000
N_SUBMISSION = 50_000
rnd = random.Random(20260819)

ACTORS = ["foreman", "goms", "operator", "gims", "human:evan", "watcher", "runner"]
EVENTS = ["work_order_forwarded_to_goms", "coordination_answer", "ticket_stage_advanced",
          "gate_cleared", "spike_finding_written", "conformance_run", "hold_placed"]
RISK = ["low", "medium", "high"]
STATUS = ["open", "closed", "coordinating", "blocked", "done"]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(days_offset, secs=0):
    return (BASE + timedelta(days=days_offset, seconds=secs)).isoformat()


def ledger_row(i):
    d = {
        "record_id": f"{i:08x}-869a-4011-ad72-5b8fc10fa0c6",
        "kind": "event",
        "event_type": rnd.choice(EVENTS),
        "actor": rnd.choice(ACTORS),
        "created_at": iso(rnd.randrange(0, 230), rnd.randrange(0, 86400)),
        "human_required": "false" if rnd.random() < 0.9 else "true",
        "summary": "WO-%06X %s" % (rnd.randrange(0, 1 << 24), rnd.choice(EVENTS)),
        "_runID": f"WO-{rnd.randrange(0, 1<<24):06X}",
        "work_order": f"WO-{rnd.randrange(0, 1<<24):06X}",
        "payload": {
            "goal_id": None,
            "artifact_refs": [f"work_orders:WO-{rnd.randrange(0, 1<<24):06X}"],
            "machine": rnd.choice(ACTORS),
            "timestamp": iso(rnd.randrange(0, 230)),
        },
    }
    # sparse keys, at the frequencies measured on the real 17,087-row table
    if rnd.random() < 0.282:
        d["risk_level"] = rnd.choice(RISK)
    if rnd.random() < 0.246:
        d["proposal_slug"] = f"prop-{rnd.randrange(0, 400)}"
    if rnd.random() < 0.246:
        d["ticket_id"] = f"T-{rnd.randrange(1, 900)}"
    if rnd.random() < 0.244:
        d["run_id"] = f"run-{rnd.randrange(0, 5000)}"
    if rnd.random() < 0.237:
        d["sprint_id"] = f"S-{rnd.randrange(1, 60)}"
        d["commit_sha"] = "%040x" % rnd.getrandbits(160)
    if rnd.random() < 0.161:
        d["correlation_id"] = "%032x" % rnd.getrandbits(128)
    if rnd.random() < 0.008:
        d["responds_to"] = "%08x" % rnd.getrandbits(32)
    if rnd.random() < 0.0007:
        d["revision"] = rnd.randrange(1, 9)          # number, rare key
    return d


def submission_row(i):
    # dashboard-shaped noun.  Deliberately heterogeneous, the way a GIMS project is:
    #  - due_date present on 92% of rows (absent key -> expr null, SQL NULL)
    #  - priority is a real JSON bool on most rows but the STRING "true" on 3%
    #    (GIMS stores adjective/bool fields inconsistently -- the real LedgerRecord
    #     table stores human_required as the string "false")
    #  - score is a JSON number on 95% of rows and a numeric STRING on 5%
    #  - one key with a space in it, one with mixed case: both legal GIMS field names
    #    (LIMS-System noun_types.json has "Sample Weight (g)", "Did it land?", etc.)
    d = {
        "submission_id": f"SUB-{i:07d}",
        "status": rnd.choice(STATUS),
        "received_date": iso(rnd.randrange(0, 200)),
        "comments": "lot %d %s" % (rnd.randrange(0, 9999), "x" * rnd.randrange(0, 40)),
        "client": f"client-{rnd.randrange(0, 250)}",
    }
    if rnd.random() < 0.92:
        d["due_date"] = iso(rnd.randrange(150, 400))
    r = rnd.random()
    if r < 0.03:
        d["priority"] = "true" if rnd.random() < 0.5 else "false"   # string, not bool
    elif r < 0.99:
        d["priority"] = rnd.random() < 0.25                         # real JSON bool
    # else: key absent entirely
    if rnd.random() < 0.95:
        d["score"] = round(rnd.uniform(0, 100), 4)                  # JSON number
    else:
        d["score"] = "%.4f" % rnd.uniform(0, 100)                   # numeric STRING
    d["Sample Weight (g)"] = round(rnd.uniform(0.1, 25.0), 3)
    if rnd.random() < 0.4:
        d["Analyte Type"] = rnd.choice(["potency", "terpene", "pesticide", "micro"])
    if rnd.random() < 0.15:
        d["vials"] = [{"id": f"V{rnd.randrange(0,999):03d}", "ml": round(rnd.uniform(1, 50), 2)}
                      for _ in range(rnd.randrange(1, 4))]
    return d


def emit(collection, key, data):
    # TSV for COPY; jsonb must not contain a raw tab/newline -- json.dumps escapes both.
    sys.stdout.write(collection + "\t" + key + "\t" + json.dumps(data, separators=(",", ":")) + "\n")


for i in range(N_LEDGER):
    emit("LedgerRecord", f"lr-{i:08d}", ledger_row(i))
for i in range(N_SUBMISSION):
    emit("Submission", f"SUB-{i:07d}", submission_row(i))
