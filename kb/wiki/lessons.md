---
name: lessons
description: Durable lessons this project has learned (seeded stub — fill me in)
type: reference
---

# lessons

Seeded stub (FAC-123): durable lessons land here as the project runs — one entry per lesson, newest first, each citing the ticket/incident it came from.

---

## "Read-only" isn't: a read-only open of a WAL-mode SQLite file writes beside it (GIMS T-33)

*2026-10-01 · GIMS T-33's adversarial review, F1 · fixed in GIMS `9d15c5c`*

**The class.** A read-only flag is a promise about the file you named, not about the files a
library keeps beside it. SQLite in WAL mode opens `-wal` and `-shm` read-write even under
`mode=ro` (Python's `sqlite3` included), CREATES them when they are missing, and writes
read-marks into `-shm`. The main `.db` stays byte-identical, so checking the main file shows
nothing happened.

**Witness.** A `mode=ro` dashboards query at 01:11:24 MDT created `nodes.db-wal` (0 B) and
`nodes.db-shm` (32 KiB) inside the LIVE GIMS project-nodes folder; `nodes.db` was unchanged.
Nothing was removed: deleting a `-shm` that a live process may have mapped is itself unsafe.

**The rule (a NEVER since that night).** Never open a live SQLite file, not even `mode=ro`, not
even for one query. Copy the `.db` and any `-wal` into a fresh `mktemp -d` (re-copy if their
stats moved) and open the copy. Never delete a live `-wal` or `-shm`, even one you created:
report it. GIMS T-33's fix does exactly this (RED `5e9f549`, failing on `a4faf72`; GREEN
`3834889`; landed `9d15c5c`).

---

## A test that can only pass proves nothing (GIMS T-58, GIMS T-39, T-55)

*2026-10-01 · three finds in one night, two by adversarial review and one by a watched-failing run*

**The class.** A test proves a behaviour only if some wrong implementation would fail it. Three
shapes of a test that cannot fail:

1. **It hand-builds the only input that works.** GIMS T-58 F1: every backup GIMS writes restored
   ZERO rows while answering `200 ok:true` (the producers write `dir:"<key>"` and the restore
   read it without `db/`). T-58's test passed because it built the one shape the restore could
   read, not the shape the producers write. Ruled: T-58's merge reverted on the GIMS trunk; the
   rework is safe-by-refusal.
2. **Its lane accepts any fallback.** GIMS T-39 F1: Lane S counted a fallback to Python as a pass,
   so a compiler that refused EVERYTHING passed 119/119. Fixed in `54b3a3f` (Lane S must push
   down unless the case documents a refusal; strict compare); the refuse-everything mutant now
   fails 65/66. Round 2, F1': the refusal oracle shared the adapter's own helpers, so a lying
   `_calls` passed 135/135; fixed in `6baab03` with an independent AST walk.
3. **Its probe cannot say no.** T-55 (this repo): the regression test's stub checked the lock with
   `flock -n <file> true` on a curated PATH that had no `true`, so `flock` failed and "held" read
   yes on every run; one test passed against the unfixed script. Caught only by the
   watched-failing run, and fixed before landing (`540eb76`) with a descriptor probe and a
   conflict code of its own (`-E 75`), so an error can never read as "held".

**The rule.** Feed a test what the PRODUCER writes, not what the consumer can read. Keep every
oracle independent of the code under test. Watch every assertion fail at least once: the unfixed
code, or a mutant that refuses everything, must turn it red.

---

## A fixed port inside the kernel's ephemeral range can be taken by anyone, briefly (T-62)

*2026-10-01 · two collisions on 55440 in one night · T-62's retry, `052508e`*

**The class.** Linux gives client connections source ports from `net.ipv4.ip_local_port_range`
(here 32768–60999). Every dev database port on this machine (5544x–5547x) lies inside it and
none is reserved, so ANY local client can hold 127.0.0.1:55440 as its own source port for a few
seconds. A port check that passes, followed by a bind, is a race that no lock can win.

**Witness.** At 08:29:20Z something bound 127.0.0.1:55440 for about 10 s, between a seat's port
check and its compose start, and Docker refused to start the demo database. No seat's process
held it (checked). Nothing was lost: T-45's launcher re-attached the lost network and kept the
container and its volume.

