# AutoDev plugin — three defects, one root cause: a filesystem path containing a space

Drafted 2026-08-21 against **autodev 0.53.0**, read at
`~/.claude/plugins/cache/autodev-marketplace/autodev/0.53.0/`.
Reporting machine: Linux 6.8.0 (Ubuntu), Node v22.22.2, repo at
`/home/corgea/Desktop/Coding Projects/autoSQL` — the parent directory is **`Coding Projects`**,
with a space in it. That single space is what all three defects turn on.

**Every line number, quoted line and output block below is real** — read from the shipped files or
produced by running them on this machine. Nothing here is from memory.

> **Read this first if you are looking at the same files on your own machine.** Two of these files
> are **patched locally here** (`scripts/sidecar-service.mjs`, `scripts/lib/sidecar-heal.mjs`) so
> that this repo can be monitored at all. The patch is a one-line change in each file, so the
> **line numbers are identical to yours**. Everything described below as "what happens" is the
> **shipped, unpatched** behaviour, recovered verbatim from `git diff` in the marketplace checkout
> at `~/.claude/plugins/marketplaces/autodev-marketplace` (which is a git clone, still holding the
> pristine blobs). Both quoted originals are shown.

Ready to paste **as one issue** (the whole file) or **as three** (each `## Defect N` section is
self-contained).

---

## Where this report should go

I looked for a published bug-report route in the plugin. Verbatim, this is everything the plugin
says about its own origin:

| Source | What it contains |
|---|---|
| `.claude-plugin/plugin.json` | `"author": { "name": "Ryan Shuken" }` — **no** `repository`, `homepage`, or `bugs` field |
| `package.json` | `"name": "autodev-plugin"`, `"private": true` — **no** `repository`, `homepage`, or `bugs` field |
| `.claude-plugin/marketplace.json` | `"owner": { "name": "Ryan Shuken" }`, `"source": "."` — **no** URL of any kind |
| `README.md` | No URL, no contact. Points only at internal files: *"the factory repo's kb/wiki/skill-design-decisions.md"* and *"process spec: factory-system/"* |
| `NOTICE` | The one URL in the whole package is `https://github.com/eschnei/autodev` — and that is the **different, upstream project this plugin adapts** (Eric Schneider, Apache-2.0), not this plugin's home |
| `docs/`, `ops/` | `PIPELINES.md`, `linear-setup.md`, `shortcut-setup.md`, `verify-access.sh` — no contact route |

**So: there is no published route.** Nothing in the plugin's own metadata tells a user where to
report a bug.

There is, however, a **private** one, found outside the package metadata — in the marketplace
checkout's git config:

```
$ git -C ~/.claude/plugins/marketplaces/autodev-marketplace remote -v
origin	https://github.com/RShuken/autodev-plugin.git (fetch)
origin	https://github.com/RShuken/autodev-plugin.git (push)

$ gh repo view RShuken/autodev-plugin --json name,visibility,hasIssuesEnabled,url
{"hasIssuesEnabled":true,"name":"autodev-plugin","url":"https://github.com/RShuken/autodev-plugin","visibility":"PRIVATE"}
```

That repo is **private**, and its issue tracker **is enabled**. Your GitHub account (`BMA-Corgea`,
per `gh auth status`) can read it — the `gh repo view` above succeeded — so you can almost
certainly open issues there.

