import json

import numpy as np

from eyegaze import config as cfgmod
from eyegaze.calibration import GazeModel
from eyegaze.features import extract_features, head_angles


def synth_landmarks(iris_dx=0.0, iris_dy=0.0, open_=0.3):
    lm = np.full((478, 3), 0.5)
    lm[:, 2] = 0.0
    # occhio destro del soggetto (a sinistra in immagine)
    lm[33, :2] = (0.30, 0.40); lm[133, :2] = (0.40, 0.40)
    lm[159, :2] = (0.35, 0.40 - open_ * 0.05); lm[145, :2] = (0.35, 0.40 + open_ * 0.05)
    lm[362, :2] = (0.60, 0.40); lm[263, :2] = (0.70, 0.40)
    lm[386, :2] = (0.65, 0.40 - open_ * 0.05); lm[374, :2] = (0.65, 0.40 + open_ * 0.05)
    lm[468, :2] = (0.35 + iris_dx * 0.1, 0.40 + iris_dy * 0.1)
    lm[473, :2] = (0.65 + iris_dx * 0.1, 0.40 + iris_dy * 0.1)
    return lm


def test_iris_horizontal_sign_and_scale():
    f = extract_features(synth_landmarks(0.3), 640, 480, None)
    assert abs(f.iris_h - 0.3) < 1e-6 and abs(f.iris_v) < 1e-6
    assert extract_features(synth_landmarks(-0.3), 640, 480, None).iris_h < 0


def test_iris_vertical_down_positive():
    assert extract_features(synth_landmarks(0, 0.2), 640, 480, None).iris_v > 0.0


def test_closed_eye_gives_blink_score():
    closed = extract_features(synth_landmarks(open_=0.01), 640, 480, None)
    opened = extract_features(synth_landmarks(open_=0.3), 640, 480, None)
    assert closed.blink > 0.9 and opened.blink < 0.1


def test_blendshapes_override_blink():
    f = extract_features(synth_landmarks(), 640, 480, None, {"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.7})
    assert f.blink == 0.8


def test_head_angles_identity_and_yaw():
    assert head_angles(np.eye(4)) == (0.0, 0.0)
    a = np.radians(20)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = np.cos(a), np.sin(a), -np.sin(a), np.cos(a)
    yaw, pitch = head_angles(m)
    assert abs(abs(yaw) - 20) < 1e-6 and abs(pitch) < 1e-6


def test_config_defaults_match_spec(tmp_path):
    c = cfgmod.load(tmp_path / "missing.json")
    assert c["timing"]["away_seconds"] == 1.5 and c["timing"]["return_seconds"] == 0.8
    assert c["outputs"]["tablet"]["on_away"] == "play" and c["outputs"]["tablet"]["on_return"] == "pause"
    assert c["detection"]["no_face_is_away"] is True


def test_config_validation_clamps_and_repairs(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"timing": {"away_seconds": 999, "return_seconds": "abc"}, "unknown": 1}))
    c = cfgmod.load(p)
    assert c["timing"]["away_seconds"] == 6.0 and c["timing"]["return_seconds"] == 0.8


def test_config_roundtrip_and_corrupt_file(tmp_path):
    p = tmp_path / "c.json"
    c = cfgmod.load(p)
    c["timing"]["away_seconds"] = 2.2
    cfgmod.save(c, p)
    assert cfgmod.load(p)["timing"]["away_seconds"] == 2.2
    p.write_text("{rotto")
    assert cfgmod.load(p)["timing"]["away_seconds"] == 1.5


def test_every_setting_has_default():
    for s in cfgmod.SETTINGS:
        cfgmod.get_path(cfgmod.DEFAULTS, s["path"])


def test_model_json_roundtrip(tmp_path):
    from tests.test_engine import synthetic_model
    m = synthetic_model()
    p = tmp_path / "cal.json"
    m.save(p)
    assert np.allclose(m.weights, GazeModel.load(p).weights)
    assert GazeModel.load(tmp_path / "nope.json") is None
