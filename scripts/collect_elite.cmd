@echo off
rem Collect elite managers' picks (fplrank.collect.elite_picks) and append the output to a log.
rem Used by Windows Task Scheduler; see docs/collect-schedule.md.
cd /d "%~dp0.."
if not exist data\collected\logs mkdir data\collected\logs
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"
echo ==== %DATE% %TIME% ==== >> data\collected\logs\collect.log
"%UV%" run python -m fplrank.collect.elite_picks collect >> data\collected\logs\collect.log 2>&1
