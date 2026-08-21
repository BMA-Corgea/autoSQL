# Windows autostart for the monitoring watcher

Answering Evan's **Q46** — *"Still on Windows — make it automatic."*

**I could not do this for you. I am on the Linux box.** Registering a Windows Scheduled Task
requires the `ScheduledTasks` module, which only exists on Windows; there is no remote path
from here to that machine. So what follows is the exact thing **you** run there, plus a precise
account of what I did and did not manage to test from here.

**Status: written and machine-checked, never executed on Windows.**

| | |
|---|---|
| Script | `ops/autodev-watch-windows.ps1` (in this repo — `git pull` on Windows and run it), also inline below |
| Tested here | PowerShell 7.6.5 (downloaded to a scratch dir for this job): parses clean; the generated launcher parses clean; argument quoting verified in **both** argument-passing modes; every input guard exercised; the real `watch.mjs` ran through the generated launcher and found 3 repos |
| **Not** tested here | `Register-ScheduledTask` and everything else in the `ScheduledTasks` module — Windows-only. The task settings are written from documented behaviour, not from a run |
| Blast radius | read-only; the watcher never writes ticket state |

---

## 1. What you run on Windows

Open **Windows PowerShell** (5.1 is fine; PowerShell 7 also works), then:

```powershell
cd $env:USERPROFILE\<wherever autoSQL lives>\autoSQL
notepad .\ops\autodev-watch-windows.ps1        # set $RepoParents in the block at the top
.\ops\autodev-watch-windows.ps1                # install (idempotent — re-run any time)
```

If PowerShell refuses to run it (`running scripts is disabled on this system`), either unblock
the one file or launch it explicitly:

```powershell
Unblock-File .\ops\autodev-watch-windows.ps1
# or, without changing any policy:
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\autodev-watch-windows.ps1
```

**Check it:**

```powershell
.\ops\autodev-watch-windows.ps1 status     # task state + node pid + heartbeat age
.\ops\autodev-watch-windows.ps1 logs       # last 40 lines of the watcher's own output
```

or straight from Windows, with no script involved:

```powershell
Get-ScheduledTask -TaskPath '\AutoDev\' | Get-ScheduledTaskInfo
schtasks /query /tn "\AutoDev\AutoDev monitoring sidecar" /v /fo LIST
Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Select-Object ProcessId, CommandLine
Get-Content $env:USERPROFILE\autodev-reports\heartbeat.json
```

**Remove it:**

```powershell
.\ops\autodev-watch-windows.ps1 uninstall
# or straight from Windows:
Unregister-ScheduledTask -TaskName 'AutoDev monitoring sidecar' -TaskPath '\AutoDev\' -Confirm:$false
```

`status` deliberately does not stop at "the task is running". It reads
`%USERPROFILE%\autodev-reports\heartbeat.json` and reports its **age**, because the plugin's own
rule (`scripts/lib/monitoring-health.mjs`) is that a live process is not the fact that matters —
reports landing is. A running watcher with a stale heartbeat is a broken watcher.

---

## 2. The script

Everything you need to change is in the marked block at the top. Nothing below it needs editing.

