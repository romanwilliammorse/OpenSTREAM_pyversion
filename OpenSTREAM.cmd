@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo The OpenSTREAM Python environment is missing. See README.md.
    pause
    exit /b 1
)
start "OpenSTREAM" ".venv\Scripts\pythonw.exe" -m idlelib -r "tools\interactive_console.py"
