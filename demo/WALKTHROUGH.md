<!--
demo/WALKTHROUGH.md — W15 (plan §10, ruling B16).

Every number below is annotated immediately after it, in an HTML comment
that names the exact path inside demo/expected-answers.json it came from
— invisible when this file is rendered, visible in the raw source. That
is not decoration: demo/tests/test_walkthrough_doc.py reads this file as
text, resolves every one of those paths against expected-answers.json,
and fails if a single one is missing or wrong. See that file for what
"every number in the document equals the corresponding entry" actually
means here — a test, not a read (plan §6.2, W15's row).

Do not remove an annotation while editing prose around it, and do not
place a bare inline-code number directly against an HTML comment naming a
JSON path unless the number really does come from expected-answers.json at
that exact path — the test treats every such occurrence as a claim to
check, itself included, which is why this instruction is phrased to avoid
literally typing the shape it is warning about.
-->

# Walking through the demo

This is the same 14 steps Evan drives at the running screen, written down so
the numbers can be checked ahead of time and so anyone reading this later —
without the screen open — can see what it is supposed to show.

Every step below does one thing on the picking panel (the column of numbered
controls on the left of the screen) and then reports what shows up in the two
answer panes beside it: the **SQL pane**, which is the answer Postgres itself
computed, and the **Python pane**, a second, completely separate program that
reads the same rows and works the answer out again from scratch, in Python,
never by asking the database. When the two agree, that is worth something —
two independent pieces of code reached the same number. When they don't
(step 11, on purpose), the screen says so loudly rather than picking one and
hiding the other.

All the data is invented. Nothing below describes a real sender, a real
customer, or anything that happened anywhere. It exists only so this screen
has something to compute over.

## Terms used below

Twelve words appear in what follows without being ordinary English, either
because they're SQL (the language the SQL pane's statements are written in)
or because they name a specific rule this screen follows. Each gets one
sentence, here, the first time it would otherwise be unexplained.

| Term | What it means |
|---|---|
| **`LATERAL`** | A kind of join that lets the right-hand side see each row of the left one at a time. It's how the screen answers "list every field name inside this collection" — it runs once per record rather than once for the whole table. |
| **`IS DISTINCT FROM`** | Means "different, and a missing value counts as a value." The ordinary `<>` doesn't: if either side is missing, `<>` refuses to answer at all rather than saying yes or no. Step 9 depends on the difference. |
| **`NULLS LAST`** | Where rows with nothing in the sort field go. Postgres's own default for this flips depending on whether you sort ascending or descending, which is confusing enough that this screen states it explicitly every time rather than relying on the default. |
| **`to_char`** | A Postgres function that turns a date or a number into text, in a format you specify — used here to print a bucket's date the same way every time. |
| **`PRIMARY KEY`** | The column, or pair of columns, that identifies one row uniquely. The database itself refuses to store a second row with the same one. |
| **SQLSTATE `22P02`** | A five-character code Postgres attaches to one specific error: "that piece of text is not a number." A program can check for this code without reading the English sentence next to it. |
| **stable sort** | A sort that leaves two equal items in whatever order they arrived in. Python's sort has this property; Postgres's does not — which is exactly why every result on this screen carries a tiebreak (see "the tiebreak," used throughout below), so "the first row" always means one specific row and not whichever one the database happened to read first. |
| **allowlist / fails closed** | Listing what is *permitted*, so anything not on the list is refused automatically — the opposite of listing what's *banned*, which lets tomorrow's new problem straight through. Step 14 is this rule in action. |
| **closed set** | A choice that must be one of a fixed, finite list the screen itself offers — there is no box to type a different answer into. Where a collection or a status is picked below, it's a closed set. |
| **parameterised statement** | A way of sending SQL where the query's text and the values inside it travel to the database separately — the values are never pasted into the text. This is the ordinary safe way to talk to a database, and it's why typing something hostile into a filter or an expression can't turn into a different SQL statement (steps 12–14 test the one place this screen has to be more careful still). |
| **CTE** | Short for *common table expression* — a named sub-result, written `WITH name AS (…)` in front of a query, so the rest of the query can read it exactly like a table. Step 9's statement uses one. |
| **`AT TIME ZONE`** | Re-reads a stored instant as if you were looking at a clock in a specific place. Step 7 is the one place on this screen where the time zone changes the answer, and it's why that step shows which zone the session used, right on the screen. |

### Why this screen doesn't sort exactly like GIMS's own dashboard

