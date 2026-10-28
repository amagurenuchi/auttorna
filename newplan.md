# PLAN.md: StepMania/Etterna Hybrid Bot (rebuild)

## 0. Goal and scope
Rebuild the bot from scratch as a **chart-driven + vision-synced** auto-player for StepMania/Etterna.

- The chart file (`.sm`/`.ssc`) supplies the note schedule.
- A custom RF-DETR detector (kept from the old project) supplies **clock sync** and a **fallback** when sync is lost.
- **Offline use only**: local play, testing charts, latency experiments. No online score submission, no detection-evasion features, no "humanizer".
- Must run on **Windows** and use few resources: the vision loop must not starve the game.

## 1. Assumptions (edit if wrong)
- Python 3.11+, Windows 10/11, single machine running both game and bot.
- Existing trained RF-DETR weights are reused. Model classes are in `config/classes.yaml`; the agent must read the old training config to fill it in.
- Notes are detected per frame with bounding boxes. Columns are derived from x-position.
- Game runs windowed-borderless or fullscreen at a fixed resolution.
- Old code is **not** reused except the weights and the label map.

## 2. Tech choices
| Concern | Choice |
|---|---|
| Chart parsing/timing | `simfile` library (verify its timing engine handles BPMS/STOPS/DELAYS/WARPS; otherwise write `timing.py` and test against it) |
| Screen capture | `dxcam` (fallback `mss`); capture a cropped ROI only |
| Inference | RF-DETR exported to ONNX, run with `onnxruntime` (DirectML or CUDA provider if available); fixed small input size |
| Input | `SendInput` via `ctypes`, scan codes, in a dedicated thread |
| Timing | `time.perf_counter_ns`, `timeBeginPeriod(1)`, hybrid sleep + busy-wait |
| GUI | Minimal Tkinter (arm/disarm, chart picker, calibration sliders, status) |
| Config | YAML (`config/default.yaml`), loaded into typed dataclasses |
| Tests | `pytest`, plus an offline simulator |

## 3. Repo layout
```
bot/
  chart/        parser.py  timing.py  schedule.py
  vision/       capture.py  detector.py  tracker.py
  sync/         clock.py  matcher.py
  input/        scheduler.py  keys.py
  app/          controller.py  gui.py  main.py
  sim/          fake_clock.py  synthetic_frames.py  replay.py
  util/         perf.py  logging.py
config/         default.yaml  classes.yaml  keymap.yaml
tests/
tools/          calibrate_latency.py  measure_capture.py
PLAN.md
```

## 4. Core interfaces (define first, keep stable)
```python
@dataclass(frozen=True)
class NoteEvent:
    t: float            # seconds on the SONG clock
    col: int            # 0..keys-1
    kind: Literal["tap", "hold_start", "hold_end", "roll_start", "roll_end", "mine"]

@dataclass
class Detection:
    t_frame: float      # wall-clock seconds (perf_counter) when frame was captured
    col: int
    y: float            # note centre, pixels, in ROI space
    cls: str            # tap / hold / mine / ...
    conf: float

class ClockModel:       # song_time = a * wall_time + b
    def update(self, wall_t: float, song_t: float, weight: float) -> None: ...
    def song_to_wall(self, song_t: float) -> float: ...
    confidence: float   # 0..1
```

## 5. Milestones
Each milestone ends with its acceptance checks passing before the next begins. Commit after each.

### M0: Skeleton and config
- Create layout, `pyproject.toml`, pinned deps, logging, config loader.
- **Accept:** `python -m bot.app.main --help` runs; `pytest` collects.

### M1: Chart parsing and schedule
- Parse `.sm` and `.ssc`; select chart by steps type + difficulty.
- Convert rows to beats to seconds (OFFSET, BPMS, STOPS, DELAYS, WARPS). Emit sorted `NoteEvent`s. Warped notes are dropped.
- Support rate mod: `schedule.scaled(rate)`.
- **Accept:** unit tests with hand-computed timings for charts with BPM change, stop, delay, hold, roll, mine; a golden file for one real chart.

### M2: Input scheduler (no vision yet)
- Thread that takes `NoteEvent`s plus a `song_to_wall` function and fires key down/up at `wall_time − input_latency`.
- Holds release exactly at `hold_end`; rolls re-tap at a configured interval; mines never pressed.
- Hybrid wait: sleep until ~2 ms before the target, then busy-wait.
- Keymap from `keymap.yaml` (4-key default).
- **Accept:** simulator test with a fake clock shows p99 firing error < 1 ms of target; a real run against a Notepad-style key logger shows tap/hold durations match the schedule.

