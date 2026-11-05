"""Scelta dell'area monitorata: una calibrazione per area, cambio senza ricalibrare."""
import copy
import json

import numpy as np

from eyegaze import config as cfgmod
from eyegaze.calibration import GazeModel
from eyegaze.engine import Engine
from tests.test_engine import NullSource, RecOutput, synthetic_model


def test_keys_and_paths(tmp_path, monkeypatch):
    assert cfgmod.calibration_key("primary") == "0"
    assert cfgmod.calibration_key("2") == "2"
    assert cfgmod.calibration_key("boh") == "all"
    assert cfgmod.calibration_path("all").name == "calibration_all.json"
    assert cfgmod.calibration_path("1").name == "calibration_1.json"


def test_load_for_uses_per_area_file_and_legacy_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    import eyegaze.calibration as cal
    monkeypatch.setattr(cal, "calibration_path", lambda s: tmp_path / f"calibration_{cfgmod.calibration_key(s)}.json")
    monkeypatch.setattr(cal, "CALIBRATION_PATH", tmp_path / "calibration.json")
    m = synthetic_model()
    m.area = {"monitor": "all"}
    m.save(tmp_path / "calibration.json")                       # vecchio file unico = area "all"
    assert GazeModel.load_for("all") is not None
    assert GazeModel.load_for("1") is None                      # altra area: nessuna calibrazione
    m2 = synthetic_model()
    m2.save(tmp_path / "calibration_1.json")
    assert GazeModel.load_for("1") is not None


def test_switching_area_swaps_model_and_blocks_commands_until_calibrated(monkeypatch):
    import eyegaze.engine as eng_mod
    store = {"all": synthetic_model()}
    monkeypatch.setattr(eng_mod.GazeModel, "load_for", classmethod(lambda cls, s: store.get(cfgmod.calibration_key(s))))
    cfg = cfgmod.load(cfgmod.ROOT / "nonexistent.json")
    out = RecOutput()
    e = Engine(cfg, source=NullSource(), outputs=[out], model=store["all"], printer=lambda s: None)
    new = copy.deepcopy(e.cfg)
    new["calibration"]["monitor"] = "1"
    e.apply_config(new, False)
    assert e.model is None and "Calibrazione" in e.snapshot()["message"]     # monitor 2 non calibrato
    store["1"] = synthetic_model()
    new2 = copy.deepcopy(new)
    new2["calibration"]["monitor"] = "all"
    e.apply_config(new2, False)
    assert e.model is store["all"]                                           # tornando indietro: calibrazione già pronta


def test_monitor_option_values_are_valid():
    from eyegaze.monitors import monitor_options
    for value, label in monitor_options():
        assert cfgmod.calibration_key(value) == value and label
