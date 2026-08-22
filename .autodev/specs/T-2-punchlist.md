# T-2 build punch list

Sixteen items the sixth spec review found and deliberately did NOT refuse the spec over.
None of them meets the signing bar (a wrong number shown silently, something that would not run,
unauthorised scope, or a control nobody could tell was broken). They are carried into the build.

**Whoever builds T-2 reads this alongside `.autodev/specs/T-2.md`.** Several are real implementation
questions the spec leaves ambiguous; resolve each one before writing the code it touches, and
record how you resolved it. Items 2, 3, 4 and 5 in particular describe SQL that will not run as
the spec implies — they were judged non-blocking because the spec's own acceptance criteria would
catch them during the build, not because they are harmless.

---

### 1.

§7.1's time-bucket rule prints two code fences that both end `AS "bucket"` — the bare `date_trunc(...)` and the `to_char(...)` label. Only one column is emitted (§7.3 and AC-43(c) settle it as the text label). Relabel the first fence as the inner expression, because a build that emits both gets `ORDER BY "bucket" is ambiguous`.

### 2.

§4.4 row 6 says a previously-defined alias reaches "the aggregate as SQL text". Postgres will not resolve a SELECT-list alias inside an aggregate in the same SELECT (`SELECT expr AS busy, sum(busy)` fails). §7.2 item 5 already pins the runnable form — re-emit the compiled expression — so make row 6 say that. ORDER BY and GROUP BY alias references are fine as written.

### 3.

Operation 9 is described as a filter ("show only rows that changed") and emitted as a flag column `AS "changed"`. A window function cannot appear in `WHERE`, so the filtering pass needs a subquery or CTE around the flag. The document never says so; AC-40(a) counts kept rows as though it does.

### 4.

Operations 7, 8 and 9 hard-code `ts` and `sender_id`, which exist only on `noun:Heartbeat`. On `noun:Sample` and `noun:EdgeCase` they degrade to one partition, one NULL bucket and a whole-record comparison — identically on both panes, so no wrong number, but meaningless output from a control the reader is being taught to trust. AC-25 asserts only reachability. Either restrict those three operations to the heartbeat or define a per-collection ordering and partition key.

### 5.

Nothing pins which operation combinations are legal. Operation 7's `GROUP BY` alongside an ungrouped computed column or an ungrouped sort field raises. The UI has to disable the illegal combinations or the spec has to name them.

### 6.

`extra_float_digits = 1` (§4.9) is a decision Evan deferred to T-3, and it is the one pinned session value with no R-number, while its twin — the session time zone — has R15. §14.1's promise is that nothing here is unattributed; give it an R or state explicitly why a session value the SQL pane displays needs none.

### 7.

§7.2 does not say how the Python pane constructs its `Decimal`s. `Decimal(float)` carries the binary value; `Decimal(str)` carries the JSON text. Harmless on the heartbeat's integer `load`, drift-prone on `noun:Sample`'s 4-decimal `field_n` floats. Pin the string route, next to the `bool`-is-an-`int` trap the same item already names.

### 8.

§8.5 does not say how `demo/expected-answers.json`'s numbers are produced. If the seed computes them with the same code as the Python pane, then for step 6 — the one walkthrough number with no per-pane absolute assertion — AC-31 is checking the pane against itself.

### 9.

AC-45(b) requires inserting a row into a scratch collection, but §4.4 row 7 closes the source choice to the three seeded collection names. That half therefore has to run below the UI, against the server's field-name reader and the validator directly. Say so, or the criterion reads as unreachable through the screen it describes.

### 10.

§4.10's "Cost and freshness" states that nothing writes to `demo.records` while the demo runs except AC-23(a)'s mutation — but AC-45(b) inserts a row. Reconcile the two, and say who cleans it up before AC-38(b) counts 10,410 rows.

### 11.

§4.5's probe is built by compiling operand sub-ASTs separately, and each separately compiled fragment restarts its bind-parameter numbering at `p0`. Nothing says how the demo namespaces the fragments before they are OR-ed into one statement.

### 12.

Part counts are wrong in three places: AC-40 announces "four parts" and lists (a)-(e); AC-41 announces "three parts" and lists (a)-(e); AC-13 says "all four witnesses §8.3 names" where §8.3's table has five rows.

### 13.

AC-2(c) lists `PGSERVICE` among the poisoned environment variables; §11.2's list has `~/.pgpass` and not `PGSERVICE`. Make them one list.

### 14.

§7.4 calls `measurements.json → tolerant_key_probe` "a test that currently fails". It is a divergence probe recording `agree: false`, `path_a_ids ["T-1","T-2","T-3"]` against `path_b_ids ["T-1"]`. The substance is right; the word "test" is loose in a document that is strict about this elsewhere.

### 15.

§5 renders the guard as `1.797693134862316e+296`. That is the source file's own float8 rendering; the literal's exact value is `1.7976931348623157e+296`. Harmless, but the document insists on full digits everywhere else.

### 16.

Glossary gaps for the stated audience (fluent Python, shaky on ad-hoc SQL): `LATERAL`, `IS DISTINCT FROM`, `NULLS LAST`, `to_char`, `PRIMARY KEY`, SQLSTATE `22P02`, "stable sort", "allowlist" / "fails closed", "closed set", and "parameterised statement" (only "bind parameter" is glossed).
