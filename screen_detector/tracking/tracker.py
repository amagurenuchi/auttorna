from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from ..model import Detection


@dataclass
class NoteTrack:
    note_id: int
    lane: int
    y: float
    x: float
    width: float
    height: float
    confidence: float
    first_seen_ns: int
    last_seen_ns: int
    velocity_px_s: float | None = None
    missed_frames: int = 0
    scheduled: bool = False
    unsupported_reason: str | None = None

    @property
    def age_ns(self) -> int:
        return self.last_seen_ns - self.first_seen_ns


@dataclass(frozen=True)
class TrackingResult:
    tracks: tuple[NoteTrack, ...]
    receptor_y: float | None
    scroll_speed_px_s: float | None
    unsupported: tuple[str, ...] = ()


class NoteTracker:
    """Associates arrow detections to persistent tap-note tracks.

    Lanes are supplied as x bounds in capture/ROI coordinates. Association is
    nearest-neighbour on predicted y within a motion gate; stale tracks are
    retained briefly to survive a dropped detector frame.
    """

    def __init__(self, lanes: list[tuple[int, int]], max_missed_frames: int = 4, match_distance_px: float = 80.0, velocity_smoothing: float = 0.35) -> None:
        if not lanes:
            raise ValueError("at least one lane bound is required")
        if not 0 < velocity_smoothing <= 1:
            raise ValueError("velocity_smoothing must be in (0, 1]")
        self.lanes = lanes
        self.max_missed_frames = max_missed_frames
        self.match_distance_px = match_distance_px
        self.velocity_smoothing = velocity_smoothing
        self._tracks: dict[int, NoteTrack] = {}
        self._next_id = 1
        self._receptor_y: float | None = None
        self._last_scroll_speed: float | None = None

    @property
    def tracks(self) -> tuple[NoteTrack, ...]:
        return tuple(self._tracks.values())

    def lane_for_x(self, x: float) -> int | None:
        for index, (left, right) in enumerate(self.lanes):
            if left <= x <= right:
                return index
        return None

    @staticmethod
    def _center(box: tuple[float, float, float, float]) -> tuple[float, float, float, float, float]:
        x1, y1, x2, y2 = box
        return (x1 + x2) / 2, (y1 + y2) / 2, max(0.0, x2 - x1), max(0.0, y2 - y1), y2 - y1

    def update(self, detections: list[Detection], captured_at_ns: int, receptor_label: str = "receptor", note_label: str = "arrow") -> TrackingResult:
        arrows = []
        receptors = []
        unsupported: list[str] = []
        for detection in detections:
            label = detection.label.lower()
            if label == note_label.lower():
                center_x, center_y, width, height, _ = self._center(detection.box)
                lane = self.lane_for_x(center_x)
                if lane is not None:
                    arrows.append((lane, center_x, center_y, width, height, detection))
            elif label == receptor_label.lower():
                receptors.append(self._center(detection.box)[1])
            elif label in {"hold", "mine"}:
                unsupported.append(f"unsupported detection class: {label}")

        if receptors:
            self._receptor_y = sum(receptors) / len(receptors)

        unmatched = set(self._tracks)
        assignments: list[tuple[NoteTrack, tuple[int, float, float, float, float, Detection]]] = []
        assigned_arrow_indexes: set[int] = set()
        for arrow_index, arrow in sorted(enumerate(arrows), key=lambda item: item[1][2]):
            lane, _, y, *_ = arrow
            candidates = [self._tracks[index] for index in unmatched if self._tracks[index].lane == lane]
            if not candidates:
                continue
            def distance(track: NoteTrack) -> float:
                elapsed_s = max(0.0, (captured_at_ns - track.last_seen_ns) / 1_000_000_000)
                predicted = track.y + (track.velocity_px_s or 0.0) * elapsed_s
                return abs(predicted - y)
            candidate = min(candidates, key=distance)
            if distance(candidate) <= self.match_distance_px:
                unmatched.remove(candidate.note_id)
                assignments.append((candidate, arrow))
                assigned_arrow_indexes.add(arrow_index)

        for track, arrow in assignments:
            _, x, y, width, height, detection = arrow
            elapsed_s = (captured_at_ns - track.last_seen_ns) / 1_000_000_000
            measured = (y - track.y) / elapsed_s if elapsed_s > 0 else track.velocity_px_s
            if measured is not None and measured > 0:
                track.velocity_px_s = measured if track.velocity_px_s is None else (1 - self.velocity_smoothing) * track.velocity_px_s + self.velocity_smoothing * measured
                self._last_scroll_speed = track.velocity_px_s
            track.x, track.y, track.width, track.height = x, y, width, height
            track.confidence = detection.confidence
            track.last_seen_ns = captured_at_ns
            track.missed_frames = 0

        for note_id in list(unmatched):
            track = self._tracks[note_id]
            track.missed_frames += 1
            if track.missed_frames > self.max_missed_frames:
                del self._tracks[note_id]

        assigned_ids = {track.note_id for track, _ in assignments}
        for arrow_index, (lane, x, y, width, height, detection) in enumerate(arrows):
            if arrow_index in assigned_arrow_indexes:
                continue
            note_id = self._next_id
            self._next_id += 1
            self._tracks[note_id] = NoteTrack(note_id, lane, y, x, width, height, detection.confidence, captured_at_ns, captured_at_ns)

        return TrackingResult(tuple(self._tracks.values()), self._receptor_y, self._last_scroll_speed, tuple(sorted(set(unsupported))))
