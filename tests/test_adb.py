import subprocess

import pytest

from eyegaze.adb import AdbClient, AdbError
from eyegaze.outputs import AdbOutput, DryRunOutput

DEVICES = """List of devices attached
R52W80XXXX             device usb:1-1 product:gta7 model:SM_X200 device:gta7 transport_id:1
192.168.1.50:41234     offline transport_id:2
"""


class FakeRunner:
    """ADB finto: registra i comandi, risposte configurabili."""

    def __init__(self, devices=DEVICES, fail_keys=0):
        self.calls, self.devices, self.fail_keys = [], devices, fail_keys

    def __call__(self, args, **kw):
        a = list(args)[1:]
        self.calls.append(a)
        if a[:1] == ["devices"]:
            return subprocess.CompletedProcess(args, 0, self.devices, "")
        if "keyevent" in a:
            if self.fail_keys > 0:
                self.fail_keys -= 1
                return subprocess.CompletedProcess(args, 1, "", "error: device offline")
            return subprocess.CompletedProcess(args, 0, "", "")
        if a[:1] == ["connect"]:
            return subprocess.CompletedProcess(args, 0, "connected to " + a[1], "")
        if a[:1] == ["pair"]:
            return subprocess.CompletedProcess(args, 1, "", "Failed: wrong code 123456")
        return subprocess.CompletedProcess(args, 0, "", "")


def client(runner):
    c = AdbClient(runner=runner)
    c.adb = "adb"
    return c


def make_out(cfg, runner):
    out = AdbOutput(cfg, client(runner))
    out.RECONNECT_MIN_INTERVAL = 0
    return out


def test_parse_devices():
    d = client(FakeRunner()).devices()
    assert d[0].serial == "R52W80XXXX" and d[0].ready and d[0].model == "SM X200"
    assert not d[1].ready


def test_keyevents_are_explicit_play_and_pause():
    r = FakeRunner()
    out = make_out({"serial": "R52W80XXXX", "method": "keyevent"}, r)
    assert out.send("play").ok and out.send("pause").ok
    keys = [c for c in r.calls if "keyevent" in c]
    assert keys[0] == ["-s", "R52W80XXXX", "shell", "input", "keyevent", "126"]
    assert keys[1][-1] == "127"


def test_single_ready_device_auto_selected():
    r = FakeRunner("List of devices attached\nABC123 device model:Tab_A\n")
    out = make_out({"serial": ""}, r)
    assert out.send("play").ok and out.serial == "ABC123"


def test_multiple_devices_require_explicit_selection():
    r = FakeRunner("List of devices attached\nA device\nB device\n")
    out = make_out({"serial": ""}, r)
    res = out.send("play")
    assert not res.ok and "selezionane" in res.message
    assert not any("keyevent" in c for c in r.calls)       # nessun comando a un dispositivo non scelto


def test_disconnected_reports_error_and_retries_are_bounded():
    r = FakeRunner("List of devices attached\n")
    out = make_out({"serial": "X1"}, r)
    res = out.send("play")
    assert not res.ok
    assert sum(1 for c in r.calls if c[:1] == ["devices"]) <= AdbOutput.MAX_RETRIES + 1
    assert not out.status()["connected"]


def test_transient_failure_recovers_with_retry():
    r = FakeRunner(fail_keys=1)
    out = make_out({"serial": "R52W80XXXX"}, r)
    assert out.send("play").ok


def test_wifi_device_reconnect_attempted_on_failure():
    r = FakeRunner("List of devices attached\n")
    out = make_out({"serial": "192.168.1.50:41234"}, r)
    out.send("play")
    assert any(c[:1] == ["connect"] for c in r.calls)


def test_pairing_code_never_leaks_into_error():
    with pytest.raises(AdbError) as e:
        client(FakeRunner()).pair("192.168.1.50:37000", "123456")
    assert "123456" not in str(e.value)


def test_dry_run_sends_nothing():
    r = FakeRunner()
    lines = []
    out = DryRunOutput(make_out({"serial": "R52W80XXXX"}, r), lines.append)
    res = out.send("play")
    assert res.ok and res.dry_run
    assert not any("keyevent" in c for c in r.calls)
    assert "keyevent 126" in lines[0]
