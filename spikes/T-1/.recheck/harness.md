# T-1 recheck · Can the conformance harness actually report a failure?

**Verification task:** Evan's NO-GO on T-1 is conditional on two verifications. This is one of
them. The spike's headline is *"130 of 130 fixture cases agree bit-exactly"*. `FINDINGS.md`
§5.9(6) states, against the spike, that the code which assigns the *other* outcomes has never
executed. This section establishes whether that is true, and then runs the experiment §5.9(6)
itself names as *"what would establish it"*.

**Result up front — the rig is sound.** §5.9(6) is factually correct that the branches had never
executed, and I confirmed that by measured line coverage. But when driven, they work: a wrong
compilation emits `COMPILED_DIVERGES`, a refusal to compile emits `DID_NOT_COMPILE` and lands in
the denominator (`Pass rate = 125/130 = 96.2%`), a raising query emits `SQL_ERROR`, and a
jsonb-`null`-for-SQL-NULL substitution whose values compare **equal** is still caught. The
branches were dead, not broken. The `FRAMING.md` §8 failure mode did **not** occur. What that
does and does not do to the ruling is §9; what it does not establish is §7.

**Rule I worked under:** the spike ran under a written no-edit rule (`FRAMING.md` §3). Evan
waived it in writing on 2026-08-21 for this pass. Everything I changed is listed in §7.

---

## 1. How the harness assigns outcomes — read, not assumed

`/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance.py` is 1078 lines.
The outcome vocabulary is declared at `conformance.py:218-239` (`OUTCOME_DEFINITIONS`) and is
**four** outcomes, not three — the module docstring at `:17-24` explains that `FRAMING.md` §8
demanded three and the fourth (`SQL_ERROR`) was split out of "diverges" deliberately.

All outcome assignment happens in exactly one function, `run()` (`conformance.py:331-548`),
inside the per-case loop `for case in CASES:` (`:346`). There are **four** assignment sites and
no fallthrough:

| # | lines | branch condition | sets `outcome` to | increments |
| --- | --- | --- | --- | --- |
| A | `:377-382` | `except proto_compile.Uncompilable` around `compile_ast()` at `:376` | `DID_NOT_COMPILE` | `counts["DID_NOT_COMPILE"]` (`:380`) |
| B | `:396-404` | `except SqlRaised` around `run_sql()` at `:393` | `SQL_ERROR` | `counts["SQL_ERROR"]` (`:402`) |
| C | `:443-448` | `if agree and not leak` | `COMPILED_AGREES` | `counts["COMPILED_AGREES"]` (`:445`) |
| D | `:449-455` | the `else` of C | `COMPILED_DIVERGES` | `counts["COMPILED_DIVERGES"]` (`:455`) |

where, at `:437-438`:

```python
leak  = (not is_null) and jtype == "null"
agree = matches(sql_value, py_value)
```

Branches A and B `continue` the loop (`:382`, `:404`), so they are mutually exclusive with C/D
by construction. C and D are an if/else. The counts are asserted to sum to the case count at
`:508-512`, and the pass rate's denominator is `len(CASES)` (`:508`, `:535-536`) — so a
`DID_NOT_COMPILE` genuinely cannot be *arithmetically* laundered into the pass rate. That is the
part of the docstring's claim at `:26` ("There is no code path that can score DID_NOT_COMPILE or
SQL_ERROR as a pass") that is verifiable by reading, and it is true.

The part that reading alone cannot settle is whether branches A, B and D **work** — whether they
are reached at all when they should be, and whether what they emit is what the report prints.
That is §2 onward.

**The design is not the concern.** By reading, the classification logic is sound: mutually
exclusive branches, a summing assertion, a denominator that cannot be shrunk. §5.9(6)'s charge
is narrower and different — that three of these four branches are *dead code in every run that
has ever been performed*.

---

## 2. Is §5.9(6) true? Yes — established two independent ways

### 2a. Statically: nothing outside `run()` can set an outcome

Every assignment of the `outcome` key in the whole 1078-line file:

```
$ grep -n 'outcome=' conformance.py
378:                entry.update(outcome="DID_NOT_COMPILE", uncompilable_reason=exc.reason,
398:                entry.update(outcome="SQL_ERROR", sql_value=None,
444:                entry.update(outcome="COMPILED_AGREES", cause=None)
451:                    outcome="COMPILED_DIVERGES",
```

All four are inside `run()`. `run()` is called from exactly one place — `main()` at `:1058`:

```
$ grep -n '\brun()' conformance.py
331:def run() -> Dict[str, Any]:
1058:    res = run()
```

