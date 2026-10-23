# Baseline

The Phase 1 timing recorder is integrated into the existing GUI worker path.
It records bounded samples for capture, inference, orientation, and input and
can export them with `TimingRecorder.write_csv()`.

No representative latency numbers are recorded yet. A valid baseline requires:

- the trusted `weights.pt` checkpoint;
- a visible, windowed Etterna session;
- a configured target window and detector labels;
- a repeatable capture interval long enough to produce p50/p95/p99 values;
- CPU and GPU utilization measurements during that run.

Until those prerequisites are available, performance claims must not be made.
