# Decision — T-44: the faster compiled path is right and 9× faster than Python, but missed 300 ms on a loaded host

**Status: OPEN. This is the packet for T-44's `sp_decide`, not the ruling.** The verdict
against the pre-written bar is **FAIL**, and GA-34 Q2 = A sends a fail to the owner.

**Evidence:** `spikes/T-44/FINDINGS.md` · bar: `spikes/T-44/FRAMING.md` §4 and §10 ·
numbers: `spikes/T-44/out/timing.json`, `out/K_summary.json`

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