And the 23 negative controls (`selftest()`, `conformance.py:946-1040`) never reach any of it:

```
$ sed -n '946,1041p' conformance.py | grep -n 'outcome\|counts\|entries\|entry'
  (no matches — selftest touches none of them)
```

The controls assert on `matches()`, `deep_strict()`, `run_sql()`, `check_placeholders()` and
`compile_ast()` **as components**. NC11, NC12 and NC13 — the three that look like the ones that
would settle this — hand-write a wrong SQL string, run it, and call `matches()` on the result.
They construct no `entry` dict, touch no `counts`, and assert no `outcome` string. Confirmed
against the recorded artifact too: no entry in `results.json → negative_controls` mentions any of
the four outcome names.

So §5.9(6)'s wording — *"NC11/12/13 call `matches()` directly on hand-written SQL, construct no
case entry and assert no `outcome`"* — is exactly right.

### 2b. Dynamically: measured line coverage of a normal run

Reading tells you the controls *don't* reach those branches; it does not by itself prove that no
fixture case does. So I measured it. `.recheck/trace_outcome_lines.py` runs `conformance.py`'s
own `main()` (selftest + the full 130-case pass) under `sys.settrace` and counts executions per
line.

```
$ "/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python" \
    "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/.recheck/trace_outcome_lines.py"
```

Verbatim, the summary block:

```
------------------------------------------------------------------------------
SUMMARY (the assignment lines only)
------------------------------------------------------------------------------
  line  377  hits=0      DID_NOT_COMPILE
  line  378  hits=0      entry.update(outcome=DID_NOT_COMPILE)
  line  380  hits=0      counts["DID_NOT_COMPILE"] += 1
  line  396  hits=0      SQL_ERROR
  line  398  hits=0      entry.update(outcome=SQL_ERROR)
  line  402  hits=0      counts["SQL_ERROR"] += 1
  line  443  hits=130    if agree and not leak
  line  444  hits=130    entry.update(outcome=COMPILED_AGREES)
  line  445  hits=130    counts["COMPILED_AGREES"] += 1
  line  449  hits=0      else:
  line  451  hits=0      outcome=COMPILED_DIVERGES
  line  455  hits=0      counts["COMPILED_DIVERGES"] += 1

main() returned 0
total distinct lines of conformance.py executed: 466
```

**§5.9(6) is true, and I established it by measurement, not by taking the document's word.** Of
466 distinct lines executed in a full normal run, the 22 lines spanning branches A, B and D are
executed **zero** times. Only branch C has ever run.

One thing the trace turned up that §5.9(6) does not mention: `conformance.py:447-448` — the
"mirrored rule agrees but the stricter deep check does not" note *inside* branch C — also has
**0 hits**. That is consistent with the report's own "No case passes under the mirrored rule
while failing the stricter deep check", so it is a corroboration, not a new defect. It does mean
the dead-code surface in the outcome region is 24 lines, not 22.

### 2c. What this does and does not mean

It means the sentence *"130 of 130 cases agree"* had, until this pass, exactly the same
observable evidence behind it as the sentence *"the harness always writes COMPILED_AGREES"*.
Nothing in the run distinguished them. That is precisely the shape `FRAMING.md` §8 warned about.

It does **not** yet mean the number is wrong. Unexercised is not the same as broken. §3–§5 run
the experiment that separates the two.

---

## 3. Rebuilding the environment (and why this is itself evidence)

The spike's scratch database was gone. `autosql_spike` did not exist:

```
DB FAIL: OperationalError connection to server at "127.0.0.1", port 55433 failed:
FATAL:  database "autosql_spike" does not exist
```

Postgres 16.14 was still listening on 55433 with `glp_strong`, `postgres`, `template0`,
`template1`. I recreated `autosql_spike` and installed `proto/runtime.sql` into it — 21 `xpr`
functions, no tables (the harness synthesises the record inline in its `WRAPPER`
statement at `conformance.py:158-161`, so no data load is needed).

Before doing that I checked the four inputs the recorded run hashed, against the files on disk
today:

| input | recorded sha256 | on disk now | |
| --- | --- | --- | --- |
| `GIMS-Project/tests/fixtures/expr_vectors.json` | `0091df64283d91cb…` | `0091df64283d91cb…` | MATCH |
| `GIMS-Project/core/dashboard/expr.py` | `90cbb56d04b08b82…` | `90cbb56d04b08b82…` | MATCH |
| `proto/compile.py` | `b71b153802d0df94…` | `b71b153802d0df94…` | MATCH |
| `proto/runtime.sql` | `32628b45f2d1dd04…` | `32628b45f2d1dd04…` | MATCH |