```powershell
#Requires -Version 5.1
<#
    autodev-watch-windows.ps1 — run the AutoDev monitoring sidecar automatically on Windows.

    The plugin installs itself as a launchd agent (macOS) or a systemd --user unit (Linux).
    It has no Windows branch, so it refuses:
        scripts/sidecar-service.mjs:100
        return { ok: false, os, error: `no service manager for ${os} — start it by hand: ...` }
    This registers the Windows equivalent: a Scheduled Task that starts watch.mjs at logon,
    with no visible window, and restarts it if it dies.

    Usage (Windows PowerShell 5.1 or PowerShell 7):
        .\autodev-watch-windows.ps1              # install (or re-install; idempotent)
        .\autodev-watch-windows.ps1 status
        .\autodev-watch-windows.ps1 logs
        .\autodev-watch-windows.ps1 uninstall
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('install', 'status', 'logs', 'start', 'stop', 'uninstall')]
    [string]$Action = 'install'
)

# ============================================================================
# ===  EDIT THIS BLOCK — NOTHING BELOW IT  ===================================
# ============================================================================

# 1. THE ONE THING YOU MUST SET.
#    The folder(s) that CONTAIN your AutoDev repos — the PARENT, not the repo itself.
#    (On the Linux box this is /home/corgea/Desktop/Coding Projects, which holds
#     autoSQL, GUTS and GLP-Strong-App.)
#    Spaces are fine — that is the whole point of how this script passes arguments.
#    No trailing backslash. A comma inside a path is impossible: watch.mjs splits
#    --roots on commas, so the script refuses one instead of breaking quietly.
$RepoParents = @(
    'C:\Users\evanb\FILL-THIS-IN'
)

# 2. node.exe. 'auto' looks on PATH, then the usual install locations.
#    If you use nvm-windows / fnm / volta, PUT THE REAL PATH HERE — shims often do not
#    resolve inside a Scheduled Task, which has no shell profile.
$NodeExe = 'auto'

# 3. watch.mjs. 'auto' picks the newest installed AutoDev plugin version.
$WatchScript = 'auto'

# 4. Cadence. These are the same numbers sidecar-service.mjs install() uses on mac/Linux.
$IntervalSeconds = 60   # seconds between sweeps  (watch.mjs --interval)
$UploadMinutes   = 15   # minutes between uploads (watch.mjs --upload; 0 disables uploading)

# 5. How the task logs on.
#    'Interactive' — runs when you log in. No elevation needed to register. (default)
#    'S4U'         — also runs when you are NOT logged in, and can never flash a window.
#                    Register-ScheduledTask usually needs an ELEVATED PowerShell for this.
$LogonType = 'Interactive'

# ============================================================================
# ===  END OF THE EDIT BLOCK  ================================================
# ============================================================================

# No Set-StrictMode here on purpose: -Version 2.0 THROWS on a reference to a property that
# does not exist, and this script reads optional keys out of telemetry-status.json.
$ErrorActionPreference = 'Stop'

$TaskName  = 'AutoDev monitoring sidecar'
$TaskPath  = '\AutoDev\'
$StateDir  = Join-Path $env:LOCALAPPDATA 'AutoDev'
$Launcher  = Join-Path $StateDir 'autodev-watch-launcher.ps1'
$LogFile   = Join-Path $StateDir 'watch.log'
$ReportDir = Join-Path $env:USERPROFILE 'autodev-reports'
$WinPS     = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Say  ([string]$m) { Write-Host $m }
function Warn ([string]$m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die  ([string]$m) { Write-Host "  x $m" -ForegroundColor Red; exit 1 }

# Quote a string as a PowerShell single-quoted literal. Single quotes take no escapes,
# so a Windows path can never turn into an escape sequence — this is what keeps
# 'C:\Coding Projects\' out of trouble when it is baked into the launcher.
function Q ([string]$s) { "'" + ($s -replace "'", "''") + "'" }

function Get-NodeExe {
    if ($NodeExe -ne 'auto') {
        if (-not (Test-Path -LiteralPath $NodeExe)) { Die "NodeExe does not exist: $NodeExe" }
        return (Resolve-Path -LiteralPath $NodeExe).Path
    }
    $cmd = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    # String concatenation, not Join-Path: Join-Path THROWS if the env var is unset, which
    # would take out the whole search instead of skipping one candidate.
    $bases = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)
    foreach ($b in $bases) {
        if (-not $b) { continue }
        foreach ($sub in @('\nodejs\node.exe', '\Programs\nodejs\node.exe')) {
            $c = $b + $sub
            if (Test-Path -LiteralPath $c) { return $c }
        }
    }
    Die "Could not find node.exe. Set `$NodeExe in the edit block to its full path."
}

function Get-WatchScript {
    if ($WatchScript -ne 'auto') {
        if (-not (Test-Path -LiteralPath $WatchScript)) { Die "WatchScript does not exist: $WatchScript" }
        return (Resolve-Path -LiteralPath $WatchScript).Path
    }
    $base = Join-Path $env:USERPROFILE '.claude\plugins\cache\autodev-marketplace\autodev'
    if (-not (Test-Path -LiteralPath $base)) { Die "AutoDev plugin cache not found at $base — set `$WatchScript by hand." }
    $best = Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'scripts\watch.mjs') } |
        Sort-Object -Property @{ Expression = { try { [version]$_.Name } catch { [version]'0.0.0' } } } -Descending |
        Select-Object -First 1
    if (-not $best) { Die "No plugin version under $base contains scripts\watch.mjs — set `$WatchScript by hand." }
    return (Join-Path $best.FullName 'scripts\watch.mjs')
}

