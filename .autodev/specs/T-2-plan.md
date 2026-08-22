# T-2 — Build plan

**Everything a competent worker needs to build the demo without re-deriving a decision.**

| | |
|---|---|
| Ticket | `T-2` · stage `plan` · pipeline `feature@v1` + `design@v1` |
| Written | 2026-08-22 |
| Process | **FULL** — `.autodev/shop.json → settings.lean = false` (GA-6, wrap-up item 5). The build runs in an **isolated git worktree** |
| Reads | `.autodev/specs/T-2.md` (signed) · `.autodev/specs/T-2-punchlist.md` (16 items) · `.autodev/specs/T-2-locate.md` (the file tree, this machine's versions, eleven further gaps) · `design/t2-demo.md` + `design/t2-demo-mock.html` (**approved as drawn**) |
| Authority for the rulings below | Evan, 2026-08-22, wrap-up item 26 default and his standing instruction *"use your best judgement and previously answered questions for guidance"* (GA-6); and GA-4, *"I feel like these questions can be answered with your best judgement"* |

---

## 0. How to read this

**Numbering.** The spec's rulings are `R1…R19`. The design brief's are `D1…D15`. **This document's
are `B1…B32`**, deliberately separate so a citation cannot collide.

| | |
|---|---|
| **B1…B16** | the sixteen punch-list items, **one to one, in the punch list's own order** (§1, §2) |
| **B17…B25** | the nine locate findings `L1…L9` (§3). `L10` and `L11` fall inside `B3` and `B5` and are resolved there as `B3b` and `B5c` |
| **B26…B27** | two seed decisions the spec leaves open (§5) |
| **B28…B32** | the five open look-questions of `design/t2-demo.md` part 9, which the brief leaves to the build (§5.6) |

**Every B is a ruling on delegated authority** — a decision this document took *for* Evan, not one he
made. Each shows its derivation and each carries **the one line that overturns it**. Three of them
(**B4**, **B5a**, **B6**) are visible product choices rather than implementation detail, and the
handoff names them so he can rule them himself if he would rather.

**A bare §** means a section of `.autodev/specs/T-2.md`. **Part n** means `design/t2-demo.md`.
**AC-n** are the spec's 45 acceptance criteria.

**The order to read this in if you are about to write code:** §1 (the four that will not run),
then §4 (the four statement shapes and the pipeline order — the query builder's whole contract),
then §6 (the work items). Everything else is reference.

**Words used here, because two of them are the whole ticket.** A **bind parameter** is a value handed
to Postgres separately from the SQL text rather than pasted into it — the safe way, and the way SQL
injection does not happen. A **window function** is SQL that judges a row against its neighbours (a
rolling average; "what did the previous row say"). A **CTE** — *common table expression* — is a named
sub-result written `WITH name AS (…)` in front of a query, so the outer query can treat it as a
table; it is how you filter on something a window function computed, because SQL will not let a
window function appear in a `WHERE`. A **SQLSTATE** is the five-character code Postgres puts on every
error so a program can recognise which error happened without reading the English beside it.

---

## 1. The four punch-list items that describe SQL which will not run

These four are the most valuable thing in this document. For each: **what the spec implies**,
**why that fails** (with the error Postgres actually raises), and **what runs instead**, written out
so no build has to invent it.

Three of the four make Postgres raise. The fourth runs, produces output, and the output is
meaningless — which is worse, because nothing on the screen says so.

---

### B2 — punch-list 2 · a SELECT-list alias inside an aggregate

> **§4.4 row 6** says the aggregate's field may be *"a **previously-defined alias**, which reaches
> `ORDER BY` / `GROUP BY` / **the aggregate** as SQL text"*.

**Why it fails.** Postgres resolves SELECT-list aliases in `GROUP BY`, `ORDER BY` and `HAVING` — a
documented Postgres extension — and **nowhere else**. It does **not** resolve them inside the
`SELECT` list itself, and it does not resolve them in `WHERE`. So

```sql
SELECT to_jsonb(xpr.ord('>', (data -> 'load'), to_jsonb(80::float8))) AS "busy",
       sum("busy")
  FROM demo.records;
```

raises **`ERROR: column "busy" does not exist`** — SQLSTATE **`42703`**. This is not a corner case:
walkthrough step 6 aggregates a field, and the moment anyone aggregates a *computed column* instead
of a JSON field, the pick dies.

**§7.2 item 5 already pins the runnable form and §4.4 row 6 contradicts it.** Item 5 says `<j>` — the
thing the numeric read wraps — is one of exactly two things: `data #> %(path)s`, or *"the compiled
expression of a previously-defined computed column"*. **The compiled expression, not its name.**

**THE RULING (B2).** **The aggregate never references an alias. It re-emits the compiled expression
inline**, wrapped in §7.2 item 5's numeric read:

```sql
round(
  sum(
    CASE WHEN jsonb_typeof( <compiled expression of the chosen computed column> ) = 'number'
         THEN ( <the same compiled expression> #>> '{}' )::numeric
    END
  ), 6
) AS "agg"
```

`ORDER BY` and `GROUP BY` alias references stay exactly as §4.4 row 6 writes them — those are legal
and are not touched.

**Two consequences that make this cheaper than it looks.**

1. The compiled expression appears **twice** inside the numeric read. Its bind parameters are named
   `%(p0)s`-style, and a named placeholder may appear any number of times in one statement — the
   driver substitutes each occurrence. No duplication of parameters is needed. (What *does* need care
   is two *different* fragments both naming `p0`; that is **B11**.)
2. Under **B5a** a computed column is not even *emitted* when an aggregate is chosen — it is a
   definition, usable as the aggregate's field, and nothing else. So in the shape where B2's failure
   would have happened there is no alias in the statement at all. **The bug is removed by
   construction, not merely worked around.**

**One line to overturn.** *"Let me aggregate the column by name"* — which requires wrapping the row
query in a CTE so the alias becomes a real column, at the cost of one extra query level on every
aggregate pick.

---

### B3 — punch-list 3 · operation 9 filters on a window function

> **Operation 9** is described as a filter (*"show only rows that changed"*) and §7.3 emits it as a
> **flag column** `… AS "changed"`. Nothing in the document ever filters on the flag, and
> **AC-40(a) counts kept rows** as though something does.

**Why it fails.** A window function may not appear in `WHERE`. Postgres raises
**`ERROR: window functions are not allowed in WHERE`**, SQLSTATE **`42P20`** — because `WHERE` is
evaluated *before* the window pass, so at the time the predicate runs the window has not been
computed. The same is true of `GROUP BY` and `HAVING`.

**THE RULING (B3).** **Operation 9's flag is computed in a CTE and filtered in the outer query.**
The statement, written out — this is the demo's ROWS shape with operation 9 on:

```sql
WITH picked AS (
  SELECT r.collection,
         r.key,
         r.data,
         <computed column 1>  AS "alias1",            -- op 2, zero or more
         avg( <numeric read of the window field> )
           OVER (w ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)  AS "rolling_avg",   -- op 8, if on
         ( lag( r.data - 'ts' ) OVER w
             IS DISTINCT FROM ( r.data - 'ts' ) )     AS "changed"
    FROM demo.records AS r
   WHERE r.collection = %(collection)s
     AND xpr.truthy( <compiled filter expression> )   -- op 3, if present
  WINDOW w AS (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key)
)
SELECT collection, key, data, "alias1", "rolling_avg"
  FROM picked
 WHERE "changed"
 ORDER BY ( data #> %(sort_path)s ) DESC NULLS LAST, key ASC     -- op 4, or just: ORDER BY key ASC
 LIMIT %(cap)s;                                                   -- op 5, if set
```

**Six details this form pins, each of which is a divergence or a raise if a build guesses.**

1. **`WHERE "changed"` in the outer query is legal** precisely because `changed` is an ordinary
   column of the CTE by the time the outer query runs. This is the whole reason for the CTE.
2. **`changed` is never NULL**, so `WHERE "changed"` needs no `IS TRUE`. `lag()` returns NULL at each
   sender's first beat, and `NULL IS DISTINCT FROM x` is **true** — which is exactly how "each
   sender's first beat is always kept" falls out of the operator instead of a special case. A build
   that writes `<>` instead drops all 50 first beats and fails **AC-40(d)**.
3. **`changed` is not emitted by the outer `SELECT`.** After the filter it is `true` on every
   surviving row, so showing it is a column of noise. It still counts as a name the builder emits, so
   **§4.10's collision list keeps `changed` forbidden as an alias** — the collision would be inside
   the CTE, where it is just as fatal.
4. **The filter (op 3) is inside the CTE, so the window sees only the rows that survived it.** That
   is the only order SQL permits, and the Python pane must do the same: filter first, then walk the
   groups. A Python runner that computes `changed` over the unfiltered rows and filters afterwards
   disagrees on every row adjacent to a filtered-out one.
5. **`LIMIT` is in the outer query, so it caps *kept* rows**, not scanned rows. Python caps last too.
6. **`WINDOW w AS (…)` is written once and used twice.** Operations 8 and 9 share one frame by R9;
   naming it makes that structural rather than a coincidence of two copies staying in step.

**When operation 9 is off, there is no CTE.** A window function in the `SELECT` list needs no
wrapping — operation 8 alone is a plain single-level statement. The builder emits the CTE **if and
only if** operation 9 is on. (One statement level fewer is not the point; the point is that the SQL
pane shows the reader the simplest true statement for the pick they made.)

**AC-40(a) now works as written:** the kept-row count is a real count of returned rows, on each pane
separately, and the band is 700–1,100 of 8,400.

#### B3b — AC-40(c) as written is unsatisfiable, and here is the test that means what it meant

**AC-40(c)** requires a grep over operation 9's SQL asserting it *"contains **no arithmetic operator
at all**"*. But the same criterion requires the expression `data - 'ts'`, **which contains a `-`**.
Read literally, the criterion fails on its own required text. (`-` there is jsonb key-deletion; it is
not arithmetic.)

**THE RULING (B3b).** The assertion is **that operation 9's compared value does no arithmetic**, and
it is tested as three positive facts plus one negative, not as a character grep:

- the compared expression is exactly `data - 'ts'`, appearing **twice** (inside `lag()` and beside
  `IS DISTINCT FROM`);
- the comparison operator is **`IS DISTINCT FROM`**, and the string `<>` does not appear in it;
- with the two literal `data - 'ts'` occurrences removed from the text, **no `+`, `-`, `*`, `/`,
  `xpr.div`, `xpr.num`, `xpr.f8`, `sum(`, `avg(` or `::numeric` remains** in operation 9's fragment.

That last form is a grep, it is decidable, and it fails for exactly the reason AC-40(c) exists: an
operation 9 that started doing arithmetic on the compared value.

**One line to overturn B3.** *"Show me the changed flag as a column instead of filtering"* — the CTE
disappears, the flag is displayed, and AC-40(a)'s count becomes a count of `true` values rather than
of rows. Everything else stands.

---

### B4 — punch-list 4 · operations 7, 8 and 9 hard-code fields only the heartbeat has

> Operations 7, 8 and 9 are written against **`ts`** and **`sender_id`**. Those fields exist on
> **`noun:Heartbeat` only**. On `noun:Sample` and `noun:EdgeCase`, `data ->> 'sender_id'` is NULL for
> every row and `data ->> 'ts'` is NULL for every row.

**Why it is the dangerous one.** It **does not raise.** `PARTITION BY NULL` is one partition;
`ORDER BY NULL, key` degrades to `ORDER BY key`; `date_trunc('day', NULL::timestamptz)` is NULL, so
every row lands in **one NULL bucket**; and `data - 'ts'` on a record with no `ts` is the whole
record, so operation 9 compares whole records and keeps everything that is not a byte-identical
neighbour. All of that happens **identically on both panes**, so **the side-by-side agrees** — §5's
control stays green — and the screen shows a person a number produced by a control that is doing
nothing it claims to do. AC-25 asserts only that the controls are *reachable*.

That is the exact failure this project exists to prevent, arriving through the UI instead of through
the arithmetic.

**THE RULING (B4). Restrict operations 7, 8 and 9 to `noun:Heartbeat`, and say so on the screen.**

This is **not a new decision** — it is `design/t2-demo.md` part 3.1.2 rule **X1**, ruled under D15,
**drawn in the mock**, and **approved as drawn by Evan on 2026-08-22 under GA-6**. The mock's
measured behaviour (part 11): changing the source select from `noun:Heartbeat` to `noun:EdgeCase`
takes the disabled count from 0 to 3, keeps focus on the select, and states the collection's actual
field list as the reason. The build reproduces that.

**Why restrict rather than define per-collection keys** — the punch list offers both:

- `noun:Sample` has no ordering key that means anything. `due_date` is a due date, not an event time,
  **5% of rows omit it entirely** (`gen_data.py:30-31`), and there is no sender-like key to partition
  on. A rolling average "per nothing, ordered by a date 5% of rows do not have" is a number nobody
  can check — against Q21's *"correct and readable only"*.
- `noun:EdgeCase` is **10 rows**, each a deliberate hostile witness. Bucketing it by time is
  meaningless by construction.
- Inventing keys would put a *second* set of ordering conventions into a document whose §7.1 spends
  three ruling boxes pinning **one** set so the two panes cannot drift.
- The restriction costs the demo nothing: the heartbeat is the default source and the collection
  every walkthrough step that uses ops 7–9 already runs on.

**What the build owes AC-25.** AC-25 requires all nine operations reachable and asserts the shape of
7, 8 and 9. Under B4 the UI test gains one part: on `noun:Heartbeat` all nine are **enabled**; on
`noun:Sample` and `noun:EdgeCase` operations 7, 8 and 9 are **disabled with `.op-why` stating the
collection's field list**. Reachability is satisfied on the heartbeat; the disable is a `DR-2`
obligation, not an evasion.

**One line to overturn.** *"Let me bucket and window the other collections too"* — the build then
owes a per-collection ordering key and partition key for each, plus the short-window and first-row
conventions for each, plus AC-24(d) and AC-40 re-derived per collection. Stated so the cost is not a
surprise.

---

### B5 — punch-list 5 · nothing pins which operation combinations are legal

> *"Nothing pins which operation combinations are legal. Operation 7's `GROUP BY` alongside an
> ungrouped computed column or an ungrouped sort field raises. The UI has to disable the illegal
> combinations or the spec has to name them."*

**Why it fails, precisely.** Postgres raises **`ERROR: column "…" must appear in the GROUP BY clause
or be used in an aggregate function`** — SQLSTATE **`42803`** — for every ungrouped column in a
grouped or aggregated `SELECT`, and for every ungrouped expression in that query's `ORDER BY`. It
raises **`ERROR: window functions are not allowed in GROUP BY`** (`42P20`) for a window function in
a grouped query. And `PARTITION BY (data ->> 'sender_id')` inside an aggregated query is itself an
ungrouped reference to `data`, so it raises `42803` too.

Design part 3.1.2 names **two** rules (X1, X2) and does not claim to be exhaustive — the punch list
is the record that the *spec* names none.

**THE RULING (B5a). A pick has exactly one of three shapes, and the shape decides every control.**

| | **ROWS** | **SCALAR** | **BUCKET** |
|---|---|---|---|
| **entered by** | op 6 = `none`, op 7 = `off` | op 6 = a function, op 7 = `off` | op 7 = `hour` or `day` |
| **the answer is** | a list of rows | one number | a derived table: label + number per bucket |
| **1 source** | required | required | required, **`noun:Heartbeat` only** (B4) |
| **2 computed columns** | **emitted** as `AS "alias"` columns | **defined, not emitted** — usable only as op 6's field, re-emitted inline (B2) | **defined, not emitted** — same |
| **3 filter** | available | available | available |
| **4 sort** | available | **disabled** — "an aggregate returns one row; there is nothing to sort" | **disabled** — "bucketed results are ordered by the bucket" (X2, §7.1's time-bucket rule) |
| **5 row cap** | available | **disabled** — "an aggregate returns one row" | available — caps buckets |
| **6 aggregate** | `none` | the chosen function; a field is required unless the function is `count` | the chosen function; **may not be `none`** (B5c) |
| **7 time bucket** | `off` | `off` | `hour` or `day` (Q20's own two, closed set) |
| **8 rolling window** | available (heartbeat only) | **disabled** — X2: op 6 emits one `AS "agg"` for the whole result, op 8 emits one `AS "rolling_avg"` per row, and one statement cannot emit both | **disabled** — a window's `PARTITION BY` reads ungrouped `data` in a grouped query (`42803`) |
| **9 changed rows** | available (heartbeat only) | **disabled** — "one row has no predecessor" | **disabled** — same `42803`, and a bucket has no predecessor |

Plus the one rule that lives *inside* an operation, already drawn in the mock: **with `count` chosen,
operation 6's field picker is disabled**, because `count` counts rows and takes no field.

**THE RULING (B5b). Every disable is a `DR-2` disable, not a submit-time refusal.** Design's DR-2:
*"the screen disables that operation's control and states the reason beside it. It never leaves a
control live that will be refused on submit, and it never disables one silently."* The reason text
goes in `.op-why`, and it names the other operation that caused it — *"unavailable while the
aggregate is set: one statement cannot return both a total and a per-row value"* — never "invalid
combination".

**THE RULING (B5c) — locate finding L11. `BUCKET` requires an aggregate.** §7.1's time-bucket rule
says *"What aggregates inside a bucket is operation 6's chosen function"*; nothing says what happens
when there is none. Switching operation 7 on while operation 6 is `none` **sets operation 6 to
`count`**, visibly, in the control — the field picker greys (it is `count`), and `.op-why` reads
*"a bucket has to count or total something; set to `count`"*. It is never left at `none`, and it is
never silently defaulted behind the person's back. Derivation: walkthrough step 7 is literally *"Time
bucket by day, **count** per bucket"*, so `count` is the value his own walkthrough already assumes.

**One line to overturn B5a/B5b/B5c.** *"Let me try any combination and tell me afterwards"* — every
disable becomes a submit-time refusal, which is the shape §4.4 spends its length arguing against, and
DR-2 and D15 are rewritten. *"Show my computed columns beside the total"* is the narrower line and it
costs a CTE on every aggregate pick.

**One thing about B5a that is a visible product choice, stated so Evan can take it back.**
The mock's `V2` (time buckets) draws **two** operations disabled — operation 4 and operation 8, which
are exactly X2's two. Under B5a a bucketed pick disables **three**: operation 9 as well, because a
window function's `PARTITION BY` over ungrouped `data` raises `42803`. So the built screen greys one
more row than the drawing does, in one of seven states. That is an extension of the drawn rule, not a
contradiction of it — part 3.1.2 derives X1 and X2 from the spec and never claims the pair is
exhaustive, and the punch list exists because the spec names none. It is called out here because
"approved as drawn" deserves to be told where the build goes past the drawing. **One line to
overturn:** *"Leave operation 9 available on a bucketed pick"* — and the pick then raises `42803` on
submit, so that line really means *"go back to submit-time refusals"*.

---

## 2. The other twelve punch-list items, resolved

---

### B1 — punch-list 1 · two code fences both ending `AS "bucket"`

§7.1's time-bucket rule prints the bare `date_trunc(…) AS "bucket"` and then the `to_char(…) AS
"bucket"` label. A build that emits both gets **`ERROR: ORDER BY "bucket" is ambiguous`** (SQLSTATE
`42702`), and — worse — §4.10's collision list would be protecting one name against two columns.

**THE RULING (B1). Exactly one column named `bucket` is emitted, and it is the text label.** The
`date_trunc(…)` is the *inner expression*; it never carries an alias of its own. §7.3 and AC-43(c)
already settle it as the text label; this makes the emission match. Written out:

```sql
SELECT to_char( date_trunc('day', (data ->> 'ts')::timestamptz) AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS"Z"' )                      AS "bucket",
       round( <the aggregate over the numeric read> , 6)             AS "agg"
  FROM demo.records
 WHERE collection = %(collection)s
   AND xpr.truthy( <compiled filter> )        -- op 3, if present
 GROUP BY "bucket"
 ORDER BY "bucket"
 LIMIT %(cap)s;                               -- op 5, if set
```

with `'hour'` for the other granularity — a fixed keyword from §4.4 row 7's closed set, never user
text.

**Grouping and ordering by the label rather than by the timestamp is correct, not a shortcut.** The
label is fixed-width UTC ISO-8601, so it is injective on truncated instants and its **text order is
time order** — that is precisely the property R15 chose the format for, and §7.4 pins the `C`
collation so the ordering is byte order on both panes. `GROUP BY "bucket"` on a SELECT-list alias is
the same Postgres extension `ORDER BY "bucket"` uses. **AC-43(a)'s grep still finds
`date_trunc(<granularity>, (data ->> 'ts')::timestamptz)` in the builder** — it is inside the
`to_char`.

**One line to overturn.** *"Group by the timestamp and label it separately"* — two columns, the
label aliased `bucket` and the timestamp unaliased in `GROUP BY`; equivalent, one column longer, and
it re-opens the ambiguity the moment someone aliases the second one.

---

### B6 — punch-list 6 · `extra_float_digits = 1` has no R-number

§14.1's promise is that nothing in the spec is unattributed. The session **time zone** has R15; its
twin, the digit setting the SQL pane displays, has nothing.

**THE RULING (B6). It gets one here, and this is it.** `extra_float_digits` is **set to `1` on every
connection the demo opens**, and the SQL pane **displays the value it ran at** and makes **no claim
that 1 is the right value**. Derivation, entirely from what is already recorded:

- **Q10's answer was *"Make the correctness run test all three settings"*** — he sent the question to
  T-3 rather than settling it. So the demo may not assert a rule.
- **T-1's whole 130/130 result was obtained at `1`** (`coverage_probe.py:111`,
  `idxshape_immutable.sql:3`). Running the demo at any other value would put it on ground nothing has
  been measured on, for no gain.
- **`1` is also the modern Postgres default**, so pinning it changes nothing about what a reader would
  otherwise have seen — it removes the possibility that a container's environment supplied something
  else without saying so.
- **Displaying it is what discharges Q10 honestly**: the screen states the setting, so a reader can
  tell that the number they are looking at was produced at a particular one.

**When T-3 answers, this ruling is superseded by T-3's finding**, not by a new judgement here. If
T-3 finds a value at which the two engines disagree, the demo's displayed value becomes evidence
rather than trivia.

**One line to overturn.** *"Run the demo at `extra_float_digits = 0`"* (or `2`, `3`) — one constant
in `demo/server/settings.py`, and the SQL pane shows the new value. Nothing else changes.

---

### B7 — punch-list 7 · how the Python pane constructs its `Decimal`s

`Decimal(float)` carries the binary value — `Decimal(0.1)` is
`0.1000000000000000055511151231257827021181583404541015625`. `Decimal(str)` carries the decimal text.
Harmless on the heartbeat's integer `load`; **drift-prone on `noun:Sample`'s 4-decimal `field_n`
floats** (`gen_data.py:41` writes `round(uniform(-1000,1000), 4)`), where Postgres's `numeric` holds
the decimal digits and Python's `float` does not.

**THE RULING (B7). The Python pane never sees a float where a number matters. Rows arrive as JSON
*text* and are parsed twice.**

`demo/pyrunner/rows.py` selects `data::text` alongside `collection` and `key`, and for each row
produces **two** parses of the same string:

| parse | how | who consumes it |
|---|---|---|
| **`record_f`** | `json.loads(raw)` — ordinary floats | **the vendored `expr.py` evaluator only** (operations 2 and 3). It must see exactly what GIMS's evaluator would see; §7.2 keeps the compiler's expressions in `float8` for the same reason, and §5's defect has to stay visible |
| **`record_d`** | `json.loads(raw, parse_float=decimal.Decimal)` | **the numeric read** for operations 6, 7 and 8, **and operation 9's comparison** |

**Why operation 9 uses the Decimal parse too, which the punch list does not ask for and which is the
better answer.** jsonb stores numbers as `numeric`, exactly. Two records differing only past float
precision compare **unequal** in jsonb and **equal** in Python floats. The seeded heartbeat's `load`
is an integer 0–100 so it cannot bite today, but operation 9's whole job is deciding whether two
records are the same, and doing that on a lossy parse is a divergence waiting for a different seed.

**The `bool` trap, restated because it is one character.** A value counts as numeric only if it is an
`int` or a `float`/`Decimal` **and `isinstance(v, bool)` is false**. Python's `bool` subclasses `int`,
so a bare `isinstance(v, (int, float))` scores `True` as 1 while `jsonb_typeof` calls it `'boolean'`
and the SQL side scores it as nothing. §7.2 item 5 already names this; the check lives once, in
`demo/pyrunner/decimals.py`, and every caller uses it.

**Cost.** Two `json.loads` over at most 8,400 small rows. Affordable for the same reason everything
else here is (Q21 kept the data small; §6 forbids a speed claim).

**One line to overturn.** *"Just use floats on the Python side"* — and step 8's digit-for-digit
agreement (AC-24(a)) becomes unachievable on any collection with fractional data.

---

### B8 — punch-list 8 · `expected-answers.json` may be checking the pane against itself

§8.5 does not say how the file's numbers are produced. If the seed computes them with the same code
as the Python pane, then for **step 6** — the one walkthrough number with no per-pane absolute
assertion — **AC-31 is a tautology**.

**THE RULING (B8). `demo/seed/expectations.py` is a third, independent path, and a test enforces
that it is.**

1. **It may import nothing from `demo/pyrunner/`, `demo/builder.py` or `demo/probes.py`.** A test in
   `demo/tests/test_walkthrough.py` walks `expectations.py`'s AST and fails on any such import. That
   is the assertion that cannot be satisfied by good intentions.
2. **It computes from the generator's own in-memory model**, not by querying the database and not by
   running a pick. `demo/seed/generate.py` returns the rows it created; `expectations.py` sums,
   groups and walks them with plain Python. Three independent producers therefore exist for every
   walkthrough number: **the SQL**, **the Python pane**, and **the seed's own arithmetic**.
3. **Every entry carries a `derivation` string** saying how the number was reached — e.g.
   `"8400 = 50 senders x 7 days x 24 hours (R5, R17)"`, `"7 buckets x 1200 = 50 x 24"`. A number
   whose derivation is *"whatever the code returned"* is not admissible, and the reviewer reads that
   field.
4. **Step 6 gains the per-pane absolute assertion it lacked.** The sum of `payload.load` over 8,400
   rows is asserted against `expectations.py`'s figure **on each pane separately** before the panes
   are compared — the same shape AC-40(a) and AC-24(d) already use, and for the same reason.

**One line to overturn.** *"Drop the expected-answers file"* — §14.2 item 1 is his to answer; if he
drops it, the walkthrough carries its numbers inline and B8 applies to whatever produces those.

---

### B9 — punch-list 9 · AC-45(b) is unreachable through the screen it describes

AC-45(b) inserts a row into a **scratch collection** and asserts its key is refused as an alias — but
§4.4 row 7 closes operation 1's source to the **three seeded collection names**, so no scratch
collection can be chosen on the screen.

**THE RULING (B9). AC-45(b) is a server-level test, and the criterion says so.** It calls
`demo/server/app.py`'s field-name reader and `demo/gate.py`'s `validate_alias()` **directly**, with
the collection name passed as an argument — which is exactly the surface the UI would use. The closed
set at §4.4 row 7 is a property of *what the screen offers*, not of what the reader can be asked
about, and B9 makes that explicit rather than leaving the criterion reading as a UI step.

**The half that matters is preserved in full:** a hard-coded list still cannot pass, because the key
inserted is one no seeded row carries and the assertion is that it is refused. That is the whole
point of (b), and it survives moving below the UI.

**How the scratch row is inserted and removed** is **B10**.

**One line to overturn.** *"Let me pick any collection on the screen"* — operation 1 becomes an open
text field, which adds a row to §4.4's inventory and a closed-set-to-free-text change nobody asked
for.

---

### B10 — punch-list 10 · two criteria write to `demo.records` and a third counts it

§4.10 states that nothing writes to `demo.records` while the demo runs **except AC-23(a)'s
mutation** — but **AC-45(b) inserts a row**, and **AC-38(b) asserts 10,410 rows afterwards**, and
**AC-10 checksums every row**.

**THE RULING (B10). Every write the suite makes is inside a transaction that is rolled back, and the
suite proves the database came back unchanged.**

| write | how | why that shape |
|---|---|---|
| **AC-45(b)'s scratch row** | `BEGIN; INSERT … VALUES ('noun:__scratch__', …); <run the two assertions on this connection>; ROLLBACK;` | Nothing is ever committed, so no ordering between tests matters and no cleanup can be forgotten. The field-name reader and the validator both run **on the same connection**, inside the transaction, so they see the row |
| **AC-23(a)'s mutation** | The pick has to be re-run *through the API*, which uses its own connection, so a transaction cannot contain it. Instead: record the original `data`, `UPDATE`, re-run the pick, assert both panes moved, then **`UPDATE` back to the recorded value** in a `finally` | The one write that must be committed, so it is the one that must be explicitly undone |
| **the guard** | `demo/tests/conftest.py` asserts **AC-10's checksum** — `md5` over all rows ordered by `(collection, key)` — **at session start and again at session end**, and fails if they differ | This is what turns "we remembered to clean up" into a checked fact. A future test that writes and forgets fails here rather than corrupting AC-38(b) two runs later |

§4.10's sentence is then true as written for **the running demo** (nothing writes), and the suite's
two writes are bounded and proven reverted.

**One line to overturn.** *"Just reseed between tests"* — correct but slow, and it hides a leaking
write rather than catching it.

---

### B11 — punch-list 11 · every compiled fragment restarts its bind parameters at `p0`

Verified by reading the file: `_Compiler.__init__` sets `self._n = 0` and `_bind` returns
`f"p{self._n}"` (`compile.py:159-164`); `compile_ast` constructs a fresh `_Compiler` on every call
(`:437`). So **two computed columns and a filter produce three fragments that all name their first
parameter `p0`**, with different values. Merged into one statement they silently overwrite each other
— and the surviving value is applied to *all* of them.

**That is a wrong number that runs clean**, which is this project's defined failure mode. It is
also §4.5's problem: the probe compiles operand sub-ASTs separately and `OR`s them into one
statement.

**THE RULING (B11). One namespacing function, applied to every fragment, in one place.**

`demo/builder.py` exposes:

```python
def namespace(frag: Compiled, prefix: str) -> tuple[str, dict]:
    """Rewrite compile.py's p0,p1,… into <prefix>_p0,… in both the SQL and the params."""
```

- The rewrite is `re.sub(r"%\((p\d+)\)s", rf"%({prefix}_\1)s", frag.sql)`, and the params dict is
  re-keyed to match. It is a transform on the compiler's **output**; `compile.py` is not edited and
  **AC-33 is unaffected**.
- **The `ctx` parameter needs no rewrite** — `compile_ast` takes `ctx_param` as a keyword, so each
  fragment is compiled with `ctx_param=f"{prefix}_ctx"` and the collision never arises.
- **The prefixes are fixed and mechanical**, so the SQL pane reads predictably:
  `cc0`, `cc1`, … for computed columns in the order they were entered; `flt` for the filter;
  `prbA0`, `prbA1`, … for member (a)'s operands; `prbB0`, … for member (b)'s; `agg` for the
  aggregate's field expression; `win` for the window field's.
- **Merging is checked, not assumed.** A unit test builds a pick with two computed columns and a
  filter whose literals are three *different* numbers, and asserts (i) the merged params dict has
  three distinct keys, (ii) no key appears twice with different values, and (iii) each fragment's
  placeholders in the final SQL all carry that fragment's prefix. A regression here would be exactly
  the silent-wrong-number class, so it gets an explicit test rather than being covered by end-to-end
  luck.

**One line to overturn.** *"Compile the whole pick in one pass"* — which means editing `compile.py`
to accept a list of ASTs, which Q19 forbids and AC-33 catches.

---

### B12 — punch-list 12 · three wrong part counts

**THE RULING (B12). The enumerations are authoritative; the announced counts are corrected here and
the build tests the list, never the number.**

| criterion | says | actually lists | corrected |
|---|---|---|---|
| **AC-40** | "four parts" | (a) (b) (c) (d) (e) | **five parts** |
| **AC-41** | "three parts" | (a) (b) (c) (d) (e) | **five parts** |
| **AC-13** | "all four witnesses §8.3 names" | §8.3's table has **five** rows | **five witnesses** — the fifth is *"boundary values just below the shipped guard"*, and it is the one that proves the guard's edge is where the file says it is |

**AC-13 therefore gains a fifth assertion**, and it is not filler: a row holding a value just below
`1.7976931348623157e+296` must survive `xpr.f8` (a number comes back) while a row just above it must
come back NULL. That pair is what makes §5's twelve-decade defect *visible as a boundary* rather than
as an anecdote about `1e300`.

---

### B13 — punch-list 13 · two different lists of poisoned environment variables

AC-2(c) names `AUTOSQL_SPIKE_DSN`, `PGHOST`, `PGPORT`, `PGPASSWORD`, **`PGSERVICE`**; §11.2 names
`AUTOSQL_SPIKE_DSN`, `PGHOST`, `PGPORT`, `PGPASSWORD`, **`~/.pgpass`**.

**THE RULING (B13). One list, and — more importantly — a mechanism that does not depend on the list
being complete.**

**The mechanism first.** `demo/server/db.py` **passes every libpq connection parameter explicitly**:
`host`, `port`, `dbname`, `user`, `password`, `sslmode`, `connect_timeout`, `application_name`.
libpq's environment variables are *defaults consulted only when the parameter is absent*, so with all
of them supplied **no environment variable can change where the demo connects** — including ones
nobody thought to enumerate. A test that only unsets known names can never prove that; passing them
all can.

**The list second**, as the union of the two, enumerated once in `db.py`'s docstring and poisoned by
the test: `AUTOSQL_SPIKE_DSN`, `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSWORD`, `PGPASSFILE`, `PGSERVICE`, `PGSERVICEFILE`, `PGSSLMODE`, `PGOPTIONS`, `PGCONNECT_TIMEOUT`
— **and `HOME` pointed at a temporary directory containing a hostile `.pgpass`**, which is the only
way to test the `~/.pgpass` half at all.

**And the assertion that makes it a fence rather than a hope:** `db.py` exposes exactly one function
that returns a connection, and it **raises** if the port it is about to dial is not `55440`. A grep
test asserts no other module in the demo tree imports `psycopg` directly.

---

### B14 — punch-list 14 · "a test that currently fails" is loose

§7.4 calls `measurements.json → tolerant_key_probe` *"a test that currently fails"*. It is a
**divergence probe** recording `agree: false`, `path_a_ids ["T-1","T-2","T-3"]` against
`path_b_ids ["T-1"]`. The substance is right; the word is loose in a document strict about this
elsewhere.

**THE RULING (B14).** Wherever the build repeats this — `demo/README.md`, `demo/WALKTHROUGH.md`, a
code comment near `demo/pyrunner/order.py` — it is written as: *"a recorded divergence probe
(`spikes/T-1/analysis/measurements.json → tolerant_key_probe`) in which GIMS's tolerant key matching
returns one id where the two-path comparison expected three"*. **The spec itself is not edited** —
it is signed, and this is a wording note, not a defect that changes behaviour. Its practical
consequence is unchanged: the demo does **not** port GIMS's comparator (R12).

---

### B15 — punch-list 15 · the guard literal's digits

**Verified mechanically today.** `spikes/T-1/proto/runtime.sql:33` and `:51` hold
`17976931348623157` followed by **280 zeros** — **297 digits**, i.e. the exact value
**`1.7976931348623157e+296`**. The spec renders it `1.797693134862316e+296`, which is that value's
float8 round-trip at 16 significant digits.

**THE RULING (B15). Punch-list 15 is right. The build writes `1.7976931348623157e+296` for the
shipped guard and `1.7976931348623157e+308` for the real limit**, in `demo/README.md`,
`demo/WALKTHROUGH.md` step 11 and the probe's own comment, and never mixes the two renderings.

**One consequence the build should know about, since it is the same family of detail.** §4.5's probe
threshold is written `>= 1.7976931348623157e+308::numeric`. As a `numeric` that literal is very
slightly **less** than the true `DBL_MAX` (whose exact decimal expansion is 309 digits long), so a
value of exactly `DBL_MAX` would be refused although it is representable. That is deliberate
conservatism — a refusal is never a wrong answer — and it cannot arise on the seeded data, which
carries `1e300` and `1e400` and nothing in between. **AC-17's two required behaviours are unaffected:
`1e300` must not trigger and `1e400` must.** Stated so a later reader does not "fix" it into a `>`.

---

### B16 — punch-list 16 · glossary gaps for the stated audience

The spec's audience is *fluent Python, shaky on ad-hoc SQL*. Ten terms are used without gloss.

**THE RULING (B16). `demo/WALKTHROUGH.md` opens with a glossary carrying exactly these ten**, each in
one sentence, each in Evan's register (no process jargon, no research shorthand — the standing note
in this repo's operator model):

| term | the sentence it gets |
|---|---|
| **`LATERAL`** | a join that lets the right-hand side see each row of the left — how "list the keys inside this record" runs once per record |
| **`IS DISTINCT FROM`** | "different, and NULL counts as a value" — unlike `<>`, which answers NULL when either side is NULL |
| **`NULLS LAST`** | where rows with no value go in a sort. Postgres's default flips with the direction, so this demo always says it out loud |
| **`to_char`** | turns a date or number into text in a format you specify |
| **`PRIMARY KEY`** | the column pair that identifies a row uniquely; the database refuses a duplicate |
| **SQLSTATE `22P02`** | the code Postgres uses for "that text is not a number" |
| **stable sort** | a sort that leaves equal items in the order they arrived. Python's is; Postgres's is not — which is why every result here carries a tiebreak |
| **allowlist / fails closed** | you list what is permitted, and anything not on the list is refused. The opposite of listing what is banned, which lets tomorrow's new thing through |
| **closed set** | the value must be one the screen itself offered — there is no way to type a fourth option |
| **parameterised statement** | the query text and the values travel separately; the values are never pasted into the text |

**Two more the build should add for the same reason**, because they appear in the SQL pane where he
will see them: **CTE** (`WITH … AS (…)` — a named sub-result the outer query reads like a table) and
**`AT TIME ZONE`** (re-reads an instant in a named zone).

---

## 3. The nine locate findings, resolved

`.autodev/specs/T-2-locate.md` §7 lists eleven gaps neither the spec nor the design settles. Two of
them (`L10`, `L11`) belong inside `B3` and `B5` and are resolved there. These are the other nine.

### B17 — L1 · 18 of the mock's 30 icons are not in GIMS's sprite

Measured today: GIMS's `static/icons.svg` carries **54** symbols; the approved mock draws **30**; the
overlap is **12**, and of those, **`i-play`, `i-plus` and `i-search` have different path data** in the
mock. The 18 that exist only in the mock include **`i-neq`** — one of DR-1's five independent
disagreement signals — and `i-shield`, `i-shield-stop`, `i-python`, `i-sigma`, `i-columns`,
`i-caret`.

**THE RULING (B17). Two sprites, one resolver, and the vendored file always wins.**

- `demo/vendor/icons.svg` is GIMS's 54 symbols, **byte-identical, never edited** (D1, D2).
- `demo/static/icons-demo.svg` carries **exactly the 18 symbols that do not exist upstream**, lifted
  verbatim from the approved mock. Its header says what it is and why it is separate.
- A one-line wrapper around GIMS's `Icon` resolves a name to whichever sprite holds it, checking the
  **vendored** sprite first. So `i-play`, `i-plus` and `i-search` render **GIMS's** shapes, not the
  mock's — the three differences are sub-pixel (`M7 4.5` vs `M7 4.8`) and D1's rule that the demo
  recolours and redraws nothing of GIMS's outranks a drawing detail nobody chose deliberately.
- A test asserts the two sprites have **no id in common** — which is what fails the day GIMS adds an
  `i-sort` and the demo silently keeps shadowing it.

**One line to overturn.** *"Use the mock's icons throughout"* — one sprite, 30 symbols, and the
vendored file stops being the source of truth for the 12 it shares.

### B18 — L2 · the mock inlines a near-copy of `watery.css`'s tokens

Measured today: the mock's `:root` is watery's **minus `--blue-deep`, plus `--mono`**.

**THE RULING (B18). `demo/static/demo.css` declares no custom property on `:root`, and a test says
so.** The tokens come from the vendored `watery.css`, linked first. `demo.css` holds only part 5.2's
new classes plus D11's `@font-face` block. The test is `grep -c '^\s*--' demo/static/demo.css` inside
a `:root` block → **0**. That single assertion is what keeps a silent fork of GIMS's stylesheet out
of the demo. (`--mono` is not needed: part 5.1 already specifies the monospace stack literally, as
the established GIMS page convention.)

### B19 — L3 · `.gitignore` would swallow the committed bundles

`.gitignore` ignores `dist/` and `build/` at any depth; AC-36 requires the front end to run from
**committed** bundles with no Node present.

**THE RULING (B19). The bundles are written to `demo/static/js/` and committed**, and
`demo/tests/test_isolation.py` asserts `git check-ignore -q demo/static/js/app.js` **fails** (i.e.
the file is not ignored) and that both bundles are tracked. A bundle that exists on the build machine
and not in a fresh clone is the worst shape a criterion can have; this is the one line that prevents
it.

### B20 — L4 · no driver, no FastAPI, and PEP 668 blocks installing them

Measured today: `psycopg2`, `psycopg`, `fastapi`, `starlette`, `pydantic` and `playwright` are all
absent; `/usr/lib/python3.12/EXTERNALLY-MANAGED` exists; PyPI is reachable (200).
**AC-32** requires the suite to pass *"with no network access beyond pulling the Postgres image"*.

**THE RULING (B20). A committed wheelhouse, installed offline into the demo's own venv.**

- `demo/requirements.txt` pins exact versions with hashes.
- `demo/vendor/wheels/` holds every wheel needed, committed, for CPython 3.12 on manylinux x86-64:
  `psycopg[binary]` (or `psycopg2-binary`), `fastapi`, `starlette`, `pydantic`, `pydantic-core`,
  `annotated-types`, `typing-extensions`, `anyio`, `sniffio`, `idna`, `uvicorn`, `click`, `h11`,
  `pytest`, `pluggy`, `iniconfig`, `packaging`, `httpx`, `httpcore`, `certifi`.
- `./run-demo up` creates `demo/.venv` if absent and runs
  `pip install --no-index --find-links demo/vendor/wheels -r demo/requirements.txt`. **`--no-index`
  is the load-bearing flag**: with it, a network fetch is impossible rather than merely unlikely, so
  AC-32 is proven by the command rather than by observing that nothing was downloaded.
- The wheelhouse is populated **once, at build time**, by `pip download -r demo/requirements.txt`.
  That step needs network; it happens on the build machine and never again.
- `.venv/` is already in `.gitignore`; **`demo/vendor/wheels/` must not be**, and a test asserts the
  wheels are tracked (same shape as B19).

**Why not the alternatives.** *Standard library only* would drop FastAPI, which §9.1 pins from Q23.
*A second container for the app* moves the same install into a `docker build`, which needs the same
network and adds an image to AC-32's one. *Install from PyPI at `up` time* is the honest-but-losing
option: it works on this machine today and makes AC-32 false.

**One line to overturn.** *"Just pip install it, I don't care about offline"* — the wheelhouse goes,
`requirements.txt` stays, and AC-32 is rewritten to *"no network beyond the Postgres image and PyPI"*.
That is his to say, not this document's.

### B21 — L5 · no `psql` and no `pg_isready` on this machine

**THE RULING (B21). Nothing in `./run-demo` shells out to a Postgres client binary.**

- **Readiness** is a Python poll: attempt a connection through the driver every 250 ms up to 60 s,
  and on timeout print the container's last 40 log lines and exit non-zero. (The container's own
  `HEALTHCHECK` may also be declared, but the wait is the Python loop, because the compose healthcheck
  runs inside the image and tells the host nothing on failure.)
- **The bulk load** uses the driver's `COPY … FROM STDIN` with a generated CSV/TSV stream, not
  `psql \copy`. 10,410 small rows loads in well under a second.
- **`runtime.sql` is executed by reading the file and issuing it as one statement batch** through the
  driver. It is 427 lines of `CREATE OR REPLACE FUNCTION` bodies in `$$ … $$`, which the driver sends
  fine as a single `execute`; `psql`'s `\i` is not needed and is not available.
- A grep test asserts the strings `psql`, `pg_isready` and `pg_dump` appear nowhere in the demo tree.

### B22 — L6 · five criteria say "a UI test" and there is no browser automation installed

AC-20, AC-25, AC-29, AC-40(e) and AC-43(d) each say *"a UI test asserts…"*. Playwright is not
installed, and installing a browser is a network dependency AC-32 cannot carry.

**THE RULING (B22). The screen renders from a server-supplied contract, and that contract is what the
always-on tests assert. A browser layer exists on top and skips loudly.**

1. **`demo/server/operations.py` is the single source of truth for the nine controls** — for each
   operation: its number, its label, its control shape (`select` / `input` / `textarea` / `toggle` /
   `repeatable`), its closed set of options where it has one, its `.ctl-fixed` note where it has one,
   and — computed by `demo/legality.py` for the current pick — whether it is **enabled**, and if not,
   the `.op-why` reason. It is served at `GET /api/operations` and re-derived on every pick.
2. **`pick.jsx` renders from that contract and invents no control.** A source assertion over
   `pick.jsx` fails if it contains a literal `<select`, `<input`, `<textarea>` or `.toggle` outside
   the single loop over the contract.
3. **The always-on tests assert the contract**, which is the actual data the screen is built from:
   nine operations present (**AC-25**); operation 7's options are exactly `off`/`hour`/`day`;
   operation 8 exposes **one** field control and no width, direction or aggregate (**R14**);
   operation 9 exposes a toggle and **no value picker** (**R13, AC-40(e)**); every legality transition
   of §4's matrix produces the right enabled/disabled set with a non-empty reason (**B5b**); the pick
   response always carries **both** panes and no field that could hide one (**AC-20**); no route,
   cookie or response field mentions a session, role or saved view (**AC-29**); the response carries
   the session time zone and `extra_float_digits` (**AC-26, AC-43(d)**).
4. **The browser layer is optional and skips in §9.7's four-part sense** — `SKIPPED`, naming what it
   looked for (`playwright`), counted separately in the final summary, everything else still running
   and still having to pass. When it is present it drives the seven views, asserts both panes visible
   on first paint, asserts the verdict banner is above the fold and has no dismiss control, and
   re-runs part 11's `prefers-reduced-motion` measurement.

**Why this is stronger than a browser test alone, not a substitute for one.** A browser test asserts
what one rendered page happened to contain. The contract test asserts what the screen *can* contain,
across every legality state, on every run, offline — and it also removes the possibility that the
server's idea of a legal pick and the screen's idea of an enabled control ever diverge, which is the
bug DR-2 exists to prevent.

### B23 — L7 · `./run-demo test` never says whether it starts the stack

**THE RULING (B23). `test` uses a running stack if there is one and brings up its own if there is
not, and says which in its first line.**

- If `autosql-demo-db` is running **and** the app answers on 8787, the suite uses them and prints
  `using the stack already up`.
- If not, `test` runs `up` itself, runs the suite, and — **only if it started it** — runs `down`
  afterwards. It prints `brought the stack up for this run` and `took it down again`.
- It **never** takes down a stack it did not start; a person mid-walkthrough does not lose it.
- If `up` is impossible because a **foreign** process holds 55440 or 8787, it stops with AC-5's
  message rather than connecting to whatever is there.

That makes AC-32's *"`./run-demo test` on a fresh clone"* literally true, and keeps the suite usable
while driving the demo.

### B24 — L8 · `noun:EdgeCase` is ten rows and only five purposes are named

§8.3 names five witness kinds; AC-7 asserts exactly **10** rows; R11 says *"10 rows, labelled, one
purpose each"*.

**THE RULING (B24). All ten, named here.** Every row carries a **`label`** key stating its purpose in
plain words, which is what R11's *"labelled on screen as an edge case rather than as data"* is
rendered from.

| key | contents | what it is for |
|---|---|---|
| `edge-00` | `{"label":"…","a":1e300}` | §5's seven *value → null* divergences (`$.a + 0`, `$.a * 1`, `-$.a`, `abs($.a)`, `$.a < 1e301`, `$.a > 1`, `$.a >= $.a`) |
| `edge-01` | `{"label":"…","l":[1e300,1]}` | §5's wrong **number**: `max($.l)` → SQL `1`, Python `1e+300`. **Walkthrough step 11**, AC-22 |
| `edge-02` | `{"label":"…","where":{"code":"alpha","n":7},"tags":["a","b"]}` | layer 2 member (b): an `==` operand that really resolves to a container. **Step 12**, AC-18 |
| `edge-03` | `{"label":"…","huge":1e400}` — written as **raw JSON text**, never through a Python float | layer 2 member (a): above the largest double. **Step 13**, AC-17, AC-13 |
| `edge-04` | `{"label":"…","g":1.7976931348623156e+296}` | **just below** the shipped 297-digit guard — `xpr.f8` returns a number |
| `edge-05` | `{"label":"…","g":1.7976931348623158e+296}` | **just above** it — `xpr.f8` returns NULL. `edge-04`/`edge-05` together are AC-13's fifth witness (B12) and are what show the guard's edge is where the file says it is |
| `edge-06` | `{"label":"…","z":0,"d":7}` | division by zero — `xpr.div` returns NULL, matching `expr`'s `None`. The two panes must **agree** here; it is a control that must *not* fire |
| `edge-07` | `{"label":"…","s":"12.5","t":"not a number"}` | `xpr.num`'s string gate: one string converts, one does not, and neither raises |
| `edge-08` | `{"label":"…","n":null,"present":1}` | §7.4(1b)'s **two kinds of null** — a present JSON null beside a key that is simply absent from every other row |
| `edge-09` | `{"label":"…","arr":[],"obj":{},"txt":""}` | `xpr.truthy`'s empty-container branches, and an **empty** container operand for member (b) |

**Two constraints the build must not break.**

1. **No `noun:EdgeCase` row may carry a `status` key.** AC-45(a) requires the alias `status` to be
   **accepted** on `noun:EdgeCase` and refused on `noun:Heartbeat` — that pair is what proves the
   collision list is read per-collection from the data rather than typed into the validator.
2. **`label` becomes a forbidden alias on `noun:EdgeCase`**, because it is a top-level field name of
   that collection (§4.10's third group). That is correct behaviour, not a side effect to work
   around, and AC-45 can use it as a second positive case.

### B25 — L9 · nothing says how many rows the panes render

Walkthrough step 2 returns **8,400** rows and asserts the panes agree "row for row"; the mock's
agreement view draws **eight**.

**THE RULING (B25). The comparison is over the whole result, on the server. The rendering is a page.**

- `POST /api/pick` computes both answers **in full**, compares them **in full**, and returns:
  the verdict, the number of differing rows, the index of the **first** differing row, the total row
  count of each pane, and **the first 50 rows of each** under §7.4's total order. AC-20, AC-21 and
  AC-41(c) are all satisfied by the full comparison; the 50 is display only.
- The count pill shows the true total; a line under the panes reads *"showing the first 50 of 8,400,
  ordered by `key`"* — so nobody can mistake a page for the answer.
- **D8 is preserved:** when there is a differing row past row 50, the response's first-differing index
  drives the page, and both panes jump to include it and scroll to it. A disagreement is never below
  the fold of a paginator.
- Response size stays small (about 6 KB of rows per pane) rather than shipping 8,400 records twice.

**One line to overturn.** *"Show me all the rows"* — the page size becomes the row cap, and the
browser paints 8,400 rows twice.

---

## 4. The query builder's whole contract

Everything above resolves into this. **A build that implements §4 correctly has implemented the SQL
half of the demo**; everything else is plumbing and paint.

### 4.1 The pipeline order — pinned once, obeyed by both panes

Both sides apply the pick in **exactly this order**. A pane that reorders any two of these steps
produces a different number while looking entirely correct, which is the failure mode §5 exists for.

| # | step | SQL | Python |
|---|---|---|---|
| 1 | **source** | `WHERE collection = %(collection)s` | select the collection's rows |
| 2 | **computed columns** (op 2) | compiled expressions in the `SELECT` list (ROWS) or inline in the aggregate (SCALAR/BUCKET) | evaluate the AST per row with the vendored `expr.py`, on `record_f` |
| 3 | **filter** (op 3) | `AND xpr.truthy( <compiled filter> )` | keep rows where `expr`'s truthiness of the evaluated filter is true |
| 4 | **window functions** (ops 8, 9) | over the rows step 3 left, in the frame's order | group by `sender_id`, sort by `(ts, key)`, walk — **after** filtering |
| 5 | **keep only changed** (op 9) | the CTE's outer `WHERE "changed"` | drop rows whose compared value equals the predecessor's |
| 6 | **aggregate / bucket** (ops 6, 7) | `GROUP BY` / the bare aggregate | accumulate in `Decimal`, then round |
| 7 | **sort** (op 4) | `ORDER BY <field> [NULLS LAST], key ASC`, or `ORDER BY "bucket"` | §7.4's comparator in `order.py` |
| 8 | **cap** (op 5) | `LIMIT %(cap)s` — **last** | slice — **last** |

**Two orderings a build gets wrong by instinct, both stated so it cannot.**
*Filter before window* (step 3 before 4): SQL has no choice; a Python runner that windows first and
filters after disagrees on every row next to a filtered-out one. *Cap last* (step 8): `LIMIT` applies
after windows and after the changed filter, so the rolling average of the tenth row is computed from
rows that may not be displayed. A Python runner that caps first computes different numbers for the
same visible rows.

By the legality matrix (B5a), steps 4–5 and step 6 are **never both active**.

### 4.2 The four statement shapes

**Shape A — ROWS, no operation 9.** The default; walkthrough steps 2, 3, 4, 5, 8.

```sql
SELECT r.collection, r.key, r.data,
       <compiled cc0>  AS "alias0", …                                     -- op 2
       avg( <numeric read of the window field> )
         OVER (PARTITION BY (r.data ->> 'sender_id')
               ORDER BY     (r.data ->> 'ts'), r.key
               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)  AS "rolling_avg" -- op 8
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
   AND xpr.truthy( <compiled filter> )                                     -- op 3
 ORDER BY ( r.data #> %(sort_path)s ) DESC NULLS LAST, r.key ASC            -- op 4, or ORDER BY r.key ASC
 LIMIT %(cap)s;                                                            -- op 5
```

**Shape B — ROWS with operation 9.** The CTE of **B3**; walkthrough step 9. (Written out in full at
B3; not repeated here.)

**Shape C — SCALAR.** Walkthrough step 6.

```sql
SELECT round( sum( CASE WHEN jsonb_typeof( <j> ) = 'number'
                        THEN ( <j> #>> '{}' )::numeric END ), 6)  AS "agg"
  FROM demo.records AS r
 WHERE r.collection = %(collection)s
   AND xpr.truthy( <compiled filter> );
```

`count` is the exception: `count( CASE WHEN jsonb_typeof(<j>) = 'number' THEN 1 END )` when a field
is given, `count(*)` when it is not (op 6 = `count` disables the field picker).
`min`/`max` take no `round`.

**Shape D — BUCKET.** The statement of **B1**; walkthrough step 7. (Written out at B1.)

`<j>` in every shape is §7.2 item 5's numeric read input: **either** `r.data #> %(path)s` — the field
path as a bind parameter, never SQL text — **or** the compiled expression of a computed column,
re-emitted inline (**B2**).

### 4.3 The two probes, and the one way to get them wrong

Both run **before** the pick's own statement, over **the same rows the pick will read** — i.e. with
the same `WHERE collection = … AND xpr.truthy(<filter>)`.

**Member (a) — above the largest double.** For each compiled operand `<op>` that reaches a numeric
context, prefixed per **B11**:

```sql
SELECT EXISTS (
  SELECT 1 FROM demo.records AS r
   WHERE r.collection = %(collection)s
     AND ( ( jsonb_typeof( <op0> ) = 'number'
             AND abs( ( <op0> #>> '{}' )::numeric ) >= 1.7976931348623157e+308::numeric )
        OR ( jsonb_typeof( <op1> ) = 'number'
             AND abs( ( <op1> #>> '{}' )::numeric ) >= 1.7976931348623157e+308::numeric ) )
);
```

**Member (b) — an `==`/`!=` operand that really is a container.** Same shape, with
`jsonb_typeof( <operand> ) IN ('object','array')`.

**The one way to get member (a) wrong, named so a build cannot arrive at it by accident.** The probe
reads the **raw jsonb** and casts through `numeric`. It must **never** be routed through `xpr.f8` or
`xpr.num`. Those carry the shipped 297-digit guard, and that guard **returns NULL rather than
raising** (`runtime.sql:33-34`) — so a probe built on them would ask *"is this too big?"* and be handed
a **null for exactly the values that are**, and `NULL >= anything` is null, never true. The probe
would answer "nothing to refuse", the pick would run, and the screen would show the silent null the
probe exists to prevent. **A guess here produces a quiet null instead of a refusal.** `numeric` has no
such limit; `runtime.sql` itself uses the same `(j #>> '{}')::numeric` idiom to *test* the value it
then declines to return.

**A second way to get member (a) wrong, which would destroy AC-22.** The probe asks
`jsonb_typeof(<op>) = 'number'`, and an **array** is not a number. So on walkthrough step 11,
`max($.l)` over `{"l":[1e300,1]}` is **not refused** — the `1e300` is *inside* an array, and the
operand `$.l` is an array. That is correct and required: step 11 must show the **disagreement**
(Python `1e+300` beside SQL `1`), not a refusal. A build that "improves" the probe to look inside
containers turns AC-22's asserted disagreement into a refusal and fails it. The probe's scope is the
operands the expression touches, at the type they touch them.

**Both probes are shown in the SQL pane** (§9.3), including the one that did not fire, stated as a
comment rather than hidden (part 9 question 3's corrected reading).

### 4.4 The alias, the only user text in the SQL text

Pattern, exactly: `re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", alias)` — **`fullmatch`, not
`match`**, because `match` anchors only the start and `alive"; DROP TABLE demo.records; --` would
pass it. Emitted double-quoted, **after** the check, never instead of it.

Refused, by name, if it collides with any of:

1. `collection`, `key`, `data` — the table's own columns;
2. `agg`, `bucket`, `rolling_avg`, `changed` — the four names the builder emits (R8), **including
   `changed`, which under B3 lives inside the CTE and collides just as fatally there**;
3. **every top-level JSON field name of the chosen collection**, read from the data at operation 1 by

   ```sql
   SELECT DISTINCT k FROM demo.records, LATERAL jsonb_object_keys(data) AS k
    WHERE collection = %(collection)s ORDER BY k;
   ```

   once per collection, cached for the session, re-read when the source changes, **computed on the
   server and handed to both panes** so the identical check runs on the identical string;
4. an alias already defined in this pick.

### 4.5 Where each rule is enforced, so nothing is implemented twice

| rule | the one file | everything else calls it |
|---|---|---|
| the 32-construct allowlist and the 12 tags | `demo/gate.py :: gate(ast)` | the server, before `compile_ast`, for op 2 and op 3 |
| the alias pattern and the four collision groups | `demo/gate.py :: validate_alias(name, collection_keys, pick_aliases)` | every emission site — `SELECT`, `ORDER BY`, `GROUP BY` |
| which combinations are legal | `demo/legality.py :: evaluate(pick)` | the `/api/operations` contract **and** the pick handler — one function, so the screen and the server cannot disagree |
| the numeric read | `demo/builder.py :: numeric_read(j_sql)` | ops 6, 7, 8 |
| exact decimal + half-up to 6 places | `demo/pyrunner/decimals.py :: q6(x)` and SQL `round(…, 6)` | ops 6, 7, 8, both panes |
| §7.4's comparator | `demo/pyrunner/order.py :: sort_key(...)` | every Python sort |
| fragment namespacing | `demo/builder.py :: namespace(frag, prefix)` | every `compile_ast` call site |
| the connection | `demo/server/db.py :: connect()` | everything; nothing else imports the driver |

---

## 5. The seeded data

**10,410 rows in one table, invented, deterministic, and labelled as invented in three places.**

### 5.1 The table

```sql
CREATE SCHEMA demo;
CREATE TABLE demo.records (
  collection text  NOT NULL,
  key        text  NOT NULL,
  data       jsonb NOT NULL,
  PRIMARY KEY (collection, key)
);
```

No other index, ever (Q11, §4.8). **AC-12** asserts `pg_indexes WHERE schemaname='demo'` returns
exactly **one** row — the primary key, which is part of the table's definition rather than query
acceleration (R6). `spikes/T-1/proto/runtime.sql` is installed **unmodified** into the `xpr` schema
alongside it (§9.6, AC-33).

### 5.2 `noun:Heartbeat` — 8,400 rows

| field | contents | fixed by |
|---|---|---|
| `sender_id` | `hb-01` … `hb-50`, text, zero-padded | Q22 (50 senders); R19's key format |
| `ts` | `2026-08-14T00:00:00Z` + *b* hours, *b* = 0…167 — **fixed-width UTC ISO-8601**, a literal constant, never from the clock | **R17** |
| `status` | closed set `ok` / `warn` / `error`, about 90 / 8 / 2 | **R16** |
| `payload` | object with exactly two keys: `load`, an integer 0–100 **present and JSON-numeric in every row**; `note`, short ASCII from a fixed 16-word vocabulary | **R16** |
| `key` | `hb-<NN>-<BBBB>` — `hb-01-0000` … `hb-50-0167` | **R19** |

50 senders × 168 hourly beats = **8,400**. All 50 share every one of the 168 instants, which is what
makes §7.4's `key` tiebreak necessary rather than decorative, and what makes step 5's cap of 10 fall
inside a 50-row tie.

Bucketing by UTC day gives **exactly 7 buckets of 1,200** (50 senders × 24 hours) — arithmetic, not a
lucky draw, and true only because R17 pins whole UTC days and §7.1's time-bucket rule pins the session
zone.

> #### B27 — the change mechanism, and how determinism is actually achieved
>
> R16 leaves the seed's change mechanism to the build, bounded by two criteria: consecutive beats from
> one sender match on `status` **and** `payload` in **88–92%** of cases (AC-8), and operation 9 keeps
> **700–1,100** rows (AC-40). This is the mechanism that satisfies both, pinned so two runs and two
> machines agree.
>
> - **Per-sender independent streams.** For sender *s*, the generator seeds
>   `random.Random(int.from_bytes(hashlib.sha256(f"T-2:{s}".encode()).digest()[:8], "big"))`.
>   Written out rather than using `random.Random("string")` because an explicit hash is stable across
>   Python versions by construction rather than by documentation, and because per-sender streams make
>   the output independent of the loop order — a build that later parallelises the seed cannot change
>   a single row.
> - **Beat 0** draws `status` from the 90/8/2 distribution, `load` uniform 0–100, `note` from the
>   vocabulary.
> - **Beat *b* > 0** carries the previous `(status, payload)` forward unchanged with probability
>   **0.90**. With probability **0.10** it draws a new `(status, payload)` **and redraws until the
>   pair actually differs from the previous one.** That last clause is load-bearing: without it a
>   "change" that happens to redraw the same values is a silent non-change, and the kept-row count
>   drifts below AC-40's band for a reason nobody would find.
> - **Consequence, which is why the two criteria agree:** the number of rows operation 9 keeps is
>   exactly *50 first beats + the number of change events*, expected ≈ 50 + 0.10 × 8,350 = **885** —
>   comfortably inside AC-40's 700–1,100 — and the repeat rate is exactly 1 − (change events / 8,350),
>   expected **90%**, inside AC-8's 88–92%. Both criteria measure the same coin flip from opposite
>   sides, which is what makes a failure of either one informative.
> - **`ts` is never part of the change decision.** It advances every beat by construction. That is
>   §7.1's comparison rule seen from the seed's side.
>
> **One line to overturn.** Any other rate — AC-8's band and AC-40's band move with it, and step 9's
> number regenerates.

### 5.3 `noun:Sample` — 2,000 rows

The **record** rule of `spikes/T-1/proto/gen_data.py:25-46`, verbatim in behaviour: `id`, `status`
(60% `open`, else one of `closed`/`hold`/`void`), `due_date` (**5% of rows omit it entirely**),
`priority` 1–5, plus **5–15** extra keys `field_0 … field_14` of mixed type — text, a 4-decimal
float, a boolean, **JSON null**, and an **object** `{"code": …, "n": …}`.

This is the collection that makes the demo's data look like GIMS data rather than a tidy example, and
it is why §7.4's comparator has to handle mixed types and **two kinds of null** — an absent key (SQL
`NULL`, governed by `NULLS LAST`) and a present JSON null (`'null'::jsonb`, a *value*, ordered below
everything else). **AC-41(e)** is the criterion that exercises all three bands.

Its key format is **not** taken from that file — `gen_data.py:58`'s unpadded `S-{i}` orders
`S-0, S-1, S-10, S-100, …` as text. R19 replaces it with `smp-0000 … smp-1999`.

> #### B26 — the in-record `id` matches the key
>
> `gen_data.py:25` writes `row["id"] = f"S-{i}"` **inside the record**, while R19 renames the row's
> `key` to `smp-0000`. Carrying both would put **two contradictory identifiers for one row on the
> screen** — `smp-0007` in the key column and `S-7` in the data — and a person checking a number by
> eye would have to work out which one the demo meant. Ruled: **the record's `id` field holds the same
> string as the row's `key`.** R19 replaced the identifier format; it did not intend to create a
> second one. **One line to overturn:** *"Keep the spike's ids inside the records"*.

### 5.4 `noun:EdgeCase` — 10 rows

All ten named at **B24**, each carrying a `label` key stating its purpose. Ten rows out of 10,410 —
under 0.1% of the database — and every one is shown labelled as an edge case rather than as data
(R11).

### 5.5 Determinism, and what proves it

- **Every constant is literal.** The span (R17), the seed material (B27), the vocabulary, the
  distributions. **Nothing reads the clock**, and a grep test asserts that: the strings
  `datetime.now`, `date.today`, `time.time` and `random.seed()` without an argument appear nowhere in
  `demo/seed/`.
- **AC-10** compares an `md5` over all rows ordered by `(collection, key)` between two runs on two
  clean checkouts. The expected digest is recorded in `demo/manifest.json` once the seed is written,
  so a third party can check without running the seed twice.
- **`demo/expected-answers.json` is regenerated by the seed**, from the seed's own model, by code that
  may not import the Python pane (**B8**).

### 5.6 How the demo says the data is invented — and the five look-questions, ruled

AC-11 requires the label *"in both the seed script and the screen"* and does not say how often. Part 9
question 4 puts the frequency to Evan, noting he may show this to an employer (Q43). These are the
five open look-questions of `design/t2-demo.md` part 9, ruled here so the build does not stop for
them. **All five are cheap to overturn, and three of them are explicitly the kind of thing that ten
minutes at the real screen settles better than any argument here — so the builder may revisit any of
them if driving the built screen contradicts the reasoning, and must record it if they do.**

| # | question | **the ruling** | why |
|---|---|---|---|
| **B28** | Should agreement speak as loudly as disagreement? | **Keep D12: the green *BOTH PANES AGREE* banner on every accepted pick.** | A reader has to be trained to look at the strip *before* the one pick where it turns coral. A strip that appears only on disagreement is a strip nobody has learned to read. The banner-blindness risk is real but is the lesser one, and it is mitigated by D8 — the banner is not the only signal |
| **B29** | Side by side, or stacked? | **Side by side, fixed, and the layout yields before the signal does (DR-1).** Below 760px the comparison grid unstacks, which is the mock's measured behaviour and is out of scope anyway (part 7: designed at 1440, must not break at 1280) | §5's mechanism is a single glance. Stacking makes two numbers a scroll apart |
| **B30** | How much SQL at rest? | **The statement and both probes open, in full**, with the probe that did not run stated in a comment rather than hidden — the maximally-visible reading of §9.3, which is why part 2 puts the SQL pane last | The demo's one claim is that the SQL on screen *is* the query. A collapsed probe is a question the demo asked the database and did not show |
| **B31** | How insistently should the invented data say it is invented? | **Three places, not one.** (1) the amber `INVENTED DATA` chip in the masthead and the standing banner under it, as drawn; (2) **one `.chip.warn` reading `invented` in each answer pane's head**; (3) the seed script's own header and console line. | The mock's two live in the header. **A screenshot of the answer panes alone — which is exactly what gets pasted into a message to an employer — carries neither.** The pane chip is one 10.5px pill against that, and it is the one addition to the drawn screen this document makes on its own initiative. **One line to overturn:** *"The header chip is enough"* |
| **B32** | Is the picking column too long? | **Leave it as drawn, and move nothing behind a `?`.** | Measured at 1,949–2,236px against a working area of 1,081–1,748px, so it is the longer column in all seven states. The alternative trades a shorter column for a person leaving the screen to find out what `MAX_SCAN` is — against Q21's *"correct and readable"*. **This is the one of the five most likely to be overturned at the real screen**, and the change is mechanical: each `.ctl-hint` moves into a `?` popover |

---

## 6. The work items

**Eighteen items. Each ends in something a different person can check without reading the code that
produced it** — that is what "independently checkable" means here, and it is also what
`autodev/instructions/build.md` demands of this stage: *"a build stage here ends with the generated
SQL and the rows it produced on a known fixture, so the next stage has a number to check rather than
a promise."*

### 6.1 The strictly sequential spine

Everything else hangs off this. **W1 → W2 → W5 → W10 → W13 → W14 → W17.** Six links, and the reason
each is a link rather than a preference:

- **W1 → W2** — nothing can be checksummed before the manifest exists.
- **W2 → W5** — the seed installs `runtime.sql`, whose digest W2 recorded.
- **W5 → W10** — the query builder's tests assert row counts against seeded data.
- **W10 → W13** — the API returns what the builder produces.
- **W13 → W14** — the screen renders the `/api/operations` contract (**B22**); building the JSX first
  means building it against a guess.
- **W14 → W17** — the walkthrough's end-to-end steps drive the screen.

### 6.2 The items

| # | Item | Done means (checkable by someone else) | After | Parallel with |
|---|---|---|---|---|
| **W1** | **Skeleton + `run-demo` + `manifest.json`** — the tree of locate §3.1, the four verbs stubbed, the manifest empty | `./run-demo` prints its four verbs and exits 0; the tree matches locate §3.1 file for file | — | — |
| **W2** | **Vendoring + the drift machinery (D1, D2, R4)** — `expr.py` and the six style assets copied byte-identically, digests in `manifest.json`, plus §9.7's **four-part loud skip** (`SKIPPED`, names the path, counted separately, tree-independent halves still run) | `sha256sum` of each vendored file equals the manifest; **AC-33, AC-34 (both halves), AC-35, AC-39** pass with the trees present **and** with `AUTOSQL_GIMS_TREE=/nope` | W1 | W3 |
| **W3** | **The wheelhouse and the venv (B20)** — `requirements.txt`, `demo/vendor/wheels/`, `up` bootstraps `demo/.venv` with `--no-index` | `pip install --no-index --find-links demo/vendor/wheels -r demo/requirements.txt` succeeds **with the network off**; the wheels are tracked by git (**B19**'s shape) | W1 | W2, W7, W8, W9 |
| **W4** | **The container and the launcher (§11.2, B21, B23)** — `compose.yaml` with `autosql-demo-db`, `127.0.0.1:55440`, `POSTGRES_INITDB_ARGS: "--locale=C --encoding=UTF8"`; port guards; the Python readiness poll; `down`; `ops/checks/neighbour-ports.sh` | **AC-1, AC-2(a)(b), AC-5, AC-6** pass; `ops/checks/neighbour-ports.sh` reports no change on any port but 55440/8787 across an up/down cycle; `SHOW lc_collate` returns `C` | W3 | W5 |
| **W5** | **Schema, `runtime.sql`, the seed (§5, B24, B26, B27)** | **AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13** pass; `SELECT count(*)` is 8,400 / 2,000 / 10; the AC-10 digest is recorded in the manifest | W2, W4 | W6 |
| **W6** | **`expectations.py` (B8)** — the third independent path, with a `derivation` on every number | `demo/expected-answers.json` exists; the AST test finds **no** import of `pyrunner`/`builder`/`probes`; every entry has a non-empty `derivation` | W5 | — |
| **W7** | **`gate.py` — layer 1 (§4.4, §4.10, R10)** — `gate(ast)` and `validate_alias(...)`. **The safety-critical file** | **AC-14** passes: 48 construct rows each with its verdict, all **twelve** tags accepted at the tag, a thirteenth refused, `\|index\| < 2³¹` at the boundary both ways. **AC-38(a)** passes with all 13 hostile names. Every refusal names the construct or the rule | W1 | W3, W8, W9 — **no database needed** |
| **W8** | **`legality.py` + `operations.py` (B5, B22)** — the three shapes, X1, X2, the extensions, and the served contract | **test_legality.py** walks every combination of the nine operations across the three sources and asserts the enabled set and a non-empty reason for each disable; `GET /api/operations` returns it | W1 | W3, W7, W9 |
| **W9** | **`decimals.py` + `order.py` (§7.2, §7.4)** — `q6()` half-up to 6 places; §7.4(1b)'s comparator written out, `C`-collation text order, both kinds of null | **AC-24(b)**'s tie test passes on the Python side; `order.py`'s comparator reproduces a hand-written expected sequence over a mixed-type fixture | W1 | W3, W7, W8 |
| **W10** | **`builder.py` (§4 of this plan: B1, B2, B3, B5a, B11)** — the four statement shapes, `namespace()`, `numeric_read()` | The four shapes **run** against the seeded database and return the expected counts; **the merge test of B11** passes; **AC-24(c), AC-40(c) (as B3b restates it), AC-41(a), AC-43(a)** pass | W5, W7, W8 | W11, W12 |
| **W11** | **`probes.py` — layer 2 (§4.5)** | **AC-17** (1e400 refuses, **1e300 does not**), **AC-18** (container refuses; steps 3 and 4 do not) | W5, W7 | W10, W12 |
| **W12** | **`pyrunner/` — the second calculator (§9.5, B7)** — rows (the double parse), evaluate, shape, using W9's `decimals`/`order` | **AC-23(a)(b)**; **AC-24(d)** on the Python pane **alone**, against hand-computed values; **AC-40(a)(b)(d)** on the Python pane alone | W5, W9 | W10, W11 |
| **W13** | **`server/` (§9.3, B13, B22, B25)** — `db.py` (the only connection factory), `/api/operations`, `/api/fields`, `/api/pick` with the full comparison and the paged rows | **AC-2(c)** with the full poisoned environment **and** a hostile `~/.pgpass`; **AC-20, AC-26, AC-27, AC-28, AC-29**; the pick response carries both panes, the verdict, the differing count and the first differing index | W10, W11, W12 | — |
| **W14** | **The screen (part 2, 3.1, 4, 5; B17, B18, B25, B28–B32)** — the JSX, `demo.css` (**no `:root` tokens**), `icons-demo.svg` (**the 18**), self-hosted Inter, `build.mjs`, and **the committed bundles under `demo/static/js/`** | **AC-36** — `up` with `node` removed from `PATH` serves a working screen; **AC-25**'s contract assertions; **B18**'s and **B19**'s greps; the seven states of the mock are reachable and match it | W13 | W15 |
| **W15** | **`WALKTHROUGH.md` + the glossary (§10, B16)** — 14 steps, numbers from `expected-answers.json`, the twelve glossed terms | Every number in the document equals the corresponding entry in `expected-answers.json` (a test, not a read) | W6 | W14, W18 |
| **W16** | **The suite wiring (B23, §9.7)** — `run-demo test`'s stack logic, the skip summary line, the forbidden-string grep, the checksum guard of **B10** | **AC-3, AC-4, AC-32, AC-39**; the final summary line counts skips separately; the session-start/session-end checksum guard fires on a deliberately leaked write | W4, W13 | W17, W18 |
| **W17** | **The walkthrough end to end (AC-30, AC-31, and the asserted disagreement)** — all 14 steps driven through the API | **AC-22** (the asserted disagreement: Python `1e+300`, SQL `1`, flagged), **AC-30, AC-31, AC-40(a)(e), AC-41(b)(c)(d)(e), AC-43(b)(c)(d), AC-44, AC-45(a)(b)(c)** | W14, W16 | W18 |
| **W18** | **`README.md` + the no-speed-claim sweep (AC-37)** — and the build's evidence pack (§6.4) | **AC-37**: a grep for timing vocabulary over the demo tree finds nothing, and a reviewer's read agrees. The evidence pack exists | W15 | W17 |

### 6.3 What is genuinely parallel

- **W7, W8, W9 need no database and no container.** They are pure Python over the vendored `expr.py`
  and can start the moment W1 lands, alongside W3's download. **Three of the four heaviest
  correctness surfaces — the gate, the legality matrix and the comparator — are on this path**, so
  starting them early is not just schedule padding.
- **W10, W11, W12 are three workers against one pinned contract** (§4 of this plan). They must not
  negotiate it between themselves; where §4 is silent the answer is a new `B` ruling recorded here,
  not a local convention.
- **W15 and W18 are documents** and can be drafted alongside anything after W6.
- **W2 and W3 both fetch things** (one from the sibling checkouts, one from PyPI) and are the two
  items that behave differently on a machine without them. Doing them first surfaces that.

### 6.4 What the build stage hands to `auto-review`

Per `autodev/instructions/build.md`, not "the tests pass" but **numbers**:

1. **The generated SQL for all 14 walkthrough steps**, verbatim, as the SQL pane renders it — the
   parameterised text *and* the display rendering, so a reviewer can see they differ only in
   substitution.
2. **The rows each one returned**, or the first 20 of them plus the count.
3. **The two panes' answers side by side for each step**, with the verdict, so step 11's asserted
   disagreement is visible in the record and not only in a green test.
4. **`demo/expected-answers.json`**, with every `derivation`.
5. **The three digests**: `compile.py`, `runtime.sql`, `demo/vendor/expr.py`.
6. **The suite's final summary line**, including the skip count and what was skipped.

---

## 7. How each of the 45 acceptance criteria is demonstrated

**"The suite"** is `./run-demo test`. Where a `B` ruling changes what a criterion means, the change
is named in the last column — those are the rows a reviewer should read first.

### Launch and isolation

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **1** | Clone to an empty dir, `./run-demo up`, load `http://127.0.0.1:8787`. Recorded in the evidence pack as a transcript | manual + W4 | B20 (the venv bootstrap is part of `up`) |
| **2** | (a) `docker inspect autosql-demo-db` shows `127.0.0.1:55440`; (b) the app answers on 8787; (c) the connection factory under the **full** poisoned environment and a hostile `~/.pgpass`, plus the raise-on-any-other-port test | `test_isolation.py` | **B13** — one union list, and every libpq parameter passed explicitly so an unenumerated variable cannot bite |
| **3** | A grep for `55433`, `glp_owner`, `glp_strong`, `glp-strong-db` over `demo/` + `./run-demo` | `test_isolation.py` | — |
| **4** | `ops/checks/neighbour-ports.sh` — `docker ps` + `ss -ltn` before `up` and after `down`; asserts every listener on every port but 55440/8787 unchanged. **Outside the demo tree, port numbers only** | W4 | — |
| **5** | Occupy 55440, then 8787; `up` refuses naming the port | `test_isolation.py` | **B23** — `test` inherits the same guard |
| **6** | `docker ps -a` and `docker volume ls` after `down` | `test_isolation.py` | — |

### Data

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **7** | Three `count(*)`: 8,400 / 2,000 / 10 | `test_data.py` | B24 (the 10 are named) |
| **8** | Adjacent-pair query per sender: `status` **and** `payload` match in 88–92% | `test_data.py` | B27 (the mechanism that lands it there) |
| **9** | `GROUP BY date_trunc('day', (data ->> 'ts')::timestamptz)` in a `UTC` session → 7 × 1,200 | `test_data.py` | — |
| **10** | `md5` over all rows ordered by `(collection, key)`, against the manifest digest; **re-asserted at session start and end** | `conftest.py` | **B10** — the end-of-session assertion is new, and is what catches a leaking test write |
| **11** | String assertion on the seed's header and console line; the screen's three labels | `test_data.py`, `test_ui`-contract | **B31** — three places, not one |
| **12** | `pg_indexes WHERE schemaname='demo'` returns exactly one row | `test_data.py` | — |
| **13** | **Five** row assertions, not four — including the guard-boundary pair `edge-04`/`edge-05`; the `huge` row asserted to be `jsonb_typeof = 'number'` | `test_data.py` | **B12**, **B24** |

### The subset and the two enforcement layers

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **14** | Table-driven: **48** construct rows with expected verdicts, `\|index\| < 2³¹` at the boundary both ways, **plus** all **twelve** tags accepted at the tag and an invented thirteenth refused. Every refusal names the construct | `test_gate.py` | — |
| **15** | A driver-level spy: a refused expression sends **zero** statements and `compile_ast` is never called | `test_gate.py` | — |
| **16** | Walkthrough step 10 through the API: refusal named, **both** panes empty | `test_walkthrough.py` | — |
| **17** | Step 13 refuses; **and a unit test that `1e300` does not trigger** and the threshold is the 309-digit `DBL_MAX`, not the shipped 297-digit guard | `test_probes.py` | **B15** (the exact literals), **§4.3** (why `max($.l)` must *not* be caught) |
| **18** | Step 12 refuses and names the row; **steps 3 and 4 are not refused** — the half that proves reading A rather than reading B | `test_probes.py` | — |
| **19** | With `../GIMS-Project` present: run the gate over all 130 fixture cases, **report per case**, no threshold. With `AUTOSQL_GIMS_TREE=/nope`: **`SKIPPED`, naming the path, counted separately** | `test_vendor.py` | — |

### The side-by-side — §5's control

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **20** | The API returns **both** answers in one response with no field that could suppress one; the contract test asserts both panes are rendered on first paint and `.pane-pair` carries no collapse affordance | `test_ui.py` | **B22** (contract-level), **B25** (full comparison, paged render) |
| **21** | Step 11's response carries the verdict `disagree`, a differing count and a first-differing index | `test_walkthrough.py` | **B25** |
| **22** | End to end: Python `1e+300`, SQL `1`, **and** the flag. **This test asserts a disagreement** — if the panes ever agree here, the build is not accepted | `test_walkthrough.py` | §4.3 — the probe must not "improve" into refusing this |
| **23** | (a) mutate one row, re-run, both panes move, **then restore**; (b) a test hook perturbs the compiled expression and the Python pane does **not** follow | `test_walkthrough.py` | **B10** (the restore + the checksum guard) |
| **24** | (a) step 8 digit for digit; (b) a tie rounded half-up on **both** engines, Postgres's half evaluated on the demo's own database; (c) the grep for `float8`/`double precision` over the aggregate, bucket and window SQL — **not** the changed-rows SQL; (d) **divisor 1, 2, 3 asserted on each pane separately against hand-computed values before the panes are compared** | `test_decimal.py`, `test_walkthrough.py` | **B7** (the `Decimal(str)` route makes (a) reachable at all) |

### The screen and the SQL

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **25** | The `/api/operations` contract: nine operations; op 7 = exactly `off`/`hour`/`day`; op 8 = one field control and **no** width/direction/aggregate; op 9 = a toggle and **no** value picker. **Plus:** ops 7/8/9 enabled on `noun:Heartbeat` and disabled-with-reason on the other two | `test_ui.py` | **B4** (the new part), **B22** (how it is asserted without a browser) |
| **26** | String assertions on a known pick: the full statement, **both** probes, `extra_float_digits` **and** the session time zone | `test_ui.py` | **B30** (both probes open) |
| **27** | The executed text still contains its `%(…)s` placeholders; `render_for_display`'s output never reaches the driver (asserted at the driver boundary, not by reading code) | `test_ui.py` | — |
| **28** | Type a field name containing `"` and `;`: it appears only in the parameter list, and the row count is unaffected | `test_ui.py` | — |
| **29** | No route, cookie, header or response field mentions a session, a role or a saved view; the page loads with no login | `test_ui.py` | **B22** |

### The walkthrough

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **30** | All 14 steps performed end to end through the API, each producing its stated result | `test_walkthrough.py` | — |
| **31** | Every number in `WALKTHROUGH.md` = the entry in `expected-answers.json` = what the app returns, **all three**, including op 9's kept count and its first five kept keys | `test_walkthrough.py` | **B8** — and step 6 gains a per-pane absolute assertion so it is not the pane checking itself |
| **32** | `./run-demo test` on a fresh clone with **no network**: the wheelhouse installs with `--no-index`, the Postgres image is already local (and would otherwise be the one permitted pull) | W16 | **B20**, **B23** |

### The build itself

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **33** | sha256 of `compile.py` and `runtime.sql` against the manifest | `test_vendor.py` | — |
| **34** | The **manifest half** always; the **tree half** when a checkout is present, **skipping loudly** when not | `test_vendor.py` | — |
| **35** | `git status` clean in each tree present; no `__pycache__` mtime inside the build window; **loud skip** when absent | `test_vendor.py` | — |
| **36** | `./run-demo up` with `node` removed from `PATH`; the screen loads and the controls work | W14 + manual | **B19** — the bundles are at `demo/static/js/` so they survive a clone |
| **37** | A grep for timing vocabulary (`ms`, `faster`, `benchmark`, `elapsed`, `latency`, `throughput`, `speed`) over the demo tree, plus a reviewer's read | `test_isolation.py` + review | — |
| **38** | (a) the 13-name table, **one from each of §4.10's three collision groups plus the in-pick duplicate**; (b) step 14 leaves both panes empty, sends **zero** statements, and `demo.records` still holds 10,410; (c) an accepted alias appears as `AS "alive"` and the Python pane keys the same name | `test_alias.py`, `test_walkthrough.py` | — |
| **39** | (a) both tree variables pointed at nothing → AC-19, AC-34's tree half and AC-35 each report `SKIPPED` naming the path, counted separately; (b) everything else still runs and passes, **AC-34's manifest half among the passes**; (c) `up` completes and answers steps 2 and 8 with both panes populated | `test_vendor.py` | — |

### Operation 9, the ordering rule, the inventory

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **40** | **Five** parts: (a) kept count 700–1,100 **on each pane separately**; (b) the three unit cases — differ only in `ts` → **not** kept, differ in `payload.load` → kept, differ in `status` → kept; (c) the SQL assertions **as B3b restates them**; (d) exactly **50** first beats kept; (e) the compared value is a constant of the builder and the screen offers no picker | `test_walkthrough.py`, `test_builder_sql.py`, `test_ui.py` | **B3** (the CTE is what makes (a) a count of rows at all), **B3b**, **B12** |
| **41** | **Five** parts: (a) every multi-row statement ends in an `ORDER BY` whose last component is `key` or the group key; (b) the five picks run **ten times** each and return the identical sequence; (c) Python's sequence equals SQL's **element for element** over the full result; (d) step 5's ten *lowest* keys within the winning tie, **each pane separately**; (e) the three null/type bands on `noun:Sample`, plus the `--locale=C` grep | `test_order.py`, `test_walkthrough.py` | **B12**, **B25** (the comparison is over the full result, not the page) |
| **42** | One case per row of §4.4's inventory, each fed a value outside what that row accepts and asserted to refuse **by name**: gate (rows 1–2), field binding (row 3), the alias validator (rows 4 and 6), the integer range (row 5), the closed set (row 7). **A row whose check cannot be shown firing fails** | `test_gate.py`, `test_alias.py`, `test_ui.py` | — |

### The bucket, the keys, the alias namespace

| AC | Demonstrated by | Where | Changed by |
|---|---|---|---|
| **43** | (a) the grep: `date_trunc(<granularity>, (data ->> 'ts')::timestamptz)`, the granularity one of two fixed keywords, the cast **`timestamptz`** — a `::timestamp` cast fails even though it returns the right answer on this seed; (b) **the hostile-inheritance test**: container `TZ` and client `PGTZ` both `America/New_York`, step 7 still gives **7 × 1,200 on each pane separately** and the same seven labels; (c) the labels compared **as strings**; (d) the SQL pane displays the zone beside `extra_float_digits` | `test_walkthrough.py`, `test_builder_sql.py` | **B1** — one emitted `bucket` column, so `ORDER BY "bucket"` is unambiguous |
| **44** | (a) a regex per collection over every key — `^hb-\d{2}-\d{4}$`, `^smp-\d{4}$`, `^edge-\d{2}$`; (b) `ORDER BY key` returns every beat of `hb-01` before any of `hb-02`, and within a sender in ascending `ts`; (c) Python's sort of that list equals Postgres's element for element | `test_order.py` | — |
| **45** | (a) `status` refused on `noun:Heartbeat`, **accepted on `noun:EdgeCase`** — which is why no EdgeCase row may carry a `status` key (**B24**); (b) the scratch-collection half **at server level, inside a rolled-back transaction**; (c) on `noun:Sample`, **every** `field_0…field_14` refused — the union over the collection, not one row's keys | `test_alias.py` | **B9**, **B10**, **B24** |

---

## 8. The test approach — how a wrong number is **caught**, not how tests exist

This project's failure mode is stated in its own roster file: *"autoSQL generates SQL, so its failure
mode is a subtly wrong **number** that still runs clean — nothing crashes, nothing goes red."* A test
plan that answers *"is there coverage?"* does not address that. This one answers *"by what mechanism
does a wrong number fail to reach the screen?"*, five ways, each with the specific thing that fires.

### 8.1 The five ways a wrong number could survive, and what stops each

| # | how it survives | why the obvious defence misses it | **what actually catches it** |
|---|---|---|---|
| **1** | **Both panes are wrong the same way.** Two implementations of one misreading agree perfectly | The side-by-side compares them to each other. It cannot see a shared error — §5's control stays green | **Absolute assertions before comparative ones.** Every number that matters is asserted on **each pane separately against an independently derived value**, and only *then* are the panes compared. Already required at AC-24(d), AC-40(a), AC-41(d) and AC-43(b); **B8 adds it at step 6**, the one walkthrough number that had none. This is the only defence against mode 1, and it is why it is applied everywhere rather than where it seemed necessary |
| **2** | **The check is the thing being checked.** `expected-answers.json` computed by the Python pane | The suite is green and the document agrees with the app | **Three independent producers, enforced structurally** (**B8**): the SQL, the Python pane, and `demo/seed/expectations.py` — which an **AST test forbids from importing either of the other two**, and every entry of which carries a `derivation` a reviewer reads |
| **3** | **A near miss hides inside a tolerance.** `abs(a-b) < 1e-9` swallows a real difference | Floating-point comparison "obviously" needs a tolerance | **There is no tolerance anywhere in this suite.** §7.2's exact-decimal rule makes every compared number a `Decimal`/`numeric` rounded half-up to 6 places, so comparison is `==`. **A grep test fails the build if `math.isclose`, `pytest.approx`, `abs(` … `<` … `e-` or `rel_tol` appears anywhere under `demo/`.** A tolerance is not a testing convenience here; it is the mechanism by which the defect this demo exists to show would be hidden |
| **4** | **Silent nulls and quietly dropped rows.** A count that is plausible but wrong | Nothing raises; the number looks fine | **Assertions chosen to fail by an order of magnitude, not by a digit.** Operation 9's band is **700–1,100 out of 8,400**, so the whole-record misreading fails by **eight-fold in a single integer**. Step 7 is **7 buckets, not 8**. AC-44(b) fails if row 1,000 arrives fourth. None of these is a near miss; each is a number a person reading the failure understands immediately |
| **5** | **Order flakiness reads as agreement, or as a finding.** An unordered result matches by luck, or differs by luck | One run passes | **AC-41(b) runs five picks ten times each** and requires the identical sequence, and **AC-41(c)** compares element for element over the **full** result rather than the rendered page (**B25**). §7.4's total order exists for exactly this, and the repeat-run test is what proves the order comes from `ORDER BY` rather than from the plan |

### 8.2 The mutation pass — the part that proves the catchers work

**There is a precedent in this repository and it is the reason this section exists.** T-1's own
re-check drove its conformance harness with **six deliberately wrong compilations** and discovered
that every branch which reports a failure had **0 executions** across a full run — *"those branches
were dead, not broken."* A suite whose failure paths have never been emitted is a suite nobody has
watched work.

So the build runs a **mutation pass** before it hands over: a committed list of one-line defects,
each applied in turn, each with **the named criterion that must fail**. `./run-demo test --mutants`
applies each, runs only that criterion, asserts it **fails**, and reverts. A mutant that survives is
a build failure — it means the criterion is decorative.

| # | the defect (one line) | the criterion that must fail |
|---|---|---|
| M1 | Python rolling window divides by **3 always** | AC-24(d), Python half, rows 1 and 2 |
| M2 | Python rolling window returns `None` until three rows accumulate | AC-24(d), Python half |
| M3 | Python sort uses `sorted(…, reverse=True)` over a tuple containing `key` | AC-41(d) — ten *highest* keys instead of ten lowest |
| M4 | operation 9 compares the whole record (drop `- 'ts'`) | AC-40(a) — 8,400 kept against a band of 700–1,100 |
| M5 | operation 9 uses `<>` instead of `IS DISTINCT FROM` | AC-40(d) — the 50 first beats vanish |
| M6 | the bucket cast becomes `::timestamp` | AC-43(a) — **and nothing else**, which is the point: it returns the right answer on this seed |
| M7 | the session time zone is not set | AC-43(b) — 8 uneven buckets under the hostile inheritance |
| M8 | Python rounding left at `ROUND_HALF_EVEN` | AC-24(b) |
| M9 | `Decimal(v)` from the float instead of from the JSON text | AC-24(a) **on a `noun:Sample` aggregate over a 4-decimal `field_n`** — which is why that case is added to the suite (**B7**) |
| M10 | fragment prefixes removed, so every fragment names `p0` | B11's merge test — three distinct literals collapse to one |
| M11 | the probe routed through `xpr.f8` | AC-17 — `1e400` stops being refused, because the guard returns NULL |
| M12 | the gate accepts only the ten leaf/structural tags | AC-14's tag half — and every comparison in the demo is refused |
| M13 | `re.match` instead of `re.fullmatch` in the alias validator | AC-38(a) — `alive"; DROP TABLE demo.records; --` is accepted |
| M14 | the numeric read's `jsonb_typeof` guard removed | the `noun:Sample` aggregate raises `22P02`; a **loud** failure, and the mutant proves the guard is load-bearing rather than defensive |
| M15 | `ORDER BY` dropped from one multi-row statement | AC-41(a) grep, and AC-41(b)'s ten runs |
| M16 | a test writes a row and does not clean up | **B10**'s end-of-session checksum guard |

**M6 is the most valuable row in the table** and should be read twice. A `::timestamp` cast returns
**the identical answer** on this seed, because the seed is UTC throughout. Every number on the screen
is right. The only thing that catches it is a criterion that asserts the *cast*, not the *result* —
which is why AC-43(a) is a grep and not a comparison, and why a build must not "simplify" it into an
assertion about buckets.

### 8.3 What the suite is not allowed to do

- **No tolerance.** §8.1 row 3, enforced by grep.
- **No silent skip.** §9.7's four-part rule applies to every skip in the suite, not only the
  GIMS-tree ones: report `SKIPPED`, name what was looked for, count separately in the summary, and
  keep running everything that does not need the missing thing. **B22**'s optional browser layer is
  held to the same rule.
- **No assertion that only compares the panes.** Every criterion in §7's table that produces a number
  has a per-pane absolute assertion **before** the comparison. Where one does not, it is because the
  criterion is about a refusal or a structure rather than a number.
- **No test that reads its expectation from the code under test.** Enforced by B8's AST check for
  `expectations.py`, and by review everywhere else.

### 8.4 The one thing the suite cannot prove

**That the demo's SQL is right in general.** It is not, and Q18's own option text says so: the
subset is not clean, eight of sixteen measured divergence paths sit inside it, and one returns `1`
where Python returns `1e+300`. The suite proves that **the demo behaves as specified on the seeded
data**, that **the control which makes that safe is alive**, and that **the control has been watched
firing** (AC-22 asserts the disagreement). Whether the subset is trustworthy is **T-3's** question,
and nothing here may be quoted as an answer to it.

---

## 9. Risks, each with what to do about it

| # | Risk | Why it is real here | What to do about it |
|---|---|---|---|
| **1** | **The two panes drift on a detail nobody pinned.** W10 and W12 are two workers implementing one behaviour twice — which is the demo's whole design and also its main hazard | The spec has already been bitten by three ellipses (`lag(…)`, `date_trunc(…, …)`, `avg(…)`), each of which was a decision moved to build time and then made twice | **§4 of this plan is the contract, and it has no ellipsis.** Where it is silent the answer is a **new `B` ruling written into this file**, never a local convention. The mutation pass (§8.2) is the check that the two really do agree for the right reason |
| **2** | **The wheelhouse cannot be built** — the build host is offline, or `pip download` fetches wheels for the wrong platform tag | B20 needs one networked step, and manylinux/CPython-3.12 tags must match this machine | Populate it with `pip download --python-version 3.12 --platform manylinux2014_x86_64 --only-binary=:all:` and **verify by installing into a throwaway venv with `--no-index` before committing**. If the host is offline, fall back to installing from PyPI at `up` time, **record it as a deviation in the handoff**, and put the AC-32 wording to Evan — do not quietly redefine his criterion |
| **3** | **Something touches `glp-strong-db` on 55433.** It has happened on this project before and was called out as a defect | It is running right now, healthy, holding his live data, and it is a Postgres on this machine that a careless default could find | Three independent fences, all in this plan: `db.py` **raises** on any port but 55440 and passes every libpq parameter explicitly (**B13**); AC-3's grep forbids the strings anywhere in the demo tree; `ops/checks/neighbour-ports.sh` runs **before and after** and asserts by port number from outside the tree. **Run the neighbour check manually once before W4 and once after, and put both transcripts in the evidence pack** |
| **4** | **T-4's timing run starts beside this build and gets void numbers** | T-4 needs an idle host; this build is exactly the heavy work that voids it | Already sequenced (`.autodev/specs/T-2-queue.md`: T-4 **not today**, waiting for a window Evan names). If anyone starts it, stop and say so — the measurement is worth more than the hour |
| **5** | **The built screen goes past the approved drawing.** Two places, both deliberate: **B5a** greys one more control on the bucketed view than the mock does, and **B31** adds an `invented` chip to each answer pane's head | "Approved as drawn" is a real commitment, and quietly exceeding it is how a sign-off stops meaning anything | Both are **named in the handoff, explicitly, as the two places the build exceeds the drawing**, each with its one line to overturn. Neither is a look change he cannot see in ten seconds |
| **6** | **`render_for_display`'s output gets executed.** Its own comment says *"NEVER execute this"* | It is a string that looks like SQL and reads better than the parameterised form | **AC-27 asserts at the driver boundary**, not by reading code, and `db.py` is the only module in the tree that imports the driver — a grep enforces it. The display string never leaves the response object |
| **7** | **The committed bundles go stale** — someone edits the JSX and forgets `./run-demo build-ui`, so the screen a reviewer sees is not the screen the source describes | AC-36 makes the bundles the thing that runs; nothing otherwise ties them to their sources | `manifest.json` records a **sha256 over the concatenated JSX sources**, and the suite fails if the bundle's recorded source-hash does not match the current sources. `build-ui` updates both |
| **8** | **A gap in `demo/gate.py` ships an unchecked construct.** It is new, it is safety-critical, and it is the only thing between the demo and the fifteen out-of-subset functions `compile.py` will happily compile | An allowlist with an accidental extra entry is invisible in review | AC-14 is **table-driven over the full 48-construct census plus all twelve tags plus a thirteenth**, so the test enumerates rather than samples; the allowlist **fails closed**, so a construct nobody thought about is refused rather than allowed; and **M12** proves the tag half of the test actually fires |
| **9** | **The suite's own writes corrupt the seed**, and a later run's counts are wrong for a reason nobody traces | AC-23(a) mutates and AC-45(b) inserts | **B10**: rolled-back transaction for the insert, explicit restore for the mutation, and **AC-10's checksum asserted at session start and session end**. **M16** proves the guard fires |
| **10** | **A `noun:Sample` aggregate aborts the whole pick** with SQLSTATE `22P02` the first time a `field_n` holds a string | Its extra keys are deliberately of mixed type; the obvious `(<j> #>> '{}')::numeric` raises on the first one | §7.2 item 5's `jsonb_typeof` guard, applied through the single `numeric_read()` (§4.5), and **M14**, which removes it and requires the raise |
| **11** | **`expr.py` drifts in GIMS while this is being built** | Both trees are live checkouts of someone else's project | AC-34's **tree half** catches it and reports; the **vendored copy stays the authority for the demo** (R4) and a drift is a finding to write down, not a demo failure. AC-35 additionally proves the demo did not cause it |
| **12** | **The worktree collides with a stack already up** — the container name and the two ports are global to the machine, not per-worktree | Full process means an isolated worktree | AC-5's refusal already covers the ports; **B23** covers the container name and makes `test` refuse rather than adopt a foreign stack. Locate §8 is the full list |
| **13** | **The browser layer is never actually run**, so the visual half of DR-1 is asserted by nobody | Playwright is not installed here and B22 makes it optional | The **always-on contract tests carry the load** and are the ones the criteria are written against; the browser skip is **loud and counted separately**, so a run without it cannot be mistaken for a full one. If the `uat` stage wants the visual evidence, installing Playwright is one command on a networked machine |
| **14** | **Evan overturns a ruling mid-build.** The likeliest are **B4** (ops 7/8/9 heartbeat-only), **B5a** (the legality matrix) and **B31** (the third invented label) | They are the three visible product choices, and wrap-up item 26 already offered him the first two | Each carries **one line to overturn and a stated blast radius**, so the cost is known before he decides. None of the three reaches the gate, the probes, the comparator or the seed — the four things that would be expensive to redo |
| **15** | **A criterion passes because it never ran.** The exact failure T-1's re-check found in its own harness | Six of that harness's failure branches had **0 executions** across a full run | The **mutation pass** (§8.2). Sixteen mutants, each naming the criterion that must fail. A surviving mutant is a build failure |

---

## 10. What this plan deliberately leaves open

### 10.1 Left to the builder — small, local, and not worth a ruling

- The `note` vocabulary's sixteen words, and the exact 90/8/2 draw, bounded by AC-8 and AC-40.
- Pixel values inside part 5.2's new classes beyond what the mock draws; the mock is the authority.
- The pinned wheel **versions** (the *set* is pinned at B20; the versions are whatever installs
  cleanly on CPython 3.12 and is recorded in `requirements.txt` with hashes).
- Module-level organisation inside each file, provided §4.5's "one place per rule" table holds.
- Refusal message wording beyond the shapes §4.4, §4.10 and §9.3 pin — except that no message may
  ever read *"invalid input"*.
- The mutation harness's implementation (patch-and-revert, or a fixture that monkey-patches).

### 10.2 Stays Evan's — §14.2, unchanged

1. **Does `demo/expected-answers.json` stay?** Q24's option 3 was "Both" and he ticked option 2.
   Deleting it would take away something he ticked, and delegated authority does not stretch that
   far. **If he says nothing: it stays**, clearly subordinate to the side-by-side, which is not
   droppable either way (§5). **B8** makes it honest while it is here.
2. **What "done" looks like at the `accept` gate.** The 45 criteria are what a build can be tested
   against; the gate is his eye on the running screen. This plan does not attempt to define it
   beyond §5's control being demonstrably alive.

### 10.3 Named for him because they are visible product choices, not implementation detail

Wrap-up item 26 already put the first two to him and he returned them with *"use your best judgement
and previously answered questions for guidance"*. They are ruled here, and they are the three worth
his ten seconds:

| ruling | what he would see | one line to overturn |
|---|---|---|
| **B4** | Time buckets, the rolling window and "only what changed" are **available on the heartbeat only**; on the other two collections they are greyed with the collection's field list as the reason | *"Let me bucket and window the other collections too"* |
| **B5a** | Some control combinations are greyed rather than refused after the fact — including **one more on the bucketed view than the mock drew** | *"Let me try any combination and tell me afterwards"* |
| **B31** | The invented-data label appears in **three** places, one of them a small chip in each answer pane's head — one more than the mock drew | *"The header chip is enough"* |

And one that is his by deferral rather than by choice: **B6** pins `extra_float_digits = 1` and
displays it, making no claim it is the right value. **T-3 answers that**, and when it does, T-3's
finding supersedes B6 — not a new judgement here.

---

## 11. Evidence

| Claim | Where it was checked |
|---|---|
| `compile.py`'s `_bind` restarts at `p0` per instance; `compile_ast` builds a fresh `_Compiler` | `spikes/T-1/proto/compile.py:159-164`, `:437` — opened |
| The stray-`%` guard in `compile_ast` has body `pass` | `compile.py:439-441` — opened |
| The twelve `_t_*` methods the gate must accept at the tag | `compile.py:196` dispatch; `:204 :212 :215 :218 :222 :243 :246 :252 :255 :259 :277 :297` |
| `xpr.truthy(jsonb) RETURNS boolean` and is **never NULL** — so the filter predicate is `xpr.truthy(<compiled>)` | `spikes/T-1/proto/runtime.sql:61-75` — opened. **The spec never states the filter's boolean bridge; §4.1 of this plan does** |
| 21 `xpr.*` functions in 427 lines | `grep -n "CREATE OR REPLACE FUNCTION" runtime.sql` → 21 |
| The shipped guard is **297 digits**, value `1.7976931348623157e+296`, and **returns NULL rather than raising** | `runtime.sql:33-34`, `:51-53`; digit count taken mechanically |
| `gen_data.py`'s record rule, its unpadded `S-{i}`, and that it holds no heartbeat path | `spikes/T-1/proto/gen_data.py` read in full (65 lines) |
| `expr.py` byte-identical in both GIMS trees at `90cbb56d…`; the six Watery assets match part 1.1's digests | `sha256sum`, re-run 2026-08-22 |
| **AC-33's baseline digests, taken today with both files confirmed unmodified in `git status`** — `compile.py` `b71b153802d0df9479141ac02b662ca94d86268a940f66f1fb7a9782c8d0f3e2`, `runtime.sql` `32628b45f2d1dd043f71728dc7e100e2f54bd7bff508a775c3c05f5b15f77b23`. **These two strings go into `demo/manifest.json` verbatim at W2** | `sha256sum`, 2026-08-22 |
| **T-3 is editing `spikes/T-1/proto/conformance.py` and `analysis/fuzz/differ.py` in parallel today** (Q7 permits it). Neither is an AC-33 file, and the two that are remain untouched | `git status --short spikes/T-1/proto/` |
| 18 of the mock's 30 icons are absent from GIMS's sprite; three of the shared twelve differ | symbol-by-symbol comparison, 2026-08-22 |
| The mock's `:root` is watery's minus `--blue-deep`, plus `--mono` | regex diff of the two blocks, 2026-08-22 |
| Docker 29.1.3 / Compose v2.29.2; `postgres:16-alpine` local; 55440 and 8787 free; `glp-strong-db` up on 55433 | `docker --version`, `docker compose version`, `docker image inspect`, `ss -ltn`, `docker ps` |
| Python 3.12.3; PEP 668 in force; psycopg / fastapi / playwright absent; PyPI reachable (200) | `python3 --version`, `ls EXTERNALLY-MANAGED`, an import loop, `urllib.request` |
| `psql` and `pg_isready` absent | `which psql pg_isready` |
| `.gitignore` swallows `dist/` and `build/` | file read |
| X1 and X2, the DR-2 rule, and that the mock's DISABLED logic is **live** rather than painted | `design/t2-demo.md` parts 3.1.2 and 11 |
| The look sign-off, verbatim | the ticket passport, 2026-08-22, GA-6 |
| T-1's harness had **0 executions** of every failure-reporting branch — the precedent behind §8.2 | `kb/wiki/decision-expr-to-sql.md` §5 |

**Read-only throughout.** No file under `spikes/`, no file in either GIMS checkout, and no
`tracker.mjs` / `.autodev/tickets/` / `.autodev/events.jsonl` entry was written by this stage.
Nothing connected to port 55433. **No demo code was written** — this stage is locate and plan only.
