"""Motore: ciclo webcam -> classificazione -> macchina a stati -> uscite. Thread-safe verso la GUI."""
from __future__ import annotations

import copy
import threading
import time
from typing import Callable, Optional

import numpy as np

from . import config as cfgmod
from .calibration import MAX_YAW_DEG, GazeModel, fit_model, in_zone
from .capture import FaceDetector, FrameResult, FrameSource, ModelMissing
from .outputs import AdbOutput, CommandResult, Dispatcher, DryRunOutput, Output, PcMediaOutput
from .statemachine import GazeStateMachine, Transition
from .states import ACTION_LABELS, STATE_LABELS, GazeState, Obs


def build_outputs(cfg: dict, printer: Callable[[str], None] = print) -> list[Output]:
    outs: list[Output] = []
    o = cfg["outputs"]
    if o["tablet"]["enabled"]:
        outs.append(AdbOutput(o["tablet"]))
    if o["pc_media"]["enabled"]:
        outs.append(PcMediaOutput(o["pc_media"]))
    if cfg["dry_run"]:
        outs = [DryRunOutput(x, printer) for x in outs]
    return outs


class Engine:
    def __init__(self, cfg: Optional[dict] = None, source: Optional[FrameSource] = None,
                 outputs: Optional[list[Output]] = None, clock: Callable[[], float] = time.monotonic,
                 model: Optional[GazeModel] = None, printer: Callable[[str], None] = print):
        self.cfg = copy.deepcopy(cfg or cfgmod.load())
        self._clock = clock
        self._injected_source = source
        self._injected_outputs = outputs
        self._printer = printer
        self.model: Optional[GazeModel] = model if model is not None else GazeModel.load_for(self.cfg["calibration"]["monitor"])
        self.sm = GazeStateMachine.from_config(self.cfg)
        self.dispatcher: Optional[Dispatcher] = None
        self.source: Optional[FrameSource] = None

        self.paused = False
        self._lock = threading.Lock()
        self._last_cmd: dict[str, Optional[CommandResult]] = {}
        self._error: str = ""
        self._cam_msg: str = ""
        self._gaze_xy: Optional[tuple[float, float]] = None
        self._smoothed: Optional[np.ndarray] = None
        self._was_at = True
        self._preview: Optional[np.ndarray] = None
        self._fps = 0.0
        self._calib_collect = False
        self._calib_buf: list[np.ndarray] = []
        self._calibrating = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._restart = threading.Event()
        self._outputs_restart = threading.Event()
        self._capturing = False            # registrazione di un'area sicura: nessun comando
        self._zone_collect = False
        self._zone_buf: list[tuple[float, float]] = []
        self._was_safe = False
        self._last_frame_kind = ""

    # ---------------------------------------------------------------- ciclo vita
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="engine")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._teardown()

    def restart(self) -> None:
        """Riapre webcam/uscite (dopo modifica di impostazioni che lo richiedono)."""
        self._restart.set()

    def _setup(self) -> None:
        self._error = ""
        if self._injected_source is not None:
            self.source = self._injected_source
        else:
            try:
                det = FaceDetector()
            except ModelMissing as exc:
                self._error = str(exc)
                det = None
            except Exception as exc:
                self._error = f"MediaPipe non utilizzabile: {exc}"
                det = None
            self.source = FrameSource(self.cfg["camera"], self.cfg["show_preview"], det)
        self._setup_outputs()

    def _setup_outputs(self) -> None:
        outs = self._injected_outputs if self._injected_outputs is not None else build_outputs(self.cfg, self._printer)
        self.dispatcher = Dispatcher(outs, self._on_result)

    def _teardown_outputs(self) -> None:
        if self.dispatcher:
            self.dispatcher.stop()
            self.dispatcher = None

    def _teardown(self) -> None:
        self._teardown_outputs()
        if self.source:
            self.source.close()
            self.source = None

    def _run(self) -> None:
        self._setup()
        last = self._clock()
        frames, fps_t = 0, self._clock()
        while not self._stop.is_set():
            if self._restart.is_set():
                self._restart.clear()
                self._teardown()
                self._setup()
                self.sm.reset()
            if self._outputs_restart.is_set():          # cambio di uscite attive: la webcam non si tocca
                self._outputs_restart.clear()
                self._teardown_outputs()
                self._setup_outputs()
            t0 = self._clock()
            try:
                res = self.source.next() if self.source else FrameResult("camera_fail")
                self.step(res, self._clock())
            except Exception as exc:       # il ciclo non deve morire per un frame problematico
                self._error = f"{type(exc).__name__}: {exc}"
                res = None
            frames += 1
            if t0 - fps_t >= 1.0:
                self._fps, frames, fps_t = frames / (t0 - fps_t), 0, t0
            period = 1.0 / max(1, self.cfg["camera"]["processing_fps"])
            delay = period - (self._clock() - t0)
            if delay > 0:
                self._stop.wait(delay)

    # ---------------------------------------------------------------- logica per-frame
    def step(self, res: FrameResult, t: float) -> Optional[Transition]:
        """Un passo di elaborazione (usato anche dai test con sorgenti finte)."""
        self._last_frame_kind = res.kind
        if res.preview is not None:
            self._preview = res.preview
        if res.kind == "no_data":
            return None
        obs = self._observe(res)
        if self._calibrating or self._capturing or self.paused:
            return None
        tr = self.sm.update(t, obs)
        if tr and not tr.initial:
            self._dispatch(tr)
        return tr

    def _observe(self, res: FrameResult) -> Obs:
        det = self.cfg["detection"]
        if res.kind == "camera_fail":
            self._cam_msg = res.detail or "webcam non disponibile"
            self._gaze_xy = None
            return Obs.CAMERA_FAIL
        self._cam_msg = ""
        if res.kind == "no_face":
            self._gaze_xy = None
            self._smoothed = None
            return Obs.AWAY if det["no_face_is_away"] else Obs.NONE
        f = res.features
        if f is None or f.blink >= det["blink_threshold"]:
            return Obs.NONE                                  # ammiccamento: frame ignorato
        vec = f.vector()
        if self._calib_collect:
            self._calib_buf.append(vec)
        if self.model is None:
            return Obs.NONE                                  # senza calibrazione non si indovina
        a = det["smoothing"]
        self._smoothed = vec if self._smoothed is None else a * self._smoothed + (1 - a) * vec
        x, y = self.model.predict(self._smoothed)
        self._gaze_xy = (x, y)
        at = self.model.is_at_screen(x, y, float(self._smoothed[0]), self._was_at, det["screen_margin"], det["hysteresis"])
        self._was_at = at
        if self._zone_collect:
            self._zone_buf.append((x, y))
        # aree sicure (es. tastiera): guardarle non conta come "altrove"
        yaw_ok = abs(float(self._smoothed[0]) - self.model.center_yaw) <= MAX_YAW_DEG
        margin = det["hysteresis"] if self._was_safe else 0.0
        self._was_safe = yaw_ok and any(z["enabled"] and in_zone(z, x, y, margin) for z in self.current_zones())
        if not at and self._was_safe:
            at = True
        return Obs.AT if at else Obs.AWAY

    def _dispatch(self, tr: Transition) -> None:
        key = "on_away" if tr.new_state == GazeState.LOOKING_AWAY else "on_return"
        if not self.dispatcher:
            return
        for name in self.dispatcher.outputs:
            ocfg = self.cfg["outputs"].get(name, {})
            action = ocfg.get(key, "none")
            if action in ("play", "pause"):
                self.dispatcher.submit(name, action)

    def _on_result(self, r: CommandResult) -> None:
        with self._lock:
            self._last_cmd[r.output] = r
        tag = "OK" if r.ok else "ERRORE"
        self._printer(f"[{time.strftime('%H:%M:%S')}] {r.output}: {ACTION_LABELS.get(r.action, r.action)} -> {tag} {r.message}")

    # ---------------------------------------------------------------- controlli da GUI
    def set_paused(self, paused: bool) -> None:
        if self.paused and not paused:
            self.sm.reset()                  # alla ripresa nuova stabilizzazione, nessun comando improvviso
        self.paused = paused

    def apply_config(self, cfg: dict, needs_restart: bool) -> None:
        old_key = cfgmod.calibration_key(self.cfg["calibration"]["monitor"])
        old_outputs = (copy.deepcopy(self.cfg["outputs"]), self.cfg["dry_run"])
        self.cfg = copy.deepcopy(cfg)
        self.sm.apply_config(self.cfg)
        new_key = cfgmod.calibration_key(self.cfg["calibration"]["monitor"])
        if new_key != old_key:                       # altra area: usa la sua calibrazione (o chiedila)
            self.model = GazeModel.load_for(new_key)
            self._smoothed, self._gaze_xy, self._was_at = None, None, True
            self.sm.reset()
        if needs_restart:
            self.restart()
        elif (self.cfg["outputs"], self.cfg["dry_run"]) != old_outputs:
            self._outputs_restart.set()

    def begin_calibration(self) -> None:
        self._calibrating = True
        self._calib_buf = []
        self._calib_collect = False

    def calib_collect(self, on: bool) -> list[np.ndarray]:
        if on:
            self._calib_buf = []
            self._calib_collect = True
            return []
        self._calib_collect = False
        buf, self._calib_buf = self._calib_buf, []
        return buf

    def finish_calibration(self, samples, area: dict) -> GazeModel:
        """Adatta il modello; solleva ValueError se i dati sono insufficienti. Chiude sempre la modalità calibrazione."""
        try:
            model = fit_model(samples, area=area)
            model.save(cfgmod.calibration_path(self.cfg["calibration"]["monitor"]))
            self.model = model
            self._smoothed = None
            return model
        finally:
            self._calibrating = False
            self.sm.reset()

    # ---- aree sicure ------------------------------------------------
    def current_zones(self) -> list[dict]:
        return self.cfg.get("safe_zones", {}).get(cfgmod.calibration_key(self.cfg["calibration"]["monitor"]), [])

    def begin_zone_capture(self) -> None:
        self._capturing, self._zone_collect, self._zone_buf = True, False, []

    def zone_collect(self, on: bool) -> list[tuple[float, float]]:
        if on:
            self._zone_buf, self._zone_collect = [], True
            return []
        self._zone_collect = False
        buf, self._zone_buf = self._zone_buf, []
        return buf

    def end_zone_capture(self) -> None:
        self._capturing = self._zone_collect = False
        self.sm.reset()                               # nessun comando improvviso dopo la registrazione

    def cancel_calibration(self) -> None:
        self._calib_collect = False
        self._calibrating = False

    # ---------------------------------------------------------------- stato per la GUI
    def snapshot(self) -> dict:
        t = self._clock()
        tgt, frac = self.sm.progress(t)
        with self._lock:
            cmds = dict(self._last_cmd)
        outs = {}
        if self.dispatcher:
            for n, o in self.dispatcher.outputs.items():
                s = o.status()
                s["label"] = o.label
                s["last"] = cmds.get(n)
                outs[n] = s
        disp = self.sm.display_state
        if self.model is None and self.sm.camera_ok:
            disp = GazeState.UNKNOWN
        msg = self._error or self._cam_msg
        if not msg and self.model is None:
            msg = "Calibrazione necessaria: premi «Ricalibra»."
        elif not msg and self.sm.warming_up and not self.paused:
            msg = "Stabilizzazione iniziale… nessun comando verrà inviato."
        return {
            "state": disp, "label": STATE_LABELS[disp], "camera_ok": self.sm.camera_ok,
            "progress_target": tgt, "progress": frac, "gaze": self._gaze_xy,
            "margin": self.cfg["detection"]["screen_margin"], "paused": self.paused,
            "calibrated": self.model is not None, "calibrating": self._calibrating,
            "message": msg, "outputs": outs, "fps": self._fps,
            "preview": self._preview, "dry_run": self.cfg["dry_run"],
            "rmse": self.model.rmse if self.model else None,
            "zones": [dict(z) for z in self.current_zones()], "safe_hit": self._was_safe, "capturing": self._capturing,
        }
