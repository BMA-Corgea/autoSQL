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
    'C:\Users\<you>\FILL-THIS-IN'
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
