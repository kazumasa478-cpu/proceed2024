@echo off
rem ===== First-time setup (Windows) : creates .venv and installs libraries =====
cd /d "%~dp0"
rem Offline package bundles libraries for Python 3.12 / 3.13 only
set PY=
py -3.13 --version >nul 2>nul && set PY=py -3.13
if not defined PY py -3.12 --version >nul 2>nul && set PY=py -3.12
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo [ERROR] Python is not installed. Install Python 3.12 or 3.13 from https://www.python.org/ and check "Add python.exe to PATH".
  pause & exit /b 1
)
echo Using: %PY%
if not exist .venv %PY% -m venv .venv || (pause & exit /b 1)
if exist wheels (
  echo Installing from bundled wheels ^(offline^)...
  .venv\Scripts\python -m pip install --no-index --find-links wheels -r requirements.txt || (pause & exit /b 1)
) else (
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || (pause & exit /b 1)
)
if not exist inbox mkdir inbox
if not exist 名簿.csv copy sample\名簿.csv 名簿.csv >nul
echo.
echo Setup completed. Edit the roster CSV, then double-click make_forms.bat.
pause
