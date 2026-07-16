@echo off
REM DraggyEncoder launcher (CMD / double-click)
REM Forces UTF-8 console so ffmpeg output never hits 'charmap' codec.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] DraggyEncoder exited with code %errorlevel%.
    pause
)
