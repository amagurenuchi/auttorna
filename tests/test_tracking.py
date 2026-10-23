from screen_detector.model import Detection
from screen_detector.tracking import HitTimePredictor, NoteTracker


def arrow(y: float, x: float = 10.0) -> Detection:
    return Detection((x - 4, y - 5, x + 4, y + 5), 0.95, 0, "arrow")


def receptor(y: float, x: float = 10.0) -> Detection:
    return Detection((x - 8, y - 4, x + 8, y + 4), 0.99, 1, "receptor")


def test_tracker_persists_note_and_estimates_speed():
    tracker = NoteTracker([(0, 30)], match_distance_px=40)
    first = tracker.update([arrow(100), receptor(300)], 1_000_000_000)
    second = tracker.update([arrow(120), receptor(300)], 1_100_000_000)
    assert len(second.tracks) == 1
    assert second.tracks[0].note_id == first.tracks[0].note_id
    assert 190 < second.scroll_speed_px_s < 210
    assert second.receptor_y == 300


def test_predictor_schedules_each_tap_once():
    tracker = NoteTracker([(0, 30)], match_distance_px=40)
    tracker.update([arrow(100), receptor(300)], 1_000_000_000)
    result = tracker.update([arrow(120), receptor(300)], 1_100_000_000)
    predictor = HitTimePredictor(pipeline_latency_ns=10_000_000)
    events = predictor.predict(result, 1_200_000_000)
    assert len(events) == 1
    assert events[0].target_ns == 1_200_000_000 + 900_000_000 - 10_000_000
    assert predictor.predict(result, 1_300_000_000) == []


def test_tracker_flags_unsupported_classes():
    tracker = NoteTracker([(0, 30)])
    result = tracker.update([Detection((0, 10, 10, 20), 1.0, 2, "mine")], 1)
    assert result.unsupported == ("unsupported detection class: mine",)
