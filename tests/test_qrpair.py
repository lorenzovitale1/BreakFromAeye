import subprocess
import threading

import pytest

from eyegaze.adb import AdbClient, AdbError, MdnsService
from eyegaze.qrpair import QrPairing, new_credentials, qr_image, qr_payload

REAL_LINE = "List of discovered mdns services\nadb-R52X90J4WCH-SjXxnN\t_adb-tls-pairing._tcp\t192.168.1.14:34519\n"


class FakeAdb:
    """ADB finto con mDNS: il servizio di abbinamento compare dopo `appear_after` interrogazioni."""

    def __init__(self, name, appear_after=2, pair_ok=True, mdns_check="mdns daemon version [Openscreen discovery 0.0.0]",
                 devices_after_pair=True):
        self.name, self.appear_after, self.pair_ok, self.mdns_check = name, appear_after, pair_ok, mdns_check
        self.devices_after_pair = devices_after_pair
        self.polls, self.calls, self.paired = 0, [], False

    def __call__(self, args, **kw):
        a = list(args)[1:]
        self.calls.append(a)
        cp = lambda rc=0, out="", err="": subprocess.CompletedProcess(args, rc, out, err)       # noqa: E731
        if a[:2] == ["mdns", "check"]:
            return cp(0, self.mdns_check)
        if a[:2] == ["mdns", "services"]:
            self.polls += 1
            lines = ["List of discovered mdns services"]
            if self.polls > self.appear_after:
                lines.append(f"{self.name}\t_adb-tls-pairing._tcp\t192.168.1.14:34519")
            lines.append("altro-dispositivo\t_adb-tls-pairing._tcp\t192.168.1.99:40000")
            if self.paired:
                lines.append("adb-R52X-abc\t_adb-tls-connect._tcp\t192.168.1.14:41111")
            return cp(0, "\n".join(lines) + "\n")
        if a[:1] == ["pair"]:
            if self.pair_ok:
                self.paired = True
                return cp(0, "Successfully paired to " + a[1])
            return cp(1, "", "Failed: wrong password")
        if a[:1] == ["devices"]:
            if self.paired and self.devices_after_pair:
                return cp(0, "List of devices attached\nadb-R52X-abc._adb-tls-connect._tcp\tdevice model:SM_X510\n")
            return cp(0, "List of devices attached\n")
        if a[:1] == ["connect"]:
            return cp(0, "connected to " + a[1])
        return cp(0)


def make(fake):
    c = AdbClient(runner=fake)
    c.adb = "adb"
    return c


def pairing_for(fake_factory, **kw):
    box = {}
    c = AdbClient(runner=lambda args, **k: box["f"](args, **k))
    c.adb = "adb"
    p = QrPairing(c, sleep=lambda s: None, clock=kw.pop("clock", None) or __import__("time").monotonic)
    box["f"] = fake_factory(p.name, **kw)
    return p, box["f"]


def test_credentials_and_payload_format():
    n, pw = new_credentials()
    assert n.startswith("bfa-") and len(pw) == 12 and pw.isalnum()
    assert qr_payload("bfa-x", "Pw1") == "WIFI:T:ADB;S:bfa-x;P:Pw1;;"
    assert new_credentials() != new_credentials()


def test_qr_roundtrip_decodes_to_payload():
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    pairing = QrPairing(AdbClient(runner=lambda *a, **k: None))
    img = np.array(qr_image(pairing.payload, box_size=6))[:, :, ::-1].copy()
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert text == pairing.payload


def test_parse_real_mdns_line():
    c = make(lambda args, **kw: subprocess.CompletedProcess(args, 0, REAL_LINE, ""))
    assert c.mdns_services() == [MdnsService("adb-R52X90J4WCH-SjXxnN", "pairing", "192.168.1.14:34519")]


def test_full_flow_pairs_with_our_service_only_and_connects():
    p, fake = pairing_for(FakeAdb, appear_after=2)
    status = []
    msg = p.run(threading.Event(), status.append, timeout=60)
    pair_calls = [c for c in fake.calls if c[:1] == ["pair"]]
    assert pair_calls == [["pair", "192.168.1.14:34519", p._password]]        # non il dispositivo "altro"
    assert "connesso" in msg and "SM X510" in msg
    assert any("trovato" in s for s in status)


def test_cancel_stops_without_pairing():
    p, fake = pairing_for(FakeAdb, appear_after=10 ** 6)
    ev = threading.Event()
    ev.set()
    with pytest.raises(AdbError, match="annullato"):
        p.run(ev, timeout=60)
    assert not any(c[:1] == ["pair"] for c in fake.calls)


def test_timeout_when_tablet_never_scans():
    t = {"now": 0.0}

    def clock():
        t["now"] += 10
        return t["now"]
    p, fake = pairing_for(FakeAdb, appear_after=10 ** 6, clock=clock)
    with pytest.raises(AdbError, match="tempo scaduto"):
        p.run(threading.Event(), timeout=60)


def test_wrong_password_error_does_not_leak_secret():
    p, fake = pairing_for(FakeAdb, appear_after=0, pair_ok=False)
    with pytest.raises(AdbError) as e:
        p.run(threading.Event(), timeout=60)
    assert p._password not in str(e.value)


def test_mdns_unavailable_falls_back_to_openscreen_then_gives_clear_error():
    p, fake = pairing_for(FakeAdb, appear_after=0, mdns_check="ERROR: mdns daemon unavailable")
    with pytest.raises(AdbError, match="mDNS non disponibile"):
        p.run(threading.Event(), timeout=60)
    assert ["kill-server"] in fake.calls and p.client.env_extra.get("ADB_MDNS_OPENSCREEN") == "1"
