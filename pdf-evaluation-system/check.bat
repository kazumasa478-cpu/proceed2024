@echo off
rem ===== Show people whose answers still need checking (要確認) =====
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  pause & exit /b 1
)
.venv\Scripts\python -m pdfeval todo
echo.
echo Fix the yellow rows in each 回答確認.xlsx, set 状態 to 確認済, then run run.bat again.
pause
