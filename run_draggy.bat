@echo off
REM DraggyEncoder launcher (CMD / double-click)
REM Forces UTF-8 console so ffmpeg output never hits 'charmap' codec.
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%~dp0"

REM ── Locate a suitable Python interpreter (no WSL, no bash) ─────────────
set "PYTHON_EXE="

REM 1. Project virtual environments
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    goto :found
)
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :found
)

REM 2. Windows Python launcher (py.exe) - works when Python is from the Store
where py >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_EXE=py -3"
    goto :found
)

REM 3. Plain python/python3 on PATH
where python >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_EXE=python"
    goto :found
)
where python3 >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_EXE=python3"
    goto :found
)

REM 4. Common per-user install locations (Python.org / Windows Store)
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set "PYTHON_EXE=%%P"
        goto :found
    )
)

echo.
echo [ERROR] Python 3 was not found in PATH.
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo and run: pip install -r requirements.txt
pause
exit /b 1

:found
"%PYTHON_EXE%" launch.py

:check_exit
if errorlevel 1 (
    echo.
    echo [ERROR] DraggyEncoder exited with code %errorlevel%.
    echo Make sure Python and the dependencies in requirements.txt are installed.
    pause
)
