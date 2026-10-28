"""Robust clock estimator with median gating and EMA offset updates."""

from collections import deque

from bot.sync.clock import ClockModel
from bot.sync.matcher import ClockSample


class SyncEstimator:
    def __init__(self, *, gate_s: float = 0.05, history: int = 21, alpha: float = 0.2) -> None:
        self.clock = ClockModel()
        self.gate_s, self.alpha = gate_s, alpha
        self.samples: deque[ClockSample] = deque(maxlen=history)

    def update(self, sample: ClockSample) -> bool:
        if self.samples:
            offsets = sorted(item.wall_t - item.song_t for item in self.samples)
            median = offsets[len(offsets) // 2]
            if abs((sample.wall_t - sample.song_t) - median) > self.gate_s:
                return False
        self.samples.append(sample)
        self.clock.update(sample.wall_t, sample.song_t, self.alpha)
        return True
