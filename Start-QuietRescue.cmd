@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run the setup commands in README.md first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -I -B "%~dp0launch.py"
