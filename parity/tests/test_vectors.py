"""The vector file's format, checked without GIMS or a database (T-46, AC1).

The GIMS half and the SQL half live in parity/check_gims_pipeline.py, because they need a GIMS
source tree and a scratch Postgres. This file only guards the structure every consumer relies on,
GIMS's pin test included, and proves the validator is not a check that never runs.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("parity_check", ROOT / "parity" / "check_gims_pipeline.py")
CHECK = importlib.util.module_from_spec(_spec)
sys.modules["parity_check"] = CHECK
_spec.loader.exec_module(CHECK)
DOC = json.loads((ROOT / "parity" / "gims-pipeline-vectors.json").read_text())


def test_the_committed_file_is_well_formed():
    assert CHECK.validate(DOC) == []


def test_every_kind_is_present_and_every_divergence_says_why():
    kinds = {c["kind"] for c in DOC["cases"]}
    assert kinds == set(CHECK.KINDS), kinds
    for c in DOC["cases"]:
        if c["autosql"]["status"] == "diverges":
            assert c["autosql"].get("why"), c["name"]


def test_the_source_digests_name_the_compiler_and_runtime_in_this_tree():
    """If either file changes, the recorded statuses describe a different autoSQL: re-run the check
    (it re-measures every case) and update `source`, or GIMS's pin test will say which one moved."""
    for key, rel in (("compiler_sha256", "compiler/compile.py"), ("runtime_sha256", "runtime/runtime.sql")):
        assert DOC["source"][key] == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), rel


@pytest.mark.parametrize("break_it, says", [
    (lambda d: d.update(format="gims-pipeline-vectors/2"), "format must be"),
    (lambda d: d.update(version=True), "version must be"),
    (lambda d: d["source"].pop("runtime_sha256"), "source must carry"),
    (lambda d: d["cases"].append(copy.deepcopy(d["cases"][0])), "duplicate name"),
    (lambda d: d["cases"][0].update(kind="bogus"), "kind must be one of"),
    (lambda d: d["cases"][0].pop("stored"), "needs ['stored']"),
    (lambda d: next(c for c in d["cases"] if c["kind"] == "sort")["rows"].append({"no": "id"}), "carry a string 'id'"),
    (lambda d: next(c for c in d["cases"] if c["kind"] == "sort")["sort"].update(dir="down"), "sort must be"),
    (lambda d: next(c for c in d["cases"] if c["autosql"]["status"] == "diverges")["autosql"].pop("why"),
     "a divergence must say why"),
    (lambda d: d["cases"][0]["autosql"].update(status="maybe"), "autosql.status must be"),
    (lambda d: next(c for c in d["cases"] if c["autosql"]["status"] == "diverges")["autosql"].update(fix_side="later"),
     "must name its fix_side"),
    (lambda d: next(c for c in d["cases"] if c["autosql"]["status"] == "diverges")["autosql"].pop("sql_gives"),
     "must record sql_gives"),
    (lambda d: next(c for c in d["cases"] if c["autosql"].get("folded") == "diverges")["autosql"].pop("folded_gives"),
     "must record folded_gives"),
    (lambda d: d.pop("noun"), "noun must name"),
    (lambda d: d.update(key_order="insertion"), "key_order must be 'jsonb'"),
    (lambda d: d["source"].update(compiler_sha256="abc"), "64 lowercase hex"),
    (lambda d: next(c for c in d["cases"] if c["kind"] == "sort").update(expect=[]), "answers with expect_ids"),
    (lambda d: next(c for c in d["cases"] if c["kind"] == "filter").update(filter=5), "filter must be"),
    (lambda d: next(c for c in d["cases"] if c["kind"] == "sort")["rows"][0].update(id=7), "carry a string 'id'"),
])
def test_the_validator_would_actually_catch_one(break_it, says):
    broken = copy.deepcopy(DOC)
    break_it(broken)
    errs = CHECK.validate(broken)
    assert any(says in e for e in errs), errs
