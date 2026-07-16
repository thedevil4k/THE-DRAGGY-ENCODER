# run_draggy.ps1  —  PowerShell launcher
# Double-click in Explorer or run from console:  powershell -File .\run_draggy.ps1
$ErrorActionPreference = "Stop"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Set-Location -LiteralPath $PSScriptRoot

try {
    python main.py
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "[ERROR] DraggyEncoder failed to launch:"
    Write-Host $_.Exception.Message
    Read-Host "Press Enter to exit"
    exit 1
}
