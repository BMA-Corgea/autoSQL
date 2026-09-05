# autoSQL — what's still waiting on you · 21 Aug 2026

> **ANSWERED — 2026-08-21.** This is the blank form, kept as the record of what was asked.
> Every answer the owner gave, and what each one caused, is in [`kb/notes/owner-answers.md`](kb/notes/owner-answers.md).
> The checkboxes and ANSWER lines below are deliberately left empty.

**12 items. 2 of them are your signature — nobody else can do those.**

Write your answer on the `ANSWER:` line. Leave it blank and I take the stated default; saying nothing is a real answer.

---

# Your signature

*Section A*

The one thing nobody else can do. Everything the research was sent back for is done; the summary page is being updated now, and then the decision is yours to sign.

### 1. **[YOUR SIGNATURE]** The re-check is in. Is your ruling still don't-build-yet?

**What's going on:** You answered this once already — don't build; fund the two follow-up runs. Since then the two things you asked for first have both landed. The test rig turned out to be sound, which quietly removes one of the arguments the write-up used to support your answer: it had leaned on the possibility that the 130-of-130 result was hollow, and it isn't. Nothing found touches the three facts the ruling actually rests on — there is nowhere in GIMS's reply to a widget to say the database couldn't do it, the generated SQL is 3.79x to 7.15x slower, and 18 of 33 ways it can disagree with Python cannot be detected in principle. So the answer is probably the same, but you are signing on slightly different ground and should know that.

- [ ] **Stands — don't build yet** — I clear the gate on your behalf with your words on the record, and the two follow-up runs become the next work.
- [ ] **I want to read RECHECK first** — Nothing moves. The document is spikes/T-1/RECHECK-2026-08-21.md and its first page is written for exactly this moment.
- [ ] **It's changed — tell me in notes** — Whatever you write becomes the ruling and I re-plan from it.
- [ ] *Take your stated default* — Nothing moves. The ticket sits at your gate exactly as it did before, and the demo stays behind it.

**ANSWER:** 

---

### 2. **[YOUR SIGNATURE]** Two corrections never made it into the findings document. Fix them, or leave it frozen?

**What's going on:** During the original research one of the reviewing passes died partway through, and six corrections it had produced were never applied. Two of them matter, and both are still wrong in the published text. The catch: the ticket's record pins that document by checksum — a fingerprint of its exact bytes, recorded as proof of what the research actually produced. Editing it now breaks that fingerprint. Leaving it means the errors stay in the main document and only the re-check names them.

- [ ] **Fix them — re-fingerprint the document** — The two corrections go into FINDINGS.md, the checksum changes, and I record why so the old fingerprint isn't a mystery later.
- [ ] **Leave it frozen** — FINDINGS.md stays exactly as the research produced it, errors and all, and RECHECK-2026-08-21.md is the document that carries the corrections.
- [ ] **Show me the two corrections first** — I paste both, you decide after reading them.
- [ ] *Take your stated default* — Frozen. The published text keeps both errors and the re-check carries the corrections.

**ANSWER:** 

---

# Calls that finish work already done

*Section B*

Each of these is a thing that got built or found in the last hour and is sitting one decision short of finished. All of them are one-liners.

### 3. Which model should the heaviest jobs run on?

**What's going on:** You asked for the cheap/mid/top split, and it now works — routine steps drop to a cheaper model instead of everything running on the most expensive one. The top slot is the open question. AutoDev's shipped default there is claude-fable-5, and the worker deliberately left it alone rather than overriding your tooling's own default. The alternative is pinning it to claude-opus-5, which is what everything has actually been running on so far.

- [ ] **Leave the shipped default** — The heaviest steps ask for claude-fable-5, falling back to claude-opus-5 if that isn't available to your account.
- [ ] **Pin it to claude-opus-5** — One line changes; the heaviest steps always get Opus, which you know you have.
- [ ] *Take your stated default* — The shipped default stays. If claude-fable-5 isn't available to you it falls back to Opus, so nothing breaks either way.

**ANSWER:** 

---

### 4. File the four GIMS defects now?

**What's going on:** You said open them in the GIMS repo directly. All four were re-verified by running GIMS's own code on main rather than trusting the research notes, and all four are present. The repo has no issues at all today, so none are duplicates. The drafts are in .autodev/notes/gims-defects.md.

- [ ] **File them** — Four issues get created on BMA-Corgea/GIMS-Project under your GitHub account, and I give you the links.
- [ ] **Show me the bodies first** — I paste all four in full; nothing is filed until you say so.
- [ ] **Hold — not yet** — They stay as drafts in the repo and nothing reaches GitHub.
- [ ] *Take your stated default* — Nothing is filed. They sit as drafts and the four problems stay untracked in GIMS.

**ANSWER:** 

---

### 5. What should actually trigger the Telegram message?

**What's going on:** The route works — a test ping reached your phone. What is missing is the thing that fires it. AutoDev deliberately has no timer and no background dispatcher; nothing runs on its own. So when a ticket stops and waits on you, the message only goes out if something sends it.

