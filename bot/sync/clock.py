"""Affine song-clock model: song_time = a * wall_time + b."""

from dataclasses import dataclass


@dataclass
class ClockModel:
    """Small, dependency-free clock model used as the M0 contract."""

    a: float = 1.0
    b: float = 0.0
    confidence: float = 0.0

    def update(self, wall_t: float, song_t: float, weight: float) -> None:
        """Apply a conservative weighted offset update."""
        if weight <= 0:
            return
        error = song_t - self.song_at(wall_t)
        alpha = min(1.0, max(0.0, weight))
        self.b += alpha * error
        self.confidence = min(1.0, self.confidence + alpha * (1.0 - self.confidence))

    def reset(self) -> None:
        self.a, self.b, self.confidence = 1.0, 0.0, 0.0

    def song_at(self, wall_t: float) -> float:
        return self.a * wall_t + self.b

    def song_to_wall(self, song_t: float) -> float:
        if self.a == 0:
            raise ZeroDivisionError("clock slope cannot be zero")
        return (song_t - self.b) / self.a
