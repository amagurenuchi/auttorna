from screen_detector.timing import TimingRecorder


def test_timing_stats_are_bounded_and_percentiled():
    recorder = TimingRecorder(max_samples=3)
    recorder.record("capture", 0, 1_000_000)
    recorder.record("capture", 0, 3_000_000)
    recorder.record("capture", 0, 2_000_000)
    recorder.record("capture", 0, 4_000_000)
    stats = recorder.stats("capture")
    assert stats["count"] == 3
    assert stats["p50_ms"] == 3.0
    assert stats["p99_ms"] == 3.98


def test_timing_csv_export(tmp_path):
    recorder = TimingRecorder()
    recorder.record("inference", 10, 20)
    output = tmp_path / "timing.csv"
    recorder.write_csv(output)
    assert "stage,started_ns,ended_ns,duration_ns" in output.read_text()