function Get-Roots {
    $clean = @()
    foreach ($r in $RepoParents) {
        $t = ([string]$r).Trim().TrimEnd('\')          # a trailing \ is the classic Windows quoting bomb
        if (-not $t) { continue }
        if ($t -like '*FILL-THIS-IN*') { Die 'Set $RepoParents in the edit block at the top to the folder that holds your repos.' }
        if ($t.Contains(',')) { Die "A comma in a path cannot work — watch.mjs splits --roots on commas: $t" }
        # Loud, not lenient. A root that does not exist is how monitoring goes dark without
        # an error: the watcher runs happily and discovers nothing, forever.
        if (-not (Test-Path -LiteralPath $t)) { Die "This folder does not exist: $t" }
        $clean += $t
    }
    if (-not $clean) { Die 'RepoParents is empty. Put the folder that contains your repos in the edit block.' }
    return , $clean
}

function Get-Task { Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue }

function Write-Launcher ([string]$node, [string[]]$argv) {
    # The whole point of a generated launcher: the task's command line carries ONE argument
    # (-File <launcher>), and the arguments that contain spaces live inside the launcher as
    # a PowerShell array. `& $node @argv` hands each element to node as its own argv entry,
    # so nothing re-parses 'Coding Projects' into two words.
    $template = @'
# GENERATED by autodev-watch-windows.ps1 — do not edit; re-run that script instead.
$ErrorActionPreference = 'Continue'
$log  = __LOG__
$node = __NODE__
$argv = __ARGV__

$dir = Split-Path -Parent $log
if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
if ((Test-Path -LiteralPath $log) -and ((Get-Item -LiteralPath $log).Length -gt 5MB)) {
    Move-Item -LiteralPath $log -Destination ($log + '.1') -Force -ErrorAction SilentlyContinue
}
("[{0}] starting {1} {2}" -f (Get-Date -Format s), $node, ($argv -join ' ')) |
    Out-File -FilePath $log -Append -Encoding utf8

& $node @argv *>> $log
# A null exit code (killed, not exited) must NOT read as success, or restart-on-failure sleeps.
if ($null -eq $LASTEXITCODE) { exit 1 }
exit $LASTEXITCODE
'@
    $argvLiteral = '@(' + (($argv | ForEach-Object { Q $_ }) -join ', ') + ')'
    $body = $template.Replace('__LOG__', (Q $LogFile)).Replace('__NODE__', (Q $node)).Replace('__ARGV__', $argvLiteral)
    if (-not (Test-Path -LiteralPath $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }
    [System.IO.File]::WriteAllText($Launcher, $body, (New-Object System.Text.UTF8Encoding $true))
}

function Invoke-Install {
    $node  = Get-NodeExe
    $watch = Get-WatchScript
    $roots = Get-Roots
    $rootsArg = ($roots -join ',')

    $argv = @($watch, '--roots', $rootsArg, '--interval', "$IntervalSeconds", '--upload', "$UploadMinutes")

    Say ''
    Say 'AutoDev monitoring sidecar — installing as a Scheduled Task'
    Say "  node    : $node"
    Say "  watcher : $watch"
    Say "  roots   : $rootsArg"
    Say "  log     : $LogFile"
    Say ''

    # PREFLIGHT: one real sweep, synchronously, before anything is registered. If the roots are
    # wrong you see '0 repo(s)' here instead of discovering it in three weeks of silence.
    Say 'Preflight sweep (read-only, nothing archived):'
    & $node @($watch, '--once', '--no-ship', '--roots', $rootsArg)
    if ($LASTEXITCODE -ne 0) { Warn "the preflight sweep exited $LASTEXITCODE — installing anyway, but check the output above." }
    Say ''

    Write-Launcher -node $node -argv $argv

    $userId = "$env:USERDOMAIN\$env:USERNAME"
    $taskArgs = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $Launcher

    $action = New-ScheduledTaskAction -Execute $WinPS -Argument $taskArgs -WorkingDirectory $env:USERPROFILE

    $triggers = @()
    $triggers += New-ScheduledTaskTrigger -AtLogOn -User $userId
    # Keep-alive: the closest Windows gets to systemd's Restart=always. RestartCount below
    # covers a crash; this covers "it is simply not running any more, for any reason".
    # MultipleInstances=IgnoreNew means a re-trigger while it is healthy is a no-op.
    try {
        $keep = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
                    -RepetitionInterval (New-TimeSpan -Minutes 5) `
                    -RepetitionDuration ([TimeSpan]::MaxValue)
        $triggers += $keep
    } catch {
        Warn "could not add the 5-minute keep-alive trigger on this Windows build ($($_.Exception.Message))."
        Warn 'Logon trigger + restart-on-failure are still installed.'
    }

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
    $settings.Priority = 7   # background priority, matching launchd's ProcessType=Background

    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType $LogonType -RunLevel Limited

    if ($LogonType -eq 'S4U') {
        $admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
                 ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $admin) { Warn 'LogonType S4U normally requires an elevated PowerShell. If registration fails, re-run this from an Administrator prompt, or set $LogonType = ''Interactive''.' }
    }

    # -Force replaces any existing definition instead of stacking a second watcher —
    # the same idempotence the mac/Linux installer gets from `launchctl unload` first.
    Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath `
        -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
    Start-Sleep -Seconds 12   # let the first sweep land a heartbeat before we read it
    Say 'Installed.'
    Invoke-Status
}

function Invoke-Status {
    Say ''
    $t = Get-Task
    if (-not $t) { Say 'Task     : NOT INSTALLED'; return }

    $info = $t | Get-ScheduledTaskInfo
    Say ("Task     : {0}{1}" -f $TaskPath, $TaskName)
    Say ("State    : {0}" -f $t.State)
    Say ("Last run : {0}  (result 0x{1:X})" -f $info.LastRunTime, $info.LastTaskResult)
    Say ("Next run : {0}" -f $info.NextRunTime)

    $procs = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and $_.CommandLine -match 'watch\.mjs' })
    if ($procs.Count -gt 0) {
        foreach ($p in $procs) { Say ("Process  : node.exe pid {0}" -f $p.ProcessId) }
    } else {
        Warn 'no node.exe running watch.mjs was found'
    }

    # THE ONLY REAL PROOF. The plugin is explicit that a live process is not the fact that
    # matters (scripts/lib/monitoring-health.mjs) — reports LANDING is. heartbeat.json is
    # rewritten every single sweep, so its age is the honest answer to "is it working".
    $hb = Join-Path $ReportDir 'heartbeat.json'
    if (Test-Path -LiteralPath $hb) {
        try {
            $age = [int]((Get-Date) - (Get-Item -LiteralPath $hb).LastWriteTime).TotalSeconds
            $j   = Get-Content -LiteralPath $hb -Raw | ConvertFrom-Json
            Say ("Heartbeat: {0}s ago — {1} repo(s) watched, roots {2}" -f $age, $j.reposWatched, ($j.roots -join ','))
            if ($age -gt ($IntervalSeconds * 3)) { Warn "heartbeat is stale (> 3 sweeps). Check: $LogFile" }
            if ($j.reposWatched -eq 0) { Warn 'the watcher is running but sees ZERO repos — the roots are wrong.' }
        } catch { Warn "heartbeat.json is unreadable: $($_.Exception.Message)" }
    } else {
        Warn "no heartbeat.json in $ReportDir yet — give it one sweep ($IntervalSeconds s), then check $LogFile"
    }

    $ts = Join-Path $ReportDir 'telemetry-status.json'
    if (Test-Path -LiteralPath $ts) {
        try {
            $spine = Get-Content -LiteralPath $ts -Raw | ConvertFrom-Json
            $ok  = $spine.PSObject.Properties['lastSuccess']
            $bad = $spine.PSObject.Properties['lastError']
            Say ("Uploads  : lastSuccess={0} lastError={1}" -f
                 $(if ($ok)  { $ok.Value }  else { 'never' }),
                 $(if ($bad) { $bad.Value } else { 'none' }))
            if (-not $ok -or -not $ok.Value) { Warn 'running is not reporting: no upload has EVER succeeded from this machine.' }
        } catch { Warn "telemetry-status.json is unreadable: $($_.Exception.Message)" }
    }
    Say ''
}

function Invoke-Logs {
    if (-not (Test-Path -LiteralPath $LogFile)) { Say "No log yet at $LogFile"; return }
    Get-Content -LiteralPath $LogFile -Tail 40
}

function Invoke-Start { Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath; Say 'Started.'; Invoke-Status }

function Invoke-Stop  { Stop-ScheduledTask  -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue; Say 'Stopped (it will start again at next logon / keep-alive tick).' }

function Invoke-Uninstall {
    $t = Get-Task
    if (-not $t) { Say 'Nothing to remove — the task is not installed.' }
    else {
        Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        Say 'Scheduled Task removed.'
    }
    foreach ($p in @($Launcher)) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; Say "Removed $p" }
    }
    $stray = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and $_.CommandLine -match 'watch\.mjs' })
    foreach ($p in $stray) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Say ("Killed stray watcher pid {0}" -f $p.ProcessId) }
    Say "Left alone: $LogFile and $ReportDir (your reports)."
}

