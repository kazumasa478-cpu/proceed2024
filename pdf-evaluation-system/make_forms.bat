@echo off
rem ===== Create printable questionnaires (with QR code) from the roster CSV =====
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  pause & exit /b 1
)
.venv\Scripts\python -m pdfeval forms %*
if not errorlevel 1 start "" "%~dp0調査票"
pause
