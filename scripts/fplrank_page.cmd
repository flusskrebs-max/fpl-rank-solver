@echo off
rem Double-click launcher for the solver page: gets the latest code, then opens `fplrank page` in the browser.
rem Steps 1 and 4 of docs/weekly-run.md in one go; a desktop shortcut to this file is set up as shown there.
title fplrank page
cd /d "%~dp0.."
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"

rem Back to main if another branch is checked out (unless it has uncommitted edits), then update.
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
if /i not "%BRANCH%"=="main" (
    set "DIRTY="
    for /f "delims=" %%s in ('git status --porcelain --untracked-files^=no') do set "DIRTY=1"
    if not defined DIRTY (
        echo Switching from branch "%BRANCH%" to main...
        git switch main && set "BRANCH=main"
    )
)
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
    echo On branch "%BRANCH%" with uncommitted changes: skipping the update.
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