**The rule.** Treat "address already in use" at start as possibly transient: retry with backoff,
and say why (T-62's `up` retries five times and re-attaches the network: `052508e`). "Port is
already allocated" means a real holder: fail at once. The durable fix is reserving the ports
(`net.ipv4.ip_local_reserved_ports`), a sudo change, put to the owner as a question.

---

## A teardown removes exactly what its own run created: no less, no more (T-25)

**The class.** A teardown must remove exactly what its own run created. **No less** (T-25): if
an image declares `VOLUME` and the run mounts nothing at that path, Docker creates an
**anonymous volume**, and `docker rm -f <c>` removes the container and leaves that volume
dangling, invisible to `docker ps -a`. Both Postgres images this repo uses declare
`VOLUME /var/lib/postgresql/data`. For a container the run created, the cure is `-v` on
`docker rm`, which removes only that container's own anonymous volumes, or `docker run --rm`,
which was measured clean. **No more** (T-45): `--volumes` on `compose … down` is not that cure.
It also deletes the **named** volumes the compose file declares, including one the run did not
create. That is how `./run-demo test` deletes a deliberately kept demo volume (found 2026-10-01;
T-45 is the fix). A service whose data path is a named volume cannot leak an anonymous one
there, so `--volumes` buys it nothing and costs it the kept data.

**Paid for twice.** First by the corpus: about 1 GiB left on disk after a plain `docker rm -f`
(`spikes/T-1/proto/REGENERATE-CORPUS.md` §9, which wrote `-v` into its own teardown). Then by
`ops/runtime-check.sh`, written 18 days later (2026-08-21 → 2026-09-08) without it. Measured 2026-10-01: one normal run
took the machine's dangling count from 74 to 75, and the survivor was the run's own data-dir
mount, about 48 MB. With `docker rm -f -v` the count stayed at 74.

**How it got past its own check.** T-21's criterion was "the throwaway container is destroyed".
That was true, and it was the only thing measured; nobody asked about the volume. It is
witness 7's shape below: the check was right about what it inspected.

**What stops it coming back, and what does not.** `ops/tests/test_volume_teardown.mjs` enforces
the default rule: every teardown it recognises in a tracked shell script outside `spikes/` must
pass `-v`/`--volumes`. It recognises `docker rm`, `docker container rm|remove`,
`docker compose … down|rm` and `docker-compose … down|rm`, plus `docker system prune` (it must
pass `--volumes`) and `docker container prune` (always flagged, because it cannot remove volumes).
Docker can be written as `docker`, `$DOCKER` or `${DOCKER}`, after global flags such as
`--context` or `-H`, inside `$( … )`, or after `sudo` or `xargs`. It does **not** see docker
behind a wrapper function or an alias (`dk() { docker "$@"; }`), in an array or another
variable, or in an `eval`. It also misses Python's list-form calls, files that are not shell
scripts, and a container started with no teardown at all. The rule is a default, not a law: a
deliberate keep of a volume the run did not create needs a reasoned exemption, which T-45 adds.
The guard was watched failing against the unfixed script and planted leaks, and with each of its
own checks broken.

**Cleaning up a volume a run leaked.** If the container still exists, remove it with
`docker rm -f -v <container>`. Docker takes the container's own anonymous volume with it, and
nothing else. If the container is already gone, so is the link, and the volume's creation time
and labels are all that is left. Use `spikes/T-1/proto/REGENERATE-CORPUS.md` §9's recipe: list
the dangling volumes by `CreatedAt`, take the one created when you started the container, check
that its labels say `com.docker.volume.anonymous`, and `docker volume rm` that one id. **Never
prune**: other projects' volumes sit in the same dangling list, and a prune cannot be undone.


### 2026-10-01: the "no more" half, three times, and a fourth rule: one run at a time

- **T-45 (`eb076e7`):** `./run-demo test`'s teardown (`compose down --volumes`) deleted a demo
  volume somebody had kept. It now takes an inventory first and puts back exactly what it found.
- **The live witness, ~07:24Z (a near-miss, no loss):** one seat's `docker start autosql-demo-db`
  failed because another seat's throwaway held 55440 (crossed slot messages). Its chained
  `./run-demo test` ran anyway, found the database down, and ran `up` itself: exactly the path
  to `down --volumes` over the kept volume. The volume survived by luck.
- **T-55 (`540eb76`):** `ops/checks/neighbour-ports.sh` cycled `up`/`down` over a kept stack and
  deleted its volume while printing PASS (watched on a throwaway). It now refuses, exit 2, when
  the demo's container, volume or network already exists.
- **T-62 (`9773300`):** two seats ran the demo suite against one stack, kept apart only by a
  person sequencing them. Now `test`, `up` and `down` take one host-wide flock
  (`/tmp/run-demo.<container>.lock`), and a caller that holds it says so (`RUN_DEMO_LOCK_HELD`).

**The rule, extended.** Decide what is yours by looking BEFORE you create anything (an
inventory, taken under the lock), remove only that, and hold the lock until the teardown is
done. A teardown that cannot tell what it created must refuse.

---

## A check that never ran reads exactly like a check that passed

*Nine instances in this project. Six were found on 2026-09-08; the seventh, eighth and ninth
on 2026-09-09. **None was found by reading the code, and none was found by the check itself.**
Six through seven came from re-driving a path for an unrelated reason; eight and nine came
from adversarial reviews told to hunt this class by name. The sections below were written as
the witnesses arrived, so they read four, then six, then seven, then nine; that sequence is
the record and is left as it is.*

**The class.** A verification step that does not execute is indistinguishable, in its
output, from one that executed and found nothing. Zero checks run renders as zero failures
found. Every instance below is the same sentence with different nouns, and in every one the
*detecting* half was present and correct — what was missing was any assurance that it ran.

### The four witnesses

| | the instrument | what did not run | how it read |
|---|---|---|---|
| **1** | `proto/conformance.py` | three of four outcome branches, **0 executions** across a full run | every conformance headline in the record, from a rig whose failure surface was dead. Found only because the owner asked for the check directly (**Q4**) |
| **2** | T-4's §6.1 negative control | the exclusion clause was asserted by calling `aggregate()` on a hand-built list — a **unit test of a helper**, which §6.1 rules out in as many words — while the real path in `run_cell` stayed dead | a passing control, over the very code it existed to prove |
| **3** | §8.2's mutation pass (`--only <typo>`) | the whole pass: an empty selection | `0 of 0`, then *"Every criterion was watched failing against its own mutant"*, **exit 0** |
| **4** | the digit mapping (T-21) | the **39** cases comparing `xpr.num` against the Python evaluator, behind `@needs_db` on a DSN nothing set | `8 passed, 50 skipped` — green. A Unicode bump would fire the staleness guard, you regenerate, the guard goes green, and **not one Unicode digit was ever compared between the two engines** |

### 2026-10-01: four more, one shape: a check that cannot look must say so, never "clean"

- **T-47 (`b846172`):** `ops/name-check.sh` run outside a git work tree printed
  `name-check: clean`, exit 0, with the owner's name planted beside it. Now exit 2, "could not tell".
- **T-59 (`4c8a516`):** run from another checkout, it answered "clean" for a tree it had not been
  asked about. It now refuses when the caller's checkout is not its own, and every "clean" names
  the checkout it scanned.
- **T-55 (`540eb76`):** `ops/checks/neighbour-ports.sh` read a failed `docker ps`, a missing `ss`
  and a failing `ss` as empty halves that compared clean: PASS in six blind cases. And `ss`
  prints its header and exits 0 even with no socket table to read, so a command that SUCCEEDS can
  be blind too. While the demo is up, the check must now see the demo's own :55440 mapping and
  its app on :8787, or exit 2.
- **T-46 (`d13bfb9`):** `parity/check_gims_pipeline.py` with no DSN printed a loud "DID NOT RUN"
  banner and exited 0, which is all a caller reads. Now exit 3 unless `--gims-only`.

**The rule.** Three answers, not two. 0 means looked and clean, 1 means looked and found, and
anything that could not look, or could not see what it knows is there, gets its own exit with
the words "could not tell". A banner is not an exit code.

### The sixth member, and the hardest to catch: a gate that performs being a gate

| | the mechanism | what never ran | how it read |
|---|---|---|---|
| **6** | the `design` gate | **nothing consults it.** `.autodev/data/gates.json` defines it, `gates-policy.json` polices it `human:strict`, and `design@v1`'s `bands.gate` is **`None`** | it **refuses on-behalf clears when tested directly** — so it answers correctly every time you poke it, and holds nothing when you don't |

**Measured 2026-09-08.** T-22 advanced `design → queue` on a validator pass with `design: false`.
The gate had never held anything in its existence: T-2, the precedent everyone cites, was given
the `design` *modifier* on 21 August and the gate was added to `gates.json` on **22 August** — a
day later — so T-2's ticket has no `design` key at all and its mock was approved conversationally.

**The cross-check nobody had run, and it generalises:** `gates-policy.json` defines **eight**
gates. **Six are bound to a loop. `design` and `compliance` are not.** `compliance` is `human`
policy and consulted by nothing; it has simply never been reached. `client-signoff@v1` and
`sec-review@v1` are gateless stages in the same blueprint.

> **Corrected 2026-10-01 (T-24).** `compliance` *is* bound: `compliance-review@v1` names it,
> and the engine loads that loop from the plugin's full set. The cross-check above read only the
> blueprint's loop list, which lacks it. Only `feature-regulated@v1` routes to that loop, and no
> ticket here has that type, so `compliance` is **unreached, not unbound** (a ticket filed as, or
> rerouted to, `feature-regulated` would reach it). It is dormant, and it misleads nobody until
> someone relies on it. **`design` was the only gate that performed.** T-24's release step binds
> it: it publishes `design@v2`, with `bands.gate = "design"` and the policy left at
> `human:strict`, into this shop's git-ignored `.autodev/data/loops/`. To see whether it holds
> today, ask the tracker for a new design ticket's journey, or run
> `.autodev/evidence/T-24/watched-hold.sh --expect-real bound`.
>
> **The binding is forward-only.** Read from `loopFor` alone, a new loop version looked as if it
> would bind every ticket carrying the modifier at once, because no pipeline pins `design`. The
> tracker's own comments say otherwise (a modifier-inserted stage is pinned on the ticket when the
> modifier is applied: `tracker.mjs` around `resolveRoute` and `create`), and a run on a throwaway
> copy confirmed it: a ticket created before the publish walked straight through after it
> (`pins: {"design": "design@v1"}`). So the publish holds tickets created, or given the modifier,
> after it. **And it does not simply survive a plugin update:** if a plugin release ships its own
> `design@v3`, that becomes the latest loop and new tickets are unbound again. After any plugin
> update, run the check above. This is the shape of *The procedure transfers; the proof does not*,
> below: the reading transferred, and the proof had to be run.

