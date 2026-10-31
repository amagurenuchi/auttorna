"""Per-column tracking and scroll-speed estimation."""

from dataclasses import dataclass
from collections import deque
from typing import Iterable

from bot.model import Detection


@dataclass(frozen=True)
class Track:
    col: int
    y: float
    velocity: float
    last_t: float
    # Estimated wall-clock crossing time at the receptor.  This is derived
    # from several frames, never from a model-provided timestamp.
    fit_intercept: float | None = None


class Tracker:
    def __init__(self) -> None:
        self.tracks: dict[int, Track] = {}
        self.history: dict[int, deque[tuple[float, float]]] = {}
        self.scroll_speed = 0.0

    def update(self, detections: Iterable[Detection]) -> list[Track]:
        result = []
        for detection in detections:
            previous = self.tracks.get(detection.col)
            velocity = previous.velocity if previous else 0.0
            points = self.history.setdefault(detection.col, deque(maxlen=6))
            if previous and detection.t_frame > previous.last_t:
                velocity = (detection.y - previous.y) / (detection.t_frame - previous.last_t)
                self.scroll_speed = 0.8 * self.scroll_speed + 0.2 * abs(velocity)
            points.append((detection.t_frame, detection.y))
            # Fit y = a*t+b over the recent trajectory.  A fit is much less
            # sensitive to detector jitter than the current-frame velocity.
            fit_intercept = None
            if len(points) >= 3:
                mean_t = sum(point[0] for point in points) / len(points)
                mean_y = sum(point[1] for point in points) / len(points)
                denominator = sum((t - mean_t) ** 2 for t, _ in points)
                if denominator > 1e-12:
                    slope = sum((t - mean_t) * (y - mean_y) for t, y in points) / denominator
                    intercept = mean_y - slope * mean_t
                    # The receptor coordinate is supplied later; keep the
                    # fitted line in the track via its slope/intercept data.
                    velocity = slope
                    fit_intercept = intercept
            current = Track(detection.col, detection.y, velocity, detection.t_frame, fit_intercept)
            self.tracks[detection.col] = current
            result.append(current)
        return result

    def arrival_at(self, track: Track, receptor_y: float) -> float | None:
        """Return the fitted time at which *track* reaches receptor_y."""
        if track.fit_intercept is None or abs(track.velocity) < 1e-9:
            if abs(track.velocity) < 1e-9:
                return None
            return track.last_t + (receptor_y - track.y) / track.velocity
        return (receptor_y - track.fit_intercept) / track.velocity
