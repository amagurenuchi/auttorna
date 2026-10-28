from bot.model import Detection, NoteEvent
from bot.sync.clock import ClockModel


def test_core_contracts_and_clock_round_trip():
    event = NoteEvent(1.25, 2, "tap")
    detection = Detection(10.0, 2, 100.0, "arrow", 0.9)
    assert event.col == detection.col

    clock = ClockModel()
    clock.update(10.0, 12.0, 1.0)
    assert clock.song_to_wall(12.0) == 10.0
    assert clock.confidence == 1.0