switch ($Action) {
    'install'   { Invoke-Install }
    'status'    { Invoke-Status }
    'logs'      { Invoke-Logs }
    'start'     { Invoke-Start }
    'stop'      { Invoke-Stop }
    'uninstall' { Invoke-Uninstall }
}
```

---

## 3. Why the plugin refuses, and what it does on the other two platforms

`scripts/sidecar-service.mjs` has exactly two branches. Windows falls off the end of them:

```js
// sidecar-service.mjs:80   export function install({ roots, interval, upload, home, os = platform(), exec = run })
if (os === "darwin") { ...launchd plist...  }                              // :84
if (os === "linux")  { ...systemd --user... }                              // :92
return { ok: false, os, error: `no service manager for ${os} — start it by hand: node ${script} --roots ${roots}` };   // :100
```

That refusal is not an oversight the plugin might quietly fix — it is a locked contract:
`tests/contracts/monitoring/sidecar.test.mjs:67` asserts `install({ os: "win32" }).ok === false`
and that the error says "start it by hand". It is also exactly what your Windows onboarding
recorded: *"sidecar-service.mjs install REFUSED on win32 … Started watch.mjs by hand in
background instead … NOT persistent across sessions."*

What the two supported platforms actually set up, and what I mirrored:

| | macOS (`plist()`, :40) | Linux (`unit()`, :61) | This Scheduled Task |
|---|---|---|---|
| Where | `~/Library/LaunchAgents/com.autodev.watch.plist` | `~/.config/systemd/user/autodev-watch.service` | `\AutoDev\AutoDev monitoring sidecar` |
| Command | `node watch.mjs --roots R --interval 60 --upload 15` | same | same |
| Start | `RunAtLoad` | `WantedBy=default.target` | `-AtLogOn` trigger |
| Restart | `KeepAlive` (always) | `Restart=always`, `RestartSec=30` | `RestartInterval 1min / RestartCount 3`, **plus** a 5-minute repetition trigger with `MultipleInstances IgnoreNew` |
| No time limit | n/a | n/a | `ExecutionTimeLimit = 0` (Windows kills a task after 3 days by default) |
| Priority | `ProcessType Background` | — | `$settings.Priority = 7` |
| Output | `~/autodev-reports/watch.log` | journald | `%LOCALAPPDATA%\AutoDev\watch.log`, rotated at 5 MB |
| Idempotent | `launchctl unload` then `load` | `daemon-reload` + `enable --now` | `Register-ScheduledTask -Force` |

Two deliberate differences from the mac/Linux behaviour:

- **The log does not go in `~/autodev-reports`.** launchd puts `watch.log` there, but that folder
  is the telemetry archive, and `telemetry.mjs upload()` runs `git add -A` over it when a git
  remote is configured. Log and launcher live in `%LOCALAPPDATA%\AutoDev\` instead, so nothing
  local ever rides along with your reports.
- **The Windows task also rotates the log** at 5 MB. launchd and systemd never rotate this file
  at all; at a 60-second cadence it grows perhaps 30 KB an hour, forever.

The two battery settings (`-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`) are not
decoration. Task Scheduler's defaults are the opposite of both, and on a laptop that alone is
enough to make a task look installed and never run.

---

## 4. The quoting trap — the thing this had to get right

Your Windows onboarding note already records the Linux version of this bug: the plugin's
`unit()` wrote `--roots` **unquoted**, systemd split `/home/corgea/Desktop/Coding Projects` at
the space, and the watcher silently watched a folder called `.../Coding` that does not exist.
Both local patches are still in place and still local:

```
$ git -C ~/.claude/plugins/marketplaces/autodev-marketplace diff --stat
 scripts/lib/sidecar-heal.mjs | 2 +-
 scripts/sidecar-service.mjs  | 2 +-
 2 files changed, 2 insertions(+), 2 deletions(-)
