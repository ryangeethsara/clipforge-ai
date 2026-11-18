@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call install.bat
  if errorlevel 1 exit /b 1
)
start "" /B cmd /C "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8765"
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
