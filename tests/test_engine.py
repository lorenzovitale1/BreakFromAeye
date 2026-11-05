"""Scenari end-to-end con webcam e dispositivi finti (nessun hardware)."""
import time

import numpy as np

from eyegaze import config as cfgmod
from eyegaze.calibration import calibration_grid, fit_model
from eyegaze.capture import FrameResult
from eyegaze.engine import Engine
from eyegaze.features import FaceFeatures
from eyegaze.outputs import CommandResult, Output
from eyegaze.states import GazeState

FPS = 15


class NullSource:
    def close(self):
        pass


class RecOutput(Output):
    def __init__(self, name="tablet"):
        self.name, self.label, self.sent = name, name, []

    def send(self, action):
        self.sent.append(action)
        return CommandResult(time.time(), self.name, action, True)


def synthetic_model():
    # mappa lineare nota: yaw -> x, pitch -> y (feature iride a zero)
    pts = []
    for (tx, ty) in calibration_grid():
        yaw, pitch = (tx - 0.5) * 20, (ty - 0.5) * 12
        pts.append(((tx, ty), [np.array([yaw, pitch, 0.0, 0.0]) for _ in range(10)]))
    return fit_model(pts)


def face(x, y, blink=0.0):
    return FrameResult("face", FaceFeatures((x - 0.5) * 20, (y - 0.5) * 12, 0, 0, 0.3, 0.3, blink))


class Rig:
    def __init__(self):
        self.cfg = cfgmod.load(cfgmod.ROOT / "nonexistent.json")
        self.cfg["detection"]["smoothing"] = 0.0
        self.cfg["timing"]["cooldown_seconds"] = 0.0
        self.out = RecOutput()
        self.eng = Engine(self.cfg, source=NullSource(), outputs=[self.out], model=synthetic_model(), printer=lambda s: None)
        self.eng._setup()
        self.t = 0.0

    def run(self, res, secs):
        for _ in range(round(secs * FPS)):
            self.eng.step(res, self.t)
            self.t += 1 / FPS
        time.sleep(0.05)       # lascia lavorare il thread dell'uscita

    def close(self):
        self.eng._teardown()


def test_model_fit_quality():
    assert synthetic_model().rmse < 0.05


def test_looking_at_edges_never_plays():
    r = Rig()
    r.run(face(0.5, 0.5), 4)
    for x, y in [(0.02, 0.02), (0.98, 0.02), (0.98, 0.98), (0.02, 0.98), (0.5, 0.98), (-0.05, 0.5)]:
        r.run(face(x, y), 4)
    assert r.out.sent == []
    r.close()


def test_full_scenario_play_then_pause_once_each():
    r = Rig()
    r.run(face(0.5, 0.5), 4)                 # stabilizzazione, guarda il PC
    r.run(face(0.5, 2.0), 4)                 # guarda molto in basso (il tablet)
    r.run(face(0.5, 0.5), 4)                 # torna
    assert r.out.sent == ["play", "pause"]
    r.close()


def test_blink_and_short_glance_do_not_trigger():
    r = Rig()
    r.run(face(0.5, 0.5), 4)
    r.run(face(0.5, 0.5, blink=0.9), 0.4)
    r.run(face(0.5, 2.0), 0.8)
    r.run(face(0.5, 0.5), 3)
    assert r.out.sent == []
    r.close()


def test_face_lost_counts_as_away_when_camera_ok():
    r = Rig()
    r.run(face(0.5, 0.5), 4)
    r.run(FrameResult("no_face"), 3)
    assert r.out.sent == ["play"]
    r.close()


def test_face_lost_ignored_when_option_off():
    r = Rig()
    r.eng.cfg["detection"]["no_face_is_away"] = False
    r.run(face(0.5, 0.5), 4)
    r.run(FrameResult("no_face"), 5)
    assert r.out.sent == []
    r.close()


def test_camera_failure_never_fakes_gaze():
    r = Rig()
    r.run(face(0.5, 0.5), 4)
    r.run(FrameResult("camera_fail", detail="webcam scollegata"), 10)
    assert r.out.sent == []
    snap = r.eng.snapshot()
    assert snap["state"] == GazeState.UNKNOWN and not snap["camera_ok"] and "webcam" in snap["message"]
    r.close()


def test_pause_automation_blocks_commands():
    r = Rig()
    r.run(face(0.5, 0.5), 4)
    r.eng.set_paused(True)
    r.run(face(0.5, 2.0), 5)
    assert r.out.sent == []
    r.close()


def test_without_calibration_nothing_is_sent():
    r = Rig()
    r.eng.model = None
    r.run(face(0.5, 0.5), 4)
    r.run(face(0.5, 2.0), 5)
    assert r.out.sent == []
    assert "Calibrazione" in r.eng.snapshot()["message"]
    r.close()


def test_inverse_mapping_for_pc_video():
    r = Rig()
    r.eng.cfg["outputs"]["tablet"].update(on_away="pause", on_return="play")   # mappa invertita (video sul PC)
    r.run(face(0.5, 0.5), 4)
    r.run(face(0.5, 2.0), 3)
    r.run(face(0.5, 0.5), 3)
    assert r.out.sent == ["pause", "play"]
    r.close()


def test_return_pause_can_be_disabled():
    r = Rig()
    r.eng.cfg["outputs"]["tablet"]["on_return"] = "none"
    r.run(face(0.5, 0.5), 4)
    r.run(face(0.5, 2.0), 3)
    r.run(face(0.5, 0.5), 3)
    assert r.out.sent == ["play"]
    r.close()