```

and the change itself, in `unit()` at `sidecar-service.mjs:66`:

```diff
-ExecStart=${node} ${script} --roots ${roots} --interval ${interval} --upload ${upload}
+ExecStart="${node}" "${script}" --roots "${roots}" --interval ${interval} --upload ${upload}
```

Why it matters that much, proved here rather than asserted — the same watcher, same machine,
the only difference being whether the path arrived as one argument or two:

```
$ node watch.mjs --once --no-ship --roots "/home/corgea/Desktop/Coding Projects"
AutoDev watch · corgea-MS-7C79 · 3 repo(s) · window 24h · read-only, no AI
  GLP-Strong-App / GUTS / autoSQL

$ node watch.mjs --once --no-ship --roots /home/corgea/Desktop/Coding Projects
AutoDev watch · corgea-MS-7C79 · 0 repo(s) · window 24h · read-only, no AI
No AutoDev-enrolled repos found.
```

No error. No warning. Just zero. That is the failure mode this script exists to avoid, so it
never builds a command-line string at all:

1. The **task's** argument string carries exactly one path (`-File "<launcher>"`), and that path
   has no spaces of its own and never ends in a backslash.
2. The **launcher** holds the real arguments as a PowerShell array of single-quoted literals,
   and calls `& $node @argv`. Splatting hands each element to the process as its own argv entry.
   Single-quoted PowerShell strings have no escape characters, so `C:\Users\evanb\Coding
   Projects` cannot become anything else; an apostrophe in a folder name is doubled on the way in.
3. `Get-Roots` strips a trailing backslash before the value is ever used. On Windows, a quoted
   argument ending in `\` puts a `\"` in front of the closing quote, which the C runtime reads as
   an *escaped quote* — the classic way a correctly-quoted path still gets mangled.