A few steps below (2, 4, 5 and 9) depend on a specific tiebreak rule this
screen enforces on every result: ties are broken by each row's own `key`,
ascending, no matter which way the rest of the sort runs. GIMS's own
dashboard sorts differently, and this screen deliberately does not copy that
part of it. The reason is a real, previously recorded finding rather than a
guess: a recorded divergence probe
(`spikes/T-1/analysis/measurements.json → tolerant_key_probe`), in which
GIMS's tolerant key matching returns one id where the two-path comparison
expected three. Building this screen's ordering on a mechanism with an open
finding like that would put a known-uncertain comparator underneath the very
thing this demo exists to check — every disagreement it produced would be
indistinguishable from a real one. So this screen defines its own, narrower
ordering rule instead, and pins it explicitly rather than inheriting it.

---

## Step 1 — Run the one command, from a clean checkout

**What you do.** From a fresh clone, run `./run-demo up`. Nothing is picked
yet — this step is about the infrastructure starting up, not about the data.

**What to expect.** The demo's own database comes up on port
`55440`<!--#steps[0].expect.db_port--> and the app on port
`8787`<!--#steps[0].expect.app_port-->. Neither of those is the port Evan's
live database runs on — this demo never touches that machine, under any
circumstance. Once the database is seeded, it holds
`10,410`<!--#steps[0].expect.rows_loaded--> rows in total, all of them
invented: `8,400`<!--#corpus.heartbeat_rows--> in the collection
`noun:Heartbeat`, `2,000`<!--#corpus.sample_rows--> in `noun:Sample`, and
`10`<!--#corpus.edge_case_rows--> in `noun:EdgeCase` — the three collections
every other step below picks from.

---

## Step 2 — Choose a source: `noun:Heartbeat`, nothing else picked yet

**What you do.** On control **`1`<!--#steps[1].pick.operation--> — Choose a
source**, pick `noun:Heartbeat`. Leave every other control alone.

**What to expect.** Both panes return
`8,400`<!--#steps[1].expect.row_count--> rows — the whole collection, since
nothing has filtered it yet. Because no sort field was picked, the tiebreak
rule from the glossary above is the *only* ordering in play, and that's what
makes "the first row" a meaningful thing to ask for at all: it's
`hb-01-0000`, the lowest key in the collection, and the last is
`hb-50-0167`, the highest.

---

## Step 3 — Add a computed column: `alive = $.status == "ok"`

**What you do.** On control **`2`<!--#steps[2].pick.operation--> — Computed
columns**, add one named `alive`, with the expression `$.status == "ok"`.
This is accepted, not refused — it's a plain field comparison, squarely
inside what this screen allows an expression to do.

**What to expect.** Every heartbeat row's `status` is one of three fixed
values — `ok`, `warn`, or `error` — so this splits the 8,400 rows into two
counts that must add up to the step-2 total: `7,543`<!--#steps[2].expect.true_count-->
rows where `alive` comes out true, and `857`<!--#steps[2].expect.false_count-->
where it comes out false. `7,543 + 857 = 8,400` — the two counts partition the
whole collection, with no third bucket, because `status` is never missing on
this collection.

---

## Step 4 — Filter: `$.status != "ok"`

**What you do.** On control **`3`<!--#steps[3].pick.operation--> — One
filter**, filter `noun:Heartbeat` down to `$.status != "ok"`.

**What to expect.** `857`<!--#steps[3].expect.row_count--> rows — the exact
complement of step 3's true count, reached by a completely different route
(a filter rather than a computed column), which is itself a small check that
the two numbers agree. The first row in key order is `hb-01-0148`, whose
status is `warn` — visibly not `ok`, which is the filter's whole point.

---

## Step 5 — Sort by `$.ts`, descending, capped at 10 rows

**What you do.** On control **`4`<!--#steps[4].pick.operation--> — Sort
field**, sort `noun:Heartbeat` by `$.ts` descending. On **Row cap**, set the
limit to `10`<!--#steps[4].pick.limit-->.

**What to expect.** Here's where the tiebreak rule earns its keep. Every one
of the 50 senders shares the exact same latest timestamp, so the entire
result is one 50-way tie, and the row cap has to cut somewhere *inside* it.
The rule says ties break by `key`, always ascending — even though the sort
itself is descending — so what actually comes back is the 10 **lowest** keys
at that latest instant: `hb-01` through `hb-10`, each at their final beat.
A Python program that broke the tie the naive way — sorting the whole tuple
in reverse, key included — would return the 10 **highest** keys instead, and
disagree with the SQL pane on all ten rows without anywhere being obviously
wrong. `10`<!--#steps[4].expect.row_count--> rows come back either way; which
ten is the entire test.

---

## Step 6 — Aggregate: sum of `$.payload.load`

