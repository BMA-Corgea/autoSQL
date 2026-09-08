# T-23 · Framing — the raw-mode re-run

**Written after the investigation ran, and that ordering is recorded rather than tidied.** The
foreman directed the battery to proceed while other work was in flight; the framing below is the
question it was answering, and the bar it was answered against, both of which were fixed before
the numbers were read.

## 1. The question

**Does the correctness claim hold for `raw`-mode data?**

T-6 passed with *0 wrong numbers over 11,367 expressions* — the result this project leads with.
Its own decision doc lists *"`raw`-mode data was not re-run"* as an open item, and T-6's framing
§5 said of the one signal T-3 had already seen there: **"if that changes, it is a finding."**

## 2. Why the two modes are not the same experiment

`differ.py`'s own docstring:

- **`py`** — the record is a Python object; *"every number has ALREADY collapsed to an IEEE
  double before it reaches the column."*
- **`raw`** — raw JSON text cast `::jsonb`, Python doing `json.loads` on the same text; *"the
  only mode that can exercise jsonb's `numeric` storage against Python's `float` parse"*, and
  *"the shape of any row written by something that is not this Python process (ETL, migration,
  `psql`, another service)."*

**T-7 established that six of seven GIMS write paths never check the declared type.** Non-Python
writers are the norm, so `raw` is not an exotic case.

## 3. Timebox and stop rules

One session. **Stop and report** if: the corpus cannot be built against the shipping runtime; the
instrument needs editing (it is frozen evidence — extend or stop); or the first divergence found
is unexplainable, in which case the mechanism matters more than the count.

## 4. What a decision needs — the bar, fixed before the numbers

| outcome | what it means |
|---|---|
| **no divergence** | the claim extends to raw data. The open item closes. |
| **divergence with a mechanism** | the claim is **scoped**, not wrong. Report what the 11,367 figure covers and what it does not, at the place the claim is made. |
| **divergence without a mechanism** | stop. An unexplained wrong answer is worth more attention than a counted one. |

**A count is not a rate.** Whatever number comes back is over a **hand-picked adversarial set**,
and may not be quoted as a frequency. This project has already shipped a figure whose name
described something other than what was measured; that is not being repeated.

## 5. What makes the result inadmissible

- **Editing anything under `spikes/`.** It is frozen evidence. The battery imports
  `differ.run_case` and modifies nothing.
- **Running against the frozen spike runtime instead of the shipping one.** The question is about
  what ships: `runtime/runtime.sql`, variant C.
- **Port 55433.** The owner's live database. A throwaway database on 55434, dropped afterwards.
- **Quoting the count as a frequency.** See §4.