4. It refuses a path containing a comma outright, because `watch.mjs:205` splits `--roots` on
   commas and there is no escape for it.

There is also no `--roots=C:\...` form to fall back on. The shared parser only accepts a flag and
its value as two separate arguments — I checked what it does with the other shapes:

```
["--roots","C:\\Users\\Evan\\Coding Projects","--interval","60"]
  -> flags: {"roots":"C:\\Users\\Evan\\Coding Projects","interval":"60"}      correct

["--roots=C:\\Users\\Evan\\Coding Projects"]
  -> flags: {"roots=C:\\Users\\Evan\\Coding Projects":true}                   roots is UNSET
                                                            (silently falls back to $HOME)

["--roots","C:\\Users\\Evan\\Coding","Projects"]
  -> flags: {"roots":"C:\\Users\\Evan\\Coding"}, positionals: ["Projects"]    the split-path bug
```

---

## 5. What I actually tested, and what I could not

I downloaded PowerShell 7.6.5 into a scratch directory (no root, nothing installed on this
machine) so the checks below are real runs, not readings.

**Tested, passing:**

| Check | Result |
|---|---|
| `Parser::ParseFile` on the shipped script | `PARSE OK - ops/autodev-watch-windows.ps1, 1691 tokens`, 0 syntax errors |
| `Parser::ParseFile` on the *generated* launcher | `generated launcher parses OK` |
| Argv fidelity, PowerShell 7 "Standard" passing | `["--roots","C:\\Users\\Evan\\Coding Projects,D:\\Ev's Repos\\work","--interval","60","--upload","15"]` |
| Argv fidelity, **"Legacy"** passing (what Windows PowerShell 5.1 does) | byte-identical to the above |
| Real `watch.mjs` launched *through the generated launcher* | `AutoDev watch · 3 repo(s)` written to the rotating log, exit 0 |
| `Get-Roots` — unedited placeholder | dies: *"Set $RepoParents in the edit block…"* |
| `Get-Roots` — folder does not exist | dies: *"This folder does not exist: …"* |
| `Get-Roots` — comma in a path | dies: *"A comma in a path cannot work…"* |
| `Get-Roots` — padding + trailing separator on a real spaced path | `[/home/corgea/Desktop/Coding Projects]` |

Two defects that these runs caught and I then fixed, rather than shipping them to you:

- `Set-StrictMode -Version 2.0` **throws** on a reference to a property that does not exist, and
  `status` reads optional keys out of `telemetry-status.json`. Proved:
  `STRICTMODE THREW on missing property: The property 'lastSuccess' cannot be found on this object.`
  Strict mode is gone and those reads are property-existence checked inside `try/catch`.
