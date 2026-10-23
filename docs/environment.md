# Environment

This project targets Windows 10/11 and uses screen capture only. Generate a
fresh machine report with:

```powershell
python -m screen_detector.config --check
```

Known target setup supplied for this migration:

- GPU: Intel Iris Xe
- Etterna: windowed
- Elevation: neither Etterna nor the bot is elevated by default
- GPU sharing: Etterna and inference share the same GPU
- Accuracy: prioritize detector accuracy; do not lower model resolution without
  measured validation evidence
- Detector scope: tap notes only
- Scroll speed and note-field height: must be estimated from captured frames;
  they are not fixed configuration assumptions

The command output is the source of truth for the installed Python version,
Windows build, display information, GPU discovery, ONNX Runtime providers,
elevation state, and configured Etterna window visibility. Hardware and game
state are intentionally not guessed by the application.

## Current observed report

On 2026-10-23, the command reported:

- Windows 11 build 26200
- Python 3.14.7
- Intel Iris Xe Graphics
- display metrics of 1440x960 from the primary Windows display
- no ONNX Runtime providers installed yet
- the current shell reported as elevated by Windows
- the configured `Etterna` window was not visible at check time

The elevation result describes the process that ran the check; it should be
verified again from the normal user session before input-injection testing.
