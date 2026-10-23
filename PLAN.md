# PLAN: Low-latency vision pipeline for the StepMania/Etterna bot (Windows)

> Hand this file to the IDE agent as the task brief. Work phase by phase. Do not start a phase until the previous phase's acceptance criteria pass.
> Target platform: **Windows 10/11 only** (no Linux/Wayland code paths in this plan).

## 0. Context

- We already have: a custom-trained **RF-DETR** note detector and a small **GUI** (input arming + process start).
- Goal: the detector must "see" notes **early enough** to press on time, while using **as few CPU/GPU resources as possible** (the game runs on the same machine).
- Scope: single-player / offline use and research. Do not wire this to online leaderboards or score submission.
- **Vision-only scope (decided).** Runtime decisions come solely from screen capture and the detector. Do **not** parse chart files (.sm/.ssc), read game memory, or add a Lua/theme hook for song position in this milestone. Chart data may be used **offline** only for calibration, tests, and detector evaluation (Phases 5 and 8). A hybrid chart-synced mode is a possible future milestone, not part of this plan.

## 1. Core design principles

1. **Predict, don't react.** Notes scroll at constant speed. Detect them while they are still far from the receptors, estimate hit time, and schedule the keypress. Do not wait for a note to reach the receptor.
2. **Jitter is the enemy, not constant delay.** A fixed latency is calibrated out with one offset constant. Optimize p99 latency and timing variance, not the mean.
3. **Latest frame only.** No frame queues anywhere. A single-slot buffer that overwrites stale frames.
4. **Crop, shrink, fix shapes.** ROI-only capture, low fixed input resolution, batch size 1, no dynamic shapes.
5. **Hide platform-specific pieces behind interfaces** (capture, inference runtime, input injection) so backends can be swapped and benchmarked.

## 2. Windows-specific constraints (read before coding)

- **Game display mode:** run Etterna in **windowed or borderless fullscreen**. Desktop Duplication / Windows Graphics Capture generally cannot capture exclusive fullscreen reliably.
- **Elevation (UIPI):** if the game runs as administrator, the bot's input injector must also run as administrator, or keypresses are silently dropped.
- **Input injection:** use `SendInput` with **scan codes** (`KEYEVENTF_SCANCODE`). Virtual-key-only events are ignored by many games. Call it via `ctypes` directly or use `pydirectinput` as a reference.
- **Timer resolution:** the default Windows timer tick is ~15.6 ms. Use a high-resolution waitable timer (`CreateWaitableTimerExW` with `CREATE_WAITABLE_TIMER_HIGH_RESOLUTION`, Windows 10 1803+) or `timeBeginPeriod(1)`, then spin-wait the final ~0.5-1 ms. Python 3.11+ `time.sleep` already uses a high-resolution timer on Windows; verify on the target Python version.
- **Clock:** `time.perf_counter_ns()` maps to QueryPerformanceCounter. Use it for every timestamp.
- **Priority and power:** raise the scheduler process to `HIGH_PRIORITY_CLASS` (never `REALTIME`), the scheduler thread to `TIME_CRITICAL`, and opt the bot out of Windows 11 **EcoQoS / power throttling** (`SetProcessInformation` with `ProcessPowerThrottling`). A minimized or background GUI process can otherwise be throttled. Recommend the High/Ultimate Performance power plan and Game Mode on.
- **Compositor latency:** captures come from the DWM-composed desktop, which can add up to a frame versus what the game rendered. Measure it with a test pattern (Phase 8) instead of assuming.

## 3. Target architecture

```
[Capture thread/proc] -> latest-frame slot (shared memory, timestamped)
        |
[Inference proc]  preprocess -> model (ONNX Runtime EP / TensorRT / OpenVINO) -> detections
        |
[Tracker/Predictor]  per-lane association -> note IDs -> t_hit estimates
        |
[Scheduler]  priority queue of (t_hit, lane, action) -> high-res timer -> SendInput
        |
[GUI]  arm/disarm, start/stop, live stats, global kill-switch hotkey
```

Timestamps are taken **at capture time** and carried through the whole pipeline.

## 4. Suggested repo layout

```
bot/
  config.py              # loads config.yaml, validates
  config.yaml            # ROI, scroll speed, refresh rate, offsets, backend choices
  timing.py              # stage timers, histograms, CSV export
  winutil.py             # priority, EcoQoS opt-out, high-res timer, admin check
  capture/
    base.py              # Capture interface: grab() -> (frame, t_capture_ns)
    dxcam_backend.py     # Desktop Duplication (primary)
    wgc_backend.py       # Windows Graphics Capture (alternative, per-window)
  inference/
    base.py              # Detector interface: infer(frame) -> list[Detection]
    export_onnx.py       # RF-DETR -> ONNX
    ort_backend.py       # ONNX Runtime: CUDA / DirectML / OpenVINO / CPU providers
    trt_backend.py       # TensorRT (optional, NVIDIA)
    preprocess.py
  tracking/
    tracker.py           # lane association, dedupe, hold head/tail
    predictor.py         # hit-time estimation
  control/
    scheduler.py         # priority queue + precise timer
    input_sendinput.py   # SendInput scan-code backend
    hotkey.py            # global kill switch (RegisterHotKey)
  tools/
    benchmark.py         # per-stage + end-to-end benchmarks
    calibrate.py         # offset calibration
    parity_check.py      # PyTorch vs exported model comparison
  gui/                   # existing GUI, integrate via a thin controller API
tests/
```