Then I re-ran the unmodified harness. It reproduced the recorded run **exactly**:

```
$ "/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python" \
    "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance.py"
...
  [ok ] NC14 stray % refused
{
 "cases": 130,
 "compiled_agrees": 130,
 "compiled_diverges": 0,
 "did_not_compile": 0,
 "sql_error": 0,
 "pass_rate_denominator": 130,
 "pass_rate": 1.0
}
control (python vs fixture expect) failures: 0
mutation probe: 44 of 130 cases changed answer on an empty record; 24 field-reading cases did NOT change
```

and the regenerated artifacts are **byte-identical** to the ones the spike committed:

```
$ diff .recheck/orig/CONFORMANCE.md.orig proto/CONFORMANCE.md && echo IDENTICAL
  IDENTICAL
$ sha256sum proto/results.json .recheck/orig/results.json.orig
002cda09c2238c1f2bf38c85ae7fe113b33322e7efa843278b4407aff945c212  proto/results.json
002cda09c2238c1f2bf38c85ae7fe113b33322e7efa843278b4407aff945c212  .recheck/orig/results.json.orig
```

That is worth recording on its own: **the 130/130 run is reproducible from a cold database**,
23/23 controls and all. It was not a one-off. It is also why the injection results below can be
read as a difference caused by the injection and nothing else.

---

## 4. The experiment

`/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance_injection_test.py`
— new file, written by me.

**`conformance.py` is not modified.** The script imports it by path and replaces the module's
handle on the compiler, `conformance.proto_compile.compile_ast`, with a wrapper that is the real
compiler except for a table of named injections keyed by fixture case name. Everything
downstream is the real, unmodified harness: `run_sql()`, the `WRAPPER` statement, the parameter
binding, `matches()`, `deep_strict()`, the mutation probe, the four outcome branches, the
`counts` dict, the summing assertion at `:509` and `write_report()`.

The script calls `conformance.run()` directly, never `main()`, so it **writes nothing to
`proto/`**. `proto/results.json` and `proto/CONFORMANCE.md` are byte-identical before and after
(verified by sha256 after every run).

Six injections, each declaring the outcome it must provoke:

| id | fixture case | expr | injected instead of the real compilation | must emit |
| --- | --- | --- | --- | --- |
| I1 | `add` | `1 + 2` | `to_jsonb(999::float8)` | `COMPILED_DIVERGES` |
| I2 | `precedence_mul_before_add` | `10 - 4 * 2` | `raise Uncompilable(...)` | `DID_NOT_COMPILE` |
| I3 | `parens_override` | `(10 - 4) * 2` | `to_jsonb((1::int / 0::int))` | `SQL_ERROR` |
| I4 | `divide_by_zero_is_null` | `5 / 0` | `'null'::jsonb` | `COMPILED_DIVERGES` |
| I5 | `true_division` | `7 / 2` | `to_jsonb(3.50000001::float8)` — off by 1e-8 | `COMPILED_DIVERGES` |
| I6 | `modulo_pos` | `7 % 3` | `to_jsonb(1.0000000001::float8)` — off by 1e-10 | `COMPILED_AGREES` |

Why these six and not one:

- **I1** is the gross error — 999 where the answer is 3. It is the minimum the task asked for.
- **I2** is the one `FRAMING.md` §8 names by name: a case that *fails to compile*. §8's specific
  fear is that this gets scored as a pass.
- **I3** exercises the fourth branch, `SQL_ERROR`, which `FINDINGS.md` §5.9(6) does not mention
  but which is dead for the same reason.
- **I4** is the subtle one. It is the **only wrong answer for which `matches()` returns `True`**:
  `'null'::jsonb` decodes to Python `None`, Python's value is `None`, so the values compare
  equal. Only the `and not leak` half of `conformance.py:443` can catch it. A rig that got I1–I3
  right and I4 wrong would still be a rig that passes a compiler which has broken the
  SQL-NULL/jsonb-null contract.
- **I5/I6** are a near-miss pair bracketing the fixture's own 1e-9 **absolute** epsilon. I1 alone
  would only show the rig catches a large error; a rig can catch 999-vs-3 and still be blind to
  1e-8. **I6 expecting `COMPILED_AGREES` is not leniency** — 1e-10 is inside the tolerance the
  fixture itself defines, so agreeing is the correct answer, and a rig that failed I6 would be
  broken in the other direction.

Target cases were chosen so none of their expressions collides with an out-of-fixture `PROBE`
expression. Two fixture cases *do* collide (`simple` = `$.a`, `upper` = `upper($.s)`) and are
deliberately unused. Each injection asserts it fired **exactly once**.

