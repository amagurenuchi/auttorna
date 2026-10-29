from bot.model import Detection, NoteEvent
from bot.sync.matcher import match_detection
from bot.sync.estimator import SyncEstimator


def test_matcher_and_outlier_gate():
    event = NoteEvent(2.0, 1, "tap")
    sample = match_detection(Detection(1.5, 1, 50, "arrow", 1), [event], 100, 100)
    assert sample and sample.song_t == 2.0
    estimator = SyncEstimator(gate_s=0.01)
    assert estimator.update(sample)
    assert abs(estimator.clock.song_at(sample.wall_t) - sample.song_t) < 1e-9
    assert not estimator.update(type(sample)(10, 2, 0, event))
