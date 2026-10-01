"""T-48: compile-time GIMS key folding, `compile_ast(ast, fold="gims", noun=...)`.

A GIMS dashboard serves a noun row with every top-level key ALSO under its spaces and
underscores swapped (api/iostore/nouns.py `_normalize_row`, setdefault, stored keys taken in
jsonb order), and then with `setdefault("_noun_type", <noun>)` (api/dashboard/sources.py). A WHERE
pushed into SQL runs over the STORED row, so folding compiles each field's first key step to the
key the served row would answer with. T-46's parity vectors show the class; this file pins the
compiler's side of it:

  * the copy-source rule itself (no database);
  * the refusals: a construct that cannot be folded statically is Uncompilable, never a guess;
  * the default stays the default: without `fold`, nothing about the output moves;
  * THE ORACLE (needs a database): 600 generated stored ROWS, each checked under several expression
    forms, where the expected answer is autoSQL's own expr.py over the row normalised exactly as
    GIMS does it, with the key order read back from Postgres itself rather than assumed. The
    generator deliberately produces colliding copy sources, stored JSON nulls beside a copy source,
    keys with up to 4 separators, index first steps, and nested keys that contain separators.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DSN = os.environ.get("AUTOSQL_COMPILER_DSN")


def _connect():
    """Connect, then refuse port 55433 by the port actually reached, before any statement (the
    DSN text alone can be bypassed: PGPORT, URL forms, spacing)."""
    import psycopg
    cx = psycopg.connect(DSN, autocommit=True)
    if int(cx.info.port) == 55433:
        cx.close()
        raise SystemExit("refusing to run against port 55433 — that is a live database")
    return cx
needs_db = pytest.mark.skipif(not DSN, reason="set AUTOSQL_COMPILER_DSN to a Postgres with the runtime installed")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


EXPR = _load("t48_expr", "demo/vendor/expr.py")
C = _load("t48_compile", "compiler/compile.py")
NOUN = "parity_noun"


# ---- the copy-source rule -------------------------------------------------------------------------
@pytest.mark.parametrize("key, sources", [
    ("Sample_ID", ["Sample ID"]),
    ("Sample ID", ["Sample_ID"]),
    ("a b c", ["a b_c", "a_b c", "a_b_c"]),           # byte order: ' ' (0x20) before '_' (0x5f)
    ("_noun_type", [" noun type", " noun_type", "_noun type"]),
    ("a_b c", []),                                    # both kinds: a copy is never mixed
    ("plain", []),
    ("run-id", []),                                   # hyphens are not copied
])
def test_copy_sources(key, sources):
    assert C.gims_copy_sources(key) == sources


def test_every_copy_source_really_copies_into_the_key():
    """The rule, checked against _normalize_row's own two replacements."""
    for key in ("a b c d", "x_y_z", "_noun_type", "Lot No 2"):
        for src in C.gims_copy_sources(key):
            assert key in (src.replace("_", " "), src.replace(" ", "_")), (key, src)
            assert src != key


def test_the_separator_cap_refuses_rather_than_enumerating():
    ok = "a" + "_a" * C.FOLD_MAX_SEPARATORS
    assert len(C.gims_copy_sources(ok)) == 2 ** C.FOLD_MAX_SEPARATORS - 1
    with pytest.raises(C.Uncompilable, match="separators"):
        C.gims_copy_sources(ok + "_a")


# ---- refusals and caller errors -------------------------------------------------------------------
def test_a_bare_dollar_is_refused_under_folding():
    with pytest.raises(C.Uncompilable, match="bare \\$"):
        C.compile_ast(EXPR.parse("$"), fold="gims", noun=NOUN)


def test_a_key_over_the_cap_is_refused_under_folding():
    key = "a" + "_a" * (C.FOLD_MAX_SEPARATORS + 1)
    with pytest.raises(C.Uncompilable, match="Python"):
        C.compile_ast(EXPR.parse(f"$.{key}"), fold="gims", noun=NOUN)


@pytest.mark.parametrize("kwargs", [{"fold": "gims"}, {"fold": "gims", "noun": ""}, {"fold": "other", "noun": NOUN}])
def test_caller_errors_are_errors(kwargs):
    with pytest.raises(ValueError):
        C.compile_ast(EXPR.parse("$.a"), **kwargs)