**Recommendation:** file at `https://github.com/RShuken/autodev-plugin/issues`. The last commit in
that checkout is authored `Ryan Shuken <ryanshuken@gmail.com>` (from git commit metadata — use your
judgement about whether email is the right channel; the issue tracker is the better one, since it
is the project's own).

**A fourth thing worth saying in the issue:** the plugin should publish that route. Adding
`"repository"` and `"bugs"` fields to `package.json`, or a "Reporting bugs" line in `README.md`,
would mean the next person does not have to read a git remote to find you.

---

## Defect 1 — the Linux service file writes `--roots` unquoted, so a path with a space silently watches the wrong directory

**Title (91 chars):** `Linux sidecar: unquoted --roots in the systemd unit breaks any repo path containing a space`

### What happens

The monitoring sidecar (`watch.mjs` — the read-only watcher that discovers enrolled repos and
reports on them) is installed on Linux as a systemd user service. The unit file's `ExecStart=` line
is built by string interpolation with **no quoting**. systemd splits `ExecStart` on unquoted
whitespace, exactly like a shell does. A root directory containing a space is therefore split into
two arguments: the path is truncated at the space, and the remainder becomes a stray argument that
the CLI parser silently discards.

The watcher then starts successfully, `systemctl` reports it `active`, and it scans a directory
**that does not exist**. It finds zero repos and reports on nothing, forever.

### Where — exact file and line

**`scripts/sidecar-service.mjs`, line 66**, inside `unit()` (lines 61–73). Shipped:

```js
ExecStart=${node} ${script} --roots ${roots} --interval ${interval} --upload ${upload}
```

`unit()` is called from the Linux branch of `install()` at **line 95**.

The failure is compounded by a **second** site that must be fixed at the same time —
**`scripts/lib/sidecar-heal.mjs`, line 32**, inside `parseServiceArgs()` (lines 25–35), the function
that reads an installed unit back. Shipped:

```js
  const parts = exec.split(/\s+/);
```

That splits on whitespace too, so the session-start self-heal reads back the **same truncated root**
that systemd saw — and cannot tell that anything is wrong with the file it wrote.

Three more lines matter for understanding why nobody notices:

- **`scripts/lib/parse-args.mjs`, lines 31–33** — the leftover token (`Projects`) is not a flag, so
  it becomes a positional. `watch.mjs`'s CLI (**`scripts/watch.mjs`, line 205**) reads only
  `flags.roots`. The positional is dropped without a word.
- **`scripts/watch.mjs`, line 45** — `discoverRepos()`'s walk does
  `try { entries = readdirSync(dir, ...); } catch { return; }`. A root that does not exist is an
  `ENOENT` that is caught and discarded. No log, no warning, no error.
- **macOS is unaffected**, and this is worth stating in the issue because it explains why it was
  never seen: `plist()` (**lines 40–48**) builds an argument *array* and emits each element as its
  own `<string>`, so spaces survive. This is a Linux-only defect.

### How to reproduce

On any Linux machine, install the sidecar with a root that contains a space:

```bash
mkdir -p "/tmp/Coding Projects/demo/.autodev/tickets"
node <plugin>/scripts/sidecar-service.mjs install --roots "/tmp/Coding Projects"
cat ~/.config/systemd/user/autodev-watch.service        # ExecStart is unquoted
tr '\0' '\n' < /proc/$(systemctl --user show -p MainPID --value autodev-watch.service)/cmdline
```

The `cmdline` readout shows `--roots`, `/tmp/Coding`, `Projects` as three separate arguments.

### Verified here

Run on this machine, read-only — nothing was installed or started; `discoverRepos()` only reads
directories:

```
ExecStart written by the shipped unit():
  ExecStart=/home/corgea/.nvm/versions/node/v22.22.2/bin/node /home/.../scripts/watch.mjs --roots /home/corgea/Desktop/Coding Projects --interval 60 --upload 15

argv systemd hands to watch.mjs: ["--roots","/home/corgea/Desktop/Coding","Projects","--interval","60","--upload","15"]
  flags.roots  = "/home/corgea/Desktop/Coding"
  positionals  = ["Projects"]   <- silently discarded

what the watcher then scans:
  discoverRepos(["/home/corgea/Desktop/Coding"])          -> []
  discoverRepos(["/home/corgea/Desktop/Coding Projects"]) -> 3 enrolled repos found

the shipped parseServiceArgs() reading that same unit back (the self-heal's view):
  {"script":".../watch.mjs","roots":"/home/corgea/Desktop/Coding"}
```

And with the local quoting patch applied, the same machine's live watcher is healthy:

```
$ cat /home/corgea/autodev-reports/heartbeat.json
{ "at": "2026-08-21T18:41:08.493Z", "host": "corgea-MS-7C79",
  "roots": [ "/home/corgea/Desktop/Coding Projects" ],
  "reposDiscovered": 3, "reposWatched": 3, "optedOut": [] }
```

Zero repos before the patch; three after. The only difference is four quote characters.

### Why it matters — the failure reports success

This is the part to emphasise. It is not merely silent: **it actively claims to have fixed itself,
once per session, forever.**

Because `parseServiceArgs()` returns the truncated root, `covers()`
(**`sidecar-heal.mjs`, lines 37–38**) correctly concludes the roots do not cover this repo —
`/home/corgea/Desktop/Coding Projects/autoSQL/` does not start with `/home/corgea/Desktop/Coding/`.
So `healSidecar()` takes the `rootsMiss` branch (**lines 72–81**), reinstalls with the union of
roots — **writing the identical unquoted, identically broken unit file** — and returns:

```
monitoring: sidecar repaired — its roots (...) did not cover this repo; now watching ...
```

The session-start hook prints that line (**`hooks/session-start.mjs`, lines 310–318**). Every
session. It says *repaired*. Nothing was repaired. A user reading their session brief is told the
monitoring problem was found and fixed, while telemetry stays at zero.

`/autodev:doctor` does catch it, at **`scripts/doctor.mjs`, line 487** —
`sidecar roots (...) do NOT cover this repo — it is invisible to monitoring` — but its suggested
remedy is to re-run the same `install` command that produces the broken file.

This is exactly the failure mode the sidecar's own header comment says it exists to prevent
(`sidecar-heal.mjs` lines 1–19: *"Dead was indistinguishable from nothing happening"*, Gregory's
fresh install that *"sent nothing ever"*). Same outcome, different cause.

### The smallest fix

Two one-line changes. **Both are required** — fixing only the writer leaves the self-heal
mis-reading the corrected file and reinstalling over it.

`scripts/sidecar-service.mjs` line 66:

```diff
-ExecStart=${node} ${script} --roots ${roots} --interval ${interval} --upload ${upload}
+ExecStart="${node}" "${script}" --roots "${roots}" --interval ${interval} --upload ${upload}
```

`scripts/lib/sidecar-heal.mjs` line 32:

```diff
-  const parts = exec.split(/\s+/);
+  const parts = (exec.match(/"[^"]*"|\S+/g) ?? []).map((t) => t.replace(/^"|"$/g, ""));
```

(systemd's `ExecStart` supports double-quoted arguments and strips the quotes, so the running
process sees one argument. Verified on this machine — the `/proc/<pid>/cmdline` readout above shows
`--roots` followed by the single argument `/home/corgea/Desktop/Coding Projects`.)

**One more thing, in the same area, found while applying the fix:** `install()`'s Linux branch
(**line 97**) uses `systemctl --user enable --now autodev-watch.service`. `--now` runs `start`, and
`start` on an already-active unit is a no-op — so after a `daemon-reload` the **unit file** is
updated but the **running process keeps its old arguments**. Every re-install onto a live watcher
therefore appears to succeed while changing nothing until the next reboot. Adding a
`systemctl --user restart autodev-watch.service` after the reload makes `install()` genuinely
idempotent. (I hit this directly: after patching, the fix did not take effect until an explicit
`restart`.)

**Out of scope but worth a line in the issue:** `roots` is comma-joined
(`sidecar-heal.mjs` line 74, `watch.mjs` line 205), so quoting fixes spaces but a path containing a
**comma** would still split. Rarer, same class of bug.

---

## Defect 2 — the time tracker derives its transcript directory by replacing only `/`, so a path with a space finds nothing and under-reports hours

**Title (91 chars):** `Time tracker: transcript dir replaces only "/", so any path with a space loses all activity`

### What happens

Time tracking measures **work blocks** from activity marks. It draws those marks from two places:
ledger events in the repo, and **every user turn in the Claude Code session transcripts**. The
transcript half is the whole point of the design — the file's own header (lines 12–17) explains that
ledger events alone are useless for duration and cites a *63,000× gap* on a real ticket.

To find the transcripts, it reconstructs Claude Code's per-project directory name by replacing `/`
with `-`. Claude Code replaces **every non-alphanumeric character**, spaces included. So on a path
with a space, the derived directory name keeps the space, does not exist, and
`if (existsSync(dir))` is simply false. Zero transcript marks. No error, no warning — the report
still prints, with a smaller number on it.

Concretely, on this machine:

| | |
|---|---|
| Claude Code actually writes | `~/.claude/projects/-home-corgea-Desktop-Coding-Projects-autoSQL` |
| The plugin looks in | `~/.claude/projects/-home-corgea-Desktop-Coding Projects-autoSQL` |

### Where — exact file and line

**`scripts/time-track.mjs`, line 72:**

```js
const transcriptDir = (root) => join(homedir(), ".claude", "projects", resolve(root).replace(/\//g, "-"));
```

Consumed at **line 83–84** in `activity()`:

```js
  const dir = transcriptDir(root);
  if (existsSync(dir)) {
```

**The identical bug exists a second time, in a second file** — same fix needed:

**`scripts/session-scan.mjs`, line 29** (its own comment on line 27 states the wrong rule:
*"Claude Code stores a repo's sessions under ~/.claude/projects/<cwd with / → ->"*):

```js
  return join(home, ".claude", "projects", resolve(root).replace(/\//g, "-"));
```

Its caller `findTranscripts()` (**lines 32–37**, guard on line 34) has the same silent `if (!existsSync(dir)) return [];`.

Those are the only two sites — I grepped the whole `scripts/` and `hooks/` tree for
`".claude", "projects"` and found exactly these two.

### How to reproduce

```bash
mkdir -p "/tmp/Coding Projects/demo"
# open a Claude Code session in that directory, take a few turns, then:
ls ~/.claude/projects/ | grep -i coding
#   -tmp-Coding-Projects-demo          <- what Claude Code writes (space -> "-")
node -e 'const{resolve}=require("path");console.log(resolve("/tmp/Coding Projects/demo").replace(/\//g,"-"))'
#   -tmp-Coding Projects-demo          <- what the plugin looks for; does not exist
node <plugin>/scripts/time-track.mjs report --root "/tmp/Coding Projects/demo"
```

The report comes back built from ledger events only.

### Verified here — the size of the undercount

I reproduced `activity()` and `blocks()` line-for-line (read-only; `.autodev/events.jsonl` was read,
never written) and ran them twice: once with the transcripts found, once without — which is exactly
what a machine with a space in its path gets.

```
                                 activity marks     blocks   raw minutes   billed (day-rounded 15)
shipped defaults (idleMin 15)
  transcript dir NOT found        42 (0 human)         6      44  (0.73 h)      60 min (1.00 h)
  transcript dir found           400 (358 human)      13     180  (3.00 h)     180 min (3.00 h)

this repo's config (idleMin 90)
  transcript dir NOT found        42 (0 human)         5     297  (4.95 h)     300 min (5.00 h)
  transcript dir found           400 (358 human)       3     669 (11.15 h)     675 min (11.25 h)
```

**358 of 400 activity marks — 89.5% of the signal — are lost.** On this repo that is a **4.1×**
undercount of raw tracked minutes at the shipped `idleMin: 15`, and **2.3×** at the `idleMin: 90`
this repo uses. (I could not reproduce a full order of magnitude here; the honest number is
"between roughly 2× and 4× on this repo, and it scales with how much of the work is human turns
between ledger writes." A repo with few ledger events and long human sessions would lose more.)

Note for anyone re-running this on **this** machine: the broken path currently resolves, because a
symlink was created here on 2026-08-21 as a stopgap —

```
/home/corgea/.claude/projects/-home-corgea-Desktop-Coding Projects-autoSQL
  -> /home/corgea/.claude/projects/-home-corgea-Desktop-Coding-Projects-autoSQL
```

That symlink is a local workaround, not upstream behaviour. The "NOT found" rows above were produced
by skipping the transcript read entirely, which is what a clean machine does.

### Why it matters

Time tracking exists to produce **numbers you bill from** — `commands/time.md`, `--push` to a Google
Sheet, an hourly `rate` field. A wrong number that looks right is worse than no number. Nothing in
the output says "I found no transcripts"; the report is fully formed and simply short. The file's
own header (lines 19–24) records a previous incident where rounding inflated a real invoice by four
hours across 35 rows — the same class of harm, in the other direction.

Anyone whose code lives under `~/My Documents`, `~/Coding Projects`, `~/Google Drive`, or any macOS
path with a space is silently under-billing.

### The smallest fix

Match Claude Code's own scheme — replace every non-alphanumeric character, not just the slash. One
line in each of the two files:

```diff
-  resolve(root).replace(/\//g, "-")
+  resolve(root).replace(/[^a-zA-Z0-9]/g, "-")
```

(Verified against the real directory names on this machine: `/` and space both become `-`, e.g.
`/home/corgea/Desktop/Coding Projects/autoSQL/spikes/T-1` →
`-home-corgea-Desktop-Coding-Projects-autoSQL-spikes-T-1`.)

**And make the miss loud.** The one-line fix repairs today's paths; the second half of the bug is
that a wrong guess is indistinguishable from a quiet week. In `activity()`, when
`existsSync(transcriptDir(root))` is false, print or record one line —
`no session transcripts found at <dir> — hours will count ledger events only`. Then the next
mismatch (a Claude Code change to the naming scheme, a moved home directory) is a visible warning
instead of a smaller invoice.

---

## Defect 3 — Windows has no install path at all, and its status check is blind, so every Windows session reports a false "sidecar down"

**Title (88 chars):** `Windows: sidecar cannot be installed as a service, and statusOf() always reports it down`

### What happens

`install()` has branches for `darwin` and `linux` only. Windows falls through to a final `return`
that reports failure with a manual command. That part is deliberate — there is a test for it. The
**undocumented** half is `statusOf()`: it has the same two branches and no Windows one, so on
Windows it **always** returns `installed: false, running: false`, regardless of reality.

Combined with the session-start self-heal, that means a Windows user who follows the instructions
and starts the watcher by hand gets told, **at the top of every single session**, that monitoring is
down and repair failed. There is no state a Windows user can reach in which the plugin says
monitoring is working.

### Where — exact file and line

**`scripts/sidecar-service.mjs`, line 100** — the fall-through in `install()` (lines 80–101):

```js
  return { ok: false, os, error: `no service manager for ${os} — start it by hand: node ${script} --roots ${roots}` };
```

**`scripts/sidecar-service.mjs`, lines 125–132** — `statusOf()`, the blind spot:

```js
export function statusOf({ home = homedir(), os = platform(), exec = run } = {}) {
  const p = os === "darwin" ? plistPath(home) : unitPath(home);
  const installed = existsSync(p);
  let running = false;
  if (os === "darwin") running = (exec("launchctl", ["list"]).out ?? "").includes(LABEL);
  else if (os === "linux") running = (exec("systemctl", ["--user", "is-active", "autodev-watch.service"]).out ?? "").trim() === "active";
  return { installed, running, path: installed ? p : null, os };
}
```

Line 126 is the tell: on Windows it checks for a **systemd unit path**,
`~/.config/systemd/user/autodev-watch.service`, which will never exist there. Line 128 sets
`running = false` and neither branch on 129–130 can change it.

The consequence is emitted at **`scripts/lib/sidecar-heal.mjs`, lines 57–61** (`!st.installed ||
!st.running` → try to install → fails → `install-failed`), printed by
**`hooks/session-start.mjs`, lines 310–318**. `/autodev:doctor` is equally blind at
**`scripts/doctor.mjs`, line 474** (`monitoring sidecar not installed — telemetry from this machine
is OFF`).

There is **no** `win32` handling anywhere in the plugin — I grepped `scripts/`, `hooks/` and `docs/`
for `win32|windows|Windows` and the only hit in the entire tree is the test named below.

### How to reproduce

On Windows, in an enrolled repo: run `node <plugin>/scripts/sidecar-service.mjs install`, then start
`watch.mjs` by hand exactly as the error message instructs, confirm with Task Manager that node is
running and that `~/autodev-reports/heartbeat.json` is being refreshed — then start a new Claude
Code session and read the session brief.

### Verified here

Simulated by injecting `os: "win32"` into the shipped functions (read-only; the service-manager
call was stubbed so nothing real was touched):

```
install({os:'win32'})  -> {"ok":false,"os":"win32","error":"no service manager for win32 — start it by hand: node .../watch.mjs --roots ..."}
statusOf({os:'win32'}) -> {"installed":false,"running":false,"path":null,"os":"win32"}
uninstall({os:'win32'})-> {"ok":true,"removed":false,"note":"nothing to remove on win32"}

session-start line     -> {"action":"install-failed",
                           "line":"monitoring: sidecar down and reinstall FAILED (no service manager for win32 — start it by hand: node .../watch.mjs --roots <parent>) — run: sidecar-service.mjs install --roots <parent>"}
```

`statusOf` returns `running: false` **without consulting anything** — no process check, no
heartbeat check. It cannot return anything else on Windows.

*(Caveat on that last block: it was produced by running the Windows code path on Linux, so the
actual path text inside the message is a POSIX artifact of the simulation and not what a real
Windows machine would print. The `ok`/`installed`/`running`/`action` values are the code's own and
are exact.)*

### Why it matters

Two distinct harms, and the second is the one that erodes trust:

1. **Windows cannot have always-on monitoring.** The whole reason `sidecar-service.mjs` exists is
   stated in its header (lines 3–9): *"monitoring is on by default" was only true of the sidecar's
   BEHAVIOUR — the sidecar itself had to be started by hand, every time... that is the third time a
   capability existed, was documented, and did not happen because it depended on someone
   remembering.* On Windows, that is still exactly the situation. Windows users are back in the
   pre-fix world, and the plugin does not say so.
2. **The alarm cries wolf, every session.** A correctly-configured Windows machine with a running
   watcher prints `sidecar down and reinstall FAILED` at the top of every session brief. Once a user
   learns that line is always wrong, they stop reading it — and then the day it is *right*, on any
   platform, they will not notice. A warning that is unconditionally true on a platform is worse
   than no warning.

The install-side fall-through **is** covered by a test —
`tests/contracts/monitoring/sidecar.test.mjs`, lines 67–73, *"an unsupported OS reports how to run
it by hand instead of failing silently"* — so the honest framing for the issue is: the manual
message was a deliberate choice, but `statusOf()` was never given the matching case, and nothing
tests it.

### The smallest fix

**Minimum, ~6 lines, stops the false alarm:** make "unsupported" a distinct state instead of
"broken", and have the self-heal respect it.

`scripts/sidecar-service.mjs`, `statusOf()`:

```diff
 export function statusOf({ home = homedir(), os = platform(), exec = run } = {}) {
+  if (os !== "darwin" && os !== "linux") return { installed: false, running: false, unsupported: true, path: null, os };
   const p = os === "darwin" ? plistPath(home) : unitPath(home);
```

`scripts/lib/sidecar-heal.mjs`, in `healSidecar()` right after `const st = statusOf({ home });`
(line 54):

```diff
+    if (st.unsupported) return { action: "skip-unsupported",
+      line: `monitoring: no service manager on ${st.os} — start the watcher by hand (see docs) or it will not run` };
```

That alone turns "an alarm that is always wrong" into "one honest statement of the platform's
limits". `doctor.mjs`'s `checkSidecar` (line 474) should read the same flag and `pass`/`note` rather
than `warn`.

**Better, and the real fix:** give Windows an install branch. Windows Task Scheduler does what
launchd and systemd do here — `Register-ScheduledTask` with an `AtLogOn` trigger, or the
`schtasks /create /sc onlogon` equivalent, plus a restart-on-failure setting to match
`KeepAlive`/`Restart=always`. `statusOf()` then queries `Get-ScheduledTaskInfo` for the same
`installed`/`running` pair.

I have a working, machine-checked version of exactly that, written for this repo before we knew it
was an upstream gap: **`ops/autodev-watch-windows.ps1`** in the autoSQL repo (install / status /
logs / uninstall verbs, idempotent, argument quoting verified in both PowerShell argument-passing
modes, and the real `watch.mjs` run through the generated launcher — it found 3 repos).
`Register-ScheduledTask` itself has **not** been executed, because this is a Linux machine. Offer it
upstream as a starting point, with that caveat stated plainly.

---

## Why these three belong together

They are one root cause wearing three coats: **a filesystem path is not a token**. Defect 1 lets a
shell-like parser split one, defect 2 lets a string-replace mangle one, and defect 3 is the same
class of assumption at the platform level — that every machine has a POSIX service manager.

They also share a failure *style*, and it is the style worth naming in the issue: **all three fail
without saying so.** Defect 1 prints "repaired" while watching nothing. Defect 2 prints a
well-formed timesheet with the hours missing. Defect 3 prints an alarm so reliably that it stops
meaning anything. This is a codebase whose own comments show real care about exactly that
(`sidecar-heal.mjs` lines 1–19; `time-track.mjs` lines 12–24; the "HEARTBEAT ALWAYS" comment at
`watch.mjs` lines 160–162 — *"'installed but mis-rooted' (reposDiscovered:0) and 'idle' are
DISTINGUISHABLE from 'dead'"*). Those instincts are right; these three paths just were not reached.

A cheap regression net for all three: one test that installs, reads back and status-checks with a
root of `/tmp/Coding Projects/x`, and one that asserts `transcriptDir()` matches the name Claude
Code actually writes. Neither needs a real service manager — `install`, `statusOf` and `exec` are
already injectable throughout.

---

## Appendix — how each claim here was checked

| Claim | How |
|---|---|
| Shipped (unpatched) text of the two patched lines | `git diff` in `~/.claude/plugins/marketplaces/autodev-marketplace` (a git clone; the pristine blobs are still there) |
| Argument splitting, discarded positional, empty repo scan | Ran the shipped `parseArgs()` and `discoverRepos()` against the split argv; read-only, nothing installed or started |
| Live watcher's real arguments | `tr '\0' '\n' < /proc/<MainPID>/cmdline` for `autodev-watch.service` |
| 3 repos discovered after the fix | `/home/corgea/autodev-reports/heartbeat.json`, written by the running watcher |
| Transcript directory names | `ls ~/.claude/projects/` — both the real name and the symlinked stopgap |
| Hours undercount | Line-for-line reproduction of `activity()` + `blocks()` + day-rounding, run twice; `.autodev/events.jsonl` read, never written |
| Windows behaviour | `os: "win32"` injected into the shipped `install`/`statusOf`/`uninstall`/`healSidecar`, with the service-manager `exec` stubbed |
| No Windows support anywhere | `grep -rn "win32\|windows\|Windows"` over `scripts/`, `hooks/`, `docs/` — one hit, the test at `tests/contracts/monitoring/sidecar.test.mjs:67` |
| No published report route | Read `plugin.json`, `package.json`, `marketplace.json`, `README.md`, `NOTICE`, `install.sh`, `docs/`, `ops/` in full |
| The private route | `git remote -v` in the marketplace checkout; `gh repo view`; `gh auth status` |
