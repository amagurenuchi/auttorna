from screen_detector.model import Detection
from screen_detector.pipeline import DryRunBackend, VisionPipeline


def test_dry_run_pipeline_predicts_tap_without_keyboard_output():
    pipeline = VisionPipeline([(0, 30)], receptor_y=300, scroll_speed_px_s=None)
    first = [Detection((10, 95, 20, 105), 0.9, 0, "arrow")]
    second = [Detection((10, 115, 20, 125), 0.9, 0, "arrow")]
    assert pipeline.update(first, 1_000_000_000) == []
    events = pipeline.update(second, 1_100_000_000)
    assert len(events) == 1
    assert events[0].lane == 0

    backend = DryRunBackend()
    assert backend.events == []
    backend.send_actions([(events[0].lane, None, "press")])
    assert backend.events == [(0, None, "press")]