### 4a. The control — the injection mechanism itself changes nothing

```
$ <venv-python> proto/conformance_injection_test.py --control
CONTROL RUN — compile_ast is the real one, no injection.

TOTALS AS EMITTED BY THE HARNESS
{
 "cases": 130,
 "compiled_agrees": 130,
 "compiled_diverges": 0,
 "did_not_compile": 0,
 "sql_error": 0,
 "pass_rate_denominator": 130,
 "pass_rate": 1.0
}

control: 130/130 COMPILED_AGREES
```

Same driver, same import path, no injection → the original 130/130. So every difference in §5 is
caused by the injected compilation and by nothing about how the script drives the harness.

---

## 5. What the harness ACTUALLY emitted

```
$ "/home/corgea/Desktop/Coding Projects/GIMS-Project/.venv/bin/python" \
    "/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance_injection_test.py"
```

Verbatim, complete, unedited:

```
INJECTING into the real per-case loop:
  I1  case 'add'
      constant wrong number (999) where Python says 3.0
      MUST emit outcome = COMPILED_DIVERGES
  I2  case 'precedence_mul_before_add'
      compiler refuses: raises Uncompilable
      MUST emit outcome = DID_NOT_COMPILE
  I3  case 'parens_override'
      SQL that raises at execution time (integer division by zero)
      MUST emit outcome = SQL_ERROR
  I4  case 'divide_by_zero_is_null'
      jsonb 'null' where Python has None — decodes EQUAL, breaks the SQL-NULL representation contract
      MUST emit outcome = COMPILED_DIVERGES
  I5  case 'true_division'
      3.50000001 where Python says 3.5 — off by 1e-8, just ABOVE the 1e-9 absolute epsilon
      MUST emit outcome = COMPILED_DIVERGES
  I6  case 'modulo_pos'
      1.0000000001 where Python says 1.0 — off by 1e-10, just BELOW the 1e-9 absolute epsilon. Agreeing here is CORRECT, not lenient.
      MUST emit outcome = COMPILED_AGREES

TOTALS AS EMITTED BY THE HARNESS
{
 "cases": 130,
 "compiled_agrees": 125,
 "compiled_diverges": 3,
 "did_not_compile": 1,
 "sql_error": 1,
 "pass_rate_denominator": 130,
 "pass_rate": 0.9615384615384616
}

PER-INJECTION — what the harness ACTUALLY emitted
--------------------------------------------------------------------------
I1  case 'add'
    expr                 '1 + 2'
    python_value         3.0
    sql (injected)       'to_jsonb(999::float8)'
    sql_is_null          False
    sql_jsonb_typeof     'number'
    sql_value            999
    mirrored_rule_agrees False
    cause_shape          'numeric difference |999.0 - 3.0| = 996.0 > 1e-09'
    cause                'UNCLASSIFIED'
    injection fired      1 time(s)
    EXPECTED outcome     COMPILED_DIVERGES
    EMITTED  outcome     COMPILED_DIVERGES      <-- OK

I2  case 'precedence_mul_before_add'
    expr                 '10 - 4 * 2'
    python_value         2.0
    uncompilable_reason  'INJECTED: this construct is not compilable (deliberate)'
    injection fired      1 time(s)
    EXPECTED outcome     DID_NOT_COMPILE
    EMITTED  outcome     DID_NOT_COMPILE      <-- OK

I3  case 'parens_override'
    expr                 '(10 - 4) * 2'
    python_value         12.0
    sql (injected)       'to_jsonb((1::int / 0::int))'
    sql_is_null          None
    sql_jsonb_typeof     None
    sql_value            None
    mirrored_rule_agrees None
    sql_error            22012 'ERROR:  division by zero'
    cause                'Postgres raised where expr returns a value or null (totality violation)'
    injection fired      1 time(s)
    EXPECTED outcome     SQL_ERROR
    EMITTED  outcome     SQL_ERROR      <-- OK

I4  case 'divide_by_zero_is_null'
    expr                 '5 / 0'
    python_value         None
    sql (injected)       "'null'::jsonb"
    sql_is_null          False
    sql_jsonb_typeof     'null'
    sql_value            None
    mirrored_rule_agrees True
    cause_shape          "SQL returned jsonb 'null' at top level, not SQL NULL (representation leak)"
    cause                'UNCLASSIFIED'
    injection fired      1 time(s)
    EXPECTED outcome     COMPILED_DIVERGES
    EMITTED  outcome     COMPILED_DIVERGES      <-- OK

I5  case 'true_division'
    expr                 '7 / 2'
    python_value         3.5
    sql (injected)       'to_jsonb(3.50000001::float8)'
    sql_is_null          False
    sql_jsonb_typeof     'number'
    sql_value            3.50000001
    mirrored_rule_agrees False
    cause_shape          'numeric difference |3.50000001 - 3.5| = 9.99999993922529e-09 > 1e-09'
    cause                'UNCLASSIFIED'
    injection fired      1 time(s)
    EXPECTED outcome     COMPILED_DIVERGES
    EMITTED  outcome     COMPILED_DIVERGES      <-- OK

I6  case 'modulo_pos'
    expr                 '7 % 3'
    python_value         1.0
    sql (injected)       'to_jsonb(1.0000000001::float8)'
    sql_is_null          False
    sql_jsonb_typeof     'number'
    sql_value            1.0000000001
    mirrored_rule_agrees True
    injection fired      1 time(s)
    EXPECTED outcome     COMPILED_AGREES
    EMITTED  outcome     COMPILED_AGREES      <-- OK

COUNTS
    expected {'COMPILED_AGREES': 125, 'COMPILED_DIVERGES': 3, 'DID_NOT_COMPILE': 1, 'SQL_ERROR': 1}
    emitted  {'COMPILED_AGREES': 125, 'COMPILED_DIVERGES': 3, 'DID_NOT_COMPILE': 1, 'SQL_ERROR': 1}
    pass_rate 125/130 = 0.9615384615384616

```