**What you do.** On control **`6`<!--#steps[5].pick.operation--> —
Aggregate**, choose `sum` over the field `$.payload.load`, still on
`noun:Heartbeat`.

**What to expect.** `400,207`<!--#steps[5].expect.sum-->, across all
`8,400`<!--#steps[5].expect.row_count--> rows — every one of them
contributes, because `payload.load` is present and numeric on every single
heartbeat row. That total isn't just trusted by eye: `payload.load` is
always a whole number from 0 to 100, so the sum has to land between 0 and
`8,400 × 100 = 840,000`, and 400,207 does; dividing back out gives a mean
load of about 47.6, which is close to what a uniform draw between 0 and 100
would produce. Both panes are checked against this number on their own,
separately, before they're ever compared to each other — the one walkthrough
number that used to be checked only by comparing the panes to one another,
which is no check at all if both panes happen to share the same mistake.

---

## Step 7 — Time bucket by day, count per bucket

**What you do.** On control **`7`<!--#steps[6].pick.operation--> — Time
buckets**, choose `per day`, with `count` as the aggregate.

**What to expect.** `7`<!--#steps[6].expect.bucket_count--> buckets, one per
UTC day the seeded data spans, every one holding exactly
`1,200`<!--#steps[6].expect.rows_per_bucket[0]--> rows (50 senders × 24
hourly beats). `7 × 1,200 = 8,400` — the same total as step 2, which is a
real check: if the session's clock were off by even an hour, the same 8,400
beats would split into 8 buckets instead of 7, with one holding far fewer
rows than the rest. Every bucket:

| Day (UTC) | Rows |
|---|---|
| `2026-08-14T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[0].count--> |
| `2026-08-15T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[1].count--> |
| `2026-08-16T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[2].count--> |
| `2026-08-17T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[3].count--> |
| `2026-08-18T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[4].count--> |
| `2026-08-19T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[5].count--> |
| `2026-08-20T00:00:00Z` | `1,200`<!--#steps[6].expect.buckets[6].count--> |

The two panes compare these day labels **as text**, not as instants — because
Postgres and Python don't necessarily spell the same moment the same way by
default, and a mismatched spelling would look like a disagreement about the
data when it's really only a disagreement about formatting.

---

## Step 8 — Rolling window: 3-point trailing average of `$.payload.load`

