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

Press F12 at any time during capture to disable actions and release held keys. `weights.pt` is trusted by the local RF-DETR loader; do not load untrusted PyTorch checkpoints.
