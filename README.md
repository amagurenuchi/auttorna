# RF-DETR Screen Control

Windows desktop prototype for live RF-DETR detection over a monitor or window, with optional debounced keyboard actions.

## Setup

Use the currently installed Python 3.14 runtime:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The app supports both monitor capture and window capture. Select `Window`, choose a visible window from the dropdown, and start detection. Use `Refresh` if the target window was opened after the app started. Capture defaults to Pillow's lightweight native Windows screen-grab path; set `capture.backend` to `mss` in `config.json` if you need the previous backend. `Apply mappings` saves all current settings to `config.json`, including capture selection, confidence, labels, and input mappings.

The current checkpoint is configured with the two detector labels `arrow` and `receptor`, uses `patch_size: 16`, and runs inference at the compatible 576px resolution. The app displays four GUI action rows: `Left`, `Down`, `Up`, and `Right`. Use `Set key` to capture a key, `Clear` to remove it, and `Test` to send one key press. When an arrow box overlaps a receptor box, the app estimates the arrow's visual orientation and sends the mapped directional key once for that overlap. Apply the mappings, then press `Arm input` to enable actions; press `Disarm input` or F12 to release held keys immediately.

Run with:

```powershell
python run.py
```

The app opens/uses an underlying terminal with timestamped debug logs. It reports the capture source, arrow/receptor overlaps, detected visual direction, selected key, and every key-down/key-up event. Keep that terminal open while diagnosing input behavior.

Press F12 at any time during capture to disable actions and release held keys.

## Low-latency backends

The current Windows target uses Intel Iris Xe graphics. The optional ONNX
Runtime DirectML provider and DXCam capture backend are supported:

```powershell
python -m pip install -r requirements.txt
python -m screen_detector.config --check
```

The installed ONNX providers should include `DmlExecutionProvider` and
`CPUExecutionProvider`. Set `inference_backend` to `directml` only after a
fixed-shape ONNX model has been exported and passed parity checks; the default
PyTorch path remains the safe reference path. Set `capture.backend` to `dxcam`
only after validating the configured ROI and display output.

Export and benchmark tools are available without committing generated model
files:

```powershell
python -m screen_detector.tools.export_onnx --weights weights.pt --output model.onnx
python -m screen_detector.tools.benchmark model.onnx --provider directml
```

The current DirectML benchmark for RF-DETR Nano on the target Iris Xe measures
about 105 ms p50 and 113 ms p99 at 384x384, so it still does not meet the 20 Hz target.
See `docs/inference_benchmark.md`; no resolution reduction is recommended
without an accuracy study.

Tap-note tracking and timestamp scheduling are implemented but not yet wired
into gameplay control; see `docs/tracking_scheduler.md`.

## Model weights

`weights.pt` is **not included in the repository** (it is gitignored) and must be obtained separately. Place it in the project root before running:

```
auttorna/
└── weights.pt   ← place here
```

> **Trust notice:** `weights.pt` is loaded by the RF-DETR PyTorch loader. Only use a checkpoint you trust; do not load untrusted `.pt` files.