**Exit code 0.** Every one of the six emitted the outcome it was required to emit.

### 5a. The reporting chain, not just the counters

Counts could be right while the report still printed something reassuring. So I rendered the
harness's own `write_report()` over the injected result (`--write-report`, output in
`.recheck/injected/CONFORMANCE.injected.md`). It is the real writer, unmodified.

Totals table:

```
## Totals

| outcome | count | of |
| --- | ---: | ---: |
| `COMPILED_AGREES` | 125 | 130 |
| `COMPILED_DIVERGES` | 3 | 130 |
| `DID_NOT_COMPILE` | 1 | 130 |
| `SQL_ERROR` | 1 | 130 |

**Pass rate = 125/130 = 96.2%** — denominator is every fixture case, not every compiled case.
```

**The `DID_NOT_COMPILE` case is outside the numerator and inside the denominator.** That is the
precise thing `FRAMING.md` §8 said must be true and that nothing had ever demonstrated.

The three loud sections all populate:

```
## SQL_ERROR — totality violations (most severe)

| case | expr | sqlstate | message |
| --- | --- | --- | --- |
| `parens_override` | `(10 - 4) * 2` | `22012` | ERROR:  division by zero |

## DID_NOT_COMPILE — coverage gaps (not passes)

| case | expr | Uncompilable reason |
| --- | --- | --- |
| `precedence_mul_before_add` | `10 - 4 * 2` | INJECTED: this construct is not compilable (deliberate) |

## COMPILED_DIVERGES — with cause

| case | expr | Python | SQL | shape of the difference | cause |
| --- | --- | --- | --- | --- | --- |
| `add` | `1 + 2` | `3.0` (float) | `999` (int, jsonb number) | numeric difference \|999.0 - 3.0\| = 996.0 > 1e-09 | UNCLASSIFIED |
| `true_division` | `7 / 2` | `3.5` (float) | `3.50000001` (float, jsonb number) | numeric difference \|3.50000001 - 3.5\| = 9.99999993922529e-09 > … | UNCLASSIFIED |
| `divide_by_zero_is_null` | `5 / 0` | `None` (NoneType) | `None` (NoneType, jsonb null) | SQL returned jsonb 'null' at top level, not SQL NULL (representation … | UNCLASSIFIED |
```

And the per-case table marks them individually, with the group header tallying them:

```
### `arithmetic` — 11 cases (PASS 6 · FAIL 3 · GAP 1 · RAISE 1)

| # | case | expr | outcome | Python | SQL | cause / reason |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `add` | `1 + 2` | **FAIL** `COMPILED_DIVERGES` | `3.0` (float) | `999` (int, jsonb number) | UNCLASSIFIED — numeric difference \|999.0 - 3.0\| = 996.0 >… |
| 2 | `precedence_mul_before_add` | `10 - 4 * 2` | **GAP** `DID_NOT_COMPILE` | `2.0` (float) | — | INJECTED: this construct is not compilable (deliberate) |
| 3 | `parens_override` | `(10 - 4) * 2` | **RAISE** `SQL_ERROR` | `12.0` (float) | **RAISED** 22012 | ERROR:  division by zero |
| 4 | `true_division` | `7 / 2` | **FAIL** `COMPILED_DIVERGES` | `3.5` (float) | `3.50000001` (float, jsonb number) | UNCLASSIFIED — numeric difference \|3.50000001 - 3.5\| = 9.… |
| 5 | `modulo_pos` | `7 % 3` | **PASS** `COMPILED_AGREES` | `1.0` (float) | `1.0000000001` (float, jsonb number) |  |
```

