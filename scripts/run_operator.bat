@echo off
setlocal enabledelayedexpansion
cd /d F:\bot

echo [%date% %time%] === Operator Agent START === >> F:\bot\data\logs\operator_agent.log
python -m footstats.operator_agent --faza full >> F:\bot\data\logs\operator_agent.log 2>&1
set EXITCODE=%errorlevel%
echo [%date% %time%] === Operator Agent END exit=%EXITCODE% === >> F:\bot\data\logs\operator_agent.log
exit /b %EXITCODE%