# ---- the default stays the default ----------------------------------------------------------------
def _vector_expressions():
    doc = json.loads((ROOT / "parity" / "gims-pipeline-vectors.json").read_text())
    out = []
    for c in doc["cases"]:
        src = c.get("expr") or (c["filter"] if isinstance(c.get("filter"), str) else None)
        if src:
            out.append(src)
    return out


@pytest.mark.parametrize("src", _vector_expressions() + ["$.a + 1", "$['k'][0]", "$.a.b.c", "$", "coalesce($.a, 1)"])
def test_without_fold_the_output_is_unchanged(src):
    ast = EXPR.parse(src)
    assert C.compile_ast(ast) == C.compile_ast(ast, fold=None)
    plain = C.compile_ast(ast)
    # no copy source is ever bound without folding: every bound key is a key the source names
    named = {v for v in plain.params.values() if isinstance(v, str)}
    assert all(v in src for v in named), (src, plain.params)


# ---- THE ORACLE -----------------------------------------------------------------------------------
KEY_POOL = ["a", "b", "Sample ID", "Sample_ID", "lot_no 2", "x y", "x_y", "a b_c", "a_b c", "a b c", "a_b_c",
            " noun type", "_noun_type", " noun_type", "_noun type", "run-id", "Dry Weight", "k_1", "k 1",
            "é_x", "é x", "日本 語", "日本_語", "p q r s", "p_q r_s", "p q_r s", "p_q_r_s", "w_x_y_z", "w x_y z",
            "_", " ", "a  b", "a__b", "a _b"]
LOOKUPS = KEY_POOL + ["Dry_Weight", "lot no 2", "lot_no_2", "run_id", "k 1", "x y", "zz z", "日本 語",
                      "p_q_r_s", "p q r s", "w x y z", "a b", "a_ b"]
VALUES = [None, 0, 1, -2.5, "", "s", "S-1", True, False, [1, 2], {"sub": 3}, {"Sample ID": "nested"},
          {"a b": 7, "a_b": 8}, {"a b": 7}, [{"sub": 1}]]


def _gims_served_row(stored_in_jsonb_order: dict) -> dict:
    """GIMS's rule, written out independently of the compiler: _normalize_row's loop as it is in
    api/iostore/nouns.py:41-50, then _noun_records' setdefault of the tag."""
    fixed = dict(stored_in_jsonb_order)
    for k in list(stored_in_jsonb_order.keys()):
        if "_" in k:
            fixed.setdefault(k.replace("_", " "), stored_in_jsonb_order[k])
        if " " in k:
            fixed.setdefault(k.replace(" ", "_"), stored_in_jsonb_order[k])
    fixed.setdefault("_noun_type", NOUN)
    return fixed


def _expressions_for(key: str):
    ref = f"$['{key}']"
    forms = [ref, f"{ref}.sub", f"{ref} == 'S-1'", f"{ref} + 1", f"not {ref}", f"{ref} == null",
             f"{ref}['a b']", f"{ref}['a_b']", f"{ref}[0]", f"{ref}[0].sub", "$[0]", f"{ref}.sub == 3"]
    if key.replace("_", "a").isidentifier() and key.isascii():
        forms.append(f"$.{key}")
    return forms


def _matches(actual, expected):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected or (actual == expected and type(actual) is type(expected))
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-9)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(_matches(a, e) for a, e in zip(actual, expected))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_matches(actual[k], expected[k]) for k in expected)
    return actual == expected


