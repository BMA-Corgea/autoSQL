# Do non-ASCII digit strings actually occur in the real data? — options and a recommendation

**Status:** synthesis, awaiting Evan's ruling at `sp-decide` · **Ticket:** T-5 (the homework T-3's
ruling ordered first) · **Written:** 2026-09-01 · **Evidence:** `spikes/T-5/FINDINGS.md`,
`spikes/T-5/FRAMING.md` (bar fixed before evidence, plus Evan's two rulings), three re-runnable
read-only probes in `spikes/T-5/probes/`

**This is a recommendation, not a decision. The decision is Evan's.**

> **The one-line version:** In the data you have — **none, zero, and the zero is trustworthy.**
> But the zero is over **144 strings, not the 1.1 million the earlier figure implied**, and GIMS's
> own CSV import path will accept these values into a number field without complaint. **It has not
> happened. Nothing stops it happening.**

---

## What was asked, and what came back

T-3 found that the compiled SQL returns wrong numbers, and one of the causes was this: a string like
`１２３` (full-width digits) reads as **123** in Python and as **nothing** in SQL, silently. T-3
proved the failure *can* happen. It never measured whether it *would*. Your ruling was **homework
first** — go and look at the real data before spending anything bigger. This is that homework.

**Two facts came back, and they point in different directions.**

### Fact 1 — the stored data is clean, and that finding is solid

Eight databases, opened read-only, **38,457 rows and 1,141,929 strings**: not one non-ASCII digit,
not one non-ASCII space. That reproduces the earlier sweep with a fresh instrument eleven days later
— four independent instruments now agree — and it is a *meaningful* zero rather than an empty one,
because **48,297 of those strings do carry other non-ASCII characters** (dashes, arrows, box-drawing,
emoji). The data could have had them. It doesn't.

### Fact 2 — but the number that made it sound overwhelming was the wrong number

The earlier sweep reported "**0 out of 1,096,202**". That counts every piece of text in the database.
The count that matters is much smaller: **strings a dashboard would actually try to turn into a
number**. That figure is **144**. Of those, **137 are in the one small tenant project**.

So the honest statement is **"zero out of 144"**, on one machine, from one operator, in a project
whose noun list includes `Soup Ladel` and `LL Cool J`. Both statements are true. Only one of them
tells you how much weight the zero can carry.

### Fact 3 — the finding that isn't a row count at all

You pointed at it yourself: *"there's a method of adding rows and data for a run or noun via CSV."*
Following that path through the code, **every link is open**:

- The CSV reader hands back **every cell as text, exactly as typed** — it never tries to parse numbers.
- The check that is supposed to enforce *"this field must be a number"* is one line: `float(value)`.
  **Python's `float()` happily accepts full-width, Arabic-Indic, Persian, Thai and Devanagari
  digits.** So the check says yes.
- Nothing downstream converts or cleans it. **The original text is what gets stored.**
- Your dashboard today reads it correctly. **autoSQL's compiled SQL reads it as blank.**

Run against GIMS's real validator: **8 of 10 forms sail straight through**, including a `7` with a
non-breaking space around it — which is what an ordinary Excel export produces, no unusual language
required. And these land in real, **required** fields: `Sample Weight (g)` and `Dilution Weight (g)`
on `Potency Sample` and `Terpene Sample`. Every number-typed field in that project that holds any
data at all **holds it as text** — so this coercion path isn't an edge case, it's how every number
in the project is read.

---

## The options

### A. Proceed exactly as ruled — fix it in autoSQL, re-run the batteries

Pin the float-digit setting, make autoSQL **refuse loudly** on a value it can't read the same way
Python does, and re-run T-3's tests against the same unchanged bar.

**The honest case for it:** the homework says these values occur **zero** times, so a refusal costs
you nothing that exists today — it can only fire on data you don't have. This was your ruling, and
the evidence supports it rather than undermining it. **Against:** it leaves the front door open, so
the first time a customer imports a spreadsheet from a lab that writes Thai numerals, autoSQL starts
refusing where the old dashboard quietly worked.

### B. Proceed as ruled, **and** close the door in GIMS as a separate piece of work

A, plus tighten GIMS's `is_number` so `１２３` is rejected at import instead of being stored.

**For:** it fixes the problem at the one place it enters, and it's a small change — one function.
**Against:** it's **GIMS's** code and GIMS's product behaviour, not autoSQL's. A spreadsheet that
imports fine today would start being rejected, which is a real decision about your users, not a
tidy-up. It also does nothing about rows already stored or about the write path in Fact 4 below.

### C. Close the door **instead** — don't harden autoSQL

Fix `is_number` and leave autoSQL tolerant.

**For:** cheapest of all. **Against — and this is the one I'd argue hardest:** it makes autoSQL's
correctness depend on GIMS's validator, which is exactly what you ruled against — *"autoSQL should
be its own project. If it's not we have a much bigger problem on our hands."* It also doesn't hold:
we found `Glove.size`, a field declared as a number, containing **`'lmao im a changling'`**. Something
already writes rows without running that check. A door-only fix guards a door that has a hole beside it.

### D. Narrow the language, or stop

T-3's options A and B. **The trigger that would have pointed here did not fire.** The bar written
before any evidence said: revisit the ruling if these values turn out to be *common*. They are not
present at all. **Choosing D now would mean ignoring the homework you ordered.**

---

## Recommendation

**Take A. Put B's door-fix to yourself separately, as its own small GIMS ticket, and do not let it
hold up the re-run. Add one thing to A: make the refusal countable.**

Why:

1. **The evidence supports your original ruling.** You ordered the homework precisely to find out
   whether the fix would turn silent wrong numbers into constant visible refusals. It won't — the
   rate today is zero. The main risk to your plan has been measured and it isn't there.
2. **C is ruled out by your own architecture call**, and independently by the `Glove.size` finding.
3. **D has nothing behind it.** No evidence arrived that argues for narrowing or stopping.
4. **B is a good idea wearing the wrong hat.** It's a GIMS product change about what your users are
   allowed to upload. It deserves its own decision, not a line item inside a correctness re-run.
5. **The one addition — count the refusals.** Fact 2 is the uncomfortable one: "zero out of 144" is
   a weak guarantee about a product's future, and no amount of sweeping this machine will strengthen
   it. The way out isn't a bigger sweep, it's **making the first real occurrence visible**. If
   autoSQL records every time it refuses a value, then the day a customer's spreadsheet trips it,
   you *see* it instead of inferring it. That converts a question nobody can answer today into one
   that answers itself later, and it's cheap to build while T-6 is already in there.

---

## What this does NOT settle

- **Production data was never examined**, and cannot be from here. Everything above is one machine,
  one operator, a sandbox tenant project.
- **`glp_strong` was deliberately not touched**, on your ruling that it's the wrong corpus. Correct
  call — but it means the largest database on the machine is unexamined, and that's worth saying out loud.
- **How often anyone actually imports a CSV, and in what locale, is unknown.** An open door tells
  you nothing about traffic through it.
- **The `Glove.size` bypass was found, not chased.** Which write path skips validation is still
  unknown, and it undermines any plan that trusts declared field types.
- **The GIMS gate stays shut regardless.** Nothing enters GIMS until both T-3's re-run and the
  speed run (T-4) pass. A clean homework buys the re-run, not admission.