### M3: Capture and detector
- `capture.py`: ROI capture with `dxcam`, target 20 Hz, frame timestamp taken at capture time.
- `detector.py`: ONNX Runtime wrapper, fixed input size, batch 1, returns `Detection`s with column assignment from x.
- `tools/measure_capture.py`: reports capture + inference latency and CPU/GPU use.
- **Accept:** detector reproduces the old model's accuracy on a saved validation set; end-to-end capture+inference p95 < 30 ms at 20 Hz; CPU use under 15% of one core budget on the target machine (record the numbers).

### M4: Tracker and scroll-speed estimate
- Track detections across frames per column; estimate note velocity (px/s) from successive frames; keep a running scroll-speed estimate (fixed if the config provides it).
- **Accept:** on recorded footage, velocity is stable within 3% across a song; tracker survives dropped frames.

### M5: Clock sync
- `matcher.py`: for each tracked note, predict wall arrival `t_frame + (y_receptor − y) / v`, match it to the nearest scheduled event in the same column within a window, and emit an error sample.
- `clock.py`: robust filter over samples (median gating, then EMA or a small Kalman over offset and drift). Output `ClockModel` with confidence.
- Initial lock from the first N notes; relock when confidence drops.
- **Accept:** in the simulator with injected offset, drift and jitter, the clock converges within 500 ms and error stays < 3 ms; with a 5% outlier rate it still holds.

### M6: Hybrid controller
- `controller.py` wires chart, capture, detector, tracker, sync and scheduler.
- States: `IDLE → ARMED → LOCKING → RUNNING → DEGRADED → STOPPED`.
- `DEGRADED` (low confidence): fall back to vision-only hits for visible notes near the receptor and keep trying to relock.
- Vision rate adapts: lower it when confidence is high, raise it when low.
- **Accept:** a full-song run in the game completes with the controller reaching `RUNNING` and logging sync residuals; forced desync (pausing the game for 2 s) recovers.

### M7: GUI
- Tkinter: chart picker, rate-mod field, arm/start/stop, latency calibration sliders (input and display), live status (state, confidence, residual, fps).
- GUI never blocks the scheduler thread.
- **Accept:** all controls work during a run; closing the window stops the bot cleanly and releases all keys.

### M8: Calibration, logging, hardening
- `tools/calibrate_latency.py`: measure input-to-screen latency using a test chart and detections.
- Per-run log: residual histogram, jitter histogram, state transitions, dropped frames.
- Failsafes: global hotkey to stop and release all keys; auto-release on exceptions; refuse to run if the game window is not focused.
- **Accept:** documented calibration procedure in `README`; failsafe tests pass.

## 6. Performance budgets
| Item | Budget |
|---|---|
| Capture + inference per frame | p95 < 30 ms |
| Vision rate | 10–20 Hz adaptive |
| Scheduler firing error | p99 < 1 ms |
| Clock error when locked | < 3 ms |
| Bot CPU use | measured and recorded at M3 and M6 |

If the budgets cannot be met, reduce ROI size and model input size first.

## 7. Testing strategy
- **Unit:** parser, timing math, filter, matcher, keymap.
- **Simulator:** fake clock plus synthetic frames of falling notes (with configurable offset, drift, jitter, dropped frames) driving the same controller code path.
- **Integration:** short real chart in the game, logs reviewed per milestone.
- Every bug found gets a regression test.

## 8. Risks and mitigations
- Timing library gaps (warps, delays): own tests, fall back to custom timing.
- Rate mods and scroll mods (`#SPEEDS`, `#SCROLLS`, player speed mods): detect via scroll-speed estimate, not by assuming.
- Display/input latency variation: calibration tool and sliders.
- Vision failures: `DEGRADED` mode.
- Python GIL contention: scheduler in its own thread with minimal work; heavy inference in a separate process if jitter shows up.

## 9. Agent working rules
- Work milestone by milestone; do not start the next until acceptance checks pass.
- Define and keep the interfaces in section 4; propose changes before making them.
- Write tests with the code, not after.
- Keep modules small, typed, and documented with short docstrings.
- Record measured numbers (latency, CPU, residuals) in `docs/measurements.md` after M3, M5 and M6.
- Ask before adding dependencies not listed in section 2.
