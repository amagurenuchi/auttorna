from bot.model import Detection
from bot.vision.tracker import Tracker


def test_tracker_estimates_crossing_from_multiple_frames():
    tracker = Tracker()
    # y = 100*t - 100, so y=100 at t=2.0.
    for t in (0.0, 0.1, 0.2, 0.3):
        tracks = tracker.update([Detection(t, 0, 100 * t - 100, "arrow", 0.99)])
    assert tracks
    assert abs(tracker.arrival_at(tracks[-1], 100.0) - 2.0) < 1e-9


def test_matcher_does_not_reuse_a_chart_event():
    from bot.model import NoteEvent
    from bot.sync.matcher import match_detection

    event = NoteEvent(2.0, 0, "tap")
    used = {(event.t, event.col, event.kind)}
    assert match_detection(Detection(2.0, 0, 0, "arrow", 1.0), [event], 0, 100,
                           used_events=used) is None


def test_matcher_rejects_chart_events_before_previous_match():
    from bot.model import NoteEvent
    from bot.sync.matcher import match_detection

    events = [NoteEvent(1.0, 0, "tap"), NoteEvent(2.0, 0, "tap")]
    assert match_detection(Detection(1.0, 0, 0, "arrow", 1.0), events, 0, 100,
                           min_song_t=2.0) is None


def test_sequence_alignment_does_not_need_a_provisional_clock():
    from bot.model import NoteEvent
    from bot.sync.matcher import ArrowObservation, align_observations

    events = [NoteEvent(1.0, 0, "tap"), NoteEvent(1.5, 1, "tap"),
              NoteEvent(2.0, 0, "tap"), NoteEvent(2.5, 1, "tap")]
    observations = [ArrowObservation(t + 10.0, col) for t, col in
                    ((1.0, 0), (1.5, 1), (2.0, 0), (2.5, 1))]
    alignment = align_observations(observations, events)
    assert alignment is not None
    assert abs(alignment.offset - 10.0) < 1e-9


