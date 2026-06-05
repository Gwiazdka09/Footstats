# FootStats — rejestracja zadań w Windows Task Scheduler
# Uruchom jako Administrator: powershell -ExecutionPolicy Bypass -File scripts\schedule_agents.ps1

$python = (Get-Command python).Source
$botDir = Split-Path -Parent $PSScriptRoot

# Daily agent DRAFT — 08:00 (analiza + zapis DRAFT do DB)
$dailyDraftAction = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m footstats.daily_agent --faza draft" `
    -WorkingDirectory $botDir

$dailyDraftTrigger = New-ScheduledTaskTrigger -Daily -At "08:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "FootStats-DailyAgentDraft" `
    -Action $dailyDraftAction `
    -Trigger $dailyDraftTrigger `
    -Settings $settings `
    -Description "FootStats daily_agent DRAFT phase - analysis + save to DB at 08:00" `
    -Force

# Daily agent FINAL — 11:00 (LLM Scout veto + promuj DRAFT→ACTIVE)
$dailyFinalAction = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m footstats.daily_agent --faza final" `
    -WorkingDirectory $botDir

$dailyFinalTrigger = New-ScheduledTaskTrigger -Daily -At "11:00"

Register-ScheduledTask `
    -TaskName "FootStats-DailyAgentFinal" `
    -Action $dailyFinalAction `
    -Trigger $dailyFinalTrigger `
    -Settings $settings `
    -Description "FootStats daily_agent FINAL phase - LLM Scout veto + DRAFT to ACTIVE at 11:00" `
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
    -Description "FootStats evening_agent - coupon settlement and alerts at 23:00" `
    -Force

Write-Host "OK: FootStats-DailyAgentDraft (08:00), FootStats-DailyAgentFinal (11:00), FootStats-EveningAgent (23:00) zarejestrowane." -ForegroundColor Green
Write-Host "Sprawdz: schtasks /query /fo LIST /TN FootStats-DailyAgentDraft" -ForegroundColor Cyan