**What you do.** On control **`8`<!--#steps[7].pick.operation--> — Rolling
window**, choose the field `$.payload.load`. The width
(`3`<!--#steps[7].pick.width-->), the direction (trailing) and the average
itself are all fixed by this control — there's no box to change them,
because that's what the underlying rule requires.

**What to expect.** One rolling average per row — all
`8,400`<!--#steps[7].expect.row_count--> of them — where each value looks
back at up to 3 rows: itself and up to 2 before it, from the *same* sender
only. Right at the start of a sender's rows there aren't 3 yet to look back
at, and what happens then is the whole point of this step: the average
divides by however many rows are actually in the frame — 1, then 2, then 3
— never always by 3, and never blank until 3 have piled up. A version that
got this wrong would still be right everywhere except the first two rows of
every sender, and quietly wrong on precisely those 100 cells — the kind of
mistake that looks like a real finding when it's a bug.

Worked by hand, sender `hb-18` (chosen because its first three rolling
values are genuinely different from each other, unlike most senders — a
sender whose first few loads happen to repeat would make this step prove
nothing):

| Beat | Load | Rows averaged | 3-point average (6 places) |
|---|---|---|---|
| `hb-18-0000` | `27`<!--#steps[7].expect.worked_loads[0]--> | `27`<!--#steps[7].expect.worked_values[0].window[0]--> | `27.000000`<!--#steps[7].expect.worked_values[0].value--> |
| `hb-18-0001` | `88`<!--#steps[7].expect.worked_loads[1]--> | `27`<!--#steps[7].expect.worked_values[1].window[0]-->, `88`<!--#steps[7].expect.worked_values[1].window[1]--> | `57.500000`<!--#steps[7].expect.worked_values[1].value--> |
| `hb-18-0002` | `88`<!--#steps[7].expect.worked_loads[2]--> | `27`<!--#steps[7].expect.worked_values[2].window[0]-->, `88`<!--#steps[7].expect.worked_values[2].window[1]-->, `88`<!--#steps[7].expect.worked_values[2].window[2]--> | `67.666667`<!--#steps[7].expect.worked_values[2].value--> |
| `hb-18-0003` | `88`<!--#steps[7].expect.worked_loads[3]--> | `88`<!--#steps[7].expect.worked_values[3].window[0]-->, `88`<!--#steps[7].expect.worked_values[3].window[1]-->, `88`<!--#steps[7].expect.worked_values[3].window[2]--> | `88.000000`<!--#steps[7].expect.worked_values[3].value--> |
| `hb-18-0004` | `88`<!--#steps[7].expect.worked_loads[4]--> | `88`<!--#steps[7].expect.worked_values[4].window[0]-->, `88`<!--#steps[7].expect.worked_values[4].window[1]-->, `88`<!--#steps[7].expect.worked_values[4].window[2]--> | `88.000000`<!--#steps[7].expect.worked_values[4].value--> |

Row 3's average (67.666667) is the interesting one: `(27 + 88 + 88) / 3`
never terminates in decimal, so it's the row where rounding to 6 places
half-up (see "half-up" — a tie goes away from zero, the way a person rounds
by hand, which is *not* the default either language uses on its own) is
actually deciding the last digit rather than just formatting an exact
answer.

---

## Step 9 — Show only rows that changed, per sender

This is the case the project was built to demonstrate: out of a stream of
mostly repeated values, show only the rows whose value differs from the one
right before it.

**What you do.** Turn on control **`9`<!--#steps[8].pick.operation--> —
Show only rows that changed**, still on `noun:Heartbeat`. There's a toggle
and nothing else — what "changed" compares is fixed by the same rule that
built the data, not something you choose.

**What to expect.** `861`<!--#steps[8].expect.kept_count--> of the 8,400 rows
survive — inside the expected band of
`700`<!--#steps[8].expect.band[0]-->–`1,100`<!--#steps[8].expect.band[1]-->,
and there are two independent ways to sanity-check that number without
running anything: every sender's very first beat has no predecessor, so it's
always kept — that alone is 50 rows — and the seed redraws a genuinely new
value about one beat in ten, so roughly `50 + 50 × 167 × 0.10 ≈ 885` is what
that mechanism predicts, and 861 sits right there. What "changed" actually
compares is the **whole record except the timestamp** — `status` and
`payload`, jointly. That exclusion is the entire operation: put the
timestamp back into the comparison and every single row would differ from
the one before it, because the timestamp always advances. The number that
would come back then is stated here on purpose, as a negative control:
`8,400`<!--#steps[8].expect.kept_if_ts_included--> — all of them, a ten-fold
miss that would be easy to overlook if it weren't written down as a number
in its own right.

The five lowest surviving keys under the tiebreak rule — all from `hb-01`,
because key order groups a sender's own rows together — are `hb-01-0000`,
`hb-01-0006`, `hb-01-0007`, `hb-01-0041` and `hb-01-0056`.

---

## Step 10 — Try a computed column using `round(…, 1)`

**What you do.** On control **`2`<!--#steps[9].pick.operation--> — Computed
columns**, try adding one named `rounded` with the expression
`round($.payload.load, 1)`.

**What to expect.** Refused — and refused before a single character of SQL
exists. `round` is one of the small number of functions this screen's
expression language does not allow, and that decision is made by reading the
typed expression alone, without looking at a single row or touching the
database. Both panes stay empty, because neither calculator is ever reached.
The refusal names the construct: `round`.

---

## Step 11 — On `noun:EdgeCase`, computed column `biggest = max($.m)`

This is the one step on this walkthrough where the two panes are *supposed*
to disagree — the deliberate demonstration this whole screen exists to make
visible rather than hide.

**What you do.** Switch source to `noun:EdgeCase`. On control
**`2`<!--#steps[10].pick.operation--> — Computed columns**, add one named
`biggest` with the expression `max($.m)`. (`max` itself is allowed —
it's `sum` and `avg` that this screen refuses; that's why this step runs at
all where step 10 didn't.)

**What to expect.** The one row with an `m` field holds the array
`["１２３", 1]` — its first element is a piece of *text*, and the digits in
it are the wide, full-width kind sometimes typed on a Japanese keyboard,
not the ordinary `123`. Both calculators try to read that text as a number
before taking the biggest value, and this is exactly where they part ways.

Python recognises digits from any writing system, so it reads the text as
the number one-hundred-twenty-three, and the Python pane reports
`123`<!--#steps[10].expect.python_value-->, the larger of the two elements.

The SQL side's number-reading rule only recognises the ordinary characters
`0` through `9`, so to it that text is not a number at all — it comes back
as *missing*, `max` ignores anything missing, and the SQL pane reports the
only element left standing: `1`<!--#steps[10].expect.sql_value-->.

Neither side warns you. Each answer looks perfectly plausible on its own —
which is exactly why the screen has to say so loudly rather than picking one
side. The verdict here reads *disagree*, and a run where the panes ever
happened to agree on this particular step would be the one that's actually
wrong.

(This particular gap is a real, measured finding from this project's
correctness run, not something staged for the demo: the two engines'
shared string-to-number routine genuinely differs on non-ASCII digits, and
until that gap is turned into a loud refusal — already ruled, in a later
ticket — it is the honest live example of a silent disagreement. An
earlier version of this step demonstrated a different gap, a number-range
guard set twelve decades too low; that defect has since been fixed, and
with the fix adopted both panes now read `[1e300, 1]` identically — so
this step moved to the divergence that survived.)

---

## Step 12 — Still on `noun:EdgeCase`, filter `$.where == "alpha"`

**What you do.** On control **`3`<!--#steps[11].pick.operation--> — One
filter**, filter `noun:EdgeCase` with `$.where == "alpha"`.

**What to expect.** Refused — but not the way step 10 was. This expression
is perfectly legal on its own; nothing is wrong with it until the database
actually looks at the data. One seeded row's `where` field holds an object,
not a plain value, and comparing an object against the text `"alpha"` isn't
something this screen will silently do — so the pick is abandoned mid-query,
by name, naming the row that caused it (`edge-02`). The SQL pane shows no
number. The Python pane still shows its own answer, clearly labelled as a
fallback rather than as agreement: since an object is never equal to the
string `"alpha"`, and the other nine rows have no `where` field at all,
Python keeps `0`<!--#steps[11].expect.python_pane_rows_kept--> of the 10
rows.

---

## Step 13 — Still on `noun:EdgeCase`, computed column `scaled = $.huge * 1`

**What you do.** On control **`2`<!--#steps[12].pick.operation--> — Computed
columns**, add one named `scaled` with the expression `$.huge * 1`.

**What to expect.** Refused again, and again only once the query is actually
running — SQL is generated this time, which is the visible difference from
step 10's refusal. The seeded row `edge-03` stores `1e400` in its `huge`
field — shorthand for a 1 followed by 400 zeros, far past the largest number
either engine's fast number type can hold — and the SQL pane's guard catches
it and stops before returning anything.

The part worth watching is the other side. **The Python pane cannot read it
either**, and says so: it reports `raised`<!--#steps[12].expect.python_pane-->
rather than an answer, with the error named underneath it. Here is why, in
order. The database does not keep the shorthand you typed; it stores the
number exactly and writes it back out as all 401 of its digits. Python reads
a plain run of digits — no decimal point, no `e` anywhere in it — as a whole
number, so it hands back that exact 401-digit integer rather than an
approximation of it. Then the `× 1` in the expression has to convert that
integer into the very same fast number type the SQL side just refused it
for, and it cannot: the number does not fit, and the conversion fails.

That is a better outcome than it first looks, and it is the point of the
step. The honest statement about this value is *neither calculator can
represent it*, and that is now what the screen says on both sides. The
alternative would be one side quietly printing `inf` — computer shorthand
for "past anything I can count to" — beside the other side's refusal, which
would read as the two calculators disagreeing when in truth they agree
completely: this number is out of reach for both of them. A demo whose
entire purpose is to show you when two calculators differ must never invent
a number to fill a gap; a gap honestly reported is worth more than a
plausible-looking answer nobody can check.

(The refusal has an edge, and it sits exactly at the largest number the
fast number type can hold: another seeded row carries `1e300` — huge, but
representable — and it is never refused; `1e400` is comfortably past the
limit. The refusal is not a blanket ban on large numbers — only on the
ones neither engine can represent safely.)

---

## Step 14 — Back on `noun:Heartbeat`, a hostile column name

**What you do.** On control **`2`<!--#steps[13].pick.operation--> — Computed
columns**, add one whose **name** — not its expression — is
`alive"; DROP TABLE demo.records; --`, with an ordinary, harmless expression
underneath it (`$.status == "ok"`).

**What to expect.** Refused, before any SQL exists at all. A computed
column's name is the one piece of what you type that has to be written
directly into the SQL text — every value in every other control travels to
the database separately from the SQL text itself (that's what "parameterised
statement" means, in the glossary above). So the name is checked against a
fixed allowlist before anything is built, and this one isn't on it — the
refusal names both the offending text and the rule it broke. Nothing is ever
sent to the database. Confirming that isn't left to the refusal message
alone: picking `noun:Heartbeat` again afterwards still returns
`8,400`<!--#steps[13].expect.table_survives--> rows — the same count as step
2, proving the table is exactly as it was.

Retyping the name as plain `alive` is accepted, and shows up in the SQL pane
emitted as `AS "alive"` — a quoted, ordinary column name, with the Python
pane keying its own answer the same way.
