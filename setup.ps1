# BreakFromAeye setup (Windows 10/11) / Installazione. Double-click setup.bat or / Doppio clic su setup.bat oppure:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
# Note: ASCII-only on purpose (compatible with Windows PowerShell 5.1) / file volutamente solo ASCII.
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

# Messages follow the Windows display language: Italian, otherwise English.
$IT = ((Get-UICulture).TwoLetterISOLanguageName -eq 'it')
function T($it, $en) { if ($IT) { return $it } else { return $en } }
function Fail($msg) { Write-Host ""; Write-Host ((T "ERRORE: " "ERROR: ") + $msg) -ForegroundColor Red; Read-Host (T "Premi Invio per chiudere" "Press Enter to close"); exit 1 }
function Ask($q) { $a = Read-Host ($q + (T " [s/N]" " [y/N]")); return ($a -match '^(s|si|y|yes)$') }

Write-Host "== 1/5  Python ==" -ForegroundColor Cyan
$py = $null
foreach ($v in '3.12', '3.11', '3.10') {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py = @('py', "-$v"); break } } catch {}
}
if (-not $py) {
    try {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -in '3.10', '3.11', '3.12') { $py = @('python') }
    } catch {}
}
if (-not $py) { Fail (T "Serve Python 3.10-3.12 (consigliato 3.11 o 3.12; MediaPipe non supporta ancora le versioni piu recenti). Installalo da python.org o con: winget install Python.Python.3.12" "Python 3.10-3.12 is required (3.11 or 3.12 recommended; MediaPipe does not support newer versions yet). Install it from python.org or with: winget install Python.Python.3.12") }
Write-Host ((T "Uso: " "Using: ") + ($py -join ' '))

Write-Host ("== 2/5  " + (T "Ambiente virtuale e dipendenze" "Virtual environment and dependencies") + " ==") -ForegroundColor Cyan
$pyExe = $py[0]; $pyArgs = @(); if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $pyExe @pyArgs -m venv .venv; if ($LASTEXITCODE -ne 0) { Fail (T "Creazione dell'ambiente virtuale non riuscita." "Could not create the virtual environment.") } }
& .venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail (T "Installazione dipendenze non riuscita (controlla la connessione a Internet)." "Dependency installation failed (check your Internet connection).") }

Write-Host ("== 3/5  " + (T "Modello di rilevamento del volto" "Face detection model") + " ==") -ForegroundColor Cyan
$model = "models\face_landmarker.task"
$modelSha = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
if (Test-Path $model) { Write-Host (T "Gia presente." "Already present.") }
else {
    Write-Host (T "Serve il file 'face_landmarker.task' (circa 4 MB) da storage.googleapis.com (modello ufficiale MediaPipe)." "The file 'face_landmarker.task' (about 4 MB) is required, from storage.googleapis.com (official MediaPipe model).")
    Write-Host (T "Viene scaricato una sola volta; le immagini della webcam restano sempre sul tuo PC." "It is downloaded only once; webcam images always stay on your PC.")
    if (Ask (T "Scaricarlo ora?" "Download it now?")) {
        New-Item -ItemType Directory -Force -Path models | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile $model
        if ((Get-FileHash $model -Algorithm SHA256).Hash.ToLower() -ne $modelSha) { Remove-Item $model; Fail (T "File scaricato non valido (impronta SHA-256 diversa)." "Downloaded file is not valid (different SHA-256 hash).") }
        Write-Host ((T "Scaricato e verificato: " "Downloaded and verified: ") + (Get-Item $model).Length + " bytes")
    } else { Write-Host (T "Salto. Senza il modello l'app non puo rilevare lo sguardo." "Skipped. Without the model the app cannot detect your gaze.") -ForegroundColor Yellow }
}

Write-Host ("== 4/5  ADB (" + (T "per il tablet Android" "for the Android tablet") + ") ==") -ForegroundColor Cyan
$adbLocal = "tools\platform-tools\adb.exe"
if ((Test-Path $adbLocal) -or (Get-Command adb -ErrorAction SilentlyContinue)) { Write-Host (T "adb gia disponibile." "adb already available.") }
else {
    Write-Host (T "adb non trovato. Servono gli Android platform-tools (circa 8 MB) da dl.google.com." "adb not found. The Android platform-tools (about 8 MB) from dl.google.com are required.")
    if (Ask (T "Scaricarli in tools\platform-tools?" "Download them into tools\platform-tools?")) {
        New-Item -ItemType Directory -Force -Path tools | Out-Null
        $zip = "tools\platform-tools.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath tools -Force
        Remove-Item $zip
        Write-Host (T "Installato in tools\platform-tools." "Installed in tools\platform-tools.")
    } else { Write-Host (T "Salto. Puoi usare solo il controllo del video sul PC, oppure indicare adb.exe nelle Impostazioni." "Skipped. You can only control the video on the PC, or set adb.exe in Settings.") -ForegroundColor Yellow }
}

Write-Host ("== 5/5  " + (T "Collegamento sul Desktop" "Desktop shortcut") + " ==") -ForegroundColor Cyan
if (Ask (T "Creare il collegamento 'BreakFromAeye' sul Desktop (si avvia senza finestra nera)?" "Create a 'BreakFromAeye' shortcut on the Desktop (starts without a black console window)?")) {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'BreakFromAeye.lnk'))
    $lnk.TargetPath = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
    $lnk.Arguments = '-m eyegaze'
    $lnk.WorkingDirectory = $PSScriptRoot
    if (Test-Path "assets\icon.ico") { $lnk.IconLocation = (Resolve-Path "assets\icon.ico").Path }
    $lnk.Save()
    Write-Host (T "Collegamento creato sul Desktop." "Shortcut created on the Desktop.")
}

Write-Host ""
Write-Host (T "Setup completato. Avvia con il collegamento Desktop, con start.vbs o con start.bat (prima prova consigliata: start-dryrun.bat)." "Setup complete. Start it from the Desktop shortcut, start.vbs or start.bat (first try with start-dryrun.bat is recommended).") -ForegroundColor Green
Read-Host (T "Premi Invio per chiudere" "Press Enter to close")
