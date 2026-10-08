@echo off
rem ===== First-time setup (Windows) : creates .venv and installs libraries =====
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo [ERROR] Python is not installed. Install Python 3.10+ from https://www.python.org/ and check "Add python.exe to PATH".
  pause & exit /b 1
)
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
