@echo off
title Biretos Orchestrator Cron
echo Starting Orchestrator Cron (every 10 min)...
echo Press Ctrl+C to stop.
echo.
cd /d D:\BIRETOS\projects\biretos-automation
python orchestrator/cron_runner.py --interval 600
pause
