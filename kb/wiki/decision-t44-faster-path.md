# Decision — T-44: the faster compiled path, re-timed on a quiet host, and passed

**Status: RULED — A, and the re-time PASSED.** The quiet re-time ran on 2026-10-01 at
09:00–09:09Z. C_both met every condition of the bar fixed before any run: **108.69 ms at
100,000 rows** (136.71 ms text-encoded), against same-session Python's 829.46 ms and the 300 ms
target. `sp_decide` was cleared at 09:10:51Z on the owner's behalf, under GA-34 Q2 = A
(GA-36). The packet below is kept as it stood when the pass came in. It was written after the
loaded-host run. **The ADR is the last section.**

**Evidence:** `spikes/T-44/FINDINGS.md` (§0 is the quiet re-time) · bar: `spikes/T-44/FRAMING.md`
§4 and §10 · numbers: `spikes/T-44/out/timing-quiet.json` (the pass), `out/timing.json` (the
loaded run), `out/K_summary.json` (correctness)

---

## The decision, in one paragraph

The faster design works on everything except tonight's clock. **It gives zero wrong numbers**
across 11,367 battery expressions and at every timed size. **It answers the 100,000-row widget
in 457 ms while today's Python took 4,292 ms**, measured side by side on the same rows in the
same minutes. That is faster than Python's best *quiet-host* time (784 ms) even under load. **But
it missed the 300 ms target**, because tonight's host ran at a load of about 35 on 20 cores
(a second overnight run). The same load slowed today's Python 5.5×. The bar was written so
that a miss under load is reported as a miss. So the question is whether to measure it
again on a quiet machine, or rule now.

| at 100,000 rows · widget INVENTED · loaded host | C_both (the faster design) | today's Python | the target |
|---|---:|---:|---:|
| number-encoded rows, median / p95 | **457 / 753 ms** | 4,292 ms | ≤ 300 / ≤ 600 ms |
| text-encoded rows (how real number fields are stored), median / p95 | **517 / 824 ms** | 4,380 ms | ≤ 300 / ≤ 600 ms |

**Where the 457 ms went** (measured): about 162 ms is the SQL itself, about 190 ms is moving
the 5,311 matching rows into Python, and about 108 ms is the Python sort. On a quiet host T-4
measured that sort at 5 ms.

---

## The options

| | option | what it costs | what happens next |
|---|---|---|---|
| **A** | **Re-time on a quiet host first.** Same harness, same bar, about 25 minutes with the machine to itself. | One quiet window, when nothing else is running. | A clear pass is cleared on your behalf (GA-34 Q2 = A), and the shipping change is built. A miss comes back to you with that number. |
| **B** | **Rule it passed now**, on what was measured: zero wrong numbers, and about 9× faster than today's Python on the same rows in the same minutes. | You accept the 300 ms target as unproven. | The shipping change is built today. |
| **C** | **Hold the bar, and take the FAIL.** Fall back to T-4's options: close the SQL path, or ship the slow path. | You set aside a design that is right and much faster. | The slow path loses in every cell to the design measured here, so "ship slow" no longer makes sense. "Close" leaves dashboards wrong above 20,000 records: Python's recall is 26% at 100,000. |

## Recommendation

**A.** It is cheap, it fits the bar you set, and the numbers point one way. The design passed
everything except a clock reading taken on a machine twice oversubscribed. Under that load
Python slowed 5.5× and T-4's own path 2.3×. Neither figure is applied to the verdict, but
together they are why the re-time is worth its 25 minutes. **If the quiet window is not coming
soon, B is defensible on the same evidence.**

## What else is waiting on this ruling

- **The shipping change.** That means `compile_inline.py` folded into `compiler/compile.py`,
  and the lever-(a) edits made in `runtime/runtime.sql.in`, then regenerated. It is not built.
- **The corpus teardown.** `autosql-corpus` is still held, for this re-time.
- **T-23's equality question.** It becomes a prerequisite of the shipping change, as the T-4 ADR
  says.

---

## ADR — T-44's ruling (2026-10-01)

- **Decision: A, re-time on a quiet host. It passed.**
  - **The candidate:** C_both, the inline number checks plus the parallel-safe runtime.
  - **Correctness:** zero wrong numbers across 11,367 battery expressions (K1–K4), and identity
    row for row with uncapped Python in every timed cell (K5).
  - **Speed:**
    - 100,000 rows, median: 108.69 ms for number-encoded rows and 136.71 ms for text-encoded rows.
    - 100,000 rows, p95: 123.28 ms and 151.52 ms.
    - Same-session Python: 829.46 ms and 833.76 ms.
    - The bar: ≤ 300 ms median and ≤ 600 ms p95.
    - The negative control ran first: 25/25.
- **Who cleared it, and on what:**
  - The foreman cleared `sp_decide` at 09:10:51Z, on the owner's behalf, citing GA-36.
  - GA-36 names T-44 and carries GA-34 Q2 = A's rule:
    - a CLEAR pass against the bar written before the run is cleared on the owner's behalf;
    - a fail or near-miss parks for the owner.
  - The foreman checked the result against the bar independently before clearing.
  - The owner did not rule by hand.
- **Disclosed with the pass:**
  - The 100,000-row cells ran at a 1-minute load of 2.11–2.81.
  - T-4's original start ceiling (≤ 2.0) would have voided the text-encoded cell.
  - T-44's §10, written before both runs, records load and never voids.
  - The margins are 2.2–2.8× on the median bar and 4.0–4.9× on the p95 bar.
- **Consequences:**
  - **T-52 ships C_both.** It is T-44's spawned child. GA-39 made its merge wait for exactly
    this: "a CLEAR pass on a quiet re-time cleared under GA-34 Q2".
    - The SQL that ships is T-52's head.
    - For this widget it is byte-identical to C_both, and it measured the same: 108.46 / 135.69 ms.
  - **GIMS needs a re-vendor** of the runtime and the compiler once T-52 lands.
  - **T-23's deferred question is settled before shipping.** T-23 asked whether `==` should route
    through `xpr.f8`.
    - T-61 (`0cff5a8`) has since made `==` and `!=` compare numbers as doubles, as GIMS does.
    - T-52 keeps T-61's equality forms exactly: parity v8 is 86/86 against main.
  - **The corpus.** Its hold lasted "until T-4's child spike has re-timed against it", which has
    now happened. Removing it stays the owner's call (a banked question). It is the only copy that
    can re-run any of this.
- **What it does not decide:**
  - The widget is invented, so none of the owner's own widgets has been timed.
  - The loaded run's FAIL stands as a measurement of the loaded host. It is not a measurement of
    the design.
