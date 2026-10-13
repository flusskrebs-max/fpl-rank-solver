@echo off
rem Double-click launcher for the solver page: gets the latest code, then opens `fplrank page` in the browser.
rem Steps 1 and 4 of docs/weekly-run.md in one go; a desktop shortcut to this file is set up as shown there.
title fplrank page
cd /d "%~dp0.."
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"

rem Only update when on main, so a branch checked out to try a PR is left alone.
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
if /i "%BRANCH%"=="main" (
    echo Getting the latest code from GitHub...
    git pull --ff-only
    if errorlevel 1 (
        echo.
        echo Could not update the code ^(see the message above^). Opening the page with the code you have.
        echo Ask Claude in the project if this keeps happening.
        echo.
        pause
    )
) else (
    echo On branch "%BRANCH%", not main: skipping the update.
)

echo Installing any new packages...
"%UV%" sync --group dev
if errorlevel 1 (
    echo.
    echo uv sync failed ^(see the message above^).
    pause
    exit /b 1
)

echo.
echo Opening the page at http://localhost:8501. Close this window to stop it.
echo.
"%UV%" run fplrank page
if errorlevel 1 pause
