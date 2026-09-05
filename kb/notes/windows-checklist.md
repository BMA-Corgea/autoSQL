# Windows checklist

**Nothing here is urgent, and nothing breaks if you never do it.** Both machines work
today. This is quality-of-life. Do it in one sitting when you're next on Windows —
about ten minutes — or don't.

Two jobs:

1. **Make the background monitor start itself when you log in.** Right now on Windows it
   has to be hand-started every session, and it dies when you log out. Mac and Linux get
   this automatically from the plugin; Windows has no built-in path, so there's a script.
2. **Make that machine file its reports as "the owner" instead of "owner".** It picked up your
   Windows account name on its first run. The Linux box was already corrected.

They're independent. Doing one without the other is fine.

---

## Before you start

The script isn't on the Windows box yet — it has never been committed. Step 1 checks for
it. If the check fails, stop: it needs pushing from the Linux side first.

---

## Job 1 — start the monitor at login

### Step 1. Get the script onto the machine

```powershell
cd <wherever autoSQL lives>
git pull
Test-Path .\ops\autodev-watch-windows.ps1
```

**Verify:** the last line prints `True`.

If it prints `False`, stop here — the script wasn't pushed. Nothing else in Job 1 will
work. (Job 2 is unaffected; skip ahead to it.)

### Step 2. The one line you must edit

The script needs to know **the folder that contains your repos** — the parent folder, not
the autoSQL folder itself. Standing in the autoSQL folder, this prints it:

```powershell
(Get-Item .).Parent.FullName
```

Copy that output. Then open the script:

```powershell
notepad .\ops\autodev-watch-windows.ps1
```

Near the top (lines 36-38) you'll find:

```powershell
$RepoParents = @(
    'C:\Users\<you>\FILL-THIS-IN'
)
```

Replace the placeholder with what you copied. **Keep the single quotes. No trailing
backslash.** On the Linux box that same line reads:

```powershell
    '/home/corgea/Desktop/Coding Projects'
```

so yours ends up looking like:

```powershell
    'C:\Users\<you>\Desktop\Coding Projects'
```

Save and close. That is the only edit. Everything below the marked block is done.

Two things not to do: don't point it at the autoSQL folder itself (it looks *inside* the
folder you give it), and don't point it at `C:\Users\<you>` (it would sweep your whole
profile every 60 seconds).

**Verify:**

```powershell
Select-String -Path .\ops\autodev-watch-windows.ps1 -Pattern '\$RepoParents' -Context 0,2
```

That prints your line back at you. If you skip this, the script refuses to install and
tells you why — the placeholder is a hard stop, not a silent default.

### Step 3. Run it

```powershell
.\ops\autodev-watch-windows.ps1
```

