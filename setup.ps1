# Setup Eye Gaze -> Play/Pausa (Windows 10/11). Esegui con doppio clic su setup.bat oppure:  powershell -ExecutionPolicy Bypass -File setup.ps1
# Nota: file volutamente solo ASCII (compatibile con Windows PowerShell 5.1).
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Fail($msg) { Write-Host ""; Write-Host "ERRORE: $msg" -ForegroundColor Red; Read-Host "Premi Invio per chiudere"; exit 1 }
function Ask($q) { $a = Read-Host "$q [s/N]"; return ($a -match '^(s|si|y|yes)$') }

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
if (-not $py) { Fail "Serve Python 3.10-3.12 (consigliato 3.11 o 3.12; MediaPipe non supporta ancora le versioni piu recenti). Installalo da python.org o con: winget install Python.Python.3.12" }
Write-Host ("Uso: " + ($py -join ' '))

Write-Host "== 2/5  Ambiente virtuale e dipendenze ==" -ForegroundColor Cyan
$pyExe = $py[0]; $pyArgs = @(); if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $pyExe @pyArgs -m venv .venv; if ($LASTEXITCODE -ne 0) { Fail "Creazione dell'ambiente virtuale non riuscita." } }
& .venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Installazione dipendenze non riuscita (controlla la connessione a Internet)." }

Write-Host "== 3/5  Modello di rilevamento del volto ==" -ForegroundColor Cyan
$model = "models\face_landmarker.task"
if (Test-Path $model) { Write-Host "Gia presente." }
else {
    Write-Host "Serve il file 'face_landmarker.task' (circa 4 MB) da storage.googleapis.com (modello ufficiale MediaPipe)."
    Write-Host "Viene scaricato una sola volta; le immagini della webcam restano sempre sul tuo PC."
    if (Ask "Scaricarlo ora?") {
        New-Item -ItemType Directory -Force -Path models | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile $model
        Write-Host ("Scaricato: " + (Get-Item $model).Length + " byte")
    } else { Write-Host "Salto. Senza il modello l'app non puo rilevare lo sguardo." -ForegroundColor Yellow }
}

Write-Host "== 4/5  ADB (per il tablet Android) ==" -ForegroundColor Cyan
$adbLocal = "tools\platform-tools\adb.exe"
if ((Test-Path $adbLocal) -or (Get-Command adb -ErrorAction SilentlyContinue)) { Write-Host "adb gia disponibile." }
else {
    Write-Host "adb non trovato. Servono gli Android platform-tools (circa 8 MB) da dl.google.com."
    if (Ask "Scaricarli in tools\platform-tools?") {
        New-Item -ItemType Directory -Force -Path tools | Out-Null
        $zip = "tools\platform-tools.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath tools -Force
        Remove-Item $zip
        Write-Host "Installato in tools\platform-tools."
    } else { Write-Host "Salto. Puoi usare solo il controllo del video sul PC, oppure indicare adb.exe nelle Impostazioni." -ForegroundColor Yellow }
}

Write-Host "== 5/5  Collegamento sul Desktop ==" -ForegroundColor Cyan
if (Ask "Creare il collegamento 'Eye Gaze' sul Desktop (si avvia senza finestra nera)?") {
    & .venv\Scripts\python.exe -c "from eyegaze.tray import make_icon; make_icon('#3fb950', 256).save('eyegaze.ico', sizes=[(256,256),(64,64),(32,32),(16,16)])"
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Eye Gaze.lnk'))
    $lnk.TargetPath = (Resolve-Path ".venv\Scripts\pythonw.exe").Path
    $lnk.Arguments = '-m eyegaze'
    $lnk.WorkingDirectory = $PSScriptRoot
    if (Test-Path "eyegaze.ico") { $lnk.IconLocation = (Resolve-Path "eyegaze.ico").Path }
    $lnk.Save()
    Write-Host "Collegamento creato sul Desktop."
}

Write-Host ""
Write-Host "Setup completato. Avvia con il collegamento Desktop, con start.vbs o con start.bat (prima prova consigliata: start-dryrun.bat)." -ForegroundColor Green
Read-Host "Premi Invio per chiudere"
