from bot.model import Detection, NoteEvent
from bot.sync.matcher import match_detection


def test_matcher_uses_provisional_song_clock_for_bootstrap():
    event = NoteEvent(2.0, 0, "tap")
    detection = Detection(101.0, 0, 50.0, "arrow", 0.9)
    sample = match_detection(detection, [event], 100.0, 100.0,
                             wall_to_song=lambda wall: wall - 99.0, window_s=0.6)
    assert sample is not None
    assert sample.song_t == 2.0
