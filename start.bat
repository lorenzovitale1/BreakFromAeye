@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Ambiente non trovato: esegui prima setup.bat
  pause
  exit /b 1
)
rem Avvio senza finestra di comando; se resta nascosto cerca l icona nell area di notifica (freccia ^ vicino all orologio)
start "" ".venv\Scripts\pythonw.exe" -m eyegaze %*
