# Build script for Windows (.exe)
# Requirements: PyInstaller, Inno PySide6>=6.7.0

$APP_NAME = "DraggyEncoder"
$VERSION = "1"
$SPEC_FILE = "draggy_encoder.spec"
$ISS_FILE = "installer.iss"

# Find ISCC in PATH or use default
$INNO_SETUP_PATH = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $INNO_SETUP_PATH) {
    $INNO_SETUP_PATH = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
}

# Ensure output dir is relative to repo root
$REPO_ROOT = (Get-Item $PSScriptRoot).Parent.FullName
$EXTERNAL_OUTPUT = Join-Path $REPO_ROOT "DRAGGY_RELEASES"

Write-Host "--- Starting Windows Build (v$VERSION) ---" -ForegroundColor Cyan
Write-Host "Output Directory: $EXTERNAL_OUTPUT" -ForegroundColor Cyan

if (!(Test-Path $EXTERNAL_OUTPUT)) { New-Item -ItemType Directory -Path $EXTERNAL_OUTPUT }

# 1. Skip pip install in script (handled by CI/shell)
Write-Host "1. Checking environment (PyInstaller)..." -ForegroundColor Yellow
if (-not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue) -and -not (python -m PyInstaller --version)) {
    Write-Host "Error: PyInstaller not found. Please run 'pip install pyinstaller' first." -ForegroundColor Red
    exit 1
}

# 2. Run PyInstaller
Write-Host "2. Running PyInstaller via python -m..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
python -m PyInstaller -y --clean $SPEC_FILE

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: PyInstaller failed." -ForegroundColor Red
    exit 1
}

# 3. Run Inno Setup
Write-Host "3. Generating Installer (.exe)..." -ForegroundColor Yellow
if (Test-Path $INNO_SETUP_PATH) {
    & $INNO_SETUP_PATH /O"$EXTERNAL_OUTPUT" $ISS_FILE
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Inno Setup failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "--- Build Complete! Check $EXTERNAL_OUTPUT ---" -ForegroundColor Green
} else {
    Write-Host "Warning: Inno Setup (ISCC.exe) not found at $INNO_SETUP_PATH" -ForegroundColor Magenta
    Write-Host "Binary bundle available in dist/$APP_NAME" -ForegroundColor Cyan
}
