# Cleanly stops the postflow watchdog (see watchdog.ps1) without needing to
# touch Task Scheduler or hunt down the process yourself.
#
# Usage: powershell -File stop-watchdog.ps1

$RepoRoot = "F:\claude_code_VS\LinkedIn_Post_Automation"
$StopFile = Join-Path $RepoRoot "postflow-plugin\state\watchdog.stop"

New-Item -ItemType Directory -Force -Path (Split-Path $StopFile) | Out-Null
New-Item -ItemType File -Force -Path $StopFile | Out-Null

Write-Host "Stop signal written to $StopFile."
Write-Host "The watchdog will exit once the current claude session ends (it checks between runs, not mid-session)."
Write-Host ""
Write-Host "To also end the currently-running claude session right now:"
Write-Host "  Get-Process claude -ErrorAction SilentlyContinue | Stop-Process"
Write-Host ""
Write-Host "This only stops the watchdog loop for this login session's lifetime — it will start again at next logon"
Write-Host "via the PostflowTelegramListener scheduled task. To disable that too:"
Write-Host "  Disable-ScheduledTask -TaskName PostflowTelegramListener"
