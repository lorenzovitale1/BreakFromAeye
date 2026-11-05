# BreakFromAeye 👁

> *A break from AI + eye.* Distogli lo sguardo dal PC e il tuo video parte.

[![tests](https://github.com/lorenzovitale1/VideoDistractionAI/actions/workflows/tests.yml/badge.svg)](https://github.com/lorenzovitale1/VideoDistractionAI/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)

Guardi un video sul **tablet** mentre lavori al **PC**? Questo programma usa **solo la webcam del PC** per capire se stai guardando lo schermo
e mette in play/pausa il video di conseguenza. Niente eye tracker, niente cloud: tutto gira in locale.

| Uscita | Guardi altrove (≥ 1,5 s) | Torni a guardare il PC (≥ 0,8 s) |
|---|---|---|
| 📱 **Tablet Android** (ADB via Wi-Fi) | **PLAY** | **PAUSA** |
| 🖥 **Video sul PC** (YouTube ecc. nel browser) | **PAUSA** | **PLAY** |

Tempi e azioni si cambiano dall'interfaccia. Tablet e PC si possono usare **separatamente o insieme**.
*English summary: [README.en.md](README.en.md).*

## Funzioni
- **Scelta rapida tablet / PC / entrambi** nella schermata principale (e dal menu dell'icona).
- **Aree sicure**: zone dove guardare *non* conta come "guardi altrove" (es. la tastiera). Le definisci guardando i 4 angoli
  (con bip di inizio/fine, perché fuori dallo schermo non si vedono i punti), disegnandole sulla mappa o scrivendo le coordinate.
- **Più monitor**: valuta lo sguardo su tutti gli schermi o su uno solo, con una calibrazione salvata per ciascuna scelta.
- **Resta in background**: chiudendo la finestra il programma va nell'area di notifica (freccia ^ vicino all'orologio), senza finestre nere.
  Modificabile in *Impostazioni → Interfaccia*.
- Calibrazione a 9 punti, anti-falsi-positivi (ammiccamenti, occhiate rapide), un solo comando per ogni transizione, modalità *dry-run*.
- Webcam scollegata/bloccata/coperta → stato "incerto" e **nessun comando**. Nessun fotogramma viene salvato o inviato in rete.

## Installazione (Windows 10/11)

Servono: Windows 10/11, una webcam, **Python 3.10–3.12** ([python.org](https://www.python.org/downloads/) o `winget install Python.Python.3.12`).

**A) Più semplice — scarica lo ZIP**
1. Sulla pagina del repository: **Code → Download ZIP**, estrai la cartella dove vuoi.
2. Doppio clic su **`setup.bat`** e rispondi alle domande (modello di rilevamento ~4 MB, `adb` ~8 MB solo se usi il tablet, collegamento sul Desktop).
3. Avvia dal collegamento **BreakFromAeye** sul Desktop (oppure `start.vbs`).

**B) Con git**
```bash
git clone https://github.com/lorenzovitale1/VideoDistractionAI.git
cd VideoDistractionAI
setup.bat
```

**C) Con pip / pipx** (i dati personali finiscono in `%APPDATA%\BreakFromAeye`)
```bash
pipx install git+https://github.com/lorenzovitale1/VideoDistractionAI.git
breakfromaeye --setup      # scarica modello e adb, chiedendo conferma
breakfromaeye-gui          # avvia senza finestra di comando
```
Tutti i download sono facoltativi e chiesti prima; il modello è verificato con SHA-256.

## Primo avvio
1. Il programma propone la **calibrazione** (~30 s): segui con lo sguardo i 9 punti.
2. Nella scheda **Stato** guarda la *mappa dello sguardo*: il rettangolo blu è lo schermo. Se scatta guardando i bordi, alza *Margine schermo*.
3. Prova prima con `start-dryrun.bat` (mostra i comandi senza inviarli: compare il badge **DRY-RUN**), poi avvia normalmente.
4. Nei primi secondi si "stabilizza": non invia nulla e adotta lo stato corrente.

## Tablet Android (ADB via Wi-Fi)
Sul tablet (Android 11+): *Impostazioni → Opzioni sviluppatore → **Debug wireless***, con tablet e PC sulla **stessa rete fidata**.
1. Tocca **la scritta** "Debug wireless" (non l'interruttore) per aprire la pagina con *Abbina dispositivo con codice di associazione* e *Indirizzo IP e porta*.
2. Nell'app: **Abbina…** → IP:porta di *abbinamento* + codice a 6 cifre. Poi **Connetti IP…** → IP:porta della pagina principale (la porta è diversa).
3. **Aggiorna**, scegli il tablet nella lista, poi **Test PLAY / Test PAUSA** con un video già aperto sul tablet.

Comandi distinti e idempotenti (`keyevent 126` = PLAY, `127` = PAUSA), non un toggle. Alcune app **ignorano** i tasti multimediali: in quel caso
imposta *Metodo* su `toggle_if_needed` (legge lo stato del player con `dumpsys media_session`). Non vengono aggirati DRM o protezioni.
Android < 11: collegamento USB iniziale e `adb tcpip 5555`. Se i dispositivi sono più d'uno devi sceglierlo: non si invia mai a uno non selezionato.
Non abilitare il debug wireless su reti non fidate; i codici di abbinamento non vengono registrati.

## Video sul PC (YouTube, anche sul secondo schermo)
Scegli **🖥 Video sul PC** (o *Entrambi*) in alto nella scheda Stato. Usa i controlli multimediali di Windows con Play/Pausa **espliciti** (non il tasto toggle):
funziona con i video nel browser (Chrome/Edge/Firefox) già avviati. Con più player attivi imposta *Filtro applicazione* (`chrome`, `msedge`…).
Con il video sul secondo schermo calibra *tutti i monitor* oppure solo quello.

## Aree sicure
Scheda **Aree sicure** → *Guarda i 4 angoli…*: segui le istruzioni a schermo e i bip (acuto = inizia a guardare l'angolo, due bassi = finito),
nell'ordine alto-sx, alto-dx, basso-dx, basso-sx. Oppure *Disegna sulla mappa* / *Modifica…* per i valori numerici (0–1 = schermo, >1 = sotto/destra).
Le aree sono salvate per ciascuna area monitorata; dopo una nuova calibrazione conviene registrarle di nuovo.

## Impostazioni principali (`config.json`, creato al primo salvataggio)
| Chiave | Predef. | Significato |
|---|---|---|
| `timing.away_seconds` / `return_seconds` | 1.5 / 0.8 | secondi "altrove" / "sul PC" prima dell'azione |
| `timing.glitch_tolerance_seconds` | 0.25 | disturbi più brevi non interrompono il conteggio |
| `timing.cooldown_seconds` | 1.0 | pausa minima tra due comandi |
| `detection.no_face_is_away` | true | volto assente (webcam ok) = "altrove" |
| `detection.screen_margin` / `hysteresis` / `smoothing` | 0.12 / 0.06 / 0.45 | tolleranza ai bordi, isteresi, filtro |
| `outputs.tablet.*`, `outputs.pc_media.*` | — | attivazione, azioni, dispositivo, metodo |
| `calibration.monitor` | `all` | `all` o indice del monitor |
| `ui.close_action` | `tray` | `tray` = nascondi nell'area di notifica, `quit` = chiudi |

Tutte le opzioni (con descrizioni) sono nella scheda **Impostazioni**. `python -m eyegaze --help` elenca le opzioni da terminale
(`--dry-run`, `--minimized`, `--headless`, `--simulate`, `--list-devices`, `--check-camera`, `--setup`).

## Come funziona
Webcam → MediaPipe Face Landmarker (478 punti con iridi, posa della testa) → feature (yaw, pitch, posizione delle iridi) → regressione appresa
dalla calibrazione → punto stimato rispetto allo schermo → "sul PC" se dentro lo schermo + margine (o in un'area sicura), con isteresi →
macchina a stati con durate minime → un comando per transizione. Elaborazione locale; l'anteprima di debug è disattivata di default.

## Limiti
- Precisione **molto inferiore a un eye tracker dedicato**: distingue "sul monitor" da "altrove", non il punto esatto.
- La calibrazione vale per postura/posizione simili; ricalibra se cambi postazione o luce. Occhiali scuri e controluce peggiorano i risultati.
- Alcuni player Android ignorano i tasti multimediali. Il progetto è un esperimento/strumento personale, **non** un dispositivo di sicurezza.

## Risoluzione problemi
| Problema | Cosa fare |
|---|---|
| Non succede niente (compare **DRY-RUN**) | disattiva *Prova a vuoto* o avvia senza `--dry-run` |
| "Modello mancante" | riapri l'app e accetta il download, o `breakfromaeye --setup` |
| Tablet "Scollegato" | stessa rete Wi-Fi; riabbina; il Debug wireless si può spegnere al cambio rete |
| Scatta guardando i bordi / non scatta altrove | regola *Margine schermo*; ricalibra; controlla la mappa |
| "Webcam non disponibile" | chiudi le app che la usano; prova un altro *Indice webcam*; `--check-camera` |
| YouTube non reagisce | avvia il video nel browser; *Filtro applicazione*; Test PLAY/PAUSA |
| La finestra non c'è più | è nell'area di notifica (freccia ^): clic sull'icona. Rilanciare il programma la riapre |
| Errori all'avvio | `start-debug.bat` (con console) e il file `eyegaze.log` |

## Sviluppo
```bash
pip install -e ".[dev]"
python -m pytest -q          # test senza webcam né tablet (ADB e webcam simulati)
python -m eyegaze --simulate # scenario finto in dry-run
```
Struttura: `eyegaze/` (codice: `statemachine`, `features`, `calibration`, `capture`, `adb`, `outputs`, `engine`, `gui`, …), `tests/`.

## Privacy
Le immagini della webcam sono elaborate in locale e non vengono salvate né inviate. Gli unici accessi in rete sono i download facoltativi
(modello MediaPipe da `storage.googleapis.com`, platform-tools da `dl.google.com`). La calibrazione (`calibration_*.json`) resta sul tuo PC ed è esclusa da git.

## Licenza e riconoscimenti
[MIT](LICENSE). Usa [MediaPipe](https://github.com/google-ai-edge/mediapipe) (Apache-2.0, modello scaricato a parte), OpenCV, NumPy, pystray, Pillow e
Android platform-tools (scaricati da Google, con la loro licenza).