- `Join-Path` **throws** on a null path, so a machine without `%ProgramFiles(x86)%` would have
  killed the whole node.exe search instead of skipping one candidate. Proved:
  `JOIN-PATH THREW on null: Cannot bind argument to parameter 'Path' because it is null.`
  Path candidates are now built by string concatenation with a null check.

**Not tested — cannot be, from Linux:**

- `Register-ScheduledTask`, `New-ScheduledTaskTrigger/-Settings/-Principal`, `Get-ScheduledTaskInfo`,
  `Unregister-ScheduledTask`. The `ScheduledTasks` module does not exist off Windows.
- Whether `-RepetitionDuration ([TimeSpan]::MaxValue)` is accepted on your Windows build. Some
  builds reject it. If yours does, install still succeeds — the keep-alive trigger is wrapped in
  `try/catch` and you get a printed warning, with the logon trigger and restart-on-failure intact.
- Whether a console window flashes for an instant at logon under `LogonType = 'Interactive'`.
  The task runs `powershell.exe -WindowStyle Hidden`, so no window should remain, but I cannot
  promise there is no flash. If it bothers you, set `$LogonType = 'S4U'` in the edit block and
  re-run the installer **from an elevated PowerShell** — S4U never touches your desktop session,
  and it also keeps the watcher running when you are logged out.
- The trailing-backslash trap in point 3 above. PowerShell on Linux does not use the Windows
  command-line parser, so my run there passed the backslash through intact — which proves nothing
  about Windows. The `TrimEnd('\')` is defensive, based on the documented Windows rule.
- `Get-CimInstance Win32_Process` filtering on `CommandLine` — CIM exists only on Windows.

---

## 6. Windows-specific things that will bite, that this script cannot fix

**a. Every session start on Windows will claim monitoring is broken.** The hook runs
`healSidecar()` (`hooks/session-start.mjs:310`), which calls `statusOf()`. On any non-macOS
platform that function looks for the **systemd unit path**:

```js
// sidecar-service.mjs:126
const p = os === "darwin" ? plistPath(home) : unitPath(home);   // ~/.config/systemd/user/autodev-watch.service
```

On Windows that file will never exist, and `running` is only ever computed for `darwin` and
`linux` — so it is permanently `false`. The heal then tries to reinstall, `install()` refuses,
and your session brief prints:

> `monitoring: sidecar down and reinstall FAILED (no service manager for win32 — start it by hand: …)`

**That line will be wrong, and there is nothing the Scheduled Task can do about it.** Ignore it
and trust `heartbeat.json` instead. The heal is read-only about this: it cannot damage the task,
it just cannot see it. The real fix is a `win32` branch in `statusOf()` shelling out to `schtasks`,
which belongs upstream — worth filing, but I have not written or tested one, and a plugin update
reverts local patches anyway (you already have two riding on that).

**b. A plugin update breaks the path, and Windows cannot self-heal it.** The launcher hard-codes
`…\autodev\0.53.0\scripts\watch.mjs`. On mac/Linux the session-start heal notices a stale script
path and reinstalls itself. On Windows it cannot. **After every AutoDev plugin update, re-run
`.\ops\autodev-watch-windows.ps1`** — it is idempotent, takes seconds, and re-resolves to the
newest version folder automatically. Until you do, the watcher keeps running the old version's
watcher, or dies if the old folder was cleaned up.

**c. Version managers.** If `node` on Windows comes from nvm-windows, fnm or volta, the thing on
your PATH may be a shim that only resolves inside an initialised shell. A Scheduled Task has no
profile. The installer resolves and hard-codes an absolute `node.exe` at install time, which
mostly handles this — but if you later switch node versions with one of those tools, the recorded
path can vanish. Re-run the installer after a node version change too, or set `$NodeExe` to a
stable path in the edit block.

**d. It watches every AutoDev repo it finds, not just autoSQL.** That is `watch.mjs`'s design —
`--roots` is a folder to search, depth 3. Point it at the folder that holds your repos, not at
`C:\Users\evanb`, which would sweep your whole profile every 60 seconds. Anything you do not want
observed gets `.autodev/monitoring.json` with `{"enabled": false}`, and the watcher will say out
loud that it is skipping it.

**e. Two machines, two identities.** The Windows box already files telemetry as
`evanb-evanscience-art-dfd5f3` and this Linux box as `corgea-corgea-ms-7c79-da02f2`. Making the
Windows watcher permanent means it starts filing continuously under that separate id. That is
Q45's question, not this one — but this is the change that makes it start mattering.
