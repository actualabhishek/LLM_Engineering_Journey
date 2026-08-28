# Watchdog for the postflow Telegram listener.
#
# Keeps a "claude --channels plugin:telegram@claude-plugins-official" session
# alive, relaunching it whenever it exits (crash, closed window, exit, etc).
# The session is seeded with a plain-text instruction to run /postflow start
# as its first prompt, so the listener is armed automatically on every
# relaunch - no manual typing needed. (A literal "/postflow start" as the CLI
# prompt argument does NOT work - Claude Code's CLI parser reads a leading
# "/" as an attempt to invoke a top-level CLI subcommand, not chat text, and
# fails with "Unknown command: /postflow" - confirmed by testing.)
#
# Stop cleanly with stop-watchdog.ps1 (writes a sentinel file this loop checks
# for between runs) rather than killing this script's window directly, or the
# next Task Scheduler trigger / crash-restart will just bring it back.

$ErrorActionPreference = "Continue"

$RepoRoot = "F:\claude_code_VS\LinkedIn_Post_Automation"
$LogDir   = Join-Path $RepoRoot "postflow-plugin\logs"
$LogFile  = Join-Path $LogDir "watchdog.log"
$StopFile = Join-Path $RepoRoot "postflow-plugin\state\watchdog.stop"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $RepoRoot

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Write-Log "=== Watchdog started (PID $PID) ==="

$restartTimestamps = New-Object System.Collections.Generic.List[datetime]

while ($true) {
    if (Test-Path $StopFile) {
        Write-Log "Stop file found - exiting watchdog without relaunching."
        Remove-Item $StopFile -Force
        break
    }

    # Crash-loop guard: if we've restarted 10+ times in the last 10 minutes,
    # something is persistently broken (bad auth, bad flag, etc) - back off
    # instead of hammering the API / relaunching in a tight loop.
    $now = Get-Date
    $restartTimestamps.RemoveAll({ param($t) $t -lt $now.AddMinutes(-10) }) | Out-Null
    if ($restartTimestamps.Count -ge 10) {
        Write-Log "10+ restarts in the last 10 minutes - backing off for 15 minutes. Check the log above for the recurring error."
        Start-Sleep -Seconds 900
        $restartTimestamps.Clear()
        continue
    }

    Write-Log "Launching claude session..."
    $restartTimestamps.Add($now)

    try {
        # Argument order matters: --channels is variadic and swallows any bare
        # word placed right after it (confirmed by testing), and a prompt
        # starting with "/" gets misread as a CLI subcommand instead of chat
        # text (also confirmed) - so the prompt must come first, be plain
        # text, and --dangerously-skip-permissions must come after --channels
        # so it isn't swallowed as a channel entry.
        & claude "Run /postflow start now to arm the Telegram listener for this session." --channels plugin:telegram@claude-plugins-official --dangerously-skip-permissions
        $code = $LASTEXITCODE
        Write-Log "claude exited with code $code."
    } catch {
        Write-Log "claude threw: $($_.Exception.Message)"
    }

    if (Test-Path $StopFile) {
        Write-Log "Stop file found after exit - exiting watchdog."
        Remove-Item $StopFile -Force
        break
    }

    Write-Log "Restarting in 15 seconds..."
    Start-Sleep -Seconds 15
}

Write-Log "=== Watchdog stopped ==="

