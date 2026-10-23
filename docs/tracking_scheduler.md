# Tracking and scheduling status

The Phase 5/6 foundation is implemented for the current tap-note detector:

- `screen_detector.tracking.NoteTracker` associates arrow detections to lane
  bounds, persists note IDs, estimates downward motion, and learns receptor Y
  from receptor detections.
- `HitTimePredictor` calculates target timestamps from receptor position,
  observed/configured scroll speed, capture time, pipeline latency, and global
  offset. Each track is marked scheduled exactly once.
- `screen_detector.control.Scheduler` orders events by target timestamp, waits
  with a sleep-then-spin strategy, clears events on disarm, and auto-disarms
  after stale capture timestamps.
- `SendInputBackend` uses scan-code `SendInput` on Windows and supports grouped
  simultaneous events.
- `GlobalKillSwitch` provides the dedicated `RegisterHotKey` hook.

The GUI still uses the legacy overlap strategy. Predictive scheduling is not
enabled in gameplay yet because the model has not passed parity/accuracy
validation and DirectML is currently below the target inference rate.

Holds, mines, and scroll stops/changes are surfaced as unsupported tracker
states. The trained model currently supports tap notes only.