**Why this member is worse than the other five.** They were *checks* nothing ran, and a check that
never runs is at least silent. **This is a mechanism that answers convincingly when interrogated
and never fires otherwise.** Asked directly, it refused an on-behalf clear with a correct,
specific message. That refusal is what persuaded two people it was working — and one of them
relayed a clearance command to the owner on the strength of it. He ran the command. Nothing
happened, and nothing could have.

> **A mechanism that refuses you when you test it, and never fires when you don't, is the hardest
> member of this family to catch** — because the thing you would do to check it is the one thing
> it still does correctly.

**So the test for a gate is not "does it refuse me?" It is "what consults it, and when did that
last fire?"** For an AutoDev gate: find the loop whose `bands.gate` names it, and confirm a ticket
has actually been held there. If nothing names it, the policy is decoration.

### A fifth member, and it is a different one

| | the instrument | what did not run | how it read |
|---|---|---|---|
| **5** | `ops/name-check.sh` (T-14's rule) | **nothing** — the check's failure path works perfectly; **no hook, no CI, no suite invoked it** | a sound guard, documented as `ops/name-check.sh && git push`, i.e. someone remembering to type it. The name reached `origin/main` anyway |

**The first four are checks whose failure path never executed. This one's failure path is
fine — the invocation was missing.** Same family, and worth separating, because a reader who
has only met the first four will look for a dead branch and find none.

**It has a precursor worth naming too:** the arrangement it replaced was an inline
`git grep … ; echo … && git add …`, where the grep *fired* and its exit status was never
consumed. So the sequence was: a check that ran and was discarded → replaced by a better
check that nothing called. **Both are the same failure at different distances from the code.**

**The test:** *what would have to break for this check to stop protecting me, and would I
notice?* If the answer is "someone stops typing it", it is not a guard yet — and if the answer is
"nothing calls it at all", see the sixth member above.

**Its first catch was its own author, on the day it was written.** With the guard now invoked by
the suite, the next commit was refused — because `demo/tests/test_owner_name_absent.py` used the
owner's name **literally** as its probe fixture, so the check correctly flagged its own test file.
Two things made that a good outing rather than an embarrassing one: the commit was **chained with
`&&`**, so the refusal actually stopped it (the failure hours earlier was a `;` that let the push
through), and the fix was to **assemble** the probe (`"ev" + "an"`) so the file never contains the
token while the test still drives the real pattern. **A guard whose first catch is the person who
wrote it, minutes after writing it, is a guard that works** — and it is a reminder that the author
is inside the blast radius, not above it.

**Instance 2 is the sharpest and instance 4 is the most instructive.** Number 2 is a control
whose job was proving failure paths fire, and its own failure path could not. Number 4 shows
the class survives having a *correct, running* guard next door: detection worked perfectly,
and detection is not verification. **"The guard fired and I fixed it" is not evidence the fix
was right.**

### What to do about it, since naming a class is not a practice

- **Drive the empty case on purpose.** Ask the instrument for nothing — no matching id, an
  empty selection, a filter excluding everything — and require it to **refuse**. `--only M17`
  exits 2 now.
- **Make "nothing happened" and "everything passed" different outputs.** Different exit
  codes, different sentences. Where a skip is legitimate (no Postgres on this machine), keep
  the skip and print a **disclosure above the summary**, so the count and the caveat cannot
  be separated by a copy-paste — `runtime/tests/conftest.py`, and `run-demo`'s §8.2 line.
- **Prove green before you allow red.** A criterion that was already failing proves nothing
  by failing again. The mutation pass's KILLED / SURVIVED / **INVALID** triple is this, and it
  caught eight bad mutants of mine on its first run.
- **Watch it fail, and keep the exercise.** `.autodev/evidence/T-18/watched-failing.mjs`,
  `.autodev/evidence/T-21/watched-failing.sh`, `.autodev/evidence/T-17/watched-failing.sh` —
  each breaks the thing on purpose and asserts the guard reacts, re-runnably.
- **Put the invocation where it cannot be forgotten, and prefer the one that travels.**
  A `.git/hooks/` hook does not travel with the repo, so a fresh clone is unprotected —
  the case that matters for a public one. With no CI in this repo, the suite is the thing
  that both travels and always runs: `demo/tests/test_owner_name_absent.py` *runs the
  script* rather than reimplementing it, so one implementation is checked and the test also
  fails if the script itself breaks.
- **Give a known failure a name, a reason and a ticket, and give a NEW failure a different
  exit code.** Otherwise the known red masks the new one and the whole check becomes noise —
  `EXPECTED_SURVIVORS` in `demo/tests/mutation_pass.py`.

### The seventh, where the check was not even wrong: declaration vs. consumption

| | the mechanism | what never applied | how it read |
|---|---|---|---|
| **7** | the guided tour's per-skin palette (T-22) | **three CSS custom properties**, on all seven skins, since the first build. `tour.js` `_build()` sets `--tour-dim`, `--tour-ring` and `--tour-radius` as **inline** properties on `.tour-root` — the ancestor of everything that reads them. Custom properties inherit; inline beats any stylesheet | the tokens were **correct at `:root`**, which is where anyone would assert them. The dim, the ring colour and the corner radius painted were the engine's defaults on every skin |

**Measured on `classic` (2026-09-09):** `:root` said `--tour-dim: rgba(0,0,32,.55)`, `--tour-ring:
#000080`, `--tour-radius: 0`. What was painted: `rgba(6,10,20,0.74)`, `#4f6ef7`, `10px`. Nothing
was broken enough to look broken — the navy dim and the square ring were declared, they were
simply never the values on the screen.

**Why this one is different from the other six.** In those, a check did not run. Here the check
would have run, and would have been **right about the thing it inspected**. `:root` really does
declare `--tour-dim: rgba(0,0,32,.55)`. The assertion and the defect were about *different
questions*, and no amount of care in writing the assertion closes that gap:

> **A token is declared in one place and consumed in another, and only the consumption is ever
> the thing you actually care about.** The same shape covers a config value read by nobody, an
> environment variable exported after the process started, a CSS class that loses the cascade,
> a feature flag defaulted in two files. Asserting the *declaration* is asserting the input to a
> mechanism you have not checked.

**What settles it, and what does not.** No static read of the stylesheet could have found this;
the answer lives in the cascade, and the cascade only exists at runtime. `getComputedStyle` on
the **painted element** found it in one call. So:

- **Assert at the point of consumption when the consumption is what you mean.** For CSS that is
  the computed style of the element, not the custom property at `:root`.
- **When runtime is the only instrument, say so out loud rather than substituting a static check
  that resembles one.** `demo/tests/test_tour.py` therefore guards the *seam* — that this repo
  never declares a token name the vendored engine sets inline, read out of the engine itself so
  a version bump updates the fact — and `demo/EVIDENCE.md` records the browser run, which is
  what actually proves the pixels. The file says in its own docstring that the appearance is not
  asserted anywhere and cannot be.
- **A third-party library can shadow your configuration without forking anything.** Before
  theming a vendored component through variables, grep it for `setProperty` and for the names it
  writes. Two minutes, and it was the whole defect.

### The eighth and ninth, found by a review of the ticket that recorded the seventh

Two more arrived within hours, in the same change, from adversarial reviews run **against**
the work rather than by the person who did it. Both are worth their own rows because neither
resembles the others.

| | the mechanism | what never applied | how it read |
|---|---|---|---|
| **8** | `data-tour="panes"` on `demo/frontend/panes.jsx` | the anchor sat on **one of the component's two return paths**. The `if (!answer)` empty state renders the same `<section aria-label="The same pick, two answers">` without it | the guard I had written did `re.findall(r'data-tour="…"', file)` and reported the anchor **present** — which it was, on one branch. Before the first pick resolves, and **permanently** if the API call fails, the tour's two most important steps would have spotlighted nothing and blacked out the screen |
| **9** | `narrator: { image, name: "GIMS" }` | `tour.js` reads `narrator.image` and reads `name` **nowhere**. There was no byline element in the DOM at all | I then recorded in append-only evidence that a browser run had **confirmed** a bubble "bylined GIMS" |

**Eight is the same shape as seven at one remove.** Seven was *a token declared where nothing
consumes it*. Eight is *a check that inspects the file rather than the render path*. Both are
the gap between **declaration and consumption**, and in both my assertion was accurate about
the thing it looked at. The fix generalises: an element carrying an anchor establishes an
**identity** (its `aria-label`, else its `className`), and every element in the file with that
identity must carry the same anchor. Multi-branch components are the normal shape in React;
"the file contains the string" was never the property I meant.

**Nine is the one to be uncomfortable about.** A library accepted a config key and ignored it,
which is indistinguishable from a key that worked — that is ordinary. What is not ordinary is
that I wrote *"the run confirmed … byline GIMS"* into a **frozen, append-only evidence file**,
in a table whose other rows were real measurements. **An unobservable claim placed among
observations borrows their credibility.** The tests defer to that file explicitly ("only a
browser can say that, and one did"), so the weakest link was the one thing nothing checks.

- **Say what you measured, not what you configured.** If the reading came from
  `getComputedStyle` or `getBoundingClientRect`, it is an observation. If it came from knowing
  what you passed in, it is not — and it does not belong in a table of observations.
- **Diff the config you send against the config the library reads.** Two greps. It is now
  `test_the_config_steps_js_passes_uses_only_options_the_engine_reads`, and the keys this repo
  consumes itself are listed by name, so "the engine ignores it" and "we render it ourselves"
  cannot be confused again.

**The habit that found all three of seven, eight and nine: reviews run by someone who did not
do the work, told to hunt for this specific class by name.** Seven came from a screenshot,
eight and nine from two parallel adversarial reviews of the commit that recorded seven. Every
one was invisible to the person who wrote the code, and every one was found within an hour of
being looked for on purpose. **Assume the work is not clean until a review says so** is not a
posture; on this ticket it was worth three defects, one of them in the evidence record itself.

## The procedure transfers; the proof does not

*2026-09-08 · ruled while approving T-22's `.jsx` edit · the precedent is T-16*

**T-16 rebuilt digest-covered `.jsx` bundles and could say the rebuild was safe *because the
bundles came back byte-identical*.** That worked because T-14 had only reworded two comments:
any bundle change at all would have meant something unintended happened. It is a genuinely
strong proof — for that change.

**It is unavailable to the next change, and its absence proves nothing.** T-22 adds
`data-tour` attributes to about eight controls. That *legitimately* changes the bundles. A
session reaching for "byte-identical" out of habit gets a failure it cannot interpret: the
check fails, and it fails for a good reason, and nothing distinguishes that from the bad one.

**So: reuse the steps, re-derive the evidence.** The procedure carries over unchanged — edit
the `.jsx`, run `./run-demo build-ui`, re-baseline `manifest.json`. What has to be rebuilt for
each change is the *argument that the rebuild did only what was intended*:

| change | the proof that fits it |
|---|---|
| comments reworded (T-16) | bundles **byte-identical** — any diff is a defect |
| attributes added (T-22) | **diff the bundles** and show the change set contains only the added attributes |

**The general rule: a borrowed procedure comes with a borrowed proof, and the proof is the half
that expires.** When you inherit a runbook, ask what its evidence step was *establishing*, and
whether your change still makes that the right question. Ask it before running the check, not
after it goes red.

## A citation to "the plan" is not a citation to the spec

*2026-09-08 · found while starting plan §8.2's mutation pass · `.autodev/notes/plan-8-2-mutation-pass-citation.md`*

**This shop writes two documents per ticket and both have numbered sections.** For T-2 they
are `.autodev/specs/T-2.md` (the **spec**) and `.autodev/specs/T-2-plan.md` (the **plan**),
1,486 lines, a different document. Both have a `## 8`. The spec's §8.2 is *The table*; the
plan's §8.2 is *The mutation pass*. **Checking one is not checking the other.**

Six live files cite "plan §8.2" for a sixteen-mutant pass. A session read the **spec's** §8.2,
found a `CREATE TABLE`, checked several more places, and concluded the citation was broken and
the sixteen mutants had never been specified. Every individual check it ran was accurate. It
simply never opened the document the citation named. The proposed remedy — author sixteen
substitute mutants and "correct" six correct citations — would have replaced a real
specification with an invented one and then satisfied it.

**Before concluding a citation is broken, resolve the noun.** `spec`, `plan`, `locate` and
`handoff` are four different artifacts here, they live side by side in `.autodev/specs/` and
`.autodev/handoffs/`, and a section number means nothing without the document.

### Two search habits this exposed, both general

1. **Never conclude absence from a truncated search.** The grep that "proved" the mutants were
   undefined *did* glob the plan; `| head -10` discarded the hit. A `head` is fine for looking
   around and fatal for a negative conclusion — for absence use `-c`, or no limit, or name the
   file directly.
2. **In this repo, missing from `git log` is not missing from disk.** `adf23bf` shows as
   *deleting* `.autodev/**`; it untracked that directory from the public repo and left every
   file in the working tree. Around thirty `.autodev/` paths are cited by live files and all of
   them still exist. Reasoning from git history alone yields a confident story about a destroyed
   document — and, next, a fabricated reconstruction of it.

**The habit that saved it:** refusing to write a substitute for a specification that could not
be found, and saying so, rather than producing something shaped like the missing thing. A review
cannot catch a fabricated citation when it has been handed the same wrong document.
