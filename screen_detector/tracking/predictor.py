from __future__ import annotations

from dataclasses import dataclass

from .tracker import NoteTrack, TrackingResult


@dataclass(frozen=True)
class PredictedTap:
    note_id: int
    lane: int
    target_ns: int
    y: float
    speed_px_s: float


class HitTimePredictor:
    """Converts tracked tap notes into exactly-once scheduled tap events."""

    def __init__(self, global_offset_ms: float = 0.0, pipeline_latency_ns: int = 0, lookahead_ns: int = 0, min_speed_px_s: float = 1.0) -> None:
        self.global_offset_ns = int(global_offset_ms * 1_000_000)
        self.pipeline_latency_ns = pipeline_latency_ns
        self.lookahead_ns = lookahead_ns
        self.min_speed_px_s = min_speed_px_s

    def predict(self, result: TrackingResult, captured_at_ns: int, receptor_y: float | None = None, scroll_speed_px_s: float | None = None) -> list[PredictedTap]:
        target_y = receptor_y if receptor_y is not None else result.receptor_y
        speed = scroll_speed_px_s if scroll_speed_px_s is not None else result.scroll_speed_px_s
        if target_y is None or speed is None or speed < self.min_speed_px_s:
            return []
        events: list[PredictedTap] = []
        for track in result.tracks:
            if track.scheduled or track.unsupported_reason is not None:
                continue
            track_speed = track.velocity_px_s or speed
            if track_speed < self.min_speed_px_s or track.y >= target_y:
                continue
            target_ns = captured_at_ns + int((target_y - track.y) / track_speed * 1_000_000_000) - self.pipeline_latency_ns + self.global_offset_ns
            if target_ns < captured_at_ns + self.lookahead_ns:
                continue
            track.scheduled = True
            events.append(PredictedTap(track.note_id, track.lane, target_ns, track.y, track_speed))
        return events
