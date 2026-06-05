# FootStats — rejestracja zadań w Windows Task Scheduler
# Uruchom jako Administrator: powershell -ExecutionPolicy Bypass -File scripts\schedule_agents.ps1

$python = (Get-Command python).Source
$botDir = Split-Path -Parent $PSScriptRoot

# Daily agent — 08:00 każdego dnia
$dailyAction = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m footstats.daily_agent" `
    -WorkingDirectory $botDir

$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "08:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "FootStats-DailyAgent" `
    -Action $dailyAction `
    -Trigger $dailyTrigger `
    -Settings $settings `
    -Description "FootStats daily_agent — generowanie predykcji i kuponów" `
    -Force

# Evening agent — 23:00 każdego dnia
$eveningAction = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m footstats.evening_agent" `
    -WorkingDirectory $botDir

$eveningTrigger = New-ScheduledTaskTrigger -Daily -At "23:00"

Register-ScheduledTask `
    -TaskName "FootStats-EveningAgent" `
    -Action $eveningAction `
    -Trigger $eveningTrigger `
    -Settings $settings `
    -Description "FootStats evening_agent — rozliczanie kuponów i alerty" `
    -Force

Write-Host "OK: FootStats-DailyAgent (08:00) i FootStats-EveningAgent (23:00) zarejestrowane." -ForegroundColor Green
Write-Host "Sprawdz: schtasks /query /fo LIST /TN FootStats-DailyAgent" -ForegroundColor Cyan