If PowerShell refuses with *"running scripts is disabled on this system"*:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\autodev-watch-windows.ps1
```

**Verify:** near the end it prints a line like

```
Heartbeat: 4s ago — 1 repo(s) watched, roots C:\Users\<you>\Desktop\Coding Projects
```

The number of repos must not be `0`. `0 repo(s)` means the folder from step 2 is wrong —
fix the line and run the script again. Re-running is always safe; it replaces the old
registration rather than stacking a second copy.

That heartbeat number is the thing to trust, here and later. It's the age of a file the
monitor rewrites on every sweep. A process that's "running" but hasn't rewritten it in
five minutes is a broken monitor.

### Step 4. Prove it survives a logout

Log out and back in (or reboot), then:

```powershell
cd <the autoSQL folder>
.\ops\autodev-watch-windows.ps1 status
```

**Verify:** `State : Running`, a `Process : node.exe pid ...` line, and a heartbeat under
about 180 seconds old.

If the heartbeat is stale or missing:

```powershell
.\ops\autodev-watch-windows.ps1 logs
```

**To undo, ever:** `.\ops\autodev-watch-windows.ps1 uninstall`

---

## Job 2 — report as "the owner"

The file is `C:\Users\<you>\autodev-reports\install.json`. Replacing it is the whole job.

### Step 5. Overwrite the identity file

Paste this whole block into PowerShell in one go:

```powershell
$json = @'
{
  "id": "evan-evanscience-art-1a442f",
  "operator": "the owner",
  "host": "evanscience-art",
  "created": "2026-08-18T20:34:17.985Z",
  "_changed": "2026-08-21 - identity unified under one the owner identity, matching the Linux box (evan-corgea-ms-7c79-6a45ef). Was <telemetry-id>: install-id.mjs fell back to the Windows account name (owner) on first run because the caller passed no repo root, so shop.json's operator (human:owner) was never read. The id and its 6-char hash are exactly what installId() would now generate for who=the owner on this machine (sha256('the owner|evanscience-art|owner')[0:6] = 1a442f), so deleting this cache regenerates the same id rather than a third one.",
  "_previous_id": "<telemetry-id>",
  "_created_note": "The 'created' value above is the Windows setup timestamp recorded in .autodev/onboarding.json, not the original value of this field - the original file could not be read from the Linux box where this replacement was written. Nothing reads this field."
}
'@
[System.IO.File]::WriteAllText("$env:USERPROFILE\autodev-reports\install.json", $json + "`n", (New-Object System.Text.UTF8Encoding $false))
```

The reason for the last line instead of Notepad: some Windows versions save text files with
an invisible marker at the front, and that marker makes this file unreadable to the tool.
That line writes it plain.

**Verify:**

```powershell
Get-Content C:\Users\<you>\autodev-reports\install.json | ConvertFrom-Json | Select-Object id, operator
```

Should print `evan-evanscience-art-1a442f` and `the owner`. If `ConvertFrom-Json` complains, the
paste got mangled — redo it.

Stronger check — ask the tool who it now thinks it is:

```powershell
node "$env:USERPROFILE\.claude\plugins\cache\autodev-marketplace\autodev\0.53.0\scripts\telemetry.mjs" whoami --to "$env:USERPROFILE\autodev-reports"
```

The `--to` is not optional on Windows: without it the tool looks for the reports folder
relative to whatever directory you're standing in and finds nothing. If the `0.53.0`
folder doesn't exist, the plugin has updated since — use the highest-numbered folder under
`...\autodev\`.

### Step 6. Confirm it took, end to end

No restart needed — the file is re-read on every upload. Within about 15 minutes:

```powershell
Get-Content C:\Users\<you>\autodev-reports\telemetry-status.json
```

**Verify:** `"install": "evan-evanscience-art-1a442f"` and a recent `lastSuccess`.

### Why that exact text, and one honest limit

The id isn't a label you get to pick — it's built from three ingredients: the operator
name, the machine name, and a 6-character fingerprint of both plus your Windows account
name. Hand-writing one risks an id the tool would never produce on its own, so that if the
file were ever deleted you'd get a *third* identity.

`1a442f` is the real computed value for operator `the owner` on that machine. I checked the
recipe by running it backwards: the same formula reproduces your current `dfd5f3` exactly.
So this file is what the tool would have written itself, and deleting it regenerates the
same id.

**The limit:** reports already filed under `<telemetry-id>` stay filed under
that name. This changes new reports only — the history splits at this point. The Linux box
has the identical split at its own changeover.

---

## Two things that will look wrong afterwards and aren't

**a. Every Claude session on Windows will claim monitoring is down.** You'll see a line
like *"monitoring: sidecar down and reinstall FAILED (no service manager for win32)"*. It
is wrong. The plugin only knows how to look for the Mac/Linux service file, so it can't
see a Windows scheduled task and reports "not running" no matter what. It can't damage
anything — it just can't see. Trust
`.\ops\autodev-watch-windows.ps1 status` and the heartbeat instead.

**b. Re-run the installer after any AutoDev plugin update.** The registration hard-codes
the path to the current plugin version's monitor. Mac and Linux repair that themselves;
Windows can't. Until you re-run it, the machine keeps running the old version, or stops if
the old folder was cleaned up.

```powershell
.\ops\autodev-watch-windows.ps1
```

Seconds, and safe to run any time.

Same applies if you switch Node versions with nvm-windows / fnm / volta — the absolute path
to `node.exe` is recorded at install time and those tools move it.

---

Full background, including what was and wasn't tested from Linux:
`.autodev/notes/windows-autostart.md`.
