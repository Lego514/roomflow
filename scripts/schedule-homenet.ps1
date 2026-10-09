<#
.SYNOPSIS
    Run RoomFlow's home measurements on a schedule (Windows Task Scheduler).

.DESCRIPTION
    Registers three tasks for the current user, in the \RoomFlow\ task folder.
    They run only while you are logged on, with no console window, and append
    their output to data\homenet.log. Results go to data\home.sqlite; see them
    with `python -m homenet report`.

      check        every 5 minutes   Wi-Fi + latency layer by layer (skipped while a bloat test runs)
      path         every 2 hours     hop-by-hop trace to 1.1.1.1, then IPv4 vs IPv6
      capacity     every hour (:20)  available download/upload, ~5 s each way at full speed
                                     (about 0.15 GB each time at 200/40 Mbps)
      bloat        08:30 13:00 21:00 bufferbloat test: saturates the connection for ~40 s,
                                     about 0.3 GB of data each time at 200/40 Mbps

.EXAMPLE
    .\scripts\schedule-homenet.ps1 install
    .\scripts\schedule-homenet.ps1 status
    .\scripts\schedule-homenet.ps1 uninstall
#>
param(
    [ValidateSet("install", "uninstall", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$TaskPath = "\RoomFlow\"
$Repo = Split-Path -Parent $PSScriptRoot

function Get-Pythonw {
    $python = (Get-Command python -ErrorAction Stop).Source
    $pythonw = Join-Path (Split-Path $python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }
    return $pythonw
}

function New-HomenetAction([string]$Pythonw, [string]$Arguments) {
    $log = Join-Path $Repo "data\homenet.log"
    New-ScheduledTaskAction -Execute $Pythonw -Argument "-m homenet --log `"$log`" $Arguments" -WorkingDirectory $Repo
}

function Install-Tasks {
    $pythonw = Get-Pythonw
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive -RunLevel Limited
    $start = (Get-Date).Date.AddMinutes([Math]::Ceiling((Get-Date).TimeOfDay.TotalMinutes / 5) * 5)

    $tasks = @(
        @{
            Name    = "check"
            Actions = @(New-HomenetAction $pythonw "check --count 5 --skip-during-bloat")
            Trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 5)
        },
        @{
            Name    = "path"
            # One action: Task Scheduler starts multiple actions without waiting for each other.
            Actions = @(New-HomenetAction $pythonw "path")
            Trigger = New-ScheduledTaskTrigger -Once -At $start.AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 2)
        },
        @{
            Name    = "capacity"
            Actions = @(New-HomenetAction $pythonw "capacity")
            Trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddHours((Get-Date).Hour).AddMinutes(20)) `
                -RepetitionInterval (New-TimeSpan -Hours 1)
        },
        @{
            Name    = "bloat"
            Actions = @(New-HomenetAction $pythonw "bloat")
            Trigger = @(
                (New-ScheduledTaskTrigger -Daily -At "08:30"),
                (New-ScheduledTaskTrigger -Daily -At "13:00"),
                (New-ScheduledTaskTrigger -Daily -At "21:00")
            )
        }
    )
    foreach ($t in $tasks) {
        Register-ScheduledTask -TaskPath $TaskPath -TaskName $t.Name -Action $t.Actions -Trigger $t.Trigger `
            -Settings $settings -Principal $principal -Force | Out-Null
        Write-Host "registered $TaskPath$($t.Name)"
    }
    Write-Host "`nlog:     $(Join-Path $Repo 'data\homenet.log')"
    Write-Host "results: python -m homenet report"
}

function Uninstall-Tasks {
    $existing = Get-ScheduledTask -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if (-not $existing) { Write-Host "nothing installed"; return }
    $existing | Unregister-ScheduledTask -Confirm:$false
    Write-Host "removed $($existing.Count) tasks from $TaskPath"
}

function Show-Status {
    $existing = Get-ScheduledTask -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if (-not $existing) { Write-Host "not installed (run: .\scripts\schedule-homenet.ps1 install)"; return }
    $existing | ForEach-Object {
        $info = $_ | Get-ScheduledTaskInfo
        [pscustomobject]@{
            Task       = $_.TaskName
            State      = $_.State
            LastRun    = $info.LastRunTime
            LastResult = $info.LastTaskResult
            NextRun    = $info.NextRunTime
        }
    } | Format-Table -AutoSize
}

switch ($Action) {
    "install"   { Install-Tasks }
    "uninstall" { Uninstall-Tasks }
    "status"    { Show-Status }
}
