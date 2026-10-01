"""T-44 K2 and the case-level differential: a candidate's battery against the shipping pair's.

Both runs draw the same seeded cases. Every case is paired by index, and the expression
text is asserted equal. Then:

  K2   every case the candidate REFUSES (SQL_REFUSAL / SQL_RAISE, value or predicate form)
       must be refused by the shipping pair too, with the SAME SQLSTATE. A refusal that
       moves from XPR01 to 22003 is a regression even when the totals match, because GIMS's
       fallback reads the code.
  DIFF the full verdict-transition matrix, plus every case whose value or predicate result
       differs from the shipping pair's at all. Reported, not gated: K1 already judges each
       side against Python.

Usage: compare_cases.py <baseline-tag> <candidate-tag> [...more candidate tags]
"""
import collections
import json
import os
import sys

CASES = "/home/corgea/Desktop/Coding Projects/autoSQL/.autodev/evidence/T-44/cases"
REFUSED = ("SQL_REFUSAL", "SQL_RAISE")


def load(tag):
    with open(os.path.join(CASES, tag + ".jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def compare(base_tag, cand_tag):
    b, c = load(base_tag), load(cand_tag)
    assert len(b) == len(c), f"{cand_tag}: {len(c)} cases vs baseline {len(b)}"
    trans = collections.Counter()
    new_refusals, changed_state, value_diffs, pred_diffs = [], [], [], []
    for x, y in zip(b, c):
        assert x["expr"] == y["expr"], f"case {x['i']}: the seeded draws diverged"
        trans[(x["verdict"], y["verdict"])] += 1
        if y["verdict"] in REFUSED:
            if x["verdict"] not in REFUSED:
                new_refusals.append((y["i"], "value", x["verdict"], y.get("sqlstate"), y["expr"][:140]))
            elif x.get("sqlstate") != y.get("sqlstate"):
                changed_state.append((y["i"], "value", x.get("sqlstate"), y.get("sqlstate"), y["expr"][:140]))
        if y.get("pred") == "SQL_RAISE":
            if x.get("pred") != "SQL_RAISE":
                new_refusals.append((y["i"], "predicate", x.get("pred"), y.get("pred_sqlstate"), y["expr"][:140]))
            elif x.get("pred_sqlstate") != y.get("pred_sqlstate"):
                changed_state.append((y["i"], "predicate", x.get("pred_sqlstate"), y.get("pred_sqlstate"), y["expr"][:140]))
        if x["verdict"] == y["verdict"] == "AGREE" and x.get("sql_value") != y.get("sql_value"):
            value_diffs.append((y["i"], x.get("sql_value"), y.get("sql_value"), y["expr"][:140]))
        if x.get("pred") != y.get("pred") or x.get("pred_sql") != y.get("pred_sql"):
            pred_diffs.append((y["i"], x.get("pred"), y.get("pred"), x.get("pred_sql"), y.get("pred_sql")))
    return {
        "baseline": base_tag, "candidate": cand_tag, "cases": len(c),
        "K2_new_refusals": len(new_refusals), "K2_changed_sqlstate": len(changed_state),
        "K2": "PASS" if not new_refusals and not changed_state else "FAIL",
        "transitions": {f"{k[0]} -> {k[1]}": v for k, v in sorted(trans.items())},
        "agree_cases_with_a_different_value": len(value_diffs),
        "cases_with_a_different_predicate_result": len(pred_diffs),
        "examples": {"new_refusals": new_refusals[:10], "changed_sqlstate": changed_state[:10],
                     "value_diffs": value_diffs[:10], "pred_diffs": pred_diffs[:10]},
    }


def main():
    base = sys.argv[1]
    results = [compare(base, t) for t in sys.argv[2:]]
    for r in results:
        print(f"{r['candidate']} vs {r['baseline']}: K2 {r['K2']} "
              f"(new refusals {r['K2_new_refusals']}, changed SQLSTATE {r['K2_changed_sqlstate']}); "
              f"agree-but-different-value {r['agree_cases_with_a_different_value']}; "
              f"different predicate {r['cases_with_a_different_predicate_result']}")
    print(json.dumps(results, indent=1, default=str))
    return 0 if all(r["K2"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
