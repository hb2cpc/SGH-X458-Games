@echo off
setlocal
cd /d "%~dp0"
rem Run from the source tree without requiring "pip install -e .".
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
"%PYTHON%" -B -m sgh_x458
if errorlevel 1 pause
