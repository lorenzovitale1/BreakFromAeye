# BreakFromAeye 👁

> *A break from AI + eye.* Look away from your PC and your video starts.

Watching a video on your **Android tablet** while working at your **PC**? This tool uses **only your PC webcam** to detect whether you are
looking at the screen and pauses/plays the video accordingly. Everything runs locally: no eye tracker, no cloud.

| Output | Look away (≥ 1.5 s) | Look back at the PC (≥ 0.8 s) |
|---|---|---|
| Android tablet (ADB over Wi-Fi) | PLAY | PAUSE |
| Video on the PC (YouTube etc. in the browser) | PAUSE | PLAY |

Timings and actions are configurable. Tablet and PC outputs can be used separately or together.

**Features:** one-click tablet / PC / both switch · "safe areas" where looking does not count as looking away (e.g. the keyboard; defined by looking at its
4 corners with audio cues, by drawing on a map, or numerically) · multi-monitor support (all screens or a single one, one calibration per choice) ·
runs in the system tray when the window is closed (configurable) · 9-point calibration · blink/glance filtering · one command per transition · dry-run mode ·
no command is ever sent when the webcam fails. No frames are stored or sent over the network.

## Install (Windows 10/11)
**Recommended:** download `BreakFromAeye-Setup-<version>.exe` from [Releases](https://github.com/lorenzovitale1/BreakFromAeye/releases). It bundles everything
(no Python needed, includes the face model and adb), installs per-user and shows up in *Apps & features*. Windows SmartScreen may warn because the installer is not
code-signed: *More info → Run anyway*.

**From source** (Python 3.10–3.12):
```bash
git clone https://github.com/lorenzovitale1/BreakFromAeye.git
cd BreakFromAeye
setup.bat            # venv + dependencies; asks before downloading the model (~4 MB) and adb (~8 MB)
```
Then start it from the desktop shortcut created by `setup.bat`, or `start.vbs` (no console window).
Or with pip: `pipx install git+https://github.com/lorenzovitale1/BreakFromAeye.git`, then `breakfromaeye --setup` and `breakfromaeye-gui`.

## Tablet setup (Android 11+)
Developer options → **Wireless debugging** (tap the *label*, not the switch) → *Pair device with pairing code*. In the app: **Abbina…** (pair, using the pairing IP:port and
code) → **Connetti IP…** (connect, using the IP:port shown on the main Wireless debugging page) → pick the device → *Test PLAY / PAUSA*.
Some Android apps ignore media keys; switch *Metodo* to `toggle_if_needed` in that case. DRM/protections are not bypassed.

## Development
```bash
pip install -e ".[dev]"
python -m pytest -q            # no webcam or tablet needed
python -m eyegaze --simulate   # scripted dry-run scenario
```
The full documentation (Italian) is in [README.md](README.md). Accuracy is far below a dedicated eye tracker; this is a personal-productivity tool,
not a safety device. Licensed under [MIT](LICENSE). Third-party: MediaPipe (Apache-2.0), OpenCV, NumPy, pystray, Pillow, Android platform-tools (Google).
