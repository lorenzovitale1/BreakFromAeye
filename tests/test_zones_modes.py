"""Aree sicure, scelta delle uscite, istanza unica."""
import copy
import time

import numpy as np
import pytest

from eyegaze import config as cfgmod
from eyegaze import single
from eyegaze.calibration import in_zone, zone_from_corners, zone_from_points
from eyegaze.capture import FrameResult
from eyegaze.engine import Engine
from tests.test_engine import FPS, NullSource, RecOutput, face, synthetic_model


def make_engine(zones=None):
    cfg = cfgmod.load(cfgmod.ROOT / "nonexistent.json")
    cfg["detection"]["smoothing"] = 0.0
    cfg["timing"]["cooldown_seconds"] = 0.0
    if zones is not None:
        cfg["safe_zones"] = {"all": zones}
    out = RecOutput()
    eng = Engine(cfg, source=NullSource(), outputs=[out], model=synthetic_model(), printer=lambda s: None)
    eng._setup()
    return eng, out


def run(eng, res, secs, t0):
    t = t0
    for _ in range(round(secs * FPS)):
        eng.step(res, t)
        t += 1 / FPS
    time.sleep(0.05)
    return t


KEYBOARD = {"name": "Tastiera", "enabled": True, "x0": 0.0, "y0": 1.15, "x1": 1.0, "y1": 1.9}


def test_looking_at_keyboard_zone_does_not_trigger():
    eng, out = make_engine([KEYBOARD])
    t = run(eng, face(0.5, 0.5), 4, 0)
    run(eng, face(0.5, 1.5), 6, t)                  # guarda la tastiera per 6 s
    assert out.sent == []
    eng._teardown()


def test_same_gaze_without_zone_triggers_play():
    eng, out = make_engine([])
    t = run(eng, face(0.5, 0.5), 4, 0)
    run(eng, face(0.5, 1.5), 4, t)
    assert out.sent == ["play"]
    eng._teardown()


def test_disabled_zone_is_ignored_and_far_gaze_still_triggers():
    eng, out = make_engine([dict(KEYBOARD, enabled=False)])
    t = run(eng, face(0.5, 0.5), 4, 0)
    t = run(eng, face(0.5, 1.5), 4, t)
    assert out.sent == ["play"]
    eng._teardown()
    eng, out = make_engine([KEYBOARD])
    t = run(eng, face(0.5, 0.5), 4, 0)
    run(eng, face(0.5, 2.6), 4, t)                   # molto più in basso dell'area sicura (es. il tablet)
    assert out.sent == ["play"]
    eng._teardown()


def test_zones_are_per_area():
    eng, out = make_engine([KEYBOARD])
    assert eng.current_zones() == [KEYBOARD]
    new = copy.deepcopy(eng.cfg)
    new["calibration"]["monitor"] = "1"
    eng.apply_config(new, False)
    assert eng.current_zones() == []
    eng._teardown()


def test_zone_from_corners_and_points():
    corner = lambda x, y: [np.array([x + dx, y + dy]) for dx in (-0.01, 0, 0.01) for dy in (-0.01, 0, 0.01)]
    z = zone_from_corners([corner(0.1, 1.2), corner(0.9, 1.2), corner(0.9, 1.8), corner(0.1, 1.8)], pad=0.03)
    assert abs(z["x0"] - 0.07) < 1e-6 and abs(z["y1"] - 1.83) < 1e-6 and z["enabled"]
    assert in_zone(z, 0.5, 1.5) and not in_zone(z, 0.5, 0.5)
    with pytest.raises(ValueError):
        zone_from_corners([[(0, 0)], corner(0, 0), corner(0, 0), corner(0, 0)])
    pts = [(0.2 + 0.001 * i, 1.4) for i in range(30)]
    assert in_zone(zone_from_points(pts), 0.22, 1.4)


def test_config_zones_roundtrip_and_cleaning(tmp_path):
    cfg = cfgmod.load(tmp_path / "x.json")
    cfg["safe_zones"] = {"all": [KEYBOARD, {"name": "rotta"}, {"x0": "a", "x1": 1, "y0": 0, "y1": 1}]}
    cfgmod.save(cfg, tmp_path / "x.json")
    back = cfgmod.load(tmp_path / "x.json")
    assert back["safe_zones"] == {"all": [KEYBOARD]}


def test_toggling_outputs_rebuilds_only_outputs_not_camera():
    eng, out = make_engine()
    src = eng.source
    new = copy.deepcopy(eng.cfg)
    new["outputs"]["pc_media"]["enabled"] = True
    eng.apply_config(new, False)
    assert eng._outputs_restart.is_set() and eng.source is src
    eng._teardown()


def test_default_close_action_is_tray():
    cfg = cfgmod.load(cfgmod.ROOT / "nonexistent.json")
    assert cfg["ui"]["close_action"] == "tray" and cfg["ui"]["start_minimized"] is False


def test_single_instance_signals_first_instance():
    shown = []
    port = 47999
    assert single.acquire(lambda: shown.append(1), port) is True
    assert single.acquire(lambda: None, port) is False
    for _ in range(40):
        if shown:
            break
        time.sleep(0.05)
    assert shown == [1]
