# StepMania/Etterna Hybrid Bot

This is an offline-only, chart-driven auto-player for StepMania/Etterna. The
chart supplies the note schedule; the RF-DETR vision model supplies clock
synchronisation and a degraded-mode fallback.

The rebuild follows [newplan.md](newplan.md) milestone by milestone. The old
prototype is retained in `old/` for reference but is intentionally ignored by
Git. Model files are local artifacts and are not committed.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- StepMania or Etterna running locally in a windowed/borderless window
- A trusted RF-DETR ONNX model for the detector
- A local `.sm` or `.ssc` chart

The bot is designed for offline local play and testing only. It does not
submit scores or communicate with an online service.

## Installation

From the repository root, create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,windows]"
```

If PowerShell blocks activation for the current user, run PowerShell once as
your user and then retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Verify the installation:

```powershell
python -m bot.app.main --help
python -m pytest
```

## Configuration

The default settings are in [`config/default.yaml`](config/default.yaml).
Adjust these values before a real run:

- `vision.roi`: capture rectangle as `left, top, right, bottom`.
- `vision.model`: path to the exported ONNX detector.
- `vision.weights`: trusted RF-DETR checkpoint used for on-demand export.
- `vision.variant`: RF-DETR architecture used during export.
- `vision.target_hz`: capture rate, normally 10-20 Hz.
- `sync.receptor_y`: receptor position inside the ROI.
- `sync.scroll_speed_px_s`: set a measured value, or leave it `null` to estimate it.
- `input.input_latency_s`: measured input latency compensation.
- `input.keymap`: lane-to-key mapping in [`config/keymap.yaml`](config/keymap.yaml).

To enable song/rate autodetection, select the Etterna installation folder in
the GUI. The bot checks the Etterna root for `nowplaying.txt` and the
related `nowplaying_title`, `nowplaying_artist`, `nowplaying_group`, and
`nowplaying_rate` files. The GUI watches those root-level files and updates
the chart and rate once per second. If your theme does not create them, select
the Songs folder and chart manually instead.

Detector labels must remain in training order in
[`config/classes.yaml`](config/classes.yaml). The current label map is
`arrow`, `receptor`. Place the default detector at `model.onnx` in the project
root; its companion `model.onnx.data` file must be beside it when the model
uses external ONNX data. Model files are intentionally ignored by Git; do not
load an untrusted checkpoint.

## Generating the ONNX model

Install the optional export dependencies:

```powershell
python -m pip install -e ".[test,windows,export]"
```

Then press **Generate ONNX** in the GUI after choosing a trusted checkpoint,
or run:

```powershell
python tools/export_onnx.py --weights weights.pt --output model.onnx --variant nano
```

The GUI export runs in a background thread and writes the configured model
path. Do not use untrusted PyTorch checkpoints; loading them can execute
arbitrary code.

## Launching the GUI

Use either command from the repository root:

```powershell
python -m bot.app.main --gui
python run_gui.py
```

The **Song & play** tab contains Etterna autodetection, chart browsing, rate,
steps type, and difficulty. The **Vision** tab contains the model, capture
backend, ROI, detector rate, input size, and confidence. Use **Pick ROI from
screen** to drag around the playfield; use **Pick receptor line** to click the
center of the receptor arrows in that ROI. The **Timing & keys**
tab contains receptor position, scroll speed, latency compensation, startup
delay, and lane keys. The startup delay is useful when you press Start before
Etterna begins the song; it delays the song-clock anchor rather than sending
the first chart event immediately. Choose an `.sm` or `.ssc` chart, set its
rate, and press **Arm / Start**.
Press **Stop** or F12 to stop and release scheduled input. The GUI is local
and offline; it does not submit scores or connect to online services.

For the first run:

1. Start StepMania/Etterna and select a fixed game resolution.
2. Set `vision.roi` to the playfield area, not the entire desktop.
3. Set `sync.receptor_y` and the four lane key mappings.
4. Launch the GUI and select the matching chart file.
5. Keep the game focused, then press **Arm / Start**.
6. Watch the status and logs. Press **Stop** or F12 immediately if the game
   loses focus or the detector behaves unexpectedly.

The command-line parser can also be checked without launching the GUI:

```powershell
python -m bot.app.main --config config/default.yaml --chart path\to\song.sm --rate 1.0
```

## Project checks

Run the offline test suite after changes:

```powershell
python -m pytest -q
```

## Terminal debugging

The GUI leaves the terminal open and logs chart/input activity there. A normal
GUI launch logs chart summaries, scheduler state, and every key event sent to
Windows:

```powershell
python run_gui.py
```

For detailed note parsing, vision locking, and scheduler timing, launch the GUI with verbose
logging:

```powershell
python -m bot.app.main --gui --verbose
```

Verbose output includes each parsed note (`song_t`, lane, and type), the number
and duration of scheduled events, vision sync samples, the moment the vision
clock locks, each event becoming due, and each Windows key-down/key-up attempt.
The bot sends no keys while it is in `LOCKING`; it must first see enough notes
in the configured ROI to match them to the chart. If the model cannot load,
the ROI is wrong, the receptor line is wrong, or a chart parses with zero
events, the terminal reports that explicitly.

The measurement entry points are available for later hardware validation:

```powershell
python tools/measure_capture.py --config config/default.yaml
python tools/calibrate_latency.py --config config/default.yaml
```

They currently report that their milestone-specific measurement workflow is
not yet configured for a real game/model session.

## Troubleshooting

- **`ModuleNotFoundError`**: activate `.venv` and rerun the install command.
- **GUI does not open**: run `python -m tkinter`; if that fails, reinstall
  Python with Tcl/Tk enabled.
- **No detections**: confirm the ONNX path, class order, ROI, and model input
  size. Start with CPU inference before trying a GPU provider.
- **Vision never locks**: run with `--verbose` and confirm the terminal shows
  arrows/receptors in `vision status`. Set `receptor_y`, or leave it at `0` to
  let a detected receptor bootstrap it. If Etterna starts after the bot,
  increase the GUI startup delay so provisional song time is close enough for
  the first visible notes to be matched.
- **DXCam reports `No module named 'cv2'`**: update the project installation;
  the bot now requests DXCam's NumPy processor, which avoids the OpenCV
  conversion path. The configured ROI is passed directly to DXCam.
- **Keys are early or late**: adjust `input.input_latency_s` using the
  calibration tool and keep the game at a fixed refresh rate.
- **The game is paused or unfocused**: stop the bot, refocus the game, and
  start a fresh run. Do not rely on stale scheduled events.

The bot is not intended for online score submission, evasion, or humanisation.
