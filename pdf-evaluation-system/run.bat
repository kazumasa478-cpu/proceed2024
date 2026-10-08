@echo off
rem ===== Run: inbox\*.pdf -> output\<name>\ + output\summary Excel =====
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  pause & exit /b 1
)
.venv\Scripts\python -m pdfeval %*
if errorlevel 1 echo [WARN] Some files failed. See logs\pdfeval.log
start "" "%~dp0output"
pause