Row 5 is I6 — the 1e-10 near-miss, correctly still a PASS.

### 5b. The dead branches are now measurably alive

Same tracer as §2b, run through the injection driver (`--inject`). Verbatim:

```
------------------------------------------------------------------------------
SUMMARY (the assignment lines only)
------------------------------------------------------------------------------
  line  377  hits=1      DID_NOT_COMPILE
  line  378  hits=2      entry.update(outcome=DID_NOT_COMPILE)
  line  380  hits=1      counts["DID_NOT_COMPILE"] += 1
  line  396  hits=1      SQL_ERROR
  line  398  hits=2      entry.update(outcome=SQL_ERROR)
  line  402  hits=1      counts["SQL_ERROR"] += 1
  line  443  hits=128    if agree and not leak
  line  444  hits=125    entry.update(outcome=COMPILED_AGREES)
  line  445  hits=125    counts["COMPILED_AGREES"] += 1
  line  449  hits=0      else:
  line  451  hits=3      outcome=COMPILED_DIVERGES
  line  455  hits=3      counts["COMPILED_DIVERGES"] += 1
```

Reading the numbers: `hits=2` on `:378`/`:398` is one execution of a two-line statement counted
at both of its lines. `:449` reads 0 because CPython attributes the `else` jump to `:450`, which
does register. `:443` at 128 = 130 minus the two cases (I2, I3) that took branch A or B and
`continue`d before reaching it. 125 + 3 = 128. ✓

Compare with §2b, where every one of those lines read `hits=0`. The branches are not broken and
they are not unreachable — they were simply never provoked.

### 5c. The fifth path — the harness-integrity abort

The per-case loop has one more exit I had not exercised: `conformance.py:405-408`. If
`check_placeholders()` finds a stray literal `%` in generated SQL — which psycopg2 would eat
during its own parameter interpolation, silently changing the statement — the `AssertionError`
is recorded in `harness_errors` and **re-raised**, aborting the run. NC14 tests
`check_placeholders()` as a component; nothing had ever driven this path through the loop.

```
$ <venv-python> proto/conformance_injection_test.py --stray-percent
STRAY-% PROBE — conformance.py:405-408, the harness-integrity abort path
  injecting SQL containing a stray literal '%' for fixture case 'add'
  REQUIRED behaviour: run() raises AssertionError and produces no result

  AssertionError raised, as required: stray literal '%' in generated SQL at offset 141

RESULT: the harness aborted. It cannot score a stray-% case at all.
```

A pass here means the harness **refuses to produce a number**, which is the correct response to
an integrity failure — and it is the fifth and last exit from the per-case loop. All five are now
exercised.

---

## 6. Verdict — the rig is sound

Of the three publishable outcomes the task named, this is the first one:

> **the rig correctly reports divergence and non-compilation; the 130/130 number is
> trustworthy as a statement about what the harness measured.**

I would have written the opposite with the same directness, and §2 is what that section would
have opened with. It did not go that way.

Specifically, established by running it:

1. **A compiled-but-wrong answer is emitted as `COMPILED_DIVERGES`, not as a pass** (I1, I5).
2. **A case that fails to compile is emitted as `DID_NOT_COMPILE`** (I2) — and lands in the
   denominator, not the numerator: `Pass rate = 125/130 = 96.2%`. This is the exact scenario
   `FRAMING.md` §8 was written to warn about, and the warned-of failure **did not occur**.
3. **A case where Postgres raises is emitted as `SQL_ERROR`** (I3), with sqlstate and message.
4. **The subtle one is caught too** (I4): a compilation that returns jsonb `null` where Python
   returns `None` decodes to values that compare **equal** — `mirrored_rule_agrees True` — and
   the harness *still* emits `COMPILED_DIVERGES`, correctly naming
   `"SQL returned jsonb 'null' at top level, not SQL NULL (representation leak)"`. This is the
   one I most expected to fail, because it requires the `and not leak` conjunct at `:443` to be
   live and correct. It is.