Adapt to the existing repo structure rather than forcing this layout. Reuse existing code where it already does the job.

## 5. Phases

### Phase 0: Recon and config

Tasks:

- Inspect the repo: locate the GUI, the model weights/loading code, current capture and input code, dependencies, and Python version.
- Create `config.yaml` with: `roi` (x, y, w, h), `lanes` (count and x-bounds), `receptor_y`, `scroll_speed_px_per_s` (or a way to measure it), `display_refresh_hz`, `global_offset_ms`, `capture_backend`, `inference_backend`, `lane_scancodes`.
- Detect and print: Windows version, Python version, GPU vendor/model and driver, installed ONNX Runtime providers, display refresh rate, whether the process is elevated. Write them to `docs/environment.md`.
- List unknowns the user must fill in. Do not guess hardware.

Acceptance: `python -m bot.config --check` validates the config and prints the environment summary.

### Phase 1: Instrumentation first

Tasks:

- Implement `timing.py`: context-manager stage timers using `perf_counter_ns`, ring-buffer histograms, p50/p95/p99, CSV dump.
- Instrument existing code paths (capture, preprocess, inference, postprocess) before changing anything, to get a baseline.
- Record CPU and GPU utilization during the baseline (Task Manager counters, `psutil`, `nvidia-smi`/vendor tools as available).
- Optionally show live p50/p99 in the GUI.

Acceptance: a baseline report in `docs/baseline.md` with per-stage p50/p95/p99 and CPU/GPU utilization.

### Phase 2: Capture backend (Windows)

Tasks:

- Define the `Capture` interface. Return the frame **and its capture timestamp**.
- Implement `dxcam` (Desktop Duplication) as the primary backend, **region-limited to the ROI**, using its latest-frame mode (`start(region=..., target_fps=...)` + `get_latest_frame()`). Implement Windows Graphics Capture as an alternative (useful for per-window capture or if Desktop Duplication misbehaves with the user's display setup).
- Confirm behavior with the game in windowed/borderless mode and document any multi-monitor or HDR caveats found (HDR/color-format issues can break color-based detections; the model must see the same format it was trained on).
- Implement the single-slot latest-frame buffer using shared memory so the inference process reads without copying through pipes.
- Make capture rate independent from inference rate.

Acceptance: capture p99 stays below a fraction of one display frame time at the configured ROI. No growth in memory or latency over a 10-minute run.

### Phase 3: Model export and inference backends

Tasks:

- Export RF-DETR to ONNX with fixed input shape. Pick the smallest resolution that preserves accuracy; if needed retrain/fine-tune at that resolution and report it.
- Write `parity_check.py` comparing exported-model detections vs PyTorch on a validation set (IoU-matched, report mAP drop and count mismatches).
- Implement `ort_backend.py` with provider selection by hardware:
  - **NVIDIA:** CUDA execution provider, or TensorRT EP / native TensorRT with FP16 for lowest latency.
  - **AMD / Intel / any DX12 GPU:** DirectML execution provider (`onnxruntime-directml`). Set `enable_mem_pattern=False` and sequential execution as the ORT DirectML docs require, and use fixed shapes. Verify against current ORT docs that DirectML is still the recommended path for the installed version.
  - **Intel CPU/iGPU:** OpenVINO execution provider.
  - **Fallback:** CPU provider.
- Warm up before use. Pin batch size to 1. Prefer FP16. Treat INT8 as optional and verify accuracy separately (transformer detectors can degrade under INT8).
- Write `benchmark.py` comparing providers on the same inputs and recording latency distributions.

Acceptance: chosen backend meets the inference budget in `config.yaml` (default target: stable >= 20 Hz inference with p99 below the lookahead margin) and parity check is within agreed tolerance.

### Phase 4: Preprocess optimization

Tasks:

- Do crop/resize/normalize in one fused path with preallocated buffers (GPU-side if the backend supports it; otherwise a single optimized CPU path with OpenCV).
- Eliminate per-frame allocations and unnecessary copies or colorspace conversions (match the BGR/RGB order the model expects once, at the edge).

Acceptance: preprocess p99 is a small fraction of inference time; allocation count per frame is zero in steady state.

### Phase 5: Tracker and hit-time predictor

Tasks:

- Associate detections to existing notes per lane (nearest-neighbor on y, gated by expected motion). Assign persistent IDs so each note triggers exactly one action.
- Estimate scroll speed from tracked motion (or use the configured value) and compute `t_hit = t_capture + (receptor_y - y) / speed - pipeline_latency + global_offset`.
- Smooth `t_hit` estimates across frames (running average or Kalman) so one noisy detection does not move the press time.
- Handle hold notes (head and tail tracked separately, release scheduled from the tail) and mines (never pressed).
- Handle scroll-speed changes or stops if the chart uses them. Flag unsupported cases explicitly instead of failing silently.

Acceptance: unit tests with synthetic detection streams (including dropped detections, false positives, and jitter) show each note scheduled exactly once with bounded `t_hit` error.

### Phase 6: Scheduler and input injection (Windows)

Tasks:

- Implement a priority queue keyed by `t_hit`. Sleep with the high-resolution waitable timer until ~0.5-1 ms before the target, then spin-wait.
- Implement `input_sendinput.py`: `SendInput` with scan codes per lane (`lane_scancodes` in config), `press`/`release` only. Batch simultaneous lanes (jumps/hands) into a single `SendInput` call so they land together.
- Implement `winutil.py`: priority class, thread priority, EcoQoS opt-out, admin detection (warn loudly if the game process is elevated and the bot is not).
- Add safety: armed/disarmed state, a **global kill-switch hotkey** (`RegisterHotKey` on a dedicated message-loop thread), auto-disarm if the pipeline stalls (no fresh frames for N ms), and clear the queue plus release all held keys on disarm.
- Measure press-time error: scheduled vs actually issued timestamps.

Acceptance: issued-vs-scheduled error p99 within a tight bound (target well under 1 ms of scheduling jitter on the test machine). Kill switch verified to stop all output and release held keys immediately.

### Phase 7: Process architecture and GUI integration

Tasks:

- Run capture, inference, and scheduler as separate processes (or native threads) so the Python GIL does not add jitter. On Windows use `multiprocessing` with the `spawn` start method and `multiprocessing.shared_memory` for frames; keep the entry point guarded by `if __name__ == "__main__":`.
- Expose a controller API to the existing GUI: `start()`, `stop()`, `arm()`, `disarm()`, `get_stats()`.
- Set CPU affinity where useful (`psutil`), keeping the scheduler core away from the game's render thread if cores are scarce.
- Make shutdown clean (no orphaned processes, no stuck keys), including when the GUI is force-closed.

Acceptance: GUI start/stop/arm/disarm work repeatedly without leaks; no stuck keys after crash tests.

### Phase 8: Calibration

Tasks:

- Build `calibrate.py` that plays a known chart (or a synthetic test pattern) and collects timing offsets of the bot's presses against ground-truth note times. Include a visual test pattern to measure capture-to-screen latency including DWM compositing.
- Compute mean and standard deviation, then write `global_offset_ms` to config.
- Support importing judgment offsets from game replay/evaluation data if accessible, and document how to do the manual version.

Acceptance: after calibration, mean offset is near zero and spread is within the target; results saved in `docs/calibration.md`.

### Phase 9: Resource budget and adaptive behavior

Tasks:

- Profile CPU, GPU, and memory during real play. Record results next to the baseline.
- Add optional adaptive inference rate (lower rate when no notes are in the lookahead window, higher during dense sections) and frame skipping under load.
- If the game and model contend for the same GPU, document mitigations: cap game FPS and lower its graphics settings, run inference on a different device (e.g. iGPU via DirectML/OpenVINO while a dGPU runs the game), or use a second machine with a capture card.
- Check the GPU scheduling situation: Hardware-accelerated GPU scheduling on/off and Windows power plan effects, and report which setting gives the lowest jitter.

Acceptance: documented resource usage within agreed limits; no dropped game frames attributable to the bot during a full chart.

### Phase 10: Hardening and docs

Tasks:

- Tests for the tracker, scheduler, config validation; smoke tests for each backend available on the machine.
- README covering Windows setup (Python version, drivers, ORT package choice), config fields, calibration steps, and troubleshooting (elevation, exclusive fullscreen, HDR, multi-monitor).
- Pin dependency versions and document the supported runtime matrix. Optionally package with PyInstaller once stable.

## 6. Working rules for the agent

- Make small, reviewable commits per task. Run the benchmark after any change touching the hot path and report the delta.
- **Measure before optimizing.** Every optimization needs a before/after number from `timing.py`.
- Do not modify or retrain model weights unless a task explicitly says so. Do not commit large binaries (weights, ONNX files, captures); use `.gitignore` and document where to obtain them.
- Never add unbounded queues or logging in the hot path.
- Keep platform-specific code behind the interfaces above. If a backend can't be tested on the current machine, say so explicitly rather than claiming it works.
- When something is ambiguous (hardware, scroll speed, resolution), stop and ask rather than guessing.

## 7. Open questions for the user

1. Which GPU (NVIDIA / AMD / Intel iGPU only) is in the Windows machine? This decides the ONNX Runtime provider (CUDA/TensorRT vs DirectML vs OpenVINO).
2. Does Etterna run windowed/borderless, and does it run elevated (as administrator)?
3. Display refresh rate and the scroll speed/note-field height used during play.
4. Should the game and bot share one GPU, or is a second device available for inference?
5. Is a lower input resolution acceptable if mAP drops slightly?
6. Are hold notes, mines, and scroll-speed changes in scope for the first milestone?