- [ ] **I send it when a ticket stops** — Reliable while a session is running, and completely silent if one isn't — which is the exact case you'd want the ping for.
- [ ] **Install the hook** — A rule fires every time a session finishes a turn and pages you if anything is waiting. It changes how your terminal behaves, which is why I haven't installed it without asking.
- [ ] **Leave it manual** — The route stays built but nothing sends anything; you run one command when you want to check.
- [ ] *Take your stated default* — I send it whenever a ticket lands on your gate during a session. No hook is installed.

**ANSWER:** 

---

### 6. Confirm: both follow-up runs, correctness first?

**What's going on:** Your Q6 said both, correctness first. Your Q9 said fund only the speed run. Your Q10 then spent effort widening the correctness run to test three settings, which would be pointless if it were cancelled. I'm reading Q6 as governing and Q9's 'no cap' as the speed run's budget. This is me checking that reading once, not asking again.

- [ ] **Right — both, correctness first** — Confirms what I'm already planning; nothing changes.
- [ ] **No — speed run only** — The correctness battery is cancelled, and with it the three-settings work from Q10.
- [ ] **Speed run first as a kill switch** — The cheap one runs first and can end the project before the expensive one is paid for.
- [ ] *Take your stated default* — I proceed on Q6 governing: both runs, correctness first, no cap on the speed run.

**ANSWER:** 

---

### 7. Name a real widget for the speed run.

**What's going on:** You said you'd name one you actually use rather than have one invented. The speed run can't be scoped without it. It needs to be something the restricted version could actually compile — so arithmetic, comparisons, and the functions abs, coalesce, count, if, length, max, min. Date functions are excluded, which rules out the only widget anyone has ever timed end to end.

- [ ] *Take your stated default* — One gets invented and labelled as invented, which leaves the result arguable if anyone questions whether it represents real usage.

**ANSWER:** 

---

### 8. Your hourly rate, for the time tracking.

**What's going on:** Time tracking is configured and staying local — no spreadsheet, nothing leaves the machine. The rate is the one field left blank, because it isn't mine to guess. Leave it blank and hours still get tracked; only the money column stays empty.

- [ ] *Take your stated default* — Hours are tracked, no rate is applied, and the billing column stays empty.

**ANSWER:** 

---

### 9. Three bugs in AutoDev itself — report them upstream?

**What's going on:** You said report the monitoring fix to the plugin's authors. Two more turned up since. All three are the same shape: a path with a space in it. (1) The watcher's startup line doesn't quote the folder path, so 'Coding Projects' splits in two and it watches nothing — patched locally, and a plugin update wipes the patch. (2) The time tracker builds its own folder name the same careless way, which is most of why your hours read an order of magnitude low. (3) The watcher installer refuses on Windows outright.

- [ ] **Report all three** — One write-up covering all three with the reproduction for each, filed wherever the plugin takes reports.
- [ ] **Just the watcher quoting bug** — The one you already knew about gets reported; the other two stay local workarounds.
- [ ] **None — keep the local patches** — Nothing is reported, and every plugin update silently reverts the fixes until someone notices.
- [ ] *Take your stated default* — Nothing is reported. The local patches survive until the next plugin update, then quietly stop working.

**ANSWER:** 

---

### 10. Should the two machines share notification state?

**What's going on:** Right now the record of what has already been sent to you is kept per-machine and left out of git. That's clean, but it means a hold that's live when you switch machines can page you a second time from the other one. The alternative syncs that record through git, which stops the duplicate but puts machine-specific state into your history.

- [ ] **Leave it — a rare duplicate is fine** — Nothing changes. You may occasionally get the same alert twice after switching machines.
- [ ] **Sync it through git** — Two lines come out of .gitignore; no duplicate pings, at the cost of delivery bookkeeping in your commits.
- [ ] *Take your stated default* — Left as it is. Duplicates are possible but rare, and nothing machine-specific enters git.

**ANSWER:** 

---

# Only you can do these

*Section C*

Both are on the Windows machine, which I can't reach from here. I've written everything so that each one is a copy-paste.

### 11. What is the folder path on Windows that contains your repos?

**What's going on:** The autostart script is written and tested as far as it can be from Linux, but it needs one value filled in at the top and that value isn't recorded anywhere in this repo. On this machine it's /home/corgea/Desktop/Coding Projects. Tell me the Windows equivalent and I'll fill it in for you so the script is ready to run as-is.

- [ ] *Take your stated default* — The script ships with a placeholder that stops with an error until you edit it yourself — safe, but one more step for you.

**ANSWER:** 

---

### 12. Two edits on the Windows box — want them queued for when you're next there?

**What's going on:** The autostart registration, so the monitoring watcher starts itself at logon instead of needing a hand-start every session. And a two-field edit to a file there so both machines report under the name the owner rather than that one still reporting as owner. Neither is urgent and neither breaks anything if you never do it.

- [ ] **Queue them — remind me when I'm there** — I write both into a single checklist at the repo root so you can run through them in one sitting.
- [ ] **I'll handle it, no checklist** — The script and instructions are already committed; nothing more gets written.
- [ ] **Drop Windows entirely** — This Linux machine becomes the only place autoSQL runs, and the Windows setup notes stop being maintained.
- [ ] *Take your stated default* — The instructions sit in .autodev/notes/ where you'll find them if you look. No checklist, no reminder.

**ANSWER:** 

---
