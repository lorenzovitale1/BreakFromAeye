@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente non trovato: esegui prima setup.bat
  pause
  exit /b 1
)
rem Con finestra di comando visibile: utile per vedere errori e messaggi
".venv\Scripts\python.exe" -m eyegaze %*
if errorlevel 1 pause
