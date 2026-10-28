"""Per-column tracking and scroll-speed estimation."""

from dataclasses import dataclass
from typing import Iterable

from bot.model import Detection


@dataclass(frozen=True)
class Track:
    col: int
    y: float
    velocity: float
    last_t: float


class Tracker:
    def __init__(self) -> None:
        self.tracks: dict[int, Track] = {}
        self.scroll_speed = 0.0

    def update(self, detections: Iterable[Detection]) -> list[Track]:
        result = []
        for detection in detections:
            previous = self.tracks.get(detection.col)
            velocity = previous.velocity if previous else 0.0
            if previous and detection.t_frame > previous.last_t:
                velocity = (detection.y - previous.y) / (detection.t_frame - previous.last_t)
                self.scroll_speed = 0.8 * self.scroll_speed + 0.2 * abs(velocity)
            current = Track(detection.col, detection.y, velocity, detection.t_frame)
            self.tracks[detection.col] = current
            result.append(current)
        return result
