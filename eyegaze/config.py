"""Configurazione: valori predefiniti, metadati (usati dalla GUI e dal README), caricamento/salvataggio."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parent.parent
# Modalità "portatile": eseguito dalla cartella del progetto (git clone / ZIP / pip install -e): dati accanto al codice.
# Modalità "installata" (pip install): dati personali in %APPDATA%\BreakFromAeye, mai dentro site-packages.
PORTABLE = (PKG_ROOT / "setup.ps1").exists() or (PKG_ROOT / ".git").exists()
ROOT = PKG_ROOT if PORTABLE else Path(os.environ.get("APPDATA") or Path.home()) / "BreakFromAeye"
if not PORTABLE:
    ROOT.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = ROOT / "config.json"
CALIBRATION_PATH = ROOT / "calibration.json"      # file unico delle versioni precedenti (solo lettura, compatibilita)


def calibration_key(setting) -> str:
    """'all', 'primary' o indice monitor -> chiave normalizzata ('primary' equivale al monitor 0)."""
    s = str(setting).strip().lower()
    if s == "primary":
        return "0"
    return s if s == "all" or s.isdigit() else "all"


def calibration_path(setting) -> Path:
    """Una calibrazione per ogni area (tutti i monitor / singolo monitor): si puo cambiare area senza ricalibrare."""
    return ROOT / f"calibration_{calibration_key(setting)}.json"
MODEL_PATH = ROOT / "models" / "face_landmarker.task"

DEFAULTS: dict[str, Any] = {
    "timing": {
        "away_seconds": 1.5,
        "return_seconds": 0.8,
        "glitch_tolerance_seconds": 0.25,
        "cooldown_seconds": 1.0,
        "startup_warmup_seconds": 3.0,
        "uncertain_timeout_seconds": 2.0,
    },
    "detection": {
        "no_face_is_away": True,
        "screen_margin": 0.12,
        "hysteresis": 0.06,
        "smoothing": 0.45,
        "blink_threshold": 0.5,
    },
    "camera": {
        "index": 0,
        "width": 640,
        "height": 480,
        "processing_fps": 15,
    },
    "calibration": {
        "monitor": "all",
        "settle_seconds": 1.0,
        "sample_seconds": 1.2,
    },
    "outputs": {
        "tablet": {
            "enabled": True,
            "on_away": "play",
            "on_return": "pause",
            "serial": "",
            "adb_path": "",
            "method": "keyevent",
        },
        "pc_media": {
            "enabled": False,
            "on_away": "pause",
            "on_return": "play",
            "app_filter": "",
            "fallback_media_key": False,
        },
    },
    "dry_run": False,
    "show_preview": False,
    "ui": {
        "close_action": "tray",
        "start_minimized": False,
    },
    "safe_zones": {},
}

# Metadati: (percorso, sezione, etichetta, descrizione, tipo, extra)
# tipo: float|int|bool|choice|str   extra: dict(min,max,step) oppure choices
SETTINGS: list[dict[str, Any]] = [
    # --- Tempi
    dict(path="timing.away_seconds", section="Tempi", label="Distolgo lo sguardo per",
         help="Secondi consecutivi lontano dallo schermo prima di eseguire l'azione «sguardo altrove».",
         type="float", min=0.3, max=6.0, step=0.1, unit="s"),
    dict(path="timing.return_seconds", section="Tempi", label="Torno a guardare per",
         help="Secondi consecutivi sullo schermo prima di eseguire l'azione «sguardo di ritorno».",
         type="float", min=0.2, max=4.0, step=0.1, unit="s"),
    dict(path="timing.glitch_tolerance_seconds", section="Tempi", label="Tolleranza ai disturbi",
         help="Frame «contrari» più brevi di questo valore (ciglia, rumore) non interrompono il conteggio.",
         type="float", min=0.0, max=1.0, step=0.05, unit="s"),
    dict(path="timing.cooldown_seconds", section="Tempi", label="Pausa tra comandi",
         help="Intervallo minimo tra due comandi consecutivi.",
         type="float", min=0.0, max=10.0, step=0.5, unit="s"),
    dict(path="timing.startup_warmup_seconds", section="Tempi", label="Stabilizzazione all'avvio",
         help="All'avvio osserva senza inviare nulla; poi adotta lo stato corrente senza comandi.",
         type="float", min=1.0, max=15.0, step=0.5, unit="s"),
    dict(path="timing.uncertain_timeout_seconds", section="Tempi", label="Timeout dati assenti",
         help="Dopo tanti secondi senza dati utili (occhi chiusi…) lo stato diventa «incerto».",
         type="float", min=0.5, max=10.0, step=0.5, unit="s"),
    # --- Rilevamento
    dict(path="detection.no_face_is_away", section="Rilevamento", label="Volto assente = sguardo altrove",
         help="Se la webcam funziona ma non vede il volto, conta come «guardi altrove». Se la webcam è guasta non succede mai.",
         type="bool"),
    dict(path="detection.screen_margin", section="Rilevamento", label="Margine schermo",
         help="Quanto fuori dai bordi dello schermo (frazione della sua dimensione) è ancora «guardi il PC». Alza se scatta guardando i bordi.",
         type="float", min=0.0, max=0.6, step=0.01),
    dict(path="detection.hysteresis", section="Rilevamento", label="Isteresi",
         help="Per uscire dalla zona serve superare il margine + isteresi; per rientrare, scendere sotto margine − isteresi.",
         type="float", min=0.0, max=0.3, step=0.01),
    dict(path="detection.smoothing", section="Rilevamento", label="Fluidità (smoothing)",
         help="0 = nessun filtro, valori alti = punto sguardo più stabile ma più lento.",
         type="float", min=0.0, max=0.9, step=0.05),
    dict(path="detection.blink_threshold", section="Rilevamento", label="Soglia ammiccamento",
         help="Punteggio sopra cui l'occhio è considerato chiuso (frame ignorato).",
         type="float", min=0.2, max=0.9, step=0.05),
    # --- Webcam
    dict(path="camera.index", section="Webcam", label="Indice webcam",
         help="0 = prima webcam. Cambia se hai più camere.", type="int", min=0, max=9, step=1),
    dict(path="camera.width", section="Webcam", label="Larghezza", help="Risoluzione di acquisizione (più bassa = più leggero).",
         type="choice", choices=[320, 640, 960, 1280]),
    dict(path="camera.height", section="Webcam", label="Altezza", help="Deve corrispondere alla larghezza (4:3 o 16:9).",
         type="choice", choices=[240, 360, 480, 540, 720]),
    dict(path="camera.processing_fps", section="Webcam", label="FPS di elaborazione",
         help="Frame analizzati al secondo. Riduci su PC lenti.", type="int", min=5, max=30, step=1),
    # --- Calibrazione
    dict(path="calibration.monitor", section="Calibrazione", label="Area da calibrare",
         help="Su quali monitor valutare lo sguardo: tutti, oppure uno solo. Ogni area ha la sua calibrazione salvata.",
         type="str", widget="monitor"),
    dict(path="calibration.settle_seconds", section="Calibrazione", label="Tempo di assestamento",
         help="Secondi per raggiungere ogni punto prima di campionare.", type="float", min=0.5, max=3.0, step=0.1, unit="s"),
    dict(path="calibration.sample_seconds", section="Calibrazione", label="Durata campionamento",
         help="Secondi di campionamento per punto.", type="float", min=0.5, max=3.0, step=0.1, unit="s"),
    # --- Tablet
    dict(path="outputs.tablet.enabled", section="Tablet Android", label="Controlla il tablet", help="Abilita l'uscita ADB.", type="bool"),
    dict(path="outputs.tablet.on_away", section="Tablet Android", label="Quando guardo altrove", help="Azione inviata al tablet.",
         type="choice", choices=["play", "pause", "none"]),
    dict(path="outputs.tablet.on_return", section="Tablet Android", label="Quando torno al PC",
         help="Azione inviata al tablet (metti «none» per disattivare la pausa al ritorno).", type="choice", choices=["pause", "play", "none"]),
    dict(path="outputs.tablet.serial", section="Tablet Android", label="Seriale ADB",
         help="Vuoto = scelta dalla lista nella schermata Stato (obbligatoria se i dispositivi sono più di uno).", type="str"),
    dict(path="outputs.tablet.adb_path", section="Tablet Android", label="Percorso adb.exe",
         help="Vuoto = automatico (tools/platform-tools, PATH, cartelle standard).", type="str"),
    dict(path="outputs.tablet.method", section="Tablet Android", label="Metodo",
         help="keyevent = tasti MEDIA_PLAY(126)/MEDIA_PAUSE(127). toggle_if_needed = legge lo stato del player e invia PLAY/PAUSA(85) solo se serve.",
         type="choice", choices=["keyevent", "toggle_if_needed"]),
    # --- PC
    dict(path="outputs.pc_media.enabled", section="Video sul PC (YouTube…)", label="Controlla il video sul PC",
         help="Controlla il player del browser (YouTube, ecc.) tramite i controlli multimediali di Windows.", type="bool"),
    dict(path="outputs.pc_media.on_away", section="Video sul PC (YouTube…)", label="Quando guardo altrove",
         help="Di solito PAUSA: il video sul PC si ferma se non lo guardi.", type="choice", choices=["pause", "play", "none"]),
    dict(path="outputs.pc_media.on_return", section="Video sul PC (YouTube…)", label="Quando torno al PC",
         help="Di solito PLAY.", type="choice", choices=["play", "pause", "none"]),
    dict(path="outputs.pc_media.app_filter", section="Video sul PC (YouTube…)", label="Filtro applicazione",
         help="Parte del nome dell'app (es. chrome, msedge, firefox). Vuoto = sessione multimediale corrente di Windows.", type="str"),
    dict(path="outputs.pc_media.fallback_media_key", section="Video sul PC (YouTube…)", label="Tasto multimediale di riserva",
         help="Se non c'è una sessione multimediale, simula il tasto Play/Pausa (è un toggle: può invertire lo stato).", type="bool"),
    # --- Interfaccia
    dict(path="ui.close_action", section="Interfaccia", label="Cliccando Chiudi (X)",
         help="«Nascondi» lascia il programma attivo nell'area di notifica (freccia ^ vicino all'orologio); «Chiudi» lo termina.",
         type="choice", choices=["tray", "quit"],
         labels={"tray": "Nascondi nell'area di notifica", "quit": "Chiudi il programma"}),
    dict(path="ui.start_minimized", section="Interfaccia", label="Avvia nascosto",
         help="All'avvio parte direttamente nell'area di notifica, senza aprire la finestra.", type="bool"),
    # --- Generale
    dict(path="dry_run", section="Generale", label="Prova a vuoto (dry-run)",
         help="Mostra i comandi previsti senza inviarli a tablet o PC.", type="bool"),
    dict(path="show_preview", section="Generale", label="Anteprima webcam di debug",
         help="Mostra una piccola anteprima nella finestra (disattivata di default).", type="bool"),
]


def get_path(cfg: dict, path: str) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        cur = cur[part]
    return cur


def set_path(cfg: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def clean_zones(zones: Any) -> dict:
    """Aree sicure per area calibrata: {chiave_area: [{name, enabled, x0, y0, x1, y1}]}. Scarta le voci non valide."""
    out: dict[str, list] = {}
    if not isinstance(zones, dict):
        return out
    for key, lst in zones.items():
        if not isinstance(lst, list):
            continue
        clean = []
        for z in lst:
            try:
                x0, x1 = sorted((float(z["x0"]), float(z["x1"])))
                y0, y1 = sorted((float(z["y0"]), float(z["y1"])))
                clean.append({"name": str(z.get("name", "Area sicura"))[:40], "enabled": bool(z.get("enabled", True)),
                              "x0": x0, "y0": y0, "x1": x1, "y1": y1})
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        out[str(key)] = clean
    return out


def validate(cfg: dict) -> dict:
    """Riporta ogni valore al tipo/intervallo ammesso; i valori non validi tornano al predefinito."""
    out = copy.deepcopy(cfg)
    for s in SETTINGS:
        p, t = s["path"], s["type"]
        default = get_path(DEFAULTS, p)
        try:
            v = get_path(out, p)
        except KeyError:
            v = default
        try:
            if t == "float":
                v = min(max(float(v), s["min"]), s["max"])
            elif t == "int":
                v = int(min(max(int(v), s["min"]), s["max"]))
            elif t == "bool":
                if not isinstance(v, bool):
                    raise ValueError
            elif t == "choice":
                v = type(s["choices"][0])(v)
                if v not in s["choices"]:
                    raise ValueError
            else:
                v = "" if v is None else str(v)
        except (TypeError, ValueError):
            v = default
        set_path(out, p, v)
    out["safe_zones"] = clean_zones(out.get("safe_zones", {}))
    return out


def load(path: Path = CONFIG_PATH) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            cfg = _merge(DEFAULTS, raw)
            if isinstance(raw, dict):
                cfg["safe_zones"] = raw.get("safe_zones", {})
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[config] {path.name} illeggibile ({exc}); uso i valori predefiniti.")
    return validate(cfg)


def save(cfg: dict, path: Path = CONFIG_PATH) -> None:
    """Scrittura atomica."""
    data = json.dumps(validate(cfg), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