@needs_db
def test_the_oracle_folded_sql_over_the_stored_row_equals_gims_over_the_served_row():
    import psycopg
    rng = random.Random(48)
    checked, refused, wrong = 0, 0, []
    with _connect() as cx:
        cx.execute("SET extra_float_digits = 1")
        rows = 0
        while rows < 600:
            rows += 1
            stored = {k: rng.choice(VALUES) for k in rng.sample(KEY_POOL, rng.randint(1, 6))}
            if rng.random() < 0.25:
                # a stored JSON null right beside one of its own copy sources
                k = rng.choice([k for k in KEY_POOL if (" " in k) != ("_" in k)])
                stored[k] = None
                srcs = C.gims_copy_sources(k)
                if srcs:
                    stored[rng.choice(srcs)] = rng.choice(VALUES)
            raw = json.dumps(stored)
            # the key order GIMS receives in Postgres mode, read back from Postgres itself
            order = [r[0] for r in cx.execute(
                "SELECT k FROM jsonb_object_keys((%s)::jsonb) WITH ORDINALITY AS t(k, o) ORDER BY o", (raw,))]
            served = _gims_served_row({k: stored[k] for k in order})
            key = rng.choice(LOOKUPS + ["_noun_type"])
            for src in _expressions_for(key):
                ast = EXPR.parse(src)
                want = EXPR.evaluate(ast, served, {})
                try:
                    c = C.compile_ast(ast, fold="gims", noun=NOUN)
                except C.Uncompilable:
                    refused += 1
                    continue
                params = dict(c.params, rec=raw, ctx="{}")
                is_null, jt, vt = cx.execute(
                    "SELECT (v IS NULL), jsonb_typeof(v), v::text FROM (SELECT " + c.sql +
                    " AS v FROM (SELECT (%(rec)s)::jsonb AS data) t) q", params).fetchone()
                got = None if (is_null or jt == "null") else json.loads(vt)
                checked += 1
                if not _matches(got, want):
                    wrong.append((src, stored, order, want, got))
    assert refused == 0, f"{refused} generated expressions were refused; the generator stays under the cap"
    assert not wrong, f"{len(wrong)} of {checked} disagree, e.g. {wrong[:3]}"
    assert rows == 600 and checked >= 600 * 6


@needs_db
def test_the_oracle_would_catch_an_unfolded_compiler():
    """Watched failing, every run: the same oracle over UNFOLDED output must disagree somewhere,
    or the test above proves nothing about folding."""
    import psycopg
    stored = {"Sample ID": "S-1"}
    ast = EXPR.parse("$.Sample_ID")
    want = EXPR.evaluate(ast, _gims_served_row(stored), {})
    c = C.compile_ast(ast)  # no fold
    with _connect() as cx:
        v = cx.execute("SELECT " + c.sql + " FROM (SELECT (%(rec)s)::jsonb AS data) t",
                       dict(c.params, rec=json.dumps(stored), ctx="{}")).fetchone()[0]
    assert want == "S-1" and v is None


@needs_db
@pytest.mark.parametrize("stored, src, want", [
    ({"Sample ID": {"sub": 3}}, "$.Sample_ID.sub == 3", True),     # a multi-step path folds its FIRST step
    ({"Sample ID": {"sub": 3}}, "$['Sample ID'].sub", 3),
    ({"a": 1}, "$[0]", None),                                      # an index first step on an object row
    ({"k": [{"Sample ID": 1}]}, "$.k[0].Sample_ID", None),        # nested keys are never copied
    ({"k": {"a b": 7}}, "$.k.a_b", None),                          # ... in an object either
    ({"x y": None, "x_y": 5}, "$['x y']", None),                  # a stored null beats its own copy source
    ({"x_y": 5}, "$['x y']", 5),
])
def test_pinned_paths_the_review_found_unguarded(stored, src, want):
    """T-48 review: two mutants (index first step dropped; only single-step paths folded) survived
    the generated oracle. These pin each path directly, against GIMS's rule as the oracle states it."""
    served = _gims_served_row(stored)
    assert EXPR.evaluate(EXPR.parse(src), served, {}) == want
    c = C.compile_ast(EXPR.parse(src), fold="gims", noun=NOUN)
    with _connect() as cx:
        is_null, jt, vt = cx.execute(
            "SELECT (v IS NULL), jsonb_typeof(v), v::text FROM (SELECT " + c.sql +
            " AS v FROM (SELECT (%(rec)s)::jsonb AS data) t) q", dict(c.params, rec=json.dumps(stored), ctx="{}")).fetchone()
    got = None if (is_null or jt == "null") else json.loads(vt)
    assert _matches(got, want), (src, stored, got, want)
