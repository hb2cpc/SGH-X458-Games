@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -B "%~dp0launcher.py"
) else (
    python -B "%~dp0launcher.py"
)
if errorlevel 1 pause
