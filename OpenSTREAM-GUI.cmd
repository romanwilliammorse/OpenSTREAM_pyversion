@echo off
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m openstream.gui_launcher --output-root "%~dp0outputs\gui"
