# run_draggy.ps1 — PowerShell launcher for DraggyEncoder
# Double-click in Explorer or run from console: powershell -File .\run_draggy.ps1
$ErrorActionPreference = "Stop"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    # 1. Project virtual environments
    $candidates = @(
        "venv\Scripts\python.exe",
        ".venv\Scripts\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return (Resolve-Path $c).Path }
    }

    # 2. Commands on PATH
    $commands = @("py", "python", "python3")
    foreach ($cmd in $commands) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $cmd }
    }

    # 3. Common per-user install locations
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path $p) { return (Resolve-Path $p).Path }
    }

    return $null
}

$PYTHON_EXE = Find-Python

if (-not $PYTHON_EXE) {
    Write-Host "[ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/"
    Write-Host "and run: pip install -r requirements.txt"
    Read-Host "Press Enter to exit"
    exit 1
}

& $PYTHON_EXE launch.py

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] DraggyEncoder exited with code $exitCode."
    Write-Host "Make sure Python and the dependencies in requirements.txt are installed."
    Read-Host "Press Enter to exit"
}

exit $exitCode