5. **The epsilon boundary is sharp in both directions** (I5/I6): 1e-8 diverges, 1e-10 agrees,
   which is the fixture's own 1e-9 absolute tolerance behaving as specified.
6. **The whole reporting chain carries it through** — totals table, the three loud sections, the
   per-case rows, and the group tallies (`PASS 6 · FAIL 3 · GAP 1 · RAISE 1`).
7. **The fifth exit refuses to produce a number at all** (§5c): SQL the harness cannot verify
   aborts the run rather than being scored. All five exits from the per-case loop are now
   exercised — A, B, C, D and the integrity abort at `:405-408`.

I also confirmed the oracle is what it claims to be. `conformance.py:98-104` is
character-for-character the rule at `GIMS-Project/tests/test_dashboard_expr.py:20-25` (read
read-only, quoted at §3's hash table): same bool-first branch with the `type(actual) is
type(expected)` guard, same `math.isclose(..., rel_tol=0, abs_tol=_EPS)`. The claim in the
docstring that it is "mirrored unchanged" is true.

**So: `FINDINGS.md` §5.9(6) is factually correct about the branches never having executed, and
correct to have flagged it — but the defect it feared is not there.** The branches were dead,
not broken. That distinction is the whole content of this section, and it could only be settled
by running it, which is what §5.9(6) itself said.

---

## 7. What this does NOT establish

The result above is narrow, and it is worth being precise about how narrow.

**7a. It tests the judge, not the defendant.** The injection replaces `compile_ast`'s *output*.
It proves the harness classifies a wrong compilation correctly. It says nothing whatever about
whether `compile.py` is correct, and it cannot: a compiler that produced SQL agreeing with
Python for the wrong reason would still score `COMPILED_AGREES`, correctly, under this rig.
*What would settle that:* nothing here — it is the divergence register (`xc` C.8) and the
out-of-fixture probes, which already found real defects (`float8_overflow_raises`, the `xpr.f8`
guard being ~12 orders of magnitude too tight).

**7b. It does not touch the separate charge against the same number.** `FINDINGS.md` §5.2 and
§5.7 argue that 130/130 is a statement about the **fixture**, and that the fixture covers only
**68 of 130 (52.3%)** of the corrected subset and cannot serve as an acceptance test for a third
runtime. That is a *different* criticism of the *same* number, and this experiment leaves it
exactly where it was. A sound rig scoring an inadequate fixture still produces an inadequate
result. *What would settle it:* §5.11's E1, the subset acceptance battery — not run here.

**7c. `CAUSES` is empty, so every real divergence would report `UNCLASSIFIED`.** Visible in the
output above: all three injected divergences carry `cause: 'UNCLASSIFIED'`. That is by design —
`conformance.py:265-267` says a case absent from `CAUSES` is *"reported as 'unclassified' rather
than guessed at"*, and the mechanical `cause_shape` **is** populated and is accurate in all three
cases. But `OUTCOME_DEFINITIONS["COMPILED_DIVERGES"]` at `:224-229` promises *"Cause is named per
case"*, and nothing names it automatically; a human must add the entry after reading the case.
This is a small overstatement in the definition text, not a defect in the machinery. I did not
change it (it is the spike's document, and this is a wording matter, not a correctness one).

**7d. The database had to be rebuilt, so this is a reconstruction, not the original run.** The
byte-identical reproduction in §3 is strong evidence the reconstruction is faithful — 130 cases,
23 controls, 8 out-of-fixture probes and a full rendered report all matching to the byte. But it
is reproduction, not the same process. *What would make it stronger:* nothing available; the
original database is gone.

**7e. `extra_float_digits` is still pinned to 1 by `conformance.py:341`.** §5.11 already names
"whether the 130 still agree at `extra_float_digits` 0 or −3" as an open gap, with 68 of 130
exposed. My runs inherit that pin. I did not vary it — out of scope for this task, and it is
already recorded as open.

**7f. Nothing here validates the *other* instruments.** §5.9(6) sits in a list of residuals that
also names `differ.py` and `bench.py` as having **no negative controls** (`critic` §7) — and
`differ.py` is described there as *"the instrument that produced every decision-relevant
divergence"*. My task was `conformance.py`. Those two are untouched by this pass and the residual
against them stands unchanged. *What would settle it:* the same treatment applied to them —
inject a known-wrong input and assert the emitted classification.

---

## 8. Everything I changed

The spike ran under `FRAMING.md` §3's no-edit rule. Evan waived it for this pass in writing on
2026-08-21 (*"Let them edit the existing code in place"*). In the event I did **not** need to
edit anything in place — the injection is a separate driver — so the waiver went unused on
`proto/`'s existing files. The complete ledger:

**Added (one file under `proto/`, the required reproducible artifact):**

- `/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1/proto/conformance_injection_test.py`
  — the injection experiment. Three modes: default (6 injections), `--control` (none),
  `--stray-percent` (the integrity-abort path). `--write-report DIR` renders the harness's own
  report writer into `DIR`. Writes nothing to `proto/`.

**Added (this pass's evidence, under `.recheck/`):**

- `.recheck/harness.md` — this file
- `.recheck/trace_outcome_lines.py` — the line-coverage prober (`--inject` to trace under injection)
- `.recheck/injection-run.txt`, `.recheck/injection-control.txt` — verbatim run output
- `.recheck/trace-normal.txt`, `.recheck/trace-injected.txt` — verbatim trace output
- `.recheck/injected/CONFORMANCE.injected.md`, `.recheck/injected/results.injected.json` — the
  harness's own report writer over the injected result
- `.recheck/orig/CONFORMANCE.md.orig`, `.recheck/orig/results.json.orig` — pre-pass backups

**Modified: nothing.**

- `proto/conformance.py`, `proto/compile.py`, `proto/runtime.sql` — **not touched**. sha256 of
  `compile.py` and `runtime.sql` still match what `results.json` recorded (§3).
- `proto/results.json` and `proto/CONFORMANCE.md` — **mtime changed, bytes did not.** The
  baseline re-run in §3 rewrote them with byte-identical content; sha256 verified before and
  after every subsequent run (`002cda09c223…` / `72db7f8246889…`).

**Read-only trees:** `GIMS-Project` was read (fixture, `expr.py`, `tests/test_dashboard_expr.py`)
and **not written** — `find GIMS-Project -newermt "2026-08-21 00:00"` returns nothing.
`GUTS/spine/L1-memory/gims-ledger` I did not open at all, in either direction. (Files there
*do* carry today's mtimes — `objects.db`, `backups/`, `logins.db-shm` — from the running GUTS
system, independently of this pass.)

**Not touched:** `tracker.mjs`, `.autodev/tickets/`, `.autodev/events.jsonl`, anything else under
`.autodev/`. Also not touched: `.recheck/trail.md`, which belongs to the other verification
running in this directory.

**Outside the filesystem — the one real side effect:** I created the Postgres database
`autosql_spike` on `127.0.0.1:55433` and installed `proto/runtime.sql` into it (schema `xpr`, 21
functions, no tables). It did not exist when I started (§3). `runtime.sql` itself calls this
*"the scratch database `autosql_spike`"* (`runtime.sql:13`). No other database was altered;
`glp_strong` was never opened. To undo: `DROP DATABASE autosql_spike;`

**No `__pycache__` was written** — every invocation ran under `PYTHONDONTWRITEBYTECODE=1` and the
scripts set `sys.dont_write_bytecode = True`. `proto/__pycache__/` still holds only the four
`.pyc` files from 2026-08-19.

---

## 9. Bearing on the NO-GO

**This came out in the spike's favour, and I am saying so as plainly as I would have said the
opposite.**

The direct effect is on one named leg. `FINDINGS.md`'s own leg-strength table (the row *"the
fixture-adequacy leg"*) records it as **firmer** with this stated reason:

> 130/130 was scored by a harness whose "compiled and diverges" and "did not compile" branches
> have **never been emitted, only inferred**

That reason no longer holds. They have now been emitted, correctly, through the real per-case
loop. So the fixture-adequacy leg loses this particular support and returns to resting on what
`FINDINGS.md` §5.2 and §5.7 argue on their own terms — that the fixture covers **68 of 130
(52.3%)** of the corrected subset and was never built to be an acceptance test for a third
runtime. That argument is untouched by anything here, and it was always the stronger half.

So: **one NO-GO leg is slightly weakened; the ruling is unchanged.** 130/130 was never what the
NO-GO rested on — it was the pro-GO fact the NO-GO had to account for, and it now stands as a
credible fact rather than a possibly-hollow one. The load-bearing legs are elsewhere: the
performance leg (3.79×–7.15×), the divergence register's 18 undetectable classes of 33, the
FRAMING §5 *raise → value* breach (8 mechanisms, unchanged), and the fixture-adequacy argument on
its own merits. None of them are touched by this section.

The one thing that would have changed the ruling is the result I did not get. Had the rig scored
`DID_NOT_COMPILE` as a pass, `FRAMING.md` §8's warning would have been realised inside the spike,
every downstream conformance number would have been void, and the correct move would have been to
re-run the spike rather than rule on it. That is not what happened.
