@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Environment not found: run setup.bat first. / Ambiente non trovato: esegui prima setup.bat
  pause
  exit /b 1
)
rem Starts without a console window; if hidden, look for the icon in the notification area (^ near the clock) / cerca l icona nell area di notifica
start "" ".venv\Scripts\pythonw.exe" -m eyegaze %*
